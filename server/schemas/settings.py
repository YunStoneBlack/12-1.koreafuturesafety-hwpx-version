from __future__ import annotations

from pydantic import BaseModel


class ApiKeyIn(BaseModel):
    api_key: str


class ApiKeyStatus(BaseModel):
    """실제 키 값은 저장 후 다시 브라우저로 내려주지 않는다(불필요한 노출을 줄이려고) —
    설정 여부와 끝 4자리만 마스킹해서 보여준다."""

    has_key: bool
    masked: str = ""
