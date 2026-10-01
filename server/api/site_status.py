"""현장 공사 상태(2026-10-01 사용자) — 착공전 / 진행중 / 공사중지 / 준공. 지도 출장 배치는 **진행중** 현장만
(착공전·공사중지는 언제 공사할지 모르고, 준공은 더 갈 필요가 없음). 자동 배치·일정 없는 현장·방문 달력 현장 목록이 이 판정을 쓴다.
웹판 새 현장은 착공전으로 등록(routers/sites.create_site). 예전 값(완료·보류, 데스크톱)은 배치 안 함으로 본다."""
from __future__ import annotations

from core.models_db import Site

STATUSES = ("착공전", "진행중", "공사중지", "준공")
ACTIVE = "진행중"
NEW_SITE = "착공전"


def is_active(site: Site) -> bool:
    return (site.status or ACTIVE) == ACTIVE
