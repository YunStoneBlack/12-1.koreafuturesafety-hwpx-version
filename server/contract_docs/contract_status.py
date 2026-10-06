"""용역 계약의 제출 판정·일정 날짜·현장 이름 비슷한 정도 — 판정은 이 한 곳에서만(보고서 제출 현황 server/api/submission.py와 같은 원칙).

- 제출됨(사용자 10/6): 착수계·완수계 **합본 PDF를 만들었으면** 제출로 본다(start_made_at·done_made_at + 파일 있음).
- 단계: 착수계 전 → 착수계 제출 → 완수계 제출(끝). 현장 연결은 단계와 따로.
- 기한: **없음**(사용자 10/6 — 회사에 정해진 규칙이 없음). "기한 지남" 같은 경고는 안 하고, 일정 달력엔 계약의 착수일·완수일만(plan_dates).
"""
from __future__ import annotations

import datetime
import re
from difflib import SequenceMatcher

STAGES = [("before", "착수계 전"), ("started", "착수계 제출"), ("finished", "완수계 제출")]


def submitted(contract, kind: str, pdf_exists: bool) -> bool:
    at = contract.start_made_at if kind == "start" else contract.done_made_at
    return bool(at) and pdf_exists


def stage(start_done: bool, done_done: bool) -> str:
    if done_done:
        return "finished"
    if start_done:
        return "started"
    return "before"


def plan_dates(contract) -> dict[str, datetime.date | None]:
    """일정 달력에 놓는 날 — 착수계 = 착수일, 완수계 = 완수일(준공기한). 기한이 아니라 계약의 날짜."""
    return {"start": contract.start_date, "done": contract.end_date}


_NOISE = re.compile(r"재해\s*예방|기술\s*지도|용역|공사|\(.*?\)|\[.*?\]|20\d\d년?|\s|[^\w가-힣]")


def _norm(text: str) -> str:
    return _NOISE.sub("", text or "")


def similarity(contract_title: str, site_name: str) -> float:
    """용역명과 현장명이 얼마나 비슷한지(0~1) — 현장 연결 추천 순서. "재해예방 기술지도 용역"·연도·괄호는 빼고 비교."""
    a, b = _norm(contract_title), _norm(site_name)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()
