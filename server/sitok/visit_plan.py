"""시특법 방문 달력 — 반기마다 현장 점검 날 자동 배치(2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리").

규칙(문서 그대로 + 내가 정한 것 ★)
- 시설물 카드(묶인 동은 한 카드 — 한 번 가서 다 봄)마다, 계약이 덮는 반기에 하루씩. 장기·지속은 계약기간 안 반기마다(끝 없는 계약은
  ★ 지금 반기부터 3년 = 6반기까지), 1회성은 그 계약 반기만, 지속계약 종료는 안 잡음. 정기·정밀 모두 하루(더 필요하면 사람이 날 추가).
  예) 민간 26~28 정기 + 27 하반기 정밀 → 6번.
- 관급은 착수일부터 1주일 안(그 반기). 지났으면 ★ 그 반기 남은 날 안.
- 같은 시·군 시설물은 같은 날로 묶음, 하루 건물 4개까지(묶인 동은 동 수만큼 셈). ★ 다른 시·군과는 되도록 같은 날에 안 넣고,
  반기 안에서 시·군마다 날을 고르게 벌려 놓음(한쪽에 몰리지 않게). 주말·공휴일·징검다리는 뺌(산안법 달력과 같은 규칙 — visit_scheduler).
- 지난 날·오늘은 안 잡음. 그 반기 보고서를 이미 만들었으면(합본 PDF) 잡지 않음. 이미 그 반기 날이 있으면(자동·사람) 그대로.
  제출 현황에서 현장점검일을 넣었거나 "밖에서 작성 완료"로 표시한 반기도 잡지 않음(10/16 민재형 — 이미 다녀온 현장).
- 계약 정보는 서류 자동화 계약(sitok_doc_contract — 민간 회차 줄·관급 용역 기간)이 먼저, 없으면 보고서 쪽 계약(sitok_contract).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models_web import SitokContract, SitokDocContract, SitokFacility, SitokGroup, SitokReport, SitokVisit
from server.api.visit_scheduler import blocked_days, korean_holidays, region_of
from server.sitok import seasons as SZ

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
    year: int
    half: str  # 상반기·하반기, 연 3회면 해빙기·우기·동절기(10/16)
    kind: str
    start: datetime.date  # 이 날부터
    end: datetime.date  # 이 날까지
    why: str = ""  # 관급 착수 주 등
    pri: int = 0

    @property
    def key(self) -> tuple[int, str]:
        return (self.year, self.half)

    @property
    def index(self) -> int:  # 반기 칸(해빙기·우기 = 상반기, 동절기 = 하반기)
        return h_index(self.year, SZ.bucket(self.half))


def key_sort(k: tuple[int, str]) -> tuple[int, int]:
    return (k[0], SZ.order(k[1]))


def slot_of(db: Session, u: "Unit | None", d: datetime.date) -> tuple[int, str]:
    """그 날 점검이 드는 시기 — 연 3회 시설물(그 해 계약 회차 줄·회차에 해빙기·우기·동절기)이면 그 시기(날이 창 밖이면 가장 가까운 시기), 아니면 반기."""
    y = d.year
    used: set[str] = set()
    if u is not None:
        ids = set(u.ids)
        for c in db.query(SitokDocContract).filter(SitokDocContract.company_id == u.lead.company_id):
            if set(int(x) for x in (c.facility_ids or ([c.facility_id] if c.facility_id else []))) & ids:
                used |= {r.get("half") for r in (c.rounds or []) if r.get("year") == y and SZ.is_season(r.get("half"))}
        for c in db.query(SitokContract).filter(SitokContract.facility_id.in_(ids)):
            used |= {r.get("half") for r in (c.rounds or []) if r.get("year") == y and SZ.is_season(r.get("half"))}
        used |= {r.half for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(ids), SitokReport.year == y) if SZ.is_season(r.half)}
    if not used:
        return h_of(d_index(d))

    def gap(s: str) -> int:
        a, b = SZ.date_range(y, s)
        return 0 if a <= d <= b else min(abs((a - d).days), abs((d - b).days))
    return y, min(used, key=lambda s: (gap(s), SZ.order(s)))


def units(db: Session, company_id: int, with_ended: bool = False) -> list[Unit]:
    facs = db.query(SitokFacility).filter(SitokFacility.company_id == company_id, SitokFacility.survey_only.is_(False), SitokFacility.seismic_only.is_(False)).order_by(SitokFacility.group_order, SitokFacility.id).all()
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
    for u, nm in zip(out, tell_apart([(u.lead, u.members, u.name) for u in out])):
        u.name = nm
    return out


def tell_apart(units: list[tuple[SitokFacility, list[SitokFacility], str]]) -> list[str]:
    """[(대표 동, 동들, 이름)] → 보일 이름 — 같은 현장(번호)에 이름이 같은 보고서가 여럿이면(묶음 이름 = 건물 이름의 같은 앞부분 —
    전엔 뒷번호 관급-9-1·9-2로 갈랐음, 10/19 뒷번호 없앰) 이름 뒤에 건물 이름(그 앞부분 뺀 것). 달력·제출 현황(sitok_status)."""
    from collections import Counter

    key = lambda lead, name: (lead.mgmt_no or f"#{lead.id}", name)  # noqa: E731
    n = Counter(key(lead, name) for lead, _, name in units)
    out = []
    for lead, members, name in units:
        if n[key(lead, name)] > 1 and len(members) > 1:
            name = f"{name} " + "·".join((m.name[len(name):].strip() or m.name) if m.name.startswith(name) else m.name for m in members)
        out.append(name)
    return out


def needs_for(db: Session, u: Unit, today: datetime.date) -> list[Need]:
    """이 시설물 카드가 지금 반기부터 점검해야 하는 반기들(창 = 그 반기 안에서 갈 수 있는 날 범위, 오늘 다음 날부터)."""
    now_i = d_index(today)
    last_i = now_i + HORIZON - 1
    hz_end = h_range(last_i)[1]
    found: dict[tuple[int, str], Need] = {}

    def add(y: int, h: str, kind: str, a: datetime.date | None, b: datetime.date | None, pri: int, why: str = "",
            fb_end: datetime.date | None = None) -> None:
        ha, hb = SZ.date_range(y, h)  # 반기, 연 3회면 해빙기 2~3월·우기 5~6월·동절기 11~12월(10/16)
        if hb <= today or ha > hz_end:
            return
        lo, hi = max(a or ha, ha, today + DAY), min(b or hb, hb)
        if lo > hi and why:  # 관급 착수 주가 지났으면 그 반기 남은 날(계약 끝까지)
            lo, hi, why = max(a or ha, ha, today + DAY), min(fb_end or hb, hb), ""
        if lo > hi:
            return
        old = found.get((y, h))
        if old is None or pri > old.pri:
            found[(y, h)] = Need(u, y, h, kind or "정기", lo, hi, why, pri)

    ids = u.ids
    docs = [d for d in db.query(SitokDocContract).filter(SitokDocContract.company_id == u.lead.company_id).order_by(SitokDocContract.id)
            if set(int(x) for x in (d.facility_ids or ([d.facility_id] if d.facility_id else []))) & set(ids)]  # 시설물 여럿 계약(0052)도
    def only(c, tag: str = "") -> set[int] | None:  # 반기 하나짜리 계약이면 그 반기 칸만(다음 해로 넘어간 완수일이 다음 해 반기를 만들지 않게, 10/25 민재형)
        th = SZ.title_half(c.title)
        if tag in ("상반기", "하반기") and th and th[1] == tag:
            return {h_index(*th)}
        if tag in ("상반기", "하반기") and c.start_date:  # 표시만 있으면 시작 해부터 그 반기 칸들
            return {i for i in range(d_index(c.start_date), d_index(c.end_date or c.start_date) + 1) if h_of(i)[1] == tag}
        return {h_index(*th)} if th else None

    for c in docs:
        if c.sector == "관급":
            if c.start_date is None:
                continue
            end = c.end_date or c.start_date
            k = kind_of_title(c.title)
            keep = only(c, c.half_tag or "")
            for i in range(d_index(c.start_date), d_index(end) + 1):
                if keep is not None and i not in keep:
                    continue
                if i == d_index(c.start_date):
                    add(*h_of(i), k, c.start_date, min(c.start_date + DAY * GOV_WEEK, end), 3, "관급 착수일 1주일 안", fb_end=end)
                else:
                    add(*h_of(i), k, None, end, 2)
            continue
        rounds = [r for r in (c.rounds or []) if r.get("year") and r.get("half")]
        for r in rounds:
            add(int(r["year"]), r["half"], r.get("kind") or "정기", c.start_date, c.end_date, 2)
        if c.open_ended and c.start_date:
            k = (c.unit or {}).get("kind") or "정기"
            for i in range(d_index(c.start_date), last_i + 1):
                add(*h_of(i), k, c.start_date, None, 2)
        elif not rounds and c.start_date:
            keep = only(c, c.half_tag or "")
            for i in range(d_index(c.start_date), d_index(c.end_date or c.start_date) + 1):
                if keep is None or i in keep:
                    add(*h_of(i), kind_of_title(c.title), c.start_date, c.end_date, 2)
    for c in db.query(SitokContract).filter(SitokContract.facility_id.in_(ids)).order_by(SitokContract.id):
        if c.start_date is None:
            continue
        rounds = [r for r in (c.rounds or []) if r.get("year") and r.get("half")]
        if rounds:
            for r in rounds:
                add(int(r["year"]), r["half"], r.get("kind") or "정기", c.start_date, c.end_date, 1)
            continue
        end_i = d_index(c.end_date) if c.end_date else last_i
        keep = only(c) if c.halves not in ("상반기", "하반기") else None  # 연간이어도 건명이 "2026년 하반기 …"면 그 반기만
        for i in range(d_index(c.start_date), end_i + 1):
            if c.halves in ("상반기", "하반기") and h_of(i)[1] != c.halves:
                continue
            if keep is not None and i not in keep:
                continue
            if c.sector == "관급" and i == d_index(c.start_date):
                add(*h_of(i), kind_of_title(c.title), c.start_date, min(c.start_date + DAY * GOV_WEEK, c.end_date or c.start_date + DAY * GOV_WEEK), 1,
                    "관급 착수일 1주일 안", fb_end=c.end_date)
            else:
                add(*h_of(i), kind_of_title(c.title), c.start_date, c.end_date, 1)
    # 종류: 그 반기 회차가 있으면 그 종류, 없으면 계약 회차 줄·계약건명(보고서 쪽 kind_known — 서류 자동화 회차 줄까지 봄)
    from server.api.routers.sitok import contract_for, kind_known

    rep_kind = {(r.year, r.half): r.kind for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(ids)) if r.kind}
    for n in found.values():
        if n.key in rep_kind:
            n.kind = rep_kind[n.key]
        elif n.pri < 2:
            k = kind_known(db, contract_for(db, u.lead, n.year, n.half), n.year, n.half)
            n.kind = k or n.kind
    return sorted(found.values(), key=lambda n: key_sort(n.key))


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
        have = {(v.year, v.half) for v in db.query(SitokVisit).filter(SitokVisit.facility_id.in_(u.ids))}
        done = {(r.year, r.half) for r in db.query(SitokReport).filter(SitokReport.facility_id.in_(u.ids))
                if r.status == "done" or (r.submit or {}).get("field") or (r.submit or {}).get("report")}  # 다녀옴·밖에서 끝남(10/16)
        out += [n for n in ns if n.key not in have and n.key not in done]
    return out


@dataclass
class DayLoad:
    buildings: int = 0
    regions: set = field(default_factory=set)


def merge_unit_visits(db: Session, company_id: int) -> list[dict]:
    """묶음마다 같은 반기 일정은 하나로(10/23 사용자 "묶음별 1개로 일정") — 묶기 전에 동마다 따로 잡힌 일정이 묶은 뒤에도 남아 달력에 같은 묶음이 여러 번
    나오고 건물 수도 여러 번 셌음. 사람이 정한 날(📌)은 다 남기고, 자동은 사람이 정한 날이 있으면 지우고 자동만 있으면 가장 이른 날 하나만.
    남는 일정은 묶음 대표(첫 동)에 붙임. 지운 일정 [{id, facility_id, year, half, date, source}]를 돌려줌(되살리기용 기록)."""
    removed = []
    for u in units(db, company_id, with_ended=True):
        if len(u.members) < 2:
            continue
        by: dict[tuple, list[SitokVisit]] = {}
        for v in db.query(SitokVisit).filter(SitokVisit.facility_id.in_(u.ids)).order_by(SitokVisit.plan_date, SitokVisit.id):
            by.setdefault((v.year, v.half), []).append(v)
        for xs in by.values():
            keep = [v for v in xs if v.source == "manual"] or xs[:1]
            for v in xs:
                if v in keep:
                    v.facility_id = u.lead.id
                    continue
                removed.append({"id": v.id, "facility_id": v.facility_id, "year": v.year, "half": v.half, "kind": v.kind, "date": v.plan_date.isoformat(),
                                "end": v.plan_end.isoformat() if v.plan_end else None, "source": v.source, "memo": v.memo, "created_by": v.created_by, "unit": u.name})
                db.delete(v)
    db.flush()
    return removed


def visit_span(v: SitokVisit) -> tuple[datetime.date, datetime.date]:
    """방문 일정 (시작, 끝) — 끝 날이 없거나 앞이면 하루(0055, 10/19 민재형 "일정을 범위로")."""
    return v.plan_date, max(v.plan_end or v.plan_date, v.plan_date)


def day_share(v: SitokVisit, buildings: int) -> list[tuple[datetime.date, int]]:
    """여러 날 일정의 날마다 건물 수 — 건물을 날 수로 나눠 올림(13개소 3일 → 날마다 5), 하루면 그대로."""
    a, b = visit_span(v)
    n = (b - a).days + 1
    return [(a + datetime.timedelta(days=i), -(-buildings // n)) for i in range(n)]


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
    for v in db.query(SitokVisit).filter(SitokVisit.company_id == company_id, func.coalesce(SitokVisit.plan_end, SitokVisit.plan_date) > today):
        u = fac_unit.get(v.facility_id)
        if u is None:
            continue
        for d, n in day_share(v, u.buildings):  # 여러 날 일정은 건물을 날마다 나눠 셈(10/19)
            if d > today:
                dl = load.setdefault(d, DayLoad())
                dl.buildings += n
                dl.regions.add(u.region_key)
    lo = min(n.start for n in needs)
    hi = max(n.end for n in needs)
    blocked = blocked_days(lo, hi, korean_holidays(range(lo.year, hi.year + 1)))
    # 반기마다 시·군 차례 → 목표일(반기 창 안에 고르게)
    targets: dict[tuple, datetime.date] = {}
    for i in sorted({n.key for n in needs}, key=key_sort):
        group = [n for n in needs if n.key == i and not n.why]
        if not group:
            continue
        regs = sorted({n.unit.region_key for n in group})
        a, b = min(n.start for n in group), max(n.end for n in group)
        span = (b - a).days
        for k, r in enumerate(regs):
            targets[(i, r)] = a + datetime.timedelta(days=int(span * (k + 0.5) / len(regs)))
    out = []
    order = sorted(needs, key=lambda n: (0 if n.why else 1, key_sort(n.key), n.unit.region_key, n.unit.lead.id))
    for n in order:
        days = [n.start + DAY * k for k in range((n.end - n.start).days + 1)]
        free = [d for d in days if d not in blocked] or [d for d in days if d.weekday() < 5]
        if not free:
            out.append({"need": n, "date": None, "note": "갈 수 있는 날이 없음"})
            continue
        target = targets.get((n.key, n.unit.region_key), free[0])
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
