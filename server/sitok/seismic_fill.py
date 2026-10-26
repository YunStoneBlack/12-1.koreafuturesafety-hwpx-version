"""내진성능평가 보고서 칸 채우기 3단계(2026-10-21 사용자 "1~2장 + 지반조사보고서·3~7장(외주)에서 자동으로 채워지는 부분").

seismic_build.build가 우리 1~2장 원본(견본 삼숭초 교사동)에 이름·결과표 가·사·1.1·철근배근을 채운 뒤 여기서 나머지:
- 요약: 위치도·전경 사진, (1) 현장 시험 조사개소(부재규격·콘크리트 강도·지반조사), 결함·중량물 분석 글
- 1장: 1.1 경과년수(조사 연도 기준), 1.3 내진등급·성능목표 ◎, 1.4 층별 용도현황·증축·용도변경(건축물대장)
- 2장: 2.2.1 부재 단면 표·수량·사진·조사결과 문장, 2.2.2 사진·조사결과 문장, 2.2.3 코어 사진, 2.2.4 강도결정 표·성적서 그림·조사결과 문장,
  2.3 분석 글 다섯, 2.4.1 중량물·2.4.2 마감재 사진·글, 2.4.3 조적조 사진·결과표, 2.5 지반(문장·위치도·BH별 사진 6장·결과 그림 — 지반조사보고서)
견본 값 자리(예: "15.7~17.3MPa(평균 13.82MPa)")는 견본 글을 그대로 찾아 바꿈 — 원본이 바뀌면 SAMPLE_* 도 같이.
"""
from __future__ import annotations

import contextlib
import copy
import io
import re
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb
from server.sitok.report_build import _n
from server.sitok import seismic_docs as SD
from server.sitok import seismic_field as SF
from server.sitok import seismic_todo as TD
from server.sitok.wall_build import HC, HP, _size_pic, _tables

SAMPLE_CORE = "15.7~17.3MPa(평균 13.82MPa)로 설계도면상 강도기준의 85%, 각각의 값이 75%를 하회하나"
SAMPLE_CORE_TITLE = "콘크리트 코어시험에 의한 강도결정(조사단위 12개소)"
SAMPLE_MEMBER_DIFF = "지상5층 B1부재가 구조도면과 실측 수치와 상이하여 현장 실측 데이터를 내진성능 평가에 반영하였다."
SAMPLE_GROUND = "얕고 단단한 지반인 S2 지반(기반암 깊이 1~20.0이하, 전단파속도 BH-1 : 305.9m/s, BH-2 : 569.9m/s)"
SAMPLE_BORING = "본 구조물은 2개소 시추조사를"
SAMPLE_EXT_NOTE = "※ 건축물대장에 증축사항이 없어 도면 참고함"
PHOTO_TABLES = [("구조부재단면조사", ("member_1", "member_2")), ("철근탐사장비", ("rebar_1", "rebar_2")), ("코어채취작업", ("core_1", "core_2")),
                ("코어시료채취완료", ("core_3", "core_4")), ("건물외중량물", ("heavy_1", "heavy_2")), ("건물외부마감재", ("finish_1", "finish_2")),
                ("조적채움벽현황", ("infill_1", "infill_2")), ("조적허리벽현황", ("parapet_1", "parapet_2"))]
GRADE_MARK = {"특등급": "특", "1등급": "I", "2등급": "II"}


def _t(el) -> str:
    return "".join(x.text or "" for x in el.iter(f"{{{HP}}}t"))


def _outer(root) -> list:
    return [t for t in _tables(root) if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None]


def _top_p(el):
    """el이 든 맨 위 문단(구역 root 바로 아래)."""
    p = el
    for a in el.iterancestors(f"{{{HP}}}p"):
        p = a
    return p


def _set(cells: dict, rc: tuple, text) -> None:
    tc = cells.get(rc)
    if tc is not None:
        rb._set_lines(tc, str(text if text is not None else "").split("\n"))


def _fmt(v, nd: int = 1) -> str:
    return f"{v:,.{nd}f}" if isinstance(v, (int, float)) else str(v or "")


COMPANY = "㈜한국미래안전"  # 표지 회사 글자(속표지와 같게)


def fill_cover_names(root, d: dict) -> int:
    """표지 아래 발주처·회사 — 로고 그림을 지우고 글자로 가운데(10/22 사용자 "글자로 바꾸기, 로고 삭제, 가운데 맞추기").
    견본 = 2×1 표(위 칸 발주처 로고 그림 + 발주처 이름, 아래 칸 한국미래안전 로고 그림) → 두 칸 다 발주처 이름 글자 모양(검정)·가운데 문단.
    replace_globals 앞에서 — 뒤에 하면 발주처 이름이 앞 칸 띄어쓰기의 붉은 글자 모양으로 합쳐짐."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    for p in tops[:40]:
        for t in _outer(p):
            if (t.get("rowCnt"), t.get("colCnt")) != ("2", "1") or next(t.iter(f"{{{HP}}}pic"), None) is None:
                continue
            cells = rb._cells(t)
            if (0, 0) not in cells or (1, 0) not in cells:
                continue
            named = [r for r in cells[(0, 0)].iter(f"{{{HP}}}run") if _t(r).strip()]
            char = named[0].get("charPrIDRef") if named else None
            center = next(cells[(1, 0)].iter(f"{{{HP}}}p")).get("paraPrIDRef")
            for rc, text in (((0, 0), d.get("client") or "-"), ((1, 0), COMPANY)):
                tc = cells[rc]
                for pic in list(tc.iter(f"{{{HP}}}pic")):
                    pic.getparent().remove(pic)
                first = next(tc.iter(f"{{{HP}}}p"))
                runs = first.findall(f"{{{HP}}}run")
                keep = named[0] if rc == (0, 0) and named and named[0].getparent() is first else (runs[0] if runs else None)
                for r in runs:
                    if r is not keep:
                        first.remove(r)
                if keep is not None and char:
                    keep.set("charPrIDRef", char)
                if center:
                    first.set("paraPrIDRef", center)
                rb._set_lines(tc, [text])
            for pic in [x for x in p.iter(f"{{{HP}}}pic") if next(x.iterancestors(f"{{{HP}}}tbl"), None) is None]:  # 표 밖에 떠 있는 발주처 로고
                pic.getparent().remove(pic)
            return 1
    return 0


@contextlib.contextmanager
def borders_for(doc):
    """내진성능평가 한글(Hwpx) 채우는 동안 테두리 도구(report_build.using_borders) — 줄 지울 때 끝줄 굵은 선 옮기기·줄 복사 때 맞닿는 선 얇게(10/22).
    끝나면 더한 테두리 모양을 doc.header에 붙임."""
    from lxml import etree

    from server.sitok.borders import Borders

    b = Borders(etree.tostring(doc.header, encoding="unicode"))
    with rb.using_borders(b):
        yield b
    if b.added or getattr(b, "chars_added", None):
        doc.header = etree.fromstring(b.result(etree.tostring(doc.header, encoding="unicode")).encode("utf-8"))


def thick_bottom(tbl) -> int:
    """표 끝줄(아래로 끝까지 닿는 칸) 아래 선 = 머리줄 첫 칸의 위 선 모양(보통 굵은 선) — 다음 쪽으로 이어지던 견본 표를 틀로 쓴 표도 그 쪽에서 끝나면
    굵게(10/22 사용자 "표 맨 아래 굵은선"). 테두리 도구(borders_for) 안에서만. 바꾼 칸 수."""
    b = getattr(rb._TL, "borders", None)
    trs = tbl.findall(f"{{{HP}}}tr")
    if b is None or len(trs) < 2:
        return 0
    first = trs[0].find(f"{{{HP}}}tc")
    d0 = b.by_id.get(str(first.get("borderFillIDRef"))) if first is not None else None
    m = re.search(r"<hh:topBorder ([^>]*)/>", d0 or "")
    if not m:
        return 0
    last, n = len(trs) - 1, 0
    for (r, _c), tc in rb._cells(tbl).items():
        if r + int(tc.find(f"{{{HP}}}cellSpan").get("rowSpan")) - 1 != last:
            continue
        d = b.by_id.get(str(tc.get("borderFillIDRef")))
        if not d:
            continue
        new = re.sub(r"<hh:bottomBorder [^>]*/>", f"<hh:bottomBorder {m.group(1)}/>", d, count=1)
        if new != d:
            tc.set("borderFillIDRef", b.adopt(new))
            n += 1
    return n


def replace_loose(doc, old: str, new: str) -> int:
    """견본 글 바꾸기 — 띄어쓰기 칸 수와 상관없이(2.5 (3) "전단파속도         BH-1"처럼 줄 맞춤 빈칸이 있음). 문단마다 글자 칸을 이어 찾음."""
    pat = re.compile(r"\s*".join(re.escape(ch) for ch in re.sub(r"\s", "", old)))
    n = 0
    for root in doc.roots.values():
        for para in root.iter(f"{{{HP}}}p"):
            pieces = [pc for x in para.iter(f"{{{HP}}}t") if next(x.iterancestors(f"{{{HP}}}p"), None) is para for pc in rb._pieces(x)]
            joined = "".join(pc.text or "" for pc in pieces)
            if not pieces or not pat.search(joined):
                continue
            pieces[0].text = pat.sub(new, joined)
            for pc in pieces[1:]:
                pc.text = ""
            n += 1
    return n


def blank_png(rdir: Path) -> Path:
    """빈칸 그림(연한 노랑) — 입력이 없으면 견본 사진 대신(10/22 형 "없으면 공란이 정상", 10/26 "노란색으로 바뀌어야 한다는 표시" — 전엔 흰 바탕)."""
    from PIL import Image

    p = rdir / "보고서그림" / "빈칸_노랑.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (400, 300), (255, 242, 168)).save(p)
    return p


def _put_or_blank(doc, pic, path: Path | None, rdir: Path, crop: bool = True) -> bool:
    """그림을 넣고(True), 없으면 빈칸 그림(False)."""
    if _put(doc, pic, path, crop=crop):
        return True
    _put(doc, pic, blank_png(rdir), crop=False)
    return False


def _put(doc, pic, path: Path | None, crop: bool = True) -> bool:
    img = next(pic.iter(f"{{{HC}}}img"), None)
    if img is None or path is None or not Path(path).exists():
        return False
    data = rb._fit_to_pic(str(path), img, crop=crop)
    if not isinstance(data, (bytes, bytearray)):
        data = Path(data).read_bytes()
    img.set("binaryItemIDRef", doc.add_image(bytes(data)))
    return True


# ---------- 사진 ----------
def map_image(f, field: dict, rdir: Path) -> Path | None:
    """위치도 그림 — 현장 사진 칸에 올린 위치도 > 건 화면 📍 위치도(올린 그림 > 깃발 자리 지도 > 주소 지도, 10/22 형 "기존 방식처럼 주소로 찍고 깃발")."""
    rel = ((field.get("photos") or {}).get("map") or {}).get("rel")
    if rel and (rdir / rel).exists():
        return rdir / rel
    if f is None:
        return None
    from server.api.routers.sitok import _facility_dir
    from server.sitok import locmap

    try:
        return locmap.facility_map(f, _facility_dir(f))
    except Exception:  # noqa: BLE001 — 지도 서버가 안 되면 빈칸
        return None


def fill_photos(doc, root, field: dict, rdir: Path, warn: list, f=None) -> int:
    photos, n, miss = field["photos"], 0, []
    path = lambda slot: (rdir / photos[slot]["rel"]) if (photos.get(slot) or {}).get("rel") else None  # noqa: E731
    for key, slots in PHOTO_TABLES:
        t = next((t for t in _outer(root) if key in _n(_t(t)) and rb._pic_slots(t)), None)
        if t is None:
            continue
        for slot, (_, pic) in zip(slots, rb._pic_slots(t)):
            if _put_or_blank(doc, pic, path(slot), rdir):
                n += 1
            else:
                miss.append(SF.PHOTO[slot][0])
    # 요약 "시설물 위치도 및 전경사진" — 다음 그림 문단의 첫 표 = 위치도, 끝 표 = 전경
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    i = next((k for k, p in enumerate(tops) if "시설물위치도및전경사진" in _n(_t(p)) and next(p.iter(f"{{{HP}}}pic"), None) is None), None)
    if i is not None:
        p = next((q for q in tops[i + 1:i + 6] if sum(1 for _ in q.iter(f"{{{HP}}}pic")) >= 2), None)
        ts = [t for t in (_outer(p) if p is not None else []) if rb._pic_slots(t)]
        if len(ts) >= 2:
            for slot, t, crop in (("map", ts[0], False), ("front", ts[-1], True)):
                src = map_image(f, field, rdir) if slot == "map" else path(slot)
                if _put_or_blank(doc, rb._pic_slots(t)[0][1], src, rdir, crop=crop):
                    n += 1
                else:
                    miss.append(SF.PHOTO[slot][0])
    if miss:
        warn.append(f"현장 사진 없음(빈칸): {'·'.join(miss)} — 현장조사 입력 📷")
    return n


# ---------- 표 줄 맞추기 ----------
def _resize_tail(tbl, header: int, want: int) -> None:
    """데이터 줄 수를 want로 — 끝 줄을 복사·지움(첫 열 세로 합친 칸은 늘어남·줄어듦)."""
    have = int(tbl.get("rowCnt")) - header
    want = max(want, 1)
    if want > have:
        rb._dup_rows(tbl, header + have - 1, 1, want - have)
    elif want < have:
        rb._del_rows(tbl, header + want, have - want)


def _resize_flat(tbl, header: int, want: int) -> None:
    """데이터 줄을 첫 데이터 줄(칸이 다 있는 줄) 하나로 줄인 뒤 want줄로 복사 — 줄마다 칸이 다 있게(층·구분 합친 칸 없이)."""
    have = int(tbl.get("rowCnt")) - header
    if have > 1:
        rb._del_rows(tbl, header + 1, have - 1)
    row = [tc for tc in tbl.iter(f"{{{HP}}}tc") if int(tc.find(f"{{{HP}}}cellAddr").get("rowAddr")) == header]
    single = [int(tc.find(f"{{{HP}}}cellSz").get("height")) for tc in row if tc.find(f"{{{HP}}}cellSpan").get("rowSpan") == "1"]
    for tc in row:  # 남긴 줄의 세로 합친 칸(층·구분)을 한 줄로(높이도) — _del_rows는 지운 범위 끝까지 걸친 칸만 줄여서, 중간에서 끝나던 칸이 남으면 한글이 멈춤(10/22)
        tc.find(f"{{{HP}}}cellSpan").set("rowSpan", "1")
        if single:
            tc.find(f"{{{HP}}}cellSz").set("height", str(min(single)))
    if want > 1:
        rb._dup_rows(tbl, header, 1, want - 1)


def _empty_para(p) -> bool:
    """글·표·그림·조판 부호가 없는 빈 문단(쪽 나눔만 든 것 포함)."""
    if next(p.iter(f"{{{HP}}}tbl", f"{{{HP}}}pic", f"{{{HP}}}ctrl", f"{{{HP}}}secPr"), None) is not None:
        return False
    return not "".join(x.text or "" for x in p.iter(f"{{{HP}}}t")).strip()


def _drop_empty_before(p) -> None:
    """p 바로 앞의 빈 문단들을 지움(견본 표 사이 빈 줄·쪽 나눔 — 앞 표가 쪽을 꽉 채우면 다음 쪽으로 밀려 빈 쪽이 생김, 10/22)."""
    q = p.getprevious()
    while q is not None and q.tag == f"{{{HP}}}p" and _empty_para(q):
        prev = q.getprevious()
        q.getparent().remove(q)
        q = prev


def even_rows(tbl, header: int) -> None:
    """데이터 줄 높이·글자 모양을 표에서 가장 많이 쓴 것으로 — 견본 줄마다 달랐던 높이(두 줄 글 자리)·글자(파란·작은 비고)가 우리 값에 남던 것(10/22)."""
    from collections import Counter

    data = tbl.findall(f"{{{HP}}}tr")[header:]
    single = [tc for tr in data for tc in tr.findall(f"{{{HP}}}tc") if tc.find(f"{{{HP}}}cellSpan").get("rowSpan") == "1"]
    if not single:
        return
    h = Counter(int(tc.find(f"{{{HP}}}cellSz").get("height")) for tc in single).most_common(1)[0][0]
    delta = 0
    for tr in data:
        old = rb._row_height(tr)
        for tc in tr.findall(f"{{{HP}}}tc"):
            if tc.find(f"{{{HP}}}cellSpan").get("rowSpan") == "1":
                tc.find(f"{{{HP}}}cellSz").set("height", str(h))
        if old:
            delta += h - old
    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None and sz.get("height") and delta:
        sz.set("height", str(max(int(sz.get("height")) + delta, 0)))
    runs = [x for tr in data for x in tr.iter(f"{{{HP}}}run")]
    if runs:
        base = Counter(x.get("charPrIDRef") for x in runs).most_common(1)[0][0]
        for x in runs:
            x.set("charPrIDRef", base)


def split_pages(t) -> None:
    """한 쪽을 넘기는 표를 줄 단위로 쪽에서 나뉘게(pageBreak TABLE — CELL은 칸 안 글이 끊기고 NONE은 안 나뉨). 글자처럼 취급이면 한글이 표를 통째로
    다음 쪽으로 밀어 나뉘지 않으니(10/26 호원초 조적벽 결과표 — 제목만 남고 표는 다음 쪽) 끄고 단 가운데(민재형도 한 표로 합칠 때 끔)."""
    t.set("pageBreak", "TABLE")
    pos = t.find(f"{{{HP}}}pos")
    if pos is not None and pos.get("treatAsChar") == "1":
        for k, v in (("treatAsChar", "0"), ("flowWithText", "1"), ("allowOverlap", "0"), ("vertRelTo", "PARA"), ("vertOffset", "0"),
                     ("horzRelTo", "COLUMN"), ("horzAlign", "CENTER"), ("horzOffset", "0")):
            pos.set(k, v)


def _notes_after(p) -> list:
    """p 바로 뒤 "※" 주석 문단들."""
    out, nxt = [], p.getnext()
    while nxt is not None and nxt.tag == f"{{{HP}}}p" and next(nxt.iter(f"{{{HP}}}tbl"), None) is None             and "".join(x.text or "" for x in nxt.iter(f"{{{HP}}}t")).strip().startswith("※"):
        out.append(nxt)
        nxt = nxt.getnext()
    return out


def fill_chunks(root, tables: list, rows: list[list], per: int, header: int, flat: bool, one: bool = False) -> int:
    """견본 표들(같은 모양)에 rows를 per줄씩 — 표가 모자라면 마지막 표 문단을 복사(쪽 나눔), 남는 견본 표는 지움. 넣은 줄 수.
    표는 문단 안 몇 번째 표인지로 집음(부록은 사진 머리 표와 값 표가 한 문단에 같이 있음, 10/22). 둘째 표부터는 앞 빈 문단을 지우고 그 표 문단에서 새 쪽,
    남는 견본 표를 지울 때는 앞 빈 문단·뒤 "※" 주석도(빈 쪽·겹친 주석 없게), 줄 높이·글자 모양은 고르게(even_rows — 줄 복사로 만든 flat 표는 이미 고름).
    one: 첫 견본 표 하나에 다 넣고 쪽을 넘기면 머리 줄 반복(10/26 민재형 "쪽마다 나뉜 표를 한 표로") — 주석은 마지막 견본 표 것(□ 조사불가 등)을 첫 표 주석 모양으로
    표 바로 뒤에 한 번, 한 쪽에 안 들어갈 만큼(per줄 넘게)이면 줄 단위로 나뉘게(pageBreak TABLE)."""
    if not tables:
        return 0
    slots = []
    for t in tables:
        p = _top_p(t)
        slots.append((p, _outer(p).index(t)))
    tpl_p, tpl_idx = slots[-1]
    tpl = copy.deepcopy(tpl_p)
    chunks = [rows] if one else [rows[i:i + per] for i in range(0, len(rows), per)] or [[]]
    if one and len(slots) > 1:
        first, last = _notes_after(slots[0][0]), _notes_after(slots[-1][0])
        if last:
            style = first[0].get("paraPrIDRef") if first else None
            for x in first:
                x.getparent().remove(x)
            inline = [x for x in slots[0][0].iter(f"{{{HP}}}t") if next(x.iterancestors(f"{{{HP}}}tbl"), None) is None]
            if "".join(x.text or "" for x in inline).strip().startswith("※"):  # 첫 표 문단에 같이 붙은 주석 글("※ □ : 조사불가") — 두 번 나오지 않게
                for x in inline:
                    for pc in rb._pieces(x):
                        pc.text = ""
            at = slots[0][0]
            for x in last:
                if style:
                    x.set("paraPrIDRef", style)
                at.addnext(x)
                at = x
    used = []
    for k, chunk in enumerate(chunks):
        if k < len(slots):
            p, idx = slots[k]
            if k > 0 and len(_outer(p)) == 1:
                _drop_empty_before(p)
                p.set("pageBreak", "1")
        else:
            p, idx = copy.deepcopy(tpl), tpl_idx
            rb._new_ids(p)
            used[-1].addnext(p)
            p.set("pageBreak", "1")
        used.append(p)
        t = _outer(p)[idx]
        (_resize_flat if flat else _resize_tail)(t, header, len(chunk))
        if one and len(chunk) > per:  # 쪽을 넘기는 한 표 — 줄 단위로 나뉘게
            split_pages(t)
            cap = p.getprevious()  # 표 제목("【 부재 단면 치수 조사 결과 】")부터 새 쪽 — 앞 쪽 끝에 머리 줄만 걸리지 않게(짧은 표는 이어서)
            if cap is not None and next(cap.iter(f"{{{HP}}}tbl"), None) is None and _t(cap).strip()[:1] in ("【", "["):
                _drop_empty_before(cap)  # 앞 빈 줄이 앞 쪽 끝에서 넘치면 쪽 나눔과 겹쳐 빈 쪽
                cap.set("pageBreak", "1")
        if not flat:
            even_rows(t, header)
        cells = rb._cells(t)
        for j, vals in enumerate(chunk):
            for c, v in enumerate(vals):
                if v is not None:
                    _set(cells, (header + j, c), v)
        thick_bottom(t)
    for p, idx in slots[len(chunks):]:
        if p.getparent() is None:
            continue
        if len(_outer(p)) <= 1:
            _drop_empty_before(p)
            nxt = p.getnext()
            while nxt is not None and nxt.tag == f"{{{HP}}}p" and next(nxt.iter(f"{{{HP}}}tbl"), None) is None                     and "".join(x.text or "" for x in nxt.iter(f"{{{HP}}}t")).strip().startswith("※"):
                after = nxt.getnext()
                nxt.getparent().remove(nxt)
                nxt = after
            p.getparent().remove(p)
        else:  # 다른 표(사진 머리 등)와 같은 문단이면 그 표만
            t = _outer(p)[idx]
            t.getparent().remove(t)
    return len(rows)


# ---------- 요약 (1) 현장 시험 및 분석 ----------
def fill_summary(root, field: dict, ground: dict | None, drawings: bool = True, grade: str = "특등급", member_total: int = 0, core_min: int = 6, doc=None) -> int:
    n = 0
    holes = (ground or {}).get("holes") or []
    rule = {"부재규격": "부재 종별로 각각 3개소 이상 조사" if drawings else "부재 종별로 각각 9개소 이상 조사(구조도면 작성)",  # 매뉴얼 <표 3-1>(10/22)
            "철근배근": "부재 종별로 각각 3개소 이상 조사" if drawings else "구조도면 작성에 충분한 수량으로 부재 종별로 각각 3개소 이상",
            "지반조사(공통)": "특등급 구조물 2개소" if grade == "특등급" else "기타 내진등급 구조물 1개소"}
    for t in _outer(root):
        cells = rb._cells(t)
        if _n(rb._cell_text(cells.get((0, 1), t))) != "조사·시험항목":
            continue
        for (r, c), x in list(cells.items()):
            label = _n(rb._cell_text(x)) if c == 1 else ""
            if label in rule:
                _set(cells, (r, 2), rule[label])
            v = {"부재규격": member_total or len(field["members"]), "콘크리트강도": len(field["cores"]) or core_min,  # 조사개소 = 칸 수(형이 정한 수량, 10/22)
                 "지반조사(공통)": len(holes) or (2 if grade == "특등급" else 1)}.get(label)
            if v:
                _set(cells, (r, 3), f"{v}EA")
                n += 1
        break
    visual_done = False
    for t in _outer(root):  # 요약 표 — 조사결과 글 그대로(본문과 같은 글), 비었으면 빈칸(견본 글 안 남김, 10/22 형 "결과값 연동")
        cells = rb._cells(t)
        if _n(rb._cell_text(cells.get((0, 0), t))) != "구분" or _n(rb._cell_text(cells.get((0, 1), t))) != "내용":
            continue
        if not visual_done and _n(rb._cell_text(cells.get((1, 0), t))) == "분석결과":  # 첫 "분석 결과" = 가. 결함조사 결과 — 외관조사 글들을 이어서
            visual_done = True
            joined = "\n".join(x for k in SF.VISUAL for x in (field["texts"].get(k) or "").split("\n") if x.strip())
            _set(cells, (1, 1), joined)
            if not joined:
                _no_bullet(doc, cells[(1, 1)])
                TD.paint(cells[(1, 1)])  # 조사결과 글이 없음 — 노랑(10/26)
            n += 1
            continue
        for (r, c), x in list(cells.items()):
            key = SF.SUMMARY_ROWS.get(_n(rb._cell_text(x))) if c == 0 else None
            if key and (r, 1) in cells:
                _set(cells, (r, 1), field["texts"].get(key) or "")
                if not field["texts"].get(key):
                    _no_bullet(doc, cells[(r, 1)])
                    TD.paint(cells[(r, 1)])
                n += 1
    return n


BODY_RESULTS = (("2.2.1부재단면", "(2)조사결과", "eq_member"), ("2.2.2철근배근", "(3)철근배근조사결과", "eq_rebar"),
                ("2.2.4재료강도의결정", "조사결과", "eq_core"))  # 본문 조사결과 글머리 — 요약 장비조사와 같은 글(10/22)


def _para_text(p, text: str) -> None:
    ts = [x for x in p.iter(f"{{{HP}}}t") if next(x.iterancestors(f"{{{HP}}}p"), None) is p]
    if not ts:
        run = p.find(f"{{{HP}}}run")
        if run is None:
            return
        ts = [etree.SubElement(run, f"{{{HP}}}t")]
    ts[0].text = text
    for x in ts[1:]:
        x.text = ""
    for el in list(p.iter(f"{{{HP}}}linesegarray")):
        el.getparent().remove(el)


def fill_body_results(root, field: dict, doc=None) -> int:
    """본문 조사결과 글머리(2.2.1 (2)·2.2.2 (3)·2.2.4 조사결과) = 조사결과 글 줄마다 하나(첫 글머리 모양), 비었으면 빈 줄 하나."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    n = 0
    for sec, head, key in BODY_RESULTS:
        s = max((i for i, p in enumerate(tops) if _n(_t(p)) == sec), default=None)
        if s is None:
            continue
        h = next((i for i in range(s + 1, min(s + 200, len(tops))) if _n(_t(tops[i])) == head), None)
        if h is None:
            continue
        bullets = []
        for p in tops[h + 1:]:
            if not _n(_t(p)) or _outer(p):
                break
            bullets.append(p)
        if not bullets:
            continue
        lines = [x.strip() for x in (field["texts"].get(key) or "").split("\n") if x.strip()] or [""]
        first = bullets[0]
        tpl = copy.deepcopy(first)
        for p in bullets[1:]:
            p.getparent().remove(p)
        _para_text(first, lines[0])
        _blacken(first)
        if not lines[0]:
            _no_bullet(doc, first)
        last = first
        for line in lines[1:]:
            q = copy.deepcopy(tpl)
            rb._new_ids(q)
            _para_text(q, line)
            _blacken(q)
            last.addnext(q)
            last = q
        n += 1
    return n


HH = "http://www.hancom.co.kr/hwpml/2011/head"
GROUND_HANG = 3466  # 2.5 "   (3) " 폭(맑은 고딕 11pt, 빈칸 = 글자 절반) — PDF로 잰 "(1) 지" 시작 87.19pt − 여백 52.53pt(10/22)


def _para_variant(doc, pid: str, left: int, intent: int, align: str | None = None) -> str:
    """문단 모양 pid를 왼쪽 여백·첫 줄(내어쓰기)(+ 정렬)만 바꾼 새 모양 번호(header에 더함)."""
    hdr = doc.header
    pp = next((x for x in hdr.iter(f"{{{HH}}}paraPr") if x.get("id") == str(pid)), None)
    if pp is None:
        return pid
    new = copy.deepcopy(pp)
    nid = str(max(int(x.get("id")) for x in hdr.iter(f"{{{HH}}}paraPr")) + 1)
    new.set("id", nid)
    if align:
        for al in new.iter(f"{{{HH}}}align"):
            al.set("horizontal", align)
    for mg in new.iter(f"{{{HH}}}margin"):
        for el in mg:
            if el.tag == f"{{{HC}}}left":
                el.set("value", str(left))
            elif el.tag == f"{{{HC}}}intent":
                el.set("value", str(intent))
    parent = pp.getparent()
    parent.append(new)
    if parent.get("itemCnt"):
        parent.set("itemCnt", str(int(parent.get("itemCnt")) + 1))
    return nid


def fix_ground_indent(doc, root) -> int:
    """2.5 (1)~(3) — 왼쪽 정렬(양쪽 정렬이 ")" 뒤 빈칸을 늘려 (2)·(3) 글 시작이 어긋남, 고정폭 빈칸은 약 19pt로 너무 넓음) + 내어쓰기(둘째 줄을 글 시작에 맞춤)
    (10/22 형 "(2)본, (3)지 시작 시점 미세하게 다름, BH-1 줄 바뀔 때 지반조사결과 여기랑 시작 지점 맞추기")."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    s = max((i for i, p in enumerate(tops) if _n(_t(p)) == "2.5지반및기초"), default=None)
    if s is None:
        return 0
    n, pid = 0, None
    for p in tops[s + 1:s + 12]:
        t = next((x for x in p.iter(f"{{{HP}}}t") if next(x.iterancestors(f"{{{HP}}}p"), None) is p), None)
        m = re.match(r"^(\s*\(\d\)) (.*)$", (t.text or "") if t is not None else "", re.S)
        if not m:
            continue
        # 한글은 문단 여백 값을 절반으로 씀(PDF로 두 번 잼: 첫 줄 = left/2, 둘째 줄부터 = (left + |intent|)/2) → 첫 줄은 여백, 둘째 줄은 글 시작(34.66pt)
        pid = pid or _para_variant(doc, p.get("paraPrIDRef"), 0, -2 * GROUND_HANG, "LEFT")
        p.set("paraPrIDRef", pid)
        for el in list(p.iter(f"{{{HP}}}linesegarray")):
            el.getparent().remove(el)
        n += 1
    return n


def _tab_para_variant(doc, pid: str, pos: int) -> str:
    """문단 모양 pid를 탭 하나(pos, 왼쪽)만 있는 탭 설정으로 바꾼 새 모양 번호(탭 설정·문단 모양을 header에 더함)."""
    hdr = doc.header
    tabs = next(hdr.iter(f"{{{HH}}}tabProperties"), None)
    pp = next((x for x in hdr.iter(f"{{{HH}}}paraPr") if x.get("id") == str(pid)), None)
    if tabs is None or pp is None:
        return pid
    tid = str(max(int(x.get("id")) for x in tabs.iter(f"{{{HH}}}tabPr")) + 1)
    tp = etree.SubElement(tabs, f"{{{HH}}}tabPr", {"id": tid, "autoTabLeft": "0", "autoTabRight": "0"})
    etree.SubElement(tp, f"{{{HH}}}tabItem", {"pos": str(pos), "type": "LEFT", "leader": "NONE"})
    if tabs.get("itemCnt"):
        tabs.set("itemCnt", str(int(tabs.get("itemCnt")) + 1))
    new = copy.deepcopy(pp)
    new.set("id", str(max(int(x.get("id")) for x in hdr.iter(f"{{{HH}}}paraPr")) + 1))
    new.set("tabPrIDRef", tid)
    parent = pp.getparent()
    parent.append(new)
    if parent.get("itemCnt"):
        parent.set("itemCnt", str(int(parent.get("itemCnt")) + 1))
    return new.get("id")


def _own_ps(tc) -> list:
    return [q for q in tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is tc]


CONFIRM_TAB = 44000  # 확인서 오른쪽 칸(발주자) 탭 자리 — 한글은 탭 위치 값도 절반으로 씀(PDF로 잼, 25000이면 125pt) → 220pt
# (견본은 250pt = 칸 폭 479pt의 절반 남짓, 10/25 사용자 "살짝 왼쪽으로" — 담당부서 책임자에 이름·도장이 들어가면 "(인 또는 서명)"이 접혔음)


def _text_w(text: str, size: int = 1100) -> int:
    """글 폭 어림(HWPUNIT) — 맑은 고딕, 빈칸은 글자 크기의 절반(글꼴 빈칸 안 씀 — 한글 기본, PDF로 잰 2.5 빈칸 548)."""
    from PIL import ImageFont

    global _MALGUN
    try:
        _MALGUN
    except NameError:
        _MALGUN = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 1100)
    k = size / 1100
    return int(sum(size / 2 if ch == " " else _MALGUN.getlength(ch) * k for ch in text))


def fix_confirm_layout(doc, root) -> int:
    """확인서 아래 서명 칸 — 견본은 칸 안 두 단(수행자 | 발주자). 서버 한글이 한 단으로 그려 발주자가 아래로 흘러내림 → 두 단 설정을 지우고
    줄마다 "수행자 쪽 글 ⇥ 발주자 쪽 글"(가운데 탭), "담당주무관 … (인 또는 서명)담당부서 책임자 …"는 두 줄로(10/22 형 "발주자 소속 담당주관 위치 틀어짐"),
    그 사이 한 줄 띄움(10/25 — 담당부서 책임자는 수행자 "성명" 다음 줄)."""
    tc = next((x for x in root.iter(f"{{{HP}}}tc") if "적법한절차에따라" in _n(rb._cell_text(x)) and "발주자" in rb._cell_text(x)), None)
    if tc is None:
        return 0
    ps = _own_ps(tc)
    i0 = next((k for k, q in enumerate(ps) if q.find(f".//{{{HP}}}colPr") is not None), None)
    j0 = next((k for k, q in enumerate(ps) if k > (i0 or 0) and k + 1 < len(ps) and "발주자" in _t(ps[k + 1])), None)
    if i0 is None or j0 is None:
        return 0
    left = ps[i0:j0]
    right = [q for q in ps[j0:]]
    lines = []
    for q in right:
        lines += [x for x in re.split(r"(?<=\))\s*(?=담당부서)", _t(q).strip()) if x] if _t(q).strip() else []
    if not lines:
        return 0
    k = next((i for i, x in enumerate(lines) if x.startswith("담당부서") and i and lines[i - 1].startswith("담당주무관")), None)
    if k is not None:  # 담당주무관·담당부서 책임자 사이 한 줄(왼쪽 "소속 / 빈 줄 / 성명"처럼 — 도장·서명이 안 겹치게, 10/25 사용자 미리보기 ②)
        lines.insert(k, "")
    while left and not _t(left[-1]).strip() and len(left) > len(lines):
        left.pop()
    pid = _tab_para_variant(doc, left[0].get("paraPrIDRef"), CONFIRM_TAB)
    for run in list(left[0].findall(f"{{{HP}}}run")):  # 두 단 설정 칸 지움
        if run.find(f".//{{{HP}}}colPr") is not None and run.find(f"{{{HP}}}t") is None:
            left[0].remove(run)
    for k, line in enumerate(lines):
        if k < len(left):
            q = left[k]
        else:
            q = copy.deepcopy(left[-1])
            rb._new_ids(q)
            for pic in list(q.iter(f"{{{HP}}}pic")):
                pic.getparent().remove(pic)
            for t in q.iter(f"{{{HP}}}t"):  # 앞 줄에 붙인 탭·발주자 글도 지움(안 지우면 글이 두 번)
                for x in list(t):
                    t.remove(x)
            _para_text(q, "")
            left[-1].addnext(q)
            left.append(q)
        if not line:  # 띄운 줄 — 발주자 쪽 글 없음(탭도 안 붙임)
            continue
        ts = [x for x in q.iter(f"{{{HP}}}t") if next(x.iterancestors(f"{{{HP}}}p"), None) is q]
        if not ts:
            run = q.find(f"{{{HP}}}run")
            if run is None:
                run = etree.SubElement(q, f"{{{HP}}}run", {"charPrIDRef": left[0].find(f"{{{HP}}}run").get("charPrIDRef")})
            ts = [etree.SubElement(run, f"{{{HP}}}t")]
        width = max(CONFIRM_TAB // 2 - _text_w(_t(q)), 500)  # 탭 폭(한글이 탭 자리로 다시 잼 — 어림값)
        tab = etree.SubElement(ts[-1], f"{{{HP}}}tab", {"width": str(width), "leader": "0", "type": "1"})
        tab.tail = line
        q.set("paraPrIDRef", pid)
        for el in list(q.iter(f"{{{HP}}}linesegarray")):
            el.getparent().remove(el)
    for q in right:
        if q.getparent() is not None:
            q.getparent().remove(q)
    return 1


def fix_checklist_stamp(root) -> int:
    """체크리스트 표지 도장 — 견본은 표 앞 빈 문단에 붙어 아래로 내려가 "(서명)" 위에 놓임 → 쪽 끝에 걸리면 다음 쪽으로 넘어감(10/22 형 "도장 넘어감").
    "(서명)" 칸 문단으로 옮겨 칸에 겹치게."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    n = 0
    for k, p in enumerate(tops):
        tbs = _outer(p)
        if not tbs:
            continue
        cells = rb._cells(tbs[0])
        if _n(rb._cell_text(cells.get((0, 0), tbs[0]))) != "책임자" or (0, 7) not in cells or "서명" not in rb._cell_text(cells[(0, 7)]):
            continue
        prev = next((tops[j] for j in range(k - 1, max(k - 3, -1), -1) if tops[j].find(f".//{{{HP}}}pic") is not None), None)
        if prev is None:
            continue
        pic = next(prev.iter(f"{{{HP}}}pic"))
        sz = pic.find(f"{{{HP}}}curSz")
        tc = cells[(0, 7)]
        h = int(sz.get("height"))
        chh = int(tc.find(f"{{{HP}}}cellSz").get("height"))
        q = _own_ps(tc)[0]
        run = q.find(f"{{{HP}}}run")
        if run is None:
            continue
        pic.getparent().remove(pic)
        run.insert(0, pic)
        pos = pic.find(f"{{{HP}}}pos")
        pos.set("vertRelTo", "PARA")  # 세로만 칸 문단 기준(가로는 견본 그대로 — 단 기준 40876)
        pos.set("flowWithText", "0")
        pos.set("allowOverlap", "1")
        pos.set("vertOffset", str((2 ** 32 + (chh - h) // 2) % 2 ** 32))  # 칸 가운데(칸보다 크면 위로 — 음수는 32비트로)
        n += 1
    return n


def _no_bullet(doc, el) -> None:
    """빈칸으로 둔 글머리 문단은 글머리 점("·")도 안 보이게 — 그 문단 모양에서 글머리만 없앤 모양으로(10/22)."""
    if doc is None:
        return
    cache = doc.__dict__.setdefault("_nobullet", {})
    hdr = doc.header
    for q in ([el] if el.tag == f"{{{HP}}}p" else list(el.iter(f"{{{HP}}}p"))):
        pid = q.get("paraPrIDRef")
        if pid not in cache:
            pp = next((x for x in hdr.iter(f"{{{HH}}}paraPr") if x.get("id") == str(pid)), None)
            hd = pp.find(f"{{{HH}}}heading") if pp is not None else None
            if hd is None or hd.get("type") == "NONE":
                cache[pid] = pid
            else:
                new = copy.deepcopy(pp)
                new.set("id", str(max(int(x.get("id")) for x in hdr.iter(f"{{{HH}}}paraPr")) + 1))
                new.find(f"{{{HH}}}heading").attrib.update({"type": "NONE", "idRef": "0", "level": "0"})
                parent = pp.getparent()
                parent.append(new)
                if parent.get("itemCnt"):
                    parent.set("itemCnt", str(int(parent.get("itemCnt")) + 1))
                cache[pid] = new.get("id")
        q.set("paraPrIDRef", cache[pid])


def _blacken(el) -> None:
    """붉은 견본 글(고칠 자리 표시)을 검정 글자 모양으로(10/22 형 2.4 붉은 글) — 테두리 도구(borders_for) 안에서만."""
    b = getattr(rb._TL, "borders", None)
    if b is None:
        return
    for r in el.iter(f"{{{HP}}}run"):
        cid = r.get("charPrIDRef")
        new = b._char_variant(cid, lambda d: re.sub(r'textColor="#FF0000"', 'textColor="#000000"', d, count=1))
        if new and new != cid:
            r.set("charPrIDRef", new)


# ---------- 1장 ----------
def fill_grade(root, grade: str, warn: list) -> int:
    """1.3 【표 1-1】 내진등급과 중요도계수 · 【표 1-2】 최소성능목표 — 등급 줄에 ◎(성능목표 표는 그 등급의 인명보호 줄)."""
    mark = GRADE_MARK.get(grade, "특")
    n = 0
    for t in _outer(root):
        cells = rb._cells(t)
        head = [_n(rb._cell_text(cells.get((0, c), t))) for c in range(5)]
        if head[0] != "내진등급" or head[4] != "적용":
            continue
        target = head[1] == "성능목표"
        group = ""
        for r in range(1, int(t.get("rowCnt"))):
            g = re.sub(r"[()]", "", _n(rb._cell_text(cells[(r, 0)]))) if (r, 0) in cells else ""
            group = g or group
            if (r, 4) not in cells or (target and r == 1):
                continue
            hit = group == mark and (not target or _n(rb._cell_text(cells.get((r, 2), t))) == "인명보호")
            _set(cells, (r, 4), "◎" if hit else "")
        n += 1
    if mark != "특":
        warn.append("1.3 내진등급·성능목표 글은 특등급 견본 글 — 등급에 맞게 고쳐 주세요(표 ◎는 바꿈)")
    return n


def fill_history(doc, root, f, reg: dict) -> int:
    """1.4 층별 용도현황(옥탑 뺀 층, 위층부터)·신축 및 증축·용도변경 — 건축물대장."""
    n = 0
    floors = [x for x in reg.get("floors") or [] if not str(x.get("floor", "")).startswith("옥탑")]

    def key(x):
        s = str(x.get("floor", ""))
        m = re.search(r"\d+", s)
        v = int(m.group()) if m else 0
        return -v if s.startswith("지") else v

    floors.sort(key=key, reverse=True)
    use = f.main_use or f.use_type or "-"
    for t in _outer(root):
        cells = rb._cells(t)
        head = [_n(rb._cell_text(cells.get((0, c), t))) for c in range(6)]
        if head[:4] == ["구분", "층구분", "바닥면적(㎡)", "주용도"] and floors:
            _resize_tail(t, 1, len(floors))
            cells = rb._cells(t)
            _set(cells, (1, 0), f.name.split()[-1] if f.name else "본관")
            for j, x in enumerate(floors):
                fl = str(x.get("floor", ""))
                m = re.fullmatch(r"지(\d+)층?", fl)  # 대장 표기 "지1"·"지1층" → 지하1층
                fl = f"지하{m.group(1)}층" if m else fl
                _set(cells, (1 + j, 1), fl)
                _set(cells, (1 + j, 2), _fmt(x.get("area"), 2))
                _set(cells, (1 + j, 3), use)
                _set(cells, (1 + j, 4), "-")
            n += 1
        elif head[:5] == ["구분", "일시", "면적(㎡)", "주용도", "원인"]:
            ext = [c for c in reg.get("changes") or [] if "증축" in c.get("text", "")]
            rows = []
            for c in ext:
                areas = re.findall(r"(\d[\d,]*\.?\d*)㎡\s*증축", c["text"])
                rows.append(["증축", str(c.get("date") or "")[:4] or "-", " + ".join(areas) or "-", use, "-", "-"])
            for j in range(int(t.get("rowCnt")) - 1):
                vals = rows[j] if j < len(rows) else (["-"] * 6 if j == 0 and not rows else [""] * 6)
                for cc, v in enumerate(vals):
                    _set(cells, (1 + j, cc), v)
            if ext:
                replace_loose(doc, SAMPLE_EXT_NOTE, "※ 건축물대장 참조")
            n += 1
        elif head[:4] == ["구분", "변경사항", "일시", "비고"]:
            ch = [c for c in reg.get("changes") or [] if "용도변경" in c.get("text", "")]
            if ch:
                _set(cells, (1, 0), "용도변경")
                _set(cells, (1, 1), ch[0]["text"])
                _set(cells, (1, 2), str(ch[0].get("date") or "")[:10])
                _set(cells, (1, 3), "-")
            n += 1
    return n


# ---------- 2.2.1 부재 단면 · 2.2.2 문장 ----------
def _dims(s: str) -> list:
    return [int(x) if x.isdigit() else None for x in re.findall(r"\d+|□", s or "")]


def member_diffs(members: list[dict]) -> list[str]:
    """도면치수와 실측치수가 10% 넘게 다른 부재(보 높이는 비고에 "슬래브"가 있으면 뺌)."""
    out = []
    for m in members:
        d, s = _dims(m["design"]), _dims(m["measured"])
        if len(d) < 2 or len(s) < 2:
            continue
        idx = [0] if "슬래브" in m.get("note", "") else [0, 1]
        if any(d[i] and s[i] and abs(s[i] - d[i]) > 0.1 * d[i] for i in idx):
            out.append(f"{SF.floor_label(m['floor'])} {m['mark'] or m['kind']}")
    return list(dict.fromkeys(out))


def _diff_sentence(labels: list[str]) -> str:
    if not labels:
        return "조사된 부재는 구조도면과 실측 수치가 대체로 일치하여 구조도면의 수치를 내진성능 평가에 반영하였다."
    more = f" 등 {len(labels)}개" if len(labels) > 3 else ""
    return f"{', '.join(labels[:3])}{more} 부재가 구조도면과 실측 수치와 상이하여 현장 실측 데이터를 내진성능 평가에 반영하였다."


def fill_members(root, field: dict, d: dict, rebar_rows: list, units, warn: list, drawings: bool = True, member_total: int = 0) -> int:
    from server.sitok import rebar_survey as RV

    members = field["members"]
    tables = [t for t in _outer(root) if t.get("colCnt") == "6" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "NO"
              and _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "조사위치"]
    n = 0
    if members:
        rows = [[str(i + 1), f"{SF.floor_label(m['floor'])}( {m['where']} )" if m["where"] else SF.floor_label(m["floor"]),
                 f"{m['kind']} ({m['mark']})" if m["mark"] else m["kind"], m["design"] or "-", m["measured"] or "-", m["note"]] for i, m in enumerate(members)]
        n += fill_chunks(root, tables, rows, 18, 1, flat=False, one=True)
    else:  # 입력 없으면 빈 줄 하나(10/22 형 "안 적었는데 값이 들어가 있음") — 노랑(10/26)
        fill_chunks(root, tables, [[""] * 6], 18, 1, flat=False, one=True)
        TD.paint_empty(next((t for t in _outer(root) if t.get("colCnt") == "6" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "NO"
                             and _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "조사위치"), None), 1)
        warn.append("부재 단면 줄이 없어 2.2.1 표는 빈칸입니다(현장조사 입력)")
    qty = [x for x in _outer(root) if (x.get("rowCnt"), x.get("colCnt")) == ("2", "4") and "금회조사수량" in _n(rb._cell_text(rb._cells(x).get((0, 3), x)))]
    by = units if isinstance(units, dict) else {"member": units, "rebar": units}  # 항목별 조사단위(10/26) — 부재 단면 표 = member, 철근배근 표 = rebar
    rules = (("모든 조사단위에서 부재 종별로 각각 3개소 이상 조사", "모든 조사단위에서 부재 종별로 각각 9개소 이상 조사하여 구조도면 작성"),  # 부재단면·철근배근(매뉴얼 <표 3-1>)
             ("모든 조사단위에서 부재 종별로 각각 3개소 이상 조사", "모든 조사단위에서 구조도면 작성에 충분한 수량으로서 부재 종별로 각각 3개소 이상"))
    for k, t in enumerate(qty[:2]):
        cells = rb._cells(t)
        _set(cells, (1, 0), f"{d['name']}\n({by['member' if k == 0 else 'rebar']}개층)")  # 조사단위 수(건물 칸 — 기본 지상 층수, 10/22)
        _set(cells, (1, 1), "보유" if drawings else "미보유")
        _set(cells, (1, 2), rules[k][0 if drawings else 1])
        if k == 0:  # 조사 수량 = 칸 수(형이 정한 수량, 10/22 "변경한 수량과 안 맞음")
            _set(cells, (1, 3), f"금회 조사 수량 = {member_total or len(members)}개소")
    # 조사결과 문장 — 2.2.1 다음 첫 견본 문장 = 부재, 2.2.2 다음 = 철근
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    sec = ""
    for p in tops:
        t = _n(_t(p))
        if t.startswith("2.2.1부재단면"):
            sec = "member"
        elif t.startswith("2.2.2철근배근"):
            sec = "rebar"
        elif t.startswith("2.2.3"):
            break
        if t == _n(SAMPLE_MEMBER_DIFF) and sec:
            if sec == "member" and members:
                labels = member_diffs(members)
            elif sec == "rebar" and rebar_rows:
                labels = list(dict.fromkeys(f"{SF.floor_label(x['floor'])} {x.get('mark') or x['kind']}" for x in rebar_rows if RV.mismatch(x)))
            else:
                labels = None  # 입력 없음 — 견본 문장(지상5층 B1부재 …) 지움
            ts = list(p.iter(f"{{{HP}}}t"))
            if ts:
                ts[0].text = _diff_sentence(labels) if labels is not None else ""
                for x in ts[1:]:
                    x.text = ""
                n += 1
    return n


# ---------- 2.2.3 · 2.2.4 코어 ----------
def fill_cores(doc, root, field: dict, rdir: Path, core_doc: dict | None, warn: list) -> int:
    cores = field["cores"]
    st = SF.core_stats(cores)
    n = 0
    if not st["n"]:
        warn.append("코어 압축강도가 없어 2.2.4 강도결정 표·글 숫자는 빈칸입니다(현장조사 입력 — 성적서에서 읽기)")
        _blank_cores(doc, root)
    else:
        m_v = [c["mpa"] for c in cores if c.get("mpa") is not None]  # core_stats는 반올림 값 — 아래 계산은 반올림 전으로
        mm = sum(m_v) / len(m_v)
        ss = (sum((x - mm) ** 2 for x in m_v) / (len(m_v) - 1)) ** 0.5 if len(m_v) > 1 else 0.0
        decided = round(mm - 1.34 * ss if (ss / mm if mm else 0) <= 0.2 else 0.75 * (mm - ss), 1)  # 2.2.4 본문 규칙: s/m ≤ 0.2면 m−1.34s, 넘으면 0.75(m−s)
        vals = {"m": f"{mm:.1f}", "s": f"{ss:.1f}", "s/m": f"{(ss / mm if mm else 0):.2f}", "m-1.34s": f"{mm - 1.34 * ss:.1f}",
                "0.75(m-s)": f"{0.75 * (mm - ss):.1f}", "0.75m": f"{0.75 * mm:.1f}", "설계기준강도": f"{decided:.1f}", "평균강도": f"{mm:.1f}"}
        t = next((t for t in _tables(root) if _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "압축강도(MPa)"  # 부록은 다른 표 안에 들어 있음
                  and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "구분"), None)
        if t is not None:
            cells = rb._cells(t)
            last = int(t.get("rowCnt")) - 1
            slots = sorted(r for (r, c) in cells if c == 1 and 1 <= r < last)
            per = -(-len(m_v) // max(len(slots), 1))
            for k, r in enumerate(slots):
                part = m_v[k * per:(k + 1) * per]
                _set(cells, (r, 1), ", ".join(f"{x:g}" for x in part) if part else "-")
            for (r, c), x in cells.items():
                if c == 2:
                    lab = _n(rb._cell_text(x)).replace("−", "-")
                    if lab in vals:
                        _set(cells, (r, 3), vals[lab])
            nested = next((x for x in t.iter(f"{{{HP}}}tbl") if x is not t), None)
            if nested is not None:
                nc = rb._cells(nested)
                fc = field.get("core_design") or decided
                _set(nc, (2, 0), f"{fc:g}")
                _set(nc, (2, 1), f"{mm:.2f}")
                _set(nc, (2, 2), f"{min(m_v):.2f}")
                _set(nc, (2, 3), f"{len(m_v)}개소 측정")
                _set(nc, (3, 1), f"{0.85 * fc:.2f}")
                _set(nc, (3, 2), f"{0.75 * fc:.2f}")
            n += 1
        replace_loose(doc, SAMPLE_CORE_TITLE, f"콘크리트 코어시험에 의한 강도결정(코어 {len(m_v)}개소)")
        fc = field.get("core_design")
        if fc:
            ok85, ok75 = mm >= 0.85 * fc, min(m_v) >= 0.75 * fc
            judge = ("설계도면상 강도기준의 85% 이상, 각각의 값이 75% 이상으로 조사되었으며" if ok85 and ok75 else
                     f"설계도면상 강도기준({fc:g}MPa)의 85%{' 이상' if ok85 else '를 하회'}, 각각의 값이 75%{' 이상' if ok75 else '를 하회'}하나")
        else:
            judge = "조사되었으며"
        replace_loose(doc, SAMPLE_CORE, f"{min(m_v):g}~{max(m_v):g}MPa(평균 {mm:.1f}MPa)로 {judge}")
        judge2 = ("평균이 설계도면상 강도기준의 85% 이상, 각각의 값이 75% 이상이며" if fc and ok85 and ok75 else
                  f"평균이 설계도면상 강도기준의 85%{' 이상' if fc and ok85 else '를 하회'}, 각각의 값이 75%{' 이상' if fc and ok75 else '를 하회'}하나") if fc else "평균과 각각의 값이"
        for old, new in (("평균이 설계도면상 강도기준의 85%, 각각의 값이 75%를 하회하나", judge2),  # 2.2.4 표 아래 주석·요약의 견본 값(15.8MPa·6개소)
                         ("6개소의 코어가 모두 양호", f"{len(m_v)}개소의 코어가 모두 양호"), ("현장채취값인 15.8MPa", f"현장채취값인 {decided:g}MPa"),
                         ("설계 기준강도 15.8MPa로 측정되어", f"설계 기준강도 {decided:g}MPa로 측정되어"),
                         ("현장조사 설계기준강도 값인 15.8MPa", f"현장조사 설계기준강도 값인 {decided:g}MPa"), ("설계기준강도인 15.8MPa를", f"설계기준강도인 {decided:g}MPa를")):
            replace_loose(doc, old, new)
    # 성적서 그림(2.2.4 "압축강도 시험성적서" 다음 1×1 그림 표들)
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    i = next((k for k, p in enumerate(tops) if _n(_t(p)) == "압축강도시험성적서"), None)
    if i is not None:
        frames = []
        for p in tops[i + 1:i + 8]:
            ts = [t for t in _outer(p) if (t.get("rowCnt"), t.get("colCnt")) == ("1", "1") and rb._pic_slots(t)]
            if ts:
                frames.append((p, ts[0]))
            elif _n(_t(p)):
                break
        pages = _core_pages(core_doc, rdir)
        if pages:
            for k, (p, t) in enumerate(frames):
                if k < len(pages):
                    _put(doc, rb._pic_slots(t)[0][1], pages[k], crop=False)
                    n += 1
                elif p.getparent() is not None:
                    _drop_empty_before(p)  # 성적서 둘째 쪽 칸 앞 쪽 나눔 빈 줄도(남으면 다음 제목 쪽 나눔과 겹쳐 빈 쪽, 10/26)
                    p.getparent().remove(p)
        else:
            warn.append("압축강도 시험성적서가 없어 2.2.4 성적서 그림은 빈칸입니다(서류 칸)")
            for k, (p, t) in enumerate(frames):
                if k == 0:
                    _put(doc, rb._pic_slots(t)[0][1], blank_png(rdir), crop=False)
                elif p.getparent() is not None:
                    _drop_empty_before(p)
                    p.getparent().remove(p)
    return n


def _blank_cores(doc, root) -> None:
    """코어 입력이 없을 때 — 2.2.4 강도결정 표 값 칸·안쪽 표를 비우고, 본문·주석의 견본 숫자는 "-"."""
    t = next((t for t in _tables(root) if _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "압축강도(MPa)"
              and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "구분"), None)
    if t is not None:
        cells = rb._cells(t)
        last = int(t.get("rowCnt")) - 1
        for (r, c) in list(cells):
            if (c == 1 and 1 <= r < last) or c == 3:
                _set(cells, (r, c), "")
                TD.paint(cells.get((r, c)))  # 노랑(10/26)
        nested = next((x for x in t.iter(f"{{{HP}}}tbl") if x is not t), None)
        if nested is not None:
            nc = rb._cells(nested)
            for rc in ((2, 0), (2, 1), (2, 2), (2, 3), (3, 1), (3, 2)):
                _set(nc, rc, "")
                TD.paint(nc.get(rc))
    for old, new in ((SAMPLE_CORE, "-~-MPa(평균 -MPa)로 조사되었으며"), (SAMPLE_CORE_TITLE, "콘크리트 코어시험에 의한 강도결정(코어 -개소)"),
                     ("6개소의 코어가 모두 양호", "-개소의 코어가 모두 양호"), ("현장채취값인 15.8MPa", "현장채취값인 -MPa"),
                     ("설계 기준강도 15.8MPa로 측정되어", "설계 기준강도 -MPa로 측정되어"), ("현장조사 설계기준강도 값인 15.8MPa", "현장조사 설계기준강도 값인 -MPa"),
                     ("설계기준강도인 15.8MPa를", "설계기준강도인 -MPa를")):
        replace_loose(doc, old, new)


def _core_pages(core_doc: dict | None, rdir: Path) -> list[Path]:
    if not core_doc or not core_doc.get("rel"):
        return []
    src = rdir / core_doc["rel"]
    if not src.exists():
        return []
    if src.suffix.lower() != ".pdf":
        return [src]
    import pymupdf

    out_dir = rdir / "보고서그림"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    with pymupdf.open(src) as d:
        for k, pg in enumerate(list(d)[:2]):
            p = out_dir / f"성적서_{k + 1}.png"
            pg.get_pixmap(dpi=150).save(p)
            out.append(p)
    return out


# ---------- 2.3 · 2.4 글 ----------
def fill_texts(root, field: dict, doc=None) -> int:
    tx = field["texts"]
    n = 0
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    order = ["crack", "leak", "rebar", "aging", "steel"]
    on = False
    k = 0
    for p in tops:
        t = _n(_t(p))
        if t == "2.3외관조사":  # 제목 문단과 같을 때만(목차 줄 "2.3 외관조사24"는 아님)
            on = True
            continue
        if t.startswith("2.4") and on:
            break
        if not on:
            continue
        for tb in _outer(p):
            cells = rb._cells(tb)
            if _n(rb._cell_text(cells.get((0, 0), tb))) == "구분" and _n(rb._cell_text(cells.get((1, 0), tb))) == "분석결과" and k < len(order):
                _set(cells, (1, 1), tx[order[k]])
                if not tx[order[k]]:
                    _no_bullet(doc, cells[(1, 1)])
                k += 1
                n += 1
    for tb in _outer(root):  # 2.4.1·2.4.2 — 조사결과 글(비면 빈칸), 붉은 견본 글자는 검정으로(10/22)
        whole = _n(_t(tb))
        cells = rb._cells(tb)
        if "건물외중량물" in whole and (3, 0) in cells:
            _set(cells, (3, 0), "\n".join(f"· {x.strip()}" for x in tx["heavy"].split("\n") if x.strip()))
            _blacken(cells[(3, 0)])
            n += 1
        elif "건물외부마감재" in whole and (2, 0) in cells:
            _set(cells, (2, 0), tx["finish"])
            _blacken(cells[(2, 0)])
            n += 1
    return n


# ---------- 2.4.3 조적조 ----------
def fill_masonry(root, field: dict, warn: list) -> int:
    rows = field["masonry"]
    tables = [t for t in _outer(root) if t.get("colCnt") == "11" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "층"]
    if not rows:
        fill_chunks(root, tables, [[""] * 11], 60, 2, flat=True, one=True)
        TD.paint_empty(next((t for t in _outer(root) if t.get("colCnt") == "11" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "층"), None), 2)  # 노랑(10/26)
        warn.append("조적조 줄이 없어 2.4.3 조적벽 결과표는 빈칸입니다(현장조사 입력)")
        return 0
    rows = sorted(rows, key=lambda x: (x["floor"], x["kind"] != "채움벽", x["mid"]))
    vals = [[SF.floor_label(x["floor"]).replace("지상", "지상 ").replace("지하", "지하 "), x["kind"], x["mid"], _fmt(x["height"], 0) if x["height"] else "-",
             _fmt(x["width"], 0) if x["width"] else "-", x["thick"], x["dir"], x["expose"].replace(" ", "\n", 1), f"{x['finish']}" if x["finish"] is not None else "-",
             x["boundary"], x["applied"]] for x in rows]
    return fill_chunks(root, tables, vals, 20, 2, flat=True, one=True)


# ---------- 2.5 지반 ----------
def ground_result_image(crop: Path | None, hole: dict, dest: Path) -> Path:
    """BH 결과 그림 = 지반조사보고서 Result Analysis 위쪽 표(잘라 온 것) + 지반의 분류 표·comment(견본 모양으로 그림)."""
    from PIL import Image, ImageDraw, ImageFont

    W = 1240

    def font(sz, bold=False):
        for name in (("malgunbd.ttf" if bold else "malgun.ttf"), "malgun.ttf"):
            try:
                return ImageFont.truetype(f"C:/Windows/Fonts/{name}", sz)
            except OSError:
                continue
        return ImageFont.load_default()

    parts = []
    if crop and Path(crop).exists():
        im = Image.open(crop).convert("RGB")
        parts.append(im.resize((W, int(im.height * W / im.width))))
    cls = hole.get("cls") or ""
    rows = [("S1", "암반 지반", "1 미만", "-"), ("S2", "얕고 단단한 지반", "1~20 이하", "260 이상"), ("S3", "얕고 연약한 지반", "1~20 이하", "260 미만"),
            ("S4", "깊고 단단한 지반", "20 초과", "180 이상"), ("S5", "깊고 연약한 지반", "20 초과", "180 미만"),
            ("S6", "부지 고유의 특성평가 및 지반응답해석이 필요한 지반", "", "")]
    rh, top = 46, 70
    img = Image.new("RGB", (W, top + rh * (len(rows) + 2) + 230), "white")
    dr = ImageDraw.Draw(img)
    f1, f2, fb = font(22), font(20), font(22, True)
    line = (40, 40, 40)
    # 머리 줄: 지반의 분류 | 기반암의 깊이 | 값 | 전단파속도 | 값
    cols = [(20, 230), (230, 520), (520, 700), (700, 1040), (1040, 1220)]
    head = ["지반의 분류", "기반암의 깊이, H(m)", (hole.get("depth") or "").replace(" ", ""), "토층평균전단파속도(m/s)", f"{hole.get('vs') or ''}"]
    for (x0, x1), txt, k in zip(cols, head, range(5)):
        dr.rectangle([x0, 10, x1, 10 + rh], outline=line, width=2, fill=(235, 241, 250) if k in (0, 1, 3) else (255, 255, 255))
        fnt = fb if k in (0, 2, 4) else f2
        tw = dr.textlength(txt, font=fnt)
        dr.text(((x0 + x1 - tw) / 2, 10 + (rh - 26) / 2), txt, fill=(0, 60, 160) if k in (2, 4) else (0, 0, 0), font=fnt)
    # 분류 표
    cx = [20, 150, 640, 860, 1080, 1220]
    y = top
    heads = ["지반종류", "지반종류의 호칭", "기반암 깊이 H(m)", "전단파속도(m/s)", "지반등급"]
    for k, txt in enumerate(heads):
        dr.rectangle([cx[k], y, cx[k + 1], y + rh], outline=line, width=2, fill=(235, 241, 250))
        tw = dr.textlength(txt, font=fb if k == 4 else f2)
        dr.text(((cx[k] + cx[k + 1] - tw) / 2, y + (rh - 24) / 2), txt, fill=(200, 0, 0) if k == 4 else (0, 0, 0), font=fb if k == 4 else f2)
    for code, name, depth, vs in rows:
        y += rh
        cells = [code, name, depth, vs, "◎" if code == cls else ""]
        for k, txt in enumerate(cells):
            dr.rectangle([cx[k], y, cx[k + 1], y + rh], outline=line, width=1)
            fnt = f1 if dr.textlength(txt, font=f1) < cx[k + 1] - cx[k] - 10 else font(16)
            tw = dr.textlength(txt, font=fnt)
            dr.text(((cx[k] + cx[k + 1] - tw) / 2, y + (rh - 24) / 2), txt, fill=(0, 0, 0), font=fnt)
    y += rh + 24
    ad = hole.get("apply_depth")
    dr.text((20, y), "comment", fill=(0, 0, 0), font=font(26, True))
    dr.text((190, y), f"기반암 적용심도 : {ad:g} m (내진설계기준 KDS 17 10 00 : 2024)" if ad is not None else "기반암 적용심도 : - (내진설계기준 KDS 17 10 00 : 2024)",
            fill=(0, 0, 0), font=font(24, True))
    notes = ["1. 국지적인 토질조건, 지질조건과 지표 및 지하 지형이 지반운동에 미치는 영향을 고려하기 위하여 지반을 S1~S6의 6종으로 분류한다.",
             "2. 기반암 깊이와 무관하게 토층 평균 전단파속도가 120m/s 이하인 지반은 S5 지반으로 분류한다.",
             "3. 지반종류 S6은 부지 고유의 특성평가 및 지반응답해석이 필요한 지반이다."]
    for k, s in enumerate(notes):
        dr.text((20, y + 48 + k * 34), s, fill=(30, 30, 30), font=font(18))
    parts.append(img)
    total = Image.new("RGB", (W, sum(p.height for p in parts) + 20 * (len(parts) - 1)), "white")
    yy = 0
    for p in parts:
        total.paste(p, (0, yy))
        yy += p.height + 20
    dest.parent.mkdir(parents=True, exist_ok=True)
    total.save(dest, "PNG")
    return dest


def _ole_to_pic(doc, ole, pic_tpl, path: Path) -> bool:
    """OLE 개체(견본 위치도)를 그림으로 — 그림 틀을 복사해 OLE 크기로."""
    sz = ole.find(f"{{{HP}}}curSz")
    if sz is None:
        sz = ole.find(f"{{{HP}}}sz")
    w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None else (40000, 30000)
    pic = copy.deepcopy(pic_tpl)
    rb._new_ids(pic)
    data = path.read_bytes()
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    canvas = Image.new("RGB", (max(int(w / 7200 * rb.PIC_DPI), 1), max(int(h / 7200 * rb.PIC_DPI), 1)), "white")
    im.thumbnail(canvas.size)
    canvas.paste(im, ((canvas.width - im.width) // 2, (canvas.height - im.height) // 2))
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    _size_pic(pic, w, h, buf.getvalue(), inline=True)
    img = next(pic.iter(f"{{{HC}}}img"), None)
    if img is None:
        return False
    img.set("binaryItemIDRef", doc.add_image(buf.getvalue()))
    ole.addprevious(pic)
    ole.getparent().remove(ole)
    return True


def fill_ground(doc, root, ground: dict | None, rdir: Path, warn: list) -> int:
    holes = (ground or {}).get("holes") or []
    if not holes:
        warn.append("지반조사보고서가 없어 2.5 지반 및 기초 값은 비우고 노랗게 칠했습니다(서류 칸에 올리면 채워짐)")
        key = _n(SAMPLE_GROUND)[:12]
        for t in _tables(root):  # 요약 "가. 지반 조사 결과" 칸 — 견본 문장(S2 지반·BH 속도) 대신 빈칸 + 노랑(10/26, 있으면 SAMPLE_GROUND를 바꿈)
            for tc in rb._cells(t).values():
                if key in _n(rb._cell_text(tc)) and next(tc.iter(f"{{{HP}}}tbl"), None) is None:
                    rb._set_lines(tc, [""])
                    _no_bullet(doc, tc)
                    TD.paint(tc)
        return 0
    gdir = rdir / "지반"
    n = 0
    replace_loose(doc, SAMPLE_BORING, f"본 구조물은 {len(holes)}개소 시추조사를")
    replace_loose(doc, SAMPLE_GROUND, SD.ground_phrase(holes))
    tabs = _outer(root)
    photo_tbls = [t for t in tabs if _n(rb._cell_text(rb._cells(t).get((0, 0), t))).startswith("지반조사현황(BH")]
    result_tbls = [t for t in tabs if re.fullmatch(r"BH-?\d+지반조사결과", _n(rb._cell_text(rb._cells(t).get((0, 0), t))))]
    pic_tpl = copy.deepcopy(rb._pic_slots(result_tbls[0])[0][1]) if result_tbls and rb._pic_slots(result_tbls[0]) else None
    # 위치도(견본은 OLE)
    if ground.get("map") and (gdir / ground["map"]).exists():
        mt = next((t for t in tabs if _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "지반조사현황"), None)
        if mt is not None:
            cell = rb._cells(mt).get((1, 0))
            ole = next(cell.iter(f"{{{HP}}}ole"), None) if cell is not None else None
            slot = rb._pic_slots(mt)
            if slot:
                n += _put(doc, slot[0][1], gdir / ground["map"], crop=False)
            elif ole is not None and pic_tpl is not None:
                n += _ole_to_pic(doc, ole, pic_tpl, gdir / ground["map"])

    def multiply(tbls: list, write) -> None:
        if not tbls:
            return
        paras = [_top_p(t) for t in tbls]
        tpl = copy.deepcopy(paras[-1])
        used = []
        for k, h in enumerate(holes):
            if k < len(paras):
                p = paras[k]
            else:
                p = copy.deepcopy(tpl)
                rb._new_ids(p)
                used[-1].addnext(p)
            used.append(p)
            write(_outer(p)[0], h)
        for p in paras[len(holes):]:
            if p.getparent() is not None:
                p.getparent().remove(p)

    def write_photos(t, h):
        nonlocal n
        cells = rb._cells(t)
        _set(cells, (0, 0), f"지반 조사 현황({h['bh']})")
        slots = rb._pic_slots(t)
        for (rc, pic), (slot, label, _keys) in zip(slots, SD.GROUND_SLOTS):
            _set(cells, (rc[0] + 1, rc[1]), f"{h['bh']} {label}")
            name = (h.get("photos") or {}).get(slot)
            if name and _put(doc, pic, gdir / name, crop=True):
                n += 1
            else:  # 없으면 빈칸(10/22 형 "없으면 공란이 정상")
                _put(doc, pic, blank_png(rdir), crop=False)
                warn.append(f"{h['bh']} {label} 사진 없음(빈칸) — 지반조사 확인")

    def write_result(t, h):
        nonlocal n
        cells = rb._cells(t)
        _set(cells, (0, 0), f"{h['bh']} 지반조사 결과")
        crop = gdir / h["result"] if h.get("result") else None
        img = ground_result_image(crop, h, rdir / "보고서그림" / f"지반결과_{h['bh']}.png")
        slot = rb._pic_slots(t)
        if slot and _put(doc, slot[0][1], img, crop=False):
            n += 1

    multiply(photo_tbls, write_photos)
    multiply(result_tbls, write_result)
    return n


def fill_all(doc, root, r, f, rdir: Path, d: dict, warn: list, front_taken: bool = False, vendor_text: str = "") -> int:
    """seismic_build.build에서 — 현장조사 입력·서류(지반·성적서)·건축물대장 값으로 나머지 칸. front_taken = 외주 견본 전체에서 결과표 나~마를 옮김."""
    from sqlalchemy.orm import object_session

    sv = r.survey or {}
    mt = [t for t in _outer(root) if t.get("colCnt") == "6" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "NO"
          and _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "조사위치"]
    member_tpl = copy.deepcopy(_top_p(mt[0])) if mt else None  # 2.3 결함 표 틀(채우기 전에)
    field = SF.normalize(sv.get("seismic_field"))
    docs = sv.get("seismic_docs") or {}
    ground = (docs.get("ground") or {}).get("parsed")
    reg = (f.ledger or {}).get("register") or {}
    units = SD.item_units(f)  # 항목별 조사단위(안 고쳤으면 모두 전체 단위, 10/26)
    drawings = SD.has_drawings(f)
    grade = reg.get("grade") or ("특등급" if re.search(r"교육|학교", f.main_use or "") else "1등급")
    member_total = sum(SD.member_plan(f, field.get("member_plan")).values())  # 부재 단면 칸 수(형이 정한 수량)
    n = fill_photos(doc, root, field, rdir, warn, f)
    n += fill_summary(root, field, ground, drawings, grade, member_total, SD.min_counts(units, grade, drawings)["core"], doc)
    n += fill_body_results(root, field, doc)  # 본문 조사결과 = 조사결과 글(요약 표와 같은 글, 10/22) — 부재 단면 견본 문장 처리보다 먼저(끊김 막음)
    n += fill_grade(root, reg.get("grade") or ("특등급" if re.search(r"교육|학교", f.main_use or "") else "1등급"), warn)
    if reg:
        n += fill_history(doc, root, f, reg)
    n += fill_members(root, field, d, d.get("rebar") or [], units, warn, drawings, member_total)
    filled = len(field["members"])
    if filled and filled < member_total:
        warn.append(f"부재 단면 입력 {filled}/{member_total}칸 — 조사 수량은 칸 수 {member_total}개소로 적었습니다")
    n += fill_cores(doc, root, field, rdir, docs.get("core"), warn)
    n += fill_texts(root, field, doc)
    n += fill_masonry(root, field, warn)
    n += fill_ground(doc, root, ground, rdir, warn)
    n += fix_ground_indent(doc, root)  # 2.5 글머리 시작점·내어쓰기(10/22)
    n += fill_size_plans(doc, root, f, reg, rdir, warn, field)
    for p in (p for p in root if p.tag == f"{{{HP}}}p" and _n(_t(p)) == "2.2.3콘크리트압축강도"):  # 새 쪽에서(10/22 형 "2.2.3부터 다음 페이지로")
        p.set("pageBreak", "1")
    for p in [p for p in root if p.tag == f"{{{HP}}}p" and _t(p).strip() == "`" and not _outer(p)]:  # 견본에 남은 군더더기 글자(2.2.4 끝)
        _para_text(p, "")
    db = object_session(r)
    if db is not None:
        n += fill_defects(root, defect_rows(db, r.id), member_tpl)
    if not front_taken:
        n += fill_result_na(root, d, reg, ground, field)
    saved = (field.get("summary") or "").strip()
    chief = d["persons"][0]["name"] if d.get("persons") else ""
    n += fill_opinion(root, saved or summary_text(d, field, f, reg, vendor_text), chief)
    if not saved:
        warn.append("요약문 종합의견은 자동 문장입니다 — 현장조사 입력 📝에서 고치거나 🤖 AI 초안")
    return n


# ---------- 코어 강도 결정(2.2.4 규칙) ----------
def core_decided(cores: list[dict]) -> tuple[float, float, float] | None:
    """(평균 m, 표준편차 s, 설계기준강도) — s/m ≤ 0.2면 m−1.34s, 넘으면 0.75(m−s)(2.2.4 본문)."""
    v = [c["mpa"] for c in cores if c.get("mpa") is not None]
    if not v:
        return None
    mm = sum(v) / len(v)
    ss = (sum((x - mm) ** 2 for x in v) / (len(v) - 1)) ** 0.5 if len(v) > 1 else 0.0
    return mm, ss, round(mm - 1.34 * ss if (ss / mm if mm else 0) <= 0.2 else 0.75 * (mm - ss), 1)


# ---------- 요약문 책임기술자 종합의견(10/22 민재형 "둘 다 가능하게" — 견본 문장 채우기 + AI 초안) ----------
MANUAL = "「학교시설 내진성능평가 및 보강매뉴얼(2021.10, 교육부)」"


def vendor_results(text: str) -> dict:
    """외주 글(5·6·7장)에서 보유성능지수 보강 전·후(X, Y), 보강안. 견본은 "보유성능지수 = 0.80 (불만족)"이 X·Y 차례로, 보강 후는 앞에 "보강후".
    바로 앞 값 다음부터 이 값까지 글에 "보강후"가 있으면 보강 후. 문장 모양("보유성능지수는 X방향 1.12, Y방향 1.05")도 봄."""
    t = re.sub(r"\s+", " ", text or "")
    out: dict = {}
    before, after, prev = [], [], 0
    for m in re.finditer(r"보유성능지수\s*=\s*([\d.]+)", t):
        (after if re.search(r"보강\s*후", t[prev:m.start()]) else before).append(m.group(1))
        prev = m.end()
    if len(before) >= 2:
        out["before"] = (before[0], before[1])
    if len(after) >= 2:
        out["after"] = (after[0], after[1])
    for m in re.finditer(r"보유성능지수(?:가|는)?\s*X방향\s*([\d.]+)\s*,?\s*Y방향\s*([\d.]+)", t):
        out.setdefault("after" if "보강" in t[max(0, m.start() - 120):m.start()] else "before", (m.group(1), m.group(2)))
    m = re.search(r"보강안은\s*(.{2,30}?)\s*보강으로", t)
    if m:
        out["method"] = m.group(1).strip()
    return out


def summary_text(d: dict, field: dict, f, reg: dict, vendor_text: str = "") -> str:
    """견본 문장 그대로 값만 이번 건으로 — 우리 값(이름·사용승인·경과년수·등급·도면·중량물·결함·코어) + 외주 값(보유성능지수·보강안, 없으면 그 문장 뺌)."""
    import datetime

    from server.api.routers.sitok import _facility_dir
    from server.sitok import drawings as D

    name = d["name"]
    comp = d.get("completion")
    ref = d.get("period_start") or datetime.date.today()
    grade = reg.get("grade") or ("특등급" if re.search(r"교육|학교", d.get("use") or "") else "1등급")
    has_dwg = bool(D.items(f, "struct", _facility_dir(f)) or D.items(f, "schedule", _facility_dir(f)) or (f.ledger or {}).get("rebar_schedule"))
    lines = [f"본 내진성능평가 대상 건축물은 “{name}”으로 " + (f"{comp.year}년 최초 사용승인 되어 약 {ref.year - comp.year}년이 경과된 시설물로 " if comp else "")
             + f"내진 등급은 {grade}이며 해당 건축물은 " + ("도면이 존재하여 도면과 현장조사를 토대로" if has_dwg else "도면이 없어 현장조사를 토대로") + " 내진성능평가를 실시하였다."]
    heavy = field["texts"]["heavy"].strip()
    if heavy:
        lines.append(heavy if heavy.startswith("육안조사") else f"육안조사 결과, {heavy}")
    crack = field["texts"]["crack"].strip()
    if crack:
        lines.append(f"외관 조사 결과, {crack}" if not crack.startswith(("외관", "본 시설물", "육안")) else crack)
    lines.append("현장조사 필수항목 및 세부기준에 따라 조사 항목 및 수량을 선정하고, 이에 따라 부재규격조사, 구조성능 저하 및 손상조사, 중량물조사, 마감재조사, "
                 "콘크리트 코어 시험, 철근배근상태 조사, 조적벽체 상태조사를 실시하였다.")
    cd = core_decided(field["cores"])
    if cd:
        lines.append(f"평가대상 건축물에 콘크리트 코어채취를 실시한 결과 {MANUAL}에 따른 설계 기준강도 {cd[2]:g}MPa로 측정되어 이를 내진성능평가에 적용하였다.")
    v = vendor_results(vendor_text)
    if v.get("before"):
        x, y = v["before"]
        ok = min(float(x), float(y)) >= 1.0
        lines.append(f"{MANUAL}에 따른 내진성능 선형해석평가를 실시한 결과, 구조모델에 대한 선형해석평가 결과 보유성능지수가 X방향 {x}, Y방향 {y}로 성능수준을 "
                     + ("만족하는 것으로 검토되어 보강이 불필요한 것으로 판단됨." if ok else "불만족하는 것으로 검토되어 보강이 필요한 것으로 판단됨."))
        if not ok and v.get("after"):
            ax, ay = v["after"]
            lines.append(f"해당 건축물의 X, Y방향으로 보강하여 선형해석법을 수행하였으며, 보강안은 {v.get('method') or '○○'} 보강으로 보강안에 따른 선형해석평가 결과 "
                         f"보유성능지수는 X방향 {ax}, Y방향 {ay}로 산정되어 안전한 것으로 평가됨.")
    return "\n".join(lines)


def fill_opinion(root, text: str, chief: str) -> int:
    """요약문 표 두 곳(요약 4×3 "(인)" · 결과 요약 4×5 "(서명)") — 글과 책임기술자 이름(뒤 괄호 모양은 그대로)."""
    n = 0
    for t in _outer(root):
        cells = rb._cells(t)
        if _n(rb._cell_text(cells.get((0, 0), t))) != "책임기술자종합의견":
            continue
        _set(cells, (2, 0), text)
        sig = next((q for q in cells[(3, 0)].iter(f"{{{HP}}}p") if _n(_t(q)).startswith("책임기술자")), None) if (3, 0) in cells else None
        m = re.match(r"(\s*책\s*임\s*기\s*술\s*자\s*:\s*)(.*?)(\s*\(.*\)\s*)$", _t(sig)) if sig is not None else None
        if chief and m:  # 서명 문단 글만 — 칸째 다시 쓰면 첫 빈 문단(붉은 작은 글자) 모양이 씌워짐(10/22 형 "검은색 글자로", "글씨 크기와 색 견본과 안 맞음")
            ts = list(sig.iter(f"{{{HP}}}t"))
            ts[0].text = f"{m.group(1)}{' '.join(chief)}{m.group(3)}"
            for x in ts[1:]:
                x.text = ""
        n += 1
    return n


# ---------- 2.3 결함 현황 표(10/22 민재형 "층별 외관조사망도는 없어 — 결함, 사진첩만") ----------
def defect_rows(db, report_id: int) -> list[list]:
    from server.api.routers.sitok_defects import album_floors

    out = []
    for floor, rows in album_floors(db, report_id):
        for x in rows:
            size = ", ".join(s for s in (f"{x['폭']}mm" if x.get("폭") not in (None, "", "-") else "", f"{x['길이']}m" if x.get("길이") not in (None, "", "-") else "",
                                         f"{x['개수']}개소" if x.get("개수") not in (None, "", "-") else "") if s) or "-"
            prog = " / ".join(s for s in (x.get("진행유무") or "", x.get("결함원인") or "") if s and s != "-") or "-"
            out.append([str(len(out) + 1), f"{floor} {x.get('구분') or ''}".strip(), x.get("부재") or "-", x.get("결함유형") or "-", size, prog])
    return out


def fill_defects(root, rows: list[list], member_tpl) -> int:
    """【 금회 균열 및 기타 결함현황 조사 결과표 】 — 견본 층별 망도 그림(문단들)을 빼고 결함 표(부재 단면 표 틀, 18줄씩) + "부록4 사진첩 참조"."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    i = next((k for k, p in enumerate(tops) if _n(_t(p)) == "【금회균열및기타결함현황조사결과표】"), None)
    if i is None or member_tpl is None:
        return 0
    j = next((k for k in range(i + 1, len(tops)) if _n(_t(tops[k])).startswith("2.4")), len(tops))
    note = next((copy.deepcopy(p) for p in tops[i + 1:j] if "부록4" in _n(_t(p))), None)
    for p in tops[i + 1:j]:
        root.remove(p)
    tp = copy.deepcopy(member_tpl)
    rb._new_ids(tp)
    for x in tp.iter(f"{{{HP}}}t"):  # 부재 단면 표 틀 문단에 붙은 "※ □ : 조사불가" 주석(표 밖 글)은 다 뺌
        if next(x.iterancestors(f"{{{HP}}}tbl"), None) is None:
            for pc in rb._pieces(x):
                pc.text = ""
    if note is not None:
        tops[i].addnext(note)
    tops[i].addnext(tp)
    t = _outer(tp)[0]
    cells = rb._cells(t)
    for c, label in enumerate(("NO", "위치", "부재", "결함유형", "크기·개수", "진행유무·원인")):
        _set(cells, (0, c), label)
    return fill_chunks(root, [t], rows or [["-", "-", "-", "결함 없음", "-", "-"]], 18, 1, flat=False, one=True)


# ---------- 1.2 건물 길이·층별 평면도 ----------
PLAN_TITLE = re.compile(r"(지붕및옥탑층|옥탑지붕|옥탑층|옥탑|지붕층|지붕|기초|(?:지하|지상)\d+층|\d+층)평면도")


def plan_title(text: str) -> str | None:
    """도면 글에서 평면도 제목 — "지붕 및 옥탑층"·"지상 5층"·"지하 1층"(표제란·도면 아래 제목에 여러 번 나오면 가장 많은 것). 없으면 None."""
    import collections

    found = PLAN_TITLE.findall(re.sub(r"\s", "", text or ""))
    if not found:
        return None
    name = collections.Counter(found).most_common(1)[0][0]
    name = name.replace("지붕및옥탑층", "지붕 및 옥탑층")
    name = re.sub(r"^(지하|지상)(\d+)층$", r"\1 \2층", name)
    return re.sub(r"^(\d+)층$", r"지상 \1층", name)


def _plan_order(name: str) -> float:
    """층 차례 — 기초 → 지하(깊은 데부터) → 지상 1층… → 옥탑 → 지붕."""
    m = re.search(r"(지하|지상)?\s*(\d+)층", name)
    if "기초" in name:
        return -100
    if "옥탑지붕" in name:
        return 950
    if "옥탑" in name:
        return 900
    if "지붕" in name:
        return 940
    if m:
        return -int(m[2]) if m[1] == "지하" else int(m[2])
    return 1000


def plan_images(f, rdir: Path) -> list[tuple[str, Path]]:
    """서류 칸 층별 평면도 → [(제목, 그림)] — 이름은 도면에 적힌 제목(10/26 형 "도면상 네이밍으로" — 호원초 첫 쪽이 지붕인데 "지상 1층"이었음),
    없으면 파일 이름에 "층"이 있으면 그 이름, 그것도 없으면 차례대로 지상 1층부터. 제목을 읽은 것은 층 차례(지하 → 지상 → 옥탑 → 지붕)로."""
    import pymupdf

    from server.api.routers.sitok import _facility_dir
    from server.sitok import drawings as D

    out: list[tuple[float, int, str, Path]] = []
    cache = rdir / "보고서그림"
    cache.mkdir(parents=True, exist_ok=True)
    k = 0
    for it in D.items(f, "floorplan", _facility_dir(f)):  # 서류 칸 "층별 평면도"(키 floorplan — "plan"은 과업수행계획서)
        p = Path(it["path"])
        stem = Path(it.get("name") or p.name).stem
        if p.suffix.lower() == ".pdf":
            with pymupdf.open(p) as doc:
                for pg in doc:
                    k += 1
                    img = cache / f"평면도_{k}.png"
                    pg.get_pixmap(dpi=130).save(img)
                    title = plan_title(pg.get_text())
                    cap = f"{title} 평면도" if title else f"{stem} 평면도" if "층" in stem and doc.page_count == 1 else f"지상 {k}층 평면도"
                    out.append((_plan_order(title) if title else 2000 + k, k, cap, img))
        else:
            k += 1
            cap = f"{stem} 평면도" if "층" in stem else f"지상 {k}층 평면도"
            out.append((_plan_order(stem) if "층" in stem else 2000 + k, k, cap, p))
    return [(cap, img) for _, _, cap, img in sorted(out)]


def _put_full(doc, pic, path: Path) -> bool:
    """도면 그림을 원본 해상도 그대로 틀에 — 틀 비율로 흰 여백만 둘러 PNG, 크기는 틀(_size_pic: 원래 크기·자르기를 픽셀로)이라 한글이 줄여 그림
    (10/26 형 "도면 화질저하" — 전엔 틀 크기 96dpi JPEG로 줄여 넣어 566px, 이제 원본 2149px → PDF 속 364dpi, 한 장 약 120KB)."""
    from PIL import Image

    img = next(pic.iter(f"{{{HC}}}img"), None)
    sz = pic.find(f"{{{HP}}}curSz")
    if img is None or sz is None or path is None or not Path(path).exists():
        return False
    w, h = int(sz.get("width") or 0), int(sz.get("height") or 0)
    if w <= 0 or h <= 0:
        return False
    im = Image.open(path).convert("RGB")
    r = w / h
    cw, ch = (im.width, round(im.width / r)) if im.width / im.height > r else (round(im.height * r), im.height)
    canvas = Image.new("RGB", (cw, ch), "white")
    canvas.paste(im, ((cw - im.width) // 2, (ch - im.height) // 2))
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    img.set("binaryItemIDRef", doc.add_image(data, "png", "image/png"))
    _size_pic(pic, w, h, data)
    return True


def _pic_turned(t) -> bool:
    ri = rb._pic_slots(t)[0][1].find(f"{{{HP}}}rotationInfo") if rb._pic_slots(t) else None
    return ri is not None and (ri.get("angle") or "0") not in ("0", "360")


def fill_size_plans(doc, root, f, reg: dict, rdir: Path, warn: list, field: dict | None = None) -> int:
    n = 0
    lx, ly = reg.get("length_x"), reg.get("length_y")
    t = next((t for t in _outer(root) if (t.get("rowCnt"), t.get("colCnt")) == ("8", "4") and _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "층수"), None)
    if t is not None:
        cells = rb._cells(t)
        _set(cells, (3, 3), f"장변방향 (X방향) {float(lx):g}m" if lx else "장변방향 (X방향) -")
        _set(cells, (4, 3), f"단변방향 (Y방향) {float(ly):g}m" if ly else "단변방향 (Y방향) -")
        n += 1
        if not (lx or ly):
            warn.append("1.2 건물 길이(장변·단변)가 없어 \"-\"입니다(건 화면 🏢 건물 정보)")
        if rb._pic_slots(t):  # 1.2 표 안 전경 사진 — 현장조사 입력 "시설물 전경", 없으면 빈칸(10/22 형 "전경 없는데 들어가 있음")
            front = ((field or {}).get("photos") or {}).get("front") or {}
            n += _put_or_blank(doc, rb._pic_slots(t)[0][1], (rdir / front["rel"]) if front.get("rel") else None, rdir)
    plans = plan_images(f, rdir)
    tables = [t for t in _outer(root) if (t.get("rowCnt"), t.get("colCnt")) == ("3", "4") and rb._pic_slots(t)
              and _n(rb._cell_text(rb._cells(t).get((2, 0), t))).endswith("평면도")]
    if not tables:
        return n
    if not plans:  # 없으면 첫 칸만 빈칸으로
        warn.append("1.2 층별 평면도가 없어 빈칸입니다(건 화면 서류 칸 층별 평면도)")
        plans = [("평면도", blank_png(rdir))]
    paras = [_top_p(t) for t in tables]
    tpl = copy.deepcopy(paras[0])  # 첫 평면도 칸(회전 없는 가로 틀) — 견본 다섯째 칸은 그림 틀이 90° 돌아 있음(10/22 형 "평면도가 세로로 회전됨")
    used = []
    for k, (cap, img) in enumerate(plans):
        if k < len(paras) and not _pic_turned(next(x for x in _outer(paras[k]) if rb._pic_slots(x))):
            p = paras[k]
        else:
            p = copy.deepcopy(tpl)
            rb._new_ids(p)
            (used[-1] if used else paras[0]).addnext(p)
            if k < len(paras) and paras[k].getparent() is not None:
                paras[k].getparent().remove(paras[k])
        used.append(p)
        tb = next(x for x in _outer(p) if rb._pic_slots(x))
        _set(rb._cells(tb), (2, 0), cap)
        n += _put_full(doc, rb._pic_slots(tb)[0][1], img)  # 원본 해상도(10/26)
    for p in paras[len(plans):]:
        if p.getparent() is not None and p not in used:
            p.getparent().remove(p)
    return n


# ---------- 결과표 나 — 외주가 3~7장만 줄 때 우리가 아는 값 ----------
def _right_of(cells: dict, r: int, c: int):
    nxt = sorted(cc for (rr, cc) in cells if rr == r and cc > c)
    return (r, nxt[0]) if nxt else None


def fill_result_na(root, d: dict, reg: dict, ground: dict | None, field: dict) -> int:
    t = next((t for t in _outer(root) if t.get("colCnt") == "13" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))).startswith("가.일반현황")), None)
    if t is None:
        return 0
    grade = reg.get("grade") or "특등급"
    imp = {"특등급": "1.5", "1등급": "1.2", "2등급": "1.0"}.get(grade, "1.5")
    holes = (ground or {}).get("holes") or []
    cd = core_decided(field["cores"])
    vals = {"층수": (f"지하{d['below']}층/" if d.get("below") else "") + f"지상{d.get('above') or 0}층",
            "건물높이": f"{d['height']:g}m" if d.get("height") else None,
            "지반종류": holes[0].get("cls") if holes and holes[0].get("cls") else None,
            "내진설계여부": reg.get("seismic_design") or None,
            "중요도/내진등급": f"{imp}/{grade}", "콘크리트": f"{cd[2]:g}MPa" if cd else None}
    cells = rb._cells(t)
    n = 0
    for (r, c), x in sorted(cells.items()):
        if r < 7:
            continue
        lab = _n(rb._cell_text(x))
        if lab in vals and vals[lab]:
            rc = _right_of(cells, r, c)
            if rc:
                _set(cells, rc, vals[lab])
                n += 1
    return n


# ---------- 목차 쪽 번호(첫 PDF로 세어 넣고 다시 PDF) ----------
def fill_toc(hwpx: Path, pdf: Path) -> int:
    """우리 목차("목차" ~ "부록" 줄)의 "N.N 제목 … 쪽" 줄 끝 숫자를 본문 꼬리말 쪽 번호로(wall_build._page_map — 간지·번호 없는 쪽은 뺌). 바꾼 줄 수."""
    from server.sitok.wall_build import Hwpx, _page_map

    pages = _page_map(pdf)
    if not pages:
        return 0
    doc = Hwpx(hwpx)
    tops = [p for p in doc.root if p.tag == f"{{{HP}}}p"]
    i0 = next((k for k, p in enumerate(tops) if _n(_t(p)) == "목차"), None)
    if i0 is None:
        return 0
    i1 = next((k for k in range(i0 + 1, len(tops)) if _n(_t(tops[k])) == "부록"), min(len(tops), i0 + 80))
    n = 0
    for p in tops[i0 + 1:i1]:
        key = re.sub(r"\d+$", "", _n(_t(p)))
        page = pages.get(key)
        if not page or not re.match(r"\d+\.\d+", key):
            continue
        pieces = [pc for x in p.iter(f"{{{HP}}}t") for pc in rb._pieces(x)]
        tail = next((pc for pc in reversed(pieces) if pc.text and re.fullmatch(r"\s*\d+\s*", pc.text)), None)
        if tail is not None and tail.text.strip() != str(page):
            tail.text = str(page)
            n += 1
    if n:
        doc.save(hwpx, drop_unused=False)
    return n
