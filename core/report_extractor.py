"""과거에 작성된 기술지도 결과보고서 PDF를 Claude API로 읽어 현장/회차 데이터를 통째로
추출하는 모듈 — "이전 보고서 업로드" 기능용.

`contract_analyzer.py`와 완전히 같은 원칙을 따른다: PDF에 없거나 불확실한 값은 추측해서
채우지 않고 빈 문자열/None/빈 리스트로 남긴다. PDF는 이 앱(`core/report_builder.py`)이
만든 것일 수도, 예전 홈페이지에서 만든 레이아웃이 다른 것일 수도 있으므로 프롬프트는
고정 좌표가 아니라 "이런 라벨을 찾아서" 방식으로 작성한다.
"""

from __future__ import annotations

from pathlib import Path

from core.contract_analyzer import SITE_FIELD_KEYS, _call_claude, _encode_pdf, _normalize_int, _parse_json_object

REPORT_EXTRACTION_PROMPT = """당신은 건설재해예방전문지도기관이 작성한 "기술지도 결과보고서" PDF를
분석하는 전문가입니다. 첨부된 PDF에서 아래 항목을 추출하세요. 이 PDF는 우리 회사가 자체
프로그램으로 만든 것이거나, 예전에 쓰던 다른 웹사이트로 만든 것일 수 있어 레이아웃이 다를 수
있습니다 — 표의 위치가 아니라 각 항목의 한글 라벨(예: "사업장관리번호", "회차", "지적사항" 등)을
기준으로 찾으세요.

중요한 규칙:
- 문서에 없거나 읽기 불확실한 값은 절대 추측해서 채우지 말고 빈 문자열("")/null/빈 배열([])로
  남기세요. 특히 지적사항·이전지적사항·계측자료·제공자료·진행공정은 실제로 그 항목이 문서에
  있는 만큼만 배열에 넣고, 없는 칸은 만들어내지 마세요.
- "본사" 관련 항목은 발주자가 아니라 실제 공사를 시공하는 건설업체(시공사) 정보에서 추출하세요.
- 날짜는 YYYY-MM-DD 형식, 숫자 항목(금액/회차/공정률/총회차/참석인원)은 숫자만.
- "회차"는 보통 "(N)회차 / 총(M)회" 형식으로 적혀 있습니다 — N은 report.visit_no, M은
  site.total_guidance_count 입니다.
- 가능성/중대성/빈도/강도 같은 위험성평가 숫자는 표에 적힌 숫자 그대로(1~3) 가져오세요.
- 12대 사망사고 기인물 안전조치 표에서 체크(■/✓ 등)된 항목의 번호만 배열로 담으세요.

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{
  "site": {
    "name": "현장명", "address": "현장 소재지",
    "period_start": "공사기간 시작일", "period_end": "공사기간 종료일", "amount": "공사금액(숫자만)",
    "site_mgmt_no": "사업장관리번호", "biz_start_no": "사업개시번호",
    "manager_name": "현장책임자", "manager_phone": "현장책임자 연락처", "manager_email": "현장책임자 이메일",
    "hq_company": "시공사 회사명", "corp_reg_no": "시공사 법인등록번호", "biz_reg_no": "시공사 사업자등록번호",
    "license_no": "시공사 건설면허번호", "hq_phone": "시공사 연락처", "hq_address": "시공사 주소",
    "total_guidance_count": "기술지도 총 횟수(숫자만)"
  },
  "report": {
    "visit_no": "이번 회차 번호(숫자만)",
    "guidance_date": "기술지도실시일",
    "progress_rate": "공정률(숫자만, %제외)",
    "notification_method": "현장책임자 등 통보방법 (직접전달/등기우편/전자우편/모바일/기타 중 하나)",
    "prev_guidance_implemented": "이전 기술지도 이행여부 (true=이행/false=불이행/null=알수없음)",
    "special_note": "기타 특이사항",
    "attendee_count": "안전교육 참석인원(숫자만)",
    "hazard_factor_checks": [1, 4, 7]
  },
  "findings": [
    {"title": "", "content": "", "law_citation": "", "likelihood": 1, "severity": 1}
  ],
  "previous_findings": [
    {"title": "", "content": "", "action_result": ""}
  ],
  "measurements": [
    {"instrument_type": "소음측정기", "value": ""}
  ],
  "provided_materials": [
    {"title": ""}
  ],
  "process_entries": [
    {"process_name": "", "hazard_text": "", "prevention_text": "", "risk_level": "상"}
  ]
}"""


def extract_report_info(file_path: str | Path, model: str | None = None) -> dict:
    """과거 보고서 PDF에서 현장/회차 데이터를 통째로 추출한다.

    반환 구조는 {"site": {...}, "report": {...}, "findings": [...], "previous_findings": [...],
    "measurements": [...], "provided_materials": [...], "process_entries": [...]} 이며,
    site/report의 키는 각각 core.models_db.Site / Report 컬럼명과 맞춰져 있다.
    찾지 못한 값은 억지로 채우지 않고 빈 값으로 둔다.
    """
    pdf_b64 = _encode_pdf(file_path)
    # 계약서 추출(필드 17개)보다 한 번에 뽑아야 할 정보가 훨씬 많아(지적사항/계측자료 등
    # 중첩 리스트 여러 개) 기본 max_tokens(1024)로는 잘릴 수 있어 넉넉하게 늘린다.
    # 이 모델은 기본적으로 확장 사고(extended thinking)를 쓰는데 사고 토큰도 같은
    # max_tokens 예산을 나눠 쓰기 때문에(실측 시 2000~2500토큰까지 소모), 4096 정도로는
    # 사고가 길어지는 경우 실제 JSON 응답이 중간에 잘려 파싱 실패로 이어질 수 있었다
    # (실제 이 버그로 실패하는 걸 재현·확인함). 안전하게 8192로 늘린다.
    raw_response = _call_claude(pdf_b64, REPORT_EXTRACTION_PROMPT, model=model, max_tokens=8192)
    data = _parse_json_object(raw_response)

    site_raw = data.get("site") or {}
    site = {key: (site_raw.get(key) or "") for key in SITE_FIELD_KEYS}
    site["amount"] = _normalize_int(site_raw.get("amount"))
    site["total_guidance_count"] = _normalize_int(site_raw.get("total_guidance_count"))

    report_raw = data.get("report") or {}
    report = {
        "visit_no": _normalize_int(report_raw.get("visit_no")),
        "guidance_date": report_raw.get("guidance_date") or "",
        "progress_rate": _normalize_int(report_raw.get("progress_rate")),
        "notification_method": report_raw.get("notification_method") or "",
        "prev_guidance_implemented": report_raw.get("prev_guidance_implemented"),
        "special_note": report_raw.get("special_note") or "",
        "attendee_count": _normalize_int(report_raw.get("attendee_count")),
        "hazard_factor_checks": [
            n for n in (report_raw.get("hazard_factor_checks") or []) if isinstance(n, int)
        ],
    }

    def _list(key: str) -> list[dict]:
        items = data.get(key)
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    findings = [
        {
            "title": f.get("title") or "",
            "content": f.get("content") or "",
            "law_citation": f.get("law_citation") or "",
            "likelihood": _normalize_int(f.get("likelihood")),
            "severity": _normalize_int(f.get("severity")),
        }
        for f in _list("findings")
    ]

    return {
        "site": site,
        "report": report,
        "findings": findings,
        "previous_findings": _list("previous_findings"),
        "measurements": _list("measurements"),
        "provided_materials": _list("provided_materials"),
        "process_entries": _list("process_entries"),
    }
