from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class ReportIn(BaseModel):
    """보고서 헤더급 + 섹션 1(결재·통보 정보) 필드. 서명 이미지 자체는 별도 업로드
    엔드포인트(POST/DELETE /reports/{id}/notify-signature)가 관리하므로 여기 안 넣는다.
    나머지 섹션(사진/위험성평가 표 등)은 다음 단계에서 이어서 추가한다 — Report는 이
    필드들 외엔 전부 기본값(빈 문자열/None/False)이라도 실제 렌더링 가능한 PDF가 나온다."""

    assigned_staff_id: int | None = None
    visit_no: int | None = None  # 회차 — 수정 가능(데스크톱 Sub-phase 22와 동일), 생성 시 비우면 자동 증가
    guidance_date: datetime.date | None = None
    prev_guidance_date: datetime.date | None = None  # 이전 지도일(None = 없음, 1회차 등)
    progress_rate: int | None = None
    notification_method: str = ""
    notify_signee_name: str = ""
    special_note: str = ""

    # 2. 기타 특이사항
    misc_overwork: bool = False
    misc_no_photo: bool = False
    misc_other: bool = False
    misc_other_text: str = ""
    accident_status: str = ""  # "" | "유" | "무"
    accident_content: str = ""

    # 5. 대형사고 위험작업 사항 — core.constants.MAJOR_HAZARD_WORKS의 체크된 인덱스 목록
    major_hazard_work_checks: list[int] = []

    # 6. 위험성평가 기준 및 12대 기인물 — 문자열 목록. "{번호}"는 기인물 자체 체크,
    # "{번호}-{줄번호}"는 그 기인물의 특정 지도사항 줄 체크(core/report_builder_hwpx_fields.py::
    # fill_hazard_factor_fields가 이 정확한 형식을 그대로 읽는다 — 임의로 바꾸면 렌더링 안 됨).
    hazard_factor_checks: list[str] = []
    # 6-3. 건설기계장비/위험기계기구/유해위험물질 평가 — 각각 core.constants의 해당 목록과
    # 같은 순서로 [{"checked": bool, "notes": ["양호"|"미흡"|"", ...]}, ...]
    machinery_checks: list[dict] = []
    hand_tool_checks: list[dict] = []
    hazmat_checks: list[dict] = []


class ReportOut(ReportIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    visit_no: int
    status: str
    # 현장 화면 목록용 — PDF를 만든 뒤(렌더 작업 시작 이후) 내용을 고쳤으면 True(목록 API에서만 채움)
    pdf_outdated: bool = False
    # 고객사에 마지막으로 메일 보낸 시각·받는 사람(목록 API에서만 채움, server/api/routers/report_mail.py)
    last_mail_at: str = ""
    last_mail_to: str = ""
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
