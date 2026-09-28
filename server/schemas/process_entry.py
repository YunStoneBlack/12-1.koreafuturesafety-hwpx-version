from __future__ import annotations

from pydantic import BaseModel


class ProcessItemIn(BaseModel):
    hazard: str = ""
    prevention: str = ""
    risk_level: str = ""  # "" | "상" | "중" | "하"


class ProcessEntryIn(BaseModel):
    process_name: str = ""
    items: list[ProcessItemIn] = []


class ProcessEntryOut(ProcessEntryIn):
    slot: int
