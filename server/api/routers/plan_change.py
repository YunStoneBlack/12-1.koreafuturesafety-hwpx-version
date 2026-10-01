"""방문 예정 [일정 변경]·대타·담당 교체(2026-10-01) — 현장이 "내일 공사 안 해요" 할 때 폰에서 바로 옮기기.

- `GET /calendar/plans/{id}/options` — 작은 달력용 날짜 정보(그 요원이 그날 가는 현장 수·같은 지역 출장·못 가는 날) + 추천 날짜 1~3개
  (같은 지역 출장에 붙이기 → 가장 가까운 빈 평일). 옮기기는 기존 `PATCH /calendar/plans/{id}`(옮기면 📌 고정).
- `GET /calendar/plans/{id}/substitutes?date=` — 그날 대신 갈 요원(같은 지역 출장 있는 요원 → 여유 있는 요원 순). 바꾸기도 PATCH(staff_id).
- `POST /sites/{id}/plans/handover` — 현장 담당요원을 바꿀 때 앞으로의 예정도 새 담당자로(dry_run이면 건수만). replan이면 그 현장
  자동 예정을 새 담당자의 다른 현장과 같은 지역끼리 다시 짠다(📌 고정 예정은 날짜 그대로, 요원만 바뀜).
규칙(빼는 날·지역·하루 4곳)은 server/api/visit_scheduler.py와 같다.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import SiteContact, User, VisitPlan
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY as LIMIT
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.visit_scheduler import blocked_days, korean_holidays, region_of

router = APIRouter(tags=["plan-change"])
DAY = datetime.timedelta(days=1)
SUGGEST_WINDOW_DAYS = 21  # 원래 날짜 ± 이만큼에서 같은 지역 출장을 찾는다(현장은 보통 2주 간격 — 14면 바로 다음 출장을 못 잡음)


def _plan(db: Session, user: User, plan_id: int) -> VisitPlan:
    plan = db.query(VisitPlan).filter(VisitPlan.id == plan_id, VisitPlan.company_id == user.company_id).first()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "방문 예정을 찾을 수 없습니다.")
    return plan


def _regions(db: Session, sites: dict[int, Site]) -> dict[int, str]:
    va = dict(db.query(SiteContact.site_id, SiteContact.visit_address).filter(SiteContact.site_id.in_(list(sites)))) if sites else {}
    return {sid: region_of(va.get(sid) or s.address or "") for sid, s in sites.items()}


def _day_sites(db: Session, company_id: int, start: datetime.date, end: datetime.date, exclude_plan: int | None):
    """(요원, 날짜) → 그날 가는 현장들(방문 예정 + 그날 지도일로 만든 보고서)."""
    out: dict[tuple[int, datetime.date], set[int]] = defaultdict(set)
    for p in db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date >= start, VisitPlan.plan_date <= end):
        if p.id != exclude_plan and p.staff_id is not None:
            out[(p.staff_id, p.plan_date)].add(p.site_id)
    for sid, staff_id, gdate in db.query(Report.site_id, Report.assigned_staff_id, Report.guidance_date).join(Site, Site.id == Report.site_id).filter(
            Site.company_id == company_id, Report.guidance_date >= start, Report.guidance_date <= end):
        if staff_id is not None:
            out[(staff_id, gdate)].add(sid)
    return out


@router.get("/calendar/plans/{plan_id}/options")
def options(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    today = datetime.date.today()
    first = (min(plan.plan_date, today + DAY)).replace(day=1)
    end = (first + datetime.timedelta(days=95)).replace(day=1) - DAY  # 원래 날짜(또는 내일)가 있는 달부터 석 달
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == user.company_id)}
    region = _regions(db, sites)
    my_region = region.get(plan.site_id, "")
    blocked = blocked_days(first, end, korean_holidays({first.year, end.year}))
    busy = _day_sites(db, user.company_id, first, end, plan.id)

    days = []
    d = first
    while d <= end:
        here = busy.get((plan.staff_id, d), set()) if plan.staff_id is not None else set()
        same = sorted(sites[x].name for x in here if region.get(x) and region.get(x) == my_region and x != plan.site_id)
        other = any(region.get(x) and region.get(x) != my_region for x in here)
        days.append({"date": d.isoformat(), "blocked": blocked.get(d, ""), "past": d <= today, "count": len(here),
                     "same": same, "other": other, "already": plan.site_id in here})
        d += DAY

    def usable(x):
        return not x["blocked"] and not x["past"] and not x["already"] and x["count"] < LIMIT and x["date"] != plan.plan_date.isoformat()

    near = lambda x: abs((datetime.date.fromisoformat(x["date"]) - plan.plan_date).days)
    lo, hi = plan.plan_date - datetime.timedelta(days=SUGGEST_WINDOW_DAYS), plan.plan_date + datetime.timedelta(days=SUGGEST_WINDOW_DAYS)
    join = sorted((x for x in days if usable(x) and x["same"] and not x["other"]
                   and lo <= datetime.date.fromisoformat(x["date"]) <= hi), key=near)[:2]
    free = sorted((x for x in days if usable(x) and x["count"] == 0), key=lambda x: (near(x), x["date"]))
    # 같은 지역 출장에 붙이기 최대 2개 + 가장 가까운 빈 평일(붙일 데가 없으면 빈 평일 3개)
    suggestions = [{"date": x["date"], "kind": "join", "with": x["same"]} for x in join]
    suggestions += [{"date": x["date"], "kind": "free", "with": []} for x in free[:1 if join else 3]]
    staff_name = db.query(Staff.name).filter(Staff.id == plan.staff_id).scalar() if plan.staff_id else ""
    return {
        "plan": {"id": plan.id, "site_id": plan.site_id, "site_name": sites[plan.site_id].name if plan.site_id in sites else "",
                 "staff_id": plan.staff_id, "staff_name": staff_name or "", "date": plan.plan_date.isoformat(), "region": my_region},
        "limit": LIMIT, "days": days, "suggestions": suggestions,
    }


@router.get("/calendar/plans/{plan_id}/substitutes")
def substitutes(plan_id: int, date: datetime.date = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == user.company_id)}
    region = _regions(db, sites)
    my_region = region.get(plan.site_id, "")
    busy = _day_sites(db, user.company_id, date, date, plan.id)
    out = []
    for st in db.query(Staff).filter(Staff.company_id == user.company_id, Staff.active.is_(True)).order_by(Staff.id):
        if st.id == plan.staff_id:
            continue
        here = busy.get((st.id, date), set())
        same = sorted(sites[x].name for x in here if region.get(x) and region.get(x) == my_region)
        other = sorted({region.get(x) or "지역 모름" for x in here if region.get(x) != my_region})
        out.append({"staff_id": st.id, "name": st.name, "count": len(here), "same": same, "other_regions": other, "full": len(here) >= LIMIT})
    # 같은 지역 출장 있는 사람 → 그날 비어 있는 사람 → 다른 지역 출장 있는 사람(한도 찬 사람은 맨 뒤)
    out.sort(key=lambda x: (x["full"], 0 if x["same"] and not x["other_regions"] else 1 if x["count"] == 0 else 2, x["count"], x["name"]))
    return {"date": date.isoformat(), "region": my_region, "limit": LIMIT, "staff": out}


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
