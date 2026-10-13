"""시설물관리대장·점검 용역 계약서 PDF 읽기(Claude API, 2026-10-10) — 시설물 등록 화면에서 올리면 칸을 채운다(사람이 고칠 수 있음).

- 관리대장 = FMS "시설물관리대장(건축물)" 출력물(글자 있음, 4쪽쯤).
- 계약서 = 민간 "정기점검 표준계약서"(2쪽째가 팩스 스캔이라 글자 없음 — AI가 그림을 읽음, 상·하반기 금액 따로) /
  관급 나라장터 "용역계약서"(글자 있음 — 착수·완수일, 계약번호). 둘 다 AI 한 번(건당 몇십 원). 키·호출은 산안법과 같은 것(core/contract_analyzer).
없거나 불확실한 값은 비워 둔다(추측 금지).
"""
from __future__ import annotations

import datetime
from pathlib import Path

from core import config
from core.contract_analyzer import _call_claude, _encode_pdf, _parse_json_object

LEDGER_PROMPT = """첨부는 국토안전관리원 FMS에서 출력한 "시설물관리대장(건축물)"입니다. 아래 값을 찾아 JSON 객체 하나로만 답하세요(설명 없이).
문서에 없거나 불확실하면 "" 또는 null — 절대 추측하지 마세요. 날짜는 YYYY-MM-DD, 숫자는 단위 없이 숫자만.
주의: 기본현황에 "사업계획 승인일 · 준공(사용승인)일 · 하자담보책임 만료일"이 나란히 있음 — 준공일은 "준공(사용승인)일" 칸에 적힌 날짜 그대로
(하자담보 만료일보다 앞 날짜). 설계/시공의 공사기간 끝 날짜와 다를 수 있으니 공사기간 날짜로 대신하지 말 것(10/12 숭의 B동: 공사 끝 1991-06-15, 준공 1991-06-26).
층수는 상세제원의 지상(옥탑제외)·옥탑·지하.

{"fms_no": "시설물번호(예: AR2004-0004955)", "name": "시설물명", "kind": "시설물종류(예: 건축물)", "grade": "시설물종별 숫자만(1·2·3)",
 "facility_class": "시설물분류", "main_use": "주용도", "address": "주소(도로명 우선, 없으면 지번) 한 줄",
 "owner_name": "관리주체", "owner_type": "관리주체구분(민간·공공 등)", "owner_phone": "관리주체 전화번호",
 "completion_date": "준공(사용승인)일", "construction_end": "설계/시공 공사기간의 끝 날짜", "defect_end": "하자담보책임 만료일",
 "owner_rep": "소유자·관리주체의 대표자 이름(사람 이름)", "structure": "구조형식", "floors_above": null, "floors_below": null, "floors_roof": null,
 "max_height": null, "total_area": "연면적(건축 연면적)", "building_area": "건축면적(1층 바닥 — 연면적보다 작음)",
 "use_type_guess": "결과표 '종류' 칸에 쓸 건축법 용도 분류 추정(예: 종교시설·교육연구시설·업무시설) — 주용도로 판단"}"""

CONTRACT_PROMPT = """첨부는 시설물 정기안전점검 용역 계약서입니다(계약상대자 = 점검 회사 (주)한국미래안전). 두 종류 중 하나입니다:
- 민간: "정기점검 표준계약서"(관리주체와 직접 계약, 상반기·하반기 금액이 따로 적힘, 스캔 그림일 수 있음)
- 관급: 나라장터 등 "용역계약서"(계약번호·착수일자·완수일자·계약방법·공동도급방식이 있음)
아래 값을 찾아 JSON 객체 하나로만 답하세요(설명 없이). 없거나 불확실하면 "" 또는 null — 추측 금지. 날짜 YYYY-MM-DD, 금액은 원 단위 숫자만.

{"sector": "민간 또는 관급", "title": "계약건명·용역명 그대로", "contract_no": "계약번호(관급)", "contract_date": "계약일",
 "start_date": "계약기간 시작·착수일", "end_date": "계약기간 끝·(총)완수일",
 "amount_first_half": null, "amount_second_half": null, "amount_total": null,
 "owner_name": "관리주체·발주기관(수요기관) 이름", "rep_name": "관리주체 대표자 이름(관급이면 계약관·기관장 이름)",
 "address": "시설물 위치·현장 주소", "bid_method": "계약방법(수의계약·일반경쟁·제한경쟁·지명경쟁 중 가까운 것)",
 "joint_type": "공동도급(단독계약이면 독자수행, 공동이행·분담이행)",
 "rounds": [{"year": 연도, "half": "상반기|하반기", "kind": "정기|정밀", "amount": 금액(원, 정수)}]}
rounds = 점검 회차마다 한 줄(예: 장기 계약서의 "26년 상반기 정기 / 26년 하반기 정밀", 단발 계약은 계약기간의 반기 하나). kind는 계약건명·금액 칸의
"정밀안전점검"/"정기안전점검" 글자로 — 없으면 "정기". 반기 표시가 없으면 계약기간으로 판단, 총합 줄은 빼기."""


def _date(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v).strip()[:10]) if v else None
    except ValueError:
        return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip()) if v not in (None, "") else None
    except ValueError:
        return None


def _int(v) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _str(v) -> str:
    return str(v or "").strip()


def _ask(pdf: Path, prompt: str, company_id: int) -> dict:
    if not config.has_api_key(company_id):
        raise RuntimeError("Claude API 키가 없습니다 — 보고서 자동화 설정 탭에서 등록하세요.")
    return _parse_json_object(_call_claude(_encode_pdf(pdf), prompt, max_tokens=6000, company_id=company_id))


def _text_dates(pdf: Path) -> list[datetime.date]:
    """관리대장 글자에서 "사업계획 승인일 · 준공(사용승인)일 · 하자담보책임 만료일" 칸 날짜들(FMS 출력은 "5. 첨부자료 목록" 다음, "설계기간" 앞에
    "1991년 06월 26일" 꼴로 차례로 — 빈 칸은 안 나옴). 못 찾으면 []."""
    import re

    import pymupdf

    try:
        with pymupdf.open(pdf) as doc:
            text = "\n".join(p.get_text() for p in doc)
    except Exception:  # noqa: BLE001
        return []
    m = re.search(r"준공\s*\(사용승인\)\s*일.*?첨부자료\s*목록(.*?)설계기간", text, re.S)
    if not m:
        return []
    out = []
    for y, mo, dd in re.findall(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", m[1]):
        try:
            out.append(datetime.date(int(y), int(mo), int(dd)))
        except ValueError:
            pass
    return out


def _completion(d: dict, pdf: Path | None = None) -> datetime.date | None:
    """준공일 — 관리대장의 날짜 칸이 표가 돌아간 쪽이라 AI가 하자담보 만료일(10/10 평택: 2004 준공·2005 하자)이나 공사기간 끝
    (10/12 숭의 B동: 공사 끝 06-15·준공 06-26)과 헷갈리기도 한다.
    1) 글자에서 날짜 칸을 찾았으면 그걸로 확인 — AI 날짜가 그 안에 있으면 그대로, 아니면 칸 수로(1개 = 준공, 3개 = 가운데, 2개 = AI 하자담보와 다른 앞의 것).
    2) 못 찾았으면 공사기간 끝 날짜가 있고 AI 준공일이 하자담보 만료일과 같거나 그보다 300일 넘게 늦을 때만 공사기간 끝."""
    done, built, defect = _date(d.get("completion_date")), _date(d.get("construction_end")), _date(d.get("defect_end"))
    dates = _text_dates(pdf) if pdf else []
    if dates:
        if done in dates and done != defect:
            return done
        if len(dates) == 1:
            return dates[0]
        if len(dates) == 3:
            return dates[1]
        return dates[0] if defect == dates[1] or (dates[1] - dates[0]).days > 300 else dates[1]
    if built and (done is None or done == defect or (done - built).days > 300):
        return built
    return done


def read_ledger(pdf: Path, company_id: int) -> dict:
    """관리대장 PDF → 시설물 칸(SitokFacility 이름) + grade(종별)·owner_rep(관리주체 대표자 — 계약 칸에 씀)."""
    d = _ask(pdf, LEDGER_PROMPT, company_id)
    total, built = _num(d.get("total_area")), _num(d.get("building_area"))
    if built and (total is None or built > total):  # 10/10 평택: 연면적이 건축면적 칸으로 — 큰 값이 연면적
        total, built = max(built, total or 0), (total if total and total < built else None)
    d["total_area"], d["building_area"] = total, built
    return {
        "fms_no": _str(d.get("fms_no")).replace(" ", ""), "name": _str(d.get("name")), "kind": _str(d.get("kind")) or "건축물",
        "grade": _str(d.get("grade"))[:1], "main_use": _str(d.get("main_use")), "use_type": _str(d.get("use_type_guess")),
        "address": _str(d.get("address")), "owner_name": _str(d.get("owner_name")), "owner_type": _str(d.get("owner_type")),
        "owner_phone": _str(d.get("owner_phone")), "completion_date": _completion(d, pdf), "owner_rep": _str(d.get("owner_rep")), "structure": _str(d.get("structure")),
        "floors_above": _int(d.get("floors_above")), "floors_below": _int(d.get("floors_below")), "floors_roof": _int(d.get("floors_roof")),
        "max_height": _num(d.get("max_height")), "total_area": _num(d.get("total_area")), "building_area": _num(d.get("building_area")),
        "ledger": {"facility_class": _str(d.get("facility_class"))},
    }


def read_contract(pdf: Path, company_id: int) -> dict:
    """계약서 PDF → 계약 칸(SitokContract 이름) + owner_name·address(시설물 칸이 비었을 때 채움) + rounds(회차 종류)."""
    from server.sitok import civil

    d = _ask(pdf, CONTRACT_PROMPT, company_id)
    sector = "관급" if "관" in _str(d.get("sector")) else "민간"
    first, second, total = _int(d.get("amount_first_half")), _int(d.get("amount_second_half")), _int(d.get("amount_total"))
    halves = "연간" if (first and second) or sector == "관급" else "상반기" if first else "하반기" if second else "연간"
    joint = _str(d.get("joint_type"))
    bid = _str(d.get("bid_method"))
    return {
        "sector": sector, "title": _str(d.get("title")), "contract_no": _str(d.get("contract_no")).replace(" ", ""),
        "contract_date": _date(d.get("contract_date")), "start_date": _date(d.get("start_date")), "end_date": _date(d.get("end_date")),
        "halves": halves,
        # 민간은 반기 한 번 금액(상·하반기 같으면 그 값), 관급은 계약 전체 금액
        "amount": (first or second or total) if sector == "민간" else (total or first),
        "rep_name": _str(d.get("rep_name")),
        "joint_type": "공동이행" if "공동" in joint else "분담이행" if "분담" in joint else "독자수행",
        "bid_method": next((m for m in ("일반경쟁", "제한경쟁", "지명경쟁", "수의계약") if m[:2] in bid), "수의계약"),
        "owner_name": _str(d.get("owner_name")), "address": _str(d.get("address")),
        "rounds": civil.normalize_rounds(d.get("rounds")) if isinstance(d.get("rounds"), list) else [],  # 회차 종류 정기/정밀(0043)
    }
