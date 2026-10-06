"""증명서 발급일·유효기간 자동 읽기 — 완납증명서·경력증명서(2026-10-06 사용자: 파일부터 올리고, AI로 최대한 발급일 자동 입력 — 틀리거나 못 찾으면 손으로, 경고).

1) 글자가 든 PDF(홈택스·정부24·4대보험 포털)는 글자에서 "발급일 …"·"유효기간 …까지"를 찾는다(바로·무료).
2) 발급일을 못 찾으면 Claude API에 원본(PDF는 문서, 그림은 그림 그대로)을 보여 주고 묻는다(회사 키 — 서류·보고서 자동화 설정).
못 찾으면 빈 값 — 화면에 "⚠ 발급일을 적어 주세요"(contract_library.doc_status "nodate"). 유효기간이 안 적힌 서류는 발급일 + 30일(contract_library._set_dates).
"""
from __future__ import annotations

import base64
import datetime
import io
import re

import pdfplumber
from anthropic import Anthropic

from core import config
from core.contract_analyzer import _parse_json_object

_D = r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
PROMPT = """첨부는 한국의 증명서(국세·지방세 납세증명서, 4대보험 완납증명서, 건설기술인 경력증명서 등)입니다.
이 증명서의 발급일(발급일자·발행일·증명일)과 유효기간 끝나는 날을 찾으세요. 유효기간이 날짜 범위로 적혀 있으면 끝나는 날만.
문서에 없거나 불확실하면 추측하지 말고 ""로. 아래 JSON만 답하세요:
{"issued_on": "YYYY-MM-DD", "valid_until": "YYYY-MM-DD"}"""


def _mk(y, m, d) -> datetime.date | None:
    try:
        return datetime.date(int(y), int(m), int(d))
    except ValueError:
        return None


def from_text(text: str) -> dict:
    out: dict = {"issued_on": None, "valid_until": None}
    m = re.search(r"(?:발\s*급\s*일\s*자?|발\s*급\s*일\s*시|발\s*행\s*일|증\s*명\s*일)\s*[:：]?\s*" + _D, text)
    if m:
        out["issued_on"] = _mk(*m.groups())
    m = re.search(r"유\s*효\s*기\s*간\s*[:：]?\s*(?:" + _D + r"\s*[~∼-]\s*)?" + _D, text)
    if m:
        g = m.groups()
        out["valid_until"] = _mk(*g[3:6]) if g[3] else None
    return out


def _pdf_text(data: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text(x_tolerance=1.5) or "") for p in pdf.pages[:3])
    except Exception:  # noqa: BLE001 — 그림이거나 깨진 PDF
        return ""


def _ask_ai(data: bytes, is_pdf: bool, jpeg: bytes, company_id: int) -> dict:
    if is_pdf:
        part = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(data).decode()}}
    else:
        part = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(jpeg).decode()}}
    client = Anthropic(api_key=config.get_api_key(company_id))
    res = client.messages.create(model=config.get_model_name(), max_tokens=200,
                                 messages=[{"role": "user", "content": [part, {"type": "text", "text": PROMPT}]}])
    raw = _parse_json_object("".join(b.text for b in res.content if b.type == "text"))

    def d(v):
        try:
            return datetime.date.fromisoformat(str(v).strip()[:10]) if v else None
        except ValueError:
            return None
    return {"issued_on": d(raw.get("issued_on")), "valid_until": d(raw.get("valid_until"))}


def read_dates(data: bytes, filename: str, jpeg: bytes, company_id: int) -> dict:
    """원본 바이트(PDF·그림)·변환된 JPG → {"issued_on", "valid_until", "source": "text"|"ai"|"", "error": ""}."""
    is_pdf = data[:4] == b"%PDF" or filename.lower().endswith(".pdf")
    out = from_text(_pdf_text(data)) if is_pdf else {"issued_on": None, "valid_until": None}
    source = "text" if out["issued_on"] or out["valid_until"] else ""
    error = ""
    if not out["issued_on"]:
        if not config.has_api_key(company_id):
            error = "Claude API 키가 없어 AI로 읽지 못했습니다"
        else:
            try:
                ai = _ask_ai(data, is_pdf, jpeg, company_id)
                for k, v in ai.items():
                    if v and not out.get(k):
                        out[k] = v
                        source = "ai"
            except Exception as err:  # noqa: BLE001 — 읽기 실패는 손으로
                error = (str(err).splitlines()[0] if str(err) else type(err).__name__)[:150]
    return out | {"source": source, "error": error}
