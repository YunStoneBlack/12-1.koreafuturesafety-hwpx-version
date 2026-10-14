"""정밀안전점검 부록 "3-1. 탄산화 깊이 조사 측정데이터" — 탄산화 사진현황 PDF(2026-10-14, 사용자 "형 없이 할 수 있는 건 다 해").
형이 준 양식(=탄산화결과 사진현황.xlsx)과 같은 모양: A4 세로, 제목 "[시설물명] 탄산화측정조사"(둘째 쪽부터 "(2)"), 한 쪽에 사진 6장(2열 × 3줄),
사진 아래 작은 표 "구분 | 탄산화깊이 | 피복두께 / C1 | 13.26 | 61". 사진은 재료시험 탭 탄산화 줄마다 올린 것(회차 폴더 재료시험/탄산화_*.jpg) — 없는 줄은 뺌.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from server.sitok.album_make import FONT_B, M, W, _cell, _fonts

H = 841.68
PER_PAGE = 6
PHOTO_H = 215.0  # 양식 행 높이 200pt + 여유
TABLE_H = 15.0


def make_pdf(dest: Path, facility: str, rows: list[dict]) -> Path | None:
    """rows = [{"label": "C1", "photo": Path, "depth": 13.26, "cover": 61}, …] — 사진 있는 줄만. 없으면 None."""
    rows = [r for r in rows if r.get("photo") and Path(r["photo"]).exists()]
    if not rows:
        return None
    doc = pymupdf.open()
    col_w = (W - 2 * M - 12) / 2
    for p in range(0, len(rows), PER_PAGE):
        page = doc.new_page(width=W, height=H)
        _fonts(page)
        n = p // PER_PAGE + 1
        title = f"[{facility}] 탄산화측정조사" + (f"({n})" if n > 1 else "")
        f = pymupdf.Font(fontfile=FONT_B)
        tw = f.text_length(title, fontsize=14)
        page.insert_text(((W - tw) / 2, M + 14), title, fontname="mgb", fontsize=14)
        y0 = M + 34
        for k, r in enumerate(rows[p:p + PER_PAGE]):
            col, row = k % 2, k // 2
            x = M + col * (col_w + 12)
            y = y0 + row * (PHOTO_H + TABLE_H * 2 + 14)
            box = pymupdf.Rect(x, y, x + col_w, y + PHOTO_H)
            page.draw_rect(box, color=(0.35, 0.35, 0.35), width=0.5)
            try:
                page.insert_image(box, filename=str(r["photo"]), keep_proportion=True)
            except Exception:  # noqa: BLE001 — 깨진 사진은 빈 칸
                pass
            ws = [col_w * 0.22, col_w * 0.39, col_w * 0.39]
            heads = ["구분", "탄산화깊이", "피복두께"]
            vals = [r.get("label") or "-", _num(r.get("depth"), "mm"), _num(r.get("cover"), "mm")]
            yy = y + PHOTO_H
            for i, (h_, v_) in enumerate(zip(heads, vals)):
                xx = x + sum(ws[:i])
                _cell(page, pymupdf.Rect(xx, yy, xx + ws[i], yy + TABLE_H), h_, size=7.5, bold=True, fill=(0.93, 0.93, 0.93))
                _cell(page, pymupdf.Rect(xx, yy + TABLE_H, xx + ws[i], yy + TABLE_H * 2), v_, size=7.5)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest, garbage=3, deflate=True)
    doc.close()
    return dest


def _num(v, unit: str) -> str:
    if v is None or v == "":
        return "-"
    try:
        x = float(v)
        return (f"{x:g}" if x != int(x) else f"{int(x)}") + unit
    except (TypeError, ValueError):
        return str(v)
