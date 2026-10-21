"""내진성능평가 보고서 칸 채우기 3단계(2026-10-21 사용자 "1~2장 + 지반조사보고서·3~7장(외주)에서 자동으로 채워지는 부분").

seismic_build.build가 우리 1~2장 원본(견본 삼숭초 교사동)에 이름·결과표 가·사·1.1·철근배근을 채운 뒤 여기서 나머지:
- 요약: 위치도·전경 사진, (1) 현장 시험 조사개소(부재규격·콘크리트 강도·지반조사), 결함·중량물 분석 글
- 1장: 1.1 경과년수(조사 연도 기준), 1.3 내진등급·성능목표 ◎, 1.4 층별 용도현황·증축·용도변경(건축물대장)
- 2장: 2.2.1 부재 단면 표·수량·사진·조사결과 문장, 2.2.2 사진·조사결과 문장, 2.2.3 코어 사진, 2.2.4 강도결정 표·성적서 그림·조사결과 문장,
  2.3 분석 글 다섯, 2.4.1 중량물·2.4.2 마감재 사진·글, 2.4.3 조적조 사진·결과표, 2.5 지반(문장·위치도·BH별 사진 6장·결과 그림 — 지반조사보고서)
견본 값 자리(예: "15.7~17.3MPa(평균 13.82MPa)")는 견본 글을 그대로 찾아 바꿈 — 원본이 바뀌면 SAMPLE_* 도 같이.
"""
from __future__ import annotations

import copy
import io
import re
from pathlib import Path

from server.sitok import report_build as rb
from server.sitok import seismic_docs as SD
from server.sitok import seismic_field as SF
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


def _n(s: str) -> str:
    return re.sub(r"\s", "", s or "")


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
def fill_photos(doc, root, field: dict, rdir: Path, warn: list) -> int:
    photos, n, miss = field["photos"], 0, []
    path = lambda slot: (rdir / photos[slot]["rel"]) if (photos.get(slot) or {}).get("rel") else None  # noqa: E731
    for key, slots in PHOTO_TABLES:
        t = next((t for t in _outer(root) if key in _n(_t(t)) and rb._pic_slots(t)), None)
        if t is None:
            continue
        for slot, (_, pic) in zip(slots, rb._pic_slots(t)):
            if _put(doc, pic, path(slot)):
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
                if _put(doc, rb._pic_slots(t)[0][1], path(slot), crop=crop):
                    n += 1
                else:
                    miss.append(SF.PHOTO[slot][0])
    if miss:
        warn.append(f"현장 사진 없음(견본 사진 그대로): {'·'.join(miss)} — 현장조사 입력 📷")
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


def fill_chunks(root, tables: list, rows: list[list], per: int, header: int, flat: bool) -> int:
    """견본 표들(같은 모양)에 rows를 per줄씩 — 표가 모자라면 마지막 표 문단을 복사(쪽 나눔), 남는 견본 표는 지움. 넣은 줄 수.
    표는 문단 안 몇 번째 표인지로 집음(부록은 사진 머리 표와 값 표가 한 문단에 같이 있음, 10/22)."""
    if not tables:
        return 0
    slots = []
    for t in tables:
        p = _top_p(t)
        slots.append((p, _outer(p).index(t)))
    tpl_p, tpl_idx = slots[-1]
    tpl = copy.deepcopy(tpl_p)
    chunks = [rows[i:i + per] for i in range(0, len(rows), per)] or [[]]
    used = []
    for k, chunk in enumerate(chunks):
        if k < len(slots):
            p, idx = slots[k]
        else:
            p, idx = copy.deepcopy(tpl), tpl_idx
            rb._new_ids(p)
            used[-1].addnext(p)
            p.set("pageBreak", "1")
        used.append(p)
        t = _outer(p)[idx]
        (_resize_flat if flat else _resize_tail)(t, header, len(chunk))
        cells = rb._cells(t)
        for j, vals in enumerate(chunk):
            for c, v in enumerate(vals):
                if v is not None:
                    _set(cells, (header + j, c), v)
    for p, idx in slots[len(chunks):]:
        if p.getparent() is None:
            continue
        if len(_outer(p)) <= 1:
            p.getparent().remove(p)
        else:  # 다른 표(사진 머리 등)와 같은 문단이면 그 표만
            t = _outer(p)[idx]
            t.getparent().remove(t)
    return len(rows)


# ---------- 요약 (1) 현장 시험 및 분석 ----------
def fill_summary(root, field: dict, ground: dict | None) -> int:
    n = 0
    holes = (ground or {}).get("holes") or []
    for t in _outer(root):
        cells = rb._cells(t)
        if _n(rb._cell_text(cells.get((0, 1), t))) != "조사·시험항목":
            continue
        for (r, c), x in cells.items():
            label = _n(rb._cell_text(x)) if c == 1 else ""
            v = {"부재규격": len(field["members"]), "콘크리트강도": len(field["cores"]), "지반조사(공통)": len(holes)}.get(label)
            if v:
                _set(cells, (r, 3), f"{v}EA")
                n += 1
        break
    defaults = {k: d for k, _l, d in SF.TEXTS}
    for t in _outer(root):  # 결함·중량물 분석(요약 표) — 사람이 고친 글만
        cells = rb._cells(t)
        first = _n(rb._cell_text(cells.get((1, 0), t)))
        if first == "중량물" and field["texts"]["heavy"] != defaults["heavy"]:
            _set(cells, (1, 1), field["texts"]["heavy"])
            n += 1
    return n


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
                fl = f"지하{fl[1:]}층" if re.fullmatch(r"지\d+", fl) else fl
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


def fill_members(root, field: dict, d: dict, rebar_rows: list, units: int, warn: list) -> int:
    from server.sitok import rebar_survey as RV

    members = field["members"]
    tables = [t for t in _outer(root) if t.get("colCnt") == "6" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "NO"
              and _n(rb._cell_text(rb._cells(t).get((0, 1), t))) == "조사위치"]
    n = 0
    if members:
        rows = [[str(i + 1), f"{SF.floor_label(m['floor'])}( {m['where']} )" if m["where"] else SF.floor_label(m["floor"]),
                 f"{m['kind']} ({m['mark']})" if m["mark"] else m["kind"], m["design"] or "-", m["measured"] or "-", m["note"]] for i, m in enumerate(members)]
        n += fill_chunks(root, tables, rows, 18, 1, flat=False)
    else:
        warn.append("부재 단면 줄이 없어 2.2.1 표는 견본 값 그대로입니다(현장조사 입력)")
    qty = [x for x in _outer(root) if (x.get("rowCnt"), x.get("colCnt")) == ("2", "4") and "금회조사수량" in _n(rb._cell_text(rb._cells(x).get((0, 3), x)))]
    label = f"{d['name']} ({units}개층)"
    for k, t in enumerate(qty[:2]):
        cells = rb._cells(t)
        _set(cells, (1, 0), label)
        if k == 0 and members:
            _set(cells, (1, 3), f"금회 조사 수량 = {len(members)}개소")
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
                continue
            ts = list(p.iter(f"{{{HP}}}t"))
            if ts:
                ts[0].text = _diff_sentence(labels)
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
        warn.append("코어 압축강도가 없어 2.2.4 강도결정 표는 견본 값 그대로입니다(현장조사 입력 — 성적서에서 읽기)")
    else:
        m, s = st["mean"], st["std"]
        m_v = [c["mpa"] for c in cores if c.get("mpa") is not None]
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
                    p.getparent().remove(p)
        else:
            warn.append("압축강도 시험성적서가 없어 2.2.4 성적서 그림은 견본 그대로입니다(서류 칸)")
    return n


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
def fill_texts(root, field: dict) -> int:
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
                k += 1
                n += 1
    for tb in _outer(root):
        whole = _n(_t(tb))
        cells = rb._cells(tb)
        if "건물외중량물" in whole and (3, 0) in cells:
            _set(cells, (3, 0), f"· {tx['heavy']}")
            n += 1
        elif "건물외부마감재" in whole and (2, 0) in cells:
            _set(cells, (2, 0), tx["finish"])
            n += 1
    return n


# ---------- 2.4.3 조적조 ----------
def fill_masonry(root, field: dict, warn: list) -> int:
    rows = field["masonry"]
    tables = [t for t in _outer(root) if t.get("colCnt") == "11" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "층"]
    if not rows:
        warn.append("조적조 줄이 없어 2.4.3 조적벽 결과표는 견본 값 그대로입니다(현장조사 입력)")
        return 0
    rows = sorted(rows, key=lambda x: (x["floor"], x["kind"] != "채움벽", x["mid"]))
    vals = [[SF.floor_label(x["floor"]).replace("지상", "지상 ").replace("지하", "지하 "), x["kind"], x["mid"], _fmt(x["height"], 0) if x["height"] else "-",
             _fmt(x["width"], 0) if x["width"] else "-", x["thick"], x["dir"], x["expose"].replace(" ", "\n", 1), f"{x['finish']}" if x["finish"] is not None else "-",
             x["boundary"], x["applied"]] for x in rows]
    return fill_chunks(root, tables, vals, 20, 2, flat=True)


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
        warn.append("지반조사보고서가 없어 2.5 지반 및 기초는 견본 값 그대로입니다(서류 칸)")
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
            else:
                warn.append(f"{h['bh']} {label} 사진 없음(견본 사진 그대로) — 지반조사 확인")

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


def fill_all(doc, root, r, f, rdir: Path, d: dict, warn: list) -> int:
    """seismic_build.build에서 — 현장조사 입력·서류(지반·성적서)·건축물대장 값으로 나머지 칸."""
    sv = r.survey or {}
    field = SF.normalize(sv.get("seismic_field"))
    docs = sv.get("seismic_docs") or {}
    ground = (docs.get("ground") or {}).get("parsed")
    reg = (f.ledger or {}).get("register") or {}
    units = (f.floors_below or 0) + (f.floors_above or 0)
    n = fill_photos(doc, root, field, rdir, warn)
    n += fill_summary(root, field, ground)
    n += fill_grade(root, reg.get("grade") or ("특등급" if re.search(r"교육|학교", f.main_use or "") else "1등급"), warn)
    if reg:
        n += fill_history(doc, root, f, reg)
    n += fill_members(root, field, d, d.get("rebar") or [], units, warn)
    n += fill_cores(doc, root, field, rdir, docs.get("core"), warn)
    n += fill_texts(root, field)
    n += fill_masonry(root, field, warn)
    n += fill_ground(doc, root, ground, rdir, warn)
    return n
