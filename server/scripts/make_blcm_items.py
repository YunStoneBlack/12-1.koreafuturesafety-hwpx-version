"""건축물 정기점검 매뉴얼(국토교통부 25.02, 한글) 3장 글 → 소항목 표 server/blcm/items.json(2026-10-29 건축물관리점검 보고서 자동화).

쓰는 법: 매뉴얼 hwp의 본문 글을 줄마다 뽑은 글 파일(text.txt)을 주고 돌림 — python -m server.scripts.make_blcm_items text.txt
  (글 뽑기는 HWP5 BodyText 레코드 PARA_TEXT — 핵심기술 43절). 매뉴얼이 바뀌면 다시 돌리고 화면·AI를 확인.

소항목마다:
  code "3.1.1" · name · big/mid/small(점검 대·중·소 항목)
  details [세부항목 {name, judge(count|rating|fit|cert), points(점수형 배점)·count_max(건수형 최대 건수), subs[{name, points, judge}]}]
  status [점검현황 줄 [조각 {t:"text", v} | {t:"check", v} | {t:"blank"}]] — 사이트 "세부항목 점검현황"과 같은 차례(체크 칸·빈칸)
  criteria [점검기준 줄] · advice [개선방안에 대한 의견 줄] · laws(※관련법규) · raw(원문)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "blcm" / "items.json"
HEAD = re.compile(r"^(3\.[1-5]\.\d+)\s+(.+?)\s*$")
sq = lambda x: re.sub(r"\s", "", x)  # noqa: E731


BLANK = re.compile(r"\(\s*\)|\(\s{2,}([^()\s][^()]{0,5}?)\s*\)")  # "(   )" · "(     초)"(빈칸 + 단위)


def tokens(line: str) -> list[dict]:
    """점검현황 한 줄 → 조각: 글 · □선택지 · (  ) 빈칸(단위가 있으면 unit). "기타 (    )"는 선택지 + 빈칸, "예 (청소주기 (  ) 개월)"은 선택지 "예" + 글 + 빈칸."""
    out: list[dict] = []
    i, n = 0, len(line)
    buf = ""

    def flush():
        nonlocal buf
        if buf.strip():
            out.append({"t": "text", "v": re.sub(r"\s+", " ", buf.strip())})
        buf = ""

    while i < n:
        if line[i] == "□":
            flush()
            j = i + 1
            while j < n and line[j] not in "□[]/" and not BLANK.match(line, j):
                j += 1
            label = line[i + 1:j].strip()
            rest = ""
            if label.count("(") > label.count(")"):  # "예 (청소주기" → 선택지 "예", 글 "(청소주기"
                k = label.rfind("(")
                label, rest = label[:k].strip(), label[k:].strip()
            if label:
                out.append({"t": "check", "v": label})
            if rest:
                out.append({"t": "text", "v": rest})
            i = j
            continue
        m = BLANK.match(line, i)
        if m:
            flush()
            out.append({"t": "blank", **({"unit": m[1].strip()} if m[1] else {})})
            i = m.end()
            continue
        buf += line[i]
        i += 1
    flush()
    return out


def judge_of(line: str) -> str | None:
    t = sq(line)
    if t.startswith("□양호") and "(1.0)" not in t:
        return "rating"
    if t.startswith("□적합") and "(1.0)" not in t:
        return "fit"
    if t.startswith("□인증"):
        return "cert"
    return None


def weight_of(line: str) -> str | None:
    t = sq(line)
    if t.startswith("□양호(1.0)"):
        return "rating"
    if t.startswith("□적합(1.0)"):
        return "fit"
    return None


def parse(text: str) -> list[dict]:
    L = [x.rstrip() for x in text.split("\n")]
    start = next(i for i, x in enumerate(L) if x.strip() == "제 3 장 점검세부항목별 점검내용" and i > 100)
    end = next(i for i, x in enumerate(L) if i > start and re.match(r"^3\.6\s", x))
    idx = [(i, HEAD.match(L[i])) for i in range(start, end) if HEAD.match(L[i])]
    items = []
    for k, (i, m) in enumerate(idx):
        j = idx[k + 1][0] if k + 1 < len(idx) else end
        raw = "\n".join(L[i + 1:j])
        s = [x.strip() for x in L[i + 1:j] if x.strip()]

        def after(label):
            return next((s[n + 1] for n, x in enumerate(s) if sq(x) == label and n + 1 < len(s)), "")

        a = next(n for n, x in enumerate(s) if sq(x) == "소계")
        b = next((n for n in range(a, len(s)) if sq(s[n]) in ("점검현황", "세부항목점검현황")), None)
        first = next((n for n, x in enumerate(s) if re.match(r"^1\)", x)), None)
        stop = b if b is not None else first if first is not None else len(s)
        ev = s[a + 1:(stop - 1 if b is not None and sq(s[b]) == "점검현황" else stop)]
        details, names, cur = [], [], None
        for n, x in enumerate(ev):
            if re.fullmatch(r"\(\s*(점|건)?\s*\)", x) or sq(x) in ("점", "건", "건/", "세부항목", "세부항목점검결과"):
                continue
            mm = re.fullmatch(r"\(([\d.]+)\s*(점|건)\)", x)
            nxt = ev[n + 1] if n + 1 < len(ev) else ""
            if mm:
                nm = " ".join(names).strip()
                names = []
                jd = judge_of(nxt)
                if mm[2] == "건":
                    cur = {"name": nm, "judge": "cert" if "재인증" in nxt else "count", "count_max": int(float(mm[1])), "points": None, "subs": []}
                    details.append(cur)
                elif jd:
                    cur = {"name": nm, "judge": jd, "points": float(mm[1]), "count_max": None, "subs": []}
                    details.append(cur)
                elif weight_of(nxt) and cur is not None:
                    cur["subs"].append({"name": nm, "points": float(mm[1]), "judge": weight_of(nxt)})
                continue
            sm = re.match(r"^◦\s*(.+?)\s+배점\s*\(([\d.]+)점\)", x)
            if sm and cur is not None:
                cur["subs"].append({"name": sm[1].strip().rstrip(":").strip(), "points": float(sm[2]), "judge": weight_of(nxt) or "rating"})
                names = []
                continue
            sm2 = re.match(r"^배점\s*\(([\d.]+)점\)$", x)  # "◦이름" 줄 다음 줄에 "배점 (10점)"(3.1.14 등)
            if sm2 and cur is not None and n > 0 and ev[n - 1].startswith("◦"):
                cur["subs"].append({"name": ev[n - 1].lstrip("◦").strip().rstrip(":").strip(), "points": float(sm2[1]), "judge": weight_of(nxt) or "rating"})
                names = []
                continue
            if x.startswith("□") or x.startswith("◦"):
                names = []  # 선택지·◦ 줄 앞 글은 다음 세부항목 이름이 아님(3.5.4 둘째 이름에 앞 세부 글이 섞이던 것)
                continue
            names.append(x)
        status = [tokens(x) for x in s[b + 1:next((n for n in range(b + 1, len(s)) if re.match(r"^1\)", s[n]) or sq(s[n]) in ("점검세부항목", "세부항목", "세부항목점검기준")), len(s))]] if b is not None else []
        crit = s[first:next((n for n in range(first or 0, len(s)) if sq(s[n]) == "개선방안에대한의견"), len(s))] if first is not None else []
        laws_i = next((n for n, x in enumerate(s) if sq(x).startswith("※관련법규")), None)
        advice, on = [], False
        for x in crit:
            if re.search(r"개선방안에\s*대한\s*의견", x) and re.match(r"^(\d\)|\(\d\))", x):
                on = True
                continue
            if on and re.match(r"^(\d\)|\(\d\))", x):
                on = False
            if on:
                advice.append(x)
        judges = {d["judge"] for d in details}
        items.append({"code": m[1], "name": m[2].strip(), "big": after("점검대항목"), "mid": after("점검중항목"), "small": after("점검소항목"),
                      "kind": "count" if judges == {"count"} else "cert" if judges == {"cert"} else "score",
                      "details": details, "status": status, "criteria": crit, "advice": advice,
                      "laws": " ".join(s[laws_i + 1:]) if laws_i is not None else "", "raw": raw})
    return items


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    items = parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print("소항목", len(items), "→", OUT)
    for it in items:
        print(f"{it['code']:7s} {it['name'][:14]:14s} {it['kind']:5s} | " + " / ".join(
            f"{d['name'][:18]}[{d['judge']} {d['points'] or d['count_max']}]" + (f"({len(d['subs'])}: {', '.join(x['name'][:8] for x in d['subs'][:4])})" if d['subs'] else "")
            for d in it["details"]) + f" | 현황 {len(it['status'])}줄 체크 {sum(1 for ln in it['status'] for t in ln if t['t'] == 'check')}")


if __name__ == "__main__":
    main()
