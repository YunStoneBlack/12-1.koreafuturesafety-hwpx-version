"""착수계·완수계 파일 자리(storage 규칙 — 사람이 탐색기에서 바로 찾게)와 올린 서류 저장.

    저장소\\
     ├ _서류\\회사\\국세 완납증명서.jpg …                 완수계에 붙는 회사 서류
     ├ _서류\\기술자\\권만중_3\\자격증.jpg …               착수계 기술자 서류(이름_번호 — 같은 이름이 있어도 안 겹치게)
     └ 26-1)_현장명\\착수계·완수계\\26-1)_현장명_착수계.xlsx / .pdf, …_완수계.xlsx / .pdf, …_용역계약서.pdf

올린 서류는 그림(JPG·PNG 등)이든 PDF든 받아서 JPG 한 장으로 둔다 — PDF는 첫 장(정부24·홈택스 완납증명서는 보통 PDF 한 장).
"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from fastapi import HTTPException, status
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from core.db import DATA_DIR
from core.models_db import Site
from server.api import storage

DOC_DIR = DATA_DIR / "_서류"
OUT_SUBDIR = storage.CONTRACT_SUBDIR
MAX_SIDE = 2000
PDF_DPI = 200


def company_doc_path(label: str) -> Path:
    return DOC_DIR / "회사" / f"{storage._clean(label)}.jpg"


def person_doc_path(person_id: int, name: str, label: str) -> Path:
    return DOC_DIR / "기술자" / f"{storage._clean(name) or '기술자'}_{person_id}" / f"{storage._clean(label)}.jpg"


def site_out_dir(db: Session, site: Site) -> Path:
    return storage.site_dir(db, site) / OUT_SUBDIR


def site_out_path(db: Session, site: Site, kind_label: str, suffix: str) -> Path:
    """kind_label = "착수계" | "완수계" | "용역계약서", suffix = ".xlsx" | ".pdf"."""
    return site_out_dir(db, site) / f"{storage.site_folder_name(db, site)}_{kind_label}{suffix}"


def find_out(db: Session, site: Site, kind_label: str, suffix: str) -> Path | None:
    """만든 파일 찾기 — 지금 이름이 없으면 같은 폴더의 "…_착수계.xlsx"(현장명이 바뀌기 전 이름) 중 최근 것."""
    exact = site_out_path(db, site, kind_label, suffix)
    if exact.exists():
        return exact
    folder = site_out_dir(db, site)
    found = sorted(folder.glob(f"*_{kind_label}{suffix}"), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    return found[-1] if found else None


def to_jpeg(data: bytes, filename: str) -> bytes:
    """올린 파일(그림·PDF) → JPG 바이트. 못 읽으면 400."""
    try:
        if data[:4] == b"%PDF" or filename.lower().endswith(".pdf"):
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if doc.page_count == 0:
                    raise ValueError("빈 PDF")
                pix = doc[0].get_pixmap(dpi=PDF_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
        else:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        return buf.getvalue()
    except Exception as err:  # noqa: BLE001 — 그림·PDF가 아니거나 깨진 파일
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "그림(JPG·PNG) 또는 PDF 파일만 올릴 수 있습니다.") from err


def save_jpeg(data: bytes, filename: str, dest: Path) -> Path:
    jpg = to_jpeg(data, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(jpg)
    return dest
