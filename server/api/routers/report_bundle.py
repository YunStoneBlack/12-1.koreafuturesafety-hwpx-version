"""보고서 합본(2026-10-08 사용자 — 완수계에 붙일 기술지도보고서를 직원이 직접 합쳐 올리니 40회차 199MB로 올리기 한도에 걸림).

현장 화면 보고서 목록 [📚 보고서 합본 만들기]:
- PDF가 있는 회차를 회차 순서대로 합치고(PDF 없는 회차는 빠짐, "수정 전 버전"은 있는 PDF 그대로 넣고 알림 — 사용자 (나))
- 사진만 150dpi로 줄임(contract_docs/pdf_shrink.py — 글자·표·도장·서명 그대로)
- 현장 폴더에 "26-1)_현장명_보고서합본.pdf", 이 현장에 연결된 용역 계약이 있으면 완수계 붙임 "기술지도보고서" 칸에도 "00_보고서 합본(자동).pdf"로
  (다시 만들면 바뀜, 직접 올린 파일은 그대로)

- `GET  /sites/{id}/report-bundle` — 만든 합본 정보(없으면 exists False)
- `POST /sites/{id}/report-bundle` — 만들기
- `GET  /sites/{id}/report-bundle.pdf[?inline=1]` — 받기·보기
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_db import Site
from core.models_web import ServiceContract, User
from server.api import repo, storage
from server.api.deps import get_current_user, get_db
from server.api.routers.reports import pdf_outdated_map
from server.contract_docs import attachments, files, pdf_shrink

router = APIRouter(tags=["report-bundle"])
AUTO_NAME = "00_보고서 합본(자동).pdf"  # 완수계 붙임 칸에 넣는 이름(다시 만들면 덮어씀)


def _site(db: Session, user: User, site_id: int) -> Site:
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site


def bundle_path(db: Session, site: Site) -> Path:
    return storage.site_dir(db, site) / f"{storage.site_folder_name(db, site)}_보고서합본.pdf"


def _info(db: Session, site: Site) -> dict:
    path = bundle_path(db, site)
    if not path.exists():
        return {"exists": False}
    try:
        with pymupdf.open(path) as doc:
            pages = doc.page_count
    except Exception:  # noqa: BLE001
        pages = 0
    st = path.stat()
    return {"exists": True, "pages": pages, "size_mb": round(st.st_size / 1e6, 1),
            "made_at": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")}


@router.get("/sites/{site_id}/report-bundle")
def bundle_info(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _info(db, _site(db, user, site_id))


@router.post("/sites/{site_id}/report-bundle")
def make_bundle(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _site(db, user, site_id)
    reports = repo.list_reports_for_site(db, user.company_id, site.id)
    outdated = pdf_outdated_map(db, reports) if reports else {}
    have = [r for r in reports if r.pdf_path and Path(r.pdf_path).exists()]
    if not have:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF를 만든 보고서가 없습니다 — 보고서 화면에서 'PDF 생성'을 먼저 하세요.")
    skipped = [r.visit_no for r in reports if r not in have]
    old = [r.visit_no for r in have if outdated.get(r.id)]
    out = pymupdf.open()
    raw = 0
    for r in have:
        raw += Path(r.pdf_path).stat().st_size
        with pymupdf.open(r.pdf_path) as doc:
            out.insert_pdf(doc)
    pdf_shrink.shrink_doc(out)
    dest = bundle_path(db, site)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.pdf")
    out.save(tmp, garbage=3, deflate=True)
    out.close()
    tmp.replace(dest)

    contract = db.query(ServiceContract).filter(ServiceContract.site_id == site.id).first()
    if contract is not None:  # 연결된 계약의 완수계 붙임 "기술지도보고서" 칸에 자동으로
        slot = attachments.slot_dir(files.contract_dir(contract), "done", "report")
        slot.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, slot / AUTO_NAME)
    return _info(db, site) | {
        "count": len(have), "skipped": skipped, "outdated": old, "raw_mb": round(raw / 1e6, 1),
        "contract": {"id": contract.id, "title": contract.title} if contract is not None else None,
    }


@router.get("/sites/{site_id}/report-bundle.pdf")
def download_bundle(site_id: int, inline: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _site(db, user, site_id)
    path = bundle_path(db, site)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 만든 보고서 합본이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline" if inline else "attachment")
