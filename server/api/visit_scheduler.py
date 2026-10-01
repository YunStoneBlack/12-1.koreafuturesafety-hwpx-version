"""지도 출장 자동 배치(2026-10-01 사용자와 정한 규칙) — DB 없이 도는 순수 계산. 저장·API는 server/api/routers/auto_plan.py.

규칙
- 남은 회차 = 총 횟수 − 최근 보고서 회차(진행 막대와 같은 기준) − 이미 잡힌 "사람이 정한"(고정) 앞으로의 예정 수.
- 기준일(오늘, 공사 시작 전이면 시작일, 최근 지도일이 더 늦으면 그날)부터 마감(준공일 − 설정 일수, 기본 14일)까지 고르게 나눈다
  (첫 지도는 기준일 + 한 간격 — "등록 후 한 간격 안"). 고정 예정이 있으면 그 날짜에 가장 가까운 자리를 고정 예정이 차지한다.
- 가는 날에서 빼는 날: 주말, 공휴일, 공휴일과 주말(또는 공휴일) 사이에 낀 평일(목 공휴 → 금, 화 공휴 → 월), 평일 공휴일이 3일 이상인 주는 월~금 전부.
- 같은 요원의 **같이 가기 좋은 현장**은 날짜를 모은다 — 각 회차는 목표일 ± 간격의 1/3 안에서 움직일 수 있고,
  그 안에 그런 현장 출장이 이미 있거나(고정 예정·앞서 고른 날) 그런 현장의 다른 회차도 올 수 있는 날을 고른다. 묶음은 매번 새로 짠다.
  같이 가기 좋음 = 같은 시·군이면서 좌표 거리 25km 이내(설정). 다른 시·군이라도 10km 이내(설정)면 자리가 없을 때만 묶는다(2026-10-01).
  좌표(server/api/geocode.py, 카카오)가 없는 현장은 예전처럼 시·군이 같으면 같이 가기 좋음.
- 요원 하루 4곳 한도(다녀온 방문·남은 예정·새로 넣는 것, 같은 현장은 1곳). 한 현장은 하루 한 번, 회차 순서대로.
- 한 요원은 **하루에 같이 가기 좋은 현장끼리만**(속초·김포를 한날로 잡던 것 — 2026-10-01 실데이터 미리보기에서 발견). 먼 현장 출장이 있는 날은 피한다.
- 목표 범위에 자리가 없으면 마감(없으면 준공일 전날)까지 가장 가까운 가능한 날로(그래도 없으면 그때만 지역 섞기 허용),
  그래도 없으면 "넣을 날 부족"으로 남긴다(막지 않고 안내만 — 사용자: 횟수를 다 못 채워도 큰일은 아님).
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


@dataclass
class SiteResult:
    site_id: int
    needed: int  # 이번에 넣어야 할 회차 수
    placed: int
    note: str = ""  # "넣을 날 부족" 등 안내(막지 않음)


def _targets(base: datetime.date, end: datetime.date, count: int) -> list[datetime.date]:
    span = (end - base).days
    return [base + datetime.timedelta(days=round(span * k / count)) for k in range(1, count + 1)]


SAME, NEAR, FAR = "same", "near", "far"
DEFAULT_FAR_KM = 25.0   # 같은 시·군이라도 이보다 멀면 안 묶는다
DEFAULT_NEAR_KM = 10.0  # 다른 시·군이라도 이보다 가까우면 자리가 없을 때 묶는다


def make_compat(regions: dict[int, str], coords: dict[int, tuple[float, float]], far_km: float = DEFAULT_FAR_KM,
                near_km: float = DEFAULT_NEAR_KM):
    """두 현장을 한날 묶을 수 있는지 — SAME(같이 가기 좋음) / NEAR(자리 없을 때만) / FAR(안 묶음), 거리(km, 모르면 None).
    좌표가 둘 다 있으면 거리로(같은 시·군 ≤ far_km = SAME, 다른 시·군 ≤ near_km = NEAR), 없으면 예전처럼 시·군으로(같으면 SAME).
    지역을 모르는 현장은 NEAR(막지는 않되 일부러 묶지도 않음)."""
    from server.api.geocode import km

    def compat(a: int, b: int) -> tuple[str, float | None]:
        ra, rb = regions.get(a, ""), regions.get(b, "")
        ca, cb = coords.get(a), coords.get(b)
        if ca and cb:
            d = km(ca, cb)
            if ra and ra == rb:
                return (SAME if d <= far_km else FAR), d
            return (NEAR if d <= near_km else FAR), d
        if not ra or not rb:
            return NEAR, None
        return (SAME if ra == rb else FAR), None

    return compat


def plan_sites(
    sites: list[SiteIn],
    today: datetime.date,
    busy: dict[tuple[int, datetime.date], set[int]],
    finish_before_days: int = DEFAULT_FINISH_BEFORE_DAYS,
    limit: int = 4,
    holidays_: dict[datetime.date, str] | None = None,
    site_regions: dict[int, str] | None = None,
    coords: dict[int, tuple[float, float]] | None = None,
    far_km: float = DEFAULT_FAR_KM,
    near_km: float = DEFAULT_NEAR_KM,
) -> tuple[list[Placed], list[SiteResult]]:
    """sites의 남은 회차를 배치한다.

    busy: (요원, 날짜) → 그날 가는 현장들(다녀온 방문·남기는 예정 — 새로 넣는 건 여기에 더해 간다). 묶기의 기준점도 여기서 본다.
    site_regions·coords: 현장 → 시·군 / (위도, 경도) — busy에 든 다른 현장까지(sites의 지역은 저절로 들어간다). 좌표는 믿을 만한 것만.
    """
    ends = [s.period_end for s in sites if s.period_end]
    if not ends:
        return [], [SiteResult(s.id, 0, 0, "공사 기간이 없어 배치하지 않았습니다") for s in sites]
    horizon = max(ends)
    hol = holidays_ if holidays_ is not None else korean_holidays(range(today.year, horizon.year + 1))
    blocked = blocked_days(today, horizon, hol)
    busy = defaultdict(set, {k: set(v) for k, v in busy.items()})
    regions = dict(site_regions or {})
    regions.update({s.id: s.region for s in sites})
    compat = make_compat(regions, coords or {}, far_km, near_km)

    def day_kind(site: SiteIn, d: datetime.date) -> str:
        """그날 이 요원 일정과 이 현장의 궁합 — empty(빈 날) / same(같이 가기 좋은 현장만) / near(가까운 다른 시·군 섞임) / far."""
        here = busy[(site.staff_id, d)] if site.staff_id is not None else set()
        kinds = {compat(site.id, x)[0] for x in here}
        return "empty" if not kinds else FAR if FAR in kinds else NEAR if NEAR in kinds else SAME

    def ok_day(site: SiteIn, d: datetime.date, after: datetime.date, allow: tuple[str, ...]) -> bool:
        if d <= after or d <= today or d in blocked:
            return False
        if site.staff_id is None:
            return True
        here = busy[(site.staff_id, d)]
        if site.id in here or len(here) >= limit:
            return False
        return day_kind(site, d) in allow

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

    # 2) 목표일 순서로 하나씩 — 같이 가기 좋은 현장 출장이 이미 있거나, 그런 현장의 다른 회차도 올 수 있는 날을 우선
    slots.sort(key=lambda x: (x[1], x[0].id))
    last_by_site: dict[int, datetime.date] = {}
    placed: list[Placed] = []
    pending = defaultdict(list)  # 요원 → 아직 안 놓은 회차의 (현장, 시작, 끝)
    for s, t, tol, _ in slots:
        if s.staff_id is not None:
            pending[s.staff_id].append((s.id, t - datetime.timedelta(days=tol), t + datetime.timedelta(days=tol)))
    STRICT, WITH_NEAR, ANY = ("empty", SAME), ("empty", SAME, NEAR), ("empty", SAME, NEAR, FAR)

    for s, t, tol, end in slots:
        if s.staff_id is not None:
            mine = pending[s.staff_id]
            mine.remove(next(p for p in mine if p[0] == s.id and p[1] == t - datetime.timedelta(days=tol)))
        after = last_by_site.get(s.id, datetime.date.min)
        lo, hi = max(t - datetime.timedelta(days=tol), today + DAY), min(t + datetime.timedelta(days=tol), end)
        window = [lo + DAY * i for i in range((hi - lo).days + 1)] if hi >= lo else []

        def score(d: datetime.date):
            join = day_kind(s, d) == SAME
            others = sum(1 for (sid, a, b) in pending[s.staff_id] if sid != s.id and a <= d <= b and compat(s.id, sid)[0] == SAME)                 if s.staff_id is not None else 0
            return (-join, -others, abs((d - t).days), d)

        last_ok = max(end, s.period_end - DAY)
        span = [(after if after != datetime.date.min else today) + DAY * i
                for i in range(1, (last_ok - (after if after != datetime.date.min else today)).days + 1)]
        day = None
        # 폭 안(같이 가기 좋은 곳만) → 폭 안(가까운 다른 시·군도) → 마감까지(좋은 곳만) → 마감까지(가까운 곳도) → 마감까지 아무 데나
        for days_, allow, by_score in ((window, STRICT, True), (window, WITH_NEAR, True), (span, STRICT, False),
                                       (span, WITH_NEAR, False), (span, ANY, False)):
            cands = [d for d in days_ if ok_day(s, d, after, allow)]
            if cands:
                day = min(cands, key=score) if by_score else min(cands, key=lambda d: (abs((d - t).days), d))
                break
        if day is None:
            continue
        placed.append(Placed(s.id, s.staff_id, day))
        last_by_site[s.id] = day
        results[s.id].placed += 1
        if s.staff_id is not None:
            busy[(s.staff_id, day)].add(s.id)

    for r in results.values():
        if r.needed and r.placed < r.needed and not r.note:
            r.note = f"넣을 날이 부족합니다 — {r.needed}회 중 {r.placed}회만 배치(주말·공휴일·하루 4곳 한도)"
    placed.sort(key=lambda p: (p.date, p.site_id))
    return placed, list(results.values())
