"""서류 자동화 · 시특법 민간 계약서(2026-10-12 사용자·민재형) — 민간은 착수계·완수계가 없고 계약서를 우리가 작성해 업체에 보내 날인 받음.

양식은 사실상 하나(사용자): 종류 글자만 다름 — 회차 줄(rounds: 연도·반기·정기/정밀·금액)이 정기만 "정기안전점검", 정밀만 "정밀안전점검",
섞이면 "정기·정밀안전점검"(계약건명·제목·계약조건 본문). 계약금액 칸 = 회차마다 한 줄 + 총합. 끝이 없는 계약(평생) = 계약기간 "~ 계약 해지 시까지"
+ "매 반기(정기) : 금 ○○원정"(총합 없음 — 사용자 10/12). 계약상대자(우리 회사) 칸은 고정.

템플릿: data/templates/시특법_민간계약서_양식.hwpx — 견본(정밀안전점검 계약서 · 청천영진아파트)의 값 자리를 "{시설물명}"처럼 자리표시로 바꾼 것
(make_template — 견본 두 개는 제1조(목적) 문장이 서로 뒤바뀌어 있어 목적은 종류에 맞게 코드가 넣음: PURPOSE). 회사가 한글에서 고쳐 올릴 수 있음(자리표시만 지키면 됨).
"""
from __future__ import annotations

import datetime
import io
import re
import zipfile
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb
from server.sitok import seasons

HP, T = rb.HP, rb.T
TEMPLATE_NAME = "시특법_민간계약서_양식.hwpx"
# 내진성능평가 민간 계약서(서류 자동화 › 내진성능평가, 10/28) — 시특법 양식을 바탕으로 본문 조항(시설물안전법 조항·FMS 등)을 내진성능평가에 맞게 바꾼 양식
# (server/scripts/make_seismic_civil_template.py가 처음 한 번 만듦, 형이 한글에서 고쳐 [고친 양식 올리기]로 바꿈). 회차 줄 없이 금액 한 줄.
SEISMIC = "내진"
TEMPLATE_NAME_SEISMIC = "내진_민간계약서_양식.hwpx"
SEISMIC_WORD = "내진성능평가"
SEISMIC_PURPOSE = ("본 과업은 「지진·화산재해대책법」 제16조의2에 따른 기존 시설물의 내진성능평가로써 현장조사(외관조사·재료시험·부재조사 등)와 구조해석을 통하여 "
                   "시설물의 내진성능을 평가하고, 필요한 경우 내진보강 방안을 제시하여 지진으로 인한 재해를 예방하고 공공의 안전을 확보하는데 그 목적이 있다.")


def is_seismic(c) -> bool:
    """서류 자동화 계약이 내진성능평가 분야인지(sitok_doc_contract.field, 0067)."""
    return getattr(c, "field", "") == SEISMIC
KINDS = ("정기", "정밀", "진단")  # 진단 = 정밀안전진단(1종, 10/20 민재형 — 도래주기 server/sitok/cycle.py)
HALVES = seasons.ALL  # 상반기·하반기 + 연 3회 해빙기·우기·동절기(10/16)
TOKENS = ("문서번호", "종류", "시설물명", "관리주체", "대표자", "계약건명", "계약금액", "계약보증액", "지체상금율", "계약기간", "위치", "제원", "계약일", "목적")

PURPOSE = {  # 제1조(목적) — 견본 두 개에서(서로 뒤바뀌어 있던 것을 제자리로), 섞이면 둘을 합침(형 검토)
    "정기": "본 과업은 「시설물의 안전 및 유지관리에 관한 특별법」 제11조 및 동법 시행령 제8조 규정에 따른 정기안전점검으로써 준공후 년2회 상반기와 하반기 "
            "육안검사를 통하여 시설물의 물리적·기능적 결함과 시설물에 내재되어 있는 위험요인을 조사하여 재해를 예방하고 시설물의 효용을 증진시켜 공공의 안전을 "
            "확보하는데 그 목적이 있다.",
    "정밀": "이 계약은 “갑”이 관리하고 있는 시설물에 대하여 “을”이 시설물 안전 및 유지관리에 관한 특별법에 의거, 준공후 매3년마다 1회 이상으로 면밀한 육안검사와 "
            "측정기구를 통하여 현재 존재하거나 향후 있을 수 있는 시설물의 하자 또는 결함 등을 사전에 발견, 적절한 조치를 취할 수 있도록 함으로써 재해 및 재난을 "
            "예방하고 시설물의 효용을 증진시킴으로써 공공의 안전을 확보하고 나아가 국민의 복리증진에 기여함을 그 목적으로 한다.",
    "정기·정밀": "본 과업은 「시설물의 안전 및 유지관리에 관한 특별법」 제11조 및 동법 시행령 제8조 규정에 따른 정기안전점검(준공후 년2회 상반기와 하반기 육안검사)과 "
                 "정밀안전점검(준공후 매3년마다 1회 이상 면밀한 육안검사와 측정기구)을 통하여 시설물의 물리적·기능적 결함과 시설물에 내재되어 있는 위험요인을 "
                 "조사하여 재해를 예방하고 시설물의 효용을 증진시켜 공공의 안전을 확보하는데 그 목적이 있다.",
}


# 정밀안전진단(1종) — 시설물안전법 제12조·시행령 제10조, 정의는 법 제2조 "정밀안전진단"(10/20 민재형 "정밀안전진단도 나누고")
DIAG_PURPOSE = ("본 과업은 「시설물의 안전 및 유지관리에 관한 특별법」 제12조 및 동법 시행령 제10조 규정에 따른 정밀안전진단으로써 시설물의 물리적·기능적 결함을 "
                "발견하고 그에 대한 신속하고 적절한 조치를 하기 위하여 구조적 안전성과 결함의 원인 등을 조사·측정·평가하여 보수·보강 등의 방법을 제시함으로써 "
                "재해를 예방하고 시설물의 효용을 증진시켜 공공의 안전을 확보하는데 그 목적이 있다.")
DIAG_ALSO = ("아울러 「시설물의 안전 및 유지관리에 관한 특별법」 제12조 및 동법 시행령 제10조 규정에 따른 정밀안전진단을 통하여 시설물의 구조적 안전성과 "
             "결함의 원인 등을 조사·측정·평가하고 보수·보강 등의 방법을 제시한다.")


def template_path(field: str = "") -> Path:
    from server.contract_docs.build import TEMPLATE_DIR
    return TEMPLATE_DIR / (TEMPLATE_NAME_SEISMIC if field == SEISMIC else TEMPLATE_NAME)


def template_name(field: str = "") -> str:
    return TEMPLATE_NAME_SEISMIC if field == SEISMIC else TEMPLATE_NAME


# ---------- 값 ----------

def _won(v) -> int:
    return int(str(v or 0).replace(",", "") or 0)


def normalize_rounds(v) -> list[dict]:
    """회차 줄 정리 — [{year, half, kind 정기|정밀(없으면 정기), amount 원, parts?}] (연도·반기 순). 서류 자동화 계약·보고서 쪽 계약 둘 다 씀.
    parts = 동이 여럿인 묶음 계약의 동별 금액 [{name, amount, kind?}](2026-10-15 민재형 — 대가내역서·FMS가 동별 금액을 씀), 둘 이상일 때만 두고 amount = 합.
    parts[].kind = 그 동만 줄 종류와 다를 때의 종류(10/31 민재형 — 같은 반기에 어떤 동은 정기, 어떤 동은 정밀·진단). 없으면 줄 종류(kind)."""
    out = []
    for r in v or []:
        try:
            y = int(r.get("year"))
            if 0 < y < 100:  # 계약서 "26년 상반기"를 26으로 읽은 것(10/16 숭의교회) → 2026
                y += 2000
        except (TypeError, ValueError, AttributeError):
            continue
        if r.get("half") not in HALVES:
            continue
        item = {"year": y, "half": r["half"], "kind": r.get("kind") if r.get("kind") in KINDS else "정기", "amount": _won(r.get("amount"))}
        parts = [{"name": str(p.get("name") or "").strip(), "amount": _won(p.get("amount")),
                  **({"kind": p["kind"]} if p.get("kind") in KINDS and p.get("kind") != item["kind"] else {})} for p in (r.get("parts") or []) if isinstance(p, dict)]
        parts = [p for p in parts if p["name"]]
        if len(parts) >= 2:
            item["parts"] = parts
            item["amount"] = sum(p["amount"] for p in parts)
        out.append(item)
    return sorted(out, key=lambda r: (r["year"], seasons.order(r["half"])))


def buildings(rounds: list | None) -> list[str]:
    """회차 줄에 나오는 동 이름(처음 나온 순서) — 동별 금액이 없으면 []."""
    names: list[str] = []
    for r in rounds or []:
        for p in r.get("parts") or []:
            if p.get("name") and p["name"] not in names:
                names.append(p["name"])
    return names


def _nm(s: str | None) -> str:
    return re.sub(r"\s", "", s or "")


def round_of(rounds: list | None, year: int, half: str) -> dict | None:
    return next((r for r in rounds or [] if r.get("year") == year and r.get("half") == half), None)


def find_part(parts: list, name: str | None) -> dict | None:
    """동 이름으로 동별 금액 줄 찾기(띄어쓰기 무시·포함까지)."""
    n = _nm(name)
    if not n:
        return None
    return next((p for p in parts if _nm(p.get("name")) == n), None) or next((p for p in parts if _nm(p.get("name")) in n or n in _nm(p.get("name"))), None)


def part_kind(r: dict, name: str | None = None) -> str:
    """그 회차 줄에서 그 동의 점검 종류 — 동별 종류가 있으면 그것, 없으면 줄 종류(10/31)."""
    hit = find_part(r.get("parts") or [], name)
    return (hit or {}).get("kind") if (hit or {}).get("kind") in KINDS else (r.get("kind") if r.get("kind") in KINDS else "정기")


def round_kinds(r: dict) -> list[str]:
    """그 회차 줄에 든 종류들(정기·정밀·진단 차례) — 동별 종류가 섞이면 둘 이상."""
    got = {r.get("kind") if r.get("kind") in KINDS else "정기"} | {p["kind"] for p in r.get("parts") or [] if p.get("kind") in KINDS}
    return [k for k in KINDS if k in got]


def amount_for(rounds: list | None, year: int, half: str, name: str | None = None) -> int | None:
    """그 반기 회차 금액(원) — 동별 금액이 있으면 그 동 것(이름은 띄어쓰기 무시·포함까지), 없거나 못 찾으면 None.
    결과표 점검금액·FMS 동별 금액·대가내역서가 같은 값을 쓰게(2026-10-15 민재형)."""
    r = round_of(rounds, year, half)
    if r is None:
        return None
    parts = r.get("parts") or []
    if not parts:
        return int(r.get("amount") or 0) or None
    if not name:
        return None
    hit = find_part(parts, name)
    return int(hit["amount"]) if hit and hit.get("amount") else None


def part_amount(r: dict, name: str) -> int | None:
    """그 회차의 그 동 금액(동별 금액이 없거나 그 동이 없으면 None)."""
    for p in r.get("parts") or []:
        if p.get("name") == name:
            return int(p.get("amount") or 0)
    return None


def kind_for(rounds: list | None, unit: dict | None, open_ended: bool, year: int, half: str, name: str | None = None) -> str | None:
    """그 반기의 회차 종류 — 회차 줄에 있으면 그것(name을 주면 그 동의 종류, 10/31), 끝 없는 계약이면 매 반기 종류, 모르면 None(화면은 정기)."""
    for r in rounds or []:
        if r.get("year") == year and r.get("half") == half and r.get("kind") in KINDS:
            return part_kind(r, name) if name else r["kind"]
    if open_ended and unit and unit.get("kind") in KINDS:
        return unit["kind"]
    return None


def kinds_of(rounds: list | None, unit: dict | None, open_ended: bool) -> str:
    """회차 줄에 든 종류를 정기·정밀·진단 차례로 "·"로 — "정기" | "정밀" | "정기·정밀" | "진단" | "정기·진단" | "정밀·진단" | "정기·정밀·진단"(없으면 정기)."""
    got = {r.get("kind") for r in (rounds or []) if r.get("kind") in KINDS} | {p["kind"] for r in (rounds or []) for p in r.get("parts") or [] if p.get("kind") in KINDS}
    if open_ended and unit and unit.get("kind") in KINDS:
        got.add(unit["kind"])
    return "·".join(k for k in KINDS if k in got) or "정기"


def kind_word(k: str) -> str:
    """"정기안전점검" · "정기·정밀안전점검" · "정밀안전진단" · "정기안전점검·정밀안전진단" · "정기·정밀안전점검·정밀안전진단"."""
    pts = [x for x in k.split("·") if x and x != "진단"]
    head = f"{'·'.join(pts)}안전점검" if pts else ""
    return "·".join(x for x in (head, "정밀안전진단" if "진단" in k.split("·") else "") if x)


def total(rounds: list | None) -> int:
    return sum(int(r.get("amount") or 0) for r in rounds or [])


def money(n: int | None, vat: bool = True) -> str:
    """"금 오십오만원정 (￦550,000 / VAT포함)" — 견본 모양. vat=False면 "/ VAT포함"을 뺌(회차가 여럿일 때 줄마다 — 칸 폭을 넘어 줄바꿈되어서, 총합 줄에만)."""
    from server.contract_docs.build import korean_amount

    n = int(n or 0)
    tail = " / VAT포함" if vat else ""
    return f"금 {korean_amount(n)}원정 (￦{n:,}{tail})" if n else f"금        원정 (￦          {tail})"


def amount_lines(rounds: list | None, unit: dict | None, open_ended: bool) -> list[str]:
    if open_ended:
        u = unit or {}
        return [f"매 반기({u.get('kind') or '정기'}) : {money(u.get('amount'))}"]
    rows = sorted(rounds or [], key=lambda r: (int(r.get("year") or 0), seasons.order(r.get("half"))))
    out = []
    for r in rows:
        mixed = len(round_kinds(r)) > 1  # 동마다 종류가 다르면 줄 종류를 "정기·진단"으로, 동별 줄에 종류를 붙임(10/31)
        out.append(f"{r.get('year')}년 {r.get('half')}({'·'.join(round_kinds(r)) if mixed else (r.get('kind') or '정기')}) : {money(r.get('amount'), vat=len(rows) == 1)}")
        if r.get("parts"):  # 묶음 계약 — 동별 금액을 바로 아래 줄에(대가내역서와 같은 금액)
            out.append("    (" + " · ".join(f"{p['name']}{'(' + part_kind(r, p['name']) + ')' if mixed else ''} ￦{int(p['amount']):,}" for p in r["parts"]) + ")")
    if len(rows) > 1:
        out.append(f"총 합 : {money(total(rows))}")
    return out or [money(None)]


def years_text(rounds: list | None, start: datetime.date | None, open_ended: bool) -> str:
    ys = sorted({int(r["year"]) for r in rounds or [] if str(r.get("year") or "").isdigit()})
    if open_ended:
        y = start.year if start else (ys[0] if ys else datetime.date.today().year)
        return f"{y}년~"
    if not ys:
        return f"{start.year}년" if start else ""
    return f"{ys[0]}년" if ys[0] == ys[-1] else f"{ys[0]}~{ys[-1]}년"


def default_title(c) -> str:
    """"청천영진아파트 2026~2027년 정기·정밀안전점검" · 내진 = "○○초등학교 교사동 내진성능평가 용역"."""
    if is_seismic(c):
        return " ".join(x for x in (c.facility_name or c.client, f"{SEISMIC_WORD} 용역") if x)
    k = kinds_of(c.rounds, c.unit, c.open_ended)
    return " ".join(x for x in (c.facility_name or c.client, years_text(c.rounds, c.start_date, c.open_ended), kind_word(k)) if x)


def default_doc_no(day: datetime.date | None) -> str:
    """민간 문서번호 = KFSC-연도-월일(사용자 10/12 — 계약번호가 없으니 연도·월일까지만, 견본 KFSC-26-0504-01에서 순번을 뺀 모양)."""
    d = day or datetime.date.today()
    return f"KFSC-{d:%y}-{d:%m%d}"


def period_text(start: datetime.date | None, end: datetime.date | None, open_ended: bool) -> str:
    s = f"{start:%Y. %m. %d.}" if start else "    .   .   ."
    if open_ended:
        return f"{s}  ～ 계약 해지 시까지"
    return f"{s}  ～ {end:%Y. %m. %d.}" if end else f"{s}  ～     .   .   ."


def purpose(k: str, rounds: list | None) -> str:
    """제1조(목적) — 회차 줄이 연 3회(해빙기·우기·동절기, D·E등급 — 10/16)면 "년2회 상반기와 하반기"를 "년3회 해빙기·우기·동절기"로."""
    pts = "·".join(x for x in k.split("·") if x != "진단")
    text = PURPOSE.get(pts, "") if pts else ""
    if "진단" in k.split("·"):  # 정밀안전진단 — 혼자면 진단 목적, 섞이면 점검 목적 뒤에 "아울러 …"(10/20)
        text = f"{text} {DIAG_ALSO}" if text else DIAG_PURPOSE
    if any(seasons.is_season((r or {}).get("half")) for r in rounds or []):
        text = text.replace("년2회 상반기와 하반기", "년3회 해빙기·우기·동절기")
    return text


def values(c) -> dict[str, str]:
    """계약(SitokDocContract) → 자리표시 값. 내진 = 종류 "내진성능평가", 계약금액 한 줄(계약금액 칸), 목적 SEISMIC_PURPOSE."""
    if is_seismic(c):
        return {
            "문서번호": c.doc_no or default_doc_no(c.contract_date),
            "종류": SEISMIC_WORD, "시설물명": c.facility_name or "", "관리주체": c.client or "", "대표자": c.client_rep or "대 표 자",
            "계약건명": c.title or default_title(c), "계약금액": money(c.amount),
            "계약보증액": c.guarantee or "-", "지체상금율": c.delay_rate or "-", "계약기간": period_text(c.start_date, c.end_date, False),
            "위치": c.location or "", "제원": c.spec or "", "계약일": f"{c.contract_date:%Y. %m. %d.}" if c.contract_date else "", "목적": SEISMIC_PURPOSE,
        }
    k = kinds_of(c.rounds, c.unit, c.open_ended)
    return {
        "문서번호": c.doc_no or default_doc_no(c.contract_date),
        "종류": kind_word(k), "시설물명": c.facility_name or "", "관리주체": c.client or "", "대표자": c.client_rep or "대 표 자",
        "계약건명": c.title or default_title(c), "계약금액": "\n".join(amount_lines(c.rounds, c.unit, c.open_ended)),
        "계약보증액": c.guarantee or "-", "지체상금율": c.delay_rate or "-", "계약기간": period_text(c.start_date, c.end_date, c.open_ended),
        "위치": c.location or "", "제원": c.spec or "", "계약일": f"{c.contract_date:%Y. %m. %d.}" if c.contract_date else "", "목적": purpose(k, c.rounds),
    }


# ---------- 템플릿 만들기(견본 → 자리표시) ----------

def _tops(root) -> list:
    return [p for p in root if p.tag == f"{{{HP}}}p"]


def _replace_in(p, old: str, new: str) -> bool:
    """문단 글자 조각 안에서 바꾸기(조각 하나 안에 있을 때만 — 글자 모양 그대로)."""
    hit = False
    for t in p.iter(T):
        for pc in rb._pieces(t):
            if old in pc.text:
                pc.text = pc.text.replace(old, new)
                hit = True
    return hit


def _cell_paras(tc) -> list:
    return [q for q in tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is tc]


def make_template(sample_hwpx: bytes) -> bytes:
    """견본 정밀안전점검 계약서(청천영진아파트, hwpx) → 자리표시 템플릿. 바꾼 자리가 하나라도 없으면 ValueError(견본이 달라짐)."""
    zin = zipfile.ZipFile(io.BytesIO(sample_hwpx))
    sec = "Contents/section0.xml"
    root = etree.fromstring(zin.read(sec))
    tops = _tops(root)
    done: set[str] = set()

    def text_of(p):
        return rb._top_text(p)

    for p in tops:
        t = text_of(p)
        tbl = next(p.iter(f"{{{HP}}}tbl"), None)
        if tbl is not None and "KFSC" in rb._cell_text(rb._cells(tbl).get((0, 1), tbl)):
            rb._set_lines(rb._cells(tbl)[(0, 1)], ["{문서번호}"])
            done.add("문서번호")
        elif tbl is not None and "계 약 건 명" in "".join(rb._cell_text(x) for x in rb._cells(tbl).values()):
            c = rb._cells(tbl)
            rows = {rb._cell_text(c[(r, 1)]).replace(" ", ""): r for (r, k) in c if k == 1 and (r, 2) in c}
            for label, token in (("관리주체", "관리주체"), ("계약건명", "계약건명"), ("계약금액", "계약금액"), ("계약보증액", "계약보증액"),
                                 ("지체상금율", "지체상금율"), ("계약기간", "계약기간"), ("위치", "위치")):
                if label in rows:
                    rb._set_lines(c[(rows[label], 2)], [f"{{{token}}}"])
                    done.add(token)
            title = c.get((0, 0))
            if title is not None and "표준계약서" in rb._cell_text(title):
                rb._set_lines(title, ["{종류} 표준계약서"])
            for tc in c.values():
                paras = _cell_paras(tc)
                tx = rb._cell_text(tc)
                if "기명날인" in tx:  # 계약일 줄
                    for q in paras:
                        if re.match(r"\s*\d{4}\.", "".join(rb._full(x) for x in q.iter(T))):
                            rb._set_para(q, "{계약일}", in_table=True)
                            done.add("계약일")
                elif tx.startswith("“갑”") and len(paras) >= 3:  # 서명 칸 — 둘째 줄 관리주체, 셋째 줄 대표자
                    rb._set_para(paras[1], "{관리주체}", in_table=True)
                    rb._set_para(paras[2], "{대표자}  (인)", in_table=True)
                    done.add("대표자")
        elif t.endswith("계약서") and len(t) < 20:
            rb._set_para(p, "{종류} 계약서")
            done.add("종류")
        elif t.startswith("【"):
            rb._set_para(p, "【  {시설물명}  】")
            done.add("시설물명")
        elif "관리주체인" in t:  # 견본: [" … 따라", " 관리주체인 ", "청천영진아파트(위탁…)", "(이하 “갑”…) 정밀안전점검의 실시자인 ", …] — 관리주체 바로 뒤 조각이 이름
            ts = list(p.iter(T))
            i = next((k for k, x in enumerate(ts) if "관리주체인" in rb._full(x)), None)
            if i is not None and i + 1 < len(ts) and "(이하" not in rb._full(ts[i + 1]):
                rb._clear(ts[i + 1], "{관리주체}")
            _replace_in(p, "정밀안전점검", "{종류}")
        elif t.startswith("제1조(목적)"):
            rb._set_para(p, "제1조(목적) {목적}")
            done.add("목적")
        elif t.startswith("제5조(대가의 지급"):
            rb._set_para(p, "제5조(대가의 지급 등) {종류}대가 및 선금의 지급은 “을”의 각 회차 점검의 종료 및 FMS 등재 완료 후 30일 이내에 지급하여야 한다.")
        elif re.match(r"\d\.\s*(시설물명|위\s*치|제\s*원)", t):
            ts = list(p.iter(T))
            token = "시설물명" if "시설물명" in t else "위치" if "위" in t[:6] else "제원"
            rb._clear(ts[-1], f" {{{token}}}")
            done.add(token)
        else:
            _replace_in(p, "정밀안전점검", "{종류}")
            _replace_in(p, "정밀점검", "{종류}")
    missing = [x for x in ("문서번호", "종류", "시설물명", "관리주체", "대표자", "계약건명", "계약금액", "계약기간", "위치", "제원", "계약일", "목적") if x not in done]
    if missing:
        raise ValueError("견본에서 자리를 못 찾음: " + ", ".join(missing))
    return _write(zin, {sec: root})


def _write(zin: zipfile.ZipFile, roots: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in roots:
                root = roots[info.filename]
                for el in list(root.iter(f"{{{HP}}}linesegarray")):
                    el.getparent().remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename in ("Preview/PrvText.txt", "Preview/PrvImage.png"):
                continue
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    return out.getvalue()


def check(hwpx: bytes) -> list[str]:
    """올린(고친) 템플릿에 꼭 있어야 할 자리표시 중 없는 것."""
    zin = zipfile.ZipFile(io.BytesIO(hwpx))
    text = "".join(zin.read(n).decode("utf-8", "replace") for n in rb._sections(zin))
    return [t for t in ("문서번호", "종류", "시설물명", "관리주체", "계약건명", "계약금액", "계약기간", "위치") if "{" + t + "}" not in text]


# ---------- 채우기 ----------

def build(template: bytes, vals: dict[str, str]) -> bytes:
    """템플릿 자리표시를 값으로 — 계약금액(여러 줄)은 그 칸을 줄마다 문단으로, 제원이 비면 그 줄을 지움."""
    zin = zipfile.ZipFile(io.BytesIO(template))
    roots = {}
    for n in rb._sections(zin):
        root = etree.fromstring(zin.read(n))
        for tc in list(root.iter(f"{{{HP}}}tc")):
            if "{계약금액}" in rb._cell_text(tc):
                rb._set_lines(tc, vals.get("계약금액", "").split("\n"))
        if not vals.get("제원"):
            for p in list(_tops(root)):
                if "{제원}" in rb._top_text(p):
                    p.getparent().remove(p)
        for t in root.iter(T):
            for pc in rb._pieces(t):
                if "{" in (pc.text or ""):
                    pc.text = re.sub(r"\{(" + "|".join(TOKENS) + r")\}", lambda m: vals.get(m[1], ""), pc.text)
        roots[n] = root
    return _write(zin, roots)


# ---------- AI 읽기 — 사업자등록증·이미 만든 민간 계약서(사용자 10/12 "이미 만들어 놓은 계약 건 올릴 수 있게") ----------

BIZREG_PROMPT = """사업자등록증입니다. JSON 객체 하나로만 답하세요(설명 없이, 없으면 ""):
{"name": "상호(법인명)", "rep": "대표자 성명", "biz_no": "등록번호(000-00-00000)", "address": "사업장 소재지"}"""

EXISTING_PROMPT = """시설물 안전점검(정기안전점검·정밀안전점검) 민간 계약서입니다(우리 회사 (주)한국미래안전이 "을"/계약상대자). 표와 본문에서 읽어
JSON 객체 하나로만 답하세요(설명 없이, 없으면 "" 또는 null, 날짜는 YYYY-MM-DD):
{"doc_no": "문서번호(예 KFSC-26-0504-01)", "client": "관리주체(갑) 이름 그대로", "client_rep": "서명 칸 갑의 대표자 줄(예: 관리사무소장 김춘화)",
 "facility_name": "시설물명(표지 【 】 또는 제2조)", "location": "위치", "spec": "제원(예 연면적 19,071.7m²)", "title": "계약건명",
 "rounds": [{"year": 연도, "half": "상반기|하반기|해빙기|우기|동절기", "kind": "정기|정밀", "amount": 금액(원, 정수)}] — 계약금액 칸의 회차마다(총합 줄은 빼기, 반기 표시가 없으면 계약기간으로 판단, 연 3회 계약의 "해빙기(정기)·우기(정기)·동절기(정기)"는 half에 그 시기 그대로),
 "open_ended": 계약기간이 "계약 해지 시까지"처럼 끝이 없으면 true, "unit": {"kind": "정기|정밀", "amount": 매 반기 금액} — 끝이 없을 때만,
 "guarantee": "계약보증액(없으면 -)", "delay_rate": "지체상금율(없으면 -)", "contract_date": "계약일", "start_date": "계약기간 시작", "end_date": "계약기간 끝"}"""


SEISMIC_EXISTING_PROMPT = """건물 내진성능평가 용역 민간 계약서입니다(우리 회사 (주)한국미래안전이 "을"/계약상대자). 표와 본문에서 읽어
JSON 객체 하나로만 답하세요(설명 없이, 없으면 "" 또는 null, 날짜는 YYYY-MM-DD):
{"doc_no": "문서번호(예 KFSC-26-0504)", "client": "관리주체(갑) 이름 그대로", "client_rep": "서명 칸 갑의 대표자 줄",
 "facility_name": "건물명(표지 【 】 또는 제2조)", "location": "위치", "spec": "제원(예 연면적 3,120.5m²)", "title": "계약건명",
 "amount": 계약금액(원, 정수 — VAT포함 총액), "guarantee": "계약보증액(없으면 -)", "delay_rate": "지체상금율(없으면 -)",
 "contract_date": "계약일", "start_date": "계약기간 시작", "end_date": "계약기간 끝"}"""


def _pdf_of(data: bytes, filename: str) -> Path:
    """올린 파일(PDF·그림·한글·워드) → 임시 PDF 경로(AI가 읽게)."""
    import tempfile

    from server.contract_docs.attachments import to_pdf_bytes

    tmp = Path(tempfile.mkdtemp()) / "doc.pdf"
    tmp.write_bytes(to_pdf_bytes(data, filename))
    return tmp


def read_bizreg(data: bytes, filename: str, company_id: int) -> dict:
    from server.sitok.reader import _ask, _str

    d = _ask(_pdf_of(data, filename), BIZREG_PROMPT, company_id)
    return {"client": _str(d.get("name")), "client_rep": f"대표자 {_str(d.get('rep'))}" if _str(d.get("rep")) else "",
            "client_biz_no": _str(d.get("biz_no")), "client_address": _str(d.get("address"))}


def read_existing(data: bytes, filename: str, company_id: int, field: str = "") -> dict:
    """이미 만든(날인한) 민간 계약서 → 계약 칸. 내진(field "내진") = 회차 줄 없이 계약금액 한 칸."""
    from server.sitok.reader import _ask, _date, _int, _str

    if field == SEISMIC:
        d = _ask(_pdf_of(data, filename), SEISMIC_EXISTING_PROMPT, company_id)
        return {"doc_no": _str(d.get("doc_no")), "client": _str(d.get("client")), "client_rep": _str(d.get("client_rep")),
                "facility_name": _str(d.get("facility_name")), "location": _str(d.get("location")), "spec": _str(d.get("spec")), "title": _str(d.get("title")),
                "amount": _int(d.get("amount")) or None, "guarantee": _str(d.get("guarantee")) or "-", "delay_rate": _str(d.get("delay_rate")) or "-",
                "contract_date": _date(d.get("contract_date")), "start_date": _date(d.get("start_date")), "end_date": _date(d.get("end_date"))}
    d = _ask(_pdf_of(data, filename), EXISTING_PROMPT, company_id)
    rounds = []
    for r in d.get("rounds") or []:
        y, amt = _int(r.get("year")), _int(r.get("amount"))
        if y and 0 < y < 100:  # "26년" → 2026
            y += 2000
        if y and r.get("half") in HALVES:
            rounds.append({"year": y, "half": r["half"], "kind": r.get("kind") if r.get("kind") in KINDS else "정기", "amount": amt or 0})
    unit = d.get("unit") or None
    if unit:
        unit = {"kind": unit.get("kind") if unit.get("kind") in KINDS else "정기", "amount": _int(unit.get("amount")) or 0}
    return {"doc_no": _str(d.get("doc_no")), "client": _str(d.get("client")), "client_rep": _str(d.get("client_rep")),
            "facility_name": _str(d.get("facility_name")), "location": _str(d.get("location")), "spec": _str(d.get("spec")), "title": _str(d.get("title")),
            "rounds": rounds, "open_ended": bool(d.get("open_ended")), "unit": unit if d.get("open_ended") else None,
            "guarantee": _str(d.get("guarantee")) or "-", "delay_rate": _str(d.get("delay_rate")) or "-",
            "contract_date": _date(d.get("contract_date")), "start_date": _date(d.get("start_date")), "end_date": _date(d.get("end_date"))}


def comma_k(text: str) -> str:
    """점검금액(천원) 글 — 숫자만이면 천 단위 쉼표(3441 → 3,441, 3441.5 → 3,441.5), 아니면 그대로(10/26 민재형 "결과표의 금액은 천 단위 쉼표" —
    회차에 직접 넣은 동별 금액은 넣은 글 그대로 들어갔음)."""
    s = (text or "").strip()
    raw = s.replace(",", "")
    whole, dot, frac = raw.partition(".")
    if whole.isdigit() and (not dot or frac.isdigit()):
        return f"{int(whole):,}" + (f".{frac}" if dot else "")
    return s

