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
PARTS = ("구조체", "비구조체")

# ---------- 옹벽(2026-10-20 옹벽 정기점검 — 견본 "2026 상반기 산업단지 옹벽 17개소" + 3종 매뉴얼 표 2-4·3-4) ----------
# 건축물의 "층" 자리에 부위(SitokDefect.floor 칸을 그대로 씀 — DB 안 늘림), 구분은 구조체/비구조체 대신 매뉴얼 시설영역(주요·일반·부대시설).
# 사진첩·1.4 현장조사 결과(지반 및 기초부 / 옹벽 전면부 / 기타)·실시결과 요약표(전면부·상부·기초/지반·배수시설·공중이용)가 이 부위 순서.
WALL_PARTS = ["지반 및 기초부", "전면부", "상부", "배수시설", "공중이용시설", "기타"]
WALL_MEMBERS = ["블록", "콘크리트", "기초", "뒷채움", "배수공", "배수로", "집수정", "소단", "보호콘크리트", "사면", "안전펜스", "낙석방지망", "점검로", "철망", "채움재", "-"]
WALL_TYPES = ["균열", "파손", "이격", "백태", "누수", "철근노출", "채움재유출", "토사유출", "실링재탈락", "잡목식생", "토사·낙엽퇴적", "배부름", "침하", "세굴",
              "전도·경사", "활동", "철망손상", "마감불량", "단차", "-", "보수완료"]
WALL_DEFAULTS = {"member": WALL_MEMBERS, "dtype": WALL_TYPES}
WALL_SECTIONS = ("주요시설", "일반시설", "부대시설")  # 매뉴얼 표 2-4 옹벽: 주요 = 전면부·지반 및 기초부, 일반 = 배수공·배수로·비탈면·옹벽 배면, 부대 = 안전·보호시설
WALL_MAJOR_MEMBERS = ("블록", "콘크리트", "기초", "뒷채움", "채움재", "철망")
WALL_GENERAL_MEMBERS = ("배수공", "배수로", "집수정", "소단", "보호콘크리트", "사면")
WALL_MINOR_MEMBERS = ("안전펜스", "낙석방지망", "점검로")
WALL_PART_OF_UNIT = {"지반 및 기초부": "주요시설", "전면부": "주요시설", "상부": "일반시설", "배수시설": "일반시설", "공중이용시설": "부대시설", "기타": "일반시설"}
FAMILIES = {"": DEFAULTS, "wall": WALL_DEFAULTS}  # 결함 목록 묶음(SitokVocab.kind = "wall_member"처럼 앞말이 붙음)


def family_of(facility) -> str:
    """시설물의 결함 목록 묶음 — 옹벽이면 "wall"(관리대장 시설물구분 옹벽 또는 FMS 번호 RW…), 아니면 ""(건축물)."""
    kind = (getattr(facility, "kind", "") or "")
    fms = (getattr(facility, "fms_no", "") or "").upper()
    return "wall" if ("옹벽" in kind and not kind.startswith("건축물")) or fms.startswith("RW") else ""


def is_wall(facility) -> bool:
    return family_of(facility) == "wall"


def vocab_kind(fam: str, kind: str) -> str:
    """SitokVocab.kind 값 — 건축물은 member/dtype 그대로, 옹벽은 wall_member/wall_dtype."""
    return f"{fam}_{kind}" if fam else kind


def parts_of(fam: str) -> tuple:
    return WALL_SECTIONS if fam == "wall" else PARTS


def unit_label(fam: str) -> str:
    return "부위" if fam == "wall" else "층"


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


def is_main_part(part: str) -> bool:
    """구조 결함으로 세는 구분 — 건축물 구조체, 옹벽 주요시설(전면부·지반 및 기초부)."""
    return part in ("구조체", "주요시설")


def counts_for_rating(part: str, dtype: str) -> bool:
    """상태평가(구조 결함) 개수에 넣는지 — 구조체(옹벽은 주요시설)이고 마감층 균열·기록·보수완료가 아닌 것."""
    return is_main_part(part) and bool(dtype) and not (is_finish_crack(dtype) or is_record(dtype) or is_repaired_type(dtype))


def default_part(member: str, fam: str = "") -> str:
    if fam == "wall":
        return ("주요시설" if member in WALL_MAJOR_MEMBERS else "일반시설" if member in WALL_GENERAL_MEMBERS
                else "부대시설" if member in WALL_MINOR_MEMBERS else "")
    return "구조체" if member in STRUCT_MEMBERS else "비구조체" if member in NONSTRUCT_MEMBERS else ""


def part_map(fam: str = "") -> dict:
    """부재 → 구분 기본값(화면이 부재를 고르면 구분을 바꿈)."""
    if fam == "wall":
        return {**{m: "주요시설" for m in WALL_MAJOR_MEMBERS}, **{m: "일반시설" for m in WALL_GENERAL_MEMBERS}, **{m: "부대시설" for m in WALL_MINOR_MEMBERS}}
    return {**{m: "구조체" for m in STRUCT_MEMBERS}, **{m: "비구조체" for m in NONSTRUCT_MEMBERS}}
