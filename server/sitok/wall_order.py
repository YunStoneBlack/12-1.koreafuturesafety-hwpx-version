"""발주처 과업지시서 PDF(2026-10-21 민재형) — 납품 항목(책자 N부·USB N개)을 글자로 읽고, 못 읽으면 AI 한 번(그 쪽 그림), 그래도 없으면 None(기본값 -·-·협의).
계약 카드(sitok-facility.js) 올리기 → sitok.order_upload → 과업수행계획서 5. 과업성과물 납품 항목(wall_build.fill_docs)."""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT = {"book": "-", "usb": "-", "note": "협의", "src": "default"}
WORDS = ("납품", "성과품", "성과물", "제출")


def _pages(doc) -> list[int]:
    hit = [i for i in range(len(doc)) if any(w in doc[i].get_text() for w in WORDS) and ("책자" in doc[i].get_text() or "USB" in doc[i].get_text().upper() or "부" in doc[i].get_text())]
    return hit[:3]


def _from_text(text: str) -> dict | None:
    t = re.sub(r"[ \t]+", " ", text)
    book = re.search(r"(?:책자|보고서)[^\n\d]{0,40}?(\d+)\s*부", t) or re.search(r"(\d+)\s*부\s*(?:\n|$|[^\w가-힣])", t)
    usb = re.search(r"USB[^\n\d]{0,40}?(\d+)\s*(?:EA|ea|개|식|매)", t, re.I) or re.search(r"(\d+)\s*(?:EA|ea)\b", t)
    if not (book or usb):
        return None
    return {"book": f"{book[1]}부" if book else "-", "usb": f"{usb[1]}EA" if usb else "-", "note": "-", "src": "text"}


def read_deliver(pdf: Path, company_id: int | None = None) -> dict | None:
    """→ {book, usb, note, src} 또는 None."""
    import pymupdf

    try:
        doc = pymupdf.open(str(pdf))
    except Exception:  # noqa: BLE001
        return None
    try:
        pages = _pages(doc)
        for i in pages:
            got = _from_text(doc[i].get_text())
            if got:
                return got
        if company_id and pages:  # 글자로 못 읽음(그림 PDF 등) — AI 한 번
            from server.sitok import vision

            imgs = [doc[i].get_pixmap(dpi=110).tobytes("jpg") for i in pages[:2]]
            try:
                raw = vision.ask_json(company_id, imgs, "이 과업지시서 쪽에서 과업성과물(보고서) 납품 항목을 찾아 JSON 하나로만 답하세요: "
                                      '{"book": "책자 수량(예: 3부, 없으면 -)", "usb": "USB·전자파일 수량(예: 2EA, 없으면 -)", "note": "비고(없으면 -)"}', max_tokens=800)
            except Exception:  # noqa: BLE001
                raw = None
            if isinstance(raw, dict) and (str(raw.get("book") or "-") != "-" or str(raw.get("usb") or "-") != "-"):
                return {"book": str(raw.get("book") or "-").strip(), "usb": str(raw.get("usb") or "-").strip(), "note": str(raw.get("note") or "-").strip(), "src": "ai"}
    finally:
        doc.close()
    return None
