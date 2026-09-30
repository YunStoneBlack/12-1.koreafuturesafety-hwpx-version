"""지도 출장 자동 배치(2026-10-01 사용자와 정한 규칙) — DB 없이 도는 순수 계산. 저장·API는 server/api/routers/auto_plan.py.

규칙
- 남은 회차 = 총 횟수 − 최근 보고서 회차(진행 막대와 같은 기준) − 이미 잡힌 "사람이 정한"(고정) 앞으로의 예정 수.
- 기준일(오늘, 공사 시작 전이면 시작일, 최근 지도일이 더 늦으면 그날)부터 마감(준공일 − 설정 일수, 기본 14일)까지 고르게 나눈다
  (첫 지도는 기준일 + 한 간격 — "등록 후 한 간격 안"). 고정 예정이 있으면 그 날짜에 가장 가까운 자리를 고정 예정이 차지한다.
- 가는 날에서 빼는 날: 주말, 공휴일, 공휴일과 주말(또는 공휴일) 사이에 낀 평일(목 공휴 → 금, 화 공휴 → 월), 평일 공휴일이 3일 이상인 주는 월~금 전부.
- 같은 요원의 **같은 지역**(주소의 시·군) 현장은 날짜를 모은다 — 각 회차는 목표일 ± 간격의 1/3 안에서 움직일 수 있고,
  그 안에 같은 지역 출장이 이미 있거나(고정 예정·앞서 고른 날) 다른 현장 회차도 올 수 있는 날을 고른다. 묶음은 매번 새로 짠다.
- 요원 하루 4곳 한도(다녀온 방문·남은 예정·새로 넣는 것, 같은 현장은 1곳). 한 현장은 하루 한 번, 회차 순서대로.
- 한 요원은 **하루에 한 지역만**(속초·김포를 한날로 잡던 것 — 2026-10-01 실데이터 미리보기에서 발견). 다른 지역 출장이 있는 날은 피한다.
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


def plan_sites(
    sites: list[SiteIn],
    today: datetime.date,
    busy: dict[tuple[int, datetime.date], set[int]],
    region_days: dict[tuple[int, str], set[datetime.date]],
    finish_before_days: int = DEFAULT_FINISH_BEFORE_DAYS,
    limit: int = 4,
    holidays_: dict[datetime.date, str] | None = None,
    site_regions: dict[int, str] | None = None,
) -> tuple[list[Placed], list[SiteResult]]:
    """sites의 남은 회차를 배치한다.

    busy: (요원, 날짜) → 그날 가는 현장들(다녀온 방문·남기는 예정 — 새로 넣는 건 여기에 더해 간다).
    region_days: (요원, 지역) → 그 지역에 이미 가는 날들(남기는 예정 기준, 묶기의 기준점).
    site_regions: 현장 → 지역(busy에 든 다른 현장들의 지역을 알려고 — 하루 한 지역). sites의 지역은 저절로 들어간다.
    """
    ends = [s.period_end for s in sites if s.period_end]
    if not ends:
        return [], [SiteResult(s.id, 0, 0, "공사 기간이 없어 배치하지 않았습니다") for s in sites]
    horizon = max(ends)
    hol = holidays_ if holidays_ is not None else korean_holidays(range(today.year, horizon.year + 1))
    blocked = blocked_days(today, horizon, hol)
    busy = defaultdict(set, {k: set(v) for k, v in busy.items()})
    region_days = defaultdict(set, {k: set(v) for k, v in region_days.items()})

    regions = dict(site_regions or {})
    regions.update({s.id: s.region for s in sites})

    def ok_day(site: SiteIn, d: datetime.date, after: datetime.date, one_region: bool = True) -> bool:
        if d <= after or d <= today or d in blocked:
            return False
        if site.staff_id is None:
            return True
        here = busy[(site.staff_id, d)]
        if site.id in here or len(here) >= limit:
            return False
        return not (one_region and site.region and any(regions.get(x) and regions[x] != site.region for x in here))  # 지역 모르는 현장은 안 막음

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

    # 2) 목표일 순서로 하나씩 — 같은 지역 출장이 있거나 같은 지역 다른 회차도 올 수 있는 날을 우선
    slots.sort(key=lambda x: (x[1], x[0].id))
    last_by_site: dict[int, datetime.date] = {}
    placed: list[Placed] = []
    pending = defaultdict(list)  # (요원, 지역) → 아직 안 놓은 회차의 (시작, 끝)
    for s, t, tol, _ in slots:
        if s.staff_id is not None and s.region:
            pending[(s.staff_id, s.region)].append((s.id, t - datetime.timedelta(days=tol), t + datetime.timedelta(days=tol)))

    for s, t, tol, end in slots:
        key = (s.staff_id, s.region) if s.staff_id is not None and s.region else None
        if key:
            pending[key].remove(next(p for p in pending[key] if p[0] == s.id and p[1] == t - datetime.timedelta(days=tol)))
        after = last_by_site.get(s.id, datetime.date.min)
        lo, hi = max(t - datetime.timedelta(days=tol), today + DAY), min(t + datetime.timedelta(days=tol), end)
        cands = [lo + DAY * i for i in range((hi - lo).days + 1)] if hi >= lo else []
        cands = [d for d in cands if ok_day(s, d, after)]

        def score(d: datetime.date):
            join = len(region_days[key] & {d}) if key else 0
            others = sum(1 for (sid, a, b) in pending[key] if sid != s.id and a <= d <= b) if key else 0
            return (-join, -others, abs((d - t).days), d)

        if cands:
            day = min(cands, key=score)
        else:  # 폭 안에 자리가 없으면 마감(없으면 준공일 전날)까지 가장 가까운 가능한 날
            last_ok = max(end, s.period_end - DAY)
            span = [after + DAY * i for i in range(1, (last_ok - after).days + 1)] if after != datetime.date.min else \
                [today + DAY * i for i in range(1, (last_ok - today).days + 1)]
            span = [d for d in span if ok_day(s, d, after)] or [d for d in span if ok_day(s, d, after, one_region=False)]
            if not span:
                continue
            day = min(span, key=lambda d: (abs((d - t).days), d))
        placed.append(Placed(s.id, s.staff_id, day))
        last_by_site[s.id] = day
        results[s.id].placed += 1
        if s.staff_id is not None:
            busy[(s.staff_id, day)].add(s.id)
        if key:
            region_days[key].add(day)

    for r in results.values():
        if r.needed and r.placed < r.needed and not r.note:
            r.note = f"넣을 날이 부족합니다 — {r.needed}회 중 {r.placed}회만 배치(주말·공휴일·하루 4곳 한도)"
    placed.sort(key=lambda p: (p.date, p.site_id))
    return placed, list(results.values())
