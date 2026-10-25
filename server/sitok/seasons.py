"""시특법 점검 시기(2026-10-16 민재형 — D·E등급이면 정기안전점검 연 3회: 해빙기·우기·동절기, 민간-6 안산롯데프라자).

보통은 상반기·하반기(연 2회). 연 3회 시설물은 회차·계약 회차 줄의 반기 칸에 해빙기·우기·동절기를 씀.
내진성능평가(10/21 형 "새로 항목 만들기")는 반기 칸 "성능평가"·종류 "성능평가" — 반기로 보는 곳(제출 현황·FMS·자동 배치)에는 안 들어가고,
같은 해 같은 반기 정기 회차와 따로 있음. 계약은 건명에 "성능평가"가 있는 것(is_seismic_title)끼리만 이어짐.
제출 현황·서류 현황·실적·FMS 정기 구분처럼 반기로 보는 곳은 해빙기·우기 = 상반기 칸, 동절기 = 하반기 칸으로 묶음.
점검 기간(법정 권장 — 해빙기 전·우기 전·동절기 전): 해빙기 2~3월, 우기 5~6월, 동절기 11~12월.
"""
from __future__ import annotations

import datetime

HALVES = ("상반기", "하반기")
SEASONS = ("해빙기", "우기", "동절기")
ALL = HALVES + SEASONS
SEISMIC = "성능평가"  # 내진성능평가 회차의 반기 칸(10/21)
_ORDER = {"해빙기": 0, "상반기": 1, "우기": 2, "하반기": 3, "동절기": 4, SEISMIC: 9}  # 한 해 안 차례(전회차 찾기·회차 줄 정렬)
_BUCKET = {"상반기": "상반기", "하반기": "하반기", "해빙기": "상반기", "우기": "상반기", "동절기": "하반기", SEISMIC: SEISMIC}
_RANGE = {"상반기": ((1, 1), (6, 30)), "하반기": ((7, 1), (12, 31)),
          "해빙기": ((2, 1), (3, 31)), "우기": ((5, 1), (6, 30)), "동절기": ((11, 1), (12, 31)), SEISMIC: ((1, 1), (12, 31))}


def order(half: str | None) -> int:
    return _ORDER.get(half or "", 1)


def bucket(half: str | None) -> str:
    """반기 칸 — 해빙기·우기 → 상반기, 동절기 → 하반기, 상·하반기는 그대로."""
    return _BUCKET.get(half or "", half or "")


def in_bucket(half: str) -> list[str]:
    """그 반기 칸에 드는 시기들 — 상반기 → [상반기, 해빙기, 우기]."""
    return [h for h in ALL if _BUCKET[h] == half]


def date_range(year: int, half: str) -> tuple[datetime.date, datetime.date]:
    (am, ad), (bm, bd) = _RANGE.get(half, _RANGE["상반기"])
    return datetime.date(year, am, ad), datetime.date(year, bm, bd)


def is_season(half: str | None) -> bool:
    return half in SEASONS


def is_seismic(half: str | None) -> bool:
    """내진성능평가 회차(반기 칸 "성능평가")."""
    return half == SEISMIC


def is_seismic_title(title: str | None) -> bool:
    """내진성능평가 계약 — 건명에 "성능평가"(띄어쓰기 무시). "내진보강"은 아님."""
    return "성능평가" in (title or "").replace(" ", "")


def title_half(title: str | None) -> tuple[int, str] | None:
    """계약건명에 반기 하나만 적혔으면 (연도, 상반기|하반기) — "2026년 하반기 산업단지 옹벽 안전점검 용역" → (2026, "하반기").
    상·하반기 둘 다(또는 연도 없이) 적혔으면 None(10/25 — 하반기 계약 완수일이 다음 해 1월이라 다음 해 상반기까지 덮던 것)."""
    import re

    t = title or ""
    found = re.findall(r"(20\d{2})\s*년(?:도)?\s*(상반기|하반기)", t)
    if len(found) != 1 or ("상반기" in t and "하반기" in t):
        return None
    return int(found[0][0]), found[0][1]


def _selfcheck() -> None:
    assert title_half("2026년 하반기 산업단지 옹벽 안전점검 용역") == (2026, "하반기") and title_half("2026년도 상반기 점검") == (2026, "상반기")
    assert title_half("2026년 상·하반기 정기안전점검") is None and title_half("시설물 2026~2027년 정기·정밀안전점검") is None
    assert order("해빙기") < order("우기") < order("하반기") < order("동절기") and bucket("우기") == "상반기" and bucket("동절기") == "하반기"
    assert in_bucket("하반기") == ["하반기", "동절기"] and date_range(2026, "해빙기") == (datetime.date(2026, 2, 1), datetime.date(2026, 3, 31))
    assert bucket(SEISMIC) == SEISMIC and SEISMIC not in in_bucket("상반기") and is_seismic_title("삼숭초 교사동 내진 성능평가 용역") and not is_seismic_title("내진보강공사")
    print("점검 시기 검사 통과")


if __name__ == "__main__":
    _selfcheck()
