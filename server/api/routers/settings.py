"""회사별 설정 — 지금은 Claude API 키 하나뿐(계약서 자동인식에 필요). 데스크톱 exe의
"AI 관리" 화면과 같은 역할이지만, 웹판은 회사마다 다른 키를 쓸 수 있어야 해서
`core/config.py`의 company_id 인자를 통해 이 회사(`user.company_id`)로 범위를 좁힌다."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core import config
from core.models_web import User
from server.api.deps import get_current_user
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
