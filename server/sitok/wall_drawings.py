"""옹벽 보고서 도면(2026-10-21 형 "도면파일·전회차보고서 넣으면 1.2.4 칸에") — 건축물과 같은 후면첨부: 시설물 첨부 도면(drawings attach)을
"k.2.4 시설물 주요도면" 쪽 바로 뒤에 한 장 한 쪽으로 끼움(server/sitok/drawings.insert). 전회차 보고서 PDF를 올리면 그 보고서의 1.2.4 뒤 도면 쪽을 잘라
첨부 도면에 넣어 둠(아직 도면이 없을 때만 — 점검자가 보고 지우거나 더 올림)."""
from __future__ import annotations

import io
import re
from pathlib import Path

from server.sitok import drawings as D

_HEAD = re.compile(r"(\d+)\.2\.4시설물주요도면")
_NEXT = re.compile(r"\d+\.(2\.[5-9]|3)[가-힣]")


def _sq(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _body(pg) -> str:
    """쪽 본문 글(머리말·꼬리말 자리 뺌, 띄어쓰기 없이) — 한글이 만든 PDF는 머리말이 글 맨 앞에 와서 제목으로 못 찾음."""
    from server.sitok.wall_build import _body_lines

    lines, _ = _body_lines(pg)
    return _sq("".join(lines))


def from_prior(pdf_path: Path, name: str = "") -> list[bytes]:
    """전회차 보고서 PDF의 "k.2.4 시설물 주요도면" 쪽(그림이 들어 있으면 포함)부터 다음 절 제목 쪽 전까지 → 한 쪽짜리 PDF 바이트 목록.
    묶음 책이면 이 곳 이름이 꼬리말에 든 쪽을 먼저. 도면 쪽이 없으면 []."""
    import pymupdf

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:  # noqa: BLE001
        return []
    out: list[bytes] = []
    try:
        bodies = [_body(doc[i]) for i in range(len(doc))]
        heads = [i for i, b in enumerate(bodies) if _HEAD.match(b[:40])]
        if not heads:
            return []
        if name:
            hit = [i for i in heads if _sq(name) in _sq(doc[i].get_text())]
            heads = hit or heads
        i0 = heads[0]
        i1 = next((i for i in range(i0 + 1, len(doc)) if _NEXT.match(bodies[i][:40]) or _HEAD.match(bodies[i][:40])), len(doc))
        pages = list(range(i0 + 1, i1))
        if doc[i0].get_images():  # 틀 안에 도면 그림이 든 전회차 보고서 — 그 쪽도
            pages = [i0] + pages
        for i in pages:
            one = pymupdf.open()
            one.insert_pdf(doc, from_page=i, to_page=i)
            buf = io.BytesIO()
            one.save(buf)
            one.close()
            out.append(buf.getvalue())
    finally:
        doc.close()
    return out


def seed(f, base: Path, pdf_path: Path) -> int:
    """첨부 도면이 아직 없으면 전회차 보고서에서 잘라 넣음 → 넣은 쪽 수."""
    if D.items(f, "attach", base):
        return 0
    pages = from_prior(pdf_path, f.name)
    for n, data in enumerate(pages, 1):
        D.add(f, "attach", base, data, f"전회차 보고서 도면 {n}.pdf")
    return len(pages)


def insert(pdf: Path, sites: list) -> list[int]:
    """보고서 PDF에 곳마다(장 k) 첨부 도면을 "k.2.4 시설물 주요도면" 쪽 뒤에 — sites = [(k, [도면 경로])]."""
    def finder(pg, n):
        t = _body(pg)
        return bool(re.match(rf"{n}\.2\.4시설물주요도면", t[:40])) and len(t) < 80  # 틀 쪽(제목 + 빈 틀) — 목차·장 표지 소목차는 글이 김

    return D.insert(pdf, sites, finder)
