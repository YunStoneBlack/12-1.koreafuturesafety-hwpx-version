"""공식 결과표 양식·작성방법(2026-10-21 형 "첨부1# 안전점검등 결과보고서 결과표 양식" — 현재 만든 모든 템플릿 동일하게)과 부록 손질.

- result_official(root): 결과표 "나. 점검 실시결과 현황"의 "중대결함 / 공중이 이용하는 부위" 두 줄을 공식 양식처럼
  왼쪽 "중대한 결함등"(두 줄 합침) + "중대한 결함" / "공중이 이용하는 부위에 결함" 이름칸으로(정기 건축물 원본·전회차 보고서 — 정밀·옹벽 원본은 이미 이 모양).
  격자 열은 그대로 두고 값 칸 왼쪽 몇 열을 이름칸으로 떼어 냄(다른 줄 주소가 안 바뀜).
- none_text(s): 작성방법 — 중대한 결함·공중이용부위 결함·주요 보수보강이 없으면 "없음"만(전엔 "없음 — 일상적인 유지관리 실시" 같은 문장).
- result_title(root, half): "○○ 정기안전점검 결과표" → "○○ 정기안전점검(하반기) 결과표"(양식 제목).
- schedule_days(root, days): 과업수행계획서 "과업 추진 일정(일)" 머리 숫자 = 1 … 점검기간 날수(중간은 고르게, 형 10/21).
- org_names(root, names): 과업수행조직 그림표 책임기술자·참여기술자 이름 = 결과표 기술자(참여가 모자라면 마지막 사람을 되풀이).
- precheck_other(root): 사전검토보고서 3.1 범위표 "기타시설 ∘외벽마감재" → "∘ 마감재" / "∘ 부착물 등" 두 줄(○는 정기안전점검 칸만, 10/21 형).
"""
from __future__ import annotations

import copy
import re

from server.sitok import report_build as rb

HP = rb.HP


def _n(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def _addr(tc):
    return tc.find(f"{{{HP}}}cellAddr")


def _spanel(tc):
    return tc.find(f"{{{HP}}}cellSpan")


def _sz(tc):
    return tc.find(f"{{{HP}}}cellSz")


def _is_result(cells: dict) -> bool:
    return {"용역명", "점검기간", "관리주체명"} <= {_n(rb._cell_text(v)) for v in cells.values()}


def _grid(tbl, cells: dict) -> list:
    """열 너비(HWPUNIT) — 칸마다 (시작 열, 합친 열 수, 너비)로 하나씩 풀어 냄. 못 푼 열은 None."""
    n = int(tbl.get("colCnt") or 0)
    w: list = [None] * n
    spans = [(c, int(_spanel(tc).get("colSpan")), int(_sz(tc).get("width"))) for (_, c), tc in cells.items()]
    changed = True
    while changed:
        changed = False
        for c, s, wd in spans:
            unknown = [i for i in range(c, min(c + s, n)) if w[i] is None]
            if len(unknown) == 1:
                w[unknown[0]] = wd - sum(w[i] for i in range(c, min(c + s, n)) if w[i] is not None)
                changed = True
    return w


INNER_LABELS = ("점검기간", "대표자", "계약방법", "종류", "종별", "점검금액(천원)", "안전등급", "시설물규모")  # 결과표 가. 일반현황 안쪽 이름칸


def result_official(root) -> int:
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if not _is_result(cells):
            continue
        texts = {_n(rb._cell_text(v)) for v in cells.values()}
        if any(t.startswith("중대한결함등") for t in texts):
            continue  # 이미 양식대로
        r = next((r for (r, c), tc in sorted(cells.items()) if c == 0 and _n(rb._cell_text(tc)) in ("중대결함", "중대한결함")), None)
        if r is None or (r + 1, 0) not in cells or not _n(rb._cell_text(cells[(r + 1, 0)])).startswith("공중이"):
            continue
        l8, l9 = cells[(r, 0)], cells[(r + 1, 0)]
        if _spanel(l8).get("colSpan") != "1" or _spanel(l9).get("colSpan") != "1":
            continue
        v8, v9 = rb._row_right(cells, r, 1), rb._row_right(cells, r + 1, 1)
        if v8 is None or v9 is None or _addr(v8).get("colAddr") != _addr(v9).get("colAddr"):
            continue
        c0, span = int(_addr(v8).get("colAddr")), int(_spanel(v8).get("colSpan"))
        w = _grid(tbl, cells)
        k, sub = 0, 0
        while k < span - 1 and sub < 3500:  # 이름칸 너비 = 값 칸 왼쪽 열을 3500(약 12mm) 넘게
            if w[c0 + k] is None:
                break
            sub += w[c0 + k]
            k += 1
        if not k or sub < 2000:
            continue
        inner = next((tc.get("borderFillIDRef") for (rr, c), tc in sorted(cells.items())  # 안쪽 이름칸 테두리(네 변 가는 선·회색 바탕) — 맨 왼쪽 칸을 복사하면
                      if c > 0 and _n(rb._cell_text(tc)) in INNER_LABELS and tc.get("borderFillIDRef")), None)  # 표 왼쪽 바깥선(0.5mm)까지 와 안쪽에 굵은 세로선(10/26 형 "결과표 선두께")
        for lab, v, rr, txt in ((l8, v8, r, "중대한 결함"), (l9, v9, r + 1, "공중이 이용하는 부위에 결함")):
            s = copy.deepcopy(lab)
            if inner:
                s.set("borderFillIDRef", inner)
            _addr(s).set("colAddr", str(c0))
            _addr(s).set("rowAddr", str(rr))
            _spanel(s).set("colSpan", str(k))
            _spanel(s).set("rowSpan", "1")
            _sz(s).set("width", str(sub))
            rb._set_lines(s, [txt])
            _addr(v).set("colAddr", str(c0 + k))
            _spanel(v).set("colSpan", str(span - k))
            _sz(v).set("width", str(int(_sz(v).get("width")) - sub))
            v.addprevious(s)
        h8, h9 = int(_sz(l8).get("height") or 0), int(_sz(l9).get("height") or 0)
        _spanel(l8).set("rowSpan", "2")
        _sz(l8).set("height", str(h8 + h9))
        rb._set_lines(l8, ["중대한 결함등"])
        l9.getparent().remove(l9)
        n += 1
    return n


NONE_RE = re.compile(r"^(해당\s*사항\s*없음|해당\s*없음|중대\s*결함\s*없음|이상\s*없음|없음)(\s*[—–\-,.:/].*)?$")
DEFECT_WORDS = ("균열", "파손", "부식", "탈락", "변형", "손상", "누수", "박리", "박락", "노출", "들뜸", "처짐", "침하", "결함", "훼손", "백태", "이격", "유실", "세굴")


def none_text(s: str) -> str:
    """결과표 결함 칸 — 없으면 "없음"만(작성방법: '해당 없음', '없음', '-' 중). 결함 낱말 없이 "양호"만 적힌 글도 없음."""
    t = (s or "").strip()
    core = re.sub(r"^[\s⦁ㆍ·•∘◦○\-–—]+", "", t).strip()
    if not core or core == "-" or NONE_RE.match(core):
        return "없음"
    if "양호" in core and not any(w in core for w in DEFECT_WORDS):
        return "없음"
    return t


def result_none(root) -> int:
    """결과표 중대한 결함·공중이용부위 결함 값 칸을 none_text로(AI 초안이 없을 때 전회차·원본 글에도)."""
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if not _is_result(cells):
            continue
        for names, starts in ((("중대결함", "중대한결함"), False), (("공중이",), True)):
            k = rb._label(cells, *names, starts=starts)
            v = rb._row_right(cells, k[0], k[1] + rb._span(cells[k], "colSpan")) if k else None
            if v is None:
                continue
            old = rb._cell_text(v).strip()
            new = none_text(old)
            if new != old and new == "없음":
                rb._set_lines(v, ["없음"])
                n += 1
    return n


def result_title(root, half: str) -> int:
    """결과표 제목 문단(표 바깥, "… 정기안전점검 결과표") — 양식처럼 반기를 괄호로."""
    if not half:
        return 0
    n = 0
    for p in root.iter(f"{{{HP}}}p"):
        if next(p.iterancestors(f"{{{HP}}}tc"), None) is not None:
            continue
        own = [x for x in p.iter(rb.T) if next(x.iterancestors(f"{{{HP}}}p"), None) is p]
        text = "".join(x.text or "" for x in own)
        m = re.match(r"^(.*\S)\s*정기안전점검\s*(\([^)]*\))?\s*결과표\s*$", text)
        if not m or text.lstrip().startswith(("▣", "■")) or re.match(r"\s*\d+\.\d", text):
            continue
        new = f"{m[1]} 정기안전점검({half}) 결과표"
        if new == text:
            continue
        rb._clear(own[0], new)
        for x in own[1:]:
            rb._clear(x, "")
        n += 1
    return n


def schedule_days(root, days: int) -> int:
    if not days or days < 1:
        return 0
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        head = next(((r, c) for (r, c), tc in cells.items() if "과업추진일정" in _n(rb._cell_text(tc))), None)
        if head is None:
            continue
        nums = sorted((c, tc) for (rr, c), tc in cells.items() if rr == head[0] + 1 and re.fullmatch(r"\d+", _n(rb._cell_text(tc))))
        if len(nums) < 2:
            continue
        m = len(nums)
        vals = [round(1 + (days - 1) * i / (m - 1)) for i in range(m)]
        if days >= m:  # 같은 숫자가 겹치지 않게
            for i in range(1, m):
                vals[i] = max(vals[i], vals[i - 1] + 1)
            for i in range(m - 2, -1, -1):
                vals[i] = min(vals[i], vals[i + 1] - 1)
        for (c, tc), v in zip(nums, vals):
            rb._set_lines(tc, [str(v)])
        n += 1
    return n


def org_names(root, names: list[str]) -> int:
    if not names:
        return 0
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        chief = next(((r, c) for (r, c), tc in cells.items() if _n(rb._cell_text(tc)).endswith("책임기술자")), None)
        parts = sorted((c, r) for (r, c), tc in cells.items() if _n(rb._cell_text(tc)) == "참여기술자")
        if chief is None or not parts:
            continue
        below = (chief[0] + 1, chief[1])
        if below in cells:
            rb._set_lines(cells[below], [names[0]])
        others = names[1:] or names[:1]
        for i, (c, r) in enumerate(parts):
            rows = [rr for (rr, cc) in cells if cc == c and rr > r]
            if rows:
                rb._set_lines(cells[(max(rows), c)], [others[min(i, len(others) - 1)]])
        n += 1
    return n


def precheck_other(root) -> int:
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if not any(_n(rb._cell_text(tc)).startswith("부재명/시설물명") for tc in cells.values()):
            continue
        r = next((r for (r, c), tc in cells.items() if c == 0 and _n(rb._cell_text(tc)) == "기타시설"), None)
        if r is None or (r, 1) not in cells:
            continue
        ncol = int(tbl.get("colCnt") or 0)
        regular = next((c for (rr, c), tc in cells.items() if _n(rb._cell_text(tc)) == "정기안전점검"), 2)  # 실시범위 중 정기안전점검 열(형 10/21 "정기점검만 체크")
        if any("부착물" in rb._cell_text(tc) for tc in cells.values()):  # 이미 두 줄(전회차 보고서가 원본) — ○가 정기 말고 다른 칸에도 있으면 정기만
            for (rr, c), tc in list(cells.items()):
                if c == 1 and ("마감재" in rb._cell_text(tc) or "부착물" in rb._cell_text(tc)):
                    for c2 in range(2, max(ncol - 1, 2)):
                        if c2 != regular and (rr, c2) in cells and _n(rb._cell_text(cells[(rr, c2)])) == "○":
                            rb._set_lines(cells[(rr, c2)], [""])
                            n += 1
            continue
        rb._dup_rows(tbl, r, 1, 1)
        cells = rb._cells(tbl)
        for rr, name in ((r, "∘ 마감재"), (r + 1, "∘ 부착물 등")):
            if (rr, 1) in cells:
                rb._set_lines(cells[(rr, 1)], [name])
            for c in range(2, max(ncol - 1, 2)):  # 실시범위 열(정기·정밀점검·정밀진단) — 비고 열 앞까지, ○는 정기안전점검만
                if (rr, c) in cells:
                    rb._set_lines(cells[(rr, c)], ["○" if c == regular else ""])
        for c in range(1, ncol):  # 윗줄은 가운데 줄 테두리(아랫선 얇게) — 위 줄 것을 씀
            if (r, c) in cells and (r - 1, c) in cells:
                cells[(r, c)].set("borderFillIDRef", cells[(r - 1, c)].get("borderFillIDRef"))
        for c in (0, ncol - 1):  # 구분·비고 칸은 두 줄 합침
            a, b = cells.get((r, c)), cells.get((r + 1, c))
            if a is None or b is None or _spanel(a).get("rowSpan") != "1":
                continue
            _spanel(a).set("rowSpan", "2")
            _sz(a).set("height", str(int(_sz(a).get("height") or 0) + int(_sz(b).get("height") or 0)))
            if b.get("borderFillIDRef"):  # 합친 칸 밑 = 아래 칸 밑(표 끝줄 굵은 선 — 10/26 사용자 "굵은선은 왜 빠져있지", 위 칸은 가운데 줄용 가는 선이었음)
                a.set("borderFillIDRef", b.get("borderFillIDRef"))
            b.getparent().remove(b)
        n += 1
    return n
