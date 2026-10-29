"""건축물관리점검 — 소항목 하나 AI 분석(2026-10-29 사용자 "부적합을 누르고 사진을 넣으면 변경유형 판단해 체크, 기준면적은 대장·도면에서,
개선사항·방안근거·비고(사진설명)가 자동으로 채워지게").

점검자가 정한 판정(적합/부적합·양호~불량)은 그대로 두고, 비어 있는 것만 사진·대장으로 제안. 점검현황 체크·빈칸(조각 번호 l#t#)·글 네 칸·사진 설명을 JSON으로.
매뉴얼 2.4절 작성 방법(개선방안 의견·근거·비고·설계도서 적합여부)을 규칙으로 줌. 사진은 지적(bad) 먼저 최대 4장, 한 번 약 30~60원."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from server.blcm import building as B
from server.blcm import items as I

RULES = """[작성 규칙 — 건축물 정기점검 매뉴얼(국토교통부 2025.2) 2.4절]
- 점검자가 이미 정한 판정·점수는 바꾸지 마세요. 비어 있는 판정만 사진·건축물 개요로 제안(judge/ratings)하고, 판단 근거가 없으면 비워 두세요.
  판정이 비어 있으면: 지적 사진이 있으면 건수형은 부적합, 점수형은 그 세부 점검을 미흡·불량 쪽으로, 양호 사진만 있으면 적합·양호로 제안.
- "세부항목 점검현황"은 판정과 사진에 맞는 선택지만 체크(status에 "l줄t조각": true)하고, 빈칸은 값을 적으세요("l줄t조각": "73.21").
  기준면적·건폐율·용적률·조경면적 같은 값은 건축물 개요(대장)에 있는 값만 쓰고, 없으면 비워 두세요(지어내지 말 것).
- 개선방안에 대한 의견: 부적합·미흡·불량이면 ilglt(개선사항(위법))에 조사된 현황(어디서·무엇이·얼마나 — 위치·수량·수치, 무엇과 비교해 확인했는지)을,
  perf(성능개선사항)에 필요한 조치(무엇을 어떻게 개선)를 씀 — 아래 [견본]의 길이·구체성만큼(예: 조경 부적합 견본은 위법 칸 130자 안팎, 성능 칸 30~60자).
  판정이 적합·양호면 둘 다 "-".
- basis(개선방안에 대한 근거 및 관련법령 등): 의견을 냈으면 그 사유·근거·관련 조문을 구체적으로(아래 관련법규 안에서), 의견이 없으면 "-".
- rm(비고): 점검 결과를 보고서 문장으로. 부적합·미흡이면 의견(위법 칸)과 같은 취지로 현황까지(견본처럼), 적합·양호면 한 문장(예: "조경면적은 기준면적 이상으로 확보되어
  양호하게 유지되고 있음."). 해당없음·도면없음이면 그 사유를 반드시 — 허가일·사용승인일과 그 기준의 신설·시행일을 견줘서(예: "본 건축물의 허가일(2007.03.30)이
  범죄예방건축기준 시행(2014.11.29) 이전으로 점검대상에 해당되지 않음."), 적용 대상 요건(층수·면적·용도)이 안 되면 그 수치와 요건을 같이.
  ※관련법규 줄은 사이트 양식이 비고 아래에 따로 찍으니 비고에 다시 쓰지 마세요.
- 건축물 개요·[점검자가 덧붙인 내용]에 있는 수치(실측 면적·비율·개수·위치·도면 비교 결과)는 빠뜨리지 말고 문장에 넣으세요 — 견본의 수치는 다른 건물이니 옮기지 말 것.
- "도면과 비교한 결과" 같은 확인 방법은 [사진]에 도면·서류 그림이 있거나 덧붙인 내용에 있을 때만 쓰세요(견본 문구를 그대로 옮기지 말 것 — 없으면 "현장 조사 결과").
- captions: 사진마다 짧은 설명(15자 안팎, 예: "1층 조경식재 현황", "실외기 설치로 식재 훼손") — 사진 차례대로.
- 문장은 보고서체("~임", "~함", "~요구됨"), 근거 없는 수치·법령을 지어내지 마세요."""

PROMPT = """당신은 건축물관리법 정기점검 점검자를 돕는 보조자입니다. 아래 소항목 하나의 보고서 칸을 채우세요.

[소항목] {code} {name} — {big} > {mid} > {small}
[판정 방식] {kind_text}
[세부항목]
{details}
[점검현황 칸 — 조각 번호(l줄t조각)와 지금 값]
{status}
[점검기준(매뉴얼)]
{criteria}
[개선방안 의견 작성 안내(매뉴얼)]
{advice}
[※관련법규] {laws}
{sample}

[건축물 개요(건축물대장)]
{facts}

[점검자가 정한 것]
{inspector}
[사진] {photos}

{rules}
{extra}
아래 JSON 하나로만 답하세요(설명 없이):
{{"judge": "적합|부적합|해당없음 또는 빈 글(건수형만)", "ratings": {{"d0.s0": "양호|보통|미흡|불량|해당없음"}}, "design": "적합|부적합|도면없음|해당없음 또는 빈 글",
 "status": {{"l1t0": true, "l2t1": "값"}}, "ilglt": "…", "perf": "…", "basis": "…", "rm": "…", "captions": ["…"]}}"""


STYLE_CODES = ("3.1.1", "3.5.1")  # 부적합 견본(위법·성능·근거·비고가 다 있는 것) — 같은 항목 견본이 적합이라 의견이 비어도 길이·나눔을 보게


def sample_text(code: str) -> str:
    """[견본] — 같은 항목의 우리 회사 제출 보고서 글(server/blcm/samples.json) + 부적합 견본 둘(10/30 — AI 글이 수기 보고서보다 짧고 덜 구체적이던 것)."""
    sm = I.samples()

    def one(c: str, title: str) -> str:
        v = sm.get(c) or {}
        rows = [f"  · {lab}: {v.get(k)}" for k, lab in I.TEXT_KEYS.items() if (v.get(k) or "").strip() not in ("", "-")]
        if not rows:
            return ""
        caps = [p["caption"] for p in v.get("photos") or [] if p.get("caption")]
        return f"- {title} ({v.get('from', '')} 보고서 {c} {v.get('name', '')})\n" + "\n".join(rows) + (f"\n  · 현황사진 설명: {' / '.join(caps)}" if caps else "")

    parts = [one(code, "같은 항목")]
    if not parts[0] or not any((sm.get(code) or {}).get(k) for k in ("ilglt", "perf")):
        parts += [one(c, "부적합 견본") for c in STYLE_CODES if c != code]
    body = "\n".join(p for p in parts if p)
    return f"[견본 — 우리 회사가 낸 보고서. 다른 건물이니 사실·수치는 옮기지 말고 길이·구체성·말투·칸 나눔만 따를 것]\n{body}\n" if body else ""


def _details(it: dict) -> str:
    rows = []
    for i, d in enumerate(it["details"]):
        head = f"d{i} {d['name']}" + (f" ({d['points']:g}점)" if d.get("points") else f" (최대 {d['count_max']}건)" if d.get("count_max") else "")
        rows.append(head + {"rating": " — 양호/보통/미흡/불량/해당없음", "fit": " — 적합/부적합/해당없음", "count": " — 적합(0건)/부적합(1건 이상)/해당없음",
                            "cert": " — 인증/재인증/만료/해당없음"}.get(d["judge"], ""))
        for k, s in enumerate(d.get("subs") or []):
            rows.append(f"  d{i}.s{k} {s['name']} 배점 {s['points']:g}점")
    return "\n".join(rows) or "-"


def _status_lines(it: dict, res: dict) -> str:
    st = res.get("status") or {}
    rows = []
    for li, ln in enumerate(it.get("status") or []):
        parts = []
        for ti, tok in enumerate(ln):
            key = f"l{li}t{ti}"
            if tok["t"] == "check":
                parts.append(f"[{key} {'■' if st.get(key) is True else '□'} {tok['v']}]")
            elif tok["t"] == "blank":
                parts.append(f"[{key} 빈칸({st.get(key) or ''}){tok.get('unit', '')}]")
            else:
                parts.append(tok["v"])
        rows.append(" ".join(parts))
    return "\n".join(rows) or "(점검현황 칸 없음)"


def _inspector(it: dict, res: dict) -> str:
    ev = I.evaluate(it, res)
    rows = [f"- 해당없음: {'예' if res.get('na') else '아니오'}", f"- 현행기준 비교: {res.get('cmp') or '-'} / 설계도서 적합여부: {res.get('design') or '-'}"]
    if it["kind"] == "count":
        rows.append(f"- 판정: {res.get('judge') or '(비어 있음)'} / 건수: {ev.get('count') if ev.get('count') is not None else '-'}")
    else:
        rt = res.get("ratings") or {}
        rows.append("- 점수 판정: " + (", ".join(f"{k} {v}" for k, v in rt.items()) or "(비어 있음)") + (f" → {ev.get('summary')}" if ev.get("summary") else ""))
    for k, lab in I.TEXT_KEYS.items():
        v = (res.get("texts") or {}).get(k)
        if v:
            rows.append(f"- 지금 {lab}: {v}")
    return "\n".join(rows)


def ask(it: dict, res: dict, building: dict | None, photos: list[tuple[bytes, str, str]], company_id: int, extra: str = "") -> dict:
    """photos = [(jpg, kind good|bad, 지금 설명)]. → {judge, ratings, design, status, texts, captions, made_at, ok}. AI가 안 되면 RuntimeError."""
    from server.sitok import vision

    kind_text = {"count": "건수형 — 변경 유형 체크 건수 0건 = 적합, 1건 이상 = 부적합", "cert": "인증형 — 세부항목마다 인증/재인증/만료/해당없음",
                 "score": "점수형 — 세부 점검마다 양호(1.0)·보통(0.8)·미흡(0.6)·불량(0.4)·해당없음 × 배점, 합계 백분율 90%·70%·50% 초과로 양호·보통·미흡, 그 아래 불량"}[it["kind"]]
    ph = "\n".join(f"- 사진 {i + 1}: {'지적(부적합·결함) 사진' if k == 'bad' else '도면·서류 그림' if k == 'draw' else '양호 사진'}{(' — 지금 설명 ' + c) if c else ''}" for i, (_, k, c) in enumerate(photos)) or "(사진 없음)"
    prompt = PROMPT.format(code=it["code"], name=it["name"], big=it["big"], mid=it["mid"], small=it["small"], kind_text=kind_text, details=_details(it),
                           status=_status_lines(it, res), criteria="\n".join(it.get("criteria") or [])[:5000], advice="\n".join(it.get("advice") or []) or "-",
                           laws=it.get("laws") or "-", sample=sample_text(it["code"]), facts=B.facts(building), inspector=_inspector(it, res), photos=ph, rules=RULES,
                           extra=f"[점검자가 덧붙인 내용 — 반영할 것]\n{extra.strip()}\n" if (extra or "").strip() else "")
    raw = vision.ask_json(company_id, [b for b, _, _ in photos[:4]], prompt, max_tokens=3000, writing=True)
    if not isinstance(raw, dict):
        raise RuntimeError("AI 답을 읽지 못했습니다")
    return normalize(it, raw)


def normalize(it: dict, raw: dict) -> dict:
    """AI 답 → 쓸 수 있는 값만(없는 조각 번호·선택지 밖 값은 버림)."""
    keys = {f"l{li}t{ti}": tok for li, ln in enumerate(it.get("status") or []) for ti, tok in enumerate(ln) if tok["t"] in ("check", "blank")}
    st = {}
    for k, v in (raw.get("status") or {}).items():
        tok = keys.get(str(k))
        if tok is None:
            continue
        if tok["t"] == "check" and v is True:
            st[k] = True
        elif tok["t"] == "blank" and isinstance(v, (str, int, float)) and str(v).strip() and v is not True:
            st[k] = str(v).strip()[:40]
    valid = {f"d{i}.s{k}" for i, d in enumerate(it["details"]) for k in range(len(d.get("subs") or []))} | {f"d{i}" for i, d in enumerate(it["details"]) if not d.get("subs")}
    ratings = {k: v for k, v in (raw.get("ratings") or {}).items() if k in valid and v in I.RATINGS + I.FITS}
    out = {"judge": raw.get("judge") if raw.get("judge") in I.FITS else "", "ratings": ratings,
           "design": raw.get("design") if raw.get("design") in ("적합", "부적합", "도면없음", "해당없음") else "", "status": st,
           "texts": {k: str(raw.get(k) or "").strip()[:1500] for k in I.TEXT_KEYS},
           "captions": [str(x).strip()[:40] for x in (raw.get("captions") or []) if str(x).strip()],
           "made_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "ok": True}
    return out


def merge(res: dict, got: dict) -> dict:
    """AI 결과를 결과에 — 점검자가 정한 판정·점수·체크는 그대로, 빈 것만 채움. 글 칸은 AI 글로(점검자가 고친 글은 화면이 저장 전에 덮을지 물음)."""
    out = dict(res)
    if not out.get("judge") and got.get("judge"):
        out["judge"] = got["judge"]
    rt = dict(out.get("ratings") or {})
    for k, v in (got.get("ratings") or {}).items():
        rt.setdefault(k, v)
    out["ratings"] = rt
    if not out.get("design") and got.get("design"):
        out["design"] = got["design"]
    st = dict(out.get("status") or {})
    for k, v in (got.get("status") or {}).items():
        st.setdefault(k, v)
    out["status"] = st
    out["texts"] = {**(out.get("texts") or {}), **{k: v for k, v in (got.get("texts") or {}).items() if v}}
    caps = got.get("captions") or []
    photos = [dict(p) for p in out.get("photos") or []]
    order = sorted(range(len(photos)), key=lambda i: 0 if photos[i].get("kind") == "bad" else 1)
    for n, i in enumerate(order[:len(caps)]):
        if not photos[i].get("caption"):
            photos[i]["caption"] = caps[n]
    out["photos"] = photos
    out["ai"] = {"made_at": got.get("made_at"), "ok": True}
    return out


def photo_bytes(folder: Path, photos: list[dict]) -> list[tuple[bytes, str, str]]:
    """AI에 줄 사진 — 지적(bad) 먼저, 도면 칸 그림(10/30)은 kind "draw"로(도면과 비교했다고 쓸 수 있게)."""
    out = []
    for p in sorted(photos or [], key=lambda x: 0 if x.get("kind") == "bad" else 2 if x.get("drawing") or x.get("is_draw") else 1):
        f = folder / p["rel"]
        if f.exists():
            out.append((f.read_bytes(), "draw" if p.get("drawing") or p.get("is_draw") else p.get("kind") or "good", p.get("caption") or ""))
    return out


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ---------- 주요 개선방안에 대한 의견·종합의견(10/29 2단계 나머지) ----------
OPINION_PROMPT = """당신은 건축물관리법 정기점검 보고서를 쓰는 점검자입니다. 아래 점검 결과를 바탕으로 "주요 개선방안에 대한 의견" 다섯 칸과 "종합의견"을 쓰세요.

[작성 방법 — 매뉴얼(국토교통부 2025.2) 2.5.4·2.5.5]
- 주요 개선방안에 대한 의견: 3장 점검세부항목별 결과를 근거로 건축물 기능유지(급·배수·냉난방·전기설비·마감 등), 에너지 절감(열손실 방지·단열·친환경),
  화재안전 강화(피난·방화구획·마감재·내화), 구조안전 강화(대지안전·구조부재·내진), 그 밖의 방안(수명 연장 등 — 관리계획·법정 점검 이행 등)을 요약.
  칸마다 2~4문장, 부적합·미흡·보통 항목이 있으면 그 내용과 개선방안을, 없으면 양호하게 유지되고 있으며 지속적인 관리가 필요하다는 취지로.
- 종합의견: 주요 개선방안 의견을 참조해 건축물의 안전 및 성능에 대한 문제점과 최적의 개선방안을 총괄(400~800자). 경과년수, 전반적 상태, 주의할 점, 관리계획 수립 여부를 담음.
- 예시 말투: "본 건축물은 경과년수가 18년 이상되어 설비부분의 노후화가 진행되는 부분이 있으나 지속적인 관리 및 보수로 종합적으로 양호한 상태인 것으로 조사되었으며, …"
- 보고서체("~임", "~함", "~것으로 조사됨", "~필요함"), 점검 결과에 없는 결함·수치·법령을 지어내지 마세요.

[건축물 개요]
{facts}
- 경과년수: {age}

[점검 결과 — 대항목별(판정 / 의견·비고)]
{results}

[총괄표] {recap}
[건축물관리계획 수립 및 이행 적합 여부] {plan}
[그 밖의 항목 이행 여부]
{other}
[지금 적힌 의견]
{current}
{extra}
아래 JSON 하나로만 답하세요(설명 없이):
{{"func": "…", "energy": "…", "fire": "…", "struct": "…", "etc": "…", "total": "…"}}"""


def _age(building: dict | None) -> str:
    import re as _re

    m = _re.match(r"(\d{4})", str((building or {}).get("approval_date") or ""))
    if not m:
        return "(사용승인일 모름)"
    return f"사용승인 {m.group(1)}년 → 약 {datetime.date.today().year - int(m.group(1))}년"


def _results_text(results: dict | None) -> str:
    results = results or {}
    rows, big = [], None
    for it in I.items():
        res = results.get(it["code"]) or {}
        ev = I.evaluate(it, res)
        if it["big_key"] != big:
            big = it["big_key"]
            rows.append(f"■ {I.BIG_LABEL.get(big, big)}")
        if ev["state"] == "empty":
            continue
        judge = "해당없음" if ev["state"] == "na" else (ev.get("summary") or "작성 중")
        tx = res.get("texts") or {}
        notes = [f"{lab}: {tx[k]}" for k, lab in (("ilglt", "개선사항(위법)"), ("perf", "성능개선"), ("rm", "비고")) if (tx.get(k) or "").strip() not in ("", "-")]
        rows.append(f"- {it['code']} {it['name']}({it['mid']}): {judge}" + (" / " + " / ".join(n[:200] for n in notes) if notes else ""))
    return "\n".join(rows)


def opinion(job, company_id: int, extra: str = "") -> dict:
    """주요 개선방안 의견 다섯 칸 + 종합의견 → {func, energy, fire, struct, etc, total, made_at}. 약 50~100원(글만, 사진 없음)."""
    from server.sitok import vision

    op = job.opinion or {}
    recap = ", ".join(f"{r['label']} {r['text'] or '미작성'}" for r in I.recap(job.results))
    plan = op.get("plan") or {}
    plan_text = I.plan_grade(plan) or "미작성"
    bad_plan = [lab for code, lab in I.PLAN_ROWS if plan.get(code) == "부적합"]
    if bad_plan:
        plan_text += " — 부적합: " + ", ".join(bad_plan)
    other = op.get("other") or {}
    other_text = "\n".join(f"- {lab}: {(other.get(code) or {}).get('v') or '미작성'}" + (f" ({other[code]['note']})" if (other.get(code) or {}).get("note") else "")
                           for code, lab, _ in I.OTHER_ROWS)
    cur = op.get("texts") or {}
    current = "\n".join(f"- {lab}: {cur[k]}" for k, lab, _ in I.OPINION_KEYS if (cur.get(k) or "").strip()) or "(없음)"
    prompt = OPINION_PROMPT.format(facts=B.facts(job.building), age=_age(job.building), results=_results_text(job.results)[:12000], recap=recap,
                                   plan=plan_text, other=other_text, current=current,
                                   extra=f"[점검자가 덧붙인 내용 — 반영할 것]\n{extra.strip()}\n" if (extra or "").strip() else "")
    raw = vision.ask_json(company_id, [], prompt, max_tokens=4000, writing=True)
    if not isinstance(raw, dict):
        raise RuntimeError("AI 답을 읽지 못했습니다")
    out = {k: str(raw.get(k) or "").strip()[:2500] for k, _, _ in I.OPINION_KEYS}
    out["made_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return out
