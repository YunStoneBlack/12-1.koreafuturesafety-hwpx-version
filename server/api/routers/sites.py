from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from core import config
from core.contract_analyzer import extract_site_info
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.site import SiteIn, SiteOut

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteOut])
def list_sites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.list_sites(db, user.company_id)


@router.post("/extract-from-contract", response_model=SiteIn)
async def extract_from_contract(file: UploadFile, user: User = Depends(get_current_user)):
    """계약서·공문 PDF를 업로드하면 Claude로 '신규현장추가' 폼 필드를 추출해 돌려준다
    (desktop/views/site_form_view.py의 계약서 자동인식과 동일한 기능·같은 프롬프트,
    core/contract_analyzer.py를 그대로 재사용). 여기서 DB에 아무것도 저장하지 않는다 —
    프론트가 반환된 값으로 폼을 미리 채워주고, 사용자가 확인/수정한 뒤 POST /sites로
    실제 저장을 따로 요청한다.

    실측 약 20초 걸리는 순수 API 호출(한글 COM처럼 단일 인스턴스 제약이 없음)이라 큐 없이
    이 요청 안에서 바로 처리한다 — FastAPI가 동기 함수를 스레드풀에서 돌려주므로 다른
    요청을 막지 않는다."""
    if not config.has_api_key(user.company_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Claude API 키가 설정되어 있지 않습니다. 설정 화면에서 먼저 등록하세요.",
        )
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF 파일만 업로드할 수 있습니다.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "contract.pdf"
        tmp_path.write_bytes(await file.read())
        try:
            data = extract_site_info(tmp_path, company_id=user.company_id)
        except Exception as e:  # noqa: BLE001 -- Claude/파싱 오류를 그대로 사용자에게 보여줌
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"계약서 분석에 실패했습니다: {e}") from e

    return data


@router.post("", response_model=SiteOut)
def create_site(body: SiteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repo.create_site(db, user.company_id, **body.model_dump())


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site


@router.patch("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: int, body: SiteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    site = repo.update_site(db, user.company_id, site_id, **body.model_dump())
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site
