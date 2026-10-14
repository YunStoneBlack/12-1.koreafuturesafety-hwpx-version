"""시특법 정밀안전점검 본문 한글 만들기(2026-10-13 밤, ⑤ 단계) — 정밀 본문 원본(다산은혜교회 26년 상반기, master "정밀본문")에 이 회차 값을 넣는다.

두 번에 나눠 만든다(사용자 "정기처럼 원본 구조 유지").
1) rb.build — 정기와 같은 것: 이름·용역명·기간·관리주체·준공일 바꾸기(결과표 값 기준), 등록증·수료증 그림, 장비 표, 직위, 전경사진, 개략공사비 표.
2) 이 모듈 — 정밀만 있는 것: 결과표 점검 주요결과·등급, 요약표(책임기술자 종합의견·부재별 등급·시험 요약), 내진, 2장(자료수집·보수이력·점검이력·용도현황·관리실태·전차 검토),
   3장(결함 사진 표·본문 글·하중 사진·공중이용·기타시설·분석 표), 4장(수량·규격·강도·탄산화·기울기·부등침하 표와 결과 분석 글), 5장(글·상태평가 결과 그림·등급·전차 비교),
   6장 보수물량·우선순위, 7장(분석 표·요약 글·결과 그림·결론·사용제한 표). 글은 precision_text(기본 문장 → AI 초안이 덮어씀).
표는 자리를 머리줄 글자나 바로 앞 캡션(【표 4.4】)으로 찾는다 — 형이 원본을 고쳐도 제목·머리줄만 두면 됨. 못 찾은 것은 notes에 남김.
"""
from __future__ import annotations

import copy
import datetime
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from server.sitok import condition, master, precision_text, report_build as rb, tests as TESTS

HP, CORE, T = rb.HP, rb.CORE, rb.T
HEAD_RE = re.compile(r"^(【|제\s*\d+\s*장|\d+\.\d+(\.\d+)?[\s)]|[가-힣]\.\s|\d\)\s*[가-힣]|■|▣)")


@dataclass
class Data:
    new: rb.Values
    facility: object
    tv: dict  # tests.compute 보기
    rv: dict  # 상태평가 보기(sitok_rating._compute)
    pr: dict  # 정밀 입력 보기(sitok_precision._out)
    defects: list
    texts: dict
    parts: dict  # {"public": [(이름, 경로|None)]×4, "other": [(설명, 경로|None)]×4}
    load_photos: list  # [(경로, 제목)]
    priority: list  # [(층, 구분, 부재, 손상내용, 공법, 물량, 단위, 우선순위)]
    repairs: list  # 면담 보수이력 [{period, kind, method, where, note}]
    rating_png: bytes | None
    replace: dict  # 전체 글 바꾸기 {옛: 새}
    kind_label: str = "2종"
    notes: list = field(default_factory=list)
    result_fields: dict = field(default_factory=dict)  # 결과표 이름 칸 → 값(관리주체명·대표자)
    detail: dict | None = None  # 시설물 현황(survey.detail) — 현황표에 넣은 칸은 안 비움
    cost: tuple | None = None  # 개략공사비(정기 cost_rows) — 앞부분 요약문 표는 rb.build가 안 채우므로 여기서
    map_path: str = ""  # 위치도 지도(locmap) — 없으면 흰 그림
    overview: list = field(default_factory=list)  # 전경사진 [(경로, 제목)] — 위치도 표 아래 칸·요약문 사진
    blank: str = ""
    survey_pics: dict = field(default_factory=dict)  # 조사 전경 사진 {키: [경로|""…]}(precision.SURVEY_PICS, 형 10/14) — 【사진 2.1】·【사진 4.1~4.5】
    prior_fields: dict = field(default_factory=dict)  # 이전 회차 보고서 현황표의 칸 값 {이름: 값} — 빈 칸은 여기서(형 10/14 "그럼 가져와?" → 추천대로)


# ---------- 작은 도구 ----------

def _tops(root) -> list:
    return [p for p in root if p.tag == f"{{{HP}}}p"]


def _has_tbl(p) -> bool:
    return next(p.iter(f"{{{HP}}}tbl"), None) is not None


def _table_after(root, key: str, nth: int = 0):
    """캡션(【표 4.4】 등)이 든 문단 뒤 첫 표(그 문단 안 표 포함). nth = 같은 캡션 뒤 n번째 표."""
    tops = _tops(root)
    for i, p in enumerate(tops):
        if key.replace(" ", "") in rb._top_text(p).replace(" ", ""):
            found = 0
            for q in tops[i:]:
                for tbl in q.iter(f"{{{HP}}}tbl"):
                    if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is None:
                        if found == nth:
                            return tbl
                        found += 1
                if q is not p and HEAD_RE.match(rb._top_text(q)) and found == 0 and "【" in rb._top_text(q) and key.replace(" ", "") not in rb._top_text(q).replace(" ", ""):
                    return None
    return None


def _set(cells: dict, r: int, c: int, text) -> bool:
    if (r, c) not in cells:
        return False
    lines = text if isinstance(text, list) else [str(text)]
    rb._set_lines(cells[(r, c)], [str(x) for x in lines] or [""])
    return True


def _row_cells(cells: dict, r: int) -> list:
    return [cells[k] for k in sorted(k for k in cells if k[0] == r)]


def _fit_rows(tbl, data_rows: int, head: int, tail: int = 0) -> int:
    """데이터 줄 수를 맞춤(head 머리줄, tail 꼬리줄은 남김) — 모자라면 꼬리 앞이 아니라 끝에 복사해 붙임(꼬리가 있으면 안 늘림). 쓸 수 있는 데이터 줄 수."""
    n = int(tbl.get("rowCnt"))
    avail = n - head - tail
    if data_rows < avail and tail == 0:
        rb._trim_rows(tbl, head + max(data_rows, 1))
        return max(data_rows, 1)
    if data_rows > avail and tail == 0:
        for _ in range(data_rows - avail):
            rb._add_row(tbl)
        return data_rows
    return avail


def _para_text(p) -> str:
    return rb._top_text(p).strip()


def _set_after(root, heading: str, texts: list[str], regex: bool = False, nth: int = 0) -> int:
    """제목 문단(heading과 같거나 정규식) 뒤 본문 문단들(다음 제목·캡션·표 전까지)을 texts로 — 첫 문단부터 차례로, 남는 문단은 비움, 모자라면 마지막에 이어 붙임."""
    tops = _tops(root)
    hits = [i for i, p in enumerate(tops) if (re.match(heading, _para_text(p)) if regex else _para_text(p).replace(" ", "") == heading.replace(" ", ""))]
    if len(hits) <= nth:
        return 0
    i = hits[nth]
    body = []
    for q in tops[i + 1:]:
        t = _para_text(q)
        if _has_tbl(q) or (t and HEAD_RE.match(t)):
            break
        body.append(q)
    body = [q for q in body if _para_text(q)] or body[:1]
    if not body:
        return 0
    texts = [t for t in texts if t] or [""]
    for k, q in enumerate(body):
        if k < len(body) - 1:
            rb._set_para(q, texts[k] if k < len(texts) else "")
        else:
            rb._set_para(q, " ".join(texts[k:]) if k < len(texts) else "")
    return 1


def _slots(tbl) -> list:
    """사진 표의 [(사진 칸, 설명 칸)] — 머리줄이 있든(1줄부터) 없든(0줄부터) 사진 줄(높음)·설명 줄(낮음)이 번갈아."""
    cells = rb._cells(tbl)
    rows = sorted({r for r, _ in cells})
    height = {r: max(int(tc.find(f"{{{HP}}}cellSz").get("height") or 0) for (rr, _), tc in cells.items() if rr == r) for r in rows}
    for start in (0, 1):
        use = rows[start:]
        if len(use) < 2 or any(height[use[i]] <= height[use[i + 1]] for i in range(0, len(use) - 1, 2)):
            continue
        out = []
        for i in range(0, len(use) - 1, 2):
            pr, cr = use[i], use[i + 1]
            for c in sorted(c for r, c in cells if r == pr):
                out.append(((pr, c), (cr, c) if (cr, c) in cells else None))
        return out
    return []


def _set_row_height(tbl, r: int, h: int) -> None:
    """r줄 높이를 h로(표 높이도 같이) — 긴 글이 있던 줄을 "-"로 비우면 줄이 그대로 커서 쪽을 다 차지함."""
    cells = rb._cells(tbl)
    delta = 0
    for (rr, _), tc in cells.items():
        if rr == r and rb._span(tc, "rowSpan") == 1:
            sz = tc.find(f"{{{HP}}}cellSz")
            cur = int(sz.get("height") or 0)
            if cur != h:
                sz.set("height", str(h))
                delta = h - cur
    tsz = tbl.find(f"{{{HP}}}sz")
    if tsz is not None and tsz.get("height") and delta:
        tsz.set("height", str(max(int(tsz.get("height")) + delta, 0)))


def _pic_or(tc, tpl):
    pic = next(tc.iter(f"{{{HP}}}pic"), None)
    return pic if pic is not None else tpl


def _photos_into(tbl, photos: list, tpl, add_image, none_text: str = "해당없음") -> bool:
    """사진 표(사진 줄·설명 줄 번갈아) — photos [(경로, 설명)] 차례로, 남는 칸 비움(설명 "-"), 하나도 없으면 첫 칸 none_text."""
    slots = _slots(tbl)
    if not slots:
        return False
    cells = rb._cells(tbl)
    photos = [(p, cap) for p, cap in photos if p and Path(p).exists()]
    for i, (pk, ck) in enumerate(slots):
        path, caption = photos[i] if i < len(photos) else (None, "-")
        image = None
        if path:
            pic = _pic_or(cells[pk], tpl)
            sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
            w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
            image = rb._cropped(path, w, h)
        rb._slot_put(cells[pk], cells[ck] if ck else None, image, none_text if not photos and i == 0 else "", caption, tpl, add_image)
    return True


def _fit_png(png: bytes, w: int, h: int) -> bytes:
    """그림 칸 비율(w:h)에 맞게 흰 여백을 둘러 JPG로(표 그림은 자르면 안 됨)."""
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGB")
    iw, ih = img.size
    if iw * h > ih * w:
        nh = int(iw * h / w)
        canvas = Image.new("RGB", (iw, nh), "white")
        canvas.paste(img, (0, (nh - ih) // 2))
    else:
        nw = int(ih * w / h)
        canvas = Image.new("RGB", (nw, ih), "white")
        canvas.paste(img, ((nw - iw) // 2, 0))
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _rating_crop(png: bytes, frac: float = 0.46) -> tuple[bytes, float]:
    """상태평가 갑지 PNG 윗부분(건물개요·평가결과·최종결과)만 — (JPG 바이트, 가로/세로 비율). 다산 요약문 2.4는 갑지를 가로로 자른 그림."""
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, max(int(h * frac), 1)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue(), w / max(int(h * frac), 1)


def _px_for_frame(jpg: bytes, w: int, h: int) -> bytes:
    """우리 한글(2020)은 표 칸 그림을 96dpi 원래 크기로 그리고 틀로 잘라 보인다(10/14 실험: 1406px 갑지가 6.5인치 틀에서 2.2배 확대, dpi 메타는 무시) →
    그림 픽셀을 틀 크기(HWPUNIT/7200인치 × 96)에 맞춤."""
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(jpg)).convert("RGB")
    pw, ph = max(int(w / 7200 * 96), 1), max(int(h / 7200 * 96), 1)
    im = im.resize((pw, ph))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _reset_pic(pic, w: int, h: int) -> None:
    """그림 틀을 새 그림 크기(w×h HWPUNIT)에 맞춤 — 원본 크기·현재 크기·자르기·배율을 새로(옛 사진의 자르기 속성이 남으면 확대돼 보임, 10/14)."""
    for tag in ("orgSz", "curSz", "sz"):
        el = pic.find(f"{{{HP}}}{tag}")
        if el is not None:
            el.set("width", str(w))
            el.set("height", str(h))
    rect = pic.find(f"{{{HP}}}imgRect")
    if rect is not None:
        for name, (x, y) in zip(("pt0", "pt1", "pt2", "pt3"), ((0, 0), (w, 0), (w, h), (0, h))):
            pt = rect.find(f"{{{CORE}}}{name}")
            if pt is not None:
                pt.set("x", str(x))
                pt.set("y", str(y))
    clip = pic.find(f"{{{HP}}}imgClip")
    if clip is not None:
        clip.attrib.update({"left": "0", "top": "0", "right": str(w), "bottom": str(h)})
    for m in pic.iter(f"{{{CORE}}}scaMatrix"):
        m.set("e1", "1")
        m.set("e5", "1")
    rot = pic.find(f"{{{HP}}}rotationInfo")
    if rot is not None:
        rot.set("centerX", str(w // 2))
        rot.set("centerY", str(h // 2))


def _put_png(p, png: bytes | None, add_image) -> int:
    """문단 안 그림(표 밖)을 png로."""
    if not png:
        return 0
    n = 0
    for pic in p.iter(f"{{{HP}}}pic"):
        if next(pic.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        img = next(pic.iter(f"{{{CORE}}}img"), None)
        sz = pic.find(f"{{{HP}}}curSz")
        if img is None:
            continue
        w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
        img.set("binaryItemIDRef", add_image(_fit_png(png, w, h)))
        n += 1
    return n


# ---------- 앞부분(결과표·요약표·내진·전차 비교·사용제한) ----------

RESULT_EST_FIT = 84000  # 결과표 어림 높이(rb._est_height — 결과표는 글자가 작아 실제보다 크게 나옴) — 다산 견본(한 쪽에 꼭 참)이 86718. 이보다 크면 '다.'부터 다음 쪽으로


def _split_result_table(root, tbl) -> bool:
    """결과표가 한 쪽에 안 들어갈 것 같으면(어림) 미리 '다.'부터 새 쪽으로(rb.split_result_table) — PDF를 뽑은 뒤 실제로 넘친 것은 pagecheck.split_result_tables가 잡음."""
    if rb._est_height(tbl) <= RESULT_EST_FIT:
        return False
    return rb.split_result_table(root, tbl)


def _result_tables(root) -> list:
    """정밀 결과표(첫 칸 "가. 일반현황") — 여러 동이면 동마다."""
    out = []
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        if rb._cell_text(rb._cells(tbl).get((0, 0), tbl)).replace(" ", "").startswith("가.일반현황"):
            out.append(tbl)
    return out


def _fill_result_table(root, D: Data) -> int:
    cells = rb._find_result_table([root])
    if cells is None:
        D.notes.append("결과표를 찾지 못해 점검 주요결과를 못 넣었습니다")
        return 0
    n = 0

    def right(label: str):
        for (r, c), tc in cells.items():
            if re.sub(r"\s", "", rb._cell_text(tc)).startswith(label):
                nxt = [k for k in cells if k[0] == r and k[1] > c]
                return (r, min(nxt)[1]) if nxt else None
        return None

    t = D.texts
    k = right("중대한결함")
    if k:
        _set(cells, *k, "ㆍ중대결함 없음"); n += 1  # noqa: E702
    k = right("공중이이용하는부위")
    if k:
        _set(cells, *k, "ㆍ중대결함 없음" if not any(g in ("d", "e") for g in (D.pr["grades"] and [x["grade"] for x in D.pr["grades"]["public"]] or [])) else "ㆍ보수가 필요한 손상 있음"); n += 1  # noqa: E702
    k = right("점검주요결과")
    if k:
        r0, c = k
        rows = []
        r = r0
        while (r, c) in cells and not re.sub(r"\s", "", rb._cell_text(cells.get((r, 0), cells[(r, c)]))).startswith("주요보수"):
            rows.append(r)
            r += 1
            if (r, 0) in cells and re.sub(r"\s", "", rb._cell_text(cells[(r, 0)])).startswith(("주요보수", "다.")):
                break
        f = [x if x.startswith(("ㆍ", "-", "·")) else f"ㆍ{x}" for x in precision_text.findings(t)]
        for i, rr in enumerate(rows):
            part = f[i:i + 1] if i < len(rows) - 1 else f[i:]
            _set(cells, rr, c, part or [""])
        n += 1
    k = right("주요보수")
    if k:
        lines = [f"ㆍ{p[1]} {p[2]} {p[3].lstrip('·ㆍ')} : {p[4]}" for p in D.priority if p[4] not in ("-", "주의관찰")][:3] or ["ㆍ보수·보강 대상 없음(주의관찰)"]
        _set(cells, *k, lines); n += 1  # noqa: E702
    k = right("안전등급")
    if k and t.get("grade_letter"):
        _set(cells, *k, t["grade_letter"]); n += 1  # noqa: E702
    n += rb.engineer_rows(root, D.new.persons)  # 다. 책임(참여)기술자 줄 — 이름·등급을 줄 위치로, 남는 줄 지움(10/14 숭의: 틀의 "특급기술자" 두 명이 글자 바꾸기에서 충돌)
    for tc in cells.values():
        for q in tc.iter(f"{{{HP}}}p"):
            txt = "".join(rb._full(x) for x in q.iter(T))
            if "중점 점검부위" in txt and ":" in txt:
                rb._set_para(q, txt.split(":")[0].rstrip() + " : 결함 발생 부위 및 보수 구간", in_table=True)
                n += 1
    return n


def _fill_summary_table(root, D: Data) -> int:
    """9쪽 "정밀안전점검 실시결과 요약표"(책임기술자 종합의견·부재별 상태평가·변위·시험)."""
    tbl = None
    for x in root.iter(f"{{{HP}}}tbl"):
        if rb._cell_text(rb._cells(x).get((0, 0), x)).replace(" ", "").startswith("책임기술자종합의견"):
            tbl = x
            break
    if tbl is None:
        return 0
    cells = rb._cells(tbl)
    t = D.texts
    n = 0
    _set(cells, 1, 0, t.get("summary", "")); n += 1  # noqa: E702
    for (r, c), tc in cells.items():
        txt = rb._cell_text(tc).replace(" ", "")
        if txt.startswith("종합평가결과"):
            _set(cells, r, c, f"종합평가 결과 : {t.get('grade_letter') or '-'}")
        if txt.startswith("변위") and "평가결과" in txt and (r, 9) in cells:
            _set(cells, r, 9, (D.rv["result"]["deform"]["grade"] if D.rv["result"] and D.rv["result"].get("deform") else "-"))
        if txt == "조사결과" and (r, 9) in cells:
            _set(cells, r, 9, (D.rv["result"]["deform"]["grade"] if D.rv["result"] and D.rv["result"].get("deform") else "-"))
    # 부재별 상태평가 — 표의 층 묶음(첫 칸에 "층"이 있고 rowSpan 4) 차례로 위층부터
    floors = sorted(D.rv["floors"], key=lambda f: -f["floor"])
    blocks = sorted([(r, tc) for (r, c), tc in cells.items() if c == 0 and rb._span(tc, "rowSpan") >= 3 and "층" in rb._cell_text(tc)], key=lambda x: x[0])
    if len(floors) > len(blocks) and blocks:  # 틀은 층 묶음 2개 — 마지막 묶음(부재 4줄)을 복사해 뒤에(부재 이름 열은 남기고 층·등급·결함·보수 칸만 비움, 10/14 숭의 3개층)
        r0, tc0 = blocks[-1]
        span = rb._span(tc0, "rowSpan")
        rb._dup_rows(tbl, r0, span, len(floors) - len(blocks), clear_cols={0, 3, 6, 7})
        cells = rb._cells(tbl)
        blocks = sorted([(r, tc) for (r, c), tc in cells.items() if c == 0 and rb._span(tc, "rowSpan") >= 3 and (r == r0 or r > r0 or "층" in rb._cell_text(tc))], key=lambda x: x[0])
        blocks = [b for b in blocks if "층" in rb._cell_text(b[1]) or b[0] >= r0]
    MEMBER_ROW = {"기둥": "기둥", "벽체": "내력벽", "보": "큰보", "슬래브": "슬래브"}
    for bi, (r0, tc) in enumerate(blocks):
        fl = floors[bi] if bi < len(floors) else None
        span = rb._span(tc, "rowSpan")
        if fl is None:
            _set(cells, r0, 0, ["-"])
            for r in range(r0, r0 + span):
                _set(cells, r, 3, "-"); _set(cells, r, 6, "-"); _set(cells, r, 7, "-")  # noqa: E702
            continue
        _set(cells, r0, 0, [fl["label"], f"({fl['range_label']})"])
        mem = {m["kind"]: m for m in fl["members"]}
        for r in range(r0, r0 + span):
            name = rb._cell_text(cells[(r, 1)]).replace(" ", "") if (r, 1) in cells else ""
            kind = MEMBER_ROW.get(name)
            m = mem.get(kind) if kind else None
            if not m or m.get("skip"):
                _set(cells, r, 3, "-"); _set(cells, r, 6, "-"); _set(cells, r, 7, "-")  # noqa: E702
                continue
            types = []
            for it in ("CR",):
                for d in (m["items"].get(it) or {}).get("defects", []):
                    if d["dtype"] not in types:
                        types.append(d["dtype"])
            for sub in (m["items"].get("SD") or {}).get("sub", {}).values():
                for d in sub.get("defects", []):
                    if d["dtype"] not in types:
                        types.append(d["dtype"])
            _set(cells, r, 3, condition.rating.grade_of(m["score"]) if m.get("score") is not None else "-")
            _set(cells, r, 6, "·".join(types[:3]) if types else "양호")
            _set(cells, r, 7, "표면처리, 주의관찰 등" if types else "주의관찰")
        n += 1
    if len(floors) > len(blocks):
        D.notes.append(f"요약표 부재별 상태평가 칸이 {len(blocks)}개 층뿐이라 표본층 {len(floors)}개 중 앞 {len(blocks)}개만 넣었습니다")
    n += _fill_test_rows(cells, D)
    return n


def _brief(text: str, n: int = 70) -> str:
    """책임기술자 의견 칸 — 첫 문장(마침표)까지, 너무 길면 n자 뒤 가장 가까운 쉼표·띄어쓰기에서 끊고 "…"(사용자 10/14 "50자에서 문장 중간에 잘림")."""
    t = " ".join((text or "").split())
    if not t:
        return ""
    m = re.search(r"[.。]\s", t + " ")
    first = t[:m.end()].strip() if m else t
    if len(first) <= n + 25:
        return first
    cut = first[:n]
    k = max(cut.rfind(","), cut.rfind(" "), cut.rfind("·"))
    return (cut[:k] if k > n // 2 else cut).rstrip(",· ") + "…"


def _fill_test_rows(cells: dict, D: Data) -> int:
    """시험 요약 줄(시험명 | 개소 | 조사결과 | 책임기술자 의견) — 요약표·결과표 뒤 표 공통(줄 첫 칸 글자로)."""
    tv, t = D.tv, D.texts
    sm, cs, ti, se = tv["strength"]["summary"], tv["carbonation"]["summary"], tv["tilt"], tv["settlement"]
    rows = {
        "규격조사": (f"{len(tv['sections'])}개소" if tv["sections"] else "-", "재료시험 결과 참조", t.get("section", "")[:60]),
        "강도조사": (f"{sm['count']}개소" if sm["count"] else "-", ["추정압축강도:", f"{sm['min']}~{sm['max']}MPa"] if sm["count"] else "-",
                  f"{(tv['strength']['grade'] or '-').upper()}등급 — " + _brief(t.get("strength", ""))),
        "탄산화조사": (f"{cs['count']}개소" if cs["count"] else "-", ["탄산화깊이:", f"{cs['min']}mm~{cs['max']}mm"] if cs["count"] else "-",
                   f"{(tv['carbonation']['grade'] or '-').upper()}등급, 잔존수명 " + ("평균 100년 이상" if all(r.get('life_text') == '100년 이상' for r in tv['carbonation']['rows']) else "일부 100년 미만")),
        "기울기조사": ("4면" if ti["rows"] else "-", f"1/{ti['range']['min_n']:,}~1/{ti['range']['max_n']:,}" if ti["range"]["min_n"] else "-",
                   f"건물 기울기 상태는 특이한 변위가 없는 {(ti['grade'] or '-').upper()}등급" if ti["rows"] else "-"),
        "부등침하": (str(len(se["sections"])) if se["sections"] else "-", f"{se['range']['min_disp']:g}㎜~{se['range']['max_disp']:g}㎜" if se["range"]["max_disp"] is not None else "-",
                 (se["note"] or "바닥마감 시공오차 및 구배 등으로 인한 차이") + f" — {(se['grade'] or '-').upper()}등급" if se["sections"] else "-"),
    }
    n = 0
    for r in sorted({k[0] for k in cells}):
        row = _row_cells(cells, r)
        if len(row) < 4:
            continue
        label = rb._cell_text(row[0]).replace(" ", "").replace("\n", "")
        for key, (cnt, res, opinion) in rows.items():
            if key in label:
                rb._set_lines(row[1], [cnt])
                rb._set_lines(row[2], res if isinstance(res, list) else [res])
                rb._set_lines(row[3], [opinion])
                n += 1
                break
    return n


def _fill_seismic(root, D: Data) -> int:
    tbl = rb._find_table(root, ["검토대상부재", "설계적용여부"])
    if tbl is None:
        return 0
    cells = rb._cells(tbl)
    s = D.pr["seismic"]
    _set(cells, 1, 1, s["status"] or "-")
    _set(cells, 1, 2, s["note"] or (f"시설물관리대장 등 확인 결과 내진설계 {s['status']} 확인" if s["status"] else "-"))
    return 1


def _fill_compare(root, D: Data) -> int:
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if (0, 2) not in cells or "정밀안전점검" not in rb._cell_text(cells[(0, 2)]) or not rb._cell_text(cells.get((1, 0), tbl)).replace(" ", "").startswith("안전"):
            continue
        t = D.texts
        prev = D.rv["prev_grade"] or D.rv["prev_auto"]
        _set(cells, 0, 1, f"{D.rv['prev_report']['year']}년 {D.rv['prev_report']['half']}" if D.rv.get("prev_report") else ("전차 정밀안전점검" if prev else "-"))  # 등급만 직접 넣은 전차(10/14)
        _set(cells, 0, 2, f"{D.new.year}년 정밀안전점검")
        _set(cells, 1, 1, f"·{prev}등급" if prev else "-")
        _set(cells, 1, 2, f"·{t['grade_letter']}등급({t['grade_score']:.2f})" if t.get("grade_letter") else "-")
        _set(cells, 2, 1, t.get("prev_compare", ""))
        n += 1
    return n


def _fill_limit(root, D: Data) -> int:
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if rb._cell_text(cells.get((0, 0), tbl)).replace(" ", "") != "사용제한필요성":
            continue
        t = D.texts
        for r, key in ((1, "limit"), (3, "special"), (5, "suggest"), (7, "diag")):
            _set(cells, r, 0, t.get(key, "-"))
        n += 1
    return n


def prior_status_fields(hwpx: Path | None) -> dict:
    """이전 회차 보고서(hwpx) 앞부분 현황표("시설물명(FMS등록기준)" 표)의 이름 칸 → 오른쪽 값 {이름(띄어쓰기 뺀 것): 값}. 못 읽으면 {}."""
    if not hwpx or not Path(hwpx).exists():
        return {}
    try:
        with zipfile.ZipFile(hwpx) as z:
            root = etree.fromstring(z.read(rb._sections(z)[0]))
    except Exception:  # noqa: BLE001
        return {}
    out: dict = {}
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if not any(rb._cell_text(tc).replace(" ", "").startswith("시설물명") for (r_, c_), tc in cells.items() if r_ == 0):
            continue
        for (r_, c_), tc in sorted(cells.items()):
            label = re.sub(r"\s", "", rb._cell_text(tc))
            label = label.split("(")[0] if label.startswith("시설물") else label
            nxt = [k for k in cells if k[0] == r_ and k[1] > c_]
            if label not in STATUS_LABELS or not nxt or label in out:
                continue
            val = " ".join(rb._cell_text(cells[min(nxt)]).split())
            if val and val.replace(" ", "") not in STATUS_LABELS:  # 이름 칸 → 오른쪽 값(다음 이름 칸이면 빈 값)
                out[label] = val
        break
    return out


STATUS_LABELS = {"시설물명", "시설물번호", "시설물위치", "준공일자", "용도", "시설물규모", "구조형식", "종별", "전차안전등급", "점검결과안전등급", "건축연면적", "건축면적", "층수",
                 "최고높이", "주용도", "사용승인일", "준공후경과년수", "대지면적", "기본모듈", "최고층고", "기초형식", "콘크리트설계강도", "철근종류", "철골종류", "설계자",
                 "시공자", "감리자", "공사기간", "부대시설", "규모및제원추가사항"}  # 현황표 이름 칸(띄어쓰기 뺀 것)


def _fill_status_tables(root, D: Data) -> int:
    """현황표(시설물명(FMS등록기준) …) — 시설물 칸 값, 시설물 현황(detail)에 없는 다산 고유 칸은 "-". 앞부분 두 번·시설물편 1.1."""
    from server.sitok import detail as DT

    f = D.facility
    t = D.texts
    prev = D.rv["prev_grade"] or D.rv["prev_auto"]
    WORD = {"A": "우수", "B": "양호", "C": "보통", "D": "미흡", "E": "불량"}
    age = TESTS.age_years(f.completion_date, D.new.period_start)
    values = {
        "시설물명": f.name, "시설물번호": f.fms_no or "-", "시설물위치": f.address or "-", "준공일자": f"{f.completion_date.year}년 {f.completion_date.month:02d}월 {f.completion_date.day:02d}일" if f.completion_date else "-",
        "용도": f.use_type or f.main_use or "-", "시설물규모": D.new.scale, "구조형식": f.structure or "-", "종별": f"{(f.template or '2종')[:2]}시설물",
        "전차안전등급": (WORD.get(prev, prev) if prev else "-"), "점검결과안전등급": f"{t['grade_letter']}등급" if t.get("grade_letter") else "-",
        "건축연면적": f"{f.total_area:,.2f}㎡" if f.total_area else "-", "건축면적": f"{f.building_area:,.2f}㎡" if f.building_area else "-",
        "층수": f"지하{f.floors_below or 0}층/지상{f.floors_above or 0}층", "최고높이": f"{f.max_height:g}m" if f.max_height else "-", "주용도": f.main_use or f.use_type or "-",
        "사용승인일": f.completion_date.strftime("%Y.%m.%d") if f.completion_date else "-", "준공후경과년수": f"약 {age}년 경과" if age is not None else "-",
    }
    blank = ("대지면적", "기본모듈", "최고층고", "기초형식", "콘크리트설계강도", "철근종류", "철골종류", "설계자", "시공자", "감리자", "공사기간", "부대시설")
    have = set(((D.detail or {}).get("fields") or {}).keys())
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if not any(rb._cell_text(tc).replace(" ", "").startswith("시설물명") for (r_, c_), tc in cells.items() if r_ == 0):
            continue
        for (r_, c_), tc in list(cells.items()):
            label = rb._cell_text(tc).replace(" ", "").replace("\n", "")
            label = label.split("(")[0] if label.startswith("시설물") else label
            nxt = [k for k in cells if k[0] == r_ and k[1] > c_]
            if not nxt:
                continue
            target = cells[min(nxt)]
            prior_v = (D.prior_fields or {}).get(label, "")
            if label in values:
                v = values[label]
                if v == "-" and prior_v and prior_v != "-":  # 시설물 카드에 없는 값(최고높이·건축면적 등)은 이전 회차 보고서 현황표에서
                    v = prior_v
                rb._set_lines(target, [v])
                n += 1
            elif label in blank and DT._key(label) not in have:  # 시설물 현황 창에서 안 고친 칸 — 이전 회차 보고서 값, 없으면 "-"
                rb._set_lines(target, [prior_v if prior_v else "-"])
                n += 1
    return n


def general_row(f, no: str = "") -> list[str]:
    """대상시설물 현황 표 한 줄 — [no.] 종별·시설명·위치·연면적·층수(지상/지하)·구조·준공년도."""
    vals = [(f.template or "2종")[:2], f.name or "-", f.address or "-", f"{f.total_area:,.2f}" if f.total_area else "-",
            f"지상{f.floors_above or 0}층/지하{f.floors_below or 0}층", f.structure or "-", f"{f.completion_date.year}년" if f.completion_date else "-"]
    return ([no] if no else []) + vals


def general_tables(root) -> list:
    """종별·시설명·위치·연면적·층수·구조·준공년도 머리줄 표(앞에 no.가 있든 없든) — 5쪽 시설물 현황·요약문 1.2·공통편 표 1.1."""
    out = []
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        h = _head(tbl, 8)
        if "종별" in h and "시설명" in h and any(x.startswith("연면적") for x in h) and any(x.startswith("준공") for x in h):
            out.append(tbl)
    return out


def _fill_general_tables(root, D: Data) -> int:
    n = 0
    for tbl in general_tables(root):
        cells = rb._cells(tbl)
        has_no = _head(tbl, 1)[0].lower().startswith("no")
        for tc, v in zip(_row_cells(cells, 1), general_row(D.facility, "1" if has_no else "")):
            rb._set_lines(tc, [v])
        n += 1
    return n


def _fill_front_pics(root, D: Data, add_image) -> int:
    """앞부분 그림 — "■ 대상시설물 위치도" 표(위 칸 지도, 아래 칸 첫 전경사진), 요약문의 글 없는 1×1 그림 표(전경사진 차례로). 없으면 흰 그림(원본 다산 사진이 남지 않게)."""
    n = 0
    photos = [p_ for p_, _ in D.overview if p_ and Path(p_).exists()]
    blank = D.blank
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        cells = rb._cells(tbl)
        head = rb._cell_text(cells.get((0, 0), tbl)).replace(" ", "")
        if "위치도" in head and "전경" not in head:
            slots = rb._pic_slots(tbl)
            if slots:
                rb._put_pic(slots[0][1], D.map_path or blank, add_image)
            if len(slots) > 1:
                rb._put_pic(slots[-1][1], photos[0] if photos else blank, add_image)
            n += 1
    k = 0
    tops = _tops(root)
    for i, p in enumerate(tops):
        prev = _para_text(tops[i - 1]).replace(" ", "") if i else ""
        for tbl in p.iter(f"{{{HP}}}tbl"):
            if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
                continue
            pics = list(tbl.iter(f"{{{HP}}}pic"))
            if not pics:
                continue
            head = rb._cell_text(rb._cells(tbl).get((0, 0), tbl)).replace(" ", "")
            if "위치도" in head and "전경" not in head:
                continue  # 위 "■ 대상시설물 위치도" 표는 이미
            if prev.endswith("위치도"):  # 요약문 1.4 위치도 — 지도
                rb._put_pic(pics[0], D.map_path or blank, add_image)
                n += 1
            elif prev.endswith("상태평가결과"):  # 요약문 2.4 상태평가 결과 — 갑지 윗부분(건물개요~최종결과) 그림, 틀 크기·자르기 속성을 새 그림에 맞춤(옛 사진 속성이 남으면 확대돼 보임)
                sz = pics[0].find(f"{{{HP}}}curSz")
                img = next(pics[0].iter(f"{{{CORE}}}img"), None)
                if D.rating_png and img is not None:
                    tops[i - 1].set("pageBreak", "1")  # 그림이 커서 2.3 표 아래 안 들어가면 제목만 남고 그림만 넘어감 → 2.4는 새 쪽에서(형 10/14 "아예 넘겨")
                    jpg, ratio = _rating_crop(D.rating_png, 1.0)  # rating_png는 이미 갑지 윗부분(건물개요~최종결과)만 — 더 자르지 않음
                    w = int(sz.get("width")) if sz is not None and int(sz.get("width") or 0) > 0 else 46000
                    h = int(w / ratio)
                    _reset_pic(pics[0], w, h)
                    img.set("binaryItemIDRef", add_image(_px_for_frame(jpg, w, h)))
                    for tc in tbl.iter(f"{{{HP}}}tc"):  # 1×1 그림 표 칸 높이도 그림에 맞게
                        csz = tc.find(f"{{{HP}}}cellSz")
                        if csz is not None and int(csz.get("height") or 0) < h + 600:
                            csz.set("height", str(h + 600))
                    tsz = tbl.find(f"{{{HP}}}sz")
                    if tsz is not None and int(tsz.get("height") or 0) < h + 600:
                        tsz.set("height", str(h + 600))
                    n += 1
                else:
                    rb._put_pic(pics[0], blank, add_image)
            elif head.startswith("시설물명") or (int(tbl.get("rowCnt")) == 1 and int(tbl.get("colCnt")) == 1 and len(pics) == 1 and not "".join(rb._full(t) for t in tbl.iter(T)).strip()):
                for pic in pics:  # 현황표 전경사진 칸·글 없는 1×1 그림 표 — 전경사진 차례로
                    rb._put_pic(pic, photos[k] if k < len(photos) else blank, add_image)
                    k += 1
                    n += 1
    return n


# ---------- 2장 ----------

def _fill_docs(root, D: Data) -> int:
    tbl = rb._find_table(root, ["구분", "자료수집대상자료", "보관유무"])
    if tbl is None:
        return 0
    cells = rb._cells(tbl)
    groups = ["시공관련자료", "설계도서", "유지관련자료"]
    by = {g: [d for d in D.pr["docs"] if d["group"] == g] for g in groups}
    for r, g in zip(range(1, 4), groups):
        sts = [d["status"] for d in by[g] if d["status"]]
        if not sts:
            status = "-"
        elif all(s == sts[0] for s in sts):
            status = sts[0]
        else:
            status = "일부 보유"
        notes = []
        for d in by[g]:
            if d["note"] and d["note"] not in notes:
                notes.append(d["note"])
        _set(cells, r, 2, status)
        _set(cells, r, 3, notes or ["-"])
    return 1


def _fill_repairs(root, D: Data) -> int:
    tbl = rb._find_table(root, ["공사명", "보수보강부위", "설계자", "시공자"])
    if tbl is None:
        return 0
    cells = rb._cells(tbl)
    pairs = [(r, r + 1) for r in range(2, int(tbl.get("rowCnt")) - 1, 2)]
    for i, (a, b) in enumerate(pairs):
        e = D.repairs[i] if i < len(D.repairs) else None
        vals_a = [e.get("kind") or "-", e.get("where") or "-", "-", "-"] if e else ["-"] * 4
        vals_b = [e.get("period") or "-", e.get("method") or "-", "-", "-"] if e else ["-"] * 4
        for c, v in enumerate(vals_a):
            _set(cells, a, c, v)
        for c, v in enumerate(vals_b):
            _set(cells, b, c, v)
    if len(D.repairs) > len(pairs):
        D.notes.append(f"보수·보강 이력이 {len(D.repairs)}건인데 표 칸이 {len(pairs)}건이라 앞 {len(pairs)}건만 넣었습니다")
    return 1


def _fill_history(root, D: Data) -> int:
    tbl = rb._find_table(root, ["번호", "점검명", "점검기간"])
    if tbl is None:
        return 0
    hist = D.pr["history"] or D.pr["history_auto"]
    n = _fit_rows(tbl, len(hist), 1)
    cells = rb._cells(tbl)
    for i in range(n):
        h = hist[i] if i < len(hist) else None
        vals = [str(i + 1), h["kind"] or "-", h["start"] or "-", h["end"] or "-", h["org"] or "-", h["grade"] or "-", h["result"] or "-"] if h else ["-"] * 7
        row = _row_cells(cells, i + 1)
        for tc, v in zip(row, vals):
            rb._set_lines(tc, v.split("\n")[:6] if tc is row[-1] else [v])
        lines = max(1, len((vals[-1] or "").split("\n")[:6]), (len(vals[-1]) // 28 + 1) if h else 1)
        _set_row_height(tbl, i + 1, 1200 + 900 * (lines - 1))
    return 1


def _fill_seismic_body(root, D: Data) -> int:
    tbl = rb._find_table(root, ["내용"])
    if tbl is None or int(tbl.get("colCnt")) != 1:
        return 0
    cells = rb._cells(tbl)
    s = D.pr["seismic"]
    _set(cells, 1, 0, s["note"] or (f"구조계산서, 시설물관리대장 등 관련자료 검토 결과 내진설계가 {s['status']}된 것으로 확인되었다." if s["status"] in ("적용", "미적용") else "내진설계 적용 여부는 확인되지 않았다."))
    return 1


def _fill_uses(root, D: Data) -> int:
    tbl = rb._find_table(root, ["구분", "층별", "바닥면적(㎡)"])
    if tbl is None:
        return 0
    f = D.facility
    keys = list(reversed(TESTS.floor_keys(f.floors_above or 0, f.floors_below or 0)))  # 위층부터? 다산은 지하3층부터 위로 — 지하부터
    keys = list(reversed(keys))
    cells = rb._cells(tbl)
    rows = sorted({k[0] for k in cells})
    data_rows = [r for r in rows if r >= 1 and not rb._cell_text(cells.get((r, 0), cells.get((r, 1)))).replace(" ", "").startswith("계") and (r, 1) in cells]
    total_row = next((r for r in rows if any(rb._cell_text(cells[(r, c)]).replace(" ", "") == "계" for c in range(3) if (r, c) in cells)), None)
    if len(keys) > len(data_rows) and data_rows:  # 틀은 8개 층 — 마지막 층 줄을 복사해 '계' 앞에(건물명 칸 rowSpan도 같이, 10/14 숭의 13개층)
        rb._dup_rows(tbl, data_rows[-1], 1, len(keys) - len(data_rows))
        cells = rb._cells(tbl)
        rows = sorted({k[0] for k in cells})
        data_rows = [r for r in rows if r >= 1 and not rb._cell_text(cells.get((r, 0), cells.get((r, 1)))).replace(" ", "").startswith("계") and (r, 1) in cells]
        total_row = next((r for r in rows if any(rb._cell_text(cells[(r, c)]).replace(" ", "") == "계" for c in range(3) if (r, c) in cells)), None)
    use = f.main_use or f.use_type or "-"
    by_floor = {}  # 시설물 현황 창에서 건축물대장을 읽은 층별 [층, 면적, 용도, 비고](detail.uses, 10/14)
    for row in ((D.detail or {}).get("uses") or []):
        if isinstance(row, list) and row and str(row[0]).strip():
            by_floor[str(row[0]).replace(" ", "")] = row
    for i, r in enumerate(data_rows):
        if i < len(keys):
            lb = TESTS.floor_label(keys[i])
            u = by_floor.get(lb) or by_floor.get(lb.replace("지상", "")) or []
            area = str(u[1]).strip() if len(u) > 1 and str(u[1]).strip() else "-"
            _set(cells, r, 1, lb); _set(cells, r, 2, area); _set(cells, r, 3, (str(u[2]).strip() if len(u) > 2 and str(u[2]).strip() else use)); _set(cells, r, 4, str(u[3]).strip() if len(u) > 3 else "")  # noqa: E702
        else:
            _set(cells, r, 1, "-"); _set(cells, r, 2, "-"); _set(cells, r, 3, "-")  # noqa: E702
    for p in _tops(root):  # 캡션이 틀 글자("부재별 점검방향 설정")로 남아 있던 것
        tx = _para_text(p)
        if tx.startswith("【표 2.4】") and "점검방향" in tx:
            rb._set_para(p, "【표 2.4】층별 용도 현황")
    if (1, 0) in cells:
        _set(cells, 1, 0, f.name)
    if total_row is not None and (total_row, 2) in cells:
        _set(cells, total_row, 2, f"{f.total_area:,.2f}㎡" if f.total_area else "-")
    if len(keys) > len(data_rows):
        D.notes.append(f"용도 현황 표가 {len(data_rows)}개 층뿐이라 {len(keys)}개 층 중 앞부분만 넣었습니다")
    if not by_floor:
        D.notes.append("층별 바닥면적·용도는 건축물대장을 시설물 현황 창에 올려 읽으면 들어갑니다(지금은 주용도만)")
    return 1


def _fill_manage(root, D: Data) -> int:
    m = D.pr["manage"]
    n = 0
    for p in _tops(root):
        t = _para_text(p)
        for label, key in (("용도변경", "use_change"), ("구조변경", "struct_change"), ("주변조건의 변경사항", "surround_change")):
            if t.startswith(("1)", "2)", "3)")) and label in t and ":" in t:
                head = t.split(":")[0].strip()
                marks = " ".join(f"{'■' if m[key] == v else '□'} {v}" for v in ("유", "무", "불명"))
                rb._set_para(p, f"{head} : {marks}")
                n += 1
    tbl = next((t_ for t_ in root.iter(f"{{{HP}}}tbl") if _head(t_, 3) == ["분야", "점검내용", "결과"]), None)  # 머리칸이 합쳐져 있어 _find_table로는 못 찾음(10/14)
    if tbl is not None:
        from server.sitok import precision as PR

        cells = rb._cells(tbl)
        rows = [r for r in sorted({k[0] for k in cells}) if (r, 1) in cells and rb._cell_text(cells[(r, 1)]).strip().startswith("□")]
        auto = PR.auto_checklist(D.defects) if not m["checklist"] else {}  # 점검자가 체크한 게 없으면 결함 목록으로(10/14)
        note_done = False
        for i, r in enumerate(rows):
            a = auto.get(str(i))
            bad = bool(m["checklist"].get(str(i))) or bool(a)
            _set(cells, r, 3, "" if bad else "■")
            _set(cells, r, 5, "■" if bad else "")
            _set(cells, r, 7, "■" if a else "")
            _set(cells, r, 9, "·".join(a["types"]) if a else "")
            if (r, 11) in cells:
                note = a["where"] if a else (m["note"] if bad and not note_done else "")
                _set(cells, r, 11, note)
                if bad and m["note"] and not a:
                    note_done = True
        n += 1
    return n


def _fill_prev_review(root, D: Data) -> int:
    tbl = rb._find_table(root, ["구분", "점검결과"])
    pa = D.pr["prev_auto"]
    manual = D.pr["prev_review"]["text"].strip()
    n = 0
    if tbl is not None:
        cells = rb._cells(tbl)
        lines = [ln for ln in manual.split("\n") if ln.strip() and not ln.strip().startswith("※")] if manual else (pa["lines"] if pa else ["이번 회차가 첫 회차 정밀안전점검으로 전차 점검 보고서가 없다."])
        _set(cells, 1, 1, pa["kind"] if pa else "-")
        _set(cells, 2, 1, "(주)한국미래안전" if pa else "-")
        _set(cells, 3, 1, [x if x.startswith(("ㆍ", "·", "-")) else f"ㆍ{x}" for x in lines])
        n += 1
    for p in _tops(root):
        t = _para_text(p)
        if t.startswith("※") and "정밀안전점검" in t:
            star = next((ln.strip() for ln in manual.split("\n") if ln.strip().startswith("※")), "")
            rb._set_para(p, star or ("" if pa else f"※ {D.texts.get('completion_text', '')} 준공으로 이번 회차가 첫 회차 정밀안전점검임."))
            n += 1
    return n


# ---------- 3장 ----------

def _photo_groups(D: Data) -> dict:
    """3.2 손상사진 묶음 — 이번 회차 사진, 없으면 전회차 사진("그대로"로 넘긴 결함, 10/14)."""
    def ph(d):
        return d.photo if d.photo and Path(d.photo).exists() else d.prev_photo if d.prev_photo and Path(d.prev_photo).exists() else ""
    ds = [(d, ph(d)) for d in D.defects]
    ds = [(d, p) for d, p in ds if p]
    cap = lambda d: f"{d.floor} {d.member} {d.dtype}".strip()  # noqa: E731
    return {
        "crack": [(p, cap(d)) for d, p in ds if d.part == "구조체" and "균열" in (d.dtype or "")],
        "leak": [(p, cap(d)) for d, p in ds if any(w in (d.dtype or "") for w in ("누수", "백태", "백화"))],
        "spall": [(p, cap(d)) for d, p in ds if d.part == "구조체" and any(w in (d.dtype or "") for w in ("박리", "박락", "층분리", "철근"))],
        "steel": [(p, cap(d)) for d, p in ds if (d.member or "") == "강재"],
        "nonstruct": [(p, cap(d)) for d, p in ds if d.part == "비구조체"],
    }


def _fill_survey_pics(root, D: Data, tpl, add_image) -> int:
    """조사 전경 사진(형 10/14) — 【사진 2.1】 외관조사 2 · 【사진 4.1~4.5】 재료시험 조사 전경(칸 제목 = precision.SURVEY_PICS). 안 찍은 칸은 흰 그림(다산 사진이 남지 않게)."""
    from server.sitok import precision as PR

    n = 0
    for key, cap, _, titles in PR.SURVEY_PICS:
        tbl = _table_after(root, cap)
        if tbl is None:
            continue
        paths = list(D.survey_pics.get(key) or [])
        photos = [((paths[i] if i < len(paths) and paths[i] and Path(paths[i]).exists() else D.blank), t) for i, t in enumerate(titles)]
        if _photos_into(tbl, photos, tpl, add_image):
            n += 1
    return n


def _fill_ch3(root, D: Data, tpl, add_image) -> int:
    n = 0
    t = D.texts
    groups = _photo_groups(D)
    for cap, key, text_key in (("【사진 3.2】", "crack", "crack"), ("【사진 3.3】", "leak", "leak"), ("【사진 3.4】", "spall", "spall"),
                               ("【사진 3.7】", "steel", "steel"), ("【사진 3.8】", "nonstruct", "nonstruct")):
        tbl = _table_after(root, cap)
        if tbl is not None and _photos_into(tbl, groups[key], tpl, add_image):
            n += 1
    for head, key in (("^3\\.2\\.1", "crack"), ("^3\\.2\\.2", "leak"), ("^3\\.2\\.3", "spall"), ("^3\\.2\\.4", "steel"), ("^3\\.2\\.5", "nonstruct"),
                      ("^3\\.2\\.6", "load"), ("^3\\.2\\.7", "public"), ("^3\\.2\\.8", "other")):
        n += _set_after(root, head, [t.get(key, "")], regex=True)
    for p in _tops(root):
        tx = _para_text(p)
        if tx.startswith("3.2.4") and "강재" in tx:
            rb._set_para(p, "3.2.4 강재구조 노후상태 조사결과" + ("(해당없음)" if t.get("steel_na") else ""))
    tbl = _table_after(root, "【사진 3.9】")
    if tbl is not None and _photos_into(tbl, D.load_photos, tpl, add_image, none_text="-"):
        n += 1
    tbl = _table_after(root, "【사진 3.10】")
    if tbl is not None:
        if int(tbl.get("rowCnt")) >= 6:  # 틀은 6칸(옹벽·절토사면까지) — 공중이용 탭 4항목에 맞춰 마지막 줄(사진·설명 2줄) 빼기(형 10/14)
            rb._del_rows(tbl, 4, 2)
        slots = _slots(tbl)
        cells = rb._cells(tbl)
        items = list(D.parts.get("public") or [])[:4]
        for i, (pk, ck) in enumerate(slots):
            name, path = items[i] if i < len(items) else ("-", None)
            image = None
            if path and Path(path).exists():
                pic = _pic_or(cells[pk], tpl)
                sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
                w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
                image = rb._cropped(path, w, h)
            rb._slot_put(cells[pk], cells[ck] if ck else None, image, "해당없음", name, tpl, add_image)
        n += 1
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if rb._cell_text(rb._cells(tbl).get((0, 0), tbl)).replace(" ", "").startswith("■기타시설사진현황"):
            slots = _slots(tbl)
            cells = rb._cells(tbl)
            items = list(D.parts.get("other") or [])
            for i, (pk, ck) in enumerate(slots):
                name, path = items[i] if i < len(items) else ("-", None)
                image = None
                if path and Path(path).exists():
                    pic = _pic_or(cells[pk], tpl)
                    sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
                    w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
                    image = rb._cropped(path, w, h)
                rb._slot_put(cells[pk], cells[ck] if ck else None, image, "-", name, tpl, add_image)
            n += 1
            break
    n += _fill_analysis_tables(root, D)
    return n


def _fill_analysis_tables(root, D: Data) -> int:
    """3.1·7.1 "외관조사 결과의 분석" 표(조사항목 | 조사결과) 8줄."""
    t = D.texts
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if [rb._cell_text(cells.get((0, c), tbl)).replace(" ", "") for c in range(2)] != ["조사항목", "조사결과"]:
            continue
        for r in sorted({k[0] for k in cells}):
            if r == 0 or (r, 1) not in cells:
                continue
            label = rb._cell_text(cells[(r, 0)]).replace(" ", "").replace("\n", "")
            key = ("crack" if "균열" in label else "leak" if "누수" in label else "spall" if "박리" in label or "철근" in label else "steel" if "강재" in label
                   else "nonstruct" if "비구조" in label else "load" if "하중" in label else "public" if "공중" in label else "other" if "기타" in label else None)
            if key:
                _set(cells, r, 1, f"ㆍ{t.get(key, '')}")
        rb._splittable(tbl, 1)  # 글이 길어져도 통째로 다음 쪽으로 안 가고 줄 단위로(10/14 "표가 통째로 넘어감")
        n += 1
    return n


# ---------- 4장(본문)·성과표(부록) — 표는 머리줄 글자로 찾음 ----------

def _head(tbl, n: int = 4) -> list[str]:
    """머리줄 칸 글(열 순서, 합친 칸은 하나로 — 고정 칸 번호로 읽으면 합쳐진 머리칸에서 어긋남)."""
    cells = rb._cells(tbl)
    return [re.sub(r"\s", "", rb._cell_text(cells[k])) for k in sorted(k for k in cells if k[0] == 0)][:n]


def _tables(root, head: list[str], ncol: int | None = None) -> list:
    want = [h.replace(" ", "") for h in head]
    out = []
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        if _head(tbl, len(want)) == want and (ncol is None or int(tbl.get("colCnt")) == ncol):
            out.append(tbl)
    return out


def _fill_quantity(root, D: Data) -> int:
    """표 4.1(층수·연면적 √·금회수량), 표 4.2(7×7 수량), 항목별 산출수량 3×6·3×4(캡션 뒤)."""
    tv, f = D.tv, D.facility
    n = 0
    total_floors = (f.floors_above or 0) + (f.floors_below or 0)
    need = tv["sample"]["need"] or 0
    q = tv["sample"]["quantity"]
    for tbl in _tables(root, ["층수", "수량기준", "연면적(㎡)"]):
        cells = rb._cells(tbl)
        pick = 4 if total_floors <= 10 else 3 if total_floors <= 20 else 2
        for r in (2, 3, 4):
            _set(cells, r, 4, "√" if r == pick else "")
        _set(cells, 2, 5, ["￮ 층수", f"  - 지상{f.floors_above or 0}층, 지하{f.floors_below or 0}층({total_floors}개층)", "￮ 연면적", f"  - {f.total_area or 0:,.2f}㎡",
                           "￮ 층수별·연면적별 최대치", f"  - {need}개층, {need}개 단위 산정"])
        n += 1
    for tbl in _tables(root, ["구분", "세부지침기준", "금회수량"]):
        cells = rb._cells(tbl)
        if int(tbl.get("rowCnt")) >= 7:
            _set(cells, 2, 2, ["￮ 표본층(단위)수", f"({need}개 단위 산정)"])
            for r, key in ((2, "strength"), (3, "section"), (4, "carbonation"), (5, "tilt"), (6, "settlement")):
                _set(cells, r, 5, q[key]["need"]); _set(cells, r, 6, q[key]["have"] or "-")  # noqa: E702
            n += 1
    for cap, key in (("【표 4.3】", "section"), ("【표 4.5】", "strength"), ("【표 4.7】", "carbonation"), ("【표 4.9】", "tilt"), ("【표 4.11】", "settlement")):
        tbl = _table_after(root, cap)
        if tbl is None or int(tbl.get("rowCnt")) != 3:
            continue
        cells = rb._cells(tbl)
        row = _row_cells(cells, 2)
        if len(row) >= 2:
            rb._set_lines(row[-2], [str(q[key]["need"])]); rb._set_lines(row[-1], [str(q[key]["have"] or "-")])  # noqa: E702
        if key in ("section", "strength", "carbonation") and (2, 2) in cells:
            _set(cells, 2, 2, ["￮ 표본층(단위)수", f"({need}개 단위 산정)"])
        n += 1
    return n


def _fill_section_tbl(tbl, D: Data) -> None:
    secs = D.tv["sections"]
    k = _fit_rows(tbl, len(secs), 1)
    cells = rb._cells(tbl)
    for i in range(k):
        s = secs[i] if i < len(secs) else None
        vals = [f"B{i + 1}", TESTS.floor_label(s["floor"]) if s and s["floor"] else "-", s["position"] or "-", s["member"] or "-", s["design"] or "-", s["measured"] or "-",
                ("O.K" if s["ok"] else "N.G") if s and s["ok"] is not None else "-"] if s else ["-"] * 7
        for tc, v in zip(_row_cells(cells, i + 1), vals):
            rb._set_lines(tc, [v])
        _set_row_height(tbl, i + 1, 1400)


def _fill_strength_tbl(tbl, D: Data) -> None:
    tv = D.tv
    cells = rb._cells(tbl)
    rows = sorted({k[0] for k in cells})
    label_of = lambda r: rb._cell_text(cells.get((r, 0), tbl)).replace(" ", "")  # noqa: E731
    data_rows = [r for r in rows if r >= 1 and (r, 2) in cells and label_of(r) not in ("최대값", "최소값", "평균")]
    st = tv["strength"]["rows"]
    if len(st) > len(data_rows) and data_rows:  # 표본층 3개(12개소)인데 틀은 8줄 — 마지막 데이터 줄을 복사해 꼬리(최대값…) 앞에 끼움(10/14 숭의)
        rb._dup_rows(tbl, data_rows[-1], 1, len(st) - len(data_rows))
        cells = rb._cells(tbl)
        rows = sorted({k[0] for k in cells})
        data_rows = [r for r in rows if r >= 1 and (r, 2) in cells and label_of(r) not in ("최대값", "최소값", "평균")]
    fmt = lambda v: "-" if v is None else f"{v:g}"  # noqa: E731
    for i, r in enumerate(data_rows):
        x = st[i] if i < len(st) else None
        vals = [f"S{i + 1}", TESTS.floor_label(x["floor"]) if x and x["floor"] else "-", (x.get("member_text") or x["member"]) or "-", fmt(x["r0"]), fmt(x["fc_mat"]), fmt(x["fc_arch"]), fmt(x["est"]), fmt(x["design"]),
                x["note"] or ("손상부" if x["damaged"] else "건전부")] if x else ["-"] * 9
        for tc, v in zip(_row_cells(cells, r), vals):
            rb._set_lines(tc, [v])
    sm = tv["strength"]["summary"]
    for r in rows:
        label = label_of(r)
        if label in ("최대값", "최소값", "평균"):
            row = _row_cells(cells, r)
            if len(row) >= 2:
                rb._set_lines(row[1], [fmt({"최대값": sm["max"], "최소값": sm["min"], "평균": sm["mean"]}[label])])
    if len(st) > len(data_rows):
        D.notes.append(f"강도 조사 표가 {len(data_rows)}개소뿐이라 {len(st)}개소 중 앞부분만 넣었습니다")


def _fill_carb_tbl(tbl, D: Data) -> None:
    tv = D.tv
    cells = rb._cells(tbl)
    rows = sorted({k[0] for k in cells})
    starts = [r for r in rows if (r, 0) in cells and re.fullmatch(r"C\d+", rb._cell_text(cells[(r, 0)]).strip() or "")]
    cr = tv["carbonation"]["rows"]
    if len(cr) > len(starts) and starts:  # 본문 표는 한 개소 = 2줄(C줄 + 부재줄), 부록 성과표는 1줄 — 마지막 묶음을 복사해 뒤에(10/14 숭의 6개소)
        step = (starts[1] - starts[0]) if len(starts) > 1 else (2 if (starts[0] + 1, 1) in cells and (starts[0] + 1, 0) not in cells else 1)
        rb._dup_rows(tbl, starts[-1], step, len(cr) - len(starts))
        cells = rb._cells(tbl)
        starts = starts + [starts[-1] + step * i for i in range(1, len(cr) - len(starts) + 1)]  # 복사한 묶음은 글자가 비어 다시 못 찾으니 주소로
    fmt = lambda v: "-" if v is None else f"{v:g}"  # noqa: E731
    for i, r in enumerate(starts):
        c = cr[i] if i < len(cr) else None
        vals = [f"C{i + 1}", TESTS.floor_label(c["floor"]) if c and c["floor"] else "-", str(c["age"] if c and c["age"] is not None else "-"), fmt(c["cover"]), fmt(c["depth"]), fmt(c["remain"]),
                fmt(c["coef"]), f"{tv['carbonation']['wc']:g}", f"{tv['carbonation']['ratio']:g}", fmt(c["theory"]), c["life_text"] or "-", (c["grade"] or "-").upper()] if c else ["-"] * 12
        for col, v in enumerate(vals):
            _set(cells, r, col, v)
        if (r + 1, 1) in cells:
            _set(cells, r + 1, 1, c["member"] if c else "-")
    if len(cr) > len(starts):
        D.notes.append(f"탄산화 표가 {len(starts)}개소뿐이라 {len(cr)}개소 중 앞부분만 넣었습니다")


def _fill_tilt_tbl(tbl, D: Data) -> None:
    """기울기 표 — 줄의 칸을 순서대로(본문 7칸, 부록은 변위방향 칸이 둘로 합쳐져 칸 번호가 다름). 첫 칸이 번호인 줄만(부록 표 아래 사진 줄은 건너뜀)."""
    ti = D.tv["tilt"]["rows"]
    cells = rb._cells(tbl)
    data_rows = []
    for r in sorted({k[0] for k in cells}):
        row = _row_cells(cells, r)
        if r >= 1 and len(row) >= 6 and re.fullmatch(r"[\d\-]*", rb._cell_text(row[0]).strip()):
            data_rows.append(row)
    for i, row in enumerate(data_rows):
        x = ti[i] if i < len(ti) else None
        vals = [str(i + 1), f"{x['height']:,.0f}" if x and x["height"] else "-", x["direction"] or "-", f"{x['disp']:g}" if x and x["disp"] is not None else "-", "1/",
                f"{x['n']:,}" if x and x["n"] else "-", (x["grade"] or "-").upper()] if x else ["-", "-", "-", "-", "", "-", "-"]
        for tc, v in zip(row[:7], vals):
            rb._set_lines(tc, [v])
    if len(ti) > len(data_rows):
        D.notes.append(f"기울기 표가 {len(data_rows)}개소뿐이라 {len(ti)}개소 중 앞부분만 넣었습니다")


def _fill_settle_tbls(root, D: Data) -> int:
    """첫 칸이 "… 바닥 X축 방향(1구간)"인 표들 — 축·구간을 제목에서 읽어 그 구간 값."""
    tv = D.tv
    secs = {}
    for s_ in tv["settlement"]["sections"]:
        secs.setdefault((s_["axis"], s_["no"]), s_)
    floor_label = tv["settlement"]["floor_label"] or "최하층"
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        cells = rb._cells(tbl)
        title = rb._cell_text(cells.get((0, 0), tbl)).replace(" ", "")
        m = re.search(r"([XY])축방향\((\d)구간\)", title)
        if not m or int(tbl.get("rowCnt")) < 7:
            continue
        axis, no = m[1], int(m[2])
        s_ = secs.get((axis, no))
        _set(cells, 0, 0, f"{floor_label} 바닥 {axis}축 방향({no}구간)")
        rows = s_["rows"] if s_ else []
        for i in range(3):
            r_level, r_disp = 2 + 2 * i, 3 + 2 * i
            row = rows[i] if i < len(rows) else None
            _set(cells, r_level, 0, str(i + 1)); _set(cells, r_level, 1, "위치도 참조")  # noqa: E702
            _set(cells, r_level, 2, f"{row['level']:,.0f}" if row and row["level"] is not None else "-")
            if row and row["disp"] is not None:
                _set(cells, r_disp, 3, f"{row['disp']:g}"); _set(cells, r_disp, 4, f"{row['distance']:,.0f}" if row["distance"] else "-")  # noqa: E702
                _set(cells, r_disp, 5, "1/"); _set(cells, r_disp, 6, f"{row['n']:,}" if row["n"] else "-"); _set(cells, r_disp, 7, (row["grade"] or "-").upper())  # noqa: E702
            else:
                for col in (3, 4, 5, 6, 7):
                    _set(cells, r_disp, col, "")
        n += 1
    return n


def _fill_test_tables(root, D: Data) -> int:
    """규격·강도·탄산화·기울기·부등침하 표 — 본문 4장과 부록 성과표 둘 다(머리줄로 찾음)."""
    n = 0
    for tbl in _tables(root, ["NO.", "위치", "부재", "설계도면"]):
        _fill_section_tbl(tbl, D); n += 1  # noqa: E702
    for tbl in _tables(root, ["구분", "위치", "부재부위", "보정반발경도(R0)"]):
        _fill_strength_tbl(tbl, D); n += 1  # noqa: E702
    for tbl in _tables(root, ["no", "측정위치", "경과년수"]):
        _fill_carb_tbl(tbl, D); n += 1  # noqa: E702
    for tbl in _tables(root, ["NO", "측정높이(㎜)"]):
        _fill_tilt_tbl(tbl, D); n += 1  # noqa: E702
    n += _fill_settle_tbls(root, D)
    return n


def _fill_ch4(root, D: Data) -> int:
    n = _fill_quantity(root, D) + _fill_test_tables(root, D)
    t = D.texts
    for i, keys in enumerate((["section"], ["strength"], ["carb", "carb_life"], ["tilt"], ["settle"])):
        n += _set_after(root, "나. 결과 분석", [t.get(k, "") for k in keys], nth=i)
    return n


# ---------- 5·7장 ----------

def _fill_ch5_7(root, D: Data, add_image) -> int:
    t = D.texts
    n = 0
    n += _set_after(root, "가. 부재규격 조사", [t.get("section", "")])
    n += _set_after(root, "나. 균열 및 표면노후화 상태", [f"ㆍ{t.get(k, '')}" for k in ("crack", "leak", "spall", "steel", "nonstruct", "load")])
    n += _set_after(root, "다. 콘크리트 강도", [t.get("strength", "")])
    n += _set_after(root, "라. 콘크리트 탄산화", [t.get("carb", ""), t.get("carb_life", "")])
    n += _set_after(root, "1) 기울기 조사 결과", [t.get("tilt", "")])
    n += _set_after(root, r"^2\)\s*부등침하 조사 결과", [t.get("settle", "")], regex=True)
    n += _set_after(root, "바. 공중이 이용하는 부위", [t.get("public", "")])
    n += _set_after(root, r"^5\.2\s*종합평가", [t.get("overall", "")], regex=True)
    n += _set_after(root, r"^7\.4\s*종합평가", [t.get("overall", "")], regex=True)
    for head, key in (("7.2.1", "section"), ("7.2.2", "strength"), ("7.2.3", "carb"), ("7.2.4", "tilt"), ("7.2.5", "settle")):
        n += _set_after(root, rf"^{re.escape(head)}", [t.get(key, "")], regex=True)
    n += _set_after(root, r"^7\.5\s*종합결론", [t.get("conclusion", ""), "조사된 손상들의 경우 구조적인 문제점은 없는 상태이나, 추가손상방지 및 내구성 확보를 위해 보수 및 지속적인 "
                                                   "주의관찰이 요구되며, 시설물의 공용기간 및 시설물의 등급을 감안하여 중·장기적인 건축물의 유지관리계획을 수립하여 관리하는 것이 바람직하다."], regex=True)
    # 상태평가 결과 그림(【그림 5.1】 뒤·7.3 뒤)
    tops = _tops(root)
    for i, p in enumerate(tops):
        tx = _para_text(p)
        if tx.startswith("【그림 5.1】") or tx.startswith("7.3 상태평가 결과"):
            for q in tops[i + 1:i + 4]:
                if _put_png(q, D.rating_png, add_image):
                    n += 1
                    break
    return n


# ---------- 6장 보수물량·우선순위(8칸) ----------

def _fill_priority(root, D: Data) -> int:
    """보수물량 및 우선순위(정밀 8칸: 층 칸이 세로로 합쳐짐) — 정기 _priority_table처럼 표를 새로 짜고(쪽 단위로 나눔) 층은 세로 합침.
    줄만 지우면 합친 층 칸의 rowSpan이 표 밖으로 나가 한글이 PDF 변환 중 죽음(10/13)."""
    n = 0
    for tbl in list(root.iter(f"{{{HP}}}tbl")):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        cells = rb._cells(tbl)
        if _head(tbl, 4) != ["구분", "부재", "손상내용", "적용공법"] or int(tbl.get("colCnt")) != 8 or not all((1, c) in cells for c in range(8)):
            continue
        rows = D.priority or [("-", "-", "-", "특이사항 없음", "-", "-", "-", "-")]
        data = [[[str(x)] for x in r] for r in rows]
        h = int(cells[(1, 2)].find(f"{{{HP}}}cellSz").get("height"))
        heights = rb._row_heights({c: cells[(1, c)] for c in range(8)}, data, h)
        rb._rebuild_paged(root, tbl, data, 1, heights, False, first_page_h=rb.SUMMARY_PAGE_H - 9000)
        n += 1
    return n


# ---------- 전체 ----------

def _fill(src: Path, dest: Path, D: Data) -> int:
    added: list[tuple[str, bytes]] = []
    run = datetime.datetime.now().strftime("%y%m%d%H%M%S")

    def add_image(path_or_bytes) -> str:
        key = f"sitokp{run}_{len(added) + 1}"
        added.append((key, path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()))
        return key

    changed = 0
    hpf = b""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as zout:
        ordered = rb._sections(zin)
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in ordered:
                root = etree.fromstring(data)
                is_front = info.filename == ordered[0]
                if D.replace:
                    changed += rb._apply(root, D.replace, [], set(), is_front)
                tpl = next((copy.deepcopy(p) for p in root.iter(f"{{{HP}}}pic")), None)
                changed += _fill_compare(root, D) + _fill_limit(root, D) + _fill_priority(root, D) + _fill_analysis_tables(root, D) + _fill_status_tables(root, D) + _fill_general_tables(root, D)
                if is_front:
                    changed += _fill_result_table(root, D) + _fill_summary_table(root, D) + _fill_seismic(root, D)
                    for tbl in _result_tables(root):  # 결과표가 길어지면 통째로 다음 쪽으로 넘어가지 않고 줄 단위로 나뉘게(사용자 10/14 — 원본은 pageBreak TABLE)
                        rb._splittable(tbl, 0)
                        tbl.set("repeatHeader", "0")  # "가. 일반현황" 줄이 다음 쪽에 또 찍히지 않게
                        if _split_result_table(root, tbl):  # 한 쪽을 넘을 것 같으면 '다.'부터 새 쪽(형 10/14)
                            changed += 1
                    if D.result_fields:
                        changed += rb._set_result_fields(root, D.result_fields)
                    if D.cost is not None and rb._cost_table(root, D.cost[0], D.cost[1]):  # 요약문 2.7 개략공사비
                        changed += 1
                    changed += _fill_front_pics(root, D, add_image)
                    for tbl in root.iter(f"{{{HP}}}tbl"):  # 결과표 뒤 "시험명 | 개소 | 조사결과 | 책임기술자 의견" 표
                        cells = rb._cells(tbl)
                        if rb._cell_text(cells.get((0, 0), tbl)).replace(" ", "") == "시험명":
                            changed += _fill_test_rows(cells, D)
                    for p in _tops(root):
                        if "에 대한 정밀안전점검 결과" in _para_text(p) and "안전등급은" in _para_text(p):
                            rb._set_para(p, D.texts.get("conclusion", ""))
                            changed += 1
                else:
                    changed += (_fill_docs(root, D) + _fill_repairs(root, D) + _fill_history(root, D) + _fill_seismic_body(root, D) + _fill_uses(root, D)
                                + _fill_manage(root, D) + _fill_prev_review(root, D) + _fill_ch3(root, D, tpl, add_image) + _fill_survey_pics(root, D, tpl, add_image) + _fill_ch4(root, D)
                                + _fill_ch5_7(root, D, add_image))
                for el in list(root.iter(f"{{{HP}}}linesegarray")):
                    el.getparent().remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename == "Contents/content.hpf":
                hpf = data
                continue
            elif info.filename in ("Preview/PrvImage.png",):
                continue
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
        items = "".join(f'<opf:item id="{k}" href="BinData/{k}.jpg" media-type="image/jpg" isEmbeded="1"/>' for k, _ in added)
        zout.writestr("Contents/content.hpf", hpf.decode("utf-8").replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8"))
        for k, b in added:
            zout.writestr(f"BinData/{k}.jpg", b, compress_type=zipfile.ZIP_STORED)
    dest.with_suffix(".tmp").replace(dest)
    return changed


def _rating_png(db, r, rv: dict, tv: dict, facility, company_name: str) -> bytes | None:
    """부록 결과자료 PDF 첫 쪽(건축물 평가결과) → PNG — 5.1.3·7.3 그림."""
    if not rv.get("result"):
        return None
    import pymupdf

    from server.api.routers.sitok_defects import _defects_for_cost
    from server.api.routers.sitok_reports import _report_dir

    when = r.period_start or r.report_date or datetime.date.today()
    bi = {"name": facility.name, "address": facility.address, "owner": facility.owner_name,
          "completion": f"{facility.completion_date.year}년 {facility.completion_date.month}월" if facility.completion_date else "", "use": facility.main_use or facility.use_type,
          "structure": facility.structure, "land_area": "", "building_area": f"{facility.building_area:,.1f} ㎡" if facility.building_area else "",
          "total_area": f"{facility.total_area:,.1f} ㎡" if facility.total_area else "", "above": facility.floors_above or 0, "below": facility.floors_below or 0,
          "company": company_name, "phone": "", "when": when.isoformat()}
    agg = condition.aggregate(_defects_for_cost(db, r.id), tv, rv["counts"], above=facility.floors_above or 0, below=facility.floors_below or 0,
                              tilt_note=tv["tilt"]["note"], settlement_note=tv["settlement"]["note"])
    dest = _report_dir(facility, r) / "상태평가" / "상태평가결과.pdf"
    condition.make_pdf(dest, agg, rv["result"], bi, tv, rv["prev_grade"] or rv["prev_auto"])
    doc = pymupdf.open(dest)
    page = doc[0]
    rect = page.rect
    hit = page.search_for("입력자료")
    bottom = hit[0].y0 - 6 if hit else rect.y0 + rect.height * 0.62
    clip = pymupdf.Rect(rect.x0, rect.y0, rect.x1, min(rect.y1, bottom))  # 건물개요·평가결과·최종결과까지
    pix = page.get_pixmap(dpi=170, clip=clip)
    png = pix.tobytes("png")
    doc.close()
    return png


def _priority8(db, r, ai: dict | None) -> list:
    """보수물량 및 우선순위(정밀 8칸: 층·구분·부재·손상내용·공법·물량·단위·우선순위) — 정기 priority_rows와 같은 규칙, 부재를 따로."""
    from server.api.routers.sitok_defects import _defects_for_cost, _num, action_of, is_area, method_map, priority

    methods = method_map((ai or {}).get("methods"))
    groups: dict = {}
    for d in _defects_for_cost(db, r.id):
        key = (d.floor, "구조" if condition.kinds.counts_for_rating(d.part, d.dtype) else "비구조", d.member or "-", d.dtype or "-")
        act = action_of(d, methods)
        g = groups.setdefault(key, {"qty": 0.0, "act": act, "unit": "㎡" if is_area(d.dtype) else "m", "prio": 4})
        g["qty"] += _num(d.qty) or 0
        g["prio"] = min(g["prio"], priority(d, methods))
    out = []
    for (floor, part, member, dtype), g in groups.items():
        watch = g["act"] == "주의관찰"
        out.append((floor, part, member, f"·{dtype}", g["act"], "-" if watch or not g["qty"] else f"{g['qty']:.2f}", "-" if watch else g["unit"], str(g["prio"])))
    return out


def build_body(db, r, dest: Path) -> tuple[list[str], int, rb.Values]:
    """정밀 본문 한글 — (경고, 바꾼 곳 수, 새 값)."""
    from core.models_web import SitokFacility
    from server.api.routers import sitok_reports as SR

    f = db.get(SitokFacility, r.facility_id)
    src = master.master_path("정밀본문")
    if not src.exists():
        raise ValueError("정밀안전점검 본문 원본이 없습니다 — 시특법 설정에서 올리세요.")
    old = rb.read_old(src)
    if not old.name:  # 정밀 원본 용역명 "2026년 상반기 다산은혜교회 정밀안전점검 용역"엔 [시설물명]이 없음 — 연도·반기 뒤 ~ 정밀안전점검 앞
        m = re.search(r"\d{4}\s*년(?:도)?\s*(?:상반기|하반기)\s*(.+?)\s*정밀안전점검", old.title)
        old.name = m[1].strip() if m else (old.owner or "")
    prior = SR._prior(r)
    pv = rb.read_old(prior) if prior else None
    new, warn = SR._new_values(db, r, old, pv)
    if pv is None or not pv.title:
        new.title = f"{r.year}년 {r.half} {f.name} 정밀안전점검 용역"
    new.title = new.title.replace("정기안전점검", "정밀안전점검").replace("정기점검", "정밀점검")
    new.grade = ""
    fields = {}  # 원본(다산)은 관리주체·대표자가 시설물명과 같은 글자 — 통째 바꾸기가 서로 겹치므로 결과표 칸에 따로 넣음
    if old.rep and old.rep in (old.name, old.owner):
        fields["대표자"] = new.rep
        old.rep = ""
    if old.owner and old.owner == old.name:
        fields["관리주체명"] = new.owner
        old.owner = ""
    ex = SR._extras(db, r)
    ex1 = rb.Extras(images=ex.images, equipment=ex.equipment, positions=ex.positions, history=False, cost=ex.cost, template=ex.template, blank=ex.blank,
                    overview=ex.overview, has_drawings=True, parts=None, rep_photos={}, survey=({"detail": (r.survey or {}).get("detail")} if (r.survey or {}).get("detail") else None), ai=None)
    tmp = dest.with_suffix(".p1.hwpx")
    changed = rb.build(src, old, new, tmp, ex1)
    warn += ex1.notes
    D = _data_for(db, r, new, f, ex)
    D.result_fields = fields
    changed += _fill(tmp, dest, D)
    tmp.unlink(missing_ok=True)
    if not D.tv["sample"]["floors"]:
        D.notes.append("표본층이 없어 재료시험·상태평가 표가 비었습니다(📐 재료시험)")
    if D.rv["result"] is None:
        D.notes.append("상태평가 결과가 없어 등급·결과 그림이 비었습니다(📊 상태평가)")
    return warn + D.notes, changed, new


def _data_for(db, r, new: rb.Values, f, ex) -> Data:
    """본문·부록이 같이 쓰는 자료 묶음."""
    from core.models_web import Company
    from server.api.routers import sitok_precision as SP, sitok_rating as SRt, sitok_reports as SR, sitok_tests as ST
    from server.api.routers.sitok_defects import _defects_for_cost

    src = master.master_path("정밀본문")
    tv = ST._view(db, r)
    rv = SRt._compute(db, r)
    pr = SP._out(db, r)
    defects = _defects_for_cost(db, r.id)
    co = db.get(Company, r.company_id)
    comp_text = f"{f.completion_date.year}년 {f.completion_date.month:02d}월 {f.completion_date.day:02d}일" if f.completion_date else "-"
    grades = {x["key"]: x["grade"] for grp in ("public", "other") for x in pr["grades"][grp]}
    texts = precision_text.all_texts(defects, tv, rv["result"], grades=grades, structure=f.structure or "", load_note=pr["load"]["note"],
                                     prev_grade=rv["prev_grade"] or rv["prev_auto"], name=f.name, year=r.year, completion_text=comp_text,
                                     first=rv.get("prev_report") is None and not rv["prev_grade"], ai=ex.ai)  # 전차 등급을 직접 넣었으면 첫 회차 아님(10/14)
    texts["completion_text"] = comp_text
    base_dir = SR._report_dir(f, r)
    load_photos = [(str(base_dir / ph["file"]), ph["title"]) for ph in (((r.survey or {}).get("precision") or {}).get("load") or {}).get("photos") or [] if ph.get("file")]
    # 전체 글 바꾸기 — 원본 시설물 현황 칸(연면적·층수·구조·준공년도·종류·종별·FMS 번호)
    rep: dict[str, str] = {}
    with zipfile.ZipFile(src) as z:
        roots = [etree.fromstring(z.read(n)) for n in rb._sections(z)]
    tbl = rb._find_table(roots[0], ["no.", "종별", "시설명"])
    if tbl is None:
        tbl = rb._find_table(roots[0], ["종별", "시설명", "위치"])
    if tbl is not None:
        cells = rb._cells(tbl)
        heads = [rb._cell_text(cells[k]).replace(" ", "").replace("\n", "") for k in sorted(k for k in cells if k[0] == 0)]
        vals = [rb._cell_text(cells[k]).strip() for k in sorted(k for k in cells if k[0] == 1)]
        floors = f"지상{f.floors_above or 0}층/지하{f.floors_below or 0}층"
        want = {"연면적(㎡)": f"{f.total_area:,.2f}" if f.total_area else "-", "층수(지상/지하)": floors, "구조": f.structure or "-",
                "준공년도": f"{f.completion_date.year}년" if f.completion_date else "-", "종별": (f.template or "2종")[:2]}
        for h, v in zip(heads, vals):
            if h in want and v and want[h] != v and len(v) >= 2:
                rep[v] = want[h]
    for root in roots:
        for t_el in root.iter(T):
            m = re.fullmatch(r"\s*(AR\d{4}-\d{7})\s*", rb._full(t_el))
            if m and f.fms_no:
                rep[m[1]] = f.fms_no
    if f.use_type and "종교집회장" not in (f.use_type or ""):
        rep["종교집회장"] = f.use_type
    D = Data(new=new, facility=f, tv=tv, rv=rv, pr=pr, defects=defects, texts=texts, parts=ex.parts or {}, load_photos=load_photos,
             priority=_priority8(db, r, ex.ai), repairs=(r.survey or {}).get("repairs") or [], rating_png=_rating_png(db, r, rv, tv, f, co.name if co else ""),
             replace=rep, kind_label=f.template or "2종")
    D.detail = (r.survey or {}).get("detail")
    D.prior_fields = prior_status_fields(SR._prior(r))  # 이전 회차 보고서 현황표 값 — 빈 칸 채우기(10/14)
    from server.sitok import precision as PR
    base_dir = SR._report_dir(f, r)
    D.survey_pics = {k: [str(base_dir / x) if x else "" for x in v] for k, v in PR.norm((r.survey or {}).get("precision"))["survey"].items()}
    D.cost = ex.cost
    D.overview = list(ex.overview or [])
    D.blank = ex.blank
    try:
        from server.sitok import locmap
        mp = locmap.map_for(f.address, f.name, SR._facility_dir(f))
        D.map_path = str(mp) if mp else ""
    except Exception:  # noqa: BLE001 — 지도를 못 받으면 흰 그림
        D.map_path = ""
    if not D.map_path:
        D.notes.append("주소로 위치도 지도를 만들지 못해 빈 그림으로 넣었습니다")
    if not D.overview:
        D.notes.append("전경사진이 없어 위치도 아래·요약문 사진은 빈 그림입니다(현장 조사 → 전경사진)")
    return D


def defaults(db, r) -> dict:
    """AI 초안 창에 먼저 보여 줄 기본 글(precision_text) — build_body와 같은 자료로."""
    from core.models_web import SitokFacility
    from server.api.routers import sitok_precision as SP, sitok_rating as SRt, sitok_tests as ST
    from server.api.routers.sitok_defects import _defects_for_cost

    f = db.get(SitokFacility, r.facility_id)
    tv, rv, pr = ST._view(db, r), SRt._compute(db, r), SP._out(db, r)
    defects = _defects_for_cost(db, r.id)
    comp_text = f"{f.completion_date.year}년 {f.completion_date.month:02d}월 {f.completion_date.day:02d}일" if f.completion_date else "-"
    grades = {x["key"]: x["grade"] for grp in ("public", "other") for x in pr["grades"][grp]}
    t = precision_text.all_texts(defects, tv, rv["result"], grades=grades, structure=f.structure or "", load_note=pr["load"]["note"],
                                 prev_grade=rv["prev_grade"] or rv["prev_auto"], name=f.name, year=r.year, completion_text=comp_text,
                                 first=rv.get("prev_report") is None and not rv["prev_grade"], ai=None)
    return {"texts": t, "tv": tv, "rv": rv, "pr": pr, "defects": defects, "facility": f}


def build_appendix(db, r, dest: Path, D_body: Data | None = None) -> tuple[list[str], int]:
    """정밀 부록 한글 — 부록 원본(다산)에 이름·날짜·그림(자격·수료증·장비)·성과표(규격·강도·탄산화·기울기·부등침하)·과업지시서 표를 넣음.
    관리대장·사진첩·측정데이터·상태평가 결과자료·계약서 PDF는 한글 PDF 뒤에 끼움(sitok_reports._run_precision_build)."""
    from core.models_web import SitokFacility
    from server.api.routers import sitok_reports as SR

    f = db.get(SitokFacility, r.facility_id)
    src = master.master_path("정밀부록")
    if not src.exists():
        raise ValueError("정밀안전점검 부록 원본이 없습니다 — 시특법 설정에서 올리세요.")
    body_src = master.master_path("정밀본문")
    old = rb.read_old(body_src)  # 부록엔 결과표가 없어 본문 원본 값으로 바꿈
    if not old.name:
        m = re.search(r"\d{4}\s*년(?:도)?\s*(?:상반기|하반기)\s*(.+?)\s*정밀안전점검", old.title)
        old.name = m[1].strip() if m else (old.owner or "")
    if old.rep and old.rep in (old.name, old.owner):
        old.rep = ""
    if old.owner and old.owner == old.name:
        old.owner = ""
    prior = SR._prior(r)
    pv = rb.read_old(prior) if prior else None
    new, warn = SR._new_values(db, r, old, pv)
    if pv is None or not pv.title:
        new.title = f"{r.year}년 {r.half} {f.name} 정밀안전점검 용역"
    new.title = new.title.replace("정기안전점검", "정밀안전점검").replace("정기점검", "정밀점검")
    ex = SR._extras(db, r)
    ex1 = rb.Extras(images=ex.images, equipment=ex.equipment, positions=ex.positions, history=False, cost=None, template=ex.template, blank=ex.blank,
                    overview=[], has_drawings=True, parts=None, rep_photos={}, survey=None, ai=None)
    tmp = dest.with_suffix(".p1.hwpx")
    changed = rb.build(src, old, new, tmp, ex1)
    warn = [w for w in warn if "기술자 수" not in w] + ex1.notes
    D = D_body or _data_for(db, r, new, f, ex)
    added: list[tuple[str, bytes]] = []
    run = datetime.datetime.now().strftime("%y%m%d%H%M%S")

    def add_image(path_or_bytes) -> str:
        key = f"sitoka{run}_{len(added) + 1}"
        added.append((key, path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()))
        return key

    hpf = b""
    prev = D.rv["prev_grade"] or D.rv["prev_auto"]
    WORD = {"A": "우수", "B": "양호", "C": "보통", "D": "미흡", "E": "불량"}
    with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(dest.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as zout:
        ordered = rb._sections(zin)
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in ordered:
                root = etree.fromstring(data)
                if D.replace:
                    changed += rb._apply(root, D.replace, [], set(), False)
                changed += _fill_test_tables(root, D) + _fill_quantity(root, D)
                for tbl in _tables(root, ["시설명", "용도", "최초건축년도"]) + _tables(root, ["건물명", "용도", "최초건축년도"]):  # 과업지시서·사전검토 범위 표
                    cells = rb._cells(tbl)
                    heads = _head(tbl, 16)
                    vals = {"시설명": f.name, "건물명": f.name, "용도": f.use_type or f.main_use or "-", "준공년도": str(f.completion_date.year) if f.completion_date else "-",
                            "연면적(㎡)": f"{f.total_area:,.2f}" if f.total_area else "-", "층수": f"{f.floors_above or 0}/-{f.floors_below or 0}",
                            "구조": "철콘" if "철근콘크리트" in (f.structure or "") else (f.structure or "-"), "기존등급": WORD.get(prev, prev) if prev else "-"}
                    for c, h in enumerate(heads):
                        if h in vals and (1, c) in cells:
                            _set(cells, 1, c, vals[h])
                    changed += 1
                for tbl in _tables(root, ["건물명"], 2):  # 과업지시서 3. 건축물 개요
                    cells = rb._cells(tbl)
                    age = TESTS.age_years(f.completion_date, r.period_start)
                    vals = {"건물명": f.name, "위치": f.address or "-", "건축면적": f"{f.building_area:,.2f}㎡" if f.building_area else "-", "연면적": f"{f.total_area:,.2f}㎡" if f.total_area else "-",
                            "구조": f.structure or "-", "층수": f"지상{f.floors_above or 0}층 / 지하{f.floors_below or 0}층", "최초건축년도": f"{f.completion_date.year}년" if f.completion_date else "-",
                            "경과년수": f"{age}년" if age is not None else "-"}
                    for (r_, c_), tc in list(cells.items()):
                        label = rb._cell_text(tc).replace(" ", "")
                        if c_ == 0 and label in vals and (r_, 1) in cells:
                            _set(cells, r_, 1, vals[label])
                    changed += 1
                for el in list(root.iter(f"{{{HP}}}linesegarray")):
                    el.getparent().remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename == "Contents/content.hpf":
                hpf = data
                continue
            elif info.filename in ("Preview/PrvImage.png",):
                continue
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
        items = "".join(f'<opf:item id="{k}" href="BinData/{k}.jpg" media-type="image/jpg" isEmbeded="1"/>' for k, _ in added)
        zout.writestr("Contents/content.hpf", hpf.decode("utf-8").replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8"))
        for k, b in added:
            zout.writestr(f"BinData/{k}.jpg", b, compress_type=zipfile.ZIP_STORED)
    dest.with_suffix(".tmp").replace(dest)
    tmp.unlink(missing_ok=True)
    return warn + D.notes, changed
