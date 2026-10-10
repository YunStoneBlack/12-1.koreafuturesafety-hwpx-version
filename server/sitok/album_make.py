"""외관조사 사진첩(부록2) PDF 만들기(2026-10-11 5-2단계) — 층마다 "[○층 결함 현황표]" 한 쪽(30줄, 빈 줄은 "-")과
"[○층 결함사진표]"(한 쪽 6장, 사진 아래 사진번호·결함유형·개소·폭/길이·길이·물량). 모양은 평택 견본(구글 스프레드시트로 만들던 것) 그대로, A4 세로.
사진 = 이번에 찍은 것, 없으면 전회차 사진. 보수 완료는 결함유형 "보수완료"·크기 "-"(견본과 같음). 사진 번호는 층마다 1부터 번호 순.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

FONT = "C:/Windows/Fonts/malgun.ttf"
FONT_B = "C:/Windows/Fonts/malgunbd.ttf"
W, H = 595.2, 841.68
M = 36  # 여백
STATUS_COLS = [("번호", 22), ("구분", 40), ("부재", 40), ("결함유형", 58), ("개수", 24), ("폭/길이\n(mm/m)", 36), ("길이\n(m)", 28),
               ("물량\n(m/㎡)", 32), ("면적률\n(%)", 30), ("결함원인", 62), ("진행유무", 40), ("비고", 26), ("사진\n번호", 32)]
PHOTO_COLS = [("사진\n번호", 30), ("결함유형", 58), ("개소", 22), ("폭/길이\n(mm/m)", 34), ("길이\n(m)", 26), ("물량\n(m/㎡)", 31)]
ROWS_PER_PAGE = 30


def _fonts(page):
    page.insert_font(fontname="mg", fontfile=FONT)
    page.insert_font(fontname="mgb", fontfile=FONT_B)


def _cell(page, rect, text, size=6.5, bold=False, fill=None):
    if fill:
        page.draw_rect(rect, color=None, fill=fill)
    page.draw_rect(rect, color=(0.35, 0.35, 0.35), width=0.4)
    lines = str(text).split("\n")
    lh = size * 1.25
    y = rect.y0 + (rect.height - lh * len(lines)) / 2 + size
    font = "mgb" if bold else "mg"
    for ln in lines:
        f = pymupdf.Font(fontfile=FONT_B if bold else FONT)
        tw = f.text_length(ln, fontsize=size)
        while tw > rect.width - 2 and size > 4:  # 넘치면 글자 줄임
            size -= 0.3
            tw = f.text_length(ln, fontsize=size)
        page.insert_text((rect.x0 + (rect.width - tw) / 2, y), ln, fontname=font, fontsize=size)
        y += lh


def _scale(cols, total):
    s = sum(w for _, w in cols)
    return [(n, w * total / s) for n, w in cols]


def _title(page, text, y):
    r = pymupdf.Rect(M, y, W - M, y + 22)
    _cell(page, r, text, size=10, bold=True)
    return r.y1


def status_pages(doc, floor: str, rows: list[dict]) -> None:
    cols = _scale(STATUS_COLS, W - 2 * M)
    chunks = [rows[i:i + ROWS_PER_PAGE] for i in range(0, max(len(rows), 1), ROWS_PER_PAGE)]
    for chunk in chunks:
        page = doc.new_page(width=W, height=H)
        _fonts(page)
        y = _title(page, f"[{floor} 결함 현황표]", M + 40)
        x = M
        for name, w in cols:
            _cell(page, pymupdf.Rect(x, y, x + w, y + 22), name, size=6, bold=True, fill=(0.93, 0.93, 0.93))
            x += w
        y += 22
        rh = (H - M - 20 - y) / ROWS_PER_PAGE
        for i in range(ROWS_PER_PAGE):
            vals = chunk[i] if i < len(chunk) else None
            x = M
            for k, (name, w) in enumerate(cols):
                key = ["번호", "구분", "부재", "결함유형", "개수", "폭", "길이", "물량", "면적률", "결함원인", "진행유무", "비고", "사진번호"][k]
                _cell(page, pymupdf.Rect(x, y, x + w, y + rh), (vals.get(key) or "-") if vals else "-")
                x += w
            y += rh


def photo_pages(doc, floor: str, rows: list[dict]) -> None:
    gap = 8
    colw = (W - 2 * M - gap) / 2
    cols = _scale(PHOTO_COLS, colw)
    for start in range(0, len(rows), 6):
        page = doc.new_page(width=W, height=H)
        _fonts(page)
        y0 = _title(page, f"[{floor} 결함사진표]", M) + 6
        slot_h = (H - M - y0) / 3
        for k, vals in enumerate(rows[start:start + 6]):
            r, c = divmod(k, 2)
            x0, y = M + c * (colw + gap), y0 + r * slot_h
            img_rect = pymupdf.Rect(x0, y, x0 + colw, y + slot_h - 40)
            page.draw_rect(img_rect, color=(0.35, 0.35, 0.35), width=0.4)
            photo = vals.get("_photo")
            if photo and Path(photo).exists():
                page.insert_image(img_rect + (1, 1, -1, -1), filename=str(photo), keep_proportion=True)
            yy = img_rect.y1 + 2
            x = x0
            for name, w in cols:
                _cell(page, pymupdf.Rect(x, yy, x + w, yy + 18), name, size=5.5, bold=True, fill=(0.93, 0.93, 0.93))
                x += w
            x = x0
            for (name, w), key in zip(cols, ["사진번호", "결함유형", "개수", "폭", "길이", "물량"]):
                _cell(page, pymupdf.Rect(x, yy + 18, x + w, yy + 34), vals.get(key) or "-", size=6)
                x += w


def make(floors: list[tuple[str, list[dict]]], dest: Path) -> int:
    """floors = [(층, [줄 값들 — 번호·구분·…·사진번호 + _photo 경로])]. 쪽 수를 돌려준다."""
    doc = pymupdf.open()
    for floor, rows in floors:
        status_pages(doc, floor, rows)
        photo_pages(doc, floor, rows)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest, garbage=3, deflate=True)
    n = len(doc)
    doc.close()
    return n
