"""회사별 설정 — Claude API 키(데스크톱 "AI 관리"), 결재란 이사·대표이사 도장(데스크톱 "담당요원 관리"
하단 "결재선 서명"). 웹판은 회사마다 달라야 해서 `core/config.py`의 company_id 인자로 이 회사
(`user.company_id`)로 범위를 좁힌다 — 렌더러도 site.company_id로 같은 값을 찾는다
(report_builder_hwpx_images.fill_signoff_images)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core import config
from core.models_web import User
from server.api.deps import get_current_user
from server.api.signature_files import normalize_source, save_signature_upload
from server.schemas.settings import ApiKeyIn, ApiKeyStatus

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/api-key", response_model=ApiKeyStatus)
def get_api_key_status(user: User = Depends(get_current_user)):
    raw = config.get_raw_api_key(user.company_id)
    if not raw:
        return ApiKeyStatus(has_key=False)
    return ApiKeyStatus(has_key=True, masked=f"…{raw[-4:]}" if len(raw) > 4 else "…")


@router.post("/api-key", response_model=ApiKeyStatus)
def set_api_key(body: ApiKeyIn, user: User = Depends(get_current_user)):
    config.set_api_key(body.api_key, user.company_id)
    return get_api_key_status(user)


# ---------- 결재란(이사/대표이사) 도장 — 한 번 등록하면 이 회사 모든 보고서에 자동 반영 ----------

Role = Literal["director", "ceo"]


class SignatureStatus(BaseModel):
    director: bool
    ceo: bool


def _status(company_id: int) -> SignatureStatus:
    def registered(role: str) -> bool:
        path, _ = config.get_company_signature(role, company_id)
        return bool(path) and Path(path).exists()

    return SignatureStatus(director=registered("director"), ceo=registered("ceo"))


@router.get("/signatures", response_model=SignatureStatus)
def get_signatures(user: User = Depends(get_current_user)):
    return _status(user.company_id)


@router.post("/signatures/{role}", response_model=SignatureStatus)
async def upload_signature(
    role: Role, file: UploadFile, source: str = Form("drawn"), user: User = Depends(get_current_user)
):
    # 데스크톱은 data/signatures/company_{role}.png 하나 — 웹판은 회사마다 따로
    dest = await save_signature_upload(file, f"company_{user.company_id}_{role}.png")
    config.set_company_signature(role, str(dest), normalize_source(source), user.company_id)
    return _status(user.company_id)


@router.delete("/signatures/{role}", response_model=SignatureStatus)
def delete_signature(role: Role, user: User = Depends(get_current_user)):
    path, _ = config.get_company_signature(role, user.company_id)
    if path:
        Path(path).unlink(missing_ok=True)
    config.set_company_signature(role, "", "", user.company_id)
    return _status(user.company_id)


@router.get("/signatures/{role}")
def get_signature_image(role: Role, user: User = Depends(get_current_user)):
    path, _ = config.get_company_signature(role, user.company_id)
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 도장이 없습니다.")
    return FileResponse(path, media_type="image/png")
