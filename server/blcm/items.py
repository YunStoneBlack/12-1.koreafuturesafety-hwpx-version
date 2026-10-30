"""건축물관리점검 항목표 — 매뉴얼(국토교통부 25.02) 3장 소항목 50개(items.json, server/scripts/make_blcm_items.py가 만듦)와 판정 계산.

항목 결과(BlcmJob.results[code]) 모양:
  na: True면 소항목 전체 해당없음
  cmp: 현행기준과의 비교·검토 "개선필요"|"해당없음" · design: 설계도서와의 적합여부 "적합"|"부적합"|"도면없음"|"해당없음"
  judge: 건수형 판정 "적합"|"부적합"|"해당없음"(비면 점검현황 첫 변경유형 줄의 체크 수로) · count: 건수(비면 체크 수)
  ratings: 점수형 {"d0.s1": "양호"|"보통"|"미흡"|"불량"|"해당없음"} (세부가 없는 세부항목은 "d0")
  cert: 인증형 {"d0": "인증"|"재인증"|"만료"|"해당없음"}
  status: 점검현황 {"l3t1": True(체크) | "73.21"(빈칸 글)} — 줄 l·조각 t 번호(items.json status)
  texts: {ilglt 개선사항(위법), perf 성능개선사항, basis 개선방안에 대한 근거 및 관련법령 등, rm 비고}
  photos: [{id, rel, name, kind "good"|"bad", caption, slot(견본 칸), bad{key, label}(부적합 칸 — bad_types), drawing·is_draw(도면)}] · ai: {made_at, ok}
  auto: 사진으로 자동으로 넣은 값 {status: [키], ratings: {키: 값}} — apply_photos가 다시 계산할 때 그대로인 것만 바꿈(10/30)
        + 규칙으로 넣은 값 {rules: [작은 점검 키], judge: 체크로 정한 부적합, design: 판정으로 채운 설계도서 적합여부}(normalize, 10/30)
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
ITEM_PLACES = {  # 10/30 민재형 "사진을 어디서 찍어야 하는지가 포인트 — 내용이랑 사진을 분석해서 재구성" — 민재형 메모 + 회사 제출 보고서 18건 현황사진 설명 약 2,800개(장소 낱말)
    "3.1.1": ["out"], "3.1.2": ["roof"], "3.1.3": ["out"], "3.1.4": ["out"], "3.1.5": ["out"], "3.1.6": ["out"],
    "3.1.7": ["out", "roof"],  # 수직증축 확인 = 옥상 전경
    "3.1.8": ["out"], "3.1.9": ["out"], "3.1.10": ["out"], "3.1.11": ["out"],  # 3.1.3~3.1.20 서류·면담 → 외부·대지(민재형)
    "3.1.12": ["out", "in"], "3.1.13": ["out"], "3.1.14": ["out"], "3.1.15": ["out", "in"],  # 조명 — 진입로·보행로 + 내부 통로
    "3.1.16": ["out", "in", "under"],  # 아파트 — 단지 출입구·세대 방범·지하주차장 CCTV·조명
    "3.1.17": ["out", "in"], "3.1.18": ["out", "in"], "3.1.19": ["in", "out"], "3.1.20": ["out", "in"],
    "3.2.1": ["in", "under"], "3.2.2": ["in", "under"],  # 급수·배수 — 화장실·주방 + 펌프·저수조(민재형)
    "3.2.3": ["in", "out", "roof", "under"], "3.2.4": ["in", "out", "roof", "under"],  # 냉난방 — 실내기·실외기(외부·옥상, 민재형) + 기계실 냉동기·보일러·히트펌프(사진)
    "3.2.5": ["in", "under", "out", "roof"],  # 환기 — 실내·지하·외부(민재형) + 옥상 환기설비·벤틸레이터(사진)
    "3.2.6": ["roof"], "3.2.7": ["in"],  # 방송수신 옥상 → 실내(민재형)
    "3.2.8": ["under"], "3.2.9": ["in"], "3.3.1": ["out", "in"], "3.3.2": ["doc"],
    "3.4.1": ["out"], "3.4.2": ["out"], "3.4.3": ["out"], "3.4.4": ["out", "under"], "3.4.5": ["in", "under"], "3.4.6": ["doc"], "3.4.7": ["out"],
    "3.4.8": ["out", "roof"],  # 무단 증축(옥상 경량철골 등)·외형 변경 — 외부·옥상(민재형)
    "3.4.9": ["doc"],
    "3.5.1": ["in", "out"],  # 옥외 피난계단
    "3.5.2": ["roof"], "3.5.3": ["doc"], "3.5.4": ["in", "under"], "3.5.5": ["in", "out"], "3.5.6": ["in", "under"], "3.5.7": ["in", "under"],  # 방화구획·배연·내화 — 지하·실내(민재형)
    "3.5.8": ["out", "doc"], "3.5.9": ["in"], "3.5.10": ["under"],
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
        out["draw" if DRAW_RE.search(p.get("caption") or "") else "photo"].append({"n": p["n"], "caption": p.get("caption") or "", "file": p.get("file") or "",
                                                                               "from": p.get("from") or ""})  # 다른 회사 보고서에서 온 견본(10/30) — 어느 건물인지
    return out


def slot(code: str, n: int | None) -> dict | None:
    """견본 칸 n 하나 — slots()의 칸 + draw(도면·서류 칸이면 True), 없으면 None."""
    if n is None:
        return None
    s = slots(code)
    return next(({**x, "draw": k == "draw"} for k in ("photo", "draw") for x in s[k] if x["n"] == n), None)


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
    rt = res.get("ratings") or {}
    need = [k for k, rule in (AUTO_RULES.get(it["code"]) or {}).items() if not rt.get(k) and rule_allow(it, res, rule)[0] == []]
    if need and not res.get("na"):
        out.append(f"점검현황 고르기 — {_sub_name(it, need[0])[:16]}" + (f" 외 {len(need) - 1}" if len(need) > 1 else "") + "(고르면 판정 자동)")
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
            out.append("도면 없음(② 관리사무소 — 도면에서 넣기 · 도면이 없으면 설계도서 적합여부 '도면없음')")
    return out


def _sub_name(it: dict, key: str) -> str:
    """작은 점검 키 "d0.s1" → 이름."""
    m = re.fullmatch(r"d(\d+)(?:\.s(\d+))?", key)
    try:
        d = it["details"][int(m[1])]
        return d["subs"][int(m[2])]["name"] if m[2] is not None else _short(d["name"])
    except (TypeError, IndexError, KeyError):
        return key


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
    """화면용 — 원문(raw) 빼고. radios = 하나만 고르는 점검현황 칸 묶음, rules = 점검현황으로 정해지는 작은 점검 {키: 종류}(10/30)."""
    return {**{k: v for k, v in it.items() if k != "raw"}, "radios": RADIOS.get(it["code"]) or [],
            "rules": {k: r["how"] for k, r in (AUTO_RULES.get(it["code"]) or {}).items()}}


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


def _short(name: str) -> str:
    return re.sub(r"\s*(의\s*)?(성능\s*)?(상태\s*)?유지\s*여부.*$|\s*\(.*$", "", name).strip() or name


def bad_file() -> Path:
    """부적합 견본 고른 것(회사 공통, 화면 [🖼 부적합 견본 고르기]) — 저장소 _건축물관리점검/_참고사진/bad.json {code: {칸 key: [{file, caption, from, ok, by, at}]}}."""
    from core.db import DATA_DIR

    return DATA_DIR / "_건축물관리점검" / "_참고사진" / "bad.json"


@lru_cache(maxsize=4)
def _bad_read(path: str, mtime: int) -> dict:  # noqa: ARG001 — mtime은 캐시 열쇠
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bad_samples() -> dict:
    f = bad_file()
    try:
        return _bad_read(str(f), f.stat().st_mtime_ns)
    except OSError:
        return {}


def bad_types(it: dict) -> list[dict]:
    """부적합 칸(10/30 사용자 "적합 견본 / 부적합 실외기·간이 시설물·쓰레기 분리시설 … 견본 — 부적합 칸에 사진을 넣으면 판정 자동") —
    건수형 = "변경 유형" 체크 줄의 체크마다(key "st:l1t0"), 점수형 = 작은 점검마다(key "rt:d0.s1", 작은 점검이 없으면 "rt:d0"), 인증형 = 없음.
    [{key, label, fit(적합/부적합으로 매기는 칸), samples: [{file, caption, from}](samples.json bad[key] — 회사 보고서 부적합 사진)}]."""
    bad = {**((samples().get(it["code"]) or {}).get("bad") or {}), **(bad_samples().get(it["code"]) or {})}
    out: list[dict] = []
    if it["kind"] == "count":
        ln = change_line(it)
        if ln is not None:
            out = [{"key": f"st:l{ln}t{t}", "label": tok["v"], "fit": False} for t, tok in enumerate(it["status"][ln]) if tok["t"] == "check"]
    elif any(r["how"] == "count" for r in (AUTO_RULES.get(it["code"]) or {}).values()):  # 범죄예방 세부기준·청문점검 — 체크 수가 판정(10/30)
        out = [{"key": f"st:l{li}t{ti}", "label": re.sub(r"\s*\(가중치\s*\d+\)", "", tok["v"]), "fit": False}
               for li, ln in enumerate(it.get("status") or []) for ti, tok in enumerate(ln) if tok["t"] == "check"]
    elif it["kind"] != "cert":
        names = [s["name"] for d in it["details"] for s in d.get("subs") or []]
        for i, d in enumerate(it["details"]):
            subs = d.get("subs") or []
            if not subs:
                out.append({"key": f"rt:d{i}", "label": _short(d["name"]), "fit": d.get("judge") == "fit"})
            for k, s in enumerate(subs):
                lab = s["name"] if names.count(s["name"]) == 1 else f"{_short(d['name'])} — {s['name']}"
                out.append({"key": f"rt:d{i}.s{k}", "label": lab, "fit": s.get("judge") == "fit"})
    return [{**x, "samples": bad.get(x["key"]) or []} for x in out]


def apply_photos(it: dict, res: dict) -> dict:
    """사진 → 판정(10/30 사용자 "지적 사진을 넣어도 적합으로 표시됨 — 판단 근거를 모르겠음"): 부적합 칸 사진(photos[].bad.key)이 있으면
    체크 칸(st:)은 그 변경·부적합 유형 체크(건수형은 판정·건수를 점검자가 '적합'·0으로 두었으면 비움 → 체크 수로 부적합), 작은 점검 칸(rt:)은 미흡(적합/부적합 칸이면 부적합)
    — 점검자가 불량으로 올려 둔 것은 그대로. 현장 사진이 있는데 판정이 빈 작은 점검은 양호(적합).
    개수로 정해지는 작은 점검(AUTO_RULES pick, 10/30)은 판정 대신 점검현황 선택지를 올림 — 부적합 사진이면 "0개"·빈 것 → 둘째 선택지("1~2개"), 사진만 있고 비면 "0개".
    숫자·체크 수로 정해지는 것(num·cycle·count)은 사진으로 안 정함(count는 체크가 없으면 양호). 전에 자동으로 넣은 값(auto)이 그대로면 지우고 다시 — 점검자가 바꾼 값은 남음."""
    r = dict(res or {})
    if r.get("na") or it["kind"] == "cert":
        return r
    photos = [p for p in r.get("photos") or [] if not p.get("is_draw") and not p.get("drawing") and not p.get("evidence")]
    bad_keys = {(p.get("bad") or {}).get("key") for p in photos if p.get("kind") == "bad"} - {None}
    prev = r.get("auto") or {}
    st = dict(r.get("status") or {})
    for k in prev.get("status") or []:
        if st.get(k) is True:
            st.pop(k)
    rt = dict(r.get("ratings") or {})
    for k, v in (prev.get("ratings") or {}).items():
        if rt.get(k) == v:
            rt.pop(k)
    new_st: list[str] = []
    new_rt: dict[str, str] = {}

    def put(k: str) -> None:
        if st.get(k) is not True:
            st[k] = True
            new_st.append(k)

    for key in sorted(bad_keys):
        if key.startswith("st:"):
            put(key[3:])
    if it["kind"] == "count":
        if bad_keys:
            if r.get("judge") == "적합":
                r["judge"] = ""
            if r.get("count") in (0, "0"):
                r["count"] = None
    else:
        rules = AUTO_RULES.get(it["code"]) or {}
        subs = [t for t in bad_types(it) if t["key"].startswith("rt:")]
        if not subs:  # 체크 칸만인 소항목(범죄예방 세부기준 등) — 작은 점검 키는 규칙에서
            subs = [{"key": f"rt:{k}", "fit": False} for k in rules]
        ruled = set(prev.get("rules") or [])  # 규칙이 넣은 판정은 점검현황을 다시 정할 때 빈 것으로 봄
        for t in subs:
            k, cur = t["key"][3:], rt.get(t["key"][3:])
            rule = rules.get(k)
            if rule and k in ruled and cur != "해당없음":
                cur = None
            if rule and rule["how"] == "pick":
                keys = rule["keys"]
                on = next((n for n, x in enumerate(keys) if st.get(x) is True), None)
                if t["key"] in bad_keys and cur != "해당없음" and (on is None or on == 0):
                    if on == 0:
                        st.pop(keys[0])
                    put(keys[1])
                elif photos and on is None and not cur and re.match(r"^0", _label(it, keys[0])):
                    put(keys[0])
                continue
            if rule:
                if rule["how"] == "count" and photos and not cur and rule_count(it, {"status": st}) == 0:
                    rt[k] = new_rt[k] = LADDER[0]
                continue
            if t["key"] in bad_keys:
                want = "부적합" if t["fit"] else "미흡"
                if cur in (None, "", "양호", "보통", "적합"):
                    rt[k] = new_rt[k] = want
            elif photos and not cur:
                rt[k] = new_rt[k] = "적합" if t["fit"] else "양호"
        r["ratings"] = rt
    r["status"] = st
    r["auto"] = {**prev, "status": new_st, "ratings": new_rt}
    return r


def _ratio_judge(score: float, full: float) -> str:
    r = score / full if full else 0
    return "양호" if r > 0.9 + 1e-9 else "보통" if r > 0.7 + 1e-9 else "미흡" if r > 0.5 + 1e-9 else "불량"


def evaluate(it: dict, res: dict | None) -> dict:
    """판정 — {state: "empty"|"done"|"na", judge(건수형 적합/부적합/해당없음), count, details: [{name, judge, score, full}], score, full, summary}."""
    res = res or {}
    if res.get("na"):
        return {"state": "na", "judge": "해당없음", "summary": "해당없음", "details": [], "score": None, "full": None, "count": None}
    if it["kind"] == "count":
        cnt = _count_state(it, res)[0]
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


# ---------- 개수·숫자로 정해지는 판정(10/30 사용자 "방화구획 0개면 양호 — 개수에 따라 양호·보통·미흡·불량으로 정해지는 것은 손으로 못 바꾸게,
# 사이트도 기준에서 벗어나면 클릭 자체가 안 됨 — 세부항목 점검기준대로 자동으로 점수가 매겨져야 시스템에 올릴 때 오류가 안 남") ----------
# 사이트(10/29 연습 때 저장한 상세 창 47개 칸·화면 코드, 핵심기술 50절): 세부항목 점검판단결과는 작은 점검 점수 합으로 자동(잠김), 건수형 판정·범죄예방 세부기준·
# 이상징후 청문점검은 건수 고르기로 자동(잠김), 설계도서 적합여부는 판정과 맞는 쪽 + 도면없음만(fn_set_required4). 작은 점검은 사이트도 손으로 고르지만
# 우리는 매뉴얼 점검기준이 개수·거리·숫자인 것을 점검현황에서 정함(사이트보다 한 단계 더 잠금 — 보고서 앞뒤가 맞게).
LADDER = ("양호", "보통", "미흡", "불량")
GOOD_J = ("적합", "양호", "보통", "인증", "재인증")  # 사이트 fn_set_required4 — 이 판정이 하나라도 있으면 설계도서 "적합"
BAD_J = ("부적합", "미흡", "불량", "만료")  # → "부적합", "해당없음"이 있으면 → "해당없음", "도면없음"은 늘
# 하나만 고르는 점검현황 칸(사이트 라디오 — 상세 창 47개 라벨로 맞춤, 10/30). 키 = l{줄}t{조각}
RADIOS = {
    "3.1.12": [["l3t0", "l3t1"]], "3.2.1": [["l3t1", "l3t5"], ["l4t1", "l4t5"]], "3.2.2": [["l1t1", "l1t2", "l1t3"]],
    "3.2.3": [["l2t1", "l2t2", "l2t3"]], "3.2.4": [["l2t1", "l2t2", "l2t3"]], "3.2.6": [["l1t1", "l1t2", "l1t3"]], "3.2.7": [["l1t1", "l1t2", "l1t3"]],
    "3.2.8": [["l1t1", "l1t2", "l1t3"]], "3.2.9": [["l1t1", "l1t2", "l1t3"]],
    "3.3.1": [["l0t1", "l0t2", "l0t3", "l0t4"], ["l1t1", "l1t2", "l1t3", "l1t4"]],
    "3.3.2": [["l1t1", "l1t2", "l1t3", "l1t4", "l1t5"], ["l3t1", "l3t2", "l3t3", "l3t4", "l3t5", "l3t6", "l3t7", "l3t8", "l4t0", "l4t1"],
              ["l6t1", "l6t2", "l6t3", "l6t4", "l6t5"], ["l8t1", "l8t2", "l8t3", "l8t4"]],
    "3.4.3": [["l0t1", "l0t2"]], "3.4.4": [["l1t1", "l1t2"], ["l2t1", "l2t2"]], "3.4.8": [["l3t1", "l3t2", "l3t3"], ["l5t1", "l5t2", "l5t3"], ["l8t1", "l8t2", "l8t3"]],
    "3.4.9": [["l0t1", "l0t2"], ["l3t1", "l3t2", "l3t3"]],
    "3.5.1": [["l0t1", "l0t2", "l0t3", "l0t4"], ["l1t1", "l1t2", "l1t3", "l1t4"], ["l2t1", "l2t2", "l2t3", "l2t4"], ["l4t1", "l4t2", "l4t3", "l4t4"],
              ["l5t1", "l5t2", "l5t3", "l5t4"]],
    "3.5.2": [["l1t0", "l1t1", "l1t2"], ["l4t0", "l4t1", "l4t2", "l4t3"], ["l5t1", "l5t2", "l5t3", "l5t4"]],
    "3.5.3": [["l1t0", "l1t1", "l1t2"], ["l3t1", "l3t2", "l3t3"]],
    "3.5.4": [["l3t0", "l3t1", "l3t2", "l3t3"], ["l6t0", "l6t1", "l6t2", "l6t3"], ["l8t0", "l8t1", "l8t2", "l8t3"], ["l11t0", "l11t1", "l11t2", "l11t3"]],
    "3.5.5": [["l3t0", "l3t1"], ["l6t1", "l6t2"], ["l8t1", "l8t2"]], "3.5.6": [["l1t0", "l1t1", "l1t2", "l2t0"], ["l4t0", "l4t1", "l4t2", "l5t0"]],
    "3.5.7": [["l0t1", "l0t2", "l0t3", "l0t4"]], "3.5.9": [["l1t0", "l1t1"], ["l3t0", "l3t1"], ["l5t0", "l5t1"], ["l7t0", "l7t1"]],
    "3.5.10": [["l1t0", "l1t1", "l1t2", "l1t3"]],
}
_STEP_H = (("<=", 12, ("양호",)), ("<=", 20, ("보통",)))  # 급수압 2리터 급수시간(초) — 20초 넘으면 미흡·불량(성능 저하 정도로 고름)
# 작은 점검 판정 규칙 {소항목: {작은 점검 키: 규칙}} — 매뉴얼 점검기준(25.02):
#   pick  — 점검현황 선택지(keys) 차례대로 양호·보통·미흡·불량(0개·1~2개·3~4개·5개 이상, 10m 미만·10~30m·30~50m·50m 초과 …)
#   count — 점검현황 체크 수(라벨 "가중치 N"이면 N씩) → bands[(최소, 최대)] 차례대로 양호·보통·미흡·불량(3.1.19 2건은 미흡·불량 둘 — 사이트도 "2건(미흡)·2건(불량)")
#   num   — 빈칸 숫자 → steps[(">=" | "<=", 기준, 판정들)] 처음 맞는 것, 없으면 rest(판정이 둘이면 그 안에서 고름). manual = 이 주용도면 손으로(매뉴얼 다른 기준)
#   cycle — 예/아니오 + 주기(개월): 예이고 주기 ≤ max면 ok, 아니오이거나 주기 > max면 ng
AUTO_RULES = {
    "3.1.16": {"d0.s0": {"how": "count", "bands": ((0, 3), (4, 7), (8, 11), (12, 99))}},
    "3.1.17": {"d0.s0": {"how": "count", "bands": ((0, 1), (2, 3), (4, 5), (6, 99))}},
    "3.1.18": {"d0.s0": {"how": "count", "bands": ((0, 0), (1, 2), (3, 3), (4, 99))}},
    "3.1.19": {"d0.s0": {"how": "count", "bands": ((0, 0), (1, 1), (2, 2), (2, 99))}},
    "3.1.20": {"d0.s0": {"how": "count", "bands": ((0, 0), (1, 1), (2, 2), (3, 99))}},
    "3.2.1": {"d0.s0": {"how": "num", "key": "l0t1", "unit": "초", "steps": _STEP_H, "rest": ("미흡", "불량")},
              "d0.s1": {"how": "num", "key": "l1t1", "unit": "초", "steps": _STEP_H, "rest": ("미흡", "불량")},
              "d1.s0": {"how": "cycle", "yes": "l3t1", "no": "l3t5", "num": "l3t3", "max": 6, "ok": ("양호", "보통"), "ng": ("미흡", "불량")}},
    "3.4.6": {"d0": {"how": "count", "bands": ((0, 0), (1, 1), (2, 2), (3, 99))}},
    "3.5.1": {"d0.s0": {"how": "pick", "keys": ["l0t1", "l0t2", "l0t3", "l0t4"]}, "d0.s1": {"how": "pick", "keys": ["l1t1", "l1t2", "l1t3", "l1t4"]},
              "d1.s1": {"how": "pick", "keys": ["l2t1", "l2t2", "l2t3", "l2t4"]},  # d1.s0 계단출입문 닫힘 상태 = 글 기준이라 손으로
              "d2.s0": {"how": "pick", "keys": ["l4t1", "l4t2", "l4t3", "l4t4"]}, "d2.s1": {"how": "pick", "keys": ["l5t1", "l5t2", "l5t3", "l5t4"]}},
    "3.5.2": {"d0.s2": {"how": "pick", "keys": ["l4t0", "l4t1", "l4t2", "l4t3"]}},  # 면적 유지·난간 = 글 기준
    "3.5.4": {"d0.s0": {"how": "pick", "keys": ["l3t0", "l3t1", "l3t2", "l3t3"]}, "d0.s1": {"how": "pick", "keys": ["l6t0", "l6t1", "l6t2", "l6t3"]},
              "d1.s0": {"how": "pick", "keys": ["l8t0", "l8t1", "l8t2", "l8t3"]}, "d1.s1": {"how": "pick", "keys": ["l11t0", "l11t1", "l11t2", "l11t3"]}},
    "3.5.6": {"d0.s0": {"how": "pick", "keys": ["l1t0", "l1t1", "l1t2", "l2t0"]}, "d1.s0": {"how": "pick", "keys": ["l4t0", "l4t1", "l4t2", "l5t0"]},
              "d2.s0": {"how": "num", "key": "l6t1", "unit": "m", "steps": ((">=", 2.4, ("양호",)), (">=", 2.1, ("보통",)), (">=", 2.0, ("미흡",))), "rest": ("불량",),
                        "manual": r"문화\s*및\s*집회|종교|장례|위락"}},  # (2-1) 관람실·집회실 200㎡ 이상은 4.5m 기준·기계환기 — 손으로
    "3.5.7": {"d0.s0": {"how": "pick", "keys": ["l0t1", "l0t2", "l0t3", "l0t4"]}},  # 내화피복재 탈락 0개·1~5개·6~10개·10개 초과
    "3.5.10": {"d1.s0": {"how": "pick", "keys": ["l1t0", "l1t1", "l1t2", "l1t3"]}},  # 지하층 구획 = 글 기준
}


def _label(it: dict, key: str) -> str:
    m = re.fullmatch(r"l(\d+)t(\d+)", key or "")
    try:
        return it["status"][int(m[1])][int(m[2])].get("v", "") if m else ""
    except (IndexError, KeyError):
        return ""


def _num(v) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", "" if v is True or v is None else str(v))
    return float(m.group()) if m else None


def rule_count(it: dict, res: dict) -> int:
    """점검현황 체크 수 — 라벨에 "가중치 N"이면 N씩(이상징후 청문점검)."""
    st = res.get("status") or {}
    n = 0
    for li, ln in enumerate(it.get("status") or []):
        for ti, tok in enumerate(ln):
            if tok["t"] == "check" and st.get(f"l{li}t{ti}") is True:
                m = re.search(r"가중치\s*(\d+)", tok["v"])
                n += int(m.group(1)) if m else 1
    return n


def _rule_keys(it: dict, rule: dict) -> list[str]:
    """규칙이 보는 점검현황 칸."""
    if rule["how"] == "count":
        return [f"l{li}t{ti}" for li, ln in enumerate(it.get("status") or []) for ti, tok in enumerate(ln) if tok["t"] == "check"]
    return list(rule.get("keys") or []) + [rule[k] for k in ("key", "yes", "no", "num") if rule.get(k)]


def rule_allow(it: dict, res: dict, rule: dict, use: str = "") -> tuple[list[str] | None, str, bool]:
    """규칙 하나 → (고를 수 있는 판정, 까닭, 점검현황에 값이 있는지). 판정이 []면 점검현황을 먼저, None이면 이 건물은 손으로."""
    st = res.get("status") or {}
    how = rule["how"]
    if how == "pick":
        i = next((n for n, k in enumerate(rule["keys"]) if st.get(k) is True), None)
        if i is None:
            return [], "점검현황에서 고르면 자동", False
        return [LADDER[i]], f"점검현황 {_label(it, rule['keys'][i])}", True
    if how == "count":
        n = rule_count(it, res)
        return [LADDER[k] for k, (lo, hi) in enumerate(rule["bands"]) if lo <= n <= hi], f"부적합 유형 {n}건", n > 0
    if how == "num":
        if rule.get("manual") and re.search(rule["manual"], use or ""):
            return None, "", False
        v = _num(st.get(rule["key"]))
        if v is None:
            return [], f"점검현황 숫자({rule.get('unit', '')})를 넣으면 자동", False
        for op, lim, allow in rule["steps"]:
            if (v >= lim - 1e-9) if op == ">=" else (v <= lim + 1e-9):
                return list(allow), f"{v:g}{rule.get('unit', '')}", True
        return list(rule["rest"]), f"{v:g}{rule.get('unit', '')}", True
    if how == "cycle":
        yes, no, v = st.get(rule["yes"]) is True, st.get(rule["no"]) is True, _num(st.get(rule["num"]))
        if no:
            return list(rule["ng"]), "정기청소 아니오", True
        if yes:
            if v is not None and v > rule["max"]:
                return list(rule["ng"]), f"주기 {v:g}개월({rule['max']}개월 넘음)", True
            return list(rule["ok"]), "정기청소 예" + (f" {v:g}개월" if v is not None else ""), True
        return [], "점검현황 예·아니오를 고르면 자동", False
    return None, "", False


def _count_state(it: dict, r: dict) -> tuple[int, bool]:
    """건수형 — (건수, 정해졌는지): 건수를 적었거나 변경 유형 체크가 있으면 정해짐."""
    cnt = r.get("count")
    if cnt not in (None, ""):
        return int(cnt), True
    n = checked_count(it, r)
    return n, n > 0


def design_allow(ev: dict) -> list[str]:
    """설계도서 적합여부로 고를 수 있는 것 — 사이트 fn_set_required4와 같게(판정·세부 판정에 적합·양호·보통·인증·재인증 → 적합,
    부적합·미흡·불량·만료 → 부적합, 해당없음 → 해당없음, 도면없음은 늘). 판정이 아직 없으면 도면없음만."""
    js = [ev.get("judge")] + [d.get("judge") for d in ev.get("details") or []]
    out = []
    if any(j in GOOD_J for j in js):
        out.append("적합")
    if any(j in BAD_J for j in js):
        out.append("부적합")
    out.append("도면없음")
    if "해당없음" in js:
        out.append("해당없음")
    return out


def normalize(it: dict, res: dict | None, prev: dict | None = None, use: str = "") -> dict:
    """저장할 때마다(화면·사진·AI) — ① 하나만 고르는 줄은 새로 고른 것만 ② 개수·숫자로 정해지는 작은 점검·건수형 판정을 점검현황대로
    ③ 설계도서 적합여부를 판정과 맞게(사이트 규칙, 고를 수 있는 게 하나면 그것으로). 점검자가 넣은 해당없음은 그대로(그 뒤 점검현황을 새로 고르면 그 값),
    점검현황이 비어 정할 수 없으면 있던 값은 둠(예전 건 — 개수 선택지 규칙은 판정에 맞는 선택지를 골라 줌). prev = 고치기 전 결과, use = 주용도(3.5.6 반자높이)."""
    r = dict(res or {})
    if r.get("na"):
        return r
    prev = prev or {}
    st = dict(r.get("status") or {})
    pst = prev.get("status") or {}
    for grp in RADIOS.get(it["code"]) or []:
        on = [k for k in grp if st.get(k) is True]
        if len(on) > 1:
            keep = ([k for k in on if pst.get(k) is not True] or on)[-1]
            for k in on:
                if k != keep:
                    st.pop(k)
    r["status"] = st
    auto = dict(r.get("auto") or {})
    if it["kind"] == "count":
        n, known = _count_state(it, r)
        j = r.get("judge") or ""
        if j != "해당없음":
            if known:
                r["judge"] = "적합" if n == 0 else "부적합"
                auto["judge"] = n > 0 and r.get("count") in (None, "")
            elif j == "부적합" and auto.get("judge"):
                r["judge"], auto["judge"] = "", False
    elif it["kind"] == "score":
        rt = dict(r.get("ratings") or {})
        mine = set(auto.get("rules") or [])
        for key, rule in (AUTO_RULES.get(it["code"]) or {}).items():
            cur = rt.get(key)
            keys = _rule_keys(it, rule)
            if rule["how"] == "pick" and not any(st.get(k) is True for k in keys) and cur in LADDER[:len(rule["keys"])] and key not in mine:
                st[rule["keys"][LADDER.index(cur)]] = True  # 점검현황 없이 판정만 있던 것(예전 건·AI) → 그 선택지
            touched = bool(prev) and any(st.get(k) != pst.get(k) for k in keys)
            if cur == "해당없음" and not touched:
                if rule["how"] == "pick":
                    for k in keys:
                        st.pop(k, None)
                mine.discard(key)
                continue
            allow, _, has = rule_allow(it, r, rule, use)
            if allow is None:
                mine.discard(key)
                continue
            if len(allow) == 1 and (has or cur):
                rt[key] = allow[0]
                mine.add(key)
            elif (cur and cur not in allow) or (not has and key in mine):
                rt.pop(key, None)
                mine.discard(key)
        r["ratings"] = rt
        auto["rules"] = sorted(mine)
    ev = evaluate(it, r)
    allow = design_allow(ev)
    one = [x for x in allow if x != "도면없음"]
    cur = r.get("design") or ""
    if cur != "도면없음":
        if cur and cur not in allow:
            r["design"], auto["design"] = (one[0], True) if len(one) == 1 else ("", False)
        elif not cur and len(one) == 1:
            r["design"], auto["design"] = one[0], True
    else:
        auto["design"] = False
    r["auto"] = auto
    return r


def normalize_all(results: dict | None, use: str = "") -> dict:
    """건의 결과 전체를 규칙대로(건 화면 응답·봇 — 예전 값도 같게 보이고 같게 넣음, 저장은 안 함)."""
    by = by_code()
    return {c: (normalize(by[c], r, use=use) if c in by and r else r) for c, r in (results or {}).items()}


def ui_locks(it: dict, res: dict | None, use: str = "") -> dict:
    """화면 잠금(10/30) — {rt: {작은 점검 키: {allow, why}}, judge: 건수형 판정으로 고를 수 있는 것, design: 설계도서 적합여부로 고를 수 있는 것}.
    해당없음은 화면에서 늘 고를 수 있음(사유는 비고에)."""
    r = res or {}
    out: dict = {"rt": {}, "judge": None, "design": design_allow(evaluate(it, r))}
    if it["kind"] == "count":
        n, known = _count_state(it, r)
        out["judge"] = {"allow": ["부적합" if n else "적합"] if known else ["적합"],
                        "why": f"{n}건" if known else "변경 유형이 없으면 적합 — 있으면 아래에서 체크(부적합 자동)"}
    for key, rule in (AUTO_RULES.get(it["code"]) or {}).items():
        allow, why, _ = rule_allow(it, r, rule, use)
        if allow is not None:
            out["rt"][key] = {"allow": allow, "why": why}
    return out


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
