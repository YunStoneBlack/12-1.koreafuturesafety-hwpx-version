"""지도 기한 계산 — 기술지도는 모든 현장이 15일 간격(사용자 확인 2026-09-29).

기한 = 마지막 지도일 + 15일(보고서가 아직 없으면 공사 시작일 + 15일). 진행 중인 현장만 본다:
현장 상태 "진행중" + 공사 종료일이 안 지남 + 기술지도 총 횟수를 다 안 채움(총 횟수가 비어 있으면 횟수는 안 봄).
단계: 초과(over, 기한 지남) / 임박(imminent, 기한까지 설정 일수 이내 — 기본 D-3, 설정 탭에서 조정) / 정상(ok).

쓰는 곳: 제출 현황 화면·맨 위 배너·현장 목록 D-day(server/api/routers/submission.py, sites.py),
아침 알림 메일(server/worker/deadline_notifier.py). 계산은 전부 여기서만.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff

GUIDANCE_INTERVAL_DAYS = 15


@dataclass
class SiteDeadline:
    site_id: int
    site_name: str
    staff_id: int | None
    staff_name: str
    last_date: datetime.date | None  # 마지막 지도일(없으면 None — 공사 시작일 기준)
    last_visit_no: int | None
    deadline: datetime.date
    days_left: int  # 기한까지 남은 날(0 = 오늘이 기한, 음수 = 지남)
    stage: str  # ok | imminent | over

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("last_date", "deadline"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


def stage_for(days_left: int, imminent_days: int) -> str:
    if days_left < 0:
        return "over"
    if days_left <= imminent_days:
        return "imminent"
    return "ok"


def site_deadlines(db: Session, company_id: int, today: datetime.date | None = None) -> list[SiteDeadline]:
    """진행 중인 현장들의 지도 기한(기한 가까운 순)."""
    today = today or datetime.date.today()
    imminent_days = config.get_deadline_imminent_days(company_id)
    sites = db.query(Site).filter(Site.company_id == company_id).all()
    ids = [s.id for s in sites]
    stats = {
        sid: (cnt, last_date, last_no)
        for sid, cnt, last_date, last_no in db.query(
            Report.site_id, func.count(Report.id), func.max(Report.guidance_date), func.max(Report.visit_no)
        ).filter(Report.site_id.in_(ids)).group_by(Report.site_id)
    } if ids else {}
    staff_names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == company_id))
    out = []
    for site in sites:
        cnt, last_date, last_no = stats.get(site.id, (0, None, None))
        if (site.status or "진행중") != "진행중":
            continue
        if site.period_end and site.period_end < today:
            continue
        if site.total_guidance_count and cnt >= site.total_guidance_count:
            continue
        base = last_date or site.period_start
        if base is None:
            continue
        deadline = base + datetime.timedelta(days=GUIDANCE_INTERVAL_DAYS)
        days_left = (deadline - today).days
        out.append(SiteDeadline(
            site_id=site.id, site_name=site.name, staff_id=site.assigned_staff_id,
            staff_name=staff_names.get(site.assigned_staff_id, ""), last_date=last_date, last_visit_no=last_no,
            deadline=deadline, days_left=days_left, stage=stage_for(days_left, imminent_days),
        ))
    out.sort(key=lambda d: d.days_left)
    return out
