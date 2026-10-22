"""내진성능평가 현장조사 입력(2026-10-21 사용자 "현장조사 구성 — 규격조사·조적조사·철근조사 등등, 콘크리트 압축강도 시험 성적서 첨부하는 칸 이런 식으로
만들어 놔야 보고서 틀을 만들 수 있잖아"). 칸은 견본(삼숭초 교사동 2026.01) 2장 표 그대로.

- 부재 단면(2.2.1 【부재 단면 치수 조사 결과】): 층·위치·부재(기둥/보/벽체)·부호·도면치수·실측치수·비고 — 도면치수는 구조 일람표 칸(size)에서.
- 코어 압축강도(2.2.3·2.2.4 【콘크리트 코어시험에 의한 강도결정】): 구분(4층-벽체-1)·MPa — 성적서(스캔)는 AI가 읽고(약 20원) 사람이 확인, 평균·표준편차 자동.
- 조적조(2.4.3 [조적벽 치수 및 상태조사 결과표]): 층·구분(채움벽/허리벽)·부재ID·순높이·순너비·추정 순수 조적두께·방향·노출·마감두께·경계면·적용.
- 현장 사진(칸마다 한 장): 위치도·전경, 부재 단면, 철근탐사, 코어, 중량물, 외부 마감재, 채움벽·허리벽.
- 분석 글: 2.3 외관조사 다섯 항목, 2.4.1 중량물, 2.4.2 마감재(견본 글이 기본 — 고쳐 씀).
값은 회차 survey["seismic_field"].
"""
from __future__ import annotations

import math
import re
import uuid

MEMBER_KINDS = ("보", "기둥", "벽체")  # 부재 규격 종별(매뉴얼 <표 3-1> — 칸 차례도 이대로)
MASONRY_KINDS = ("채움벽", "허리벽")
EXPOSE = ("2면 모르타르", "1면 모르타르", "노출")
PHOTO_SLOTS = [  # (키, 이름, 보고서 자리)
    ("map", "시설물 위치도", "요약 — 시설물 위치도 및 전경사진"), ("front", "시설물 전경", "요약 — 시설물 위치도 및 전경사진"),
    ("member_1", "구조 부재 단면 조사 1", "2.2.1"), ("member_2", "구조 부재 단면 조사 2", "2.2.1"),
    ("rebar_1", "철근탐사 장비", "2.2.2"), ("rebar_2", "철근배근 탐사", "2.2.2"),
    ("core_1", "코어 채취 작업 1", "2.2.3"), ("core_2", "코어 채취 작업 2", "2.2.3"), ("core_3", "코어시료 채취 완료", "2.2.3"), ("core_4", "코어 시료 단면", "2.2.3"),
    ("heavy_1", "건물 외 중량물 1", "2.4.1"), ("heavy_2", "건물 외 중량물 2", "2.4.1"),
    ("finish_1", "건물외부 마감재 1", "2.4.2"), ("finish_2", "건물외부 마감재 2", "2.4.2"),
    ("infill_1", "조적 채움벽 현황 1", "2.4.3"), ("infill_2", "조적 채움벽 현황 2", "2.4.3"),
    ("parapet_1", "조적 허리벽 현황 1", "2.4.3"), ("parapet_2", "조적 허리벽 현황 2", "2.4.3"),
]
PHOTO = {k: (label, where) for k, label, where in PHOTO_SLOTS}
TEXTS = [  # (키, 이름, 기본 글) — 조사결과 글: 한 글이 본문 조사결과와 요약 표에 같이(10/22 형 "결과값 연동 AI 작성"), 처음엔 빈칸(견본 글 안 남김)
    ("eq_member", "부재규격 — 본문 2.2.1 (2) 조사결과 · 요약 장비조사 부재치수", ""),
    ("eq_rebar", "철근배근 — 본문 2.2.2 (3) 철근 배근 조사 결과 · 요약 장비조사 철근배근", ""),
    ("eq_core", "압축강도 — 본문 2.2.4 조사결과 · 요약 장비조사 콘크리트 강도", ""),
    ("crack", "외관조사 균열 — 본문 2.3 (2) · 요약 결함조사", ""),
    ("leak", "외관조사 누수·백태 — 본문 2.3 (3) · 요약 결함조사", ""),
    ("rebar", "외관조사 철근 노출 — 본문 2.3 (4) · 요약 결함조사", ""),
    ("aging", "외관조사 콘크리트 노후화(박리·박락·층분리) — 본문 2.3 (5) · 요약 결함조사", ""),
    ("steel", "외관조사 강재구조 노후화 — 본문 2.3 (6) · 요약 결함조사", ""),
    ("heavy", "중량물 — 본문 2.4.1 조사내용 · 요약 비구조 중량물", ""),
    ("finish", "마감재 — 본문 2.4.2 조사내용 · 요약 비구조 마감재", ""),
    ("ns_masonry", "조적조 — 요약 비구조 조적 허리벽 및 채움벽", ""),
    ("eq_steel_joint", "강재 접합부 — 요약 장비조사", ""),
    ("eq_steel_rust", "강재 부식 — 요약 장비조사", ""),
]
OLD_DEFAULTS = {  # 예전 기본 글(견본) — 저장돼 있어도 빈칸으로(10/22)
    "crack": "본 시설물의 주요 구조부재에 대한 균열 조사 결과, 대부분의 구조부재 각 부위에서 구조적 안전성에 영향을 미치는 균열은 조사되지 않았다.",
    "leak": "육안조사결과, 구조체의 내구성에 영향을 미치는 누수 및 백태는 조사되지 않았다.",
    "rebar": "본 시설물의 주요 구조 부재에 대한 철근 노출은 조사되지 않았다.",
    "aging": "육안조사결과, 구조체의 내구성에 영향을 미치는 박리, 박락, 층분리 등의 노후화는 조사되지 않았다.",
    "steel": "강재 구조는 없는 것으로 조사되었다.",
    "heavy": "육안조사 결과, 지붕층 실외기 및 물탱크 이외에는 특기할만한 하중의 증가는 없는 것으로 조사되었다.",
    "finish": "몰탈위 치장벽돌 / 드라이비트 마감",
}
SUMMARY_ROWS = {"부재치수조사결과": "eq_member", "철근배근조사결과": "eq_rebar", "강재접합부조사": "eq_steel_joint", "강재부식조사": "eq_steel_rust",
                "콘크리트강도조사": "eq_core", "중량물": "heavy", "마감재": "finish", "조적허리벽및채움벽": "ns_masonry"}  # 요약 표 구분 칸 → 글 칸
VISUAL = ("crack", "leak", "rebar", "aging", "steel")  # 외관조사 — 요약 결함조사 분석 결과는 이 글들을 이어서


def _s(v, n: int = 60) -> str:
    return str(v if v is not None else "").strip()[:n]


def _num(v) -> float | None:
    try:
        x = float(str(v).replace(",", "").strip())
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    x = _num(v)
    return int(round(x)) if x is not None else None


def size_text(v: str) -> str:
    """"400X500"·"400 * 500"·"400×500" → "400 x 500"(견본 표 모양). 한쪽 못 잰 칸은 "□"."""
    s = _s(v, 40).replace("×", "x").replace("*", "x").replace("X", "x")
    m = re.fullmatch(r"\s*(\d+|□)\s*x\s*(\d+|□)\s*", s)
    return f"{m.group(1)} x {m.group(2)}" if m else s


MATCH = ("일치", "불일치", "일부 일치")  # 실측치수 고르기(10/22 민재형) — 일치면 도면치수 그대로


def norm_member(row: dict) -> dict:
    kind = row.get("kind") if row.get("kind") in MEMBER_KINDS else "기둥"
    match = row.get("match") if row.get("match") in MATCH else ""
    design = size_text(row.get("design"))
    measured = design if match == "일치" and design else size_text(row.get("measured"))
    return {"id": _s(row.get("id"), 12) or uuid.uuid4().hex[:8], "floor": _int(row.get("floor")) or 1, "where": _s(row.get("where"), 30),
            "kind": kind, "mark": _s(row.get("mark"), 20), "item_id": _s(row.get("item_id"), 12),
            "design": design, "measured": measured, "match": match, "note": _s(row.get("note"), 40)}


def norm_core(row: dict) -> dict:
    return {"id": _s(row.get("id"), 12) or uuid.uuid4().hex[:8], "name": _s(row.get("name"), 30), "mpa": _num(row.get("mpa"))}


def masonry_apply(expose: str, boundary: str) -> str:
    """적용 상태 기본값(매뉴얼 — 사람이 고침): 경계면 불량이거나 노출이면 불량, 2면 모르타르 = 양호, 1면 = 보통."""
    if boundary == "불량" or expose == "노출":
        return "불량"
    return {"2면 모르타르": "양호", "1면 모르타르": "보통"}.get(expose, "")


def norm_masonry(row: dict) -> dict:
    kind = row.get("kind") if row.get("kind") in MASONRY_KINDS else "채움벽"
    expose = row.get("expose") if row.get("expose") in EXPOSE else "1면 모르타르"
    boundary = row.get("boundary") if row.get("boundary") in ("양호", "불량") else "양호"
    applied = row.get("applied") if row.get("applied") in ("양호", "보통", "불량") else masonry_apply(expose, boundary)
    return {"id": _s(row.get("id"), 12) or uuid.uuid4().hex[:8], "floor": _int(row.get("floor")) or 1, "kind": kind, "mid": _s(row.get("mid"), 12),
            "type_id": _s(row.get("type_id"), 12),  # 조적 목록에서 고른 것(10/22 — 저장 때 그 값으로)
            "height": _int(row.get("height")), "width": _int(row.get("width")), "thick": _s(row.get("thick"), 8) or "1.0B",
            "dir": "Y" if row.get("dir") == "Y" else "X", "expose": expose, "finish": _int(row.get("finish")), "boundary": boundary, "applied": applied,
            "manual": bool(row.get("manual"))}


def norm_plan(plan) -> dict:
    """부재 단면 칸 수 {"층|부재": 개수} — 표본 층 × 종별 칸(10/22 형 "수량 조정할 수 있도록"). 0~40."""
    out = {}
    for k, v in (plan or {}).items() if isinstance(plan, dict) else []:
        m = re.fullmatch(r"(-?\d+)\|(.+)", str(k))
        n = _int(v)
        if m and m.group(2) in MEMBER_KINDS and n is not None and int(m.group(1)):
            out[f"{int(m.group(1))}|{m.group(2)}"] = max(0, min(n, 40))
    return dict(list(out.items())[:200])


def norm_mtype(row: dict) -> dict:
    """조적 목록 한 줄(F-n 채움벽·P-n 허리벽) — 층별 칸에서 고르면 이 값(10/22 민재형 "같은 사이즈·방향·상태로 조적 리스트를 만들고 선택해서 자동 입력")."""
    t = norm_masonry(row)
    mid = t["mid"] = t["mid"].upper()  # p-1 → P-1
    t["kind"] = "채움벽" if mid.startswith("F") else "허리벽" if mid.startswith("P") else t["kind"]
    t.pop("floor", None)
    t.pop("type_id", None)
    return t


def apply_types(field: dict) -> dict:
    """층별 조적 칸 — 목록에서 고른 줄은 목록 값으로(목록을 고치면 다음 저장 때 칸도)."""
    types = {t["id"]: t for t in field.get("masonry_types") or []}
    for m in field.get("masonry") or []:
        t = types.get(m.get("type_id") or "")
        if t:
            m.update({k: t[k] for k in ("kind", "mid", "height", "width", "thick", "dir", "expose", "finish", "boundary", "applied", "manual")})
    return field


def norm_mplan(plan) -> dict:
    """층마다 조적 칸 수 {"층": 0~20}."""
    out = {}
    for k, v in (plan or {}).items() if isinstance(plan, dict) else []:
        n, c = _int(k), _int(v)
        if n and c is not None:
            out[str(n)] = max(0, min(c, 20))
    return out


def normalize(data: dict | None) -> dict:
    d = dict(data or {})
    texts = {k: _s((d.get("texts") or {}).get(k, default), 600) for k, _label, default in TEXTS}
    texts = {k: "" if v == OLD_DEFAULTS.get(k) else v for k, v in texts.items()}  # 예전 견본 기본 글은 빈칸
    return {"members": [norm_member(x) for x in d.get("members") or [] if isinstance(x, dict)][:300],
            "cores": [norm_core(x) for x in d.get("cores") or [] if isinstance(x, dict)][:60],
            "masonry": [norm_masonry(x) for x in d.get("masonry") or [] if isinstance(x, dict)][:300],
            "texts": texts, "photos": {k: v for k, v in (d.get("photos") or {}).items() if k in PHOTO and isinstance(v, dict)},
            "core_note": _s(d.get("core_note"), 200),
            "core_design": _num(d.get("core_design")),  # 설계기준강도(도면, MPa) — 2.2.4 85%·75% 비교
            "summary": _s(d.get("summary"), 4000),  # 요약문 책임기술자 종합의견(견본 문장 채우기·AI 초안 뒤 사람이 고침, 10/22)
            "member_plan": norm_plan(d.get("member_plan")),  # 부재 단면 칸 수(비면 표본 층 × 종별 × 3·9 기본)
            "masonry_types": [norm_mtype(x) for x in d.get("masonry_types") or [] if isinstance(x, dict)][:60],
            "masonry_plan": norm_mplan(d.get("masonry_plan"))}


def core_stats(cores: list[dict]) -> dict:
    """코어 강도 — 개수·평균(m)·표준편차(s, 표본)·최소·최대(2.2.4 표)."""
    v = [c["mpa"] for c in cores if c.get("mpa") is not None]
    if not v:
        return {"n": 0}
    m = sum(v) / len(v)
    s = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)) if len(v) > 1 else 0.0
    return {"n": len(v), "mean": round(m, 1), "std": round(s, 1), "min": min(v), "max": max(v)}


def floor_label(n: int) -> str:
    return f"지하{-n}층" if n < 0 else f"지상{n}층"


CORE_PROMPT = """아래 그림은 콘크리트 코어 압축강도 시험성적서입니다(쪽마다 한 장).
시험 결과 표의 줄마다 구분(위치 이름 그대로, 예: "4층-벽체-1")과 시험결과(MPa 숫자)를 읽어 주세요.
JSON만: {"rows": [{"name": "4층-벽체-1", "mpa": 16.4}], "test_no": "접수번호(있으면)", "issued": "발급일자 YYYY-MM-DD(있으면)", "lab": "시험기관(있으면)"}"""


def read_core_report(company_id: int, path) -> dict:
    """성적서(PDF·그림) → {rows, test_no, issued, lab} — AI(company 키, 쪽마다 그림 한 장, 약 20원)."""
    from pathlib import Path

    from server.sitok import vision

    p = Path(path)
    images: list[bytes] = []
    if p.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(p) as d:
            for pg in list(d)[:4]:
                images.append(pg.get_pixmap(dpi=150).tobytes("png"))
    else:
        images.append(p.read_bytes())
    got = vision.ask_json(company_id, images, CORE_PROMPT, max_tokens=2000, side=1568, effort="low") or {}
    rows = [norm_core(x) for x in got.get("rows") or [] if isinstance(x, dict) and _num(x.get("mpa")) is not None]
    return {"rows": rows, "test_no": _s(got.get("test_no"), 30), "issued": _s(got.get("issued"), 10), "lab": _s(got.get("lab"), 40)}


def _selfcheck() -> None:
    assert size_text("400X500") == "400 x 500" and size_text("420 x □") == "420 x □"
    assert core_stats([{"mpa": 16.4}, {"mpa": 17.3}, {"mpa": 16.9}, {"mpa": 15.7}, {"mpa": 16.2}, {"mpa": 16.8}]) == {"n": 6, "mean": 16.6, "std": 0.6, "min": 15.7, "max": 17.3}
    assert masonry_apply("2면 모르타르", "양호") == "양호" and masonry_apply("1면 모르타르", "불량") == "불량"
    n = normalize({"members": [{"kind": "보", "design": "400*600", "floor": "3"}], "masonry": [{"expose": "2면 모르타르"}]})
    assert n["members"][0]["design"] == "400 x 600" and n["members"][0]["floor"] == 3 and n["masonry"][0]["applied"] == "양호"
    assert n["texts"]["steel"] == "" and n["texts"]["eq_member"] == ""  # 기본은 빈칸(10/22)
    m = normalize({"texts": {"heavy": OLD_DEFAULTS["heavy"], "finish": "치장벽돌 마감"}})
    assert m["texts"]["heavy"] == "" and m["texts"]["finish"] == "치장벽돌 마감"  # 예전 견본 글은 빈칸, 직접 쓴 글은 그대로


if __name__ == "__main__":
    _selfcheck()
    print("ok")
