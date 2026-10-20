"""옹벽 지난 보고서 부록2 "외관조사 사진첩" 읽기(2026-10-20 사용자 제안 — 옹벽은 결함현황표가 없고 사진 + 설명뿐).

견본(2026 상반기 산업단지 옹벽 17개소 부록): "부록2.외관조사 사진첩" 간지 → 시설물 간지 "1.보강토옹벽-2" → 전경 쪽(사진 6장, 설명 "시점측 전경"…)
→ "주 요 손 상 및 현 황 사 진" 쪽들(사진 2×3, 설명 "블록 균열(0.3mm이상)"·"배수로 낙엽 및 토사퇴적"·"기초 상태 양호"…) → 다음 시설물 … → "부록3" 간지.
- 읽기: 쪽마다 그림(Rect)과 바로 아래 같은 열의 낱말(설명 칸)을 짝지음(_caption_below). 한글 파일은 먼저 작업 프로그램이 PDF로(hwp_queue).
- 분류: 설명 글을 AI가 부위(kinds.WALL_PARTS)·구분·부재·결함유형으로(guess_rows — AI 한 번, 실패하면 낱말 규칙 keyword_guess), "~양호"·"~현황"은 기록용(상태양호 탭).
  점검자가 확인 창에서 고친 뒤 넣음(server/api/routers/sitok_wall_import.py).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import pymupdf

from server.sitok import kinds

SHOTS_HEAD = "주요손상및현황사진"
OVERVIEW_WORDS = ("전경",)


@dataclass
class Shot:
    caption: str
    jpg: bytes
    page: int
    kind: str = "shot"  # "overview"(전경) / "shot"(주요 손상 및 현황)


@dataclass
class Facility:
    name: str
    overview: list[Shot] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)


@dataclass
class WallAlbum:
    facilities: list[Facility] = field(default_factory=list)
    pages: tuple[int, int] = (0, 0)  # 부록2 쪽 범위(0부터, 끝은 빼고)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _divider(text: str) -> str:
    """간지 쪽(글이 한 줄뿐 — 머리말·꼬리말로 두 번 나옴) → 그 글, 아니면 ""."""
    lines = [" ".join(x.split()) for x in (text or "").splitlines() if x.strip()]
    uniq = list(dict.fromkeys(lines))
    return uniq[0] if len(uniq) == 1 and len(uniq[0]) <= 60 else ""


def _facility_name(divider: str) -> str:
    m = re.fullmatch(r"\s*\d+\s*[.)]\s*(.+)", divider)
    return m[1].strip() if m else ""


BELOW_GAP = 60  # 그림 아래쪽 끝과 설명 낱말 사이 최대 간격(pt) — 견본 표에서 설명 칸은 그림 바로 아래 줄


def _caption_below(words: list, im) -> str:
    """그림 바로 아래, 같은 열(낱말 가운데가 그림 가로 안)의 낱말들 → 설명 글(한 줄 두 칸이 한 덩어리로 읽히는 것을 피함)."""
    got = [w for w in words if im.x0 <= (w[0] + w[2]) / 2 <= im.x1 and -4 <= w[1] - im.y1 <= BELOW_GAP]
    got.sort(key=lambda w: (round(w[1]), w[0]))
    txt = " ".join(w[4] for w in got)
    return "" if _squash(txt) == SHOTS_HEAD else " ".join(txt.split())


def read_pdf(pdf_bytes: bytes) -> WallAlbum:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = WallAlbum()
    start = end = None
    for pn, page in enumerate(doc):
        d = _squash(_divider(page.get_text()))
        if start is None and d.startswith("부록2") and "사진첩" in d:
            start = pn + 1
        elif start is not None and re.match(r"부록[3-9]", d):
            end = pn
            break
    if start is None:
        return out
    end = end if end is not None else doc.page_count
    out.pages = (start, end)
    cur: Facility | None = None
    for pn in range(start, end):
        page = doc[pn]
        text = page.get_text()
        div = _divider(text)
        if div:
            name = _facility_name(div) or div
            cur = Facility(name)
            out.facilities.append(cur)
            continue
        imgs = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info() if pymupdf.Rect(i["bbox"]).width > 40]
        if not imgs:
            continue
        if cur is None:  # 시설물 간지 없이 바로 사진(한 곳짜리 보고서)
            cur = Facility("")
            out.facilities.append(cur)
        is_shots = SHOTS_HEAD in _squash(text)
        words = page.get_text("words")
        for rect in sorted(imgs, key=lambda r: (round(r.y0 / 20), r.x0)):  # 줄(위→아래) → 왼쪽부터
            cap = _caption_below(words, rect)
            if not cap:
                continue
            jpg = page.get_pixmap(clip=rect, dpi=150).tobytes("jpg")
            if is_shots:
                cur.shots.append(Shot(cap, jpg, pn, "shot"))
            else:
                cur.overview.append(Shot(cap, jpg, pn, "overview"))
    out.facilities = [f for f in out.facilities if f.overview or f.shots]
    return out


def pick(album: WallAlbum, facility_name: str) -> int:
    """우리 시설물 이름과 가장 닮은 장(없으면 0)."""
    if not album.facilities:
        return -1
    key = _squash(facility_name)
    best = max(range(len(album.facilities)), key=lambda i: difflib.SequenceMatcher(None, key, _squash(album.facilities[i].name)).ratio())
    return best


# ---------- 설명 → 부위·구분·부재·결함유형 ----------
RECORD_WORDS = ("양호", "현황", "전경", "상태")
UNIT_WORDS = [("지반 및 기초부", ("기초", "지반", "세굴", "침하")), ("배수시설", ("배수", "집수", "측구")), ("공중이용시설", ("휀스", "펜스", "난간", "점검로", "방지망", "울타리")),
              ("상부", ("상부", "소단", "상단", "보호콘크리트", "활용부지", "배면")), ("기타", ("사면", "비탈", "주변")), ("전면부", ("블록", "전면", "벽체", "콘크리트", "이격", "백태", "균열", "파손"))]
MEMBER_WORDS = [("블록", ("블록", "블럭")), ("배수로", ("배수로", "측구")), ("배수공", ("배수공",)), ("집수정", ("집수정",)), ("기초", ("기초", "지반")), ("소단", ("소단",)),
                ("보호콘크리트", ("보호콘크리트",)), ("사면", ("사면", "비탈")), ("안전펜스", ("휀스", "펜스", "난간", "울타리")), ("낙석방지망", ("방지망",)), ("점검로", ("점검로",)),
                ("철망", ("철망", "wire")), ("채움재", ("채움재",)), ("뒷채움", ("뒷채움", "배면")), ("콘크리트", ("콘크리트", "옹벽"))]
TYPE_WORDS = [("균열", ("균열",)), ("파손", ("파손", "단부")), ("이격", ("이격", "벌어")), ("백태", ("백태", "백화")), ("누수", ("누수",)), ("철근노출", ("철근",)),
              ("채움재유출", ("채움재", "유실")), ("토사유출", ("토사유출", "토사 유출")), ("실링재탈락", ("실링", "씰링")), ("잡목식생", ("식생", "잡목", "넝쿨", "수목")),
              ("토사·낙엽퇴적", ("퇴적", "낙엽", "이물질")), ("배부름", ("배부름",)), ("침하", ("침하",)), ("세굴", ("세굴",)), ("전도·경사", ("전도", "경사")), ("활동", ("활동",)),
              ("철망손상", ("철망",)), ("마감불량", ("마감불량", "설치불량")), ("단차", ("단차",))]


def _first(words: list, text: str) -> str:
    for name, keys in words:
        if any(k in text for k in keys):
            return name
    return ""


def keyword_guess(caption: str) -> dict:
    """낱말 규칙(AI 없을 때·AI 실패 때) — {unit, part, member, dtype, record, width}."""
    t = caption or ""
    record = bool(re.search(r"(양호|현황|전경)\s*$", t)) or (any(w in t for w in RECORD_WORDS) and not _first(TYPE_WORDS, t.replace("상태", "")))
    unit = _first(UNIT_WORDS, t) or "기타"
    member = _first(MEMBER_WORDS, t)
    dtype = "" if record else _first(TYPE_WORDS, t)
    part = kinds.default_part(member, "wall") or kinds.WALL_PART_OF_UNIT.get(unit, "일반시설")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|㎜)\s*(이상|미만|이하)?", t)
    width = ""
    if m and "균열" in t:
        v = float(m[1])
        width = ("0.3" if m[2] in ("이상", None) else "0.2") if v == 0.3 else f"{v:g}"
    return {"unit": unit, "part": part, "member": member, "dtype": dtype if not record else f"{(member or unit)} 현황", "record": record, "width": width}


GUESS_PROMPT = """옹벽 정기안전점검 지난 보고서 부록 "주요 손상 및 현황 사진"의 사진 설명 {n}개입니다. 설명마다 우리 현장 조사 칸으로 분류하세요.
- unit(부위): 반드시 이 중 하나: {units}  (블록·전면 벽체 = 전면부, 기초·지반·세굴·침하 = 지반 및 기초부, 소단·상단·보호콘크리트·배면 활용부지 = 상부,
  배수로·배수공·집수정 = 배수시설, 휀스·펜스·난간·점검로·낙석방지망 = 공중이용시설, 사면·주변 = 기타)
- part(구분): "주요시설"(전면부·지반 및 기초부 부재) / "일반시설"(배수·상부·사면) / "부대시설"(펜스·방지망·점검로)
- member(부재): 반드시 이 중 하나 그대로(모르면 ""): {members}
- dtype(결함유형): 반드시 이 중 하나 그대로: {types} — "~양호"·"~현황"·"~전경"처럼 결함이 아닌 기록 사진이면 record=true, dtype는 "○○ 현황"(예: "기초부 현황")
- width: 설명에 균열 폭이 있으면 mm 숫자 글자("0.3"·"0.2"), 없으면 ""
JSON 배열 하나로만 답하세요(설명 없이): [{{"no": 번호, "unit": "", "part": "", "member": "", "dtype": "", "record": false, "width": ""}}]
[설명 — 번호 | 글]
{rows}"""


def guess_rows(captions: list[str], company_id: int, allowed: dict) -> list[dict]:
    """설명 글 목록 → 분류 목록(AI 한 번, 목록 밖·실패는 낱말 규칙). allowed = {member: [...], dtype: [...]}(옹벽 목록)."""
    from server.sitok import vision

    base = [keyword_guess(c) for c in captions]
    if not captions:
        return base
    rows = "\n".join(f"{i} | {c}" for i, c in enumerate(captions, 1))
    try:
        got = vision.ask_json(company_id, [], GUESS_PROMPT.format(n=len(captions), units=", ".join(kinds.WALL_PARTS), members=", ".join(allowed["member"]),
                                                                  types=", ".join(allowed["dtype"]), rows=rows), max_tokens=6000)
    except Exception:  # noqa: BLE001 — AI가 안 되면 낱말 규칙
        return base
    by_no = {int(g["no"]): g for g in got if isinstance(g, dict) and str(g.get("no", "")).isdigit()} if isinstance(got, list) else {}
    for i, b in enumerate(base, 1):
        g = by_no.get(i)
        if not g:
            continue
        unit = str(g.get("unit") or "")
        if unit in kinds.WALL_PARTS:
            b["unit"] = unit
        part = str(g.get("part") or "")
        if part in kinds.WALL_SECTIONS:
            b["part"] = part
        member = str(g.get("member") or "")
        if member in allowed["member"]:
            b["member"] = member
        rec = bool(g.get("record"))
        dtype = str(g.get("dtype") or "").strip()
        if rec or kinds.is_record(dtype):
            b["record"], b["dtype"] = True, dtype if kinds.is_record(dtype) else f"{b['member'] or b['unit']} 현황"
        elif dtype in allowed["dtype"]:
            b["record"], b["dtype"] = False, dtype
        w = str(g.get("width") or "").strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", w):
            b["width"] = w
    return base
