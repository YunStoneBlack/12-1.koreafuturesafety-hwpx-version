"""시특법 여러 동 한 권(2026-10-12 판 다시 잡기 ② — 견본 바탕화면 `시특법 견본\\숭의교회\\` 본관 + B동 260쪽).

동마다 회차를 따로 만들고(report_build) 한 권으로 합친다 — merge(parts, dest, 묶음 이름, 묶음 용역명):
- 첫 구역: 표지·책등·제출문·명단·목차는 첫 동 것 하나. 결과표·요약표·위치도/전경 묶음은 동마다(같은 종류끼리 이어서, 제목에 "1."·"2.").
  목차 Ⅱ. 시설물편에 "제 N장. 동 이름"·"N.x" 줄.
- 공통편: 일반현황 표에 동마다 줄 + 합계, 끝의 "Ⅱ. 시설물편" 간지 표에 "제N장 | 동 이름".
- 시설물편: 2동째부터 장 표지~부록 앞을 복사해 "제 N 장"·"N.x"로, 구역 설정·쪽 번호 새로 시작(견본은 2장이 38쪽부터 다시 — 복사 흔적)은 뺌.
- 용역명: 동마다 다른 용역명은 결과표에만 두고 나머지(머리글·제출문·명단)는 묶음 용역명.
- 다른 동 파일의 그림은 이름을 바꿔 옮김(같은 원본에서 만들어 글자 모양 번호는 같음).
split(src, k, dest) = 거꾸로 — 묶음 보고서(이미 낸 것)에서 k번째 동만 남긴 한 동짜리(다음 회차가 그 동 데이터를 가져가게).
"""
from __future__ import annotations

import copy
import random
import re
import zipfile
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb
from server.sitok.borders import Borders
from server.sitok.borders import defs as border_defs

HP = rb.HP
CORE = rb.CORE
MEDIA = {".jpg": "image/jpg", ".jpeg": "image/jpg", ".png": "image/png", ".bmp": "image/bmp", ".gif": "image/gif", ".tif": "image/tif", ".tiff": "image/tif"}


def _tops(root) -> list:
    return [p for p in root if p.tag == f"{{{HP}}}p"]


def _tables(p) -> list:
    return [x for x in p.iter(f"{{{HP}}}tbl") if next(x.iterancestors(f"{{{HP}}}tbl"), None) is None]


def _head(p) -> str:
    return " ".join(rb._cell_text(rb._cells(t).get((0, 0), t)) for t in _tables(p))


TITLES = ("정기안전점검 결과표", "실시결과 요약표", "위치도 및 전경사진")


def _overview_end(tops: list, s: int) -> int:
    """위치도·전경 묶음 끝 — 제목 뒤 마지막 위치도/전경 표 다음(사이 빈 문단은 포함, 뒤 빈 쪽 나눔은 빼고)."""
    last = s
    for i in range(s + 1, len(tops)):
        x = rb._top_text(tops[i]).strip()
        if x.endswith(TITLES):
            break
        h = _head(tops[i])
        if "위치도" in h or "전경사진" in h:
            last = i
        elif x or _tables(tops[i]):
            break
    return last + 1


def _front_blocks(root) -> dict[str, tuple[int, int]]:
    """첫 구역 동별 묶음 위치 {"result"|"summary"|"overview": (시작, 끝)} — 제목 문단부터 다음 묶음 제목 앞까지."""
    tops = _tops(root)
    t = [rb._top_text(p).strip() for p in tops]
    rs = next(i for i, x in enumerate(t) if x.endswith(TITLES[0]))
    ss = next(i for i, x in enumerate(t) if i > rs and x.endswith(TITLES[1]))
    os_ = next(i for i, x in enumerate(t) if i > ss and x.endswith(TITLES[2]))
    return {"result": (rs, ss), "summary": (ss, os_), "overview": (os_, _overview_end(tops, os_))}


def _toc2(root) -> tuple[int, int]:
    """목차 Ⅱ. 시설물편의 장·절 줄 (시작, 끝)."""
    tops = _tops(root)
    t = [rb._top_text(p).strip() for p in tops]
    s = next(i for i, x in enumerate(t) if x.startswith("Ⅱ")) + 1
    e = s
    while e < len(t) and not t[e].startswith(("▣", "부록")):
        e += 1
    while e > s and not re.match(r"^(제\s*\d+\s*장|\d+\.\d+)", t[e - 1]):
        e -= 1
    return s, e


def _appendix(root) -> int:
    """시설물편 구역에서 부록 간지 문단 번호."""
    tops = _tops(root)
    for i, p in enumerate(tops):
        txt = " ".join(rb._cell_text(c) for t in _tables(p) for c in rb._cells(t).values()).replace(" ", "")
        if "부록" in txt and "시설물관리대장" in txt and "사진첩" in txt:
            return i
    return len(tops)


def _chapters(root) -> list[tuple[int, int]]:
    """시설물편 장 [(시작, 끝)] — 장 표지 문단("제 N 장" 표 + 쪽 숨김)마다."""
    tops = _tops(root)
    stop = _appendix(root)
    starts = [i for i, p in enumerate(tops[:stop]) if re.search(r"제\s*\d+\s*장", " ".join(rb._cell_text(c) for t in _tables(p) for c in rb._cells(t).values())[:60])
              and next(p.iter(f"{{{HP}}}pageHiding"), None) is not None]
    return [(s, starts[k + 1] if k + 1 < len(starts) else stop) for k, s in enumerate(starts)]


def _renew_ids(el) -> None:
    """복사한 표·그림·도형에 새 id(같은 id가 둘이면 한글이 하나를 잃을 수 있음)."""
    for x in el.iter():
        if x.get("id") and (x.tag in (f"{{{HP}}}tbl", f"{{{HP}}}pic") or x.get("zOrder") is not None):
            x.set("id", str(random.randint(10 ** 9, 2 * 10 ** 9)))
        if x.get("instid"):
            x.set("instid", str(random.randint(10 ** 7, 10 ** 8)))


class _Bins:
    """다른 동 파일의 그림을 이 파일로 — 새 이름(g{k}_원래이름). borders(이 파일 테두리 모양)를 주면 칸 테두리 번호도 정의 기준으로 이 파일 번호로
    (동마다 줄 복사 테두리 모양을 따로 더해 번호가 서로 다를 수 있음, 10/15)."""

    def __init__(self, borders: Borders | None = None):
        self.add: dict[str, tuple[str, bytes]] = {}
        self.borders = borders
        self._defs: dict[int, dict[str, str]] = {}

    def take(self, el, z: zipfile.ZipFile, k: int) -> None:
        hrefs = dict(re.findall(r'<opf:item id="([^"]+)" href="([^"]+)"', z.read("Contents/content.hpf").decode("utf-8")))
        for img in el.iter(f"{{{CORE}}}img"):
            old = img.get("binaryItemIDRef")
            if not old:
                continue
            new = f"g{k}_{old}"
            if new not in self.add and hrefs.get(old) in z.namelist():
                self.add[new] = (Path(hrefs[old]).suffix.lower() or ".jpg", z.read(hrefs[old]))
            img.set("binaryItemIDRef", new)
        if self.borders is not None:
            if k not in self._defs:
                self._defs[k] = border_defs(z.read("Contents/header.xml").decode("utf-8"))
            d = self._defs[k]
            for x in el.iter():
                old = x.get("borderFillIDRef")
                if old and old in d and self.borders.by_id.get(old) != d[old]:
                    x.set("borderFillIDRef", self.borders.adopt(d[old]))


def _sub_pieces(el, pat: str, repl, first_only: bool = False) -> int:
    n = 0
    for t in el.iter(rb.T):
        for pc in rb._pieces(t):
            new = re.sub(pat, repl, pc.text)
            if new != pc.text:
                pc.text = new
                n += 1
                if first_only:
                    return n
    return n


def _renum_chapter(paras: list, k: int) -> None:
    """복사한 장: "제 1 장"·"제 1장." → k, 절 제목·장 표지 소목차 "1.x(.y)" → "k.x(.y)", 쪽 번호 새로 시작·구역 설정 빼기."""
    for p in paras:
        for el in list(p.iter(f"{{{HP}}}secPr", f"{{{HP}}}newNum")):
            if el.tag.endswith("newNum") and el.get("numType") != "PAGE":
                continue
            par = el.getparent()
            par.remove(el)
            if par.tag == f"{{{HP}}}ctrl" and not len(par):
                par.getparent().remove(par)
        for el in list(p.iter(f"{{{HP}}}colPr")):  # 구역 설정과 같이 있던 단 설정
            par = el.getparent()
            if par.tag == f"{{{HP}}}ctrl":
                par.getparent().remove(par)
        _sub_pieces(p, r"(제\s*)1(\s*장)", rf"\g<1>{k}\g<2>")
        if re.match(r"^\s*1\.\d+", rb._top_text(p)):
            _sub_pieces(p, r"^(\s*)1\.(?=\d)", rf"\g<1>{k}.", first_only=True)
        for t in _tables(p):  # 장 표지 소목차 칸
            for tc in rb._cells(t).values():
                if re.match(r"^1\.\d+\s", rb._cell_text(tc)):
                    _sub_pieces(tc, r"^(\s*)1\.(?=\d)", rf"\g<1>{k}.", first_only=True)


def _is_result(tbl) -> bool:
    texts = {k: rb._cell_text(v).replace(" ", "") for k, v in rb._cells(tbl).items()}
    return texts.get((1, 0)) == "용역명" and texts.get((1, 4)) == "점검기간" and texts.get((2, 0)) == "관리주체명"


def _replace_titles(root, titles: list[str], group_title: str) -> None:
    """동 용역명 → 묶음 용역명(결과표 칸 안은 그대로 — 동마다 다름)."""
    skip = {id(t) for tbl in root.iter(f"{{{HP}}}tbl") if _is_result(tbl) for t in tbl.iter(rb.T)}
    for t in root.iter(rb.T):
        if id(t) in skip:
            continue
        for pc in rb._pieces(t):
            s = pc.text
            for old in titles:
                if old and old != group_title and old in s:
                    s = s.replace(old, group_title)
            if s != pc.text:
                pc.text = s


def _general_table(root, rows: list[list[str]], total: str) -> None:
    """공통편 일반현황(구분|건물명|준공연도|건물층수|연면적|구조형식 + 합계) — 동마다 줄."""
    for tbl in root.iter(f"{{{HP}}}tbl"):
        c = rb._cells(tbl)
        head = "".join(rb._cell_text(c[k]) for k in c if k[0] == 0).replace(" ", "")
        if not ("건물명" in head and "준공" in head and tbl.get("colCnt") == "6"):
            continue
        trs = tbl.findall(f"{{{HP}}}tr")
        body, tail = trs[1:-1], trs[-1]
        tmpl = body[0]
        for tr in body[1:]:
            tbl.remove(tr)
        last = tmpl
        for _ in rows[1:]:
            tr = copy.deepcopy(tmpl)
            last.addnext(tr)
            last = tr
        h = 0
        for i, tr in enumerate(tbl.findall(f"{{{HP}}}tr")):
            for tc in tr.findall(f"{{{HP}}}tc"):
                tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(i))
            if 0 < i <= len(rows):
                for k, tc in enumerate(tr.findall(f"{{{HP}}}tc")):
                    rb._set_lines(tc, [rows[i - 1][k] if k < len(rows[i - 1]) else "-"])
                h += int(tr.findall(f"{{{HP}}}tc")[0].find(f"{{{HP}}}cellSz").get("height"))
        tcs = tail.findall(f"{{{HP}}}tc")
        area = next((tc for tc in tcs if tc.find(f"{{{HP}}}cellAddr").get("colAddr") == "4"), None)
        if area is not None:
            rb._set_lines(area, [total])
        old = int(tbl.get("rowCnt"))
        n = len(rows) + 2
        tbl.set("rowCnt", str(n))
        for cz in tbl.iter(f"{{{HP}}}cellzone"):
            if int(cz.get("endRowAddr", "0")) >= old - 1:
                cz.set("endRowAddr", str(n - 1))
        sz = tbl.find(f"{{{HP}}}sz")
        if sz is not None and len(rows) > 1:
            sz.set("height", str(int(sz.get("height")) + h // len(rows) * (len(rows) - 1)))
        return


def _divider_table(root, names: list[str]) -> None:
    """공통편 끝 "Ⅱ. 시설물편" 간지 표(제1장 | 이름, 빈 줄들) — 동마다 한 줄."""
    for tbl in root.iter(f"{{{HP}}}tbl"):
        c = rb._cells(tbl)
        if re.sub(r"\s", "", rb._cell_text(c.get((0, 0), tbl))) == "제1장" and tbl.get("colCnt") == "2":
            for i, name in enumerate(names):
                if (i, 0) in c and (i, 1) in c:
                    rb._set_lines(c[(i, 0)], [f"제{i + 1}장"])
                    rb._set_lines(c[(i, 1)], [name])
            return


def cover_name(parts: list[dict], group_name: str) -> str:
    """표지 "○○에 대한"의 ○○ — 묶음이면 "1장 시설물명 등 N개소"(10/19 민재형, 보고서 분권도 동 개수 기준으로 같게), 한 동이면 그 이름."""
    return f"{parts[0]['name']} 등 {len(parts)}개소" if len(parts) > 1 else (parts[0]["name"] if parts else group_name)


def merge(parts: list[dict], dest: Path, group_name: str, group_title: str) -> list[str]:
    """parts = [{hwpx, name, title, row: [구분, 건물명, 준공연도, 층수, 연면적, 구조], area: float}] 동 순서(첫 동 = 대표). 안내를 돌려줌."""
    notes: list[str] = []
    zs = [zipfile.ZipFile(p["hwpx"]) for p in parts]
    bins = _Bins(Borders(zs[0].read("Contents/header.xml").decode("utf-8")))
    try:
        secs = rb._sections(zs[0])
        roots = [etree.fromstring(zs[0].read(n)) for n in secs]
        others = [[etree.fromstring(z.read(n)) for n in rb._sections(z)] for z in zs[1:]]
        # --- 첫 구역: 동별 묶음
        front = roots[0]
        blocks = _front_blocks(front)
        tops = _tops(front)
        anchors = {kind: tops[e - 1] for kind, (s, e) in blocks.items()}
        titles = {kind: tops[s] for kind, (s, e) in blocks.items()}
        for kind in ("result", "summary", "overview"):
            _prefix_title(titles[kind], kind, 1, parts[0]["name"])
        for k, (part, oroots) in enumerate(zip(parts[1:], others), 2):
            otops = _tops(oroots[0])
            ob = _front_blocks(oroots[0])
            for kind in ("result", "summary", "overview"):
                s, e = ob[kind]
                copies = [copy.deepcopy(p) for p in otops[s:e]]
                _prefix_title(copies[0], kind, k, part["name"])
                for q in copies:
                    _renew_ids(q)
                    bins.take(q, zs[k - 1], k)
                last = anchors[kind]
                for q in copies:
                    last.addnext(q)
                    last = q
                anchors[kind] = last
        # 목차 Ⅱ. 시설물편
        s, e = _toc2(front)
        last = _tops(front)[e - 1]
        for k, oroots in enumerate(others, 2):
            os_, oe = _toc2(oroots[0])
            for p in [copy.deepcopy(q) for q in _tops(oroots[0])[os_:oe]]:
                _sub_pieces(p, r"(제\s*)1(\s*장)", rf"\g<1>{k}\g<2>", first_only=True)
                _sub_pieces(p, r"^(\s*)1\.(?=\d)", rf"\g<1>{k}.", first_only=True)
                last.addnext(p)
                last = p
        # 표지 "○○에 대한" = "1장 시설물명 등 N개소에 대한"(10/19 형 — 1개 동은 시설물명(FMS) 그대로), 책등 이름 → 묶음 이름
        for p in _tops(front):
            m = re.fullmatch(r"\s*(.+?)에\s*대한\s*", rb._top_text(p))
            if m:
                rb._set_para(p, f"{cover_name(parts, group_name)}에 대한")
                break
        for tbl in front.iter(f"{{{HP}}}tbl"):
            if "︻" in "".join(rb._cell_text(c) for c in rb._cells(tbl).values()):
                _sub_pieces(tbl, re.escape(parts[0]["name"]), group_name)
        # --- 공통편
        with rb.using_borders(bins.borders):  # 동 수만큼 줄 복사 — 맞닿는 선 얇게(10/15)
            _general_table(roots[1], [p["row"] for p in parts], f"{sum(p.get('area') or 0 for p in parts):,.2f}㎡")
            _divider_table(roots[1], [p["name"] for p in parts])
        # --- 시설물편: 2동째부터 장 복사
        body = roots[2]
        app = _tops(body)[_appendix(body)]
        for k, oroots in enumerate(others, 2):
            ch = _chapters(oroots[2])
            if not ch:
                notes.append(f"{parts[k - 1]['name']}: 시설물편 장을 찾지 못했습니다")
                continue
            s, e = ch[0]
            copies = [copy.deepcopy(p) for p in _tops(oroots[2])[s:e]]
            _renum_chapter(copies, k)
            for q in copies:
                _renew_ids(q)
                bins.take(q, zs[k - 1], k)
                app.addprevious(q)
        # --- 용역명 → 묶음 용역명(결과표 칸 말고)
        for root in roots:
            _replace_titles(root, [p["title"] for p in parts], group_title)
            for el in list(root.iter(f"{{{HP}}}linesegarray")):
                el.getparent().remove(el)
        # --- 쓰기
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zs[0].infolist():
                data = zs[0].read(info.filename)
                if info.filename in secs:
                    data = etree.tostring(roots[secs.index(info.filename)], xml_declaration=True, encoding="UTF-8", standalone=True)
                elif info.filename == "Contents/content.hpf":
                    items = "".join(f'<opf:item id="{k}" href="BinData/{k}{ext}" media-type="{MEDIA.get(ext, "image/jpg")}" isEmbeded="1"/>'
                                    for k, (ext, _) in bins.add.items())
                    data = data.decode("utf-8").replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8")
                elif info.filename == "Contents/header.xml":
                    data = bins.borders.result(data.decode("utf-8")).encode("utf-8")
                elif info.filename == "Preview/PrvImage.png":
                    continue
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
            for k, (ext, b) in bins.add.items():
                zout.writestr(f"BinData/{k}{ext}", b, compress_type=zipfile.ZIP_STORED)
        tmp.replace(dest)
    finally:
        for z in zs:
            z.close()
    return notes


def _prefix_title(p, kind: str, k: int, name: str) -> None:
    """동별 묶음 제목 — "1.○○ 정기안전점검 결과표" / "1.○○ 정기안전점검 실시결과 요약표" / "1.○○의 위치도 및 전경사진"(견본 모양)."""
    text = {"result": f"{k}.{name} 정기안전점검 결과표", "summary": f"{k}.{name} 정기안전점검 실시결과 요약표",
            "overview": f"{k}.{name}의 위치도 및 전경사진"}[kind]
    rb._set_para(p, text)


def split(src: Path, k: int, dest: Path) -> None:
    """묶음 보고서 → k번째 동(1부터)만 남긴 한 동짜리 — 결과표·요약표·위치도/전경은 k번째 묶음만, 시설물편은 k번째 장만(번호는 그대로).
    다음 회차가 그 동의 결과표·1.2.6·1.2.7·시설물 현황·1.3 글·전경사진을 가져가게(이미 낸 묶음 보고서 등록)."""
    with zipfile.ZipFile(src) as z:
        secs = rb._sections(z)
        roots = [etree.fromstring(z.read(n)) for n in secs]
        front = roots[0]
        tops = _tops(front)
        t = [rb._top_text(p).strip() for p in tops]
        for suffix in TITLES:
            starts = [i for i, x in enumerate(t) if x.endswith(suffix)]
            if len(starts) < 2:
                continue
            spans = []
            for s in starts:
                if suffix == TITLES[2]:
                    e = _overview_end(tops, s)
                else:
                    e = s + 1
                    while e < len(t) and not t[e].endswith(TITLES):
                        e += 1
                spans.append((s, e))
            for j, (s, e) in enumerate(spans, 1):
                if j != k:
                    for p in tops[s:e]:
                        if p.getparent() is not None:
                            p.getparent().remove(p)
        body = roots[2]
        btops = _tops(body)
        for j, (s, e) in enumerate(_chapters(body), 1):
            if j != k:
                for p in btops[s:e]:
                    if j == 1 and p is btops[s]:  # 첫 장 표지 문단엔 구역 설정이 있어 남김(글만)
                        continue
                    p.getparent().remove(p)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in z.infolist():
                data = z.read(info.filename)
                if info.filename in secs:
                    data = etree.tostring(roots[secs.index(info.filename)], xml_declaration=True, encoding="UTF-8", standalone=True)
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
