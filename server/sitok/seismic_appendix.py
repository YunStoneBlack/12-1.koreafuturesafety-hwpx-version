"""내진성능평가 부록·합본 4단계(2026-10-21 사용자 "1~4단계 시작" — 4 = 부록 합본).

부록 원본(master "성능평가부록" = 견본 삼숭초 부록 한글): 부록 목차 + 간지 1~9, 5 측정 및 시험성과표(부재단면·철근배근·조적벽·콘크리트 강도 표 + 사진),
6 철근데이터(시험번호마다 표 하나 — 탐사기 캡처 두 장·줄 두 개). 여기서 채우고(fill_appendix) PDF로 바꾼 뒤 간지 뒤에 서류를 끼워(assemble):
1 과업지시서 · 2 과업수행계획서 · 3 지반조사보고서 · 4 외관조사 및 사진첩(현장 조사 결함 → album_make) · 5 끝 = 장비·측정 위치도 ·
7 마이다스데이터 · 8 보강공사 내역서 · 9 구조도면(서류 칸 구조도면 여러 장). 마지막에 본문 PDF + 부록 PDF = 합본.
"""
from __future__ import annotations

import copy
from pathlib import Path

from server.sitok import rebar_survey as RV
from server.sitok import report_build as rb
from server.sitok.report_build import _n
from server.sitok import seismic_field as SF
from server.sitok import seismic_fill as SFL
from server.sitok.wall_build import HP

APPX = [(1, "과업지시서"), (2, "과업수행계획서"), (3, "지반조사보고서"), (4, "외관조사및사진첩"), (5, "측정및시험성과표"), (6, "철근데이터"),
        (7, "마이다스데이터"), (8, "보강공사내역서"), (9, "구조도면")]
DOC_OF = {1: "task", 2: "plan", 3: "ground", 8: "estimate"}  # 서류 칸 키(4 = 사진첩 만들기, 5 = measure, 7 = MIDAS_SUB, 9 = 구조도면 여러 장)
MIDAS_SUB = (("midas", "안전성검토", "1. 안전성 검토"), ("midas_linear", "선형해석", "2. 선형해석"))  # 7 안 작은 간지(원본 틀)마다 그 뒤에(10/22 형 "두 개 넣고 간지는 틀로")
HEAD_PHOTOS = [("부재단면조사", ("member_1", "member_2")), ("철근배근상태조사", ("rebar_1", "rebar_2")),
               ("조적벽상태조사", ("infill_1", "parapet_1")), ("콘크리트강도조사", ("core_1", "core_2", "core_3", "core_4"))]


def _blank(rdir: Path) -> Path:
    from PIL import Image

    p = rdir / "보고서그림" / "빈칸.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (400, 300), "white").save(p)
    return p


def _divider_index(tops: list, n: int, title: str) -> int | None:
    for i, p in enumerate(tops):
        for t in SFL._outer(p):
            if (t.get("rowCnt"), t.get("colCnt")) == ("1", "1") and _n(rb._cell_text(rb._cells(t).get((0, 0), t))).startswith(f"{n}.{title}"):
                return i
    return None


def fill_rebar_blocks(doc, root, rows: list[dict], rdir: Path, warn: list) -> int:
    """6 철근데이터 — 시험번호마다 표 하나(견본 첫 7×17 표가 틀): 캡처 그림 두 장, 줄마다 RC 번호·조사위치·부재·구조도면·실측·구분."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    i6, i7 = _divider_index(tops, 6, "철근데이터"), _divider_index(tops, 7, "마이다스데이터")
    if i6 is None or i7 is None:
        warn.append("부록 원본에서 6 철근데이터 자리를 못 찾았습니다")
        return 0
    seg = tops[i6 + 1:i7]
    tpl = next((p for p in seg for t in SFL._outer(p) if t.get("colCnt") == "17" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))).startswith("시험번호")), None)
    if tpl is None:
        return 0
    tpl = copy.deepcopy(tpl)
    if not rows:
        warn.append("철근탐사 줄이 없어 부록 6 철근데이터는 간지만 남깁니다")
    for p in seg:
        root.remove(p)
    anchor, n, miss = tops[i6], 0, 0
    for k, row in enumerate(rows, 1):
        p = copy.deepcopy(tpl)
        rb._new_ids(p)
        p.set("pageBreak", "1")
        anchor.addnext(p)
        anchor = p
        t = SFL._outer(p)[0]
        cells = rb._cells(t)
        pics = dict(rb._pic_slots(t))
        head, mark = RV.member_text(row)
        SFL._set(cells, (0, 0), f"시험번호{k}")
        for line, (rr, prc) in enumerate(((3, (1, 0)), (6, (4, 0)))):
            SFL._set(cells, (rr, 0), f"RC-{row.get('no') or k}")
            SFL._set(cells, (rr, 11), f"{SF.floor_label(row['floor'])} {head}".strip())
            SFL._set(cells, (rr, 13), f"{RV.kind_short(row)}{mark}")  # 접합부 = 보(보 단부로 조사)
            SFL._set(cells, (rr, 14), row["design"][line] or "-")
            SFL._set(cells, (rr, 15), "실측불가" if row["unable"][line] else (row["measured"][line] or "-"))
            SFL._set(cells, (rr, 16), RV.LINES[row["kind"]][line])
            cap = row["captures"][line]
            pic = pics.get(prc)
            if pic is not None:
                if not (cap and SFL._put(doc, pic, rdir / cap, crop=False)):
                    SFL._put(doc, pic, _blank(rdir), crop=False)
                    miss += 1
        n += 1
    if miss:
        warn.append(f"부록 6 철근데이터 — 탐사기 캡처 없는 줄 {miss}개는 빈 그림(🧪 철근탐사에서 📷 캡처)")
    return n


def fill_appendix(doc, d: dict, r, f, rdir: Path, warn: list) -> int:
    from server.sitok import seismic_build as SB

    root = doc.root
    field = SF.normalize((r.survey or {}).get("seismic_field"))
    quiet: list[str] = []  # 본문에서 이미 알린 것은 다시 안 알림
    n = SB.replace_globals(doc, d)
    photos = field["photos"]
    for key, slots in HEAD_PHOTOS:  # 5 표 머리 사진
        t = next((t for t in SFL._outer(root) if _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == key and rb._pic_slots(t)), None)
        if t is None:
            continue
        for slot, (_, pic) in zip(slots, rb._pic_slots(t)):
            rel = (photos.get(slot) or {}).get("rel")
            n += SFL._put_or_blank(doc, pic, (rdir / rel) if rel else None, rdir)  # 없으면 빈칸(10/22 형 "측정 데이터 안 넣었는데 들어감")
    members = field["members"]
    tables = [t for t in SFL._outer(root) if t.get("colCnt") == "6" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "NO"]
    rows = [[str(i + 1), f"{SF.floor_label(m['floor'])}( {m['where']} )" if m["where"] else SF.floor_label(m["floor"]),
             f"{m['kind']} ({m['mark']})" if m["mark"] else m["kind"], m["design"] or "-", m["measured"] or "-", m["note"]] for i, m in enumerate(members)]
    n += SFL.fill_chunks(root, tables, rows or [[""] * 6], 18, 1, flat=False)  # 없으면 빈 줄
    n += SB.fill_rebar(root, d, quiet)  # 없으면 빈 줄(fill_rebar가)
    rows = sorted(field["masonry"], key=lambda x: (x["floor"], x["kind"] != "채움벽", x["mid"]))
    vals = [[SF.floor_label(x["floor"]).replace("지상", "지상 ").replace("지하", "지하 "), x["kind"], x["mid"], SFL._fmt(x["height"], 0) if x["height"] else "-",
             SFL._fmt(x["width"], 0) if x["width"] else "-", x["thick"], x["dir"], x["expose"].replace(" ", "\n", 1), f"{x['finish']}" if x["finish"] is not None else "-",
             x["boundary"], x["applied"]] for x in rows]
    tables = [t for t in SFL._outer(root) if t.get("colCnt") == "11" and _n(rb._cell_text(rb._cells(t).get((0, 0), t))) == "층"]
    n += SFL.fill_chunks(root, tables, vals or [[""] * 11], 60, 2, flat=True)
    n += SFL.fill_cores(doc, root, field, rdir, None, quiet)
    rebar_rows = RV.report_rows(RV.normalize((r.survey or {}).get("rebar"))["rows"])  # 결과 있는 줄만(10/22)
    n += fill_rebar_blocks(doc, root, rebar_rows, rdir, warn)
    # 7 마이다스 안 작은 간지(안전성 검토·선형 해석)는 원본 틀 그대로 남김 — assemble이 간지마다 그 뒤에 서류 칸 PDF(10/22)
    return n


# ---------- PDF 합본 ----------
def _doc_pdf(r, rdir: Path, key: str, cache: Path) -> Path | None:
    """서류 칸 파일 → PDF(한글·엑셀·그림이면 바꿔 cache에)."""
    from server.contract_docs import attachments

    d = ((r.survey or {}).get("seismic_docs") or {}).get(key) or {}
    src = rdir / d["rel"] if d.get("rel") else None
    if src is None or not src.exists():
        return None
    if src.suffix.lower() == ".pdf":
        return src
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(attachments.to_pdf_bytes(src.read_bytes(), src.name))
    return cache


def _album(db, r, out: Path) -> Path | None:
    from server.api.routers.sitok_defects import album_floors
    from server.sitok import album_make

    floors = album_floors(db, r.id)
    if not floors:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    album_make.make(floors, out)
    return out


def assemble(db, main_pdf: Path, appx_hwpx: Path, dest: Path, r, f, rdir: Path, warn: list) -> tuple[Path, Path]:
    """부록 한글 → PDF, 간지 뒤에 서류 PDF 끼우기, 본문 + 부록 = 합본. (부록 PDF, 합본 PDF)."""
    import pymupdf

    from server.api.routers.sitok import _facility_dir
    from server.contract_docs import hwp_queue, pdf_shrink
    from server.sitok import drawings as D

    appx_pdf = appx_hwpx.with_suffix(".pdf")
    appx_pdf.write_bytes(hwp_queue.convert_via_worker(appx_hwpx.read_bytes(), ".hwpx", wait=1500))
    cache = rdir / "보고서그림"
    adds: dict[int, list[Path]] = {}
    for n, key in DOC_OF.items():
        p = _doc_pdf(r, rdir, key, cache / f"부록{n}.pdf")
        if p is not None:
            adds[n] = [p]
    if 2 not in adds:  # 과업수행계획서를 안 올렸으면 자동으로(10/22)
        try:
            from server.contract_docs import attachments
            from server.sitok import seismic_plan

            hw = seismic_plan.build_plan(db, r, f, cache / "부록2_과업수행계획서.hwpx")
            out = cache / "부록2.pdf"
            out.write_bytes(attachments.to_pdf_bytes(hw.read_bytes(), hw.name))
            adds[2] = [out]
            warn.append("부록 2 과업수행계획서는 자동으로 만들었습니다(건 화면 서류 칸에서 받아 고칠 수 있음)")
        except Exception as err:  # noqa: BLE001
            warn.append(f"부록 2 과업수행계획서를 자동으로 못 만들었습니다: {str(err).splitlines()[0][:80]}")
    alb = _album(db, r, cache / "부록4_사진첩.pdf")
    if alb is not None:
        adds[4] = [alb]
    five = [x for x in (_doc_pdf(r, rdir, "measure", cache / "부록5_위치도.pdf"), _doc_pdf(r, rdir, "masonry_map", cache / "부록5_조적벽위치도.pdf")) if x is not None]
    if five:  # 장비·측정 위치도 + 조적벽 조사 위치도(10/22 형 "파일 2개 들어가야 함")
        adds[5] = five
    struct = [it["path"] for it in D.items(f, "struct", _facility_dir(f))]
    if struct:
        adds[9] = struct
    names = dict(APPX)
    for n, title in APPX:
        if n not in adds and n not in (6, 7):
            label = {4: "외관조사 사진첩(현장 조사 결함)", 5: "장비·측정 위치도"}.get(n, title)
            warn.append(f"부록 {n} {label} 없음 — {'간지만' if n != 5 else '표만'}(서류 칸·현장 조사)")
    doc = pymupdf.open(appx_pdf)
    div = {}
    for i in range(1, doc.page_count):
        flat = _n(doc[i].get_text())
        for n, title in APPX:
            if n not in div and f"{n}.{title}" in flat and len(flat) < 160:
                div[n] = i
    plan = []  # (끼울 위치, 파일들)
    end7 = div.get(8, doc.page_count)
    for key, title, label in MIDAS_SUB:  # 7 작은 간지 뒤
        p = _doc_pdf(r, rdir, key, cache / f"부록7_{key}.pdf")
        if p is None:
            warn.append(f"부록 7 마이다스 데이터 {label} 없음 — 간지만(서류 칸)")
            continue
        at = next((i + 1 for i in range(div.get(7, 0) + 1, end7) if title in (flat := _n(doc[i].get_text())) and len(flat) < 160), None)
        if at is None:
            at = div[7] + 1 if 7 in div else None
            warn.append(f"부록 PDF에서 7 '{label}' 작은 간지를 못 찾아 7 간지 뒤에 넣었습니다" if at else f"부록 PDF에서 7. 마이다스데이터 간지를 못 찾아 {label}을 못 넣었습니다")
        if at:
            plan.append((at, [p]))
    for n, paths in adds.items():
        if n not in div:
            warn.append(f"부록 PDF에서 {n}. {names[n]} 간지를 못 찾아 그 서류를 못 넣었습니다")
            continue
        if n == 5:  # 5는 표 뒤(6 간지 앞)
            at = div.get(6, doc.page_count)
        else:
            at = div[n] + 1
        plan.append((at, paths))
    for at, paths in sorted(plan, key=lambda x: -x[0]):
        pos = at
        for p in paths:
            if Path(p).suffix.lower() == ".pdf":
                with pymupdf.open(p) as src:
                    doc.insert_pdf(src, start_at=pos)
                    pos += src.page_count
            else:
                from PIL import Image

                with Image.open(p) as im:
                    w, h = im.size
                W, H = (842, 595) if w > h else (595, 842)
                page = doc.new_page(pno=pos, width=W, height=H)
                page.insert_image(pymupdf.Rect(20, 20, W - 20, H - 20), filename=str(p), keep_proportion=True)
                pos += 1
    full = pymupdf.open(main_pdf)
    full.insert_pdf(doc)
    doc.close()
    try:
        pdf_shrink.shrink_doc(full)
        full.subset_fonts()
    except Exception:  # noqa: BLE001 — 줄이기 못 하면 그대로
        pass
    tmp = dest.with_suffix(".tmp.pdf")
    full.save(tmp, garbage=3, deflate=True)
    full.close()
    tmp.replace(dest)
    return appx_pdf, dest


def _selfcheck() -> None:
    assert _n(" 1. 과업 지시서 ") == "1.과업지시서"


if __name__ == "__main__":
    _selfcheck()
    print("ok")
