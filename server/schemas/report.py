from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class ReportIn(BaseModel):
    """1차 범위: 보고서 헤더급 최소 필드만. 나머지 ~10개 섹션(사진/서명/위험성평가 표 등)은
    다음 단계에서 이어서 추가한다 — core/models_db.py의 Report는 이 필드들 외엔 전부
    기본값(빈 문자열/None/False)이라도 실제 렌더링 가능한 PDF가 나온다."""

    assigned_staff_id: int | None = None
    guidance_date: datetime.date | None = None
    progress_rate: int | None = None
    notification_method: str = ""
    special_note: str = ""


class ReportOut(ReportIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    visit_no: int
    status: str
    pdf_path: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    error_message: str
