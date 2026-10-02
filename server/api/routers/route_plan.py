"""출장 동선 짜기(2026-10-01) — 한 요원의 그날 현장들을 출발지 → 현장들 → 복귀지 도로 거리가 가장 짧은 순서로.

- `POST /calendar/route` — body: date, staff_id, start/end(주소, 비우면 회사 주소 — 설정 탭), order(사람이 바꾼 순서, 없으면 최적).
  돌려줌: 출발·복귀·현장(이름·주소·좌표), 순서, 구간 거리, 총 거리, 최적 순서와 그 총 거리(사람 순서가 얼마나 긴지 비교).
- 현장 = 그 요원의 그날 방문 예정 + 그날 지도일로 만든 보고서 중 이 요원이 다녀온 것(출장자 = 그날 그 현장 예정의 요원, 없으면 보고서 담당 —
  server/api/report_staff.travelers)(같은 현장 1번). "⚠ 대타 필요"(담당 없음)는 안 넣는다.
- 거리는 카카오 길찾기 도로 거리(server/api/geocode.py) — 현장끼리는 site_distance에 저장된 것, 출발·복귀지와는 이 프로세스 안에서만 기억.
  출장은 한 사람 한도가 없어져(2026-10-02) 8곳까지는 가능한 순서를 전부 비교(8곳 = 40,320가지), 그보다 많으면 가까운 곳부터 + 2-opt로
  다듬은 순서(최적에 가깝지만 보장은 아님). 운전 시간은 교통에 따라 달라 쓰지 않는다(사용자 결정).
- 내비 연결은 화면(js/route-plan.js) — 네이버 지도 앱 경유지(키 없이 됨, 폰 시험), 티맵은 SK 오픈API 키 받아 시험 예정.
"""

from __future__ import annotations

import datetime
import itertools

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site
from core.models_web import User, VisitPlan
from server.api.deps import get_current_user, get_db
from server.api.geocode import RoadDistance, geocode, km, map_addresses, road_km, site_coords
from server.api.report_staff import travelers
from server.api.site_label import site_label

router = APIRouter(tags=["route"])
EXACT_MAX = 8  # 이 곳 수까지는 모든 순서를 비교

_point_cache: dict[str, tuple[float, float] | None] = {}   # 주소 → 좌표(출발·복귀지)
_leg_cache: dict[str, float] = {}                          # "lat,lng|lat,lng" → 도로 km(출발·복귀지 구간)


class RouteIn(BaseModel):
    date: datetime.date
    staff_id: int
    start: str | None = None  # 출발지 주소(비우면 회사)
    end: str | None = None    # 복귀지 주소(비우면 회사)
    order: list[int] | None = None  # 사람이 바꾼 현장 순서(site_id)


def _point(address: str) -> tuple[float, float] | None:
    if address not in _point_cache:
        try:
            found = geocode(address)
        except Exception:  # noqa: BLE001
            return None
        _point_cache[address] = (found[0], found[1]) if found else None
    return _point_cache[address]


def _leg(a: tuple[float, float], b: tuple[float, float]) -> float:
    key = f"{a[0]:.6f},{a[1]:.6f}|{b[0]:.6f},{b[1]:.6f}"
    if key not in _leg_cache:
        try:
            found = road_km(a, b)
        except Exception:  # noqa: BLE001 — 길찾기가 안 되면 직선거리(저장 안 함 → 다음에 다시 물음)
            return km(a, b)
        _leg_cache[key] = found if found is not None else km(a, b)
    return _leg_cache[key]


@router.post("/calendar/route")
def route(body: RouteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = user.company_id
    sites_all = {s.id: s for s in db.query(Site).filter(Site.company_id == cid)}
    ids: list[int] = []
    for (sid,) in db.query(VisitPlan.site_id).filter(VisitPlan.company_id == cid, VisitPlan.plan_date == body.date,
                                                      VisitPlan.staff_id == body.staff_id).order_by(VisitPlan.id):
        if sid in sites_all and sid not in ids:
            ids.append(sid)
    went = travelers(db, cid, body.date, body.date)
    for sid, staff_id in db.query(Report.site_id, Report.assigned_staff_id).filter(Report.site_id.in_(list(sites_all)),
                                                                                    Report.guidance_date == body.date):
        if went.get((sid, body.date), staff_id) == body.staff_id and sid not in ids:
            ids.append(sid)
    if not ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 날 이 요원의 방문 현장이 없습니다.")

    home = config.get_route_home_address(cid)
    start_addr = (body.start or "").strip() or home
    end_addr = (body.end or "").strip() or home
    start, end = _point(start_addr), _point(end_addr)
    if start is None or end is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{'출발지' if start is None else '복귀지'} 주소를 지도에서 찾지 못했습니다 — 주소를 확인하세요.")

    coords = site_coords(db, {i: sites_all[i] for i in ids})
    missing = [i for i in ids if i not in coords]
    stops = [i for i in ids if i in coords]
    dist = RoadDistance(db, coords)

    def total(order: list[int]) -> tuple[float, list[float]]:
        if not order:
            legs = [_leg(start, end)]
        else:
            legs = [_leg(start, coords[order[0]])]
            legs += [dist(a, b) for a, b in zip(order, order[1:])]
            legs.append(_leg(coords[order[-1]], end))
        return sum(legs), legs

    best = _best_order(stops, total)
    best_total, _ = total(best)
    order = [i for i in (body.order or []) if i in stops]
    if sorted(order) != sorted(stops):
        order = best
    total_km, legs = total(order)
    dist.save()

    addr = map_addresses(db, {i: sites_all[i] for i in ids})
    site_out = lambda i: {"site_id": i, "name": site_label(sites_all[i]), "address": addr[i],
                          "lat": coords[i][0] if i in coords else None, "lng": coords[i][1] if i in coords else None}
    return {
        "date": body.date.isoformat(), "staff_id": body.staff_id, "home": home,
        "start": {"address": start_addr, "lat": start[0], "lng": start[1], "is_home": start_addr == home},
        "end": {"address": end_addr, "lat": end[0], "lng": end[1], "is_home": end_addr == home},
        "stops": [site_out(i) for i in order], "missing": [site_out(i) for i in missing],
        "legs": [round(x, 1) for x in legs], "total_km": round(total_km, 1),
        "best_order": best, "best_total_km": round(best_total, 1), "is_best": order == best,
    }


def _best_order(stops: list[int], total) -> list[int]:
    """총 거리가 가장 짧은 순서 — EXACT_MAX곳까지는 전부 비교, 넘으면 가까운 곳부터 고른 뒤 2-opt(구간 뒤집기)로 더 줄어들 때까지 다듬는다."""
    if not stops:
        return []
    if len(stops) <= EXACT_MAX:
        return min((list(p) for p in itertools.permutations(stops)), key=lambda o: total(o)[0])
    best: list[int] | None = None
    for first in stops:  # 출발 현장을 하나씩 바꿔 가며 가까운 곳부터
        order, left = [first], [x for x in stops if x != first]
        while left:
            nxt = min(left, key=lambda x: total(order + [x])[0])
            order.append(nxt)
            left.remove(nxt)
        if best is None or total(order)[0] < total(best)[0]:
            best = order
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if total(cand)[0] + 1e-9 < total(best)[0]:
                    best, improved = cand, True
    return best
