"""시특법 결함 부재·결함유형 기본 목록과 판정(2026-10-12 — 민재형 구글 시트 드롭다운, 사용자 붙임1).

- 부재·결함유형은 고정 목록에서만 고름(AI도). 목록에 없는 것은 현장에서 "이 보고서에만 / 회사 전체 목록에" 추가(SitokVocab, 설정 탭에서 회사 목록 관리).
  나중 정밀안전점검은 국가 프로그램의 정해진 결함유형으로 부재·유형별 개수를 세므로 이름이 흔들리면 안 됨.
- 수직·수평·경사균열은 안 씀 — 구조체 균열로 잘못 세어짐. 박락과 층분리는 따로(시트는 한 칸이었음).
- 상태평가 개수에서 빼는 것 = 비구조체 전부 + 구조체라도 미장·마감·조적균열(마감층 결함 — 구조 결함 아님). 1.3에서는 견본대로 구조체 미장균열도 "구조체 균열" 항목.
"""
from __future__ import annotations

MEMBERS = ["내력벽", "조적벽", "기둥", "큰보", "작은보", "슬라브", "강재", "파라펫", "마감재", "-", "계단", "처마"]
TYPES = ["균열", "미장균열", "마감균열", "조적균열", "이격", "철근노출", "박리", "박락", "층분리", "누수·백태", "파손", "재료분리", "-", "높이부족", "보수완료"]
KINDS = {"member": "부재", "dtype": "결함유형"}
DEFAULTS = {"member": MEMBERS, "dtype": TYPES}

STRUCT_MEMBERS = ("내력벽", "기둥", "큰보", "작은보", "슬라브", "강재", "계단")  # 부재를 고르면 구분 기본값(점검자가 바꿀 수 있음)
NONSTRUCT_MEMBERS = ("조적벽", "파라펫", "마감재")
FINISH_WORDS = ("미장", "마감", "조적")  # 결함유형에 이 낱말 + 균열 = 마감층 균열(상태평가 제외)
LEGACY = {"박락·층분리": "박락", "박락ㆍ층분리": "박락"}  # 시트 옛 한 칸 → 지난 사진첩 가져올 때


def norm(dtype: str) -> str:
    t = (dtype or "").strip()
    return LEGACY.get(t, t)


def is_record(dtype: str) -> bool:
    """결함이 아닌 줄 — 기록용 사진("실외기 현황")·"-"."""
    t = (dtype or "").strip()
    return t.endswith("현황") or t == "-"


def is_repaired_type(dtype: str) -> bool:
    return (dtype or "").replace(" ", "") == "보수완료"


def is_finish_crack(dtype: str) -> bool:
    t = dtype or ""
    return "균열" in t and any(w in t for w in FINISH_WORDS)


def counts_for_rating(part: str, dtype: str) -> bool:
    """상태평가(구조 결함) 개수에 넣는지 — 구조체이고 마감층 균열·기록·보수완료가 아닌 것."""
    return part == "구조체" and bool(dtype) and not (is_finish_crack(dtype) or is_record(dtype) or is_repaired_type(dtype))


def default_part(member: str) -> str:
    return "구조체" if member in STRUCT_MEMBERS else "비구조체" if member in NONSTRUCT_MEMBERS else ""
