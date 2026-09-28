from __future__ import annotations

from pydantic import BaseModel


class FindingIn(BaseModel):
    title: str = ""
    content: str = ""
    law_citation: str = ""
    likelihood: int | None = None  # 가능성 1~3
    severity: int | None = None  # 중대성 1~3
    action_status: str = "추후확인"  # "추후확인" | "즉시이행"
    description: str = ""  # 지도자가 적는 간단 설명 — AI추천 입력용(보고서엔 안 나감)


class FindingOut(FindingIn):
    slot: int
    has_photo: bool = False
