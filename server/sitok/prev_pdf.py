"""전회차 보고서 PDF(2026-10-18 민재형 — "지난 보고서 한글 넣기를 없애고, 전회차가 우리 회사든 타사든 있으면 동마다 전회차 시설물현황·보관관리실태·
용도현황·보수보강이력·변경사항 실태조사 PDF를 첨부하면 읽을 수 있도록").

동(회차)마다 PDF 하나 — 회차 폴더 "전회차보고서.pdf". 올리기만 하면 AI를 안 씀. [🤖 채우기](시설물 현황)·[🤖 전회차 보고서로 초안](1.2.8)·
[🤖 읽기](1.2.7 지난 이력) 중 처음 누를 때 한 번 읽어 sitok_report.survey["prev"]에 저장하고, 그다음부턴 저장한 값(다시 올리면 지움).
읽는 것: 1.1 건축물 현황표·1.2.4 구조 및 마감(칸 키 = 회사 원본 detail.read), 1.2.1~1.2.3 보관·관리 실태 체크, 용도현황, 1.2.6 기실시 점검이력,
1.2.7 보수·보강 이력, 1.2.8 변경사항, 결과표(점검기간·점검기관·안전등급·주요결과). 쓰는 곳: sitok_reports._detail_defaults·_base_extras·survey_get, sitok_prev.py.
"""
from __future__ import annotations

import datetime
from pathlib import Path

NAME = "전회차보고서.pdf"
MAX_PAGES = 14  # AI에 보내는 쪽(글자 + 그림) — 보고서 통째로 올려도 필요한 쪽만
KEYS = ("건축물 현황표", "시설물 현황", "보관실태", "1.2.1", "1.2.4", "용도현황", "1.2.6", "기실시", "점검이력", "1.2.7", "보수", "1.2.8", "변경사항",
        "결과표", "안전등급", "주요결과")

PROMPT = """시설물 안전점검 보고서(지난 회차, 다른 회사 보고서일 수도 있음)의 쪽들입니다. 대상 동: {name}
보고서에 여러 동이 들어 있으면 이 동의 장(章)만 읽으세요. 붙인 그림과 아래 글자에서 찾아 JSON 객체 하나로만 답하세요(설명 없이).
없는 것은 "-" 또는 빈 목록(지어내지 말 것). 값은 보고서에 쓰인 그대로(단위 포함).
{{"fields": {{칸 키: 값}} — 아래 [현황 칸]의 키로(1.1 건축물 현황표·1.2.4 구조 및 마감상태),
 "checks": {{체크 키: 고른 보기 번호(0부터)}} — 아래 [보관·관리 실태 체크](☑·■·V·○ 표시가 된 보기, 표시가 없으면 빼기),
 "uses": [[층, 바닥면적(숫자), 주용도, 비고]] — 대상시설물의 용도현황 표 줄, "uses_total": "연면적 합계 글(표 맨 아래 합계)",
 "history": [{{"kind": "점검 종류", "period": "점검기간", "org": "점검기관", "grade": "안전등급", "title": "결과 제목 줄", "lines": ["주요 결과 줄"]}}] — 1.2.6 기실시 점검결과 표(위·최근부터),
 "repairs": [[보수기간, 공사종류, 보수방안, 위치, 비고]] — 1.2.7 보수·보강 이력 표 줄(빈 줄·"-"만 있는 줄은 빼기),
 "changes": {{항목 이름: {{"before": 변경전, "after": 변경후, "where": 위치, "note": 비고}}}} — 1.2.8 변경사항 실태조사 표에서 "변경사항없음"이 아닌 항목만, 항목 이름은 아래 [1.2.8 항목]에서 고르기,
 "report": {{"period": "이 보고서의 점검기간(예: 2026.03.02~2026.04.15)", "org": "점검기관(회사 이름)", "grade": "안전등급 글자 A~E(2종은 양호·보통·미흡·불량)", "findings": ["결과표 점검 주요결과 줄"]}}}}

[현황 칸 — 키 — 이름]
{fields}

[보관·관리 실태 체크 — 키 — 이름 — 보기(번호)]
{checks}

[1.2.8 항목]
{changes}

[글자]
{text}"""


def path(folder: Path) -> Path:
    return folder / NAME


def pick_pages(pdf: Path, name: str) -> list[int]:
    """보낼 쪽 — 짧은 PDF는 전부, 긴 PDF(보고서 통째)는 현황·이력·결과표 낱말이 있는 쪽(이 동 이름이 있는 쪽 먼저)."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        n = len(doc)
        if n <= MAX_PAGES:
            return list(range(n))
        texts = [p.get_text() for p in doc]
    if not any(t.strip() for t in texts):  # 스캔 PDF — 앞쪽부터
        return list(range(MAX_PAGES))
    short = (name or "").split()[-1] if name else ""
    scored = []
    for i, t in enumerate(texts):
        hits = sum(1 for k in KEYS if k in t)
        if hits:
            scored.append((-(hits + (3 if short and short in t else 0)), i))
    return sorted(i for _, i in sorted(scored)[:MAX_PAGES])


def read(pdf: Path, company_id: int, name: str, base: dict, change_labels: list[str]) -> dict:
    """AI로 한 번 읽음 → survey["prev"]에 넣을 값. base = detail.read(회사 원본)(칸 키·체크 보기)."""
    import pymupdf

    from server.sitok import vision

    pages = pick_pages(pdf, name)
    text, imgs = [], []
    with pymupdf.open(pdf) as doc:
        for i in pages:
            pg = doc[i]
            text.append(f"<{i + 1}쪽>\n{pg.get_text()}")
            zoom = min(2.0, 1600 / max(pg.rect.width, pg.rect.height))
            imgs.append(pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("jpeg"))
    fields = "\n".join(f"{f['key']} — {f['label']}" for f in base["fields"])
    checks = "\n".join(f"{c['key']} — {c['label']} — " + " / ".join(f"{i}:{o}" for i, o in enumerate(c["options"])) for c in base["checks"])
    got = vision.ask_json(company_id, imgs, PROMPT.format(name=name, fields=fields, checks=checks, changes="\n".join(change_labels) or "(없음)",
                                                          text="\n\n".join(text)[:30000]), max_tokens=16000)
    if not isinstance(got, dict):
        raise ValueError("AI 답 모양이 맞지 않습니다.")
    keys = {f["key"] for f in base["fields"]}
    opts = {c["key"]: len(c["options"]) for c in base["checks"]}
    s = lambda v: str(v or "").strip()  # noqa: E731
    out = {"at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "pages": [i + 1 for i in pages],
           "fields": {k: s(v) or "-" for k, v in (got.get("fields") or {}).items() if k in keys},
           "checks": {k: int(v) for k, v in (got.get("checks") or {}).items() if k in opts and str(v).lstrip("-").isdigit() and 0 <= int(v) < opts[k]},
           "uses": [[s(x) for x in (list(row) + ["", "", "", ""])[:4]] for row in got.get("uses") or [] if isinstance(row, list) and any(s(x) for x in row)],
           "uses_total": s(got.get("uses_total")),
           "history": [{k: (s(h.get(k)) or "-") if k != "lines" else [s(x) for x in h.get("lines") or [] if s(x)] for k in ("kind", "period", "org", "grade", "title", "lines")}
                       for h in got.get("history") or [] if isinstance(h, dict)],
           "repairs": [[s(x) for x in (list(row) + [""] * 5)[:5]] for row in got.get("repairs") or [] if isinstance(row, list) and s(row[0] if row else "") not in ("", "-")],
           "changes": {k: {f: s((v or {}).get(f)) for f in ("before", "after", "where", "note")} for k, v in (got.get("changes") or {}).items()
                       if k in change_labels and isinstance(v, dict) and s(v.get("after")) not in ("", "-", "변경사항없음")},
           "report": {k: s((got.get("report") or {}).get(k)) for k in ("period", "org", "grade")}}
    out["report"]["findings"] = [s(x) for x in (got.get("report") or {}).get("findings") or [] if s(x)]
    return out


def as_detail(prev: dict) -> dict:
    """detail.read 모양(시설물 현황 기본값) — fields [{key, value}], checks [{key, selected}], uses, uses_total."""
    return {"fields": [{"key": k, "value": v} for k, v in (prev.get("fields") or {}).items()],
            "checks": [{"key": k, "selected": v} for k, v in (prev.get("checks") or {}).items()],
            "uses": prev.get("uses") or [], "uses_total": prev.get("uses_total") or ""}
