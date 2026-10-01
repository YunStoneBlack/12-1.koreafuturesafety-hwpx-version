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


def resolve_material_path(stored_path: str | None) -> Path | None:
    """DB에 저장된 file_path/thumbnail_path를 실제 파일로 해석한다.

    이 경로는 시딩 당시 `BASE_DIR`을 기준으로 만든 절대경로라, exe 배포 폴더를 통째로
    복사/압축해서 다른 위치(다른 PC, 다른 폴더명)로 옮기면 그대로는 존재하지 않게 된다.
    그대로 있으면 쓰고, 없으면 파일명(및 thumbnails 하위 여부)만 살려서 지금 이 PC의
    `data/materials/` 밑에서 다시 찾는다.
    """
    if not stored_path:
        return None
    path = Path(stored_path)
    if path.exists():
        return path

    from core.db import BASE_DIR, DATA_DIR

    # 웹판 저장소의 자료실(2026-10-01 — DATA_DIR/_자료실) → 예전 자리(data/materials) 순서로 찾는다
    for materials_dir in (DATA_DIR / "_자료실", BASE_DIR / "data" / "materials"):
        fallback = materials_dir / "thumbnails" / path.name if path.parent.name == "thumbnails" else materials_dir / path.name
        if fallback.exists():
            return fallback
    return None


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


def render_pdf_pages(pdf_path: str | Path, width: int = 760, max_pages: int = 40) -> list[bytes]:
    """PDF 각 페이지를 PNG 바이트로 렌더링한다 (보고서 미리보기 모달용).

    실패해도 예외를 던지지 않고 빈 리스트를 반환한다 — 호출부가 "미리보기를 만들지
    못했습니다" 같은 메시지로 처리하게 한다.
    """
    try:
        doc = pymupdf.open(str(pdf_path))
        pages: list[bytes] = []
        for i in range(min(doc.page_count, max_pages)):
            page = doc.load_page(i)
            zoom = width / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            pages.append(pix.tobytes("png"))
        doc.close()
        return pages
    except Exception:
        return []


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
