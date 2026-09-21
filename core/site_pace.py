"""현장 카드 상태바용 계산 — 공기(시간) 경과율 vs 기술지도 횟수 소진율(사용자 요청 2026-09-21).

- 시간 경과율 = (오늘 − 공사 시작일) ÷ (종료일 − 시작일), 0~1로 자른다.
- 수행 횟수 = 그 현장 가장 최근 보고서의 **회차 번호**(18회 계약에 9회차부터 쓰기 시작해도 수행은 9회로 본다).
- 이상적인 수행 횟수 = 총 횟수 × 시간 경과율(반올림). 실제가 그보다 적으면 그 차이가 "부족", 많으면 "여유".
- 월 필요 횟수 = (총 횟수 − 수행) ÷ 남은 개월 수.
화면 코드와 분리해 순수 함수로 두었다(DB·Qt 없이 검증 가능).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

_DAYS_PER_MONTH = 30.4375

SHORTAGE = "shortage"   # 🚨 [N회 부족] — 빨강
SURPLUS = "surplus"     # ✅ [N회 여유] — 파랑
NORMAL = "normal"       # ✅ [정상] — 검정
DONE = "done"           # 🏁 [완료] — 파랑
UNKNOWN = "unknown"     # 공기 또는 총 횟수 정보 없음


@dataclass(frozen=True)
class SitePace:
    performed: int
    total: int | None
    time_ratio: float | None        # 0~1, 공기 정보 없으면 None
    count_ratio: float | None       # 0~1(넘으면 1), 총 횟수 없으면 None
    status: str
    diff: int                       # 부족(+)/여유(−) 횟수의 크기(항상 0 이상)
    elapsed_text: str               # "6개월 경과" / "12일 경과" / "시작 전" / ""
    monthly_needed: float | None    # 월 필요 횟수, 계산 불가(기간 종료·정보 없음·완료)면 None
    period_over: bool               # 공사 기간이 끝났는데 횟수가 남았는지


def _elapsed_text(start: datetime.date, today: datetime.date) -> str:
    days = (today - start).days
    if days < 0:
        return "시작 전"
    months = days / _DAYS_PER_MONTH
    return f"{round(months)}개월 경과" if months >= 1 else f"{days}일 경과"


def compute_site_pace(
    period_start: datetime.date | None,
    period_end: datetime.date | None,
    total: int | None,
    performed: int,
    today: datetime.date | None = None,
) -> SitePace:
    today = today or datetime.date.today()
    performed = max(int(performed or 0), 0)
    total = int(total) if total else None

    has_period = bool(period_start and period_end and period_end > period_start)
    time_ratio = None
    elapsed_text = ""
    if has_period:
        span = (period_end - period_start).days
        time_ratio = min(max((today - period_start).days / span, 0.0), 1.0)
        elapsed_text = _elapsed_text(period_start, today)
    count_ratio = min(performed / total, 1.0) if total else None

    if not total:
        return SitePace(performed, None, time_ratio, None, UNKNOWN, 0, elapsed_text, None, False)
    if performed >= total:
        return SitePace(performed, total, time_ratio, 1.0, DONE, 0, elapsed_text, None, False)
    if time_ratio is None:
        return SitePace(performed, total, None, count_ratio, UNKNOWN, 0, "", None, False)

    ideal = round(total * time_ratio)
    gap = ideal - performed
    status = SHORTAGE if gap > 0 else SURPLUS if gap < 0 else NORMAL

    months_left = (period_end - today).days / _DAYS_PER_MONTH
    period_over = months_left <= 0
    monthly = None if period_over else (total - performed) / months_left
    return SitePace(performed, total, time_ratio, count_ratio, status, abs(gap), elapsed_text, monthly, period_over and gap > 0)
