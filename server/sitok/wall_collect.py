"""옹벽 1.3 자료수집 및 분석(2026-10-21 민재형 ⑩ — 항목별 우선순위):
- 1.3.1 자료수집 현황 = 전회차 보고서 PDF(read_prior_pdf) > 전회차 회차(그룹웨어) 값 > 직접 선택(보유/미보유·비고) — 기본값은 defaults.
- 1.3.2 기존 점검 실시결과 요약 = FMS 점검진단실적 엑셀(fms_history, 전체분) > 없으면 "-"; 그룹웨어에서 한 번 쓰면 다음 회차는 전회차 점검 줄만 더해 자동(chain_history).
- 1.3.3 보수·보강 이력 = 전회차 회차 값 > 직접.
- 1.3.4 자료분석 결과 = 1.3.1~1.3.3으로 AI(analysis_ai) — 다음 회차에 자료가 안 바뀌면(analysis_hash) 그대로, 바뀌면 다시.
회차 survey JSON: collect {key: {status, note}}, history [..], repairs [..], analysis {build_result, build_dir, maint_result, maint_dir, hash}.
"""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import re

ROWS = [("design", "설계도서(공통 — 준공내역서·시방서·계산서·지반조사)"), ("drawing", "설계도면(준공도면)"), ("ledger", "시설물관리대장"),
        ("const", "시공관련 자료(품질·시험기록·계측·사고기록)"), ("inspect", "안전점검 및 정밀안전진단 자료"), ("repair", "보수·보강 자료")]
STATUSES = ("보유", "미보유", "-")
KIND_MAP = {"정기안전점검": "정기점검", "정밀안전점검": "정밀점검", "정밀안전진단": "정밀진단", "긴급안전점검": "긴급점검", "초기점검": "초기점검"}
ROW_INDEX = {"design": 1, "drawing": 2, "ledger": 3, "const": 4, "inspect": 5, "repair": 6}  # 1.3.1 표(7×4) 줄


def _bul(s: str) -> str:
    s = (s or "").strip()
    return s if not s or s[0] in "∙⦁◦-" else "∙" + s


def defaults(spec: dict, history: list, repairs: list) -> dict:
    """1.3.1 기본값(견본 모양) — 관리대장 공사명·점검 이력·보수 이력으로."""
    proj = (spec or {}).get("project") or ""
    fms = "∙시설물정보관리종합시스템(FMS)" + (f"\n(공사명 : {proj})" if proj else "")
    insp_note = "-"
    if history:
        first, last = history[0], history[-1]
        y = lambda h: (re.search(r"(\d{4})", h.get("period") or "") or [None, ""])[1]  # noqa: E731
        insp_note = f"∙{y(first)}년 {first.get('kind') or '점검'} 용역 ∼\n∙{y(last)}년 {last.get('kind') or '점검'} 용역"
    return {"design": {"status": "보유", "note": fms}, "drawing": {"status": "보유", "note": fms}, "ledger": {"status": "보유", "note": "∙시설물정보관리종합시스템(FMS)"},
            "const": {"status": "미보유", "note": "-"}, "inspect": {"status": "보유" if history else "-", "note": insp_note},
            "repair": {"status": "보유" if repairs else "-", "note": "∙보수·보강 이력 있음(1.3.3 참조)" if repairs else "∙보수·보강 이력 없음"}}


def norm_collect(raw: dict | None, base: dict) -> dict:
    """저장값 정리 — 없는 줄은 base로, status는 보유/미보유/-."""
    out = {}
    for key, _ in ROWS:
        v = (raw or {}).get(key) or {}
        st = str(v.get("status") or "").strip()
        out[key] = {"status": st if st in STATUSES else base[key]["status"], "note": str(v.get("note") if v.get("note") is not None else base[key]["note"]).strip()}
    return out


def read_prior_pdf(pdf_path) -> dict | None:
    """전회차 보고서 PDF의 1.3.1 표 글자 → {key: {status, note}} (한글이 만든 PDF라 칸 글이 줄로 나옴: 보유/미보유/- 여섯 개가 차례로). 못 읽으면 None."""
    import pymupdf

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:  # noqa: BLE001
        return None
    try:
        for page in doc:
            t = page.get_text()
            if "1.3.1 자료수집 현황" not in t and "자료수집 현황" not in t:
                continue
            lines = [x.strip() for x in t.splitlines()]
            try:
                s = next(i for i, x in enumerate(lines) if x.startswith("보존대상"))
            except StopIteration:
                continue
            e = next((i for i, x in enumerate(lines) if i > s and x.startswith("1.3.2")), len(lines))
            seg = lines[s:e]
            idx = []
            for i, x in enumerate(seg):
                if x in STATUSES and not (x == "-" and idx and i == idx[-1] + 1):  # 보유현황 바로 다음 줄 "-"는 비고
                    idx.append(i)
            if len(idx) < 6:
                continue
            out = {}
            keys = [k for k, _ in ROWS]
            for n, i in enumerate(idx[:6]):
                stop = idx[n + 1] if n + 1 < len(idx) else len(seg)
                note = [x for x in seg[i + 1:stop] if x and (x[0] in "∙⦁(-" or x.startswith("∙")) and not re.match(r"^(◦|보존대상|시설물$|관리대장|시공관련|자료$|설계$|도서$)", x)]
                note = [x for x in note if x not in ("-",)] or (["-"] if seg[i] != "보유" else [])
                out[keys[n]] = {"status": seg[i], "note": "\n".join(note)}
            return out
    finally:
        doc.close()
    return None


def fms_history(data: bytes) -> list[dict]:
    """FMS 점검진단실적 엑셀(머리: No·점검진단구분·시작일·종료일·점검진단기관·책임기술자·비용·안전등급·주요점검진단결과·주요보수보강안…) → 1.3.2 줄(오래된 것부터)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)  # read_only는 크기 정보 없는 FMS 파일에서 줄을 못 읽음
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    head_i = next((i for i, r in enumerate(rows) if r and any("점검진단구분" in str(v or "") for v in r)), None)
    if head_i is None:
        raise ValueError("FMS 점검진단실적 엑셀이 아닙니다(머리줄에 '점검진단구분'이 없음)")
    head = [str(v or "").replace(" ", "") for v in rows[head_i]]
    col = lambda *names: next((i for i, h in enumerate(head) if any(n in h for n in names)), None)  # noqa: E731
    c_kind, c_s, c_e, c_org, c_grade, c_res, c_rep = col("점검진단구분"), col("시작일"), col("종료일"), col("점검진단기관", "기관"), col("안전등급"), col("주요점검진단결과", "결과"), col("주요보수보강", "보수")
    out = []
    for r in rows[head_i + 1:]:
        if not r or c_kind is None or not r[c_kind]:
            continue
        kind_raw = str(r[c_kind]).strip()
        kind = next((v for k, v in KIND_MAP.items() if k in kind_raw), kind_raw)
        d1, d2 = _date(r[c_s] if c_s is not None else None), _date(r[c_e] if c_e is not None else None)
        period = f"{d1}~{d2}" if d1 and d2 else (d1 or d2 or "")
        grade = str(r[c_grade] or "").strip() if c_grade is not None else ""
        grade = re.sub(r"등급$", "", grade)
        res_lines = [_bul(re.sub(r"^[\s\-–?？]+", "", x)) for x in str(r[c_res] or "").splitlines() if x.strip()] if c_res is not None else []  # FMS 글머리(-·？) → ∙
        rep = str(r[c_rep] or "").replace("？", "").strip() if c_rep is not None else ""
        out.append({"period": period, "kind": kind, "org": str(r[c_org] or "").strip() if c_org is not None else "", "grade": grade,
                    "result": "\n".join(res_lines), "note": "", "repair": rep, "_sort": d1 or ""})
    out.sort(key=lambda x: x["_sort"])
    for x in out:
        x.pop("_sort", None)
    return out


def _date(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return f"{v.year}.{v.month:02d}.{v.day:02d}."
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(v))
    return f"{m[1]}.{int(m[2]):02d}.{int(m[3]):02d}." if m else str(v).strip()


def chain_history(prev_history: list, prev_report, company: str, grade: str, findings: list) -> list[dict]:
    """다음 회차 — 전회차 점검 이력 + 전회차 자체 줄(점검기간·종류·우리 회사·등급·주요결과) — 이미 같은 기간 줄이 있으면 안 더함."""
    rows = [dict(h) for h in prev_history or []]
    if prev_report is None:
        return rows
    s, e = prev_report.period_start, prev_report.period_end
    period = f"{_date(s)}~{_date(e)}" if s and e else f"{prev_report.year}년 {prev_report.half}"
    if any((h.get("period") or "") == period for h in rows):
        return rows
    kind = "정밀점검" if (prev_report.kind or "정기") == "정밀" else "정기점검"
    rows.append({"period": period, "kind": kind, "org": company or "", "grade": grade or "양호", "result": "\n".join(_bul(x) for x in (findings or [])[:4]) or "-", "note": ""})
    return rows


def analysis_hash(collect: dict, history: list, repairs: list) -> str:
    return hashlib.md5(json.dumps([collect, history, repairs], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def analysis_fallback(collect: dict, history: list, repairs: list) -> dict:
    """AI 없이 — 견본 글을 보유 여부에 맞춰."""
    c = collect or {}
    st = lambda k: (c.get(k) or {}).get("status") or "-"  # noqa: E731
    build_res = [f"◦설계도서(준공도면 등) {'보유' if st('design') == '보유' or st('drawing') == '보유' else '미보유'}", f"◦시공관련자료 {'보유' if st('const') == '보유' else '미보유'}"]
    maint_res = [f"◦시설물관리대장 {'보유' if st('ledger') == '보유' else '미보유'}", f"◦점검이력 {'보유' if history else '미보유'}", f"◦보수∙보강 이력 {'보유' if repairs else '미기재'}"]
    return {"build_result": "\n".join(build_res), "build_dir": "◦준공후 하중변화 등 구조적 변경사항 파악",
            "maint_result": "\n".join(maint_res), "maint_dir": "◦신규손상 조사 및 전차 손상에 대한 진행성 확인" + ("\n◦보수·보강 부위 재손상 여부 확인" if repairs else ""),
            "hash": analysis_hash(collect, history, repairs)}


PROMPT = """당신은 시설물(옹벽) 정기안전점검 보고서를 쓰는 책임기술자입니다. 아래 자료수집 현황·점검 이력·보수 이력으로 "1.3.4 자료분석 결과" 표의 네 칸을 쓰세요.
표: 구분(건설관련 자료 / 유지관리 자료) × 자료분석결과 · 과업진행방향. 칸마다 "◦"로 시작하는 짧은 글머리 2~3줄, 보고서 문어체, 사실은 아래 자료에 있는 것만.

[1.3.1 자료수집 현황]
{collect}
[1.3.2 기존 점검 실시결과 요약 — 오래된 것부터]
{history}
[1.3.3 보수·보강 이력]
{repairs}

아래 JSON 객체 하나로만 답하세요(설명 없이):
{{"build_result": "건설관련 자료 분석결과(설계도서·시공자료 보유 여부와 활용)", "build_dir": "건설관련 자료로 본 과업진행방향(예: 준공후 하중변화 등 구조적 변경사항 파악)",
 "maint_result": "유지관리 자료 분석결과(관리대장·점검이력·보수이력 — 전회차 등급·주요 손상 추이)", "maint_dir": "유지관리 자료로 본 과업진행방향(예: 신규손상 조사 및 전차 손상 진행성 확인, 보수부 재손상 확인)"}}"""


def analysis_ai(collect: dict, history: list, repairs: list, company_id: int) -> dict:
    """AI로 1.3.4 네 칸 — 실패하면 fallback."""
    from server.sitok import vision

    c_txt = "\n".join(f"- {label}: {(collect.get(k) or {}).get('status', '-')} / {(collect.get(k) or {}).get('note', '')}".replace("\n", " ") for k, label in ROWS)
    h_txt = "\n".join(f"- {h.get('period')} {h.get('kind')} {h.get('org')} 등급 {h.get('grade')} : {(h.get('result') or '').replace(chr(10), ' ')}" for h in history) or "(없음 — 처음 점검)"
    r_txt = "\n".join(f"- {x.get('period')} {x.get('where')} : {x.get('method')}" for x in repairs) or "(없음)"
    fb = analysis_fallback(collect, history, repairs)
    try:
        raw = vision.ask_json(company_id, [], PROMPT.format(collect=c_txt, history=h_txt, repairs=r_txt), max_tokens=1500)
    except Exception:  # noqa: BLE001
        raw = None
    if not isinstance(raw, dict):
        return fb
    out = dict(fb)
    for k in ("build_result", "build_dir", "maint_result", "maint_dir"):
        v = raw.get(k)
        if isinstance(v, list):
            v = "\n".join(str(x) for x in v)
        if str(v or "").strip():
            out[k] = "\n".join(_bul(x).replace("∙", "◦", 1) if x.strip() and x.strip()[0] not in "◦" else x for x in str(v).splitlines() if x.strip())
    out["ai"] = True
    out["hash"] = analysis_hash(collect, history, repairs)
    return out
