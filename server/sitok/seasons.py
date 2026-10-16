"""시특법 점검 시기(2026-10-16 민재형 — D·E등급이면 정기안전점검 연 3회: 해빙기·우기·동절기, 민간-6 안산롯데프라자).

보통은 상반기·하반기(연 2회). 연 3회 시설물은 회차·계약 회차 줄의 반기 칸에 해빙기·우기·동절기를 씀.
제출 현황·서류 현황·실적·FMS 정기 구분처럼 반기로 보는 곳은 해빙기·우기 = 상반기 칸, 동절기 = 하반기 칸으로 묶음.
점검 기간(법정 권장 — 해빙기 전·우기 전·동절기 전): 해빙기 2~3월, 우기 5~6월, 동절기 11~12월.
"""
from __future__ import annotations

import datetime

HALVES = ("상반기", "하반기")
SEASONS = ("해빙기", "우기", "동절기")
ALL = HALVES + SEASONS
_ORDER = {"해빙기": 0, "상반기": 1, "우기": 2, "하반기": 3, "동절기": 4}  # 한 해 안 차례(전회차 찾기·회차 줄 정렬)
_BUCKET = {"상반기": "상반기", "하반기": "하반기", "해빙기": "상반기", "우기": "상반기", "동절기": "하반기"}
_RANGE = {"상반기": ((1, 1), (6, 30)), "하반기": ((7, 1), (12, 31)),
          "해빙기": ((2, 1), (3, 31)), "우기": ((5, 1), (6, 30)), "동절기": ((11, 1), (12, 31))}


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


def _selfcheck() -> None:
    assert order("해빙기") < order("우기") < order("하반기") < order("동절기") and bucket("우기") == "상반기" and bucket("동절기") == "하반기"
    assert in_bucket("하반기") == ["하반기", "동절기"] and date_range(2026, "해빙기") == (datetime.date(2026, 2, 1), datetime.date(2026, 3, 31))
    print("점검 시기 검사 통과")


if __name__ == "__main__":
    _selfcheck()
