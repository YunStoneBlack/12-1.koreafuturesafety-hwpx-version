"""시특법 정기안전점검 보고서 만들기(2026-10-10 4단계) — "지난 회차 보고서(한글 hwpx)를 틀로 새 회차" = 지금 손으로 하는 방식(복사 → 바뀐 값 고치기) 자동.

1) read_old(지난 hwpx) — 결과표(가. 일반현황 표)에서 예전 값(용역명·점검기간·관리주체·대표자·준공일·점검금액·위치·규모·기술자)과 표지의 연도·반기·월을 읽는다.
2) build(지난 hwpx, old, new, 새 hwpx) — 본문 글자 칸(<hp:t>)마다 예전 값을 새 값으로 바꾼다. 결과표 칸처럼 칸 전체가 그 값인 곳은 칸째로,
   연도·반기·점검기간처럼 문장 속에 들어간 것은 그 부분만. 줄 배치 캐시(linesegarray)는 지움(글자를 바꾸면 한글이 "변조"로 막을 수 있음 —
   server/contract_docs/inspection.py와 같은 이유), 미리보기 글자(Preview/PrvText.txt)도 새로.
결함·외관조사·종합결론 등 내용은 지난 회차 그대로 두고(5·6단계에서 현장 조사·AI로), 여기선 회차가 바뀌며 달라지는 값만 바꾼다.
"""
from __future__ import annotations

import copy
import datetime
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
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
    """결과표 = "용 역 명"·"점검기간"·"관리주체명"이 있는 표."""
    for root in roots:
        for tbl in root.iter(f"{{{HP}}}tbl"):
            cells = _cells(tbl)
            texts = {k: _cell_text(v).replace(" ", "") for k, v in cells.items()}
            if texts.get((1, 0)) == "용역명" and texts.get((1, 4)) == "점검기간" and texts.get((2, 0)) == "관리주체명":
                return cells
    return None


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
    g = lambda r, c: _cell_text(cells[(r, c)]) if (r, c) in cells else ""  # noqa: E731
    v = Values(title=" ".join(g(1, 1).split()), owner=g(2, 1), rep=g(2, 5), amount_k=g(5, 5), address=g(6, 1), scale=g(6, 5))
    period = g(1, 5)
    parts = re.split(r"[~∼]", period)
    v.period_start, v.period_end = _d(parts[0]), _d(parts[1]) if len(parts) > 1 else None
    v.completion = _d(g(5, 1))
    v.grade = g(5, 8)
    r = 10  # "나. 점검 실시결과 현황" 아래 점검 주요결과 칸들(주요 보수ㆍ보강 줄 전까지)
    while (r, 1) in cells and not re.sub(r"\s", "", g(r, 0)).startswith(("주요보수", "다.")):
        txt = " ".join(x.strip() for x in g(r, 1).split("\n") if x.strip()).lstrip(".").strip()
        if txt:
            v.findings.append(txt)
        r += 1
    m = re.search(r"\[(.+?)\]", v.title)
    v.name = m[1].strip() if m else ""
    m = re.search(r"(\d{4})\s*년\s*(?:도\s*)?(상반기|하반기)", v.title)
    if m:
        v.year, v.half = int(m[1]), m[2]
    # 기술자: "다. 책임(참여)기술자 현황" 아래 줄들(구분 | 성명 | 과업 참여기간 | 기술등급)
    for r in range(8, 40):
        role, name, grade = g(r, 0).replace(" ", ""), g(r, 2).replace(" ", ""), g(r, 6)
        if role.endswith("기술자") and name and role != "구분":
            v.persons.append((name, grade))
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
    if old.completion and new.completion:
        for o, f in _date_forms(old.completion):
            cell(o, f(new.completion))
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
                    img.set("binaryItemIDRef", add_image(ph))
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
    for tr in tail:
        tcs = tr.findall(f"{{{HP}}}tc")
        _set_cell(tcs[-1], money(amounts[re.sub(r"\s", "", _cell_text(tcs[0]))]))
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
            if re.match(r"1\.\d\s*외관조사", t):
                on = True
                continue
            if on and re.match(r"1\.\d\s", t) and "외관조사" not in t:
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
    g = lambda r, c: _cell_text(cells[(r, c)]) if (r, c) in cells else ""  # noqa: E731
    if ai.get("critical") and (8, 1) in cells:
        _set_lines(cells[(8, 1)], [ai["critical"]]); n += 1  # noqa: E702
    if ai.get("public") and (9, 1) in cells:
        _set_lines(cells[(9, 1)], [ai["public"]]); n += 1  # noqa: E702
    rows = []
    r = 10
    while (r, 1) in cells and not re.sub(r"\s", "", g(r, 0)).startswith(("주요보수", "다.")):
        rows.append(r)
        r += 1
    repair_row = r if (r, 1) in cells and re.sub(r"\s", "", g(r, 0)).startswith("주요보수") else None
    f = [x if x.startswith(("ㆍ", "-", "·")) else f"ㆍ{x}" for x in ai.get("findings") or []]
    if f and rows:
        for i, rr in enumerate(rows):
            part = f[i:i + 1] if i < len(rows) - 1 else f[i:]
            _set_lines(cells[(rr, 1)], part or [""])
        n += 1
    if ai.get("repairs") and repair_row is not None:
        _set_lines(cells[(repair_row, 1)], ai["repairs"]); n += 1  # noqa: E702
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


def _ai_body(root, ai: dict, template: str) -> int:
    """1.3 외관조사 항목 서술(제목 다음 문단)·결과의 분석 표·종합결론 글머리·안전등급 줄과 정의."""
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
    return n


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

    def add_image(path) -> str:
        key = f"sitok{len(added) + 1}"
        added.append((key, Path(path).read_bytes()))
        return key
    dest.parent.mkdir(parents=True, exist_ok=True)
    changed = 0
    texts: list[str] = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as zout:
        ordered = _sections(zin)
        sections = set(ordered)
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in sections:
                root = etree.fromstring(data)
                is_front = info.filename == ordered[0]
                changed += _apply(root, whole, parts, front, is_front)
                for img, kind, idx in _doc_pics(root, is_front):
                    path = extras.images.get((kind, idx))
                    if path and Path(path).exists():
                        img.set("binaryItemIDRef", add_image(path))
                        changed += 1
                if extras.equipment:
                    note = _equipment(root, extras.equipment, add_image)
                    if note:
                        extras.notes.append(note)
                if extras.positions:
                    _positions(root, extras.positions)
                if extras.history and _add_history(root, old):
                    changed += 1
                if is_front and extras.summary and _summary_table(root, extras.summary):
                    changed += 1
                if not is_front and extras.priority and _priority_table(root, extras.priority):
                    changed += 1
                if not is_front and extras.cost is not None and _cost_table(root, extras.cost[0], extras.cost[1]):
                    changed += 1
                if extras.ai:
                    changed += _ai_front(root, extras.ai, extras.template) if is_front else _ai_body(root, extras.ai, extras.template)
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
