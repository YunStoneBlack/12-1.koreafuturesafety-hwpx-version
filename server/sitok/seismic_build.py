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
from server.sitok.seismic_fill import _set
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
    """결과표 "사. 책임(참여)기술자 현황"(라~사 표 안, 우리 몫) — 머리 줄(구분·성명·과업참여기간·기술등급) 칸 위치로, 남는 줄은 비움."""
    if not d["persons"]:
        return 0
    period = f"{_date(d['period_start'])} ~ {_date(d['period_end'])}" if d["period_start"] and d["period_end"] else "-"
    for t in _tables(root):
        cells = rb._cells(t)
        if not rb._n(rb._cell_text(cells.get((0, 0), t))).startswith("라.내진성능"):
            continue
        head = next((r for (r, c), x in cells.items() if c == 0 and rb._n(rb._cell_text(x)) == "사업책임기술자"), None)
        if head is None:
            return 0
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
        from server.sitok.seismic_fill import thick_bottom

        thick_bottom(t)  # 표 끝 굵은 선(10/22)
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
    """우리 1~2장 한글 끝에 외주 3~7장을 한글이 직접 끼워 넣음(hwp_queue "merge" — 쪽 나눔 뒤 파일 끼워 넣기, 구역 설정은 우리 것 → 쪽 번호·꼬리말 이어짐)
    → 외주 장 번호 고침. 고친 장 수."""
    import zipfile

    from server.contract_docs import hwp_queue

    data = vendor.read_bytes()
    if vendor.suffix.lower() == ".hwp":
        data = hwp_queue.convert_via_worker(data, ".hwp", to="hwpx", wait=600)
    merged = hwp_queue.convert_via_worker(ours.read_bytes(), ".hwpx", to="merge", add=data, keep_section=0, wait=1200)
    dest.write_bytes(merged)
    with zipfile.ZipFile(ours) as z:
        from lxml import etree

        root = etree.fromstring(z.read(rb._sections(z)[0]))
        n0 = len([p for p in root if p.tag == f"{{{HP}}}p"])
    return fix_vendor_chapters(dest, n0)


def _tidy(hwpx: Path, pdf: Path, say=None, sections_from: int = 1) -> list[str]:
    """애매한 넘침 정리(10/26 사용자 "산안·시특·내진·결함 전부" — pagecheck.tidy_checked, 시특법과 같은 규칙·안전장치). 못 하면 그대로."""
    import traceback

    from server.contract_docs import hwp_queue
    from server.sitok import pagecheck

    def render(hx: Path, out: Path) -> None:
        if say:
            say("애매하게 넘친 쪽 정리해서 다시 PDF로…")
        out.write_bytes(hwp_queue.convert_via_worker(hx.read_bytes(), ".hwpx", wait=1500))

    try:
        return pagecheck.tidy_checked(hwpx, pdf, render, sections_from=sections_from)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return []


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
    finally:
        if todo is not None:
            todo.stop()
    ours = folder / f"{base}(1~2장).hwpx"
    doc.save(ours)
    hwpx = folder / f"{base}.hwpx"
    if chapters is not None:
        say("외주 3~7장 한글 끼워 넣는 중(1~2분)…")
        fixed = merge_vendor(ours, chapters, hwpx)
        warn.append(f"외주 3~7장을 끼워 넣었습니다(장 번호 {fixed}곳 3장부터 고침)")
    else:
        hwpx.write_bytes(ours.read_bytes())
        if body is None or not body.exists():
            warn.append("외주 한글이 없어 우리 1~2장만 — 회차 화면 [📎 외주 결과물]에서 올리세요")
    warn += [f"검토: {x}" for x in checks]
    say("PDF로 바꾸는 중(2~3분)…")
    pdf = folder / f"{base}.pdf"
    pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
    _tidy(hwpx, pdf, say)  # 애매한 넘침 정리(10/26) — 목차 쪽 번호 전에
    if f.seismic_only:  # 목차 쪽 번호 — 첫 PDF로 세어 넣고 다시(10/22)
        if seismic_fill.fill_toc(hwpx, pdf):
            say("목차 쪽 번호 넣고 다시 PDF로…")
            pdf.write_bytes(hwp_queue.convert_via_worker(hwpx.read_bytes(), ".hwpx", wait=1500))
    with pymupdf.open(pdf) as x:
        pages = x.page_count
    head = f"{pages}쪽"
    if f.seismic_only and master.master_path("성능평가부록").exists():  # 별개 건(10/21) — 부록 채우고 서류 PDF 끼워 합본
        from server.sitok import seismic_appendix as SA

        say("부록 채우는 중…")
        adoc = Hwpx(master.master_path("성능평가부록"))
        with seismic_fill.borders_for(adoc):
            SA.fill_appendix(adoc, d, r, f, folder, warn)
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
