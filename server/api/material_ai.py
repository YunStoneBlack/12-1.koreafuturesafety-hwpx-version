"""11번 제공자료 AI 추천(2026-10-15 사용자 "추천이 공정과 너무 안 맞음 → AI가 고르고 직원이 입맛대로 바꾸게").

[✨ AI 추천] 버튼을 누를 때만 돈다(빈 칸 자동 채우기 X — 직원이 고른 걸 덮지 않게).
AI에 주는 것: 8번 지적사항, 진행 공정·공정별 유해위험요인(표12), 방문 월(계절), 같은 현장 지난 회차에 준 자료(되도록 피함), 라이브러리 목록(번호·이름·분류).
받는 것: 칸에 넣을 2개 + 다음 후보 최대 6개, 각각 고른 이유 한 줄.
AI를 못 쓰면(키 없음·오류) 분류 겹침으로 고른다(예전 단어 겹침 방식은 "작업·시·중" 같은 흔한 말로 엉뚱한 자료를 뽑았음).
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from core.models_db import MaterialLibrary, ProvidedMaterial, Report
from server.api.material_lib import categories_of, categorize

N_PICKS = 2
N_OTHERS = 6
_GENERIC = {"재해사례", "법령·기준"}  # 어디에나 걸리는 분류 — 분류로 고를 땐 점수 낮게


def _season(month: int) -> str:
    if month in (6, 7, 8, 9):
        return "여름(폭염·장마·집중호우)"
    if month in (11, 12, 1, 2):
        return "겨울(한파·한랭질환·동절기 화재)"
    return "봄·가을(환절기)"


def context(db: Session, report: Report) -> dict:
    findings = [f"{(f.title or '').strip()}: {(f.content or '').strip()[:160]}" for f in sorted(report.findings, key=lambda f: f.slot)
                if (f.title or "").strip() or (f.content or "").strip()]
    procs = []
    for e in sorted(report.process_entries, key=lambda e: e.slot):
        if not (e.process_name or "").strip():
            continue
        hz = [i.hazard.strip() for i in sorted(e.items, key=lambda i: i.order) if (i.hazard or "").strip()][:3]
        procs.append(e.process_name.strip() + (f" — {' / '.join(h[:60] for h in hz)}" if hz else ""))
    for e in sorted(report.current_process_entries, key=lambda e: e.slot):
        name = (e.process_name or "").strip()
        if name and not any(p.startswith(name) for p in procs):
            procs.append(name)
    day = report.guidance_date or datetime.date.today()
    prev_rows = (
        db.query(ProvidedMaterial.material_id, ProvidedMaterial.title)
        .join(Report, Report.id == ProvidedMaterial.report_id)
        .filter(Report.site_id == report.site_id, Report.id != report.id, Report.visit_no < report.visit_no)
        .order_by(Report.visit_no.desc())
        .limit(8)
        .all()
    )
    return {"site": report.site.name if report.site else "", "day": day, "findings": findings, "processes": procs,
            "prev_ids": {mid for mid, _ in prev_rows if mid}, "prev_titles": list(dict.fromkeys(t for _, t in prev_rows if t))}


def _prompt(ctx: dict, library: list[MaterialLibrary]) -> str:
    lines = "\n".join(f"{m.id}|{m.title}|{','.join(categories_of(m))}" for m in library)
    day = ctx["day"]
    return f"""너는 건설재해예방 기술지도 요원을 돕는다. 이번 기술지도 결과보고서 "11. 제공자료"에 붙일 안전 교육자료를 아래 [자료 목록]에서 고른다.

고르는 기준(앞이 더 중요):
1) 8번 지적사항(이번에 지적한 위험)과 직접 맞는 자료
2) 진행 공정과 공정별 유해위험요인에 맞는 자료
3) 지적사항·공정에 맞는 게 부족할 때만 방문 계절에 맞는 자료
4) 같은 현장 지난 회차에 이미 준 자료는 피한다(정말 딱 맞을 때만 다시)
5) 칸에 넣을 두 자료는 분류가 서로 달라야 한다(같은 주제 두 개 X). 지적사항이 한 가지뿐이면 두 번째는 공정 유해요인(그다음 계절)에서 고른다
재해사례 카드는 지적사항·공정과 같은 종류의 사고일 때만 고른다.

[현장] {ctx['site'] or '-'}
[방문일] {day.isoformat()} — {_season(day.month)}
[8번 지적사항]
{chr(10).join('- ' + f for f in ctx['findings']) or '- (없음)'}
[진행 공정 — 유해위험요인]
{chr(10).join('- ' + p for p in ctx['processes']) or '- (없음)'}
[같은 현장 지난 회차에 준 자료]
{chr(10).join('- ' + t for t in ctx['prev_titles']) or '- (없음)'}

[자료 목록] 번호|이름|분류
{lines}

JSON 하나로만 답한다:
{{"picks": [{{"id": 번호, "reason": "고른 이유 30자 이내"}}], "others": [{{"id": 번호, "reason": "30자 이내"}}]}}
picks = 칸에 넣을 {N_PICKS}개(맞는 게 정말 없으면 1개), others = picks 다음으로 맞는 순서대로 최대 {N_OTHERS}개(picks와 겹치지 않게).
이유는 "지적사항 ○○ 관련"·"○○ 공정 유해요인"처럼 무엇과 맞는지 짧게."""


def _keyword(ctx: dict, library: list[MaterialLibrary]) -> tuple[list[tuple[MaterialLibrary, str]], list[tuple[MaterialLibrary, str]]]:
    """AI를 못 쓸 때 — 지적사항·공정 글의 분류와 자료 분류가 겹치는 순서(지난 회차 자료·흔한 분류는 낮게)."""
    want_f = set(categorize(" ".join(ctx["findings"])))
    want_p = set(categorize(" ".join(ctx["processes"])))
    scored = []
    for m in library:
        cats = set(categories_of(m))
        hit_f, hit_p = (cats & want_f) - _GENERIC, (cats & want_p) - _GENERIC
        score = 3 * len(hit_f) + len(hit_p - hit_f)  # 지적·공정에 같은 분류는 한 번만
        specific = cats - _GENERIC
        if specific:  # 분류가 딱 맞는 자료 먼저(안전모 지적 → "안전모 포스터"가 "크레인·부딪힘"보다)
            score += 0.3 * len(specific & (want_f | want_p)) / len(specific)
        if "재해사례" in cats:  # 같은 점수면 포스터·OPS 먼저
            score -= 0.5
        if score <= 0:
            continue
        if m.id in ctx["prev_ids"]:
            score -= 2
        reason = f"지적사항 {'·'.join(sorted(hit_f))} 관련" if hit_f else f"공정 {'·'.join(sorted(hit_p))} 관련" if hit_p else "관련 사례"
        scored.append((score, m, reason))
    scored.sort(key=lambda x: -x[0])
    picks, used = [], set()
    for _, m, r in scored:  # 칸 두 개는 서로 다른 분류로
        main = next(iter(sorted(set(categories_of(m)) - _GENERIC)), "")
        if main in used and len(scored) > N_PICKS:
            continue
        picks.append((m, r))
        used.add(main)
        if len(picks) == N_PICKS:
            break
    ids = {m.id for m, _ in picks}
    others = [(m, r) for _, m, r in scored if m.id not in ids][:N_OTHERS]
    return picks, others


def recommend(db: Session, company_id: int, report: Report) -> dict:
    """{"source": "ai"|"keyword", "note": 안내, "picks": [{id,title,reason}], "others": [...]}"""
    library = db.query(MaterialLibrary).order_by(MaterialLibrary.id).all()
    by_id = {m.id: m for m in library}
    ctx = context(db, report)
    if not ctx["findings"] and not ctx["processes"]:
        raise ValueError("8번 지적사항이나 진행 공정을 먼저 입력해야 추천할 수 있습니다.")
    source, note = "ai", ""
    try:
        from server.sitok.vision import ask_json

        ans = ask_json(company_id, [], _prompt(ctx, library), max_tokens=2000, effort="low")
        if not isinstance(ans, dict):
            raise ValueError("AI 답 형식이 다릅니다")

        def pick(key: str, limit: int, seen: set) -> list[tuple[MaterialLibrary, str]]:
            out = []
            for it in ans.get(key) or []:
                try:
                    m = by_id.get(int(it.get("id")))
                except (TypeError, ValueError, AttributeError):
                    continue
                if m and m.id not in seen:
                    seen.add(m.id)
                    out.append((m, str(it.get("reason") or "")[:60]))
                if len(out) == limit:
                    break
            return out

        seen: set = set()
        picks = pick("picks", N_PICKS, seen)
        others = pick("others", N_OTHERS, seen)
        if not picks:
            raise ValueError("AI가 고른 자료가 없습니다")
    except Exception as e:  # noqa: BLE001 — 키 없음·네트워크·형식 오류 → 분류로
        source = "keyword"
        note = f"AI를 쓰지 못해 분류로 골랐습니다({str(e)[:80]})."
        picks, others = _keyword(ctx, library)
    item = lambda m, r: {"id": m.id, "title": m.title, "reason": r}  # noqa: E731
    return {"source": source, "note": note, "picks": [item(m, r) for m, r in picks], "others": [item(m, r) for m, r in others]}
