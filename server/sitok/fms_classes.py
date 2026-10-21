"""FMS 시설물분류 표(2026-10-21 사용자 엑셀 — 시설물구분·시설물종류·세분류·종별·시특법적용일, data/fms_classes.json 228줄).
관리대장의 "시설물종류" 칸엔 세분류 글("지면으로부터 노출된 높이가 5미터 이상인 부분의 합이 100미터 이상인 건축물옹벽")이 오는데,
보고서 결과표 "종류"는 엑셀의 시설물종류("건축물옹벽")로(사용자 10/21). 시설물구분(옹벽·교량·…)은 묶음 타일 머리 "건물 3 · 옹벽 1"에."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).parent / "data" / "fms_classes.json"


def _sq(s: str) -> str:
    return re.sub(r"[\s,.·()（）]", "", s or "")


@lru_cache(maxsize=1)
def rows() -> list[dict]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def lookup(sub_text: str) -> dict | None:
    """세분류 글(관리대장 시설물종류 칸, 띄어쓰기·줄바꿈 무시) → 표 줄 {group, kind, sub, class, since}. 똑같은 줄 > 한쪽이 다른 쪽을 품는 줄(가장 긴 것) > 없음."""
    t = _sq(sub_text)
    if len(t) < 2:
        return None
    exact = next((r for r in rows() if _sq(r["sub"]) == t), None)
    if exact:
        return exact
    # 짧은 글("옹벽")이 아무 세분류에나 걸리지 않게 — 입력이 세분류를 품거나, 입력이 충분히 길 때만 세분류 안에 든 경우
    part = [r for r in rows() if len(_sq(r["sub"])) >= 6 and (_sq(r["sub"]) in t or (len(t) >= 15 and t in _sq(r["sub"])))]
    return max(part, key=lambda r: len(_sq(r["sub"]))) if part else None


def kind_of(sub_text: str) -> str:
    """세분류 글 → 시설물종류(건축물옹벽·도로교량·…), 못 찾으면 ""."""
    r = lookup(sub_text)
    return r["kind"] if r else ""


def group_of(sub_text: str) -> str:
    """세분류(또는 시설물종류) 글 → 시설물구분(옹벽·교량·터널·건축물·…), 못 찾으면 ""."""
    r = lookup(sub_text)
    if r:
        return r["group"]
    t = _sq(sub_text)
    hit = [r for r in rows() if _sq(r["kind"]) == t]
    return hit[0]["group"] if hit else ""
