"""시특법 회차 칸 완료(2026-10-18 민재형 — 칸마다 [✓ 조사 완료]·[✓ 작성 완료], 회차 화면 ✓는 이 버튼으로만).

저장 = sitok_report.survey["steps"] {칸: {at, by}}. 칸 = STEPS. 빠진 항목 검사·버튼 API는 server/api/routers/sitok_steps.py.
"""
from __future__ import annotations

STEPS = {"field": "현장 조사", "tests": "재료시험", "rating": "상태평가", "survey": "면담·변경사항 조사", "detail": "시설물 현황", "ai": "AI 초안"}


def needed(kind: str, upto: str) -> list[str]:
    """그 단계 전에 끝나야 할 칸(10/18 형 요청1 — "각 항목이 모두 체크 완료되었을 때 AI 초안 작성 버튼이 활성화, 그 이후 보고서 합본 버튼").
    ai = 현장 조사(정밀은 재료시험·상태평가)·면담·변경사항 조사·시설물 현황, build = 그 위 + AI 초안."""
    out = ["field", *(["tests", "rating"] if kind == "정밀" else []), "survey", "detail"]
    return out + (["ai"] if upto == "build" else [])


def left(r, upto: str) -> list[str]:
    """아직 완료 안 된 칸 이름(needed 순서)."""
    return [STEPS[k] for k in needed(r.kind or "정기", upto) if not get(r, k)]


def get(r, step: str) -> dict | None:
    return ((r.survey or {}).get("steps") or {}).get(step)


def put(r, step: str, value: dict | None) -> None:
    """value = {at, by} 완료 / None 취소. survey는 JSON이라 새 dict로 갈아 끼움(바뀐 줄 알게)."""
    sv = dict(r.survey or {})
    steps = dict(sv.get("steps") or {})
    if value:
        steps[step] = value
    else:
        steps.pop(step, None)
    sv["steps"] = steps
    r.survey = sv
