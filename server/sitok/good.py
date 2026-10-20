"""시특법 현장 조사 [👍 상태양호]·[🏫 내진보강] 탭(2026-10-19 민재형 요구사항 문서 B3·B5) — 저장은 sitok_report.survey(면담·현황과 같은 JSON, 다른 칸은 그대로 둠).

- good: 1.3 항목(구조체 균열·누수/백화·박리/박락·강재·비구조체)마다 상태양호 사진(4장까지) — 결함이 적은(없는) 항목의 1.3 대표사진 칸을 채우고 AI 글에 "양호"로.
- steel_na: 강재 해당없음(철근콘크리트 구조 등) — 1.3 강재 글 = STEEL_NA_TEXT, 사진표 "해당없음".
- seismic(학교만): 내진보강시설 — none(해당없음) 또는 사진 2장 → [🤖 점검표 쓰기](AI)로 부록 "내진보강시설 육안 점검표" 6항목(○/×·내용·조치사항)·종합의견,
  사진은 종합의견 상자의 두 칸에(해당없음이면 회사 원본 그대로 ×·해당없음·"-").
API server/api/routers/sitok_good.py, 화면 js/sitok-good.js, 보고서 sitok_reports._extras·report_build(apply_seismic).
"""
from __future__ import annotations

from pathlib import Path

CATS = [("crack", "콘크리트 구조체 균열"), ("leak", "누수 및 백화"), ("spall", "박리·박락 및 철근노출"), ("steel", "강재구조"), ("nonstruct", "비구조체")]
# 옹벽(10/20) — 보고서 1.4 현장조사 결과 3절(지반 및 기초부 / 옹벽 전면부 / 기타)마다 사진 표 2×2 → 결함 사진이 모자란 칸에 상태양호 사진
WALL_CATS = [("found", "지반 및 기초부"), ("front", "옹벽 전면부"), ("etc", "기타(배수시설·사면·점검로)")]
PER = 4  # 항목마다 상태양호 사진(1.3 대표사진 칸 4개)


def cats_for(fam: str = "") -> list:
    return WALL_CATS if fam == "wall" else CATS
STEEL_NA_TEXT = "해당 시설물은 철근콘크리트 구조로 강재에 대한 조사는 해당사항이 없다."
SEISMIC_ITEMS = ["내진보강 부위 및 시설의 해체 또는 손상 여부", "내진보강을 위해 증설, 신설된 부재의 상태",
                 "기존 골조와 내진보강을 위해 증설된 부분의 결합부위의 이격 또는 균열", "철골 가새와 철근콘크리트의 접합부위의 이격 또는 균열 여부",
                 "신설 기초의 침하 여부", "기타사항"]
DIR_GOOD, DIR_SEISMIC = "상태양호", "내진보강"


def norm(sv: dict | None, fam: str = "") -> dict:
    sv = sv or {}
    good = {k: [{"file": str(x.get("file") or ""), "title": str(x.get("title") or "").strip(), "prev": bool(x.get("prev"))}
                for x in (sv.get("good") or {}).get(k) or [] if isinstance(x, dict) and x.get("file")][:PER * 2]  # prev = 전회차 가져온 사진(옹벽 10/21), 이번 PER + 전회차 PER
            for k, _ in cats_for(fam)}
    se = sv.get("seismic") or {}
    rows = [{"mark": r.get("mark") if r.get("mark") in ("○", "×") else "", "text": str(r.get("text") or "").strip(), "action": str(r.get("action") or "").strip()}
            for r in (se.get("rows") or []) if isinstance(r, dict)][:len(SEISMIC_ITEMS)]
    return {"good": good, "steel_na": bool(sv.get("steel_na")),
            "seismic": {"none": bool(se.get("none")), "photos": [str(x or "") for x in (se.get("photos") or [])][:2] + [""] * max(0, 2 - len((se.get("photos") or [])[:2])),
                        "rows": rows, "opinion": str(se.get("opinion") or "").strip(), "at": str(se.get("at") or "")}}


def add_to_rep(rep: dict, sv: dict | None, base: Path, fam: str = "") -> dict:
    """1.3 대표사진 {항목: [(사진, 설명)]}에 상태양호 사진을 뒤에 더함(결함 사진이 모자란 칸만 채워짐 — 칸 수는 표가 정함), 강재 해당없음이면 강재 사진 비움."""
    g = norm(sv, fam)
    out = {k: list(v) for k, v in (rep or {}).items()}
    for k, name in cats_for(fam):
        if k == "steel" and g["steel_na"]:
            out["steel"] = []
            continue
        rows = [x for x in g["good"][k] if not x.get("prev")] or [x for x in g["good"][k] if x.get("prev")]  # 이번 사진, 없으면 전회차
        for x in rows:
            p = base / x["file"]
            if p.exists():
                out.setdefault(k, []).append((str(p), x["title"] or f"{name} 상태양호"))
    return out


def facts(sv: dict | None, fam: str = "") -> str:
    """AI 초안에 넘길 사실 — 상태양호 사진이 있는 항목·강재 해당없음."""
    g = norm(sv, fam)
    lines = []
    have = [name for k, name in cats_for(fam) if g["good"][k] and not (k == "steel" and g["steel_na"])]
    if have:
        lines.append("[상태양호 사진] 현장에서 상태가 양호함을 찍어 둔 항목: " + ", ".join(have) + " — 그 항목에 결함이 없거나 적으면 \"전반적으로 양호한 상태\"로 쓸 것")
    if g["steel_na"]:
        lines.append(f"[강재구조] 해당없음(철근콘크리트 구조) — sections.steel은 \"{STEEL_NA_TEXT}\" 그대로, 결과표·종합결론에 강재 결함을 쓰지 말 것")
    return "\n".join(lines)


def apply_seismic(root, se: dict, base: Path, add_image, rb) -> int:
    """부록 "내진보강시설 육안 점검표"(6항목 ○/×·내용·조치사항) + "▪ 종합의견" 상자(사진 두 칸·의견 줄).
    해당없음(또는 사진 없음) = 형 상반기 보고서 그대로 "×·해당없음", 사진·의견 "-"."""
    HP = rb.HP
    n = 0
    tpl = next((p for p in root.iter(f"{{{HP}}}pic") if next(p.iterancestors(f"{{{HP}}}tc"), None) is not None), None)  # 표 안 그림(글자처럼)을 본뜸
    photos = [p for p in (base / x for x in se["photos"] if x) if p.exists()] if not se["none"] else []
    na = se["none"] or not photos
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        texts = {k: rb._n(rb._cell_text(tc)) for k, tc in cells.items()}
        if any("내진보강부위" in t for t in texts.values()) and tbl.get("colCnt") == "4":
            rows = sorted({r for (r, c) in cells if c == 0 and texts[(r, 0)].startswith("∙")})
            for i, r in enumerate(rows[:len(SEISMIC_ITEMS)]):
                got = {"mark": "×", "text": "해당없음", "action": ""} if na else se["rows"][i] if i < len(se["rows"]) else {"mark": "-", "text": "-", "action": ""}
                for c, v in ((1, got["mark"] or "×"), (2, got["text"] or "-"), (3, got["action"])):
                    if (r, c) in cells:
                        rb._set_lines(cells[(r, c)], [v])
            n += 1
        elif texts.get((0, 0), "").startswith("▪종합의견") and tbl.get("colCnt") == "2":
            for i, c in enumerate((0, 1)):
                if (1, c) in cells:
                    _photo_cell(cells[(1, c)], photos[i] if i < len(photos) else None, tpl, add_image, rb)
            if (2, 0) in cells:
                rb._set_lines(cells[(2, 0)], ["-" if na else se["opinion"] or "-"])
            n += 1
    return n


def _photo_cell(tc, path: Path | None, tpl, add_image, rb) -> None:
    """종합의견 상자 사진 칸(원본은 "-" 글만) — 칸 폭에 맞춘 4:3 그림 틀(본뜬 그림 크기·자르기를 새로), 사진 없으면 "-"."""
    from server.sitok.precision_build import _reset_pic

    if path is None:
        rb._slot_put(tc, None, None, "-", "", tpl, add_image)
        return
    HP = rb.HP
    sz, mg = tc.find(f"{{{HP}}}cellSz"), tc.find(f"{{{HP}}}cellMargin")
    w = int(sz.get("width")) - (int(mg.get("left", 510)) + int(mg.get("right", 510)) if mg is not None else 1020) - 400
    h = w * 3 // 4
    rb._slot_put(tc, None, rb._cropped(str(path), w, h), "-", "", tpl, add_image)
    pic = next(tc.iter(f"{{{HP}}}pic"), None)
    if pic is not None:
        _reset_pic(pic, w, h)
