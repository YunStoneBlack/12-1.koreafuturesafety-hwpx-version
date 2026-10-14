"""진행공정 표(표12 현재공정)가 쪽을 넘을 때 — 쪽이 바뀐 자리에 선 살리기 + 다음 쪽에도 공정명 (2026-10-15 사용자).

표12는 한 공정 안 유해요인마다 줄을 따로 두고, 같은 공정 안 줄 사이 경계선은 지워 둔다
(report_builder_hwpx_fields_process._borderfill_hide_edges — "한 공정으로 보이게"). 한글이 그 지운 경계에서
쪽을 나누면 오른쪽 세 칸은 쪽 끝·다음 쪽 첫머리가 열린 채 찍히고, 공정명 칸(세로로 합친 칸)만 쪽마다 닫혀 그려져
"선이 끊겨 보임". 어디서 쪽이 나뉠지는 그려 봐야 알므로, 첫 PDF를 보고 나뉜 자리만 고친다:
- 앞 줄 아래선·뒷 줄 위선 = 공정 첫 줄 위선과 같은 선(가는 실선)
- 공정명 합친 칸을 그 자리에서 둘로 나눠 다음 쪽 칸에도 같은 공정명("(계속)"은 안 붙임 — 사용자 10/15)

안전장치(사용자 "잘 되고 있는 보고서 생성에 영향 주면 안 됨"): 여기서는 새 hwpx만 만들고(원본·첫 PDF는 그대로),
못 찾거나 애매하면(유해요인 글이 PDF에 안 보임, 한 줄이 쪽 중간에서 잘림 등) 그 공정은 안 건드린다.
호출부(report_builder_hwpx.build_report_pdf_via_hwpx)는 고친 게 있을 때만 켜 둔 한글로 다시 저장하고,
쪽 수가 같을 때만 새 PDF를 쓴다 — 어떤 오류든 첫 PDF 그대로.
"""
from __future__ import annotations

import copy
import re
import zipfile
from pathlib import Path

from lxml import etree

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _norm(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(f"{HP}t"))


def _cells(tbl) -> dict:
    out = {}
    for tc in tbl.iter(f"{HP}tc"):
        if next(tc.iterancestors(f"{HP}tbl"), None) is not tbl:
            continue
        a = tc.find(f"{HP}cellAddr")
        out[(int(a.get("rowAddr")), int(a.get("colAddr")))] = tc
    return out


def _span(tc) -> int:
    s = tc.find(f"{HP}cellSpan")
    return int(s.get("rowSpan") or 1) if s is not None else 1


def process_tables(root) -> list:
    """진행공정 표 — 4칸, 머리줄 첫 칸에 "공정", 마지막 칸 "위험성"."""
    out = []
    for tbl in root.iter(f"{HP}tbl"):
        if tbl.get("colCnt") != "4" or next(tbl.iterancestors(f"{HP}tbl"), None) is not None:
            continue
        c = _cells(tbl)
        if "공정" in _norm(_text(c.get((0, 0), tbl))) and _norm(_text(c.get((0, 3), tbl))).startswith("위험성"):
            out.append(tbl)
    return out


def _groups(tbl) -> list[tuple[int, int]]:
    """공정 묶음 [(첫 줄, 끝 줄)] — 공정명 칸이 여러 줄에 걸친 것만(한 줄짜리 공정은 쪽 사이에서 안 나뉨)."""
    c = _cells(tbl)
    return sorted((r, r + _span(tc) - 1) for (r, col), tc in c.items() if col == 0 and r >= 1 and _span(tc) > 1)


def _snip(s: str, head: bool = True, n: int = 12) -> str:
    s = _norm(s).lstrip("•·ㆍ-")
    return s[:n] if head else s[-n:]


def find_cuts(roots: list, pdf: Path) -> list[tuple[int, int, int, int, int]]:
    """첫 PDF에서 공정 안 줄 사이로 쪽이 바뀐 자리 [(구역, 표 순번, 공정 첫 줄, 끝 줄, 앞 줄)] — 문서 순서대로 PDF 쪽을 따라감."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        pages = [_norm(pg.get_text()) for pg in doc]

    def find(snip: str, start: int, upto: int = 4):
        if len(snip) < 5:
            return None
        return next((p for p in range(start, min(start + upto, len(pages))) if snip in pages[p]), None)

    cuts = []
    cur = 0
    for si, root in enumerate(roots):
        for ti, tbl in enumerate(process_tables(root)):
            c = _cells(tbl)
            head = _snip(_text(c.get((0, 2), tbl)))
            p0 = find(head, cur, len(pages))
            if p0 is None:
                continue
            cur = p0
            for a, b in _groups(tbl):
                starts, ends = {}, {}
                ok = True
                for r in range(a, b + 1):
                    if (r, 1) not in c or (r, 2) not in c:
                        ok = False
                        break
                    ps = find(_snip(_text(c[(r, 1)])), cur)
                    if ps is None:
                        ok = False
                        break
                    pe = find(_snip(_text(c[(r, 2)]), head=False), ps)  # 그 줄 예방대책 끝 — 줄이 쪽 중간에서 잘렸는지
                    starts[r], ends[r] = ps, (pe if pe is not None else ps)
                    cur = ps
                if not ok:
                    break  # 이 표는 더 못 따라감(글이 PDF에서 안 보임) — 안 건드림
                if any(ends[r] != starts[r] for r in starts):
                    continue  # 한 줄이 쪽 중간에서 잘린 공정 — 이 방법으로는 안 맞음, 그대로 둠
                for r in range(a, b):
                    if starts[r + 1] > starts[r]:
                        cuts.append((si, ti, a, b, r))
                        break  # 한 공정에 한 군데(공정이 두 쪽을 넘는 일은 드묾 — 첫 자리만)
    return cuts


class _BorderFills:
    """header.xml borderFill 복사(위/아래 선만 바꾼 것) — 같은 조합은 한 번만."""

    def __init__(self, hdr_root):
        self.list = next(hdr_root.iter(f"{HH}borderFills"))
        self.by_id = {bf.get("id"): bf for bf in self.list.findall(f"{HH}borderFill")}
        self.cache: dict = {}

    def with_edge(self, base_id: str, edge: str, line) -> str:
        key = (base_id, edge)
        if key in self.cache:
            return self.cache[key]
        src = self.by_id.get(str(base_id))
        if src is None:
            return base_id
        clone = copy.deepcopy(src)
        new_id = str(max(int(x) for x in self.by_id if x.isdigit()) + 1)
        clone.set("id", new_id)
        old = clone.find(f"{HH}{edge}")
        new = copy.deepcopy(line)
        new.tag = f"{HH}{edge}"
        if old is not None:
            old.addprevious(new)
            clone.remove(old)
        else:
            clone.append(new)
        self.list.append(clone)
        self.list.set("itemCnt", str(len(self.list.findall(f"{HH}borderFill"))))
        self.by_id[new_id] = clone
        self.cache[key] = new_id
        return new_id


def _cut(tbl, bfs: _BorderFills, a: int, b: int, c: int) -> bool:
    cells = _cells(tbl)
    first = bfs.by_id.get(cells[(a, 1)].get("borderFillIDRef"))
    line = first.find(f"{HH}topBorder") if first is not None else None
    if line is None or line.get("type") == "NONE":
        return False
    for col in (1, 2, 3):  # ① 쪽이 바뀐 자리 선
        if (c, col) in cells:
            tc = cells[(c, col)]
            tc.set("borderFillIDRef", bfs.with_edge(tc.get("borderFillIDRef"), "bottomBorder", line))
        if (c + 1, col) in cells:
            tc = cells[(c + 1, col)]
            tc.set("borderFillIDRef", bfs.with_edge(tc.get("borderFillIDRef"), "topBorder", line))
    head = cells[(a, 0)]  # ② 공정명 칸 둘로(다음 쪽 칸에도 공정명)
    hts = {r: int(cells[(r, 1)].find(f"{HP}cellSz").get("height") or 0) for r in range(a, b + 1)}
    tail = copy.deepcopy(head)
    head.find(f"{HP}cellSpan").set("rowSpan", str(c - a + 1))
    head.find(f"{HP}cellSz").set("height", str(sum(hts[r] for r in range(a, c + 1))))
    tail.find(f"{HP}cellAddr").set("rowAddr", str(c + 1))
    tail.find(f"{HP}cellSpan").set("rowSpan", str(b - c))
    tail.find(f"{HP}cellSz").set("height", str(sum(hts[r] for r in range(c + 1, b + 1))))
    for el in list(tail.iter(f"{HP}linesegarray")):  # 다음 쪽 칸 = 같은 공정명(사용자 10/15 "(계속) 없이 공정명만")
        el.getparent().remove(el)
    row = next(tr for tr in tbl.findall(f"{HP}tr") if any(tc is cells.get((c + 1, 1)) for tc in tr.findall(f"{HP}tc")))
    row.insert(0, tail)
    return True


def fix_process_splits(hwpx_in: Path, pdf: Path, hwpx_out: Path) -> int:
    """첫 PDF를 보고 공정 안에서 쪽이 바뀐 자리를 고친 hwpx를 hwpx_out에 — 고친 곳 수(0이면 파일 안 만듦)."""
    with zipfile.ZipFile(hwpx_in) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    secs = sorted((n for n in data if re.fullmatch(r"Contents/section\d+\.xml", n)), key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1])[0]))
    roots = [etree.fromstring(data[n]) for n in secs]
    cuts = find_cuts(roots, pdf)
    if not cuts:
        return 0
    hdr = etree.fromstring(data["Contents/header.xml"])
    bfs = _BorderFills(hdr)
    done = 0
    for si, ti, a, b, c in sorted(cuts, key=lambda x: (x[0], x[1], -x[2])):  # 같은 표는 아래 공정부터(줄 주소 그대로)
        if _cut(process_tables(roots[si])[ti], bfs, a, b, c):
            done += 1
    if not done:
        return 0
    for n, root in zip(secs, roots):
        data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    data["Contents/header.xml"] = etree.tostring(hdr, xml_declaration=True, encoding="UTF-8", standalone=True)
    hwpx_out = Path(hwpx_out)
    with zipfile.ZipFile(hwpx_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in infos:
            zout.writestr(i, data[i.filename], compress_type=zipfile.ZIP_STORED if i.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    return done
