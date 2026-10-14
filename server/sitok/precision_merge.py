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
                anchors[kind] = _append_after(anchors[kind], copies)
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
            copies = _copy_block(otops, (s, len(otops)), zs[k - 1], k, bins)
            _strip_section(copies)
            for q in copies[:12]:  # 동 표지 "제1장. ○○" → "제k장. ○○"
                if M._sub_pieces(q, r"(제\s*)1(\s*장\s*\.)", rf"\g<1>{k}\g<2>", first_only=True):
                    break
            last = _append_after(last, copies)
        # --- 용역명 → 묶음 용역명(결과표 칸은 동마다)
        for root in roots:
            M._replace_titles(root, [p["title"] for p in parts], group_title)
            for el in list(root.iter(f"{{{HP}}}linesegarray")):
                el.getparent().remove(el)
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
            plan.append((le, adds))
    for le, adds in sorted(plan, key=lambda x: -x[0]):  # 뒤에서부터 끼워 앞 쪽 번호가 안 밀리게
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
        # 1번 구간(관리대장 1쪽) 뒤에 간지 "B동" + 1쪽, 2번 구간(2쪽: 2-1·사진) 뒤에 간지 + 2쪽, 4번(1쪽), 5번(1쪽) → 12 + 4×1 + (1+2+1+1) = 21
        assert m.page_count == 21 and texts.count("B동") == 4 and not notes, (m.page_count, texts.count("B동"), notes)
        assert texts[2] == "관리대장 내용" and texts[3] == "B동" and texts[4] == "관리대장 내용", texts[:6]
        m.close()
    print("정밀 묶음 부록 합치기 검증 통과")


if __name__ == "__main__":
    _selfcheck()
