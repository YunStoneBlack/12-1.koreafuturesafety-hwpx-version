"""지도 출장 자동 배치(2026-10-01 사용자와 정한 규칙) — DB 없이 도는 순수 계산. 저장·API는 server/api/routers/auto_plan.py.

규칙
- 남은 회차 = 총 횟수 − 최근 보고서 회차(진행 막대와 같은 기준) − 이미 잡힌 "사람이 정한"(고정) 앞으로의 예정 수.
- 기준일(오늘, 공사 시작 전이면 시작일, 최근 지도일이 더 늦으면 그날)부터 마감(준공일 − 설정 일수, 기본 14일)까지 고르게 나눈다
  (첫 지도는 기준일 + 한 간격 — "등록 후 한 간격 안"). 고정 예정이 있으면 그 날짜에 가장 가까운 자리를 고정 예정이 차지한다.
- 가는 날에서 빼는 날: 주말, 공휴일, 공휴일과 주말(또는 공휴일) 사이에 낀 평일(목 공휴 → 금, 화 공휴 → 월), 평일 공휴일이 3일 이상인 주는 월~금 전부.
- **같이 가기 좋은 현장**은 날짜를 모은다(요원과 상관없이 — 2026-10-02) — 각 회차는 목표일 ± 간격의 1/3 안에서 움직일 수 있고,
  그 안에 그런 현장 출장이 이미 있거나(고정 예정·앞서 고른 날) 그런 현장의 다른 회차도 올 수 있는 날을 고른다. 묶음은 매번 새로 짠다.
  같이 가기 좋음 = 같은 시·군이면서 도로 거리 30km 이내(설정). 시·군이 달라도 70km 이내(설정)면 자리가 없을 때 묶는다(2026-10-02,
  예전 12km — 인천·파주는 묶고 인천·속초는 다른 날로).
  도로 거리는 카카오 길찾기(server/api/geocode.py, 실패하면 직선거리). 좌표가 없는 현장은 예전처럼 시·군이 같으면 같이 가기 좋음.
- **출장자 ≠ 보고서 담당자(2026-10-02, server/api/report_staff.py)**: 출장은 한 사람 한도 없음, 회사 하루 = 요원 수 × 4곳. 그날 같은 지역 출장이
  있으면 그 사람이 붙여서 가고, 없으면 빈 사람(1순위 = 직전 회차 보고서 담당 → 현장 담당, 아니면 보고서 담당 순서)이 새 지역을 맡는다.
  새로 만든 묶음은 마지막에 그 현장들의 1순위 중 가장 많은 사람으로(그날 비어 있으면). 정석 규칙(요원별 하루 4곳, 자기 현장만)은 태그 standard-rules-20261002.
- 한 현장은 하루 한 번, 회차 순서대로.
- 한 사람의 그날 현장은 **서로 70km(설정) 안끼리만**(속초·김포를 한날로 잡던 것 — 2026-10-01 실데이터 미리보기에서 발견).
- **하루 출장 인원 = 회사 전체 2명(설정)**(2026-10-02 사용자: 비상 인력을 남김) — 그날 이미 그만큼 나가면 새 사람을 안 내보내고, 그 사람들에게
  붙일 수 없으면 다른 날로.
- 목표 범위에 자리가 없으면 마감(없으면 준공일 전날)까지 가장 가까운 가능한 날로, 그래도 없으면 "넣을 날 부족"으로 남긴다
  (막지 않고 안내만 — 사용자: 횟수를 다 못 채워도 큰일은 아님). 예전 "⚠ 대타 필요"(담당 없이 넣기)는 출장자를 고를 수 있게 되며 안 생긴다.
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from dataclasses import dataclass, field

DAY = datetime.timedelta(days=1)
DEFAULT_FINISH_BEFORE_DAYS = 14

_REGION_RE = re.compile(r"^\S+(시|군)$")
_PROVINCES = {"경기", "경기도", "강원", "강원도", "강원특별자치도", "충북", "충청북도", "충남", "충청남도", "전북", "전라북도", "전북특별자치도",
              "전남", "전라남도", "경북", "경상북도", "경남", "경상남도", "제주", "제주도", "제주특별자치도"}


def region_of(address: str) -> str:
    """주소에서 시·군("경기 포천시 소흘읍…" → "포천시"). 서울·광역시·세종은 도시 이름 그대로, 못 찾으면 ""(묶지 않음)."""
    for tok in (address or "").replace(",", " ").split():
        if tok in _PROVINCES:
            continue
        if _REGION_RE.match(tok):
            return tok
    return ""


def korean_holidays(years) -> dict[datetime.date, str]:
    import holidays  # 대체공휴일·선거일 포함(그룹웨어 달력보다 최신 — 제헌절 2026 부활 등)

    return {d: n for d, n in holidays.KR(years=sorted(set(years)), language="ko").items()}


def blocked_days(start: datetime.date, end: datetime.date, holidays_: dict[datetime.date, str]) -> dict[datetime.date, str]:
    """start~end 사이 출장 못 가는 날 → 이유(주말·공휴일 이름·징검다리·연휴 주)."""
    out: dict[datetime.date, str] = {}
    first = start - datetime.timedelta(days=start.weekday())  # 그 주 월요일부터(주 단위 판단)
    d = first
    while d <= end + DAY * 7:
        if d.weekday() >= 5:
            out[d] = "주말"
        elif d in holidays_:
            out[d] = holidays_[d]
        d += DAY
    # 평일 공휴일 3일 이상인 주 → 월~금 전부
    week = first
    while week <= end:
        days = [week + DAY * i for i in range(5)]
        if sum(1 for x in days if x in holidays_) >= 3:
            for x in days:
                out.setdefault(x, "연휴 주")
        week += DAY * 7
    # 징검다리: 쉬는 날 사이에 낀 평일 하루(공휴일이 하나라도 끼어야 — 그냥 주말 사이 평일은 없음)
    d = first
    while d <= end + DAY * 7:
        if d not in out and d.weekday() < 5:
            prev, nxt = d - DAY, d + DAY
            if prev in out and nxt in out and (prev in holidays_ or nxt in holidays_):
                out[d] = "징검다리"
        d += DAY
    return {k: v for k, v in out.items() if start <= k <= end}


@dataclass
class SiteIn:
    id: int
    name: str
    staff_id: int | None
    region: str
    period_start: datetime.date | None
    period_end: datetime.date | None
    total: int | None
    performed: int  # 최근 보고서 회차
    last_date: datetime.date | None  # 최근 지도일
    fixed: list[datetime.date] = field(default_factory=list)  # 이 현장의 고정(사람이 정한) 앞으로의 예정


@dataclass
class Placed:
    site_id: int
    staff_id: int | None
    date: datetime.date
    need_sub: bool = False  # 담당 요원은 먼 현장과 섞어야만 갈 수 있음 → 담당 없이 "⚠ 대타 필요"(staff_id None)


@dataclass
class SiteResult:
    site_id: int
    needed: int  # 이번에 넣어야 할 회차 수
    placed: int  # 담당 요원으로 넣은 회차
    note: str = ""  # "넣을 날 부족"·"대타 필요" 안내(막지 않음)
    need_sub: int = 0  # "⚠ 대타 필요"로 넣은 회차


def _targets(base: datetime.date, end: datetime.date, count: int) -> list[datetime.date]:
    span = (end - base).days
    return [base + datetime.timedelta(days=round(span * k / count)) for k in range(1, count + 1)]


SAME, NEAR, FAR = "same", "near", "far"
DEFAULT_FAR_KM = 30.0   # 같은 시·군이면서 도로 거리가 이 안이면 같이 가기 좋음(먼저 묶음)
DEFAULT_TRIP_KM = 70.0  # 한 사람의 그날 현장끼리 도로 거리가 이 안이면 시·군이 달라도 묶음(자리 없을 때), 넘으면 다른 날로


def make_compat(regions: dict[int, str], dist=None, far_km: float = DEFAULT_FAR_KM, trip_km: float = DEFAULT_TRIP_KM):
    """두 현장을 한 사람이 한날 갈 수 있는지 — SAME(같이 가기 좋음) / NEAR(자리 없을 때 묶음) / FAR(안 묶음, 다른 날로), 거리(km, 모르면 None).
    dist(a, b) = 두 현장 사이 도로 거리 km(server/api/geocode.RoadDistance — 좌표 모르면 None). 거리가 있으면
    같은 시·군 ≤ far_km = SAME, (시·군 상관없이) ≤ trip_km = NEAR(2026-10-02 사용자: 인천·파주 OK, 인천·속초 안 됨), 넘으면 FAR.
    거리를 모르면 예전처럼 시·군으로(같으면 SAME, 다르면 FAR). 지역을 모르는 현장은 NEAR(막지는 않되 일부러 묶지도 않음)."""
    memo: dict[tuple[int, int], tuple[str, float | None]] = {}

    def compat(a: int, b: int) -> tuple[str, float | None]:
        if (a, b) in memo:
            return memo[(a, b)]
        memo[(a, b)] = memo[(b, a)] = out = _compat(a, b)
        return out

    def _compat(a: int, b: int) -> tuple[str, float | None]:
        ra, rb = regions.get(a, ""), regions.get(b, "")
        d = dist(a, b) if dist else None
        if d is not None:
            if ra and ra == rb and d <= far_km:
                return SAME, d
            return (NEAR if d <= trip_km else FAR), d
        if not ra or not rb:
            return NEAR, None
        return (SAME if ra == rb else FAR), None

    return compat


def plan_sites(
    sites: list[SiteIn],
    today: datetime.date,
    busy: dict[tuple[int, datetime.date], set[int]],
    finish_before_days: int = DEFAULT_FINISH_BEFORE_DAYS,
    day_cap: int = 16,
    holidays_: dict[datetime.date, str] | None = None,
    site_regions: dict[int, str] | None = None,
    dist=None,
    far_km: float = DEFAULT_FAR_KM,
    trip_km: float = DEFAULT_TRIP_KM,
    staff_order: list[int] | None = None,
    day_sites: dict[datetime.date, set[int]] | None = None,
    max_travelers: int = 2,
) -> tuple[list[Placed], list[SiteResult]]:
    """sites의 남은 회차를 배치한다(출장자는 그날 묶음마다 고른다 — 2026-10-02).

    busy: (출장자, 날짜) → 그날 가는 현장들(다녀온 방문·남기는 예정 — 새로 넣는 건 여기에 더해 간다). 묶기의 기준점도 여기서 본다.
    day_sites: 날짜 → 회사 전체 그날 가는 현장들(요원 없는 예정 포함) — 회사 하루 한도(day_cap = 요원 수 × 4).
    staff_order: 출장 갈 수 있는 요원(보고서 담당 순서). site.staff_id = 1순위(직전 회차 보고서 담당 → 현장 담당).
    max_travelers: 하루 출장 인원(회사 전체) — 그날 이만큼 나가면 새 사람(빈 사람)을 안 내보낸다(이미 넘은 날의 사람이 정한 예정은 그대로).
    site_regions: 현장 → 시·군(busy에 든 다른 현장까지, sites의 지역은 저절로 들어간다). dist(a, b): 도로 거리 km(모르면 None — 시·군으로).
    """
    ends = [s.period_end for s in sites if s.period_end]
    if not ends:
        return [], [SiteResult(s.id, 0, 0, "공사 기간이 없어 배치하지 않았습니다") for s in sites]
    horizon = max(ends)
    hol = holidays_ if holidays_ is not None else korean_holidays(range(today.year, horizon.year + 1))
    blocked = blocked_days(today, horizon, hol)
    busy = defaultdict(set, {k: set(v) for k, v in busy.items()})
    on_day: dict[datetime.date, set[int]] = defaultdict(set, {k: set(v) for k, v in (day_sites or {}).items()})
    for (_, d), here in busy.items():
        on_day[d] |= here
    regions = dict(site_regions or {})
    regions.update({s.id: s.region for s in sites})
    compat = make_compat(regions, dist, far_km, trip_km)
    people = list(staff_order or [])
    for s in sites:  # 1순위가 순서 목록에 없으면(쉬는 요원 등) 뒤에
        if s.staff_id is not None and s.staff_id not in people:
            people.append(s.staff_id)

    def kind_with(site: SiteIn, here: set[int]) -> str:
        kinds = {compat(site.id, x)[0] for x in here}
        return "empty" if not kinds else FAR if FAR in kinds else NEAR if NEAR in kinds else SAME

    crew: dict[datetime.date, set[int]] = defaultdict(set)  # 날짜 → 그날 출장 나가는 사람(하루 출장 인원 세기)
    for (x, d), here in busy.items():
        if here:
            crew[d].add(x)

    def travelers(d: datetime.date) -> int:
        return len(crew[d])

    def choose(site: SiteIn, d: datetime.date, allow: tuple[str, ...]) -> tuple[str, int] | None:
        """그날 이 현장을 누가 가면 되는지 — 같은 지역 출장(SAME)에 붙이기 → 빈 사람(1순위 → 순서, 하루 출장 인원이 남을 때만)
        → 70km 안 다른 시·군 출장(NEAR)."""
        by_kind: dict[str, list[int]] = defaultdict(list)
        for x in people:
            by_kind[kind_with(site, busy[(x, d)])].append(x)
        if travelers(d) >= max_travelers:
            by_kind.pop("empty", None)
        for k in (SAME, "empty", NEAR):
            if k in allow and by_kind[k]:
                cands = by_kind[k]
                if site.staff_id in cands:
                    return k, site.staff_id
                if k == "empty":
                    return k, cands[0]
                return k, max(cands, key=lambda x: len(busy[(x, d)]))  # 붙일 데가 여럿이면 많이 가는 사람에게
        return None

    def ok_day(site: SiteIn, d: datetime.date, after: datetime.date, allow: tuple[str, ...]) -> bool:
        if d <= after or d <= today or d in blocked:
            return False
        if site.id in on_day[d] or len(on_day[d]) >= day_cap:
            return False
        return choose(site, d, allow) is not None

    # 1) 현장마다 회차 자리(목표일·움직일 폭) 만들기
    slots = []  # (site, 목표일, 폭, 마감)
    results: dict[int, SiteResult] = {}
    for s in sites:
        if not s.total or not s.period_end:
            results[s.id] = SiteResult(s.id, 0, 0, "총 횟수나 공사 기간이 없어 배치하지 않았습니다")
            continue
        fixed = sorted(d for d in s.fixed if d > today)
        need = s.total - s.performed - len(fixed)
        if need <= 0:
            results[s.id] = SiteResult(s.id, 0, 0)
            continue
        if s.period_end <= today:
            results[s.id] = SiteResult(s.id, need, 0, "공사 기간이 끝나 배치하지 않았습니다")
            continue
        base = max(today, s.period_start or today, s.last_date or today)
        end = s.period_end - datetime.timedelta(days=finish_before_days)
        if end <= base:  # 마감이 이미 지났으면 준공일 전날까지
            end = max(s.period_end - DAY, base + DAY)
        all_targets = _targets(base, end, need + len(fixed))
        for f in fixed:  # 고정 예정이 가장 가까운 자리를 차지
            all_targets.remove(min(all_targets, key=lambda t: abs((t - f).days)))
        step = (end - base).days / (need + len(fixed))
        tol = max(1, round(step / 3))
        results[s.id] = SiteResult(s.id, need, 0)
        for t in all_targets:
            slots.append((s, t, tol, end))

    # 2) 목표일 순서로 하나씩 — 같은 지역 출장이 이미 있거나, 같은 지역 다른 현장의 회차도 올 수 있는 날을 우선
    slots.sort(key=lambda x: (x[1], x[0].id))
    last_by_site: dict[int, datetime.date] = {}
    placed: list[Placed] = []
    pending = [(s.id, t - datetime.timedelta(days=tol), t + datetime.timedelta(days=tol)) for s, t, tol, _ in slots]
    STRICT, WITH_NEAR = ("empty", SAME), ("empty", SAME, NEAR)

    for s, t, tol, end in slots:
        pending.remove((s.id, t - datetime.timedelta(days=tol), t + datetime.timedelta(days=tol)))
        after = last_by_site.get(s.id, datetime.date.min)
        lo, hi = max(t - datetime.timedelta(days=tol), today + DAY), min(t + datetime.timedelta(days=tol), end)
        window = [lo + DAY * i for i in range((hi - lo).days + 1)] if hi >= lo else []

        def score(d: datetime.date):
            got = choose(s, d, WITH_NEAR)
            join = got is not None and got[0] == SAME
            others = sum(1 for (sid, a, b) in pending if sid != s.id and a <= d <= b and compat(s.id, sid)[0] == SAME)
            return (-join, -others, abs((d - t).days), d)

        last_ok = max(end, s.period_end - DAY)
        start = after if after != datetime.date.min else today
        span = [start + DAY * i for i in range(1, (last_ok - start).days + 1)]
        day = allow_used = None
        # 폭 안(같은 지역·빈 사람만) → 폭 안(가까운 다른 시·군도) → 마감까지(좋은 곳만) → 마감까지(가까운 곳도)
        for days_, allow, by_score in ((window, STRICT, True), (window, WITH_NEAR, True), (span, STRICT, False),
                                       (span, WITH_NEAR, False)):
            cands = [d for d in days_ if ok_day(s, d, after, allow)]
            if cands:
                day = min(cands, key=score) if by_score else min(cands, key=lambda d: (abs((d - t).days), d))
                allow_used = allow
                break
        if day is None:
            continue  # 갈 날이 없음 → 아래에서 "넣을 날 부족"
        _, who = choose(s, day, allow_used)
        placed.append(Placed(s.id, who, day))
        last_by_site[s.id] = day
        results[s.id].placed += 1
        busy[(who, day)].add(s.id)
        on_day[day].add(s.id)
        crew[day].add(who)

    # 3) 새로 만든 출장 묶음(그날 그 사람에게 원래 일정이 없던 것)은 그 현장들의 1순위 중 가장 많은 사람이 가게(동점이면 순서) —
    #    그 사람이 그날 비어 있을 때만 바꾼다(사용자 2026-10-02: 포천 7곳 중 1곳만 맡은 사람이 7곳 다 가면 이상함).
    first_of = {s.id: s.staff_id for s in sites}
    rank = {x: i for i, x in enumerate(people)}
    groups: dict[tuple[int, datetime.date], list[Placed]] = defaultdict(list)
    for p in placed:
        groups[(p.staff_id, p.date)].append(p)
    for (who, d), group in sorted(groups.items(), key=lambda kv: (kv[0][1], -len(kv[1]))):
        if busy[(who, d)] != {p.site_id for p in group}:
            continue  # 원래 있던 출장(사람이 정한 예정·보고서)에 붙인 것 — 그 사람 그대로
        votes: dict[int, int] = defaultdict(int)
        for p in group:
            if first_of.get(p.site_id) is not None:
                votes[first_of[p.site_id]] += 1
        if not votes:
            continue
        best = max(votes, key=lambda x: (votes[x], -rank.get(x, 99)))
        if best != who and not busy[(best, d)]:
            busy[(best, d)] = busy.pop((who, d))
            crew[d].discard(who)
            crew[d].add(best)
            for p in group:
                p.staff_id = best

    for r in results.values():
        short = r.needed - r.placed
        if r.needed and short > 0 and not r.note:
            r.note = (f"넣을 날이 부족합니다 — {r.needed}회 중 {r.placed}회만 배치(주말·공휴일·회사 하루 {day_cap}곳·하루 출장 {max_travelers}명·"
                      f"한 사람 하루 현장끼리 {trip_km:g}km)")
    placed.sort(key=lambda p: (p.date, p.site_id))
    return placed, list(results.values())
