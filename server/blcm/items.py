"""건축물관리점검 항목표 — 매뉴얼(국토교통부 25.02) 3장 소항목 50개(items.json, server/scripts/make_blcm_items.py가 만듦)와 판정 계산.

항목 결과(BlcmJob.results[code]) 모양:
  na: True면 소항목 전체 해당없음
  cmp: 현행기준과의 비교·검토 "개선필요"|"해당없음" · design: 설계도서와의 적합여부 "적합"|"부적합"|"도면없음"|"해당없음"
  judge: 건수형 판정 "적합"|"부적합"|"해당없음"(비면 점검현황 첫 변경유형 줄의 체크 수로) · count: 건수(비면 체크 수)
  ratings: 점수형 {"d0.s1": "양호"|"보통"|"미흡"|"불량"|"해당없음"} (세부가 없는 세부항목은 "d0")
  cert: 인증형 {"d0": "인증"|"재인증"|"만료"|"해당없음"}
  status: 점검현황 {"l3t1": True(체크) | "73.21"(빈칸 글)} — 줄 l·조각 t 번호(items.json status)
  texts: {ilglt 개선사항(위법), perf 성능개선사항, basis 개선방안에 대한 근거 및 관련법령 등, rm 비고}
  photos: [{id, rel, name, kind "good"|"bad", caption}] · ai: {made_at, ok}
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("items.json")
WEIGHT = {"양호": 1.0, "보통": 0.8, "미흡": 0.6, "불량": 0.4, "적합": 1.0, "부적합": 0.4}
RATINGS = ("양호", "보통", "미흡", "불량", "해당없음")
FITS = ("적합", "부적합", "해당없음")
CERTS = ("인증", "재인증", "만료", "해당없음")
TEXT_KEYS = {"ilglt": "개선사항(위법)", "perf": "성능개선사항", "basis": "개선방안에 대한 근거 및 관련법령 등", "rm": "비고"}
BIG_ORDER = ("법규유지", "기능유지", "에너지및친환경", "구조안전", "화재안전")
BIG_LABEL = {"법규유지": "법규유지", "기능유지": "기능유지", "에너지및친환경": "에너지 및 친환경", "구조안전": "구조안전", "화재안전": "화재안전"}


def _sq(s: str) -> str:
    return re.sub(r"\s", "", s or "")


@lru_cache(maxsize=1)
def items() -> list[dict]:
    data = json.loads(FILE.read_text(encoding="utf-8"))
    for it in data:
        it["big_key"] = _sq(it["big"])
    return data


def by_code() -> dict[str, dict]:
    return {it["code"]: it for it in items()}


def public(it: dict) -> dict:
    """화면용 — 원문(raw) 빼고."""
    return {k: v for k, v in it.items() if k != "raw"}


def groups() -> list[dict]:
    """대항목 탭 [{key, label, items: [code]}]."""
    out = {k: [] for k in BIG_ORDER}
    for it in items():
        out.setdefault(it["big_key"], []).append(it["code"])
    return [{"key": k, "label": BIG_LABEL.get(k, k), "items": v} for k, v in out.items() if v]


def change_line(it: dict) -> int | None:
    """건수형의 "변경 유형" 체크 줄 번호 — "◦… 유형" 다음 줄(체크가 있는 첫 줄)."""
    st = it.get("status") or []
    for i, ln in enumerate(st):
        if any(t["t"] == "text" and "유형" in t["v"] for t in ln):
            for j in range(i, min(i + 2, len(st))):
                if any(t["t"] == "check" for t in st[j]):
                    return j
    return next((i for i, ln in enumerate(st) if any(t["t"] == "check" for t in ln)), None)


def checked_count(it: dict, res: dict) -> int:
    ln = change_line(it)
    if ln is None:
        return 0
    st = res.get("status") or {}
    return sum(1 for t, tok in enumerate(it["status"][ln]) if tok["t"] == "check" and st.get(f"l{ln}t{t}") is True)


def _ratio_judge(score: float, full: float) -> str:
    r = score / full if full else 0
    return "양호" if r > 0.9 + 1e-9 else "보통" if r > 0.7 + 1e-9 else "미흡" if r > 0.5 + 1e-9 else "불량"


def evaluate(it: dict, res: dict | None) -> dict:
    """판정 — {state: "empty"|"done"|"na", judge(건수형 적합/부적합/해당없음), count, details: [{name, judge, score, full}], score, full, summary}."""
    res = res or {}
    if res.get("na"):
        return {"state": "na", "judge": "해당없음", "summary": "해당없음", "details": [], "score": None, "full": None, "count": None}
    if it["kind"] == "count":
        cnt = res.get("count")
        cnt = checked_count(it, res) if cnt in (None, "") else int(cnt)
        j = res.get("judge") or ("" if not res.get("status") and not res.get("photos") else ("적합" if cnt == 0 else "부적합"))
        if j == "해당없음":
            return {"state": "na", "judge": "해당없음", "summary": "해당없음", "details": [], "score": None, "full": None, "count": None}
        return {"state": "done" if j else "empty", "judge": j, "count": cnt if j else None, "summary": f"{j} ({cnt}건)" if j else "", "details": [], "score": None, "full": None}
    if it["kind"] == "cert":
        cert = res.get("cert") or {}
        ds = [{"name": d["name"], "judge": cert.get(f"d{i}") or ""} for i, d in enumerate(it["details"])]
        done = any(x["judge"] for x in ds)
        return {"state": "done" if done else "empty", "judge": "", "details": ds, "summary": " · ".join(f"{x['name'][:10]} {x['judge']}" for x in ds if x["judge"]),
                "score": None, "full": None, "count": None}
    rt = res.get("ratings") or {}
    ds, tot, full, any_set = [], 0.0, 0.0, False
    for i, d in enumerate(it["details"]):
        subs = d.get("subs") or []
        parts = [(f"d{i}.s{k}", s["points"]) for k, s in enumerate(subs)] if subs else [(f"d{i}", d["points"] or 0)]
        sc, fl, seen = 0.0, 0.0, False
        for key, pts in parts:
            v = rt.get(key)
            if not v:
                continue
            seen = any_set = True
            if v == "해당없음":
                continue
            sc += (pts or 0) * WEIGHT.get(v, 0)
            fl += pts or 0
        if not seen:
            ds.append({"name": d["name"], "judge": "", "score": None, "full": d["points"]})
            continue
        if fl == 0:
            ds.append({"name": d["name"], "judge": "해당없음", "score": None, "full": d["points"]})
            continue
        j = ("적합" if sc >= fl - 1e-9 else "부적합") if d["judge"] == "fit" else _ratio_judge(sc, fl)
        ds.append({"name": d["name"], "judge": j, "score": round(sc, 2), "full": fl})
        tot += sc
        full += fl
    state = "done" if any_set and all(x["judge"] for x in ds) else ("part" if any_set else "empty")
    return {"state": state, "judge": "", "details": ds, "score": round(tot, 2) if full else None, "full": full or None, "count": None,
            "summary": " · ".join(f"{x['judge']}" + (f" {x['score']:g}/{x['full']:g}점" if x.get("score") is not None else "") for x in ds if x["judge"])}


def status_text(it: dict, res: dict) -> str:
    """점검현황을 글로(AI 물음·보고서용) — "□ 실외기 ■ 식재 훼손 …", 빈칸은 적은 값."""
    st = res.get("status") or {}
    lines = []
    for li, ln in enumerate(it.get("status") or []):
        parts = []
        for ti, tok in enumerate(ln):
            key = f"l{li}t{ti}"
            if tok["t"] == "check":
                parts.append(("■ " if st.get(key) is True else "□ ") + tok["v"])
            elif tok["t"] == "blank":
                parts.append(f"( {st.get(key) or ''} ){tok.get('unit', '')}")
            else:
                parts.append(tok["v"])
        lines.append(" ".join(parts))
    return "\n".join(lines)
