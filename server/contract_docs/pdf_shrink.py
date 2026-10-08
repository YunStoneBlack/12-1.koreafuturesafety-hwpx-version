"""PDF 용량 줄이기(2026-10-08 사용자 — 기술지도보고서 40회차 합본이 199MB라 올리기 한도에 걸림). 글자·표(벡터)는 그대로, 그림만 해상도를 낮춘다.

- 사진(보고서 사진 칸 1400px — 칸에 비해 약 550dpi): 150dpi, JPG 품질 60(사용자 10/8 "150dpi 좋아" — 확대 비교로 차이 거의 없음)
- 쪽 전체 크기의 문서 그림(11번 제공자료·스캔 서류): 글씨를 읽어야 하므로 200dpi, 품질 70
- 손대지 않음: 도장·서명·로고처럼 작게 들어간 그림(가로 100pt 미만), 투명 배경 그림(smask), 이미 목표 해상도 근처인 그림
측정(보고서 3회차 37쪽): 7.1MB → 2.7MB(38%), 1초 안팎.
"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image

PHOTO_DPI, PHOTO_QUALITY = 150, 60
DOC_DPI, DOC_QUALITY = 200, 70
MIN_SHOWN_PT = 100     # 이보다 작게 들어간 그림(도장·서명·로고)은 그대로
DOC_SHOWN_PT = 400     # 이보다 넓게 들어간 그림은 문서 그림으로 봄
MARGIN = 1.15          # 목표보다 15% 넘게 높을 때만 줄임(줄여 봐야 거의 안 작아지는 그림은 두기)


def shrink_doc(doc: pymupdf.Document) -> int:
    """doc 안의 큰 그림을 줄인다(제자리). 줄인 그림 수."""
    shown: dict[int, float] = {}  # 그림 → 가장 크게 들어간 가로(pt)
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            for r in page.get_image_rects(xref):
                shown[xref] = max(shown.get(xref, 0.0), r.width)
    done = 0
    for xref, width_pt in shown.items():
        if width_pt < MIN_SHOWN_PT:
            continue
        info = doc.extract_image(xref)
        if not info or info.get("smask"):
            continue
        w, h = info["width"], info["height"]
        dpi, quality = (DOC_DPI, DOC_QUALITY) if width_pt >= DOC_SHOWN_PT else (PHOTO_DPI, PHOTO_QUALITY)
        target_w = round(width_pt / 72 * dpi)
        if w <= target_w * MARGIN:
            continue
        try:
            img = Image.open(io.BytesIO(info["image"]))
            img.load()
        except Exception:  # noqa: BLE001 — PIL이 못 여는 그림(특수 압축)은 그대로
            continue
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img = img.resize((target_w, max(1, round(h * target_w / w))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        if len(buf.getvalue()) >= len(info["image"]):
            continue
        doc[0].replace_image(xref, stream=buf.getvalue())  # 같은 그림을 쓰는 모든 쪽이 바뀜
        done += 1
    return done


def shrink_bytes(data: bytes) -> bytes:
    """PDF 바이트 → 줄인 PDF 바이트(더 커지면 원래 것)."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not shrink_doc(doc):
            return data
        out = doc.tobytes(garbage=3, deflate=True)
    return out if len(out) < len(data) else data
