"""시특법 보고서 시설물편 1.1·1.2 시설물 현황(2026-10-11) — 처음 맡는 시설물(신축·타회사 인계)은 틀이 다른 시설물 것이라 새로 채워야 함.

틀마다 칸 배치가 조금씩 달라도 되게 "이름 칸 → 값 칸"으로 읽고 씀:
- 건축물 현황표(머리 "건축물 현황표", 4칸: 이름|값|이름|값, 세로로 합친 이름은 값 여러 줄),
- 1.2.4 구조 및 마감상태(3칸: 구분|세부|내용 — 이름 = "재료강도/콘크리트"처럼),
- 1.2.1~1.2.3 체크 줄(☑/□ — 줄마다 하나 고르기),
- 용도현황(층수|바닥면적|주용도|비고 + 마지막 "연면적 합계" 줄).
값 = 회차 survey["detail"]({fields: {이름: 값}, checks: {줄 앞부분: 고른 번호}, uses: [[층, 면적, 용도, 비고]], uses_total}).
AI 초안 = 관리대장(+건축물대장) PDF 글자로 — fill_ai.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb

HP = rb.HP
BOX = re.compile(r"[☑□☐■]")


def _key(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def _tables(root):
    """(현황표, 구조표, 용도표) — 없으면 None."""
    hy = gu = yo = None
    for t in root.iter(f"{{{HP}}}tbl"):
        c = rb._cells(t)
        first = _key(rb._cell_text(c.get((0, 0), t)))
        txt = _key("".join(rb._cell_text(v) for v in c.values()))
        if hy is None and first == "건축물현황표":
            hy = t
        elif gu is None and t.get("colCnt") == "3" and first == "구분" and "구조형식" in txt and "재료강도" in txt:
            gu = t
        elif yo is None and "바닥면적" in txt and "주용도" in txt and first.startswith("층"):
            yo = t
    return hy, gu, yo


def _old_table(root):
    """옛 모양 1.1 표(첫 칸 "시설물명(FMS등록기준)", 한 줄에 이름|값 여럿 — 숭의 2025 하반기) — 전회차 값 읽기만(10/12)."""
    for t in root.iter(f"{{{HP}}}tbl"):
        if _key(rb._cell_text(rb._cells(t).get((0, 0), t))).startswith("시설물명"):
            return t
    return None


OLD_ALIAS = {"시설물위치": "위치", "준공일자": "준공년월일", "건축연면적": "연면적"}  # 옛 모양 이름 → 회사 원본 칸 이름


def _old_fields(t) -> list[dict]:
    """옛 모양 표 → 칸들(줄마다 칸 차례로 이름, 오른쪽 값 — 같은 이름은 처음 것)."""
    c = rb._cells(t)
    out, seen = [], set()
    for r in sorted({k[0] for k in c}):
        row = [c[k] for k in sorted(k for k in c if k[0] == r)]
        for a, b in zip(row[::2], row[1::2]):
            label = rb._cell_text(a).replace("\n", " ").strip()
            k = re.sub(r"\(.*?\)", "", _key(label))
            k = OLD_ALIAS.get(k, k)
            v = rb._cell_text(b).strip()
            if k and v and k not in seen:
                seen.add(k)
                out.append({"key": k, "label": label, "value": v, "group": "건축물 현황표"})
    return out


def _seismic(root):
    """1.2.5 내진설계 여부 표(머리 "내진설계 여부"|"확인결과") → (여부 칸, 확인결과 칸) 또는 None."""
    for t in root.iter(f"{{{HP}}}tbl"):
        c = rb._cells(t)
        if _key(rb._cell_text(c.get((0, 0), t))) == "내진설계여부" and (1, 0) in c and (1, 1) in c:
            return c[(1, 0)], c[(1, 1)]
    return None


def _span(tc, kind="rowSpan") -> int:
    return int(tc.find(f"{{{HP}}}cellSpan").get(kind))


def _pairs(t, label_cols: tuple[int, ...]) -> list[tuple[str, list]]:
    """현황표: [(이름, [값 칸들])] — 이름 칸 오른쪽 칸(세로 합친 이름이면 그 줄들의 오른쪽 칸들)."""
    c = rb._cells(t)
    out = []
    for (r, col), tc in sorted(c.items()):
        if r == 0 or col not in label_cols or (r, col + 1) not in c:
            continue
        vals = [c[(rr, col + 1)] for rr in range(r, r + _span(tc)) if (rr, col + 1) in c]
        out.append((rb._cell_text(tc).replace("\n", " ").strip(), vals))
    return out


def _struct_pairs(t) -> list[tuple[str, list]]:
    """구조표: 이름 = 구분(+세부), 값 = 셋째 칸."""
    c = rb._cells(t)
    out, group = [], ""
    for r in sorted({k[0] for k in c if k[0] > 0}):
        if (r, 0) in c:
            group = rb._cell_text(c[(r, 0)]).replace("\n", " ").strip()
        sub = rb._cell_text(c[(r, 1)]).strip() if (r, 1) in c else ""
        if (r, 2) in c:
            out.append((f"{group}/{sub}" if sub else group, [c[(r, 2)]]))
    return out


def _check_paras(root) -> list:
    """1.2.1 ~ 1.2.3의 체크 줄 문단(☑/□가 두 개 이상)."""
    out, on = [], False
    for p in (q for q in root if q.tag == f"{{{HP}}}p"):
        t = rb._top_text(p)
        if re.match(r"1\.2\.1", t):
            on = True
        elif re.match(r"1\.2\.4", t) or re.match(r"1\.3", t):
            on = False
        if on and len(BOX.findall(t)) >= 2:
            out.append(p)
    return out


def _options(line: str) -> tuple[str, list[str], int | None]:
    """"4) 실시자 자격 : □ 관리주체직원, ☑ 외부 의뢰" → (앞부분, [선택지], 고른 번호)."""
    parts = BOX.split(line)
    head = parts[0].strip()
    marks = BOX.findall(line)
    opts = [re.sub(r"[,，]\s*$", "", x).strip() for x in parts[1:]]
    sel = next((i for i, m in enumerate(marks) if m in "☑■"), None)
    return head, opts, sel


def _check_keys(paras) -> list[str]:
    """체크 줄 키 — 앞부분 글(같은 줄이 두 번이면 "#2")."""
    out, seen = [], {}
    for p in paras:
        head, opts, _ = _options(rb._top_text(p))
        k = _key(head) or _key(" ".join(opts))
        seen[k] = seen.get(k, 0) + 1
        out.append(k if seen[k] == 1 else f"{k}#{seen[k]}")
    return out


def _val_text(cells: list) -> str:
    return "\n".join(rb._cell_text(x).strip() for x in cells)


def read(hwpx: Path) -> dict:
    """틀의 지금 값 — 창에 보여 줄 모양."""
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in rb._sections(z)]
    root = next((r for r in roots if _tables(r)[0] is not None), None)  # 시설물편 구역
    if root is None:
        root = next((r for r in roots if _old_table(r) is not None), roots[-1])
    hy, gu, yo = _tables(root)
    fields = [{"key": _key(n), "label": n, "value": _val_text(v), "group": "건축물 현황표"} for n, v in (_pairs(hy, (0, 2)) if hy is not None else [])]
    if hy is None and _old_table(root) is not None:
        fields = _old_fields(_old_table(root))
    fields += [{"key": "구조/" + _key(n), "label": n, "value": "\n".join(x.lstrip("ㆍ·").strip() for x in _val_text(v).split("\n")),
                "group": "1.2.4 구조 및 마감상태"} for n, v in (_struct_pairs(gu) if gu is not None else [])]
    checks = []
    paras = _check_paras(root)
    for p, k in zip(paras, _check_keys(paras)):
        head, opts, sel = _options(rb._top_text(p))
        checks.append({"key": k, "label": head or "└ (위 줄 이어서)", "options": opts, "selected": sel})
    se = _seismic(root)
    if se is not None:
        _, opts, sel = _options(rb._cell_text(se[0]))
        checks.append({"key": "내진설계여부", "label": "1.2.5 내진설계 여부", "options": opts, "selected": sel})
        fields.append({"key": "내진/확인결과", "label": "확인결과", "value": rb._cell_text(se[1]).lstrip("ㆍ·").strip(), "group": "1.2.5 내진설계 여부 확인"})
    uses, total = [], ""
    if yo is not None:
        c = rb._cells(yo)
        rows = sorted({k[0] for k in c if k[0] > 0})
        for r in rows:
            first = rb._cell_text(c.get((r, 0), yo)).strip()
            if "합계" in first or "계" == first:
                total = rb._cell_text(c.get((r, 1), yo)).strip()
                continue
            uses.append([rb._cell_text(c[(r, k)]).strip() if (r, k) in c else "" for k in range(4)])
    return {"fields": fields, "checks": checks, "uses": uses, "uses_total": total}


def _set_rows(t, rows: list[list[str]]) -> None:
    """용도표 데이터 줄을 rows로(첫 줄 머리, 마지막 줄 합계는 그대로) — 줄 수가 다르면 가운데 줄을 본떠 늘리거나 지움."""
    import copy

    trs = t.findall(f"{{{HP}}}tr")
    head, body, tail = trs[0], trs[1:-1], trs[-1]
    if not body:
        return
    tmpl = body[0]
    while len(body) < len(rows):
        tr = copy.deepcopy(tmpl)
        body[-1].addnext(tr)
        body.append(tr)
    while len(body) > max(len(rows), 1):
        t.remove(body.pop())
    h = 0
    for i, tr in enumerate([head, *body, tail]):
        for tc in tr.findall(f"{{{HP}}}tc"):
            tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(i))
    for tr, row in zip(body, rows or [["-", "-", "-", "-"]]):
        for k, tc in enumerate(tr.findall(f"{{{HP}}}tc")):
            rb._set_lines(tc, [row[k] if k < len(row) and row[k] else "-"])
        h += int(tr.findall(f"{{{HP}}}tc")[0].find(f"{{{HP}}}cellSz").get("height"))
    n = len(body) + 2
    old = int(t.get("rowCnt"))
    t.set("rowCnt", str(n))
    for cz in t.iter(f"{{{HP}}}cellzone"):
        if int(cz.get("endRowAddr", "0")) >= old - 1:
            cz.set("endRowAddr", str(n - 1))


def _bare(x) -> str:
    """앞 글머리 점·공백 뗀 값."""
    return str(x or "").strip().lstrip("ㆍ·•∙・").strip()


def apply(root, detail: dict) -> int:
    """회차 detail을 틀 표·체크 줄에 — 이름이 같은 칸만(없는 이름은 그대로)."""
    hy, gu, yo = _tables(root)
    fields = detail.get("fields") or {}
    n = 0
    for t, pairs, pre in ((hy, _pairs(hy, (0, 2)) if hy is not None else [], ""), (gu, _struct_pairs(gu) if gu is not None else [], "구조/")):
        for name, cells in pairs:
            v = fields.get(pre + _key(name))
            if v is None:
                continue
            lines = [x for x in str(v).split("\n")] or [""]
            if pre:  # 값 앞에 이미 점(·ㆍ)이 있으면 떼고 하나만(10/19 형 "점이 두 개 생김" — 전회차 보고서 PDF에서 읽은 값)
                lines = [f"ㆍ{_bare(x)}" if _bare(x) and _bare(x) != "-" else (_bare(x) or "-") for x in lines]
            if len(cells) == 1:
                rb._set_lines(cells[0], lines)
            else:  # 세로로 합친 이름(방수공법) — 칸마다 한 줄, 줄이 모자라면 "-"(10/12 빈칸 안 남게)
                for i, tc in enumerate(cells):
                    rb._set_lines(tc, [lines[i] if i < len(lines) else "-"])
            n += 1
    checks = detail.get("checks") or {}
    se = _seismic(root)
    if se is not None:
        if "내진설계여부" in checks:
            line = rb._cell_text(se[0])
            marks = iter(range(len(BOX.findall(line))))
            rb._set_lines(se[0], [BOX.sub(lambda m: "☑" if next(marks) == checks["내진설계여부"] else "□", line)])
            n += 1
        v = fields.get("내진/확인결과")
        if v is not None:
            rb._set_lines(se[1], [f"ㆍ{_bare(v)}" if _bare(v) and _bare(v) != "-" else "-"])
            n += 1
    paras = _check_paras(root)
    for p, k in zip(paras, _check_keys(paras)):
        line = rb._top_text(p)
        head, opts, _ = _options(line)
        if k not in checks:
            continue
        sel = checks[k]
        marks = iter(range(len(opts)))
        new = BOX.sub(lambda m: "☑" if next(marks) == sel else "□", line)
        if new != line:
            rb._set_para(p, new)
            n += 1
    if yo is not None and detail.get("uses") is not None:
        _set_rows(yo, detail["uses"])
        c = rb._cells(yo)  # 합계 칸 — 값이 없어도 "-"(원본 광숭초 "9,534.1 ㎡"가 남지 않게, 10/12)
        last = max(k[0] for k in c)
        if (last, 1) in c:
            rb._set_lines(c[(last, 1)], [detail.get("uses_total") or "-"])
        n += 1
    return n


PROMPT = """시설물 정기안전점검 보고서의 "시설물 현황" 칸을 채우려 합니다. 아래 자료(시설물관리대장·건축물대장 글자, 시설물 정보)에서 각 칸 값을 찾아
JSON 객체 하나로만 답하세요(설명 없이). 자료에 없으면 "-"(지어내지 말 것). 숫자는 단위까지(예: "2,241.28㎡", "19.8m", "fck=21MPa").
{{"fields": {{칸 키: 값}}, "uses": [[층(예: 지하1층·지상1층·옥탑1층), 바닥면적(숫자), 주용도, 비고]] — 건축물대장 층별 현황이 있을 때만(없으면 []), "uses_total": "연면적 합계 글(예: 8,795.17㎡(건축물대장기준))"}}

[칸 키 — 이름(지금 틀 값은 다른 시설물 것이니 참고만)]
{fields}

[시설물 정보]
{facility}

[자료]
{docs}
{drawings}"""

DRAWINGS = """
[구조일반사항·건축개요 도면 — 붙인 그림(쪽 그림)과 아래 글자] 도면 주기·표에서 찾을 것: 콘크리트 설계강도(fck)·철근 종류(SD400 등, MPa)·철골 종류(SS275 등)·
기초형식(매트기초·독립기초·파일 등)·지하깊이(GL 기준)·기둥 표준간격(스팬)·지하수위·기준층 슬래브 두께·방수공법(지붕층·지하층)·구조형식·최고높이.
관리대장·건축물대장과 다르면 관리대장·건축물대장 값을 쓰되, 그쪽에 없는 칸만 도면에서.
{text}"""


def _pdf_text(path: Path, limit: int = 15000) -> str:
    import pymupdf

    with pymupdf.open(path) as doc:
        return "\n".join(p.get_text() for p in doc)[:limit]


def fill_ai(cur: dict, facility: str, pdfs: list[Path], company_id: int, drawings: tuple[str, list[bytes]] | None = None) -> dict:
    """AI 초안 — fields·uses만(체크 줄은 점검자가). drawings = 구조일반사항·건축개요 도면(글자, 쪽 그림들) — server/sitok/drawings.py for_ai(10/12)."""
    from server.sitok import vision

    docs = "\n\n".join(f"<{p.name}>\n{_pdf_text(p)}" for p in pdfs if p and Path(p).exists()) or "(없음)"
    spec = "\n".join(f"{f['key']} — {f['label']} (지금: {f['value'][:40]})" for f in cur["fields"])
    text, imgs = drawings or ("", [])
    extra = DRAWINGS.format(text=text[:12000] or "(글자 없음 — 그림으로)") if drawings else ""
    got = vision.ask_json(company_id, imgs, PROMPT.format(fields=spec, facility=facility, docs=docs, drawings=extra), max_tokens=16000)
    fields = {f["key"]: str((got.get("fields") or {}).get(f["key"], "-") or "-").strip() for f in cur["fields"]}
    uses = [[str(x or "").strip() for x in (row + ["", "", "", ""])[:4]] for row in (got.get("uses") or []) if isinstance(row, list)]
    return {"fields": fields, "uses": uses or None, "uses_total": str(got.get("uses_total") or "").strip()}
