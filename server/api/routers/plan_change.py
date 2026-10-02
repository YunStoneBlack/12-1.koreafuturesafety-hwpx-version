"""방문 예정 [일정 변경]·대타·담당 교체(2026-10-01) — 현장이 "내일 공사 안 해요" 할 때 폰에서 바로 옮기기.

- `GET /calendar/plans/{id}/options` — 작은 달력용 날짜 정보(그 요원이 그날 가는 현장 수·같은 지역 출장·못 가는 날) + 추천 날짜 1~3개
  (같은 지역 출장에 붙이기 → 가장 가까운 빈 평일). 옮기기는 기존 `PATCH /calendar/plans/{id}`(옮기면 📌 고정).
- `GET /calendar/plans/{id}/substitutes?date=` — 그날 대신 갈 요원(같은 지역 출장 있는 요원 → 여유 있는 요원 순). 바꾸기도 PATCH(staff_id).
- `POST /sites/{id}/plans/handover` — 현장 담당요원을 바꿀 때 앞으로의 예정도 새 담당자로(dry_run이면 건수만). replan이면 그 현장
  자동 예정을 새 담당자의 다른 현장과 같은 지역끼리 다시 짠다(📌 고정 예정은 날짜 그대로, 요원만 바뀜).
- `POST /sites/{id}/status` — 공사 상태(착공전·진행중·공사중지·준공, server/api/site_status.py) 바꾸기. 진행중이 아니게 되면 그 현장의
  내일 이후 예정을 전부(📌 포함) 지운다. dry_run이면 지울 건수만.
규칙(빼는 날·지역)은 server/api/visit_scheduler.py와 같다. 출장은 한 사람 한도 없음 — 회사 하루 한도(요원 수 × 4, report_staff.day_cap)만(2026-10-02).
그날 요원이 가는 현장 = 그 요원의 예정 + 그날 보고서(출장자 = 그날 그 현장 예정의 요원, 없으면 보고서 담당).
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import User, VisitPlan
from server.api import repo
from server.api.deps import get_current_user, get_db
from core import config
from server.api.geocode import RoadDistance, map_addresses, site_coords
from server.api.site_label import site_label
from server.api.report_staff import day_cap, travelers
from server.api.site_status import ACTIVE, STATUSES
from server.api.visit_scheduler import FAR, blocked_days, korean_holidays, make_compat, region_of

router = APIRouter(tags=["plan-change"])
DAY = datetime.timedelta(days=1)
SUGGEST_WINDOW_DAYS = 21  # 원래 날짜 ± 이만큼에서 같은 지역 출장을 찾는다(현장은 보통 2주 간격 — 14면 바로 다음 출장을 못 잡음)


def _plan(db: Session, user: User, plan_id: int) -> VisitPlan:
    plan = db.query(VisitPlan).filter(VisitPlan.id == plan_id, VisitPlan.company_id == user.company_id).first()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "방문 예정을 찾을 수 없습니다.")
    return plan


def _compat(db: Session, company_id: int, sites: dict[int, Site]):
    """(현장 → 시·군, 두 현장 궁합 함수, 도로 거리) — 자동 배치와 같은 기준(같은 시·군 30km·다른 시·군 12km 도로 거리, 좌표 없으면 시·군)."""
    region = {sid: region_of(addr) for sid, addr in map_addresses(db, sites).items()}
    dist = RoadDistance(db, site_coords(db, sites))
    compat = make_compat(region, dist, config.get_plan_far_km(company_id), config.get_plan_near_km(company_id))
    return region, compat, dist


def _together(sites: dict[int, Site], compat, me: int, here: set[int]):
    """그날 가는 현장들 중 같이 가도 되는 것(이름·거리 km)과 먼 현장이 섞였는지."""
    ok, far = [], False
    for x in sorted(here - {me}, key=lambda x: site_label(sites[x]) if x in sites else ""):
        kind, dist = compat(me, x)
        if kind == FAR:
            far = True
        elif x in sites:
            ok.append((site_label(sites[x]), round(dist, 1) if dist is not None else None))
    return ok, far


def _day_sites(db: Session, company_id: int, start: datetime.date, end: datetime.date, exclude_plan: int | None):
    """((요원, 날짜) → 그날 가는 현장들, 날짜 → 회사 전체 현장들) — 방문 예정 + 그날 지도일로 만든 보고서(실제 출장자 기준)."""
    out: dict[tuple[int, datetime.date], set[int]] = defaultdict(set)
    total: dict[datetime.date, set[int]] = defaultdict(set)
    for p in db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date >= start, VisitPlan.plan_date <= end):
        if p.id != exclude_plan:
            total[p.plan_date].add(p.site_id)
            if p.staff_id is not None:
                out[(p.staff_id, p.plan_date)].add(p.site_id)
    went = travelers(db, company_id, start, end)
    for sid, staff_id, gdate in db.query(Report.site_id, Report.assigned_staff_id, Report.guidance_date).join(Site, Site.id == Report.site_id).filter(
            Site.company_id == company_id, Report.guidance_date >= start, Report.guidance_date <= end):
        total[gdate].add(sid)
        who = went.get((sid, gdate), staff_id)
        if who is not None:
            out[(who, gdate)].add(sid)
    return out, total


@router.get("/calendar/plans/{plan_id}/options")
def options(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    today = datetime.date.today()
    first = (min(plan.plan_date, today + DAY)).replace(day=1)
    end = (first + datetime.timedelta(days=95)).replace(day=1) - DAY  # 원래 날짜(또는 내일)가 있는 달부터 석 달
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == user.company_id)}
    region, compat, dist = _compat(db, user.company_id, sites)
    my_region = region.get(plan.site_id, "")
    blocked = blocked_days(first, end, korean_holidays({first.year, end.year}))
    busy, total = _day_sites(db, user.company_id, first, end, plan.id)
    cap = day_cap(db, user.company_id)

    days = []
    d = first
    while d <= end:
        here = busy.get((plan.staff_id, d), set()) if plan.staff_id is not None else set()
        ok, far = _together(sites, compat, plan.site_id, here)
        days.append({"date": d.isoformat(), "blocked": blocked.get(d, ""), "past": d <= today, "count": len(here),
                     "total": len(total.get(d, set())), "full": len(total.get(d, set()) - {plan.site_id}) >= cap,
                     "same": [n for n, _ in ok], "same_km": [k for _, k in ok], "other": far, "already": plan.site_id in here})
        d += DAY

    def usable(x):
        return not x["blocked"] and not x["past"] and not x["already"] and not x["full"] and x["date"] != plan.plan_date.isoformat()

    near = lambda x: abs((datetime.date.fromisoformat(x["date"]) - plan.plan_date).days)
    lo, hi = plan.plan_date - datetime.timedelta(days=SUGGEST_WINDOW_DAYS), plan.plan_date + datetime.timedelta(days=SUGGEST_WINDOW_DAYS)
    join = sorted((x for x in days if usable(x) and x["same"] and not x["other"]
                   and lo <= datetime.date.fromisoformat(x["date"]) <= hi), key=near)[:2]
    free = sorted((x for x in days if usable(x) and x["count"] == 0), key=lambda x: (near(x), x["date"]))
    # 같은 지역 출장에 붙이기 최대 2개 + 가장 가까운 빈 평일(붙일 데가 없으면 빈 평일 3개)
    suggestions = [{"date": x["date"], "kind": "join", "with": x["same"], "with_km": x["same_km"]} for x in join]
    suggestions += [{"date": x["date"], "kind": "free", "with": []} for x in free[:1 if join else 3]]
    staff_name = db.query(Staff.name).filter(Staff.id == plan.staff_id).scalar() if plan.staff_id else ""
    dist.save()  # 이번에 새로 물은 도로 거리 저장
    return {
        "plan": {"id": plan.id, "site_id": plan.site_id, "site_name": site_label(sites[plan.site_id]) if plan.site_id in sites else "",
                 "staff_id": plan.staff_id, "staff_name": staff_name or "", "date": plan.plan_date.isoformat(), "region": my_region},
        "day_cap": cap, "days": days, "suggestions": suggestions,
    }


@router.get("/calendar/plans/{plan_id}/substitutes")
def substitutes(plan_id: int, date: datetime.date = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == user.company_id)}
    region, compat, dist = _compat(db, user.company_id, sites)
    my_region = region.get(plan.site_id, "")
    busy, _ = _day_sites(db, user.company_id, date, date, plan.id)
    out = []
    for st in db.query(Staff).filter(Staff.company_id == user.company_id, Staff.active.is_(True)).order_by(Staff.id):
        if st.id == plan.staff_id:
            continue
        here = busy.get((st.id, date), set())
        ok, _ = _together(sites, compat, plan.site_id, here)
        other = sorted({region.get(x) or "지역 모름" for x in here if compat(plan.site_id, x)[0] == FAR})
        out.append({"staff_id": st.id, "name": st.name, "count": len(here), "same": [n for n, _ in ok], "same_km": [k for _, k in ok],
                    "other_regions": other})
    # 같은 지역 출장 있는 사람 → 그날 비어 있는 사람 → 다른 지역 출장 있는 사람(출장은 한 사람 한도 없음 — 2026-10-02)
    out.sort(key=lambda x: (0 if x["same"] and not x["other_regions"] else 1 if x["count"] == 0 else 2, x["count"], x["name"]))
    dist.save()
    return {"date": date.isoformat(), "region": my_region, "staff": out}


class HandoverIn(BaseModel):
    to_staff_id: int | None = None
    replan: bool = False
    dry_run: bool = False


@router.post("/sites/{site_id}/plans/handover")
def handover(site_id: int, body: HandoverIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    if body.to_staff_id is not None and repo.get_staff(db, user.company_id, body.to_staff_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "담당요원을 찾을 수 없습니다.")
    today = datetime.date.today()
    plans = db.query(VisitPlan).filter(VisitPlan.site_id == site_id, VisitPlan.plan_date > today,
                                       VisitPlan.staff_id.is_distinct_from(body.to_staff_id)).all()
    if body.dry_run:
        return {"count": len(plans), "auto": sum(p.source == "auto" for p in plans)}
    for p in plans:
        p.staff_id = body.to_staff_id
    db.commit()
    moved = len(plans)
    replanned = None
    if body.replan:
        from server.api.routers.auto_plan import AutoPlanIn
        from server.api.routers.auto_plan import apply as auto_apply

        replanned = auto_apply(AutoPlanIn(site_id=site_id), user, db)
    return {"ok": True, "moved": moved, "replanned": replanned}


class SiteStatusIn(BaseModel):
    status: str
    dry_run: bool = False


@router.post("/sites/{site_id}/status")
def set_site_status(site_id: int, body: SiteStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    if body.status not in STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"상태는 {'·'.join(STATUSES)} 중 하나입니다.")
    plans = []
    if body.status != ACTIVE:
        plans = db.query(VisitPlan).filter(VisitPlan.site_id == site_id,
                                           VisitPlan.plan_date > datetime.date.today()).all()
    if body.dry_run:
        return {"plans": len(plans)}
    site.status = body.status
    for p in plans:
        db.delete(p)
    db.commit()
    return {"ok": True, "status": site.status, "deleted_plans": len(plans)}
