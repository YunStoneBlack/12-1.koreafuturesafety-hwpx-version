from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PreviousFindingIn(BaseModel):
    """PATCH는 보낸 필드만 갱신한다(exclude_unset). 이월 항목은 제목/내용/이행 전 위험성이
    원본을 따르므로 서버가 그 세 가지를 무시한다."""

    title: str = ""
    content: str = ""
    result_status: Literal["", "확인불가", "보완필요", "이행완료"] = ""
    # 수기 항목의 "이행 전 위험성"(1~3) — 이월 항목은 원본 값이 우선이라 무시
    manual_likelihood: int | None = Field(default=None, ge=1, le=3)
    manual_severity: int | None = Field(default=None, ge=1, le=3)


class PreviousFindingOut(BaseModel):
    slot: int
    title: str = ""
    content: str = ""
    result_status: str = ""
    has_photo: bool = False
    has_completion_photo: bool = False
    carried: bool = False  # 직전 회차 8번에서 자동 이월된 항목(제목/내용/사진 잠김)
    before_likelihood: int | None = None
    before_severity: int | None = None
    after_likelihood: int | None = None
    after_severity: int | None = None


class PreviousFindingList(BaseModel):
    prev_visit_no: int | None = None  # 직전 회차 번호(없으면 None = 1회차 등)
    carried_count: int = 0
    items: list[PreviousFindingOut]
