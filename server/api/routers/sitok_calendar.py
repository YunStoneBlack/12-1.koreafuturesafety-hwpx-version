"""보고서 자동화 · 시특법 — 방문 달력(2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리"). 계산은 server/sitok/visit_plan.py.

- `GET /sitok/calendar?start=&end=` — 그 사이 점검 날(시설물 카드·반기·종류·지역·상태) + 날마다 건물 수 + 일정 없는 반기 수
- `POST /sitok/calendar/visits` {facility_id, plan_date, plan_end?, kind?} — 사람이 날 넣기(📌, 같은 반기에 더 넣기도)
- `PATCH /sitok/calendar/visits/{id}` {plan_date?, plan_end?, memo?} — 날 바꾸기(끌어 옮기기 → 📌). 시작만 바꾸면 기간 그대로 옮김.
  일정은 범위(시작~끝, 10/19 민재형 "일정을 범위 설정 가능하도록, 디폴트 10.30~10.30") — 끝이 비면 하루, 하루 건물 수는 날마다 나눠 셈(visit_plan.day_share).
- `DELETE /sitok/calendar/visits/{id}`
- `PATCH /sitok/calendar/visits/{id}/site-contact` {manager?, phone} — 카드의 현장 담당 연락처 = 서류 자동화 계약 정보 "현장 담당"을 바로 고침
- `PATCH /sitok/calendar/facilities/{id}/map-address` {address} — 시설물 지도용 주소(카드 📍 지도·복사·동선만, 빈 글 = 관리대장 주소, 10/25 민재형) — 관리대장·보고서 주소는 그대로
  (10/20 민재형 "달력 전화번호는 현장 담당 번호로, 없으면 등록 버튼, 달력에서 고치면 계약 정보도 같이" — 시설물 칸 관리주체·담당자 전화는 안 씀)
- `GET /sitok/calendar/missing` — 일정 없는 반기 목록(계약기간 안인데 날이 없음)
- `POST /sitok/calendar/fill` {dry_run, facility_ids?} — 자동으로 잡기(미리보기 → 잡기). 이미 있는 날은 안 건드림.
- `POST /sitok/calendar/route` {date, start?, end?, order?} — 그날 동선(10/23 — 산안법 동선 창과 같은 모양, 시설물 = 묶음 안 시설물 전부)
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models_web import SitokDocContract, SitokFacility, SitokReport, SitokVisit, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_docs import contract_index, site_contract, site_phone
from server.sitok import visit_plan as V

router = APIRouter(prefix="/sitok/calendar", tags=["sitok-calendar"])


def _unit_map(db: Session, company_id: int) -> dict[int, V.Unit]:
    out = {}
    for u in V.units(db, company_id, with_ended=True):
        for m in u.members:
            out[m.id] = u
    return out


def map_address(f: SitokFacility) -> str:
    """달력 지도·복사·동선에 쓰는 주소 — 고친 지도용 주소(ledger.map_address, 10/25 민재형), 없으면 관리대장 주소. 보고서는 늘 f.address."""
    return str((f.ledger or {}).get("map_address") or "").strip() or (f.address or "")


def _unit_out(u: V.Unit) -> dict:
    f = u.lead
    return {"id": f.id, "mgmt_no": f.mgmt_no, "name": u.name, "sector": f.sector or "민간", "badge_field": f.badge_field or "",
            "badge_kind": f.badge_kind or "", "region": u.region, "address": map_address(f), "ledger_address": f.address or "", "buildings": u.buildings,
            "contract_type": f.contract_type,
            "members": [{"id": m.id, "name": m.name, "address": map_address(m), "ledger_address": m.address or ""} for m in u.members]}  # 주소 = 카드 안 시설물 위치(10/23)


def _state(db: Session, v: SitokVisit, u: V.Unit, today: datetime.date) -> tuple[str, int | None]:
    """done = 보고서 만듦(밖에서 완료 포함, 진하게) · field = 현장점검 완료(채운 칸 — 10/18 형 "산안법 달력처럼") · missed = 지난 날 · planned = 빈 칸."""
    reps = db.query(SitokReport).filter(SitokReport.facility_id.in_(u.ids), SitokReport.year == v.year, SitokReport.half == v.half).order_by(SitokReport.id).all()
    rid = reps[0].id if reps else None
    if any(x.status == "done" or (x.submit or {}).get("report") for x in reps):
        return "done", rid
    if any((x.submit or {}).get("field") for x in reps):
        return "field", rid
    return ("missed" if V.visit_span(v)[1] < today else "planned"), rid


def _site_out(c: SitokDocContract | None) -> dict | None:
    if c is None:
        return None
    return {"cid": c.id, "manager": c.site_manager or "", "phone": c.site_phone or "", "title": c.title or ""}


def _visit_out(db: Session, v: SitokVisit, u: V.Unit, today: datetime.date, cons: list | None = None) -> dict:
    st, rid = _state(db, v, u, today)
    cons = cons if cons is not None else contract_index(db, v.company_id)
    return {"id": v.id, "date": v.plan_date.isoformat(), "end": V.visit_span(v)[1].isoformat(), "year": v.year, "half": v.half, "kind": v.kind, "pinned": v.source == "manual",
            "memo": v.memo, "state": st, "report_id": rid, "facility": _unit_out(u), "site": _site_out(site_contract(cons, set(u.ids), v.year, v.half)),
            "phone": site_phone(cons, set(u.ids), u.lead.owner_phone, v.year, v.half)}  # 현장 담당, 비면 관리주체 전화(10/20)


@router.get("")
def calendar(start: datetime.date, end: datetime.date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if (end - start).days > 70:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "한 번에 70일까지 봅니다.")
    today = datetime.date.today()
    um = _unit_map(db, user.company_id)
    rows = db.query(SitokVisit).filter(SitokVisit.company_id == user.company_id, SitokVisit.plan_date < end,
                                       func.coalesce(SitokVisit.plan_end, SitokVisit.plan_date) >= start).order_by(SitokVisit.plan_date, SitokVisit.id).all()
    cons = contract_index(db, user.company_id)
    visits = [_visit_out(db, v, um[v.facility_id], today, cons) for v in rows if v.facility_id in um]
    load: dict[str, int] = {}
    for v in rows:
        if v.facility_id in um:
            for d, n in V.day_share(v, um[v.facility_id].buildings):  # 여러 날 일정은 날마다 나눠(10/19)
                load[d.isoformat()] = load.get(d.isoformat(), 0) + n
    miss = V.missing(db, user.company_id, today)
    return {"visits": visits, "day_load": load, "day_cap": V.DAY_CAP, "missing": len(miss), "missing_units": len({n.unit.lead.id for n in miss}),
            "missing_list": [_need_out(n) for n in miss[:30]],  # 어떤 시설물·반기인지(10/23 사용자 "어떤 건지 보여 주기")
            "facilities": [_unit_out(u) for u in {id(u): u for u in um.values()}.values()]}


class VisitIn(BaseModel):
    facility_id: int
    plan_date: datetime.date
    plan_end: datetime.date | None = None
    kind: str | None = None
    memo: str | None = None


@router.post("/visits")
def add_visit(body: VisitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = db.get(SitokFacility, body.facility_id)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    um = _unit_map(db, user.company_id)
    u = um.get(f.id)
    y, h = V.slot_of(db, u, body.plan_date)  # 반기, 연 3회 시설물이면 그 날이 드는 해빙기·우기·동절기(10/16)
    kind = body.kind if body.kind in ("정기", "정밀") else None
    if kind is None:  # 그 반기 할 일(계약)의 종류, 없으면 그 반기 다른 날의 종류, 없으면 정기
        need = next((n for n in V.needs_for(db, u, min(datetime.date.today(), body.plan_date - V.DAY)) if n.key == (y, h)), None) if u else None
        old = db.query(SitokVisit).filter(SitokVisit.facility_id.in_(u.ids if u else [f.id]), SitokVisit.year == y, SitokVisit.half == h).first()
        kind = need.kind if need else old.kind if old else "정기"
    v = SitokVisit(company_id=user.company_id, facility_id=(u.lead.id if u else f.id), year=y, half=h, kind=kind, plan_date=body.plan_date,
                   plan_end=_end(body.plan_date, body.plan_end), source="manual", memo=(body.memo or "").strip(), created_by=user.display_name or "")
    db.add(v)
    db.commit()
    return _visit_out(db, v, u or V.Unit(f, [f], f.name, V.region_of(f.address)), datetime.date.today())


class VisitPatch(BaseModel):
    plan_date: datetime.date | None = None
    plan_end: datetime.date | None = None
    memo: str | None = None
    kind: str | None = None


def _end(start: datetime.date, end: datetime.date | None) -> datetime.date | None:
    """끝 날 — 비거나 시작과 같으면 None(하루), 시작보다 앞이면 400."""
    if end is None or end == start:
        return None
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "끝 날이 시작 날보다 앞입니다.")
    return end


def _require(db: Session, user: User, vid: int) -> SitokVisit:
    v = db.get(SitokVisit, vid)
    if v is None or v.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    return v


@router.patch("/visits/{vid}")
def patch_visit(vid: int, body: VisitPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = _require(db, user, vid)
    start, end = V.visit_span(v)
    if body.plan_date is not None and body.plan_date != v.plan_date:
        if body.plan_end is None and v.plan_end:  # 시작만 옮기면 기간 그대로(끌어 옮기기)
            v.plan_end = body.plan_date + (end - start)
        v.plan_date = body.plan_date
        v.year, v.half = V.slot_of(db, _unit_map(db, user.company_id).get(v.facility_id), body.plan_date)  # 다른 반기(연 3회면 시기)로 옮기면 그 점검이 됨
        v.source = "manual"  # 사람이 옮긴 날 = 📌(자동 배치가 안 건드림)
    if body.plan_end is not None:
        v.plan_end = _end(v.plan_date, body.plan_end)
        v.source = "manual"
    if body.memo is not None:
        v.memo = body.memo.strip()
    if body.kind in ("정기", "정밀"):
        v.kind = body.kind
    db.commit()
    um = _unit_map(db, user.company_id)
    return _visit_out(db, v, um[v.facility_id], datetime.date.today())


class SiteContactIn(BaseModel):
    phone: str
    manager: str | None = None


@router.patch("/visits/{vid}/site-contact")
def site_contact(vid: int, body: SiteContactIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """카드의 현장 담당 연락처 → 서류 자동화 계약 정보 "현장 담당"(SitokDocContract.site_manager·site_phone)을 바로 고침(10/20 민재형).
    계약 저장(put_contract)의 카드 정리 같은 일은 안 함 — 이 두 칸만."""
    v = _require(db, user, vid)
    um = _unit_map(db, user.company_id)
    f = db.get(SitokFacility, v.facility_id)
    u = um.get(v.facility_id) or V.Unit(f, [f], f.name, V.region_of(f.address))
    c = site_contract(contract_index(db, user.company_id), set(u.ids), v.year, v.half)
    if c is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 시설물의 계약이 서류 자동화에 없습니다 — 계약을 먼저 넣으면 현장 담당 연락처를 등록할 수 있습니다.")
    c.site_phone = body.phone.strip()
    if body.manager is not None:
        c.site_manager = body.manager.strip()
    c.updated_at, c.updated_by = datetime.datetime.now(), user.display_name or ""
    db.commit()
    return _site_out(c)


class MapAddressIn(BaseModel):
    address: str = ""


@router.patch("/facilities/{fid}/map-address")
def set_map_address(fid: int, body: MapAddressIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """시설물 지도용 주소 고치기(빈 글 = 관리대장 주소로 되돌림) — 달력 지도·복사·동선만, 관리대장·보고서 주소(f.address)는 그대로(10/25 민재형)."""
    f = db.get(SitokFacility, fid)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    addr = " ".join((body.address or "").split())[:200]
    led = dict(f.ledger or {})
    if addr and addr != (f.address or "").strip():
        led["map_address"] = addr
    else:
        led.pop("map_address", None)
    f.ledger = led
    db.commit()
    return {"id": f.id, "address": map_address(f), "ledger_address": f.address or ""}


@router.delete("/visits/{vid}")
def delete_visit(vid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = _require(db, user, vid)
    db.delete(v)
    db.commit()
    return {"ok": True}


def _need_out(n: V.Need) -> dict:
    return {"facility": _unit_out(n.unit), "year": n.year, "half": n.half, "kind": n.kind, "start": n.start.isoformat(), "end": n.end.isoformat(), "why": n.why}


@router.get("/missing")
def get_missing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"missing": [_need_out(n) for n in V.missing(db, user.company_id)]}


class RouteIn(BaseModel):
    date: datetime.date
    start: str | None = None  # 출발지 주소(비우면 회사 — 산안법 설정과 같은 칸)
    end: str | None = None
    order: list[int] | None = None  # 사람이 바꾼 순서(곳 id = 그 자리 첫 시설물 id)


@router.post("/route")
def route(body: RouteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """그날 동선(10/23 사용자 "여러 개 시설물일 경우 동선 짜 주기(기술지도처럼)") — 그날 일정의 시설물(묶음은 묶음 안 시설물 전부), 출발지 → 시설물들 → 복귀지.
    주소 좌표가 같은 시설물은 한 곳(옹벽 여러 개가 한 번지). 순서는 직선거리로 가장 짧게(17곳도 바로 — 도로 거리로 모든 순서를 묻으면 길찾기가 수백 번),
    보여 주는 구간 거리는 그 순서의 도로 거리(카카오 길찾기, 산안법 동선과 같은 기억). 모양은 산안법 /calendar/route와 같음(js/route-plan.js)."""
    from core import config
    from server.api.geocode import km
    from server.api.routers.route_plan import _best_order, _leg, _point

    um = _unit_map(db, user.company_id)
    rows = db.query(SitokVisit).filter(SitokVisit.company_id == user.company_id, SitokVisit.plan_date <= body.date,
                                       func.coalesce(SitokVisit.plan_end, SitokVisit.plan_date) >= body.date).order_by(SitokVisit.plan_date, SitokVisit.id).all()
    facs, seen = [], set()
    for v in rows:
        u = um.get(v.facility_id)
        for m in (u.members if u else []):
            if m.id not in seen:
                seen.add(m.id)
                facs.append(m)
    if not facs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 날 점검 일정이 없습니다.")
    home = config.get_route_home_address(user.company_id)
    start_addr, end_addr = (body.start or "").strip() or home, (body.end or "").strip() or home
    start, end = _point(start_addr), _point(end_addr)
    if start is None or end is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{'출발지' if start is None else '복귀지'} 주소를 지도에서 찾지 못했습니다 — 주소를 확인하세요.")
    places: dict[int, dict] = {}  # 곳 id(첫 시설물) → {names, address, c}
    by_c: dict[tuple, int] = {}
    missing = []
    for f in facs:
        c = _point(map_address(f).strip()) if map_address(f).strip() else None  # 지도용 주소(고쳤으면 그 주소, 10/25)
        if c is None:
            missing.append(f)
            continue
        k = (round(c[0], 5), round(c[1], 5))
        if k not in by_c:
            by_c[k] = f.id
            places[f.id] = {"names": [], "address": map_address(f), "c": c}
        places[by_c[k]]["names"].append(f.name)
    ids = list(places)

    def legs_of(order: list[int], d) -> tuple[float, list[float]]:
        pts = [start] + [places[i]["c"] for i in order] + [end]
        legs = [d(a, b) for a, b in zip(pts, pts[1:])]
        return sum(legs), legs

    best = _best_order(ids, lambda o: legs_of(o, km))
    order = [i for i in (body.order or []) if i in places]
    if sorted(order) != sorted(ids):
        order = best
    total_km, legs = legs_of(order, _leg)
    best_total = legs_of(best, _leg)[0] if order != best else total_km
    name = lambda p: p["names"][0] + (f" 외 {len(p['names']) - 1}곳" if len(p["names"]) > 1 else "")  # noqa: E731
    out = lambda i: {"site_id": i, "name": name(places[i]), "address": places[i]["address"], "lat": places[i]["c"][0], "lng": places[i]["c"][1],  # noqa: E731
                     "names": places[i]["names"]}
    return {"date": body.date.isoformat(), "home": home,
            "start": {"address": start_addr, "lat": start[0], "lng": start[1], "is_home": start_addr == home},
            "end": {"address": end_addr, "lat": end[0], "lng": end[1], "is_home": end_addr == home},
            "stops": [out(i) for i in order], "missing": [{"site_id": f.id, "name": f.name, "address": map_address(f)} for f in missing],
            "legs": [round(x, 1) for x in legs], "total_km": round(total_km, 1), "best_order": best, "best_total_km": round(min(best_total, total_km), 1),
            "is_best": order == best or total_km <= best_total + 0.05}


class FillIn(BaseModel):
    dry_run: bool = True
    facility_ids: list[int] | None = None


@router.post("/fill")
def fill(body: FillIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    planned = V.plan(db, user.company_id, V.missing(db, user.company_id, facility_ids=body.facility_ids))
    out = [{**_need_out(p["need"]), "date": p["date"].isoformat() if p["date"] else None, "note": p["note"]} for p in planned]
    if not body.dry_run:
        V.apply(db, user.company_id, planned, user.display_name or "")
        db.commit()
    return {"planned": out, "applied": not body.dry_run}
