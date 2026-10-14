"""시특법 정밀안전점검 AI 초안(2026-10-13 밤, ⑤-2) — 정기 [🤖 AI 초안] 창을 정밀 회차에서 쓰면 항목이 이 25개로 바뀜(사용자 "추천대로", 10/15 유지관리방안 3개 더함).
결함현황표 + 재료시험 수치 + 상태평가 결과 + 하중·공중이용 등급을 글로 묶어 한 번에 보내고 항목별 JSON으로 받음(사진 안 보냄).
기본 글(precision_text)이 먼저 칸에 들어 있고 [AI로 다시 쓰기]를 누르면 다시 씀. 저장은 r.ai["final"]["precision"] = {키: 글} → precision_build가 덮어씀.
"""
from __future__ import annotations

ITEMS = [  # (키, 이름, 어디에 들어가는지)
    ("crack", "콘크리트 구조체 균열", "3.2.1 본문 · 3.1/7.1 분석 표 · 5.1.1 나 · 결과표 점검 주요결과"),
    ("leak", "누수 및 백화", "3.2.2 · 분석 표 · 결과표"),
    ("spall", "박리·박락·철근노출·부식", "3.2.3 · 분석 표 · 결과표"),
    ("steel", "강재구조 노후상태", "3.2.4 · 분석 표 · 결과표(철근콘크리트면 해당없음)"),
    ("nonstruct", "비구조체", "3.2.5 · 분석 표 · 결과표"),
    ("load", "시설물의 하중상태", "3.2.6 · 분석 표 · 결과표"),
    ("public", "공중이 이용하는 부위·부대시설", "3.2.7 · 분석 표 · 5.1.1 바"),
    ("other", "기타시설", "3.2.8 · 분석 표 · 결과표"),
    ("section", "부재 규격 조사 결과 분석", "4.2.1 나 · 5.1.1 가 · 7.2.1 · 요약표"),
    ("strength", "콘크리트 강도 결과 분석", "4.2.2 나 · 5.1.1 다 · 7.2.2"),
    ("carb", "탄산화 결과 분석(첫 문단)", "4.2.3 나 · 5.1.1 라 · 7.2.3"),
    ("carb_life", "탄산화 잔존수명(둘째 문단)", "4.2.3 나 · 5.1.1 라"),
    ("tilt", "기울기 결과 분석", "4.2.4 나 · 5.1.1 마 1) · 7.2.4"),
    ("settle", "부등침하 결과 분석", "4.2.5 나 · 5.1.1 마 2) · 7.2.5"),
    ("summary", "책임기술자 종합의견(8~10줄, 350~450자 — 등급·주요 손상·재료시험 결과·유지관리 방향을 담아 칸을 채우게)", "요약표 첫 칸"),
    ("overall", "종합평가 및 안전등급 한 문장", "5.2 · 7.4"),
    ("conclusion", "종합결론 첫 문단", "7.5 · 요약문"),
    ("prev_compare", "전차 점검 비교 검토(상태평가·기울기 및 침하·종합 항목별 전차→이번 변동 + 전차 결론과 이번 결론 비교)", "표 5.5 검토 칸 · 요약문"),
    ("maint_struct", "유지관리방안 — 구조체(ㆍ로 나눈 3줄: 이번 결함 원인별 점검 포인트 2줄 + 관리 방법 1줄)", "표 6.2 구조체 칸"),
    ("maint_nonstruct", "유지관리방안 — 비구조체(ㆍ로 나눈 3줄)", "표 6.2 비구조체 칸"),
    ("maint_public", "유지관리방안 — 공중이 이용하는 부위(ㆍ로 나눈 1~2줄)", "표 6.2 공중이용 칸"),
    ("limit", "사용제한 필요성", "사용제한 표"),
    ("special", "유지관리 특별 요구사항", "사용제한 표"),
    ("suggest", "건의사항", "사용제한 표"),
    ("diag", "정밀안전진단 실시여부", "사용제한 표(필요/불필요)"),
]
KEYS = [k for k, _, _ in ITEMS]

PROMPT = """당신은 한국의 시설물 정밀안전점검(시설물안전법) 보고서를 쓰는 건축 책임기술자입니다. 아래 이번 회차 자료(외관조사 결함현황표, 재료시험 수치, 상태평가 결과)로
보고서 각 항목의 문장을 쓰세요. 문체는 보고서체("~조사되었다", "~판단된다", "~권고한다"), 사실(자료에 있는 층·부재·개수·수치·등급)만 쓰고 없는 것은 지어내지 마세요.
각 항목은 "참고 기본 글"과 비슷한 길이·구성으로, 자료의 수치를 정확히 넣어 더 구체적으로 쓰세요. 기본 글이 이미 맞으면 다듬기만 해도 됩니다.

[시설물] {facility}
[회차] {period}

[외관조사 결함현황표 — 구조체 줄이 상태평가에 들어감]
{defects}

[재료시험]
{tests}

[상태평가 결과]
{rating}

[하중상태·공중이용·기타시설]
{extra}

[참고 기본 글 — 항목 키: 글]
{defaults}

아래 키마다 글을 써서 JSON 객체 하나로만 답하세요(설명 없이). 값은 문자열 하나(문단 하나, 줄바꿈 없이). diag는 "필요" 또는 "불필요".
{keys}"""


def material(db, r, tv: dict, rv: dict, pr: dict, defects: list, f) -> dict:
    """프롬프트에 넣을 자료 글."""
    from server.sitok import condition

    lines = []
    for d in defects:
        size = " ".join(x for x in (f"{d.count}개" if d.count else "", f"폭 {d.width}mm" if d.width else "", f"깊이 {d.depth}mm" if d.depth else "",
                                   f"길이 {d.length}m" if d.length else "", f"면적률 {d.area_ratio}%" if d.area_ratio else "") if x)
        item = condition.defect_item(d.dtype) if d.part == "구조체" else None
        lines.append(f"- {d.floor} {d.seq}번 [{d.part}] {d.member} {d.dtype} {size}" + (f" 원인: {d.cause}" if d.cause else "") + (f" ({d.mark})" if d.mark else "")
                     + ("" if item else " ※상태평가 제외"))
    sm, cs = tv["strength"]["summary"], tv["carbonation"]["summary"]
    secs = tv["sections"]
    tests = [
        f"표본층: {', '.join(x['label'] + '(' + x['range_label'] + ')' for x in tv['sample']['floors']) or '없음'}",
        f"부재 규격 {len(secs)}개소: " + (", ".join(f"{s['member']} {s['design']}→{s['measured']} {'O.K' if s['ok'] else 'N.G'}" for s in secs if s.get('ok') is not None) or "-"),
        f"콘크리트 강도 {sm['count']}개소: 추정 {sm['min']}~{sm['max']}MPa(평균 {sm['mean']}), 설계 {sorted({x['design'] for x in tv['strength']['rows'] if x.get('design')})}, 등급 {(tv['strength']['grade'] or '-').upper()}" if sm["count"] else "콘크리트 강도: 없음",
        f"탄산화 {cs['count']}개소: 깊이 {cs['min']}~{cs['max']}mm, 경과년수 {tv['building']['age']}년, 잔존수명 {[x['life_text'] for x in tv['carbonation']['rows']]}, 등급 {(tv['carbonation']['grade'] or '-').upper()}" if cs["count"] else "탄산화: 없음",
        f"기울기 {len(tv['tilt']['rows'])}개소: 1/{tv['tilt']['range']['min_n']:,}~1/{tv['tilt']['range']['max_n']:,}, 등급 {(tv['tilt']['grade'] or '-').upper()}, 메모 {tv['tilt']['note']}" if tv["tilt"]["range"]["min_n"] else "기울기: 없음",
        f"부등침하 {len(tv['settlement']['sections'])}구간({tv['settlement']['floor_label']}): 변위 {tv['settlement']['range']['min_disp']}~{tv['settlement']['range']['max_disp']}mm, 등급 {(tv['settlement']['grade'] or '-').upper()}, 메모 {tv['settlement']['note']}" if tv["settlement"]["range"]["max_disp"] is not None else "부등침하: 없음",
    ]
    res = rv["result"]
    rating = ["상태평가 결과 없음"]
    if res:
        rating = [f"{fl['label']}: " + ", ".join(f"{m['kind']} {m['condition']:.1f}" for m in fl["members"] if m["condition"] is not None) + f" → 층 {fl['condition']:.2f}" for fl in res["floors"]]
        rating.append(f"상태평가 {res['condition']['score']:.2f}({res['condition']['grade']}) · 기울기 및 침하 {res['deform']['score']:.2f}({res['deform']['grade']}) · 종합 {res['total']['score']:.2f}({res['total']['grade']})"
                      + (f" · 전차 점검 {rv['prev_grade'] or rv['prev_auto']}등급" if rv["prev_grade"] or rv["prev_auto"] else " · 첫 회차(전차 없음)"))
    extra = [f"하중상태: {pr['load']['note'] or '(메모 없음)'}",
             "공중이용: " + ", ".join(f"{x['name']} {x['grade'] or '-'}" for x in pr["grades"]["public"]),
             "기타시설: " + ", ".join(f"{x['name']} {x['grade'] or '-'}" for x in pr["grades"]["other"]),
             f"내진: {pr['seismic']['status'] or '-'} {pr['seismic']['note']}"]
    pi = (rv.get("prior_info") or {})
    if pi:
        sc = lambda v: (f"{v[0]:.2f}({v[1]})" if v[0] is not None else f"{v[1]}등급") if v and v[1] else "-"  # noqa: E731
        extra.append(f"전차 점검({pi.get('label', '-')}): 상태평가 {sc(pi.get('state'))} · 기울기 및 침하 {sc(pi.get('deform'))} · 종합 {sc(pi.get('total'))} · 결론: {pi.get('conclusion', '-')}")
    return {"facility": f"{f.name} — {f.use_type or f.main_use} · {f.structure} · 지상 {f.floors_above or '-'}층/지하 {f.floors_below or 0}층 · 연면적 {f.total_area or '-'}㎡ · 준공 {f.completion_date}",
            "period": f"{r.year}년 {r.half} (점검기간 {r.period_start}~{r.period_end})", "defects": "\n".join(lines) or "(결함 없음)",
            "tests": "\n".join(tests), "rating": "\n".join(rating), "extra": "\n".join(extra)}


def draft(company_id: int, mat: dict, defaults: dict) -> dict:
    """AI에게 22항목 → {키: 글}. 빠진 키는 기본 글."""
    from server.sitok import vision

    prompt = PROMPT.format(**mat, defaults="\n".join(f"{k}: {defaults.get(k, '')}" for k in KEYS),
                           keys="{" + ", ".join(f'"{k}": "…"' for k in KEYS) + "}")
    raw = vision.ask_json(company_id, [], prompt, max_tokens=8000)
    out = {}
    for k in KEYS:
        v = raw.get(k) if isinstance(raw, dict) else None
        out[k] = str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else defaults.get(k, "")
    if out["diag"] not in ("필요", "불필요"):
        out["diag"] = defaults.get("diag", "불필요")
    return out
