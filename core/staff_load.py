"""담당요원 1인이 같은 지도일에 맡을 수 있는 현장 수 제한(사용자 요청 2026-09-21).

한 요원이 하루에 5개 이상 현장을 맡으면 업무 능률이 떨어지고 국가기관도 좋아하지 않는다 — 그래서 **같은 지도일**에 한 요원이 맡는
서로 다른 현장은 최대 4개로 제한한다(주 단위가 아니라 지도일 기준). 작성 중·확정 보고서를 모두 센다(우선 이렇게 — 바꾸려면
`_COUNTED_STATUSES`만 손보면 된다). 지금 편집 중인 현장의 보고서는 세지 않는다 — 같은 현장의 다른 보고서가 같은 날 있어도 1개 현장이고,
이미 4번째로 잡힌 보고서를 다시 열어 저장할 때 막히지 않게 한다.
"""

from __future__ import annotations

import datetime

from core.models_db import Report, Site

MAX_SITES_PER_STAFF_PER_DAY = 4
_COUNTED_STATUSES = None  # None = 모든 상태(작성 중 + 확정)


def other_site_names(session, staff_id: int, guidance_date: datetime.date, current_site_id: int | None) -> list[str]:
    """그 지도일에 `staff_id`가 이미 맡고 있는 **다른 현장**의 이름 목록(중복 없이, 이름순)."""
    if not staff_id or not guidance_date:
        return []
    query = session.query(Report.site_id).filter(
        Report.assigned_staff_id == staff_id, Report.guidance_date == guidance_date
    )
    if current_site_id:
        query = query.filter(Report.site_id != current_site_id)
    if _COUNTED_STATUSES is not None:
        query = query.filter(Report.status.in_(_COUNTED_STATUSES))
    site_ids = {row[0] for row in query.all()}
    if not site_ids:
        return []
    names = [s.name or "(이름 없음)" for s in session.query(Site).filter(Site.id.in_(site_ids)).all()]
    return sorted(names)


def is_full(other_names: list[str]) -> bool:
    """이미 다른 현장 4곳을 맡고 있으면 이 현장은 5번째라 맡을 수 없다."""
    return len(other_names) >= MAX_SITES_PER_STAFF_PER_DAY
