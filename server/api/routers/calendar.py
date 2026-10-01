"""방문 달력(2026-09-30, 시안 (나) — 다녀온 방문 + 방문 예정).

- `GET /calendar?start=&end=` — 그 기간의 다녀온 방문(보고서 지도일), 방문 예정, 요원 목록·지금 로그인한
  사람의 요원(나만 보기), 요원·날짜별 현장 수(하루 4곳 한도, 다녀온 방문 + 아직 안 다녀온 예정 — 같은 현장은 1곳).
- 예정 상태: 그 현장·그 날짜 보고서가 있으면 done(달력엔 다녀온 방문으로만 보임), 날짜가 지났는데 없으면 missed(지난 예정), 아니면 planned.
- (2026-10-01 "마지막 지도일 + 15일" 지도 기한·⚠ 예정없음은 없앰 — 실제 규칙이 아니었음.)
- `POST/PATCH/DELETE /calendar/plans` — 누구나 누구의 예정이든 넣고 고친다(사용자 결정). 하루 4곳을 넘겨도 막지 않고 화면이 경고만 한다.
  사람이 넣은 예정, 자동 배치 예정의 날짜·현장·요원을 사람이 바꾼 것은 source=manual(📌 고정 — 자동 배치가 안 건드림, routers/auto_plan.py).
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import Report, Site, Staff
from core.models_web import SiteContact, User, VisitPlan
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.site_pace_out import last_visit_nos, pace_dict
from server.api.routers.staff_groupware import my_staff_id
from server.api.submission import report_states

router = APIRouter(prefix="/calendar", tags=["calendar"])

MAX_RANGE_DAYS = 62  # 달력 한 화면(앞뒤 주 포함 6주) + 여유


class PlanIn(BaseModel):
    site_id: int | None = None
    staff_id: int | None = None
    plan_date: datetime.date | None = None
    memo: str | None = None


def _plan_out(p: VisitPlan, site: Site, state: str) -> dict:
    # owner_staff_id = 현장 담당요원 — "⚠ 대타 필요"(source=sub, 요원 비어 있음)도 그 담당자를 볼 때 보이게
    return {"id": p.id, "site_id": p.site_id, "site_name": site.name, "staff_id": p.staff_id, "owner_staff_id": site.assigned_staff_id,
            "date": p.plan_date.isoformat(), "memo": p.memo, "state": state, "source": p.source or "manual"}


@router.get("")
def calendar(
    start: datetime.date = Query(...),
    end: datetime.date = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "기간이 너무 깁니다.")
    today = datetime.date.today()
    cid = user.company_id
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == cid)}
    staff = db.query(Staff).filter(Staff.company_id == cid).order_by(Staff.id).all()

    reports = (
        db.query(Report)
        .filter(Report.site_id.in_(list(sites)), Report.guidance_date >= start, Report.guidance_date <= end)
        .all()
        if sites else []
    )
    states = report_states(db, reports)
    visits = [{
        "report_id": r.id, "site_id": r.site_id, "site_name": sites[r.site_id].name, "visit_no": r.visit_no,
        "date": r.guidance_date.isoformat(), "staff_id": r.assigned_staff_id, "state": states[r.id]["state"],
    } for r in reports]
    visited = {(r.site_id, r.guidance_date) for r in reports}

    plans_q = db.query(VisitPlan).filter(VisitPlan.company_id == cid, VisitPlan.plan_date >= start, VisitPlan.plan_date <= end)
    plans = []
    for p in plans_q:
        if p.site_id not in sites:
            continue
        state = "done" if (p.site_id, p.plan_date) in visited else ("missed" if p.plan_date < today else "planned")
        plans.append(_plan_out(p, sites[p.site_id], state))

    # 하루 현장 수 — 요원·날짜별 서로 다른 현장(다녀온 방문 + 아직 안 다녀온 예정)
    load: dict[tuple[int, str], set[int]] = defaultdict(set)
    for v in visits:
        if v["staff_id"]:
            load[(v["staff_id"], v["date"])].add(v["site_id"])
    for p in plans:
        if p["staff_id"] and p["state"] != "done":
            load[(p["staff_id"], p["date"])].add(p["site_id"])
    day_load = [{"staff_id": sid, "date": d, "count": len(s)} for (sid, d), s in load.items()]

    last_nos = last_visit_nos(db, list(sites))
    visit_addr = dict(db.query(SiteContact.site_id, SiteContact.visit_address).filter(SiteContact.site_id.in_(list(sites)))) if sites else {}
    return {
        "today": today.isoformat(),
        # 현장별 [📞 전화]·[📍 지도](현장책임자 연락처, 지도 방문 주소 — 없으면 현장 주소) + 진행 막대(pace)
        "site_links": {
            s.id: {"phone": (s.manager_phone or "").strip(), "map_address": (visit_addr.get(s.id) or s.address or "").strip(),
                   "pace": pace_dict(s, last_nos.get(s.id))}
            for s in sites.values()
        },
        "limit": MAX_SITES_PER_STAFF_PER_DAY,
        "staff": [{"id": s.id, "name": s.name, "active": s.active} for s in staff],
        "me_staff_id": my_staff_id(db, user),
        "sites": sorted(
            [{"id": s.id, "name": s.name, "staff_id": s.assigned_staff_id} for s in sites.values()
             if (s.status or "진행중") == "진행중"],
            key=lambda s: s["name"],
        ),
        "visits": visits,
        "plans": plans,
        "day_load": day_load,
    }


def _require_plan(db: Session, user: User, plan_id: int) -> VisitPlan:
    plan = db.query(VisitPlan).filter(VisitPlan.id == plan_id, VisitPlan.company_id == user.company_id).first()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "방문 예정을 찾을 수 없습니다.")
    return plan


def _check_refs(db: Session, user: User, site_id: int | None, staff_id: int | None) -> None:
    if site_id is not None and repo.get_site(db, user.company_id, site_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    if staff_id is not None and repo.get_staff(db, user.company_id, staff_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "담당요원을 찾을 수 없습니다.")


@router.post("/plans")
def add_plan(body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.site_id is None or body.plan_date is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장과 날짜를 고르세요.")
    _check_refs(db, user, body.site_id, body.staff_id)
    plan = VisitPlan(
        company_id=user.company_id, site_id=body.site_id, staff_id=body.staff_id, plan_date=body.plan_date,
        memo=(body.memo or "").strip(), created_by=user.display_name or "",
    )
    db.add(plan)
    db.commit()
    return {"id": plan.id}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _require_plan(db, user, plan_id)
    fields = body.model_dump(exclude_unset=True)
    _check_refs(db, user, fields.get("site_id"), fields.get("staff_id"))
    if fields.get("site_id") is not None:
        plan.site_id = fields["site_id"]
    if "staff_id" in fields:
        plan.staff_id = fields["staff_id"]
    if fields.get("plan_date") is not None:
        plan.plan_date = fields["plan_date"]
    if "memo" in fields:
        plan.memo = (fields["memo"] or "").strip()
    if plan.source == "sub" and fields.get("staff_id") and "memo" not in fields:  # "⚠ 대타 필요"에 대신 갈 요원을 정함
        plan.memo = (plan.memo or "").replace("거리가 멀어 대타 필요 — 원 담당", "대타 · 원 담당")
    if {"site_id", "staff_id", "plan_date"} & fields.keys():
        plan.source = "manual"  # 사람이 옮기거나 바꾼 예정은 고정
    db.commit()
    return {"ok": True}


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_require_plan(db, user, plan_id))
    db.commit()
    return {"ok": True}
