"""계약서/공문 PDF를 Claude API에 document로 전달해 '신규현장추가' 폼 필드를 추출하는 모듈.

실제 웹 시스템의 동작을 그대로 따른다:
- 본사 정보는 발주자가 아니라 실제 시공사(건설업체) 쪽에서 채운다.
- 계약서에 없는 값은 절대 지어내지 말고 빈 문자열로 남긴다.
API 호출부(_call_claude)를 분리해서 나중에 테스트 시 mocking하기 쉽게 했다.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from anthropic import Anthropic

from core.config import get_api_key, get_model_name

# core.models_db.Site의 컬럼명과 1:1로 맞춘 키 목록.
SITE_FIELD_KEYS = [
    "name",
    "address",
    "period_start",
    "period_end",
    "amount",
    "site_mgmt_no",
    "biz_start_no",
    "manager_name",
    "manager_phone",
    "manager_email",
    "hq_company",
    "corp_reg_no",
    "biz_reg_no",
    "license_no",
    "hq_phone",
    "hq_address",
    "total_guidance_count",
]

SITE_EXTRACTION_PROMPT = """당신은 건설재해예방 기술지도 계약서를 분석하는 전문가입니다.
첨부된 계약서 또는 공문 PDF에서 아래 항목을 추출하세요.

중요한 규칙:
- "본사" 관련 항목(hq_company, corp_reg_no, biz_reg_no, license_no, hq_phone, hq_address)은
  발주자가 아니라 실제 공사를 시공하는 건설업체(시공사) 정보에서 추출하세요.
- 계약서에 없거나 불확실한 값은 절대 추측해서 채우지 말고 빈 문자열("") 또는 null로 남기세요.
- 날짜는 YYYY-MM-DD 형식, 금액은 숫자만(쉼표/원 제외).

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{
  "name": "현장명 (공사명)",
  "address": "현장 소재지",
  "period_start": "공사기간 시작일 (YYYY-MM-DD)",
  "period_end": "공사기간 종료일 (YYYY-MM-DD)",
  "amount": "공사금액 (숫자만)",
  "site_mgmt_no": "사업장관리번호",
  "biz_start_no": "사업개시번호",
  "manager_name": "현장책임자 이름",
  "manager_phone": "현장책임자 연락처",
  "manager_email": "현장책임자 이메일",
  "hq_company": "시공사(건설업체) 회사명",
  "corp_reg_no": "시공사 법인등록번호",
  "biz_reg_no": "시공사 사업자등록번호",
  "license_no": "시공사 건설면허번호",
  "hq_phone": "시공사 연락처",
  "hq_address": "시공사 주소",
  "total_guidance_count": "기술지도 총 횟수 (숫자만)",
  "contract_start": "기술지도 계약기간 시작일 (YYYY-MM-DD) — 아래쪽 '계약기간 ○년 ○월 ○일부터 ○년 ○월 ○일까지'의 앞 날짜(공사기간과 다름)",
  "contract_end": "기술지도 계약기간 종료일 (YYYY-MM-DD) — 같은 '계약기간'의 뒤 날짜"
}"""

# 기술지도 계약기간(2026-10-20 사용자 "기술지도계약서에도 공사기간 말고 우리 계약기간이 명시되어 있어 — 그걸 따르면 됨") — Site 칸이 아니라
# 웹판 site_contact.contract_start·contract_end(우리 계약기간 = 자동 배치·공기 경과, server/api/contract_sites.our_periods). 데스크톱은 안 씀.
GUIDE_PERIOD_KEYS = ("contract_start", "contract_end")
_GUIDE_PERIOD = re.compile(r"계\s*약\s*기\s*간\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*부\s*터\s*"
                           r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*까\s*지")


def _encode_pdf(file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"지원하지 않는 파일 형식입니다: {path.suffix} "
            "(워드/엑셀/사진은 사전에 PDF로 변환해야 합니다)"
        )
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def _call_claude(
    pdf_b64: str,
    prompt: str,
    model: str | None = None,
    max_tokens: int = 1024,
    company_id: int | None = None,
) -> str:
    """실제 Claude API 호출. 분리해두면 테스트할 때 이 함수만 mocking하면 된다."""
    client = Anthropic(api_key=get_api_key(company_id))
    response = client.messages.create(
        model=model or get_model_name(),
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    from core import ai_usage
    ai_usage.log(response, company_id)
    return "".join(block.text for block in response.content if block.type == "text")


def _parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답에서 JSON을 파싱하지 못했습니다: {e}\n원본 응답: {raw_text}") from e

    if not isinstance(data, dict):
        raise ValueError(f"JSON 객체가 아닌 응답을 받았습니다: {raw_text}")
    return data


def _normalize_int(value) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def guide_contract_period(file_path: str | Path) -> tuple[str, str]:
    """K2B 기술지도계약서 아래쪽 "계약기간 2026년 06월15일부터 2027년 02월28일 까지" → ("2026-06-15", "2027-02-28") — 글자 PDF에서만
    (K2B 출력본은 글자가 있음 — AI보다 정확). 못 찾으면 ("", "")."""
    try:
        import pymupdf

        with pymupdf.open(str(file_path)) as doc:
            text = "".join(page.get_text() for page in doc)
    except Exception:  # noqa: BLE001 — 그림 PDF·깨진 파일이면 AI 값으로
        return "", ""
    m = _GUIDE_PERIOD.search(text)
    if not m:
        return "", ""
    y1, m1, d1, y2, m2, d2 = (int(x) for x in m.groups())
    return f"{y1:04d}-{m1:02d}-{d1:02d}", f"{y2:04d}-{m2:02d}-{d2:02d}"


def extract_site_info(file_path: str | Path, model: str | None = None, company_id: int | None = None) -> dict:
    """계약서 PDF에서 '신규현장추가' 폼 필드를 추출해 dict로 반환한다.

    반환값의 키는 core.models_db.Site 컬럼명과 동일하며, 값을 찾지 못한 항목은
    빈 문자열/None으로 채워진다(억지 추측 금지).

    `company_id`: 웹판(server/)에서 로그인한 사용자의 회사별 API 키를 쓸 때만 넘긴다
    (Sub-phase 33) — 데스크톱 exe는 안 넘기므로 예전과 동일하게 동작.
    """
    pdf_b64 = _encode_pdf(file_path)
    raw_response = _call_claude(pdf_b64, SITE_EXTRACTION_PROMPT, model=model, company_id=company_id)
    data = _parse_json_object(raw_response)

    result = {key: (data.get(key) or "") for key in SITE_FIELD_KEYS}
    result["amount"] = _normalize_int(data.get("amount"))
    result["total_guidance_count"] = _normalize_int(data.get("total_guidance_count"))
    start, end = guide_contract_period(file_path)  # 계약기간은 글자가 있으면 글자 값(AI는 공사기간과 헷갈릴 수 있음)
    for key, found in zip(GUIDE_PERIOD_KEYS, (start, end)):
        value = found or str(data.get(key) or "")
        result[key] = value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""
    return result
