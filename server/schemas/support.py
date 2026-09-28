"""10. 사업장 지원 사항 (TBM 교육 + 계측자료) / 11. 제공자료."""

from __future__ import annotations

from pydantic import BaseModel


class TbmIn(BaseModel):
    attendee_count: int | None = None
    location: str = ""
    content: str = ""
    material: str = ""


class TbmOut(TbmIn):
    has_photo: bool = False


class MeasurementIn(BaseModel):
    value: str = ""
    manual_verdict: str = ""  # "" | "양호" | "불량"
    manual_action: str = ""


class MeasurementOut(MeasurementIn):
    instrument_type: str
    unit: str = ""
    has_photo: bool = False


class MaterialIn(BaseModel):
    """보낸 필드만 갱신(exclude_unset) — material_id를 보내면 라이브러리 자료로 지정."""

    title: str = ""
    material_id: int | None = None


class MaterialOut(BaseModel):
    slot: int
    title: str = ""
    material_id: int | None = None  # 라이브러리 자료면 그 id, 직접 올린 이미지거나 비었으면 None
    has_photo: bool = False
