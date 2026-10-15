"""시특법 정밀안전점검 — 건축물 상태평가·종합평가 계산(2026-10-13, 사용자 "우리가 할 수 있는 건 미리").

공단 "건축물 종합평가 시스템"(SafetyMan 2007 — 민재형: 개발자 사라짐, 국토부도 권리 없음, 표본 10개 넘으면 오류)을 그룹웨어에 녹이려고
그 프로그램의 계산 규칙을 다시 만든 것. 규칙 출처 = 건축물 안전점검 및 정밀안전진단 세부지침(2003.12, 건설교통부·한국시설안전기술공단) 부록 Ⅲ "평가요령"
(scratchpad jm/law/2003_세부지침_건축물.pdf p138~213) — 지금 지침(2021.12 시설물의 안전 및 유지관리 실시 세부지침 안전점검·진단편 6장)도 "구체적인 절차는 부록의
평가요령에 따른다"고만 하고 같은 요령을 씀. 검증: 지침 예제(OO플라자, p168~175·204)와 SafetyMan 다산은혜교회 결과(상태 1.00 + 기울기 5.00 → 종합 3.80)를 `_selfcheck`가 맞춤.

계산 순서(요령 2장):
1) 항목 → 등급 a~e(세부지침 표) → 점수 1·3·5·7·9.
2) 부재 상태평가 = 퍼지 합성: 항목 등급 한 줄(one-hot) × 내구성계수 Table(nRM) → 등급별 가능성(최댓값) → 소속함수(삼각, 꼭짓점 1·3·5·7·9)가
   최대 높이에 닿는 가장 오른쪽 x = 대표값(높이 0.75 → 1.5 → 2, 높이 0.75 미만 = 표면노후만 → 평가 제외). SafetyMan 직접 실행으로 확인(10/13).
3) 층 = 부재 대표값을 부재 중요도(기둥·내력벽 0.9, 큰보 0.7, 작은보 0.5, 슬래브 0.3)의 λ-퍼지척도로 Choquet 적분.
4) 전체 = 층 점수를 층 중요도(ζ = (N-(n-1))/N → 0.9/0.7/0.5/0.3/0.1)로 Choquet 적분.
5) 변위·변형 = max(기울기, 부동침하). 종합 = Choquet(상태 0.7, 변위·변형 0.7, [안전성 0.9 — 정밀안전진단만]).
등급 범위: A 0≤x<2, B 2≤x<4, C 4≤x<6, D 6≤x<8, E 8≤x≤10.

DB·화면은 모름 — 값만 받는다(시험하기 쉽게). 호출은 evaluate()(건물 전체) 또는 항목별 grade_* 함수.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

GRADES = ("a", "b", "c", "d", "e")
SCORE = {"a": 1, "b": 3, "c": 5, "d": 7, "e": 9}
ALPHA = 0.75  # 대표값 수준집합
# 부재 중요도(요령 표 1-4 — 기둥 기준 하중 분담 비율) — 지침 표 1-13·SafetyMan 갑지 열 순서
MEMBER_G = {"기둥": 0.9, "내력벽": 0.9, "큰보": 0.7, "작은보": 0.5, "슬래브": 0.3, "테두리보": 0.7, "접합부": 0.9, "지판": 0.7}
# 강재 항목 중요도 — SafetyMan에 항목 둘씩(9점 + 1점) 넣어 역산(10/15): 강재규격 0.5 · 용접접합 0.7 · 볼트접합 0.7 · 강재부식도 0.9 · 내화피복 0.3.
# 부재 점수 = 있는 항목들의 Choquet(항목 점수는 반올림 없는 평균 — 규격 b·a 두 개면 2.0, 용접 a9·b1이면 1.2)
STEEL_G = {"SS": 0.5, "WE": 0.7, "BO": 0.7, "SC": 0.9, "FP": 0.3}
STEEL_LABEL = {"SS": "강재 규격", "WE": "용접 접합상태", "BO": "볼트 접합상태", "SC": "강재 부식도", "FP": "내화피복"}
STEEL_KINDS = ("기둥", "큰보", "작은보")  # SafetyMan 강재 표 열
MEMBERS = ("기둥", "내력벽", "큰보", "작은보", "슬래브", "테두리보", "접합부")
# 종합평가 중분류 중요도(표 1-3)
G_SAFETY, G_CONDITION, G_DEFORM = 0.9, 0.7, 0.7


def grade_of(x: float) -> str:
    """점수 → 등급 A~E(표 6.49·6.2-1)."""
    return "A" if x < 2 else "B" if x < 4 else "C" if x < 6 else "D" if x < 8 else "E"


# ---------- 1) 항목 → 등급(세부지침 6.4.1 표) ----------

def _band(v: float, cuts: tuple[float, ...], rising: bool) -> str:
    """cuts 4개로 a~e. rising=True면 값이 클수록 좋음(비율 %), False면 클수록 나쁨."""
    if rising:
        a, b, c, d = cuts  # a: v≥a … e: v<d
        return "a" if v >= a else "b" if v >= b else "c" if v >= c else "d" if v >= d else "e"
    a, b, c, d = cuts  # a: v≤a … e: v>d
    return "a" if v <= a else "b" if v <= b else "c" if v <= c else "d" if v <= d else "e"


def grade_strength(measured: float, design: float, damaged: bool = False) -> str:
    """콘크리트 강도(표 6.25/6.22): αc = 측정÷설계 ×100. a 100%↑ / b 100%↑(경미한 손상) / c 85~100 / d 70~85 / e 70 미만."""
    if not design:
        raise ValueError("설계기준강도가 없습니다.")
    r = measured / design * 100
    if r >= 100:
        return "b" if damaged else "a"
    return "c" if r >= 85 else "d" if r >= 70 else "e"


def grade_section(measured_area: float, design_area: float) -> str:
    """부재단면의 규격(표 6.24 신판·6.33): c = 측정÷설계 ×100. a 100↑ / b 95~100 / c 90~95 / d 75~90 / e 75 미만."""
    if not design_area:
        raise ValueError("설계 단면적이 없습니다.")
    return _band(measured_area / design_area * 100, (100, 95, 90, 75), rising=True)


def grade_bolt(bad: int, total: int) -> str | None:
    """볼트 접합상태(SafetyMan 10/15 직접 확인): 누락·이완·풀림 볼트접합부 ÷ 조사 접합부. 0 a / 5% 미만 b / 10% 미만 c / 30% 미만 d / 30% 이상 e."""
    if not total:
        return None
    r = bad / total * 100
    return "a" if r <= 0 else "b" if r < 5 else "c" if r < 10 else "d" if r < 30 else "e"


def grade_fireproof(measured: float, design: float, damaged: bool = False) -> str:
    """내화피복(SafetyMan 10/15 직접 확인) — 강도와 같은 띠: 실제÷규준 100%↑ a(손상 b) / 85~100 c / 70~85 d / 70 미만 e."""
    return grade_strength(measured, design, damaged)


def mean_score(grades: list[str]) -> float | None:
    """등급들의 점수 평균(반올림 없음) — 강재 규격·내화피복 여러 부재(SafetyMan: b·a → 2.0)."""
    gs = [g for g in grades if g]
    return sum(SCORE[g] for g in gs) / len(gs) if gs else None


def count_score(counts: dict[str, int]) -> float | None:
    """개수 표(A~E) → 점수 평균(반올림·최소범위 없음) — 용접 접합상태·강재 부식도(SafetyMan: a9·b1 → 1.2, a8·d2 → 2.2)."""
    n = sum(int(v or 0) for v in counts.values())
    return sum(SCORE[g] * int(counts.get(g) or 0) for g in GRADES) / n if n else None


def steel_condition(scores: dict[str, float | None]) -> float | None:
    """강재 부재 상태 = 강재 항목 점수들의 Choquet(STEEL_G). 항목이 하나면 그 점수."""
    pairs = [(float(v), STEEL_G[k]) for k, v in (scores or {}).items() if v is not None and k in STEEL_G]
    return choquet(pairs) if pairs else None


def grade_crack(width_mm: float, area_pct: float = 0.0) -> str:
    """콘크리트 균열(표 6.23): 최대 균열폭 cw(mm) — 면적률 20% 이상이면 한 등급 내림(판재만). 0.1/0.2/0.3/0.5."""
    g = "a" if width_mm < 0.1 else "b" if width_mm < 0.2 else "c" if width_mm < 0.3 else "d" if width_mm < 0.5 else "e"
    if area_pct >= 20 and g != "a":
        g = GRADES[min(GRADES.index(g) + 1, 4)]
    return g


def grade_carbonation(ct_cm: float, cover_cm: float) -> str:
    """콘크리트 탄산화(표 6.27 신판·6.24): Ct(탄산화 깊이) ÷ D(철근 피복두께). ≤0.25D a / ≤0.5D b / ≤0.75D c / ≤D d / 초과 e."""
    if not cover_cm:
        raise ValueError("철근 피복두께가 없습니다.")
    return _band(ct_cm / cover_cm, (0.25, 0.5, 0.75, 1.0), rising=False)


def grade_scaling(depth_mm: float, area_pct: float = 0.0) -> str:
    """박리(표 6.27 구판): 깊이 sc(mm) 0 / <0.5 / <1.0 / <25 / ≥25, 면적률 10% 이상이면 한 등급 내림."""
    g = "a" if depth_mm <= 0 else "b" if depth_mm < 0.5 else "c" if depth_mm < 1.0 else "d" if depth_mm < 25 else "e"
    if area_pct >= 10 and g != "a":
        g = GRADES[min(GRADES.index(g) + 1, 4)]
    return g


def grade_spalling(depth_mm: float, area_pct: float = 0.0) -> str:
    """박락·층분리(표 6.28): 깊이 sd(mm) 0 / <15 / <20 / <25 / ≥25(조골재 손실), 면적률 20% 이상이면 한 등급 내림."""
    g = "a" if depth_mm <= 0 else "b" if depth_mm < 15 else "c" if depth_mm < 20 else "d" if depth_mm < 25 else "e"
    if area_pct >= 20 and g != "a":
        g = GRADES[min(GRADES.index(g) + 1, 4)]
    return g


def grade_leak(ratio_pct: float) -> str:
    """누수·백태(표 6.29, SafetyMan 줄): 없음 a / 경미 — 면적 5% 미만 b / 현저 — 10% 미만 c / 진행 관찰 — 20% 미만 d / 확연 — 20% 이상 e."""
    return "a" if ratio_pct <= 0 else "b" if ratio_pct < 5 else "c" if ratio_pct < 10 else "d" if ratio_pct < 20 else "e"


def grade_rebar_exposure(ratio_pct: float) -> str:
    """철근노출(표 6.30): 노출 면적률 ra(%) 0 / <1 / <3 / <5 / ≥5."""
    return "a" if ratio_pct <= 0 else "b" if ratio_pct < 1 else "c" if ratio_pct < 3 else "d" if ratio_pct < 5 else "e"


def grade_deflection(delta: float, span: float, damaged: bool = False) -> str:
    """부재 변위·변형(표 6.34 신판·6.31): 처짐 ÷ 경간. ≤L/480 a(경미한 손상 b) / ≤L/240 c / ≤L/150 d / 초과 e."""
    if not span:
        raise ValueError("경간 길이가 없습니다.")
    r = delta / span
    if r <= 1 / 480:
        return "b" if damaged else "a"
    return "c" if r <= 1 / 240 else "d" if r <= 1 / 150 else "e"


def grade_tilt(ratio: float) -> str:
    """건축물 기울기·부동침하 각변위(표 6.35 신판·6.32): 변위량÷높이(거리). ≤1/750 a / ≤1/500 b / ≤1/250 c / ≤1/150 d / 초과 e."""
    return _band(ratio, (1 / 750, 1 / 500, 1 / 250, 1 / 150), rising=False)


def worst(*grades: str | None) -> str | None:
    """여러 등급 중 나쁜 것(표면노후 = 박리·박락·누수·철근노출의 최솟값, 강재 규격·강도도 낮은 쪽)."""
    gs = [g for g in grades if g]
    return max(gs, key=GRADES.index) if gs else None


def score_grade(score: float) -> str:
    """평가점수(1~9) → 등급: 자리 = (점수 - 1) / 2 를 **0.5 올림**(SafetyMan 직접 비교 10/15 — 파이썬 round는 0.5를 짝수로 보내 a·b 평균 2.0이 a가 됐음, SafetyMan은 b)."""
    return GRADES[min(4, max(0, math.floor((score - 1) / 2 + 0.5 + 1e-9)))]


def mean_grade(grades: list[str]) -> str:
    """단위부재 여러 측정값의 평가점수 평균 → 등급(표 6.21 "부재 평가점수 = 측정결과의 평균값")."""
    if not grades:
        raise ValueError("측정값이 없습니다.")
    return score_grade(sum(SCORE[g] for g in grades) / len(grades))


MIN_RANGE = {"기둥": 0.2, "내력벽": 0.2, "큰보": 0.3, "작은보": 0.3, "슬래브": 0.3, "테두리보": 0.3}  # 균열·표면노후 대푯값 최소범위(표 6.23)


def grade_from_counts(counts: dict[str, int], member: str, area_ge: int = 0) -> str | None:
    """균열·표면노후처럼 부재 개수를 등급 칸에 넣는 항목(SafetyMan 입력 방식) → 부재 대푯값.
    표 6.23: "결함·손상부재를 포함해 평가대상 부재수의 최소범위(기둥·벽 20%, 보·슬래브 30%)에 대한 결함·손상부재의 평가점수의 평균값" —
    나쁜 등급부터 최소범위 개수만큼 모아 점수 평균 → 등급. 예: 내력벽 a 4개 + b 1개 → 최소범위 1개 = b(조훈빌딩 SafetyMan 3.00과 일치).
    area_ge = 균열 면적률 20% 이상 부재 수(SafetyMan 균열 "면적율" 표) — 평균 점수 × (1 + 0.1 × area_ge ÷ 전체 개수)
    (10/15 SafetyMan 직접 비교 — 개수 0~10을 하나씩 바꾼 표로 확인: a7·b2·c1은 10개 다일 때만 b→c, a5·b1·c1·d2·e1은 5개부터 d→e,
    a7·c3 + 10개 → c 그대로 / a26·e1 + 23개 → b)."""
    total = sum(int(v or 0) for v in counts.values())
    if total <= 0:
        return None
    n = max(1, math.ceil(total * MIN_RANGE.get(member, 0.3) - 1e-9))
    picked: list[str] = []
    for g in reversed(GRADES):
        for _ in range(int(counts.get(g) or 0)):
            if len(picked) < n:
                picked.append(g)
    return score_grade(sum(SCORE[g] for g in picked) / len(picked) * (1 + 0.1 * int(area_ge or 0) / total))


# ---------- 2) 부재 상태평가(퍼지 합성 — 요령 2.1.1·2.2.2, 내구성계수 Table p151~152) ----------

# 항목 등급(행 a~e) → 종합 노후도 DM 등급(열 a~e)에 대한 가능성
_IDENT = [[1, 0, 0, 0, 0], [0, 1, 0, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 0, 1]]
RELATION = {
    "CA": [[1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [0.75, 1, 0.5, 0.25, 0], [0.5, 0.75, 1, 0.5, 0]],  # 중성화(탄산화) ARM
    "CL": [[1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [0.75, 1, 0.25, 0, 0], [0.25, 0.75, 1, 0.75, 0], [0, 0.25, 0.75, 1, 0.75]],  # 염화물 LRM
    "DS": [[1, 0.06, 0.06, 0, 0], [1, 0.06, 0.06, 0, 0], [0.75, 0.25, 0.25, 0.25, 0.25], [0.75, 0.5, 0.5, 0.5, 0.5], [0.75, 0.5, 0.5, 0.5, 0.5]],  # 강도 SRM
    "CR": _IDENT,  # 균열 RRM(요령 예제 p169 — 판재 RsRM과 같은 항등 관계; p152의 RnRM은 쓰지 않음 — SafetyMan 결과로 확인할 것)
    "SD": [[0.5, 0.06, 0.06, 0, 0], [0.5, 0.06, 0.06, 0, 0], [0.5, 0.25, 0.25, 0.25, 0.06], [0.5, 0.5, 0.25, 0.25, 0.06], [0.5, 0.5, 0.5, 0.5, 0.06]],  # 표면노후 DRM
    "CO": _IDENT,  # 철근부식 ORM
}
ITEM_LABEL = {"DS": "콘크리트 강도", "CR": "균열", "CA": "탄산화", "SD": "표면노후", "CL": "염화물", "CO": "철근부식"}
# 콘크리트 부재단면 규격(2023판 표 6.24)은 보고서 재료시험에서 a~e로 평가만 하고 상태평가 점수엔 넣지 않음(민재형 10/13 — SafetyMan에도 없음, 국토부 미개정)


def member_condition(items: dict[str, str | None]) -> dict:
    """부재 하나의 상태평가 — items = {"DS": "b", "CR": "c", "CA": "d", "SD": "d", ...}(없는 항목은 None·생략).
    돌려주는 값: {score 대표값(1·3·5·7·9), possibility 등급별 가능성, grade}."""
    used = {k: g for k, g in items.items() if g}
    if not used:
        raise ValueError("평가할 항목이 없습니다.")
    poss = [0.0] * 5
    for key, g in used.items():
        row = RELATION[key][GRADES.index(g)]  # one-hot × 관계행렬의 max-min 합성 = 그 등급 행
        poss = [max(p, r) for p, r in zip(poss, row)]
    # μDT(x) = max_g min(poss[g], 삼각(x)). 대표값 = μ가 최대 높이(= 가장 큰 가능성)에 닿는 가장 오른쪽 x(실수) → 0.5는 올림.
    # SafetyMan을 돌려 맞춘 규칙(10/13, 작업내용 43차): 높이 1이면 가능성 1인 등급 중 가장 오른쪽 꼭짓점(지침 예제 5·7·3, 탄산화 d→3·e→5),
    # 강도 c·d·e만 있는 부재(높이 0.75 → x=1.5)는 2.0(조훈빌딩 슬래브·다산 시험), 표면노후만 있는 부재(높이 0.5)는 평가 제외("-").
    # 예전 "0.75 수준집합의 가장 큰 정수 x"는 강도만 있을 때 1을 내서 SafetyMan과 달랐음.
    hgt = max(poss)
    if hgt < ALPHA:
        return {"score": None, "possibility": dict(zip(GRADES, poss)), "grade": None, "items": used}
    top = max(i for i in range(5) if poss[i] == hgt)
    best = math.floor(2 * top + 1 + (1 - hgt) * 2 + 0.5)
    return {"score": float(best), "possibility": dict(zip(GRADES, poss)), "grade": grade_of(best), "items": used}


# ---------- 3·4) λ-퍼지척도 + Choquet 적분(요령 1.2.2·1.2.3) ----------

def fuzzy_lambda(gs: list[float]) -> float:
    """λ: ∏(1+λg_i) = 1+λ 의 해(λ>-1, g 합이 1보다 크면 음수). 예: 0.9·0.7·0.3 → -0.9715."""
    gs = [g for g in gs if g > 0]
    if len(gs) <= 1:
        return 0.0
    f = lambda lam: math.prod(1 + lam * g for g in gs) - (1 + lam)  # noqa: E731
    lo, hi = -1 + 1e-9, 1e6
    if abs(sum(gs) - 1) < 1e-9:
        return 0.0
    if sum(gs) > 1:  # 대체적 — λ∈(-1, 0)
        lo, hi = -1 + 1e-9, 0.0
    else:
        lo, hi = 0.0, 1e6
    flo = f(lo)
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def g_union(gs: list[float], lam: float) -> float:
    """합집합의 척도 g(A∪B∪…) = (∏(1+λg) - 1)/λ (λ=0이면 합)."""
    gs = [g for g in gs if g > 0]
    if not gs:
        return 0.0
    if abs(lam) < 1e-12:
        return min(1.0, sum(gs))
    return (math.prod(1 + lam * g for g in gs) - 1) / lam


def choquet(pairs: list[tuple[float, float]]) -> float:
    """Choquet 적분 — pairs = [(점수 h, 중요도 g)]. h 내림차순 x1≥x2≥…: Σ [h(x_i) - h(x_{i+1})]·g({x1..xi}), h(x_{n+1}) = 0.
    예: (3, .9) (7, .7) (5, .3) → 5.99."""
    pairs = [(h, g) for h, g in pairs if g > 0 and h is not None]
    if not pairs:
        raise ValueError("점수가 없습니다.")
    if len(pairs) == 1:  # 하나뿐이면 그 점수(전체 집합 척도 = 1) — 철골조 묶음 부재 하나·표본층 하나·상태만 있는 종합(10/15 SafetyMan 직접 비교, 예전엔 점수×중요도)
        return float(pairs[0][0])
    lam = fuzzy_lambda([g for _, g in pairs])
    order = sorted(pairs, key=lambda p: -p[0])
    total, prefix = 0.0, []
    for i, (h, g) in enumerate(order):
        prefix.append(g)
        nxt = order[i + 1][0] if i + 1 < len(order) else 0.0
        total += (h - nxt) * min(1.0, g_union(prefix, lam))
    return total


def importance_rep(ratio: float) -> float:
    """중요도 산정 기준(표 1-1): 비율 → 대표값 0.9/0.7/0.5/0.3/0.1."""
    return 0.9 if ratio >= 0.8 else 0.7 if ratio >= 0.6 else 0.5 if ratio >= 0.4 else 0.3 if ratio >= 0.2 else 0.1


def floor_importance(floor: int, above: int, below: int) -> float:
    """층 중요도(요령 1.3.4): ζn = (N-(n-1))/N, N = 지하 포함 전체 층수, n = 아래서부터 센 층 번호(지하 n층 = 1 …). floor는 -3, -1, 1, 5 처럼."""
    n_total = above + below
    n = (floor + below) if floor < 0 else (below + floor)  # 지하 -k층 → k번째(아래서), 지상 k층 → below + k
    n = max(1, min(n_total, n))
    return importance_rep((n_total - (n - 1)) / n_total)


# ---------- 5) 건물 전체 ----------

@dataclass
class Member:
    kind: str  # 기둥·내력벽·큰보·작은보·슬래브·테두리보
    items: dict = field(default_factory=dict)  # 상태평가 항목 등급 {"DS": "a", …}
    safety: str | None = None  # 안전성 등급 a~e(정밀안전진단) — 없으면 상태만
    steel: dict = field(default_factory=dict)  # 강재 항목 점수 {"SS": 2.0, "WE": 1.2, …}(철골조·SRC 기둥·큰보·작은보)


@dataclass
class Floor:
    label: str  # "5층(1층~5층)"
    floor: int  # 대표 층(지하는 음수) — 층 중요도
    members: list[Member] = field(default_factory=list)
    structure: str = "라멘(RC)"
    material: str = "RC"  # RC·SRC·철골 — 부재 점수에 쓰는 항목이 달라짐(member_score)


def member_score(m: Member, material: str = "RC") -> float | None:
    """층 합산에 쓰는 부재 상태 점수 — SafetyMan 구조재료별(10/15 직접 확인):
    철골조 = 기둥·큰보·작은보는 강재 항목만(콘크리트 항목은 안 씀, 강재 없으면 제외), 내력벽 제외, 슬래브 등은 콘크리트 /
    SRC = 큰보·작은보는 콘크리트·강재 중 큰 점수, 기둥 등은 콘크리트만 / RC = 콘크리트만(강재 항목은 안 씀)."""
    rc = member_condition(m.items)["score"] if any(m.items.values()) else None
    st = steel_condition(m.steel) if m.steel else None
    if material == "철골":
        return st if m.kind in STEEL_KINDS else None if m.kind == "내력벽" else rc
    if material == "SRC" and m.kind in ("큰보", "작은보"):
        vals = [x for x in (rc, st) if x is not None]
        return max(vals) if vals else None
    return rc


@dataclass
class Building:
    above: int
    below: int
    floors: list[Floor]
    tilt: str | None = None  # 건물 기울기 등급 a~e
    settlement: str | None = None  # 부동침하 등급
    kind: str = "정밀점검"  # 정밀점검 / 정밀안전진단


def evaluate(b: Building) -> dict:
    """건물 평가 → SafetyMan 갑지와 같은 구조: floors[{label, g, members[{kind, condition, safety, total}], condition, safety, total}],
    condition(전체 상태), safety, deform(기울기 및 침하), total(종합), 각각 score·grade."""
    out_floors = []
    for f in b.floors:
        g_f = floor_importance(f.floor, b.above, b.below)
        rows = []
        for m in f.members:
            cond = member_score(m, f.material)
            saf = float(SCORE[m.safety]) if m.safety else None
            tot = choquet([(saf, G_SAFETY), (cond, G_CONDITION)]) if saf is not None and cond is not None else (cond if cond is not None else saf)
            rows.append({"kind": m.kind, "g": MEMBER_G.get(m.kind, 0.5), "condition": cond, "safety": saf, "total": tot})
        fc = choquet([(r["condition"], r["g"]) for r in rows if r["condition"] is not None]) if any(r["condition"] is not None for r in rows) else None
        fs = choquet([(r["safety"], r["g"]) for r in rows if r["safety"] is not None]) if any(r["safety"] is not None for r in rows) else None
        ft = choquet([(fs, G_SAFETY), (fc, G_CONDITION)]) if fs is not None and fc is not None else (fc if fc is not None else fs)
        out_floors.append({"label": f.label, "floor": f.floor, "structure": f.structure, "g": g_f, "members": rows,
                           "condition": fc, "safety": fs, "total": ft})
    cond = choquet([(x["condition"], x["g"]) for x in out_floors if x["condition"] is not None]) if any(x["condition"] is not None for x in out_floors) else None
    saf = choquet([(x["safety"], x["g"]) for x in out_floors if x["safety"] is not None]) if any(x["safety"] is not None for x in out_floors) else None
    deform = max([SCORE[g] for g in (b.tilt, b.settlement) if g], default=None)  # 변위·변형 = 둘 중 큰 결함점수(요령 2.4)
    parts = [(saf, G_SAFETY), (cond, G_CONDITION), (float(deform) if deform is not None else None, G_DEFORM)]
    total = choquet([(h, g) for h, g in parts if h is not None])
    fmt = lambda x: None if x is None else {"score": round(x, 2), "grade": grade_of(x)}  # noqa: E731
    return {"kind": b.kind, "floors": out_floors, "condition": fmt(cond), "safety": fmt(saf), "deform": fmt(deform), "total": fmt(total)}


# ---------- 재료시험 표본 수량(2021 세부지침 표 6.19·6.20·6.3.3) ----------

def sample_floors(total_floors: int, total_area: float, kind: str = "정밀안전점검") -> int:
    """표본층 수 — 층수(지하 포함) 기준과 연면적 기준 중 큰 것. 정밀안전점검: 1~10층 2, 11~20층 3, 21~30층 4, 31층↑ 10층마다 +1 /
    연면적 ~24,999 2, ~49,999 3, ~75,000 4, 75,001↑ 25,000마다 +1. 정밀안전진단은 3·4·6·(+2)."""
    diag = kind == "정밀안전진단"
    if total_floors <= 10:
        by_floor = 3 if diag else 2
    elif total_floors <= 20:
        by_floor = 4 if diag else 3
    elif total_floors <= 30:
        by_floor = 6 if diag else 4
    else:
        by_floor = (6 if diag else 4) + ((total_floors - 31) // 10 + 1) * (2 if diag else 1)
    if total_area < 25000:
        by_area = 3 if diag else 2
    elif total_area < 50000:
        by_area = 4 if diag else 3
    elif total_area <= 75000:
        by_area = 6 if diag else 4
    else:
        by_area = (6 if diag else 4) + (int((total_area - 75001) // 25000) + 1) * (2 if diag else 1)
    return max(by_floor, by_area)


def sample_quantities(floors: int) -> dict:
    """표본층 수 → 조사 기준 수량(정밀안전점검): 강도 = 층 × 2종 부재 × 2개소(단부·중앙부), 부재규격 = 층 × 2종 × 3개소, 탄산화 = 층 × 2종 × 1개소."""
    return {"strength": floors * 2 * 2, "section": floors * 2 * 3, "carbonation": floors * 2 * 1}


# ---------- 검증(지침 예제 + SafetyMan 다산은혜교회) ----------

def _selfcheck() -> None:
    # 요령 2.2.2 예제 — 부재별 대표값: 슬래브 5, 보 7, 기둥 3
    assert member_condition({"CA": "d", "CL": "b", "DS": "b", "CR": "c", "SD": "d", "CO": "c"})["score"] == 5
    assert member_condition({"CA": "c", "CL": "b", "DS": "b", "CR": "d", "SD": "c", "CO": "d"})["score"] == 7
    assert member_condition({"CA": "d", "CL": "b", "DS": "b", "CR": "b", "SD": "c", "CO": "b"})["score"] == 3
    # 2.2.3 층별: 기둥3·보7·슬래브5 → 5.99, λ = -0.9715
    assert abs(fuzzy_lambda([0.9, 0.7, 0.3]) + 0.9715) < 0.001
    assert abs(choquet([(3, 0.9), (7, 0.7), (5, 0.3)]) - 5.99) < 0.01
    # 2.2.4 전체: 7층(0.3) 5.99 · 2층(0.7) 3.6 · -2층(0.9) 5.6 → 5.59 ; 층 중요도(지하2·지상10)
    assert (floor_importance(7, 10, 2), floor_importance(2, 10, 2), floor_importance(-2, 10, 2)) == (0.3, 0.7, 0.9)
    assert abs(choquet([(5.99, 0.3), (3.6, 0.7), (5.6, 0.9)]) - 5.59) < 0.01
    # 2.3 안전성: 4.88 / 6.53, 2.5 종합: 6.42(λ=-0.989)
    assert abs(choquet([(5, 0.9), (3, 0.7), (5, 0.3)]) - 4.88) < 0.01
    assert abs(choquet([(4.88, 0.3), (7.19, 0.7), (5.0, 0.9)]) - 6.53) < 0.01
    assert abs(fuzzy_lambda([0.9, 0.7, 0.7]) + 0.989) < 0.001
    assert abs(choquet([(6.53, 0.9), (5.59, 0.7), (5.0, 0.7)]) - 6.42) < 0.01
    # p204 출력 예: 7층 기둥 안전성5·상태3 → 종합 4.80, 층 종합 = Choquet(안전 4.88, 상태 5.99) = 5.66
    assert abs(choquet([(5, G_SAFETY), (3, G_CONDITION)]) - 4.8) < 0.01
    assert abs(choquet([(4.88, G_SAFETY), (5.99, G_CONDITION)]) - 5.66) < 0.01
    # SafetyMan 다산은혜교회(지상5·지하3, 정밀점검): 상태 1.00(A), 기울기 및 침하 5.00(C) → 종합 3.80(B)
    b = Building(above=5, below=3, kind="정밀점검", tilt="c", settlement=None, floors=[
        Floor("-3층(-3층~-1층)", -3, [Member(k, {"DS": "a", "CR": "a", "CA": "a", "SD": "a"}) for k in ("기둥", "내력벽", "큰보", "작은보", "슬래브")]),
        Floor("5층(1층~5층)", 5, [Member(k, {"DS": "a", "CR": "a", "CA": "a", "SD": "a"}) for k in ("기둥", "내력벽", "큰보", "작은보", "슬래브")]),
    ])
    r = evaluate(b)
    assert r["condition"]["score"] == 1.0 and r["deform"]["score"] == 5.0 and r["total"]["score"] == 3.8 and r["total"]["grade"] == "B", r
    assert (r["floors"][0]["g"], r["floors"][1]["g"]) == (0.9, 0.1)
    # 조훈빌딩(2019, 지하2·지상16, 표본층 -2·8·16층) SafetyMan: 부재 점수(-2층 기둥1·내력벽3·큰보1·슬래브2 / 8층 1·1·1 / 16층 내력벽3·슬래브1) → 층 2.83·1.00·2.80,
    # 상태 2.68(B), 기울기·침하 1.00 → 종합 2.18(B). 층 중요도 -2층 0.9 · 8층 0.5 · 16층 0.1
    assert abs(choquet([(1, 0.9), (3, 0.9), (1, 0.7), (2, 0.3)]) - 2.83) < 0.01 and abs(choquet([(3, 0.9), (1, 0.3)]) - 2.8) < 0.01
    assert (floor_importance(-2, 16, 2), floor_importance(8, 16, 2), floor_importance(16, 16, 2)) == (0.9, 0.5, 0.1)
    assert abs(choquet([(2.83, 0.9), (1.0, 0.5), (2.8, 0.1)]) - 2.68) < 0.01 and abs(choquet([(2.68, G_CONDITION), (1.0, G_DEFORM)]) - 2.18) < 0.01
    # 조훈 부재: 기둥(강도 c 97.6% + 탄산화 a) 1, 내력벽(강도 c + 균열 a4·b1 → b + 표면노후 a) 3, 큰보(강도 c + 탄산화 b) 1
    assert grade_from_counts({"a": 4, "b": 1}, "내력벽") == "b" and grade_from_counts({"a": 48}, "기둥") == "a"
    assert member_condition({"DS": "c", "CA": "a"})["score"] == 1 and member_condition({"DS": "c", "CR": "b", "SD": "a"})["score"] == 3
    # 강재(10/15 SafetyMan .sfm 직접 — scratchpad sfm/t_steel_*.py): 항목 기준·중요도·평균, 구조재료별 부재 점수
    assert [grade_section(x, 100) for x in (105, 95, 94.9, 90, 89.9, 75, 74.9)] == ["a", "b", "c", "c", "d", "d", "e"]
    assert [grade_bolt(x, 1000) for x in (0, 5, 49, 50, 99, 100, 299, 300)] == ["a", "b", "b", "c", "c", "d", "d", "e"]
    assert [grade_fireproof(x, 2.0) for x in (2.4, 1.98, 1.7, 1.698, 1.4, 1.398)] == ["a", "c", "c", "d", "d", "e"] and grade_fireproof(2.0, 2.0, True) == "b"
    assert count_score({"a": 9, "b": 1}) == 1.2 and abs(count_score({"a": 8, "d": 2}) - 2.2) < 1e-9 and mean_score(["b", "a"]) == 2.0
    for st, want in (({"SS": 9, "WE": 1}, 5.0), ({"FP": 9, "SS": 1}, 3.4), ({"BO": 9, "SS": 1}, 6.6), ({"WE": 9, "SS": 1}, 6.6), ({"SC": 9, "SS": 1}, 8.2),
                     ({"SS": 2.0, "FP": 7, "WE": 8 / 6, "BO": 1}, 3.24), ({"SS": 7, "WE": 2.6, "SC": 1.4}, 4.63), ({"SS": 1, "BO": 7, "SC": 2.2}, 5.54)):
        assert abs(steel_condition(st) - want) < 0.006, (st, steel_condition(st))
    assert member_score(Member("기둥", {"CR": "e"}, steel={"SS": 1}), "철골") == 1 and member_score(Member("내력벽", {"CR": "e"}), "철골") is None
    assert member_score(Member("큰보", {"CR": "b"}, steel={"SS": 9}), "SRC") == 9 and member_score(Member("기둥", {"CR": "b"}, steel={"SS": 9}), "SRC") == 3
    assert member_score(Member("작은보", {"CR": "c"}, steel={"BO": 1, "WE": 5}), "SRC") == 5 and member_score(Member("큰보", {"CR": "a"}, steel={"SS": 9}), "RC") == 1
    assert member_condition({"DS": "c", "CA": "b"})["score"] == 1
    # 조훈 -2층 슬래브(강도 c 92.9%만) SafetyMan 2.00 — 10/13 SafetyMan을 다산 파일로 직접 돌려 확인(작업내용 43차):
    # 강도만 a·b → 1, c·d·e → 2 / 강도 a + 탄산화 c·d·e → 1·3·5 / 표면노후만(a·b) → "-"(제외) / 균열 d만 → 7(균열은 항등 관계)
    for g, want in (("a", 1), ("b", 1), ("c", 2), ("d", 2), ("e", 2)):
        assert member_condition({"DS": g})["score"] == want, (g, member_condition({"DS": g}))
    for g, want in (("c", 1), ("d", 3), ("e", 5)):
        assert member_condition({"DS": "a", "CA": g})["score"] == want
    assert member_condition({"SD": "a"})["score"] is None and member_condition({"SD": "b"})["score"] is None
    assert member_condition({"CR": "d"})["score"] == 7 and member_condition({"DS": "c", "CR": "a", "SD": "a"})["score"] == 1
    # 그때 층·전체: 작은보 2 → -3층 1.50, 전체 1.45 / 작은보 3 → 2.00(B) / 내력벽 7 → 6.40(D) / 균열 48개 중 b 7 → 최소범위 15개(올림) 평균 1.93 → a
    assert abs(choquet([(1, 0.9), (1, 0.9), (1, 0.7), (2, 0.5), (1, 0.3)]) - 1.5) < 0.01 and abs(choquet([(1.5, 0.9), (1.0, 0.1)]) - 1.45) < 0.01
    assert abs(choquet([(1, 0.9), (1, 0.9), (1, 0.7), (3, 0.5), (1, 0.3)]) - 2.0) < 0.01 and abs(choquet([(1, 0.9), (7, 0.9), (1, 0.7), (1, 0.5), (1, 0.3)]) - 6.4) < 0.01
    assert grade_from_counts({"a": 41, "b": 7}, "슬래브") == "a"
    # 10/15 SafetyMan 직접 비교(.sfm 만들어 평가 — scratchpad sfm/): 0.5 올림, 균열 면적률 20%↑ > a 개수면 올림, 하나뿐인 Choquet = 그 점수
    assert grade_from_counts({"a": 9, "b": 1}, "기둥") == "b" and grade_from_counts({"a": 8, "b": 1, "e": 1}, "기둥") == "d"  # 평균 2.0 → b, 6.0 → d
    assert grade_from_counts({"a": 28, "b": 1, "c": 1}, "내력벽") == "b"
    assert grade_from_counts({"a": 7, "b": 2, "c": 1}, "큰보", 10) == "c" and grade_from_counts({"a": 7, "b": 2, "c": 1}, "슬래브", 5) == "b"
    assert grade_from_counts({"a": 7, "c": 3}, "큰보", 10) == "c" and grade_from_counts({"a": 8, "b": 1, "c": 1}, "슬래브", 10) == "b"
    assert grade_from_counts({"a": 5, "b": 3, "c": 3, "d": 1, "e": 3}, "작은보", 6) == "e" and grade_from_counts({"a": 5, "b": 3, "c": 3, "d": 1, "e": 3}, "작은보", 1) == "d"
    assert grade_from_counts({"a": 19, "b": 12, "c": 7, "d": 5}, "슬래브", 36) == "d" and grade_from_counts({"a": 19, "b": 12, "c": 7, "d": 5}, "슬래브") == "c"
    assert grade_from_counts({"a": 26, "e": 1}, "큰보", 23) == "b" and grade_from_counts({"a": 9, "b": 10, "c": 7, "d": 6, "e": 5}, "큰보", 14) == "d"
    assert grade_from_counts({"a": 12, "b": 8, "c": 8, "d": 3, "e": 5}, "슬래브", 13) == "d" and grade_from_counts({"a": 2, "b": 4, "d": 2, "e": 1}, "작은보", 3) == "d"
    for area, want in ((9, "b"), (10, "c")):  # 면적률 개수 표(t_area): a7·b2·c1 보·슬래브
        assert grade_from_counts({"a": 7, "b": 2, "c": 1}, "큰보", area) == want, area
    for area, want in ((4, "d"), (5, "e")):  # a5·b1·c1·d2·e1
        assert grade_from_counts({"a": 5, "b": 1, "c": 1, "d": 2, "e": 1}, "슬래브", area) == want, area
    assert choquet([(6.35, 0.3)]) == 6.35 and choquet([(1.0, 0.7)]) == 1.0
    # 항목 등급
    assert grade_strength(27.6, 27) == "a" and grade_strength(27.6, 27, damaged=True) == "b" and grade_strength(20, 27) == "d"
    assert grade_carbonation(1.326, 6.1) == "a" and grade_carbonation(3.5, 6.1) == "c"
    assert grade_tilt(1 / 313) == "c" and grade_tilt(1 / 550) == "b" and grade_tilt(1 / 100) == "e"
    assert grade_crack(0.25) == "c" and grade_crack(0.25, 25) == "d"
    assert sample_floors(8, 6882) == 2 and sample_floors(15, 30000) == 3 and sample_floors(8, 30000) == 3 and sample_floors(8, 6882, "정밀안전진단") == 3
    print("상태평가 계산 검증 통과 — 지침 예제·SafetyMan 다산은혜교회 결과와 일치")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    _selfcheck()
