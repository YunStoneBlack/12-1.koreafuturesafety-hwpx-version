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
 "owner_rep": "소유자·관리주체의 대표자 이름(사람 이름)", "holder": "기본현황 표의 소유자 칸 값 그대로(기관·회사·사람 이름)", "structure": "구조형식", "floors_above": null, "floors_below": null, "floors_roof": null,
 "max_height": null, "total_area": "연면적(건축 연면적)", "building_area": "건축면적(1층 바닥 — 연면적보다 작음)",
 "land_area": "대지면적(없으면 null)", "coverage_ratio": "건폐율 % 숫자(없으면 null)", "floor_area_ratio": "용적률 % 숫자(없으면 null)",
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
 "rounds": [{"year": 연도, "half": "상반기|하반기|해빙기|우기|동절기", "kind": "정기|정밀", "amount": 금액(원, 정수)}]}
rounds = 점검 회차마다 한 줄(예: 장기 계약서의 "26년 상반기 정기 / 26년 하반기 정밀", 단발 계약은 계약기간의 반기 하나). kind는 계약건명·금액 칸의
"정밀안전점검"/"정기안전점검" 글자로 — 없으면 "정기". 반기 표시가 없으면 계약기간으로 판단, 총합 줄은 빼기.
연 3회 계약(D·E등급 — "해빙기(정기)·우기(정기)·동절기(정기)")이면 half에 해빙기·우기·동절기를 그대로."""


ESTIMATE_PROMPT = """첨부는 시설물 안전점검 용역의 내역서입니다(산출내역서·견적(세부)내역서·과업내용서 중 하나). 점검 대상 시설물(건물·동·사업장·옹벽 등)마다
이름과 금액을 찾아 JSON 객체 하나로만 답하세요(설명 없이). 없거나 불확실하면 "" 또는 null — 추측 금지. 금액은 원 단위 정수만.

{"parts": [{"name": "시설물·건물·동·사업장 이름 그대로(예: 본관, 체육관, 세종국책연구단지)", "amount": 그 시설물의 총 금액(여러 회차·항목이면 합, 없으면 null)}],
 "total": 총합계 금액(없으면 null)}
- 합계·소계·총합계·부가가치세·제경비 같은 줄은 parts에 넣지 말 것(시설물 이름 줄만).
- 시설물이 하나뿐이거나 시설물 구분이 없으면 parts는 그 하나(이름을 모르면 빈 목록 [])."""


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
    if pdf.stat().st_size > 20_000_000:  # AI가 받는 PDF는 32MB까지 — 사진이 큰 관리대장(10/16 모노폴리 4쪽 48MB)은 사진을 줄여서
        import tempfile

        from server.contract_docs import pdf_shrink

        with tempfile.TemporaryDirectory() as tmp:
            small = Path(tmp) / "작게.pdf"
            small.write_bytes(pdf_shrink.shrink_bytes(pdf.read_bytes()))
            return _parse_json_object(_call_claude(_encode_pdf(small), prompt, max_tokens=6000, company_id=company_id))
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


HOLDER_SKIP = {"공공", "민간", "중앙부처", "지자체", "공기업", "V", "v", "√", "■", "□"}


def ledger_holder(pdf) -> str:
    """관리대장 PDF 글자에서 "소유자" 칸 값(10/21 사용자 — 결과표 대표자) — 표가 돌려진 쪽이라 좌표를 화면 방향으로 돌려
    "소유자" 머리 아래 줄(관리주체 값과 같은 줄)에서 소유자구분(중앙부처·지자체…) 칸 앞까지. 그림 PDF·못 찾으면 ""."""
    import pymupdf

    try:
        doc = pymupdf.open(str(pdf))
    except Exception:  # noqa: BLE001
        return ""
    try:
        for pg in doc:
            if "소유자" not in pg.get_text():
                continue
            m = pg.rotation_matrix
            ws = [(pymupdf.Rect(w[:4]) * m, w[4]) for w in pg.get_text("words")]
            head = next((r for r, t in ws if t == "소유자"), None)
            if head is None:
                continue
            below = [(r, t) for r, t in ws if head.y1 + 15 < r.y0 < head.y1 + 65]
            subs = [r.x0 for r, t in below if t in HOLDER_SKIP and r.x0 > head.x1]
            right = min(subs) - 2 if subs else head.x1 + 60
            left = head.x0 - 45
            vals = [(r, t) for r, t in below if left <= (r.x0 + r.x1) / 2 <= right and t not in HOLDER_SKIP and not t.startswith(("(", ")"))]
            lines: dict[int, list] = {}
            for r, t in vals:
                lines.setdefault(round(r.y0 / 6), []).append((r.x0, t))
            # 줄 안은 띄어 쓰고, 칸이 좁아 줄이 바뀐 이름("아시아신탁주식회" / "사")은 붙임
            out = "".join(" ".join(t for _, t in sorted(ws_)) for _, ws_ in sorted(lines.items())).strip()
            if len(out) < 2 or any(w in out for w in ("미만", "이상인", "제곱미터", "~", "관련시설", "순환")):
                return ""  # 다른 칸 글(시설물종류 설명)이 섞임 — 못 읽은 것으로
            return out
    finally:
        doc.close()
    return ""


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
        "holder": ledger_holder(pdf) or _str(d.get("holder")),  # 소유주 — 결과표 대표자(10/21, 글자 PDF는 좌표로, 그림이면 AI 값)
        "floors_above": _int(d.get("floors_above")), "floors_below": _int(d.get("floors_below")), "floors_roof": _int(d.get("floors_roof")),
        "max_height": _num(d.get("max_height")), "total_area": _num(d.get("total_area")), "building_area": _num(d.get("building_area")),
        "land_area": _num(d.get("land_area")), "coverage_ratio": _num(d.get("coverage_ratio")), "floor_area_ratio": _num(d.get("floor_area_ratio")),
        "ledger": {"facility_class": _str(d.get("facility_class")), "holder": ledger_holder(pdf) or _str(d.get("holder"))},
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


def read_estimate(pdf: Path, company_id: int) -> list[dict]:
    """관급 내역서(산출내역서·견적세부내역서·과업내용서) → 건물·사업장별 [{name, amount}](10/16 민재형 — 계약이 맡는 건물·건물별 금액)."""
    d = _ask(pdf, ESTIMATE_PROMPT, company_id)
    out, seen = [], set()
    for x in d.get("parts") or []:
        name = _str((x or {}).get("name"))
        if not name or name in seen or any(w in name.replace(" ", "") for w in ("합계", "소계", "총계", "부가가치세", "부가세")):
            continue
        seen.add(name)
        amt = _int((x or {}).get("amount"))
        out.append({"name": name, "amount": amt if amt and amt > 0 else None})
    return out


SHEET_PROMPT = """첨부는 건축물 안전점검 보고서에서 뽑은 쪽들입니다 — 건물(동)마다 "정기안전점검 결과표"(가. 일반현황 — 용역명·관리주체명·종별·준공일·안전등급·시설물위치·
시설물규모)와 "시설물 현황"(시설물명·시설물번호·준공년월일·건축면적·연면적·층수·주용도·구조형식·최고높이)이 있습니다. 다른 회사 보고서여도 결과표 양식은 같습니다.
건물(동)마다 하나씩 아래 값을 찾아 JSON 객체 하나로만 답하세요(설명 없이). 없거나 불확실하면 "" 또는 null — 절대 추측하지 마세요. 날짜 YYYY-MM-DD, 숫자는 단위 없이.
결과표와 시설물 현황이 같은 건물이면 한 줄로 합치고(시설물 현황 값이 더 자세하면 그것), 건물 순서는 문서 순서대로.

{"buildings": [{"name": "시설물명(동 이름까지 — 예: 안산대학교 본관동)", "fms_no": "시설물번호(예: AR2004-0004955, 없으면 빈 글자)",
  "address": "시설물 위치 한 줄", "owner_name": "관리주체명", "grade": "종별 숫자만(1·2·3 — 해당없음·없으면 빈 글자)", "safety_grade": "안전등급 글자(A~E)",
  "use_type_guess": "결과표 '종류' 칸(예: 교육연구시설)", "main_use": "주용도", "completion_date": "준공일(사용승인일)", "structure": "구조형식",
  "floors_above": null, "floors_below": null, "floors_roof": null, "max_height": null, "total_area": "연면적", "building_area": "건축면적(연면적보다 작음)"}]}"""


def sheet_pages(pdf: Path) -> tuple[list[int], int]:
    """결과표·시설물 현황이 있는 쪽 번호(0부터)와 결과표 개수(= 건물 수, 글자가 있는 PDF일 때). 글자가 없으면([], 0) — 스캔은 AI가 앞쪽을 봄."""
    import pymupdf

    keep, sheets = [], 0
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc):
            t = "".join(page.get_text().split())
            if "결과표" in t and ("일반현황" in t or "용역명" in t) and "목차" not in t:
                sheets += 1
                keep.append(i)
            elif ("시설물현황" in t or "시설물명" in t) and "연면적" in t and "목차" not in t:
                keep.append(i)
    return keep, sheets


def read_sheets(pdf: Path, company_id: int) -> tuple[list[dict], int]:
    """전회차 보고서·동마다 결과표+시설물 현황을 모은 PDF → 건물(동)마다 시설물 칸(read_ledger와 같은 모양), 글자로 센 결과표 개수.
    관리대장이 없는 자체점검(법정 외 — 안산대·연성대, 10/16 민재형 개편). 보고서 전체 대신 결과표·현황 쪽만 AI에 보냄(없으면 앞 20쪽)."""
    import pymupdf

    keep, sheets = sheet_pages(pdf)
    with pymupdf.open(pdf) as doc:
        pages = keep[:60] if keep else list(range(min(doc.page_count, 20)))
        if len(pages) < doc.page_count:
            sub = pymupdf.open()
            for i in pages:
                sub.insert_pdf(doc, from_page=i, to_page=i)
            part = pdf.with_name(pdf.stem + "_결과표쪽.pdf")
            sub.save(part)
            sub.close()
        else:
            part = pdf
    try:
        d = _ask(part, SHEET_PROMPT, company_id)
    finally:
        if part != pdf:
            part.unlink(missing_ok=True)
    out = []
    for b in d.get("buildings") or []:
        b = b or {}
        total, built = _num(b.get("total_area")), _num(b.get("building_area"))
        if built and (total is None or built > total):
            total, built = max(built, total or 0), (total if total and total < built else None)
        name = _str(b.get("name"))
        if not name:
            continue
        out.append({
            "fms_no": _str(b.get("fms_no")).replace(" ", ""), "name": name, "kind": "건축물", "grade": _str(b.get("grade"))[:1],
            "main_use": _str(b.get("main_use")), "use_type": _str(b.get("use_type_guess")), "address": _str(b.get("address")),
            "owner_name": _str(b.get("owner_name")), "completion_date": _date(b.get("completion_date")), "structure": _str(b.get("structure")),
            "floors_above": _int(b.get("floors_above")), "floors_below": _int(b.get("floors_below")), "floors_roof": _int(b.get("floors_roof")),
            "max_height": _num(b.get("max_height")), "total_area": total, "building_area": built,
            "safety_grade": _str(b.get("safety_grade"))[:1].upper(),
        })
    return out, sheets


COVER_SIM = 0.8  # 표지 모양 닮음 기준 — 포천 용정산단 옹벽 12개 묶음(10/20): 표지 0.95~1.00, 다른 쪽 0.19 이하


def _page_print(page, w: int = 200, h: int = 140) -> list[float]:
    """쪽 모양 — 작게 그린 회색 그림(잉크 = 큰 값)을 평균 빼고 길이 1로. 글자가 선으로 그려져 글자를 못 읽는 쪽도 모양은 같음."""
    import pymupdf

    r = page.rect
    pix = page.get_pixmap(matrix=pymupdf.Matrix(w / r.width, h / r.height), colorspace=pymupdf.csGRAY, alpha=False)
    s, st = pix.samples, pix.stride
    v = [255 - s[y * st + x] if y < pix.height and x < pix.width else 0 for y in range(h) for x in range(w)]
    m = sum(v) / len(v)
    v = [a - m for a in v]
    n = sum(a * a for a in v) ** 0.5 or 1.0
    return [a / n for a in v]


def ledger_starts(pdf: Path) -> list[int]:
    """관리대장 PDF에서 건물마다 시작 쪽(0부터) — FMS 출력물은 건물마다 "시설물번호 … 내용 1. 기본현황 2. 상세제원" 표지로 시작(10/16 양주덕산초 "종합" 관리대장).
    글자로 찾고, 표지와 모양이 같은 쪽도 더함(10/20 민재형 — 글꼴이 선으로 바뀐 인쇄본 PDF는 글자가 없어 12개 중 2개만 잡혔음).
    모양 기준 표지 = 글자로 찾은 첫 표지, 없으면 첫 쪽(묶음 관리대장은 표지로 시작)."""
    import pymupdf

    starts = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc):
            t = "".join(page.get_text().split())[:400]
            if t.startswith("시설물번호") and "1.기본현황" in t:
                starts.append(i)
        if doc.page_count < 2:
            return starts
        prints = [_page_print(page) for page in doc]
        ref = prints[starts[0] if starts else 0]
        looks = {i for i, p in enumerate(prints) if sum(a * b for a, b in zip(ref, p)) >= COVER_SIM}
        if starts or len(looks) >= 2:  # 글자 표지가 없고 모양 표지도 하나뿐이면 묶음이 아님
            starts = sorted(set(starts) | looks)
    return starts


def split_ledgers(pdf: Path) -> list[Path]:
    """여러 건물 관리대장을 한 PDF로 모은 것("시설물관리대장종합.pdf") → 건물마다 PDF(같은 폴더 이름_1·_2…). 하나뿐이면 [pdf].
    첫 표지 앞 쪽이 있으면 첫 건물에 붙임(버리지 않음)."""
    import pymupdf

    starts = ledger_starts(pdf)
    if len(starts) < 2:
        return [pdf]
    out = []
    with pymupdf.open(pdf) as doc:
        bounds = [0] + starts[1:] + [doc.page_count]
        for k in range(len(starts)):
            sub = pymupdf.open()
            sub.insert_pdf(doc, from_page=bounds[k], to_page=bounds[k + 1] - 1)
            p = pdf.with_name(f"{pdf.stem}_{k + 1}.pdf")
            sub.save(p)
            sub.close()
            out.append(p)
    return out
