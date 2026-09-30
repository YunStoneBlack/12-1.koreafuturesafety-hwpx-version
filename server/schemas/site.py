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
    # 진행 막대(공기 경과 vs 기술지도 수행, server/api/site_pace_out.py) — 현장 조회·목록에서만 채움
    pace: dict | None = None


class SiteListItem(SiteOut):
    """현장 목록 화면용 — 현장 정보 + 보고서 진행 요약(목록에서 바로 보이게)."""

    report_count: int = 0
    last_visit_no: int | None = None
    last_guidance_date: datetime.date | None = None
    staff_name: str = ""
    # [📍 지도] 버튼이 여는 주소(지도 방문 주소, 없으면 현장 주소 — server/api/routers/site_contacts.py)
    map_address: str = ""
