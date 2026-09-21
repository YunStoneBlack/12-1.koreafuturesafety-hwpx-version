"""hwpx에 넣을 이미지를 흰 배경 JPG 바이트로 바꾼다 — PNG 등은 한글 2018/2024의 PDF 저장(미리보기·PDF 생성)에서 96dpi로 뭉개진다.

실제 2024 PC에서 만든 PDF를 열어보니 우리가 넣은 PNG(결재란 도장 220dpi→96dpi, 서명 653dpi→96dpi, PDF에서
그려낸 제공자료 226dpi→96dpi)는 전부 화면용 해상도로 줄어 있었고, JPG(폰 사진, 템플릿 로고)는 원본 해상도가
남아 있었다(2026-09-21). 한글 파일 자체는 선명하고 PDF만 흐린 증상과 일치한다. 한글 2020은 PNG도 원본 해상도로
PDF에 넣는다. 그래서 JPG가 아닌 이미지는 흰 배경에 합성한 고화질 JPG로 바꿔 넣는다 — 투명 배경이 필요한 서명은
"글 뒤로" 배치(`report_builder_hwpx_images._insert_floating_signature`)와 함께 쓴다(서명 칸에는 배경 채우기가 없다).
"""

from __future__ import annotations

import hashlib
import io
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageOps

_JPEG_QUALITY = 95

# 보고서에 넣는 사진의 긴 변 상한(px). 칸에 들어가는 가장 큰 사진도 가로 10cm 안팎이라 1400px이면 약 350dpi — 인쇄해도
# 차이를 못 느끼면서 폰 원본(4000px대)보다 PDF는 약 1/5, hwpx는 약 1/8로 줄어 국가기관 제출 용량 제한(10MB)을 맞춘다(2026-09-21).
PHOTO_MAX_LONG_SIDE = 1400
_PHOTO_QUALITY = 85
_PHOTO_CACHE_DIR = Path(tempfile.gettempdir()) / "hwp_report_photos"
_CACHE_MAX_AGE_SECONDS = 14 * 24 * 3600
_cache_pruned = False


def _prune_photo_cache() -> None:
    """오래된 줄인 사진 사본을 지운다(같은 사진은 파일 이름이 같아 재사용되므로, 쌓이는 건 안 쓰는 사진뿐)."""
    global _cache_pruned
    if _cache_pruned:
        return
    _cache_pruned = True
    try:
        limit = time.time() - _CACHE_MAX_AGE_SECONDS
        for old in _PHOTO_CACHE_DIR.glob("*.jpg"):
            if old.stat().st_mtime < limit:
                old.unlink()
    except OSError:
        pass


def prepare_photo_for_report(path: Path) -> Path:
    """보고서에 넣을 사진 파일을 돌려준다 — 긴 변이 1400px을 넘으면 줄인 JPEG 사본을, 폰 사진의 "회전 표시(EXIF)"가 있으면 회전을
    실제 픽셀에 반영한 사본을 만든다. 원본 파일은 그대로 둔다.

    회전을 미리 반영하는 이유: 폰 사진은 가로 픽셀(4000×3000)에 "90도 회전" 표시만 붙은 경우가 많은데, 칸에 비율 맞추는 계산은
    픽셀 크기로 하므로 표시와 실제가 어긋나면 사진이 눌려 보일 수 있다. 줄이거나 회전할 필요가 없으면(작은 사진·도장·서명
    등) 원본 경로를 그대로 돌려줘서 화질을 건드리지 않는다. 같은 사진은 사본을 재사용한다."""
    try:
        stat = path.stat()
        with Image.open(path) as img:
            width, height = img.size
            rotated = (img.getexif().get(274) or 1) != 1
            if max(width, height) <= PHOTO_MAX_LONG_SIDE and not rotated:
                return path
            key = hashlib.sha1(f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{PHOTO_MAX_LONG_SIDE}".encode()).hexdigest()
            target = _PHOTO_CACHE_DIR / f"{key}.jpg"
            if target.exists() and target.stat().st_size > 0:
                return target
            img.load()
            fixed = ImageOps.exif_transpose(img)
            if fixed.mode in ("RGBA", "LA") or (fixed.mode == "P" and "transparency" in fixed.info):
                rgba = fixed.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.split()[-1])
                fixed = flat
            else:
                fixed = fixed.convert("RGB")
            ratio = PHOTO_MAX_LONG_SIDE / max(fixed.size)
            shrunk = ratio < 1
            if shrunk:
                fixed = fixed.resize((round(fixed.width * ratio), round(fixed.height * ratio)), Image.LANCZOS)
            _PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _prune_photo_cache()
            temp = target.with_suffix(".tmp")
            fixed.save(temp, "JPEG", quality=_PHOTO_QUALITY if shrunk else 92, dpi=(72, 72))
            temp.replace(target)
            return target
    except Exception:  # noqa: BLE001 - 사진을 못 읽으면 예전처럼 원본 그대로 넣는다
        return path


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
