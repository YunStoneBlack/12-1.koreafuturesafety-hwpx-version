from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class SiteIn(BaseModel):
    """1차 범위: dashboard_view.py + site_detail_view.py에 있던 현장 CRUD 필드 그대로."""

    name: str
    address: str = ""
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    amount: int | None = None
    manager_name: str = ""
    manager_phone: str = ""
    manager_email: str = ""
    hq_company: str = ""
    assigned_staff_id: int | None = None


class SiteOut(SiteIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
