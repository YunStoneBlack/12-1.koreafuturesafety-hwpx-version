"""착수계·완수계 파일 자리(storage 규칙 — 사람이 탐색기에서 바로 찾게)와 올린 서류 저장.

    저장소\\
     ├ _서류\\회사\\국세 완납증명서.jpg …                 완수계에 붙는 회사 서류
     ├ _서류\\기술자\\권만중_3\\자격증.jpg …               착수계 기술자 서류(이름_번호 — 같은 이름이 있어도 안 겹치게)
     └ _용역계약\\007_2025 한탄강 생태경관단지…\\           용역 계약 하나(번호_용역명 — 현장보다 먼저 생기므로 현장 폴더 밖, 2026-10-06)
          ├ 착수계.xlsx / 착수계.pdf(합본) / 완수계.xlsx / 완수계.pdf / 용역계약서.pdf
          └ 붙임\\산출내역서\\01_….pdf …                    받아 온 붙임 파일(attachments.py)

용역명이 바뀌면 폴더 이름도 다음에 열 때 맞춘다(번호로 찾음). 받을 때 파일 이름은 "용역명_착수계.pdf".
올린 서류는 그림(JPG·PNG 등)이든 PDF든 받아서 JPG 한 장으로 둔다 — PDF는 첫 장(정부24·홈택스 완납증명서는 보통 PDF 한 장).
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import pymupdf
from fastapi import HTTPException, status
from PIL import Image, ImageOps

from core.db import DATA_DIR
from server.api import storage

DOC_DIR = DATA_DIR / "_서류"
CONTRACT_ROOT = DATA_DIR / "_용역계약"
MAX_SIDE = 2000
PDF_DPI = 200
NAME_MAX = 40


def company_doc_path(label: str) -> Path:
    return DOC_DIR / "회사" / f"{storage._clean(label)}.jpg"


def person_doc_path(person_id: int, name: str, label: str) -> Path:
    return DOC_DIR / "기술자" / f"{storage._clean(name) or '기술자'}_{person_id}" / f"{storage._clean(label)}.jpg"


def contract_dir(contract) -> Path:
    """계약 폴더 "007_용역명". 예전 이름(용역명이 바뀜) 폴더가 있으면 지금 이름으로 바꾼다(실패하면 예전 폴더 그대로 씀)."""
    prefix = f"{contract.id:03d}_"
    want = CONTRACT_ROOT / (prefix + (storage._clean(storage._clean(contract.title or "")[:NAME_MAX]) or "용역"))
    if want.exists():
        return want
    old = next((p for p in CONTRACT_ROOT.glob(f"{prefix}*") if p.is_dir()), None) if CONTRACT_ROOT.exists() else None
    if old is not None:
        try:
            old.rename(want)
        except OSError:
            return old
    return want


def out_path(contract, name: str) -> Path:
    """name = "착수계.xlsx" | "착수계.pdf" | "완수계.xlsx" | "완수계.pdf" | "용역계약서.pdf"."""
    return contract_dir(contract) / name


def download_name(contract, name: str) -> str:
    title = storage._clean((contract.title or "용역")[:NAME_MAX]) or "용역"
    return f"{title}_{name}"


def delete_contract_files(contract) -> None:
    d = contract_dir(contract)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


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
