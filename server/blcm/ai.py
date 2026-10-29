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
- "세부항목 점검현황"은 판정과 사진에 맞는 선택지만 체크(status에 "l줄t조각": true)하고, 빈칸은 값을 적으세요("l줄t조각": "73.21").
  기준면적·건폐율·용적률·조경면적 같은 값은 건축물 개요(대장)에 있는 값만 쓰고, 없으면 비워 두세요(지어내지 말 것).
- 개선방안에 대한 의견: 위법(사용승인 당시 기준에 부적합·사용승인 후 무단 변경)이면 ilglt(개선사항(위법))에, 적법하나 노후·성능 저하로 개선이 필요하면 perf(성능개선사항)에
  짧게(한두 문장) 쓰고, 없으면 "-". 판정이 적합·양호면 둘 다 "-".
- basis(개선방안에 대한 근거 및 관련법령 등): 의견을 냈으면 그 사유·근거·관련 조문을 구체적으로(아래 관련법규 안에서), 의견이 없으면 "-".
- rm(비고): 점검 결과를 보고서 문장으로 한두 문장(예: "조경면적은 기준면적 이상으로 확보되어 양호하게 유지되고 있음."). 해당없음·도면없음이면 그 사유(적용 대상이 아님·
  사용승인 시점 기준 미적용·육안 점검 불가 등)를 반드시.
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
    ph = "\n".join(f"- 사진 {i + 1}: {'지적(부적합·결함)' if k == 'bad' else '양호'} 사진{(' — 지금 설명 ' + c) if c else ''}" for i, (_, k, c) in enumerate(photos)) or "(사진 없음)"
    prompt = PROMPT.format(code=it["code"], name=it["name"], big=it["big"], mid=it["mid"], small=it["small"], kind_text=kind_text, details=_details(it),
                           status=_status_lines(it, res), criteria="\n".join(it.get("criteria") or [])[:5000], advice="\n".join(it.get("advice") or []) or "-",
                           laws=it.get("laws") or "-", facts=B.facts(building), inspector=_inspector(it, res), photos=ph, rules=RULES,
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
    """AI에 줄 사진 — 지적(bad) 먼저."""
    out = []
    for p in sorted(photos or [], key=lambda x: 0 if x.get("kind") == "bad" else 1):
        f = folder / p["rel"]
        if f.exists():
            out.append((f.read_bytes(), p.get("kind") or "good", p.get("caption") or ""))
    return out


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
