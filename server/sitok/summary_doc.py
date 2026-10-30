"""정기안전점검 요약문(2026-10-16 민재형 — 견본 안산대 2026 상반기 정기 요약문 8쪽) — 회사 템플릿 폴더의 정기안전점검_요약문_원본.hwpx를
이번 보고서 값으로 채워 따로 한글로 만들고(build) PDF로 바꿔 보고서 PDF의 목차 앞에 끼움(insert_before_toc). 목차에는 "▣ 요약문" 줄(add_toc_line).

견본 구성: 머리말(용역명 ▣ 요약문) · 1. 과업의 목적(고정) · 2. 과업수행기간 · 3. 정기점검 결과 요약
  3.1 시설물 현황(건물마다 준공연도·층수·연면적·구조형식) · 3.2 등급 현황(3종 A~E, 2종 양호·보통·미흡·불량 — 별개 체계, 형 10/16)
  3.3 보수보강 우선순위표(본문 보수물량 표의 그 건물 적용공법 전부·우선순위 범위 "2~4순위") · 3.4 시설물 결과 요약(전차·금회 등급, 결과표 점검 주요결과, 보수방안)
  3.5 정밀안전점검·정밀안전진단 대상 · 3.6 결언(고정 첫 문단 + 동마다 결론을 묶은 글 — AI 초안, 없으면 기본 문장)
표 칸은 report_build의 칸 만들기를 그대로 씀(_make_cell·_fill_rows·_row_heights).
"""
from __future__ import annotations

import copy
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb
from server.sitok.borders import Borders

HP = rb.HP
T = rb.T
SAMPLE_TITLE = "2026년 상반기 안산대학교 정기안전점검 용역"
GRADES3 = ["A", "B", "C", "D", "E"]
GRADES2 = ["양호", "보통", "미흡", "불량"]  # 2종 — A~E와 별개(우수 없음)
KINDS = ("1종", "2종", "3종", "미지정")  # 3.2 등급 현황 줄 순서(형 10/20 표)
KIND_LINES = {"1종": ["1종"], "2종": ["2종"], "3종": ["3종"], "미지정": ["미지정", "시설물"]}
TO5 = {"양호": "B", "보통": "C", "미흡": "D", "불량": "E"}  # 1·2종 등급 → A등급(우수)~E등급(불량) 칸(종별이 섞인 표 머리)
WORD5 = dict(zip(GRADES3, ("우수", "양호", "보통", "미흡", "불량")))
BAD = ("D", "E", "미흡", "불량")  # 정밀안전진단 대상 — 동마다 그 동 등급 체계로(3종·미지정 D·E, 1·2종 미흡·불량)
NAME_STEP = 1132  # 3.2 이름 칸 한 줄 늘 때 높이(견본 두 줄 3872 − 한 줄 2740)
TOC_AFTER = "▣ 시설물의 위치도 및 전경사진"


@dataclass
class Building:
    name: str
    year: str = "-"
    floors: str = "-"
    area: str = "-"
    structure: str = "-"
    prev: str = "-"
    grade: str = "-"  # 3종 A~E · 2종 양호·보통·미흡·불량
    cls: str = ""  # 1종/2종/3종/미지정(3.2 표 줄 — 비면 Summary.cls·label)
    findings: list = field(default_factory=list)
    methods: str = "주의관찰"
    prio: str = "4순위"


@dataclass
class Summary:
    title: str
    period: str
    year: int
    half: str
    kind: str = "정기"
    cls: str = "3종"  # 3종 / 2종 — 동마다 종별(Building.cls)이 없을 때만
    label: str = "제3종시설물"  # 제3종시설물·제2종시설물·미지정시설물(법정 외) — 〃
    category: str = "건축물"
    buildings: list = field(default_factory=list)
    conclusion: list = field(default_factory=list)
    precise: list = field(default_factory=list)  # 정밀안전점검 대상
    diag: list = field(default_factory=list)  # 정밀안전진단 대상(D·E — 2종 미흡·불량)


def _text(el) -> str:
    return "".join(x.text or "" for x in el.iter(T))


def _table(root, *head: str):
    for tbl in root.iter(f"{{{HP}}}tbl"):
        tr = tbl.find(f"{{{HP}}}tr")
        if tr is None:
            continue
        cells = [re.sub(r"\s", "", _text(tc)) for tc in tr.findall(f"{{{HP}}}tc")]
        if all(h in cells for h in head):
            return tbl
    return None


def _top_paras(root) -> list:
    return [p for p in root.iter(f"{{{HP}}}p") if next(p.iterancestors(f"{{{HP}}}tbl"), None) is None]


def _after(paras: list, pred) -> object | None:
    for i, p in enumerate(paras):
        if pred(re.sub(r"\s", "", _text(p))):
            return next((q for q in paras[i + 1:] if _text(q).strip()), None)
    return None


def _cls(s: Summary, b: Building) -> str:
    return b.cls or ("미지정" if s.label == "미지정시설물" else s.cls)


def _cell(tmpl, r: int, c: int, lines: list[str], span: int, height: int, width: int | None = None, colspan: int | None = None):
    tc = rb._make_cell(tmpl, r, lines, span, height)
    tc.find(f"{{{HP}}}cellAddr").set("colAddr", str(c))
    if colspan is not None:
        tc.find(f"{{{HP}}}cellSpan").set("colSpan", str(colspan))
    if width is not None:
        tc.find(f"{{{HP}}}cellSz").set("width", str(width))
    return tc


def _grade_table(tbl, s: Summary) -> None:
    """3.2 등급 현황(10/20 형 표 — 1종·2종·3종·미지정 중 이 보고서에 있는 것만): 위 = 종별마다 한 줄(대상 수·등급별 수), 아래 = 1·2종(양호~불량)·
    3종(A~E)·미지정(A~E) 칸 중 있는 것(등급별 건물 이름). 등급 머리 — 1·2종만이면 양호·보통·미흡·불량 4칸(형 10/16 "2종은 A~B가 없어 — 별개"),
    3종·미지정만이면 A~E등급, 섞이면 A등급(우수)~E등급(불량)(1·2종 양호는 B 칸…). 견본 표(머리 2줄 + 종별 1줄 + 등급 5줄)를 본떠 줄을 다시 만듦."""
    kinds = [k for k in KINDS if any(_cls(s, b) == k for b in s.buildings)] or [_cls(s, Building(name=""))]
    only12 = all(k in ("1종", "2종") for k in kinds)
    mixed = not only12 and any(k in ("1종", "2종") for k in kinds)
    cols = GRADES2 if only12 else GRADES3
    head = [[g] for g in GRADES2] if only12 else [[f"{g}등급", f"({WORD5[g]})"] if mixed else [f"{g}등급"] for g in GRADES3]
    col_of = (lambda b: b.grade) if only12 else (lambda b: TO5.get(b.grade, b.grade))  # noqa: E731
    cells = rb._cells(tbl)
    T = {k: copy.deepcopy(v) for k, v in cells.items()}
    trs = tbl.findall(f"{{{HP}}}tr")
    last = len(trs) - 1
    hgt = lambda k: int(T[k].find(f"{{{HP}}}cellSz").get("height"))  # noqa: E731
    wid = lambda k: int(T[k].find(f"{{{HP}}}cellSz").get("width"))  # noqa: E731
    ng = len(cols)
    gw = sum(wid((1, c)) for c in range(3, 8))
    widths = [gw // ng] * ng
    widths[-1] += gw - sum(widths)
    note_c = 3 + ng
    # 머리 두 줄 — 등급 현황 칸 수·비고 열, 등급 이름
    for tc in trs[0].findall(f"{{{HP}}}tc"):
        a, sp = tc.find(f"{{{HP}}}cellAddr"), tc.find(f"{{{HP}}}cellSpan")
        if a.get("colAddr") == "3":
            sp.set("colSpan", str(ng))
        elif a.get("colAddr") == "8":
            a.set("colAddr", str(note_c))
    rb._set_cell(cells[(1, 2)], f"{s.year}년 {s.half} {s.kind}안전점검")
    for tc in [x for x in trs[1].findall(f"{{{HP}}}tc") if int(x.find(f"{{{HP}}}cellAddr").get("colAddr")) >= 3]:
        trs[1].remove(tc)
    for j, lines in enumerate(head):
        trs[1].append(_cell(T[(1, 3)], 1, 3 + j, lines, 1, hgt((1, 3)), width=widths[j]))
    for tr in trs[2:]:
        tbl.remove(tr)
    # 위 — 종별마다 한 줄
    r, h_top, total = 2, hgt((2, 1)), hgt((0, 0))
    for i, k in enumerate(kinds):
        bs = [b for b in s.buildings if _cls(s, b) == k]
        tr = etree.SubElement(tbl, f"{{{HP}}}tr")
        if i == 0:
            tr.append(_cell(T[(2, 0)], r, 0, [s.category], len(kinds), h_top * len(kinds)))
        tr.append(_cell(T[(2, 1)], r, 1, KIND_LINES[k], 1, h_top))
        tr.append(_cell(T[(2, 2)], r, 2, [str(len(bs))], 1, h_top))
        for j, g in enumerate(cols):
            n = sum(1 for b in bs if col_of(b) == g)
            tr.append(_cell(T[(2, 3)], r, 3 + j, [str(n) if n else "-"], 1, h_top, width=widths[j]))
        tr.append(_cell(T[(2, 8)], r, note_c, ["-"], 1, h_top))
        r += 1
    total += h_top * len(kinds)
    # 아래 — 1·2종 / 3종 / 미지정 칸 중 있는 것(등급별 건물 이름)
    k12 = [k for k in kinds if k in ("1종", "2종")]
    blocks = ([(k12, k12, GRADES2, lambda b: b.grade, lambda g: g)] if k12 else []) + [
        ([k], KIND_LINES[k], GRADES3, lambda b: TO5.get(b.grade, b.grade), lambda g: f"{g}등급") for k in ("3종", "미지정") if k in kinds]
    para = lambda tc: next(tc.iter(f"{{{HP}}}p")).get("paraPrIDRef")  # noqa: E731
    left, center = para(T[(3, 2)]), para(T[(last, 2)])  # 견본: 이름 있는 줄은 왼쪽, "-" 줄은 가운데
    per = max(1, (wid((3, 2)) - 400) // rb.CHAR_W)
    h_one = hgt((last, 2))
    for bi, (ks, label, rows, key, word) in enumerate(blocks):
        end_block = bi == len(blocks) - 1
        bs = [b for b in s.buildings if _cls(s, b) in ks]
        names = {g: ", ".join(b.name for b in bs if key(b) == g) for g in rows}
        hs = [h_one + NAME_STEP * (max(1, -(-len(names[g]) // per)) - 1) for g in rows]
        for j, g in enumerate(rows):
            end = end_block and j == len(rows) - 1  # 맨 아래 줄 — 굵은 밑줄(견본 끝줄 칸)
            tr = etree.SubElement(tbl, f"{{{HP}}}tr")
            if j == 0:
                c0 = _cell(T[(3, 0)], r, 0, label, len(rows), sum(hs))
                if not end_block:  # 견본 왼쪽 칸은 맨 아래까지 닿아 밑줄이 굵음 — 위 칸들은 위 종별 칸 선(왼쪽만 굵음)
                    c0.set("borderFillIDRef", T[(2, 0)].get("borderFillIDRef"))
                tr.append(c0)
            tr.append(_cell(T[(last, 1)] if end else T[(3, 1)], r, 1, [word(g)], 1, hs[j]))
            nm = _cell(T[(last, 2)] if end else T[(3, 2)], r, 2, [names[g] or "-"], 1, hs[j], colspan=ng + 2)
            for q in nm.iter(f"{{{HP}}}p"):
                q.set("paraPrIDRef", left if names[g] else center)
            tr.append(nm)
            r += 1
        total += sum(hs)
    tbl.set("rowCnt", str(r))
    tbl.set("colCnt", str(4 + ng))
    for cz in tbl.iter(f"{{{HP}}}cellzone"):
        cz.set("endRowAddr", str(min(int(cz.get("endRowAddr", "0")), r - 1)))
        cz.set("endColAddr", str(min(int(cz.get("endColAddr", "0")), 3 + ng)))
    tbl.find(f"{{{HP}}}sz").set("height", str(total))


def _simple_rows(tbl, rows: list) -> None:
    """머리줄 + 데이터 줄 표(3.1·3.3) — 첫 데이터 줄 모양으로 rows."""
    cells = rb._cells(tbl)
    n = int(tbl.get("colCnt"))
    tmpl = {c: copy.deepcopy(cells[(1, c)]) for c in range(n)}
    head_h = int(cells[(0, 0)].find(f"{{{HP}}}cellSz").get("height"))
    h = int(cells[(1, 0)].find(f"{{{HP}}}cellSz").get("height"))
    data = [[[str(x)] for x in r] for r in rows]
    rb._fill_rows(tbl, data, tmpl, head_h, rb._row_heights(tmpl, data, h), 0)


def _result_rows(tbl, buildings: list) -> None:
    """3.4 시설물 결과 요약 — 건물마다 점검결과 글머리 수만큼 줄, 번호·이름·전차·금회·보수방안 칸은 세로로 합침(견본 61줄 = 10동 × 6)."""
    cells = rb._cells(tbl)
    first = {c: copy.deepcopy(cells[(1, c)]) for c in range(6)}
    cont = copy.deepcopy(cells[(2, 4)]) if (2, 4) in cells else copy.deepcopy(cells[(1, 4)])
    head_h = int(cells[(0, 0)].find(f"{{{HP}}}cellSz").get("height"))
    width = int(first[4].find(f"{{{HP}}}cellSz").get("width")) - 400
    per = max(1, width // rb.CHAR_W)
    trs = tbl.findall(f"{{{HP}}}tr")
    end_bf = {int(tc.find(f"{{{HP}}}cellAddr").get("colAddr")): tc.get("borderFillIDRef") for tc in trs[-1].findall(f"{{{HP}}}tc")}  # 원본 끝줄 선(밑줄)
    for tr in trs[1:]:
        tbl.remove(tr)
    r, total = 1, head_h
    for i, b in enumerate(buildings, 1):
        lines = [x if x.lstrip().startswith(("ㆍ", "·", "-", "∙")) else f"ㆍ{x}" for x in (b.findings or ["-"])]
        hs = [max(2600, rb.LINE_H * max(1, -(-len(x) // per)) + 500) for x in lines]
        span, block = len(lines), sum(hs)
        for k, line in enumerate(lines):
            tr = etree.SubElement(tbl, f"{{{HP}}}tr")
            if k == 0:
                for c, v in ((0, str(i)), (1, b.name), (2, b.prev or "-"), (3, b.grade or "-")):
                    tr.append(rb._make_cell(first[c], r, [v], span, block))
                tr.append(rb._make_cell(first[4], r, [line], 1, hs[k]))
                tr.append(rb._make_cell(first[5], r, [b.methods or "-"], span, block))
            else:
                tr.append(rb._make_cell(cont, r, [line], 1, hs[k]))
            r += 1
        total += block
    old_last = int(tbl.get("rowCnt")) - 1
    for cz in tbl.iter(f"{{{HP}}}cellzone"):
        if int(cz.get("endRowAddr", "0")) >= old_last:
            cz.set("endRowAddr", str(r - 1))
    tbl.set("rowCnt", str(r))
    tbl.find(f"{{{HP}}}sz").set("height", str(total))
    _result_borders(tbl, end_bf)


def _result_borders(tbl, end_bf: dict) -> None:
    """3.4 표 선(10/19 형 "표 내부 줄 두껍게 되어있는 거 한 줄로, 맨 밑 칸 줄 왜 날라갔는지") — 건물 줄을 첫 데이터 줄 모양(위 = 머리줄 밑 이중선)으로
    복사해 동 사이마다 굵은 선 → 첫 줄 말고는 위 선을 가는 선으로, 원본 끝줄을 지워 밑줄이 없던 것 → 맨 아래에 닿는 칸은 원본 끝줄의 아래 선."""
    b = getattr(rb._TL, "borders", None)
    if b is None:
        return
    last = int(tbl.get("rowCnt")) - 1
    for tc in tbl.iter(f"{{{HP}}}tc"):
        a, sp = tc.find(f"{{{HP}}}cellAddr"), tc.find(f"{{{HP}}}cellSpan")
        r, c, rs = int(a.get("rowAddr")), int(a.get("colAddr")), int(sp.get("rowSpan"))
        bid = tc.get("borderFillIDRef")
        if r > 1:
            bid = b.thin(bid, top=True, bottom=False)
        if r + rs - 1 == last and end_bf.get(c, end_bf.get(min(end_bf, key=lambda k: abs(k - c)) if end_bf else None)):
            bid = b.side_from(bid, "bottom", end_bf.get(c) or end_bf[min(end_bf, key=lambda k: abs(k - c))])
        elif r + rs - 1 < last:
            bid = b.thin(bid, top=False, bottom=True)
        if bid:
            tc.set("borderFillIDRef", bid)


def _conclusion(root, paras: list[str]) -> None:
    """3.6 결언 상자 — 고정 첫 문단("금회 점검은 … 요약하면 다음과 같다.")은 그대로, 그 아래 글을 paras로(문단 모양은 견본 첫 결론 문단)."""
    box = next((tbl for tbl in root.iter(f"{{{HP}}}tbl") if re.sub(r"\s", "", _text(tbl)).startswith("금회점검은")), None)
    if box is None:
        return
    sub = box.find(f".//{{{HP}}}subList")
    ps = sub.findall(f"{{{HP}}}p")
    body = [p for p in ps if re.sub(r"\s", "", _text(p)).startswith(("금번", "이외의", "이 외의"))]
    if not body:
        return
    tmpl = copy.deepcopy(body[0])
    at = list(sub).index(body[0])
    for p in body:
        sub.remove(p)
    for k, text in enumerate(paras or []):
        q = copy.deepcopy(tmpl)
        rb._set_para(q, f"   {text.strip()}", in_table=True)
        sub.insert(at + k, q)


def _trim_tail(root) -> None:
    """결언 상자 뒤 맨 끝 빈 문단(원본 2개)을 뺌 — 결언이 쪽 끝까지 차면 빈 문단만 다음 쪽으로 넘어가 빈 쪽이 생김(10/19 양주덕산초)."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    while len(tops) > 1 and not _text(tops[-1]).strip() and not any(True for _ in tops[-1].iter(f"{{{HP}}}tbl", f"{{{HP}}}pic", f"{{{HP}}}secPr", f"{{{HP}}}ctrl")):
        root.remove(tops.pop())


def trim_box_tail(hwpx: Path) -> bool:
    """결언 상자 안 맨 끝 빈 문단을 뺌(10/30 민재형 나라키움대전센터 "한 줄 때문에 쪽이 늘어남") — 결언이 쪽 끝까지 차면 상자 안 끝 빈 문단만 다음 쪽으로 넘어가
    머리글 + 빈 상자 줄뿐인 쪽이 생김(_trim_tail은 상자 밖 빈 문단만 뺐음). 쪽 끝에 걸릴 때만 부름(평소엔 그 빈 문단이 상자 아래 여백). 뺐으면 True."""
    with zipfile.ZipFile(hwpx) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    name = next(i.filename for i, _ in items if re.match(r"Contents/section0\.xml$", i.filename))
    root = etree.fromstring(next(d for i, d in items if i.filename == name))
    box = next((tbl for tbl in root.iter(f"{{{HP}}}tbl") if re.sub(r"\s", "", _text(tbl)).startswith("금회점검은")), None)
    sub = box.find(f".//{{{HP}}}subList") if box is not None else None
    if sub is None:
        return False
    ps = sub.findall(f"{{{HP}}}p")
    cut = 0
    while len(ps) - cut > 1 and not _text(ps[-1 - cut]).strip() and not any(True for _ in ps[-1 - cut].iter(f"{{{HP}}}tbl", f"{{{HP}}}pic", f"{{{HP}}}ctrl")):
        cut += 1
    if not cut:
        return False
    for p in ps[len(ps) - cut:]:
        sub.remove(p)
    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    tmp = hwpx.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w") as zo:
        for info, d in items:
            zo.writestr(info, data if info.filename == name else d)
    tmp.replace(hwpx)
    return True


def last_page_empty(pdf: Path) -> bool:
    """요약문 PDF 맨 끝 쪽에 머리글(보고서 이름·▣ 요약문·등록기관)만 있나 — 글자 100자 미만이고 쪽이 둘 이상."""
    import pymupdf

    with pymupdf.open(pdf) as d:
        return d.page_count > 1 and len(d[d.page_count - 1].get_text().strip()) < 100


def build(s: Summary, template: Path, out: Path) -> None:
    """요약문 한글(out) — template(정기안전점검_요약문_원본.hwpx)을 s 값으로."""
    with zipfile.ZipFile(template) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    name = next(i.filename for i, _ in items if re.match(r"Contents/section0\.xml$", i.filename))
    root = etree.fromstring(next(d for i, d in items if i.filename == name))
    for t in root.iter(T):  # 머리말 용역명
        if t.text and SAMPLE_TITLE in t.text:
            t.text = t.text.replace(SAMPLE_TITLE, s.title)
    paras = _top_paras(root)
    p = _after(paras, lambda t: t.startswith("2.과업수행기간"))
    if p is not None:
        rb._set_para(p, f" {s.period}")
    cap = next((q for q in paras if re.search(r"<.*등급\s*현황>", _text(q))), None)
    if cap is not None:
        rb._set_para(cap, f"<{s.year}년 {s.half} {s.kind}점검 대상시설물 등급 현황>")
    t31 = _table(root, "구분", "건물명", "준공연도")
    if t31 is not None:
        _simple_rows(t31, [[i, b.name, b.year, b.floors, b.area, b.structure] for i, b in enumerate(s.buildings, 1)])
    t32 = _table(root, "구조물", "대상시설물수")
    if t32 is not None:
        _grade_table(t32, s)
    t33 = _table(root, "번호", "시설물명", "금회등급", "보수방안")
    if t33 is not None:
        _simple_rows(t33, [[i, b.name, b.grade or "-", b.methods or "-", b.prio or "-"] for i, b in enumerate(s.buildings, 1)])
    t34 = _table(root, "번호", "시설물명", "전차등급", "점검결과")
    hname = next((i.filename for i, _ in items if i.filename == "Contents/header.xml"), None)
    bd = Borders(next(d for i, d in items if i.filename == hname).decode("utf-8")) if hname else None
    if t34 is not None:
        with rb.using_borders(bd):
            _result_rows(t34, s.buildings)
    for key, names in (("∙정밀안전점검대상", s.precise), ("∙정밀안전진단대상", s.diag)):
        p = _after(paras, lambda t, key=key: t.startswith(key))
        if p is not None:
            rb._set_para(p, f"      - {', '.join(names) if names else '해당없음'}")
    _conclusion(root, s.conclusion)
    _trim_tail(root)
    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w") as zo:
        for info, d in items:
            if info.filename == name:
                d = data
            elif info.filename == hname and bd is not None:  # 3.4 표 선 모양 더한 것(10/19)
                d = bd.result(d.decode("utf-8")).encode("utf-8")
            zo.writestr(info, d)
    tmp.replace(out)


def add_toc_line(hwpx: Path) -> bool:
    """보고서 목차에 "▣ 요약문"(▣ 시설물의 위치도 및 전경사진 다음) — 이미 있으면 그대로. 고쳤으면 True."""
    with zipfile.ZipFile(hwpx) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    changed = False
    out = []
    for info, d in items:
        if not changed and re.match(r"Contents/section\d+\.xml$", info.filename) and "전경사진".encode() in d:  # 목차 글은 조각으로 나뉘어 있을 수 있어 문단 글로 비교
            root = etree.fromstring(d)
            if any(_text(q).strip() == "▣ 요약문" for q in root.iter(f"{{{HP}}}p")):
                break
            for p in root.iter(f"{{{HP}}}p"):
                if re.sub(r"\s", "", _text(p)) == re.sub(r"\s", "", TOC_AFTER) and next(p.iterancestors(f"{{{HP}}}tc"), None) is not None:
                    q = copy.deepcopy(p)
                    rb._set_para(q, "▣ 요약문", in_table=True)
                    p.addnext(q)
                    changed = True
                    break
            if changed:
                d = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        out.append((info, d))
    if changed:
        tmp = hwpx.with_suffix(".toc.part")
        with zipfile.ZipFile(tmp, "w") as zo:
            for info, d in out:
                zo.writestr(info, d)
        tmp.replace(hwpx)
    return changed


def insert_before_toc(pdf: Path, summary_pdf: Path) -> int:
    """보고서 PDF의 목차 쪽 앞에 요약문 PDF를 끼움(앞 30쪽 안에서 "목 차"로 시작하는 쪽) → 끼운 쪽 수(못 찾으면 0)."""
    import pymupdf

    doc = pymupdf.open(pdf)
    at = next((i for i in range(min(30, doc.page_count)) if re.sub(r"\s", "", doc[i].get_text())[:6].startswith("목차")), None)
    if at is None:
        doc.close()
        return 0
    with pymupdf.open(summary_pdf) as add:
        doc.insert_pdf(add, start_at=at)
        n = add.page_count
    tmp = pdf.with_suffix(".sum.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return n


def fallback_conclusion(s: Summary) -> list[str]:
    """결언 기본 문장(AI 결언이 없을 때 — 견본 문장 모양): 전체 개수·등급별 건물 이름. 종별이 섞이면 동마다 그 등급 말(B등급 / 양호), 좋은 순은 A·B(양호)·C(보통)…"""
    n = len(s.buildings)
    order = sorted(GRADES3 + GRADES2, key=lambda g: (GRADES3.index(TO5.get(g, g)), g in GRADES2))
    word = lambda g: g if g in GRADES2 else f"{g}등급"  # noqa: E731
    ro = lambda w: w + ("로" if (ord(w[-1]) - 0xAC00) % 28 in (0, 8) else "으로")  # 양호로·보통으로·B등급으로  # noqa: E731
    by = {g: [b.name for b in s.buildings if b.grade == g] for g in order}
    got = [g for g in order if by[g]]
    out = [f"금번 {s.year}년 {s.half} 시설물 {s.kind}안전점검 점검결과, {'전체 ' + str(n) + '개 시설물' if n > 1 else '대상 시설물'}에 발생된 손상들은 건조수축, "
           "온도변화에 따른 수축⋅팽창 등에 의해 발생된 것으로 구조안전성에는 문제가 없는 것으로 판단된다. 다만 추후 내구성 확보를 위하여 보수하는 것이 바람직할 것으로 판단된다."]
    if len(got) > 1:
        worst, best = got[-1], got[0]
        out.append(f"금번 점검 시설물 중 {ro(word(worst))} 평가된 {', '.join(by[worst])}은(는) 관리주체가 유지관리계획에 따라 보수를 실시하고, 그 이외 "
                   f"{ro(word(best))} 평가된 시설물({', '.join(by[best])})에 대해서는 보고서에 제시된 공법을 토대로 유지계획 수립 후 유지관리를 시행하는 것이 바람직할 것으로 판단된다.")
    elif got:
        out.append(f"금번 점검 결과 {'시설물 모두 ' if n > 1 else '본 시설물은 '}{ro(word(got[0]))} 평가되었으며, 보고서에 제시된 공법을 토대로 유지계획 수립 후 유지관리를 시행하는 것이 바람직할 것으로 판단된다.")
    out.append("이 외의 시설물에 대해서는 주기적인 점검을 통한 관찰로 유지관리를 실시한다면, 시설물의 사용성에는 문제가 없을 것으로 판단된다.")
    return out
