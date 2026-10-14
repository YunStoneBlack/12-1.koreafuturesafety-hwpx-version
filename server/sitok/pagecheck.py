"""시특법 보고서 자동 쪽 검사(2026-10-12 사용자 — "다른 데서도 표가 늘면 부자연스러운 쪽이 생길 수 있으니 대비") — 미리 막지 못한 곳도 놓치지 않게.

한글이 만든 PDF(관리대장·계약서·사진첩을 합치기 전 — 본문 쪽 번호가 최종과 같음)를 훑어 회차 카드 경고로:
- 제목만 쪽 끝: 쪽 마지막 줄이 절 제목(1.2.4 …·1) …·가. …)이고 쪽 아래쪽에 있음(다음 쪽에 그 내용).
- 꼬리말 넘음: 본문 글·선이 꼬리말 줄(쪽 아래 로고) 아래로 — 표가 한 쪽보다 커져 잘렸을 수 있음.
- 넘친 몇 줄만 있는 쪽: 앞 쪽이 꽉 찼는데 이 쪽엔 몇 줄뿐(결과표·표 꼬리가 넘침 등).
원본이 일부러 새 쪽에서 시작하게 한 절(문단 쪽 나눔)·구역 첫 쪽·간지(장 표지)는 빼고 봄.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

HEAD = re.compile(r"^(\d+(\.\d+)+\.?|\d+\)|[가-하]\.)\s*\S")
TOP = 70  # 머리말 아래(pt)


def _key(s: str) -> str:
    return re.sub(r"\s", "", s or "")[:12]


def designed_starts(hwpx: Path) -> set[str]:
    """원본이 새 쪽에서 시작하게 한 곳의 첫 글 — 쪽 나눔 문단(안에 표가 있으면 그 표 첫 칸 글도)·구역 첫 문단."""
    from server.sitok import report_build as rb

    out: set[str] = set()
    with zipfile.ZipFile(hwpx) as z:
        for n in rb._sections(z):
            root = etree.fromstring(z.read(n))
            tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
            for i, p in enumerate(tops):
                if i == 0 or p.get("pageBreak") == "1":
                    t = rb._top_text(p)
                    if t:
                        out.add(_key(t))
                    tbl = next(p.iter(f"{{{rb.HP}}}tbl"), None)
                    if tbl is not None:
                        out.add(_key(rb._cell_text(rb._cells(tbl).get((0, 0), tbl))))
                    if not t and tbl is None and i + 1 < len(tops):  # 쪽 나눔이 빈 문단에 걸린 경우 — 다음 문단 글
                        out.add(_key(rb._top_text(tops[i + 1])))
    out.discard("")
    return out


def _body(pg) -> tuple[list[tuple[float, float, str]], float, float, list]:
    """(본문 줄들 [(y0, y1, 글)], 내용 끝 y, 꼬리말 줄 y, 꼬리말을 넘은 선)."""
    H = pg.rect.height
    foot = min([rr.y0 for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0]) if rr.y0 > H * 0.85] or [H - 63])
    lines = []
    for b in pg.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t and TOP < ln["bbox"][1] < foot - 2:
                lines.append((ln["bbox"][1], ln["bbox"][3], t))
    draws = [d["rect"] for d in pg.get_drawings() if TOP < d["rect"].y0 < foot - 2 and d["rect"].height < H * 0.9]
    over = [r for r in draws if r.y1 > foot + 1 and r.y0 < foot - 20]
    pics = [rr for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0]) if TOP < rr.y0 < foot - 2]
    bottom = max([y1 for _, y1, _ in lines] + [r.y1 for r in draws] + [r.y1 for r in pics] + [0])
    return sorted(lines), bottom, foot, over


def _divider(lines) -> bool:
    """간지(장·편·부록 표지) — 짧은 줄 몇 개뿐, 또는 "제 N 장" + 소목차(1.1 …) 줄들."""
    if len(lines) <= 6 and all(len(t) <= 30 for _, _, t in lines):
        return True
    toc = sum(1 for _, _, t in lines if re.match(r"^\d+\.\d+\s", t) and len(t) <= 30)
    return toc >= 3 and len(lines) <= 14 and any(re.match(r"^제\s*\d+\s*장", t) for _, _, t in lines)


def scan(pdf: Path, hwpx: Path, limit: int = 12, skip: set[int] | None = None) -> list[str]:
    """경고 글들(쪽 번호 순, 많으면 limit개까지 + 나머지 개수). skip = 안 볼 쪽(0부터 — 끼운 도면 쪽)."""
    import pymupdf

    starts = designed_starts(hwpx)
    doc = pymupdf.open(pdf)
    pages = [_body(pg) for pg in doc]
    out = []
    skip = skip or set()
    for i, (lines, bottom, foot, over) in enumerate(pages):
        if i in skip or i - 1 in skip and i + 1 in skip:
            continue
        span = foot - TOP
        if over or any(y1 > foot + 1 for _, y1, _ in lines):
            out.append(f"{i + 1}쪽: 내용이 쪽 아래(꼬리말)를 넘음 — 표가 잘렸을 수 있음")
        if not lines or _divider(lines):
            continue
        last_y0, _, last = lines[-1]
        nxt = pages[i + 1][0] if i + 1 < len(pages) else []
        if HEAD.match(last) and len(last) <= 45 and last_y0 > TOP + span * 0.7 and len(lines) > 1 and nxt and _key(nxt[0][2]) not in starts:
            out.append(f"{i + 1}쪽: 제목 '{last[:20]}'만 쪽 끝에 있음")
        if i > 0 and _key(lines[0][2]) not in starts and len(lines) <= 6 and bottom < TOP + span * 0.2:
            prev_lines, prev_bottom, prev_foot, _ = pages[i - 1]
            if prev_lines and prev_bottom > TOP + (prev_foot - TOP) * 0.8 and not _divider(prev_lines):
                out.append(f"{i + 1}쪽: 앞 쪽에서 넘친 몇 줄만 있음('{lines[0][2][:16]}…')")
    if len(out) > limit:
        out = out[:limit] + [f"외 {len(out) - limit}곳"]
    return out


HEAD_WARN = re.compile(r"제목 '(.+?)'만 쪽 끝에 있음")


def push_headings(hwpx: Path, found: list[str]) -> list[str]:
    """scan이 "제목 'X'만 쪽 끝에 있음"이라 한 제목 문단을 새 쪽에서 시작하게(pageBreak) 하고 hwpx를 다시 씀 — 형 10/14 "2~3줄 애매하게 넘어가면
    아예 넘겨버려". 돌려주는 값 = 민 제목들(비면 안 바꿈). 부르는 쪽이 PDF를 한 번 더 뽑는다."""
    from server.sitok import report_build as rb

    keys = {_key(m[1]) for w in found for m in [HEAD_WARN.search(w)] if m}
    if not keys:
        return []
    pushed: list[str] = []
    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    for n in sections:
        root = etree.fromstring(data[n])
        hit = False
        for p in root:
            if p.tag != f"{{{rb.HP}}}p" or p.get("pageBreak") == "1":
                continue
            t = rb._top_text(p)
            if t and _key(t) in keys:
                p.set("pageBreak", "1")
                pushed.append(t[:20])
                hit = True
        if hit:
            data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if not pushed:
        return []
    _rewrite(hwpx, infos, data)
    return pushed


def _rewrite(hwpx: Path, infos, data: dict) -> None:
    import time

    tmp = hwpx.with_suffix(".push.hwpx")
    with zipfile.ZipFile(tmp, "w") as zout:
        for i in infos:
            zout.writestr(i.filename, data[i.filename], compress_type=zipfile.ZIP_STORED if i.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    for k in range(5):  # 누가 잠깐 열어 두었으면(미리보기 등) 잠시 뒤 다시
        try:
            tmp.replace(hwpx)
            return
        except PermissionError:
            if k == 4:
                raise
            time.sleep(1.5)


CAPTION = re.compile(r"^【[^】]*】")


def _chapter_start(p, rb) -> bool:
    """장 시작(장 제목 "제N장 …"·간지 머리 띠 표·"시설물편")은 늘 새 쪽 — 당기지 않음."""
    t = rb._top_text(p).strip().replace(" ", "")
    if re.match(r"^제\d+장", t) or t in ("시설물편", "공통편"):
        return True
    tbl = next(p.iter(f"{{{rb.HP}}}tbl"), None)
    return tbl is not None and tbl.get("rowCnt") == "1" and tbl.get("colCnt") == "2"


def _photo_rows_shrink(tbl, rb, cut: int) -> bool:
    """그림이 든 줄 높이를 합쳐 cut(HWPUNIT)만큼 줄임 — 그림도 같은 비율로(가운데). 그림 줄이 너무 작아지면(원래의 55% 미만) 안 함."""
    cells = rb._cells(tbl)
    rows: dict = {}
    for (r, c), tc in cells.items():
        if next(tc.iter(f"{{{rb.HP}}}pic"), None) is not None and rb._span(tc, "rowSpan") == 1:
            rows[r] = max(rows.get(r, 0), int(tc.find(f"{{{rb.HP}}}cellSz").get("height") or 0))
    total = sum(rows.values())
    if not total or cut <= 0 or total - cut < total * 0.55:
        return False
    k = (total - cut) / total
    for (r, c), tc in cells.items():
        if r not in rows or rb._span(tc, "rowSpan") != 1:
            continue
        csz = tc.find(f"{{{rb.HP}}}cellSz")
        csz.set("height", str(int(int(csz.get("height") or 0) * k)))
        for pic in tc.iter(f"{{{rb.HP}}}pic"):
            for tag in ("curSz", "sz"):
                el = pic.find(f"{{{rb.HP}}}{tag}")
                if el is not None:
                    el.set("width", str(int(int(el.get("width") or 0) * k)))
                    el.set("height", str(int(int(el.get("height") or 0) * k)))
    tsz = tbl.find(f"{{{rb.HP}}}sz")
    if tsz is not None:
        tsz.set("height", str(max(int(int(tsz.get("height") or 0) - cut), 0)))
    return True


def fill_gaps(hwpx: Path, pdf: Path, sections_from: int = 1) -> list[str]:
    """빈 자리 메우기(형 10/15 "빈 공간이 있고 아래는 표만 달랑 — 빈 공간에 표를 끼워 넣어 한 쪽에 쏙", "쓸데없는 빈 페이지") — PDF를 보고 hwpx를 고침:
    ① 빈 쪽(머리말·꼬리말만) 다음 쪽이 원본 쪽 나눔으로 시작하면 그 쪽 나눔을 뺌.
    ② 쪽 아래가 25% 넘게 비었고 다음 쪽이 원본 쪽 나눔 문단(장 시작 아님)으로 시작하면 — 다음 쪽 내용이 빈 자리에 들어가면 쪽 나눔을 뺌,
       조금(20%까지) 크고 사진 표면 사진 줄을 줄여서 같이 당김.
    ③ 쪽 끝이 캡션【…】이고 다음 쪽이 표로 시작(글자처럼 취급 표가 통째로 넘어감)하면 — 사진 줄을 줄여 그 표를 빈 자리에 넣음.
    sections_from = 고칠 구역 시작(1 = 시설물편·본문 구역만, 앞부분 결과표·요약문은 안 건드림). 돌려주는 값 = 고친 곳 설명(비면 안 바꿈)."""
    import pymupdf

    from server.sitok import report_build as rb

    doc = pymupdf.open(pdf)
    pages = [_body(pg) for pg in doc]
    has_pic = [any(TOP < rr.y0 < pages[i][2] - 2 for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0])) for i, pg in enumerate(doc)]
    doc.close()

    def divider(i: int) -> bool:  # 간지 = 짧은 줄 몇 개뿐이고 사진·캡션이 없는 쪽(사진 표만 있는 쪽·제목+캡션만 남은 쪽은 간지 아님)
        lines = pages[i][0]
        return bool(lines) and _divider(lines) and not has_pic[i] and not any(CAPTION.match(t) for _, _, t in lines)

    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    roots = {n: etree.fromstring(data[n]) for n in sections}
    if sections_from < 0:  # 뒤에서 몇 번째 구역부터(부록은 마지막 구역 = 과업수행계획서·사전검토보고서만)
        sections_from = max(len(sections) + sections_from, 0)
    breaks = []  # 원본 쪽 나눔 문단(구역 순서대로) [(구역, 문단, 키)]
    for si, n in enumerate(sections):
        tops = [p for p in roots[n] if p.tag == f"{{{rb.HP}}}p"]
        for i, p in enumerate(tops):
            if p.get("pageBreak") != "1":
                continue
            t = rb._top_text(p).strip()
            if not t:
                tbl = next(p.iter(f"{{{rb.HP}}}tbl"), None)
                t = rb._cell_text(rb._cells(tbl).get((0, 0), tbl)) if tbl is not None else (rb._top_text(tops[i + 1]) if i + 1 < len(tops) else "")
            breaks.append((si, p, _key(t), tops, i))
    caps = []  # 캡션 문단 [(구역, 문단, 키, tops, i)]
    for si, n in enumerate(sections):
        tops = [p for p in roots[n] if p.tag == f"{{{rb.HP}}}p"]
        for i, p in enumerate(tops):
            if CAPTION.match(rb._top_text(p).strip()):
                caps.append((si, p, _key(rb._top_text(p)), tops, i))
    done: list[str] = []
    bi = 0
    cap_seen: dict = {}
    hit_sections: set = set()
    for i, (lines, bottom, foot, _) in enumerate(pages[:-1]):
        for _, _, t in lines:  # 캡션 순번은 문서 전체 순서로(같은 캡션이 동마다 있음)
            if CAPTION.match(t or ""):
                cap_seen[_key(t)] = cap_seen.get(_key(t), 0) + 1
        nxt_lines, nxt_bottom, nxt_foot, _ = pages[i + 1]
        if not nxt_lines:
            continue
        first = _key(nxt_lines[0][2])
        span = foot - TOP
        gap = foot - max(bottom, TOP)
        # 다음 쪽이 원본 쪽 나눔으로 시작하는지(순서대로 맞춰 감)
        match = next((j for j in range(bi, len(breaks)) if breaks[j][2] and breaks[j][2] == first), None)  # 쪽 나눔은 문서 순서대로 쪽 첫 줄에 나옴
        cap_last = lines and CAPTION.match(lines[-1][2] or "")
        if match is not None:
            bi = match + 1
        if not lines or divider(i) or divider(i + 1):
            if not lines and not has_pic[i] and match is not None and not divider(i + 1):  # ① 빈 쪽
                si, p, _, tops, idx = breaks[match]
                if si >= sections_from and not _chapter_start(p, rb):
                    p.set("pageBreak", "0")
                    hit_sections.add(sections[si])
                    done.append(f"{i + 1}쪽 빈 쪽")
            continue
        need = nxt_bottom - TOP  # 다음 쪽 내용 높이(pt)
        if match is not None and gap > span * 0.25:  # ②
            si, p, _, tops, idx = breaks[match]
            if si < sections_from or _chapter_start(p, rb):
                continue
            if need <= gap - 12:
                p.set("pageBreak", "0")
                hit_sections.add(sections[si])
                done.append(f"{i + 2}쪽 당김")
            elif need <= (gap - 12) / 0.8:
                tbl = next((t for q in tops[idx:idx + 4] for t in q.iter(f"{{{rb.HP}}}tbl") if next(t.iterancestors(f"{{{rb.HP}}}tbl"), None) is None), None)
                if tbl is not None and _photo_rows_shrink(tbl, rb, int((need - gap + 16) * 100)):
                    p.set("pageBreak", "0")
                    hit_sections.add(sections[si])
                    done.append(f"{i + 2}쪽 사진 줄여 당김")
        elif cap_last and not CAPTION.match(nxt_lines[0][2] or ""):  # ③ 캡션만 쪽 끝, 표·그림은 다음 쪽
            k = _key(lines[-1][2])
            hits = [c for c in caps if c[2] == k]
            if len(hits) >= cap_seen[k]:
                si, p, _, tops, idx = hits[cap_seen[k] - 1]
                if si < sections_from:
                    continue

                def obj(q) -> bool:
                    return next(q.iter(f"{{{rb.HP}}}tbl"), None) is not None or next(q.iter(f"{{{rb.HP}}}pic"), None) is not None
                if obj(p) or not any(obj(q) for q in tops[idx + 1:idx + 3]) or (idx > 0 and obj(tops[idx - 1])):
                    continue  # 캡션 다음 문단에 표·그림이 오는 것만(그림과 한 문단인 캡션·그림 아래 캡션은 쪽 끝에 있어도 정상)
                tbl = next((t for q in tops[idx:idx + 3] for t in q.iter(f"{{{rb.HP}}}tbl") if next(t.iterancestors(f"{{{rb.HP}}}tbl"), None) is None), None)
                if (gap > span * 0.25 and gap - 12 < need <= (gap - 12) / 0.8 and tbl is not None
                        and _photo_rows_shrink(tbl, rb, int((need - gap + 16) * 100))):
                    hit_sections.add(sections[si])
                    done.append(f"{i + 2}쪽 표 줄여 앞 쪽에")
                else:  # 못 줄이면 캡션(바로 위 절 제목까지)을 표와 같이 다음 쪽으로(형 10/14 "애매하면 아예 넘겨")
                    prev_t = rb._top_text(tops[idx - 1]).strip() if idx > 0 else ""
                    target = tops[idx - 1] if prev_t and HEAD.match(prev_t) and len(prev_t) <= 45 else p
                    if target.get("pageBreak") != "1":
                        target.set("pageBreak", "1")
                        hit_sections.add(sections[si])
                        done.append(f"{i + 1}쪽 캡션 '{lines[-1][2][:12]}' 다음 쪽으로")
    if not done:
        return []
    for n in hit_sections:
        data[n] = etree.tostring(roots[n], xml_declaration=True, encoding="UTF-8", standalone=True)
    _rewrite(hwpx, infos, data)
    return done


def split_result_tables(hwpx: Path, pdf: Path) -> list[str]:
    """PDF에서 결과표("안전점검 결과표"+"가. 일반현황" 쪽)가 한 쪽을 넘쳤으면(그 쪽에 '다. 책임'은 있는데 마지막 줄 '후속 조치사항'이 없음) hwpx의 그 결과표를
    '다.'부터 새 쪽 둘째 표로(rb.split_result_table) 다시 씀 — 정기·정밀 공용, 동마다 결과표가 여럿이면 순서대로. 돌려주는 값 = 나눈 결과표 제목들."""
    import pymupdf

    from server.sitok import report_build as rb

    doc = pymupdf.open(pdf)
    over = []
    for i, pg in enumerate(doc):
        t = pg.get_text()
        if "안전점검 결과표" in t and "가. 일반현황" in t:
            over.append("다. 책임" in t and "후속" not in t)
    doc.close()
    if not any(over):
        return []
    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    done: list[str] = []
    n = 0
    for name in sections:
        root = etree.fromstring(data[name])
        hit = False
        for tbl in list(root.iter(f"{{{rb.HP}}}tbl")):
            if next(tbl.iterancestors(f"{{{rb.HP}}}tbl"), None) is not None:
                continue
            cells = rb._cells(tbl)
            texts = {re.sub(r"\s", "", rb._cell_text(v)) for v in cells.values()}
            if not {"용역명", "점검기간", "관리주체명"} <= texts:
                continue
            if n < len(over) and over[n] and rb.split_result_table(root, tbl):
                done.append(rb._cell_text(cells.get((1, 1), tbl)).strip()[:20] or f"결과표 {n + 1}")
                hit = True
            n += 1
        if hit:
            data[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if done:
        _rewrite(hwpx, infos, data)
    return done
