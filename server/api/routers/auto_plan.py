"""지도 출장 자동 배치 API(2026-10-01) — 계산은 server/api/visit_scheduler.py, 여기는 DB에서 읽고 쓰기만.

- `POST /calendar/auto-plan/preview` — 저장 없이 "이렇게 넣겠습니다"(미리보기). body: `site_id`(그 현장만) 또는 `staff_ids`(그 요원들의 진행 중 현장 전부).
- `POST /calendar/auto-plan/apply` — 같은 계산을 다시 해서 저장: 대상 현장의 "자동(auto)이면서 내일 이후" 예정을 지우고 새로 넣는다.
  사람이 넣거나 옮긴 예정(manual, 📌)은 안 건드리고 기준점으로 쓴다. 현장 하나만 할 땐 다른 현장 예정은 그대로(새 현장을 기존 일정에 끼워 넣기).
- `GET /calendar/unplanned` — "📅 일정 없는 현장"(진행 중·남은 회차 있음·공사 기간 안 끝남인데 내일 이후 예정이 하나도 없음) — 현장 목록·달력 위 안내.
- `GET/POST /settings/auto-plan` — 마감(준공 며칠 전까지 마칠지, 기본 14일) + 도로 거리 기준(같은 시·군 30km·다른 시·군 12km, server/api/geocode.py).
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import SiteContact, User, VisitPlan
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY
from server.api.deps import get_current_user, get_db
from server.api.geocode import RoadDistance, site_coords
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
    near_km: float = config.DEFAULT_PLAN_NEAR_KM  # 다른 시·군이라도 이보다 가까우면 자리 없을 때 묶음


def _active(site: Site) -> bool:
    return (site.status or "진행중") == "진행중"


def _compute(db: Session, company_id: int, body: AutoPlanIn, today: datetime.date):
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == company_id)}
    if body.site_id is not None:
        site = sites.get(body.site_id)
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
        targets = [site] if _active(site) else []
    elif body.staff_ids:
        wanted = set(body.staff_ids)
        targets = [s for s in sites.values() if _active(s) and s.assigned_staff_id in wanted]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장이나 요원을 고르세요.")
    target_ids = {s.id for s in targets}

    future = db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date > today).all()
    redo = lambda p: p.site_id in target_ids and p.source in AUTO_SOURCES  # 자동으로 넣은 것(대타 필요 포함)만 다시 짠다
    replaced = [p for p in future if redo(p)]
    kept = [p for p in future if not redo(p)]

    visit_addr = dict(db.query(SiteContact.site_id, SiteContact.visit_address).filter(SiteContact.site_id.in_(list(sites)))) if sites else {}
    region = {sid: region_of(visit_addr.get(sid) or s.address or "") for sid, s in sites.items()}
    stats = {
        sid: (no or 0, last)
        for sid, no, last in db.query(Report.site_id, func.max(Report.visit_no), func.max(Report.guidance_date))
        .filter(Report.site_id.in_(list(target_ids))).group_by(Report.site_id)
    } if target_ids else {}

    dist = RoadDistance(db, site_coords(db, sites))  # 현장 사이 도로 거리(카카오, 처음 묻는 쌍만 길찾기) — 거리 기준 묶기
    # 요원·날짜별로 이미 가는 현장(남기는 예정 + 앞날짜로 만든 보고서) — 묶기 기준점
    busy: dict[tuple[int, datetime.date], set[int]] = defaultdict(set)
    for p in kept:
        if p.staff_id is not None:
            busy[(p.staff_id, p.plan_date)].add(p.site_id)
    for sid, staff_id, gdate in db.query(Report.site_id, Report.assigned_staff_id, Report.guidance_date).filter(
            Report.site_id.in_(list(sites)), Report.guidance_date > today):
        if staff_id is not None:
            busy[(staff_id, gdate)].add(sid)

    fixed = defaultdict(list)
    for p in kept:
        if p.site_id in target_ids:
            fixed[p.site_id].append(p.plan_date)
    ins = [SiteIn(
        id=s.id, name=s.name, staff_id=s.assigned_staff_id, region=region[s.id], period_start=s.period_start, period_end=s.period_end,
        total=s.total_guidance_count, performed=stats.get(s.id, (0, None))[0], last_date=stats.get(s.id, (0, None))[1], fixed=fixed[s.id],
    ) for s in targets]
    finish = config.get_plan_finish_before_days(company_id)
    placed, results = plan_sites(ins, today, busy, finish, MAX_SITES_PER_STAFF_PER_DAY, site_regions=region, dist=dist,
                                 far_km=config.get_plan_far_km(company_id), near_km=config.get_plan_near_km(company_id))
    dist.save()
    return sites, region, dist, replaced, kept, placed, results, finish


def _names(db: Session, company_id: int) -> dict[int, str]:
    return dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == company_id))


@router.post("/calendar/auto-plan/preview")
def preview(body: AutoPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
    others = lambda p: sorted((x for x in day_sites.get((p.staff_id, p.date), set()) if x != p.site_id and x in sites), key=lambda x: sites[x].name)
    km_of = lambda a, b: round(d, 1) if (d := dist(a, b)) is not None else None  # "○○(4km)와 함께" — 도로 거리
    return {
        "today": today.isoformat(),
        "finish_before_days": finish,
        "replace_count": len(replaced),
        "plans": [{"date": p.date.isoformat(), "site_id": p.site_id, "site_name": sites[p.site_id].name, "region": region[p.site_id],
                   "staff_id": p.staff_id, "staff_name": names.get(p.staff_id, ""), "need_sub": p.need_sub,
                   "owner_name": names.get(sites[p.site_id].assigned_staff_id, ""), "with": [sites[x].name for x in others(p)],
                   "with_km": [km_of(p.site_id, x) for x in others(p)]} for p in placed],
        "sites": [{"site_id": r.site_id, "site_name": sites[r.site_id].name, "staff_name": names.get(sites[r.site_id].assigned_staff_id, ""),
                   "region": region[r.site_id], "needed": r.needed, "placed": r.placed, "need_sub": r.need_sub, "note": r.note} for r in results],
    }


@router.post("/calendar/auto-plan/apply")
def apply(body: AutoPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    sites, _, _, replaced, _, placed, results, _ = _compute(db, user.company_id, body, today)
    names = _names(db, user.company_id)
    for p in replaced:
        db.delete(p)
    for p in placed:
        owner = names.get(sites[p.site_id].assigned_staff_id, "")
        db.add(VisitPlan(company_id=user.company_id, site_id=p.site_id, staff_id=p.staff_id, plan_date=p.date,
                         memo=f"거리가 멀어 대타 필요 — 원 담당 {owner}" if p.need_sub else "",
                         source="sub" if p.need_sub else "auto", created_by=user.display_name or ""))
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
    last = dict(db.query(Report.site_id, func.max(Report.visit_no)).filter(Report.site_id.in_(ids)).group_by(Report.site_id))
    names = _names(db, user.company_id)
    return sorted(
        ({"site_id": s.id, "site_name": s.name, "staff_id": s.assigned_staff_id, "staff_name": names.get(s.assigned_staff_id, ""),
          "remaining": s.total_guidance_count - (last.get(s.id) or 0)}
         for s in sites if s.id not in planned and s.total_guidance_count > (last.get(s.id) or 0)),
        key=lambda x: (x["staff_name"], x["site_name"]),
    )


@router.get("/settings/auto-plan", response_model=AutoPlanSettings)
def get_settings(user: User = Depends(get_current_user)):
    cid = user.company_id
    return AutoPlanSettings(finish_before_days=config.get_plan_finish_before_days(cid), far_km=config.get_plan_far_km(cid),
                            near_km=config.get_plan_near_km(cid), home_address=config.get_route_home_address(cid))


@router.post("/settings/auto-plan", response_model=AutoPlanSettings)
def set_settings(body: AutoPlanSettings, user: User = Depends(get_current_user)):
    if not 0 <= body.finish_before_days <= 180:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "0~180일 사이로 정하세요.")
    if not (0 < body.near_km <= 100 and 0 < body.far_km <= 200):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "거리 기준을 확인하세요(다른 시·군 0~100km, 같은 시·군 0~200km).")
    config.set_plan_finish_before_days(body.finish_before_days, user.company_id)
    config.set_plan_far_km(body.far_km, user.company_id)
    config.set_plan_near_km(body.near_km, user.company_id)
    if body.home_address.strip():
        config.set_route_home_address(body.home_address, user.company_id)
    return get_settings(user)
