"""내진성능평가 외주 결과물 받기·검토(2026-10-21 형 "끼워 넣는 식으로 하고 검토하는 게 나을 것 같아, 걔네가 그냥 작성하고 줄 때도 있어서 · 양식은 동일해").

외주 파일은 두 가지 — ① 3~7장만(견본 폴더 "1. 내진성능평가 보고서_….hwp") ② 우리 견본 한글 전체에 외주 몫까지 써서 줌.
- 3~7장: ②면 "제3장" 간지부터 끝까지 잘라(cut_chapters) — 둘 다 한글이 우리 문서 끝에 끼워 넣음(seismic_build.merge_vendor).
- 앞 외주 몫(② 일 때, take_front): 결과표 두 표(가~다 18×13 · 라~사 19×16 — 가·사는 우리가 다시 채움)와
  "(2) 내진성능평가 적용"부터 확인서·체크리스트 끝(제1장 간지 앞)까지 — 그 문단들이 쓰는 한글 서식(글자·문단 모양·테두리·스타일·번호)이
  우리 원본과 같으면 문단째 가져옴(층 수가 달라 표 줄 수가 달라도 됨, 모델링 그림·서명 그림도). 서식이 다르면 같은 모양 표 칸 글자만 + 알림.
- 검토(review): 외주가 쓴 값 ↔ 우리 값(시설물명·층수·연면적·준공년도, 체크리스트 철근상세 개소 ↔ 철근탐사 줄 수), 견본 이름이 남았는지.
"""
from __future__ import annotations

import copy
import hashlib
import re
import zipfile
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb
from server.sitok.report_build import _n
from server.sitok.wall_build import HC, HP, Hwpx

HH = "http://www.hancom.co.kr/hwpml/2011/head"
SAMPLE_MARK = "삼숭초"  # 견본 시설물 이름(외주가 안 고치고 남긴 곳 찾기)
RESULT_KEYS = ("가.일반현황", "라.내진성능")  # 결과표 두 표 — 첫 칸 글(띄어쓰기 없이) 앞부분


def _text(el) -> str:
    return "".join(x.text or "" for x in el.iter(f"{{{HP}}}t"))


def tops_of(root) -> list:
    return [p for p in root if p.tag == f"{{{HP}}}p"]


def _has_tbl(p) -> bool:
    return next(p.iter(f"{{{HP}}}tbl"), None) is not None


def _first(t) -> str:
    return _n(rb._cell_text(rb._cells(t).get((0, 0), t)))


def chapter3_index(tops: list) -> int | None:
    """"제3장 설계하중" 간지(외주 3~7장 시작) — 표 안 글이 "제3장"으로 시작하는 첫 문단(목차 쪽은 뺌)."""
    for i, p in enumerate(tops):
        if not _has_tbl(p):
            continue
        t = _n(_text(p))
        if re.search(r"제3장", t[:60]) and "목차" not in t[:20] and not re.search(r"제1장.*제2장", t):
            return i
    return None


def front_range(tops: list) -> tuple[int, int] | None:
    """앞 외주 몫 — "(2) 내진성능평가 적용" 머리 문단부터 "제1장 건물개요" 간지 앞까지(견본 문단 161~219)."""
    start = next((i for i, p in enumerate(tops) if not _has_tbl(p) and re.fullmatch(r"(\(\d\))?내진성능평가적용", _n(_text(p)))), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(tops)) if _has_tbl(tops[i]) and _n(_text(tops[i])).startswith("제1장건물개요")), None)
    return (start, end) if end else None


def result_para(tops: list, key: str):
    """결과표(첫 칸이 key로 시작하는 표)가 든 문단과 그 표."""
    for p in tops:
        for t in p.iter(f"{{{HP}}}tbl"):
            if _first(t).startswith(key):
                return p, t
    return None, None


def analyze(doc: Hwpx) -> dict:
    tops = tops_of(doc.root)
    c3, fr = chapter3_index(tops), front_range(tops)
    return {"chapter3": c3, "front": fr, "full": bool(fr and c3 and fr[1] < c3)}


def vendor_hwpx(path: Path) -> Path:
    """외주 파일 → hwpx(.hwp면 한글로 바꿔 옆에 같은 이름 .hwpx로 둠, 원본보다 새것이면 다시 안 바꿈)."""
    if path.suffix.lower() == ".hwpx":
        return path
    out = path.with_suffix(".hwpx")
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        return out
    from server.contract_docs import hwp_queue

    out.write_bytes(hwp_queue.convert_via_worker(path.read_bytes(), ".hwp", to="hwpx", wait=600))
    return out


def cut_chapters(src: Path, dest: Path) -> int:
    """외주 견본 전체 → 3장 간지부터 끝까지만 남긴 hwpx(첫 문단의 구역 설정은 남김). 남긴 문단 수."""
    from server.sitok.wall_build import _drop_before

    doc = Hwpx(src)
    tops = tops_of(doc.root)
    i = chapter3_index(tops)
    if i is None:
        raise ValueError("외주 파일에서 제3장을 못 찾았습니다.")
    if i > 0:
        _drop_before(doc.root, tops, i, sec_only=True)  # 꼬리말·쪽 감추기는 우리 것이 이어지게(간지 앞 빈 쪽도 막음)
    _fold_head(doc.root)
    doc.save(dest)
    return len(tops) - i


def _fold_head(root) -> bool:
    """첫 문단이 구역 설정·머리말 칸만 든 빈 줄이면 그 칸들을 다음 문단(3장 간지) 앞으로 옮기고 지움 — 끼워 넣을 때 쪽 나눔 뒤 빈 줄 + 한 쪽짜리 간지 표가
    같은 쪽에 안 들어가 빈 쪽이 생김(10/22 형 "빈 페이지 발생")."""
    tops = tops_of(root)
    if len(tops) < 2:
        return False
    first, nxt = tops[0], tops[1]
    own = "".join(t.text or "" for r in first.findall(f"{{{HP}}}run") for t in r.findall(f"{{{HP}}}t"))
    body = [c for r in first.findall(f"{{{HP}}}run") for c in r if c.tag in (f"{{{HP}}}tbl", f"{{{HP}}}pic")]  # 머리말 안 표·그림은 셈 안 함
    if own.strip() or body:
        return False
    runs = first.findall(f"{{{HP}}}run")
    at = list(nxt).index(nxt.find(f"{{{HP}}}run")) if nxt.find(f"{{{HP}}}run") is not None else 0
    for k, r in enumerate(runs):
        for t in r.findall(f"{{{HP}}}t"):
            r.remove(t)
        nxt.insert(at + k, r)
    root.remove(first)
    return True


# ---------- 서식이 같은지 ----------
_REF = (("charPrIDRef", "charPr"), ("paraPrIDRef", "paraPr"), ("borderFillIDRef", "borderFill"), ("styleIDRef", "style"))
_TAGS = ("charPr", "paraPr", "borderFill", "style", "tabPr", "numbering", "bullet")


def _defs(hdr) -> dict:
    return {tag: {e.get("id"): e for e in hdr.iter(f"{{{HH}}}{tag}")} for tag in _TAGS}


def _xml(e) -> bytes:
    return etree.tostring(e) if e is not None else b""


def _xml_cmp(tag: str, e) -> bytes:
    """비교용 — 번호 정의는 시작값(start)을 빼고: 우리 원본은 요약문·2.2.4 번호가 이어지게 시작값을 고쳐 둠(10/26 fix_seismic_master),
    외주 견본은 고치기 전 그대로(모두 1)라 다르게 보임. 문단째 옮기면 우리 시작값을 쓰니 번호도 맞음."""
    if tag != "numbering" or e is None:
        return _xml(e)
    e = copy.deepcopy(e)
    for x in e.iter():
        x.attrib.pop("start", None)
    return _xml(e)


def style_mismatch(our: Hwpx, ven: Hwpx, paras: list) -> list[str]:
    """paras(외주 문단)가 쓰는 서식이 우리 header에 같은 번호·같은 내용으로 있는지 — 다른 것 목록(빈 목록 = 문단째 옮겨도 됨)."""
    O, V = _defs(our.header), _defs(ven.header)
    need: dict[str, set] = {t: set() for t in _TAGS}
    for p in paras:
        for el in p.iter():
            for attr, tag in _REF:
                if el.get(attr):
                    need[tag].add(el.get(attr))
    for sid in list(need["style"]):
        s = V["style"].get(sid)
        if s is not None:
            need["paraPr"].add(s.get("paraPrIDRef"))
            need["charPr"].add(s.get("charPrIDRef"))
    for pid in list(need["paraPr"]):
        pp = V["paraPr"].get(pid)
        if pp is None:
            continue
        need["tabPr"].add(pp.get("tabPrIDRef"))
        for hd in pp.iter(f"{{{HH}}}heading"):
            if hd.get("type") in ("NUMBER", "OUTLINE"):
                need["numbering"].add(hd.get("idRef"))
            elif hd.get("type") == "BULLET":
                need["bullet"].add(hd.get("idRef"))
        for b in pp.iter(f"{{{HH}}}border"):
            need["borderFill"].add(b.get("borderFillIDRef"))
    for cid in list(need["charPr"]):
        cp = V["charPr"].get(cid)
        if cp is not None:
            need["borderFill"].add(cp.get("borderFillIDRef"))
    bad = [f"{tag} {i}" for tag in _TAGS for i in sorted(x for x in need[tag] if x)
           if i in V[tag] and _xml_cmp(tag, O[tag].get(i)) != _xml_cmp(tag, V[tag][i])]
    if need["charPr"]:
        fo = b"".join(_xml(e) for e in our.header.iter(f"{{{HH}}}fontface"))
        fv = b"".join(_xml(e) for e in ven.header.iter(f"{{{HH}}}fontface"))
        if fo != fv:
            bad.append("글꼴 목록")
    return bad


# ---------- 앞 외주 몫 옮기기 ----------
def _bin_items(doc: Hwpx) -> dict:
    """그림 id → (zip 안 이름, media-type)."""
    out = {}
    for it in re.findall(r"<opf:item [^>]*href=\"BinData/[^\"]+\"[^>]*/>", doc.hpf):
        i, h = re.search(r'id="([^"]+)"', it), re.search(r'href="(BinData/[^"]+)"', it)
        m = re.search(r'media-type="([^"]+)"', it)
        if i and h:
            out[i[1]] = (h[1], m[1] if m else "image/jpg")
    return out


def _copy_images(our: Hwpx, ven: Hwpx, paras: list) -> int:
    """옮긴 문단의 그림 — 우리 파일에 똑같은 그림이 있으면 그것을, 없으면 외주 그림을 더함. 더한 그림 수."""
    vi, oi = _bin_items(ven), _bin_items(our)
    added = 0
    with zipfile.ZipFile(ven.src) as zv, zipfile.ZipFile(our.src) as zo:
        have = {}
        names = set(zo.namelist())
        for k, (name, _m) in oi.items():
            if name in names:
                have[hashlib.md5(zo.read(name)).hexdigest()] = k
        done: dict[str, str] = {}
        for p in paras:
            for img in p.iter(f"{{{HC}}}img"):
                ref = img.get("binaryItemIDRef")
                if ref in done:
                    img.set("binaryItemIDRef", done[ref])
                    continue
                if ref not in vi:
                    continue
                name, media = vi[ref]
                data = zv.read(name)
                key = have.get(hashlib.md5(data).hexdigest())
                if key is None:
                    key = our.add_image(data, ext=Path(name).suffix.lstrip("."), media=media)
                    added += 1
                done[ref] = key
                img.set("binaryItemIDRef", key)
    return added


def _swap(old_paras: list, new_paras: list) -> None:
    parent = old_paras[0].getparent()
    anchor = old_paras[0].getprevious()
    for p in old_paras:
        parent.remove(p)
    for p in new_paras:
        rb._new_ids(p)
        if anchor is None:
            parent.insert(0, p)
        else:
            anchor.addnext(p)
        anchor = p


def copy_cells(dst, src) -> int:
    """같은 모양 표 — 칸 글자를 src로(우리 서식 그대로). 바꾼 칸 수."""
    dc, sc = rb._cells(dst), rb._cells(src)
    n = 0
    for rc, tc in sc.items():
        if rc not in dc:
            continue
        new = rb._cell_text(tc)
        if _n(new) != _n(rb._cell_text(dc[rc])):
            rb._set_lines(dc[rc], new.split("\n"))
            n += 1
    return n


def _outer_tables(paras: list) -> list:
    return [t for p in paras for t in p.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None]


def take_front(our: Hwpx, ven: Hwpx, warn: list) -> int:
    """앞 외주 몫을 우리 문서로 — 서식이 같으면 문단째, 다르면 같은 모양 표 칸 글자. 옮긴 문단(또는 칸) 수."""
    ot, vt = tops_of(our.root), tops_of(ven.root)
    a, b = front_range(ot), front_range(vt)
    if not a or not b:
        warn.append("외주 파일에서 \"(2) 내진성능평가 적용\"~체크리스트 자리를 못 찾아 견본 값 그대로입니다")
        return 0
    pairs = []  # (우리 문단들, 외주 문단들)
    for key in RESULT_KEYS:
        op, _ = result_para(ot, key)
        vp, _ = result_para(vt, key)
        if op is not None and vp is not None:
            pairs.append(([op], [vp]))
    pairs.append((ot[a[0]:a[1]], vt[b[0]:b[1]]))
    bad = style_mismatch(our, ven, [p for _, vs in pairs for p in vs])
    if not bad:
        n = 0
        for olds, vens in pairs:
            new = [copy.deepcopy(p) for p in vens]
            _copy_images(our, ven, new)
            _swap(olds, new)
            n += len(new)
        return n
    # 서식이 다름 — 같은 모양 표만 칸 글자
    warn.append(f"외주 파일 한글 서식이 우리 원본과 달라({', '.join(bad[:4])}{' …' if len(bad) > 4 else ''}) 같은 모양 표의 글자만 옮겼습니다 — "
                "그림(모델링 등)·줄 수가 다른 표는 외주 파일에서 직접 옮겨 주세요")
    n = miss = 0
    for olds, vens in pairs:
        ots = _outer_tables(olds)
        for vtb in _outer_tables(vens):
            k = (vtb.get("rowCnt"), vtb.get("colCnt"), _first(vtb)[:8])
            otb = next((t for t in ots if (t.get("rowCnt"), t.get("colCnt"), _first(t)[:8]) == k), None)
            if otb is None:
                miss += 1
                continue
            ots.remove(otb)
            n += copy_cells(otb, vtb)
    if miss:
        warn.append(f"외주 표 {miss}개는 줄·칸 수가 우리 원본과 달라 못 옮겼습니다")
    return n


# ---------- 검토 ----------
def _after(text: str, label: str) -> str:
    """"이름: 값" 글에서 값(다음 "이름:" 앞까지)."""
    m = re.search(re.escape(label) + r"\s*:\s*(.{0,40}?)(?=\s+[^\s:]+\s*:|$)", text)
    return m.group(1).strip() if m else ""


def _num(s: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group()) if m else None


def review(ven: Hwpx, ours: dict) -> list[str]:
    """외주 값 검토 — 우리 값과 다른 곳·견본 이름 남은 곳만 글로. ours = seismic_build.gather 값."""
    out: list[str] = []
    tops = tops_of(ven.root)
    info = analyze(ven)
    if info["full"]:
        a, b = info["front"]
        vend = tops[a:b] + tops[info["chapter3"]:]
        for key in RESULT_KEYS:
            p, _ = result_para(tops, key)
            if p is not None:
                vend.append(p)
    else:
        vend = tops
    vtext = " ".join(" ".join(_text(p).split()) for p in vend)
    left = vtext.count(SAMPLE_MARK)
    if left and SAMPLE_MARK not in (ours.get("name") or ""):
        out.append(f"외주 문서에 견본 이름 \"{SAMPLE_MARK}\"이 {left}곳 남아 있습니다(외주가 안 고친 곳)")
    name = _n(ours.get("name") or "")
    if name and name not in _n(vtext):
        out.append(f"외주 문서에 시설물명 \"{ours['name']}\"이 없습니다(다른 이름으로 썼는지 확인)")
    if not info["full"]:
        return out
    # 확인서(붙임 1-1) 건축물 일반사항 ↔ 관리대장
    conf = next((t for t in _outer_tables(tops[info["front"][0]:info["front"][1]]) if "건축물일반사항" in _first(t)), None)
    if conf is not None:
        ct = " ".join(_text(conf).split())
        fl = re.search(r"층수\s*\(높이\)\s*:\s*(?:지하\s*(\d+)\s*층\s*,?\s*)?지상\s*(\d+)\s*층", ct)
        if fl and ours.get("above") and int(fl.group(2)) != ours["above"]:
            out.append(f"확인서 층수 지상 {fl.group(2)}층 ≠ 관리대장 지상 {ours['above']}층")
        if fl and int(fl.group(1) or 0) != (ours.get("below") or 0):
            out.append(f"확인서 지하 {fl.group(1) or 0}층 ≠ 관리대장 지하 {ours.get('below') or 0}층")
        area = _num(_after(ct, "연면적"))
        if area and ours.get("area") and abs(area - ours["area"]) > 0.01:
            out.append(f"확인서 연면적 {area:,.2f}㎡ ≠ 관리대장 {ours['area']:,.2f}㎡")
        year = _num(_after(ct, "준공년도"))
        if year and ours.get("completion") and int(year) != ours["completion"].year:
            out.append(f"확인서 준공년도 {int(year)}년 ≠ 관리대장 {ours['completion'].year}년")
    # 결과표 나. 층수 ↔ 관리대장
    _, rt = result_para(tops, RESULT_KEYS[0])
    if rt is not None:
        cells = rb._cells(rt)
        for (r, c), tc in sorted(cells.items()):
            if r >= 7 and _n(rb._cell_text(tc)) == "층수" and (r, c + 1) in cells:
                v = _n(rb._cell_text(cells[(r, c + 1)]))
                m = re.search(r"지상(\d+)층", v)
                if m and ours.get("above") and int(m.group(1)) != ours["above"]:
                    out.append(f"결과표 나. 층수 {v} ≠ 관리대장 지상 {ours['above']}층")
                break
    # 체크리스트 D.3 철근상세 조사 부재 개소 ↔ 철근탐사 줄
    rebar = ours.get("rebar") or []
    if rebar:
        flat = _n(vtext)
        for k, label in (("기둥", "a.기둥"), ("보", "b.보"), ("벽체", "c.벽체")):
            m = re.search(rf"{label}(\d+)철근탐사기", flat)
            mine = sum(1 for x in rebar if x["kind"] == k or (k == "보" and x["kind"] == "보-기둥 접합부"))  # 접합부 = 보 단부 조사
            if m and int(m.group(1)) != mine:
                out.append(f"체크리스트 철근상세 {k} {m.group(1)}개소 ≠ 우리 철근탐사 {mine}개소")
    return out


def _selfcheck() -> None:
    assert _num("15.8MPa") == 15.8 and _num("10,093.95㎡") == 10093.95 and _n(" 제 3 장 ") == "제3장"
    t = "층수(높이): 지상 5 층 (20.05m) 연면적: 10,093.95 ㎡ 준공년도: 2005 년, 증축 여부: O"
    assert _num(_after(t, "연면적")) == 10093.95 and _num(_after(t, "준공년도")) == 2005, (_after(t, "연면적"), _after(t, "준공년도"))
    assert re.fullmatch(r"(\(\d\))?내진성능평가적용", "(2)내진성능평가적용")


if __name__ == "__main__":
    _selfcheck()
    print("ok")
