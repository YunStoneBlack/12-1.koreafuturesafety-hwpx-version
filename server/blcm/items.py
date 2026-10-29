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
SAMPLES = Path(__file__).with_name("samples.json")  # 견본(제출한 보고서에서 — server/scripts/make_blcm_samples.py, 10/30)
WEIGHT = {"양호": 1.0, "보통": 0.8, "미흡": 0.6, "불량": 0.4, "적합": 1.0, "부적합": 0.4}
RATINGS = ("양호", "보통", "미흡", "불량", "해당없음")
FITS = ("적합", "부적합", "해당없음")
CERTS = ("인증", "재인증", "만료", "해당없음")
TEXT_KEYS = {"ilglt": "개선사항(위법)", "perf": "성능개선사항", "basis": "개선방안에 대한 근거 및 관련법령 등", "rm": "비고"}
BIG_ORDER = ("법규유지", "기능유지", "에너지및친환경", "구조안전", "화재안전")
BIG_LABEL = {"법규유지": "법규유지", "기능유지": "기능유지", "에너지및친환경": "에너지 및 친환경", "구조안전": "구조안전", "화재안전": "화재안전"}


# 현장에서 찍는 자리(10/30 사용자 "옥상에 가면 조경·피뢰침 … 항목이 순차적이지 않아 위아래를 반복" → 방안1 장소별로 묶고 보고서는 원래 순서).
# 우리프라자 보고서 현황사진 설명으로 정함(예: 급수 = 화장실·주방 급수압 + 급수펌프·저수조). 첫 자리가 주된 곳, 여러 곳이면 탭마다 나옴.
PLACES = (("out", "외부·대지"), ("roof", "옥상"), ("in", "실내"), ("under", "지하·기계·전기실"), ("doc", "서류·면담"))
ITEM_PLACES = {
    "3.1.1": ["out"], "3.1.2": ["roof"], "3.1.3": ["out", "doc"], "3.1.4": ["out"], "3.1.5": ["out"], "3.1.6": ["out", "doc"], "3.1.7": ["out", "doc"],
    "3.1.8": ["out"], "3.1.9": ["out", "doc"], "3.1.10": ["out", "doc"], "3.1.11": ["out", "doc"], "3.1.12": ["out", "in"], "3.1.13": ["out"], "3.1.14": ["out"],
    "3.1.15": ["doc"], "3.1.16": ["doc"], "3.1.17": ["doc"], "3.1.18": ["doc"], "3.1.19": ["doc"], "3.1.20": ["doc"],
    "3.2.1": ["in", "under"], "3.2.2": ["in", "under"], "3.2.3": ["in", "roof"], "3.2.4": ["in", "roof"], "3.2.5": ["in"], "3.2.6": ["roof"], "3.2.7": ["roof", "in"],
    "3.2.8": ["under"], "3.2.9": ["in"], "3.3.1": ["out", "in"], "3.3.2": ["doc"],
    "3.4.1": ["out"], "3.4.2": ["out"], "3.4.3": ["out"], "3.4.4": ["out", "under"], "3.4.5": ["in", "under"], "3.4.6": ["doc"], "3.4.7": ["out"],
    "3.4.8": ["in", "doc"], "3.4.9": ["doc"],
    "3.5.1": ["in"], "3.5.2": ["roof"], "3.5.3": ["doc"], "3.5.4": ["in"], "3.5.5": ["in", "out"], "3.5.6": ["in"], "3.5.7": ["in"], "3.5.8": ["out", "doc"],
    "3.5.9": ["in"], "3.5.10": ["under"],
}


@lru_cache(maxsize=1)
def samples() -> dict:
    """견본 {code: {from, name, ilglt, perf, basis, rm, photos: [{n, file, caption}]}} — 없으면 {}."""
    try:
        return json.loads(SAMPLES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


DRAW_RE = re.compile(r"도면|정면도|배면도|측면도|배치도|평면도|입면도|단면도|대장|확인원")  # 견본 사진 중 현장에서 안 찍는 그림(도면·서류) — 📐 도면 칸으로


def slots(code: str) -> dict:
    """견본 칸(10/30 사용자 "사진 찍을 때 우리프라자 사진을 견본으로, 전회차 느낌") — {"photo": [{n, caption, file}], "draw": [{n, caption, file}]}.
    n = 견본 사진 번호(1부터) — 이번 사진·고른 도면은 photos[].slot = n. 견본이 없으면 둘 다 []."""
    out = {"photo": [], "draw": []}
    for p in (samples().get(code) or {}).get("photos") or []:
        out["draw" if DRAW_RE.search(p.get("caption") or "") else "photo"].append({"n": p["n"], "caption": p.get("caption") or "", "file": p.get("file") or ""})
    return out


def _has(texts: dict, k: str) -> bool:
    return (texts.get(k) or "").strip() not in ("", "-")


def missing(it: dict, res: dict | None) -> list[str]:
    """빠진 것(10/30 사용자 "조사항목이 누락되지 않도록 — 시특법 조사완료처럼") — 판정 없음·일부만, 해당없음 사유, 부적합·미흡인데 지적 사진·개선 의견·근거 없음,
    현황사진 없음(서류·면담만인 항목은 안 봄), 건수형 부적합인데 변경 유형 체크 없음. 다 됐으면 []."""
    res = res or {}
    ev = evaluate(it, res)
    if ev["state"] == "empty":
        return ["판정 없음"]
    out = ["세부 판정 일부만"] if ev["state"] == "part" else []
    tx = res.get("texts") or {}
    if ev["state"] == "na":
        if not _has(tx, "rm"):
            out.append("해당없음 사유(비고) 없음")
        return out
    bad = ev.get("judge") == "부적합" or any(d.get("judge") in ("미흡", "불량", "부적합") for d in ev.get("details") or [])
    photos = res.get("photos") or []
    if bad and not any(p.get("kind") == "bad" for p in photos):
        out.append("부적합·미흡인데 지적 사진 없음")
    elif not photos and ITEM_PLACES.get(it["code"], ["out"]) != ["doc"]:
        out.append("현황사진 없음")
    if bad and not (_has(tx, "ilglt") or _has(tx, "perf")):
        out.append("부적합·미흡인데 개선방안 의견 없음")
    if bad and not _has(tx, "basis"):
        out.append("부적합·미흡인데 개선 근거 없음")
    if it["kind"] == "count" and ev.get("judge") == "부적합" and not res.get("count") and not checked_count(it, res):
        out.append("부적합인데 변경 유형 체크 없음")
    draw = slots(it["code"])["draw"]
    if draw and res.get("design") != "도면없음":
        got = {p.get("slot") for p in photos if p.get("slot") is not None}  # 모음에서 고른 것·현장에서 찍은 것 둘 다(10/30)
        left = [d["caption"] for d in draw if d["n"] not in got]
        if len(left) == len(draw):
            out.append("도면·서류 그림 없음(📐 도면 칸 — 도면이 없으면 설계도서 적합여부 '도면없음')")
    return out


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


# ---------- 총괄표·관리계획·그 밖의 항목·주요 개선방안 의견(10/29 2단계 나머지) ----------
# 총괄표 중항목 14개 — (중항목 이름(띄어쓰기 없이), 표 이름, 생애이력시스템 칸 이름, 건수/등급). 매뉴얼 2.3.2: 대지·높이 및 형태 = 건수 합, 친환경 인증 = 인증·재인증 건수,
# 나머지 = 소항목 점수 합의 백분율로 A(95 이상)·B(85 이상)·C(65 이상)·D(55 이상)·E, 해당없음뿐이면 "-".
RECAP = (("대지", "대지", "recapTablePlat", "count"), ("높이및형태", "높이·형태", "recapTableHeitStle", "count"),
         ("범죄예방", "범죄예방", "recapTableCrmnlPrevnt", "grade"), ("급・배수", "급·배수", "recapTableWspDrng", "grade"),
         ("냉난방・환기", "냉난방·환기", "recapTableCdysmVentl", "grade"), ("전기설비", "전기설비", "recapTableEltl", "grade"),
         ("열손실방지", "열손실 방지", "recapTableHeatLossPrvn", "grade"), ("친환경인증", "친환경 인증", "recapTableAuth", "cert"),
         ("대지안전", "대지안전", "recapTablePlatSafe", "grade"), ("연직하중", "연직하중", "recapTableStaticld", "grade"),
         ("지진하중", "지진하중", "recapTableErthqkld", "grade"), ("피난성능", "피난성능", "recapTableRefgePerf", "grade"),
         ("화재확산", "화재확산", "recapTableFiredff", "grade"), ("내화구조", "내화구조", "recapTableFfPerf", "grade"))

# 건축물관리계획의 수립 및 이행이 적합한지 여부 — 8줄 적합/부적합(사이트 칸 번호 61~68), 하나라도 부적합이면 부적합
PLAN_ROWS = (("61", "건축물 현황"), ("62", "건축주, 설계자, 시공자, 감리자 및 관리자"), ("63", "건축물 마감재 및 건축물에 부착된 제품"), ("64", "장기 수선 계획"),
             ("65", "건축물 화재 및 피난안전"), ("66", "건축물 구조안전 및 내진능력"), ("67", "에너지 및 친환경 성능관리"), ("68", "기타사항"))
# 그 밖의 항목에 대한 이행 여부 — 12줄 예/아니오/기타/해당없음 + 점검·검사 등 일자(사이트 칸 번호 — 수도법이 712, 사이트 화면 차례)
OTHER_ROWS = (("701", "「시설물의 안전 및 유지관리에 관한 특별법」 제11조에 따른 안전점검 이행 여부", "예: 대상 건축물이 아님"),
              ("702", "「화재예방, 소방시설 설치·유지 및 안전관리에 관한 법률」 제25조에 따른 소방시설등의 자체점검 등 이행 여부", "예: 26.02.15 소방점검"),
              ("712", "「수도법」 제33조에 따른 위생상의 조치 이행 여부", "예: 26.05.15 저수조 청소"),
              ("703", "「승강기 안전관리법」 제28조 및 제32조에 따른 승강기 설치검사 및 안전검사 이행 여부", "예: 26.01.22 승강기 점검"),
              ("704", "「에너지이용 합리화법」 제39조에 따른 검사대상기기의 검사 이행 여부", "예: 보일러 미사용"),
              ("705", "「전기안전관리법」 제12조에 따른 일반용전기설비의 점검 이행 여부", "예: 26.08.03 전기점검"),
              ("706", "「하수도법」 제39조에 따른 개인하수처리시설의 운영·관리 이행 여부", "예: 개인하수처리시설 미사용"),
              ("707", "「공동주택관리법」 제33조 및 제34조에 따른 안전점검 및 소규모 공동주택 안전관리 이행 여부", "예: 공동주택이 아님"),
              ("708", "「도시가스사업법」 제17조에 따른 정기검사 및 수시검사 이행 여부", "예: 지역가스업체 개별 위탁점검"),
              ("709", "「도시 및 주거환경정비법」 제12조에 따른 안전진단 이행 여부", "예: 해당 대상이 아님"),
              ("710", "「건축법」 제22조에 따라 사용승인을 신청할 때 제출된 설계도서의 내용대로 유지·관리되는지 여부", ""),
              ("711", "건축물의 안전을 강화하고 에너지 절감을 위하여 보완해야 할 사항이 있는지 여부", ""))
OTHER_VALUES = ("예", "아니오", "기타", "해당없음")
# 주요 개선방안에 대한 의견 다섯 칸 + 종합의견(사이트 칸 bildFuncMtnImprvOpin … gnrlzImprvOpin, 종합의견 2000자 내외)
OPINION_KEYS = (("func", "건축물 기능유지", "bildFuncMtnImprvOpin"), ("energy", "에너지 절감", "energyImprvOpin"), ("fire", "화재안전 강화", "fireSafeImprvOpin"),
                ("struct", "구조안전 강화", "strctSafeImprvOpin"), ("etc", "그 밖의 방안(수명 연장 등)", "etcImprvOpin"), ("total", "종합의견", "gnrlzImprvOpin"))


def grade_of(pct: float) -> str:
    return "A" if pct >= 95 - 1e-9 else "B" if pct >= 85 - 1e-9 else "C" if pct >= 65 - 1e-9 else "D" if pct >= 55 - 1e-9 else "E"


def recap(results: dict | None) -> list[dict]:
    """총괄표 — [{key, label, site, kind, text("1건"·"A"·"-"·""), value}]. 아직 안 쓴 소항목만 있으면 text "" (미작성)."""
    results = results or {}
    by_mid: dict[str, list[tuple[dict, dict]]] = {}
    for it in items():
        by_mid.setdefault(_sq(it["mid"]), []).append((it, evaluate(it, results.get(it["code"]))))
    out = []
    for key, label, site, kind in RECAP:
        evs = by_mid.get(key, [])
        done = [(it, e) for it, e in evs if e["state"] in ("done", "na")]
        live = [(it, e) for it, e in done if e["state"] != "na"]
        text, value = "", None
        if evs and len(done) == len(evs) and not live:
            text = "-"
        elif kind == "count":
            if live:
                value = sum(e.get("count") or 0 for _, e in live)
                text = f"{value}건"
        elif kind == "cert":
            if live:
                value = sum(1 for _, e in live for d in e.get("details") or [] if d.get("judge") in ("인증", "재인증"))
                text = f"{value}건" if value else "-"
        else:
            sc = sum(e["score"] for _, e in live if e.get("score") is not None)
            fl = sum(e["full"] for _, e in live if e.get("full"))
            if fl:
                value = round(100 * sc / fl, 1)
                text = grade_of(value)
        out.append({"key": key, "label": label, "site": site, "kind": kind, "text": text, "value": value,
                    "done": len(done), "total": len(evs)})
    return out


def plan_grade(plan: dict | None) -> str:
    """관리계획 적합 여부 — 하나라도 부적합이면 "부적합", 8줄 다 적합이면 "적합", 아니면 ""."""
    plan = plan or {}
    vals = [plan.get(code) for code, _ in PLAN_ROWS]
    if "부적합" in vals:
        return "부적합"
    return "적합" if all(v == "적합" for v in vals) else ""
