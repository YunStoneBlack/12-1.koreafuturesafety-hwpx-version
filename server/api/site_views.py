"""현장 열람 기록(2026-10-08 사용자 — 현장 목록 "최근 열람순", 로그인한 사람 기준). 현장 화면(GET /sites/{id})·보고서 화면(GET /reports/{id})을 열면 남긴다."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from core.models_web import SiteView


def mark(db: Session, user_id: int, site_id: int | None) -> None:
    """마지막으로 연 때를 지금으로(실패해도 화면은 열리게 — 기록만 못 남김)."""
    if not site_id:
        return
    try:
        row = db.get(SiteView, (user_id, site_id))
        now = datetime.datetime.now()
        if row is None:
            db.add(SiteView(user_id=user_id, site_id=site_id, viewed_at=now))
        else:
            row.viewed_at = now
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def viewed_map(db: Session, user_id: int) -> dict[int, datetime.datetime]:
    return dict(db.query(SiteView.site_id, SiteView.viewed_at).filter(SiteView.user_id == user_id))
