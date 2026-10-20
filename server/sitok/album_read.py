"""지난 보고서 PDF의 외관조사 사진첩(부록2) 읽기(2026-10-10 5단계) — 층별 "[지상2층 결함 현황표]"(번호~사진번호 13칸)와
"[지상2층 결함사진표]"(사진 6장 + 사진번호·결함유형·개소·폭·길이·물량)를 읽어 전회차 결함 목록 + 사진으로.

사진첩은 한글 밖(구글 스프레드시트)에서 만들어 PDF로 합친 것이라 글자가 살아 있다(평택 견본 94~106쪽). 사진은 결함사진표 쪽에서
"사진N" 설명 칸마다 같은 열(가로가 겹침) 바로 위의 그림을 짝지어 그 자리를 잘라 낸다(원본 그림이 돌아가 있거나 커도 보이는 그대로).
예전엔 그림을 위쪽 끝 좌표 → 왼쪽 차례로 늘어놓고 설명 칸 차례와 맞췄는데, 같은 줄 그림의 위쪽 끝이 1pt만 달라도(칸 가운데 맞춤) 순서가 뒤바뀌어
사진이 서로 바뀌었음(10/20 형 검수 — 의정부시 스포츠센터 87쪽 지상3층 사진5 569pt·사진6 568pt). 외관망도 위치와 이어지니 위치로 짝지음.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

HEAD = ["번호", "구분", "부재", "결함유형", "개수", "폭", "길이", "물량", "면적률", "결함원인", "진행유무", "비고", "사진번호"]


@dataclass
class Row:
    floor: str
    seq: int
    values: dict
    photo_no: str = ""
    photo_png: bytes | None = None


@dataclass
class Album:
    rows: list[Row] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


def _floor(text: str) -> str:
    m = re.search(r"\[\s*(.+?)\s*결함\s*(현황표|사진표)\s*\]", text or "")
    f = m[1].replace(" ", "") if m else ""
    return "옥상층" if f in ("지붕층", "지붕", "옥상", "옥탑층") else f  # 지난 보고서 "지붕층" → 우리 층 이름 "옥상층"(형 10/14)


def _clean(v) -> str:
    return " ".join(str(v or "").split())


ABOVE_GAP = 80  # 설명 칸 위쪽 끝과 그 위 그림 아래쪽 끝 사이 최대 간격(pt) — 견본·의정부 33pt
ROW_TOL = 12  # 위치로 못 짝지은 것끼리 줄로 묶을 때 위쪽 끝 차이 허용(pt)


def match(imgs: list, caps: list[tuple]) -> list[tuple]:
    """그림(Rect)과 설명 칸 [(Rect, "사진N")] → [(그림 Rect, "사진N")]. 설명 칸마다 같은 열(가로가 겹침)에서 바로 위(ABOVE_GAP 안, 가장 가까운) 그림,
    못 찾은 것끼리는 줄(ROW_TOL로 묶음) → 왼쪽 차례로 맞춤."""
    used: set[int] = set()
    out, left = [], []
    for cap, no in sorted(caps, key=lambda c: (round(c[0].y0), c[0].x0)):
        cand = [(cap.y0 - im.y1, k) for k, im in enumerate(imgs)
                if k not in used and im.x0 < cap.x1 and im.x1 > cap.x0 and -8 <= cap.y0 - im.y1 <= ABOVE_GAP]
        if cand:
            k = min(cand)[1]
            used.add(k)
            out.append((imgs[k], no))
        else:
            left.append((cap, no))

    def rows(items, rect):  # 위쪽 끝이 ROW_TOL 안이면 같은 줄 → (줄, x)
        items = sorted(items, key=lambda it: rect(it).y0)
        keyed, row, top = [], -1, None
        for it in items:
            if top is None or rect(it).y0 - top > ROW_TOL:
                row, top = row + 1, rect(it).y0
            keyed.append(((row, rect(it).x0), it))
        return [it for _, it in sorted(keyed, key=lambda x: x[0])]

    rest = [im for k, im in enumerate(imgs) if k not in used]
    for im, (cap, no) in zip(rows(rest, lambda r: r), rows(left, lambda c: c[0])):
        out.append((im, no))
    return out


def read(pdf_bytes: bytes) -> Album:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = Album()
    photos: dict[tuple[str, str], bytes] = {}  # (층, "사진3") → PNG
    for pn, page in enumerate(doc):
        text = page.get_text()
        if "결함 현황표" not in text and "결함사진표" not in text and "결함 사진표" not in text:
            continue
        floor = _floor(text)
        if not floor:
            continue
        out.pages.append(pn)
        tables = page.find_tables().tables
        if "현황표" in text and "사진표" not in text:
            for t in tables:
                for r in t.extract():
                    cells = [_clean(c) for c in r]
                    if len(cells) < 13 or not cells[0].isdigit():
                        continue
                    vals = dict(zip(HEAD, cells[:13]))
                    out.rows.append(Row(floor, int(cells[0]), {k: ("" if v == "-" else v) for k, v in vals.items()}, cells[12]))
        else:
            caps = []  # [(설명 칸 Rect, "사진N")]
            for t in tables:
                for row in t.rows:
                    for cell in row.cells:
                        if cell is None:
                            continue
                        txt = _clean(page.get_textbox(cell))
                        if re.fullmatch(r"사진\s*\d+", txt):
                            caps.append((pymupdf.Rect(cell), txt.replace(" ", "")))
            imgs = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info() if pymupdf.Rect(i["bbox"]).width > 40]
            for rect, no in match(imgs, caps):
                photos[(floor, no)] = page.get_pixmap(clip=rect, dpi=150).tobytes("jpg")
    for r in out.rows:
        r.photo_png = photos.get((r.floor, r.photo_no.replace(" ", "")))
    return out
