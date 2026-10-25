"""시특법 FMS(시설물통합정보관리시스템, www.fms.or.kr) 제출 값 만들기 — 시특법 7단계(2026-10-15 사용자 "산안법 K2B처럼 시특법은 FMS, 정기·정밀·진단 전부").

FMS 흐름(형 PPT "fms등록"): 진단업체 점검진단계약 등록 → 승인요청 → 관리주체 승인 → 진단업체 점검진단실적보고(+ e-보고서 파일) → 승인요청 → 관리주체 승인.
이 모듈은 사이트를 건드리지 않고 **넣을 값**만 만든다(브라우저로 채우는 쪽은 server/sitok/fms_bot.py).
- 값은 FMS 화면 칸 이름(name)과 선택지 코드 그대로(2026-10-15 실제 화면을 읽어서 확인 — 일반현황 any12001, 대상시설물 any13001, 기술자 any14001).
- 실적의 주요 점검진단결과·주요 보수보강(안)·안전등급·중대결함은 **만든 보고서의 결과표에서 그대로 읽음**("점검진단실적은 e-보고서와 동일하게" — FMS 화면 문구).
- e-보고서 파일: 합본 PDF를 쪽 글(간지 번호·결과표 제목)로 나눠 FMS 폴더·파일 이름대로(형 PPT 16·17장 — 정기/정밀 표 1-2).
"""
from __future__ import annotations

import datetime
import re
import zipfile
from pathlib import Path

import pymupdf
from lxml import etree

from server.sitok import report_build as rb

# FMS 선택지 코드(화면에서 읽은 값)
DIGN = {"정기": "100", "정밀": "202", "진단": "401"}  # dign_gbn — 정기안전점검·정밀안전점검·정밀안전진단
JOINT = {"독자수행": "01", "공동이행": "02", "분담이행": "03"}  # divide_gbn
BID = {"일반경쟁": "01", "제한경쟁": "02", "지명경쟁": "05", "수의계약": "03", "기타": "04"}  # bid_method
EVAL = {"PQ평가방식": "01", "기술자평가방식": "02", "기술제안서평가방식": "03", "기타": "04"}  # eval_method(선정방식)
CONTRACT = {"총액계약": "01", "장기계속계약": "02", "계속비": "03"}  # contract_method
PRICE = {"공사비요율방식": "01", "실비정액가산방식": "02", "기타": "03"}  # price_method(대가산출)
FIELD = {"교량 및 터널": "1", "건축": "2", "항만": "3", "수리시설": "4"}  # tech_field(수행분야)
TECH_GRADE = {"특급": "1", "고급": "2", "중급": "3", "초급": "4"}  # tech_grade0..
KIND_LABEL = {"정기": "정기안전점검", "정밀": "정밀안전점검", "진단": "정밀안전진단"}

MAX_FILE = 48_000_000  # e-보고서 파일 한 개 50MB — 여유 두고 48MB


def _roots(hwpx: Path) -> list:
    with zipfile.ZipFile(hwpx) as z:
        return [etree.fromstring(z.read(n)) for n in sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n))]


def _bullets(text: str) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        s = line.strip().lstrip("ㆍ·-•").strip()
        if s and s != "-":
            out.append(s)
    return out


def _result_tables(roots) -> list[dict]:
    """결과표들(묶음 합본이면 동 순서대로 여러 개)."""
    out = []
    for root in roots:
        for tbl in root.iter(f"{{{rb.HP}}}tbl"):
            cells = rb._cells(tbl)
            if {"용역명", "점검기간", "관리주체명"} <= {re.sub(r"\s", "", rb._cell_text(v)) for v in cells.values()}:
                out.append(cells)
    return out


def _opinions(roots) -> list[str]:
    """정밀 요약표 "책임기술자 종합의견"(이름칸 아래 줄) — 동 순서대로."""
    out = []
    for root in roots:
        for tbl in root.iter(f"{{{rb.HP}}}tbl"):
            cells = rb._cells(tbl)
            k = rb._label(cells, "책임기술자종합의견", starts=True)
            if not k:
                continue
            right = rb._value(cells, "책임기술자종합의견", starts=True)
            below = rb._cell_text(cells[(k[0] + 1, 0)]) if (k[0] + 1, 0) in cells else ""
            out.append((right or below).strip())
    return out


def result_fields(hwpx: Path, nth: int = 0) -> dict:
    """만든 보고서 결과표(묶음이면 nth번째 동) → 실적보고 값. {project_nm, period, findings[], repairs[], grade, serious, public, opinion}."""
    roots = _roots(hwpx)
    tables = _result_tables(roots)
    if not tables:
        return {}
    cells = tables[min(nth, len(tables) - 1)]
    val = lambda *n, starts=False: rb._value(cells, *n, starts=starts)  # noqa: E731
    findings = [x for tc in rb._label_rows(cells, "점검주요결과", starts=True) for x in _bullets(rb._cell_text(tc))]
    repairs = _bullets(val("주요보수·보강", "주요보수보강", "주요보수", starts=True))
    serious_t, public_t = val("중대한결함", starts=True), val("공중이이용하는부위", starts=True)
    grade = re.sub(r"\s", "", val("안전등급", starts=True))
    m = re.search(r"[A-E]|양호|보통|미흡|불량|우수", grade)  # 3종 글자, 2종 낱말(10/16 — 2종은 양호·보통·미흡·불량)
    ops = _opinions(roots)
    no_repair = not repairs or all(re.search(r"대상\s*없음|주의관찰", r) for r in repairs)
    return {
        "project_nm": val("용역명"),
        "period": val("점검기간"),
        "findings": findings,
        "repairs": [] if no_repair else repairs,
        "grade": m[0] if m else "",
        "serious": bool(serious_t) and "없음" not in serious_t,
        "public": bool(public_t) and "없음" not in public_t,
        "serious_text": serious_t,
        "public_text": public_t,
        "opinion": ops[min(nth, len(ops) - 1)] if ops else "",
    }


def _k(won: int | float | None) -> int:
    return int(round((won or 0) / 1000))


def payload(db, reports: list) -> dict:
    """같이 내는 회차들(묶음 동 — 같은 해·반기·종류) → FMS 계약·실적 값. reports는 SitokReport(묶음 순서대로)."""
    from core.models_web import SitokContract, SitokFacility, SitokGroup, TechPerson

    reports = sorted(reports, key=lambda r: (db.get(SitokFacility, r.facility_id).group_order, r.id))
    r0 = reports[0]
    f0 = db.get(SitokFacility, r0.facility_id)
    c = db.get(SitokContract, r0.contract_id) if r0.contract_id else None
    grp = db.get(SitokGroup, f0.group_id) if f0.group_id else None
    # 묶음은 동마다 같은 합본 한글 파일 — 그 안 결과표·요약표가 동 순서대로라 순서 번호로 고름
    seen: dict = {}
    res = []
    for r in reports:
        if r.out_hwpx and Path(r.out_hwpx).exists():
            nth = seen.get(r.out_hwpx, 0)
            seen[r.out_hwpx] = nth + 1
            res.append(result_fields(Path(r.out_hwpx), nth))
        else:
            res.append({})
    name = (grp.name if grp and len(reports) > 1 else f0.name)
    project_nm = (res[0].get("project_nm") or f"{r0.year}년 {r0.half} {name} {KIND_LABEL.get(r0.kind, '정기안전점검')} 용역").strip()
    project_nm = re.sub(r'[\\/:*?"<>|]', " ", project_nm)  # FMS: 용역명에 특수문자 \ / : * ? " < > | 안 됨
    start, end = r0.period_start, r0.period_end
    notes = []
    facs = []
    for r, rr in zip(reports, res):
        f = db.get(SitokFacility, r.facility_id)
        from server.sitok import civil
        by_round = civil.amount_for(c.rounds, r.year, r.half, f.name) if c else None  # 계약 회차 줄(동별 금액)
        amt = int(re.sub(r"\D", "", r.amount_k or "") or 0) or (_k(by_round) if by_round else 0) or (_k(c.amount) if c and len(reports) == 1 else 0)
        if not amt:
            notes.append(f"{f.name}: 이 동 점검금액(천원)이 없습니다")
        if not f.fms_no:
            notes.append(f"{f.name}: FMS 시설물번호가 없습니다(관리대장)")
        facs.append({
            "facility_id": f.id, "report_id": r.id, "name": f.name, "fms_no": f.fms_no,
            "dign_gbn": DIGN.get(r.kind, "100"), "dign_label": KIND_LABEL.get(r.kind, ""), "half": r.half if r.kind == "정기" else "",
            "dign_amt": amt, "design_amt": amt, "base_amt": amt,
            # 실적(수시보고) 대상시설물 탭
            "dign_content": "\n".join(f"{i + 1}) {x}" for i, x in enumerate(rr.get("findings") or [])),
            "amend_content": "\n".join(f"ㆍ{x}" for x in rr.get("repairs") or []),
            "serious_defect_yn": "Y" if rr.get("serious") else "",
            "public_defect_yn": "Y" if rr.get("public") else "",
            "amend_req_yn": "Y" if rr.get("repairs") else "",
            "overall_grade": rr.get("grade", ""),
            "quake_target_yn": "N",  # 금회평가대상 — 정기·정밀은 비대상(형 PPT 13장)
            "opinion": rr.get("opinion", ""),
        })
        if not rr:
            notes.append(f"{f.name}: 만든 보고서(한글)가 없어 결과표 값을 못 읽었습니다")
    total = sum(x["dign_amt"] for x in facs)
    people = []
    ids = ([r0.chief_id] if r0.chief_id else []) + [i for i in (r0.participant_ids or []) if i != r0.chief_id]
    for n, pid in enumerate(ids):
        p = db.get(TechPerson, pid)
        if not p:
            continue
        safety = "안전" in (p.sitok_field or "")
        people.append({
            "rep_yn": "Y" if n == 0 else "N", "name": p.name, "birth": p.birth_date.isoformat() if p.birth_date else "",
            "start": start.isoformat() if start else "", "end": end.isoformat() if end else "",
            "days": ((end - start).days + 1) if start and end else "", "rate": 100,
            "tech_grade": TECH_GRADE.get((p.grade or "")[:2], ""), "grade_label": p.grade or "",
            "parti_field": "안전관리(건축)" if safety else "건축",  # 건축물 — 안전관리 분야면 안전관리(건축), 나머지 건축(기존 FMS 계약 현우선 토목 → 건축)
        })
    sector = c.sector if c else "민간"
    contract = {
        "project_nm": project_nm,
        "start_ymd": start.isoformat() if start else "", "end_ymd": end.isoformat() if end else "",
        "contract_ymd": c.contract_date.isoformat() if c and c.contract_date else "",
        "mng_main_nm": f0.owner_name,
        "const_amt": total, "design_amt": total,
        "divide_gbn": JOINT.get(c.joint_type if c else "독자수행", "01"), "financing_ratio": (c.joint_pct if c else 100),
        "bid_method": BID.get(c.bid_method if c else "수의계약", "03"),
        "eval_method": EVAL["기타"],
        "contract_method": CONTRACT["총액계약"],
        "price_method": PRICE["실비정액가산방식"],  # 대가산출 — 민간·관급 둘 다(민재형 10/15)
        "tech_field": FIELD.get(c.field if c else "건축", "2"),
        "etc_comment": "",
    }
    if not contract["contract_ymd"]:
        notes.append("계약일이 없습니다(계약)")
    return {"contract": contract, "facilities": facs, "engineers": people, "sector": sector, "notes": notes,
            "kind": r0.kind, "year": r0.year, "half": r0.half, "group": name}


# ---------- e-보고서 파일 나누기 ----------

# 부록 간지 제목(띄어쓰기·기호 빼고) → (FMS 폴더, 파일 이름)
APPX = [
    (r"시설물관리대장", ("보고서 부록", "시설물관리대장 사본")),
    (r"외관조사사진첩", ("보고서 부록", "외관조사 사진첩")),
    (r"외관(조사)?망도", ("보고서 부록", "외관조사망도")),  # 정기 간지는 "외 관 망 도"(10/25)
    (r"측정.*성과표|시험.*성과표|장비측정위치도", ("보고서 부록", "측정, 시험 성과표")),
    (r"상태평가결과", ("보고서 부록", "상태평가 결과 자료")),
    (r"사용장비", ("보고서 부록", "사용장비 및 기기의 사진")),
    (r"과업지시서", ("과업지시서", "과업지시서")),
    (r"과업수행계획서", ("보고서 부록", "과업수행계획서")),
    (r"사전검토", ("보고서 부록", "사전검토 보고서")),
    (r"계약서", ("계약서 및 대가내역서", "계약서")),
    (r"대가내역", ("계약서 및 대가내역서", "대가내역서")),
]
FOLDERS = ["계약서 및 대가내역서", "과업지시서", "결과표", "보고서", "보고서 부록"]


def _lines(page) -> list[str]:
    return [x.strip() for x in page.get_text().splitlines() if x.strip()]


def _divider(lines: list[str]) -> tuple[int, str, str] | None:
    """부록 간지 쪽이면 (단계, 제목, 모양) — 단계 1 = 큰 간지(파일 하나), 2 = 작은 간지(아는 항목이면 따로, 아니면 큰 간지 파일에 붙음).
    정밀(10/15 숭의) "1. 시설물관리대장 사본"·"7-2. 과 업 지 시 서", 정기(10/25) "부록.1" + 다음 줄 "시설물관리대장 사본"·"부록3-4. 과 업 지 시 서",
    옹벽 "부록3.과업지시서". 모양 = 처음 나온 큰 간지 모양으로 고정할 때 씀(끼운 옛 관리대장 속 "부록.5 시설물대장 사본" 같은 쪽에 속지 않게)."""
    if not lines or len("".join(lines)) > 80:
        return None
    m = re.match(r"^부록\s*\.\s*(\d+)$", lines[0])
    if m and len(lines) > 1:
        return 1, lines[1], "dot"
    m = re.match(r"^부록\s*\d+-\d+(?:-\d+)?\.\s*(\S.*)$", lines[0])
    if m:
        return 2, m[1], "sub"
    m = re.match(r"^부록\s*\d+\.\s*(\S.*)$", lines[0])
    if m:
        return 1, m[1], "num"
    m = re.match(r"^(\d+)(-\d+)?\.\s*([^\d\s].*)$", lines[0])  # 정밀 — "4.3 정밀…"처럼 번호 뒤가 숫자면 본문 제목
    if m and not re.search(r"\d+\.\s*\S", " ".join(lines[1:3])):
        return (2 if m[2] else 1), m[3], "plain"
    return None


def split_plan(pdf: Path) -> list[dict]:
    """합본 PDF → [{folder, name, pages:[(시작, 끝) 0부터]}]. 결과표는 동마다 결과표 쪽만 모아 한 파일."""
    d = pymupdf.open(str(pdf))
    pages = [_lines(p) for p in d]
    n = len(pages)
    # 부록 표지 = 본문 뒤쪽의 짧은 쪽에 "부 록"만 있는 줄(앞쪽 목차의 "- 부 록 -"은 n/4 앞이라 제외)
    appx = next((i for i, ls in enumerate(pages) if i > n // 4 and len("".join(ls)) < 200 and any(re.fullmatch(r"[-▣\s]*부\s*록[-\s]*", x) for x in ls[:3])), n)
    plan: list[dict] = []

    def add(folder: str, name: str, a: int, b: int) -> None:
        for x in plan:
            if x["folder"] == folder and x["name"] == name:
                x["pages"].append((a, b))
                return
        plan.append({"folder": folder, "name": name, "pages": [(a, b)]})

    # 결과표 — "…안전점검 결과표"·"…안전진단 결과표"로 시작하는 쪽부터 다음 제목(요약표·결과표·요약문·위치도·목차) 앞까지.
    # 정기 양식 제목은 "…정기안전점검(하반기)" / "결과표" 두 줄(83차) — 첫 두 줄을 합쳐서도 봄(10/25)
    head = lambda ls: " ".join(ls[:2])  # noqa: E731
    res = r"(점검|진단)(\([^)]*\))?\s*결과표$"
    starts = [i for i in range(appx) if pages[i] and (re.search(res, pages[i][0]) or re.search(res, head(pages[i])))]
    for k, s in enumerate(starts):
        e = s
        while e + 1 < appx and e + 1 not in starts and not (pages[e + 1] and re.search(r"요약표|실시결과|현황표|결과표$|요\s*약\s*문|위치도|목\s*차", head(pages[e + 1]))):
            e += 1
        add("결과표", "결과표", s, e)
    add("보고서", "본보고서", 0, appx - 1)
    # 부록 — 간지마다(간지 쪽 포함) 다음 간지 앞까지. 큰 간지 = 파일, 작은 간지(부록3-4 등)는 아는 항목이면 따로 아니면 큰 간지 파일에
    # (사진첩 안 동 간지 "부록2-1. 본관"은 사진첩에 남음). 큰 간지 모양은 처음 나온 것으로 고정.
    divs = [(i, dv) for i in range(appx, n) if (dv := _divider(pages[i]))]
    first = next((dv[2] for _, dv in divs if dv[0] == 1), None)
    divs = [(i, dv) for i, dv in divs if dv[0] == 2 or dv[2] == first]
    other = ("보고서 부록", "기타 부록 참고자료")
    parent = other
    for k, (i, (level, title, _)) in enumerate(divs):
        e = (divs[k + 1][0] - 1) if k + 1 < len(divs) else n - 1
        key = re.sub(r"[\s,·ㆍ.]", "", title)
        hit = next((v for pat, v in APPX if re.search(pat, key)), None)
        if level == 1:
            parent = hit or other
            add(*parent, i, e)
        else:
            add(*(hit or parent), i, e)
    order = {f: j for j, f in enumerate(FOLDERS)}
    plan.sort(key=lambda x: order.get(x["folder"], 9))
    return plan


def write_split(pdf: Path, out_dir: Path) -> list[dict]:
    """split_plan대로 PDF 파일을 만든다(50MB 넘으면 "이름 1·2…"로 나눔) → [{folder, name, file, pages, size}]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    src = pymupdf.open(str(pdf))
    made = []
    for x in split_plan(pdf):
        doc = pymupdf.open()
        for a, b in x["pages"]:
            doc.insert_pdf(src, from_page=a, to_page=b)
        data = doc.tobytes(garbage=3, deflate=True)
        if len(data) > MAX_FILE:  # 먼저 그림 해상도를 낮춰 봄(스캔한 관리대장·성과표 사진이 큼)
            try:
                doc.rewrite_images(dpi_threshold=200, dpi_target=150, quality=80)
                data = doc.tobytes(garbage=3, deflate=True)
            except Exception:  # noqa: BLE001
                pass
        parts = [data]
        if len(data) > MAX_FILE:  # 쪽을 반씩 나눠 50MB 아래로
            k = 2
            while True:
                per = -(-doc.page_count // k)
                parts = []
                for j in range(k):
                    sub = pymupdf.open()
                    sub.insert_pdf(doc, from_page=j * per, to_page=min(doc.page_count, (j + 1) * per) - 1)
                    parts.append(sub.tobytes(garbage=3, deflate=True))
                if max(len(p) for p in parts) <= MAX_FILE or k > 20:
                    break
                k += 1
        counts = [doc.page_count] if len(parts) == 1 else [min(doc.page_count, (j + 1) * per) - j * per for j in range(len(parts))]
        for j, data in enumerate(parts):
            nm = x["name"] if len(parts) == 1 else f"{x['name']} {j + 1}"
            dest = out_dir / x["folder"] / f"{nm}.pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            made.append({"folder": x["folder"], "name": nm, "file": str(dest), "pages": counts[j], "size": len(data)})
    return made


def today() -> str:
    return datetime.date.today().isoformat()


def apply_engineers(payload: dict, found: dict) -> list[str]:
    """FMS 기술자 찾기 결과로 기술등급·직무분야를 FMS 값에 맞춤(우리 명단과 다르면 FMS를 따름 — FMS에 등록된 자격이 기준).
    found = fms_bot.lookup_engineers 결과. 다른 점은 글로 돌려줌(사용자 확인용)."""
    diffs = []
    building = payload["contract"].get("tech_field") == FIELD["건축"]
    for e in payload["engineers"]:
        f = found.get(e["name"]) or {}
        if f.get("missing"):
            diffs.append(f"{e['name']}: FMS 기술자 목록에 없음")
            continue
        if f.get("grade") and f["grade"] != e["tech_grade"]:
            diffs.append(f"{e['name']}: 기술등급 우리 명단 {e['grade_label'] or '-'} / FMS {f.get('grade_label')}")
        e["tech_grade"], e["grade_label"] = f.get("grade", e["tech_grade"]), f.get("grade_label", e["grade_label"])
        field = f.get("field", "")
        if building:
            e["parti_field"] = "안전관리(건축)" if "안전" in field else "건축"
        else:
            e["parti_field"] = ("안전관리" if "안전" in field else "토목") + "(교량및터널)"
        e["fms_field"] = field
    return diffs


def contract_files(db, reports: list) -> tuple[list[dict], list[str]]:
    """e-보고서 "계약서 및 대가내역서" 폴더에 더할 대가내역서 — 이 회차 계약과 이어진 서류 자동화 계약(보고서 쪽 계약으로 넣은 것, 없으면 같은 시설물 연결)으로
    만든 대가내역서.pdf(없으면 지금 만듦, server/sitok/daega.py). → (파일들, 알림)."""
    from core.models_web import SitokDocContract
    from server.api.routers.sitok_docs import folder
    from server.sitok import daega

    r0 = reports[0]
    q = db.query(SitokDocContract)
    c = (q.filter(SitokDocContract.report_contract_id == r0.contract_id).order_by(SitokDocContract.id.desc()).first() if r0.contract_id else None) \
        or q.filter(SitokDocContract.facility_id.in_([r.facility_id for r in reports])).order_by(SitokDocContract.id.desc()).first()
    if c is None:
        return [], ["대가내역서: 이어진 서류 자동화 계약이 없어 못 만듦 — 서류 자동화 · 시특법 계약에서 [📑 대가내역서]"]
    pdf = folder(c) / "대가내역서.pdf"
    if not pdf.exists():
        try:
            daega.build_pdf(c, pdf.with_suffix(".xlsx"), pdf)
        except Exception as e:  # noqa: BLE001
            return [], [f"대가내역서를 만들지 못했습니다: {str(e)[:100]}"]
    return [{"folder": "계약서 및 대가내역서", "name": "대가내역서", "file": str(pdf)}], []
