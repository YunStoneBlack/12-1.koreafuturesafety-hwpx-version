"""정밀안전점검 여러 동 한 권(2026-10-14 형 2차 답: 정기 묶음처럼 — 결과표 동마다 한 장, 시설물편 동마다 한 부, 부록 동마다 한 벌. 견본 바탕화면 `시특법 견본\\정밀\\…숭의교회…(본관동,B동)`).

본문(merge_body): 동마다 만든 본문 한글(precision_build.build_body)을 첫 동 파일에 합침 —
- 첫 구역: 위치도/전경(표 머리 "위치도"·"전경사진") · 결과표~현황표(글 "…정밀안전점검 결과표"부터 "요약문" 제목 표 앞까지) · 요약문의 동 묶음("대상시설물 현황"부터 목차 앞까지) ·
  목차 시설물편 줄("01. ○○"부터 "- 부 록 -" 앞까지, "01."→"02.")을 동마다 이어 붙임. 표지·제출문·명단의 첫 동 이름 → 묶음 이름, 용역명 → 묶음 용역명(결과표 칸은 동마다).
- 둘째 구역: 시설물편(숨김 제목 문단 ~ "시설물편" ~ "제1장. ○○" 표지부터 끝)을 동마다 통째로 — 견본처럼 동 표지만 "제N장. 동 이름", 안쪽 장 번호(제1장~제7장)는 그대로.
  구역 설정·쪽 번호 새로 시작은 뺌, 다른 동 파일의 그림은 이름을 바꿔 옮김(merge._Bins).
부록(merge_appendix_pdfs): 동마다 만든 부록 PDF(간지 뒤 끼움까지 끝난 것)를 첫 동 PDF에 — 간지 "1. 관리대장"·"2. 사진첩"·"4. 성과표"·"5. 상태평가 결과 자료" 구간마다
  둘째 동부터 "동 이름" 간지 한 쪽 + 그 동 구간(견본: 관리대장·사진첩·성과표·결과자료가 동마다, 외관조사망도·장비·자격·과업지시서·계약서는 한 번).
"""
from __future__ import annotations

import copy
import re
import zipfile
from pathlib import Path

import pymupdf
from lxml import etree

from server.sitok import merge as M
from server.sitok import report_build as rb

HP = rb.HP
SHARED_APPENDIX = (1, 2, 4, 5)  # 동마다 한 벌 — 관리대장·사진첩·성과표·상태평가 결과자료


def _hidden(p) -> bool:
    return next(p.iter(f"{{{HP}}}pageHiding"), None) is not None


def _text(p) -> str:
    return rb._top_text(p).strip()


def _cells_text(p) -> str:
    return " ".join(rb._cell_text(c) for t in M._tables(p) for c in rb._cells(t).values()).replace(" ", "")


def front_blocks(root) -> dict[str, tuple[int, int]]:
    """첫 구역의 동별 묶음 {"overview"|"result"|"summary"|"toc": (시작, 끝)} — 끝은 빼고."""
    tops = M._tops(root)
    t = [_text(p) for p in tops]
    heads = [M._head(p).replace(" ", "") for p in tops]
    ov = [i for i, h in enumerate(heads) if "위치도" in h or "전경사진" in h]
    if not ov:
        raise ValueError("위치도·전경사진 표를 찾지 못했습니다.")
    rs = next(i for i, x in enumerate(t) if x.endswith("정밀안전점검 결과표"))
    re_ = next(i for i, h in enumerate(heads) if i > rs and h.startswith("요약문"))
    ss = next(i for i, x in enumerate(t) if i > re_ and x == "대상시설물 현황")
    toc = next(i for i, p in enumerate(tops) if i > ss and _hidden(p) and "목" in heads[i] and "차" in heads[i])
    se = toc
    while se > ss and not t[se - 1] and not M._tables(tops[se - 1]):
        se -= 1
    ss = next((i for i in range(ss + 1, se) if tops[i].get("pageBreak") == "1"), ss)  # 1.2~1.4(공통)는 두고 "2. ○○" 장 제목(새 쪽)부터
    p2 = next(i for i, x in enumerate(t) if i > toc and x.replace(" ", "").startswith("제2편") and "시설물편" in x)
    ts = next(i for i, x in enumerate(t) if i > p2 and re.match(r"^0?1\.\s+\S", x))  # "01. ○○" (목차 "1.1 …"은 띄어쓰기가 없어 제외)
    te = next(i for i, x in enumerate(t) if i > ts and (x.startswith("- 부") or x.startswith("-부") or x.startswith("부  록") or "부록" in x.replace(" ", "")[:3]))
    return {"overview": (ov[0], ov[-1] + 1), "result": (rs, re_), "summary": (ss, se), "toc": (ts, te)}


def part_start(root) -> int:
    """둘째 구역에서 시설물편 부분이 시작하는 문단(숨김 제목 문단) — "시설물편" 글 문단에서 숨김·빈 문단을 거슬러."""
    tops = M._tops(root)
    i = next(k for k, p in enumerate(tops) if _text(p) == "시설물편")
    while i > 0 and (_hidden(tops[i - 1]) or (not _text(tops[i - 1]) and not M._tables(tops[i - 1]))):
        i -= 1
    return i


def _strip_section(paras: list) -> None:
    """복사한 문단에서 구역 설정·쪽 번호 새로 시작·단 설정을 뺌(쪽 번호가 이어지게) — merge._renum_chapter와 같고 번호는 안 바꿈."""
    for p in paras:
        for el in list(p.iter(f"{{{HP}}}secPr", f"{{{HP}}}newNum")):
            if el.tag.endswith("newNum") and el.get("numType") != "PAGE":
                continue
            par = el.getparent()
            par.remove(el)
            if par.tag == f"{{{HP}}}ctrl" and not len(par):
                par.getparent().remove(par)
        for el in list(p.iter(f"{{{HP}}}colPr")):
            par = el.getparent()
            if par.tag == f"{{{HP}}}ctrl":
                par.getparent().remove(par)


def _copy_block(src_tops: list, span: tuple[int, int], z: zipfile.ZipFile, k: int, bins: M._Bins) -> list:
    out = []
    for p in src_tops[span[0]:span[1]]:
        q = copy.deepcopy(p)
        M._renew_ids(q)
        bins.take(q, z, k)
        out.append(q)
    return out


def _append_after(anchor, paras: list):
    last = anchor
    for q in paras:
        last.addnext(q)
        last = q
    return last


def _general_tables(root) -> list:
    """대상시설물 현황 표(종별·시설명·위치·연면적·층수·구조·준공년도, 앞에 no.가 있든 없든) — 5쪽·요약문 1.2·공통편 표 1.1."""
    out = []
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if next(tbl.iterancestors(f"{{{HP}}}tbl"), None) is not None:
            continue
        c = rb._cells(tbl)
        h = [re.sub(r"\s", "", rb._cell_text(c[k])) for k in sorted(k for k in c if k[0] == 0)]
        if "종별" in h and "시설명" in h and any(x.startswith("연면적") for x in h) and any(x.startswith("준공") for x in h):
            out.append(tbl)
    return out


def _general_rows(roots: list) -> list[list[str]]:
    """그 동 본문의 현황 표마다 첫 데이터 줄 값(표 순서대로)."""
    out = []
    for root in roots:
        for tbl in _general_tables(root):
            c = rb._cells(tbl)
            out.append([rb._cell_text(c[k]).strip() for k in sorted(k for k in c if k[0] == 1)])
    return out


def _fill_general_rows(roots: list, rows_by_part: list[list[list[str]]], notes: list[str]) -> None:
    """합친 본문의 현황 표마다 동 수만큼 줄(둘째 동부터 줄 복사) — 값은 각 동 본문에서 읽은 것, no. 열은 1·2·…(형 10/14 "시설물 2개라서 2개 들어갈 것")."""
    j = 0
    for root in roots:
        for tbl in _general_tables(root):
            rows = [pr[j] for pr in rows_by_part if j < len(pr)]
            j += 1
            if len(rows) < 2:
                continue
            if int(tbl.get("rowCnt")) < len(rows) + 1:
                rb._dup_rows(tbl, 1, 1, len(rows) + 1 - int(tbl.get("rowCnt")))
            c = rb._cells(tbl)
            has_no = re.sub(r"\s", "", rb._cell_text(c.get((0, 0), tbl))).lower().startswith("no")
            for i, vals in enumerate(rows):
                cells_i = [c[k] for k in sorted(k for k in c if k[0] == i + 1)]
                for tc, v in zip(cells_i, vals):
                    rb._set_lines(tc, [v])
                if has_no and cells_i:
                    rb._set_lines(cells_i[0], [str(i + 1)])


def _divider_rows(body, parts: list[dict], group_name: str) -> None:
    """공통편 끝 시설물편 간지 — "제1장. ○○" 줄을 동마다("제k장. ○○"), 그 위 용역명의 대표 동 이름은 묶음 이름으로(10/14)."""
    tops = M._tops(body)
    i0 = next((i for i, p in enumerate(tops) if _text(p) == "시설물편"), None)
    if i0 is None:
        return
    lead = parts[0]["name"]
    for p in tops[max(0, i0 - 10):i0]:  # 간지 위 용역명 "2027년도 상반기 ○○ 정밀안전점검 용역"
        if lead and lead != group_name and lead in _text(p):
            M._sub_pieces(p, re.escape(lead), group_name)
    line = next((p for p in tops[i0 + 1:i0 + 4] if _text(p).replace(" ", "").startswith("제1장")), None)
    if line is None:
        return
    inner = next((q for q in line.iter(f"{{{HP}}}p") if q is not line and "제1장" in "".join(x.text or "" for x in q.iter(rb.T))), None)
    if inner is not None:  # 견본·틀 모두 글상자(rect) 안 문단 — 글상자 안에 줄을 더함(문단을 통째로 복사하면 글상자가 겹침)
        W = 40000  # 긴 이름("기독교대한감리회숭의교회")이 한 줄에 들어가게 글상자 너비 — 원본 크기·현재 크기·배율(그리는 너비 = 원본 × 배율)을 같이
        for tag in ("orgSz", "curSz", "sz"):
            for sz in line.iter(f"{{{HP}}}{tag}"):
                if int(sz.get("width") or 0) < W:
                    sz.set("width", str(W))
        for m in line.iter(f"{{{rb.CORE}}}scaMatrix"):
            m.set("e1", "1")
        for dt in line.iter(f"{{{HP}}}drawText"):
            if int(dt.get("lastWidth") or 0) < W:
                dt.set("lastWidth", str(W))
        first = "".join(x.text or "" for x in inner.iter(rb.T))
        lead_sp = re.match(r"\s*", first).group(0)  # 첫 줄의 앞 공백·"제1장. " 뒤 공백을 그대로 따라 줄을 맞춤(사용자 10/14 "1.이랑 2.이랑 줄이 안 맞잖아")
        m_ = re.match(r"\s*제\s*1\s*장\.?(\s*)", first)
        gap = m_.group(1) if m_ else " "
        last = inner
        for k, part in enumerate(parts[1:], 2):
            q = copy.deepcopy(inner)
            rb._set_para(q, f"{lead_sp}제{k}장.{gap}{part['name']}")
            last.addnext(q)
            last = q
        return
    last = line
    for k, part in enumerate(parts[1:], 2):
        q = copy.deepcopy(line)
        M._sub_pieces(q, r"제\s*1\s*장", f"제{k}장", first_only=True)
        if lead:
            M._sub_pieces(q, re.escape(lead), part["name"])
        last.addnext(q)
        last = q


def _summary_toc(front, parts: list[dict]) -> None:
    """요약문 간지의 글상자 목차("1. 서 언 / 2. ○○")에 둘째 동부터 "3. □□" 줄 추가(사용자 10/14)."""
    for p in M._tops(front):
        inner = [q for q in p.iter(f"{{{HP}}}p") if q is not p]
        texts = ["".join(x.text or "" for x in q.iter(rb.T)) for q in inner]
        i2 = next((i for i, t in enumerate(texts) if t.replace(" ", "").startswith("2.") and parts[0]["name"] in t), None)
        if i2 is None or not any(t.replace(" ", "").startswith("1.서언") for t in texts[:i2]):
            continue
        lead_sp = re.match(r"\s*", texts[i2]).group(0)
        last = inner[i2]
        for k, part in enumerate(parts[1:], 3):
            q = copy.deepcopy(inner[i2])
            rb._set_para(q, f"{lead_sp}{k}. {part['name']}")
            last.addnext(q)
            last = q
        return


def merge_body(parts: list[dict], dest: Path, group_name: str, group_title: str) -> list[str]:
    """parts = [{hwpx, name, title}] 동 순서(첫 동 = 대표). 안내를 돌려줌."""
    notes: list[str] = []
    bins = M._Bins()
    zs = [zipfile.ZipFile(p["hwpx"]) for p in parts]
    try:
        secs = rb._sections(zs[0])
        roots = [etree.fromstring(zs[0].read(n)) for n in secs]
        if len(roots) < 2:
            raise ValueError("정밀 본문 한글의 구역이 2개가 아닙니다.")
        others = [[etree.fromstring(z.read(n)) for n in rb._sections(z)] for z in zs[1:]]
        general = [_general_rows(roots)] + [_general_rows(o) for o in others]  # 현황 표 값은 이름 바꾸기 전에 동마다 읽어 둠
        # --- 첫 구역: 동별 묶음 이어 붙이기
        front = roots[0]
        blocks = front_blocks(front)
        tops = M._tops(front)
        anchors = {kind: tops[e - 1] for kind, (s, e) in blocks.items()}
        for k, (part, oroots) in enumerate(zip(parts[1:], others), 2):
            otops = M._tops(oroots[0])
            try:
                ob = front_blocks(oroots[0])
            except (StopIteration, ValueError) as err:
                notes.append(f"{part['name']}: 본문 앞부분 묶음을 못 찾아 결과표·요약문을 못 합쳤습니다({err})")
                continue
            for kind in ("overview", "result", "summary", "toc"):
                copies = _copy_block(otops, ob[kind], zs[k - 1], k, bins)
                if kind == "toc" and copies:
                    M._sub_pieces(copies[0], r"^(\s*)0?1(\.\s*)", rf"\g<1>{k:02d}\g<2>", first_only=True)
                if kind == "summary":  # 요약문 쪽 머리말 "2. ○○" → "k+1. ○○"(장 제목 번호는 한글 자동 번호라 저절로)
                    for q in copies:
                        for h in q.iter(f"{{{HP}}}header"):
                            M._sub_pieces(h, r"^(\s*)2(\.\s*)", rf"\g<1>{k + 1}\g<2>", first_only=True)
                a = anchors[kind]
                if copies and copies[0].get("pageBreak") == "1":  # 앞 묶음 끝의 빈 문단들(현황표 뒤 4개, 첫 것이 쪽 나눔)은 지움 — 두면 빈 쪽이나 결과표 위 공백(10/14)
                    while a is not None and a.tag == f"{{{HP}}}p" and not _text(a) and not M._tables(a):
                        prev = a.getprevious()
                        a.getparent().remove(a)
                        a = prev
                anchors[kind] = _append_after(a, copies)
        # 표지·제출문·명단(위치도 앞까지): 첫 동 이름 → 묶음 이름
        lead_name = parts[0]["name"]
        if lead_name and lead_name != group_name:
            for p in tops[:blocks["overview"][0]]:
                M._sub_pieces(p, re.escape(lead_name), group_name)
        # --- 둘째 구역: 시설물편 동마다
        body = roots[1]
        btops = M._tops(body)
        last = btops[-1]
        for k, (part, oroots) in enumerate(zip(parts[1:], others), 2):
            obody = oroots[1]
            otops = M._tops(obody)
            try:
                s = part_start(obody)
            except StopIteration:
                notes.append(f"{part['name']}: 시설물편 시작을 못 찾아 합치지 못했습니다")
                continue
            i_txt = next((i for i in range(s, len(otops)) if _text(otops[i]) == "시설물편"), None)  # 둘째 동부터는 "시설물편" 간지를 빼고 동 표지부터
            s2 = next((i for i in range(i_txt + 1, min(i_txt + 8, len(otops))) if otops[i].get("pageBreak") == "1"), None) if i_txt is not None else None
            if s2 is not None:  # (첫 동 간지에 "제k장. ○○" 줄이 이미 있음 — 사용자 10/15 "삭제")
                s = s2
            copies = _copy_block(otops, (s, len(otops)), zs[k - 1], k, bins)
            _strip_section(copies)
            for q in copies[:12]:  # 동 표지 큰 글 "제1장" → "제k장"(사용자 10/15 "제2장") — 표지 소목차("제1장시설물 개요…")는 그대로
                if re.fullmatch(r"제\s*1\s*장\.?", _text(q).replace(" ", "")):
                    M._sub_pieces(q, r"(제\s*)1(\s*장)", rf"\g<1>{k}\g<2>", first_only=True)
                    break
            last = _append_after(last, copies)
        # --- 용역명 → 묶음 용역명(결과표 칸은 동마다)
        for root in roots:
            M._replace_titles(root, [p["title"] for p in parts], group_title)
            for el in list(root.iter(f"{{{HP}}}linesegarray")):
                el.getparent().remove(el)
        _fill_general_rows(roots, general, notes)  # 대상시설물 현황 표 3곳 — 동마다 줄
        for p in M._tops(roots[0]):  # 1.2 표가 늘어 1.4 위치도 지도 표가 다음 쪽으로 통째로 넘어가 제목만 남음 → 위치도는 새 쪽에서(10/14)
            if _text(p) == "위치도" and p.get("pageBreak") != "1":
                p.set("pageBreak", "1")
                break
        _divider_rows(roots[1], parts, group_name)  # 시설물편 간지 — 제1장·제2장…
        _summary_toc(roots[0], parts)  # 요약문 간지 목차 — 1. 서언 2. ○○ 3. □□
        # --- 쓰기(merge.merge와 같음)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zs[0].infolist():
                data = zs[0].read(info.filename)
                if info.filename in secs:
                    data = etree.tostring(roots[secs.index(info.filename)], xml_declaration=True, encoding="UTF-8", standalone=True)
                elif info.filename == "Contents/content.hpf":
                    items = "".join(f'<opf:item id="{k}" href="BinData/{k}{ext}" media-type="{M.MEDIA.get(ext, "image/jpg")}" isEmbeded="1"/>'
                                    for k, (ext, _) in bins.add.items())
                    data = data.decode("utf-8").replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8")
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


# ---------- 묶음 보고서 나누기(이미 낸 정밀 보고서 등록, 10/14) ----------

def part_count(hwpx: Path) -> int:
    """정밀 보고서의 동 수 = 첫 구역의 "…정밀안전점검 결과표" 문단 수."""
    with zipfile.ZipFile(hwpx) as z:
        root = etree.fromstring(z.read(rb._sections(z)[0]))
    return sum(1 for p in M._tops(root) if _text(p).endswith("정밀안전점검 결과표"))


def _drop(root, tops: list, spans: list[tuple[int, int]]) -> None:
    for s, e in spans:
        for p in tops[s:e]:
            if p.getparent() is root:
                root.remove(p)


def split(src: Path, k: int, dest: Path) -> str:
    """정밀 묶음 보고서 hwpx(src)에서 k번째 동만 남긴 hwpx(dest) — merge_body의 반대. 앞부분(위치도·결과표·요약문 장·목차)은 k번째 묶음만,
    현황 표는 k번째 줄만, 시설물편은 k번째 장만(제k장 → 제1장, 간지 한 줄). 돌려주는 값 = 그 동 이름."""
    with zipfile.ZipFile(src) as z:
        secs = rb._sections(z)
        roots = [etree.fromstring(z.read(n)) for n in secs]
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    front, body = roots[0], roots[1]
    tops = M._tops(front)
    t = [_text(p) for p in tops]
    heads = [M._head(p).replace(" ", "") for p in tops]
    rs = [i for i, x in enumerate(t) if x.endswith("정밀안전점검 결과표")]
    n = len(rs)
    if not 1 <= k <= n:
        raise ValueError(f"보고서에 동이 {n}개라 {k}번째를 나눌 수 없습니다.")
    names = [t[i].replace("정밀안전점검 결과표", "").strip() for i in rs]
    name = names[k - 1]
    re_ = next(i for i, h in enumerate(heads) if i > rs[0] and h.startswith("요약문"))
    toc = next(i for i, p in enumerate(tops) if i > re_ and _hidden(p) and "목" in heads[i] and "차" in heads[i])
    se = toc
    while se > re_ and not t[se - 1] and not M._tables(tops[se - 1]):
        se -= 1
    ov = [i for i, h in enumerate(heads) if "위치도" in h or "전경사진" in h]
    m = max(len(ov) // n, 1)
    spans = []
    for j in range(n):  # 다른 동 묶음들
        if j == k - 1:
            continue
        oj = ov[j * m:(j + 1) * m]
        if oj:
            spans.append((oj[0], oj[-1] + 1))
        spans.append((rs[j], rs[j + 1] if j + 1 < n else re_))
    chap = [next((i for i in range(re_, se) if tops[i].get("pageBreak") == "1" and t[i] == nm), None) for nm in names]
    for j in range(n):
        if j == k - 1 or chap[j] is None:
            continue
        nxt = next((c for c in chap[j + 1:] if c is not None), se)
        spans.append((chap[j], nxt))
    p2 = next((i for i, x in enumerate(t) if i > toc and x.replace(" ", "").startswith("제2편") and "시설물편" in x), None)
    if p2 is not None:
        te = next((i for i, x in enumerate(t) if i > p2 and (x.startswith("- 부") or x.startswith("-부") or "부록" in x.replace(" ", "")[:3])), len(tops))
        tocs = [i for i, x in enumerate(t) if p2 < i < te and re.match(r"^0?\d+\.\s+\S", x)]
        for j, i in enumerate(tocs):
            if j != k - 1:
                spans.append((i, tocs[j + 1] if j + 1 < len(tocs) else te))
            else:
                M._sub_pieces(tops[i], r"^(\s*)0?\d+(\.\s*)", r"\g<1>01\g<2>", first_only=True)
    if chap[k - 1] is not None:  # 머리말 "3. ○○" → "2. ○○"(장 번호는 한글 자동 번호)
        end = next((c for c in chap[k:] if c is not None), se)
        for p in tops[chap[k - 1]:end]:
            for h in p.iter(f"{{{HP}}}header"):
                M._sub_pieces(h, r"^(\s*)\d+(\.\s*)", r"\g<1>2\g<2>", first_only=True)
    _drop(front, tops, spans)
    for tbl in _general_tables(front):  # 현황 표 — k번째 줄만
        rows = int(tbl.get("rowCnt")) - 1
        if rows >= n:
            if k < rows:
                rb._del_rows(tbl, k + 1, rows - k)
            if k > 1:
                rb._del_rows(tbl, 1, k - 1)
            c = rb._cells(tbl)
            if re.sub(r"\s", "", rb._cell_text(c.get((0, 0), tbl))).lower().startswith("no") and (1, 0) in c:
                rb._set_lines(c[(1, 0)], ["1"])
    # --- 시설물편
    bt = M._tops(body)
    bx = [_text(p) for p in bt]
    i0 = next((i for i, x in enumerate(bx) if x == "시설물편"), None)
    if i0 is not None:
        for p in bt[i0 + 1:i0 + 1 + n]:  # 간지 글상자 안 "제1장. ○○ / 제2장. □□" 줄들 → 이 동 한 줄
            inner = [q for q in p.iter(f"{{{HP}}}p") if q is not p and re.match(r"^제\s*\d+\s*장", "".join(x.text or "" for x in q.iter(rb.T)).strip())]
            if inner:
                rb._set_para(inner[0], f"   제1장. {name}")
                for q in inner[1:]:
                    q.getparent().remove(q)
                break
        extra = [p for p in bt[i0 + 2:i0 + 1 + n] if re.match(r"^제\s*\d+\s*장", _text(p).replace(" ", ""))]
        for p in extra:
            body.remove(p)
    starts = []
    for nm in names:
        i = next((i for i, x in enumerate(bx) if i > (i0 or 0) and x == nm and i + 1 < len(bx) and bx[i + 1].replace(" ", "").startswith("제")), None)
        if i is not None:
            while i > 0 and not bx[i - 1] and not M._tables(bt[i - 1]) and bt[i].get("pageBreak") != "1":
                i -= 1
        starts.append(i)
    for j, s0 in enumerate(starts):
        if j == k - 1 or s0 is None:
            continue
        e0 = next((x for x in starts[j + 1:] if x is not None), len(bt))
        _drop(body, bt, [(s0, e0)])
    if starts[k - 1] is not None:
        e0 = next((x for x in starts[k:] if x is not None), len(bt))
        for p in bt[starts[k - 1]:min(starts[k - 1] + 6, e0)]:
            if re.fullmatch(r"제\s*\d+\s*장", _text(p).replace(" ", "")):
                rb._set_para(p, "제1장")
                break
        for p in bt[starts[k - 1]:e0]:
            for h in p.iter(f"{{{HP}}}header"):
                M._sub_pieces(h, rf"제\s*{k}\s*장", "제1장", first_only=True)
    for i, nm in enumerate(secs):
        data[nm] = etree.tostring(roots[i], xml_declaration=True, encoding="UTF-8", standalone=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            if info.filename == "Preview/PrvImage.png":
                continue
            zout.writestr(info.filename, data[info.filename], compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    tmp.replace(dest)
    return name


# ---------- 부록 PDF ----------

def _dividers(doc) -> dict[int, int]:
    """부록 PDF의 큰 간지 {번호: 쪽} — 글이 짧고 "N. 제목"으로 시작하는 쪽("2-1."·"7-5." 같은 작은 간지는 빼고)."""
    out: dict[int, int] = {}
    for i, pg in enumerate(doc):
        t = pg.get_text().strip()
        if len(t) > 140:
            continue
        m = re.match(r"^(\d{1,2})\.\s*\S", t)
        if m and int(m[1]) not in out and "후면첨부" not in t:  # "5. 장비측정위치도 [후면첨부]"(성과표 안 작은 간지)는 큰 간지가 아님
            out[int(m[1])] = i
    return out


def _trim_tail(d, s: int, e: int) -> int:
    """구간 끝의 작은 간지("… [후면첨부]"만 있는 쪽)는 뺌 — 둘째 동 성과표 끝의 장비측정위치도 간지가 첫 동 것과 겹치지 않게."""
    while e > s:
        t = d[e - 1].get_text().strip()
        if len(t) < 140 and "후면첨부" in t:
            e -= 1
        else:
            break
    return e


def _divider_page(doc, like, text: str) -> None:
    font = next((p for p in (r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf") if Path(p).exists()), None)
    page = doc.new_page(width=like.rect.width, height=like.rect.height)
    box = pymupdf.Rect(40, like.rect.height / 2 - 40, like.rect.width - 40, like.rect.height / 2 + 40)
    if font:
        page.insert_textbox(box, text, fontsize=20, fontname="kr", fontfile=font, align=1)
    else:
        page.insert_textbox(box, text, fontsize=20, align=1)


def merge_appendix_pdfs(items: list[tuple[str, Path]], dest: Path) -> list[str]:
    """items = [(동 이름, 그 동 부록 PDF)] 동 순서. 첫 동 PDF를 바탕으로 1·2·4·5 간지 구간에 둘째 동부터 "동 이름" 간지 + 그 동 구간을 이어 붙임."""
    notes: list[str] = []
    lead = pymupdf.open(items[0][1])
    ld = _dividers(lead)
    order = sorted(ld)

    def span(dv: dict[int, int], n: int, total: int) -> tuple[int, int]:
        s = dv[n] + 1
        nxt = [dv[m] for m in dv if dv[m] > dv[n]]
        return s, (min(nxt) if nxt else total)

    plan = []  # (lead 끼울 위치, [(이름, 문서, 시작, 끝)])
    for n in SHARED_APPENDIX:
        if n not in ld:
            continue
        ls_, le = span(ld, n, lead.page_count)
        le = _trim_tail(lead, ls_, le)  # 첫 동 구간 끝의 작은 간지(장비측정위치도 [후면첨부]) 앞에 둘째 동을 끼움
        adds = []
        for name, p in items[1:]:
            d = pymupdf.open(p)
            dv = _dividers(d)
            if n not in dv:
                notes.append(f"{name}: 부록 {n}번 간지를 못 찾아 그 동 자료를 못 넣었습니다")
                d.close()
                continue
            s, e = span(dv, n, d.page_count)
            e = _trim_tail(d, s, e)
            if e > s:  # 그 동에 그 자료가 없으면(관리대장·사진첩 없음) 간지도 안 넣음
                adds.append((name, d, s, e))
            else:
                d.close()
        if adds:
            plan.append((ls_, le, adds))
    for ls_, le, adds in sorted(plan, key=lambda x: -x[1]):  # 뒤에서부터 끼워 앞 쪽 번호가 안 밀리게
        at = le
        for name, d, s, e in adds:
            piece = pymupdf.open()
            _divider_page(piece, lead[0], name)
            if e > s:
                piece.insert_pdf(d, from_page=s, to_page=e - 1)
            lead.insert_pdf(piece, start_at=at)
            at += piece.page_count
            piece.close()
            d.close()
        if le > ls_:  # 첫 동 구간 앞에도 동 이름 간지(형 10/15 "간지가 B동만 있음 — 부록 다른 항목도 마찬가지")
            piece = pymupdf.open()
            _divider_page(piece, lead[0], items[0][0])
            lead.insert_pdf(piece, start_at=ls_)
            piece.close()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".pm.pdf")
    lead.save(tmp, garbage=3, deflate=True)
    lead.close()
    tmp.replace(dest)
    return notes + ([] if order else ["첫 동 부록에서 간지를 못 찾았습니다"])


def _selfcheck() -> None:
    doc = pymupdf.open()
    for txt in ("부 록", "1. 시설물관리대장 사본", "관리대장 내용", "2. 외관조사 사진첩", "2-1. 강도 측정데이터", "사진", "4. 측정, 시험, 계측 성과표", "성과표 쪽", "5. 상태평가 결과 자료", "갑지", "7. 기타 부록 참고자료", "7-5. 계약서"):
        pg = doc.new_page()
        pg.insert_font(fontname="mg", fontfile="C:/Windows/Fonts/malgun.ttf")
        pg.insert_text((80, 300), txt, fontname="mg", fontsize=12)
    dv = _dividers(doc)
    assert dv == {1: 1, 2: 3, 4: 6, 5: 8, 7: 10}, dv
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "a.pdf", Path(td) / "b.pdf"
        doc.save(a)
        doc.save(b)
        out = Path(td) / "m.pdf"
        notes = merge_appendix_pdfs([("본관", a), ("B동", b)], out)
        m = pymupdf.open(out)
        texts = [pg.get_text().strip() for pg in m]
        # 구간마다 첫 동 간지 "본관" + 첫 동 내용, 간지 "B동" + 둘째 동 내용 — 1번(1쪽)·2번(2쪽)·4번(1쪽)·5번(1쪽) → 12 + 4×2 + (1+2+1+1) = 25
        assert m.page_count == 25 and texts.count("B동") == 4 and texts.count("본관") == 4 and not notes, (m.page_count, texts.count("B동"), notes)
        assert texts[2] == "본관" and texts[3] == "관리대장 내용" and texts[4] == "B동" and texts[5] == "관리대장 내용", texts[:7]
        m.close()
    print("정밀 묶음 부록 합치기 검증 통과")


if __name__ == "__main__":
    _selfcheck()
