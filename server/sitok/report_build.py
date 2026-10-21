"""시특법 정기안전점검 보고서 만들기(2026-10-10 4단계) — "지난 회차 보고서(한글 hwpx)를 틀로 새 회차" = 지금 손으로 하는 방식(복사 → 바뀐 값 고치기) 자동.

1) read_old(지난 hwpx) — 결과표(가. 일반현황 표)에서 예전 값(용역명·점검기간·관리주체·대표자·준공일·점검금액·위치·규모·기술자)과 표지의 연도·반기·월을 읽는다.
2) build(지난 hwpx, old, new, 새 hwpx) — 본문 글자 칸(<hp:t>)마다 예전 값을 새 값으로 바꾼다. 결과표 칸처럼 칸 전체가 그 값인 곳은 칸째로,
   연도·반기·점검기간처럼 문장 속에 들어간 것은 그 부분만. 줄 배치 캐시(linesegarray)는 지움(글자를 바꾸면 한글이 "변조"로 막을 수 있음 —
   server/contract_docs/inspection.py와 같은 이유), 미리보기 글자(Preview/PrvText.txt)도 새로.
결함·외관조사·종합결론 등 내용은 지난 회차 그대로 두고(5·6단계에서 현장 조사·AI로), 여기선 회차가 바뀌며 달라지는 값만 바꾼다.
10/12 판 다시 잡기: 틀(src)은 늘 회사 원본(server/sitok/master.py prepare — 종별로 손질), old = 원본(광숭초) 값. 전회차 보고서에서는
read_history·read_survey·read_texts·read_overview·read_eval_items·read_facility_items로 데이터만 읽어 Extras.base(_base_reset)·Extras.ai로 넣는다.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import random
import re
import sys
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from server.sitok.borders import Borders

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
CORE = "http://www.hancom.co.kr/hwpml/2011/core"
T = f"{{{HP}}}t"


@dataclass
class Values:
    """보고서 한 회차의 바뀌는 값. 날짜는 date, 금액은 천원 단위 글자(결과표 "점검금액(천원)")."""
    name: str = ""            # 시설물명
    title: str = ""           # 용역명(결과표·참여기술자 명단·사전검토 과업명)
    year: int = 0
    half: str = ""            # 상반기 / 하반기
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    report_month: tuple[int, int] | None = None  # 표지 "2026. 04."
    owner: str = ""           # 관리주체명
    rep: str = ""             # 대표자
    completion: datetime.date | None = None
    amount_k: str = ""        # 점검금액(천원)
    address: str = ""
    scale: str = ""           # 시설물 규모 칸 글자 전체
    task_end: datetime.date | None = None  # 과업지시서 "용역기간은 ○○까지"
    persons: list[tuple[str, str]] = field(default_factory=list)  # [(이름, 결과표 기술등급)] 책임 → 참여 순
    grade: str = ""           # 결과표 안전등급(보통·B 등) — 다음 회차 1.2.6 기실시 점검결과에 씀
    findings: list[str] = field(default_factory=list)  # 결과표 "점검 주요결과" 글머리들 — 다음 회차 1.2.6에 씀


@dataclass
class Extras:
    """설정에서 넣는 것(4-2, 2026-10-10). images: (종류, 순번) → 그림 파일 — 종류 sitok_reg/sitok_edu/sitok_license, 순번 = 앞부분 수료증은
    기술자 순서(0 = 책임), 부록은 "chief". equipment: [(이름, 형식, 용도, [사진 경로])] 표 순서대로. positions: {이름: 직위} 참여기술자 명단."""
    images: dict = field(default_factory=dict)
    equipment: list = field(default_factory=list)
    positions: dict = field(default_factory=dict)
    history: bool = True  # 1.2.6 기실시 점검결과에 틀(= 직전 회차) 한 칸 추가
    summary: list = field(default_factory=list)  # 9쪽 요약표 줄 [(층, 구분, 부재, [점검결과], [조치])] — 비면 지난 표 그대로
    priority: list = field(default_factory=list)  # 보수물량 및 우선순위 줄 [(층, 결함유형, 손상내용, 적용공법, 물량, 단위, 우선순위)]
    cost: tuple | None = None  # 개략공사비 ([(구분, 내용, 방안, 물량, 단위, 단가, 금액)], 직접공사비 합계)
    ai: dict | None = None  # 6단계 AI 초안(점검자가 고친 것) — server/sitok/ai_draft.py 키(critical·findings·sections·conclusion·grade …)
    template: str = "2종"  # 등급 표기(2종 낱말·3종 글자)
    rep_photos: dict = field(default_factory=dict)  # 1.3 대표사진 {항목 키: [(사진 경로, 설명)]} — 공중이용·기타는 아래 parts(현장 화면 탭)로
    has_drawings: bool = True  # 첨부 도면이 있는지(10/12) — 없으면 1.2.9 "-후면첨부-"를 "-"로(server/sitok/drawings.py)
    seismic: dict | None = None  # 학교 부록 내진보강시설 육안 점검표(10/19 형 B5) — server/sitok/good.py norm()["seismic"]
    seismic_base: str = ""  # 그 사진 폴더(회차 폴더)
    parts: dict | None = None  # 1.3 6)·7) 사진 표(10/12) {"public": [(항목 이름, 사진 | None)] × 4, "other": [(설명, 사진 | None)] × 4} — server/sitok/parts.py
    blank: str = ""  # 남는 사진 칸에 넣을 흰 그림
    survey: dict | None = None  # 면담·변경사항 {repairs, changes} — 1.2.7·1.2.8
    base: dict | None = None  # 회사 기본 틀로 시작(처음 맡는 시설물) — {map, cover, name, year, floors, area, structure, grade, use}: 틀 시설물 고유 내용을 비우거나 새로
    overview: list = field(default_factory=list)  # 전경사진 [(경로, 제목)] — 10쪽 위치도 아래 첫 장 + 11쪽 6장씩(비면 지난 회차 그대로)
    notes: list = field(default_factory=list)  # 못 한 것 안내


class _Piece:
    """글자 조각 — <hp:t>의 text, 또는 그 안 자식(줄바꿈·탭 등) 뒤의 tail. 한글은 한 글자 칸 안에 줄바꿈이 끼면 뒤 글자를 tail로
    보관한다(10/10 광숭초 결과표 "용역명" 세 줄·안전등급 "B"). 읽기·바꾸기를 모두 조각 단위로 한다."""
    __slots__ = ("el", "attr", "t")

    def __init__(self, el, attr, t):
        self.el, self.attr, self.t = el, attr, t

    @property
    def text(self) -> str:
        return getattr(self.el, self.attr) or ""

    @text.setter
    def text(self, v: str) -> None:
        setattr(self.el, self.attr, v)


def _pieces(t) -> list[_Piece]:
    out = [_Piece(t, "text", t)]
    out += [_Piece(c, "tail", t) for c in t]
    return out


def _full(t) -> str:
    """글자 칸 전체(줄바꿈은 줄바꿈으로)."""
    s = t.text or ""
    for c in t:
        s += ("\n" if c.tag.endswith("lineBreak") else "") + (c.tail or "")
    return s


def _clear(t, text: str) -> None:
    """글자 칸을 text 하나로(줄바꿈 등 자식은 지움)."""
    for c in list(t):
        t.remove(c)
    t.text = text


def _cell_text(tc) -> str:
    return "\n".join("".join(_full(t) for t in p.iter(T)) for p in tc.iter(f"{{{HP}}}p")).strip()


def _cells(tbl) -> dict[tuple[int, int], object]:
    out = {}
    for tc in tbl.iter(f"{{{HP}}}tc"):
        if next((a for a in tc.iterancestors(f"{{{HP}}}tbl")), None) is not tbl:
            continue
        a = tc.find(f"{{{HP}}}cellAddr")
        out[(int(a.get("rowAddr")), int(a.get("colAddr")))] = tc
    return out


def _find_result_table(roots) -> dict | None:
    """결과표 = "용 역 명"·"점검기간"·"관리주체명" 이름칸이 있는 표(칸 위치는 보고서마다 다름 — 숭의 견본은 이름칸이 두 칸)."""
    for root in roots:
        for tbl in root.iter(f"{{{HP}}}tbl"):
            cells = _cells(tbl)
            texts = {re.sub(r"\s", "", _cell_text(v)) for v in cells.values()}
            if {"용역명", "점검기간", "관리주체명"} <= texts:
                return cells
    return None


def _n(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def _span(tc, kind: str) -> int:
    return int(tc.find(f"{{{HP}}}cellSpan").get(kind))


def _label(cells: dict, *names: str, starts: bool = False) -> tuple[int, int] | None:
    """이름칸 위치(띄어쓰기·줄바꿈 무시) — starts면 그 글로 시작하는 칸."""
    for k in sorted(cells):
        t = _n(_cell_text(cells[k]))
        if any(t.startswith(x) if starts else t == x for x in names):
            return k
    return None


def _row_right(cells: dict, r: int, mincol: int):
    """줄 r에서 mincol 칸부터 가장 왼쪽 칸(값 칸)."""
    cols = sorted(c for (rr, c) in cells if rr == r and c >= mincol)
    return cells[(r, cols[0])] if cols else None


def _value(cells: dict, *names: str, starts: bool = False) -> str:
    """이름칸 오른쪽 값 글."""
    k = _label(cells, *names, starts=starts)
    tc = _row_right(cells, k[0], k[1] + _span(cells[k], "colSpan")) if k else None
    return _cell_text(tc) if tc is not None else ""


def _label_rows(cells: dict, *names: str, starts: bool = False) -> list:
    """이름칸이 세로로 합친 줄마다 값 칸 — "점검 주요결과"(우리 = 한 칸, 숭의 견본 = 6줄)."""
    k = _label(cells, *names, starts=starts)
    if not k:
        return []
    mincol = k[1] + _span(cells[k], "colSpan")
    return [tc for r in range(k[0], k[0] + _span(cells[k], "rowSpan")) if (tc := _row_right(cells, r, mincol)) is not None]


def _d(text: str) -> datetime.date | None:
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text or "")
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3])) if m else None
    except ValueError:
        return None


def _sections(z: zipfile.ZipFile) -> list[str]:
    return sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))


def read_old(hwpx: Path) -> Values:
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    cells = _find_result_table(roots)
    if cells is None:
        raise ValueError("지난 보고서에서 '정기안전점검 결과표'(가. 일반현황 표)를 찾지 못했습니다 — 정기안전점검 보고서 한글 파일인지 확인하세요.")
    # 이름칸 → 오른쪽 값(10/12 — 칸 위치는 보고서마다 다름)
    v = Values(title=" ".join(_value(cells, "용역명").split()), owner=_value(cells, "관리주체명"), rep=_value(cells, "대표자"),
               amount_k=_value(cells, "점검금액", starts=True), address=_value(cells, "시설물위치"), scale=_value(cells, "시설물규모"))
    parts = re.split(r"[~∼]", _value(cells, "점검기간"))
    v.period_start, v.period_end = _d(parts[0]), _d(parts[1]) if len(parts) > 1 else None
    v.completion = _d(_value(cells, "준공일"))
    v.grade = _value(cells, "안전등급")
    for tc in _label_rows(cells, "점검주요결과"):  # 점검 주요결과 칸들
        txt = " ".join(x.strip() for x in _cell_text(tc).split("\n") if x.strip()).lstrip(".").strip()
        if txt:
            v.findings.append(txt)
    m = re.search(r"\[(.+?)\]", v.title)
    v.name = m[1].strip() if m else ""
    m = re.search(r"(\d{4})\s*년\s*(?:도\s*)?(상반기|하반기|해빙기|우기|동절기)", v.title)  # 연 3회(10/16)
    if m:
        v.year, v.half = int(m[1]), m[2]
    # 기술자: "다. 책임(참여)기술자 현황" 아래 줄들(구분 | 성명 | 과업 참여기간 | 기술등급) — 줄 첫 칸이 "○○기술자"
    for r in sorted({k[0] for k in cells}):
        row = [cells[k] for k in sorted(k for k in cells if k[0] == r)]
        role = _n(_cell_text(row[0]))
        if role.endswith("기술자") and role != "구분" and len(row) >= 3:
            name = _n(_cell_text(row[1]))
            if name:
                v.persons.append((name, _cell_text(row[-1])))
    # 표지 "2026. 04." — 첫 구역에서 연도. 월 모양
    for t in roots[0].iter(T):
        m = re.fullmatch(r"\s*(\d{4})\.\s*(\d{1,2})\.\s*", _full(t))
        if m:
            v.report_month = (int(m[1]), int(m[2]))
            break
    if not v.name:  # 용역명에 [시설물명]이 없으면 표지 "○○에 대한"
        for t in roots[0].iter(T):
            m = re.fullmatch(r"\s*(.+?)에\s*대한\s*", _full(t))
            if m:
                v.name = m[1].strip()
                break
    for root in roots:  # 과업지시서 "용역기간은 2026년 06월 30일 까지" — 한 문장이 글자 칸 여러 개로 나뉘어 있음
        for p in root.iter(f"{{{HP}}}p"):
            m = re.search(r"용역기간은\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)", "".join(_full(t) for t in p.iter(T)))
            if m:
                v.task_end = _d(m[1])
    return v


def _spaced(s: str) -> str:
    return " ".join(s.replace(" ", ""))


def _date_forms(d: datetime.date) -> list[tuple[str, callable]]:
    """보고서에 나오는 날짜 모양들 — (예전 글자, 새 날짜 → 같은 모양 글자)."""
    return [
        (f"{d:%Y.%m.%d}", lambda n: f"{n:%Y.%m.%d}"),
        (f"{d.year}년 {d.month:02d}월 {d.day:02d}일", lambda n: f"{n.year}년 {n.month:02d}월 {n.day:02d}일"),
        (f"{d.year}년 {d.month}월 {d.day}일", lambda n: f"{n.year}년 {n.month}월 {n.day}일"),
        (f"{d:%Y-%m-%d}", lambda n: f"{n:%Y-%m-%d}"),
    ]


def replacements(old: Values, new: Values) -> tuple[dict[str, str], list, set[str]]:
    """(칸 전체가 같을 때만 바꿀 것 {예전: 새}, 글자 속 어디든 바꿀 것 [(예전, 새)] — 긴 것부터, 맨 뒤에 (정규식, 바꿀 글),
    앞부분(첫 구역: 표지·책등·제출문·결과표·요약표)에서만 쓸 예전 값들).
    "상반기"·"2026"처럼 짧은 낱말 칸은 앞부분에서만 — 본문엔 보수·보강 이력처럼 과거 기록이 있어서(10/10)."""
    whole: dict[str, str] = {}
    parts: list[tuple[str, str]] = []
    front: set[str] = set()
    between: list = []

    def both(o, n):
        if o and n is not None and o != n:
            parts.append((o, n))

    def cell(o, n):
        if o and n is not None and o != n:
            whole[o] = n

    both(old.title, new.title)
    both(old.owner, new.owner)
    both(old.name, new.name)
    cell(old.rep, new.rep)
    cell(old.amount_k, new.amount_k)
    cell(old.address, new.address)
    cell(old.scale, new.scale)
    if old.completion:  # 준공일을 모르면 "-"(원본·다른 시설물 날짜가 남지 않게 — 10/12 관리대장 없는 법정 외 자체 점검)
        for o, f in _date_forms(old.completion):
            cell(o, f(new.completion) if new.completion else "-")
    for od, nd in ((old.period_start, new.period_start), (old.period_end, new.period_end), (old.task_end, new.task_end)):
        if od and nd and od != nd:
            for o, f in _date_forms(od):
                both(o, f(nd))
    if old.year and new.year and old.half and new.half and (old.year, old.half) != (new.year, new.half):
        for fmt in ("{y}년도 {h}", "{y}년 {h}", "{y}년도{h}", "{y}년{h}", "{y} {h}"):
            both(fmt.format(y=old.year, h=old.half), fmt.format(y=new.year, h=new.half))
        # 연도와 반기 사이에 이름이 낀 머리말 "2026년 광숭초등학교 상반기 제3종시설물 정기안전점검 용역"(10/10 광숭) — 정기·점검·용역이 뒤에 올 때만
        between.append((re.compile(rf"{old.year}(년도?\s+\S{{1,20}}\s+){old.half}(?=.*(정기|점검|용역))"), rf"{new.year}\g<1>{new.half}"))
        both(_spaced(old.half), _spaced(new.half))  # 책등 "상 반 기"
        both(old.half + "정기", new.half + "정기")
        cell(old.half, new.half)  # 표지 "상반기"만 따로 있는 칸
        front.add(old.half)
    if old.year and new.year and old.year != new.year:
        cell(str(old.year), str(new.year))
        front.add(str(old.year))
    if old.report_month and new.report_month and old.report_month != new.report_month:
        (oy, om), (ny, nm) = old.report_month, new.report_month
        both(f"{oy}. {om:02d}.", f"{ny}. {nm:02d}.")
        both(f"{oy}. {om:02d}", f"{ny}. {nm:02d}")
        both(f"{_spaced(str(oy))} . {om:02d}", f"{_spaced(str(ny))} . {nm:02d}")  # 책등 "2 0 2 6 . 04"
        both(f"{oy}.{om:02d}", f"{ny}.{nm:02d}")  # 세로글씨 책등(글자가 문단마다 따로) — 아래 _cross_runs가 이어 붙여 찾음
        for fmt in ("{y} 년 {m} 월", "{y}년 {m}월", "{y} 년 {m:02d} 월", "{y}년 {m:02d}월"):  # 제출문 날짜 "2026 년 4 월"
            both(fmt.format(y=oy, m=om), fmt.format(y=ny, m=nm))
    for (on, og), (nn, ng) in zip(old.persons, new.persons):
        if on != nn:
            both(_spaced(on), _spaced(nn))  # 결과표 "현 민 재"
            both(on, nn)
        cell(og, ng)
    parts.sort(key=lambda x: -len(x[0]))
    parts += between  # (정규식, 바꿀 글) — 일반 글자 바꾸기 뒤에
    return whole, parts, front


def _sub_parts(text: str, parts: list) -> str:
    """parts = [(예전 글, 새 글) 또는 (정규식, 바꿀 글)] 차례로."""
    for o, nw in parts:
        if isinstance(o, str):
            if o in text:
                text = text.replace(o, nw)
        else:
            text = o.sub(nw, text)
    return text


def _cross_runs(root, pairs: list[tuple[str, str]]) -> int:
    """글자 칸 여러 개에 걸쳐 나뉜 값 — 책등 "2","0","2","6"처럼(세로글씨는 글자마다 문단이 따로). 맨 바깥 문단 단위로 그 안의 글자 칸을
    차례로 이어 붙여 찾고, 글자 수가 같은 것만 글자 단위로 맞춰 바꿈(칸 모양은 그대로)."""
    n = 0
    for p in root.findall(f"{{{HP}}}p"):
        runs = [pc for t in p.iter(T) for pc in _pieces(t) if pc.text]
        if len(runs) < 2:
            continue
        joined = "".join(t.text for t in runs)
        for o, nw in pairs:
            if len(o) != len(nw) or o not in joined:
                continue
            owner = []  # 글자 위치 → (칸, 칸 안 위치)
            for t in runs:
                owner += [(t, i) for i in range(len(t.text))]
            start = 0
            while (k := joined.find(o, start)) >= 0:
                chars = {}
                for j, ch in enumerate(nw):
                    t, i = owner[k + j]
                    chars.setdefault(t, list(t.text))[i] = ch
                for t, lst in chars.items():
                    t.text = "".join(lst)
                joined = "".join(t.text for t in runs)
                start = k + len(o)
                n += 1
    return n


def _apply(root, whole: dict[str, str], parts: list[tuple[str, str]], front: set[str], is_front: bool) -> int:
    if not is_front:
        whole = {k: v for k, v in whole.items() if k not in front}
    n = 0
    for t in list(root.iter(T)):
        full = _full(t).strip()
        if len(t) and full in whole:  # 줄바꿈이 낀 칸 전체가 바꿀 값(결과표 시설물 규모 등)
            _clear(t, whole[full].replace("\n", " "))
            n += 1
            continue
        pcs = _pieces(t)
        if len(pcs) > 1:
            # 한 글자 칸이 형광펜·줄바꿈 표시로 조각났을 때(10/10 광숭 "2026.06."+형광펜 끝+"12") — 이어 붙여 먼저 바꿈.
            # 글자 수가 같으면 조각 경계를 지켜 글자 단위로, 다르면 첫 조각에 몰아 넣음(표시 위치만 앞으로 감)
            joined = "".join(pc.text for pc in pcs)
            out = whole.get(joined.strip(), None)
            out = joined.replace(joined.strip(), out) if out is not None else joined
            if out == joined:
                out = _sub_parts(out, parts)
            if out != joined:
                if len(out) == len(joined):
                    k = 0
                    for pc in pcs:
                        pc.text, k = out[k:k + len(pc.text)], k + len(pc.text)
                else:
                    pcs[0].text = out
                    for pc in pcs[1:]:
                        pc.text = ""
                n += 1
                continue
        for pc in pcs:
            s = pc.text
            if not s.strip():
                continue
            key = s.strip()
            if key in whole:
                pc.text = s.replace(key, whole[key])
                n += 1
                continue
            out = _sub_parts(s, parts)
            if out != s:
                pc.text = out
                n += 1
    # 칸 하나가 여러 줄(<hp:p> 여럿)로 나뉜 값(결과표 "형식 : … / 연면적 : …")은 칸째 비교
    for tc in root.iter(f"{{{HP}}}tc"):
        txt = _cell_text(tc)
        if "\n" in txt and txt in whole:
            ps = list(tc.iter(f"{{{HP}}}p"))
            ts = [t for t in ps[0].iter(T)]
            if ts:
                _clear(ts[0], whole[txt].replace("\n", " "))
                for t in ts[1:]:
                    _clear(t, "")
                for p in ps[1:]:
                    for t in p.iter(T):
                        _clear(t, "")
                n += 1
    # 나뉜 칸에 걸친 연도·반기(책등 등) — 앞부분에서만, 한 칸 안에서 못 바꾼 것만 남아 있으므로 글자 수가 같은 짧은 값만
    if is_front:
        n += _cross_runs(root, [(o, nw) for o, nw in parts if isinstance(o, str) and len(o) <= 8]
                         + [(o, nw) for o, nw in whole.items() if len(o) <= 4])
    return n


# ---------- 4-2: 설정 값 넣기·이력 추가 ----------

def _tbl_title(tbl) -> str:
    return "".join(t.text or "" for t in tbl.iter(T)).replace(" ", "")[:40]


def _doc_pics(root, is_front: bool) -> list[tuple[object, str, object]]:
    """서류 그림 자리 [(img 요소, 종류, 순번)] — 제목 글자가 든 표 안의 그림(등록증·수료증·책임기술자 자격)."""
    out = []
    edu = 0
    for pic in root.iter(f"{{{HP}}}pic"):
        tbl = next(pic.iterancestors(f"{{{HP}}}tbl"), None)
        img = pic.find(".//{http://www.hancom.co.kr/hwpml/2011/core}img")
        if tbl is None or img is None:
            continue
        title = _tbl_title(tbl)
        if "전문기관등록증" in title:
            out.append((img, "sitok_reg", None))
        elif "교육수료증" in title:
            out.append((img, "sitok_edu", edu if is_front else "chief"))
            edu += is_front
        elif "책임기술자자격" in title:
            out.append((img, "sitok_license", "chief"))
    return out


def _set_cell(tc, text: str) -> None:
    """칸 글자를 text 하나로 — 첫 문단 첫 글자 칸에 넣고 나머지 문단은 지움(모양은 첫 문단 것)."""
    ps = [q for q in tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is tc]
    if not ps:
        return
    ts = [t for t in ps[0].iter(T)]
    if not ts:  # 빈 칸(글자 자리 없음) — 첫 run 안에 글자 칸을 만듦(10/11 공사비 합계 금액 칸)
        run = ps[0].find(f"{{{HP}}}run")
        if run is None:
            run = etree.SubElement(ps[0], f"{{{HP}}}run", charPrIDRef="0")
            ps[0].insert(0, run)
        ts = [etree.SubElement(run, T)]
    _clear(ts[0], text)
    for t in ts[1:]:
        _clear(t, "")
    for q in ps[1:]:
        q.getparent().remove(q)


def _equipment(root, items: list, add_image) -> str:
    """공통편 1.6 장비 표 — 줄 수가 같으면 장비명·형식·용도·사진을 설정 값으로. 다르면 그대로 두고 안내."""
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = _cells(tbl)
        head = [_cell_text(cells[(0, c)]).replace(" ", "") for c in range(5) if (0, c) in cells]
        if head[:4] != ["구분", "장비명", "형식", "용도"]:
            continue
        rows = int(tbl.get("rowCnt")) - 1
        if rows != len(items):
            return f"사용 장비가 {len(items)}종인데 지난 보고서 표는 {rows}줄이라 장비 표는 그대로 두었습니다"
        for i, (name, model, purpose, photos) in enumerate(items, start=1):
            for col, val in ((1, name), (2, model or "-"), (3, purpose)):
                if (i, col) in cells:
                    _set_cell(cells[(i, col)], val)
            if (i, 4) in cells and photos:
                imgs = list(cells[(i, 4)].iter("{http://www.hancom.co.kr/hwpml/2011/core}img"))
                for img, ph in zip(imgs, photos):
                    img.set("binaryItemIDRef", add_image(_fit_to_pic(ph, img, crop=True)))  # 칸 크기 픽셀로(형 10/15 "사진 이상하게 들어감" — 확대·늘어남)
        return ""
    return ""


def _positions(root, positions: dict) -> None:
    """참여기술자 명단 표(분야·참여세부·성명·직위…) — 성명 칸의 사람 직위를 설정 값으로."""
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = _cells(tbl)
        head = {c: _cell_text(cells[(0, c)]).replace(" ", "") for c in range(8) if (0, c) in cells}
        if "참여세부" not in "".join(head.values()):
            continue
        name_c = next((c for c, h in head.items() if h.startswith("성명")), None)
        pos_c = next((c for c, h in head.items() if h.startswith("직위")), None)
        if name_c is None or pos_c is None:
            continue
        for (r, c), tc in cells.items():
            if c == name_c and r > 0:
                who = _cell_text(tc).replace(" ", "")
                if who in positions and (r, pos_c) in cells and positions[who]:
                    _set_cell(cells[(r, pos_c)], positions[who])


SUMMARY_PAGE_H = 56000  # 표 한 쪽에 넣을 높이(HWPUNIT) — 견본 요약표(머리줄 포함 60543)가 제목과 한 쪽에 들어감, 조금 여유


def _make_cell(tmpl, r: int, lines: list[str], span: int, height: int):
    """본뜬 칸 하나 — 줄 번호·세로 합침·높이를 정하고 글자를 lines(줄마다 문단 하나)로."""
    tc = copy.deepcopy(tmpl)
    tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(r))
    tc.find(f"{{{HP}}}cellSpan").set("rowSpan", str(span))
    tc.find(f"{{{HP}}}cellSz").set("height", str(height))
    sub = tc.find(f"{{{HP}}}subList")
    ps = sub.findall(f"{{{HP}}}p")
    for q in ps[1:]:
        sub.remove(q)
    first = ps[0]
    for el in list(first.iter(f"{{{HP}}}linesegarray")):
        el.getparent().remove(el)
    for i, line in enumerate(lines or [""]):
        q = first if i == 0 else copy.deepcopy(first)
        ts = list(q.iter(T))
        if ts:
            _clear(ts[0], line)
            for t in ts[1:]:
                _clear(t, "")
        if i:
            sub.append(q)
    return tc


_TL = threading.local()  # 지금 채우는 파일의 테두리 모양(borders.Borders) — 파일 쓰는 쪽이 using_borders로(동시에 여러 보고서를 만들어도 섞이지 않게 스레드마다)


@contextlib.contextmanager
def using_borders(b):
    """with using_borders(Borders(header_xml)) as b: … 표 채우기 … header.xml = b.result(xml) — 줄 복사한 곳 맞닿는 선을 얇게(형 10/15)."""
    old = getattr(_TL, "borders", None)
    _TL.borders = b
    try:
        yield b
    finally:
        _TL.borders = old


def pad_cells(tbl, lr: int | None = 425, tb: int = 283) -> None:
    """표 칸 안 여백(HWPUNIT, 283 = 1mm) — 양식이 0이라 글이 선에 붙던 표(형 10/15 "셀 위아래 너무 붙어있음"). 칸마다 따로 여백을 쓰는 칸(hasMargin=1)은 그대로."""
    m = tbl.find(f"{{{HP}}}inMargin")
    if m is None:
        return
    if lr is not None:  # None = 왼쪽·오른쪽은 그대로
        m.set("left", str(lr))
        m.set("right", str(lr))
    m.set("top", str(tb))
    m.set("bottom", str(tb))


def _thin_seams(tbl, seams) -> bool:
    """복사한 줄끼리 맞닿는 곳(seams = 위쪽 줄 번호들) — 그 선에 닿는 칸의 위·아래 선이 굵거나 이중선이면 칸의 얇은 선으로(형 10/15 "가운데 줄 진함").
    테두리 모양 틀(using_borders)이 없으면 아무것도 안 함 → False."""
    b = getattr(_TL, "borders", None)
    if b is None:
        return False
    seams = set(seams)
    for (r, _c), tc in _cells(tbl).items():
        bottom = r + int(tc.find(f"{{{HP}}}cellSpan").get("rowSpan")) - 1
        top_on, bottom_on = (r - 1) in seams, bottom in seams
        if top_on or bottom_on:
            new = b.thin(tc.get("borderFillIDRef"), top_on, bottom_on)
            if new:
                tc.set("borderFillIDRef", new)
    return True


def _fill_rows(tbl, rows: list, tmpl: dict, head_h: int, heights: list, merge: int, keep_tail: list | None = None) -> None:
    """tbl의 데이터 줄을 rows(줄마다 [칸마다 글줄 목록])로 — 앞 merge칸은 값이 같으면 세로로 합침. keep_tail = 뒤에 그대로 둘 줄(합계 등,
    줄 번호만 다시). 표 높이·테두리 구역·줄 수도 맞춤."""
    trs = tbl.findall(f"{{{HP}}}tr")
    tail = keep_tail or []
    for tr in trs[1:]:
        tbl.remove(tr)
    total = head_h
    key = lambda i, c: tuple("\n".join(x) for x in rows[i][:c + 1])  # noqa: E731
    for i, row in enumerate(rows):
        r = i + 1
        tr = etree.SubElement(tbl, f"{{{HP}}}tr")
        for c, lines in enumerate(row):
            if c < merge:
                if i and key(i - 1, c) == key(i, c):
                    continue
                n = next((k for k in range(i, len(rows)) if key(k, c) != key(i, c)), len(rows)) - i
                tr.append(_make_cell(tmpl[c], r, lines, n, sum(heights[i:i + n])))
            else:
                tr.append(_make_cell(tmpl[c], r, lines, 1, heights[i]))
        total += heights[i]
    for k, tr in enumerate(tail):  # 합계 줄 등 — 줄 번호만 새로
        for tc in tr.findall(f"{{{HP}}}tc"):
            tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(len(rows) + 1 + k))
            total += int(tc.find(f"{{{HP}}}cellSz").get("height")) if tc is tr.findall(f"{{{HP}}}tc")[0] else 0
        tbl.append(tr)
    old_last = int(tbl.get("rowCnt")) - 1
    new_last = len(rows) + len(tail)
    for cz in tbl.iter(f"{{{HP}}}cellzone"):  # 표 전체 테두리 구역도 새 줄 수까지
        if int(cz.get("endRowAddr", "0")) >= old_last:
            cz.set("endRowAddr", str(new_last))
    tbl.set("rowCnt", str(new_last + 1))
    tbl.find(f"{{{HP}}}sz").set("height", str(total))
    _thin_seams(tbl, range(1, len(rows)))  # 데이터 줄이 다 한 양식 줄(위 이중선) 복사 — 줄 사이는 얇게


LINE_H = 1450  # 글줄 하나 높이 어림(HWPUNIT, 9pt 안팎 — 광숭 시험 PDF에서 맞춤)
CHAR_W = 850  # 한글 한 글자 너비 어림(HWPUNIT)


def _row_heights(tmpl: dict, rows: list, minimum: int) -> list[int]:
    """줄마다 높이 어림 — 칸마다 (글줄 수 × 칸 너비에 맞춰 접히는 줄 수)의 최댓값."""
    out = []
    for row in rows:
        lines = 1
        for c, cell_lines in enumerate(row):
            width = int(tmpl[c].find(f"{{{HP}}}cellSz").get("width")) - 400
            per = max(1, width // CHAR_W)
            n = sum(max(1, -(-len(x) // per)) for x in (cell_lines or [""]))
            lines = max(lines, n)
        out.append(max(minimum, LINE_H * lines + 500))
    return out


def _rebuild_paged(root, tbl, rows: list, merge: int, heights: list, page_break_after: bool, first_page_h: int = SUMMARY_PAGE_H) -> None:
    """글자처럼 취급 표는 한 쪽을 넘으면 통째로 밀리므로 한 쪽 높이만큼씩 잘라 표 여러 개(각각 머리줄)로 쪽마다 하나씩."""
    cells = _cells(tbl)
    ncol = int(tbl.get("colCnt"))
    tmpl = {c: copy.deepcopy(cells[(1, c)]) for c in range(ncol)}
    head_h = int(cells[(0, 0)].find(f"{{{HP}}}cellSz").get("height"))
    chunks, cur, h = [], [], head_h
    for row, rh in zip(rows, heights):
        if cur and h + rh > (first_page_h if not chunks else SUMMARY_PAGE_H):
            chunks.append(cur)
            cur, h = [], head_h
        cur.append((row, rh))
        h += rh
    if cur:
        chunks.append(cur)
    top = tbl
    while top.getparent() is not None and top.getparent() is not root:
        top = top.getparent()  # 표가 든 맨 바깥 문단
    orig = copy.deepcopy(top)
    _fill_rows(tbl, [r for r, _ in chunks[0]], tmpl, head_h, [x for _, x in chunks[0]], merge)
    prev = top
    for n, chunk in enumerate(chunks[1:], 1):
        para = copy.deepcopy(orig)
        para.set("pageBreak", "1")
        for el in para.iter():  # 같은 문단을 복사하면 앞 글자(제목 등)도 따라오므로 표 말고 글자는 비움
            if el.tag == T and next(el.iterancestors(f"{{{HP}}}tbl"), None) is None:
                _clear(el, "")
        t2 = next(para.iter(f"{{{HP}}}tbl"))
        t2.set("id", str(int(t2.get("id", "0")) + 1000 + n))
        _fill_rows(t2, [r for r, _ in chunk], tmpl, head_h, [x for _, x in chunk], merge)
        prev.addnext(para)
        prev = para
    if page_break_after:
        nxt = prev.getnext()  # 다음(위치도 등)은 새 쪽에서 — 원래는 표가 쪽을 꽉 채워 자연히 넘어갔음(광숭)
        while nxt is not None and nxt.tag != f"{{{HP}}}p":
            nxt = nxt.getnext()
        if nxt is not None:
            nxt.set("pageBreak", "1")


def _find_table(root, head: list[str]):
    """머리줄 첫 칸들이 head와 같은 표(띄어쓰기·줄바꿈 무시)."""
    want = [h.replace(" ", "") for h in head]
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = _cells(tbl)
        # 머리줄 칸을 열 순서대로(합친 칸은 하나로 — 요약표 "부재(부위)"는 3칸 합침)
        got = [re.sub(r"\s", "", _cell_text(cells[k])) for k in sorted(k for k in cells if k[0] == 0)][:len(want)]
        if got == want and (1, 0) in cells:
            return tbl
    return None


def _summary_table(root, rows: list) -> bool:
    """9쪽 "정기안전점검 실시결과 요약표"(부재(부위) 3칸 | 점검결과 | 조치 필요사항)를 rows[(층, 구분, 부재, [결과], [조치])]로 새로 짬(10/11).
    층·구분은 세로로 합침, 쪽 단위로 나눔, 다음 문단은 새 쪽."""
    tbl = _find_table(root, ["부재(부위)", "점검결과", "조치필요사항"])
    if tbl is None or int(tbl.get("colCnt")) != 5 or not all((1, c) in _cells(tbl) for c in range(5)):
        return False
    data = [[[f], [p], [m], [f"·{x}" for x in res], [f"·{x}" for x in act]] for f, p, m, res, act in rows]
    cells = _cells(tbl)
    heights = _row_heights({c: cells[(1, c)] for c in range(5)}, data, 3178)
    _rebuild_paged(root, tbl, data, 2, heights, True)
    return True


def _priority_table(root, rows: list) -> bool:
    """1.5(3종 1.6) "보수물량 및 우선순위" 표 — rows[(층, 결함유형, 손상내용, 적용공법, 보수물량, 단위, 우선순위)], 층은 세로로 합침, 쪽 단위로 나눔."""
    tbl = _find_table(root, ["구분", "결함유형", "손상내용", "적용공법"])
    if tbl is None or int(tbl.get("colCnt")) != 7 or not all((1, c) in _cells(tbl) for c in range(7)):
        return False
    data = [[[str(x)] for x in r] for r in rows]
    cells = _cells(tbl)
    h = int(cells[(1, 2)].find(f"{{{HP}}}cellSz").get("height"))
    heights = _row_heights({c: cells[(1, c)] for c in range(7)}, data, h)
    # 첫 표는 "1.5 보수·보강 개략공사비 산정" 제목·설명과 한 쪽 — 덜 채움
    _rebuild_paged(root, tbl, data, 1, heights, False, first_page_h=SUMMARY_PAGE_H - 9000)
    return True


def _cost_table(root, rows: list, direct: int) -> bool:
    """개략공사비 산정 표 — 데이터 줄 rows[(구분, 결함 내용, 보수방안, 물량, 단위, 단가, 금액)]을 넣고(단위 칸이 없는 6칸 표면 단위는 물량에 붙임),
    직접공사비 합계·제경비(50%)·부대공(10%)·총공사비 줄의 금액 칸을 채움. 데이터 줄이 없으면 "-" 줄 그대로."""
    tbl = _find_table(root, ["구분", "결함및손상,열화내용", "보수ㆍ보강방안"])
    if tbl is None:
        return False
    cells = _cells(tbl)
    ncol = int(tbl.get("colCnt"))
    trs = tbl.findall(f"{{{HP}}}tr")
    labels = ("직접공사비합계", "제경비", "부대공", "총공사비")
    tail = [tr for tr in trs[1:] if re.sub(r"\s", "", _cell_text(tr.findall(f"{{{HP}}}tc")[0])) in labels]
    money = lambda v: f"{v:,}" if v else "-"  # noqa: E731
    amounts = {"직접공사비합계": direct, "제경비": round(direct * 0.5), "부대공": round(direct * 0.1), "총공사비": round(direct * 1.6)}
    center = next(cells[(1, 0)].iter(f"{{{HP}}}p")).get("paraPrIDRef") if (1, 0) in cells else None  # 데이터 줄 "-" 칸 모양(가운데)
    for tr in tail:
        tcs = tr.findall(f"{{{HP}}}tc")
        v = money(amounts[re.sub(r"\s", "", _cell_text(tcs[0]))])
        _set_cell(tcs[-1], v)
        if v == "-" and center:  # "-"는 가운데(10/12 사용자) — 금액 칸의 오른쪽 정렬이 남지 않게
            for p in tcs[-1].iter(f"{{{HP}}}p"):
                p.set("paraPrIDRef", center)
    if rows and all((1, c) in cells for c in range(ncol)):
        tmpl = {c: copy.deepcopy(cells[(1, c)]) for c in range(ncol)}
        head_h = int(cells[(0, 0)].find(f"{{{HP}}}cellSz").get("height"))
        h = int(cells[(1, 0)].find(f"{{{HP}}}cellSz").get("height"))
        if ncol == 7:
            data = [[[str(x)] for x in r] for r in rows]
        else:  # 평택(6칸): 단위 칸 없음 — 물량에 단위를 붙임
            data = [[[r[0]], [r[1]], [r[2]], [f"{r[3]} {r[4]}".strip()], [str(r[5])], [str(r[6])]] for r in rows]
        _fill_rows(tbl, data, tmpl, head_h, [h] * len(data), 0, keep_tail=tail)
    return True


# ---------- 6단계: AI 초안 넣기 ----------

def _top_text(p) -> str:
    return "".join(_full(t) for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None).strip()


def _set_para(p, text: str, in_table: bool = False) -> None:
    """문단 글을 text로(첫 글자 칸에, 나머지 비움 — 모양은 첫 칸 것). 기본은 본문 문단(안에 든 표 글자는 안 건드림),
    in_table이면 표 칸 안 문단(그 문단 자기 글자만)."""
    if in_table:
        ts = [t for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p]
    else:
        ts = [t for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None]
    if not ts:
        return
    _clear(ts[0], text)
    for t in ts[1:]:
        _clear(t, "")
    for el in list(p.iter(f"{{{HP}}}linesegarray")):
        el.getparent().remove(el)


def _set_lines(tc, lines: list[str]) -> None:
    """칸 글을 lines(줄마다 문단 하나)로 — 첫 문단 모양을 복사."""
    ps = [q for q in tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is tc]
    if not ps:
        return
    first = ps[0]
    for q in ps[1:]:
        q.getparent().remove(q)
    for el in list(first.iter(f"{{{HP}}}linesegarray")):
        el.getparent().remove(el)
    last = first
    for i, line in enumerate(lines or [""]):
        q = first if i == 0 else copy.deepcopy(first)
        ts = list(q.iter(T))
        if not ts:
            run = q.find(f"{{{HP}}}run")
            if run is None:
                continue
            ts = [etree.SubElement(run, T)]
        _clear(ts[0], line)
        for t in ts[1:]:
            _clear(t, "")
        if i:
            last.addnext(q)
        last = q


def old_texts(hwpx: Path) -> str:
    """지난 보고서의 1.3 외관조사 서술·종합결론 글머리 — AI에 말투 참고로 줌."""
    out = []
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    for root in roots[1:]:
        tops = [p for p in root if p.tag == f"{{{HP}}}p"]
        on = concl = False
        for p in tops:
            t = _top_text(p)
            if re.match(r"\d\.\d\s*외관조사", t):
                on = True
                continue
            if on and re.match(r"\d\.\d\s", t) and "외관조사" not in t:
                on = False
            if on and t and not re.match(r"^\d\)", t):
                out.append(t)
            if re.match(r"\d\)", t):
                concl = bool(re.match(r"2\)\s*종합결론", t))
            elif concl and t.startswith("ㆍ"):
                out.append(t)
    return "\n".join(dict.fromkeys(out))


def _ai_front(root, ai: dict, template: str) -> int:
    """결과표 — 중대결함·공중이용부위·점검 주요결과(줄 수는 표 그대로, 넘치면 마지막 칸에 이어서)·주요 보수보강·차기 중점부위·안전등급."""
    cells = _find_result_table([root])
    if cells is None:
        return 0
    n = 0
    from server.sitok import form_fix

    def val(*names, starts=False):  # 이름칸 오른쪽 값 칸 — 공식 양식(중대한 결함등)으로 바꾸면 값 칸 열이 달라져 위치 대신 이름으로(10/21)
        k = _label(cells, *names, starts=starts)
        return _row_right(cells, k[0], k[1] + _span(cells[k], "colSpan")) if k else None

    crit, pub = val("중대결함", "중대한결함"), val("공중이", starts=True)
    if ai.get("critical") and crit is not None:
        _set_lines(crit, [form_fix.none_text(ai["critical"])]); n += 1  # noqa: E702
    if ai.get("public") and pub is not None:
        _set_lines(pub, [form_fix.none_text(ai["public"])]); n += 1  # noqa: E702
    fk = _label(cells, "점검주요결과", "점검(진단)주요결과", starts=True)
    rows, repair_cell = [], None
    if fk:
        mincol = fk[1] + _span(cells[fk], "colSpan")
        allrows = sorted({k[0] for k in cells})
        for rr in [x for x in allrows if x >= fk[0]]:
            lab = next((_n(_cell_text(cells[(rr, c)])) for c in range(0, mincol) if (rr, c) in cells), "")
            if rr > fk[0] and lab.startswith(("주요보수", "다.")):
                if lab.startswith("주요보수"):
                    repair_cell = _row_right(cells, rr, mincol)
                break
            v = _row_right(cells, rr, mincol)
            if v is None:
                break
            rows.append(v)
    f = [x if x.startswith(("ㆍ", "-", "·")) else f"ㆍ{x}" for x in ai.get("findings") or []]
    if f and rows:
        for i, tc in enumerate(rows):
            part = f[i:i + 1] if i < len(rows) - 1 else f[i:]
            _set_lines(tc, part or [""])
        n += 1
    if ai.get("repairs") and repair_cell is not None:
        reps = [x for x in ai["repairs"] if str(x).strip()]
        _set_lines(repair_cell, reps if reps else ["없음"]); n += 1  # noqa: E702
    if ai.get("next_focus"):
        for tc in cells.values():
            for q in tc.iter(f"{{{HP}}}p"):
                t = "".join(_full(x) for x in q.iter(T))
                if "중점 점검부위" in t and ":" in t:
                    _set_para(q, t.split(":")[0].rstrip() + " : " + ai["next_focus"], in_table=True); n += 1  # noqa: E702
    if ai.get("grade") and (5, 8) in cells:
        _set_lines(cells[(5, 8)], [grade_text_for(ai["grade"], template)[0]]); n += 1  # noqa: E702
    return n


def grade_text_for(letter: str, template: str) -> tuple[str, str]:
    from server.sitok.ai_draft import grade_text
    return grade_text(letter, template)


def _letter(grade: str) -> str:
    """결과표 등급 글(보통·C·C등급) → 글자."""
    from server.sitok.ai_draft import WORD_TO_LETTER
    g = (grade or "").replace("등급", "").strip()
    return WORD_TO_LETTER.get(g, g.upper()[:1] if g[:1].upper() in "ABCDE" else "")


def _ai_body(root, ai: dict, template: str, old_grade: str = "") -> int:
    """1.3 외관조사 항목 서술(제목 다음 문단)·결과의 분석 표·종합결론 글머리·안전등급 줄과 정의·안전등급 변경시 사유."""
    from server.sitok.ai_draft import section_key

    n = 0
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    sections = ai.get("sections") or {}
    in13 = False
    for i, p in enumerate(tops):
        t = _top_text(p)
        if re.match(r"1\.\d\s*외관조사\s*실시결과", t):
            in13 = True
            continue
        if in13 and re.match(r"1\.\d\s", t):
            in13 = False
        if in13 and re.match(r"^\d\)", t) and "분석" not in t:
            key = section_key(t)
            text = sections.get(key or "", "")
            nxt = tops[i + 1] if i + 1 < len(tops) else None
            if key and text and nxt is not None and _top_text(nxt) and not re.match(r"^\d\)", _top_text(nxt)):
                _set_para(nxt, text)
                n += 1
    for tbl in root.iter(f"{{{HP}}}tbl"):  # 외관조사 결과의 분석(조사항목 | 조사결과)
        cells = _cells(tbl)
        if re.sub(r"\s", "", _cell_text(cells.get((0, 0), tbl))) != "조사항목":
            continue
        for (r, c), tc in cells.items():
            if c == 0 and r > 0 and (r, 1) in cells:
                key = section_key(_cell_text(tc))
                if key and sections.get(key):
                    _set_lines(cells[(r, 1)], [f"ㆍ{sections[key]}"])
                    n += 1
    concl = [x if x.startswith("ㆍ") else f"ㆍ{x}" for x in ai.get("conclusion") or []]
    for i, p in enumerate(tops):
        t = _top_text(p)
        if re.match(r"2\)\s*종합결론", t) and concl:
            bullets = []
            for q in tops[i + 1:]:
                if _top_text(q).startswith("ㆍ"):
                    bullets.append(q)
                elif _top_text(q):
                    break
            if bullets:
                for q in bullets[1:]:
                    q.getparent().remove(q)
                last = bullets[0]
                _set_para(last, concl[0])
                for line in concl[1:]:
                    q = copy.deepcopy(bullets[0])
                    _set_para(q, line)
                    last.addnext(q)
                    last = q
                n += 1
        if re.match(r"1\)\s*시설물의\s*안전등급", t) and ai.get("grade"):
            word, desc = grade_text_for(ai["grade"], template)
            _set_para(p, f"1) 시설물의 안전등급 : {word}등급")
            nxt = tops[i + 1] if i + 1 < len(tops) else None
            if nxt is not None and _top_text(nxt).startswith("본 시설물은"):
                _set_para(nxt, f"본 시설물은 {desc}로 판단된다.")
            n += 1
        if re.match(r"\d\)\s*안전등급\s*변경\s*시\s*사유", t) and ai.get("grade"):  # 지난 회차 사유가 그대로 남지 않게 늘 새로
            nxt = next((q for q in tops[i + 1:] if _top_text(q)), None)
            if nxt is not None and _top_text(nxt).startswith("-"):
                before, now = _letter(old_grade), ai["grade"]
                if before and before != now:
                    w = lambda x: grade_text_for(x, template)[0]  # noqa: E731
                    _set_para(nxt, f"- 전회차 {w(before)}등급 → 금회 {w(now)}등급 : {ai.get('grade_reason') or '외관조사 결과에 따름'}")
                else:
                    _set_para(nxt, "- 해당사항 없음")
                n += 1
    return n


# ---------- 3종 안전등급 평가(1.5.1·1.5.2, 18항목) ----------
RATINGS = [("우수", 10), ("양호", 8), ("보통", 5), ("미흡", 2), ("불량", 0), ("해당없음", None)]  # 1.5.1은 "미흡" 자리가 "주의"
GROUP_WEIGHT = {"주요": 60, "일반": 20, "부대": 20}


def _eval_tables(roots) -> tuple:
    """(1.5.1 표, 1.5.2 표, 점수 표) — 머리줄 "평가항목"·"평가결과"가 있는 11칸·8칸 표와 "평가점수합" 표. 없으면 None."""
    t1 = t2 = t3 = None
    for root in roots:
        # 시설물편 "1.5 안전등급 평가 및 결과" 제목 아래 표만(공통편 3장에 같은 모양의 예시 표가 있음 — 건드리면 안 됨)
        tables, on = [], False
        for p in (q for q in root if q.tag == f"{{{HP}}}p"):
            t = _top_text(p)
            if re.match(r"1\.\d\s*안전등급\s*평가\s*및\s*결과", t):
                on = True
            elif on and re.match(r"1\.\d\s", t) and "안전등급" not in t:
                on = False
            if on:
                tables += [x for x in p.iter(f"{{{HP}}}tbl") if next(x.iterancestors(f"{{{HP}}}tbl"), None) is None]
        for tbl in tables:
            cells = _cells(tbl)
            head = "".join(_cell_text(cells[k]) for k in cells if k[0] == 0).replace(" ", "")
            if "평가항목" in head and "평가결과" in head:
                if tbl.get("colCnt") == "11" and t1 is None:
                    t1 = tbl
                elif tbl.get("colCnt") == "8" and t2 is None:
                    t2 = tbl
            if "평가점수합" in "".join(_cell_text(tc) for tc in cells.values()).replace(" ", "") and t3 is None:
                t3 = tbl
    return t1, t2, t3


def read_eval_items(hwpx: Path) -> list[dict]:
    """3종 안전등급 평가 18항목 [{no, name, group(주요·일반·부대), rating(지난 평가)}] — 1.5.2 표에서. 2종이면 []."""
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    _, t2, _ = _eval_tables(roots)
    if t2 is None:
        return []
    cells = _cells(t2)
    groups = {}  # 줄 → 영역
    for (r, c), tc in cells.items():
        if c == 0 and r >= 2:
            g = next((k for k in GROUP_WEIGHT if k in _cell_text(tc).replace("\n", "")), None)
            span = int(tc.find(f"{{{HP}}}cellSpan").get("rowSpan"))
            for rr in range(r, r + span):
                groups[rr] = g
    out = []
    for r in sorted({k[0] for k in cells if k[0] >= 2}):
        name = _cell_text(cells.get((r, 1), t2)) if (r, 1) in cells else ""
        m = re.match(r"(\d+)\.\s*(.+)", name.replace("\n", " "))
        if not m:
            continue
        rating = next((RATINGS[i][0] for i in range(6) if "○" in _cell_text(cells.get((r, 2 + i), t2))), "")
        out.append({"no": int(m[1]), "name": m[2].strip(), "group": groups.get(r) or "", "rating": rating})
    return out


def eval_score(items: list[dict]) -> dict:
    """영역별 (점수합 a, 항목 수 b, 상태점수 a/b) → 종합 = Σ(가중치×상태점수)/100, 등급(9·7·5·3 이상 A~D, 아래 E). 해당없음은 뺌.
    한 영역이 통째로 해당없음이면 그 가중치는 나머지 영역에 비율대로(공통편 3.1.5 "부대시설이 없는 경우")."""
    score = dict(RATINGS)
    groups = {}
    for it in items:
        pts = score.get(it.get("rating") or "")
        if pts is None or not it.get("group"):
            continue
        g = groups.setdefault(it["group"], [0, 0])
        g[0] += pts
        g[1] += 1
    rows = {g: (a, b, round(a / b, 2)) for g, (a, b) in groups.items() if b}
    wsum = sum(GROUP_WEIGHT[g] for g in rows)
    total = round(sum(GROUP_WEIGHT[g] * rows[g][2] for g in rows) / wsum, 2) if wsum else 0
    letter = "A" if total >= 9 else "B" if total >= 7 else "C" if total >= 5 else "D" if total >= 3 else "E"
    return {"groups": rows, "total": total, "grade": letter if rows else ""}


def _mark_row(cells, r: int, first_col: int, rating: str) -> None:
    for i, (name, _) in enumerate(RATINGS):
        if (r, first_col + i) in cells:
            _set_lines(cells[(r, first_col + i)], ["○" if name == rating else ""])


def _apply_eval(roots_or_root, items: list[dict], opinion: str) -> int:
    """1.5.1(의견·보수필요·평가 ○·평가결과 안전등급 □■·종합의견)·1.5.2(평가 ○)·점수 표(합·개수·상태점수·종합·등급)에 넣음."""
    roots = roots_or_root if isinstance(roots_or_root, list) else [roots_or_root]
    t1, t2, t3 = _eval_tables(roots)
    by_no = {it["no"]: it for it in items}
    res = eval_score(items)
    n = 0
    for tbl, first, op_col in ((t1, 5, 3), (t2, 2, None)):
        if tbl is None:
            continue
        cells = _cells(tbl)
        for r in sorted({k[0] for k in cells}):
            name_cell = cells.get((r, 1))
            m = re.match(r"(\d+)\.", _cell_text(name_cell)) if name_cell is not None else None
            it = by_no.get(int(m[1])) if m else None
            if it is None:
                continue
            _mark_row(cells, r, first, it.get("rating") or "")
            if op_col is not None:
                if (r, op_col) in cells:
                    _set_lines(cells[(r, op_col)], [it.get("opinion") or "-"])
                if (r, op_col + 1) in cells:
                    _set_lines(cells[(r, op_col + 1)], [it.get("repair") or "-"])
            n += 1
        if op_col is not None and res["grade"]:  # 평가결과 줄 "◦ 안전등급 : □A ■B …"·종합의견
            for (r, c), tc in cells.items():
                txt = _cell_text(tc)
                if "안전등급" in txt and "□" in txt + "■":
                    for q in tc.iter(f"{{{HP}}}p"):
                        line = "".join(_full(x) for x in q.iter(T))
                        if "안전등급" in line:
                            marks = "   ".join(("■" if g == res["grade"] else "□") + g for g in "ABCDE")
                            _set_para(q, re.sub(r"(안전등급\s*:\s*).*", lambda mm: mm.group(1) + marks, line), in_table=True)
                if re.sub(r"\s", "", _cell_text(cells.get((r, 0), tc))).startswith("종합의견") and c > 0 and opinion:
                    _set_lines(tc, [f"◦ {opinion}"])
    if t3 is not None and res["groups"]:
        cells = _cells(t3)
        labels = {"①": "주요", "②": "일반", "③": "부대"}
        for (r, c), tc in cells.items():
            t = _cell_text(tc)
            g = next((v for k, v in labels.items() if t.startswith(k)), None)
            if c == 0 and g in res["groups"]:
                a, b, s = res["groups"][g]
                for i, v in enumerate((a, b, s), 1):
                    if (r, i) in cells:
                        _set_lines(cells[(r, i)], [f"{v:g}"])
            elif c == 0 and g and g not in res["groups"]:
                for i in (1, 2, 3):
                    if (r, i) in cells:
                        _set_lines(cells[(r, i)], ["-"])
            if "/100" in t and "점" in t:
                _set_lines(tc, [re.sub(r"=\s*[\d.]+\s*점", f"= {res['total']:g}점", t.replace("\n", " "))])
            if re.fullmatch(r"[A-E]\s*등급", t.strip()):
                _set_lines(tc, [f"{res['grade']}등급"])
        n += 1
    return n


# ---------- 1.4 기타 부대시설 상태조사 결과표(고정 22항목 — 없다/있다·상태·위치) ----------

def _facility_table(roots):
    """머리줄에 "점검결과"·"해당동호"가 있는 5칸 표."""
    for root in roots:
        for tbl in root.iter(f"{{{HP}}}tbl"):
            cells = _cells(tbl)
            head = "".join(_cell_text(cells[k]) for k in cells if k[0] == 0).replace(" ", "")
            if tbl.get("colCnt") == "5" and "점검결과" in head and "해당동호" in head:
                return tbl
    return None


def read_facility_items(hwpx: Path) -> list[dict]:
    """[{no, name, has(지난 회차 있다?), state, where}] — 표가 없으면 []."""
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    tbl = _facility_table(roots)
    if tbl is None:
        return []
    cells = _cells(tbl)
    out = []
    for r in sorted({k[0] for k in cells if k[0] >= 2}):
        name = _cell_text(cells[(r, 0)]).replace("\n", " ").strip() if (r, 0) in cells else ""
        if name:
            g = lambda c: _cell_text(cells[(r, c)]).replace("\n", " ").strip() if (r, c) in cells else ""  # noqa: E731
            out.append({"no": len(out) + 1, "name": name, "has": "○" in g(2), "state": g(3), "where": g(4)})
    return out


def _apply_facility(root, rows: list[dict]) -> int:
    """rows = [{no, has, state, where}] 순서대로 표 줄에."""
    tbl = _facility_table([root])
    if tbl is None or not rows:
        return 0
    cells = _cells(tbl)
    body = [r for r in sorted({k[0] for k in cells if k[0] >= 2}) if (r, 0) in cells and _cell_text(cells[(r, 0)]).strip()]
    for r, it in zip(body, rows):
        has = bool(it.get("has"))
        vals = ((1, "" if has else "○"), (2, "○" if has else ""), (3, (it.get("state") or "") if has else ""), (4, (it.get("where") or "") if has else ""))
        for c, v in vals:
            if (r, c) in cells:
                _set_lines(cells[(r, c)], [v])
    return 1


# ---------- 회사 기본 틀(다른 시설물 보고서)로 시작할 때 — 그 시설물 고유 내용 정리(2026-10-11) ----------

def _blank_pics(tbl, blank: str, add_image, captions: bool = True) -> None:
    cells = _cells(tbl)
    for (r, c), pic in _pic_slots(tbl):
        _put_pic(pic, blank, add_image)
        if captions and (r - 1, c) in cells and r - 1 > 0 and not next(cells[(r - 1, c)].iter(f"{{{HP}}}pic"), None) is not None:
            _set_lines(cells[(r - 1, c)], ["-"])
        if captions and (r + 1, c) in cells and next(cells[(r + 1, c)].iter(f"{{{HP}}}pic"), None) is None and "현황" not in _cell_text(cells[(r + 1, c)]):
            _set_lines(cells[(r + 1, c)], ["-"])


def _base_reset(root, is_front: bool, sec: int, base: dict, blank: str, add_image) -> int:
    """기본 틀의 시설물 고유 내용: 표지 사진·위치도·전경(이번 사진·주소 지도로, 없으면 흰 그림), 공통편 일반현황 표, 1.1 위치도·전경,
    1.2.6 기실시 점검결과(틀 시설물 이력 → 비움), 1.2.7 보수이력(비움), 1.3 사진 표(이번 결함 사진이 안 들어가는 표는 흰 그림)."""
    n = 0
    mp, cover = base.get("map") or blank, base.get("cover") or blank
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    if is_front:
        n += _set_result_fields(root, base.get("result") or {})
        first = next((p for p in root.iter(f"{{{HP}}}pic") if int(p.find(f"{{{HP}}}curSz").get("width") or 0) > 30000), None)
        if first is not None:  # 표지 사진
            _put_pic(first, cover, add_image)
            n += 1
        for tbl in root.iter(f"{{{HP}}}tbl"):
            head = _cell_text(_cells(tbl).get((0, 0), tbl))
            if "위치도" in head:
                slots = _pic_slots(tbl)
                if slots:
                    _put_pic(slots[0][1], mp, add_image)
                if len(slots) > 1:
                    _put_pic(slots[-1][1], cover, add_image)
                n += 1
            elif "전경사진" in head and not base.get("has_overview"):
                _blank_pics(tbl, blank, add_image)
                n += 1
        return n
    if sec == 1:  # 공통편 — 1.2 대상시설물 현황: 가. 위치도 그림, 나. 일반현황 표
        on = False
        for p in tops:
            t = _top_text(p)
            if "위치도" in t and re.match(r"^[가-하]\.", t):
                on = True
                continue
            pic = next(p.iter(f"{{{HP}}}pic"), None)
            if on and pic is not None:
                _put_pic(pic, mp, add_image)
                n += 1
                break
        for tbl in root.iter(f"{{{HP}}}tbl"):
            c = _cells(tbl)
            head = "".join(_cell_text(c[k]) for k in c if k[0] == 0).replace(" ", "")
            if "건물명" in head and "준공" in head and (1, 1) in c:
                row = ["1", base.get("short") or base.get("name") or "-", base.get("year") or "-", base.get("floors") or "-", base.get("area") or "-",
                       base.get("structure") or "-"]
                for k, v in enumerate(row):
                    if (1, k) in c:
                        _set_lines(c[(1, k)], [v])
                for (r, k), tc in c.items():
                    if r >= 2 and k == 4:
                        _set_lines(tc, [base.get("area") or "-"])
                n += 1
        return n
    for tbl in root.iter(f"{{{HP}}}tbl"):  # 1.1 위치도 및 전경(그림 2개 표)
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        slots = _pic_slots(tbl)
        par = next(tbl.iterancestors(f"{{{HP}}}p"), None)
        prev = par.getprevious() if par is not None else None
        if len(slots) == 2 and prev is not None and "위치도" in _top_text(prev):
            _put_pic(slots[0][1], mp, add_image)
            _put_pic(slots[1][1], cover, add_image)
            n += 1
    # 1.2.6 기실시 점검결과 — 전회차 보고서에서 읽은 이력(base["history"], 위 = 최근)으로. 없으면(처음 맡는 시설물) 첫 표 하나에 FMS 안내.
    hist = _hist_tables(root)
    if hist and base.get("history"):
        n += _fill_history(root, base["history"])
    elif hist:
        n += _fill_history(root, [{"kind": "정기안전점검", "period": "-", "org": "-", "grade": "-", "title": "【 기실시 점검 및 진단 결과 】",
                                   "lines": ["ㆍ당사가 처음 수행하는 점검으로, 이전 점검·진단 결과는 시설물통합정보관리체계(FMS) 이력을 참고한다."]}])
    for p in tops:
        t = _top_text(p)
        if t.startswith("본 과업대상 시설물은") and "정기안전점검" in t:
            if base.get("legal") is False:  # 법정 외 — 관리주체 요청으로 같은 기준 자체 점검(사용자 10/12, 문구는 형 검토)
                tail = ("실시하고 있으며, 그 점검결과는 다음과 같다." if base.get("history") else "실시하는 시설물이다.")
                _set_para(p, f"본 과업대상 시설물은 「시설물의 안전 및 유지관리에 관한 특별법」상 제1·2·3종 시설물에 해당하지 않는 {base.get('use') or '시설물'}이나, "
                             f"관리주체의 요청에 따라 같은 법의 정기안전점검 기준으로 점검을 {tail}")
            else:
                tail = ("법적 주기에 따라 적정하게 수행하고 있는 상태이며, 그 점검결과는 다음과 같다." if base.get("history")
                        else "법적 주기에 따라 실시하여야 하는 시설물이다.")
                _set_para(p, f"본 과업대상 시설물은 제{base.get('grade') or '-'}종에 해당하는 {base.get('use') or '시설물'}로서 「시설물의 안전 및 유지관리에 관한 특별법」에서 "
                             f"규정하고 있는 정기안전점검(1년 2회)을 {tail}")
            n += 1
            break
    n += _set_repairs(root, base.get("repairs") or [])  # 1.2.7 — 전회차 보고서 이력(이번 면담 줄은 뒤에 _apply_survey가)
    if base.get("target"):  # 부록 대상 시설물 표
        n += _set_target_table(root, base["target"], base.get("school", False))
    return n  # 1.3 사진 표는 build 끝의 _photo_tables(빈칸 규칙)가


# ---------- 회사 원본으로 만들 때 전회차 보고서에서 가져오는 것(2026-10-12 — 판 다시 잡기 ③) ----------

def _hist_tables(root) -> list:
    return [t for t in root.iter(f"{{{HP}}}tbl") if _cell_text(_cells(t).get((0, 0), t)).replace(" ", "") == "점검의종류" and t.get("rowCnt") == "4"]


def _cell_lines(tc) -> list[str]:
    """칸 글을 줄로 — 칸 안에 든 표(평택: 지난 회차 요약표)는 "이름 : 내용" 줄로."""
    out = []
    for q in (x for x in tc.iter(f"{{{HP}}}p") if next(x.iterancestors(f"{{{HP}}}tc"), None) is tc):
        t = "".join(_full(x) for x in q.iter(T) if next(x.iterancestors(f"{{{HP}}}tbl"), None) is next(q.iterancestors(f"{{{HP}}}tbl"), None)).strip()
        if t:
            out.append(t)
        for inner in q.iter(f"{{{HP}}}tbl"):
            if next(inner.iterancestors(f"{{{HP}}}tbl"), None) is not next(q.iterancestors(f"{{{HP}}}tbl"), None):
                continue
            c = _cells(inner)
            for r in sorted({k[0] for k in c}):
                row = [" ".join(_cell_text(c[(r, k)]).split()) for k in sorted(k for (rr, k) in c if rr == r)]
                if row and any(row[1:]):
                    out.append(f"{row[0]} : {' '.join(row[1:])}")
    return out


def read_history(hwpx: Path) -> list[dict]:
    """1.2.6 기실시 점검결과 표들 [{kind, period, org, grade, title, lines}] — 위(최근)부터."""
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    out = []
    for root in roots:
        for t in _hist_tables(root):
            c = _cells(t)
            g = lambda r, k: " ".join(_cell_text(c[(r, k)]).split()) if (r, k) in c else ""  # noqa: E731
            out.append({"kind": g(1, 0), "period": g(1, 1), "org": g(1, 2), "grade": g(1, 3), "title": g(2, 0),
                        "lines": _cell_lines(c[(3, 0)]) if (3, 0) in c else []})
    return out


def _fill_hist_table(tbl, e: dict) -> None:
    cells = _cells(tbl)
    for (r, k), key in (((1, 0), "kind"), ((1, 1), "period"), ((1, 2), "org"), ((1, 3), "grade"), ((2, 0), "title")):
        if (r, k) in cells:
            _set_cell(cells[(r, k)], e.get(key) or "-")
    if (3, 0) in cells:
        content = cells[(3, 0)]
        for inner in [x for x in content.iter(f"{{{HP}}}tbl")]:  # 칸 안 표(지난 회차 요약표)는 줄 글로 바꿔 넣으므로 지움
            par = inner.getparent()
            par.remove(inner)
        ps = [q for q in content.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is content]
        tmpl = ps[0]
        for q in ps[1:]:
            q.getparent().remove(q)
        last = None
        for text in e.get("lines") or ["-"]:
            q = tmpl if last is None else copy.deepcopy(tmpl)
            ts = list(q.iter(T))
            if ts:
                _clear(ts[0], text if text.startswith(("ㆍ", "-", "·", "1", "2", "3", "4", "5", "6", "7", "8", "9")) else f"ㆍ{text}")
                for x in ts[1:]:
                    _clear(x, "")
            if last is not None:
                last.addnext(q)
            last = q


def _fill_history(root, entries: list[dict]) -> int:
    """1.2.6 표들을 entries(위 = 최근)로 — 첫 표를 본떠 하나씩, 원래 표들은 지움."""
    tables = _hist_tables(root)
    if not tables or not entries:
        return 0
    tmpl = tables[0]
    for e in entries:
        t = copy.deepcopy(tmpl)
        _new_ids(t)
        _fill_hist_table(t, e)
        tmpl.addprevious(t)
    for t in tables:
        par = next(t.iterancestors(f"{{{HP}}}p"), None)
        t.getparent().remove(t)
        if par is not None and par.getparent() is root and not _top_text(par) and next(par.iter(f"{{{HP}}}tbl"), None) is None:
            root.remove(par)
    return 1


def _set_repairs(root, rows: list[list[str]]) -> int:
    """1.2.7 표를 rows([기간, 종류, 방안, 위치, 비고])로 — 원본 줄은 지우고 모자라면 늘림. 이번 면담 줄은 뒤에 _apply_survey가 빈 줄에."""
    tbl = _repair_table([root])
    if tbl is None:
        return 0
    cells = _cells(tbl)
    for (r, k), tc in cells.items():
        if r >= 1:
            _set_lines(tc, [""] if k == 0 else ["-"])
    for row in rows:
        cells = _cells(tbl)
        free = next((r for r in sorted({k[0] for k in cells if k[0] >= 1}) if not _cell_text(cells.get((r, 0), tbl)).strip()), None)
        if free is None:
            _add_row(tbl)
            cells = _cells(tbl)
            free = int(tbl.get("rowCnt")) - 1
        for k, v in enumerate((row + ["", "", "", "", ""])[:5]):
            if (free, k) in cells:
                _set_lines(cells[(free, k)], [v or "-"])
    return 1


TARGET_KEYS = {"학교명": "owner", "관리주체": "owner", "건물명": "name", "시설명": "name", "용도": "use", "최초건축년도": "first", "준공년도": "year",
               "연면적": "area", "층수": "floors", "구조": "structure", "기존등급": "grade", "실측도면작성대상": "survey", "내진보강여부": "seismic"}


def _set_target_table(root, vals: dict, school: bool) -> int:
    """부록 과업지시서·과업수행계획서의 대상 시설물 표(학교명|건물명|용도|…|내진보강여부, 8칸 넘는 것)의 첫 줄을 이 시설물 값으로(10/12 ③).
    학교가 아니면 머리 "학교명" → "관리주체"."""
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if int(tbl.get("colCnt") or 0) < 8:
            continue
        cells = _cells(tbl)
        head = {c: re.sub(r"\s|\(.*?\)", "", _cell_text(tc)) for (r, c), tc in cells.items() if r == 0}
        if not any(h in ("건물명", "시설명") for h in head.values()) or not any(h.startswith("연면적") for h in head.values()):
            continue
        for c, h in head.items():
            key = TARGET_KEYS.get(h) or ("area" if h.startswith("연면적") else None)
            if key and (1, c) in cells:
                _set_lines(cells[(1, c)], [vals.get(key) or "-"])
            if h == "학교명" and not school:
                _set_lines(cells[(0, c)], ["관리주체"])
        n += 1
    return n


def _set_result_fields(root, fields: dict[str, str]) -> int:
    """결과표 이름 칸 오른쪽 값 — {"공동수급": …, "계약방법": …, "시설물구분": …, "종류": …, "종별": …}(이름은 띄어쓰기 무시)."""
    cells = _find_result_table([root])
    if cells is None:
        return 0
    n = 0
    for (r, c), tc in list(cells.items()):
        label = re.sub(r"\s", "", _cell_text(tc))
        if label in fields and (r, c + 1) in cells and fields[label]:
            _set_lines(cells[(r, c + 1)], [fields[label]])
            n += 1
    return n


def read_overview(hwpx: Path, dest: Path) -> list[tuple[str, str]]:
    """전회차 보고서의 전경사진 [(저장한 경로, 제목)] — 10쪽 위치도 표 아래 그림이 첫 장, 11쪽 "■ 대상 시설물 전경사진" 표들(이번에 안 찍었을 때 씀).
    흰 그림(빈 칸)은 뺌. dest 폴더에 전회차_전경_N.jpg로."""
    import io

    from PIL import Image

    out: list[tuple[str, str]] = []
    with zipfile.ZipFile(hwpx) as z:
        root = etree.fromstring(z.read(_sections(z)[0]))
        hpf = z.read("Contents/content.hpf").decode("utf-8")
        href = dict(re.findall(r'<opf:item id="([^"]+)" href="([^"]+)"', hpf))

        thumbs: list[list[int]] = []

        def save(pic, title: str) -> None:
            img = next(pic.iter(f"{{{CORE}}}img"), None)
            name = href.get(img.get("binaryItemIDRef")) if img is not None else None
            if not name or name not in z.namelist():
                return
            try:
                im = Image.open(io.BytesIO(z.read(name))).convert("RGB")
            except Exception:  # noqa: BLE001
                return
            if min(lo for lo, _ in im.getextrema()) > 245:  # 흰 그림
                return
            small = list(im.convert("L").resize((16, 12)).getdata())  # 10쪽 사진이 11쪽 첫 장과 같은 사진(파일만 따로)인 경우가 많음
            if any(sum(abs(a - b) for a, b in zip(small, s)) / len(small) < 8 for s in thumbs):
                return
            thumbs.append(small)
            im.thumbnail((1600, 1600))
            p = dest / f"전회차_전경_{len(out) + 1}.jpg"
            dest.mkdir(parents=True, exist_ok=True)
            im.save(p, "JPEG", quality=88)
            out.append((str(p), title))

        tables = [t for t in root.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None]
        for t in tables:
            head = _cell_text(_cells(t).get((0, 0), t))
            if "위치도" in head:
                slots = _pic_slots(t)
                if len(slots) >= 2:
                    save(slots[-1][1], "전경사진")
        for t in tables:
            cells = _cells(t)
            if "전경사진" not in _cell_text(cells.get((0, 0), t)):
                continue
            for (r, c), pic in _pic_slots(t):
                cap = _cell_text(cells[(r - 1, c)]).strip("【】 \n") if (r - 1, c) in cells and r - 1 > 0 else ""
                save(pic, cap if cap and cap != "-" else "전경사진")
    return out


def read_texts(hwpx: Path) -> dict:
    """전회차 보고서 글을 AI 초안 모양으로(AI 초안을 안 만들었을 때 원본 글 대신 이걸 넣음) — 결과표 중대결함·공중이용·주요결과·주요보수·
    차기 중점부위·안전등급, 1.3 항목 서술, 종합결론 글머리."""
    from server.sitok.ai_draft import section_key

    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    out: dict = {"sections": {}, "conclusion": [], "findings": [], "from_prior": True}
    cells = _find_result_table(roots)
    if cells is not None:  # 이름칸 → 오른쪽 값(보고서마다 칸 위치가 다름)
        out["critical"] = _value(cells, "중대결함", "중대한결함").replace("\n", " ").strip().lstrip("ㆍ·- ")
        out["public"] = _value(cells, "공중이", starts=True).replace("\n", " ").strip().lstrip("ㆍ·- ")
        for tc in _label_rows(cells, "점검주요결과"):
            out["findings"] += [x.strip() for x in _cell_text(tc).split("\n") if x.strip()]
        rep = _value(cells, "주요보수", starts=True)
        if rep:
            out["repairs"] = [x.strip() for x in rep.split("\n") if x.strip()]
        for tc in cells.values():
            for q in tc.iter(f"{{{HP}}}p"):
                t = "".join(_full(x) for x in q.iter(T))
                if "중점 점검부위" in t and ":" in t:
                    out["next_focus"] = t.split(":", 1)[1].strip()
        out["grade"] = _letter(_value(cells, "안전등급"))
    for root in roots[1:]:
        tops = [p for p in root if p.tag == f"{{{HP}}}p"]
        in13 = False
        for i, p in enumerate(tops):
            t = _top_text(p)
            if re.match(r"\d\.\d\s*외관조사\s*실시결과", t):
                in13 = True
                continue
            if in13 and re.match(r"\d\.\d\s", t):
                in13 = False
            if in13 and re.match(r"^\d\)", t) and "분석" not in t:
                key = section_key(t)
                nxt = tops[i + 1] if i + 1 < len(tops) else None
                if key and nxt is not None and _top_text(nxt) and not re.match(r"^\d\)", _top_text(nxt)):
                    out["sections"][key] = _top_text(nxt)
            if re.match(r"2\)\s*종합결론", t):
                for q in tops[i + 1:]:
                    if _top_text(q).startswith("ㆍ"):
                        out["conclusion"].append(_top_text(q).lstrip("ㆍ").strip())
                    elif _top_text(q):
                        break
    return out


# ---------- 1.2.7 보수·보강 이력, 1.2.8 변경사항 실태조사 ----------

def _repair_table(roots):
    for root in roots:
        for tbl in root.iter(f"{{{HP}}}tbl"):
            cells = _cells(tbl)
            head = "".join(_cell_text(cells[k]) for k in cells if k[0] == 0).replace(" ", "")
            if "보수기간" in head and "공사종류" in head:
                return tbl
    return None


def _change_tables(roots) -> list:
    """[(제목, 표)] — 머리줄 "변경사항" + 둘째 줄 "변경전"인 표, 바로 앞 제목 문단("1) 주요 구조부재의 변경사항" 등)과 함께."""
    out = []
    for root in roots:
        title = ""
        for p in (q for q in root if q.tag == f"{{{HP}}}p"):
            t = _top_text(p)
            if re.match(r"\d\)", t):
                title = t
            for tbl in p.iter(f"{{{HP}}}tbl"):
                cells = _cells(tbl)
                head = "".join(_cell_text(cells[k]) for k in cells if k[0] == 0).replace(" ", "")
                if "변경사항" in head and "변경전" in _cell_text(cells.get((1, 1), tbl)).replace(" ", ""):
                    out.append((title, tbl))
    return out


def read_survey(hwpx: Path) -> dict:
    """지난 보고서의 1.2.7 이력 줄 [[기간, 종류, 방안, 위치, 비고]]과 1.2.8 항목 [{group, label}]."""
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in _sections(z)]
    rep = []
    tbl = _repair_table(roots)
    if tbl is not None:
        cells = _cells(tbl)
        for r in sorted({k[0] for k in cells if k[0] >= 1}):
            row = [_cell_text(cells[(r, c)]).replace("\n", " ").strip() if (r, c) in cells else "" for c in range(5)]
            if row[0]:
                rep.append(row)
    items = []
    for title, t in _change_tables(roots):
        cells = _cells(t)
        for r in sorted({k[0] for k in cells if k[0] >= 2}):
            label = _cell_text(cells.get((r, 0), t)).strip()
            if label:
                items.append({"group": title, "label": label})
    return {"repairs_old": rep, "change_items": items}


def _add_row(tbl) -> None:
    """표 맨 아래 줄을 복사해 한 줄 더(글자는 지움)."""
    trs = tbl.findall(f"{{{HP}}}tr")
    n = int(tbl.get("rowCnt"))
    last = {int(tc.find(f"{{{HP}}}cellAddr").get("colAddr")): tc for tc in trs[-1].findall(f"{{{HP}}}tc")}
    h = max(int(tc.find(f"{{{HP}}}cellSz").get("height")) for tc in last.values())
    for (r, c), tc in _cells(tbl).items():  # 위에서 세로로 합쳐 내려온 칸(평택 "비고")은 그 칸을 본떠 한 칸으로
        if c not in last and r + int(tc.find(f"{{{HP}}}cellSpan").get("rowSpan")) - 1 >= n - 1:
            last[c] = tc
    tr = etree.Element(f"{{{HP}}}tr")
    for c in sorted(last):
        tc = copy.deepcopy(last[c])
        tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(n))
        tc.find(f"{{{HP}}}cellSpan").set("rowSpan", "1")
        tc.find(f"{{{HP}}}cellSz").set("height", str(h))
        _set_lines(tc, [""])
        tr.append(tc)
    if getattr(_TL, "borders", None) is None and len(trs) > 2:  # 예전 마지막 줄은 이제 가운데 줄 — 아래 굵은 테두리 대신 그 위 줄 테두리 모양으로(테두리 틀이 없을 때)
        above = {tc.find(f"{{{HP}}}cellAddr").get("colAddr"): tc.get("borderFillIDRef") for tc in trs[-2].findall(f"{{{HP}}}tc")}
        for tc in trs[-1].findall(f"{{{HP}}}tc"):
            b = above.get(tc.find(f"{{{HP}}}cellAddr").get("colAddr"))
            if b:
                tc.set("borderFillIDRef", b)
    trs[-1].addnext(tr)
    tbl.set("rowCnt", str(n + 1))
    _thin_seams(tbl, [n - 1])  # 예전 끝줄과 새 줄 사이 선을 얇게(틀이 있을 때)
    for cz in tbl.iter(f"{{{HP}}}cellzone"):
        if int(cz.get("endRowAddr", "0")) >= n - 1:
            cz.set("endRowAddr", str(n))
    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None and sz.get("height"):
        sz.set("height", str(int(sz.get("height")) + h))


def _row_height(tr) -> int:
    """줄 높이 = 그 줄에서 시작해 세로로 안 합친 칸의 높이(없으면 0)."""
    return max((int(tc.find(f"{{{HP}}}cellSz").get("height")) for tc in tr.findall(f"{{{HP}}}tc") if tc.find(f"{{{HP}}}cellSpan").get("rowSpan") == "1"), default=0)


def _shift_rows(tbl, from_row: int, delta: int, h: int) -> None:
    """from_row 이후 줄의 주소를 delta만큼 밀고 줄 수·테두리 구역·표 높이(h)를 맞춤(_dup_rows·_del_rows 공용)."""
    for tr in tbl.findall(f"{{{HP}}}tr"):
        for tc in tr.findall(f"{{{HP}}}tc"):
            a = tc.find(f"{{{HP}}}cellAddr")
            if int(a.get("rowAddr")) >= from_row:
                a.set("rowAddr", str(int(a.get("rowAddr")) + delta))
    tbl.set("rowCnt", str(int(tbl.get("rowCnt")) + delta))
    for cz in tbl.iter(f"{{{HP}}}cellzone"):
        if int(cz.get("endRowAddr", "0")) >= from_row - 1:
            cz.set("endRowAddr", str(max(int(cz.get("endRowAddr", "0")) + delta, 0)))
        if int(cz.get("startRowAddr", "0")) >= from_row:
            cz.set("startRowAddr", str(max(int(cz.get("startRowAddr", "0")) + delta, 0)))
    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None and sz.get("height"):
        sz.set("height", str(max(int(sz.get("height")) + h, 0)))


def _span_over(tbl, start: int, end: int, delta: int) -> None:
    """start 위에서 시작해 end줄(포함)까지 세로로 걸친 칸(용도 현황 표 '건물명' 칸처럼)의 rowSpan을 delta만큼."""
    for tc in tbl.iter(f"{{{HP}}}tc"):
        r0 = int(tc.find(f"{{{HP}}}cellAddr").get("rowAddr"))
        sp = tc.find(f"{{{HP}}}cellSpan")
        if r0 < start and r0 + int(sp.get("rowSpan")) - 1 >= end:
            sp.set("rowSpan", str(max(int(sp.get("rowSpan")) + delta, 1)))


def _dup_rows(tbl, start: int, count: int, times: int, clear_cols: set | None = None) -> None:
    """start줄부터 count줄 묶음(세로 합친 칸 포함 — 탄산화 표의 C줄+부재줄)을 바로 뒤에 times번 복사해 끼움(글자는 비움 — clear_cols를 주면 그 열만).
    뒤 줄(최대값·최소값 같은 꼬리줄) 주소·줄 수·표 높이·위에서 걸쳐 내려온 칸의 rowSpan을 같이 맞춤 — 표본층·층수가 틀보다 많을 때(숭의 3개층·13개층, 10/14)."""
    if times <= 0 or count <= 0:
        return
    trs = tbl.findall(f"{{{HP}}}tr")
    block = trs[start:start + count]
    if len(block) < count:
        return
    h = sum(_row_height(tr) for tr in block)
    _span_over(tbl, start, start + count - 1, count * times)
    _shift_rows(tbl, start + count, count * times, h * times)  # 뒤 줄 먼저 밀고
    last = block[-1]
    for t in range(1, times + 1):
        for tr in block:
            new = copy.deepcopy(tr)
            for tc in new.findall(f"{{{HP}}}tc"):
                a = tc.find(f"{{{HP}}}cellAddr")
                a.set("rowAddr", str(int(a.get("rowAddr")) + count * t))
                if clear_cols is None or int(a.get("colAddr")) in clear_cols:
                    _set_lines(tc, [""])
            last.addnext(new)
            last = new
    if _thin_seams(tbl, [start + count * t - 1 for t in range(1, times + 1)]):  # 묶음끼리 맞닿는 선만 얇게(형 10/15 — 3·4개동도)
        return
    if start + count == len(trs) and start - count >= 1:  # 묶음이 표 끝이었으면 원래 끝줄의 굵은 아래 테두리를 그 위 묶음 모양으로(위가 머리줄이면 회색 배경이 따라오므로 안 함, 10/14)
        for src, dst in zip(trs[start - count:start], block):
            above = {tc.find(f"{{{HP}}}cellAddr").get("colAddr"): tc.get("borderFillIDRef") for tc in src.findall(f"{{{HP}}}tc")}
            for tc in dst.findall(f"{{{HP}}}tc"):
                b = above.get(tc.find(f"{{{HP}}}cellAddr").get("colAddr"))
                if b:
                    tc.set("borderFillIDRef", b)


def _del_rows(tbl, start: int, count: int) -> None:
    """start줄부터 count줄을 지움(가운데 줄도) — 뒤 줄 주소·줄 수·표 높이 같이(결과표 남는 기술자 줄, 10/14)."""
    trs = tbl.findall(f"{{{HP}}}tr")
    block = trs[start:start + count]
    if not block:
        return
    h = sum(_row_height(tr) for tr in block)
    _span_over(tbl, start, start + len(block) - 1, -len(block))
    for tr in block:
        tbl.remove(tr)
    _shift_rows(tbl, start + count, -len(block), -h)


def engineer_rows(root, persons: list[tuple[str, str]]) -> int:
    """결과표 "다. 책임(참여)기술자 현황" 줄을 위치로 채움 — i번째 줄 = persons[i](이름은 "현 민 재"처럼 띄어, 등급은 마지막 칸), 남는 줄은 지움.
    글자 바꾸기만으로는 틀에 같은 등급 글자가 두 명이면(다산 "특급기술자"×2) 누가 누구인지 못 가려 어긋남(10/14 숭의). 바꾼 줄 수."""
    cells = _find_result_table([root])
    if cells is None or not persons:
        return 0
    rows = [r for r in sorted({k[0] for k in cells}) if (r, 0) in cells and _n(_cell_text(cells[(r, 0)])).endswith("기술자") and _n(_cell_text(cells[(r, 0)])) != "구분"]
    if not rows:
        return 0
    n = 0
    for r, (name, grade) in zip(rows, persons):
        row = [cells[k] for k in sorted(k for k in cells if k[0] == r)]
        if len(row) < 3:
            continue
        _set_lines(row[1], [_spaced(name) if len(name) <= 4 else name])
        g = grade or "-"
        _set_lines(row[-1], g.split(" ", 1) if len(g) > 10 and " " in g else [g])  # "안전관리 건축분야고급기술자" — 칸이 좁아 "기술/자"로 잘림 → 두 줄(형 10/15)
        n += 1
    extra = rows[len(persons):]
    if extra:
        tbl = cells[(extra[0], 0)].getparent().getparent()
        _del_rows(tbl, extra[0], len(extra))
        n += 1
    return n


def grade_word(grade: str) -> str:
    """결과표 기술등급("안전관리 건축분야고급기술자") → 명단 자격등급("고급기술인")."""
    for key in ("특급", "고급", "중급", "초급"):
        if key in (grade or ""):
            return f"{key}기술인"
    return grade or "-"


def engineer_list(root, persons: list[tuple[str, str]]) -> int:
    """참여기술자 명단 표(분야·참여세부 과업내용·성명·자격 및 등급·비고) — 결과표와 같은 사람·줄 수로(형 10/14 "전회차랑 상관없이 이번 회차 기술자").
    첫 줄 = 책임(분야·참여세부는 틀 첫 줄 그대로), 참여는 틀의 마지막 참여 줄 모양(분야·참여세부)을 본떠, 남는 줄 삭제·모자라면 복사."""
    if not persons:
        return 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = _cells(tbl)
        head = {c: _cell_text(cells[(0, c)]).replace(" ", "") for c in range(8) if (0, c) in cells}
        if "참여세부" not in "".join(head.values()):
            continue
        name_c = next((c for c, h in head.items() if h.startswith("성명")), None)
        grade_c = next((c for c, h in head.items() if h.startswith("자격")), None)
        if name_c is None:
            continue
        rows = [r for r in sorted({k[0] for k in cells}) if r > 0 and (r, name_c) in cells]
        if not rows:
            continue
        need = len(persons)
        if len(rows) < need:
            _dup_rows(tbl, rows[-1], 1, need - len(rows), clear_cols={name_c, grade_c} if grade_c is not None else {name_c})
            cells = _cells(tbl)
            rows = [r for r in sorted({k[0] for k in cells}) if r > 0 and (r, name_c) in cells]
        elif len(rows) > need:  # 남는 줄은 마지막 참여 줄 모양을 남기고 가운데를 지움
            keep = rows[:need]
            if need >= 2:  # 참여 줄 모양은 틀의 마지막 줄(안전관리·현장조사) — 그 줄의 분야·참여세부를 마지막 남는 줄에
                last = rows[-1]
                for c in sorted(c for r, c in cells if r == last and c not in (name_c, grade_c)):
                    if (keep[-1], c) in cells:
                        _set_lines(cells[(keep[-1], c)], [x for x in _cell_text(cells[(last, c)]).split("\n")] or [""])
            _del_rows(tbl, keep[-1] + 1, rows[-1] - keep[-1])
            cells = _cells(tbl)
            rows = keep
        for r, (name, grade) in zip(rows, persons):
            _set_lines(cells[(r, name_c)], [name])
            if grade_c is not None and (r, grade_c) in cells:
                _set_lines(cells[(r, grade_c)], [grade_word(grade)])
        return 1
    return 0


def _table_row_heights(tbl, text_only: bool = False) -> dict[int, int]:
    """줄마다 어림 높이(HWPUNIT) — _est_height와 같은 셈(칸 높이 vs 글 줄 수 × LINE_H). text_only = 글 칸은 지금 칸 높이를 바닥으로 쓰지 않음
    (복사한 줄이 본 줄 높이를 그대로 물려받아 빈 칸이 커지던 것 — 표 4.2 셋째 줄, 10/15)."""
    import math

    rows: dict[int, int] = {}
    for (r, _), tc in _cells(tbl).items():
        span = tc.find(f"{{{HP}}}cellSpan")
        if span is not None and int(span.get("rowSpan") or 1) > 1:
            continue
        sz = tc.find(f"{{{HP}}}cellSz")
        w, h = int(sz.get("width") or 0), int(sz.get("height") or 0)
        m = tc.find(f"{{{HP}}}cellMargin")
        mx = (int(m.get("left") or 141) + int(m.get("right") or 141)) if m is not None else 282
        my = (int(m.get("top") or 141) + int(m.get("bottom") or 141)) if m is not None else 282
        if next(tc.iter(f"{{{HP}}}pic"), None) is not None or next(tc.iter(f"{{{HP}}}tbl"), None) is not None:
            est = h
        else:
            lines = 0
            for p in tc.iter(f"{{{HP}}}p"):
                t = "".join(x.text or "" for x in p.iter(T))
                lines += max(1, math.ceil(len(t) * CHAR_W / max(w - mx, 1000)))
            est = min(lines, 200) * LINE_H + my
            if text_only:
                h = 0
        rows[r] = max(rows.get(r, 0), h, est)
    return rows


def split_findings_row(root, tbl, limit: int) -> bool:
    """결과표 "점검 주요결과" 줄이 쪽을 넘을 것 같으면(어림) 앞 쪽에 들어갈 글머리만 남기고 나머지를 "점검 주요결과(계속)" 줄로 떼어 둘째 표(새 쪽)로 —
    형 10/14 "칸 안에서 잘리면 테두리가 끊겨 보임". limit = 한 쪽에 들어가는 어림 높이(결과표 기준값). 나눴으면 True."""
    cells = _cells(tbl)
    rows = sorted({k[0] for k in cells})
    r = next((rr for rr in rows if (rr, 0) in cells and _n(_cell_text(cells[(rr, 0)])).startswith("점검주요결과")), None)
    if r is None:
        return False
    heights = _table_row_heights(tbl)
    if sum(heights.values()) <= limit:
        return False
    nxt = [k for k in cells if k[0] == r and k[1] > 0]
    if not nxt:
        return False
    tc = cells[min(nxt)]
    paras = [p for p in tc.iter(f"{{{HP}}}p") if next(p.iterancestors(f"{{{HP}}}tc"), None) is tc]
    texts = ["".join(x.text or "" for x in p.iter(T)) for p in paras]
    if len([t for t in texts if t.strip()]) < 2:
        return False
    sz = tc.find(f"{{{HP}}}cellSz")
    w = int(sz.get("width") or 0) - 282
    import math

    before = sum(h for rr, h in heights.items() if rr < r)
    avail = limit - before - 1200
    keep, used = [], 282
    for t in texts:
        need = max(1, math.ceil(len(t) * CHAR_W / max(w, 1000))) * LINE_H
        if keep and used + need > avail:
            break
        keep.append(t)
        used += need
    rest = texts[len(keep):]
    if not rest:
        return False
    _dup_rows(tbl, r, 1, 1)  # 같은 모양 줄 하나 더(글은 비움)
    cells = _cells(tbl)
    _set_lines(cells[(r, min(nxt)[1])], keep)
    _set_lines(cells[(r + 1, 0)], ["점검", "주요결과", "(계속)"])
    _set_lines(cells[(r + 1, min(nxt)[1])], rest)
    return split_result_table(root, tbl, at=r + 1)


def split_result_table(root, tbl, at: int | None = None) -> bool:
    """결과표를 '다. 책임(참여)기술자 현황'부터 새 쪽의 둘째 표로(문단 복사 + pageBreak, 앞/뒤 줄은 _del_rows) — 형 10/14 "2~3줄 애매하게 넘어가면 아예 넘겨버려".
    '다.' 줄이 없으면(이미 나눴거나 모양이 다르면) 안 함. 정기·정밀 공용(pagecheck.split_result_tables가 PDF를 보고 부름)."""
    cells = _cells(tbl)
    rows = sorted({k[0] for k in cells})
    k = at if at is not None else next((r for r in rows if (r, 0) in cells and re.sub(r"\s", "", _cell_text(cells[(r, 0)])).startswith("다.")), None)
    if k is None or k == rows[0] or k not in rows:
        return False
    top = tbl
    while top.getparent() is not None and top.getparent() is not root:
        top = top.getparent()  # 표가 든 맨 바깥 문단(제목 "○○ 결과표"가 같은 문단)
    para = copy.deepcopy(top)
    para.set("pageBreak", "1")
    for el in para.iter():  # 복사한 문단의 제목 글자는 비움(표만)
        if el.tag == T and next(el.iterancestors(f"{{{HP}}}tbl"), None) is None:
            _clear(el, "")
    t2 = next(para.iter(f"{{{HP}}}tbl"))
    t2.set("id", str(int(t2.get("id", "0")) + 2000))
    _del_rows(tbl, k, len(rows) - k)
    _del_rows(t2, 0, k)
    top.addnext(para)
    return True


def _apply_survey(root, survey: dict) -> int:
    n = 0
    new = [r for r in survey.get("repairs") or [] if (r.get("method") or r.get("kind") or "").strip()]
    tbl = _repair_table([root])
    if tbl is not None and new:
        for row in new:
            cells = _cells(tbl)
            free = next((r for r in sorted({k[0] for k in cells if k[0] >= 1}) if not _cell_text(cells.get((r, 0), tbl)).strip()), None)
            if free is None:
                _add_row(tbl)
                cells = _cells(tbl)
                free = int(tbl.get("rowCnt")) - 1
            vals = [row.get("period") or "-", row.get("kind") or "-", row.get("method") or "-", row.get("where") or "-", row.get("note") or "-"]
            for c, v in enumerate(vals):
                if (free, c) in cells:
                    _set_lines(cells[(free, c)], [v])
        n += 1
    changes = survey.get("changes") or {}
    for _, t in _change_tables([root]):  # 변경 있는 항목만 쓰고, 나머지는 "변경사항없음"(첫 줄)·"〃"(바로 위도 없음일 때) — 지난 회차 변경이 남지 않게
        cells = _cells(t)
        prev_none = False
        for r in sorted({k[0] for k in cells if k[0] >= 2}):
            label = _cell_text(cells.get((r, 0), t)).strip()
            ch = changes.get(label)
            if ch and (ch.get("after") or "").strip():
                vals, prev_none = [ch.get("before") or "-", ch["after"], ch.get("where") or "-", ch.get("note") or "-"], False
            else:
                vals, prev_none = ["-", "〃" if prev_none else "변경사항없음", "-", "-"], True
            for c, v in enumerate(vals, 1):  # 한 항목에 변동이 여러 건(건축물대장 초안)이면 칸 안에서 줄을 나눔
                if (r, c) in cells:
                    _set_lines(cells[(r, c)], str(v).split("\n"))
        n += 1
    return n



OVERVIEW_PER_PAGE = 6


def _cropped(path, w: int, h: int) -> bytes:
    """사진을 칸 비율(w:h)로 가운데 잘라 JPG — 세로 사진이 가로 칸에 찌그러지지 않게."""
    import io

    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    iw, ih = img.size
    if iw * h > ih * w:  # 칸보다 넓음 → 좌우를 자름
        nw = ih * w // h
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = iw * h // w
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    pw, ph = max(int(w / 7200 * PIC_DPI), 1), max(int(h / 7200 * PIC_DPI), 1)  # 칸 크기 픽셀로(작은 사진은 작게, 큰 사진은 잘려 보이던 것 — 10/14)
    img = img.resize((pw, ph))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def _fit_to_pic(path, img, crop: bool = True):
    """그림 파일을 그 그림 틀(img의 pic curSz) 크기 픽셀로 — crop이면 가운데 잘라 꽉, 아니면(서류) 흰 여백을 둘러 통째로. 못 읽으면 원래 경로."""
    import io

    from PIL import Image, ImageOps

    pic = next(img.iterancestors(f"{{{HP}}}pic"), None)
    sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
    w, h = (int(sz.get("width") or 0), int(sz.get("height") or 0)) if sz is not None else (0, 0)
    if w <= 0 or h <= 0:
        return path
    try:
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    except Exception:  # noqa: BLE001
        return path
    ratio = (im.width / max(im.height, 1)) / (w / h)
    if crop and 0.4 < ratio < 2.5:  # 비율이 아주 다른 사진(스타프 433×31 같은 띠)은 자르면 한 조각만 크게 흐려짐 → 통째로
        try:
            return _cropped(path, w, h)
        except Exception:  # noqa: BLE001
            return path
    pw, ph = max(int(w / 7200 * PIC_DPI), 1), max(int(h / 7200 * PIC_DPI), 1)
    im.thumbnail((pw, ph))
    canvas = Image.new("RGB", (pw, ph), "white")
    canvas.paste(im, ((pw - im.width) // 2, (ph - im.height) // 2))
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    return buf.getvalue()


PIC_DPI = 96  # 우리 한글(2020)이 표 칸 그림을 그리는 기준 — 픽셀 = HWPUNIT/7200인치 × 96(10/14 t72_pic.py 실험: dpi 메타·orgSz 무시)


def _new_ids(el) -> None:
    """복사한 표·그림에 새 id(한글은 같은 id가 둘이면 하나를 잃을 수 있음)."""
    import random

    for x in el.iter(f"{{{HP}}}tbl", f"{{{HP}}}pic"):
        if x.get("id"):
            x.set("id", str(random.randint(10 ** 9, 2 * 10 ** 9)))
        if x.get("instid"):
            x.set("instid", str(random.randint(10 ** 7, 10 ** 8)))


def _pic_slots(tbl) -> list:
    """표의 그림 칸 [((줄, 칸), pic)] — 줄·칸 순."""
    cells = _cells(tbl)
    out = []
    for k in sorted(cells):
        pic = next(cells[k].iter(f"{{{HP}}}pic"), None)
        if pic is not None:
            out.append((k, pic))
    return out


def _put_pic(pic, path, add_image) -> None:
    img = next(pic.iter(f"{{{CORE}}}img"), None)
    sz = pic.find(f"{{{HP}}}curSz")
    if img is None or not path or not Path(path).exists():
        return
    w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
    img.set("binaryItemIDRef", add_image(_cropped(path, w, h)))


def _overview(root, photos: list, blank: str, add_image) -> int:
    """10쪽 위치도 표의 아래 그림 = 첫 전경사진, 11쪽 "■ 대상 시설물 전경사진" 표 = 한 쪽 6장씩(쪽이 모자라면 표 문단을 복사, 남으면 지움).
    제목 칸 = 사진 바로 위 칸 "【제목】", 남는 칸 = 흰 그림·"-"."""
    if not photos:
        return 0

    def head(p) -> str:
        t = next((x for x in p.iter(f"{{{HP}}}tbl") if next(x.iterancestors(f"{{{HP}}}tbl"), None) is None), None)
        return _cell_text(_cells(t).get((0, 0), t)) if t is not None else ""

    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    pages = [p for p in tops if "전경사진" in head(p)]
    if not pages:
        return 0
    n = 0
    loc = next((p for p in tops if "위치도" in head(p)), None)
    if loc is not None:
        slots = _pic_slots(next(loc.iter(f"{{{HP}}}tbl")))
        if len(slots) >= 2:
            _put_pic(slots[-1][1], photos[0][0], add_image)
            n += 1
    need = -(-len(photos) // OVERVIEW_PER_PAGE)
    while len(pages) < need:
        q = copy.deepcopy(pages[-1])
        _new_ids(q)
        q.set("pageBreak", "1")
        pages[-1].addnext(q)
        pages.append(q)
    for q in pages[need:]:
        q.getparent().remove(q)
    for k, p in enumerate(pages[:need]):
        tbl = next(p.iter(f"{{{HP}}}tbl"))
        cells = _cells(tbl)
        for i, ((r, c), pic) in enumerate(_pic_slots(tbl)):
            idx = k * OVERVIEW_PER_PAGE + i
            path, title = photos[idx] if idx < len(photos) else (blank, None)
            _put_pic(pic, path, add_image)
            if (r - 1, c) in cells and r - 1 > 0:
                _set_lines(cells[(r - 1, c)], ["-" if title is None else f"【{title or '전경사진'}】"])
        n += 1
    return n


def _photo_slots(tbl) -> list[tuple[tuple[int, int], tuple[int, int] | None]]:
    """사진 표의 [(사진 칸, 그 아래 설명 칸)] 줄·칸 순 — 머리 다음부터 사진 줄·설명 줄이 번갈아(사진 줄이 더 높음).
    그림이 없는 칸("해당없음"·"-"만 있던 칸)도 사진 자리로 셈."""
    cells = _cells(tbl)
    rows = sorted({r for r, _ in cells if r >= 1})
    height = {r: max(int(tc.find(f"{{{HP}}}cellSz").get("height") or 0) for (rr, _), tc in cells.items() if rr == r) for r in rows}
    out = []
    for i in range(0, len(rows) - 1, 2):
        pr, cr = rows[i], rows[i + 1]
        if height[pr] <= height[cr]:  # 사진 줄·설명 줄 모양이 아니면 그 표는 안 건드림
            return []
        for c in sorted(c for r, c in cells if r == pr):
            out.append(((pr, c), (cr, c) if (cr, c) in cells else None))
    return out


def _photo_table_list(root) -> list:
    from server.sitok.ai_draft import section_key

    out = []
    for tbl in root.iter(f"{{{HP}}}tbl"):
        head = _cell_text(_cells(tbl).get((0, 0), tbl))
        if ("대표사진" in head or "사진 현황" in head) and section_key(head):
            out.append((tbl, section_key(head)))
    return out


def _slot_put(tc, cap_tc, image, text: str, caption: str, tpl, add_image) -> None:
    """사진 표 한 칸 — image(add_image에 넘길 경로·바이트)가 있으면 그림(칸에 그림이 없으면 tpl을 본떠 넣음), 없으면 그림을 빼고 text.
    설명 칸 = caption. 글만 넣는 칸은 설명 칸 글자 모양으로(그림만 있던 칸은 흰 글씨인 것도 있음 — 비구조체 표)."""
    if image is not None:
        pic = next(tc.iter(f"{{{HP}}}pic"), None)
        if pic is None and tpl is not None:
            pic = copy.deepcopy(tpl)
            pic.set("id", str(random.randint(1_000_000_000, 2_000_000_000)))
            pic.set("instid", str(random.randint(100_000_000, 999_999_999)))
            _set_lines(tc, [""])
            p = next(q for q in tc.iter(f"{{{HP}}}p"))
            run = p.find(f"{{{HP}}}run")
            if run is None:
                run = etree.SubElement(p, f"{{{HP}}}run", charPrIDRef="0")
            run.insert(0, pic)
        img = next(pic.iter(f"{{{CORE}}}img"), None) if pic is not None else None
        if img is not None:
            img.set("binaryItemIDRef", add_image(image))
    else:
        for pic in list(tc.iter(f"{{{HP}}}pic")):
            pic.getparent().remove(pic)
        _set_lines(tc, [text])
        cap_run = next(cap_tc.iter(f"{{{HP}}}run"), None) if cap_tc is not None else None
        if cap_run is not None:
            for run in tc.iter(f"{{{HP}}}run"):
                run.set("charPrIDRef", cap_run.get("charPrIDRef"))
    if cap_tc is not None:
        _set_lines(cap_tc, [caption or "-"])


def _photo_tables(root, rep: dict, add_image) -> int:
    """1.3 항목별 사진 표("■ ○○ 현황: 대표사진"·"사진 현황") — 빈칸 규칙(사용자 10/12, 표마다 제각각이던 것 하나로):
    사진이 있으면 차례로 넣고 설명 = 그 결함, 남는 사진 칸은 비움(그림·글자 없음) + 설명 "-",
    그 항목 사진이 하나도 없으면(항목 자체 없음 — 강재구조 없음 등) 첫 사진 칸만 "해당없음".
    6) 공중이용·7) 기타시설은 현장 화면 탭 사진으로(_parts_tables)."""
    tables = _photo_table_list(root)
    tpl = next((copy.deepcopy(p) for tbl, _ in tables for p in tbl.iter(f"{{{HP}}}pic")), None)  # 그림 없는 칸에 사진을 넣을 때 본뜰 그림
    n = 0
    for tbl, key in tables:
        if key in ("public", "other"):
            continue
        slots = _photo_slots(tbl)
        if not slots:
            continue
        cells = _cells(tbl)
        photos = [(p, cap) for p, cap in (rep.get(key) or []) if p and Path(p).exists()]
        for i, (pk, ck) in enumerate(slots):
            path, caption = photos[i] if i < len(photos) else (None, "-")
            _slot_put(cells[pk], cells[ck] if ck else None, path, "해당없음" if not photos and i == 0 else "", caption, tpl, add_image)
        n += 1
    return n


def _trim_rows(tbl, keep: int) -> None:
    """표를 앞 keep줄만 남김(뒤 줄 지움) — 줄 수·표 높이·테두리 구역도."""
    trs = tbl.findall(f"{{{HP}}}tr")
    if len(trs) <= keep:
        return
    cut = 0
    for tr in trs[keep:]:
        first = tr.find(f"{{{HP}}}tc")
        cut += int(first.find(f"{{{HP}}}cellSz").get("height")) if first is not None else 0
        tbl.remove(tr)
    for cz in tbl.iter(f"{{{HP}}}cellzone"):
        if int(cz.get("endRowAddr", "0")) >= keep:
            cz.set("endRowAddr", str(keep - 1))
    tbl.set("rowCnt", str(keep))
    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None:
        sz.set("height", str(max(int(sz.get("height") or 0) - cut, 0)))


REGULAR_RESULT_FIT = 76000  # 정기 결과표 어림 높이 한 쪽 기준(낸 보고서 76928이 한 쪽에 듦, 넘친 숭의 2026이 76886 — 어림이 거칠어 가운데쯤; 넘치면 pagecheck가 '다.'부터 나눔)
BODY_H = 67000  # 본문 높이(HWPUNIT, ≈236mm) — A4에서 위·아래 여백·머리말·꼬리말 뺀 것(원본 쪽 설정), 한 쪽짜리 표가 이만함


def _est_height(tbl) -> int:
    """표 높이 어림(HWPUNIT) — 줄마다 max(칸 높이, 글 줄 수 × LINE_H)(칸 너비로 접히는 줄 셈). 그림·안쪽 표가 든 칸은 칸 높이(_row_heights 합)."""
    return sum(_table_row_heights(tbl).values())


def table_heights(root) -> dict[str, int]:
    """본문 표 id → 어림 높이 — 내용 넣기 전에 재 두고 _let_split이 늘어난 만큼을 봄(어림 오차는 앞뒤가 같아 상쇄)."""
    return {t.get("id"): _est_height(t) for t in root.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None}


def _splittable(t, head_rows: int = 1) -> None:
    """쪽에서 셀 단위로 나뉘게 — 글자처럼 취급 표는 한글이 안 나눔 → 자리 차지(가운데)로, 머리 줄 header 표시(다음 쪽에 반복)."""
    t.set("pageBreak", "CELL")
    pos = t.find(f"{{{HP}}}pos")
    if pos is not None and pos.get("treatAsChar") == "1":
        pos.attrib.update({"treatAsChar": "0", "flowWithText": "1", "allowOverlap": "0", "vertRelTo": "PARA", "vertAlign": "TOP", "vertOffset": "0",
                           "horzRelTo": "COLUMN", "horzAlign": "CENTER", "horzOffset": "0"})
    t.set("textWrap", "TOP_AND_BOTTOM")
    t.set("repeatHeader", "1")
    for tc in t.iter(f"{{{HP}}}tc"):
        addr = tc.find(f"{{{HP}}}cellAddr")
        if addr is not None and int(addr.get("rowAddr", "99")) < head_rows and next(tc.iterancestors(f"{{{HP}}}tbl")) is t:
            tc.set("header", "1")


def _let_split(root, before: dict | None = None) -> int:
    """표가 쪽을 넘을 때(10/12 사용자 — 동안교회 용도현황 18줄이 통째로 다음 쪽, 제목만 남은 쪽):
    - 늘 나눔: 줄이 느는 표(1.2.4 용도현황·1.2.7 보수·보강 이력·1.2.8 변경사항·개략공사비) — 원본은 "나누지 않음 + 글자처럼 취급".
    - 넘칠 때만 나눔: 나머지 본문 표는 내용을 넣은 뒤 높이를 어림해 한 쪽(BODY_H)을 넘을 것 같으면(1.4·1.5.1·8) 분석·1.2.6 등 글이 길어질 때).
      한 쪽 안이면 원본대로 통째로(회사 보고서 모양 — 앞 쪽 아래가 비면 제목도 같이 넘어감, _KeepHeads).
    9쪽 요약표·보수 우선순위표는 프로그램이 쪽 단위로 나눠 넣음(_summary_table·_priority_table)."""
    from server.sitok import detail

    changes = [tbl for _, tbl in _change_tables([root])]
    always = [detail._tables(root)[2], _repair_table([root]), *changes, _find_table(root, ["구분", "결함및손상,열화내용", "보수ㆍ보강방안"])]
    n = 0
    for t in always:
        if t is not None:
            _splittable(t, 2 if any(t is c for c in changes) else 1)  # 1.2.8은 머리 2줄(변경사항 / 변경전·변경후)
            n += 1
    done = {id(t) for t in always if t is not None}
    for t in root.iter(f"{{{HP}}}tbl"):
        if id(t) in done or next(t.iterancestors(f"{{{HP}}}tbl"), None) is not None or t.get("pageBreak") == "CELL" and t.find(f"{{{HP}}}pos").get("treatAsChar") == "0":
            continue
        if _grew_past_page(t, (before or {}).get(t.get("id"))):
            _splittable(t)
            n += 1
    return n


def _grew_past_page(t, est_before: int | None) -> bool:
    """원래 표 높이(원본 설계) + 내용을 넣으며 늘어난 어림 높이가 한 쪽(BODY_H)을 넘는지 — 늘지 않은 표(한 쪽을 꽉 채우게 설계된 틀 표 등)는 안 걸림."""
    if est_before is None:
        return False
    grew = _est_height(t) - est_before
    sz = t.find(f"{{{HP}}}sz")
    designed = int(sz.get("height") or 0) if sz is not None else 0
    return grew > LINE_H and designed + grew > BODY_H * 0.95


HEAD_RE = re.compile(r"^(\d+(\.\d+)+|\d+\)|[가-하]\.)\s*\S")  # 1.2.4 … / 1) … / 가. …


def _head_kind(t: str) -> str:
    """제목 단계 — "1.2.4"는 점 개수, "1)"·"가."는 그 꼴(같은 단계 항목이 바로 이어지면 목록이라 안 묶음)."""
    m = HEAD_RE.match(t or "")
    if not m:
        return ""
    h = m.group(1)
    return "num" if h.endswith(")") else "kor" if h.endswith(".") and not h[0].isdigit() else f"dot{h.count('.')}"


class _KeepHeads:
    """제목 문단(1.2.4 대상시설물의 용도현황·1) 주요 구조부재의 변경사항 등)에 "다음 문단과 함께" — 제목만 쪽 끝에 남고 표·글은 다음 쪽으로 가는 것
    막기(10/12 사용자). 제목 문단 모양(paraPr)을 복사해 keepWithNext만 켠 새 모양으로 바꿈(같은 모양을 쓰는 빈 줄·다른 문단은 그대로),
    제목 바로 뒤 빈 줄도 같이(빈 줄에만 붙으면 표와 떨어짐). header.xml은 build 끝에 씀."""

    HH = "http://www.hancom.co.kr/hwpml/2011/head"

    def __init__(self, header: bytes):
        self.root = etree.fromstring(header)
        self.props = self.root.find(f".//{{{self.HH}}}paraProperties")
        self.by_id = {p.get("id"): p for p in self.props.findall(f"{{{self.HH}}}paraPr")} if self.props is not None else {}
        self.next = max((int(i) for i in self.by_id), default=0) + 1
        self.made: dict[str, str] = {}

    def _keep(self, pid: str) -> str:
        if pid not in self.made:
            src = self.by_id.get(pid)
            if src is None:
                return pid
            cp = copy.deepcopy(src)
            cp.set("id", str(self.next))
            for bs in cp.iter(f"{{{self.HH}}}breakSetting"):
                bs.set("keepWithNext", "1")
            self.props.append(cp)
            self.made[pid] = str(self.next)
            self.next += 1
        return self.made[pid]

    def clone(self, pid: str, tag: str, change) -> str:
        """문단 모양 pid를 복사해 change(복사본)로 고친 새 모양 번호 — 같은 (pid, tag)는 한 번만(10/19 layout_fix: 내어 쓰기 없애기·줄 간격 줄이기)."""
        key = f"{pid}|{tag}"
        if key not in self.made:
            src = self.by_id.get(pid)
            if src is None or self.props is None:
                return pid
            cp = copy.deepcopy(src)
            cp.set("id", str(self.next))
            change(cp)
            self.props.append(cp)
            self.by_id[str(self.next)] = cp
            self.made[key] = str(self.next)
            self.next += 1
        return self.made[key]

    def apply(self, root) -> int:
        if self.props is None:
            return 0
        tops = [p for p in root if p.tag == f"{{{HP}}}p"]
        blank = lambda q: (not _top_text(q) and next(q.iter(f"{{{HP}}}tbl"), None) is None  # noqa: E731
                           and next(q.iter(f"{{{HP}}}pic"), None) is None)
        n = 0
        for i, p in enumerate(tops):
            t = _top_text(p)
            if not HEAD_RE.match(t) or len(t) > 45 or re.search(r"[☑□☐■]", t) or next(p.iter(f"{{{HP}}}tbl"), None) is not None:
                continue
            nxt = next((_top_text(q) for q in tops[i + 1:] if not blank(q)), "")
            if _head_kind(nxt) == _head_kind(t):  # "가. … 나. …"처럼 같은 단계가 바로 이어지면 목록 — 묶으면 줄줄이 붙음
                continue
            p.set("paraPrIDRef", self._keep(p.get("paraPrIDRef")))
            n += 1
            j = i + 1
            while j < len(tops) and blank(tops[j]):
                tops[j].set("paraPrIDRef", self._keep(tops[j].get("paraPrIDRef")))
                j += 1
        return n

    def header(self) -> bytes:
        if self.props is not None:
            self.props.set("itemCnt", str(len(self.props.findall(f"{{{self.HH}}}paraPr"))))
        return etree.tostring(self.root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _parts_tables(root, parts: dict, add_image) -> int:
    """1.3 6) 공중이용·7) 기타시설 사진 표(10/12 사용자) — 4칸(사진 줄·설명 줄 2쌍)으로 줄이고 현장 화면 탭 사진으로.
    공중이용 = 기준표 4항목 한 칸씩(설명 = 항목 이름, 사진 없으면 "해당없음"), 기타시설 = 윗줄 마감재 2·아랫줄 부착물 등 2(빈 칸 사진·설명 "-")."""
    tables = _photo_table_list(root)
    tpl = next((copy.deepcopy(p) for tbl, _ in tables for p in tbl.iter(f"{{{HP}}}pic")), None)
    n = 0
    for tbl, key in tables:
        if key not in ("public", "other"):
            continue
        _trim_rows(tbl, 5)  # 머리 + 사진·설명 2쌍
        slots = _photo_slots(tbl)
        cells = _cells(tbl)
        for i, (pk, ck) in enumerate(slots):
            name, path = (parts.get(key) or [])[i] if i < len(parts.get(key) or []) else ("-", None)
            img = None
            if path and Path(path).exists():
                pic = next(cells[pk].iter(f"{{{HP}}}pic"), None)
                pic = tpl if pic is None else pic
                sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
                w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
                img = _cropped(path, w, h)
            _slot_put(cells[pk], cells[ck] if ck else None, img, "해당없음" if key == "public" else "-", name, tpl, add_image)
        n += 1
    return n


def _finish_repairs(root) -> int:
    """1.2.7 보수·보강 이력 표 마무리(10/12 사용자: "-"가 가운데 아님·빈칸) — 빈 칸은 "-", 칸 정렬은 칸마다 첫 줄 모양으로
    (원본 광숭초 표의 7·8줄 보수방안 칸만 양쪽 정렬이었음)."""
    tbl = _repair_table([root])
    if tbl is None:
        return 0
    cells = _cells(tbl)
    first = {c: next(tc.iter(f"{{{HP}}}p")).get("paraPrIDRef") for (r, c), tc in cells.items() if r == 1}
    for (r, c), tc in cells.items():
        if r < 1:
            continue
        if not _cell_text(tc).strip():
            _set_lines(tc, ["-"])
        if first.get(c):
            for p in tc.iter(f"{{{HP}}}p"):
                p.set("paraPrIDRef", first[c])
    return 1


def _add_history(root, old: Values) -> bool:
    """1.2.6 기실시된 점검 및 진단결과 — 맨 위 회차 표를 복사해 틀(= 직전 회차) 한 칸을 위에 붙임(민재형 10/10: 지난 이력 + 전회차 요약).
    점검기간·안전등급·점검 주요결과는 틀의 결과표에서. 이미 그 기간 표가 있으면 안 붙임."""
    if not (old.period_start and old.period_end):
        return False
    period = f"{old.period_start:%Y.%m.%d}~{old.period_end:%Y.%m.%d}"
    tables = [t for t in root.iter(f"{{{HP}}}tbl") if _cell_text(_cells(t).get((0, 0), t)).replace(" ", "") == "점검의종류"
              and int(t.get("rowCnt")) == 4]
    if not tables or any(period in _cell_text(_cells(t)[(1, 1)]) for t in tables if (1, 1) in _cells(t)):
        return False
    first = tables[0]
    tbl = copy.deepcopy(first)  # 표만 복사 — 회차 표들이 한 묶음(run) 안에 나란히 있어서 묶음째 복사하면 다른 회차도 겹침(10/10)
    cells = _cells(tbl)
    _set_cell(cells[(1, 0)], "정기안전점검")
    _set_cell(cells[(1, 1)], period)
    _set_cell(cells[(1, 3)], old.grade or "-")
    _set_cell(cells[(2, 0)], f"【 {old.year}년 {old.half} 정기안전점검 실시결과 】")
    content = cells[(3, 0)]
    ps = [q for q in content.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is content]
    tmpl = ps[0]
    for q in ps[1:]:
        q.getparent().remove(q)
    last = None
    for text in old.findings or ["-"]:
        q = tmpl if last is None else copy.deepcopy(tmpl)
        ts = list(q.iter(T))
        if ts:
            _clear(ts[0], text if text.startswith("ㆍ") else f"ㆍ{text}")
            for t in ts[1:]:
                _clear(t, "")
        if last is not None:
            last.addnext(q)
        last = q
    first.addprevious(tbl)
    return True


def build(src: Path, old: Values, new: Values, dest: Path, extras: Extras | None = None) -> int:
    """src(지난 hwpx) → dest(새 hwpx). 바꾼 글자 칸 수를 돌려준다. extras = 설정 값(그림·장비·직위)·이력 추가(못 한 것은 extras.notes)."""
    extras = extras or Extras(history=False)
    whole, parts, front = replacements(old, new)
    added: list[tuple[str, bytes]] = []  # 새 그림(BinData 이름, 바이트)

    run = datetime.datetime.now().strftime("%y%m%d%H%M%S")  # 틀이 이 프로그램이 만든 한글이면 그 안에 이미 sitok1.jpg… 가 있어 이름이 겹침 → 만들 때마다 다른 이름

    def add_image(path_or_bytes) -> str:
        key = f"sitok{run}_{len(added) + 1}"
        added.append((key, path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()))
        return key
    dest.parent.mkdir(parents=True, exist_ok=True)
    changed = 0
    texts: list[str] = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as zout:
        ordered = _sections(zin)
        sections = set(ordered)
        keep = _KeepHeads(zin.read("Contents/header.xml")) if "Contents/header.xml" in zin.namelist() else None  # 제목 + 다음 문단 함께(10/12)
        bd = Borders(zin.read("Contents/header.xml").decode("utf-8")) if keep is not None else None  # 줄 복사 테두리(10/15)
        with using_borders(bd):
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "Contents/header.xml" and keep is not None:
                    continue  # 제목 문단 모양을 더해 맨 뒤에 씀
                if info.filename in sections:
                    root = etree.fromstring(data)
                    is_front = info.filename == ordered[0]
                    heights = table_heights(root) if not is_front else {}  # 내용 넣기 전 표 높이 어림(_let_split — 늘어난 표만 나눔)
                    changed += _apply(root, whole, parts, front, is_front)
                    from server.sitok import form_fix  # 공식 결과표 양식·작성방법(10/21 형 "첨부1#")
                    if is_front:
                        changed += form_fix.result_official(root)
                        changed += form_fix.result_title(root, new.half)
                    if is_front and new.persons:
                        changed += engineer_rows(root, new.persons)  # 결과표 기술자 줄은 위치로(글자 바꾸기 충돌 방지, 10/14)
                    if extras.base:
                        changed += _base_reset(root, is_front, ordered.index(info.filename), extras.base, extras.blank, add_image)
                    for img, kind, idx in _doc_pics(root, is_front):
                        path = extras.images.get((kind, idx))
                        if path and Path(path).exists():
                            img.set("binaryItemIDRef", add_image(_fit_to_pic(path, img, crop=False)))  # 서류는 자르지 않고 틀 비율로(형 10/15 "수료증 사진 짤림")
                            changed += 1
                    if extras.equipment:
                        note = _equipment(root, extras.equipment, add_image)
                        if note:
                            extras.notes.append(note)
                    if extras.positions:
                        _positions(root, extras.positions)
                    if extras.history and _add_history(root, old):
                        changed += 1
                    if is_front and extras.overview:
                        changed += _overview(root, extras.overview, extras.blank, add_image)
                    if is_front and extras.summary and _summary_table(root, extras.summary):
                        changed += 1
                    if not is_front and extras.priority and _priority_table(root, extras.priority):
                        changed += 1
                    if not is_front and extras.cost is not None and _cost_table(root, extras.cost[0], extras.cost[1]):
                        changed += 1
                    if extras.ai:
                        changed += _ai_front(root, extras.ai, extras.template) if is_front else _ai_body(root, extras.ai, extras.template, old.grade)
                    if is_front:
                        changed += form_fix.result_none(root)  # 결함이 없으면 "없음"만(작성방법)
                    else:  # 부록 과업수행계획서·사전검토보고서(10/21 형 수정사항 2~4)
                        if new.period_start and new.period_end:
                            changed += form_fix.schedule_days(root, (new.period_end - new.period_start).days + 1)
                        if new.persons:
                            changed += form_fix.org_names(root, [p[0] for p in new.persons])
                        changed += form_fix.precheck_other(root)
                    if is_front and new.persons:
                        changed += engineer_list(root, new.persons)  # 참여기술자 명단도 이번 회차 사람으로(10/14)
                    if is_front:
                        from server.sitok import layout_fix  # 모양 손질(10/19 형 요구사항 문서)
                        changed += layout_fix.submit_dashes(root)
                        changed += layout_fix.toc_appendix(root)
                        changed += layout_fix.submit_date(root, new.report_month)
                        changed += layout_fix.spine_name(root, new.name)  # 책등 괄호 안 = 시설물명(묶음은 merge가 "등 N개소")
                        for tbl in root.iter(f"{{{HP}}}tbl"):  # 정기 결과표 "점검 주요결과"가 길면 앞 쪽 몫 + (계속) 줄로(10/14)
                            c0 = _cells(tbl)
                            if {"용역명", "점검기간", "관리주체명"} <= {re.sub(r"\s", "", _cell_text(v)) for v in c0.values()}:
                                changed += layout_fix.result_rows(tbl)  # 좁은 줄 늘리기 — 나누기 어림 전에
                                if split_findings_row(root, tbl, REGULAR_RESULT_FIT):
                                    changed += 1
                                break
                    if extras.survey and not is_front:
                        changed += _apply_survey(root, extras.survey)
                    if extras.survey and extras.survey.get("detail") and not is_front:
                        from server.sitok import detail as _detail
                        changed += _detail.apply(root, extras.survey["detail"])
                    if extras.ai and extras.ai.get("facility") and not is_front:
                        changed += _apply_facility(root, extras.ai["facility"])
                    if extras.ai and extras.ai.get("items") and not is_front:
                        changed += _apply_eval(root, extras.ai["items"], extras.ai.get("eval_opinion") or "")
                    if not is_front:  # 1.3 사진 표(빈칸 규칙 10/12)·1.2.7 마무리 — 회사 원본으로 만들 때 늘
                        changed += _photo_tables(root, extras.rep_photos or {}, add_image)
                        if extras.parts is not None:
                            changed += _parts_tables(root, extras.parts, add_image)
                        changed += _finish_repairs(root)
                        from server.sitok import layout_fix
                        changed += layout_fix.strip_na_titles(root)
                        if extras.seismic is not None:  # 학교 내진보강 점검표(10/19 형 B5)
                            from server.sitok import good as _good
                            changed += _good.apply_seismic(root, extras.seismic, Path(extras.seismic_base), add_image, sys.modules[__name__])
                        changed += layout_fix.chapter_title_break(root)  # 장 표지 제목 둘째 줄 "양" 아래로(10/19 형)
                        changed += layout_fix.toc_list_left(root)  # 장 표지 소목차 한 줄로
                        changed += layout_fix.trim_blank_before_change_heads(root)  # 1.2.8 "3) …변경사항" 앞 빈 줄
                        if keep is not None:
                            changed += layout_fix.grade_para_indent(root, keep)  # 1.8 "본 시설물은…" 내어 쓰기 없앰
                        changed += layout_fix.appendix_dates(root, new.period_start)  # 부록 표지 날짜 = 점검 시작 연월
                        changed += layout_fix.task_title(root, new.title)  # 과업지시서 표지 = 용역명 앞부분
                        changed += layout_fix.seismic_gap(root)  # 내진 점검표 기관명·건물명 사이
                        changed += _let_split(root, heights)  # 줄이 느는 표·한 쪽을 넘게 커진 표는 쪽에서 나눔(10/12)
                        if not extras.has_drawings:  # 1.2.9 관련 설계도면 — 붙일 도면이 없으면 "후면첨부"라고 남지 않게
                            for q in root.iter(f"{{{HP}}}p"):
                                if re.fullmatch(r"-?\s*후면\s*첨부\s*-?", _top_text(q) or ""):
                                    _set_para(q, "-")
                                    changed += 1
                    if keep is not None and not is_front:
                        keep.apply(root)
                    for el in list(root.iter(f"{{{HP}}}linesegarray")):
                        el.getparent().remove(el)
                    texts.append("\r\n".join("".join(t.text or "" for t in p.iter(T)) for p in root.iter(f"{{{HP}}}p")))
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                elif info.filename == "Preview/PrvText.txt":
                    continue
                elif info.filename == "Preview/PrvImage.png":
                    continue  # 지난 회차 첫 쪽 그림 — 새것과 달라 지움
                elif info.filename == "Contents/content.hpf":
                    hpf = data  # 새 그림 목록을 붙여 맨 뒤에 씀
                    continue
                compress = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
                zout.writestr(info, data, compress_type=compress)
        if keep is not None:
            zout.writestr("Contents/header.xml", bd.result(keep.header().decode("utf-8")).encode("utf-8"))
        zout.writestr("Preview/PrvText.txt", "\r\n".join(texts)[:2000].encode("utf-8"))
        items = "".join(f'<opf:item id="{k}" href="BinData/{k}.jpg" media-type="image/jpg" isEmbeded="1"/>' for k, _ in added)
        zout.writestr("Contents/content.hpf", hpf.decode("utf-8").replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8"))
        for k, b in added:
            zout.writestr(f"BinData/{k}.jpg", b, compress_type=zipfile.ZIP_STORED)
    dest.with_suffix(".tmp").replace(dest)
    return changed


def leftovers(hwpx: Path, words: list[str]) -> dict[str, int]:
    """만든 파일에 아직 남은 예전 값(시설물명 등) 개수 — 시험·확인용."""
    out = {w: 0 for w in words if w}
    with zipfile.ZipFile(hwpx) as z:
        for n in _sections(z):
            text = z.read(n).decode("utf-8")
            for w in out:
                out[w] += text.count(w)
    return out
