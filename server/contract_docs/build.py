"""착수계·완수계 엑셀 만들기 — 회사 양식(data/templates/*_양식.xlsx)을 열어 값·그림·도장을 넣고 저장한다. DB는 모른다(값만 받음).

양식 시트 순서(10/6 받은 파일 그대로 — 바뀌면 START_SHEETS/DONE_SHEETS 개수 검사에서 멈춤):
- 착수계 14장: 갑지·착수계·현장대리인계·[현장대리인 자격증·교육수료증·경력증명서·재직증명서]·책임참여기술자 현황·
  [참여기술자 자격증·교육수료증·경력증명서·재직증명서]·예정공정표·보안각서 — 참여기술자 4장은 사람 수만큼 복사(0명이면 뺌).
- 완수계 10장: 갑지·완수계·완수검사원·청구서·4대보험(건강·연금)·4대보험(고용·산재)·국세·지방세·사업자등록증·통장 사본.
갑지 오른쪽 회색 칸(S4~S12)을 다른 시트가 수식으로 가져다 쓰므로 갑지만 채우면 된다. 예정공정표도 수식(기간 4등분) 그대로.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from core.db import BASE_DIR
from server.contract_docs import sheet_tools as st

TEMPLATE_DIR = BASE_DIR / "data" / "templates"
START_TEMPLATE = TEMPLATE_DIR / "착수계_양식.xlsx"
DONE_TEMPLATE = TEMPLATE_DIR / "완수계_양식.xlsx"
START_SHEETS = 14
DONE_SHEETS = 10

# 기술자 서류 그림 칸(올리는 파일 종류) — 시트 순서대로
PERSON_DOCS = [("license", "자격증"), ("edu", "교육수료증"), ("career", "경력증명서")]
# 완수계 회사 서류 — 시트 4~9 순서대로
COMPANY_DOCS = [("ins_health", "4대보험 완납증명서(건강·연금)"), ("ins_employ", "4대보험 완납증명서(고용·산재)"),
                ("tax_national", "국세 완납증명서"), ("tax_local", "지방세 완납증명서"),
                ("biz_reg", "사업자등록증"), ("bankbook", "통장 사본")]


@dataclass
class Contract:
    client: str = ""          # 발주처
    title: str = ""           # 용역명
    contract_no: str = ""
    amount: int | None = None
    contract_date: datetime.date | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None      # 준공기한(완수일)
    settle_amount: int | None = None           # 정산금액(비면 계약금액)
    actual_end_date: datetime.date | None = None  # 실제준공일(비면 준공기한)


@dataclass
class Person:
    name: str
    address: str = ""
    birth_date: datetime.date | None = None
    position: str = ""        # 직책
    join_date: datetime.date | None = None
    qualification: str = ""   # 기술자격(여러 개면 줄바꿈)
    grade: str = ""           # 기술등급
    docs: dict[str, str] = field(default_factory=dict)  # PERSON_DOCS 종류 → 그림 파일 경로


@dataclass
class Common:
    doc_no: str = ""
    greeting: str = ""        # "귀 ○의" — 비면 발주처로 정함
    send_date: datetime.date | None = None  # 완수계 갑지 발송일(착수계는 착수일)
    contact_name: str = ""    # 갑지 담당
    seal: bool = True         # 둥근 대표이사 도장 넣기


def greeting_word(client: str) -> str:
    """발주처 이름 → 갑지 "1. 귀 ○의 무궁한 발전을 기원합니다."의 ○(10/6 사용자: 발주처에 맞춰 자동, 고칠 수 있게).
    화면(js/contract-docs.js greetingWord)도 같은 규칙 — 바꾸면 둘 다."""
    c = (client or "").strip()
    if c.endswith(("사단", "여단", "군단", "연대", "대대", "부대", "사령부")):  # 국방조달(10/6 수도기계화보병사단) — "귀 부대의"(사용자 확인)
        return "부대"
    if "공사" in c[-4:] or c.endswith("공단"):
        return "사" if "공사" in c[-4:] else "공단"
    for end in ("청", "시", "군", "구", "도"):
        if c.endswith(end):
            return end
    # "경기도 포천시 건설교통국"처럼 뒤에 부서가 붙으면 — 띄어 쓴 마디를 뒤에서부터 보고 시·군·구·청 단위(10/6 기산7리 계약)
    for word in reversed(c.split()[:-1]):
        for end in ("청", "시", "군", "구"):
            if word.endswith(end):
                return end
    return "기관"


def default_doc_no(contract: Contract, day: datetime.date | None) -> str:
    """문서번호 = KFSC21C_계약번호_월일(사용자 10/6 회사 확인 — 착수계는 착수일, 완수계는 발송일). 화면(js/contract-docs.js autoDocNo)도 같은 규칙."""
    if not contract.contract_no:
        return ""
    return f"KFSC21C_{contract.contract_no}" + (f"_{day:%m%d}" if day else "")


def _load(path: Path, sheets: int):
    if not path.exists():
        raise FileNotFoundError(f"양식 파일이 없습니다: {path}")
    wb = openpyxl.load_workbook(path)
    if len(wb.worksheets) != sheets:
        raise ValueError(f"양식 시트 수가 {sheets}장이 아닙니다({len(wb.worksheets)}장) — 양식이 바뀌었으면 build.py 시트 순서를 맞추세요.")
    return wb


def _fill_cover(ws: Worksheet, c: Contract, common: Common, greet_default: str) -> None:
    ws["S4"] = c.client
    ws["S5"] = c.title
    ws["S6"] = c.contract_no
    ws["S7"] = c.amount
    ws["S8"] = c.contract_date
    ws["S9"] = c.start_date
    ws["S10"] = c.end_date
    ws["C4"] = common.doc_no
    ws["C10"] = f"1. 귀 {common.greeting or greet_default}의 무궁한 발전을 기원합니다."
    if common.contact_name:
        ws["B34"] = common.contact_name


_DIGITS = "영일이삼사오육칠팔구"


def korean_amount(n: int | None) -> str:
    """금액 → 한글("이천삼백오십오만사천팔백") — 양식의 한글 숫자 서식([DBNum4], "일"을 빼지 않음: 일백만·일천일백)과 같게(10/6 실측)."""
    if not n:
        return "영" if n == 0 else ""
    out = []
    for gi, unit in enumerate(["", "만", "억", "조"]):
        group = (n // 10000 ** gi) % 10000
        if not group:
            continue
        words = "".join(_DIGITS[d] + u for d, u in zip((group // 1000 % 10, group // 100 % 10, group // 10 % 10, group % 10), ("천", "백", "십", "")) if d)
        out.append(words + unit)
    return "".join(reversed(out))


def _amount_line(ws: Worksheet, cell: str, amount: int | None) -> None:
    """"팔십삼만육천 원 ( ₩836,000 )" 줄을 글자 하나로 — 양식은 한글 숫자 서식 칸 + 옆 칸 "원 ( ₩… )"이라 금액이 길면(2,300만 원 이상 등)
    칸을 넘쳐 ###로 나왔음(10/6 형). 글자는 옆 빈칸으로 이어서 보이므로 오른쪽 칸들(원·괄호·숫자)을 비우고 한 칸에 넣는다. 병합 칸이면 풀어서 넘치게."""
    col_row = ws[cell]
    r, c0 = col_row.row, col_row.column
    merged = [rng for rng in ws.merged_cells.ranges if cell in rng]
    for rng in merged:
        ws.unmerge_cells(str(rng))
    for col in range(c0 + 1, c0 + 6):  # 원 ( 숫자 ) 칸
        ws.cell(r, col).value = None
    col_row.value = f"{korean_amount(amount)}원 ( ₩{amount:,} )" if amount is not None else ""
    col_row.number_format = "General"
    if merged:  # 청구서처럼 합친 칸이었으면 오른쪽 칸까지 넓혀 다시 합침(합친 칸 글자는 넘쳐 보이지 않음 — 표 선은 그대로)
        ws.merge_cells(start_row=r, start_column=c0, end_row=r, end_column=c0 + 5)


def _date_text(d: datetime.date | None) -> str:
    return f"{d:%Y}년  {d:%m}월  {d:%d}일" if d else "      년      월      일"


def _fill_person_sheets(sheets: list[Worksheet], p: Person, role: str, warnings: list[str]) -> None:
    """한 사람 4장(자격증·교육수료증·경력증명서·재직증명서). role = "현장대리인" | "참여기술자"."""
    for ws, (kind, label) in zip(sheets[:3], PERSON_DOCS):
        ws["A2"] = f"{role} {label}({p.name})"
        old = st.main_image(ws)
        src = p.docs.get(kind)
        if src and Path(src).exists():
            if old is not None:
                st.replace_image(ws, old, src)
        else:
            st.drop_image(ws, old)
            warnings.append(f"{p.name} {label} — 올린 그림이 없어 빈 장으로 나갑니다(설정 탭 기술자 명단에서 올리세요).")
    ws = sheets[3]
    ws["A2"] = f"{role} 재직 증명서({p.name})"
    ws["E4"] = f" {p.address} " if p.address else ""
    ws["E6"] = p.name
    ws["M6"] = p.position
    ws["M7"] = f"{p.birth_date:%Y}년 {p.birth_date:%m}월 {p.birth_date:%d}일" if p.birth_date else ""  # 양식 칸이 날짜 형식이 아니라 글자로
    ws["B9"] = f"상기자는 {_date_text(p.join_date)} 부터 당사에 재직하고 있음을 증명함."
    empty = [label for value, label in ((p.address, "주소"), (p.birth_date, "생년월일"), (p.join_date, "입사일"), (p.position, "직책"))
             if not value]
    if empty:
        warnings.append(f"{p.name} 재직증명서 — 빈 칸: {'·'.join(empty)}(설정 탭 기술자 명단에서 채우세요).")


def _copy_person_sheets(wb, src: list[Worksheet], after: Worksheet) -> list[Worksheet]:
    """참여기술자 4장을 복사해 after 시트 바로 뒤에 둔다(그림·인쇄 범위도 같이)."""
    out = []
    pos = wb.worksheets.index(after) + 1
    for i, s in enumerate(src):
        ws = wb.copy_worksheet(s)
        ws.print_area = s.print_area
        ws.sheet_view.zoomScale = s.sheet_view.zoomScale
        ws.sheet_view.view = s.sheet_view.view
        for img in s._images:
            if not st.is_seal(img) and img.anchor._from.col < st.print_bounds(s)[0]:
                st.add_image_copy(ws, img)
        wb._sheets.remove(ws)
        wb._sheets.insert(pos + i, ws)
        out.append(ws)
    return out


def _unique_titles(wb) -> None:
    """시트 이름을 "현장대리인 자격증", "참여기술자1 자격증"처럼 정리(이름은 31자까지, 겹치지 않게)."""
    seen: set[str] = set()
    for ws in wb.worksheets:
        name = ws.title[:31]
        n = 2
        while name in seen:
            name = f"{ws.title[:27]} ({n})"
            n += 1
        seen.add(name)
        if ws.title != name:
            ws.title = name


def _fill_staff_table(ws: Worksheet, agent: Person, participants: list[Person]) -> None:
    """책임·참여 기술자 현황 표 — 5행 책임기술자, 6행부터 참여기술자(사람 수만큼 6행 모양을 복사)."""
    rows = [("책임기술자", agent)] + [("참여기술자", p) for p in participants]
    base = 6
    for i, (label, p) in enumerate(rows):
        r = 5 + i
        if r > base:
            ws.row_dimensions[r].height = ws.row_dimensions[base].height
            for col in "BCDEF":
                ws[f"{col}{r}"]._style = ws[f"{col}{base}"]._style
        ws[f"B{r}"] = label
        ws[f"C{r}"] = "(주)한국미래안전"
        ws[f"D{r}"] = p.name
        ws[f"E{r}"] = p.qualification
        ws[f"F{r}"] = p.grade
    if not participants:  # 참여기술자 없으면 6행 비움(테두리는 양식 그대로)
        for col in "BCDEF":
            ws[f"{col}{base}"] = None


def build_start(contract: Contract, common: Common, agent: Person, participants: list[Person], out: Path,
                template: Path = START_TEMPLATE) -> list[str]:
    """착수계 엑셀을 out에 만든다. 돌려주는 값 = 화면에 보일 경고(빠진 서류 등)."""
    warnings: list[str] = []
    wb = _load(template, START_SHEETS)
    seal = st.seal_bytes(wb)
    ws = wb.worksheets
    cover, start, agent_ws, p1, table, p2, pledge = ws[0], ws[1], ws[2], ws[3:7], ws[7], ws[8:12], ws[13]  # ws[12] 예정공정표는 수식 그대로
    _fill_cover(cover, contract, common, greeting_word(contract.client))
    cover["S3"] = common.doc_no
    cover["R10"] = "완수일"
    for s in ws[1:]:
        st.clear_outside_print(s)

    _amount_line(start, "H7", contract.amount)  # 착수계 "계 약 금 액" 줄
    agent_ws["H7"] = agent.address
    agent_ws["H8"] = agent.name
    agent_ws["H9"] = agent.birth_date
    _fill_person_sheets(list(p1), agent, "현장대리인", warnings)

    # 참여기술자: 첫 사람은 양식 4장, 둘째부터 복사, 0명이면 양식 4장을 뺀다
    groups: list[list[Worksheet]] = []
    if participants:
        groups.append(list(p2))
        last = p2[-1]
        for _ in participants[1:]:
            g = _copy_person_sheets(wb, list(p2), last)
            groups.append(g)
            last = g[-1]
        for g, p in zip(groups, participants):
            _fill_person_sheets(g, p, "참여기술자", warnings)
    else:
        for s in p2:
            wb.remove(s)
    _fill_staff_table(table, agent, participants)

    if contract.start_date is None or contract.end_date is None:
        warnings.append("착수일·완수일이 비어 예정공정표 날수가 계산되지 않습니다.")
    _apply_seals(wb, common.seal, seal, text_cells={start.title: ("A24", 40), agent_ws.title: ("A24", 52), pledge.title: ("A14", 6),
                                                   **{g[3].title: ("B24", -2) for g in [list(p1)] + groups}})
    _unique_titles(wb)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return warnings


def build_done(contract: Contract, common: Common, company_docs: dict[str, str], out: Path,
               template: Path = DONE_TEMPLATE) -> list[str]:
    """완수계 엑셀을 out에 만든다. company_docs = COMPANY_DOCS 종류 → 그림 파일 경로."""
    warnings: list[str] = []
    wb = _load(template, DONE_SHEETS)
    seal = st.seal_bytes(wb)
    ws = wb.worksheets
    cover = ws[0]
    _fill_cover(cover, contract, common, greeting_word(contract.client))
    cover["S11"] = contract.actual_end_date or contract.end_date
    cover["S12"] = contract.settle_amount if contract.settle_amount is not None else contract.amount
    cover["H35"] = common.send_date or datetime.date.today()
    settle = contract.settle_amount if contract.settle_amount is not None else contract.amount
    for sheet in (ws[1], ws[2]):  # 완수계·완수검사원 "계약금액"·"정산금액" 줄
        _amount_line(sheet, "H7", contract.amount)
        _amount_line(sheet, "H8", settle)
    _amount_line(ws[3], "G7", settle)  # 청구서 "청구 금액"  # 양식은 =TODAY() — 열 때마다 바뀌지 않게 만든 날 값으로
    for s in ws[1:]:
        st.clear_outside_print(s)
    for s, (kind, label) in zip(ws[4:10], COMPANY_DOCS):
        old = st.main_image(s)
        src = company_docs.get(kind)
        if src and Path(src).exists():
            if old is not None:
                st.replace_image(s, old, src)
        else:
            st.drop_image(s, old)
            warnings.append(f"{label} — 올린 서류가 없어 빈 장으로 나갑니다(설정 탭에서 올리세요).")
    _apply_seals(wb, common.seal, seal, text_cells={ws[1].title: ("A25", 41), ws[2].title: ("A25", 45)},
                 extra=lambda: st.place_seal(ws[3], seal, st.col_x(ws[3], 11) + 39, st.row_y(ws[3], 20) + st.row_px(ws[3], 20) / 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return warnings


def _apply_seals(wb, on: bool, seal: bytes | None, text_cells: dict[str, tuple[str, float]], extra=None) -> None:
    """양식에 있던 도장(인쇄 범위 밖)은 늘 지우고, 넣기면 "(인)" 글자 끝·원본대조필 칸에 새로 놓는다.
    text_cells = 시트 이름 → ("대표 … (인)" 칸, 병합 범위 오른쪽 끝에서 도장 가운데까지 픽셀). 픽셀은 시트마다 PDF에서 잰 값(10/6 —
    열 너비 어림이 시트마다 달리 어긋나서)."""
    for ws in wb.worksheets:
        st.remove_seals(ws)
    if not on or seal is None:
        return
    for ws in wb.worksheets:
        if ws.title in text_cells:
            coord, back = text_cells[ws.title]
            st.seal_on_text_end(ws, coord, seal, back)
        else:
            st.seal_on_original_box(ws, seal)
    if extra:
        extra()
