"""용역계약서 AI 읽기(2026-10-06 사용자: 보고서 자동화처럼 API도 쓰자) — 글자 규칙(contract_pdf.py)으로 못 읽은 칸만 Claude API로 채운다.

나라장터·국방조달처럼 아는 양식은 규칙으로 바로·무료로 읽고, 처음 보는 양식(지자체 자체 양식·스캔본)일 때만 AI(10~20초, 건당 몇십 원).
API 키는 회사 설정(보고서·서류 자동화 설정 탭 같은 키, core/config.py). 키가 없거나 AI가 실패해도 계약은 만들어지고 칸만 빈다(화면에서 손으로).
호출·JSON 풀기는 보고서 자동화의 계약서 인식(core/contract_analyzer.py)과 같은 함수를 쓴다.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from core import config
from core.contract_analyzer import _call_claude, _encode_pdf, _normalize_int, _parse_json_object

# 이 칸 중 하나라도 비면 AI에 물어본다(착수계·완수계에 꼭 들어가는 값)
KEY_FIELDS = ("client", "title", "contract_no", "start_date", "end_date", "amount")

PROMPT = """당신은 관급 용역계약서(나라장터·국방전자조달·지자체 계약서 등)를 읽는 전문가입니다.
첨부된 용역계약서 PDF에서 아래 항목을 찾으세요. 이 계약은 건설재해예방 기술지도 용역이고, 계약상대자는 (주)한국미래안전입니다.

규칙:
- client = 발주기관(계약을 맡긴 관공서·부대·공사 등). 계약상대자(한국미래안전)가 아님.
- title = 계약건명·계약명·용역명 그대로.
- contract_no = 계약번호 그대로(차수 표기 포함, 예: R25TA00551412-00, 2026LNRA190(00)).
- amount = 계약 전체 금액(총용역부기금액이 있으면 그것), 숫자만.
- start_date = 착수일, end_date = 완수일·준공일·준공기한(장기계속이면 총완수일), contract_date = 계약일. 날짜는 YYYY-MM-DD.
- 문서에 없거나 불확실하면 절대 추측하지 말고 "" 또는 null.

아래 JSON 객체만 답하세요(다른 설명 없이):
{"client": "", "title": "", "contract_no": "", "amount": null, "contract_date": "", "start_date": "", "end_date": ""}"""


def needs_ai(parsed: dict) -> bool:
    return any(not parsed.get(k) for k in KEY_FIELDS)


def _date(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v).strip()[:10]) if v else None
    except ValueError:
        return None


def read_with_ai(pdf_path: Path, company_id: int) -> dict:
    """PDF → {client, title, contract_no, amount, contract_date, start_date, end_date}. 키가 없으면 RuntimeError."""
    if not config.has_api_key(company_id):
        raise RuntimeError("Claude API 키가 없습니다 — 서류 자동화 설정 탭에서 등록하세요.")
    data = _parse_json_object(_call_claude(_encode_pdf(pdf_path), PROMPT, company_id=company_id))
    return {
        "client": str(data.get("client") or "").strip(),
        "title": str(data.get("title") or "").strip(),
        "contract_no": str(data.get("contract_no") or "").replace(" ", "").strip(),
        "amount": _normalize_int(data.get("amount")),
        "contract_date": _date(data.get("contract_date")),
        "start_date": _date(data.get("start_date")),
        "end_date": _date(data.get("end_date")),
    }
