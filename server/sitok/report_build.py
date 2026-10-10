"""시특법 정기안전점검 보고서 만들기(2026-10-10 4단계) — "지난 회차 보고서(한글 hwpx)를 틀로 새 회차" = 지금 손으로 하는 방식(복사 → 바뀐 값 고치기) 자동.

1) read_old(지난 hwpx) — 결과표(가. 일반현황 표)에서 예전 값(용역명·점검기간·관리주체·대표자·준공일·점검금액·위치·규모·기술자)과 표지의 연도·반기·월을 읽는다.
2) build(지난 hwpx, old, new, 새 hwpx) — 본문 글자 칸(<hp:t>)마다 예전 값을 새 값으로 바꾼다. 결과표 칸처럼 칸 전체가 그 값인 곳은 칸째로,
   연도·반기·점검기간처럼 문장 속에 들어간 것은 그 부분만. 줄 배치 캐시(linesegarray)는 지움(글자를 바꾸면 한글이 "변조"로 막을 수 있음 —
   server/contract_docs/inspection.py와 같은 이유), 미리보기 글자(Preview/PrvText.txt)도 새로.
결함·외관조사·종합결론 등 내용은 지난 회차 그대로 두고(5·6단계에서 현장 조사·AI로), 여기선 회차가 바뀌며 달라지는 값만 바꾼다.
"""
from __future__ import annotations

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


def _cell_text(tc) -> str:
    return "\n".join("".join(t.text or "" for t in p.iter(T)) for p in tc.iter(f"{{{HP}}}p")).strip()


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
    v = Values(title=g(1, 1), owner=g(2, 1), rep=g(2, 5), amount_k=g(5, 5), address=g(6, 1), scale=g(6, 5))
    period = g(1, 5)
    parts = re.split(r"[~∼]", period)
    v.period_start, v.period_end = _d(parts[0]), _d(parts[1]) if len(parts) > 1 else None
    v.completion = _d(g(5, 1))
    m = re.search(r"\[(.+?)\]", v.title)
    v.name = m[1].strip() if m else ""
    m = re.search(r"(\d{4})\s*년\s*(?:도\s*)?(상반기|하반기)", v.title)
    if m:
        v.year, v.half = int(m[1]), m[2]
    # 기술자: "다. 책임(참여)기술자 현황" 아래 줄들(구분 | 성명 | 과업 참여기간 | 기술등급)
    for r in range(15, 30):
        role, name, grade = g(r, 0).replace(" ", ""), g(r, 2).replace(" ", ""), g(r, 6)
        if role.endswith("기술자") and name and role != "구분":
            v.persons.append((name, grade))
    # 표지 "2026. 04." — 첫 구역에서 연도. 월 모양
    for t in roots[0].iter(T):
        m = re.fullmatch(r"\s*(\d{4})\.\s*(\d{1,2})\.\s*", t.text or "")
        if m:
            v.report_month = (int(m[1]), int(m[2]))
            break
    if not v.name:  # 용역명에 [시설물명]이 없으면 표지 "○○에 대한"
        for t in roots[0].iter(T):
            m = re.fullmatch(r"\s*(.+?)에\s*대한\s*", t.text or "")
            if m:
                v.name = m[1].strip()
                break
    for root in roots:  # 과업지시서 "용역기간은 2026년 06월 30일 까지" — 한 문장이 글자 칸 여러 개로 나뉘어 있음
        for p in root.iter(f"{{{HP}}}p"):
            m = re.search(r"용역기간은\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)", "".join(t.text or "" for t in p.iter(T)))
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


FRONT_ONLY = "front"  # 앞부분(첫 구역: 표지·책등·제출문·결과표·요약표)에서만 쓰는 규칙 표시


def replacements(old: Values, new: Values) -> tuple[dict[str, str], list[tuple[str, str]], set[str]]:
    """(칸 전체가 같을 때만 바꿀 것 {예전: 새}, 글자 속 어디든 바꿀 것 [(예전, 새)] — 긴 것부터, 앞부분에서만 쓸 예전 값들).
    "상반기"·"2026"처럼 짧은 낱말 칸은 앞부분에서만 — 본문엔 보수·보강 이력처럼 과거 기록이 있어서(10/10)."""
    whole: dict[str, str] = {}
    parts: list[tuple[str, str]] = []
    front: set[str] = set()

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
    return whole, parts, front


def _own_runs(p) -> list:
    """이 문단에 바로 속한 글자 칸(안에 든 표의 글자는 뺌)."""
    return [t for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p]


def _cross_runs(root, pairs: list[tuple[str, str]]) -> int:
    """글자 칸 여러 개에 걸쳐 나뉜 값 — 책등 "2","0","2","6"처럼(세로글씨는 글자마다 문단이 따로). 맨 바깥 문단 단위로 그 안의 글자 칸을
    차례로 이어 붙여 찾고, 글자 수가 같은 것만 글자 단위로 맞춰 바꿈(칸 모양은 그대로)."""
    n = 0
    for p in root.findall(f"{{{HP}}}p"):
        runs = [t for t in p.iter(T) if t.text]
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
    for t in root.iter(T):
        s = t.text or ""
        if not s.strip():
            continue
        key = s.strip()
        if key in whole:
            t.text = s.replace(key, whole[key])
            n += 1
            continue
        out = s
        for o, nw in parts:
            if o in out:
                out = out.replace(o, nw)
        if out != s:
            t.text = out
            n += 1
    # 칸 하나가 여러 줄(<hp:p> 여럿)로 나뉜 값(결과표 "형식 : … / 연면적 : …")은 칸째 비교
    for tc in root.iter(f"{{{HP}}}tc"):
        txt = _cell_text(tc)
        if "\n" in txt and txt in whole:
            ps = list(tc.iter(f"{{{HP}}}p"))
            ts = [t for t in ps[0].iter(T)]
            if ts:
                ts[0].text = whole[txt].replace("\n", " ")
                for t in ts[1:]:
                    t.text = ""
                for p in ps[1:]:
                    for t in p.iter(T):
                        t.text = ""
                n += 1
    # 나뉜 칸에 걸친 연도·반기(책등 등) — 앞부분에서만, 한 칸 안에서 못 바꾼 것만 남아 있으므로 글자 수가 같은 짧은 값만
    if is_front:
        n += _cross_runs(root, [(o, nw) for o, nw in parts if len(o) <= 8] + [(o, nw) for o, nw in whole.items() if len(o) <= 4])
    return n


def build(src: Path, old: Values, new: Values, dest: Path) -> int:
    """src(지난 hwpx) → dest(새 hwpx). 바꾼 글자 칸 수를 돌려준다."""
    whole, parts, front = replacements(old, new)
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
                changed += _apply(root, whole, parts, front, info.filename == ordered[0])
                for el in list(root.iter(f"{{{HP}}}linesegarray")):
                    el.getparent().remove(el)
                texts.append("\r\n".join("".join(t.text or "" for t in p.iter(T)) for p in root.iter(f"{{{HP}}}p")))
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename == "Preview/PrvText.txt":
                continue
            elif info.filename == "Preview/PrvImage.png":
                continue  # 지난 회차 첫 쪽 그림 — 새것과 달라 지움
            compress = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zout.writestr(info, data, compress_type=compress)
        zout.writestr("Preview/PrvText.txt", "\r\n".join(texts)[:2000].encode("utf-8"))
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
