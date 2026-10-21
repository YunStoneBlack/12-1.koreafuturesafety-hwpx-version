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

MEMBER_KINDS = ("기둥", "보", "벽체")
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
TEXTS = [  # (키, 이름, 견본 글)
    ("crack", "2.3 (2) 주요부재별 균열 현황", "본 시설물의 주요 구조부재에 대한 균열 조사 결과, 대부분의 구조부재 각 부위에서 구조적 안전성에 영향을 미치는 균열은 조사되지 않았다."),
    ("leak", "2.3 (3) 누수 및 백태 현황", "육안조사결과, 구조체의 내구성에 영향을 미치는 누수 및 백태는 조사되지 않았다."),
    ("rebar", "2.3 (4) 철근의 노출 현황", "본 시설물의 주요 구조 부재에 대한 철근 노출은 조사되지 않았다."),
    ("aging", "2.3 (5) 콘크리트 노후화 현황(박리·박락·층분리 등)", "육안조사결과, 구조체의 내구성에 영향을 미치는 박리, 박락, 층분리 등의 노후화는 조사되지 않았다."),
    ("steel", "2.3 (6) 강재구조 노후화 현황", "강재 구조는 없는 것으로 조사되었다."),
    ("heavy", "2.4.1 중량물 조사내용", "육안조사 결과, 지붕층 실외기 및 물탱크 이외에는 특기할만한 하중의 증가는 없는 것으로 조사되었다."),
    ("finish", "2.4.2 건물외부 마감재", "몰탈위 치장벽돌 / 드라이비트 마감"),
]


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


def norm_member(row: dict) -> dict:
    kind = row.get("kind") if row.get("kind") in MEMBER_KINDS else "기둥"
    return {"id": _s(row.get("id"), 12) or uuid.uuid4().hex[:8], "floor": _int(row.get("floor")) or 1, "where": _s(row.get("where"), 30),
            "kind": kind, "mark": _s(row.get("mark"), 20), "item_id": _s(row.get("item_id"), 12),
            "design": size_text(row.get("design")), "measured": size_text(row.get("measured")), "note": _s(row.get("note"), 40)}


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
            "height": _int(row.get("height")), "width": _int(row.get("width")), "thick": _s(row.get("thick"), 8) or "1.0B",
            "dir": "Y" if row.get("dir") == "Y" else "X", "expose": expose, "finish": _int(row.get("finish")), "boundary": boundary, "applied": applied,
            "manual": bool(row.get("manual"))}


def normalize(data: dict | None) -> dict:
    d = dict(data or {})
    texts = {k: _s((d.get("texts") or {}).get(k, default), 600) for k, _label, default in TEXTS}
    return {"members": [norm_member(x) for x in d.get("members") or [] if isinstance(x, dict)][:300],
            "cores": [norm_core(x) for x in d.get("cores") or [] if isinstance(x, dict)][:60],
            "masonry": [norm_masonry(x) for x in d.get("masonry") or [] if isinstance(x, dict)][:300],
            "texts": texts, "photos": {k: v for k, v in (d.get("photos") or {}).items() if k in PHOTO and isinstance(v, dict)},
            "core_note": _s(d.get("core_note"), 200)}


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
    assert n["texts"]["steel"].startswith("강재 구조는")


if __name__ == "__main__":
    _selfcheck()
    print("ok")
