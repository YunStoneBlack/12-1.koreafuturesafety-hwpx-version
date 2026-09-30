"""지도 출장 자동 배치 API(2026-10-01) — 계산은 server/api/visit_scheduler.py, 여기는 DB에서 읽고 쓰기만.

- `POST /calendar/auto-plan/preview` — 저장 없이 "이렇게 넣겠습니다"(미리보기). body: `site_id`(그 현장만) 또는 `staff_ids`(그 요원들의 진행 중 현장 전부).
- `POST /calendar/auto-plan/apply` — 같은 계산을 다시 해서 저장: 대상 현장의 "자동(auto)이면서 내일 이후" 예정을 지우고 새로 넣는다.
  사람이 넣거나 옮긴 예정(manual, 📌)은 안 건드리고 기준점으로 쓴다. 현장 하나만 할 땐 다른 현장 예정은 그대로(새 현장을 기존 일정에 끼워 넣기).
- `GET/POST /settings/auto-plan` — 마감(준공 며칠 전까지 마칠지, 기본 14일).
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
from server.api.visit_scheduler import SiteIn, plan_sites, region_of

router = APIRouter(tags=["auto-plan"])


class AutoPlanIn(BaseModel):
    site_id: int | None = None
    staff_ids: list[int] | None = None


class AutoPlanSettings(BaseModel):
    finish_before_days: int = config.DEFAULT_PLAN_FINISH_BEFORE_DAYS


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
    replaced = [p for p in future if p.site_id in target_ids and p.source == "auto"]
    kept = [p for p in future if not (p.site_id in target_ids and p.source == "auto")]

    visit_addr = dict(db.query(SiteContact.site_id, SiteContact.visit_address).filter(SiteContact.site_id.in_(list(sites)))) if sites else {}
    region = {sid: region_of(visit_addr.get(sid) or s.address or "") for sid, s in sites.items()}
    stats = {
        sid: (no or 0, last)
        for sid, no, last in db.query(Report.site_id, func.max(Report.visit_no), func.max(Report.guidance_date))
        .filter(Report.site_id.in_(list(target_ids))).group_by(Report.site_id)
    } if target_ids else {}

    # 요원·날짜별로 이미 가는 현장(남기는 예정 + 앞날짜로 만든 보고서), 요원·지역별로 이미 가는 날(묶기 기준점)
    busy: dict[tuple[int, datetime.date], set[int]] = defaultdict(set)
    region_days: dict[tuple[int, str], set[datetime.date]] = defaultdict(set)
    for p in kept:
        if p.staff_id is not None:
            busy[(p.staff_id, p.plan_date)].add(p.site_id)
            if region.get(p.site_id):
                region_days[(p.staff_id, region[p.site_id])].add(p.plan_date)
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
    placed, results = plan_sites(ins, today, busy, region_days, finish, MAX_SITES_PER_STAFF_PER_DAY, site_regions=region)
    return sites, region, replaced, placed, results, finish


def _names(db: Session, company_id: int) -> dict[int, str]:
    return dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == company_id))


@router.post("/calendar/auto-plan/preview")
def preview(body: AutoPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    sites, region, replaced, placed, results, finish = _compute(db, user.company_id, body, today)
    names = _names(db, user.company_id)
    return {
        "today": today.isoformat(),
        "finish_before_days": finish,
        "replace_count": len(replaced),
        "plans": [{"date": p.date.isoformat(), "site_id": p.site_id, "site_name": sites[p.site_id].name, "region": region[p.site_id],
                   "staff_id": p.staff_id, "staff_name": names.get(p.staff_id, "")} for p in placed],
        "sites": [{"site_id": r.site_id, "site_name": sites[r.site_id].name, "staff_name": names.get(sites[r.site_id].assigned_staff_id, ""),
                   "region": region[r.site_id], "needed": r.needed, "placed": r.placed, "note": r.note} for r in results],
    }


@router.post("/calendar/auto-plan/apply")
def apply(body: AutoPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    _, _, replaced, placed, results, _ = _compute(db, user.company_id, body, today)
    for p in replaced:
        db.delete(p)
    for p in placed:
        db.add(VisitPlan(company_id=user.company_id, site_id=p.site_id, staff_id=p.staff_id, plan_date=p.date,
                         memo="", source="auto", created_by=user.display_name or ""))
    db.commit()
    return {"ok": True, "added": len(placed), "removed": len(replaced),
            "short": sum(1 for r in results if r.note.startswith("넣을 날"))}


@router.get("/settings/auto-plan", response_model=AutoPlanSettings)
def get_settings(user: User = Depends(get_current_user)):
    return AutoPlanSettings(finish_before_days=config.get_plan_finish_before_days(user.company_id))


@router.post("/settings/auto-plan", response_model=AutoPlanSettings)
def set_settings(body: AutoPlanSettings, user: User = Depends(get_current_user)):
    if not 0 <= body.finish_before_days <= 180:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "0~180일 사이로 정하세요.")
    config.set_plan_finish_before_days(body.finish_before_days, user.company_id)
    return get_settings(user)
