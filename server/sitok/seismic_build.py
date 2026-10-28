"""내진성능평가 보고서 만들기(2026-10-21 형 "보고서도 만들기 시작") — 1차.

원본 = master "성능평가본문"(견본 삼숭초 교사동 2026.01의 우리 몫: 표지·제출문·참여기술자·목차·결과 요약(결과표·요약문·확인서·체크리스트)·
1장 건물개요·2장 현장조사, 외주 3~7장은 뺌). 회차마다 외주가 준 3~7장 한글(survey.seismic_files.body)을 한글이 직접 우리 한글 끝에 끼워 넣음
(hwp_queue "merge" — 사람이 붙여 넣은 것처럼 쪽 번호·꼬리말이 이어짐, 10/21 시험: PDF로 따로 바꾸면 외주 쪽에 쪽 번호가 없고 "제1장 설계하중"),
외주 장 제목 번호는 fix_vendor_chapters로 3장부터.

채우는 것: 이름·용역명·발주처·주소·날짜(문서 전체), 참여기술자 명단, 결과표 가(일반현황)·사(책임기술자), 1.1 일반사항·1.2 건물규모(아는 칸),
(1) 현장 시험 철근배근 개소, 2.2.2 철근배근 조사결과 표(현장시험 철근탐사 줄 — 18개씩 표 하나)와 조사 수량.
외주 한글이 견본 전체 모양이면(10/21 형 "걔네가 그냥 작성하고 줄 때도 있어서") 결과표 나~마·(2) 내진성능평가 적용·확인서·체크리스트를
외주 것으로 옮기고 3~7장만 잘라 끼움 + 값 검토(server/sitok/seismic_vendor). 나머지(요약문 종합의견·1.2 건물 길이·평면도·1.3·1.4·
2.2.1 부재단면·2.2.3 코어·2.2.4·2.3 외관조사·2.4·2.5·위치도·전경)는 견본 값 그대로 — 알림으로 하나하나 알림(다음 단계에서 채움).
"""
from __future__ import annotations

import copy
import datetime
import re
from pathlib import Path

from server.sitok import rebar_survey as RV
from server.sitok import report_build as rb
from server.sitok.seismic_fill import _set, _t
from server.sitok.wall_build import HP, Hwpx, _tables

SAMPLE_TITLES = ("삼숭초 교사동 내진성능평가 용역", "삼숭초 교사동 내진성능평가용역", "삼숭초교사동 내진성능평가용역")
SAMPLE_NAME = "삼숭초 교사동"
SAMPLE_CLIENT = "경기도동두천양주교육지원청"
SAMPLE_ADDRESS = "경기도 양주시 삼숭로38번길 112"
SAMPLE_PERIOD_KOR = "2025년 10월 24일~2026년 01월 02일"
SAMPLE_PERIOD_DOT = "2025. 10. 24. ~ 2026. 01. 02."
SAMPLE_MONTHS = ("2026년 01월", "2026. 01.", "2026․01", "2026∙01")

NO_FRONT = "결과표 나~마·(2) 내진성능평가 적용·확인서·체크리스트는 외주 몫이라 견본 값을 비우고 노랗게 칠했습니다 — 견본 전체에 외주 몫까지 쓴 한글을 올리면 옮겨 넣습니다"
STILL_SAMPLE = [  # 아직 견본 값 그대로인 곳 — 만들기 알림(나머지는 server/sitok/seismic_fill이 채우고 빈 입력만 알림)
    "요약문 책임기술자 종합의견(견본 글)",
    "1.2 건물 길이·층별 평면도(견본 그림)",
    "2.3 금회 균열 및 기타 결함현황 조사 결과표 — 층별 외관조사망도(견본 그림)",
]


def _date(d: datetime.date | None, kor: bool = False) -> str:
    if not d:
        return "-"
    return f"{d.year}년 {d.month:02d}월 {d.day:02d}일" if kor else f"{d.year}. {d.month:02d}. {d.day:02d}."


def gather(db, r, f) -> dict:
    from core.models_web import SitokContract, TechPerson

    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    sc = (r.survey or {}).get("seismic_contract") or {}  # 내진성능평가 건(10/21 — 용역계약서에서 읽은 값, 건 화면에서 고침)
    rd = r.report_date or r.period_end or datetime.date.today()
    ids = [x for x in [r.chief_id, *(r.participant_ids or [])] if x]
    people = {p.id: p for p in db.query(TechPerson).filter(TechPerson.id.in_(ids))} if ids else {}
    persons = []
    for i, pid in enumerate(ids):
        p = people.get(pid)
        if p:
            qual = ", ".join(x.strip() for x in (p.qualification or "").splitlines() if x.strip())
            grade = f"{p.sitok_field or '건축'}{(p.grade or '').replace('기술자', '').replace('기술인', '')}기술인" if p.grade else (p.sitok_grade or "")
            short = f"{p.sitok_field or '건축'} {(p.grade or '').replace('기술자', '').replace('기술인', '')}".strip() if p.grade else (p.sitok_grade or "")
            persons.append({"role": "사업책임기술자" if i == 0 else "분야별 참여기술자", "name": p.name, "qual": f"{grade} ({qual})" if qual else grade,
                            "duty": "사업책임 기술인" if i == 0 else "현장조사 및 보고서 작성", "grade": short})
    from server.sitok import civil

    amount_k = civil.comma_k(r.amount_k or "")  # 천 단위 쉼표(10/26)
    if not amount_k and c and c.amount:
        amount_k = f"{c.amount / 1000:,.1f}"
    if not amount_k and sc.get("amount"):
        amount_k = f"{int(sc['amount']) / 1000:,.1f}"
    joint = "독자수행 100%"
    if c and c.joint_type and c.joint_type not in ("독자수행", "단독수급"):
        joint = f"{c.joint_type} {c.joint_pct or ''}%".strip()
    elif sc.get("joint") and sc["joint"] not in ("단독계약", "단독", "독자수행"):
        joint = sc["joint"]
    all_rows = RV.normalize((r.survey or {}).get("rebar"))["rows"]
    rows = RV.report_rows(all_rows)  # 결과 있는 줄만·번호 다시(미리 만든 빈 칸 뺌, 10/22)
    title = (c.title if c and c.title else "") or sc.get("title") or f"{f.name} 내진성능평가 용역"
    return {"name": f.name, "title": title.strip(),
            "client": (sc.get("client") or f.owner_name or "").strip() or "-", "address": f.address or "-",
            "period_start": r.period_start, "period_end": r.period_end, "month": rd, "persons": persons, "amount_k": amount_k or "-",
            "joint": joint, "bid": (c.bid_method if c else "") or sc.get("method") or "수의계약", "use": f.use_type or f.main_use or "-", "class_no": f.class_no or "-",
            "grade": f.safety_grade or "-", "completion": f.completion_date, "above": f.floors_above or 0, "below": f.floors_below or 0,
            "area": f.total_area, "height": f.max_height, "structure": f.structure or "-", "rebar": rows, "rebar_empty": len(all_rows) - len(rows),
            "rebar_total": len(all_rows) if RV.normalize((r.survey or {}).get("rebar"))["seeded"] else _rebar_default(f)}  # 철근탐사 칸 수(형이 정한 수량)


def replace_globals(doc: Hwpx, d: dict) -> int:
    n = 0
    for t in SAMPLE_TITLES:
        n += doc.replace_all(t, d["title"])
    n += doc.replace_all(SAMPLE_NAME, d["name"])
    n += doc.replace_all(SAMPLE_NAME.replace(" ", ""), d["name"])
    n += doc.replace_all(SAMPLE_CLIENT, d["client"])
    n += doc.replace_all(SAMPLE_ADDRESS, d["address"])
    if d["period_start"] and d["period_end"]:
        n += doc.replace_all(SAMPLE_PERIOD_KOR, f"{_date(d['period_start'], True)}~{_date(d['period_end'], True)}")
        n += doc.replace_all(SAMPLE_PERIOD_DOT, f"{_date(d['period_start'])} ~ {_date(d['period_end'])}")
    m = d["month"]
    for old, new in zip(SAMPLE_MONTHS, (f"{m.year}년 {m.month:02d}월", f"{m.year}. {m.month:02d}.", f"{m.year}․{m.month:02d}", f"{m.year}∙{m.month:02d}")):
        n += doc.replace_all(old, new)
    return n


def fill_persons(root, d: dict) -> int:
    t = next((x for x in _tables(root) if (x.get("rowCnt"), x.get("colCnt")) == ("5", "6") and "참여기간" in rb._n(rb._cell_text(rb._cells(x).get((0, 3), x)))), None)
    if t is None or not d["persons"]:
        return 0
    cells = rb._cells(t)
    rows = d["persons"][:4]
    period = f"{_date(d['period_start'])} ~ {_date(d['period_end'])}" if d["period_start"] and d["period_end"] else "-"
    for i in range(4):
        p = rows[i] if i < len(rows) else None
        r = i + 1
        _set(cells, (r, 1), p["name"] if p else "-")
        _set(cells, (r, 2), p["qual"] if p else "-")
        _set(cells, (r, 3), period if p else "-")
        _set(cells, (r, 4), p["duty"] if p else "-")
    return len(rows)


def fill_result_ga(root, d: dict) -> int:
    n = 0
    for t in _tables(root):
        cells = rb._cells(t)
        if t.get("colCnt") != "13" or not rb._n(rb._cell_text(cells.get((0, 0), t))).startswith("가.일반현황"):  # 외주 표로 바뀌면 줄 수가 다를 수 있음
            continue
        area = f"{d['area']:,.2f}㎡" if d["area"] else "-"
        floors = (f"지하{d['below']}층/" if d["below"] else "") + f"지상{d['above']}층"
        vals = {(1, 1): d["title"], (2, 1): d["client"], (3, 1): d["joint"], (3, 9): d["bid"], (4, 1): d["name"], (4, 9): d["use"],
                (4, 12): d["class_no"], (5, 1): f"{d['completion'].year}년" if d["completion"] else "-", (5, 9): d["amount_k"], (5, 12): d["grade"],
                (6, 1): d["address"], (6, 9): f"{floors} (연면적: {area})"}
        if d["period_start"] and d["period_end"]:
            vals[(1, 9)] = f"{_date(d['period_start'], True)}~{_date(d['period_end'], True)}"
        for rc, v in vals.items():
            _set(cells, rc, v)
        n += 1
    return n


def fill_result_people(root, d: dict) -> int:
    """결과표 "사. 책임(참여)기술자 현황"(라~사 표 안, 우리 몫) — 머리 줄(구분·성명·과업참여기간·기술등급) 칸 위치로, 남는 줄은 비움.
    구분 칸("사업책임기술자"·"분야별 참여기술자")은 고정 글 — 다시 써서 '우리가 쓴 칸'으로(10/28 사용자 "여긴 책임기술자 참여기술자 고정" — 견본 값 지우기가 빈칸·노랑으로 만들었음)."""
    period = f"{_date(d['period_start'])} ~ {_date(d['period_end'])}" if d["period_start"] and d["period_end"] else "-"
    for t in _tables(root):
        cells = rb._cells(t)
        if not rb._n(rb._cell_text(cells.get((0, 0), t))).startswith("라.내진성능"):
            continue
        head = next((r for (r, c), x in cells.items() if c == 0 and rb._n(rb._cell_text(x)) == "사업책임기술자"), None)
        if head is None:
            return 0
        for r, c in ((head, 0), (head + 1, 0)):  # 고정 이름 칸 — 틀 글 그대로 다시
            if (r, c) in cells and rb._cell_text(cells[(r, c)]).strip():
                _set(cells, (r, c), rb._cell_text(cells[(r, c)]))
        if not d["persons"]:
            return 1
        hdr = {rb._n(rb._cell_text(x)): c for (r, c), x in cells.items() if r == head - 1}
        cn, cp, cg = hdr.get("성명"), hdr.get("과업참여기간"), hdr.get("기술등급")
        if cn is None:
            return 0
        rows = []
        r = head
        while (r, cn) in cells and not rb._n(rb._cell_text(cells.get((r, 0), t))).startswith("사.사용"):
            rows.append(r)
            r += 1
        for k, r in enumerate(rows):
            p = d["persons"][k] if k < len(d["persons"]) else None
            _set(cells, (r, cn), p["name"] if p else "")
            if cp is not None:
                _set(cells, (r, cp), period if p else "")
            if cg is not None:
                _set(cells, (r, cg), p["grade"] if p else "")
        return 1
    return 0


def _rebar_default(f) -> int:
    from server.sitok import seismic_docs as SD

    return sum(RV.default_plan(SD.sample_floors(f, "rebar")).values())


def fill_field_summary(root, d: dict) -> int:
    """(1) 현장 시험 및 분석 — 조사·시험항목 표의 철근배근 조사개소 = 철근탐사 칸 수(형이 정한 수량, 10/22)."""
    n = d.get("rebar_total") or len(d["rebar"])
    if not n:
        return 0
    for t in _tables(root):
        cells = rb._cells(t)
        if rb._n(rb._cell_text(cells.get((0, 1), t))) != "조사·시험항목":
            continue
        for (r, c), x in cells.items():
            if c == 1 and rb._n(rb._cell_text(x)) == "철근배근":
                _set(cells, (r, 3), f"{n}EA")
                return 1
    return 0


def fill_chapter1(root, d: dict) -> int:
    n = 0
    t = next((x for x in _tables(root) if (x.get("rowCnt"), x.get("colCnt")) == ("9", "6") and "건물명" in rb._n(rb._cell_text(rb._cells(x).get((0, 1), x)))), None)
    if t is not None:
        cells = rb._cells(t)
        ref = d["period_start"] or datetime.date.today()  # 경과년수 = 조사(착수) 연도 기준(견본 2025 착수 − 2005 = 20년)
        age = ref.year - d["completion"].year if d["completion"] else None
        _set(cells, (0, 3), d["name"])
        _set(cells, (1, 3), d["address"])
        _set(cells, (2, 3), d["structure"])
        _set(cells, (3, 3), f"{d['completion'].year}년, 경과년수 {age}년" if d["completion"] else "-")
        _set(cells, (5, 3), d["use"])
        n += 1
    t = next((x for x in _tables(root) if (x.get("rowCnt"), x.get("colCnt")) == ("8", "4") and "층수" in rb._n(rb._cell_text(rb._cells(x).get((0, 1), x)))), None)
    if t is not None:
        cells = rb._cells(t)
        _set(cells, (0, 3), (f"지하 {d['below']}층, " if d["below"] else "") + f"지상 {d['above']}층")
        _set(cells, (1, 3), "유" if d["below"] else "무")
        if d["height"]:
            _set(cells, (2, 3), f"{d['height']:g}m")
        if d["area"]:
            _set(cells, (5, 3), f"{d['area']:,.2f}㎡")
        _set(cells, (7, 0), f"【 {d['name']} 】")
        n += 1
    return n


def _rebar_tables(root) -> list:
    return [x for x in _tables(root) if x.get("colCnt") == "7" and rb._n(rb._cell_text(rb._cells(x).get((0, 0), x))) == "시험번호"]


def fill_rebar(root, d: dict, warn: list) -> int:
    """2.2.2 철근배근 조사결과 — 견본 첫 표 하나에 시험 전부(머리 줄 + 시험마다 두 줄, 쪽을 넘기면 머리 줄 반복 — 10/26 민재형 "한 표로", 전엔 18개씩 표를 나눔),
    남는 견본 표·제목·주석과 그 앞 빈 줄은 지움. 조사 수량 칸도."""
    rows = d["rebar"]
    if d.get("rebar_empty"):
        warn.append(f"철근탐사 빈 칸 {d['rebar_empty']}개(조사 결과 없음)는 보고서에서 뺐습니다 — 시험번호는 차례로 다시")
    tables = _rebar_tables(root)
    if not tables:
        warn.append("원본에서 철근배근 조사결과 표를 못 찾았습니다")
        return 0
    if not rows:
        warn.append("철근탐사 결과가 없어 2.2.2 철근배근 표는 빈칸입니다(🧪 현장시험)")
    from server.sitok.seismic_todo import paint_empty
    lines = RV.table_rows(rows) if rows else [[""] * 7, [""] * 7]  # 없으면 빈 시험 한 줄(두 줄)
    chunks = [lines]
    paras = [next(t.iterancestors(f"{{{HP}}}p")) for t in tables]
    # 표마다 앞(제목 "【 철근배근 조사결과 】")·뒤(주석) 문단 묶음 — 첫 표 것을 틀로
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]

    def block(p):
        i = tops.index(p)
        head = tops[i - 1] if i and "철근배근조사결과" in rb._n("".join(x.text or "" for x in tops[i - 1].iter(f"{{{HP}}}t"))) else None
        note = tops[i + 1] if i + 1 < len(tops) and "측정위치" in rb._n("".join(x.text or "" for x in tops[i + 1].iter(f"{{{HP}}}t"))) else None
        return [x for x in (head, p, note) if x is not None]

    tpl = [copy.deepcopy(x) for x in block(paras[0])]
    for p in paras[1:]:  # 견본 2·3번 표 묶음은 지움(앞 빈 줄도 — 첫 표 뒤에 빈 줄만 남지 않게)
        from server.sitok.seismic_fill import _drop_empty_before

        for x in block(p):
            if x.getparent() is not None:
                _drop_empty_before(x)
                x.getparent().remove(x)
    anchor = block(paras[0])[-1]
    first_block = block(paras[0])
    for k, chunk in enumerate(chunks):
        if k == 0:
            blk = first_block
        else:
            blk = [copy.deepcopy(x) for x in tpl]
            for x in blk:
                rb._new_ids(x)
                anchor.addnext(x)
                anchor = x
            blk[0].set("pageBreak", "1")
        t = next(x for b in blk for x in b.iter(f"{{{HP}}}tbl") if rb._n(rb._cell_text(rb._cells(x).get((0, 0), x))) == "시험번호")
        have = (int(t.get("rowCnt")) - 1) // 2
        want = len(chunk) // 2
        if want > have:
            rb._dup_rows(t, 1 + (have - 1) * 2, 2, want - have)
        elif want < have:
            rb._del_rows(t, 1 + want * 2, (have - want) * 2)
        if want > 18:  # 한 쪽(견본 18개)을 넘기면 줄 단위로 나뉘게(글자처럼 취급도 끔)
            from server.sitok.seismic_fill import split_pages

            split_pages(t, 1)
        cells = rb._cells(t)
        for j, line in enumerate(chunk):
            r = 1 + j
            for col, v in enumerate(line):
                if j % 2 == 1 and col in (0, 1):  # 시험번호·측정위치는 두 줄 합친 칸(윗줄에만)
                    continue
                _set(cells, (r, col), v)
        from server.sitok.seismic_fill import even_col_lines, even_head_line, thick_bottom

        thick_bottom(t)  # 표 끝 굵은 선(10/22)
        even_head_line(t, 1)  # 머리 줄 아래·세로선 고르게(10/27)
        even_col_lines(t)
        if not rows:
            paint_empty(t, 1)  # 결과가 없어 비운 줄 — 노랑(10/26)
    # 조사 수량 — "금회 조사 수량 = N개소"(철근 표 앞의 수량 표: 두 번째 2×4)
    qty = [x for x in _tables(root) if (x.get("rowCnt"), x.get("colCnt")) == ("2", "4") and "금회조사수량" in rb._n(rb._cell_text(rb._cells(x).get((0, 3), x)))]
    if len(qty) >= 2:
        _set(rb._cells(qty[1]), (1, 3), f"금회 조사 수량 = {d.get('rebar_total') or len(rows)}개소")  # 칸 수(10/22)
    return len(rows)


def fix_vendor_chapters(path: Path, ours_paras: int, first: int = 3) -> int:
    """합친 한글에서 외주 장 번호를 3·4·5…로 — 외주 파일은 장마다 번호 정의가 제각각(3장 1부터, 4·5장은 한 정의를 3부터 함께 …)이라 끼워 넣으면
    "제1장 설계하중"이 됨(10/21 시험). 외주 쪽(우리 문단 수 뒤)에서 쓰는 번호 정의마다 복제해 첫 수준 시작값 = 그 정의를 쓰는 첫 장 번호로 하고,
    그 정의를 쓰는 외주 문단(장 제목·소제목 함께 — 장 제목만 옮기면 소제목이 "3.11"이 됨)을 복제본으로. 우리 쪽 번호는 안 건드림. 고친 장 수."""
    HH = "http://www.hancom.co.kr/hwpml/2011/head"
    doc = Hwpx(path)
    hdr = doc.header
    pps = {x.get("id"): x for x in hdr.iter(f"{{{HH}}}paraPr")}
    nums_box = next(hdr.iter(f"{{{HH}}}numberings"), None)
    if nums_box is None:
        return 0
    nums = {x.get("id"): x for x in nums_box}
    tops = [p for p in doc.root if p.tag == f"{{{HP}}}p"]
    vend = tops[ours_paras:]

    def heading(p):
        pp = pps.get(p.get("paraPrIDRef"))
        hd = pp.find(f"{{{HH}}}heading") if pp is not None else None
        return hd if hd is not None and hd.get("type") == "NUMBER" and hd.get("idRef") in nums else None

    chapter = first - 1
    clone_of: dict[str, str] = {}  # 원래 번호 정의 → 복제본
    pp_of: dict[str, str] = {}  # 원래 문단 모양 → 복제본(heading idRef만 바꿈)
    fixed = 0
    for p in vend:
        hd = heading(p)
        if hd is None:
            continue
        old = hd.get("idRef")
        if hd.get("level") == "0" and "".join(x.text or "" for x in p.iter(f"{{{HP}}}t")).strip():
            chapter += 1
            if old not in clone_of:  # 이 정의를 쓰는 첫 장 — 복제해 첫 수준 시작값 = 이 장 번호
                num = copy.deepcopy(nums[old])
                nid = str(max(int(x.get("id")) for x in nums_box) + 1)
                num.set("id", nid)
                for ph in num.iter(f"{{{HH}}}paraHead"):
                    if ph.get("level") == "1":
                        ph.set("start", str(chapter))  # 10/21 시험: 보이는 번호 = paraHead 시작값
                nums_box.append(num)
                nums_box.set("itemCnt", str(len(nums_box)))
                clone_of[old] = nid
            fixed += 1
        if old not in clone_of:  # 장 제목보다 앞에 나온 소제목 — 그대로
            continue
        key = p.get("paraPrIDRef")
        if key not in pp_of:
            new_pp = doc.clone_parapr(key)
            pp2 = next(x for x in hdr.iter(f"{{{HH}}}paraPr") if x.get("id") == new_pp)
            pp2.find(f"{{{HH}}}heading").set("idRef", clone_of[old])
            pps[new_pp] = pp2
            pp_of[key] = new_pp
        p.set("paraPrIDRef", pp_of[key])
    doc.save(path, drop_unused=False)
    return fixed


def merge_vendor(ours: Path, vendor: Path, dest: Path) -> int:
    """우리 1~2장 한글 끝에 외주 3~7장을 한글이 직접 끼워 넣음(hwp_queue "merge" — 쪽 나눔 뒤 파일 끼워 넣기).
    10/27 밤부터 **외주 구역 설정 유지**(keep_section=1 — 외주 장은 제 용지 여백(10·8·6·10mm)·쪽 모양 그대로 둘째 구역으로, 쪽 번호·꼬리말은 우리 것이 이어짐):
    우리 틀이 12mm 여백이 되면서 외주 장에 우리 여백을 씌우면 한 쪽짜리 표·그림이 넘쳐 빈 쪽이 10곳 넘게 생김(삼숭초 134 → 180쪽, 구역 유지는 149쪽·외주 78쪽 그대로).
    장 번호는 외주 번호 정의가 우리 1·2장에 이어져 3장부터(시험 확인, fix_vendor_chapters는 구역 하나로 합칠 때만 필요했음 — 지금은 손댈 문단이 없어 0).
    쪽 나눔 뒤 구역이 바뀌어 빈 쪽이 하나 생기는 것은 우리 구역 끝 쪽 나눔 문단을 풀어 없앰(_unbreak_tail). 고친 장 수."""
    import zipfile

    from server.contract_docs import hwp_queue

    data = vendor.read_bytes()
    if vendor.suffix.lower() == ".hwp":
        data = hwp_queue.convert_via_worker(data, ".hwp", to="hwpx", wait=600)
    merged = hwp_queue.convert_via_worker(ours.read_bytes(), ".hwpx", to="merge", add=data, keep_section=1, wait=1200)
    dest.write_bytes(merged)
    _unbreak_tail(dest)
    with zipfile.ZipFile(ours) as z:
        from lxml import etree

        root = etree.fromstring(z.read(rb._sections(z)[0]))
        n0 = len([p for p in root if p.tag == f"{{{HP}}}p"])
    return fix_vendor_chapters(dest, n0)


def _unbreak_tail(path: Path) -> bool:
    """합친 한글 첫 구역 끝의 빈 쪽 나눔 문단(끼워 넣기 전 BreakPage) — 구역이 바뀌면 어차피 새 쪽이라 빈 쪽 하나가 생김 → 쪽 나눔을 풂. 풀었으면 True."""
    import zipfile

    from lxml import etree

    with zipfile.ZipFile(path) as z:
        names = rb._sections(z)
        if len(names) < 2:
            return False
        root = etree.fromstring(z.read(names[0]))
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    tail = tops[-1] if tops else None
    from server.sitok.seismic_fill import _empty_para

    if tail is None or tail.get("pageBreak") != "1" or not _empty_para(tail):
        return False
    tail.set("pageBreak", "0")
    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zout.writestr(info, data if info.filename == names[0] else zin.read(info.filename))
    tmp.replace(path)
    return True


SEISMIC_TOP = 49  # 쪽 검사 본문 시작(pt) — 내진 머리말 선 47pt(시특법·옹벽은 85pt 근처라 pagecheck 기본 70), 원본 틀 여백 위 10·머리말 8mm 기준(page_marks가 틀에서 다시 잼)
SEISMIC_FOOT = 41  # 쪽 검사 꼬리말 자리 = 쪽 아래에서(pt) — 내진 꼬리말 선 801pt(쪽 841pt), pagecheck 기본 63은 778pt 아래 본문 줄을 못 봄(10/27)


def page_marks(root) -> tuple[int, int]:
    """쪽 검사 기준(본문 시작 y, 꼬리말 자리)을 틀의 용지 여백에서 — 머리말 선은 위 여백 + 18.5pt(머리말 글 높이), 본문은 위 + 머리말 여백부터 → 그 사이,
    꼬리말 선은 아래 여백 + 12.7pt 위(10/27 실측: 여백 10·8·6·10mm → 선 47·본문 52·꼬리말 선 801pt = (49, 41), 12mm → 52·68·795pt = (60, 46)).
    여백 12mm 틀(민재형 10/27)과 옛 틀 모두 맞게 — 못 읽으면 옛 값."""
    pg = next(root.iter(f"{{{HP}}}pagePr"), None)
    m = pg.find(f"{{{HP}}}margin") if pg is not None else None
    if m is None:
        return SEISMIC_TOP, SEISMIC_FOOT
    top, head, bottom = (int(m.get(k) or 0) / 100 for k in ("top", "header", "bottom"))
    return round((top + 18.5 + top + head) / 2), int(bottom + 12.7)


def _tidy(hwpx: Path, pdf: Path, say=None, sections_from: int = 1, after: str | None = None, marks: tuple[int, int] | None = None) -> list[str]:
    """애매한 넘침 정리(10/26 사용자 "산안·시특·내진·결함 전부" — pagecheck.tidy_checked, 시특법과 같은 규칙·안전장치). 못 하면 그대로."""
    import traceback

    from server.contract_docs import hwp_queue
    from server.sitok import pagecheck

    def render(hx: Path, out: Path) -> None:
        if say:
            say("애매하게 넘친 쪽 정리해서 다시 PDF로…")
        out.write_bytes(hwp_queue.convert_via_worker(hx.read_bytes(), ".hwpx", wait=1500))

    try:
        with pagecheck.top_at(*(marks or (SEISMIC_TOP, SEISMIC_FOOT))):  # 내진은 머리말 선이 47pt — 본문 52pt부터, 꼬리말 선 801pt(10/27), 12mm 틀은 page_marks
            return pagecheck.tidy_checked(hwpx, pdf, render, sections_from=sections_from, after=after, split_tails=True)  # 시안 2(10/27)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return []


def _push_lonely(hwpx: Path, pdf: Path, say=None, after: str | None = None, marks: tuple[int, int] | None = None) -> list[str]:
    """제목·표 이름만 쪽 끝 → 다음 쪽(10/27 사용자 — 민재형이 정한 곳 말고는 이어 붙이되 제목만 걸리면 넘김, pagecheck.push_lonely). 넘기면 다시 PDF, 최대 3번. 못 하면 그대로."""
    import traceback

    from server.contract_docs import hwp_queue
    from server.sitok import pagecheck

    done: list[str] = []
    try:
        for _ in range(3):
            with pagecheck.top_at(*(marks or (SEISMIC_TOP, SEISMIC_FOOT))):
                got = pagecheck.push_lonely(hwpx, pdf, sections_from=0, after=after)
            if not got:
                break
            done += got
            if say:
                say("쪽 끝에 걸린 제목 넘겨서 다시 PDF로…")
            pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    if done:
        print("[제목 넘김]", hwpx.name, "—", " · ".join(done), flush=True)
    return done


def _line_check(pdf: Path, label: str = "본문") -> list[str]:
    """표 선 굵기 검사(pagecheck.line_warnings, 10/27 사용자 "선 굵기 안 맞는 것 — 이런 일 없게") — 우리 쪽만(외주 장 = 2장 간지 뒤 처음 "제3장"이 나오는 쪽부터는 뺌, 도면 얹기 전 PDF). 경고 글."""
    import traceback

    import pymupdf

    from server.sitok import pagecheck

    try:
        with pymupdf.open(pdf) as doc:
            texts = [re.sub(r"\s", "", pg.get_text()) for pg in doc]
        s2 = next((i for i, t in enumerate(texts) if t.startswith("제2장현장조사2.1")), None)  # 2장 간지(목차는 그 앞)
        end = next((i for i in range(s2 + 1, len(texts)) if "제3장" in texts[i]), len(texts)) if s2 is not None else len(texts)
        return pagecheck.line_check(pdf, range(end), label)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return []


def _vendor_chapter_check(pdf: Path) -> list[str]:
    """외주 장 제목 번호 확인 — 2장 간지 뒤 "제N장" 제목이 3·4·5…로 이어지지 않으면 경고(구역 유지 끼워 넣기에서 번호 정의가 안 이어진 경우)."""
    import pymupdf

    try:
        firsts, s2 = [], None
        with pymupdf.open(pdf) as doc:
            for i, pg in enumerate(doc):
                if s2 is None and re.sub(r"\s", "", pg.get_text()).startswith("제2장현장조사2.1"):
                    s2 = i
                lines = sorted((ln["bbox"][1], "".join(s["text"] for s in ln["spans"]).strip()) for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", []))
                lines = [t for y, t in lines if t and y > 60]  # 머리말("… 제2장 현장조사") 아래 첫 글줄
                firsts.append(re.sub(r"\s", "", lines[0]) if lines else "")
        if s2 is None:
            return []
        nums = []
        for t in firsts[s2 + 1:]:
            m = re.match(r"^제(\d+)장", t)  # 간지·장 제목 쪽
            if m and (not nums or int(m.group(1)) != nums[-1]):
                nums.append(int(m.group(1)))
        nums = [n for n in nums if n > 2]  # 2장 본문 첫 쪽도 "제2장 현장조사"로 시작 — 우리 장은 뺌
        if nums and nums[0] != 3:
            return [f"외주 장 번호가 제{nums[0]}장부터입니다(3장이어야 함) — 외주 한글의 번호 정의를 확인해 주세요"]
    except Exception:  # noqa: BLE001
        pass
    return []


def _fix_blank_pages(hwpx: Path, pdf: Path, say=None, marks: tuple[int, int] | None = None) -> list[str]:
    """꽉 찬 표 뒤 문단 끝만 다음 쪽으로 넘어가 생긴 빈 쪽(10/27 12mm 삼숭초 — 체크리스트 D 표가 외주 값으로 두 줄 칸이 늘어 쪽을 꽉 채움) →
    앞 쪽 표의 칸 빈 여백(글은 그대로)을 두 줄 남짓 줄이고 다시 PDF, 쪽이 안 줄면 되돌림. 우리 구역만(외주 장은 그대로). 고친 설명."""
    import traceback

    import pymupdf

    from server.contract_docs import hwp_queue
    from server.sitok import pagecheck
    from server.sitok import report_build as rb

    HH = "http://www.hancom.co.kr/hwpml/2011/head"
    try:
        with pagecheck.top_at(*(marks or (SEISMIC_TOP, SEISMIC_FOOT))):
            bodies = pagecheck._pages(pdf)[0]
        blanks = [i for i in range(1, len(bodies)) if not bodies[i][0] and bodies[i][1] <= 0 and bodies[i - 1][0] and bodies[i - 1][1] > bodies[i - 1][2] - 60]
        if not blanks:
            return []
        doc = Hwpx(hwpx)
        roots = {"s0": doc.root}
        done = []
        for i in blanks:
            lines = [t for _, _, t in bodies[i - 1][0] if len(pagecheck._key(t)) >= 4]
            if not lines:
                continue
            first = max(lines, key=len)
            k = sum(1 for j in range(i - 1) if any(pagecheck._key(first) == pagecheck._key(t) for _, _, t in bodies[j][0]))
            tbl = pagecheck._overflow_target(roots, first, k, rb)
            if tbl is None or int(tbl.get("rowCnt") or 1) < 2:
                continue
            got = pagecheck._squeeze_table(tbl, rb.LINE_H * 2, rb)  # ① 칸 빈 여백(글은 그대로) — 체크리스트 표는 여유가 거의 없음
            p = tbl
            while not (p.tag == f"{{{HP}}}p" and p.getparent() is doc.root):
                p = p.getparent()
            pp = next((x for x in doc.header.iter(f"{{{HH}}}paraPr") if x.get("id") == p.get("paraPrIDRef")), None)
            ls = pp.find(f"{{{HH}}}lineSpacing") if pp is not None else None
            if ls is not None and not (ls.get("type") == "PERCENT" and int(ls.get("value") or 0) <= 100):  # ② 표 문단 줄 간격 160 → 100%(문단 끝 표시 줄이 작아짐 — 10/27 시험: 빈 쪽 없어짐, 표 모양 그대로)
                nid = doc.clone_parapr(p.get("paraPrIDRef"))
                ls2 = next(x for x in doc.header.iter(f"{{{HH}}}paraPr") if x.get("id") == nid).find(f"{{{HH}}}lineSpacing")
                ls2.set("type", "PERCENT")
                ls2.set("value", "100")
                p.set("paraPrIDRef", nid)
                got += 1
            if got:
                done.append(f"{i + 1}쪽 빈 쪽 → 앞 표 문단 줄 간격 100%·칸 여백 {got // 100}pt")
        if not done:
            return []
        snap = hwpx.read_bytes()
        doc.save(hwpx, drop_unused=False)
        if say:
            say("빈 쪽 없애고 다시 PDF로…")
        tmp = pdf.with_name(pdf.stem + "_빈쪽.pdf")
        tmp.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
        with pymupdf.open(tmp) as d:
            n2 = len(d)
        if n2 >= len(bodies):
            hwpx.write_bytes(snap)
            tmp.unlink(missing_ok=True)
            print(f"[빈 쪽 정리 되돌림] {hwpx.name}: 쪽 {len(bodies)}→{n2}", flush=True)
            return []
        tmp.replace(pdf)
        print(f"[빈 쪽 정리] {hwpx.name}: 쪽 {len(bodies)}→{n2} — {' / '.join(done)}", flush=True)
        return done
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return []


def _front_layout(root) -> int:
    """외주 견본 전체 파일의 앞 문단((2) 내진성능평가 적용~체크리스트)을 그대로 옮겨 온 뒤 우리 틀의 쪽 나눔 규칙을 다시(10/27 — 옮겨 온 문단엔 fix_seismic_master ④·⑤가
    없어 12mm에서 모델링 그림만 혼자 한 쪽·체크리스트 표지 서명 줄이 다음 쪽으로): (2) 내진성능평가 적용·다. 평가방법 적용기준은 늘 새 쪽(앞 빈 줄 지움),
    체크리스트 표지 날짜 앞 빈 줄은 3개까지. 고친 곳 수."""
    from server.sitok.seismic_fill import _empty_para

    n = 0
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    start = next((k for k, p in enumerate(tops) if rb._n(_t(p)) == "내진성능평가적용"), None)  # 옮겨 온 범위 = (2)부터(목차에도 같은 글이 있음)
    if start is None:
        return 0
    exact = ("내진성능평가적용", "평가방법적용기준", "내진성능평가결과")
    prefix = ("붙임(1-1)내진성능평가확인서", "b.기존학교시설내진성능평가및보강체크리스트", "검토항목검토내용보고서페이지적합여부A.", "검토항목검토내용보고서페이지적합여부E.")
    blank_before = ("검토항목검토내용보고서페이지적합여부D.",)  # 쪽 나눔은 없이(앞 표가 꽉 찬 쪽) 앞 빈 줄만
    for p in tops[start:]:
        text = rb._n(_t(p))
        pb = text in exact or text.startswith(prefix)
        if not pb and not text.startswith(blank_before):
            continue
        if pb and p.get("pageBreak") != "1":
            p.set("pageBreak", "1")
            n += 1
        q = p.getprevious()
        while q is not None and q.tag == f"{{{HP}}}p" and _empty_para(q):
            q.getparent().remove(q)
            q = p.getprevious()
            n += 1
    sign = next((t for t in root.iter(f"{{{HP}}}tbl") if (t.get("rowCnt"), t.get("colCnt")) == ("1", "8") and rb._n(_t(t)).startswith("책임자소속")), None)
    if sign is not None:
        p = sign
        while not (p.tag == f"{{{HP}}}p" and p.getparent() is root):
            p = p.getparent()
        date = p.getprevious()
        while date is not None and not _t(date):
            date = date.getprevious()
        if date is not None and re.match(r"^\d{4}년\d{1,2}월일?$", rb._n(_t(date))):
            blanks = []
            q = date.getprevious()
            while q is not None and q.tag == f"{{{HP}}}p" and _empty_para(q):
                blanks.append(q)
                q = q.getprevious()
            for b in blanks[3:]:  # 날짜에서 먼 것부터 — 3개 남김
                b.getparent().remove(b)
                n += 1
    return n


def _merge_masonry(hwpx: Path, pdf: Path, say=None, title: str = "조적벽치수및상태조사결과표") -> int:
    """조적벽 결과표 층·구분 세로 합치기(10/27 사용자) — PDF로 쪽마다 줄 수를 세어 쪽 경계에서 끊고(다음 쪽 첫 줄에 층·구분 다시) 합친 뒤 다시 PDF.
    쪽 정리·제목 넘김이 끝난 뒤(합치기 전 모양 그대로 쪽이 나뉘므로 쪽 경계는 안 바뀜). 못 하면 그대로."""
    import traceback

    from server.contract_docs import hwp_queue
    from server.sitok import seismic_fill

    try:
        doc = Hwpx(hwpx)
        if not seismic_fill.masonry_tables(doc.root):
            return 0
        cuts = seismic_fill.masonry_cuts(doc.root, pdf, title)
        with seismic_fill.borders_for(doc):
            n = seismic_fill.merge_masonry(doc.root, cuts)
        if not n:
            return 0
        doc.save(hwpx, drop_unused=False)
        if say:
            say("조적벽 결과표 층·구분 칸 합쳐서 다시 PDF로…")
        pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
        print("[조적벽 합치기]", hwpx.name, n, "묶음", "쪽 경계 끊음" if cuts else "끊을 곳 못 찾음(통째로)", [sorted(c) for c in cuts or []], flush=True)
        return n
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 0


def build(db, r, f, folder: Path, say=None) -> tuple[Path, Path, list[str], int]:
    import pymupdf

    from core.stored_path import to_full
    from server.contract_docs import hwp_queue
    from server.sitok import master

    from server.sitok import seismic_vendor as SV

    say = say or (lambda m: None)
    folder.mkdir(parents=True, exist_ok=True)
    src = master.master_path("성능평가본문")
    if not src.exists():
        raise ValueError("내진성능평가 본문 원본이 없습니다(보고서 자동화 설정 > 원본).")
    say("값 모으는 중…")
    d = gather(db, r, f)
    warn: list[str] = []
    doc = Hwpx(src)
    root = doc.root
    base = f"{r.year}년 내진성능평가 보고서_{f.name}"
    files = (r.survey or {}).get("seismic_files") or {}
    body = Path(to_full(files["body"])) if files.get("body") else None
    chapters = None
    checks: list[str] = []
    front_taken, vendor_text = False, ""
    if body is not None and body.exists():
        say("외주 한글 살피는 중…")
        vx = SV.vendor_hwpx(body)
        ven = Hwpx(vx)
        info = SV.analyze(ven)
        front_taken = bool(info["full"])
        vendor_text = " ".join(SV._text(ven.root).split())
        checks = SV.review(ven, d)
        if info["full"]:  # 우리 견본 전체에 외주 몫까지 쓴 파일 — 앞 외주 몫 옮기고 3~7장만 잘라 끼움
            SV.take_front(doc, ven, warn)
            _front_layout(root)  # 옮겨 온 문단에 우리 쪽 나눔 규칙(10/27)
            chapters = folder / "외주_3~7장.hwpx"
            SV.cut_chapters(vx, chapters)
        elif info["chapter3"] is not None:
            chapters = folder / "외주_3~7장.hwpx"
            SV.cut_chapters(vx, chapters)  # 3장 앞이 없어도 머리 빈 줄 정리(빈 쪽, 10/22)
            warn.append(NO_FRONT)
        else:
            warn.append("외주 한글에서 \"제3장\"을 못 찾아 끼워 넣지 않았습니다 — 파일을 확인해 주세요")
    else:
        warn.append(NO_FRONT)
    from server.sitok import seismic_fill, seismic_todo

    filling = f.seismic_only or (r.survey or {}).get("seismic_field") or (r.survey or {}).get("seismic_docs")  # 별개 건(10/21) — 현장조사 입력·서류 값
    has_ground = bool((((r.survey or {}).get("seismic_docs") or {}).get("ground") or {}).get("parsed"))
    todo = seismic_todo.Todo(doc, vendor=not front_taken, ground=not has_ground) if filling else None  # 외주 몫·지반 견본 값 기억(채우기 전, 10/26)
    try:
        with seismic_fill.borders_for(doc):  # 표 줄 지우기·복사 때 끝줄 굵은 선·맞닿는 선(10/22)
            changed = seismic_fill.fill_cover_names(root, d)  # 표지 아래 발주처·회사 글자로(로고 지움, 10/22) — 이름 바꾸기 앞에서
            changed += replace_globals(doc, d)
            changed += fill_persons(root, d) + fill_result_ga(root, d) + fill_result_people(root, d) + fill_chapter1(root, d) + fill_field_summary(root, d)
            changed += fill_rebar(root, d, warn)
            if filling:
                say("현장조사·서류 값 채우는 중…")
                changed += seismic_fill.fill_all(doc, root, r, f, folder, d, warn, front_taken=front_taken, vendor_text=vendor_text)
            changed += seismic_fill.fix_confirm_layout(doc, root) + seismic_fill.fix_checklist_stamp(root)  # 확인서 두 칸·체크리스트 도장(10/22)
            if todo is not None:  # 손대지 않은 견본 값 → 빈칸 + 노랑(10/26 사용자 "다 지우고 노란색으로 바뀌어야 한다는 표시")
                changed += todo.finish(folder, warn)
            if filling:  # 도면·성적서·도해·모델링 그림 칸도 사진 칸처럼 여백 2mm(10/27) — 그림이 다 들어간 뒤
                changed += seismic_fill.pad_figures(root)
            evened = seismic_fill.even_tables(root)  # 모든 표 선 경계마다 고르게(10/28 사용자 "표 선 굵기가 제멋대로") — 채우기 끝난 뒤 마지막에
            if evened:
                print(f"[표 선 고르게] {base}: {evened}칸", flush=True)
    finally:
        if todo is not None:
            todo.stop()
    ours = folder / f"{base}(1~2장).hwpx"
    doc.save(ours)
    hwpx = folder / f"{base}.hwpx"
    if chapters is not None:
        say("외주 3~7장 한글 끼워 넣는 중(1~2분)…")
        fixed = merge_vendor(ours, chapters, hwpx)
        warn.append(f"외주 3~7장을 끼워 넣었습니다(장 번호 {fixed}곳 3장부터 고침)" if fixed else "외주 3~7장을 끼워 넣었습니다(외주 쪽 설정 그대로)")
    else:
        hwpx.write_bytes(ours.read_bytes())
        if body is None or not body.exists():
            warn.append("외주 한글이 없어 우리 1~2장만 — 회차 화면 [📎 외주 결과물]에서 올리세요")
    warn += [f"검토: {x}" for x in checks]
    say("PDF로 바꾸는 중(2~3분)…")
    pdf = folder / f"{base}.pdf"
    pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
    marks = page_marks(root)  # 쪽 검사 기준 = 틀 용지 여백에서(10/27 — 12mm 틀도 맞게)
    _tidy(hwpx, pdf, say, sections_from=0, after="제1장건물개요1.1", marks=marks)  # 애매한 넘침 정리(10/26) — 목차 쪽 번호 전에. 내진은 구역 하나 — 첫 구역부터,
    # 고치는 건 1장 간지 뒤 표만(10/27 — 전엔 둘째 구역부터라 내진 본문은 아무것도 안 고쳤음, 앞 결과표 줄 높이는 그대로)
    _push_lonely(hwpx, pdf, say, after="제1장건물개요1.1", marks=marks)  # 제목·표 이름만 쪽 끝 → 다음 쪽(10/27) — 목차 쪽 번호 전에
    _merge_masonry(hwpx, pdf, say)  # 조적벽 결과표 층·구분 합치기 — 쪽이 정해진 뒤(10/27)
    _fix_blank_pages(hwpx, pdf, say, marks=marks)  # 꽉 찬 표 뒤 빈 쪽(10/27 12mm)
    if f.seismic_only:  # 목차 쪽 번호 — 첫 PDF로 세어 넣고 다시(10/22)
        if seismic_fill.fill_toc(hwpx, pdf):
            say("목차 쪽 번호 넣고 다시 PDF로…")
            pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
    warn += _line_check(pdf)  # 표 선 굵기 다름(10/27) — 도면 얹기 전
    warn += _vendor_chapter_check(pdf)  # 외주 장 번호가 3장부터인지(10/27 구역 유지 — 번호가 외주 정의대로 이어지는지 PDF로 확인)
    if filling:  # 1.2 평면도·2.2.4 성적서 칸에 원본 PDF 쪽을 그대로(10/27 — 그림은 한글 파일용)
        seismic_fill.overlay_plans(pdf, f)
        seismic_fill.overlay_core(pdf, ((r.survey or {}).get("seismic_docs") or {}).get("core"), folder)
    with pymupdf.open(pdf) as x:
        pages = x.page_count
    head = f"{pages}쪽"
    if f.seismic_only and master.master_path("성능평가부록").exists():  # 별개 건(10/21) — 부록 채우고 서류 PDF 끼워 합본
        from server.sitok import seismic_appendix as SA

        say("부록 채우는 중…")
        adoc = Hwpx(master.master_path("성능평가부록"))
        with seismic_fill.borders_for(adoc):
            SA.fill_appendix(adoc, d, r, f, folder, warn)
            seismic_fill.even_tables(adoc.root)  # 부록 표도(10/28)
        appx = folder / f"{base}_부록.hwpx"
        adoc.save(appx)
        say("부록 PDF·합본 만드는 중(2~4분)…")
        _, merged = SA.assemble(db, pdf, appx, folder / f"{base}_합본.pdf", r, f, folder, warn)
        r.survey = {**(r.survey or {}), "appendix_hwpx": str(appx)}
        with pymupdf.open(merged) as x:
            head = f"본문 {pages}쪽 · 합본 {x.page_count}쪽"
        pdf = merged
    warn.insert(0, head)
    if not f.seismic_only:
        warn += STILL_SAMPLE
    return hwpx, pdf, warn, changed


def _selfcheck() -> None:
    assert _date(datetime.date(2025, 10, 24)) == "2025. 10. 24." and _date(datetime.date(2026, 1, 2), True) == "2026년 01월 02일"
    assert re.sub(r"\s", "", "시험 번호") == "시험번호"


if __name__ == "__main__":
    _selfcheck()
    print("ok")
