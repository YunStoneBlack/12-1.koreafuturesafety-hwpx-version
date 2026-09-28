from __future__ import annotations

from pydantic import BaseModel


class PreviousFindingIn(BaseModel):
    title: str = ""
    content: str = ""
    result_status: str = ""  # "" | "확인불가" | "보완필요" | "이행완료"


class PreviousFindingOut(PreviousFindingIn):
    slot: int
    has_photo: bool = False
    has_completion_photo: bool = False
