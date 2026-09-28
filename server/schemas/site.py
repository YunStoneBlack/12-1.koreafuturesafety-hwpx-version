from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class SiteIn(BaseModel):
    """desktop/views/site_form_view.py의 '신규현장추가' 폼 필드 그대로 — 계약서 PDF
    자동인식(POST /sites/extract-from-contract)이 채워주는 항목과 1:1로 맞춰야 해서
    Milestone 1 초안(이름/주소만)보다 넓혔다."""

    name: str
    # 표지 "관리번호" — 현장 단위(모든 회차 공통), 직접 입력 또는 GET /sites/next-management-no로 자동생성
    management_no: str = ""
    address: str = ""
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    amount: int | None = None
    site_mgmt_no: str = ""
    biz_start_no: str = ""
    manager_name: str = ""
    manager_phone: str = ""
    manager_email: str = ""
    hq_company: str = ""
    corp_reg_no: str = ""
    biz_reg_no: str = ""
    license_no: str = ""
    hq_phone: str = ""
    hq_address: str = ""
    total_guidance_count: int | None = None
    assigned_staff_id: int | None = None


class SiteOut(SiteIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
