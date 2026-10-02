"""방문 달력(2026-09-30, 시안 (나) — 다녀온 방문 + 방문 예정).

- `GET /calendar?start=&end=` — 그 기간의 다녀온 방문(보고서 지도일), 방문 예정, 요원 목록·지금 로그인한
  사람의 요원(나만 보기), 요원·날짜별 출장 현장 수, 날짜별 회사 전체 현장 수(한도 = 요원 수 × 4, 다녀온 방문 + 아직 안 다녀온 예정 — 같은 현장은 1곳).
- 2026-10-02 출장자 ≠ 보고서 담당자(server/api/report_staff.py): 달력의 요원은 **실제 출장자**(예정의 staff_id, 다녀온 방문은 그날 그 현장 예정의
  요원 — 예정이 없으면 보고서 담당), 카드에 보고서 담당자(report_staff_id — 예정은 미리 정해 둔 사람, 다녀온 방문은 보고서 담당요원).
- 예정 상태: 그 현장·그 날짜 보고서가 있으면 done(달력엔 다녀온 방문으로만 보임), 날짜가 지났는데 없으면 missed(지난 예정), 아니면 planned.
- (2026-10-01 "마지막 지도일 + 15일" 지도 기한·⚠ 예정없음은 없앰 — 실제 규칙이 아니었음.)
- `POST/PATCH/DELETE /calendar/plans` — 누구나 누구의 예정이든 넣고 고친다(사용자 결정). 출장은 한 사람 한도 없음, 회사 하루 한도를 넘겨도 막지 않고
  화면이 경고만 한다. 보고서 담당자는 넣을 때 규칙대로 정하고(report_staff.assign_new_plans), 사람이 바꿀 땐 한 사람 하루 4곳을 넘으면 막는다.
- `POST /calendar/day/{date}/report-staff` — [📝 보고서 담당 다시 나누기](dry_run이면 바뀔 것만). `POST /calendar/day/{date}/move` — [출장 담당자 변경]
  (그날 한 사람의 예정 여러 곳을 다른 사람에게 — 📌 고정, 보고서 담당자는 그대로).
  사람이 넣은 예정, 자동 배치 예정의 날짜·현장·요원을 사람이 바꾼 것은 source=manual(📌 고정 — 자동 배치가 안 건드림, routers/auto_plan.py).
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import User, VisitPlan
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY
from server.api import repo
from server.api.report_staff import (assign_new_plans, day_cap, free_names, has_room, paper_load, redistribute, staff_order,
                                     travelers)
from server.api.deps import get_current_user, get_db
from server.api.site_pace_out import done_counts, pace_dict
from server.api.geocode import map_addresses
from server.api.site_label import site_label
from server.api.site_status import is_active
from server.api.routers.staff_groupware import my_staff_id
from server.api.submission import report_states
from server.api.visit_scheduler import region_of

router = APIRouter(prefix="/calendar", tags=["calendar"])

MAX_RANGE_DAYS = 62  # 달력 한 화면(앞뒤 주 포함 6주) + 여유


class PlanIn(BaseModel):
    site_id: int | None = None
    staff_id: int | None = None  # 실제 출장자
    report_staff_id: int | None = None  # 보고서 담당자
    plan_date: datetime.date | None = None
    memo: str | None = None


def _plan_out(p: VisitPlan, site: Site, state: str) -> dict:
    # owner_staff_id = 현장 담당요원 — "⚠ 대타 필요"(source=sub, 요원 비어 있음)도 그 담당자를 볼 때 보이게
    return {"id": p.id, "site_id": p.site_id, "site_name": site_label(site), "staff_id": p.staff_id, "owner_staff_id": site.assigned_staff_id,
            "report_staff_id": p.report_staff_id,
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
    went = travelers(db, cid, start, end)  # 다녀온 방문의 실제 출장자 = 그날 그 현장 예정의 요원(없으면 보고서 담당)
    visits = [{
        "report_id": r.id, "site_id": r.site_id, "site_name": site_label(sites[r.site_id]), "visit_no": r.visit_no,
        "date": r.guidance_date.isoformat(), "staff_id": went.get((r.site_id, r.guidance_date), r.assigned_staff_id),
        "report_staff_id": r.assigned_staff_id, "state": states[r.id]["state"],
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
    total: dict[str, set[int]] = defaultdict(set)  # 날짜 → 회사 전체 출장 현장(요원 없는 "대타 필요"도)
    for v in visits:
        total[v["date"]].add(v["site_id"])
    for p in plans:
        if p["state"] != "done":
            total[p["date"]].add(p["site_id"])

    last_nos = done_counts(db, list(sites))  # 다녀온 횟수(첫 지도 회차 반영)
    map_addr = map_addresses(db, sites)
    return {
        "today": today.isoformat(),
        # 현장별 [📞 전화]·[📍 지도](현장책임자 연락처, 지도 방문 주소 — 없으면 현장 주소) + 진행 막대(pace)
        "site_links": {
            s.id: {"phone": (s.manager_phone or "").strip(), "map_address": map_addr[s.id],
                   # 시·군("포천시" → "포천") — 그날 요원 상자 머리줄 "📍포천·연천"(폰은 주소가 안 보여 어디 가는지 모름, 2026-10-02 사용자)
                   "region": short_region(map_addr[s.id]),
                   "pace": pace_dict(s, last_nos.get(s.id))}
            for s in sites.values()
        },
        "report_limit": MAX_SITES_PER_STAFF_PER_DAY,  # 보고서 담당 한 사람 하루
        "day_cap": day_cap(db, cid),  # 회사 하루 출장(요원 수 × 4)
        "day_total": {d: len(x) for d, x in total.items()},
        "max_travelers": config.get_plan_max_travelers(cid),  # 하루 출장 인원(회사 전체, 비상 인력 — 2026-10-02)
        "day_travelers": {d: len({sid for (sid, dd) in load if dd == d}) for d in total},
        "staff": [{"id": s.id, "name": s.name, "active": s.active} for s in staff],
        "staff_order": staff_order(db, cid),
        "me_staff_id": my_staff_id(db, user),
        "sites": sorted(
            [{"id": s.id, "name": site_label(s), "staff_id": s.assigned_staff_id} for s in sites.values()
             if is_active(s)],
            key=lambda s: s["name"],
        ),
        "visits": visits,
        "plans": plans,
        "day_load": day_load,
    }


_METROS = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종")


def short_region(address: str) -> str:
    """주소 → 짧은 시·군 이름("경기 포천시 …" → "포천", "서울특별시 …"·"서울 강남구" → "서울"). 못 찾으면 ""."""
    region = region_of(address)
    for metro in _METROS:
        if region.startswith(metro) or (not region and (address or "").strip().startswith(metro)):
            return metro
    return re.sub(r"(시|군)$", "", region)


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


def _check_report_staff(db: Session, user: User, plan: VisitPlan, staff_id: int | None) -> None:
    """보고서 담당자를 사람이 정할 때 — 그날 그 사람이 이미 보고서 4곳(이 현장 말고)이면 막고 여유 있는 사람을 알려 준다."""
    if staff_id is None:
        return
    _check_refs(db, user, None, staff_id)
    load = paper_load(db, user.company_id, plan.plan_date, exclude_plan_ids={plan.id} if plan.id else None)
    if not has_room(load, staff_id, plan.site_id):
        name = db.query(Staff.name).filter(Staff.id == staff_id).scalar() or ""
        free = free_names(db, load, staff_order(db, user.company_id), staff_id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{name}님은 {plan.plan_date:%m/%d}에 이미 보고서 {MAX_SITES_PER_STAFF_PER_DAY}곳을 맡았습니다(한 사람 하루 "
                            f"{MAX_SITES_PER_STAFF_PER_DAY}곳)." + (f" 여유 있는 사람: {free}." if free else ""))


@router.post("/plans")
def add_plan(body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.site_id is None or body.plan_date is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "현장과 날짜를 고르세요.")
    _check_refs(db, user, body.site_id, body.staff_id)
    plan = VisitPlan(
        company_id=user.company_id, site_id=body.site_id, staff_id=body.staff_id, plan_date=body.plan_date,
        memo=(body.memo or "").strip(), created_by=user.display_name or "",
    )
    if body.report_staff_id is not None:
        _check_report_staff(db, user, plan, body.report_staff_id)
        plan.report_staff_id = body.report_staff_id
    db.add(plan)
    assign_new_plans(db, user.company_id, [plan])  # 비어 있으면 규칙대로(직전 회차 담당 → 현장 담당, 4곳이면 순서대로)
    db.commit()
    return {"id": plan.id}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _require_plan(db, user, plan_id)
    fields = body.model_dump(exclude_unset=True)
    _check_refs(db, user, fields.get("site_id"), fields.get("staff_id"))
    moved = any(fields.get(k) is not None and fields[k] != getattr(plan, k) for k in ("plan_date", "site_id"))
    if fields.get("site_id") is not None:
        plan.site_id = fields["site_id"]
    if "staff_id" in fields:
        plan.staff_id = fields["staff_id"]
    if fields.get("plan_date") is not None:
        plan.plan_date = fields["plan_date"]
    if "report_staff_id" in fields:
        _check_report_staff(db, user, plan, fields["report_staff_id"])
        plan.report_staff_id = fields["report_staff_id"]
    elif moved and plan.report_staff_id is not None:
        # 다른 날·현장으로 옮겼는데 그날 그 사람이 이미 보고서 4곳이면 규칙대로 다시 고른다
        if not has_room(paper_load(db, user.company_id, plan.plan_date, exclude_plan_ids={plan.id}), plan.report_staff_id, plan.site_id):
            plan.report_staff_id = None
            assign_new_plans(db, user.company_id, [plan])
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


class RedistributeIn(BaseModel):
    dry_run: bool = False


@router.post("/day/{date}/report-staff")
def redistribute_day(date: datetime.date, body: RedistributeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[📝 보고서 담당 다시 나누기] — 그날 보고서가 아직 없는 예정의 보고서 담당자를 규칙대로 다시(직전 회차 담당 → 현장 담당, 한 사람 4곳,
    넘치면 보고서 담당 순서). dry_run이면 바뀌는 것만 돌려준다."""
    names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == user.company_id))
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == user.company_id)}
    result = redistribute(db, user.company_id, date)
    rows = [{"plan_id": p.id, "site_name": site_label(sites[p.site_id]) if p.site_id in sites else "", "traveler": names.get(p.staff_id, ""),
             "before": names.get(p.report_staff_id, ""), "after": names.get(new, ""), "changed": p.report_staff_id != new}
            for p, new in result]
    if not body.dry_run:
        for p, new in result:
            p.report_staff_id = new
        db.commit()
    return {"date": date.isoformat(), "rows": rows, "changed": sum(r["changed"] for r in rows),
            "unassigned": sum(1 for _, new in result if new is None)}


class MoveIn(BaseModel):
    from_staff_id: int | None = None  # 지금 출장자(None = "⚠ 대타 필요"처럼 요원 없는 예정)
    to_staff_id: int | None = None  # None = 출장자 없음(창의 [되돌리기]로 "⚠ 대타 필요"였던 예정을 되돌릴 때)
    plan_ids: list[int]


@router.post("/day/{date}/move")
def move_day(date: datetime.date, body: MoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[출장 담당자 변경] — 그날 한 사람의 예정 여러 곳을 다른 사람에게(휴가·병가 대타). 출장자만 바뀌고 보고서 담당자는 그대로, 📌 고정.
    창의 [되돌리기]도 이것으로(받은 사람 → 원래 사람)."""
    _check_refs(db, user, None, body.to_staff_id)
    plans = db.query(VisitPlan).filter(VisitPlan.company_id == user.company_id, VisitPlan.plan_date == date,
                                       VisitPlan.id.in_(body.plan_ids or [-1])).all()
    plans = [p for p in plans if p.staff_id == body.from_staff_id]
    if not plans:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "넘길 예정을 고르세요.")
    for p in plans:
        p.staff_id = body.to_staff_id
        p.source = "manual"
        p.memo = (p.memo or "").replace("거리가 멀어 대타 필요 — 원 담당", "대타 · 원 담당")
    db.commit()
    return {"ok": True, "moved": len(plans)}
