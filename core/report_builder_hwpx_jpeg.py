"""hwpx에 넣을 이미지를 흰 배경 JPG 바이트로 바꾼다 — PNG 등은 한글 2018/2024의 PDF 저장(미리보기·PDF 생성)에서 96dpi로 뭉개진다.

실제 2024 PC에서 만든 PDF를 열어보니 우리가 넣은 PNG(결재란 도장 220dpi→96dpi, 서명 653dpi→96dpi, PDF에서
그려낸 제공자료 226dpi→96dpi)는 전부 화면용 해상도로 줄어 있었고, JPG(폰 사진, 템플릿 로고)는 원본 해상도가
남아 있었다(2026-09-21). 한글 파일 자체는 선명하고 PDF만 흐린 증상과 일치한다. 한글 2020은 PNG도 원본 해상도로
PDF에 넣는다. 그래서 JPG가 아닌 이미지는 흰 배경에 합성한 고화질 JPG로 바꿔 넣는다 — 투명 배경이 필요한 서명은
"글 뒤로" 배치(`report_builder_hwpx_images._insert_floating_signature`)와 함께 쓴다(서명 칸에는 배경 채우기가 없다).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

_JPEG_QUALITY = 95


def image_bytes_for_hwpx(path: Path) -> bytes:
    """`path` 이미지를 hwpx에 넣을 JPG 바이트로 돌려준다.

    이미 RGB/그레이 JPG면 손대지 않고 원본 바이트를 그대로 쓴다(폰 사진 화질 보존). 확장자가 아니라 실제
    내용으로 판단하므로 확장자가 잘못 붙은 파일도 바로잡힌다. CMYK 등 특수 JPG나 PNG·WEBP 등은 흰 배경 RGB
    JPG(품질 95, 색상 부표본 없음)로 바꾼다."""
    with Image.open(path) as img:
        if img.format == "JPEG" and img.mode in ("RGB", "L"):
            return path.read_bytes()
        img.load()
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[-1])
        else:
            flat = img.convert("RGB")
    buffer = io.BytesIO()
    flat.save(buffer, "JPEG", quality=_JPEG_QUALITY, subsampling=0, dpi=(72, 72))
    return buffer.getvalue()
