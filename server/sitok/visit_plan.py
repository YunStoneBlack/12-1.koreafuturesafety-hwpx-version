"""시특법 방문 달력 — 반기마다 현장 점검 날 자동 배치(2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리").

규칙(문서 그대로 + 내가 정한 것 ★)
- 시설물 카드(묶인 동은 한 카드 — 한 번 가서 다 봄)마다, 계약이 덮는 반기에 하루씩. 장기·지속은 계약기간 안 반기마다(끝 없는 계약은
  ★ 지금 반기부터 3년 = 6반기까지), 1회성은 그 계약 반기만, 지속계약 종료는 안 잡음. 정기·정밀 모두 하루(더 필요하면 사람이 날 추가).
  예) 민간 26~28 정기 + 27 하반기 정밀 → 6번.
- 관급은 착수일부터 1주일 안(그 반기). 지났으면 ★ 그 반기 남은 날 안.
- 같은 시·군 시설물은 같은 날로 묶음, 하루 건물 4개까지(묶인 동은 동 수만큼 셈). ★ 다른 시·군과는 되도록 같은 날에 안 넣고,
  반기 안에서 시·군마다 날을 고르게 벌려 놓음(한쪽에 몰리지 않게). 주말·공휴일·징검다리는 뺌(산안법 달력과 같은 규칙 — visit_scheduler).
- 지난 날·오늘은 안 잡음. 그 반기 보고서를 이미 만들었으면(합본 PDF) 잡지 않음. 이미 그 반기 날이 있으면(자동·사람) 그대로.
- 계약 정보는 서류 자동화 계약(sitok_doc_contract — 민간 회차 줄·관급 용역 기간)이 먼저, 없으면 보고서 쪽 계약(sitok_contract).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from core.models_web import SitokContract, SitokDocContract, SitokFacility, SitokGroup, SitokReport, SitokVisit
from server.api.visit_scheduler import blocked_days, korean_holidays, region_of

DAY = datetime.timedelta(days=1)
DAY_CAP = 4  # 하루 건물 수(문서 "하루 묶을 수 있는 건물의 개수는 4개")
HORIZON = 6  # 끝 없는 계약은 지금 반기부터 6반기(3년)까지
GOV_WEEK = 7  # 관급 = 착수일부터 이만큼 안


def h_index(year: int, half: str) -> int:
    return year * 2 + (1 if half == "하반기" else 0)


def h_of(i: int) -> tuple[int, str]:
    return i // 2, "하반기" if i % 2 else "상반기"


def d_index(d: datetime.date) -> int:
    return d.year * 2 + (1 if d.month > 6 else 0)


def h_range(i: int) -> tuple[datetime.date, datetime.date]:
    y, h = h_of(i)
    return (datetime.date(y, 1, 1), datetime.date(y, 6, 30)) if h == "상반기" else (datetime.date(y, 7, 1), datetime.date(y, 12, 31))


def kind_of_title(title: str) -> str:
    t = (title or "").replace(" ", "")
    return "정밀" if "정밀" in t and "정기" not in t else "정기"


@dataclass
class Unit:
    lead: SitokFacility
    members: list[SitokFacility]
    name: str
    region: str

    @property
    def ids(self) -> list[int]:
        return [m.id for m in self.members]

    @property
    def buildings(self) -> int:
        return len(self.members)

    @property
    def region_key(self) -> str:
        return self.region or f"?{self.lead.id}"  # 시·군을 못 찾으면 혼자


@dataclass
class Need:
    unit: Unit
    index: int  # 반기(h_index)
    kind: str
    start: datetime.date  # 이 날부터
    end: datetime.date  # 이 날까지
    why: str = ""  # 관급 착수 주 등
    pri: int = 0

    @property
    def year(self) -> int:
        return h_of(self.index)[0]

    @property
    def half(self) -> str:
        return h_of(self.index)[1]


def units(db: Session, company_id: int, with_ended: bool = False) -> list[Unit]:
    facs = db.query(SitokFacility).filter(SitokFacility.company_id == company_id).order_by(SitokFacility.group_order, SitokFacility.id).all()
    groups: dict[int, list[SitokFacility]] = {}
    out = []
    for f in facs:
        if f.group_id:
            groups.setdefault(f.group_id, []).append(f)
    seen = set()
    for f in facs:
        if f.group_id in seen:
            continue
        members = groups.get(f.group_id, [f]) if f.group_id else [f]
        if f.group_id:
            seen.add(f.group_id)
        lead = members[0]
        if lead.contract_type == "종료" and not with_ended:
            continue
        name = lead.name
        if len(members) > 1:
            g = db.get(SitokGroup, lead.group_id)
            name = (g.name if g else "") or lead.name
        out.append(Unit(lead, members, name, region_of(lead.address)))
    return out


def needs_for(db: Session, u: Unit, today: datetime.date) -> list[Need]:
    """이 시설물 카드가 지금 반기부터 점검해야 하는 반기들(창 = 그 반기 안에서 갈 수 있는 날 범위, 오늘 다음 날부터)."""
    now_i = d_index(today)
    last_i = now_i + HORIZON - 1
    found: dict[int, Need] = {}

    def add(i: int, kind: str, a: datetime.date | None, b: datetime.date | None, pri: int, why: str = "",
            fb_end: datetime.date | None = None) -> None:
        if i < now_i or i > last_i:
            return
        ha, hb = h_range(i)
        lo, hi = max(a or ha, ha, today + DAY), min(b or hb, hb)
        if lo > hi and why:  # 관급 착수 주가 지났으면 그 반기 남은 날(계약 끝까지)
            lo, hi, why = max(a or ha, ha, today + DAY), min(fb_end or hb, hb), ""
        if lo > hi:
            return
        old = found.get(i)
        if old is None or pri > old.pri:
            found[i] = Need(u, i, kind or "정기", lo, hi, why, pri)

    ids = u.ids
    docs = [d for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == u.lead.company_id).order_by(SitokDocContract.id)
            if set(int(x) for x in (d.facility_ids or ([d.facility_id] if d.facility_id else []))) & set(ids)]  # 시설물 여럿 계약(0052)도
    for c in docs:
        if c.sector == "관급":
            if c.start_date is None:
                continue
            end = c.end_date or c.start_date
            k = kind_of_title(c.title)
            for i in range(d_index(c.start_date), d_index(end) + 1):
                if i == d_index(c.start_date):
                    add(i, k, c.start_date, min(c.start_date + DAY * GOV_WEEK, end), 3, "관급 착수일 1주일 안", fb_end=end)
                else:
                    add(i, k, None, end, 2)
            continue
        rounds = [r for r in (c.rounds or []) if r.get("year") and r.get("half")]
        for r in rounds:
            add(h_index(int(r["year"]), r["half"]), r.get("kind") or "정기", c.start_date, c.end_date, 2)
        if c.open_ended and c.start_date:
            k = (c.unit or {}).get("kind") or "정기"
            for i in range(d_index(c.start_date), last_i + 1):
                add(i, k, c.start_date, None, 2)
        elif not rounds and c.start_date:
            for i in range(d_index(c.start_date), d_index(c.end_date or c.start_date) + 1):
                add(i, kind_of_title(c.title), c.start_date, c.end_date, 2)
    for c in db.query(SitokContract).filter(SitokContract.facility_id.in_(ids)).order_by(SitokContract.id):
        if c.start_date is None:
            continue
        rounds = [r for r in (c.rounds or []) if r.get("year") and r.get("half")]
        if rounds:
            for r in rounds:
                add(h_index(int(r["year"]), r["half"]), r.get("kind") or "정기", c.start_date, c.end_date, 1)
            continue
        end_i = d_index(c.end_date) if c.end_date else last_i
        for i in range(d_index(c.start_date), end_i + 1):
            if c.halves in ("상반기", "하반기") and h_of(i)[1] != c.halves:
                continue
            if c.sector == "관급" and i == d_index(c.start_date):
                add(i, kind_of_title(c.title), c.start_date, min(c.start_date + DAY * GOV_WEEK, c.end_date or c.start_date + DAY * GOV_WEEK), 1,
                    "관급 착수일 1주일 안", fb_end=c.end_date)
            else:
                add(i, kind_of_title(c.title), c.start_date, c.end_date, 1)
    # 종류: 그 반기 회차가 있으면 그 종류, 없으면 계약 회차 줄·계약건명(보고서 쪽 kind_known — 서류 자동화 회차 줄까지 봄)
    from server.api.routers.sitok import contract_for, kind_known

    rep_kind = {h_index(r.year, r.half): r.kind for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(ids)) if r.kind}
    for n in found.values():
        if n.index in rep_kind:
            n.kind = rep_kind[n.index]
        elif n.pri < 2:
            k = kind_known(db, contract_for(db, u.lead, n.year, n.half), n.year, n.half)
            n.kind = k or n.kind
    return sorted(found.values(), key=lambda n: n.index)


def missing(db: Session, company_id: int, today: datetime.date | None = None, facility_ids: list[int] | None = None) -> list[Need]:
    """일정이 없는 반기 — 그 반기 날(자동·사람)도 없고 보고서도 아직 안 만든 것."""
    today = today or datetime.date.today()
    out = []
    for u in units(db, company_id):
        if facility_ids and not set(facility_ids) & set(u.ids):
            continue
        ns = needs_for(db, u, today)
        if not ns:
            continue
        have = {h_index(v.year, v.half) for v in db.query(SitokVisit).filter(SitokVisit.facility_id.in_(u.ids))}
        done = {h_index(r.year, r.half) for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(u.ids), SitokReport.status == "done")}
        out += [n for n in ns if n.index not in have and n.index not in done]
    return out


@dataclass
class DayLoad:
    buildings: int = 0
    regions: set = field(default_factory=set)


def plan(db: Session, company_id: int, needs: list[Need], today: datetime.date | None = None) -> list[dict]:
    """needs에 날짜를 고름 → [{need, date, note}]. 이미 잡힌 날(오늘 이후)의 지역·건물 수를 보고 같은 시·군 날에 붙이거나, 빈 날을 반기 안에 고르게."""
    today = today or datetime.date.today()
    if not needs:
        return []
    fac_unit = {}
    for u in units(db, company_id, with_ended=True):
        for m in u.members:
            fac_unit[m.id] = u
    load: dict[datetime.date, DayLoad] = {}
    for v in db.query(SitokVisit).filter(SitokVisit.company_id == company_id, SitokVisit.plan_date > today):
        u = fac_unit.get(v.facility_id)
        if u is None:
            continue
        dl = load.setdefault(v.plan_date, DayLoad())
        dl.buildings += u.buildings
        dl.regions.add(u.region_key)
    lo = min(n.start for n in needs)
    hi = max(n.end for n in needs)
    blocked = blocked_days(lo, hi, korean_holidays(range(lo.year, hi.year + 1)))
    # 반기마다 시·군 차례 → 목표일(반기 창 안에 고르게)
    targets: dict[tuple[int, str], datetime.date] = {}
    for i in sorted({n.index for n in needs}):
        group = [n for n in needs if n.index == i and not n.why]
        if not group:
            continue
        regs = sorted({n.unit.region_key for n in group})
        a, b = min(n.start for n in group), max(n.end for n in group)
        span = (b - a).days
        for k, r in enumerate(regs):
            targets[(i, r)] = a + datetime.timedelta(days=int(span * (k + 0.5) / len(regs)))
    out = []
    order = sorted(needs, key=lambda n: (0 if n.why else 1, n.index, n.unit.region_key, n.unit.lead.id))
    for n in order:
        days = [n.start + DAY * k for k in range((n.end - n.start).days + 1)]
        free = [d for d in days if d not in blocked] or [d for d in days if d.weekday() < 5]
        if not free:
            out.append({"need": n, "date": None, "note": "갈 수 있는 날이 없음"})
            continue
        target = targets.get((n.index, n.unit.region_key), free[0])
        near = lambda ds: min(ds, key=lambda d: (abs((d - target).days), d))  # noqa: E731
        fits = lambda d: load.get(d, DayLoad()).buildings + n.unit.buildings <= DAY_CAP  # noqa: E731
        same = [d for d in free if n.unit.region_key in load.get(d, DayLoad()).regions and fits(d)]
        empty = [d for d in free if not load.get(d) or not load[d].buildings]
        anyfit = [d for d in free if fits(d)]
        note = ""
        if same:
            day = near(same)
            note = "같은 지역과 같은 날"
        elif empty:
            day = near(empty)
        elif anyfit:
            day = near(anyfit)
            note = "다른 지역과 같은 날(빈 날 없음)"
        else:
            day = near(free)
            note = f"하루 {DAY_CAP}곳 넘음 — 날을 바꿔 주세요"
        dl = load.setdefault(day, DayLoad())
        dl.buildings += n.unit.buildings
        dl.regions.add(n.unit.region_key)
        out.append({"need": n, "date": day, "note": note})
    return out


def apply(db: Session, company_id: int, planned: list[dict], by: str) -> list[SitokVisit]:
    rows = []
    for p in planned:
        if p["date"] is None:
            continue
        n: Need = p["need"]
        v = SitokVisit(company_id=company_id, facility_id=n.unit.lead.id, year=n.year, half=n.half, kind=n.kind, plan_date=p["date"],
                       source="auto", created_by=by)
        db.add(v)
        rows.append(v)
    return rows


def fill(db: Session, company_id: int, by: str, facility_ids: list[int] | None = None) -> int:
    """일정 없는 반기를 자동으로 잡음(시설물 등록·계약 연결 때 — 실패해도 등록은 그대로). 넣은 개수."""
    planned = plan(db, company_id, missing(db, company_id, facility_ids=facility_ids))
    return len(apply(db, company_id, planned, by))


def fill_quietly(db: Session, company_id: int, by: str, facility_ids: list[int]) -> int:
    """시설물 등록·계약 연결 뒤 그 시설물 일정 자동(문서 "시설물카드가 등재되면 … 일정생성") — 실패해도 조용히(달력 [자동으로 잡기]로 다시)."""
    import logging

    try:
        n = fill(db, company_id, by, facility_ids)
        db.commit()
        return n
    except Exception:  # noqa: BLE001
        db.rollback()
        logging.getLogger(__name__).exception("시특법 방문 일정 자동 배치 실패")
        return 0


def _selfcheck() -> None:
    assert h_of(h_index(2026, "하반기")) == (2026, "하반기") and d_index(datetime.date(2026, 7, 1)) == h_index(2026, "하반기")
    assert kind_of_title("2026년 정밀안전점검") == "정밀" and kind_of_title("정기·정밀안전점검") == "정기"
    print("방문 달력 계산 검사 통과")


if __name__ == "__main__":
    _selfcheck()
