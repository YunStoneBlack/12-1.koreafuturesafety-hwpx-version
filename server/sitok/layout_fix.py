"""시특법 정기 보고서 모양 손질(2026-10-19 민재형 요구사항 문서 "양주덕산초등학교 등 3개소에 대한") — 회사 원본(광숭초) 틀에 맞춰 둔 길이·높이가
다른 시설물 이름·글에서 어긋나는 곳. report_build.build(동마다)·merge(묶음)가 부름.

- submit_dashes: 제출문 "------ ○○ 귀하" 점선 길이 — 원본 36개(광숭초등학교)에 고정이라 이름이 길면 "귀하"가 다음 줄로 → 이름 길이에 맞춰 첫 줄 끝에 "귀하"
- result_rows: 결과표 용역명·관리주체명·공동수급·주요 보수ㆍ보강 줄 높이 — 원본 관리주체명·공동수급 1000(글이 선에 겹침), 용역명·보수보강은 글 줄 수만큼
- strip_na_titles: 1.3 "4)강재구조 노후상태 조사결과(해당없음)" — 원본 틀 제목에 박힌 "(해당없음)" 떼기
- fit_title: 묶음 "3.○○의 위치도 및 전경사진"이 길어 두 줄이면 제목만 한 쪽에 남고 지도·사진이 다음 쪽 → 그 제목만 글자를 줄여 한 줄로(merge)
- toc_appendix: 목차 "▣ 부록" 줄 — 원본 틀이 "과업지시서·2. 외관망도·3. 기타…"인데 실제 부록 간지는 "시설물관리대장 사본·외관조사 사진첩·기타…"
- header_one_line: 머리말 용역명이 두 줄 → 오른쪽 장 이름 칸을 좁혀 늘리기 → 자간 → 머리말 글자 1pt(다 만든 파일에 한 번, sitok_reports._convert_pushing)
"""
from __future__ import annotations

import math
import re

from server.sitok import report_build as rb

HP = rb.HP
SUBMIT_EM = 26.5  # 제출문 첫 줄에 드는 글자 폭(한글 1, 점선·영숫자·공백 0.5) — 원본 "점선 36 + 광숭초등학교 귀하"(26.5)는 한 줄, "양주덕산초등학교 귀하"(28.5)는 넘침
RESULT_FLOOR = {"관리주체명": 2072, "공동수급": 2072}  # 틀 1000 → 시설물 구분 줄과 같게
RESULT_ROWS = ("용역명", "관리주체명", "공동수급", "주요보수ㆍ보강", "주요보수·보강")


def _em(text: str) -> float:
    return sum(1.0 if ord(ch) > 0x2E80 else 0.5 for ch in text)


def submit_dashes(root) -> int:
    """제출문 점선 문단(점선 글자 칸 + "○○ 귀하" 글자 칸) — 점선 수 = (한 줄 폭 − 이름·귀하 폭) ÷ 0.5. 고쳤으면 1."""
    for p in root.iter(f"{{{HP}}}p"):
        runs = [r for r in p.findall(f"{{{HP}}}run") if r.find(f"{{{HP}}}t") is not None]
        if len(runs) < 2:
            continue
        t0, t1 = runs[0].find(f"{{{HP}}}t"), runs[1].find(f"{{{HP}}}t")
        if not re.fullmatch(r"-{5,}", t0.text or "") or not (t1.text or "").rstrip().endswith("귀하"):
            continue
        n = max(4, int((SUBMIT_EM - _em(t1.text.strip())) / 0.5))
        if len(t0.text) != n:
            t0.text = "-" * n
            return 1
        return 0
    return 0


def _lines(tc) -> int:
    """칸 글이 접혀 차지할 줄 수 어림(CHAR_W·칸 너비 — report_build와 같은 셈)."""
    w = int(tc.find(f"{{{HP}}}cellSz").get("width") or 0) - 282
    paras = [p for p in tc.iter(f"{{{HP}}}p") if next(p.iterancestors(f"{{{HP}}}tc"), None) is tc]
    return sum(max(1, math.ceil(len("".join(x.text or "" for x in p.iter(rb.T))) * rb.CHAR_W / max(w, 1000))) for p in paras) or 1


def result_rows(tbl) -> int:
    """결과표 좁은 줄 늘리기(10/19 형 "용역명·관리주체명·공동수급·주요 보수보강 줄 늘리기") — 줄마다 칸 글 줄 수 × LINE_H + 여백, 바닥값,
    틀 높이보다 작으면 그대로. 늘린 줄 수."""
    from server.sitok.precision_build import _set_row_height

    cells = rb._cells(tbl)
    n = 0
    for (r, c), tc in sorted(cells.items()):
        if c != 0:
            continue
        name = rb._n(rb._cell_text(tc))
        if name not in RESULT_ROWS:
            continue
        row = [x for (rr, _), x in cells.items() if rr == r and rb._span(x, "rowSpan") == 1]
        need = max((_lines(x) for x in row), default=1) * rb.LINE_H + 700
        cur = max(int(x.find(f"{{{HP}}}cellSz").get("height") or 0) for x in row)
        target = max(need, RESULT_FLOOR.get(name, 0))
        if target > cur:
            _set_row_height(tbl, r, target)
            n += 1
    return n


NA_TITLE = re.compile(r"^(\s*\d+\)\s*강재구조\s*노후상태\s*조사결과)\s*\(\s*해당\s*없음\s*\)\s*$")


def strip_na_titles(root) -> int:
    """1.3 "4)강재구조 노후상태 조사결과(해당없음)" → "(해당없음)" 뗌(10/19 형 "해당없음 제목에서 빼고")."""
    n = 0
    for p in root.iter(f"{{{HP}}}p"):
        m = NA_TITLE.match(rb._top_text(p) or "")
        if m:
            rb._set_para(p, m[1].strip())
            n += 1
    return n


TITLE_EM = 26.5  # 위치도·전경 제목(18pt) 한 줄 폭 — "2.○○ 교사동(서관)의 …"(26.0) 한 줄, "3.○○ 급식실/다목적관의 …"(27.5) 넘침


def fit_title(p, borders, cap: float = TITLE_EM) -> int:
    """제목 문단 글이 cap보다 넓으면 글자 칸마다 크기를 cap/폭 비율로(50 단위 내림) 줄인 글자 모양으로. 줄였으면 1."""
    em = _em(rb._top_text(p) or "")
    if em <= cap or borders is None:
        return 0
    for run in p.findall(f"{{{HP}}}run"):
        h = borders.char_size(run.get("charPrIDRef"))
        if h:
            run.set("charPrIDRef", borders.char_height(run.get("charPrIDRef"), int(h * cap / em) // 50 * 50))
    return 1


APPENDIX_TOC = ("시설물관리대장 사본", "외관조사 사진첩", "기타 부록 참고자료")


def toc_appendix(root) -> int:
    """목차 "▣ 부록" 다음 세 줄 → 실제 부록 간지 순서(번호 글자는 그대로 — 첫 줄은 자동 번호)."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    at = next((i for i, p in enumerate(tops) if re.fullmatch(r"\s*▣\s*부\s*록\s*", rb._top_text(p) or "")), None)
    if at is None:
        return 0
    n = 0
    rows = [p for p in tops[at + 1:at + 6] if (rb._top_text(p) or "").strip()][:3]
    for p, want in zip(rows, APPENDIX_TOC):
        t = rb._top_text(p) or ""
        m = re.match(r"^(\s*\d+\.\s*)?(.*)$", t)
        if m[2].strip() != want:
            rb._set_para(p, f"{m[1] or ''}{want}")
            n += 1
    return n


def divider_top(tbl) -> int:
    """시설물편 간지 "제N장 | 이름" 줄 — 이름이 두 줄이면 "제N장"이 두 줄 사이에 떠서 칸을 위에 붙임(10/19 형 "장 상단 줄에 맞추기"). merge._divider_table."""
    n = 0
    for tc in rb._cells(tbl).values():
        sub = tc.find(f"{{{HP}}}subList")
        if sub is not None and sub.get("vertAlign") != "TOP":
            sub.set("vertAlign", "TOP")
            n += 1
    return n


CHAPTER_RE = re.compile(r"^\s*제\s*\d+\s*장\s+")


def _own_text(p) -> str:
    """이 문단 글(표 칸 안 문단도 — rb._top_text는 표 안 글을 뺌, 안쪽 표의 글은 뺌)."""
    return "".join(rb._full(t) for t in p.iter(rb.T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p)


def chapter_title_break(root) -> int:
    """장 표지 회색 띠 "제 1 장 양주덕산초등학교 교사동(본관)" — 칸 폭을 넘으면 마지막 띄어쓰기에서 줄을 바꾸고 둘째 줄을 이름 첫 글자 아래로
    (10/19 형 "'양' 앞을 기준으로 줄바꿈"). 앞 "제 1 장 " 폭만큼 전각 공백. 바꾼 개수."""
    borders = getattr(rb._TL, "borders", None)
    n = 0
    for p in root.iter(f"{{{HP}}}p"):
        tc = next(p.iterancestors(f"{{{HP}}}tc"), None)
        full = _own_text(p)
        if tc is None or not CHAPTER_RE.match(full) or any(x.tag.endswith("lineBreak") for t in p.iter(rb.T) for x in t):
            continue
        run = next((r for r in p.findall(f"{{{HP}}}run") if r.find(f"{{{HP}}}t") is not None), None)
        size = (borders.char_size(run.get("charPrIDRef")) if borders is not None and run is not None else None) or 2000
        cap = (int(tc.find(f"{{{HP}}}cellSz").get("width") or 0) - 1500) / size
        if _em(full) <= cap:
            continue
        prefix = CHAPTER_RE.match(full).group(0)
        ts = [t for t in p.iter(rb.T) if (t.text or "").strip()]
        last = ts[-1]  # 이름이 든 글자 칸(" 양주덕산초등학교 교사동(본관)")
        text = last.text
        words = text.split(" ")
        cut = None
        for i in range(len(words) - 1, 0, -1):  # 첫 줄에 드는 가장 긴 앞부분
            if _em(prefix + " ".join(words[:i]).strip()) <= cap:
                cut = i
                break
        if cut is None:
            continue
        head, tail = " ".join(words[:cut]), " ".join(words[cut:]).strip()
        w = _em(prefix)
        indent = "\u3000" * int(w) + (" " if w - int(w) >= 0.5 else "")
        last.text = head
        br = rb.etree.SubElement(last, f"{{{HP}}}lineBreak")
        br.tail = indent + tail
        n += 1
    return n


def _direct_text_need(tc, borders) -> int:
    """칸에 바로 든 글(그림·글상자 안 글 말고)이 한 줄로 들 폭(HWPUNIT) — 칸을 좁혀도 접히지 않게."""
    need = 0
    for p in tc.iter(f"{{{HP}}}p"):
        anc = []
        for a in p.iterancestors():
            if a is tc:
                break
            anc.append(a.tag.rsplit("}", 1)[-1])
        if any(t in ("drawText", "rect", "container", "pic", "textart", "ellipse", "polygon", "footer", "header", "tbl") for t in anc):
            continue
        text = "".join(x.text or "" for x in p.iter(rb.T) if next(x.iterancestors(f"{{{HP}}}p"), None) is p)
        if not text.strip():
            continue
        run = next(p.iter(f"{{{HP}}}run"), None)
        size = (borders.char_size(run.get("charPrIDRef")) if borders is not None and run is not None else None) or 1000
        need = max(need, int(_em(text) * size * 1.08) + 1100)
    return need


def toc_list_left(root) -> int:
    """장 표지 소목차("1.1 시설물 현황 … 1.8 종합결론 및 건의") — 긴 줄("1.7 제3종시설물 외부 치장벽돌 안전점검")이 접히면 한 줄로(10/19 형 "한 줄에 써질 수
    있을 때까지 왼쪽으로 당기기"): ① 왼쪽 빈 칸을 줄여 소목차를 왼쪽으로(다른 줄 칸 경계·그 칸에 든 숨은 글 "안전진단전문기관…"이 접히지 않는 데까지 — 접히면
    표지가 넘쳐 빈 쪽), ② 오른쪽 여백 칸만큼 넓히고, ③ 그래도 모자라면 넘치는 줄만 글자를 조금 줄임. 손댄 칸 수."""
    borders = getattr(rb._TL, "borders", None)
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        rows = {}
        for (r, c), tc in cells.items():
            if re.match(r"^\s*\d+\.\d+\s", rb._cell_text(tc) or "") and (r, 0) in cells and c > 0:
                right = next((x for (rr, cc), x in cells.items() if rr == r and cc > c), None)
                rows[r] = (cells[(r, 0)], tc, right)
        if len(rows) < 4:
            continue
        col = next(iter(rows.values()))[1].find(f"{{{HP}}}cellAddr").get("colAddr")
        for (r, c), tc in cells.items():  # 같은 칸 짜임의 빈 줄(소목차 아래 18줄)도 — 줄마다 칸 경계가 다르면 한글이 표를 다시 짜며 넘침(빈 쪽)
            if r not in rows and str(c) == col and (r, 0) in cells and rb._span(cells[(r, 0)], "colSpan") == rb._span(next(iter(rows.values()))[0], "colSpan"):
                right = next((x for (rr, cc), x in cells.items() if rr == r and cc > c), None)
                rows[r] = (cells[(r, 0)], tc, right)
        w = lambda x: int(x.find(f"{{{HP}}}cellSz").get("width") or 0)  # noqa: E731

        def setw(x, v):
            x.find(f"{{{HP}}}cellSz").set("width", str(int(v)))

        def need_of(tc):
            run = next(tc.iter(f"{{{HP}}}run"), None)
            size = (borders.char_size(run.get("charPrIDRef")) if borders is not None and run is not None else None) or 1000
            return int(_em(rb._cell_text(tc).strip()) * size * 1.08) + 1400

        need = max(need_of(tc) - w(tc) for _, tc, _ in rows.values())
        if need <= 0:
            continue
        floor = max((w(c) for (r, c0), c in cells.items() if c0 == 0 and r not in rows and rb._span(c, "colSpan") < 3), default=0)
        d_left = max(0, min([need] + [w(left) - max(floor + 300, _direct_text_need(left, borders)) for left, _, _ in rows.values()]))
        rights = [right for _, _, right in rows.values()]
        d_right = max(0, min([need - d_left] + [w(x) - 300 for x in rights if x is not None])) if all(x is not None for x in rights) else 0
        for left, tc, right in rows.values():
            if d_left:
                setw(left, w(left) - d_left)
            if d_right:
                setw(right, w(right) - d_right)
            setw(tc, w(tc) + d_left + d_right)
            n += 1
            over = need_of(tc) - w(tc)
            if over > 0 and borders is not None:  # ③ 이 줄만 글자 조금 작게
                for run in tc.iter(f"{{{HP}}}run"):
                    size = borders.char_size(run.get("charPrIDRef"))
                    if size:
                        fit = int(size * (w(tc) - 1400) / max(need_of(tc) - 1400, 1)) // 50 * 50
                        run.set("charPrIDRef", borders.char_height(run.get("charPrIDRef"), max(fit, size - 300)))
    return n


CHANGE_HEAD = re.compile(r"^\s*\d\)\s*.*변경\s*사항\s*$")


def _blank(q) -> bool:
    return not (rb._top_text(q) or "").strip() and next(q.iter(f"{{{HP}}}tbl"), None) is None and next(q.iter(f"{{{HP}}}pic"), None) is None


def trim_blank_before_change_heads(root) -> int:
    """1.2.8 "3) 건축물의 형태 및 용도 변경사항" 앞 빈 문단(원본 2개) — 쪽이 넘어가면 새 쪽 위에 빈칸으로 남음(10/19 형 "칸 올리기"). 앞이 표인 제목만. 지운 수."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    n = 0
    for i, p in enumerate(tops):
        if not CHANGE_HEAD.match(rb._top_text(p) or ""):
            continue
        j = i - 1
        blanks = []
        while j >= 0 and _blank(tops[j]):
            blanks.append(tops[j])
            j -= 1
        if blanks and j >= 0 and next(tops[j].iter(f"{{{HP}}}tbl"), None) is not None:
            for q in blanks:
                q.getparent().remove(q)
                n += 1
    return n


def grade_para_indent(root, keep) -> int:
    """1.8 "1) 시설물의 안전등급 : ○등급" 다음 "본 시설물은 …" 문단 — 원본 모양이 첫 줄 내어 쓰기(-2128)라 "본"이 튀어나옴(10/19 형 "줄맞추기") → 내어 쓰기 0."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    hh = "{http://www.hancom.co.kr/hwpml/2011/core}"

    def no_intent(pp):
        for el in pp.iter(f"{hh}intent"):
            el.set("value", "0")

    n = 0
    for i, p in enumerate(tops[:-1]):
        if re.match(r"\s*1\)\s*시설물의\s*안전등급", rb._top_text(p) or ""):
            q = next((x for x in tops[i + 1:i + 4] if (rb._top_text(x) or "").strip()), None)
            if q is not None and (rb._top_text(q) or "").strip().startswith("본"):
                q.set("paraPrIDRef", keep.clone(q.get("paraPrIDRef"), "no_intent", no_intent))
                n += 1
    return n


def submit_date(root, ym) -> int:
    """제출문 날짜 "2026 년 06월"(원본 그대로 남던 것) → 보고서 연월(표지와 같음)."""
    if not ym:
        return 0
    for p in root.iter(f"{{{HP}}}p"):
        if re.fullmatch(r"\s*\d{4}\s*년\s*\d{1,2}\s*월\s*", _own_text(p)):
            want = f"{ym[0]} 년 {ym[1]:02d}월"
            if _own_text(p).strip() != want:
                rb._set_para(p, want, in_table=next(p.iterancestors(f"{{{HP}}}tc"), None) is not None)
                return 1
            return 0
    return 0


def appendix_dates(root, start) -> int:
    """부록 과업지시서·과업수행계획서 표지 "2026. 04."(원본 날짜) → 이번 점검 시작 연월(10/19 형 "왜 4월인지")."""
    if not start:
        return 0
    n = 0
    want = f"{start.year}. {start.month:02d}."
    for p in root.iter(f"{{{HP}}}p"):
        t = _own_text(p)
        if re.fullmatch(r"\s*\d{4}\s*\.\s*\d{1,2}\s*\.\s*", t) and t.strip() != want:
            rb._set_para(p, want, in_table=next(p.iterancestors(f"{{{HP}}}tc"), None) is not None)
            n += 1
    return n


def task_title(root, title: str) -> int:
    """부록 과업지시서 표지 첫 줄("양주덕산초등학교 제3종 시설물") → 용역명(표지 문구) 앞부분 "○○에 대한 2026년 하반기"(10/19 형 "이것도 다 통일"),
    둘째 줄 "정기안전점검 용역 과업지시서"는 그대로."""
    m = re.match(r"^(.*?)\s*(정기|정밀)안전점검\s*보고서\s*$", title or "")
    if not m:
        return 0
    ps = list(root.iter(f"{{{HP}}}p"))
    for i, p in enumerate(ps):
        if re.fullmatch(r"\s*(정기|정밀)안전점검\s*용역\s*과업지시서\s*", _own_text(p)):
            prev = next((q for q in reversed(ps[max(0, i - 4):i]) if _own_text(q).strip()), None)
            if prev is not None and _own_text(prev).strip() != m[1]:
                rb._set_para(prev, m[1], in_table=next(prev.iterancestors(f"{{{HP}}}tc"), None) is not None)
                return 1
            return 0
    return 0


def seismic_gap(root) -> int:
    """부록 내진보강시설 육안 점검표 "□ 기관명 : ㈜한국미래안전        □ 건물명 : ○○" — 사이 공백이 길어 건물명 끝이 다음 줄로(10/19 형 "왼쪽으로 당기기") → 세 칸."""
    n = 0
    for p in root.iter(f"{{{HP}}}p"):
        for t in p.iter(rb.T):
            if t.text and "건물명" in t.text and re.search(r"\s{4,}□\s*건물명", t.text):
                t.text = re.sub(r"\s{4,}(□\s*건물명)", r"   \1", t.text)
                n += 1
    return n


def _is_target(tbl) -> bool:
    if int(tbl.get("colCnt") or 0) < 8:
        return False
    head = [re.sub(r"\s|\(.*?\)", "", rb._cell_text(tc)) for (r, c), tc in rb._cells(tbl).items() if r == 0]
    return any(h in ("건물명", "시설명") for h in head) and any(h.startswith("연면적") for h in head)


def target_rows(lead_roots: list, other_roots: list[list]) -> int:
    """묶음 — 부록 과업지시서·과업수행계획서 대상 시설물 표에 둘째 동부터 줄을 더함(각 동 파일 표의 첫 줄 값, 10/19 형 "동이 여러 개임"). 더한 줄 수."""
    leads = [t for root in lead_roots for t in root.iter(f"{{{HP}}}tbl") if _is_target(t)]
    n = 0
    for oroots in other_roots:
        others = [t for root in oroots for t in root.iter(f"{{{HP}}}tbl") if _is_target(t)]
        for lt, ot in zip(leads, others):
            src = {c: rb._cell_text(tc) for (r, c), tc in rb._cells(ot).items() if r == 1}
            rb._add_row(lt)
            lc = rb._cells(lt)
            new = max(r for r, _ in lc)
            for c, text in src.items():
                if (new, c) in lc:
                    rb._set_lines(lc[(new, c)], text.split("\n") or ["-"])
            n += 1
    return n


def spine_name(root, name: str, borders=None) -> int:
    """책등 표(폭 9mm, 세로로 한 글자씩) 괄호 ︻ ︼ 안 → name 한 문단(원본 "광숭초등학교 / 광숭초등학교" 두 줄 — 10/19 형 "네모칸도 똑같이 이름 바꾸고").
    묶음은 "1장 시설물명 등 N개소"(merge.cover_name)."""
    for tbl in root.iter(f"{{{HP}}}tbl"):
        if tbl.get("colCnt") != "1" or "︻" not in "".join(rb._cell_text(c) for c in rb._cells(tbl).values()):
            continue
        tc = rb._cells(tbl).get((0, 0))
        if tc is None:
            return 0
        ps = [p for p in tc.iter(f"{{{HP}}}p") if next(p.iterancestors(f"{{{HP}}}tc"), None) is tc]
        texts = [_own_text(p).strip() for p in ps]
        if "︻" not in texts or "︼" not in texts:
            return 0
        a, b = texts.index("︻"), texts.index("︼")
        inner = ps[a + 1:b]
        if not inner:
            return 0
        lines = lambda xs: sum(max(1, len(re.sub(r"\s", "", t))) for t in xs)  # noqa: E731 — 폭 9mm라 한 줄에 한 글자
        before = lines(texts)
        rb._set_para(inner[0], name, in_table=True)
        for p in inner[1:]:
            p.getparent().remove(p)
        ps = [p for p in tc.iter(f"{{{HP}}}p") if next(p.iterancestors(f"{{{HP}}}tc"), None) is tc]
        over = lines([_own_text(p).strip() for p in ps]) - before
        for p in [q for q in ps if not _own_text(q).strip()]:  # 길어진 만큼 빈 줄부터 뺌(10/19 — 맨 아래 "㈜한국미래안전"이 쪽 밖으로)
            if over <= 0:
                break
            p.getparent().remove(p)
            over -= 1
        borders = borders if borders is not None else getattr(rb._TL, "borders", None)
        if over > 0 and borders is not None:  # 그래도 길면 이름 글자만 작게
            n = max(1, len(re.sub(r"\s", "", name)))
            for run in inner[0].findall(f"{{{HP}}}run"):
                size = borders.char_size(run.get("charPrIDRef"))
                if size:
                    run.set("charPrIDRef", borders.char_height(run.get("charPrIDRef"), int(size * (n - over) / n) // 50 * 50))
        return 1
    return 0


def split_cover_pdf(pdf, title: str):
    """합본에서 책등 쪽(︻ 괄호가 있는 앞쪽)을 떼어 "표지 + 책등" PDF로(10/19 형 "제본집에 표지 파일만 따로 보내게, 합본에서는 빼고, 표지까지 합본해서").
    파일 이름 "○○에 대한 2026년 하반기 정기안전점검 표지.pdf". 책등 쪽이 없으면 None."""
    from pathlib import Path

    import pymupdf

    pdf = Path(pdf)
    with pymupdf.open(pdf) as doc:
        spine = next((i for i in range(1, min(4, len(doc))) if "︻" in doc[i].get_text()), None)
        if spine is None:
            return None
        name = re.sub(r'[\/:*?"<>|]', "_", re.sub(r"\s*보고서\s*$", "", title or "보고서").strip() + " 표지.pdf")
        dest = pdf.parent / name
        with pymupdf.open() as out:
            out.insert_pdf(doc, from_page=0, to_page=0)
            out.insert_pdf(doc, from_page=spine, to_page=spine)
            out.save(dest, garbage=3, deflate=True)
        doc.delete_page(spine)
        tmp = pdf.with_suffix(".nospine.pdf")
        doc.save(tmp, garbage=3, deflate=True)
    tmp.replace(pdf)
    return dest


HEADER_PAD = 300  # 머리말 칸 안 글 폭 어림 여유(HWPUNIT)
HEADER_SPACING_MIN = -10  # 자간은 원래보다 10%까지 줄임
HEADER_SIZE_STEP = 100  # 글자 크기 한 칸 = 1pt
_FONT_FILES = {"굴림": ("gulim.ttc", 0), "굴림체": ("gulim.ttc", 1), "돋움": ("gulim.ttc", 2), "돋움체": ("gulim.ttc", 3),
               "바탕": ("batang.ttc", 0), "바탕체": ("batang.ttc", 1), "맑은 고딕": ("malgun.ttf", 0)}
_fonts: dict = {}


def _font(face: str):
    """글꼴 이름 → PIL 글꼴(1000px = 1em), 없으면 None(글자 수 어림)."""
    if face not in _fonts:
        _fonts[face] = None
        f = _FONT_FILES.get(face)
        if f:
            try:
                from PIL import ImageFont
                _fonts[face] = ImageFont.truetype(f"C:/Windows/Fonts/{f[0]}", 1000, index=f[1])
            except OSError:
                pass
    return _fonts[face]


def _runs_width(tc, borders, faces: dict, size_step: int = 0, spacing: int | None = None) -> int:
    """칸 글(한 줄로 쓸 때) 폭 HWPUNIT — 글자 크기를 size_step만큼, 자간을 spacing(%)으로 바꾼다면."""
    w = 0.0
    for run in tc.iter(f"{{{HP}}}run"):
        text = "".join(t.text or "" for t in run.iter(rb.T))
        info = borders.char_info(run.get("charPrIDRef")) if text else None
        if not info:
            continue
        size = info["height"] - size_step
        f = _font(faces.get(info["font"], ""))
        adv = sum(f.getlength(ch) for ch in text) / 1000 * size if f is not None else _em(text) * size
        w += adv * info["ratio"] / 100 + len(text) * size * (info["spacing"] if spacing is None else spacing) / 100
    return int(w)


def header_one_line(hwpx) -> int:
    """머리말 표(왼쪽 용역명 | 오른쪽 "Ⅰ. 공통편 제 1장. 서론")에서 용역명이 두 줄로 접히면(10/19 형 "머릿말을 땡겨서 한줄로 하기,
    그래도 넘으면 자간줄이기, 그래도 넘으면 머릿말 전체 페이지 글자크기 한칸 줄이기"):
    ① 오른쪽 칸을 그 글 폭만큼으로 좁혀 왼쪽 칸을 늘림 → ② 그래도 넘으면 용역명 자간을 1%씩(-10%까지) → ③ 그래도 넘으면 머리말 글자 전부 1pt 작게(+ 자간).
    ②·③은 모든 쪽 머리말에 같게(가장 긴 장 이름 기준). 다 만든 한글 파일(합본 포함)을 PDF로 바꾸기 전에 한 번(sitok_reports._convert_pushing)."""
    import zipfile
    from pathlib import Path

    from lxml import etree

    from server.sitok.borders import Borders

    hwpx = Path(hwpx)
    with zipfile.ZipFile(hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    hx = data.get("Contents/header.xml", b"").decode("utf-8")
    if not hx:
        return 0
    bd = Borders(hx)
    faces = {}
    m = re.search(r'<hh:fontface lang="HANGUL"[\s\S]*?</hh:fontface>', hx)
    for fid, face in re.findall(r'<hh:font id="(\d+)" face="([^"]+)"', m[0] if m else ""):
        faces[int(fid)] = face
    roots = {n: etree.fromstring(data[n]) for n in sorted(data) if re.fullmatch(r"Contents/section\d+\.xml", n)}
    items = []  # (표, 왼쪽 칸, 오른쪽 칸)
    for root in roots.values():
        for h in root.iter(f"{{{HP}}}header"):
            tbl = next((t for t in h.iter(f"{{{HP}}}tbl") if t.get("rowCnt") == "1" and t.get("colCnt") == "2"), None)
            cells = rb._cells(tbl) if tbl is not None else {}
            a, b = cells.get((0, 0)), cells.get((0, 1))
            if a is not None and b is not None and rb._cell_text(a).strip() and rb._cell_text(b).strip():
                items.append((tbl, a, b))
    if not items:
        return 0
    def width(tc) -> int:
        return int(tc.find(f"{{{HP}}}cellSz").get("width"))

    def margin(tc) -> int:
        mg = tc.find(f"{{{HP}}}cellMargin")
        return int(mg.get("left", 510)) + int(mg.get("right", 510)) if mg is not None else 1020

    if all(_runs_width(a, bd, faces) + HEADER_PAD <= width(a) - margin(a) for _, a, _ in items):
        return 0  # 다 한 줄

    def plan(step: int, spacing: int | None):
        """모든 머리말이 한 줄이면 [(왼쪽 칸 폭, 오른쪽 칸 폭)], 아니면 None."""
        out = []
        for _, a, b in items:
            total = width(a) + width(b)
            right = min(width(b), _runs_width(b, bd, faces, step) + margin(b) + HEADER_PAD)
            if _runs_width(a, bd, faces, step, spacing) + HEADER_PAD > total - right - margin(a):
                return None
            out.append((total - right, right))
        return out

    base = min((bd.char_info(r.get("charPrIDRef")) or {}).get("spacing", 0) for _, a, _ in items for r in a.iter(f"{{{HP}}}run"))
    tries = [(0, None)] + [(0, base - k) for k in range(1, -HEADER_SPACING_MIN + 1)] + [(HEADER_SIZE_STEP, None)] + \
        [(HEADER_SIZE_STEP, base - k) for k in range(1, -HEADER_SPACING_MIN + 1)]
    step, spacing, sizes = HEADER_SIZE_STEP, base + HEADER_SPACING_MIN, None
    for s_, sp in tries:
        sizes = plan(s_, sp)
        if sizes:
            step, spacing = s_, sp
            break
    if sizes is None:  # 끝까지 줄여도 넘침 — 가장 줄인 모양으로(두 줄일 수 있음), 칸은 오른쪽 글 폭만큼
        sizes = [(width(a) + width(b) - min(width(b), _runs_width(b, bd, faces, step) + margin(b) + HEADER_PAD),
                  min(width(b), _runs_width(b, bd, faces, step) + margin(b) + HEADER_PAD)) for _, a, b in items]
    for (tbl, a, b), (wa, wb) in zip(items, sizes):
        a.find(f"{{{HP}}}cellSz").set("width", str(wa))
        b.find(f"{{{HP}}}cellSz").set("width", str(wb))
        for tc in (a, b) if step else (a,):
            for run in tc.iter(f"{{{HP}}}run"):
                cid = run.get("charPrIDRef")
                if step:
                    cid = bd.char_height(cid, (bd.char_size(cid) or 1000) - step)
                if spacing is not None and tc is a:
                    cid = bd.char_spacing(cid, spacing)
                run.set("charPrIDRef", cid)
        for el in list(tbl.iter(f"{{{HP}}}linesegarray")):
            el.getparent().remove(el)
    data["Contents/header.xml"] = bd.result(hx).encode("utf-8")
    for n, root in roots.items():
        data[n] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    from server.sitok.pagecheck import _rewrite

    _rewrite(hwpx, infos, data)
    return len(items)
