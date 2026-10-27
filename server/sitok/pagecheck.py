"""시특법 보고서 자동 쪽 검사(2026-10-12 사용자 — "다른 데서도 표가 늘면 부자연스러운 쪽이 생길 수 있으니 대비") — 미리 막지 못한 곳도 놓치지 않게.

한글이 만든 PDF(관리대장·계약서·사진첩을 합치기 전 — 본문 쪽 번호가 최종과 같음)를 훑어 회차 카드 경고로:
- 제목만 쪽 끝: 쪽 마지막 줄이 절 제목(1.2.4 …·1) …·가. …)이고 쪽 아래쪽에 있음(다음 쪽에 그 내용).
- 꼬리말 넘음: 본문 글·선이 꼬리말 줄(쪽 아래 로고) 아래로 — 표가 한 쪽보다 커져 잘렸을 수 있음.
- 넘친 몇 줄만 있는 쪽: 앞 쪽이 꽉 찼는데 이 쪽엔 몇 줄뿐(결과표·표 꼬리가 넘침 등).
원본이 일부러 새 쪽에서 시작하게 한 절(문단 쪽 나눔)·구역 첫 쪽·간지(장 표지)는 빼고 봄.
"""
from __future__ import annotations

import contextlib
import re
import threading
import zipfile
from pathlib import Path

from lxml import etree

HEAD = re.compile(r"^(\d+(\.\d+)+\.?|\d+\)|[가-하]\.)\s*\S")
TOP = 70  # 머리말 아래(pt) — 쓰는 곳은 _top()(내진은 49, top_at)
_TOP_TL = threading.local()


def _top() -> float:
    """본문 시작 y(pt) — 기본 TOP, 내진 보고서는 머리말 선이 47pt라 49(top_at). 스레드마다(다른 보고서 만들기와 같이 돌아도 안 섞이게)."""
    return getattr(_TOP_TL, "v", None) or TOP


@contextlib.contextmanager
def top_at(v: float):
    """이 스레드에서만 본문 시작 y를 v로(10/27 내진 — 쪽 맨 위 52pt 글을 머리말로 빼서 "몇 줄만 넘친 쪽"을 못 잡고 쪽 맨 위 제목을 넘친 줄로 잘못 잡던 것)."""
    old = getattr(_TOP_TL, "v", None)
    _TOP_TL.v = v
    try:
        yield
    finally:
        _TOP_TL.v = old


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


def _body(pg, rects: list | None = None, imgs: list | None = None) -> tuple[list[tuple[float, float, str]], float, float, list]:
    """(본문 줄들 [(y0, y1, 글)], 내용 끝 y, 꼬리말 줄 y, 꼬리말을 넘은 선). rects·imgs = 이미 읽은 선·그림 위치(_pages — 두 번 안 읽게)."""
    H = pg.rect.height
    if imgs is None:
        imgs = [rr for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0])]
    if rects is None:
        rects = [d["rect"] for d in pg.get_drawings()]
    foot = min([rr.y0 for rr in imgs if rr.y0 > H * 0.85] or [H - 63])
    lines = []
    for b in pg.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t and _top() < ln["bbox"][1] < foot - 2:
                lines.append((ln["bbox"][1], ln["bbox"][3], t))
    draws = [r for r in rects if _top() < r.y0 < foot - 2 and r.height < H * 0.9]
    over = [r for r in draws if r.y1 > foot + 1 and r.y0 < foot - 20]
    pics = [rr for rr in imgs if _top() < rr.y0 < foot - 2]
    bottom = max([y1 for _, y1, _ in lines] + [r.y1 for r in draws] + [r.y1 for r in pics] + [0])
    return sorted(lines), bottom, foot, over


_READ: dict = {}  # PDF 읽은 결과 하나(같은 파일을 넘침·꼬리·문제 수 검사가 또 읽지 않게 — 10/26 산안법 한 건 검사 1.1초 → 절반)


def _pages(pdf: Path) -> tuple[list, list, list, list]:
    """(쪽마다 _body, 쪽마다 선 그림 rect, 쪽 높이, 쪽마다 그림 rect) — 파일·크기·고친 시각이 같으면 다시 안 읽음."""
    import pymupdf

    st = pdf.stat()
    key = (str(pdf), st.st_size, st.st_mtime_ns, _top())
    if key not in _READ:
        bodies, rects, heights, imgs = [], [], [], []
        with pymupdf.open(pdf) as doc:
            for pg in doc:
                rr = [d["rect"] for d in pg.get_drawings()]
                ii = [x for info in pg.get_images(full=True) for x in pg.get_image_rects(info[0])]
                bodies.append(_body(pg, rr, ii))
                rects.append(rr)
                heights.append(pg.rect.height)
                imgs.append(ii)
        got = (bodies, rects, heights, imgs)
        _READ.clear()
        _READ[key] = got
    return _READ[key]


def _divider(lines) -> bool:
    """간지(장·편·부록 표지) — 짧은 줄 몇 개뿐, 또는 "제 N 장" + 소목차(1.1 …) 줄들.
    "~다."로 끝나는 줄이 있으면 간지가 아님 — 앞 쪽 글상자에서 넘친 문장 한 줄(10/19 요약문 결언 "의 사용성에는 문제가 없을 것으로 판단된다.")."""
    if any(t.rstrip().endswith("다.") for _, _, t in lines):
        return False
    if all(t.lstrip().startswith("※") for _, _, t in lines):  # 주석(※)만 = 앞 표에서 넘친 주석(10/27 내진 "※ □ : 조사불가" 두 줄만 다음 쪽)
        return False
    if len(lines) <= 6 and all(len(t) <= 30 for _, _, t in lines):
        return True
    toc = sum(1 for _, _, t in lines if re.match(r"^\d+\.\d+\s", t) and len(t) <= 30)
    return toc >= 3 and len(lines) <= 14 and any(re.match(r"^제\s*\d+\s*장", t) for _, _, t in lines)


def scan(pdf: Path, hwpx: Path, limit: int = 12, skip: set[int] | None = None) -> list[str]:
    """경고 글들(쪽 번호 순, 많으면 limit개까지 + 나머지 개수). skip = 안 볼 쪽(0부터 — 끼운 도면 쪽)."""
    starts = designed_starts(hwpx)
    pages = _pages(pdf)[0]
    out = []
    skip = skip or set()
    for i, (lines, bottom, foot, over) in enumerate(pages):
        if i in skip or i - 1 in skip and i + 1 in skip:
            continue
        span = foot - _top()
        if over or any(y1 > foot + 1 for _, y1, _ in lines):
            out.append(f"{i + 1}쪽: 내용이 쪽 아래(꼬리말)를 넘음 — 표가 잘렸을 수 있음")
        if not lines or _divider(lines):
            continue
        last_y0, _, last = lines[-1]
        nxt = pages[i + 1][0] if i + 1 < len(pages) else []
        if HEAD.match(last) and len(last) <= 45 and last_y0 > _top() + span * 0.7 and len(lines) > 1 and nxt and _key(nxt[0][2]) not in starts:
            out.append(f"{i + 1}쪽: 제목 '{last[:20]}'만 쪽 끝에 있음")
        if i > 0 and _key(lines[0][2]) not in starts and len(lines) <= 6 and bottom < _top() + span * 0.2:
            prev_lines, prev_bottom, prev_foot, _ = pages[i - 1]
            if prev_lines and prev_bottom > _top() + (prev_foot - _top()) * 0.8 and not _divider(prev_lines):
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


def _align(a: list[str], b: list[str]) -> dict[int, int]:
    """두 순서(쪽 나눔 문단 글 a·쪽 첫 줄 글 b)를 최장 공통 부분열로 짝지음 → {b 번호: a 번호} — 같은 글이 동마다 되풀이돼도 순서대로 맞음."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] and a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    out: dict[int, int] = {}
    i = j = 0
    while i < n and j < m:
        if a[i] and a[i] == b[j]:
            out[j] = i
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def fill_gaps(hwpx: Path, pdf: Path, sections_from: int = 1, keep: set | None = None) -> list[str]:
    """빈 자리 메우기(형 10/15 "빈 공간이 있고 아래는 표만 달랑 — 빈 공간에 표를 끼워 넣어 한 쪽에 쏙", "쓸데없는 빈 페이지") — PDF를 보고 hwpx를 고침:
    ① 빈 쪽(머리말·꼬리말만) 다음 쪽이 원본 쪽 나눔으로 시작하면 그 쪽 나눔을 뺌.
    ② 쪽 아래가 25% 넘게 비었고 다음 쪽이 원본 쪽 나눔 문단(장 시작 아님)으로 시작하면 — 다음 쪽 내용이 빈 자리에 들어가면 쪽 나눔을 뺌,
       조금(20%까지) 크고 사진 표면 사진 줄을 줄여서 같이 당김.
    ③ 쪽 끝이 캡션【…】이고 다음 쪽이 표로 시작(글자처럼 취급 표가 통째로 넘어감)하면 — 사진 줄을 줄여 그 표를 빈 자리에 넣음.
    sections_from = 고칠 구역 시작(1 = 시설물편·본문 구역만, 앞부분 결과표·요약문은 안 건드림). 돌려주는 값 = 고친 곳 설명(비면 안 바꿈)."""
    import pymupdf

    from server.sitok import report_build as rb

    keep = keep if keep is not None else set()
    doc = pymupdf.open(pdf)
    pages = [_body(pg) for pg in doc]
    has_pic = [any(_top() < rr.y0 < pages[i][2] - 2 for info in pg.get_images(full=True) for rr in pg.get_image_rects(info[0])) for i, pg in enumerate(doc)]
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
    starts = _align([b_[2] for b_ in breaks], [_key(pg[0][0][2]) if pg[0] else "" for pg in pages])  # 쪽 번호 → 그 쪽을 시작한 쪽 나눔
    cap_seen: dict = {}
    hit_sections: set = set()
    for i, (lines, bottom, foot, _) in enumerate(pages[:-1]):
        for _, _, t in lines:  # 캡션 순번은 문서 전체 순서로(같은 캡션이 동마다 있음)
            if CAPTION.match(t or ""):
                cap_seen[_key(t)] = cap_seen.get(_key(t), 0) + 1
        nxt_lines, nxt_bottom, nxt_foot, _ = pages[i + 1]
        if not nxt_lines:
            continue
        span = foot - _top()
        gap = foot - max(bottom, _top())
        # 다음 쪽이 원본 쪽 나눔으로 시작하는지(순서대로 맞춰 감)
        match = starts.get(i + 1)
        cap_last = lines and CAPTION.match(lines[-1][2] or "")
        if not lines or divider(i) or divider(i + 1):
            if not lines and not has_pic[i] and match is not None and not divider(i + 1):  # ① 빈 쪽
                si, p, _, tops, idx = breaks[match]
                if si >= sections_from and not _chapter_start(p, rb):
                    p.set("pageBreak", "0")
                    hit_sections.add(sections[si])
                    done.append(f"{i + 1}쪽 빈 쪽")
            continue
        need = nxt_bottom - _top()  # 다음 쪽 내용 높이(pt)
        if match is not None and gap > span * 0.25:  # ②
            si, p, key, tops, idx = breaks[match]
            if si < sections_from or _chapter_start(p, rb) or key in keep:
                continue  # 장 시작·앞 회에서 일부러 넘긴 것(캡션·제목)은 안 당김
            if need <= gap - 24:
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
                        keep.add(_key(rb._top_text(target)))
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


def orphans(pdf: Path, hwpx: Path) -> list[tuple[int, str, float, int]]:
    """앞 쪽이 꽉 찼는데 몇 줄만 넘어온 쪽 [(쪽 0부터, 넘친 마지막 줄 글, 넘친 높이 pt, 그 글이 PDF에서 몇 번째로 나온 것인지 0부터)].
    넘친 높이는 글자 줄만으로(꼬리말 띠·쪽 테두리 선은 빼고), 표 머리줄이 되풀이돼도 되게 줄 수는 14줄까지."""
    starts = designed_starts(hwpx)
    pages = _pages(pdf)[0]
    out = []
    for i, (lines, _, foot, _) in enumerate(pages):
        span = foot - _top()
        if i == 0 or not lines or _divider(lines) or _key(lines[0][2]) in starts or len(lines) > 14:
            continue
        text_bottom = max(y1 for _, y1, _ in lines)
        if text_bottom >= _top() + span * 0.25:
            continue
        prev_lines, prev_bottom, prev_foot, _ = pages[i - 1]
        if prev_lines and prev_bottom > _top() + (prev_foot - _top()) * 0.8 and not _divider(prev_lines):
            last = max(lines, key=lambda x: (x[0], len(x[2])))[2]
            k = sum(1 for j in range(i) if any(_key(last) == _key(t) for _, _, t in pages[j][0]))
            out.append((i, last, text_bottom - _top(), k))
    return out


def _row_spare(tbl, rb) -> tuple[dict, dict]:
    """줄마다 (지금 높이, 여유 = 지금 높이 − 글 어림 − 200(약 2mm 여유는 남김)) — 여유만 줄이면 글은 그대로."""
    cur = {}
    for (r, _), tc in rb._cells(tbl).items():
        if rb._span(tc, "rowSpan") == 1:
            cur[r] = max(cur.get(r, 0), int(tc.find(f"{{{rb.HP}}}cellSz").get("height") or 0))
    est = rb._table_row_heights(tbl, text_only=True)
    return cur, {r: max(0, h - est.get(r, 0) - 200) for r, h in cur.items()}


def _squeeze_table(tbl, need: int, rb) -> int:
    """표 tbl을 need(HWPUNIT)만큼 낮춤 — 줄마다 글 어림보다 큰 여유 높이(칸 안 빈 여백)만 비율대로, 글 높이·줄 간격은 그대로. 줄인 양.
    (10/23 사용자 "표 안에 글자가 무리하게 우겨넣어질까 봐" — 전엔 모자라면 표 안 줄 간격을 ×0.85로 줄였음. 부르는 쪽이 여백 합이 need 이상일 때만 부름)"""
    from server.sitok.precision_build import _set_row_height

    cur, spare = _row_spare(tbl, rb)
    total = sum(spare.values())
    done = 0
    if total > 0:
        k = min(1.0, need / total)
        for r, s in spare.items():
            cut = int(s * k)
            if cut > 0:
                _set_row_height(tbl, r, cur[r] - cut)
                done += cut
    if done:  # 합친 칸(여러 줄) 높이 = 그 줄들 높이 합 — 줄만 줄이고 합친 칸이 옛 높이로 남으면 표가 다시 커짐
        heights = {}
        for (r, _), tc in rb._cells(tbl).items():
            if rb._span(tc, "rowSpan") == 1:
                heights[r] = max(heights.get(r, 0), int(tc.find(f"{{{rb.HP}}}cellSz").get("height") or 0))
        for (r, _), tc in rb._cells(tbl).items():
            span = rb._span(tc, "rowSpan")
            if span > 1 and all(rr in heights for rr in range(r, r + span)):
                tc.find(f"{{{rb.HP}}}cellSz").set("height", str(sum(heights[rr] for rr in range(r, r + span))))
    return done


def squeeze_overflow(hwpx: Path, pdf: Path, sections_from: int = 1) -> list[str]:
    """몇 줄만 넘어간 쪽(형 10/19 "결언·1.3 분석표·1.4 결과표가 한두 줄 넘어감 — 고쳐도 매번 생길 수 있으니 방식으로") — 넘친 덩어리를 찾아 그만큼 줄임:
    넘친 첫 줄이 여러 줄 표 안이면 그 표, 짧은 글·상자(1줄 표)면 바로 앞 큰 표. 고친 곳 설명(비면 안 바꿈 — 부르는 쪽이 PDF를 한 번 더)."""
    from server.sitok import report_build as rb

    found = orphans(pdf, hwpx)
    if not found:
        return []
    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    roots = {n: etree.fromstring(data[n]) for n in sections[sections_from:]}
    done = []
    flat = lambda s: re.sub(r"\s", "", s or "")  # noqa: E731

    def find(hit, nth: int):
        """넘친 줄이 든 표 — hit(글) = 이 문단·칸 글에 넘친 줄이 있는지, nth = PDF에서 몇 번째로 나온 것인지."""
        seen = 0
        for root in roots.values():
            tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
            for i, p in enumerate(tops):
                tbls = [t for t in p.iter(f"{{{rb.HP}}}tbl")]
                if not hit(rb._top_text(p)) and not any(hit(rb._cell_text(c)) for t in tbls for c in rb._cells(t).values()):
                    continue
                if seen < nth:  # 같은 표가 동마다 되풀이 — PDF에서 몇 번째로 나온 것인지로 짝(1.4 결과표 3개)
                    seen += 1
                    continue
                big = next((t for t in tbls if (int(t.get("rowCnt") or 1) > 1 or len(list(t.iter(f"{{{rb.HP}}}p"))) >= 5)  # 여러 줄 표, 또는 문단 많은 상자(요약문 결언)
                            and any(hit(rb._cell_text(c)) for c in rb._cells(t).values())), None)
                if big is None:  # 짧은 글·상자 — 바로 앞(3문단 안) 큰 표
                    for q in reversed(tops[max(0, i - 3):i]):
                        big = next((t for t in q.iter(f"{{{rb.HP}}}tbl") if int(t.get("rowCnt") or 1) > 1), None)
                        if big is not None:
                            break
                return big
        return None

    for _, first, h, nth in found:
        # 넘친 줄 전체가 든 문단·칸(문단 중간에서 넘쳐도 — 10/19 요약문 결언 "의 사용성에는 …"), 못 찾으면 예전처럼 앞 12글자로 시작하는 칸
        # (PDF는 표 한 줄의 여러 칸 글을 한 줄로 합치기도 함)
        line = flat(first)
        once = len(line) >= 8 and sum(flat("".join(t.text or "" for t in p.iter(rb.T))).count(line)
                                          for root in roots.values() for p in root if p.tag == f"{{{rb.HP}}}p") == 1  # 표 안 글까지
        target = find(lambda t: line in flat(t), 0) if once else None
        if target is None:
            target = find(lambda t: _key(first) in _key(t), nth)
        if target is None:
            continue
        need = int(h * 100 * 1.2) + 800
        if sum(_row_spare(target, rb)[1].values()) < need:  # 칸 안 빈 여백으로 모자라면 글·줄 간격을 우겨넣지 않고 넘어간 그대로(10/23 사용자 — pull_tables와 같게)
            continue
        if _squeeze_table(target, need, rb):
            done.append(f"'{first[:14]}…' 넘침 → 앞 표 칸 여백 {need} 줄임(글 그대로)")
    if not done:
        return []
    for n, root in roots.items():
        data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    _rewrite(hwpx, infos, data)
    return done


def _body_end(hwpx: Path) -> float | None:
    """본문 영역 아래 끝(pt, PDF 좌표) — 첫 구역 쪽 설정(쪽 높이 − 아래 여백 − 꼬리말 여백). 꼬리말 로고 줄보다 위."""
    try:
        with zipfile.ZipFile(hwpx) as z:
            s = z.read(sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))[0]).decode("utf-8")
        pp = re.search(r"<hp:pagePr[^>]*>[\s\S]*?</hp:pagePr>", s)[0]
        h = int(re.search(r'\sheight="(\d+)"', pp)[1])
        mg = dict(re.findall(r'(\w+)="(\d+)"', re.search(r"<hp:margin [^>]*/>", pp)[0]))
        return (h - int(mg["bottom"]) - int(mg["footer"])) / 100
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _same_head(t: str, head: str) -> bool:
    """그 제목 줄인가 — 앞 12글자(빈칸 빼고)가 같고 목차 줄(끝이 쪽 번호 숫자)은 아님."""
    return _key(t) == _key(head) and not re.search(r"\d\s*$", (t or "").strip())


def pull_tables(hwpx: Path, pdf: Path, sections_from: int = 1, squeeze_max: float = 0.15) -> list[str]:
    """제목 + 글자처럼 취급한 표가 통째로 다음 쪽으로 넘어가 앞 쪽 아래가 크게(25% 넘게) 빈 곳(10/19 형 "표가 못생기게 통째로 넘어갔어 자연스럽게",
    "현장마다 표 길이가 다를 건데 여러 상황에서 자연스럽게" — 부록 사전검토 3.1 표, 과업명이 두 줄이 되며 한 줄이 모자람).
    ② 제목은 앞 쪽 끝에 남고 표만 통째로 넘어간 곳도(10/23 형 "표가 또 통째로 밀림" — 의정부 1.4 기타 부대시설 상태조사 결과표: 원본이 새 쪽에서 시작하는 제목이라
    제목만 있는 쪽 + 다음 쪽 표). 고치는 법은 같음:
    - 조금(squeeze_max, 15%까지) 모자라면 그 표를 모자란 만큼 줄여(줄 여유 → 줄 간격 한 단계) 앞 쪽에 통째로,
    - 더 모자라면 표를 쪽에서 나뉘게(rb._splittable — 제목 바로 아래에서 시작해 다음 쪽으로 이어지고 머리 줄은 되풀이).
    원본이 일부러 새 쪽에서 시작한 곳·간지는 뺌. 고친 곳 설명(비면 안 바꿈 — 부르는 쪽이 PDF를 한 번 더)."""
    import pymupdf

    from server.sitok import report_build as rb

    starts = designed_starts(hwpx)
    body_end = _body_end(hwpx)
    with pymupdf.open(pdf) as doc:
        pages = [_body(pg) for pg in doc]
        raw = [[d["rect"] for d in pg.get_drawings() if _top() < d["rect"].y0 < pages[i][2] - 2] for i, pg in enumerate(doc)]
        page_h = [pg.rect.height for pg in doc]
        draws = [sorted((r for r in raw[i] if r.height < pg.rect.height * 0.9), key=lambda r: r.y0) for i, pg in enumerate(doc)]
    found = []  # (제목 글, 모자란 pt, 표 높이 pt, 그 제목이 PDF에서 몇 번째로 나온 것인지 0부터, ② = 표가 뒤따르는 제목만 셈)

    def _short(need: float, room: float, j: int, top: float) -> float:  # 모자란 pt — j쪽 표(위 끝 top)가 쪽 밖까지 넘쳤으면(세로선이 쪽 높이 90%를 넘어 위 draws에서
        # 빠져 머리 줄만 잼, 잘린 만큼은 PDF로 모름: 10/23 시험 칸 9개 늘린 1.4 표 → 800만 줄이고 그대로) 표 높이만큼 모자란 걸로 → 줄이지 않고 나뉘게
        over = any(abs(r.y0 - top) <= 3 and r.y1 > page_h[j] - 2 for r in raw[j])
        return max(need - room, need) if over else need - room

    def table_follows(j: int, idx: int) -> bool:  # j쪽 idx번째 줄(제목) 바로 아래 60pt 안에 표, 또는 쪽 끝 줄이고 다음 쪽이 표로 시작
        if _divider(pages[j][0]) and len(pages[j][0]) > 2:  # 장 간지 소목차 줄(점선 장식이 작은 선 수백 개라 표로 보였음, 10/23 의정부 48쪽) — 제목 한 줄만 있는 쪽은 셈
            return False
        y1 = pages[j][0][idx][1]
        if any(y1 - 2 <= r.y0 <= y1 + 60 for r in draws[j]):
            return True
        return idx == len(pages[j][0]) - 1 and j + 1 < len(pages) and bool(draws[j + 1]) and bool(pages[j + 1][0]) and draws[j + 1][0].y0 <= pages[j + 1][0][0][0] + 2

    for i in range(len(pages) - 1):
        lines, bottom, foot, _ = pages[i]
        nxt = pages[i + 1][0]
        if lines and nxt and not _divider(nxt) and HEAD.match(lines[-1][2]) and (_key(lines[-1][2]) in starts or len(lines) <= 2):
            r2 = draws[i + 1]
            if r2 and r2[0].y0 <= nxt[0][0] + 2:  # ② 다음 쪽이 표로 시작(첫 줄이 표 안)
                tb = r2[0].y1
                for r in r2:
                    if r.y0 > tb + 3:
                        break
                    tb = max(tb, r.y1)
                need = tb - r2[0].y0 + 6
                room = (body_end or foot - 20) - lines[-1][1] - 4
                if room >= (foot - _top()) * 0.25:
                    k = sum(1 for j in range(i) for idx, (_, _, t) in enumerate(pages[j][0]) if _same_head(t, lines[-1][2]) and table_follows(j, idx))
                    found.append((lines[-1][2], _short(need, room, i + 1, r2[0].y0), need, k, True))
                    continue
        if not lines or not nxt or _divider(lines) or _divider(nxt):
            continue
        head = nxt[0]
        if not HEAD.match(head[2]) or _key(head[2]) in starts:
            continue
        rects = [r for r in draws[i + 1] if r.y0 >= head[1] - 1]
        if not rects or rects[0].y0 > head[1] + 60:  # 제목 바로 아래가 표가 아님
            continue
        table_bottom = rects[0].y1
        for r in rects:  # 이어진 선들 = 그 표
            if r.y0 > table_bottom + 3:
                break
            table_bottom = max(table_bottom, r.y1)
        # 제목 위 문단 간격 — 앞 쪽에서 제목 줄(1. 2. 3.1 …) 앞 빈 간격 중 큰 것(이 문서 모양), 없으면 30pt
        gaps = [y0 - lines[j - 1][1] for j, (y0, _, t) in enumerate(lines) if j and HEAD.match(t)]
        need = table_bottom - head[0] + max(gaps + [24.0]) + 6  # + 여유
        room = (body_end or foot - 20) - bottom
        if room < (foot - _top()) * 0.25:  # 앞 쪽이 별로 안 비었으면 그대로
            continue
        k = sum(1 for j in range(i + 1) if any(_same_head(t, head[2]) for _, _, t in pages[j][0]))
        found.append((head[2], _short(need, room, i + 1, rects[0].y0), need, k, False))
    if not found:
        return []
    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    roots = {n: etree.fromstring(data[n]) for n in sections[sections_from:]}
    done = []
    def char_table(tops: list, i: int):  # 제목 바로 뒤 문단의 글자처럼 취급 표
        for q in tops[i + 1:i + 3]:
            tbl = next(q.iter(f"{{{rb.HP}}}tbl"), None)
            pos = tbl.find(f"{{{rb.HP}}}pos") if tbl is not None else None
            if pos is not None and pos.get("treatAsChar") == "1":
                return tbl
        return None

    def any_table(tops: list, i: int) -> bool:  # 제목 바로 뒤 문단에 표(글자처럼이든 떠 있든) — PDF 쪽 셈(table_follows)과 같게 세려고
        return any(next(q.iter(f"{{{rb.HP}}}tbl"), None) is not None for q in tops[i + 1:i + 3])

    for head, short, need, nth, table_only in found:
        seen = 0
        target = None
        matched = False
        for root in roots.values():
            tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
            for i, p in enumerate(tops):
                if not _same_head(rb._top_text(p), head):
                    continue
                if table_only and not any_table(tops, i):  # ② 표가 뒤따르는 제목만 셈(PDF와 같게 — 이미 나뉘게 바꾼 떠 있는 표도 셈,
                    continue  # 10/26 묶음 동마다 같은 제목: 전엔 글자처럼 표만 세어 서관 대신 급식실 표를 고쳤음)
                if seen < nth:
                    seen += 1
                    continue
                target = char_table(tops, i)  # 그 제목 표가 이미 떠 있는 표면 None — 다른 동 제목으로 넘어가지 않음
                matched = True
                break
            if matched:
                break
        if target is None:
            continue
        cut = int(max(short, 0.0) * 100 * 1.2) + 800
        if short <= need * squeeze_max and sum(_row_spare(target, rb)[1].values()) >= cut:  # 칸 안 빈 여백만으로 될 때만 줄임(글·줄 간격 그대로)
            if _squeeze_table(target, cut, rb):
                done.append(f"'{head[:14]}…' 표가 통째로 넘어감 → 칸 여백 {cut} 줄여 앞 쪽에(글 그대로)")
        else:  # 여백으로 모자라면 글을 우겨넣지 않고 나뉘게
            cells = rb._cells(target)
            head_rows = max([rb._span(tc, "rowSpan") for (r, _), tc in cells.items() if r == 0] or [1])  # 2단 머리(구분·…·실시범위/정기·정밀)면 2
            rb._splittable(target, head_rows)
            om = target.find(f"{{{rb.HP}}}outMargin")
            if om is not None and int(om.get("bottom") or 0) < 1000:  # 자리 차지 표는 문단 줄 간격이 없어 뒤 제목이 표에 붙음 — 아래 여백
                om.set("bottom", "1000")
            done.append(f"'{head[:14]}…' 표가 통째로 넘어감 → 제목 아래에서 시작해 다음 쪽으로 나뉘게")
    if not done:
        return []
    for n, root in roots.items():
        data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    _rewrite(hwpx, infos, data)
    return done


def _label(pg, foot: float) -> int | None:
    """쪽 아래 꼬리말의 쪽 번호(숫자만인 줄) — 장 표지·앞부분처럼 번호를 안 찍은 쪽은 None."""
    for b in pg.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if ln["bbox"][1] >= foot - 2 and t.isdigit():
                return int(t)
    return None


def _toc_norm(s: str) -> str:
    return re.sub(r"[\s.·ㆍ]", "", s or "")


def _unfield(num, rb) -> bool:
    """목차 숫자를 감싼 상호참조 칸(fieldBegin·fieldEnd)을 풀어 그냥 글자로 — 한글이 PDF로 바꿀 때 책갈피 쪽으로 다시 계산해 넣은 숫자를 덮어씀
    (묶음 2·3장 줄은 1장 책갈피를 가리켜 늘 1장 쪽). 푼 게 있으면 True."""
    run = num.getparent()
    kids = list(run)
    i = kids.index(num)
    begin = next((c for c in reversed(kids[:i]) if c.tag == f"{{{rb.HP}}}ctrl" and c.find(f"{{{rb.HP}}}fieldBegin") is not None), None)
    if begin is None:
        return False
    fid = begin.find(f"{{{rb.HP}}}fieldBegin").get("id")
    end = next((c for c in kids[i + 1:] if c.tag == f"{{{rb.HP}}}ctrl" and (e := c.find(f"{{{rb.HP}}}fieldEnd")) is not None and e.get("beginIDRef") == fid), None)
    run.remove(begin)
    if end is not None:
        run.remove(end)
    return True


def fill_toc(hwpx: Path, pdf: Path) -> list[str]:
    """목차 쪽 번호를 실제 쪽으로(10/19 형 "페이지수나 이런 건 다 자동으로 바뀌는 건지" — 목차 숫자는 회사 원본 글자·책갈피 참조 그대로라 묶음 2·3장이
    1장 쪽(35)으로, 표가 길어지면 뒤 절도 어긋났음): 목차 줄(제목 ·····(탭) 숫자) 차례대로 PDF에서 그 제목이 처음 나오는 쪽(목차 다음부터, 앞 줄 쪽 이후)의
    꼬리말 번호(번호 없는 장 표지는 다음 쪽 번호 − 1)를 숫자 칸에. 제목: "제 N장 …"은 그 쪽에 "제N장"과 나머지 이름이 다 있으면, 절("1.3 …")은 간지가 아닌 쪽에서
    그 줄로 시작하면. 못 찾은 줄은 그대로. 찾은 줄은 상호참조를 풀고 글자로(_unfield — 한글이 다시 계산해 덮어써서).
    다 만든 PDF로 — 바꾼 게 있으면 부르는 쪽이 PDF를 한 번 더(목차 숫자만 바뀌어 쪽이 밀리지 않음)."""
    import pymupdf

    from server.sitok import report_build as rb

    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    roots = {n: etree.fromstring(data[n]) for n in sections}
    entries = []  # (제목, 숫자 글자 칸)
    for n in sections:
        for p in roots[n].iter(f"{{{rb.HP}}}p"):
            tab = next((t for t in p.iter(f"{{{rb.HP}}}tab") if t.get("leader") not in (None, "0", "NONE")), None)
            if tab is None or next(p.iterancestors(f"{{{rb.HP}}}tbl"), None) is not None:
                continue
            ts = list(p.iter(rb.T))
            num = next((t for t in reversed(ts) if rb._full(t).strip().isdigit()), None)
            if num is None:
                continue
            title = "".join(rb._full(t) for t in ts if t is not num).strip()
            if title:
                entries.append((title, num))
    if not entries:
        return []
    with pymupdf.open(pdf) as doc:
        bodies = [_body(pg) for pg in doc]
        labels = [_label(pg, bodies[i][2]) for i, pg in enumerate(doc)]
    for i in range(len(labels) - 2, -1, -1):  # 번호 없는 쪽 = 다음 쪽 − 1(장 표지)
        if labels[i] is None and labels[i + 1] is not None and labels[i + 1] > 1:
            labels[i] = labels[i + 1] - 1
    leader = re.compile(r"[·.]{5,}\s*\d+\s*$")
    tocs = [i for i, (lines, _, _, _) in enumerate(bodies) if sum(1 for _, _, t in lines if leader.search(t)) >= 3]
    if not tocs:
        return []
    at = tocs[-1] + 1
    done, missed = 0, []
    for title, num in entries:
        key = _toc_norm(title)
        m = re.match(r"제\s*(\d+)\s*장\.?\s*(.*)$", title.strip())
        hit = None
        for i in range(at, len(bodies)):
            lines = bodies[i][0]
            if m:
                text = _toc_norm(" ".join(t for _, _, t in lines))
                if f"제{m[1]}장" in text and _toc_norm(m[2]) in text and len(set(re.findall(r"제(\d+)장", text))) == 1:  # 장 목록만 있는 편 간지("제1장 …제2장 …")는 뺌
                    hit = i
                    break
            elif not _divider(lines) and any(_toc_norm(t).startswith(key) or (len(_toc_norm(t)) >= 6 and key.startswith(_toc_norm(t))) for _, _, t in lines):
                hit = i
                break
        if hit is None or labels[hit] is None:
            missed.append(title[:16])
            continue
        at = hit
        unfielded = _unfield(num, rb)
        if unfielded or rb._full(num).strip() != str(labels[hit]):
            rb._clear(num, str(labels[hit]))
            done += 1
    if not done:
        return []
    for n, root in roots.items():
        data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    _rewrite(hwpx, infos, data)
    return [f"목차 쪽 번호 {done}곳 고침" + (f"(못 찾은 줄 {len(missed)}: {', '.join(missed[:3])})" if missed else "")]


# ---------- 애매한 넘침 정리(10/26 사용자·민재형 "애매하게 페이지를 초과") — 글자 크기·장평·줄 간격은 절대 안 건드림 ----------
MIN_MARGIN = 283  # 칸 안쪽 위아래 여백은 1mm까지만 줄임(글은 그대로)


def tails(pdf: Path, hwpx: Path) -> list[tuple[int, str, float, int]]:
    """나뉜 표의 꼬리 줄만 다음 쪽 위에 오고 그 아래 다른 내용이 이어지는 곳(10/26 형 사전검토 3.1 "기타시설 두 줄만 다음 쪽" — orphans엔 안 걸림).
    [(쪽, 꼬리에서 앞 쪽에 없던 가장 긴 줄 글, 꼬리 줄 높이 pt(되풀이 머리줄 빼고), 그 글이 PDF에서 몇 번째)]. 사진 든 표·간지는 뺌."""
    starts = designed_starts(hwpx)
    pages, rects, heights, pics = _pages(pdf)
    draws = [sorted((r for r in rects[i] if _top() < r.y0 < pages[i][2] - 2 and r.height < heights[i] * 0.9), key=lambda r: r.y0) for i in range(len(pages))]
    out = []
    for i in range(1, len(pages)):
        lines, _, foot, _ = pages[i]
        prev_lines, _, prev_foot, _ = pages[i - 1]
        if not lines or not draws[i] or not draws[i - 1] or _divider(lines) or _divider(prev_lines) or _key(lines[0][2]) in starts:
            continue
        top = draws[i][0]
        if top.y0 > lines[0][0] + 2:  # 쪽 첫 줄이 표 안이 아님
            continue
        bottom = top.y1
        for r in draws[i]:  # 이어진 선들 = 그 표 덩어리
            if r.y0 > bottom + 3:
                break
            bottom = max(bottom, r.y1)
        span = foot - _top()
        if bottom - top.y0 > span * 0.15 or max(r.y1 for r in draws[i - 1]) < _top() + (prev_foot - _top()) * 0.85:
            continue  # 꼬리가 길거나(쪽 15% 넘게) 앞 쪽이 표로 끝까지 안 찼으면 자연스러운 나뉨
        if any(r.y0 < bottom and r.y1 > top.y0 for r in pics[i]) or not any(y0 > bottom + 1 for y0, _, _ in lines):
            continue  # 사진 표, 또는 꼬리 아래 내용이 없음(그건 orphans)
        before = {_key(t) for _, _, t in prev_lines}
        block = [(y0, t) for y0, y1, t in lines if top.y0 - 1 <= y0 and y1 <= bottom + 1]
        new = [(y0, t) for y0, t in block if _key(t) not in before]
        if not new or len(new) == len(block):  # 머리줄이 되풀이되지 않음 — 나뉜 표 꼬리가 아님(간지 제목 상자 등)
            continue
        text = max((t for _, t in new), key=lambda t: len(_key(t)))
        if len(_key(text)) < 4:
            continue
        k = sum(1 for j in range(i) if any(_key(text) == _key(t) for _, _, t in pages[j][0]))
        out.append((i, text, bottom - new[0][0], k))
    return out


def _overflow_target(roots: dict, first: str, nth: int, rb):
    """넘친 줄(first, PDF에서 nth번째로 나온 글)이 든 표 — 여러 줄 표 또는 문단 많은 상자, 짧은 글·상자면 바로 앞(3문단 안) 큰 표(squeeze_overflow와 같은 찾기).
    글이 너무 짧으면(4글자 미만 — "1"·"○") 엉뚱한 표를 잡으니 안 찾음."""
    flat = lambda s: re.sub(r"\s", "", s or "")  # noqa: E731
    if len(_key(first)) < 4:
        return None

    def find(hit, nth: int):
        seen = 0
        for root in roots.values():
            tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
            for i, p in enumerate(tops):
                tbls = [t for t in p.iter(f"{{{rb.HP}}}tbl")]
                if not hit(rb._top_text(p)) and not any(hit(rb._cell_text(c)) for t in tbls for c in rb._cells(t).values()):
                    continue
                if seen < nth:
                    seen += 1
                    continue
                big = next((t for t in tbls if (int(t.get("rowCnt") or 1) > 1 or len(list(t.iter(f"{{{rb.HP}}}p"))) >= 5)
                            and any(hit(rb._cell_text(c)) for c in rb._cells(t).values())), None)
                if big is None:
                    for q in reversed(tops[max(0, i - 3):i]):
                        big = next((t for t in q.iter(f"{{{rb.HP}}}tbl") if int(t.get("rowCnt") or 1) > 1), None)
                        if big is not None:
                            break
                return big
        return None

    line = flat(first)
    once = len(line) >= 8 and sum(flat("".join(t.text or "" for t in p.iter(rb.T))).count(line)
                                      for root in roots.values() for p in root if p.tag == f"{{{rb.HP}}}p") == 1
    target = find(lambda t: line in flat(t), 0) if once else None
    return target if target is not None else find(lambda t: _key(first) in _key(t), nth)


def _has(p, rb, *tags) -> bool:
    return any(next(p.iter(f"{{{rb.HP}}}{t}"), None) is not None for t in tags)


def _blank(p, rb) -> bool:
    """빈 문단 — 글도 표·그림·구역 설정도 없음."""
    return not rb._top_text(p).strip() and not _has(p, rb, "tbl", "pic", "secPr", "ctrl", "container")


def _same_page(tbl, page_top: str, rb) -> tuple[list, list]:
    """넘친 표와 같은 쪽(앞 쪽 첫 줄 글 page_top이 든 문단부터 그 표까지)의 (빈 문단들, 다른 여러 줄 표들 — 사진 든 표 빼고).
    쪽 첫 줄을 40문단 안에서 못 찾으면 표 바로 앞 빈 문단(최대 2 — 10/26 형 "3.1 다음 표 띄워쓰기 하지말고 붙이고")만."""
    host = tbl
    while host.getparent() is not None and host.getparent().getparent() is not None:
        host = host.getparent()
    root = host.getparent()
    if root is None:
        return [], []
    tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
    if host not in tops:
        return [], []
    at = tops.index(host)
    key = _key(page_top)
    start = None
    for j in range(at - 1, max(-1, at - 41), -1):
        q = tops[j]
        texts = [rb._top_text(q)] + [rb._cell_text(c) for t in q.iter(f"{{{rb.HP}}}tbl") for c in rb._cells(t).values()]
        if len(key) >= 4 and any(key in _key(t) for t in texts if t):
            start = j
            break
    blanks, tables = [], []
    if start is None:
        for q in reversed(tops[:at]):
            if len(blanks) >= 2 or not _blank(q, rb):
                break
            blanks.append(q)
        return blanks, tables
    for q in tops[start:at]:
        if _blank(q, rb):
            blanks.append(q)
        for t in q.iter(f"{{{rb.HP}}}tbl"):
            if next(t.iter(f"{{{rb.HP}}}pic"), None) is None and int(t.get("rowCnt") or 1) > 1 and next(t.iterancestors(f"{{{rb.HP}}}tbl"), None) is None:
                tables.append(t)
    return blanks, tables


def _inner_blanks(tbl, rb) -> list:
    """한 줄 상자(요약문 결언 등) 안의 빈 문단 — 끝 빈 줄 먼저, 그다음 글 문단 사이 빈 줄(첫 문단은 남김 — 10/26 끝 빈 줄이 남아 상자 아래 테두리만 다음 쪽)."""
    if int(tbl.get("rowCnt") or 1) != 1:
        return []
    tail, mid = [], []
    for tc in rb._cells(tbl).values():
        ps = [p for p in tc.iter(f"{{{rb.HP}}}p") if next(p.iterancestors(f"{{{rb.HP}}}tc"), None) is tc]
        empty = [not "".join(t.text or "" for t in p.iter(rb.T)).strip() and not _has(p, rb, "tbl", "pic") for p in ps]
        j = len(ps)
        while j > 1 and empty[j - 1]:
            j -= 1
            tail.append(ps[j])
        mid += [p for p, e in zip(ps[1:j], empty[1:j]) if e]
    return tail + mid


def _vm(tc, tbl, rb) -> tuple[int, int]:
    m = tc.find(f"{{{rb.HP}}}cellMargin") if tc.get("hasMargin") == "1" else tbl.find(f"{{{rb.HP}}}inMargin")
    if m is None:
        return 141, 141
    return int(m.get("top") or 141), int(m.get("bottom") or 141)


def _fit_rows(tbl, rb, cut: int | None) -> tuple[dict, dict]:
    """줄마다 (지금 차지 높이, 줄일 수 있는 양) — 칸 위아래 여백을 cut으로 줄였을 때(None = 그대로). 글 어림은 _table_row_heights와 같은 셈, 2mm 여유는 남김."""
    import math

    cells = rb._cells(tbl)
    h, est_now, est_cut = {}, {}, {}
    for (r, _), tc in cells.items():
        if rb._span(tc, "rowSpan") != 1:
            continue
        sz = tc.find(f"{{{rb.HP}}}cellSz")
        w, hh = int(sz.get("width") or 0), int(sz.get("height") or 0)
        h[r] = max(h.get(r, 0), hh)
        mt, mb = _vm(tc, tbl, rb)
        m = tc.find(f"{{{rb.HP}}}cellMargin")
        mx = (int(m.get("left") or 141) + int(m.get("right") or 141)) if m is not None else 282
        if next(tc.iter(f"{{{rb.HP}}}pic"), None) is not None or next(tc.iter(f"{{{rb.HP}}}tbl"), None) is not None:
            a = b = hh
        else:
            lines = 0
            for p in tc.iter(f"{{{rb.HP}}}p"):
                t = "".join(x.text or "" for x in p.iter(rb.T))
                lines += max(1, math.ceil(len(t) * rb.CHAR_W / max(w - mx, 1000)))
            body = min(lines, 200) * rb.LINE_H
            a = body + mt + mb
            b = body + (min(mt, cut) if cut else mt) + (min(mb, cut) if cut else mb)
        est_now[r] = max(est_now.get(r, 0), a)
        est_cut[r] = max(est_cut.get(r, 0), b)
    cur = {r: max(h[r], est_now.get(r, 0)) for r in h}
    if int(tbl.get("rowCnt") or 1) == 1:  # 한 칸 상자(결언 등) — 글이 많아 어림이 실제보다 작게 나오니 칸 높이 빈 자리는 안 믿고 여백 줄인 만큼만(10/26 상자 끝이 넘어감)
        return cur, {r: max(0, est_now.get(r, 0) - est_cut.get(r, 0)) for r in h}
    return cur, {r: max(0, cur[r] - est_cut.get(r, 0) - 200) for r in h}


def _apply_fit(tbl, rb, need: int, cut: int | None) -> int:
    """칸 여백(cut)·줄 빈 높이를 need만큼 줄임 — 글은 그대로. 줄인 어림 양."""
    from server.sitok.precision_build import _set_row_height

    cur, spare = _fit_rows(tbl, rb, cut)
    total = sum(spare.values())
    if total <= 0 or need <= 0:
        return 0
    if cut:
        for tc in rb._cells(tbl).values():
            m = tc.find(f"{{{rb.HP}}}cellMargin")
            if m is not None:
                for k in ("top", "bottom"):
                    if int(m.get(k) or 0) > cut:
                        m.set(k, str(cut))
        im = tbl.find(f"{{{rb.HP}}}inMargin")
        if im is not None:
            for k in ("top", "bottom"):
                if int(im.get(k) or 0) > cut:
                    im.set(k, str(cut))

    def row_heights():
        hs = {}
        for (r, _), tc in rb._cells(tbl).items():
            if rb._span(tc, "rowSpan") == 1:
                hs[r] = max(hs.get(r, 0), int(tc.find(f"{{{rb.HP}}}cellSz").get("height") or 0))
        return hs

    k = min(1.0, need / total)
    done = 0
    heights = row_heights()
    for r, s in spare.items():
        cutr = int(s * k)
        if cutr <= 0:
            continue
        done += cutr
        if heights.get(r, 0) > cur[r] - cutr:  # 칸 높이(최소 높이)가 붙들고 있던 줄만 값 낮춤 — 글이 정한 줄은 여백만 줄면 저절로
            _set_row_height(tbl, r, cur[r] - cutr)
    heights = row_heights()
    for (r, _), tc in rb._cells(tbl).items():  # 합친 칸(여러 줄) 높이 = 그 줄들 합
        span = rb._span(tc, "rowSpan")
        if span > 1 and all(rr in heights for rr in range(r, r + span)):
            tc.find(f"{{{rb.HP}}}cellSz").set("height", str(sum(heights[rr] for rr in range(r, r + span))))
    return done


SMALL_TABLE = 30000  # 이보다 낮은(어림 약 10cm, 본문 높이의 40% 남짓) 표는 꼬리만 넘기지 않고 통째로
CAPTION_LINE = re.compile(r"^\s*[<〈《【\[(].{1,40}[>〉》】\])]\s*$")


def _keep_together(tbl, rb):
    """작은 표를 통째로 다음 쪽에 보낼 때 쪽 나눔을 걸 문단 — 표 바로 앞 문단이 캡션(<…>·【…】)이면 그 문단, 그 앞이 절 제목이면 제목(제목만 남지 않게), 아니면 표 문단.
    이미 쪽 나눔이 있거나 구역 첫 문단이면 None."""
    host = tbl
    while host.getparent() is not None and host.getparent().getparent() is not None:
        host = host.getparent()
    root = host.getparent()
    if root is None:
        return None
    tops = [p for p in root if p.tag == f"{{{rb.HP}}}p"]
    if host not in tops:
        return None
    at = tops.index(host)
    j = at
    if at > 0 and CAPTION_LINE.match(rb._top_text(tops[at - 1]) or ""):
        j = at - 1
        if j > 0 and HEAD.match(rb._top_text(tops[j - 1]) or ""):
            j -= 1
    if j == 0 or tops[j].get("pageBreak") == "1" or _has(tops[j], rb, "secPr"):
        return None
    return tops[j]


def _levels(tables: list, rb) -> list:
    return sorted({m for t in tables for tc in rb._cells(t).values() for m in _vm(tc, t, rb) if m > MIN_MARGIN} | {MIN_MARGIN}, reverse=True)


def tidy_overflow(hwpx: Path, pdf: Path, sections_from: int = 1, after: str | None = None) -> list[str]:
    """애매한 넘침 정리(10/26 사용자·민재형 "애매하게 페이지를 초과" — 제미나이 권고 중 글자 크기·장평은 빼고) — 몇 줄만 넘친 쪽(orphans)·나뉜 표 꼬리(tails)마다:
    ① 당기기: 넘친 양만큼 그 쪽의 빈 줄 → 표 칸 빈 높이·칸 안쪽 위아래 여백(1mm까지, 상자면 안의 빈 줄도)을 줄여 앞 쪽에 — 글자 크기·장평·줄 간격은 그대로.
    ② 넘기기: 그걸로 모자라면 여러 줄 표는 "줄 단위로 나눔"(pageBreak TABLE — 한글 시험: CELL은 칸 안 글도 끊어 "유지되고 있다." 한 줄만 넘어감)으로 —
       마지막 줄이 통째로 머리줄과 함께 다음 쪽(뒤 ※ 상자도 같이). 상자(한 줄 표)는 못 나누니 그대로.
    고친 곳 설명(비면 안 바꿈 — 부르는 쪽이 PDF를 다시 뽑고, 문제가 늘었으면 되돌림).
    after = 이 글(띄어쓰기 뺀 앞부분)로 시작하는 문단 뒤의 표만 고침(10/27 내진 — 구역이 하나라 표지~결과표도 같은 구역, 앞 결과표 줄 높이는 손대지 않게)."""
    from server.sitok import report_build as rb

    found = [("넘침", *x) for x in orphans(pdf, hwpx)] + [("꼬리", *x) for x in tails(pdf, hwpx)]
    if not found:
        return []
    bodies, rects, heights, _ = _pages(pdf)
    firsts = [(b[0] or [(0, 0, "")])[0][2] for b in bodies]  # 쪽마다 첫 줄 글
    table_top = [bool(b[0]) and any(_top() < r.y0 <= b[0][0][0] + 2 and r.height < h * 0.9 for r in rr)
                 for b, rr, h in zip(bodies, rects, heights)]  # 쪽이 표(나뉜 표 꼬리·※ 상자)로 시작
    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        sections = rb._sections(z)
    roots = {n: etree.fromstring(data[n]) for n in sections[sections_from:]}
    done, seen = [], []
    for kind, page, first, h, nth in found:
        target = _overflow_target(roots, first, nth, rb)
        if target is None or any(target is t for t in seen) or next(target.iter(f"{{{rb.HP}}}pic"), None) is not None:
            continue
        on_prev = {_key(t) for _, _, t in bodies[page - 1][0]} if page else set()
        cells = [_key(rb._cell_text(c)) for c in rb._cells(target).values()]
        if not any(len(c) >= 4 and any(c[:12] in t or t in c for t in on_prev if len(t) >= 4) for c in cells):
            continue  # 찾은 표가 넘친 쪽 바로 앞 쪽에 없음 — 같은 글이 딴 데도 있어 엉뚱한 표(10/26 옹벽 목차 "6. 기타부록참고자료" → 부록 간지 표)
        if after:
            top = target
            while top.getparent() is not None and top.getparent().getparent() is not None:
                top = top.getparent()
            sec = top.getparent()
            tops_all = [q for q in sec if q.tag == f"{{{rb.HP}}}p"] if sec is not None else []
            start = next((k for k, q in enumerate(tops_all) if re.sub(r"\s", "", "".join(x.text or "" for x in q.iter(rb.T))).startswith(after)), None)  # 간지 글은 표 안
            if start is None or top not in tops_all or tops_all.index(top) <= start:
                continue
        seen.append(target)
        need = int(h * 100 * 1.2) + 800
        blanks, others = _same_page(target, firsts[page - 1] if page else "", rb)
        host = target
        while host.getparent() is not None and host.getparent().getparent() is not None:
            host = host.getparent()
        tops = [q for q in host.getparent() if q.tag == f"{{{rb.HP}}}p"] if host.getparent() is not None else []
        near = []  # 표 바로 앞 빈 줄(제목과 표 사이)
        for q in reversed(tops[:tops.index(host)] if host in tops else []):
            if not _blank(q, rb) or len(near) >= 2:
                break
            near.append(q)
        far = [q for q in reversed(blanks) if all(q is not x for x in near)]  # 같은 쪽 다른 빈 줄(절 사이) — 모자랄 때만, 표에 가까운 것부터
        inner = _inner_blanks(target, rb)
        tables = [target] + [t for t in others if t is not target]
        plan, use_far = False, False
        for with_far in (False, True):  # 절 사이 빈 줄은 마지막 수단
            free = (len(near) + len(inner) + (len(far) if with_far else 0)) * rb.LINE_H
            for cut in [None] + _levels(tables, rb):  # 여백은 덜 줄이는 것부터
                if free + sum(sum(_fit_rows(t, rb, cut)[1].values()) for t in tables) >= need:
                    plan, use_far = cut, with_far
                    break
            if plan is not False:
                break
        if plan is not False:
            left, n_blank = need, 0

            def drop(qs):
                nonlocal left, n_blank
                for q in qs:
                    if left <= 0:
                        return
                    if q.getparent() is not None:
                        q.getparent().remove(q)
                        left -= rb.LINE_H
                        n_blank += 1
            drop(near)
            if left > 0:
                left -= _apply_fit(target, rb, left, plan)
            drop(inner)
            if use_far:
                drop(far)
            for t in tables[1:]:
                if left <= 0:
                    break
                left -= _apply_fit(t, rb, left, plan)
            how = [f"빈 줄 {n_blank}개" if n_blank else "", f"칸 위아래 여백 {plan / 283:.1f}mm까지" if plan else "", "칸 빈 높이" if n_blank * rb.LINE_H < need else ""]
            done.append(f"{kind} '{first[:14]}…' → {'·'.join(x for x in how if x)} 줄여 앞 쪽에(글자 그대로)")
            continue
        if not table_top[page] or int(target.get("rowCnt") or 1) < 3:
            continue  # 글만 넘친 쪽·상자 — 표 나눔을 바꿔도 소용없음, 그대로
        heights = rb._table_row_heights(target, text_only=True)
        if sum(heights.values()) <= SMALL_TABLE:  # 작은 표(공사비 산정 등) — 제목(캡션)과 함께 통째로 다음 쪽 위에(10/26 형 "총 공사비만 덩그러니")
            at = _keep_together(target, rb)
            if at is not None:
                at.set("pageBreak", "1")
                done.append(f"{kind} '{first[:14]}…' → 작은 표라 제목과 함께 통째로 다음 쪽에")
                continue
        if target.get("pageBreak") == "CELL" and heights.get(max(heights, default=0), 0) <= 8000:
            target.set("pageBreak", "TABLE")  # 마지막 줄이 크면(약 3cm 넘게) 통째로 넘길 때 앞 쪽이 크게 비니 그대로
            done.append(f"{kind} '{first[:14]}…' → 줄 단위로 넘김(칸 안 글이 쪽에서 끊기지 않게)")
    if not done:
        return []
    for n, root in roots.items():
        data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    _rewrite(hwpx, infos, data)
    return done


def tidy_checked(hwpx: Path, pdf: Path, render, sections_from: int = 1, after: str | None = None) -> list[str]:
    """애매한 넘침 정리 + 안전장치(시특법·옹벽·내진·산안법 공용, 10/26) — tidy_overflow로 고치고 render(hwpx, 새 PDF)로 다시 그려
    쪽 문제(몇 줄만 넘친 쪽·제목만 쪽 끝)가 늘거나 쪽 수가 늘면 hwpx를 고치기 전으로 되돌림(PDF도 그대로). 고쳤으면 pdf를 새 것으로 바꾸고 설명, 아니면 []."""
    import pymupdf

    snap = hwpx.read_bytes()
    done = tidy_overflow(hwpx, pdf, sections_from=sections_from, after=after)  # 걸리는 곳이 없으면 여기서 끝(산안법 대부분 — 검사 약 0.5초)
    if not done:
        return []
    orig = hwpx.with_name(hwpx.stem + "_정리전.hwpx")  # 고치기 전 문제 수는 고치기 전 파일로(쪽 나눔을 더했으면 "일부러 새 쪽"이 달라짐)
    orig.write_bytes(snap)
    try:
        before = issue_count(pdf, orig)
    finally:
        orig.unlink(missing_ok=True)
    pages = len(_pages(pdf)[0])
    tmp = pdf.with_name(pdf.stem + "_정리.pdf")
    try:
        tmp.unlink(missing_ok=True)
        render(hwpx, tmp)
        after = issue_count(tmp, hwpx)
        with pymupdf.open(tmp) as d:
            pages2 = len(d)
    except Exception:  # noqa: BLE001 — 다시 못 그리면 고치기 전 그대로
        hwpx.write_bytes(snap)
        tmp.unlink(missing_ok=True)
        raise
    if after > before or pages2 > pages or pages2 == 0:  # 다른 데가 더 이상해짐 — 고치기 전 그대로
        hwpx.write_bytes(snap)
        tmp.unlink(missing_ok=True)
        print(f"[쪽 정리 되돌림] {hwpx.name}: 문제 {before}→{after}, 쪽 {pages}→{pages2}", flush=True)
        return []
    tmp.replace(pdf)
    print(f"[쪽 정리] {hwpx.name}: 문제 {before}→{after}, 쪽 {pages}→{pages2} — {' / '.join(done)}", flush=True)
    return done


def issue_count(pdf: Path, hwpx: Path) -> int:
    """쪽 문제 수 — 몇 줄만 넘친 쪽 + 제목만 쪽 끝(tidy_overflow 뒤 되돌릴지 정할 때 — 늘었으면 되돌림). 꼬리(tails)는 안 셈:
    줄 단위로 넘긴 뒤의 "머리줄 + 줄 통째로"도 짧은 꼬리로 보이니까."""
    try:
        heads = sum(1 for s in scan(pdf, hwpx, limit=200) if "만 쪽 끝에 있음" in s)
        return len(orphans(pdf, hwpx)) + heads
    except Exception:  # noqa: BLE001
        return 0
