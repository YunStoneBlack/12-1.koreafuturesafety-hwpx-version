"""전자계약 용역계약서 PDF(조달청·지자체 전자계약 표준 양식)에서 착수계·완수계에 쓰는 값을 읽는다.

글자가 그대로 들어 있는 PDF라 pdfplumber로 충분하다(AI 안 씀). x_tolerance=1.5 — 기본값(3)은 "2025한탄강생태…"처럼 띄어쓰기가 붙어 나옴.
못 읽은 값은 빈 칸으로 두고(지어내지 않음) 화면에서 사람이 채운다.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import pdfplumber


def _date(text: str) -> datetime.date | None:
    m = re.search(r"(\d{4})\s*[/.\-년]\s*(\d{1,2})\s*[/.\-월]\s*(\d{1,2})", text or "")
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _after(text: str, label: str, stop: str = r"$") -> str:
    """"라벨 : 값" 한 줄에서 값(다음 라벨 앞까지)."""
    m = re.search(label + r"\s*:\s*(.*?)\s*(?:" + stop + ")", text, re.M)
    return m[1].strip() if m else ""


def read_text(path: str | Path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text(x_tolerance=1.5) or "") for p in pdf.pages)


def parse_text(text: str) -> dict:
    """계약서 글자 → {client, title, contract_no, amount, contract_date, start_date, end_date}(못 읽으면 빈 값)."""
    out: dict = {}
    # 발주처 = <발주처> 아래 "기관명 : 경기도 포천시"(수요기관도 같은 라벨이라 첫 번째)
    out["client"] = _after(text, r"기\s*관\s*명", r"계약관|주\s*소|전\s*화|$")
    out["title"] = _after(text, r"계약건명")
    out["contract_no"] = _after(text, r"계약번호", r"관리번호|$").replace(" ", "")
    m = re.search(r"계약금액\s*:.*?\\\s*([\d,]+)", text)
    out["amount"] = int(m[1].replace(",", "")) if m else None
    out["contract_date"] = _date(_after(text, r"계약일자"))
    out["start_date"] = _date(_after(text, r"착수일자", r"금차|총완수|$"))
    # 완수일: 총완수일자(장기계속이면 금차와 다름 — 완수계는 그 계약 전체 기준이라 총완수), 없으면 금차완수일자
    out["end_date"] = _date(_after(text, r"총완수일자")) or _date(_after(text, r"금차완수일자", r"총완수|$"))
    return out


def parse_pdf(path: str | Path) -> dict:
    return parse_text(read_text(path))
