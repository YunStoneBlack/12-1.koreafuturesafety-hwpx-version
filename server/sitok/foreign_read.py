"""타회사 정기점검 보고서 PDF에서 전회차 결함 읽기(2026-10-11, 민재형: "타회사인 경우 결함현황표랑 사진대장만 잘 분석하면 된다").

양식이 회사마다 제각각이라 규칙 대신:
1. 결함현황표 = 머리줄에 결함·손상·유형과 위치·부위·폭·크기가 있는 표(pymupdf find_tables) → 줄을 AI에 주고 우리 결함현황표 칸으로 정리
   (층 이름 맞추기, 합친 칸 채우기, 단위 — 균열 폭 mm·길이 m, 면적 결함 폭·길이 m, 기록용 사진·보수완료 구분).
2. 사진대장 = 그림이 여러 장이고 "사진" 글자가 있는 쪽 — 그림마다 바로 아래 "사진 번호 N"·"사진N"을 찾아 번호와 짝(못 찾으면 그 쪽 그림을 AI에 보여 순서대로 번호를 받음).
3. 결함 줄의 사진번호로 사진을 붙임. 사진대장이 없는 PDF(본관동처럼)는 사진 없이.
결과는 album_read.Album과 같은 모양(값 키도 우리 결함현황표 머리글) — sitok_defects.import_pdf가 그대로 씀.
견본: 바탕화면 `시특법 견본\\1.보고서_본관동.pdf`(3.3 결함표, 사진 없음), `AW컨벤션센터 상반기 정기점검 보고서.pdf`(2.1.6 결함표 + 부록-1 사진 6장/쪽).
"""
from __future__ import annotations

import re

import pymupdf

from server.sitok.album_read import Album, Row

HEAD_DEFECT = ("결함", "손상", "유형")
HEAD_PLACE = ("위치", "부위", "폭", "크기", "길이")
HEAD_SKIP = ("평가항목", "점검내용", "점검항목", "용역명", "구분상태")
KEYS = ["번호", "구분", "부재", "결함유형", "개수", "폭", "길이", "물량", "면적률", "결함원인", "진행유무", "비고", "사진번호"]


def _cell(v) -> str:
    return " ".join(str(v or "").split())


def defect_tables(doc) -> list[list[list[str]]]:
    """결함현황표로 보이는 표들 [[줄[칸]]] — 쪽 순서대로."""
    out = []
    for page in doc:
        try:
            tables = page.find_tables().tables
        except Exception:  # noqa: BLE001 — 표를 못 읽는 쪽은 건너뜀
            continue
        for t in tables:
            raw = [r for r in t.extract() if any(_cell(c) for c in r)]  # 빈 구분 줄(AW) 빼기
            rows = []
            for r in raw:  # 세로로 합친 칸(None)은 위 줄 값으로 — 표를 나눠 AI에 줘도 층을 잃지 않게
                prev = rows[-1] if rows else []
                rows.append([_cell(c) if c is not None else (prev[k] if k < len(prev) else "") for k, c in enumerate(r)])
            if len(rows) < 3:
                continue
            head = "".join("".join(r) for r in rows[:2]).replace(" ", "")
            if any(w in head for w in HEAD_SKIP):
                continue
            if any(w in head for w in HEAD_DEFECT) and sum(w in head for w in HEAD_PLACE) >= 1:
                out.append(rows)
    return out


def _photo_pages(doc) -> list[int]:
    return [i for i, p in enumerate(doc) if "사진" in p.get_text() and len(_big_images(p)) >= 2]


def _big_images(page) -> list[tuple]:
    boxes = []
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        if x1 - x0 > 80 and y1 - y0 > 60 and not any(abs(x0 - b[0]) < 2 and abs(y0 - b[1]) < 2 for b in boxes):
            boxes.append((x0, y0, x1, y1))
    return sorted(boxes, key=lambda b: (round(b[1] / 20), b[0]))


def _number_below(words, box) -> int | None:
    """그림 바로 아래(또는 위) 설명 칸에서 사진 번호 — "사진 번호 1"·"사진1"·"번호 1"."""
    x0, y0, x1, y1 = box
    for top, bottom in ((y1 - 2, y1 + 50), (y0 - 50, y0 + 2)):
        near = sorted((w for w in words if top <= w[1] <= bottom and x0 - 12 <= w[0] <= x1), key=lambda w: (round(w[1] / 4), w[0]))
        text = " ".join(w[4] for w in near)
        m = re.search(r"사진\s*번호\s*(\d+)|사진\s*(\d+)|번호\s*(\d+)|NO\.?\s*(\d+)", text, re.I)
        if m:
            return int(next(g for g in m.groups() if g))
        labels = [w for w in near if w[4] in ("번호", "사진", "NO", "No")]
        if labels:  # "사진/번호" 칸 오른쪽 숫자(AW)
            lab = max(labels, key=lambda w: w[2])
            nums = sorted((w for w in near if re.fullmatch(r"\d{1,4}", w[4]) and w[0] >= lab[2] - 1), key=lambda w: w[0] - lab[2])
            if nums:
                return int(nums[0][4])
    return None


def photos(doc, company_id: int | None = None) -> dict[int, bytes]:
    """사진번호 → JPG. 번호를 글자로 못 찾은 쪽은 AI가 그림을 보고 순서대로 번호(company_id가 있을 때)."""
    out: dict[int, bytes] = {}
    for i in _photo_pages(doc):
        page = doc[i]
        words = page.get_text("words")
        boxes = _big_images(page)
        nums = [_number_below(words, b) for b in boxes]
        if any(n is None for n in nums) and company_id:
            nums = _ai_numbers(page, len(boxes), company_id) or nums
        for b, n in zip(boxes, nums):
            if n is not None and n not in out:
                out[n] = page.get_pixmap(clip=pymupdf.Rect(b), dpi=150).tobytes("jpg")
    return out


def _ai_numbers(page, n: int, company_id: int) -> list[int | None] | None:
    from server.sitok import vision

    try:
        got = vision.ask_json(company_id, [page.get_pixmap(dpi=110).tobytes("jpg")],
                              f"보고서 사진대장 한 쪽입니다. 사진이 {n}장 있습니다. 왼쪽 위부터 오른쪽으로, 그다음 아래 줄 순서로 각 사진의 사진번호(설명 칸의 숫자)를 "
                              f"JSON 배열 하나로만 답하세요(예: [7, 8, 9, 10, 11, 12]). 번호가 없으면 null.", max_tokens=3000)
        return [int(x) if str(x).isdigit() else None for x in got][:n] if isinstance(got, list) and len(got) >= n else None
    except Exception:  # noqa: BLE001
        return None


PROMPT = """다른 회사가 쓴 시설물 정기안전점검 보고서의 결함현황표입니다(표 줄을 " | "로 이음, 빈 칸은 위 줄과 합쳐진 칸일 수 있음).
우리 결함현황표 칸으로 정리해 JSON 배열 하나로만 답하세요(설명 없이). 표의 결함 줄 하나당 하나, 표 순서 그대로:
[{{"no": 원래 결함 번호(없으면 null), "floor": 층 — "지하1층"·"지상3층"·"옥상층" 꼴(동 이름 빼기, "1층"→"지상1층", "지붕층·옥탑"→"옥상층", 합쳐진 빈 칸은 위 줄 층),
  "part": "구조체" 또는 "비구조체"(철근콘크리트 슬라브·보·기둥·내력벽 = 구조체, 조적벽·미장·마감·파라펫 조적 = 비구조체),
  "member": 부재 — 되도록 이 목록 중 하나 그대로: {members}
            (벽체는 철근콘크리트면 내력벽, 벽돌·블록이면 조적벽 / 보는 큰보·작은보 구분이 없으면 큰보 / 천장·바닥은 슬라브),
  "dtype": 결함유형 — 되도록 이 목록 중 하나 그대로: {types}
           (수직·수평·경사·망상균열 같은 방향 이름은 빼고: 원문에 미장·마감이란 말이 있으면 미장균열·마감균열, 벽돌·블록·줄눈이면 조적균열, 아니면 균열 /
            박리박락은 떨어져 나갔으면 박락 / 백화·백태·누수흔적은 누수·백태 / 들뜸은 층분리 / 곰보는 재료분리 — 목록에 정말 맞는 게 없을 때만 원문 그대로),
  "count": 개수(숫자만, 모르면 "1"), "width": 폭, "length": 길이, "qty": 물량(숫자만),
  "cause": 원인(표에 있으면), "progress": 진행유무(표에 있으면 "진행성"/"비진행성"),
  "photo": 사진번호 숫자(비고·사진 칸의 "사진3" → 3, 없으면 null),
  "record": 결함이 아니라 기록용(전경·현황·"상태 양호" 등)이면 true, "repaired": 보수완료 표시면 true}}]
단위: 균열(균열·이격·조인트)은 폭 mm·길이 m, 면적 결함(누수·백태·박리·박락·철근노출·탈락 등)은 폭·길이 모두 m. 표의 단위 표시(㎜, m, ㎜*㎜ 등)를 보고 바꾸세요.
크기가 "-"이거나 없으면 빈 글. 지어내지 말 것.

{tables}"""


def _ai_rows(tables: list, company_id: int, allowed: dict) -> list[dict]:
    from server.sitok import vision

    from concurrent.futures import ThreadPoolExecutor

    # 표를 작게 나눠 동시에(165줄 한 번에 = 5분 넘음). 나눈 조각 첫 줄엔 머리줄을 붙여 칸 뜻을 알게
    chunks, cur, size = [], [], 0
    for t in tables:
        head, body = t[:2], t[2:]
        for i in range(0, len(body), 25):
            text = "\n".join(" | ".join(r) for r in head + body[i:i + 25])
            if cur and size + len(text) > 3500:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(text)
            size += len(text)
    if cur:
        chunks.append(cur)

    def one(chunk):
        got = vision.ask_json(company_id, [], PROMPT.format(tables="\n\n[다음 표]\n".join(chunk), members=", ".join(allowed["member"]),
                                                            types=", ".join(allowed["dtype"])), max_tokens=16000)
        return [g for g in got if isinstance(g, dict)]

    with ThreadPoolExecutor(max_workers=6) as pool:
        return [g for part in pool.map(one, chunks) for g in part]


def _num(s) -> str:
    m = re.search(r"\d+(\.\d+)?", str(s or ""))
    return m.group(0) if m else ""


def read(pdf_bytes: bytes, company_id: int, allowed: dict | None = None) -> Album:
    """allowed = 부재·결함유형 목록 {member: [...], dtype: [...]}(없으면 server/sitok/kinds.py 기본값) — AI가 원문 이름을 우리 목록 이름으로 맞춤(10/12)."""
    from server.sitok import kinds

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    tables = defect_tables(doc)
    album = Album()
    if not tables:
        return album
    rows = _ai_rows(tables, company_id, allowed or kinds.DEFAULTS)
    pics = photos(doc, company_id)
    seqs: dict[str, int] = {}
    for g in rows:
        if g.get("repaired"):
            continue  # 지난번에 이미 보수 끝난 것 — 다시 볼 것 없음
        floor = re.sub(r"\s", "", str(g.get("floor") or "")) or "층 모름"
        seqs[floor] = seqs.get(floor, 0) + 1
        dtype = _cell(g.get("dtype"))
        if g.get("record") and not dtype.endswith("현황"):
            dtype = f"{dtype} 현황"
        photo_no = g.get("photo")
        try:
            photo_no = int(photo_no) if photo_no is not None and str(photo_no).strip() not in ("", "null") else None
        except (TypeError, ValueError):
            photo_no = None
        v = {"번호": str(seqs[floor]), "구분": g.get("part") if g.get("part") in ("구조체", "비구조체") else "비구조체", "부재": _cell(g.get("member")),
             "결함유형": dtype, "개수": _num(g.get("count")) or "1", "폭": _num(g.get("width")), "길이": _num(g.get("length")), "물량": _num(g.get("qty")),
             "면적률": "", "결함원인": _cell(g.get("cause")), "진행유무": _cell(g.get("progress")) or "비진행성", "비고": "기존",
             "사진번호": f"사진{photo_no}" if photo_no else "", "원번호": str(g.get("no") or "")}
        album.rows.append(Row(floor=floor, seq=seqs[floor], values=v, photo_png=pics.get(photo_no) if photo_no else None))
    return album
