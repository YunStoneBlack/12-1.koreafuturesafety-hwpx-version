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
from server.api.security import hash_password, verify_password
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


# ---------- 현장 삭제 비밀번호 — 현장 삭제(DELETE /sites/{id}) 때 입력해야 하는 회사 공용 비밀번호 ----------
# 보고서 화면은 그룹웨어 로그인을 그대로 쓰고 자체 비밀번호가 없어서, 아는 사람만 현장을 지울 수 있게 따로 둔다.
# 이미 정해져 있으면 바꿀 때 지금 비밀번호가 필요하다(누구나 설정 화면에서 덮어써 버리면 의미가 없으므로).
# 잊어버리면 DB app_setting의 site_delete_password_hash(해당 회사) 값을 지우면 다시 정할 수 있다.

class DeletePasswordStatus(BaseModel):
    is_set: bool


class DeletePasswordIn(BaseModel):
    current_password: str = ""
    new_password: str


@router.get("/delete-password", response_model=DeletePasswordStatus)
def get_delete_password_status(user: User = Depends(get_current_user)):
    return DeletePasswordStatus(is_set=bool(config.get_site_delete_password_hash(user.company_id)))


@router.post("/delete-password", response_model=DeletePasswordStatus)
def set_delete_password(body: DeletePasswordIn, user: User = Depends(get_current_user)):
    current_hash = config.get_site_delete_password_hash(user.company_id)
    if current_hash and not verify_password(body.current_password, current_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "지금 비밀번호가 맞지 않습니다.")
    if len(body.new_password) < 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "새 비밀번호는 4자 이상으로 정하세요.")
    config.set_site_delete_password_hash(hash_password(body.new_password), user.company_id)
    return DeletePasswordStatus(is_set=True)


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


# ---------- 알림 설정(관리자 알림 메일 등) — 2026-10-01 "15일 지도 기한" 알림을 없애면서 화면은 숨기고 값만 보존.
# 나중에 다른 알림 기능에서 관리자 메일을 다시 쓸 때 살린다(settings.html #alert-panel). ----------
class DeadlineAlertSettings(BaseModel):
    enabled: bool = True
    imminent_days: int = config.DEFAULT_IMMINENT_DAYS
    admin_email: str = ""


@router.get("/deadline-alert", response_model=DeadlineAlertSettings)
def get_deadline_alert(user: User = Depends(get_current_user)):
    return DeadlineAlertSettings(
        enabled=config.get_deadline_alert_enabled(user.company_id),
        imminent_days=config.get_deadline_imminent_days(user.company_id),
        admin_email=config.get_deadline_admin_email(user.company_id),
    )


@router.post("/deadline-alert", response_model=DeadlineAlertSettings)
def set_deadline_alert(body: DeadlineAlertSettings, user: User = Depends(get_current_user)):
    from server.api.mailer import valid_email

    if not 0 <= body.imminent_days <= 14:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "임박 기준은 0~14일 사이로 정하세요.")
    emails = [a.strip() for a in body.admin_email.split(",") if a.strip()]
    bad = [a for a in emails if not valid_email(a)]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"메일 주소를 확인하세요: {', '.join(bad)}")
    config.set_deadline_alert_enabled(body.enabled, user.company_id)
    config.set_deadline_imminent_days(body.imminent_days, user.company_id)
    config.set_deadline_admin_email(", ".join(emails), user.company_id)
    return get_deadline_alert(user)


