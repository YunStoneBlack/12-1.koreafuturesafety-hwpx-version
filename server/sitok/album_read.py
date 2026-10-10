"""지난 보고서 PDF의 외관조사 사진첩(부록2) 읽기(2026-10-10 5단계) — 층별 "[지상2층 결함 현황표]"(번호~사진번호 13칸)와
"[지상2층 결함사진표]"(사진 6장 + 사진번호·결함유형·개소·폭·길이·물량)를 읽어 전회차 결함 목록 + 사진으로.

사진첩은 한글 밖(구글 스프레드시트)에서 만들어 PDF로 합친 것이라 글자가 살아 있다(평택 견본 94~106쪽). 사진은 결함사진표 쪽의 그림 위치를
"사진N" 설명 칸 순서(위→아래, 왼→오)와 짝지어 그 자리를 잘라 낸다(원본 그림이 돌아가 있거나 커도 보이는 그대로).
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
    return m[1].replace(" ", "") if m else ""


def _clean(v) -> str:
    return " ".join(str(v or "").split())


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
            caps = []  # (y, x, "사진N") — 설명 칸 위치
            for t in tables:
                for row in t.rows:
                    for cell in row.cells:
                        if cell is None:
                            continue
                        txt = _clean(page.get_textbox(cell))
                        if re.fullmatch(r"사진\s*\d+", txt):
                            caps.append((round(cell[1]), cell[0], txt.replace(" ", "")))
            imgs = sorted(((round(i["bbox"][1]), i["bbox"][0], pymupdf.Rect(i["bbox"])) for i in page.get_image_info()
                           if pymupdf.Rect(i["bbox"]).width > 40), key=lambda x: (x[0], x[1]))
            caps.sort(key=lambda x: (x[0], x[1]))
            for (_, _, rect), (_, _, no) in zip(imgs, caps):
                photos[(floor, no)] = page.get_pixmap(clip=rect, dpi=150).tobytes("jpg")
    for r in out.rows:
        r.photo_png = photos.get((r.floor, r.photo_no.replace(" ", "")))
    return out
