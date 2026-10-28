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

from server.sitok.cycle import class_label
from server.sitok import condition, master, precision_text, report_build as rb, tests as TESTS
from server.sitok.borders import Borders

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
    missing_photo_note: str = ""  # 이번 회차 사진 없는 결함 안내(sitok_defects.missing_photo_note, 10/14)
    prior_hist: list = field(default_factory=list)  # 전회차 보고서 점검이력 표 줄(prior_history, 10/15)
    prior_info: dict = field(default_factory=dict)  # 전차 상태평가·결론(prior_info_for, 10/15) — 【표 5.5】
    half: str = ""  # 이번 회차 반기(상반기·하반기)


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
        _no_hang(q)
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


class _Header:
    """header.xml 고치기(10/15) — 문단 모양·글자 모양을 복사해 새 번호로: 내어쓰기 없앤 문단(글머리 없는 문장을 내어쓰기 문단에 넣으면 첫 줄만 튀어나옴),
    작은 글씨(좁은 칸). 고친 번호는 _fill이 끝에 header.xml에 붙임."""

    def __init__(self, xml: str):
        self.xml = xml
        self.add = {"paraPr": [], "charPr": []}
        self.cache: dict = {}
        self.next = {t: max([int(x) for x in re.findall(rf'<hh:{t} id="(\d+)"', xml)] or [0]) + 1 for t in ("paraPr", "charPr")}

    def _block(self, tag: str, pid) -> str:
        m = re.search(rf'<hh:{tag} id="{pid}"[\s\S]*?</hh:{tag}>', self.xml)
        return m.group(0) if m else ""

    def _clone(self, tag: str, pid, change) -> str:
        key = (tag, str(pid), change.__name__)
        if key in self.cache:
            return self.cache[key]
        blk = self._block(tag, pid)
        if not blk:
            return str(pid)
        new = str(self.next[tag])
        self.next[tag] += 1
        self.add[tag].append(change(re.sub(rf'^<hh:{tag} id="{pid}"', f'<hh:{tag} id="{new}"', blk)))
        self.cache[key] = new
        return new

    def intent(self, pid) -> int:
        m = re.search(r'<hc:intent value="(-?\d+)"', self._block("paraPr", pid))
        return int(m[1]) if m else 0

    def no_hang(self, pid) -> str:
        def no_hang(blk: str) -> str:
            return re.sub(r'(<hc:intent value=")-?\d+(")', r"\g<1>0\2", blk)
        return self._clone("paraPr", pid, no_hang)

    def centered(self, pid) -> str:
        def centered(blk: str) -> str:
            return re.sub(r'(<hh:align horizontal=")\w+(")', r"\g<1>CENTER\2", re.sub(r'(<hc:(?:intent|left|right) value=")-?\d+(")', r"\g<1>0\2", blk))
        return self._clone("paraPr", pid, centered)

    def small(self, cid) -> str:
        def small(blk: str) -> str:
            return re.sub(r'(<hh:charPr id="\d+" height=")(\d+)(")', lambda m: f"{m[1]}{max(int(m[2]) * 85 // 100, 700)}{m[3]}", blk, count=1)
        return self._clone("charPr", cid, small)

    def keep_next(self, pid) -> str:
        def keep_next(blk: str) -> str:
            return re.sub(r'keepWithNext="0"', 'keepWithNext="1"', blk, count=1)
        return self._clone("paraPr", pid, keep_next)

    def result(self) -> str:
        xml = self.xml
        for tag, group in (("paraPr", "paraProperties"), ("charPr", "charProperties")):
            if not self.add[tag]:
                continue
            xml = xml.replace(f"</hh:{group}>", "".join(self.add[tag]) + f"</hh:{group}>", 1)
            xml = re.sub(rf'(<hh:{group} itemCnt=")(\d+)(")', lambda m, n=len(self.add[tag]): f"{m[1]}{int(m[2]) + n}{m[3]}", xml, count=1)
        return xml


_HDR: _Header | None = None  # _fill 동안만(문단 모양 고치기)
BULLETS = ("ㆍ", "·", "-", "○", "￮", "※", "*", "•", "▶", "◦", "∘", "■", "□", "(", "①", "1)", "2)", "3)")


def _no_hang(p) -> None:
    """글머리 없는 문장을 넣은 문단이 내어쓰기 모양이면(첫 줄만 왼쪽으로 튀어나옴 — 사용자 10/15 "들여쓰기 때문에 줄이 안 맞음") 내어쓰기 없앤 모양으로."""
    if _HDR is None:
        return
    t = _para_text(p)
    pid = p.get("paraPrIDRef")
    if t and not t.startswith(BULLETS) and pid is not None and _HDR.intent(pid) < 0:
        p.set("paraPrIDRef", _HDR.no_hang(pid))


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
        _set(cells, *k, "없음"); n += 1  # noqa: E702
    k = right("공중이이용하는부위")
    if k:
        _set(cells, *k, "없음" if not any(g in ("d", "e") for g in (D.pr["grades"] and [x["grade"] for x in D.pr["grades"]["public"]] or [])) else "ㆍ보수가 필요한 손상 있음"); n += 1  # noqa: E702
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
    n += rb.engineer_list(root, D.new.persons)  # 참여기술자 명단도 같은 사람·줄 수(형 10/14)
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
    floors = sorted([f for f in D.rv["floors"] if not f.get("steel_part")], key=lambda f: -f["floor"])  # SRC의 강재 쪽 표본층(SafetyMan 형 방식)은 요약표에 따로 안 넣음
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


def _score_text(v) -> str:
    """(점수|None, 등급) → "1.00(A등급)" / "A등급" / "-"."""
    if not v or not v[1]:
        return "-"
    return f"{v[0]:.2f}({v[1]}등급)" if v[0] is not None else f"{v[1]}등급"


def _fill_compare(root, D: Data) -> int:
    """【표 5.5】 전차 점검 비교분석 — 항목별(상태평가·기울기 및 침하·종합평가) 전회차/이번 회차 + 점검 결론 두 칸 + 검토(형 10/15 "너무 심플 — 항목별로 나눠
    비교하고 전회차 결론과 금회차 결론 비교"). 틀은 안전등급 한 줄 → 그 줄을 복사해 4줄, 첫 열을 넓힘."""
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if (0, 2) not in cells or "정밀안전점검" not in rb._cell_text(cells[(0, 2)]) or not rb._cell_text(cells.get((1, 0), tbl)).replace(" ", "").startswith("안전"):
            continue
        t = D.texts
        pi = D.prior_info or {}
        prev = D.rv["prev_grade"] or D.rv["prev_auto"]
        if prev and not pi.get("total"):
            pi = {**pi, "total": (None, prev)}
        res = D.rv.get("result") or {}
        cur = {k: ((res.get(k) or {}).get("score"), (res.get(k) or {}).get("grade")) for k in ("condition", "deform", "total")}
        if int(tbl.get("rowCnt")) == 3:
            rb._dup_rows(tbl, 1, 1, 3)
            if _col_width(tbl, 0) < 6000:
                give = 6000 - _col_width(tbl, 0)
                _move_width(tbl, 0, 1, give // 2)
                _move_width(tbl, 0, 2, give - give // 2)
            cells = rb._cells(tbl)
        label = pi.get("label") or (f"{D.rv['prev_report']['year']}년 {D.rv['prev_report']['half']}" if D.rv.get("prev_report") else ("전차 정밀안전점검" if prev else "-"))
        _set(cells, 0, 1, label)
        _set(cells, 0, 2, f"{D.new.year}년 {D.half} 정밀안전점검".replace("  ", " "))
        rows = [(["상태평가"], pi.get("state"), cur["condition"]), (["기울기", "및 침하"], pi.get("deform"), cur["deform"]),
                (["종합평가", "(안전등급)"], pi.get("total"), cur["total"])]
        for r, (lab, pv, cv) in enumerate(rows, 1):
            _set(cells, r, 0, lab)
            _set(cells, r, 1, _score_text(pv))
            _set(cells, r, 2, _score_text(cv))
        _set(cells, 4, 0, ["점검", "결론"])
        _set(cells, 4, 1, _brief(pi.get("conclusion", ""), 110) or "-")
        _set(cells, 4, 2, _brief(t.get("conclusion", ""), 110) or "-")
        for r in range(1, 5):
            _set_row_height(tbl, r, 3300 if r >= 2 else 2400)  # 두 줄 이름 칸(기울기/및 침하) 여유
        last = max(k[0] for k in cells)
        _set(cells, last, 0, "검토")
        _set(cells, last, 1, t.get("prev_compare", ""))
        rb.pad_cells(tbl)  # 양식은 칸 여백 0 — 글이 위아래 선에 붙음(형 10/15)
        n += 1
    return n


def prior_info_for(db, r) -> dict:
    """【표 5.5】 전차 정보 — 지난 정밀 회차가 우리 프로그램 상태평가를 했으면 그 점수, 아니면 그 보고서(이미 낸 보고서 등록분 포함) 글·요약표에서(prior_rating_info).
    {"label": "2026년 상반기 정밀안전점검", "state"·"deform"·"total": (점수|None, 등급), "conclusion": 글}."""
    from server.api.routers import sitok_reports as SR
    from server.api.routers.sitok_rating import _previous_precision

    prev = _previous_precision(db, r)
    info: dict = {}
    if prev is not None:
        info["label"] = f"{prev.year}년 {prev.half} {prev.kind or '정밀'}안전점검"
        if (prev.rating or {}).get("counts"):
            try:
                from server.api.routers.sitok_rating import _compute

                pres = _compute(db, prev)["result"] or {}
                for k, key in (("state", "condition"), ("deform", "deform"), ("total", "total")):
                    if pres.get(key):
                        info[k] = (pres[key]["score"], pres[key]["grade"])
                fin = ((prev.ai or {}).get("final") or {}).get("precision") or {}
                if fin.get("conclusion"):
                    info["conclusion"] = fin["conclusion"]
            except Exception:  # noqa: BLE001 — 지난 회차가 덜 됐으면 보고서 글에서
                pass
        path = Path(prev.out_hwpx) if prev.out_hwpx and Path(prev.out_hwpx).exists() else (Path(prev.source_hwpx) if prev.source_hwpx and Path(prev.source_hwpx).exists() else None)
    else:
        path = SR._prior(r)
    got = prior_rating_info(path)
    for k, v in got.items():
        info.setdefault(k, v)
    return info


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
        "용도": f.use_type or f.main_use or "-", "시설물규모": D.new.scale, "구조형식": f.structure or "-", "종별": f"{class_label(f)}시설물",
        "전차안전등급": (WORD.get(prev, prev) if prev else "-"), "점검결과안전등급": f"{t['grade_letter']}등급" if t.get("grade_letter") else "-",
        "건축연면적": f"{f.total_area:,.2f}㎡" if f.total_area else "-", "건축면적": f"{f.building_area:,.2f}㎡" if f.building_area else "-",
        "층수": f"지하{f.floors_below or 0}층/지상{f.floors_above or 0}층", "최고높이": f"{f.max_height:g}m" if f.max_height else "-", "주용도": f.main_use or f.use_type or "-",
        "사용승인일": f.completion_date.strftime("%Y.%m.%d") if f.completion_date else "-", "준공후경과년수": f"약 {age}년 경과" if age is not None else "-",
    }
    if (f.ledger or {}).get("land_area"):  # 시설 카드 대지면적(10/15 — SafetyMan 건물개요와 같은 값)
        values["대지면적"] = f"{f.ledger['land_area']:,.2f}㎡"
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
    vals = [class_label(f), f.name or "-", f.address or "-", f"{f.total_area:,.2f}" if f.total_area else "-",
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
                if D.rating_png:
                    tops[i - 1].set("pageBreak", "1")  # 그림이 커서 2.3 표 아래 안 들어가면 제목만 남고 그림만 넘어감 → 2.4는 새 쪽에서(형 10/14 "아예 넘겨")
                if _put_rating_pic(pics[0], D, add_image, tbl):
                    n += 1
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
    from server.sitok import precision as PR

    cells = rb._cells(tbl)
    for r, g in zip(range(1, 4), PR.doc_groups(D.pr["docs"])):  # 부록 4.2와 같은 목록(10/15)
        _set(cells, r, 1, g["items"])
        _set(cells, r, 2, g["status"])
        _set(cells, r, 3, g["detail"])
    _rows_to_text(tbl)
    if sum(rb._table_row_heights(tbl).values()) > rb.BODY_H - 4000:
        rb._splittable(tbl, 1)  # 목록이 길어 한 쪽을 넘으면 줄 단위로
    else:  # 한 쪽 안이면 틀대로 통째로(나누지 않음) — 쪽 끝에서 나뉘어 마지막 한 줄만 다음 쪽에 가던 것(형 10/15), 제목·표 번호도 같이 넘어감
        _keep_with_table(tbl)
    return 1


def _rows_to_text(tbl, first: int = 1) -> None:
    """줄 높이를 글 줄 수 어림에 맞춤(틀 높이가 고정이라 글이 늘면 아래 선에 걸림 — 10/15 표 2.1). 양식 줄 높이는 바닥으로 안 씀(복사한 짧은 줄이 커지던 것),
    칸 위아래 여백 0.5mm(글이 선에 붙지 않게) + 반 줄 여유(한 줄 여유는 빈 칸이 커져 표가 쪽을 넘김 — 형 10/15 "조절이 필요함")."""
    rb.pad_cells(tbl, lr=None, tb=141)
    for r, h in rb._table_row_heights(tbl, text_only=True).items():
        if r >= first:
            _set_row_height(tbl, r, h + rb.LINE_H // 2)


def _keep_with_table(tbl, n: int = 2) -> None:
    """표 앞 문단(제목·【표 N】) n개를 표와 같은 쪽에(다음 문단과 함께) — 표가 통째로 다음 쪽으로 갈 때 제목만 남지 않게."""
    p = tbl
    while p is not None and not (p.tag == f"{{{HP}}}p" and p.getparent() is not None and p.getparent().tag.endswith("}sec")):
        p = p.getparent()
    if p is None or _HDR is None:
        return
    q = p.getprevious()
    while q is not None and n > 0:
        if q.tag == f"{{{HP}}}p" and q.get("paraPrIDRef") is not None:
            q.set("paraPrIDRef", _HDR.keep_next(q.get("paraPrIDRef")))
            if _para_text(q).strip():
                n -= 1
        q = q.getprevious()


def _fill_docs_appendix(root, D: Data) -> int:
    """부록 사전검토보고서 4.2 유지관리자료 보유 현황 표 — 본문 표 2.1과 같은 3묶음 목록으로 줄을 다시 짬(시공관련자료 줄을 본으로, 사용자 10/15)."""
    from server.sitok import precision as PR

    tbl = rb._find_table(root, ["보존대상목록", "관리주체보유현황", "비고"])
    if tbl is None:
        return 0
    cells = rb._cells(tbl)
    keep = next((r for (r, c), tc in cells.items() if c == 0 and re.sub(r"\s", "", rb._cell_text(tc)) == "시공관련자료"), None)
    if keep is None:
        return 0
    n = int(tbl.get("rowCnt"))
    if keep + 1 < n:
        rb._del_rows(tbl, keep + 1, n - keep - 1)
    if keep > 1:
        rb._del_rows(tbl, 1, keep - 1)
    rb._dup_rows(tbl, 1, 1, 2)
    cells = rb._cells(tbl)
    for r, g in zip(range(1, 4), PR.doc_groups(D.pr["docs"])):
        _set(cells, r, 0, g["group"])
        _set(cells, r, 1, g["items"])
        _set(cells, r, 2, [f"◦ {g['status']}"] + [x for x in g["detail"] if x != "-"])
        _set(cells, r, 3, "-")
    _rows_to_text(tbl)
    rb._splittable(tbl, 1)
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
    hist = D.pr["history"] or merged_history(D.pr["history_auto"], D.prior_hist)  # FMS 엑셀을 올렸으면 그것, 아니면 우리 회차 + 전회차 보고서 이력 표 전부(형 10/15)
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
    if len(hist) > 6:
        rb._splittable(tbl, 1)  # 이력이 길면 쪽을 넘어 나뉘게(머리줄 반복)
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

        c0 = rb._cells(tbl)
        r1 = next((r for (r, c) in sorted(c0) if c == 1 and rb._cell_text(c0[(r, c)]).strip().startswith("□")), None)
        wide = r1 is not None and all(int(c0[(r1, c)].find(f"{{{HP}}}cellSz").get("width") or 0) > 3800 for c in (3, 5) if (r1, c) in c0)
        if wide and (r1, 3) in c0 and (r1, 5) in c0:  # ■ 하나 들어가는 없다·있다 칸(2칸 합침) 폭을 유형·비고 칸으로(형 10/15 "글자 어떻게 좀")
            _move_width(tbl, 9, 3, 550)  # 유형 +1,100 — 없다·있다 머리칸 "(양호)"가 안 꺾일 만큼만
            _move_width(tbl, 9, 5, 550)
            _move_width(tbl, 11, 1, 600)  # 비고 +600 — 넓은 점검내용 칸에서
            rb.pad_cells(tbl, lr=283, tb=141)  # 양식 좌우 여백 1.8mm → 1mm(좁은 칸 글 자리)
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
            types = [ln for t_ in (a["types"][:2] if a else []) for ln in (re.sub(r"·(?=.)", "·|", t_).split("|") if len(t_) > 4 and "·" in t_ else [t_])]
            _set(cells, r, 9, types or "")  # 종류마다 한 줄, 긴 이름은 "·" 뒤에서(좁은 칸에 "박리·재료분리"·"누수·백태"가 글자마다 꺾이던 것, 형 10/15)
            if (r, 11) in cells:
                where = [w for w in (a["where"].split(", ") if a else []) if w]
                note = (where[:2] + ([f"외 {len(where) - 2}곳"] if len(where) > 2 else [])) if a else (m["note"] if bad and not note_done else "")
                _set(cells, r, 11, note)
                if bad and m["note"] and not a:
                    note_done = True
            # ■는 "없다(양호)" 칸처럼 가운데(형 10/15), 유형·비고 글은 작게(좁은 칸에 빽빽 — 형 10/15)
            mark_p = next(cells[(r, 3)].iter(f"{{{HP}}}p"), None) if (r, 3) in cells else None
            for c in (5, 7):
                if (r, c) in cells and mark_p is not None:
                    for q in cells[(r, c)].iter(f"{{{HP}}}p"):
                        q.set("paraPrIDRef", _HDR.centered(mark_p.get("paraPrIDRef")) if _HDR is not None else mark_p.get("paraPrIDRef"))
            if _HDR is not None:
                for c in (9, 11):
                    for run in (cells[(r, c)].iter(f"{{{HP}}}run") if (r, c) in cells else []):
                        run.set("charPrIDRef", _HDR.small(run.get("charPrIDRef") or "0"))
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
        return d.photo if d.photo and Path(d.photo).exists() else ""  # 이번 회차 사진만(사용자 10/14 — 전회차가 섞이면 안 찍은 걸 못 잡음)
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
    if D.missing_photo_note and D.missing_photo_note not in D.notes:
        D.notes.append(D.missing_photo_note)
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
    if tbl is not None and int(tbl.get("rowCnt")) >= 6:  # 틀은 6칸(옹벽·절토사면까지) — 공중이용 탭 4항목에 맞춰 마지막 줄(사진·설명 2줄) 빼기(형 10/14)
        rb._del_rows(tbl, 4, 2)
    _other_like_public(root)  # 3.2.8 기타시설을 3.2.7과 같은 양식으로(10/15)
    for cap, key, none_text in (("【사진 3.10】", "public", "해당없음"), ("【사진 3.11】", "other", "해당없음")):
        tbl = _table_after(root, cap)
        if tbl is None:
            continue
        slots = _slots(tbl)
        cells = rb._cells(tbl)
        if slots:  # 다산 틀 둘째 사진 칸의 대각선(X) 테두리 — 사진을 넣으면 사진 위에 X가 겹침 → 첫 사진 칸 테두리로
            bf = cells[slots[0][0]].get("borderFillIDRef")
            for pk, _ in slots:
                if bf:
                    cells[pk].set("borderFillIDRef", bf)
        items = list(D.parts.get(key) or [])[:len(slots)]
        for i, (pk, ck) in enumerate(slots):
            name, path = items[i] if i < len(items) else ("-", None)
            image = None
            if path and Path(path).exists():
                pic = _pic_or(cells[pk], tpl)
                sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
                w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
                image = rb._cropped(path, w, h)
            rb._slot_put(cells[pk], cells[ck] if ck else None, image, none_text, name, tpl, add_image)
        n += 1
    n += _fill_analysis_tables(root, D)
    return n


def _other_like_public(root) -> bool:
    """3.2.8 기타시설만 다산 원본 양식이 달랐음("3.2.8) 기타시설" 다른 글꼴 제목 + "■ 기타시설 사진 현황:" 머리 표 — 사용자 10/15 "얘 혼자 양식이 다름") →
    3.2.7 공중이용과 같게: 제목 문단 모양("3.2.8 기타시설 조사결과"), 본문 문단 모양, 캡션 【사진 3.11】기타시설 손상사진, 사진 표는 【사진 3.10】 표 복사(2×2)."""
    from server.sitok import merge as M

    tops = _tops(root)
    i7 = next((i for i, p in enumerate(tops) if re.match(r"^3\.2\.7\s", _para_text(p))), None)
    i8 = next((i for i, p in enumerate(tops) if re.match(r"^3\.2\.8", _para_text(p))), None)
    if i7 is None or i8 is None or i8 < i7:
        return False
    cap7 = next((q for q in tops[i7 + 1:i8] if _para_text(q).startswith("【사진")), None)
    tbl7 = next((q for q in tops[i7 + 1:i8] if _has_tbl(q)), None)
    body7 = next((q for q in tops[i7 + 1:i8] if _para_text(q) and not _para_text(q).startswith("【")), None)
    end8 = next((k for k in range(i8 + 1, len(tops)) if HEAD_RE.match(_para_text(tops[k])) and not _para_text(tops[k]).startswith("■")), len(tops))
    old = next((q for q in tops[i8 + 1:end8] if _has_tbl(q)), None)
    if cap7 is None or tbl7 is None or old is None:
        return False
    head = tops[i8]
    new_head = copy.deepcopy(tops[i7])
    M._renew_ids(new_head)
    rb._set_para(new_head, "3.2.8 기타시설 조사결과")
    new_head.set("pageBreak", head.get("pageBreak") or "0")
    head.addprevious(new_head)
    root.remove(head)
    for q in tops[i8 + 1:end8]:
        if q is not old and _para_text(q) and body7 is not None:
            q.set("paraPrIDRef", body7.get("paraPrIDRef"))
            q.set("styleIDRef", body7.get("styleIDRef"))
    new_cap = copy.deepcopy(cap7)
    rb._set_para(new_cap, "【사진 3.11】기타시설 손상사진")
    new_tbl = copy.deepcopy(tbl7)
    M._renew_ids(new_tbl)
    old.addprevious(new_cap)
    old.addprevious(new_tbl)
    root.remove(old)
    return True


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
            _set_row_height(tbl, r, 2400)  # 줄 높이는 글만큼(틀 높이가 남으면 쪽 끝에서 나뉠 때 빈 줄만 다음 쪽에 찍힘, 10/15)
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
    need = tv["sample"]["need"] or 0
    q = tv["sample"]["quantity"]
    for tbl in _tables(root, ["층수", "수량기준", "연면적(㎡)"]):
        _fill_sample_tbl(tbl, tv, f)
        n += 1
    for tbl in _tables(root, ["구분", "세부지침기준", "금회수량"]):
        if int(tbl.get("rowCnt")) >= 7:
            _fill_qty_tbl(tbl, tv)
            n += 1
    for cap, key in (("【표 4.3】", "section"), ("【표 4.5】", "strength"), ("【표 4.7】", "carbonation"), ("【표 4.9】", "tilt"), ("【표 4.11】", "settlement")):
        tbl = _table_after(root, cap)
        if tbl is None or int(tbl.get("rowCnt")) != 3:
            continue
        cells = rb._cells(tbl)
        row = _row_cells(cells, 2)
        if len(row) >= 2:
            rb._set_lines(row[-2], [str(q[key]["need"])]); rb._set_lines(row[-1], [str(q[key]["have"] or "-")])  # noqa: E702
        if key in ("section", "strength", "carbonation"):  # 기준 칸 = "표본층"이 든 칸(틀 3줄 표는 (2,1) — (2,2)는 "2부재" 칸이라 거기 쓰면 좁은 칸에 눌리고 틀 글이 남음, 형 10/15)
            k = next((k for k in sorted(cells) if k[0] == 2 and "표본층" in rb._cell_text(cells[k])), None)
            if k is not None:
                _set(cells, *k, ["￮ 표본층(단위)수", f"({need}개 단위 산정)"])
        n += 1
    return n


def _fill_sample_tbl(tbl, tv: dict, f) -> None:
    """표본층 기준 표(층수 | 수량기준 | 연면적 | 수량기준 | 해당여부 | 금회수량) — √ 줄만 굵게, 나머지는 보통 글씨(형 10/15 "체크된 항이 굵은 글씨")."""
    cells = rb._cells(tbl)
    total_floors = (f.floors_above or 0) + (f.floors_below or 0)
    need = tv["sample"]["need"] or 0
    pick = 4 if total_floors <= 10 else 3 if total_floors <= 20 else 2
    for r in (2, 3, 4):
        _set(cells, r, 4, "√" if r == pick else "")
    _set(cells, 2, 5, ["￮ 층수", f"  - 지상{f.floors_above or 0}층, 지하{f.floors_below or 0}층({total_floors}개층)", "￮ 연면적", f"  - {f.total_area or 0:,.2f}㎡",
                       "￮ 층수별·연면적별 최대치", f"  - {need}개층, {need}개 단위 산정"])
    first = {}
    for r in (2, 3, 4):  # 틀은 한 줄(다산 1~10층)만 굵은 글자 모양 — 세 줄 첫 칸 글자 모양 중 하나만 다른 것이 굵은 것
        run = next(cells[(r, 0)].iter(f"{{{HP}}}run"), None) if (r, 0) in cells else None
        first[r] = run.get("charPrIDRef") if run is not None else None
    ids = [v for v in first.values() if v]
    bold = next((v for v in ids if ids.count(v) == 1), None) if len(set(ids)) == 2 else None
    normal = next((v for v in ids if v != bold), None)
    if bold is None or normal is None:
        return
    for (r, c), tc in cells.items():
        if r in (2, 3, 4) and c <= 3:
            for run in tc.iter(f"{{{HP}}}run"):
                run.set("charPrIDRef", bold if r == pick else normal)


def _fill_qty_tbl(tbl, tv: dict) -> None:
    """재료시험 산출수량 7줄 표(압축강도·규격·탄산화·기울기·부등침하)."""
    cells = rb._cells(tbl)
    need = tv["sample"]["need"] or 0
    q = tv["sample"]["quantity"]
    _set(cells, 2, 2, ["￮ 표본층(단위)수", f"({need}개 단위 산정)"])
    for r, key in ((2, "strength"), (3, "section"), (4, "carbonation"), (5, "tilt"), (6, "settlement")):
        _set(cells, r, 5, q[key]["need"]); _set(cells, r, 6, q[key]["have"] or "-")  # noqa: E702


def _col_width(tbl, col: int) -> int:
    for tc in rb._cells(tbl).values():
        a, s = tc.find(f"{{{HP}}}cellAddr"), tc.find(f"{{{HP}}}cellSpan")
        if int(a.get("colAddr")) == col and int(s.get("colSpan") or 1) == 1:
            return int(tc.find(f"{{{HP}}}cellSz").get("width") or 0)
    return 0


def _move_width(tbl, to_col: int, from_col: int, d: int) -> None:
    """열 너비 옮기기(표 전체 너비는 그대로) — 그 열에 걸친 칸(합친 머리칸 포함) 너비를 같이."""
    if d <= 0:
        return
    for tc in rb._cells(tbl).values():
        a, s = tc.find(f"{{{HP}}}cellAddr"), tc.find(f"{{{HP}}}cellSpan")
        c0, span = int(a.get("colAddr")), int(s.get("colSpan") or 1)
        sz = tc.find(f"{{{HP}}}cellSz")
        w = int(sz.get("width") or 0)
        if c0 <= to_col < c0 + span:
            w += d
        if c0 <= from_col < c0 + span:
            w -= d
        sz.set("width", str(w))


POSITION_W = 8800  # 부재규격 표 "위치" 둘째 칸("장비위치도 참조"가 한 줄에 — 형 10/15 "글씨가 너무 타이트")


def _fill_section_tbl(tbl, D: Data) -> None:
    secs = D.tv["sections"]
    w2 = _col_width(tbl, 2)
    if 0 < w2 < POSITION_W:  # 조사결과(5)·설계도면(4) 열에서 나눠 받음
        need = POSITION_W - w2
        give5 = min(need, max(_col_width(tbl, 5) - 7000, 0))
        _move_width(tbl, 2, 5, give5)
        _move_width(tbl, 2, 4, min(need - give5, max(_col_width(tbl, 4) - 7000, 0)))
    k = _fit_rows(tbl, len(secs), 1)
    cells = rb._cells(tbl)
    for i in range(k):
        s = secs[i] if i < len(secs) else None
        vals = [f"B{i + 1}", TESTS.floor_label(s["floor"]) if s and s["floor"] else "-", s["position"] or "-", s["member"] or "-", s["design"] or "-", s["measured"] or "-",
                ("O.K" if s["ok"] else "N.G") if s and s["ok"] is not None else "-"] if s else ["-"] * 7
        for tc, v in zip(_row_cells(cells, i + 1), vals):
            rb._set_lines(tc, [v])
        _set_row_height(tbl, i + 1, 1700)


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
    # 상태평가 결과 그림(【그림 5.1】 뒤 문단 그림·7.3 뒤 1×1 표 안 그림) — SafetyMan 갑지 윗부분, 그림 틀을 그림 비율로(형 10/15 "세이프티맨 갑지" — 틀 안에서 치우치고 잘렸음)
    tops = _tops(root)
    for i, p in enumerate(tops):
        tx = _para_text(p)
        if tx.startswith("【그림 5.1】") or tx.startswith("7.3 상태평가 결과"):
            for q in tops[i + 1:i + 4]:
                pic = next(q.iter(f"{{{HP}}}pic"), None)
                if pic is None:
                    continue
                holder = next(pic.iterancestors(f"{{{HP}}}tbl"), None)
                if _put_rating_pic(pic, D, add_image, holder):
                    n += 1
                break
    return n


def _put_rating_pic(pic, D: Data, add_image, holder=None) -> bool:
    """상태평가 결과 그림(D.rating_png = 갑지 윗부분)을 그림 틀에 — 너비는 틀 그대로, 높이는 그림 비율대로, 픽셀은 틀 크기(우리 한글은 96dpi 원래 크기로 그림),
    옛 사진의 자르기·배율 속성은 새로(_reset_pic). holder = 그림이 든 1×1 표(칸·표 높이도 맞춤). 그림이 없으면 흰 그림."""
    img = next(pic.iter(f"{{{CORE}}}img"), None)
    if img is None:
        return False
    if not D.rating_png:
        if D.blank:
            img.set("binaryItemIDRef", add_image(D.blank))
        return False
    sz = pic.find(f"{{{HP}}}curSz")
    jpg, ratio = _rating_crop(D.rating_png, 1.0)
    w = int(sz.get("width")) if sz is not None and int(sz.get("width") or 0) > 0 else 46000
    if holder is not None:  # 표 칸 안이면 칸 너비 안에
        tc = next(pic.iterancestors(f"{{{HP}}}tc"), None)
        cw = int(tc.find(f"{{{HP}}}cellSz").get("width") or 0) if tc is not None else 0
        if cw:
            w = min(w, cw - 1200) if w > cw - 1200 else w
    h = int(w / ratio)
    if h > rb.BODY_H - 7000:  # 평가결과 묶음이 많아 그림이 길면(숭의 본관 4묶음) 제목과 한 쪽에 들어가게 줄임 — 넘치면 제목만 남고 그림 다음 쪽 + 빈 쪽(10/15)
        h = rb.BODY_H - 7000
        w = int(h * ratio)
    _reset_pic(pic, w, h)
    img.set("binaryItemIDRef", add_image(_px_for_frame(jpg, w, h)))
    if holder is not None:
        for tc in holder.iter(f"{{{HP}}}tc"):
            csz = tc.find(f"{{{HP}}}cellSz")
            if csz is not None:
                csz.set("height", str(h + 800))
        tsz = holder.find(f"{{{HP}}}sz")
        if tsz is not None:
            tsz.set("height", str(h + 800))
    return True


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


def _maint_photos(D: Data, part: str, n: int = 3) -> list:
    """6.2 유지관리방안 대표 사진 — 이번 회차 사진이 있는 결함에서 ★ → 진행·신규 → 물량 큰 순, 결함유형이 겹치지 않게 먼저. [(경로, "부재 결함유형")]."""
    from server.api.routers.sitok_defects import _num

    ds = [d for d in D.defects if d.part == part and d.photo and Path(d.photo).exists()]
    ds.sort(key=lambda d: (not d.starred, d.check not in ("grew", "new"), -(_num(d.qty) or 0)))
    out, seen = [], set()
    for d in ds:
        key = (d.member, (d.dtype or "").replace(" ", ""))
        if key not in seen:
            seen.add(key)
            out.append((d.photo, f"{d.member} {d.dtype}".strip()))
        if len(out) >= n:
            return out
    for d in ds:
        if len(out) >= n:
            break
        if (d.photo, f"{d.member} {d.dtype}".strip()) not in out:
            out.append((d.photo, f"{d.member} {d.dtype}".strip()))
    return out


def _fill_maint(root, D: Data, tpl, add_image) -> int:
    """【표 6.2】 부재별 유지관리방안(구조체·비구조체·공중이 이용하는 부위 — 사진 3칸·설명·관리 글) — 이번 회차 대표 사진 3장씩(없으면 흰 그림 "-"),
    글은 precision_text maint_*(AI 초안이 덮어씀). 형 10/15 "금회차 사진 안 찍었으면 비어져야 함" — 원본(다산) 사진·글이 남아 있던 것."""
    tbl = next((t for t in root.iter(f"{{{HP}}}tbl") if rb._cell_text(rb._cells(t).get((0, 0), t)).replace(" ", "") == "부재별유지관리방안"), None)
    if tbl is None:
        return 0
    cells = rb._cells(tbl)
    blocks = sorted((r, rb._cell_text(tc).replace(" ", "").replace("\n", "")) for (r, c), tc in cells.items() if c == 0 and r >= 1)
    n = 0
    for r0, label in blocks:
        if "구조체" in label and "비구조체" not in label:
            key, photos = "maint_struct", _maint_photos(D, "구조체")
        elif "비구조체" in label:
            key, photos = "maint_nonstruct", _maint_photos(D, "비구조체")
        elif "공중" in label:
            key, photos = "maint_public", [(p, nm) for nm, p in (D.parts.get("public") or []) if p and Path(p).exists()][:3]
        else:
            continue
        pics = sorted(c for (r, c) in cells if r == r0 and c >= 1)
        caps = sorted(c for (r, c) in cells if r == r0 + 1 and c >= 1)
        for i, c in enumerate(pics):
            path, cap = photos[i] if i < len(photos) else (D.blank, "-")
            image = None
            if path and Path(path).exists():
                pic = _pic_or(cells[(r0, c)], tpl)
                sz = pic.find(f"{{{HP}}}curSz") if pic is not None else None
                w, h = (int(sz.get("width")), int(sz.get("height"))) if sz is not None and int(sz.get("width") or 0) > 0 else (4, 3)
                image = rb._cropped(path, w, h)
            cap_tc = cells.get((r0 + 1, caps[i])) if i < len(caps) else None
            rb._slot_put(cells[(r0, c)], cap_tc, image, "-", cap, tpl, add_image)
        lines = [x.strip() for x in D.texts.get(key, "").split("ㆍ") if x.strip()]  # 줄 구분은 ㆍ만("누수·백태"의 가운뎃점은 글)
        txt = next((c for (r, c) in sorted(cells) if r == r0 + 2 and c >= 1), None)
        if txt is not None and lines:
            _set(cells, r0 + 2, txt, [f"ㆍ{x}" for x in lines])
        n += 1
    return n


def prior_rating_info(hwpx: Path | None) -> dict:
    """전회차 보고서(hwpx)에서 상태평가 결과 — {"state"|"deform"|"total": (점수|None, 등급), "conclusion": 종합결론 첫 문단}.
    우리 보고서는 5.2 문장 "상태평가 1.00(A), 기울기 및 침하 5.00(C), 종합 3.80(B)"에서 점수까지, 아니면 요약표(종합평가 결과 : B · 변위 평가결과 · 부재별 등급 중 가장 낮은 것)."""
    out: dict = {}
    if not hwpx or not Path(hwpx).exists():
        return out
    try:
        with zipfile.ZipFile(hwpx) as z:
            roots = [etree.fromstring(z.read(n)) for n in rb._sections(z)]
    except Exception:  # noqa: BLE001
        return out
    texts = [rb._top_text(p).strip() for root in roots for p in root if p.tag == f"{{{HP}}}p"]
    for t in texts:
        m = re.search(r"상태평가\s*([\d.]+)\s*\(([A-E])\)\s*,\s*기울기\s*및\s*침하\s*([\d.]+)\s*\(([A-E])\)\s*,\s*종합\s*([\d.]+)\s*점?\s*\(([A-E])\)", t)
        if m:
            out = {"state": (float(m[1]), m[2]), "deform": (float(m[3]), m[4]), "total": (float(m[5]), m[6])}
            break
    if not out:
        for tbl in roots[0].iter(f"{{{HP}}}tbl"):
            cells = rb._cells(tbl)
            if not rb._cell_text(cells.get((0, 0), tbl)).replace(" ", "").startswith("책임기술자종합의견"):
                continue
            grades = []
            for (r, c), tc in cells.items():
                t = re.sub(r"\s", "", rb._cell_text(tc))
                m = re.match(r"종합평가결과:([A-E])", t)
                if m:
                    out["total"] = (None, m[1])
                if t.startswith("변위") and "평가결과" in t:
                    g = re.sub(r"\s", "", rb._cell_text(cells.get((r, 9), tbl)))
                    if re.fullmatch(r"[A-E]", g):
                        out["deform"] = (None, g)
                if c == 3 and re.fullmatch(r"[A-E]", t):
                    grades.append(t)
            if grades:
                out["state"] = (None, max(grades))
            break
    for i, t in enumerate(texts):  # 7.5 종합결론 첫 문단
        if re.match(r"^7\.5\s*종합결론$", t):
            nxt = next((x for x in texts[i + 1:i + 4] if len(x) > 20), "")
            if nxt:
                out["conclusion"] = nxt
            break
    return out


def prior_history(hwpx: Path | None) -> list[dict]:
    """전회차 보고서의 점검이력 표(번호 | 점검명 | 점검기간(시작·끝) | 점검기관 | 안전등급 | 주요점검 결과) 줄들 — 준공부터의 이력이 다 들어 있음(형 10/15 "17번 했으면 17번 전부")."""
    if not hwpx or not Path(hwpx).exists():
        return []
    try:
        with zipfile.ZipFile(hwpx) as z:
            roots = [etree.fromstring(z.read(n)) for n in rb._sections(z)]
    except Exception:  # noqa: BLE001
        return []
    for root in roots:
        tbl = rb._find_table(root, ["번호", "점검명", "점검기간"])
        if tbl is None:
            continue
        cells = rb._cells(tbl)
        out = []
        for r in sorted({k[0] for k in cells}):
            if r == 0:
                continue
            g = lambda c: " ".join(rb._cell_text(cells[(r, c)]).split()) if (r, c) in cells else ""  # noqa: E731
            if not g(1) and not g(2):
                continue
            result = "\n".join(x.strip() for x in rb._cell_text(cells[(r, 6)]).split("\n") if x.strip()) if (r, 6) in cells else ""
            out.append({"kind": g(1), "start": g(2), "end": g(3), "org": g(4), "grade": g(5), "result": result})
        return [h for h in out if h["kind"] not in ("-", "") or h["start"] not in ("-", "")]
    return []


GRADE_WORD = {"A": "우수", "B": "양호", "C": "보통", "D": "미흡", "E": "불량"}


def merged_history(auto: list[dict], prior: list[dict]) -> list[dict]:
    """점검이력 = 우리 지난 회차(자동) + 전회차 보고서 이력 표(시작일이 같은 건 우리 것) — 최근부터. 등급 글은 전회차 표 모양(양호/B)에 맞춤."""
    def day(s: str) -> str:
        m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s or "")
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else (s or "")

    seen = {day(h.get("start", "")) for h in auto if h.get("start")}
    rows = list(auto) + [h for h in prior if day(h.get("start", "")) not in seen]
    words = sum(1 for h in prior if h.get("grade") in GRADE_WORD.values())
    if words > len(prior) / 2:
        rows = [{**h, "grade": GRADE_WORD.get(h.get("grade") or "", h.get("grade") or "")} for h in rows]
    rows.sort(key=lambda h: day(h.get("start", "")), reverse=True)
    return rows


FILL_TAGS = ("tbl", "pic", "ctrl", "rect", "line", "ellipse", "container", "secPr", "colPr", "header", "footer", "equation", "textart", "ole", "chart", "polygon", "curve", "arc")


def _blank_para(p) -> bool:
    """글도 개체(표·그림·글상자·구역 설정 등)도 없는 빈 문단."""
    if _para_text(p):
        return False
    return not any(el.tag.rsplit("}", 1)[-1] in FILL_TAGS for el in p.iter())


def _chapter_breaks(root) -> int:
    """시설물편 장 간지(머리 띠 표 1×2 + "제N장")는 늘 새 쪽에서 — 원본은 앞 장 끝의 빈 문단 몇 개로 밀어 간지를 다음 쪽에 놓아서, 앞 표가 길어져
    다음 쪽으로 넘치면 간지가 그 쪽에 같이 찍힘(사용자 10/15 "표가 다음 페이지로 가면서 제목이 나와야 하는 페이지를 침범"). 간지 첫 문단에 쪽 나눔 + 앞 빈 문단 지움."""
    n = 0
    tops = _tops(root)
    for i, p in enumerate(tops):
        tbl = next((t for t in p.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None), None)
        if tbl is None or tbl.get("rowCnt") != "1" or tbl.get("colCnt") != "2":
            continue
        sz = tbl.find(f"{{{HP}}}sz")
        if sz is None or int(sz.get("height") or 0) > 3000:
            continue
        if not any(re.fullmatch(r"제\s*\d+\s*장", _para_text(q).replace(" ", "")) for q in tops[i + 1:i + 7]):
            continue
        k = i - 1
        while k >= 0 and _blank_para(tops[k]) and tops[k].get("pageBreak") != "1":
            k -= 1
        if k >= 0 and tops[k].get("pageBreak") == "1" and not _para_text(tops[k]) and not _has_tbl(tops[k]):
            continue  # 바로 앞 빈 문단(쪽 숨김 등 개체만)이 이미 새 쪽 — 1장 간지(쪽 나눔을 또 걸면 빈 쪽)
        if p.get("pageBreak") != "1":
            p.set("pageBreak", "1")
            n += 1
        k = i - 1
        while k >= 0 and _blank_para(tops[k]) and tops[k].get("pageBreak") != "1":
            root.remove(tops[k])
            k -= 1
    return n


def _cost_inline(root) -> int:
    """개략공사비 표(6.1)를 한 쪽에 들어가면 통째로(글자처럼 취급) — 자리 차지 표가 쪽을 넘어 나뉘면 표 아래 ※ 주석이 표 위에 겹쳐 찍힘(형 10/15)."""
    tbl = rb._find_table(root, ["구분", "결함및손상,열화내용", "보수ㆍ보강방안"])
    if tbl is None:
        tbl = rb._find_table(root, ["구분", "결함및손상,열화내용", "보수·보강방안"])
    if tbl is None or rb._est_height(tbl) > rb.BODY_H * 0.8:
        return 0
    pos = tbl.find(f"{{{HP}}}pos")
    n = 0
    if pos is not None and pos.get("treatAsChar") != "1":
        pos.set("treatAsChar", "1")
        tbl.set("pageBreak", "NONE")
        n = 1
    holder = next((p for p in tbl.iterancestors(f"{{{HP}}}p") if p.getparent() is root), None)
    if holder is not None and _HDR is not None:  # 표 + 아래 ※ 주석을 한 덩어리로(다음 문단과 함께 — 주석 한 줄만 다음 쪽에 가던 것, 형 10/15)
        tops = _tops(root)
        i = tops.index(holder)
        notes = []
        for q in tops[i + 1:i + 9]:
            t = _para_text(q)
            if q.get("pageBreak") == "1" or not (t.startswith(("※", "·", "ㆍ", "-")) or re.match(r"^\d\.\s", t)):
                break
            notes.append(q)
        for q in [holder] + notes[:-1]:
            q.set("paraPrIDRef", _HDR.keep_next(q.get("paraPrIDRef")))
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

    global _HDR
    changed = 0
    hpf = b""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as zout:
        ordered = rb._sections(zin)
        _HDR = _Header(zin.read("Contents/header.xml").decode("utf-8"))
        hdr_info = None
        with rb.using_borders(Borders(_HDR.xml)) as bd:  # 줄 복사한 표의 맞닿는 선을 얇게(형 10/15)
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "Contents/header.xml":  # 문단·글자 모양을 더할 수 있게 맨 끝에 씀
                    hdr_info = info
                    continue
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
                            if rb.split_findings_row(root, tbl, RESULT_EST_FIT):  # "점검 주요결과"가 쪽을 넘으면 앞 쪽 몫 + (계속) 줄로(형 10/14 — 칸 안에서 잘리면 테두리 끊김)
                                changed += 1
                            elif _split_result_table(root, tbl):  # 그래도 넘칠 것 같으면 '다.'부터 새 쪽
                                changed += 1
                        if D.result_fields:
                            changed += rb._set_result_fields(root, D.result_fields)
                        if D.cost is not None and rb._cost_table(root, D.cost[0], D.cost[1]):  # 요약문 2.7 개략공사비
                            changed += 1 + _cost_inline(root)  # 표 + ※ 주석 한 덩어리(10/15)
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
                                    + _fill_ch5_7(root, D, add_image) + _fill_maint(root, D, tpl, add_image) + _cost_inline(root) + _chapter_breaks(root))
                    for el in list(root.iter(f"{{{HP}}}linesegarray")):
                        el.getparent().remove(el)
                    rb.fit_added_pics([root], added)  # 200dpi 사진 — 그림 전체가 칸에 보이게(10/28)
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                elif info.filename == "Contents/content.hpf":
                    hpf = data
                    continue
                elif info.filename in ("Preview/PrvImage.png",):
                    continue
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
        if hdr_info is not None:
            zout.writestr(hdr_info, bd.result(_HDR.result()).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        _HDR = None
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

    from server.api.routers.sitok_reports import rating_result_pdf

    dest = rating_result_pdf(db, r, facility, rv, tv)
    doc = pymupdf.open(dest)
    page = doc[0]
    rect = page.rect
    hit = page.search_for("입력자료")
    limit = hit[0].y0 - 2 if hit else rect.y1
    boxes = [pymupdf.Rect(b[:4]) for b in page.get_text("blocks") if b[3] <= limit] + [d["rect"] for d in page.get_drawings() if d["rect"].y1 <= limit]
    if boxes:  # 건물개요·평가결과·최종결과까지(SafetyMan 모양 — 쪽 여백 빼고 내용 둘레 + 6pt)
        x0, y0 = min(b.x0 for b in boxes), min(b.y0 for b in boxes)
        x1, y1 = max(b.x1 for b in boxes), max(b.y1 for b in boxes)
        clip = pymupdf.Rect(max(rect.x0, x0 - 6), max(rect.y0, y0 - 6), min(rect.x1, x1 + 6), min(rect.y1, y1 + 6))
    else:
        clip = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.62)
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
    pinfo = prior_info_for(db, r)
    texts = precision_text.all_texts(defects, tv, rv["result"], grades=grades, structure=f.structure or "", load_note=pr["load"]["note"],
                                     prev_grade=rv["prev_grade"] or rv["prev_auto"], name=f.name, year=r.year, completion_text=comp_text,
                                     first=rv.get("prev_report") is None and not rv["prev_grade"], ai=ex.ai, prev_info=pinfo)  # 전차 등급을 직접 넣었으면 첫 회차 아님(10/14)
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
                "준공년도": f"{f.completion_date.year}년" if f.completion_date else "-", "종별": class_label(f)}
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
    D.prior_hist = prior_history(SR._prior(r))  # 전회차 보고서 점검이력 표 — 준공부터 전부(형 10/15)
    D.prior_info = pinfo
    D.half = r.half or ""
    from server.api.routers.sitok_defects import missing_photo_note
    D.missing_photo_note = missing_photo_note(db, r.id)
    from server.sitok import precision as PR
    base_dir = SR._report_dir(f, r)
    D.survey_pics = {k: [str(base_dir / x) if x else "" for x in v] for k, v in PR.norm((r.survey or {}).get("precision"))["survey"].items()}
    D.cost = ex.cost
    D.overview = list(ex.overview or [])
    D.blank = ex.blank
    try:
        from server.sitok import locmap
        mp = locmap.facility_map(f, SR._facility_dir(f))  # 올린 그림 > 핀 > 주소(10/23)
        D.map_path = str(mp) if mp else ""
        if mp and (note := locmap.address_note(f, SR._facility_dir(f))):
            D.notes.append(note)
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
    pinfo = prior_info_for(db, r)
    rv["prior_info"] = pinfo  # AI 자료 글에 전차 점수·결론(precision_ai.material)
    t = precision_text.all_texts(defects, tv, rv["result"], grades=grades, structure=f.structure or "", load_note=pr["load"]["note"],
                                 prev_grade=rv["prev_grade"] or rv["prev_auto"], name=f.name, year=r.year, completion_text=comp_text,
                                 first=rv.get("prev_report") is None and not rv["prev_grade"], ai=None, prev_info=pinfo)
    return {"texts": t, "tv": tv, "rv": rv, "pr": pr, "defects": defects, "facility": f}


def _josa(word: str, a: str = "은", b: str = "는") -> str:
    ch = (word or " ").rstrip()[-1:] or " "
    return (a if (ord(ch) - 0xAC00) % 28 else b) if "가" <= ch <= "힣" else b


def group_members(db, r) -> list:
    """묶음 동마다 같은 반기 회차 [(시설물, 회차)] — 묶음이 아니면 [(이 시설물, r)](sitok_reports._group_reports와 달리 없는 회차를 만들지 않음)."""
    from core.models_web import SitokFacility, SitokReport
    from server.api.routers.sitok_groups import members

    f = db.get(SitokFacility, r.facility_id)
    out = []
    for m in ((members(db, f.group_id) if f.group_id else None) or [f]):
        x = r if m.id == f.id else db.query(SitokReport).filter(SitokReport.facility_id == m.id, SitokReport.year == r.year, SitokReport.half == r.half).first()
        if x is not None:
            out.append((m, x))
    return out or [(f, r)]


def _member_infos(db, r) -> list[dict]:
    """부록 서류(과업수행계획서·사전검토보고서) 동마다 값 — [{f, r, tv, prev}]."""
    from server.api.routers import sitok_rating as SRt, sitok_tests as ST

    out = []
    for m, x in group_members(db, r):
        try:
            tv = ST._view(db, x)
        except Exception:  # noqa: BLE001
            tv = None
        try:
            rv = SRt._compute(db, x)
            prev = rv["prev_grade"] or rv["prev_auto"]
        except Exception:  # noqa: BLE001
            prev = ""
        out.append({"f": m, "r": x, "tv": tv, "prev": prev})
    return out


def _scope_vals(f, prev: str) -> dict:
    WORD = {"A": "우수", "B": "양호", "C": "보통", "D": "미흡", "E": "불량"}
    year = str(f.completion_date.year) if f.completion_date else "-"
    return {"시설명": f.name, "건물명": f.name, "용도": f.use_type or f.main_use or "-", "최초건축년도": year, "준공년도": year,
            "연면적(㎡)": f"{f.total_area:,.2f}" if f.total_area else "-", "층수": f"{f.floors_above or 0}/-{f.floors_below or 0}",
            "구조": "철콘" if "철근콘크리트" in (f.structure or "") else (f.structure or "-"), "기존등급": WORD.get(prev, prev) if prev else "-"}


def _fill_scope_tables(root, infos: list[dict]) -> int:
    """과업수행계획서 1) 과업범위·사전검토보고서 3. 과업의 범위 표 — 동마다 한 줄(형 10/15 "시설물 2개 들어가야 함"), 값은 머리칸의 열 주소로
    (17칸 표는 머리칸이 합쳐져 있어 머리칸 순번으로 넣으면 준공년도 칸에 "철콘"이 들어갔음)."""
    n = 0
    for tbl in _tables(root, ["시설명", "용도", "최초건축년도"]) + _tables(root, ["건물명", "용도", "최초건축년도"]):
        if len(infos) > 1 and int(tbl.get("rowCnt")) == 2:
            rb._dup_rows(tbl, 1, 1, len(infos) - 1, clear_cols=set())
        cells = rb._cells(tbl)
        heads = {c: re.sub(r"\s", "", rb._cell_text(tc)) for (r_, c), tc in cells.items() if r_ == 0}
        for i, info in enumerate(infos, 1):
            vals = _scope_vals(info["f"], info["prev"])
            for c, h in heads.items():
                if h in vals and (i, c) in cells:
                    _set(cells, i, c, vals[h])
        n += 1
    return n


def _qty_per_member(root, infos: list[dict]) -> int:
    """사전검토보고서 4.4 기본과업 재료시험 수량 — 동마다 표본층 표 + 산출수량 표(형 10/15 "2개 시설물에 대한 재료시험 수량 산정") — 동 이름 줄 + 표 두 개를 동마다 복사."""
    from server.sitok import merge as M

    tops = _tops(root)
    i44 = next((i for i, p in enumerate(tops) if re.match(r"^4\.4\s", _para_text(p))), None)
    if i44 is None:
        return 0
    pair = [q for q in tops[i44 + 1:i44 + 6] if _has_tbl(q)][:2]
    if len(pair) < 2:
        return 0
    body = next((tops[i + 1] for i, p in enumerate(tops) if re.match(r"^5\.\s*결론", _para_text(p)) and i + 1 < len(tops)), None)
    blocks = [pair]
    if len(infos) > 1 and body is not None:
        last = pair[-1]
        for info in infos[1:]:
            lab = copy.deepcopy(body)
            rb._set_para(lab, f"◦ {info['f'].name}")
            copies = [copy.deepcopy(q) for q in pair]
            for q in copies:
                M._renew_ids(q)
            last.addnext(lab)
            lab.addnext(copies[0])
            copies[0].addnext(copies[1])
            last = copies[1]
            blocks.append(copies)
        lab0 = copy.deepcopy(body)
        rb._set_para(lab0, f"◦ {infos[0]['f'].name}")
        pair[0].addprevious(lab0)
    n = 0
    for info, (pa, pb) in zip(infos, blocks):
        if info["tv"] is None:
            continue
        ta = next(t for t in pa.iter(f"{{{HP}}}tbl"))
        tb = next(t for t in pb.iter(f"{{{HP}}}tbl"))
        _fill_sample_tbl(ta, info["tv"], info["f"])
        if int(tb.get("rowCnt")) >= 7:
            _fill_qty_tbl(tb, info["tv"])
        n += 1
    return n


def _fill_appendix_docs(root, D: Data, infos: list[dict], state: dict, when) -> int:
    """부록 서류 손질(형 10/15) — 표지 날짜(2026. 05. → 점검 시작 연월), 과업지시서(7-2)의 "정밀점검" → "정밀안전점검", 과업수행계획서의 "정기안전점검" → 정밀, 과업범위 표 동마다, 사전검토보고서
    ("정밀점검" → "정밀안전점검", 4.2 자료 목록 = 본문 표 2.1과 같은 목록, 4.3 제목 "정밀안전점검 과업내용", 4.4 동마다 수량, 5. 결론 두 동 이름). state = 구역을 넘는 구간 표시."""
    from server.sitok import merge as M

    n = _fill_scope_tables(root, infos)
    for p in root.iter(f"{{{HP}}}p"):
        own = "".join(rb._full(t) for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}p")) is p)
        if re.fullmatch(r"\s*20\d{2}\.\s*\d{1,2}\.\s*", own) and when is not None:
            n += M._sub_pieces(p, r"20\d{2}\.\s*\d{1,2}\.", f"{when.year}. {when.month:02d}.")
    for p in _tops(root):
        allt = "".join(rb._full(t) for t in p.iter(T)).replace(" ", "")
        if "7-2" in allt and "과업지시서" in allt:
            state["task"] = True
        if "7-3" in allt and "과업수행계획서" in allt:
            state["plan"], state["pre"], state["task"] = True, False, False
        if "7-4" in allt and "사전검토보고서" in allt:
            state["plan"], state["pre"] = False, True
        if "7-5" in allt and "계약서" in allt:
            state["plan"], state["pre"] = False, False
        if state.get("plan"):
            n += M._sub_pieces(p, "정기안전점검", "정밀안전점검") + M._sub_pieces(p, "정기점검", "정밀안전점검")
        if state.get("task"):  # 7-2 과업지시서 본문도(사용자 10/15 "추천대로")
            n += M._sub_pieces(p, "정밀점검", "정밀안전점검")
        if state.get("pre"):
            n += M._sub_pieces(p, "정밀점검", "정밀안전점검")
            t = _para_text(p)
            if t.startswith("4.3") and "유지관리자료" in t:
                rb._set_para(p, "4.3 정밀안전점검 과업내용")
                n += 1
            if "과업지시서 검토결과" in t and len(infos) > 1:
                names = " 및 ".join(i["f"].name for i in infos)
                n += M._sub_pieces(p, re.escape(infos[0]["f"].name) + r"[은는]", names + _josa(names), first_only=True)
    for tbl in root.iter(f"{{{HP}}}tbl"):  # 4.3 과업내용 표 — 글자처럼 취급(통째로)이라 제목 뒤가 반 쪽 넘게 비고 다음 쪽에서 시작(형 10/15) → 줄 단위로 나눔
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is None and _head(tbl, 3) == ["과업항목", "지침상기본과업", "금회과업내용"]:
            rb._splittable(tbl, 1)
            n += 1
    for tbl in root.iter(f"{{{HP}}}tbl"):  # 좁은 머리칸 "정밀안전점검"이 "정밀안전점/검"으로 끊기지 않게 두 줄로
        for tc in rb._cells(tbl).values():
            if re.sub(r"\s", "", rb._cell_text(tc)) == "정밀안전점검" and int(tc.find(f"{{{HP}}}cellSz").get("width") or 0) < 9000:
                rb._set_lines(tc, ["정밀안전", "점검"])
    from server.sitok import form_fix

    n += form_fix.task_head_line(root)  # 과업구분 표 머리 줄 아래 굵은 한 줄(10/27 — 정기와 같게, 과업수행계획서·사전검토 어디든)
    if state.get("pre") or rb._find_table(root, ["보존대상목록", "관리주체보유현황", "비고"]) is not None:
        n += _fill_docs_appendix(root, D)
        n += _qty_per_member(root, infos)
        if len(infos) > 1:  # 과업의 범위 표가 동 수만큼 늘어난 만큼 "4. 사전검토 내용" 앞뒤 빈 줄을 빼서 4.1 표가 한 쪽에(한 줄만 넘어가던 것, 10/15)
            tops = _tops(root)
            k = next((i for i, p in enumerate(tops) if re.match(r"^4\.\s*사전검토", _para_text(p))), None)
            if k is not None:
                for q in [tops[k + 1] if k + 1 < len(tops) else None, tops[k - 1] if k > 0 else None][:len(infos) - 1 + 1]:
                    if q is not None and _blank_para(q) and q.get("pageBreak") != "1":
                        root.remove(q)
                        n += 1
    return n


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
    infos = _member_infos(db, r)
    state: dict = {}
    when = r.period_start or r.report_date or datetime.date.today()
    with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(dest.with_suffix(".tmp"), "w", zipfile.ZIP_DEFLATED) as zout:
        ordered = rb._sections(zin)
        hdr = zin.read("Contents/header.xml").decode("utf-8")
        with rb.using_borders(Borders(hdr)) as bd:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "Contents/header.xml":  # 줄 복사 테두리 모양을 더해 맨 뒤에 씀(10/15)
                    continue
                if info.filename in ordered:
                    root = etree.fromstring(data)
                    if D.replace:
                        changed += rb._apply(root, D.replace, [], set(), False)
                    changed += _fill_test_tables(root, D) + _fill_quantity(root, D)
                    changed += _fill_appendix_docs(root, D, infos, state, when)  # 과업수행계획서·사전검토보고서(동마다 줄·날짜·정밀 글·4.2~4.4·결론, 10/15)
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
                    rb.fit_added_pics([root], added)  # 200dpi 사진 — 그림 전체가 칸에 보이게(10/28)
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                elif info.filename == "Contents/content.hpf":
                    hpf = data
                    continue
                elif info.filename in ("Preview/PrvImage.png",):
                    continue
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
        zout.writestr("Contents/header.xml", bd.result(hdr).encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        items = "".join(f'<opf:item id="{k}" href="BinData/{k}.jpg" media-type="image/jpg" isEmbeded="1"/>' for k, _ in added)
        zout.writestr("Contents/content.hpf", hpf.decode("utf-8").replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8"))
        for k, b in added:
            zout.writestr(f"BinData/{k}.jpg", b, compress_type=zipfile.ZIP_STORED)
    dest.with_suffix(".tmp").replace(dest)
    tmp.unlink(missing_ok=True)
    return warn + D.notes, changed
