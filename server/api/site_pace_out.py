"""현장 진행 막대(공기 경과 vs 기술지도 수행) — 데스크톱 현장 카드(core/site_pace.py, 2026-09-21)와 **같은 계산**을 웹 화면용 dict로.
현장 목록·현장 화면·방문 달력 그날 목록이 쓴다(2026-09-30, 사용자 A안: 막대 두 줄). 수행 횟수 = 그 현장 가장 최근 보고서 회차."""

from __future__ import annotations

import datetime
from dataclasses import asdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models_db import Report
from core.site_pace import compute_site_pace

_DAYS_PER_MONTH = 30.4375  # core/site_pace.py와 같은 값


def pace_dict(site, last_visit_no: int | None, today: datetime.date | None = None) -> dict:
    """데스크톱과 같은 계산 + 화면용 "경과 개월/전체 공사 개월"(예: 6/15개월 경과 — 2026-09-30 사용자 요청)."""
    today = today or datetime.date.today()
    out = asdict(compute_site_pace(site.period_start, site.period_end, site.total_guidance_count, last_visit_no or 0, today))
    out["elapsed_months"] = out["total_months"] = None
    start, end = site.period_start, site.period_end
    if start and end and end > start:
        total = max(round((end - start).days / _DAYS_PER_MONTH), 1)
        out["total_months"] = total
        out["elapsed_months"] = None if today < start else min(round((today - start).days / _DAYS_PER_MONTH), total)
    return out


def last_visit_nos(db: Session, site_ids: list[int]) -> dict[int, int]:
    if not site_ids:
        return {}
    return dict(db.query(Report.site_id, func.max(Report.visit_no)).filter(Report.site_id.in_(site_ids)).group_by(Report.site_id))
