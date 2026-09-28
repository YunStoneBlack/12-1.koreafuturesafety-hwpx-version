from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class ReportIn(BaseModel):
    """보고서 헤더급 + 섹션 1(결재·통보 정보) 필드. 서명 이미지 자체는 별도 업로드
    엔드포인트(POST/DELETE /reports/{id}/notify-signature)가 관리하므로 여기 안 넣는다.
    나머지 섹션(사진/위험성평가 표 등)은 다음 단계에서 이어서 추가한다 — Report는 이
    필드들 외엔 전부 기본값(빈 문자열/None/False)이라도 실제 렌더링 가능한 PDF가 나온다."""

    assigned_staff_id: int | None = None
    guidance_date: datetime.date | None = None
    progress_rate: int | None = None
    notification_method: str = ""
    notify_signee_name: str = ""
    special_note: str = ""


class ReportOut(ReportIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    visit_no: int
    status: str
    pdf_path: str
    notify_signature_path: str = ""


class SignoffStatus(BaseModel):
    """섹션 1의 읽기전용 서명 상태 카드 3개(담당요원/결재란-이사/결재란-대표이사)용.
    실제 서명 이미지는 여기서 안 주고 등록 여부만 — 등록 자체는 담당요원 관리/설정
    화면에서 한다(데스크톱과 동일하게, 마법사 섹션 1은 상태만 보여준다)."""

    staff_signed: bool
    director_signed: bool
    ceo_signed: bool


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    error_message: str
