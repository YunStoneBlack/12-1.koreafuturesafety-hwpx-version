"""제공자료 라이브러리용 썸네일 생성 모듈.

원본 포스터 이미지는 수 MB짜리 고해상도(수천 px)인 경우가 많아서, 그리드에 매번
원본을 그대로 디코딩·축소해서 그리면 검색/선택할 때마다 눈에 띄게 느려진다.
그래서 그리드 표시용으로 작게 리사이즈한 캐시본을 별도로 만들어두고, 원본은
"크게 보기"(MaterialPreviewDialog)에서만 연다.

poppler 같은 외부 실행파일 없이 동작하도록 PDF는 PyMuPDF를 사용한다.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

THUMBNAIL_WIDTH = 300


def generate_pdf_thumbnail(pdf_path: str | Path, output_path: str | Path) -> bool:
    """PDF 첫 페이지를 PNG로 렌더링한다. 실패하면 False를 반환한다(예외를 던지지 않음)."""
    try:
        doc = pymupdf.open(str(pdf_path))
        if doc.page_count == 0:
            return False
        page = doc.load_page(0)
        zoom = THUMBNAIL_WIDTH / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))
        doc.close()
        return True
    except Exception:
        return False


def generate_image_thumbnail(image_path: str | Path, output_path: str | Path) -> bool:
    """jpg/png 원본을 그리드 표시용 크기로 축소해서 저장한다."""
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            ratio = THUMBNAIL_WIDTH / img.width
            new_size = (THUMBNAIL_WIDTH, max(1, int(img.height * ratio)))
            resized = img.resize(new_size, Image.LANCZOS)
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            resized.save(str(output_path), "JPEG", quality=85)
        return True
    except Exception:
        return False
