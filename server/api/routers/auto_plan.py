"""지도 출장 자동 배치 API(2026-10-01) — 계산은 server/api/visit_scheduler.py, 여기는 DB에서 읽고 쓰기만.

- `POST /calendar/auto-plan/preview` — 저장 없이 "이렇게 넣겠습니다"(미리보기). body: `site_id`(그 현장만) 또는 `staff_ids`(그 요원들이 1순위인
  진행 중 현장 전부 — 1순위 = 직전 회차 보고서 담당 → 현장 담당, server/api/report_staff.py). 출장자는 그날 지역 묶음마다 고른다(2026-10-02).
- `POST /calendar/auto-plan/apply` — 같은 계산을 다시 해서 저장: 대상 현장의 "자동(auto)이면서 내일 이후" 예정을 지우고 새로 넣는다
  (보고서 담당자도 규칙대로 — report_staff.assign_new_plans).
  사람이 넣거나 옮긴 예정(manual, 📌)은 안 건드리고 기준점으로 쓴다. 현장 하나만 할 땐 다른 현장 예정은 그대로(새 현장을 기존 일정에 끼워 넣기).
- `GET /calendar/unplanned` — "📅 일정 없는 현장"(진행 중·남은 회차 있음·공사 기간 안 끝남인데 내일 이후 예정이 하나도 없음) — 현장 목록·달력 위 안내.
- `GET/POST /settings/auto-plan` — 마감(준공 며칠 전까지 마칠지, 기본 14일) + 도로 거리 기준(같은 시·군 30km·한 사람 하루 현장끼리 70km,
  server/api/geocode.py) + 하루 출장 인원(회사 전체, 기본 2명 — 비상 인력, 2026-10-02).
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import User, VisitPlan
from server.api.deps import get_current_user, get_db, is_groupware_admin
from server.api.geocode import RoadDistance, map_addresses, site_coords
from server.api.report_staff import assign_new_plans, day_cap, preferred_map, staff_order, travelers
from server.api.site_pace_out import done_counts
from server.api.site_label import site_label
from server.api.site_status import is_active
from server.api.visit_scheduler import SiteIn, plan_sites, region_of

router = APIRouter(tags=["auto-plan"])
# visit_plan.source: auto = 자동 배치, sub = 자동 배치가 넣은 "⚠ 대타 필요"(담당 없음 — 먼 현장과 섞어야만 갈 수 있는 회차), manual = 사람이 정함(📌)
AUTO_SOURCES = ("auto", "sub")


class AutoPlanIn(BaseModel):
    site_id: int | None = None
    staff_ids: list[int] | None = None


class AutoPlanSettings(BaseModel):
    finish_before_days: int = config.DEFAULT_PLAN_FINISH_BEFORE_DAYS
    far_km: float = config.DEFAULT_PLAN_FAR_KM  # 같은 시·군이라도 이보다 멀면 안 묶음
    home_address: str = config.DEFAULT_ROUTE_HOME_ADDRESS  # 동선 짜기 출발·복귀지 기본값(회사)
    trip_km: float = config.DEFAULT_PLAN_TRIP_KM  # 한 사람의 그날 현장끼리 이 안이면 시·군이 달라도 묶음(넘으면 다른 날)
    max_travelers: int = config.DEFAULT_PLAN_MAX_TRAVELERS  # 하루 출장 인원(회사 전체)


_active = is_active  # 진행중 현장만 배치(server/api/site_status.py)


def _check_admin(body: AutoPlanIn, request: Request | None) -> None:
    """요원 단위(달력 [📅 자동 배치])는 그룹웨어 관리자만(2026-10-10 사용자·민재형) — 보고 있는 요원들 현장의 자동 예정을 전부 지우고
    다시 짜는데, 그새 생긴 규칙(하루 출장 인원 등) 때문에 예정이 크게 줄 수 있다(19건 → 6건 확인). 현장 단위(새 현장)는 누구나."""
    if body.site_id is None and request is not None and not is_groupware_admin(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "요원 단위 자동 배치는 관리자만 할 수 있습니다.")


def _compute(db: Session, company_id: int, body: AutoPlanIn, today: datetime.date):
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == company_id)}
    if body.site_id is not None:
        site = sites.get(body.site_id)
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
        targets = [site] if _active(site) else []
    elif body.staff_ids:
        wanted = set(body.staff_ids)
        first = preferred_map(db, [s for s in sites.values() if _active(s)])
        targets = [s for s in sites.values() if _active(s) and first.get(s.id) in wanted]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장이나 요원을 고르세요.")
    target_ids = {s.id for s in targets}

    future = db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date > today).all()
    redo = lambda p: p.site_id in target_ids and p.source in AUTO_SOURCES  # 자동으로 넣은 것(대타 필요 포함)만 다시 짠다
    replaced = [p for p in future if redo(p)]
    kept = [p for p in future if not redo(p)]

    region = {sid: region_of(addr) for sid, addr in map_addresses(db, sites).items()}
    last_dates = dict(db.query(Report.site_id, func.max(Report.guidance_date))
                      .filter(Report.site_id.in_(list(target_ids))).group_by(Report.site_id)) if target_ids else {}  # 최근 지도일(배치 기준일)

    dist = RoadDistance(db, site_coords(db, sites))  # 현장 사이 도로 거리(카카오, 처음 묻는 쌍만 길찾기) — 거리 기준 묶기
    # 출장자·날짜별로 이미 가는 현장(남기는 예정 + 앞날짜로 만든 보고서 — 출장자 = 그날 그 현장 예정의 요원) — 묶기 기준점,
    # 날짜별 회사 전체(요원 없는 예정 포함) — 회사 하루 한도
    busy: dict[tuple[int, datetime.date], set[int]] = defaultdict(set)
    day_sites: dict[datetime.date, set[int]] = defaultdict(set)
    for p in kept:
        day_sites[p.plan_date].add(p.site_id)
        if p.staff_id is not None:
            busy[(p.staff_id, p.plan_date)].add(p.site_id)
    future_reports = db.query(Report.site_id, Report.assigned_staff_id, Report.guidance_date).filter(
        Report.site_id.in_(list(sites)), Report.guidance_date > today).all()
    if future_reports:
        went = travelers(db, company_id, today + datetime.timedelta(days=1), max(g for _, _, g in future_reports))
        for sid, staff_id, gdate in future_reports:
            day_sites[gdate].add(sid)
            who = went.get((sid, gdate), staff_id)
            if who is not None:
                busy[(who, gdate)].add(sid)

    done = done_counts(db, list(target_ids))  # 다녀온 횟수 = max(최근 보고서 회차, 첫 지도 회차 - 1)
    fixed = defaultdict(list)
    for p in kept:
        if p.site_id in target_ids:
            fixed[p.site_id].append(p.plan_date)
    first = preferred_map(db, targets)  # 1순위(직전 회차 보고서 담당 → 현장 담당) — 빈 날 새 지역을 맡을 사람·묶음 출장자 고르기
    ins = [SiteIn(
        id=s.id, name=s.name, staff_id=first.get(s.id), region=region[s.id], period_start=s.period_start, period_end=s.period_end,
        total=s.total_guidance_count, performed=done[s.id], last_date=last_dates.get(s.id), fixed=fixed[s.id],
    ) for s in targets]
    finish = config.get_plan_finish_before_days(company_id)
    placed, results = plan_sites(ins, today, busy, finish, day_cap(db, company_id), site_regions=region, dist=dist,
                                 far_km=config.get_plan_far_km(company_id), trip_km=config.get_plan_trip_km(company_id),
                                 staff_order=staff_order(db, company_id), day_sites=day_sites,
                                 max_travelers=config.get_plan_max_travelers(company_id))
    dist.save()
    return sites, region, dist, replaced, kept, placed, results, finish


def _names(db: Session, company_id: int) -> dict[int, str]:
    return dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == company_id))


@router.post("/calendar/auto-plan/preview")
def preview(body: AutoPlanIn, request: Request = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_admin(body, request)
    today = datetime.date.today()
    sites, region, dist, replaced, kept, placed, results, finish = _compute(db, user.company_id, body, today)
    names = _names(db, user.company_id)
    # 그날 같은 요원이 같이 가는 다른 현장(남기는 예정 + 이번에 넣는 것) — 미리보기에서 "누구와 함께"를 보여 준다
    day_sites: dict[tuple[int, datetime.date], set[int]] = defaultdict(set)
    for p in kept:
        if p.staff_id is not None:
            day_sites[(p.staff_id, p.plan_date)].add(p.site_id)
    for p in placed:
        if p.staff_id is not None:
            day_sites[(p.staff_id, p.date)].add(p.site_id)
    others = lambda p: sorted((x for x in day_sites.get((p.staff_id, p.date), set()) if x != p.site_id and x in sites), key=lambda x: site_label(sites[x]))
    km_of = lambda a, b: round(d, 1) if (d := dist(a, b)) is not None else None  # "○○(4km)와 함께" — 도로 거리
    return {
        "today": today.isoformat(),
        "finish_before_days": finish,
        "replace_count": len(replaced),
        "plans": [{"date": p.date.isoformat(), "site_id": p.site_id, "site_name": site_label(sites[p.site_id]), "region": region[p.site_id],
                   "staff_id": p.staff_id, "staff_name": names.get(p.staff_id, ""), "need_sub": p.need_sub,
                   "owner_name": names.get(sites[p.site_id].assigned_staff_id, ""), "with": [site_label(sites[x]) for x in others(p)],
                   "with_km": [km_of(p.site_id, x) for x in others(p)]} for p in placed],
        "sites": [{"site_id": r.site_id, "site_name": site_label(sites[r.site_id]), "staff_name": names.get(sites[r.site_id].assigned_staff_id, ""),
                   "region": region[r.site_id], "needed": r.needed, "placed": r.placed, "need_sub": r.need_sub, "note": r.note} for r in results],
    }


@router.post("/calendar/auto-plan/apply")
def apply(body: AutoPlanIn, request: Request = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_admin(body, request)
    today = datetime.date.today()
    sites, _, _, replaced, _, placed, results, _ = _compute(db, user.company_id, body, today)
    names = _names(db, user.company_id)
    for p in replaced:
        db.delete(p)
    added = []
    for p in placed:
        owner = names.get(sites[p.site_id].assigned_staff_id, "")
        plan = VisitPlan(company_id=user.company_id, site_id=p.site_id, staff_id=p.staff_id, plan_date=p.date,
                         memo=f"거리가 멀어 대타 필요 — 원 담당 {owner}" if p.need_sub else "",
                         source="sub" if p.need_sub else "auto", created_by=user.display_name or "")
        db.add(plan)
        added.append(plan)
    assign_new_plans(db, user.company_id, added)  # 보고서 담당자(한 사람 하루 4곳, 넘치면 순서대로)
    db.commit()
    return {"ok": True, "added": len(placed), "removed": len(replaced), "need_sub": sum(p.need_sub for p in placed),
            "short": sum(1 for r in results if "넣을 날" in r.note)}


@router.get("/calendar/unplanned")
def unplanned(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    sites = [s for s in db.query(Site).filter(Site.company_id == user.company_id) if _active(s)
             and s.total_guidance_count and s.period_end and s.period_end > today]
    if not sites:
        return []
    ids = [s.id for s in sites]
    planned = {sid for (sid,) in db.query(VisitPlan.site_id).filter(VisitPlan.site_id.in_(ids), VisitPlan.plan_date > today).distinct()}
    last = done_counts(db, ids)
    names = _names(db, user.company_id)
    return sorted(
        ({"site_id": s.id, "site_name": site_label(s), "staff_id": s.assigned_staff_id, "staff_name": names.get(s.assigned_staff_id, ""),
          "remaining": s.total_guidance_count - (last.get(s.id) or 0)}
         for s in sites if s.id not in planned and s.total_guidance_count > (last.get(s.id) or 0)),
        key=lambda x: (x["staff_name"], x["site_name"]),
    )


@router.get("/settings/auto-plan", response_model=AutoPlanSettings)
def get_settings(user: User = Depends(get_current_user)):
    cid = user.company_id
    return AutoPlanSettings(finish_before_days=config.get_plan_finish_before_days(cid), far_km=config.get_plan_far_km(cid),
                            trip_km=config.get_plan_trip_km(cid), max_travelers=config.get_plan_max_travelers(cid),
                            home_address=config.get_route_home_address(cid))


@router.post("/settings/auto-plan", response_model=AutoPlanSettings)
def set_settings(body: AutoPlanSettings, user: User = Depends(get_current_user)):
    if not 0 <= body.finish_before_days <= 180:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "0~180일 사이로 정하세요.")
    if not (0 < body.far_km <= 200 and 0 < body.trip_km <= 300):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "거리 기준을 확인하세요(같은 시·군 0~200km, 한 사람 하루 현장끼리 0~300km).")
    if not 1 <= body.max_travelers <= 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "하루 출장 인원은 1명 이상으로 정하세요.")
    config.set_plan_finish_before_days(body.finish_before_days, user.company_id)
    config.set_plan_far_km(body.far_km, user.company_id)
    config.set_plan_trip_km(body.trip_km, user.company_id)
    config.set_plan_max_travelers(body.max_travelers, user.company_id)
    if body.home_address.strip():
        config.set_route_home_address(body.home_address, user.company_id)
    return get_settings(user)
