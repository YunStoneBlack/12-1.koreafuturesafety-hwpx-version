"""옹벽 정기안전점검 보고서 만들기(2026-10-20 옹벽 3단계 — 한 곳짜리). 건축물 정기(report_build)는 원본 한 파일을 채우지만, 옹벽은 형 견본이
파일 여럿(표지·요약문·서두·목차·개요·현장조사·시설물편·종합결론·부록)이라 **부분 파일마다 따로 채워 PDF로 바꾼 뒤 합침** — 한 hwpx로 합치면 스타일 id가 충돌.
원본 = data/_시특법/_회사템플릿/옹벽/*.hwpx(견본 hwp를 작업 프로그램이 hwpx로 — 10/20 민재형이 고친 2종·3종·부록).

- 쪽 번호: 부분마다 꼬리말이 자동 번호(autoNum PAGE)라 본문 부분(개요부터)의 secPr startNum page를 앞 부분 쪽 수에 이어 넣음(PDF로 바꿔 세며 차례로).
- 목차: 본문 PDF에서 제목이 처음 나오는 쪽을 찾아 숫자만 바꿈(03_목차 문단 끝 숫자), 제Ⅱ편은 제1장 한 줄.
- 서두: 제출문·참여기술자 명단 + 결과표(1개) + 전경사진(1개) — 견본의 위치도 4장·결과표 17개·전경 17개 중 첫 것만 남기고 지움(안 쓰는 BinData도 지워 163MB → 작게).
- 시설물편: 1.1 결과표·1.2.1 현황표(관리대장 제원 wall_ledger)·1.2.2 위치도(locmap)·1.2.3 전경 6장·1.3.2 점검 이력·1.4.1~1.4.4 글(AI wall_ai)·사진 표 4장씩·
  1.4.5 요약표·1.5 이름·1.6 개략공사비·1.7 종합결론. 3종은 06_시설물편_3종(1.5 안전등급 평가 표는 아직 그대로 — 5단계).
- 부록: 간지만 남기고(견본 사진 쪽 지움) 관리대장 PDF·사진첩 PDF(pymupdf로 그림 — 전경 6 + 주요 손상 및 현황 사진 2×3, 설명은 그림 바로 아래 → 다음 회차 wall_album이 읽음)·계약서를 끼움.
"""
from __future__ import annotations

import copy
import datetime
import random
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from lxml import etree

from core.db import DATA_DIR
from server.sitok import wall_ai, wall_ledger
from server.sitok import report_build as rb
from server.sitok.report_build import HP, T

TEMPLATE_DIR = DATA_DIR / "_시특법" / "_회사템플릿" / "옹벽"
PART_FILES = {"cover": "00_표지.hwpx", "summary": "01_요약문.hwpx", "front": "02_서두.hwpx", "toc": "03_목차.hwpx", "intro": "04_개요.hwpx",
              "survey": "05_현장조사.hwpx", "chapter2": "06_시설물편_2종.hwpx", "chapter3": "06_시설물편_3종.hwpx", "conclusion": "07_종합결론.hwpx",
              "appendix": "08_부록.hwpx", "plan": "09_과업수행계획서.hwpx"}
BODY = ("intro", "survey", "chapter", "conclusion", "appendix")  # 쪽 번호가 이어지는 부분(개요부터)
FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
SAMPLE_TITLE = "2026년 상반기 산업단지 옹벽 정기안전점검 용역"
SAMPLE_NAME = "보강토옹벽-2"
HC = "http://www.hancom.co.kr/hwpml/2011/core"


def ready() -> list[str]:
    """없는 원본 부분 파일 이름(있으면 빈 목록)."""
    return [v for k, v in PART_FILES.items() if k != "plan" and not (TEMPLATE_DIR / v).exists()]


# ---------- hwpx 부분 파일 ----------
class Hwpx:
    """부분 hwpx 하나 — 첫 구역 root를 고치고 그림을 더해 저장(안 쓰는 BinData는 뺄 수 있음)."""

    def __init__(self, src: Path):
        self.src = src
        with zipfile.ZipFile(src) as z:
            self.sections = rb._sections(z)
            masters = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/masterpage\d+\.xml", n))  # 바탕쪽 — 머리말 용역명이 여기(10/21)
            self.roots = {s: etree.fromstring(z.read(s)) for s in self.sections + masters}
        self.root = self.roots[self.sections[0]]
        self.added: list[tuple[str, bytes]] = []
        self.run = datetime.datetime.now().strftime("%y%m%d%H%M%S") + f"{random.randint(0, 999):03d}"

    def add_image(self, path_or_bytes) -> str:
        key = f"wall{self.run}_{len(self.added) + 1}"
        self.added.append((key, path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()))
        return key

    def replace_all(self, old: str, new: str) -> int:
        """구역·바탕쪽(머리말·꼬리말) 전부에서 글자 바꾸기."""
        return sum(replace_text(r, old, new) for r in self.roots.values())

    def start_page(self, page: int) -> None:
        """이 부분의 첫 쪽 번호 — 견본 부분 파일은 "새 번호로 시작"(hp:newNum PAGE — 개요 1·9, 시설물편 15, 종합결론 306)으로 박혀 있어
        첫 newNum을 이어지는 번호로 바꾸고 나머지(개요 2장 9)는 지움(안에서 자연히 이어짐). newNum이 없으면 구역 startNum."""
        nums = [x for r in self.roots.values() for x in r.iter(f"{{{HP}}}newNum") if x.get("numType") == "PAGE"]
        for i, x in enumerate(nums):
            if i == 0:
                x.set("num", str(page))
                continue
            parent = x.getparent()
            if parent is not None and parent.tag == f"{{{HP}}}ctrl" and len(parent) == 1:
                parent.getparent().remove(parent)
            elif parent is not None:
                parent.remove(x)
        for sn in self.root.iter(f"{{{HP}}}startNum"):
            sn.set("page", "0" if nums else str(page))
            break

    def save(self, dest: Path, drop_unused: bool = False) -> Path:
        used = {img.get("binaryItemIDRef") for r in self.roots.values() for img in r.iter(f"{{{HC}}}img")}
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        hpf = b""
        with zipfile.ZipFile(self.src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            items = re.findall(r'<opf:item [^>]*href="BinData/([^"]+)"[^>]*/>', zin.read("Contents/content.hpf").decode("utf-8"))
            id_of = {}
            for it in re.findall(r"<opf:item [^>]*href=\"BinData/[^\"]+\"[^>]*/>", zin.read("Contents/content.hpf").decode("utf-8")):
                m = re.search(r'id="([^"]+)"', it)
                h = re.search(r'href="BinData/([^"]+)"', it)
                if m and h:
                    id_of[h[1]] = m[1]
            _ = items
            for info in zin.infolist():
                name = info.filename
                data = zin.read(name)
                if name in self.roots:
                    root = self.roots[name]
                    for el in list(root.iter(f"{{{HP}}}linesegarray")):
                        el.getparent().remove(el)
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                elif name.startswith("BinData/") and drop_unused and id_of.get(name[8:]) not in used:
                    continue
                elif name == "Contents/content.hpf":
                    hpf = data
                    continue
                elif name in ("Preview/PrvText.txt", "Preview/PrvImage.png"):
                    continue
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
            text = hpf.decode("utf-8")
            if drop_unused:
                text = re.sub(r'<opf:item [^>]*href="BinData/[^"]+"[^>]*/>', lambda m: m[0] if re.search(r'id="([^"]+)"', m[0])[1] in used else "", text)
            new = "".join(f'<opf:item id="{k}" href="BinData/{k}.jpg" media-type="image/jpg" isEmbeded="1"/>' for k, _ in self.added)
            zout.writestr("Contents/content.hpf", text.replace("</opf:manifest>", new + "</opf:manifest>").encode("utf-8"))
            texts = "\r\n".join("".join(t.text or "" for t in p.iter(T)) for r in self.roots.values() for p in r.iter(f"{{{HP}}}p"))
            zout.writestr("Preview/PrvText.txt", texts[:2000].encode("utf-8"))
            for k, b in self.added:
                zout.writestr(f"BinData/{k}.jpg", b, compress_type=zipfile.ZIP_STORED)
        tmp.replace(dest)
        return dest


# ---------- 작은 도우미 ----------
def _tops(root) -> list:
    return [p for p in root if p.tag == f"{{{HP}}}p"]


def _ptext(p) -> str:
    return (rb._top_text(p) or "").strip()


def _tables(root) -> list:
    return [t for t in root.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None]


def _tbl(root, rows: int, cols: int, head: str | None = None, nth: int = 0):
    """크기(줄×칸)와 (0,0) 글 머리로 찾은 표(nth번째)."""
    k = 0
    for t in _tables(root):
        if (int(t.get("rowCnt")), int(t.get("colCnt"))) != (rows, cols):
            continue
        if head is not None and not rb._n(rb._cell_text(rb._cells(t).get((0, 0), t))).startswith(rb._n(head)):
            continue
        if k == nth:
            return t
        k += 1
    return None


def _set(cells: dict, rc: tuple, text: str) -> None:
    tc = cells.get(rc)
    if tc is not None:
        rb._set_lines(tc, str(text if text is not None else "").split("\n"))


def replace_text(root, old: str, new: str) -> int:
    """글자 칸 하나 안에 통째로 있으면 바꾸고, 머리말·꼬리말·표지처럼 글자 칸 여러 개에 나뉘어 있으면 문단 단위로 이어 붙여 찾아 바꿈(첫 칸에 몰아 넣음)."""
    n = 0
    for t in root.iter(T):
        if t.text and old in t.text:
            t.text = t.text.replace(old, new)
            n += 1
    for p in root.iter(f"{{{HP}}}p"):
        pieces = [pc for x in p.iter(T) if next(x.iterancestors(f"{{{HP}}}p"), None) is p for pc in rb._pieces(x)]
        if len(pieces) < 2:
            continue
        joined = "".join(pc.text or "" for pc in pieces)
        if old not in joined:
            continue
        pieces[0].text = joined.replace(old, new)
        for pc in pieces[1:]:
            pc.text = ""
        n += 1
    return n


def _del(root, paras: list) -> None:
    for p in paras:
        if p.getparent() is not None:
            p.getparent().remove(p)


def _date(d, dots: bool = True) -> str:
    if not d:
        return "-"
    return f"{d.year}. {d.month:02d}. {d.day:02d}." if dots else f"{d.year}년 {d.month:02d}월 {d.day:02d}일"


def _photo(tc, cap_tc, image, caption: str, tpl, add_image) -> None:
    """사진 칸에 그림(없으면 비움) + 설명 칸."""
    rb._slot_put(tc, cap_tc, image, "", caption, tpl, add_image)


def _fit(path: Path, w: int, h: int) -> bytes:
    return rb._cropped(path, w, h)


def _pic_tpl(root):
    t = _tbl(root, 6, 2)
    return next((copy.deepcopy(p) for p in t.iter(f"{{{HP}}}pic")), None) if t is not None else None


def _photo_pairs(tbl) -> list[tuple]:
    """사진 표(사진 줄·설명 줄 번갈아) → [(사진 칸, 설명 칸)] 줄·칸 순."""
    cells = rb._cells(tbl)
    rows = sorted({r for r, _ in cells})
    out = []
    for i in range(0, len(rows) - 1, 2):
        for c in sorted(c for r, c in cells if r == rows[i]):
            out.append((cells[(rows[i], c)], cells.get((rows[i + 1], c))))
    return out


def _fill_photo_table(tbl, photos: list[tuple], tpl, add_image, blank_first: str = "해당없음") -> None:
    pairs = _photo_pairs(tbl)
    for i, (tc, cap) in enumerate(pairs):
        if i < len(photos):
            path, caption = photos[i]
            sz = tc.find(f"{{{HP}}}cellSz")
            img = _fit(Path(path), int(sz.get("width")), int(sz.get("height"))) if sz is not None else Path(path).read_bytes()
            _photo(tc, cap, img, caption, tpl, add_image)
        else:
            rb._slot_put(tc, cap, None, blank_first if not photos and i == 0 else "", "-", tpl, add_image)


# ---------- 값 모으기 ----------
@dataclass
class Data:
    name: str = ""
    title: str = ""
    year: int = 0
    half: str = ""
    period: str = ""  # 2026. 04. 13. ~ 2026. 06. 30.
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    month: str = ""  # 2026. 06.
    month_dot: str = ""  # 2026∙06
    owner: str = ""
    owner_rep: str = ""
    owner_type: str = "공공"
    joint: str = "단독수급"
    bid: str = "수의계약"
    kind_text: str = "기타옹벽"
    class_no: str = "2"
    completion: datetime.date | None = None
    amount_k: str = "-"
    grade: str = "양호"
    prev_grade: str = "양호"
    address: str = ""
    spec: dict = field(default_factory=dict)
    persons: list = field(default_factory=list)  # (역할, 이름, 직급, 분야, 등급)
    overview: list = field(default_factory=list)  # [(path, caption)]
    locmap: Path | None = None
    sections: dict = field(default_factory=dict)  # found/front/etc/public → [(path, caption)]
    ai: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # [{period, kind, org, grade, result}]
    cost: tuple = ((), 0)
    shots: list = field(default_factory=list)  # 사진첩 [(path, caption)]
    compare: list = field(default_factory=list)  # 전회차 비교 사진대장 [(prev, now, caption)]
    public_names: str = ""
    template3: bool = False
    warn: list = field(default_factory=list)

    @property
    def size(self) -> str:
        h, ln = self.spec.get("height") or "-", self.spec.get("length") or "-"
        return f"H={h}m, L={ln}m"

    @property
    def completion_text(self) -> str:
        return _date(self.completion, dots=False)

    @property
    def year_month(self) -> str:
        return f"{self.completion.year}.{self.completion.month:02d}" if self.completion else "-"


def _spaced(name: str) -> str:
    return "  ".join(name.replace(" ", ""))


def gather(db, r, f) -> Data:
    """회차·시설물·계약·결함·AI 초안·사진 → Data(보고서에 넣을 값)."""
    from core.models_web import SitokContract, TechPerson
    from server.api.routers import sitok_defects as SD
    from server.api.routers.sitok_good import wall_category
    from server.api.routers.sitok_reports import _facility_dir, _report_dir
    from server.api.routers.sitok_settings import prices
    from server.sitok import good as G
    from server.sitok import locmap
    from server.sitok import parts as P

    d = Data(name=f.name, year=r.year, half=r.half)
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    d.title = (c.title if c and c.title else f"{r.year}년 {r.half} {f.name} 정기안전점검 용역").strip()
    d.period_start, d.period_end = r.period_start, r.period_end
    d.period = f"{_date(r.period_start)} ~ {_date(r.period_end)}" if r.period_start and r.period_end else "-"
    rd = r.report_date or r.period_end or datetime.date.today()
    d.month, d.month_dot = f"{rd.year}. {rd.month:02d}.", f"{rd.year}∙{rd.month:02d}"
    d.owner = f.owner_name or (c.rep_name if c else "") or "-"
    d.owner_rep = (c.rep_name if c and c.rep_name else "") or "-"
    d.owner_type = "공공" if (f.sector or (c.sector if c else "")) == "관급" or (f.owner_type or "") == "공공" else "민간"
    if c:
        d.joint = "단독수급" if (c.joint_type or "") in ("", "독자수행", "단독수급") else c.joint_type
        d.bid = c.bid_method or "수의계약"
        if c.amount:
            per_half = c.amount / 2 if c.sector == "관급" and c.halves == "연간" else c.amount
            d.amount_k = f"{round(per_half / 1000):,}"
    if (r.amount_k or "").strip():
        d.amount_k = r.amount_k.strip()
    d.completion = f.completion_date
    d.address = f.address or "-"
    # 제원 — 관리대장 글자(없으면 전에 읽어 둔 것)
    led = dict(f.ledger or {})
    spec = dict(led.get("wall") or {})
    if not spec.get("length") or not spec.get("fms_no"):
        got = wall_ledger.read(f.ledger_pdf)
        if got:
            spec = {**got, **{k: v for k, v in spec.items() if v}}
            f.ledger = {**led, "wall": spec}
    d.spec = spec
    d.kind_text = spec.get("kind_text") or wall_ledger.kind_text_of(f.kind or "")
    d.class_no = (f.class_no or spec.get("class_no") or "2").strip()
    d.template3 = (f.template or "").startswith("3종")
    # 사람
    ids = [x for x in [r.chief_id, *(r.participant_ids or [])] if x]
    people = {p.id: p for p in db.query(TechPerson).filter(TechPerson.id.in_(ids))} if ids else {}
    for i, pid in enumerate(ids):
        p = people.get(pid)
        if p:
            d.persons.append(("사업책임기술자" if i == 0 else "참여기술자", p.name, p.position or "", p.sitok_field or "토목", p.sitok_grade or p.grade or ""))
    if not d.persons:
        d.warn.append("회차 정보에 책임·참여기술자가 없어 기술자 칸이 비었습니다")
    # 사진
    rdir = _report_dir(f, r)
    for o in r.overview or []:  # 이번 사진, 없으면 전회차(가져온 것, 10/21)
        p = rdir / o["file"] if o.get("file") else (rdir / o["prev_file"] if o.get("prev_file") else None)
        if p is not None and p.exists():
            d.overview.append((p, o.get("title") or ""))
    try:
        d.locmap = locmap.map_for(f.address, f.name, _facility_dir(f))
    except Exception:  # noqa: BLE001
        d.locmap = None
    rows = SD._rows(db, r.id)
    sec: dict[str, list] = {"found": [], "front": [], "etc": [], "public": []}
    shots: list[tuple] = []
    for x in rows:
        photo = Path(x.photo) if x.photo and Path(x.photo).exists() else (Path(x.prev_photo) if x.prev_photo and Path(x.prev_photo).exists() else None)
        if photo is None or x.check == "repaired":
            continue
        cap = f"{(x.member or '').strip()} {x.dtype}".strip()
        if "균열" in (x.dtype or "") and x.width:
            try:
                cap += f"({'0.3mm이상' if float(x.width) >= 0.3 else '0.3mm미만'})"
            except ValueError:
                pass
        key = wall_category(x.floor)
        sec[key].append((photo, cap))
        shots.append((photo, cap))
        if x.photo and Path(x.photo).exists() and x.prev_photo and Path(x.prev_photo).exists():
            d.compare.append((Path(x.prev_photo), photo, f"{x.floor} {x.seq}번 {cap}"))
    g = G.norm(r.survey, "wall")
    for key, _ in G.WALL_CATS:
        gl = [x for x in g["good"][key] if not x.get("prev")] or [x for x in g["good"][key] if x.get("prev")]  # 이번 사진, 없으면 전회차
        for x in gl:
            p = rdir / x["file"]
            if p.exists():
                sec[key].append((p, x["title"] or "상태양호"))
                shots.append((p, x["title"] or "상태양호"))
    pub_names = []
    try:
        pub = P.norm(r.parts)["public"]
        for k, name in P.PUBLIC:
            it = pub.get(k) or {}
            f_ = it.get("file") or it.get("prev")
            p = rdir / f_ if f_ else None
            if p and p.exists():
                sec["public"].append((p, name))
                shots.append((p, name))
                pub_names.append(name)
    except Exception:  # noqa: BLE001
        pass
    d.sections = sec
    d.shots = shots
    d.public_names = ", ".join(pub_names)
    # AI 초안
    fin = (r.ai or {}).get("final") or {}
    defects = [{k: getattr(x, k) for k in ("part", "member", "dtype", "floor", "seq", "count", "width", "length", "qty", "check", "mark", "progress", "cause", "cause_note")} for x in rows]
    d.prev_grade = wall_ai.word(f.safety_grade or "") or "양호"
    d.ai = fin if wall_ai.is_wall_ai(fin) else wall_ai.fallback(defects, d.prev_grade, d.public_names)
    if not wall_ai.is_wall_ai(fin):
        d.warn.append("AI 초안이 없어 결함 목록으로 만든 기본 글로 채웠습니다 — [🤖 AI 초안]을 먼저 쓰면 좋습니다")
    d.grade = wall_ai.word(d.ai.get("grade") or "") or d.prev_grade
    # 이력·공사비
    d.history = list(spec.get("history") or [])
    try:
        methods = SD.method_map(fin.get("methods")) if fin else None
        d.cost = SD.cost_rows(db, r.id, prices(db, r.company_id), methods)
    except Exception:  # noqa: BLE001
        d.cost = ((), 0)
    return d


# ---------- 부분마다 채우기 ----------
def fill_cover(doc: Hwpx, d: Data) -> None:
    root = doc.root
    big = _tbl(root, 11, 1)
    if big is not None:
        inner = next(t for t in big.iter(f"{{{HP}}}tbl") if t is not big)
        rb._set_lines(rb._cells(inner)[(0, 0)], [f"{d.name}에 대한 {d.year}년 {d.half} 정기안전점검", "종합보고서"])
        cells = rb._cells(big)
        _set(cells, (5, 0), d.month)
        last = cells.get((10, 0))
        if last is not None:
            t2 = next((t for t in last.iter(f"{{{HP}}}tbl")), None)
            if t2 is not None:
                _set(rb._cells(t2), (0, 0), d.owner)
    spine = _tbl(root, 4, 2)
    if spine is not None:
        cells = rb._cells(spine)
        _set(cells, (0, 0), f"{d.name}에 대한")
        _set(cells, (0, 1), f"{d.year}년 {d.half} 정기안전점검")
        _set(cells, (2, 0), d.month_dot)


def fill_summary(doc: Hwpx, d: Data) -> None:
    root = doc.root
    t = _tbl(root, 1, 1)
    if t is not None:
        rb._set_lines(rb._cells(t)[(0, 0)], [f"{d.name}에 대한 {d.year}년 {d.half} 정기안전점검", "요           약          문"])
    for p in _tops(root):
        if re.fullmatch(r"\d{4}\.\s*\d{2}\.?", _ptext(p)):
            rb._set_para(p, d.month)
    t31 = _tbl(root, 3, 1)
    if t31 is not None:
        _set(rb._cells(t31), (0, 0), d.owner)
    replace_text(root, "어쩌구에 대한 2026년 상반기 정기안전점검", f"{d.name}에 대한 {d.year}년 {d.half} 정기안전점검")
    replace_text(root, "총 옹벽 17개소", "옹벽 1개소")
    replace_text(root, "2026년 04월 13일 ~ 2026년 07월 11일", f"{_date(d.period_start, False)} ~ {_date(d.period_end, False)}")
    for p in _tops(root):
        if _ptext(p).startswith("※ 옹벽 총"):
            rb._set_para(p, f"※ 옹벽 총 1개소({d.class_no}종시설물 : {d.grade} 1개소)")
    t = _tbl(root, 18, 11)
    if t is not None:
        cells = rb._cells(t)
        vals = ["1", d.name, f"{d.class_no}종", d.year_month, d.spec.get("form") or "-", d.spec.get("length") or "-", d.spec.get("height") or "-",
                d.prev_grade, d.grade, "\n".join(d.ai.get("findings") or []), "\n".join(d.ai.get("repairs") or [])]
        for c, v in enumerate(vals):
            _set(cells, (1, c), v)
        rb._del_rows(t, 2, 16)


def _fill_result_table(tbl, d: Data) -> None:
    """1.1 정기안전점검 결과표(서두·시설물편 같은 모양 20×9)."""
    cells = rb._cells(tbl)
    _set(cells, (1, 2), d.title)
    _set(cells, (1, 6), d.period)
    _set(cells, (2, 2), d.owner)
    _set(cells, (2, 6), d.owner_rep)
    _set(cells, (3, 2), d.joint)
    _set(cells, (3, 6), d.bid)
    _set(cells, (4, 6), d.kind_text)
    _set(cells, (4, 8), f"{d.class_no}종")
    _set(cells, (5, 2), d.completion_text)
    _set(cells, (5, 6), d.amount_k)
    _set(cells, (5, 8), d.grade)
    _set(cells, (6, 2), d.address)
    _set(cells, (6, 6), d.size)
    _set(cells, (8, 2), d.ai.get("critical") or "⦁없음")
    _set(cells, (9, 2), d.ai.get("public") or "⦁전반적으로 양호한 상태")
    _set(cells, (10, 2), "\n".join(d.ai.get("findings") or []))
    _set(cells, (11, 2), "\n".join(d.ai.get("repairs") or []))
    rows = [r for r in sorted({k[0] for k in cells}) if (r, 0) in cells and rb._n(rb._cell_text(cells[(r, 0)])).endswith("기술자")]
    for i, r in enumerate(rows):
        if i < len(d.persons):
            role, name, _, _, grade = d.persons[i]
            _set(cells, (r, 0), role)
            _set(cells, (r, 3), _spaced(name))
            _set(cells, (r, 4), d.period)
            _set(cells, (r, 7), grade)
        else:
            for c in (0, 3, 4, 7):
                _set(cells, (r, c), "")
    _set(cells, (19, 0), d.ai.get("next_focus") or "-")


def fill_front(doc: Hwpx, d: Data) -> None:
    root = doc.root
    tops = _tops(root)
    for p in tops:
        t = _ptext(p)
        if t.endswith("귀하"):
            rb._set_para(p, f"{d.owner_rep if d.owner_rep != '-' else d.owner}  귀하")
        elif "『" in t and "』" in t:
            for x in p.iter(T):
                if x.text and "『" in x.text:
                    x.text = re.sub(r"『.*?』", f"『{d.name}에 대한 {d.year}년 {d.half} 정기안전점검』", x.text)
        elif re.fullmatch(r"\d{4}년\s+\d{2}월", t):
            rb._set_para(p, f"{d.year if not d.period_end else d.period_end.year}년  {d.month[6:8]}월")
    tl = _tbl(root, 4, 5)
    if tl is not None:
        cells = rb._cells(tl)
        n_rows = int(tl.get("rowCnt")) - 1
        if len(d.persons) > n_rows:
            rb._dup_rows(tl, n_rows, 1, len(d.persons) - n_rows)
        elif len(d.persons) < n_rows and d.persons:
            rb._del_rows(tl, 1 + len(d.persons), n_rows - len(d.persons))
        cells = rb._cells(tl)
        for i, (role, name, pos, fld, grade) in enumerate(d.persons, 1):
            _set(cells, (i, 0), "책임기술자" if i == 1 else ("참여기술자" if i == 2 else ""))
            _set(cells, (i, 1), " ".join(name.replace(" ", "")))
            _set(cells, (i, 2), pos)
            _set(cells, (i, 3), f"{fld}\n{grade}" if grade else fld)
    # 위치도 4장·결과표 2~17·전경 2~17 지움
    tops = _tops(root)
    idx_res = [i for i, p in enumerate(tops) if re.match(r"\d+\.\s*.+정기점검 결과표", _ptext(p))]
    idx_ov = [i for i, p in enumerate(tops) if _ptext(p).endswith("전경사진")]
    kill = []
    i_map = [i for i, p in enumerate(tops) if _ptext(p).endswith("위치도")]
    if i_map and idx_res:
        kill += tops[i_map[0]:idx_res[0]]
    if len(idx_res) > 1 and idx_ov:
        kill += tops[idx_res[1]:idx_ov[0]]
    if len(idx_ov) > 1:
        kill += tops[idx_ov[1]:]
    _del(root, kill)
    tops = _tops(root)
    for p in tops:
        t = _ptext(p)
        if re.match(r"1\.\s*.+정기점검 결과표", t):
            rb._set_para(p, f"1. {d.name} 정기점검 결과표")
        elif t.endswith("전경사진"):
            rb._set_para(p, f"{d.name} 전경사진")
    res = _tbl(root, 20, 9, "가. 일반현황") or _tbl(root, 21, 9, "가. 일반현황")
    if res is not None:
        _fill_result_table(res, d)
    ov = _tbl(root, 6, 2)
    if ov is not None:
        _fill_photo_table(ov, d.overview[:6], next((copy.deepcopy(p) for p in ov.iter(f"{{{HP}}}pic")), None), doc.add_image, "")


def fill_toc(doc: Hwpx, d: Data, pages: dict[str, int]) -> int:
    """목차 — 제Ⅱ편은 제1장 한 줄로, 줄 끝 숫자(tab 뒤 조각) = 본문 쪽(pages: 제목 → 쪽). 장 줄 숫자는 그 장 첫 소절 쪽(견본 규칙). 바꾼 줄 수."""
    root = doc.root
    tops = _tops(root)
    kill, n = [], 0
    in_ch = 0
    lines = []  # (문단, 장 줄인지, 제목 열쇠)
    for p in tops:
        t = _ptext(p)
        m = re.match(r"제\s*(\d+)\s*장\s+(.+?)\s*(\d+)?$", t)
        if m and not re.match(r"제\s*\d+\s*장\s+(정기점검 개요|현장조사|종합결론)", t):
            in_ch = int(m[1])
        elif re.match(r"제\s*[ⅠⅡⅢ]\s*편", t) or re.match(r"<\s*부\s*록", t):
            in_ch = 0
        if in_ch >= 2:
            kill.append(p)
            continue
        if in_ch == 1 and m:
            for x in p.iter(T):
                for pc in rb._pieces(x):
                    if pc.text and SAMPLE_NAME in pc.text:
                        pc.text = pc.text.replace(SAMPLE_NAME, d.name)
            t = t.replace(SAMPLE_NAME, d.name)
        key = re.sub(r"\s+", "", re.sub(r"\s*\d+$", "", t))
        lines.append((p, bool(m), key))
    _del(root, kill)
    for i, (p, is_ch, key) in enumerate(lines):
        page = pages.get(key)
        if is_ch:  # 장 줄 = 다음 소절 줄의 쪽
            nxt = next((pages.get(k2) for q, c2, k2 in lines[i + 1:i + 3] if not c2 and pages.get(k2)), None)
            page = nxt or page
        if not page:
            continue
        pieces = [pc for x in p.iter(T) for pc in rb._pieces(x)]
        tail = next((pc for pc in reversed(pieces) if pc.text and re.fullmatch(r"\s*\d+\s*", pc.text)), None)
        if tail is not None:
            tail.text = str(page)
            n += 1
    return n


def fill_intro(doc: Hwpx, d: Data) -> None:
    root = doc.root
    doc.replace_all(SAMPLE_TITLE, d.title)
    if d.template3:  # 3종은 2.2 상태평가가 든 현장조사 부분(05)을 따로 쓰므로 여기 든 제2장은 뺌
        tops = _tops(root)
        i2 = next((i for i, p in enumerate(tops) if re.match(r"제\s*2\s*장", _ptext(p))), None)
        tbl2 = next((i for i, p in enumerate(tops) if i < (i2 or 0) and _tables_in(p) and re.sub(r"\s", "", _cell0(p)).startswith("제2장")), None)
        if i2 is not None:
            _del(root, tops[(tbl2 if tbl2 is not None else i2) - 1:])
    for p in _tops(root):
        t = _ptext(p)
        if t.startswith("본 과업은 「시설물의 안전"):
            where = d.address if d.address != "-" else ""
            rb._set_para(p, f"본 과업은 「시설물의 안전 및 유지관리에 관한 특별법」에 따른 정기점검 용역으로 {where + '에 위치한 ' if where else ''}제{d.class_no}종 시설물로 지정된 "
                            f"{d.name}에 대한 상태를 정밀히 파악하여 안전사고 예방 및 사후 조치에 만전을 기하고, 필요시 향후 유지관리 방안을 제시하여 시설물의 안전한 관리에 목적이 있다.")
        elif t.startswith("￭ 과업기간"):
            rb._set_para(p, f"￭ 과업기간 : {d.period}")
    t = _tbl(root, 18, 9, "번호")
    if t is not None:
        cells = rb._cells(t)
        for c, v in enumerate(["1", d.name, d.spec.get("form") or "-", f"{d.class_no}종", d.spec.get("length") or "-", d.spec.get("height") or "-", d.year_month, "정기점검", ""]):
            _set(cells, (1, c), v)
        rb._del_rows(t, 2, 16)


def _fill_history(tbl, rows: list) -> None:
    n_tpl = int(tbl.get("rowCnt")) - 1
    if not rows:
        rb._del_rows(tbl, 2, n_tpl - 1)
        cells = rb._cells(tbl)
        for c, v in enumerate(["-", "-", "-", "-", "-"]):
            _set(cells, (1, c), v)
        _set(cells, (1, 6), "-")
        return
    if len(rows) > n_tpl:
        rb._dup_rows(tbl, n_tpl, 1, len(rows) - n_tpl)
    elif len(rows) < n_tpl:
        rb._del_rows(tbl, 1 + len(rows), n_tpl - len(rows))
    cells = rb._cells(tbl)
    for i, h in enumerate(rows, 1):
        _set(cells, (i, 0), str(i))
        _set(cells, (i, 1), f"{h.get('period', '')}\n{h.get('kind', '')}".strip())
        _set(cells, (i, 2), h.get("org", "-"))
        _set(cells, (i, 3), h.get("grade", "-"))
        _set(cells, (i, 4), h.get("result", "-"))
        _set(cells, (i, 6), h.get("note", ""))


def fill_chapter(doc: Hwpx, d: Data) -> None:
    root = doc.root
    doc.replace_all(SAMPLE_TITLE, d.title)
    doc.replace_all(SAMPLE_NAME, d.name)
    t34 = _tbl(root, 3, 4)
    if t34 is not None:
        _set(rb._cells(t34), (0, 3), f"제1장 {d.name}")
    res = _tbl(root, 20, 9, "가. 일반현황")
    if res is not None:
        _fill_result_table(res, d)
    st = _tbl(root, 12, 8, "시설물 번호")
    if st is not None:
        cells = rb._cells(st)
        s = d.spec
        _set(cells, (0, 1), s.get("fms_no") or "-")
        _set(cells, (1, 1), d.name)
        _set(cells, (2, 2), d.address)
        _set(cells, (4, 2), wall_ledger.form_text(s, ""))
        _set(cells, (5, 2), s.get("length") or "-")
        _set(cells, (5, 7), s.get("height") or "-")
        _set(cells, (6, 2), s.get("base_width") or "-")
        _set(cells, (6, 7), s.get("route") or "-")
        _set(cells, (7, 1), s.get("owner") or d.owner)
        _set(cells, (7, 7), d.owner_type)
        _set(cells, (8, 1), s.get("surround") or "-")
        _set(cells, (9, 2), d.completion_text)
        _set(cells, (9, 7), s.get("builder") or "-")
        _set(cells, (10, 2), s.get("attached") or "-")
    tpl = _pic_tpl(root)
    # 1.2.2 위치도 = 1.2.3 문단 표(1×1, 그림 1) / 1.2.3 전경 6×2 / 1.2.4 도면 1×1(그림 3)
    one = [t for t in _tables(root) if (t.get("rowCnt"), t.get("colCnt")) == ("1", "1") and list(t.iter(f"{{{HP}}}pic"))]
    for t in one:
        pics = list(t.iter(f"{{{HP}}}pic"))
        if len(pics) == 1 and d.locmap and d.locmap.exists():
            rb._put_pic(pics[0], d.locmap, doc.add_image)
        elif len(pics) >= 3:  # 주요도면 — 도면이 없으면 빈 그림
            for pic in pics:
                img = next(pic.iter(f"{{{HC}}}img"), None)
                if img is not None:
                    img.set("binaryItemIDRef", doc.add_image(_blank_jpg()))
    ov = _tbl(root, 6, 2)
    if ov is not None:
        _fill_photo_table(ov, d.overview[:6], tpl, doc.add_image, "")
    t71 = _tbl(root, 7, 4, "보존대상 목록")
    if t71 is not None:
        proj = d.spec.get("project") or "-"
        replace_text(t71, "포천장자일반산업단지조성공사", proj)
        cells = rb._cells(t71)
        hist = [f"∙{h.get('period', '')} {h.get('kind', '')}".strip() for h in d.history[-2:]] or ["∙시설물관리대장 점검 이력 참조"]
        _set(cells, (5, 3), "\n".join(hist))
    th = _tbl(root, 17, 7, "번호")
    if th is not None:
        _fill_history(th, d.history)
    cont = _tbl(root, 5, 6, "번호")
    if cont is not None:
        p = next(cont.iterancestors(f"{{{HP}}}p"))
        _del(root, [p])
    # 1.4 글·사진 표
    tops = _tops(root)
    sec_keys = {"1.4.1": "found", "1.4.2": "front", "1.4.3": "etc", "1.4.4": "public"}
    i = 0
    while i < len(tops):
        t = _ptext(tops[i])
        m = re.match(r"(1\.4\.[1-4])\s", t)
        if m and m[1] in sec_keys and "요약표" not in t:
            key = sec_keys[m[1]]
            j = i + 1
            body = []
            while j < len(tops) and not _ptext(tops[j]).startswith("1.4") and not list(tops[j].iter(f"{{{HP}}}tbl")):
                if _ptext(tops[j]):
                    body.append(tops[j])
                j += 1
            text = (d.ai.get("sections") or {}).get(key) or ""
            if body:
                rb._set_para(body[0], text)
                _del(root, body[1:])
            if j < len(tops):
                tbl = next((x for x in tops[j].iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) == ("4", "2")), None)
                if tbl is not None:
                    _fill_photo_table(tbl, d.sections.get(key, [])[:4], tpl, doc.add_image)
            tops = _tops(root)
            i = i + 1
            continue
        i += 1
    tsum = _tbl(root, 8, 4, "부재명")
    if tsum is not None:
        cells = rb._cells(tsum)
        prev_h = f"{d.year - 1 if d.half == '상반기' else d.year}년 {'하반기' if d.half == '상반기' else '상반기'}"
        _set(cells, (0, 1), f"전회 정기점검 결과\n({prev_h})")
        _set(cells, (0, 2), f"금회 점검 결과\n({d.year}년 {d.half})")
        for i, row in enumerate((d.ai.get("summary_rows") or [])[:5], 1):
            _set(cells, (i, 1), row.get("prev") or "⦁-")
            _set(cells, (i, 2), row.get("now") or "⦁-")
            _set(cells, (i, 3), row.get("action") or "⦁주의관찰")
        _set(cells, (6, 1), f"⦁{d.prev_grade}")
        _set(cells, (6, 2), f"⦁{d.grade}")
        _set(cells, (7, 1), d.ai.get("summary_opinion") or "")
    t22 = _tbl(root, 2, 2, "구")
    if t22 is not None:
        _set(rb._cells(t22), (1, 0), d.name)
    tc_ = _tbl(root, 6, 8, "구 분")
    if tc_ is not None:
        rows, direct = d.cost
        rows = list(rows)[:2]
        cells = rb._cells(tc_)
        for i in range(2):
            vals = rows[i] if i < len(rows) else ("-",) * 7
            part, desc, act, qty, unit, price, amount = vals
            for c, v in enumerate([part, desc, act, qty, unit, price if price == "-" else _k(price), amount if amount == "-" else _k(amount), "2" if i == 0 else "3"]):
                _set(cells, (i + 1, c), v if (i < len(rows) or c == 7) else "-")
        if rows:
            direct_k = round(direct / 1000)
            _set(cells, (3, 5), f"{direct_k:,}")
            _set(cells, (4, 5), f"{round(direct_k * 0.6):,}")
            _set(cells, (5, 5), f"{direct_k + round(direct_k * 0.6):,}")
    tcon = _tbl(root, 4, 2, "구")
    if tcon is not None:
        cells = rb._cells(tcon)
        con = d.ai.get("conclusion") or {}
        _set(cells, (1, 1), "\n".join(con.get("survey") or ["⦁-"]))
        _set(cells, (2, 1), "\n".join(con.get("repair") or ["⦁-"]))
        _set(cells, (3, 1), con.get("urgent") or "⦁필요치 않음")


def _k(s: str) -> str:
    try:
        return f"{round(int(str(s).replace(',', '')) / 1000):,}"
    except ValueError:
        return s


def fill_conclusion(doc: Hwpx, d: Data) -> None:
    root = doc.root
    doc.replace_all(SAMPLE_TITLE, d.title)
    con = d.ai.get("conclusion") or {}
    for p in _tops(root):
        t = _ptext(p)
        if t.startswith("본 점검 대상시설물"):
            rb._set_para(p, f"본 점검 대상시설물 {d.name}에 대한 외관조사 결과 시설물 안전성에 영향을 주는 구조적 손상은 "
                            + ("없는 것으로 조사되었으며, 전반적으로 양호한 것으로 판단됨으로 긴급점검 및 정밀안전진단이 필요하지 않은 것으로 판단된다."
                               if d.grade in ("양호", "보통") else "일부 조사되어 지속적인 관찰과 보수·보강이 필요한 것으로 판단된다."))
    tops = _tops(root)
    firsts = [p for p in tops if _ptext(p).startswith("1.2 점검결과 총괄표")]
    if len(firsts) > 1:
        i0 = tops.index(firsts[1])
        _del(root, tops[i0:])
    t = _tbl(root, 21, 6, "No")
    if t is not None:
        cells = rb._cells(t)
        _set(cells, (1, 1), d.name)
        _set(cells, (1, 3), f"{d.completion.year}년" if d.completion else "-")
        _set(cells, (1, 4), "\n".join(d.ai.get("findings") or []))
        _set(cells, (1, 5), "\n".join(d.ai.get("repairs") or []) or "\n".join(con.get("repair") or []))
        _set(cells, (2, 3), d.spec.get("height") or "-")
        _set(cells, (3, 3), d.spec.get("length") or "-")
        _set(cells, (4, 3), d.grade)
        rb._del_rows(t, 5, 16)


def fill_appendix(doc: Hwpx, d: Data) -> None:
    root = doc.root
    doc.replace_all(SAMPLE_TITLE, d.title)
    tops = _tops(root)
    for p in tops:
        if re.fullmatch(r"1\.\s*" + re.escape(SAMPLE_NAME), _ptext(p)):
            rb._set_para(p, f"1.{d.name}")
    tops = _tops(root)
    i_ov = next((i for i, p in enumerate(tops) if _ptext(p).replace(" ", "") == "전경사진"), None)
    full = lambda p: re.sub(r"\s", "", "".join(x.text or "" for x in p.iter(T)))  # noqa: E731 — 표 안 글까지(간지 표 첫 칸은 비어 있음)
    i_end = next((i for i, p in enumerate(tops) if i > (i_ov or 0) and _tables_in(p) and not list(p.iter(f"{{{HP}}}pic")) and full(p).startswith("부록3")), None)
    if i_ov is not None and i_end is not None:
        _del(root, tops[i_ov:i_end])


def _tables_in(p) -> list:
    return list(p.iter(f"{{{HP}}}tbl"))


def _cell0(p) -> str:
    t = next(iter(_tables_in(p)), None)
    return rb._cell_text(rb._cells(t).get((0, 0), t)) if t is not None else ""


def fill_header_only(doc: Hwpx, d: Data) -> None:
    doc.replace_all(SAMPLE_TITLE, d.title)


def _blank_jpg() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (255, 255, 255)).save(buf, "JPEG")
    return buf.getvalue()


# ---------- 사진첩 PDF(부록2) ----------
def album_pdf(d: Data, dest: Path) -> int:
    """전경 6장(제목 "전 경 사 진") + "주 요 손 상 및 현 황 사 진" 2×3 — 설명은 그림 바로 아래(다음 회차 wall_album.read_pdf가 읽음). 쪽 수."""
    doc = pymupdf.open()
    font = pymupdf.Font(fontfile=str(FONT)) if FONT.exists() else pymupdf.Font("helv")
    W, H = 595.3, 841.9
    cols, rows_per = 2, 3
    bw, bh = 236, 177
    gx, gy = (W - 2 * bw - 20) / 2, 60
    cap_h = 22

    def page(title: str, items: list[tuple]):
        pg = doc.new_page(width=W, height=H)
        pg.insert_font(fontname="kr", fontfile=str(FONT) if FONT.exists() else None, fontbuffer=None if FONT.exists() else font.buffer)
        pg.insert_text((W / 2 - font.text_length(title, fontsize=14) / 2, 42), title, fontsize=14, fontname="kr")
        for k, (path, cap) in enumerate(items):
            r, c = divmod(k, cols)
            x = gx + c * (bw + 20)
            y = gy + r * (bh + cap_h + 26)
            rect = pymupdf.Rect(x, y, x + bw, y + bh)
            try:
                pg.insert_image(rect, filename=str(path), keep_proportion=False)
            except Exception:  # noqa: BLE001
                pg.draw_rect(rect, color=(0.6, 0.6, 0.6))
            pg.draw_rect(rect, color=(0.3, 0.3, 0.3), width=0.5)
            tw = font.text_length(cap, fontsize=10)
            pg.insert_text((x + (bw - tw) / 2, y + bh + 15), cap, fontsize=10, fontname="kr")

    ov = d.overview[:6]
    if ov:
        page("전 경 사 진", ov)
    shots = d.shots
    for i in range(0, len(shots), cols * rows_per):
        page("주 요 손 상 및 현 황 사 진", shots[i:i + cols * rows_per])
    for i in range(0, len(d.compare), rows_per):  # 전회차 비교 사진대장(건축물 비교 사진대장처럼 — 민재형 10/21 질문2): 왼쪽 전회차 · 오른쪽 금회
        items = []
        for prev, now, cap in d.compare[i:i + rows_per]:
            items += [(prev, f"[전회차] {cap}"), (now, f"[금회] {cap}")]
        page("전 회 차 비 교 사 진", items)
    if not ov and not shots:
        return 0
    doc.save(dest, garbage=3, deflate=True)
    n = doc.page_count
    doc.close()
    return n


# ---------- 합치기 ----------
HEADS = [("제 1 장  정기점검 개요", "제1장정기점검개요"), ("1.1 과업의 목적", "1.1과업의목적"), ("1.2 과업대상 시설물 개요", "1.2과업대상시설물개요"),
         ("1.3 과업의 범위", "1.3과업의범위"), ("1.4 과업의 기간", "1.4과업의기간"), ("1.5 과업수행 흐름도", "1.5과업수행흐름도"), ("1.6 사용장비 현황", "1.6사용장비현황"),
         ("제 2 장  현장조사", "제2장현장조사"), ("2.1 개  요", "2.1개요")]


def _page_map(pdfs: list[tuple[str, Path]], d: Data) -> dict[str, int]:
    """본문 부분 PDF들(순서대로)에서 목차 제목이 처음 나오는 쪽(이어진 번호) — 간지(글 몇 줄뿐)는 뺌."""
    out: dict[str, int] = {}
    n = 0
    wants = set()
    for key, pdf in pdfs:
        with pymupdf.open(pdf) as doc:
            for i, pg in enumerate(doc):
                lines = [" ".join(x.split()) for x in pg.get_text().splitlines() if x.strip()]
                big = len(lines) > 12
                for ln in lines:
                    k = re.sub(r"\s+", "", ln)
                    if k.startswith("제") and re.match(r"제\d+장", k) and not big:
                        if re.match(r"제\d+장\S*$", k):
                            k2 = k
                            out.setdefault(k2, n + i + 1)
                    m = re.match(r"(\d+\.\d+)([^\d].*)$", k)
                    if m and big and len(k) < 40:
                        out.setdefault(k, n + i + 1)
                        wants.add(k)
                    if re.match(r"제\d+장", k) and big:
                        out.setdefault(k, n + i + 1)
            n += doc.page_count
    return out


def build(db, r, f, folder: Path, say=None, reuse: bool = False) -> tuple[Path, list[str], int]:
    """옹벽 한 곳 보고서 → (합본 PDF, 알림, 바꾼 수). folder = 회차 폴더. say(msg)로 진행 글. reuse = 부분 PDF가 있으면 다시 안 만듦(시험용)."""
    from server.contract_docs import hwp_queue

    say = say or (lambda m: None)
    missing = ready()
    if missing:
        raise RuntimeError("옹벽 원본 부분 파일이 없습니다: " + ", ".join(missing))
    d = gather(db, r, f)
    parts_dir = folder / "부분"
    parts_dir.mkdir(parents=True, exist_ok=True)
    if not reuse:
        for old in parts_dir.glob("*"):
            old.unlink(missing_ok=True)
    base = f"{r.year}년 {r.half} 정기안전점검 보고서_{f.name}"
    order = [("cover", fill_cover), ("summary", fill_summary), ("front", fill_front), ("intro", fill_intro)]         + ([("survey", fill_header_only)] if d.template3 else []) + [("chapter", fill_chapter), ("conclusion", fill_conclusion), ("appendix", fill_appendix)]
    pdfs: dict[str, Path] = {}
    counts: dict[str, int] = {}
    page_no = 1
    changed = 0
    for key, fn in order:
        src = TEMPLATE_DIR / PART_FILES["chapter3" if key == "chapter" and d.template3 else "chapter2" if key == "chapter" else key]
        if reuse and (parts_dir / f"{key}.pdf").exists():
            pdfs[key] = parts_dir / f"{key}.pdf"
            with pymupdf.open(pdfs[key]) as pd:
                counts[key] = pd.page_count
            if key in BODY:
                page_no += counts[key]
            continue
        say(f"{key} 채우는 중…")
        doc = Hwpx(src)
        fn(doc, d)
        if key in BODY:
            doc.start_page(page_no)
        hx = doc.save(parts_dir / f"{key}.hwpx", drop_unused=(key in ("front", "appendix", "chapter")))
        say(f"{key} PDF로 바꾸는 중…")
        pdf = parts_dir / f"{key}.pdf"
        pdf.write_bytes(hwp_queue.convert_via_worker(hx.read_bytes(), ".hwpx", wait=600))
        with pymupdf.open(pdf) as pd:
            counts[key] = pd.page_count
        if key in BODY:
            page_no += counts[key]
        pdfs[key] = pdf
        changed += 1
    # 목차(본문 쪽 번호로)
    pages = _page_map([(k, pdfs[k]) for k in ("intro", "survey", "chapter", "conclusion") if k in pdfs], d)
    doc = Hwpx(TEMPLATE_DIR / PART_FILES["toc"])
    n_toc = fill_toc(doc, d, pages)
    hx = doc.save(parts_dir / "toc.hwpx")
    pdfs["toc"] = parts_dir / "toc.pdf"
    pdfs["toc"].write_bytes(hwp_queue.convert_via_worker(hx.read_bytes(), ".hwpx", wait=300))
    # 사진첩
    album = parts_dir / "album.pdf"
    n_album = album_pdf(d, album)
    # 합치기
    out = pymupdf.open()
    for key in ("cover", "summary", "front", "toc", "intro", "survey", "chapter", "conclusion", "appendix"):
        if key not in pdfs:
            continue
        with pymupdf.open(pdfs[key]) as part:
            out.insert_pdf(part)
    merged: list[str] = []
    _insert_after(out, ("부록1", "관리대장"), [Path(f.ledger_pdf)] if f.ledger_pdf and Path(f.ledger_pdf).exists() else [], merged, "시설물관리대장")
    if n_album:
        _insert_after(out, (f"1.{f.name}".replace(" ", ""),), [album], merged, "외관조사 사진첩", squash=True)
    from core.models_web import SitokContract
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    if c and c.contract_pdf and Path(c.contract_pdf).exists():
        _insert_after(out, ("계약서",), [Path(c.contract_pdf)], merged, "계약서")
    pdf_out = folder / f"{base}.pdf"
    out.save(pdf_out, garbage=3, deflate=True)
    out.close()
    warn = list(d.warn)
    if not d.overview:
        warn.append("전경사진이 없어 전경 칸이 비었습니다")
    if not pages:
        warn.append("목차 쪽 번호를 못 찾아 견본 숫자 그대로입니다")
    elif n_toc:
        merged.append(f"목차 쪽 번호 {n_toc}곳")
    if d.template3:
        warn.append("3종 안전등급 평가표(1.5)는 아직 견본 값 그대로입니다 — 다음 단계")
    if merged:
        warn.append("끼운 것: " + ", ".join(merged))
    return pdf_out, warn, changed


def _insert_after(doc, keys: tuple, srcs: list[Path], merged: list, label: str, squash: bool = False) -> None:
    """간지 쪽(글 짧고 keys가 다 든 쪽) 뒤에 PDF들을 끼움."""
    if not srcs:
        return
    page = None
    for i in range(len(doc)):
        text = doc[i].get_text()
        t = re.sub(r"\s+", "", text) if squash else text
        if squash and not re.fullmatch("(" + "|".join(re.escape(k) for k in keys) + ")+", t):
            continue  # 간지 = 그 글(머리말·꼬리말 반복)만 있는 쪽 — 서두 결과표 제목 쪽에 끼워지지 않게
        if all(k in t for k in keys) and len(text.strip()) < 80:
            page = i
            break
    if page is None:
        return
    at = page + 1
    for src in srcs:
        with pymupdf.open(src) as add:
            doc.insert_pdf(add, start_at=at)
            at += len(add)
    merged.append(label)
