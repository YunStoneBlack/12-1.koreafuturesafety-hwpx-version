"""시특법 보고서 자동 쪽 검사(2026-10-12 사용자 — "다른 데서도 표가 늘면 부자연스러운 쪽이 생길 수 있으니 대비") — 미리 막지 못한 곳도 놓치지 않게.

한글이 만든 PDF(관리대장·계약서·사진첩을 합치기 전 — 본문 쪽 번호가 최종과 같음)를 훑어 회차 카드 경고로:
- 제목만 쪽 끝: 쪽 마지막 줄이 절 제목(1.2.4 …·1) …·가. …)이고 쪽 아래쪽에 있음(다음 쪽에 그 내용).
- 꼬리말 넘음: 본문 글·선이 꼬리말 줄(쪽 아래 로고) 아래로 — 표가 한 쪽보다 커져 잘렸을 수 있음.
- 넘친 몇 줄만 있는 쪽: 앞 쪽이 꽉 찼는데 이 쪽엔 몇 줄뿐(결과표·표 꼬리가 넘침 등).
원본이 일부러 새 쪽에서 시작하게 한 절(문단 쪽 나눔)·구역 첫 쪽·간지(장 표지)는 빼고 봄.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

HEAD = re.compile(r"^(\d+(\.\d+)+\.?|\d+\)|[가-하]\.)\s*\S")
TOP = 70  # 머리말 아래(pt)


def _key(s: str) -> str:
    return re.sub(r"\s", "", s or "")[:12]


def designed_starts(hwpx: Path) -> set[str]:
    """원본이 새 쪽에서 시작하게 한 곳의 첫 글 — 쪽 나눔 문단(안에 표가 있으면 그 표 첫 칸 글도)·구역 첫 문단."""
    from server.sitok import report_build as rb

    out: set[str] = set()
    with zipfile.ZipFile(hwpx) as z:
        for n in rb._sections(z):
            root = etree.fromstring(z.read(n))
            tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
            for i, p in enumerate(tops):
                if i == 0 or p.get("pageBreak") == "1":
                    t = rb._top_text(p)
                    if t:
                        out.add(_key(t))
                    tbl = next(p.iter(f"{{{rb.HP}}}tbl"), None)
                    if tbl is not None:
                        out.add(_key(rb._cell_text(rb._cells(tbl).get((0, 0), tbl))))
                    if not t and tbl is None and i + 1 < len(tops):  # 쪽 나눔이 빈 문단에 걸린 경우 — 다음 문단 글
                        out.add(_key(rb._top_text(tops[i + 1])))
    out.discard("")
    return out


def _body(pg) -> tuple[list[tuple[float, float, str]], float, float, list]:
    """(본문 줄들 [(y0, y1, 글)], 내용 끝 y, 꼬리말 줄 y, 꼬리말을 넘은 선)."""
    H = pg.rect.height
    foot = min([rr.y0 for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0]) if rr.y0 > H * 0.85] or [H - 63])
    lines = []
    for b in pg.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t and TOP < ln["bbox"][1] < foot - 2:
                lines.append((ln["bbox"][1], ln["bbox"][3], t))
    draws = [d["rect"] for d in pg.get_drawings() if TOP < d["rect"].y0 < foot - 2 and d["rect"].height < H * 0.9]
    over = [r for r in draws if r.y1 > foot + 1 and r.y0 < foot - 20]
    pics = [rr for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0]) if TOP < rr.y0 < foot - 2]
    bottom = max([y1 for _, y1, _ in lines] + [r.y1 for r in draws] + [r.y1 for r in pics] + [0])
    return sorted(lines), bottom, foot, over


def _divider(lines) -> bool:
    """간지(장·편·부록 표지) — 짧은 줄 몇 개뿐, 또는 "제 N 장" + 소목차(1.1 …) 줄들."""
    if len(lines) <= 6 and all(len(t) <= 30 for _, _, t in lines):
        return True
    toc = sum(1 for _, _, t in lines if re.match(r"^\d+\.\d+\s", t) and len(t) <= 30)
    return toc >= 3 and len(lines) <= 14 and any(re.match(r"^제\s*\d+\s*장", t) for _, _, t in lines)


def scan(pdf: Path, hwpx: Path, limit: int = 12) -> list[str]:
    """경고 글들(쪽 번호 순, 많으면 limit개까지 + 나머지 개수)."""
    import pymupdf

    starts = designed_starts(hwpx)
    doc = pymupdf.open(pdf)
    pages = [_body(pg) for pg in doc]
    out = []
    for i, (lines, bottom, foot, over) in enumerate(pages):
        H = doc[i].rect.height
        span = foot - TOP
        if over or any(y1 > foot + 1 for _, y1, _ in lines):
            out.append(f"{i + 1}쪽: 내용이 쪽 아래(꼬리말)를 넘음 — 표가 잘렸을 수 있음")
        if not lines or _divider(lines):
            continue
        last_y0, _, last = lines[-1]
        nxt = pages[i + 1][0] if i + 1 < len(pages) else []
        if HEAD.match(last) and len(last) <= 45 and last_y0 > TOP + span * 0.7 and len(lines) > 1 and nxt and _key(nxt[0][2]) not in starts:
            out.append(f"{i + 1}쪽: 제목 '{last[:20]}'만 쪽 끝에 있음")
        if i > 0 and _key(lines[0][2]) not in starts and len(lines) <= 6 and bottom < TOP + span * 0.2:
            prev_lines, prev_bottom, prev_foot, _ = pages[i - 1]
            if prev_lines and prev_bottom > TOP + (prev_foot - TOP) * 0.8 and not _divider(prev_lines):
                out.append(f"{i + 1}쪽: 앞 쪽에서 넘친 몇 줄만 있음('{lines[0][2][:16]}…')")
    if len(out) > limit:
        out = out[:limit] + [f"외 {len(out) - limit}곳"]
    return out
