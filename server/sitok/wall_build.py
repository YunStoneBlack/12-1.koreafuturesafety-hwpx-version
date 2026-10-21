"""옹벽 정기안전점검 보고서 만들기(2026-10-20 옹벽 3단계 — 한 곳짜리, 10/21 한 파일 방식). 건축물 정기(report_build)처럼 **회사 원본 한 파일**을 채워
한글 한 파일(out_hwpx) → 작업 프로그램이 PDF → 목차 쪽 번호 넣어 한 번 더 PDF → 관리대장·사진첩·계약서 PDF를 간지 뒤에 끼움(out_pdf).
원본 = master.master_path("옹벽") = data/_시특법/_회사템플릿/정기안전점검_옹벽_원본.hwpx(10/21 민재형이 부분 11개를 구역 나누기로 한 파일로 합쳐 줌 —
설정 탭 "옹벽 정기안전점검 원본"에서 받기·올리기). 10/20~21 부분 파일 11개 방식(부분마다 PDF로 바꿔 합침)은 이걸로 바꿈(한글 한 파일을 줄 수 있고 4단계 묶음·분권이
건축물 merge 방식 그대로 되게 — 형 10/21).

원본 구역(locate가 글로 찾음 — 순서가 바뀌어도 됨): 표지 / 서두(제출문·명단·위치도·결과표·전경) / 요약문 / 목차 / 제Ⅰ편(1장 개요 + 2장 현장조사, 2.2 상태평가는 3종만) /
제Ⅱ편 시설물편(3종 — 1.6 안전등급 평가, 2종은 뺌) / 제Ⅲ편 종합결론 / 부록(표지·부록1~3 간지·견본 사진첩) / 부록4 간지 / 과업수행계획서(끝에 부록5 간지) /
사전검토보고서(끝에 부록6 간지·자격·수료증·계약서 간지). 과업지시서·과업수행계획서·사전검토보고서 본문(견본 17곳 것)은 지금 뺌(간지만 남김 — 뒤 단계).
- 쪽 번호: 요약문·제Ⅰ편 첫 "새 번호로 시작"(newNum PAGE)만 두고 나머지(2장 9·시설물편 15)는 지워 본문이 이어지게.
- 목차: 첫 PDF에서 제목이 있는 쪽의 꼬리말 번호를 읽어 숫자만 바꿈(줄 끝 tab 뒤 조각), 제Ⅱ편은 제1장 한 줄, 3종은 1.6 안전등급 평가 줄 더함.
- 서두: 제출문·참여기술자 명단 + 결과표(1개) + 전경사진(1개) — 견본의 위치도 4장·결과표 17개·전경 17개 중 첫 것만 남기고 지움(안 쓰는 BinData도 지움).
- 시설물편: 1.1 결과표·1.2.1 현황표(관리대장 제원 wall_ledger)·1.2.2 위치도(locmap)·1.2.3 전경 6장·1.3.2 점검 이력·1.4.1~1.4.4 글(AI wall_ai)·사진 표 4장씩·
  1.4.5 요약표·1.5 이름·개략공사비·종합결론. 3종 1.6 안전등급 평가 표는 아직 견본 값 그대로(5단계).
- 부록: 간지만 남기고(견본 사진 쪽 지움) 관리대장 PDF·사진첩 PDF(pymupdf로 그림 — 전경 6 + 주요 손상 및 현황 사진 2×3 + 전회차 비교, 설명은 그림 바로 아래 →
  다음 회차 wall_album.read_pdf가 읽음)·계약서 PDF를 간지 뒤에 끼움.
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

from core.stored_path import to_full

from server.sitok import wall_ai, wall_ledger, wall_manual
from server.sitok import report_build as rb
from server.sitok.report_build import HP, T

FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
SAMPLE_TITLE = "2026년 상반기 산업단지 옹벽 정기안전점검 용역"
SAMPLE_NAME = "보강토옹벽-2"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
PDF_WAIT = 900  # 한 파일 PDF(형 합본 그대로 139쪽 61초 — 10/21)


def master_path() -> Path:
    from server.sitok import master
    return master.master_path("옹벽")


def ready() -> list[str]:
    """없는 원본 파일 이름(있으면 빈 목록)."""
    p = master_path()
    return [] if p.exists() else [p.name]


# ---------- 원본 hwpx(구역 여럿) ----------
def _sq(s: str) -> str:
    return re.sub(r"\s", "", s or "")


class Hwpx:
    """원본 hwpx 한 파일 — 구역(section)·바탕쪽(masterpage) root를 고치고 그림을 더해 저장. 안 쓰는 구역은 빼고(drop) 안 쓰는 BinData도 뺌.
    구역 번호 순서(section10이 section2 앞에 오지 않게). 구역은 이름(Contents/sectionN.xml)으로 다룸 — 복제(clone_section)하면 번호가 밀리므로."""

    def __init__(self, src: Path):
        self.src = src
        with zipfile.ZipFile(src) as z:
            self.sections = sorted((n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)), key=lambda n: int(re.search(r"\d+", n)[0]))
            self.masters = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/masterpage\d+\.xml", n))  # 바탕쪽 — 머리말 용역명·장 꼬리말이 여기(10/21)
            self.roots = {s: etree.fromstring(z.read(s)) for s in self.sections + self.masters}
            self.hpf = z.read("Contents/content.hpf").decode("utf-8")
            header = z.read("Contents/header.xml")
            # header.xml 테두리/배경 정의(borderFill 그림 무늬 imgBrush)가 쓰는 그림 — "안 쓰는 그림"으로 빼면 한글이 테두리 정의를 잘못 읽어 표 선·칠이 어긋남(10/21 형 "표 선이 이상")
            self.header_refs = set(re.findall(r'binaryItemIDRef="([^"]+)"', header.decode("utf-8")))
            self.header = etree.fromstring(header)  # 글자 모양(charPr) 복제용(10/21 표지·책등 자간·크기)
        self.dropped: set[str] = set()
        self.new_masters: list[str] = []  # 복제한 바탕쪽(장마다 꼬리말 "제 N 장 이름")
        self.added: list[tuple[str, bytes]] = []
        self.run = datetime.datetime.now().strftime("%y%m%d%H%M%S") + f"{random.randint(0, 999):03d}"

    @property
    def root(self):
        return self.roots[self.sections[0]]

    def view(self, name: str) -> "_View":
        return _View(self, name)

    def text(self, name: str) -> str:
        """구역 글 전부(표 안 포함) 띄어쓰기 없이."""
        return _sq("".join(x.text or "" for x in self.roots[name].iter(T)))

    def masters_of(self, name: str) -> list[str]:
        """구역이 가리키는 바탕쪽 파일 이름들."""
        refs = [x.get("idRef") for x in self.roots[name].iter(f"{{{HP}}}masterPage") if x.get("idRef")]
        return [f"Contents/{r}.xml" for r in refs if f"Contents/{r}.xml" in self.roots]

    def clone_section(self, name: str) -> str:
        """구역을 복제해 그 구역(과 앞선 복제들) 바로 뒤에 끼움 → 새 이름. 바탕쪽도 복제해 새 번호로 가리킴(장마다 꼬리말이 다르게), 표·그림 id 새로."""
        from server.sitok.merge import _renew_ids

        stem = name[:-4]
        n = sum(1 for s in self.sections if s.startswith(stem + "_"))
        new = f"{stem}_{n + 1}.xml"
        root = copy.deepcopy(self.roots[name])
        for mp in root.iter(f"{{{HP}}}masterPage"):
            old = f"Contents/{mp.get('idRef')}.xml"
            if old in self.roots:
                mid = f"masterpage{len(self.masters) + len(self.new_masters)}"
                mroot = copy.deepcopy(self.roots[old])
                if mroot.get("id"):
                    mroot.set("id", mid)
                self.roots[f"Contents/{mid}.xml"] = mroot
                self.new_masters.append(f"Contents/{mid}.xml")
                mp.set("idRef", mid)
        _renew_ids(root)
        self.roots[new] = root
        self.sections.insert(self.sections.index(name) + n + 1, new)
        return new

    def clone_charpr(self, cid: str, height: int | None = None, spacing: int | None = None, ratio: int | None = None) -> str:
        """header.xml 글자 모양 cid를 복제해 크기(height, 1/100pt)·자간(spacing %)·장평(ratio %)만 바꾼 새 id — 긴 이름 표지·책등."""
        HH = "http://www.hancom.co.kr/hwpml/2011/head"
        props = next(self.header.iter(f"{{{HH}}}charProperties"))
        src = next((x for x in props if x.get("id") == str(cid)), None)
        if src is None:
            return str(cid)
        new = copy.deepcopy(src)
        nid = str(max(int(x.get("id")) for x in props) + 1)
        new.set("id", nid)
        if height is not None:
            new.set("height", str(height))
        for tag, val in (("spacing", spacing), ("ratio", ratio)):
            el = new.find(f"{{{HH}}}{tag}")
            if el is not None and val is not None:
                for k in el.attrib:
                    el.set(k, str(val))
        props.append(new)
        props.set("itemCnt", str(len(props)))
        return nid

    def clone_parapr(self, pid: str, keep_with_next: bool | None = None, intent: int | None = None) -> str:
        """문단 모양 복제 — keepWithNext(다음 문단과 함께)·intent(첫 줄 들여쓰기, HWPUNIT) 바꿔 새 id."""
        HH = "http://www.hancom.co.kr/hwpml/2011/head"
        props = next(self.header.iter(f"{{{HH}}}paraProperties"))
        src = next((x for x in props if x.get("id") == str(pid)), None)
        if src is None:
            return str(pid)
        new = copy.deepcopy(src)
        nid = str(max(int(x.get("id")) for x in props) + 1)
        new.set("id", nid)
        bs = new.find(f"{{{HH}}}breakSetting")
        if bs is not None and keep_with_next is not None:
            bs.set("keepWithNext", "1" if keep_with_next else "0")
        if intent is not None:
            it = new.find(f"{{{HH}}}margin/{{http://www.hancom.co.kr/hwpml/2011/core}}intent")
            if it is not None:
                it.set("value", str(intent))
        props.append(new)
        props.set("itemCnt", str(len(props)))
        return nid

    def clone_borderfill(self, bf: str, bottom_from: str) -> str:
        """테두리 정의 bf를 복제해 아랫선만 bottom_from 것으로 — 한 줄짜리 표의 마지막 줄(첫 줄 윗선 + 마지막 줄 아랫선)."""
        HH = "http://www.hancom.co.kr/hwpml/2011/head"
        props = next(self.header.iter(f"{{{HH}}}borderFills"))
        src = next((x for x in props if x.get("id") == str(bf)), None)
        ref = next((x for x in props if x.get("id") == str(bottom_from)), None)
        if src is None or ref is None:
            return str(bf)
        key = ("bf", str(bf), str(bottom_from))
        cache = getattr(self, "_bf_cache", {})
        if key in cache:
            return cache[key]
        new = copy.deepcopy(src)
        nid = str(max(int(x.get("id")) for x in props) + 1)
        new.set("id", nid)
        nb, rb_ = new.find(f"{{{HH}}}bottomBorder"), ref.find(f"{{{HH}}}bottomBorder")
        if nb is not None and rb_ is not None:
            for k, v in rb_.attrib.items():
                nb.set(k, v)
        props.append(new)
        props.set("itemCnt", str(len(props)))
        cache[key] = nid
        self._bf_cache = cache
        return nid

    def add_image(self, path_or_bytes) -> str:
        key = f"wall{self.run}_{len(self.added) + 1}"
        self.added.append((key, path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()))
        return key

    def replace_all(self, old: str, new: str) -> int:
        """구역·바탕쪽(머리말·꼬리말) 전부에서 글자 바꾸기."""
        return sum(replace_text(r, old, new) for r in self.roots.values())

    def drop_except(self, names) -> None:
        keep = set(names)
        for s in self.sections:
            if s not in keep:
                self.dropped.add(s)
                self.roots.pop(s, None)

    def kept(self) -> list[str]:
        return [s for s in self.sections if s not in self.dropped]

    def renumber_pages(self, restart) -> None:
        """"새 번호로 시작"(hp:newNum PAGE)은 restart 구역의 첫 것만(1로) 두고 나머지는 지움 — 견본은 2장 9·시설물편 15로 박혀 있음."""
        keep = set(restart)
        for name in self.kept():
            root = self.roots[name]
            nums = [x for x in root.iter(f"{{{HP}}}newNum") if x.get("numType") == "PAGE"]
            for i, x in enumerate(nums):
                if i == 0 and name in keep:
                    x.set("num", "1")
                    continue
                parent = x.getparent()
                if parent is not None and parent.tag == f"{{{HP}}}ctrl" and len(parent) == 1:
                    parent.getparent().remove(parent)
                elif parent is not None:
                    parent.remove(x)

    @staticmethod
    def _xml(root) -> bytes:
        for el in list(root.iter(f"{{{HP}}}linesegarray")):
            el.getparent().remove(el)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def save(self, dest: Path, drop_unused: bool = True) -> Path:
        used = {img.get("binaryItemIDRef") for r in self.roots.values() for img in r.iter(f"{{{HC}}}img")} | self.header_refs
        kept = self.kept()
        rename = {old: f"Contents/section{i}.xml" for i, old in enumerate(kept)}  # 뺀 구역·복제 구역 → 번호를 차례로
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with zipfile.ZipFile(self.src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            names = set(zin.namelist())
            id_of = {}
            for it in re.findall(r"<opf:item [^>]*href=\"BinData/[^\"]+\"[^>]*/>", self.hpf):
                m = re.search(r'id="([^"]+)"', it)
                h = re.search(r'href="BinData/([^"]+)"', it)
                if m and h:
                    id_of[h[1]] = m[1]
            for info in zin.infolist():
                name = info.filename
                if name in self.dropped or name in ("Contents/content.hpf", "Preview/PrvText.txt", "Preview/PrvImage.png"):
                    continue
                data = zin.read(name)
                if name in self.roots:
                    data = self._xml(self.roots[name])
                elif name.startswith("BinData/") and drop_unused and id_of.get(name[8:]) not in used:
                    continue
                elif name == "Contents/header.xml":
                    self.header.set("secCnt", str(len(kept)))
                    data = etree.tostring(self.header, xml_declaration=True, encoding="UTF-8", standalone=True)
                out_name = rename.get(name, name)
                if out_name == name:
                    zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
                else:
                    zout.writestr(out_name, data, compress_type=zipfile.ZIP_DEFLATED)
            for name in kept + self.new_masters:  # 복제한 구역·바탕쪽(원본 zip에 없음)
                if name not in names:
                    zout.writestr(rename.get(name, name), self._xml(self.roots[name]), compress_type=zipfile.ZIP_DEFLATED)
            text = self.hpf
            if drop_unused:
                text = re.sub(r'<opf:item [^>]*href="BinData/[^"]+"[^>]*/>', lambda m: m[0] if re.search(r'id="([^"]+)"', m[0])[1] in used else "", text)
            # 목록(manifest)·순서(spine)는 구역·바탕쪽을 새로 적음
            text = re.sub(r'<opf:item id="(section|masterpage)\d+"[^>]*/>', "", text)
            text = re.sub(r'<opf:itemref idref="section\d+"[^>]*/>', "", text)
            items = "".join(f'<opf:item id="section{i}" href="Contents/section{i}.xml" media-type="application/xml"/>' for i in range(len(kept)))
            items += "".join(f'<opf:item id="{m[9:-4]}" href="{m}" media-type="application/xml"/>' for m in self.masters + self.new_masters)
            text = re.sub(r'(<opf:item id="header"[^>]*/>)', lambda m: m[1] + items, text, count=1)
            refs = "".join(f'<opf:itemref idref="section{i}" linear="yes"/>' for i in range(len(kept)))
            text = re.sub(r'(<opf:itemref idref="header"[^>]*/>)', lambda m: m[1] + refs, text, count=1)
            new = "".join(f'<opf:item id="{k}" href="BinData/{k}.jpg" media-type="image/jpg" isEmbeded="1"/>' for k, _ in self.added)
            zout.writestr("Contents/content.hpf", text.replace("</opf:manifest>", new + "</opf:manifest>").encode("utf-8"))
            texts = "\r\n".join("".join(t.text or "" for t in p.iter(T)) for n in kept for p in self.roots[n].iter(f"{{{HP}}}p"))
            zout.writestr("Preview/PrvText.txt", texts[:2000].encode("utf-8"))
            for k, b in self.added:
                zout.writestr(f"BinData/{k}.jpg", b, compress_type=zipfile.ZIP_STORED)
        tmp.replace(dest)
        return dest


class _View:
    """구역 하나(채우는 함수가 보는 것) — root는 그 구역, roots = 구역 + 그 바탕쪽(replace_here), 그림 더하기·용역명 바꾸기는 파일 전체."""

    def __init__(self, doc: Hwpx, name: str):
        self.doc, self.name = doc, name
        self.root = doc.roots[name]
        self.roots = [self.root] + [doc.roots[m] for m in doc.masters_of(name)]

    def add_image(self, path_or_bytes) -> str:
        return self.doc.add_image(path_or_bytes)

    def replace_all(self, old: str, new: str) -> int:
        return self.doc.replace_all(old, new)

    def replace_here(self, old: str, new: str) -> int:
        """이 구역과 그 바탕쪽(꼬리말 장 제목)에서만."""
        return sum(replace_text(r, old, new) for r in self.roots)

    def clone_charpr(self, cid: str, **kw) -> str:
        return self.doc.clone_charpr(cid, **kw)

    def clone_parapr(self, pid: str, **kw) -> str:
        return self.doc.clone_parapr(pid, **kw)

    def clone_borderfill(self, bf: str, bottom_from: str) -> str:
        return self.doc.clone_borderfill(bf, bottom_from)


NEEDED = ("cover", "front", "summary", "toc", "intro", "chapter", "conclusion", "appendix")


def locate(doc: Hwpx) -> dict[str, str]:
    """구역을 글로 찾음 → {역할: 구역 파일 이름}. 못 찾은 필수 구역이 있으면 RuntimeError."""
    out: dict[str, str] = {}
    for i in doc.sections:
        t = doc.text(i)
        head = t[:300]
        if "cover" not in out and "종합보고서" in head and "제출문" not in head and "요약문" not in head:
            out["cover"] = i
        elif "front" not in out and head.startswith("제출문"):
            out["front"] = i
        elif "summary" not in out and "요약문" in head:
            out["summary"] = i
        elif "toc" not in out and head.startswith("목차"):
            out["toc"] = i
        elif "intro" not in out and head.startswith("제Ⅰ편"):
            out["intro"] = i
        elif "chapter" not in out and head.startswith("제Ⅱ편"):
            out["chapter"] = i
        elif "conclusion" not in out and head.startswith("제Ⅲ편"):
            out["conclusion"] = i
        elif "app4" not in out and head.startswith("부록4"):
            out["app4"] = i
        elif "order_cover" not in out and head.startswith("과업지시서"):
            out["order_cover"] = i
        elif "order_body" not in out and head.startswith("Ⅰ.과업의목적"):
            out["order_body"] = i
        elif "plan" not in out and "과업수행계획서" in head and "과업의목적및개요" in t:
            out["plan"] = i
        elif "plan_map" not in out and head.startswith("마.과업대상시설물위치도"):
            out["plan_map"] = i
        elif "plan_body" not in out and head.startswith("과업수행방법"):
            out["plan_body"] = i
        elif "precheck" not in out and "사전검토보고서" in head and "1.과업명" in t:
            out["precheck"] = i
        elif "appendix" not in out and head.startswith("부록") and "부록1" in t:
            out["appendix"] = i
        elif "app6" not in out and "부록6.기타부록참고자료" in t and "계약서" in t:
            out["app6"] = i
        elif "app5" not in out and t.endswith("부록5.사전검토보고서"):
            out["app5"] = i
    missing = [k for k in NEEDED if k not in out]
    if missing:
        raise RuntimeError("옹벽 원본에서 구역을 못 찾았습니다: " + ", ".join(missing) + " — 시특법 설정의 옹벽 원본을 확인하세요")
    return out


def _full(p) -> str:
    return _sq("".join(x.text or "" for x in p.iter(T)))


def keep_from(view: _View, prefix: str) -> None:
    """구역에서 prefix(간지 표 글)로 시작하는 문단부터만 남김 — 첫 문단의 구역 설정(secPr·colPr·머리말·꼬리말 ctrl)은 간지 문단 앞으로 옮김(빈 첫 쪽이 안 생기게)."""
    root = view.root
    tops = _tops(root)
    i = next((i for i, p in enumerate(tops) if _full(p).startswith(prefix)), None)
    if i is None or i == 0:
        return
    first, keep = tops[0], tops[i]
    moved = []
    for run in list(first.findall(f"{{{HP}}}run")):
        if next(run.iter(f"{{{HP}}}secPr", f"{{{HP}}}colPr", f"{{{HP}}}header", f"{{{HP}}}footer"), None) is not None:
            for t in list(run.findall(T)):
                run.remove(t)
            moved.append(run)
    for j, run in enumerate(moved):
        keep.insert(j, run)
    keep.set("pageBreak", "0")
    _del(root, tops[:i])


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
    signs: list = field(default_factory=list)  # persons와 같은 순서의 서명 그림 경로(없으면 None) — 명단 "서명" 칸(10/21)
    overview: list = field(default_factory=list)  # [(path, caption)]
    locmap: Path | None = None
    sections: dict = field(default_factory=dict)  # found/front/etc/public → [(path, caption)]
    ai: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # [{period, kind, org, grade, result, note}] — 면담 창(회차 survey.history) > 관리대장
    repairs: list = field(default_factory=list)  # 1.3.3 보수·보강 이력 [{period, where(시공사), method(내용), note}] — 면담 창
    cost: tuple = ((), 0)
    shots: list = field(default_factory=list)  # 사진첩 [(path, caption)]
    compare: list = field(default_factory=list)  # 전회차 비교 사진대장 [(prev, now, caption)]
    public_names: str = ""
    template3: bool = False
    form: str = ""  # 옹벽 형식 열쇠(콘크리트·보강토·석축·돌망태 — 3종 제외항목)
    warn: list = field(default_factory=list)
    sites: list = field(default_factory=list)  # 묶음 책이면 곳마다 Data(장 순서), 한 곳이면 빈 목록
    index: int = 1  # 책 안 순서(장 번호)

    @property
    def many(self) -> list:
        return self.sites or [self]

    @property
    def start_month(self) -> str:
        """서류 표지 연월(착수 월) — "2026. 11." """
        s = self.period_start
        return f"{s.year}. {s.month:02d}." if s else self.month

    @property
    def period_days(self) -> str:
        """"2026. 11. 05 ~ 2026. 12. 20 (착수일로부터 46일간)" """
        s, e = self.period_start, self.period_end
        if not (s and e):
            return "-"
        return f"{s.year}. {s.month:02d}. {s.day:02d} ~ {e.year}. {e.month:02d}. {e.day:02d} (착수일로부터 {(e - s).days + 1}일간)"

    @property
    def grade_cell(self) -> str:
        """결과표 "등급" 칸 — 3종은 글자(A~E, 견본 "B"), 2종은 말(양호)."""
        return wall_ai.letter3(self.ai.get("grade") or self.grade, self.ai.get("items"), self.form) if self.template3 else self.grade

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


def make_book(sites: list, name: str, title: str) -> Data:
    """묶음 책의 공통 값 = 첫 곳 값에 표지 이름·용역명·곳 목록. 등급·종별 요약은 요약문·총괄표에서 곳마다."""
    import dataclasses

    b = dataclasses.replace(sites[0], name=name, title=title, sites=list(sites), template3=any(s.template3 for s in sites), warn=[])
    for s in sites:
        b.warn += [f"{s.name}: {w}" for w in s.warn]
    return b


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
    d.form = wall_manual.form_of(spec.get("form") or "", f.name, f.kind or "")
    # 사람
    ids = [x for x in [r.chief_id, *(r.participant_ids or [])] if x]
    people = {p.id: p for p in db.query(TechPerson).filter(TechPerson.id.in_(ids))} if ids else {}
    for i, pid in enumerate(ids):
        p = people.get(pid)
        if p:
            d.persons.append(("사업책임기술자" if i == 0 else "참여기술자", p.name, p.position or "", p.sitok_field or "토목", p.sitok_grade or p.grade or ""))
            sp = Path(to_full(p.sign_path)) if p.sign_path else None
            if not (sp and sp.exists()):  # 따로 올린 서명이 없으면 설정의 "서명·도장(관급 보안각서)" 그림(SubmitDoc sitok_sign)을 씀(10/21 — 두 번 안 올리게)
                from core.models_web import SubmitDoc
                row = db.query(SubmitDoc).filter(SubmitDoc.person_id == p.id, SubmitDoc.kind == "sitok_sign").first()
                sp = Path(to_full(row.file)) if row is not None and row.file else None
            d.signs.append(sp if sp and sp.exists() else None)
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
    eval_items = wall_manual.items_for(d.form) if d.template3 else None
    d.ai = dict(fin) if wall_ai.is_wall_ai(fin) else wall_ai.fallback(defects, d.prev_grade, d.public_names, eval_items, d.form)
    if not wall_ai.is_wall_ai(fin):
        d.warn.append("AI 초안이 없어 결함 목록으로 만든 기본 글로 채웠습니다 — [🤖 AI 초안]을 먼저 쓰면 좋습니다")
    elif eval_items and not d.ai.get("items"):  # 5단계 전에 만든 3종 초안 — 18항목은 결함으로 어림(저장 안 함)
        d.ai = wall_ai._with_items(d.ai, None, eval_items, d.form, defects)
        d.warn.append("AI 초안에 18항목 안전등급 평가가 없어 결함으로 어림했습니다 — [🤖 AI 초안]을 다시 쓰면 AI가 매깁니다")
    d.grade = wall_ai.word(d.ai.get("grade") or "") or d.prev_grade
    # 이력·공사비
    d.history = list((r.survey or {}).get("history") or spec.get("history") or [])
    d.repairs = list((r.survey or {}).get("repairs") or [])
    try:
        methods = SD.method_map(fin.get("methods")) if fin else None
        d.cost = SD.cost_rows(db, r.id, prices(db, r.company_id), methods)
    except Exception:  # noqa: BLE001
        d.cost = ((), 0)
    return d


# ---------- 부분마다 채우기 ----------
def _runs_of(p) -> list:
    return [r for r in p.findall(f"{{{HP}}}run")]


def _set_charpr(p, cid: str) -> None:
    for r in _runs_of(p):
        r.set("charPrIDRef", cid)


def _cover_title(tc, d: Data, last: str, doc=None) -> None:
    """표지 칸 — 견본은 문단 둘(윗줄 "ㅇㅇ에대한 2026년 상반기 정기안전점검" 작은 글자·자간 좁게 / 아랫줄 "종합보고서" 큰 글자). 문단마다 제 글자 모양을 두고 글만 바꿈
    (_set_lines로 한 문단에 몰면 아랫줄이 윗줄 모양이 됨 — 사용자 10/21). 윗줄이 길면(시설물명이 긺) "이름에 대한" / "2026년 하반기 정기안전점검" 두 줄로."""
    ps = [q for q in tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is tc]
    if not ps:
        return
    head, tail = ps[0], ps[-1] if len(ps) > 1 else None
    for q in ps[1:-1]:
        q.getparent().remove(q)
    line = f"{d.name}에 대한 {d.year}년 {d.half} 정기안전점검"
    lines = [line]
    if len(line) > 26:  # 견본 자간(-5)으로 한 줄 26자쯤 — 1) 자간 더 좁혀(-15, +10%) 29자까지, 2) 그래도 길면 두 줄(형 10/21)
        if len(line) <= 29 and doc is not None and _runs_of(head):
            _set_charpr(head, doc.clone_charpr(_runs_of(head)[0].get("charPrIDRef"), spacing=-15))
        else:
            lines = [f"{d.name}에 대한", f"{d.year}년 {d.half} 정기안전점검"]
    rb._set_para(head, lines[0], in_table=True)
    anchor = head
    for extra in lines[1:]:
        q = copy.deepcopy(head)
        rb._set_para(q, extra, in_table=True)
        anchor.addnext(q)
        anchor = q
    if tail is not None:
        rb._set_para(tail, last, in_table=True)
    else:
        q = copy.deepcopy(head)
        rb._set_para(q, last, in_table=True)
        anchor.addnext(q)


def fill_cover(doc: Hwpx, d: Data) -> None:
    root = doc.root
    big = _tbl(root, 11, 1)
    if big is not None:
        inner = next(t for t in big.iter(f"{{{HP}}}tbl") if t is not big)
        _cover_title(rb._cells(inner)[(0, 0)], d, "종합보고서", doc)
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
        _fit_spine(doc, cells, f"{d.name}에 대한", f"{d.year}년 {d.half} 정기안전점검")


def _char_pr(doc, cid: str) -> tuple[int, int]:
    """(글자 크기 height, 자간 spacing %) — header.xml."""
    HH = "http://www.hancom.co.kr/hwpml/2011/head"
    x = next((c for c in doc.doc.header.iter(f"{{{HH}}}charPr") if c.get("id") == str(cid)), None)
    if x is None:
        return 1300, 20
    sp = x.find(f"{{{HH}}}spacing")
    return int(x.get("height") or 1300), int(sp.get("hangul") or 0) if sp is not None else 0


def _fit_spine(doc, cells: dict, text1: str, text2: str) -> None:
    """책등(세로 글, 4×2 표 첫 줄 두 칸) — 긴 이름이 칸 높이를 넘으면 1) 자간 0, 2) 글자 크기 1100, 3) 첫 줄 높이를 늘리고 "종합보고서" 줄을 줄임(형 10/21)."""
    c1, c2, c3 = cells.get((0, 0)), cells.get((0, 1)), cells.get((1, 0))
    if c1 is None or c2 is None or c3 is None:
        return
    sz1, sz2, sz3 = (c.find(f"{{{HP}}}cellSz") for c in (c1, c2, c3))
    cap = int(sz1.get("height"))
    p1 = next(c1.iter(f"{{{HP}}}p"))
    p2 = next(c2.iter(f"{{{HP}}}p"))
    if not _runs_of(p1):
        return
    h1, sp1 = _char_pr(doc, _runs_of(p1)[0].get("charPrIDRef"))
    need = lambda n, h, sp: int(n * h * (1 + sp / 100) * 1.02)  # noqa: E731 — 세로 글 한 글자 = 크기 + 자간
    n1 = len(text1)
    if need(n1, h1, sp1) <= cap:
        return
    sp1 = 0
    if need(n1, h1, sp1) > cap:
        h1 = 1100
    _set_charpr(p1, doc.clone_charpr(_runs_of(p1)[0].get("charPrIDRef"), height=h1, spacing=sp1))
    if need(n1, h1, sp1) > cap and _runs_of(p2):  # 그래도 넘치면 첫 줄 높이를 늘리고 종합보고서 줄에서 뺌(둘째 칸 자간도 0)
        h2, _ = _char_pr(doc, _runs_of(p2)[0].get("charPrIDRef"))
        _set_charpr(p2, doc.clone_charpr(_runs_of(p2)[0].get("charPrIDRef"), height=min(h2, 1100), spacing=0))
        delta = need(n1, h1, sp1) - cap + 600
        sz1.set("height", str(cap + delta))
        sz2.set("height", str(cap + delta))
        sz3.set("height", str(max(int(sz3.get("height")) - delta, 8000)))


def fill_summary(doc: Hwpx, d: Data) -> None:
    root = doc.root
    t = _tbl(root, 1, 1)
    if t is not None:
        _cover_title(rb._cells(t)[(0, 0)], d, "요           약          문", doc)
    for p in _tops(root):
        if re.fullmatch(r"\d{4}\.\s*\d{2}\.?", _ptext(p)):
            rb._set_para(p, d.month)
    t31 = _tbl(root, 3, 1)
    if t31 is not None:
        _set(rb._cells(t31), (0, 0), d.owner)
    replace_text(root, "어쩌구에 대한 2026년 상반기 정기안전점검", f"{d.name}에 대한 {d.year}년 {d.half} 정기안전점검")
    sites = d.many
    replace_text(root, "총 옹벽 17개소", f"옹벽 {len(sites)}개소")
    replace_text(root, "2026년 04월 13일 ~ 2026년 07월 11일", f"{_date(d.period_start, False)} ~ {_date(d.period_end, False)}")
    for p in _tops(root):
        if _ptext(p).startswith("※ 옹벽 총"):
            rb._set_para(p, f"※ 옹벽 총 {len(sites)}개소({_grade_summary(sites)})")
    t = _tbl(root, 18, 11)
    if t is not None:
        _resize(t, len(sites), 1, 1, doc)
        cells = rb._cells(t)
        for i, s in enumerate(sites, 1):
            vals = [str(i), s.name, f"{s.class_no}종", s.year_month, s.spec.get("form") or "-", s.spec.get("length") or "-", s.spec.get("height") or "-",
                    s.prev_grade, s.grade, "\n".join(s.ai.get("findings") or []), "\n".join(s.ai.get("repairs") or [])]
            for c, v in enumerate(vals):
                _set(cells, (i, c), v)


def _grade_summary(sites: list) -> str:
    """"2종시설물 : 양호 15개소, 보통 2개소 / 3종시설물 : 양호 1개소" — 종별·등급별 곳 수."""
    out = []
    for cls in sorted({s.class_no for s in sites}):
        cnt: dict[str, int] = {}
        for s in sites:
            if s.class_no == cls:
                cnt[s.grade] = cnt.get(s.grade, 0) + 1
        order = ["우수", "양호", "보통", "미흡", "불량"]
        out.append(f"{cls}종시설물 : " + ", ".join(f"{g} {cnt[g]}개소" for g in sorted(cnt, key=lambda g: order.index(g) if g in order else 9)))
    return " / ".join(out)


def _resize(tbl, want: int, first: int, per: int = 1, doc=None) -> None:
    """값 줄이 first줄부터 per줄씩 있는 표를 want곳 분량으로 — 모자라면 마지막 묶음 복제, 남으면 지움(머리줄·꼬리줄은 그대로).
    doc을 주면(per=1) 줄 테두리를 견본대로: 첫 줄 = 첫 줄 모양(윗선), 가운데 = 가운데 줄(얇은 선), 마지막 = 마지막 줄(굵은 아랫선), 한 줄뿐이면 첫 줄 모양 + 굵은 아랫선(형 10/21)."""
    rows = int(tbl.get("rowCnt"))
    have = (rows - first) // per
    fills = None
    if doc is not None and per == 1 and have >= 2:
        cells = rb._cells(tbl)
        row_f = lambda r: {c: tc.get("borderFillIDRef") for (rr, c), tc in cells.items() if rr == r}  # noqa: E731
        fills = (row_f(first), row_f(first + 1), row_f(first + have - 1))
    if want > have:
        rb._dup_rows(tbl, first + (have - 1) * per, per, want - have)
    elif want < have:
        rb._del_rows(tbl, first + want * per, (have - want) * per)
    if fills:
        f_first, f_mid, f_last = fills
        cells = rb._cells(tbl)
        for i in range(want):
            r = first + i
            use = f_first if i == 0 else f_last if i == want - 1 else f_mid
            for c, bf in use.items():
                tc = cells.get((r, c))
                if tc is None:
                    continue
                if want == 1 and bf and f_last.get(c):
                    bf = doc.clone_borderfill(bf, f_last[c])
                if bf:
                    tc.set("borderFillIDRef", bf)


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
    _set(cells, (5, 8), d.grade_cell)
    _set(cells, (6, 2), d.address)
    _set(cells, (6, 6), d.size)
    _set(cells, (8, 2), d.ai.get("critical") or "⦁없음")
    _set(cells, (9, 2), d.ai.get("public") or "⦁전반적으로 양호한 상태")
    _set(cells, (10, 2), "\n".join(d.ai.get("findings") or []))
    _set(cells, (11, 2), "\n".join(d.ai.get("repairs") or []))
    # 다. 책임(참여)기술자 — 줄 수 = 사람 수(형 10/21 "2명일 때 2칸, 3명일 때 3칸"): "구 분" 머리줄 다음부터 "라." 줄 앞까지가 사람 줄
    all_rows = sorted({k[0] for k in cells})
    r_head = next((r for r in all_rows if (r, 0) in cells and rb._n(rb._cell_text(cells[(r, 0)])).startswith("구분")), None)
    r_end = next((r for r in all_rows if r > (r_head or 0) and (r, 0) in cells and rb._n(rb._cell_text(cells[(r, 0)])).startswith("라.")), None)
    if r_head is not None and r_end is not None:
        have = r_end - r_head - 1
        want = max(len(d.persons), 1)
        if want > have:
            rb._dup_rows(tbl, r_end - 1, 1, want - have)
        elif want < have:
            rb._del_rows(tbl, r_head + 1 + want, have - want)
        cells = rb._cells(tbl)
        for i in range(want):
            r = r_head + 1 + i
            if i < len(d.persons):
                role, name, _, _, grade = d.persons[i]
                _set(cells, (r, 0), role)
                _set(cells, (r, 3), _spaced(name))
                _set(cells, (r, 4), d.period)
                _set(cells, (r, 7), grade)
            else:
                for c in (0, 3, 4, 7):
                    _set(cells, (r, c), "")
    last = max(k[0] for k in cells)
    _set(cells, (last, 0), d.ai.get("next_focus") or "-")


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
        tpl_sign = next((copy.deepcopy(p) for p in root.iter(f"{{{HP}}}pic")), None)
        for i, (role, name, pos, fld, grade) in enumerate(d.persons, 1):
            _set(cells, (i, 0), "책임기술자" if i == 1 else ("참여기술자" if i == 2 else ""))
            _set(cells, (i, 1), " ".join(name.replace(" ", "")))
            _set(cells, (i, 2), pos)
            _set(cells, (i, 3), f"{fld}\n{grade}" if grade else fld)
            sign = d.signs[i - 1] if i - 1 < len(d.signs) else None
            if sign is not None and (i, 4) in cells and tpl_sign is not None:  # 서명 칸 — 설정에 올린 서명 그림(10/21 형)
                _sign_into_cell(cells[(i, 4)], sign, tpl_sign, doc.add_image)
    # 위치도 4장 지움, 결과표·전경 덩이는 곳 수만큼(견본 17개 — 모자라면 마지막 덩이 복제)
    sites = d.many
    tops = _tops(root)
    idx_res = [i for i, p in enumerate(tops) if re.match(r"\d+\.\s*.+정기점검 결과표", _ptext(p))]
    idx_ov = [i for i, p in enumerate(tops) if _ptext(p).endswith("전경사진")]
    i_map = [i for i, p in enumerate(tops) if _ptext(p).endswith("위치도")]
    kill = []
    end_map = idx_res[0] if idx_res else len(tops)
    map_blocks = [tops[i_map[k]:(i_map[k + 1] if k + 1 < len(i_map) else end_map)] for k in range(len(i_map))]
    one_by_one = bool(map_blocks) and any((x.get("rowCnt"), x.get("colCnt")) == ("1", "1") for q in map_blocks[0] for x in q.iter(f"{{{HP}}}tbl"))
    if map_blocks and not one_by_one:  # 옛 합본 — 단지별 위치도 그림 쪽은 지움
        kill += tops[i_map[0]:end_map]
        map_blocks = []
    res_blocks = [tops[idx_res[k]:(idx_res[k + 1] if k + 1 < len(idx_res) else (idx_ov[0] if idx_ov else len(tops)))] for k in range(len(idx_res))]
    ov_blocks = [tops[idx_ov[k]:(idx_ov[k + 1] if k + 1 < len(idx_ov) else len(tops))] for k in range(len(idx_ov))]
    _extend_blocks(res_blocks, len(sites))
    _extend_blocks(ov_blocks, len(sites))
    if map_blocks:
        _extend_blocks(map_blocks, len(sites))
    for blk in res_blocks[len(sites):] + ov_blocks[len(sites):] + map_blocks[len(sites):]:
        kill += blk
    _del(root, kill)
    tpl = next((copy.deepcopy(p) for blk in ov_blocks[:1] for q in blk for p in q.iter(f"{{{HP}}}pic")), None)
    for k, s in enumerate(sites):  # 위치도(새 합본 10/21 — 곳마다 "k. 이름 위치도" + 1×1 표)
        if k >= len(map_blocks):
            break
        head, *rest = map_blocks[k]
        rb._set_para(head, f"{k + 1}. {s.name} 위치도")
        tbl = next((x for q in rest for x in q.iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) == ("1", "1")), None)
        if tbl is not None:
            _map_into_cell(rb._cells(tbl)[(0, 0)], s, tpl, doc.add_image, many=len(sites) > 1)
    for k, s in enumerate(sites):
        head, *rest = res_blocks[k]
        title = f"{k + 1}. {s.name} 정기점검 결과표"
        rb._set_para(head, title)
        res = next((x for q in rest for x in q.iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) in (("20", "9"), ("21", "9"))), None)
        if res is not None:
            _fill_result_table(res, s)
            if len(title) > 23 and _runs_of(head):  # 제목이 두 줄(한 줄 23자쯤)이면 1) 자간 -10, 2) 그래도 두 줄이면 결과표 글 줄 높이를 줄여 한 쪽에(형 10/21)
                if len(title) <= 25:
                    _set_charpr(head, doc.clone_charpr(_runs_of(head)[0].get("charPrIDRef"), spacing=-10))
                else:
                    _shrink_rows(res, 0.8)
        if k < len(ov_blocks):
            head, *rest = ov_blocks[k]
            rb._set_para(head, f"{s.name} 전경사진")
            ov = next((x for q in rest for x in q.iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) == ("6", "2")), None)
            if ov is not None:
                _fill_photo_table(ov, s.overview[:6], tpl, doc.add_image, "")


def _shrink_rows(tbl, ratio: float, all_rows: bool = False) -> None:
    """결과표 줄 높이를 ratio로(all_rows=False면 글 줄 — 높이 4000 넘는 중대결함·공중이용·주요결과만) — 글이 많으면 한글이 다시 늘림. 표 전체 높이(sz)도 같이."""
    total = 0
    for tc in tbl.iter(f"{{{HP}}}tc"):
        sz = tc.find(f"{{{HP}}}cellSz")
        if sz is None:
            continue
        h = int(sz.get("height") or 0)
        if all_rows or h > 4000:
            sz.set("height", str(int(h * ratio)))
    tsz = tbl.find(f"{{{HP}}}sz")
    if tsz is not None and all_rows:
        tsz.set("height", str(int(int(tsz.get("height") or 0) * ratio)))
    _ = total


def _contain(path: Path, w: int, h: int) -> tuple[bytes, int, int]:
    """그림을 w×h(HWPUNIT) 안에 비율대로 맞춤(자르지 않음, 흰 바탕) → (JPG 바이트, 그림 너비, 높이 HWPUNIT)."""
    import io

    from PIL import Image

    im = Image.open(path).convert("RGB")
    pw, ph = im.size
    k = min(w / pw, h / ph)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue(), int(pw * k), int(ph * k)


def _sign_into_cell(tc, sign: Path, tpl, add_image) -> None:
    """참여기술자 명단 "서명" 칸에 서명 그림(칸 안에 비율대로, 글자처럼)."""
    sz = tc.find(f"{{{HP}}}cellSz")
    cw, ch = (int(sz.get("width")) - 800, int(sz.get("height")) - 800) if sz is not None else (6000, 3000)
    cw, ch = min(cw, 7000), min(ch, 3200)
    try:
        img, w, h = _contain(sign, cw, ch)
    except Exception:  # noqa: BLE001
        return
    rb._slot_put(tc, None, img, "", "", tpl, add_image)
    _size_pic(next(tc.iter(f"{{{HP}}}pic"), None), w, h, img, inline=True)


def _map_into_cell(tc, s: Data, tpl, add_image, many: bool = False) -> None:
    """1×1 표 칸에 그 곳 위치도(locmap) 그림을 칸 크기로(글자처럼) — 서두 위치도·과업수행계획서 마. 위치도."""
    sz = tc.find(f"{{{HP}}}cellSz")
    if s.locmap and s.locmap.exists() and tpl is not None:
        w, h = (int(sz.get("width")) - 900, int(sz.get("height")) - 2400) if sz is not None else (24000, 18000)
        img = _fit(s.locmap, w, h)
        rb._slot_put(tc, None, img, "", "", tpl, add_image)
        _size_pic(next(tc.iter(f"{{{HP}}}pic"), None), w, h, img, inline=True)
    else:
        rb._set_lines(tc, [f"{s.name} — 위치도 없음(주소로 지도를 못 찾음)" if many else "위치도 없음(주소로 지도를 못 찾음)"])


def _extend_blocks(blocks: list, want: int) -> None:
    """문단 덩이 목록이 want개가 안 되면 마지막 덩이를 복제해 바로 뒤에(표·그림 id 새로)."""
    from server.sitok.merge import _renew_ids

    while blocks and len(blocks) < want:
        last = blocks[-1]
        new = [copy.deepcopy(p) for p in last]
        for p in new:
            _renew_ids(p)
        anchor = last[-1]
        for p in reversed(new):
            anchor.addnext(p)
        blocks.append(new)


def fill_toc(doc: Hwpx, d: Data, pages: dict[str, int]) -> int:
    """목차 — 제Ⅱ편은 곳 수만큼 장(견본 17장, 이름 바꿈), 3종인 곳은 "k.5 안전등급 평가" 줄 더함, 줄 끝 숫자(tab 뒤 조각) = 본문 쪽(pages: 제목 → 쪽).
    장 줄 숫자는 그 장 첫 소절 쪽(견본 규칙). 바꾼 줄 수."""
    root = doc.root
    sites = d.many
    n_ch = len(sites)
    tops = _tops(root)
    kill: list = []
    in_ch = 0
    chapter_lines: dict[int, list] = {}
    for p in tops:
        t = _ptext(p)
        m = re.match(r"제\s*(\d+)\s*장\s+(.+?)\s*(\d+)?$", t)
        if m and not re.match(r"제\s*\d+\s*장\s+(정기점검 개요|현장조사|종합결론)", t):
            in_ch = int(m[1])
        elif re.match(r"제\s*[ⅠⅡⅢ]\s*편", t) or re.match(r"<\s*부\s*록", t):
            in_ch = 0
        if in_ch > n_ch:
            kill.append(p)
            continue
        if in_ch >= 1:
            chapter_lines.setdefault(in_ch, []).append(p)
            if m:  # 장 줄 — 이름을 그 곳 이름으로(견본 이름은 장마다 다름)
                for x in p.iter(T):
                    for pc in rb._pieces(x):
                        if pc.text and re.search(r"제\s*\d+\s*장", pc.text):
                            pc.text = re.sub(r"(제\s*\d+\s*장\s*).*$", lambda mm: mm[1] + sites[in_ch - 1].name, pc.text, count=1)
                            break
    _del(root, kill)
    for k, s in enumerate(sites, 1):  # 3종 — 목차 원본은 2종 번호(k.5 유지관리방안·k.6 개략공사비·k.7 종합결론)
        if not s.template3:
            continue
        lines = chapter_lines.get(k) or []
        p15 = next((p for p in lines if _sq(_ptext(p)).startswith(f"{k}.5유지관리방안")), None)
        if p15 is None:
            continue
        for p in lines:
            t = _ptext(p)
            if t.startswith(f"{k}.7 종합결론"):
                replace_text(p, f"{k}.7 종합결론", f"{k}.8 종합결론")
            elif t.startswith(f"{k}.6 보수"):
                replace_text(p, f"{k}.6 보수", f"{k}.7 보수")
        new = copy.deepcopy(p15)
        replace_text(p15, f"{k}.5 유지관리방안", f"{k}.6 유지관리방안")
        p15.addprevious(new)
        first = next((pc for x in new.iter(T) for pc in rb._pieces(x) if pc.text and pc.text.strip()), None)
        if first is not None:
            first.text = f"{k}.5 안전등급 평가"
    tops = _tops(root)  # "< 부 록 >"부터 부록 목록 첫 줄 앞까지 "다음 문단과 함께" — 칸이 넘어가면 제목·목록이 같이 넘어가게(형 10/21)
    i_ap = next((i for i, p in enumerate(tops) if re.match(r"<\s*부\s*록", _ptext(p))), None)
    if i_ap is not None:
        cache: dict[str, str] = {}
        for p in tops[i_ap:]:
            if re.match(r"\d+\.\s*\S", _ptext(p)):
                break
            pid = p.get("paraPrIDRef") or "0"
            cache.setdefault(pid, doc.clone_parapr(pid, keep_with_next=True))
            p.set("paraPrIDRef", cache[pid])
    n = 0
    lines = []  # (문단, 장 줄인지, 제목 열쇠)
    for p in _tops(root):
        t = _ptext(p)
        m = re.match(r"제\s*(\d+)\s*장\s+(.+?)\s*(\d+)?$", t)
        key = re.sub(r"\s+", "", re.sub(r"\s*\d+$", "", t))
        lines.append((p, bool(m), key))
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
    if not d.template3:  # 2종은 2장 현장조사의 "2.2 시설물의 상태평가(3종시설물)"부터 끝까지 뺌(2.1 개요·점검 사항만)
        tops = _tops(root)
        i2 = next((i for i, p in enumerate(tops) if _sq(_ptext(p)).startswith("2.2시설물의상태평가")), None)
        if i2 is not None:
            _del(root, tops[i2:])
    for p in _tops(root):
        t = _ptext(p)
        if t.startswith("본 과업은 「시설물의 안전"):
            where = d.address if d.address != "-" else ""
            cls = "·".join(sorted({s.class_no for s in d.many}))
            rb._set_para(p, f"본 과업은 「시설물의 안전 및 유지관리에 관한 특별법」에 따른 정기점검 용역으로 {where + '에 위치한 ' if where else ''}제{cls}종 시설물로 지정된 "
                            f"{d.name}에 대한 상태를 정밀히 파악하여 안전사고 예방 및 사후 조치에 만전을 기하고, 필요시 향후 유지관리 방안을 제시하여 시설물의 안전한 관리에 목적이 있다.")
        elif t.startswith("￭ 과업기간"):
            rb._set_para(p, f"￭ 과업기간 : {d.period}")
    _fill_target_table(_tbl(root, 18, 9, "번호"), d, doc)


def _fill_target_table(t, d: Data, doc=None) -> None:
    """과업대상 시설물 표(18×9: 번호·시설물명·형식별·종별·길이·높이·준공연도·점검종류·비고) — 개요 1.2·과업지시서 Ⅱ."""
    if t is None:
        return
    _resize(t, len(d.many), 1, 1, doc)
    cells = rb._cells(t)
    for i, s in enumerate(d.many, 1):
        for c, v in enumerate([str(i), s.name, s.spec.get("form") or "-", f"{s.class_no}종", s.spec.get("length") or "-", s.spec.get("height") or "-", s.year_month, "정기점검", ""]):
            _set(cells, (i, c), v)


def _fill_status_table(t, d: Data, doc=None) -> None:
    """대상시설물 현황 표(18×8: 연번·시설명·위치·연장·높이·준공년도·구조형식·종별) — 과업수행계획서 라.·사전검토보고서 3."""
    if t is None:
        return
    _resize(t, len(d.many), 1, 1, doc)
    cells = rb._cells(t)
    for i, s in enumerate(d.many, 1):
        done = f"{s.completion.year}년 {s.completion.month}월" if s.completion else "-"
        for c, v in enumerate([str(i), s.name, s.address if s.address != "-" else "-", s.spec.get("length") or "-", s.spec.get("height") or "-", done,
                               s.spec.get("form") or wall_ledger.form_text(s.spec, "") or "-", f"{s.class_no}종"]):
            _set(cells, (i, c), v)


def _short_owner(owner: str) -> str:
    """과업지시서 표지 발주처 — "포천시청 산림공원과" → "포천시"(첫 낱말, 시청·군청·구청·도청의 청은 뗌)."""
    first = (owner or "").split()[0] if (owner or "").split() else owner
    return first[:-1] if re.search(r"(시|군|구|도)청$", first) else first


def _purpose_text(d: Data) -> str:
    where = d.address if d.address != "-" else ""
    cls = "·".join(sorted({s.class_no for s in d.many}))
    return (f"본 과업은 「시설물의 안전 및 유지관리에 관한 특별법」에 따른 정기점검 용역으로 {where + '에 위치한 ' if where else ''}제{cls}종 시설물로 지정된 "
            f"{d.name}에 대한 상태를 정밀히 파악하여 안전사고 예방 및 사후 조치에 만전을 기하고, 필요시 향후 유지관리 방안을 제시하여 시설물의 안전한 관리에 목적이 있다.")


def _set_cover_lines(tbl, d: Data, last: str) -> None:
    """서류 표지 1×1 표(줄 셋: "2026년 상반기 산업단지 옹벽 " / "정기점검 용역" / 서류 이름) — 첫 줄 = 연도·반기·이름, 둘째 그대로, 셋째 = last."""
    if tbl is None:
        return
    ps = [q for q in tbl.iter(f"{{{HP}}}p")]
    if len(ps) >= 3:  # 이름이 길면(산불대응센터…) 한 줄에 안 들어가 연도·반기 / 이름 / 정기점검 용역 / 서류 이름 네 줄로
        rb._set_para(ps[0], f"{d.year}년 {d.half}", in_table=True)
        nm = copy.deepcopy(ps[0])
        ps[0].addnext(nm)
        rb._set_para(nm, d.name, in_table=True)
        rb._set_para(ps[-1], last, in_table=True)


def fill_docs(doc: Hwpx, loc: dict, d: Data) -> int:
    """부록 서류 — 과업지시서(표지·Ⅰ 목적·Ⅱ 대상 표)·과업수행계획서(표지·과업명·기간·현황 표·위치도·조직도)·사전검토보고서(표지·과업명·현황 표). 채운 구역 수."""
    n = 0
    if "order_cover" in loc:
        v = doc.view(loc["order_cover"])
        for p in _tops(v.root):
            tx = _ptext(p)
            if "에 대한" in tx and "정기안전점검" in tx:
                rb._set_para(p, f"({d.name}에 대한 {d.year}년 {d.half} 정기안전점검)")
            elif re.fullmatch(r"\d{4}\.\s*\d{2}\.?", tx):
                rb._set_para(p, d.start_month)
            elif _sq(tx) == "포천시" and d.owner not in ("", "-"):
                rb._set_para(p, _spaced(_short_owner(d.owner)))
        n += 1
    if "order_body" in loc:
        v = doc.view(loc["order_body"])
        tops = _tops(v.root)
        i0 = next((i for i, p in enumerate(tops) if _ptext(p).startswith("본 과업은 「시설물의 안전")), None)
        if i0 is not None:  # 견본은 글을 세 문단으로 끊어 둠 — 한 문단으로
            j = i0 + 1
            while j < len(tops) and _ptext(tops[j]) and not re.match(r"[ⅠⅡⅢⅣ]", _ptext(tops[j])) and not list(tops[j].iter(f"{{{HP}}}tbl")):
                j += 1
            rb._set_para(tops[i0], _purpose_text(d))
            _del(v.root, [p for p in tops[i0 + 1:j] if _ptext(p)])
        _fill_target_table(_tbl(v.root, 18, 9, "번호"), d, v)
        n += 1
    if "plan" in loc:
        v = doc.view(loc["plan"])
        _set_cover_lines(_tbl(v.root, 1, 1), d, "과업수행계획서")
        for p in _tops(v.root):
            tx = _ptext(p)
            if re.fullmatch(r"\d{4}\.\s*\d{2}\.?", tx):
                rb._set_para(p, d.start_month)
            elif tx.startswith("가. 과업명"):
                rb._set_para(p, f"가. 과업명 : {d.title}")
            elif tx.startswith("◎") and "~" in tx:
                rb._set_para(p, f"◎ {d.period_days}")
        _fill_status_table(_tbl(v.root, 18, 8, "연 번") or _tbl(v.root, 18, 8, "연번"), d, v)
        n += 1
    if "plan_map" in loc:
        _fill_map_pages(doc, loc, d)
        n += 1
    if "plan_body" in loc:
        v = doc.view(loc["plan_body"])
        for p in _tops(v.root):
            tx = _ptext(p)
            if tx.startswith("◎ 과업기간"):
                rb._set_para(p, f"◎ 과업기간 : {d.period_days}")
        org = _tbl(v.root, 7, 8)
        if org is not None:  # 조직도 — (1,2) 책임기술자, (6,0)·(6,5) 참여기술자
            cells = rb._cells(org)
            names = [name for _, name, *_ in d.persons]
            _set(cells, (1, 2), names[0] if names else "-")
            _set(cells, (6, 0), names[1] if len(names) > 1 else "-")
            _set(cells, (6, 5), names[2] if len(names) > 2 else (names[1] if len(names) > 1 else "-"))
        n += 1
    if "precheck" in loc:
        v = doc.view(loc["precheck"])
        _set_cover_lines(_tbl(v.root, 1, 1), d, "사전검토보고서")
        for p in _tops(v.root):
            tx = _ptext(p)
            if re.fullmatch(r"\d{4}\.\s*\d{2}\.?", tx):
                rb._set_para(p, d.start_month)
            elif tx.startswith("1. 과업명"):
                rb._set_para(p, f"1. 과업명 : {d.title}")
        _fill_status_table(_tbl(v.root, 18, 8, "연 번") or _tbl(v.root, 18, 8, "연번"), d, v)
        n += 1
    return n


def _fill_map_pages(doc: Hwpx, loc: dict, d: Data) -> None:
    """과업수행계획서 마. 위치도 — 1×1 표(빈 칸)에 곳마다 위치도 그림(locmap), 둘째 곳부터 표 문단 복제(쪽 나눔). 그림 틀은 시설물편 전경 표의 pic."""
    v = doc.view(loc["plan_map"])
    tops = _tops(v.root)
    tp = next((p for p in tops if any((x.get("rowCnt"), x.get("colCnt")) == ("1", "1") for x in p.iter(f"{{{HP}}}tbl"))), None)
    if tp is None:
        return
    tpl = _pic_tpl(doc.roots[loc["chapter"]]) if "chapter" in loc else None
    if tpl is None:
        return
    from server.sitok.merge import _renew_ids

    hp = next((p for p in tops if _ptext(p).startswith("마.")), None)  # 제목 "마. 과업대상 시설물 위치도" — 곳마다 복제해 이름을 붙임(칸 안에 글을 넣으면 넘쳐 빈 쪽이 생김)
    anchor = tp
    for k, s in enumerate(d.many):
        if k == 0:
            para = tp
            if hp is not None and len(d.many) > 1:
                rb._set_para(hp, f"마. 과업대상 시설물 위치도 — {s.name}")
        else:
            if hp is not None:
                nh = copy.deepcopy(hp)
                nh.set("pageBreak", "1")
                rb._set_para(nh, f"마. 과업대상 시설물 위치도 — {s.name}")
                anchor.addnext(nh)
                anchor = nh
            para = copy.deepcopy(tp)
            _renew_ids(para)
            para.set("pageBreak", "0" if hp is not None else "1")
            anchor.addnext(para)
        anchor = para
        tbl = next(x for x in para.iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) == ("1", "1"))
        _map_into_cell(rb._cells(tbl)[(0, 0)], s, tpl, doc.add_image, many=len(d.many) > 1)


def _size_pic(pic, w: int, h: int, img_bytes: bytes, inline: bool = False) -> None:
    """그림 개체 크기를 w×h(HWPUNIT)로 — 틀(전경 사진 pic)을 본뜬 그림은 틀 크기라 칸보다 작게 나옴(위치도 칸). inline = 글자처럼 취급."""
    if pic is None:
        return
    if inline:
        pos = pic.find(f"{{{HP}}}pos")
        if pos is not None:
            pos.set("treatAsChar", "1")
            pos.set("vertOffset", "0")
            pos.set("horzOffset", "0")
    import io

    from PIL import Image

    try:
        pw, ph = Image.open(io.BytesIO(img_bytes)).size
    except Exception:  # noqa: BLE001
        pw, ph = 2048, 1536
    for tag in ("orgSz", "curSz", "sz"):
        el = pic.find(f"{{{HP}}}{tag}")
        if el is not None:
            el.set("width", str(w))
            el.set("height", str(h))
    rot = pic.find(f"{{{HP}}}rotationInfo")
    if rot is not None:
        rot.set("centerX", str(w // 2))
        rot.set("centerY", str(h // 2))
    sca = pic.find(f"{{{HP}}}renderingInfo/{{{HC}}}scaMatrix")
    if sca is not None:
        sca.set("e1", "1")
        sca.set("e5", "1")
    rect = pic.find(f"{{{HP}}}imgRect")
    if rect is not None:
        for name, (x, y) in (("pt0", (0, 0)), ("pt1", (w, 0)), ("pt2", (w, h)), ("pt3", (0, h))):
            pt = rect.find(f"{{{HC}}}{name}")
            if pt is not None:
                pt.set("x", str(x))
                pt.set("y", str(y))
    clip = pic.find(f"{{{HP}}}imgClip")
    if clip is not None:
        clip.set("left", "0")
        clip.set("top", "0")
        clip.set("right", str(pw * 75))
        clip.set("bottom", str(ph * 75))


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


def fill_chapter(doc: Hwpx, d: Data, k: int = 1, names: list | None = None, intro_root=None) -> None:
    """시설물편 한 장(구역 하나 + 그 바탕쪽) — k = 장 번호(묶음이면 2장부터 복제 구역, 제목 번호 1.x → k.x).
    names = 책의 모든 곳 이름(제Ⅱ편 간지 소목차 "제k장 이름" — 첫 장에만, 2장부터는 간지를 뺌), intro_root = 제Ⅰ편 구역(소목차 모양을 거기서 베낌, 형 10/21 "위치와 폰트 맞추기")."""
    root = doc.root
    doc.replace_all(SAMPLE_TITLE, d.title)
    doc.replace_here(SAMPLE_NAME, d.name)
    tops = _tops(root)
    i_title = next((i for i, p in enumerate(tops) if any((x.get("rowCnt"), x.get("colCnt")) == ("4", "1") for x in p.iter(f"{{{HP}}}tbl"))), None)
    if k > 1 and i_title:  # 편 간지(제Ⅱ편 표지 + 소목차)는 첫 장에만
        _del(root, tops[:i_title])
        tops = _tops(root)
        if tops:
            tops[0].set("pageBreak", "0")
    elif i_title:
        _divider_list(doc, tops[:i_title], names or [d.name], intro_root)
    _fill_chapter_body(doc, d)
    if k > 1:
        _renumber_chapter(doc, k)


def _divider_list(doc: Hwpx, paras: list, names: list, intro_root) -> None:
    """제Ⅱ편 간지 소목차(3×4 표 (0,3) 칸) — 제Ⅰ편 간지의 소목차 칸(빈 줄·"제1장 …" 줄 모양·탭)을 베껴 "제k장 이름" 줄을 곳 수만큼."""
    tbl = next((x for p in paras for x in p.iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) == ("3", "4")), None)
    if tbl is None:
        return
    tc = rb._cells(tbl).get((0, 3))
    if tc is None:
        return
    src_tc = None
    if intro_root is not None:
        it = next((x for x in intro_root.iter(f"{{{HP}}}tbl") if (x.get("rowCnt"), x.get("colCnt")) == ("3", "4")), None)
        src_tc = rb._cells(it).get((0, 3)) if it is not None else None
    full = lambda q: "".join(pc.text or "" for x in q.iter(T) for pc in rb._pieces(x)).strip()  # noqa: E731 — 탭 뒤 글(tail)까지
    if src_tc is not None:
        src_ps = [q for q in src_tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is src_tc]
        i_line = next((i for i, q in enumerate(src_ps) if re.match(r"제\s*\d+\s*장", full(q))), None)
        if i_line is not None:
            sub = next(tc.iter(f"{{{HP}}}subList"))
            for q in list(sub.findall(f"{{{HP}}}p")):
                sub.remove(q)
            for q in src_ps[:i_line]:  # 위 빈 줄(위치)
                sub.append(copy.deepcopy(q))
            line = src_ps[i_line]
            for k, name in enumerate(names, 1):
                q = copy.deepcopy(line)
                pieces = [pc for x in q.iter(T) for pc in rb._pieces(x)]
                texts = [pc for pc in pieces if pc.text and pc.text.strip()]
                if texts:
                    texts[0].text = f"제{k}장 {name}"
                    for pc in texts[1:]:
                        pc.text = ""
                sub.append(q)
            return
    ps = [q for q in tc.iter(f"{{{HP}}}p") if next(q.iterancestors(f"{{{HP}}}tc"), None) is tc]  # 제Ⅰ편 없으면 — 이 칸 줄 모양으로 N줄
    lines = [q for q in ps if re.match(r"제\s*\d+\s*장", full(q))]
    if not lines:
        return
    for q in lines[1:]:
        q.getparent().remove(q)
    anchor = lines[0]
    for k, name in enumerate(names, 1):
        q = lines[0] if k == 1 else copy.deepcopy(lines[0])
        rb._set_para(q, f"제{k}장 {name}", in_table=True)
        if k > 1:
            anchor.addnext(q)
        anchor = q


def _fit_chapter_title(doc, root, d: Data, res) -> None:
    """장 제목 표(4×1 두 번째 문단 "제 1 장  이름" — 번호 조각·이름 조각) 긴 이름: 1) 이름 자간 0, 2) 그래도 두 줄이면 1.1 결과표 글 줄을 줄여 같은 쪽에(형 10/21)."""
    t41 = _tbl(root, 4, 1)
    if t41 is None:
        return
    ps = [q for q in t41.iter(f"{{{HP}}}p") if "제" in "".join(x.text or "" for x in q.iter(T)) and len(_runs_of(q)) >= 2]
    if not ps:
        return
    q = ps[0]
    runs = _runs_of(q)
    width = 36428
    tc = next(q.iterancestors(f"{{{HP}}}tc"), None)
    sz = tc.find(f"{{{HP}}}cellSz") if tc is not None else None
    if sz is not None:
        width = int(sz.get("width"))
    need = 0
    for r in runs:
        h, sp = _char_pr(doc, r.get("charPrIDRef"))
        need += len("".join(x.text or "" for x in r.iter(T))) * h * (1 + sp / 100) * 0.95
    if need <= width:
        return
    need0 = 0
    for r in runs:
        h, sp = _char_pr(doc, r.get("charPrIDRef"))
        if sp > 0:
            r.set("charPrIDRef", doc.clone_charpr(r.get("charPrIDRef"), spacing=0))
        need0 += len("".join(x.text or "" for x in r.iter(T))) * h * 0.95
    if need0 > width and res is not None:  # 두 줄 제목(큰 글자) + 결과표가 한 쪽에 — 줄 높이를 다 20% 줄임(글이 많은 줄은 한글이 다시 늘림)
        _shrink_rows(res, 0.8, all_rows=True)


_PARA_CACHE: dict = {}


def _para_cache(doc, pid: str) -> str:
    """1.4 절 글 문단 모양(첫 줄 들여쓰기 0) — 파일마다 한 번만 복제."""
    key = (id(doc.doc), pid)
    if key not in _PARA_CACHE:
        _PARA_CACHE[key] = doc.clone_parapr(pid, intent=0)
    return _PARA_CACHE[key]


def _renumber_chapter(doc: Hwpx, k: int) -> None:
    """장 번호 — "제 1 장"·"제1장" → k, 문단 첫머리 "1.x"(소절 제목·소목차 줄·꼬리말) → "k.x". 표 안 숫자 값("1.2")은 뒤에 한글이 있어야 바꿈."""
    for root in doc.roots:
        for p in root.iter(f"{{{HP}}}p"):
            pieces = [pc for x in p.iter(T) if next(x.iterancestors(f"{{{HP}}}p"), None) is p for pc in rb._pieces(x)]
            if not pieces:
                continue
            joined = "".join(pc.text or "" for pc in pieces)
            new = re.sub(r"^(\s*)1\.(\d(?:\.\d)?\s*[가-힣(])", lambda m: f"{m[1]}{k}.{m[2]}", joined, count=1)
            new = re.sub(r"제(\s*)1(\s*)장", lambda m: f"제{m[1]}{k}{m[2]}장", new)
            if new != joined:
                pieces[0].text = new
                for pc in pieces[1:]:
                    pc.text = ""


def _fill_chapter_body(doc: Hwpx, d: Data) -> None:
    root = doc.root
    # 원본은 3종 — 본문 1.5 안전등급 평가·1.6 유지관리방안·1.7 개략공사비·1.8 종합결론(장 표지 소목차는 1.5 유지관리방안·1.6 안전등급 평가로 어긋나 있어 본문에 맞춤)
    nested = [p for p in root.iter(f"{{{HP}}}p") if p.getparent() is not root]
    if not d.template3:  # 2종은 안전등급 평가 절을 빼고 뒤 번호를 당김(1.5 유지관리방안·1.6 개략공사비·1.7 종합결론)
        tops = _tops(root)
        i6 = next((i for i, p in enumerate(tops) if re.match(r"1\.[56]안전등급평가", _sq(_ptext(p)))), None)
        i7 = next((i for i, p in enumerate(tops) if i > (i6 or 0) and re.match(r"1\.[67](유지관리방안|보수)", _sq(_ptext(p)))), None)
        if i6 is not None and i7 is not None:
            _del(root, tops[i6:i7])
        for p in _tops(root):  # 본문 제목 번호 당김
            t = _ptext(p)
            if t.startswith("1.6 유지관리방안"):
                replace_text(p, "1.6 유지관리방안", "1.5 유지관리방안")
            elif t.startswith("1.7 보수"):
                replace_text(p, "1.7 보수", "1.6 보수")
            elif t.startswith("1.8 종합결론"):
                replace_text(p, "1.8 종합결론", "1.7 종합결론")
        # 장 표지 소목차 줄(표 안, 글이 " 1" + ".6 안전등급 평가" 조각) — 문단을 지우면 한글이 죽어(RPC 오류, 10/21) 글만 한 줄씩 당기고 마지막은 비움
        sub = {_full(p): p for p in nested if _full(p) in ("1.6안전등급평가", "1.7보수·보강개략공사비", "1.8종합결론")}
        if len(sub) == 3:
            replace_text(sub["1.6안전등급평가"], "1.6 안전등급 평가", "1.6 보수·보강 개략공사비")
            replace_text(sub["1.7보수·보강개략공사비"], "1.7 보수·보강 개략공사비", "1.7 종합결론")
            replace_text(sub["1.8종합결론"], "1.8 종합결론", "")
    else:
        for p in nested:
            k = _full(p)
            if k == "1.5유지관리방안":
                replace_text(p, "1.5 유지관리방안", "1.5 안전등급 평가")
            elif k == "1.6안전등급평가":
                replace_text(p, "1.6 안전등급 평가", "1.6 유지관리방안")
    res = _tbl(root, 20, 9, "가. 일반현황")
    if res is not None:
        _fill_result_table(res, d)
    _fit_chapter_title(doc, root, d, res)
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
    trep = _tbl(root, 2, 6, "번호")  # 1.3.3 보수 및 보강 이력(번호·기간·시공사·내용·비고) — 면담 창
    if trep is not None:
        rows = [x for x in d.repairs if x.get("method") or x.get("where")]
        if rows:
            _resize(trep, len(rows), 1, 1)
            cells = rb._cells(trep)
            for i, x in enumerate(rows, 1):
                _set(cells, (i, 0), str(i))
                _set(cells, (i, 1), x.get("period") or "-")
                _set(cells, (i, 2), x.get("where") or "-")
                _set(cells, (i, 3), (f"{x.get('kind')} — " if x.get("kind") and x.get("kind") != "보수공사" else "") + (x.get("method") or "-"))
                _set(cells, (i, 5), x.get("note") or "")
            replace_text(root, "보수∙보강 이력 미기재", "보수∙보강 이력 보유")
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
                body[0].set("paraPrIDRef", _para_cache(doc, body[0].get("paraPrIDRef") or "0"))  # 첫 줄 내어쓰기(-2000) 없애 줄 시작을 맞춤(형 10/21)
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
    if d.template3:
        _fill_eval_table(root, d)
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


def _fill_eval_table(root, d: Data) -> None:
    """k.5 안전등급 평가 표(22×10 — 줄 2~19 = 1~18항목, 칸 2 점검자 의견·3 보수필요·4~8 a~e·9 해당없음, 줄 20 평가결과, 줄 21 종합의견) — AI 초안 items로."""
    t = _tbl(root, 22, 10, "구분")
    if t is None:
        return
    items = d.ai.get("items") or []
    if not items:
        return
    cells = rb._cells(t)
    by_no = {int(it.get("no", 0)): it for it in items}
    cols = {"우수": 4, "양호": 5, "보통": 6, "미흡": 7, "불량": 8, "해당없음": 9}
    for r in range(2, 20):
        name = rb._cell_text(cells[(r, 1)]) if (r, 1) in cells else ""
        m = re.match(r"\s*(\d+)\.", name)
        it = by_no.get(int(m[1])) if m else None
        if it is None:
            continue
        for c in range(4, 10):
            _set(cells, (r, c), "○" if cols.get(it.get("rating") or "") == c else "")
        _set(cells, (r, 2), it.get("opinion") or "-")
        _set(cells, (r, 3), it.get("repair") or "×")
    res = wall_manual.score(items, d.form)
    letter = res.get("grade") or ""
    for (r, c), tc in cells.items():
        if r == 20 and "안전등급" in rb._cell_text(tc):
            serious = letter in ("D", "E")
            rb._set_lines(tc, ["안전등급 : " + "   ".join(("■" if g == letter else "□") + g for g in "ABCDE"),
                               f"긴급점검·진단 필요성 : {'■있음 □없음' if serious else '□있음 ■없음'}", f"안전조치 필요성 : {'■있음 □없음' if serious else '□있음 ■없음'}"])
        elif r == 21 and c > 0:
            rb._set_lines(tc, [f"◦ {d.ai.get('eval_opinion') or '-'}"] + ([f"◦ {res['forced']}"] if res.get("forced") else []))


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
            fine = all(s.grade in ("우수", "양호", "보통") for s in d.many)
            rb._set_para(p, f"본 점검 대상시설물 {d.name}에 대한 외관조사 결과 시설물 안전성에 영향을 주는 구조적 손상은 "
                            + ("없는 것으로 조사되었으며, 전반적으로 양호한 것으로 판단됨으로 긴급점검 및 정밀안전진단이 필요하지 않은 것으로 판단된다."
                               if fine else "일부 조사되어 지속적인 관찰과 보수·보강이 필요한 것으로 판단된다."))
    tops = _tops(root)
    firsts = [p for p in tops if _ptext(p).startswith("1.2 점검결과 총괄표")]
    if len(firsts) > 1:
        i0 = tops.index(firsts[1])
        _del(root, tops[i0:])
    t = _tbl(root, 21, 6, "No")
    if t is not None:  # 곳마다 4줄(이름·준공 / H / L / 등급)
        _resize(t, len(d.many), 1, 4)
        cells = rb._cells(t)
        for i, s in enumerate(d.many):
            r0 = 1 + i * 4
            scon = s.ai.get("conclusion") or {}
            _set(cells, (r0, 0), str(i + 1))
            _set(cells, (r0, 1), s.name)
            _set(cells, (r0, 3), f"{s.completion.year}년" if s.completion else "-")
            _set(cells, (r0, 4), "\n".join(s.ai.get("findings") or []))
            _set(cells, (r0, 5), "\n".join(s.ai.get("repairs") or []) or "\n".join(scon.get("repair") or []))
            _set(cells, (r0 + 1, 3), s.spec.get("height") or "-")
            _set(cells, (r0 + 2, 3), s.spec.get("length") or "-")
            _set(cells, (r0 + 3, 3), s.grade)


def fill_appendix(doc: Hwpx, d: Data) -> None:
    root = doc.root
    doc.replace_all(SAMPLE_TITLE, d.title)
    tops = _tops(root)
    sites = d.many
    div = next((p for p in tops if re.fullmatch(r"1\.\s*" + re.escape(SAMPLE_NAME), _ptext(p))), None)
    if div is not None:  # 사진첩 간지 "k.이름" — 곳마다 한 쪽(복제는 쪽 나눔)
        rb._set_para(div, f"1.{sites[0].name}")
        anchor = div
        for k, s in enumerate(sites[1:], 2):
            new = copy.deepcopy(div)
            new.set("pageBreak", "1")
            rb._set_para(new, f"{k}.{s.name}")
            anchor.addnext(new)
            anchor = new
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


def _body_lines(pg) -> tuple[list[str], int | None]:
    """쪽의 본문 줄(머리말·꼬리말 자리 뺌)과 꼬리말 쪽 번호(아래쪽 숫자만 있는 낱말, 없으면 None)."""
    H = pg.rect.height
    words = pg.get_text("words")
    footer = [w for w in words if w[1] > H - 75 and re.fullmatch(r"\d{1,3}", w[4])]
    num = int(max(footer, key=lambda w: w[1])[4]) if footer else None
    body = [w for w in words if 55 < w[1] < H - 75]
    lines: dict[tuple, list] = {}
    for w in body:
        lines.setdefault((w[5], w[6]), []).append(w)  # block, line
    out = [" ".join(x[4] for x in sorted(ws, key=lambda x: x[0])) for _, ws in sorted(lines.items(), key=lambda kv: (kv[1][0][1], kv[1][0][0]))]
    return out, num


def _page_map(pdf: Path) -> dict[str, int]:
    """한글이 만든 PDF에서 목차 제목이 처음 나오는 쪽의 꼬리말 번호(본문 쪽 번호) — 번호 없는 쪽(표지·목차)은 뺌, 간지(글 몇 줄뿐)는 장 제목만."""
    out: dict[str, int] = {}
    with pymupdf.open(pdf) as doc:
        for pg in doc:
            lines, num = _body_lines(pg)
            if num is None:
                continue
            for ln in lines:  # 간지(장 표지·소목차)는 꼬리말 번호가 없어 위에서 빠짐
                k = re.sub(r"\s+", "", ln)
                if re.match(r"(제\d+장|\d+\.\d+[^\d])", k) and len(k) < 40:
                    out.setdefault(k, num)
    return out


def build(db, r, f, folder: Path, say=None) -> tuple[Path, Path, list[str], int]:
    """옹벽 한 곳 보고서 → (한글 파일, 합본 PDF, 알림, 채운 구역 수)."""
    return build_many(db, [(f, r)], folder, say)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def build_many(db, pairs: list, folder: Path, say=None, name: str = "", title: str = "", tag: str = "") -> tuple[Path, Path, list[str], int]:
    """옹벽 보고서 — pairs = [(시설물, 회차)] 장 순서(한 곳이면 하나). 여러 곳이면 한 권(서두 결과표·전경 곳마다, 시설물편 장 복제, 부록 사진첩 곳마다).
    name/title = 책 표지 이름·용역명(여러 곳일 때, 비면 첫 곳 것), tag = 파일 이름 꼬리("(분권 1)"). → (한글, PDF, 알림, 채운 구역 수)."""
    from server.contract_docs import hwp_queue

    say = say or (lambda m: None)
    missing = ready()
    if missing:
        raise RuntimeError("옹벽 원본이 없습니다(시특법 설정 → 옹벽 정기안전점검 원본 올리기): " + ", ".join(missing))
    sites = []
    for i, (f, r) in enumerate(pairs, 1):
        say(f"값 모으는 중 — {i}/{len(pairs)}곳…")
        s = gather(db, r, f)
        s.index = i
        sites.append(s)
    lead_f, lead_r = pairs[0]
    d = sites[0] if len(sites) == 1 else make_book(sites, name or sites[0].name, title or sites[0].title)
    folder.mkdir(parents=True, exist_ok=True)
    base = _safe(f"{lead_r.year}년 {lead_r.half} 정기안전점검 보고서_{d.name}{tag}")
    hwpx_out, pdf_out, pdf1 = folder / f"{base}.hwpx", folder / f"{base}.pdf", folder / f"{base}.1차.pdf"
    say("원본 여는 중…")
    doc = Hwpx(master_path())
    loc = locate(doc)
    changed = 0
    for key, fn in (("cover", fill_cover), ("summary", fill_summary), ("front", fill_front), ("intro", fill_intro)):
        say(f"{key} 채우는 중…")
        fn(doc.view(loc[key]), d)
        changed += 1
    chapters = [loc["chapter"]] + [doc.clone_section(loc["chapter"]) for _ in sites[1:]]  # 2장부터 구역(+바탕쪽) 복제
    for k, (sec, s) in enumerate(zip(chapters, sites), 1):
        say(f"제{k}장 {s.name} 채우는 중…")
        fill_chapter(doc.view(sec), s, k, [x.name for x in sites], doc.roots[loc["intro"]])
        changed += 1
    for key, fn in (("conclusion", fill_conclusion), ("appendix", fill_appendix)):
        say(f"{key} 채우는 중…")
        fn(doc.view(loc[key]), d)
        changed += 1
    say("부록 서류(과업지시서·과업수행계획서·사전검토보고서) 채우는 중…")
    changed += fill_docs(doc, loc, d)  # 10/21 형 — 합본에 든 서류를 다 채움(구역은 하나도 안 뺌)
    doc.renumber_pages([loc["summary"], loc["intro"]])
    say("한글 파일 저장 중…")
    doc.save(hwpx_out)
    say("PDF로 바꾸는 중(1/2 — 목차 쪽 번호 세기, 1~2분)…")
    pdf1.write_bytes(hwp_queue.convert_via_worker(hwpx_out.read_bytes(), ".hwpx", wait=PDF_WAIT))
    pages = _page_map(pdf1)
    n_toc = fill_toc(doc.view(loc["toc"]), d, pages)
    doc.save(hwpx_out)
    say("PDF로 바꾸는 중(2/2)…")
    pdf_out.write_bytes(hwp_queue.convert_via_worker(hwpx_out.read_bytes(), ".hwpx", wait=PDF_WAIT))
    pdf1.unlink(missing_ok=True)
    # 부록 끼우기 — 관리대장(곳마다 차례로)·사진첩(곳마다 간지 뒤)·계약서(계약서마다)
    merged: list[str] = []
    out = pymupdf.open(pdf_out)
    ledgers = [Path(f.ledger_pdf) for f, _ in pairs if f.ledger_pdf and Path(f.ledger_pdf).exists()]
    _insert_after(out, ("부록1", "관리대장"), ledgers, merged, "시설물관리대장")
    albums = []
    for k, s in enumerate(sites, 1):
        album = folder / f"사진첩_{k}.pdf"
        if album_pdf(s, album):
            albums.append(album)
            _insert_after(out, (f"{k}.{s.name}".replace(" ", ""),), [album], merged, "외관조사 사진첩" if k == 1 else f"사진첩 {k}", squash=True)
    from core.models_web import SitokContract
    contracts: list[Path] = []
    for _, r in pairs:
        c = db.get(SitokContract, r.contract_id) if r.contract_id else None
        if c and c.contract_pdf and Path(c.contract_pdf).exists() and Path(c.contract_pdf) not in contracts:
            contracts.append(Path(c.contract_pdf))
    _insert_after(out, ("계약서",), contracts, merged, "계약서")
    tmp = pdf_out.with_suffix(".tmp.pdf")
    out.save(tmp, garbage=3, deflate=True)
    out.close()
    tmp.replace(pdf_out)
    for a in albums:
        a.unlink(missing_ok=True)
    warn = list(d.warn)
    for s in sites:
        if not s.overview:
            warn.append(f"{s.name}: 전경사진이 없어 전경 칸이 비었습니다" if len(sites) > 1 else "전경사진이 없어 전경 칸이 비었습니다")
    if not pages:
        warn.append("목차 쪽 번호를 못 찾아 견본 숫자 그대로입니다")
    elif n_toc:
        merged.append(f"목차 쪽 번호 {n_toc}곳")
    if d.template3:
        warn.append("3종 안전등급 평가표(k.5)는 아직 견본 값 그대로입니다 — 다음 단계")
    if merged:
        warn.append("끼운 것: " + ", ".join(dict.fromkeys(merged)))
    return hwpx_out, pdf_out, warn, changed


def _insert_after(doc, keys: tuple, srcs: list[Path], merged: list, label: str, squash: bool = False) -> None:
    """간지 쪽(본문 글 짧고 keys가 다 든 쪽 — 머리말·꼬리말은 안 봄) 뒤에 PDF들을 끼움."""
    if not srcs:
        return
    page = None
    for i in range(len(doc)):
        lines, _ = _body_lines(doc[i])
        text = "\n".join(lines)
        t = re.sub(r"\s+", "", text) if squash else text
        if squash and not re.fullmatch("(" + "|".join(re.escape(k) for k in keys) + ")+", t):
            continue  # 간지 = 그 글만 있는 쪽 — 서두 결과표 제목 쪽에 끼워지지 않게
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
