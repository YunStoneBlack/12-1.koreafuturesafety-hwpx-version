"""출장자와 보고서 담당자 나누기(2026-10-02 사용자) — 한국미래안전용 규칙. 정석 규칙(요원 1명 = 출장 = 보고서)은 git 태그 standard-rules-20261002.

- 현장 담당요원(site.assigned_staff_id) = 계약 당시 요원. 보고서·예정을 바꿔도 안 바뀐다(예전엔 보고서 ↔ 현장이 서로 따라 바뀌었음).
- 실제 출장자(visit_plan.staff_id) = 그날 다녀오는 사람. 한 사람 한도 없음, 회사 하루 = 요원 수 × 4곳(day_cap).
- 보고서 담당자(report.assigned_staff_id, 예정은 visit_plan.report_staff_id) = 보고서에 이름이 들어가는 사람(K2B 점검자도).
  한 사람 하루 4곳(core/staff_load.py). 기본 = 직전 회차 보고서 담당 → 1회차면 현장 담당, 그 사람이 그날 4곳이면 보고서 담당 순서
  (설정 — 기본 요원 등록 순, 한국미래안전: 권태형 → 현우선 → 현민재 → 이인숙)에서 여유 있는 사람.
"""
from __future__ import annotations

import datetime
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import VisitPlan
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY as LIMIT


def staff_order(db: Session, company_id: int) -> list[int]:
    """보고서 담당 순서 — 설정에 적힌 순서(쉬는 요원은 뺌) + 설정에 없는 요원은 등록 순으로 뒤에."""
    active = [sid for (sid,) in db.query(Staff.id).filter(Staff.company_id == company_id, Staff.active.is_(True)).order_by(Staff.id)]
    saved = [x for x in config.get_report_staff_order(company_id) if x in active]
    return saved + [x for x in active if x not in saved]


def day_cap(db: Session, company_id: int) -> int:
    """회사 하루 출장 한도 = 일하는 요원 수 × 4(한 사람 보고서 4곳 — 서류로 다 쓸 수 있는 만큼)."""
    return LIMIT * max(1, db.query(Staff).filter(Staff.company_id == company_id, Staff.active.is_(True)).count())


def preferred_map(db: Session, sites: list[Site]) -> dict[int, int | None]:
    """현장 → 보고서 담당 1순위(직전 회차 = 가장 큰 회차 보고서의 담당, 없으면 현장 담당)."""
    ids = [s.id for s in sites]
    out = {s.id: s.assigned_staff_id for s in sites}
    if not ids:
        return out
    latest = dict(db.query(Report.site_id, func.max(Report.visit_no)).filter(Report.site_id.in_(ids)).group_by(Report.site_id))
    for sid, no, staff_id in db.query(Report.site_id, Report.visit_no, Report.assigned_staff_id).filter(Report.site_id.in_(ids)):
        if latest.get(sid) == no and staff_id:
            out[sid] = staff_id
    return out


def paper_load(db: Session, company_id: int, date: datetime.date, exclude_plan_ids: set[int] | None = None) -> dict[int, set[int]]:
    """그날 요원 → 보고서 담당 현장들(그날 보고서 + 아직 보고서가 없는 예정의 보고서 담당자). 같은 현장은 1곳."""
    load: dict[int, set[int]] = defaultdict(set)
    reported = set()
    for sid, staff_id in db.query(Report.site_id, Report.assigned_staff_id).join(Site, Site.id == Report.site_id).filter(
            Site.company_id == company_id, Report.guidance_date == date):
        reported.add(sid)
        if staff_id:
            load[staff_id].add(sid)
    for p in db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date == date):
        if p.site_id not in reported and p.report_staff_id and p.id not in (exclude_plan_ids or set()):
            load[p.report_staff_id].add(p.site_id)
    return load


def has_room(load: dict[int, set[int]], staff_id: int, site_id: int) -> bool:
    """그날 이 사람이 이 현장 보고서를 더 맡을 수 있는지 — 4곳 미만이거나 이미 이 현장을 맡음."""
    here = load.get(staff_id, set())
    return site_id in here or len(here) < LIMIT


def pick(preferred: int | None, load: dict[int, set[int]], order: list[int], site_id: int) -> int | None:
    """1순위가 그날 4곳 미만(또는 이미 이 현장을 맡음)이면 그 사람, 아니면 순서대로 여유 있는 사람. 모두 차면 None."""
    for staff_id in ([preferred] if preferred else []) + [x for x in order if x != preferred]:
        if has_room(load, staff_id, site_id):
            return staff_id
    return None


def free_names(db: Session, load: dict[int, set[int]], order: list[int], exclude: int | None = None) -> str:
    """막을 때 안내 — "현우선(1곳)·현민재(0곳)"처럼 여유 있는 사람을 순서대로."""
    names = dict(db.query(Staff.id, Staff.name).filter(Staff.id.in_(order))) if order else {}
    out = [f"{names[x]}({len(load.get(x, ()))}곳)" for x in order if x != exclude and len(load.get(x, ())) < LIMIT and x in names]
    return "·".join(out)


def _share_out(todo: list[VisitPlan], load: dict[int, set[int]], pref: dict[int, int | None],
               order: list[int]) -> list[tuple[VisitPlan, int | None]]:
    """한 날짜의 예정들에 보고서 담당을 고른다(load에 더해 감) — 새 예정 채우기·다시 나누기가 같은 순서를 쓴다(2026-10-02 리팩토링:
    예전엔 순서가 달라 채운 직후 [다시 나누기]가 24건을 바꾸려 했음). 1순위가 같은 현장끼리 모아(그 사람 4곳을 먼저 채움) 보고서 담당 순서대로,
    같은 1순위 안에서는 지금 이미 1순위로 맞게 된 예정을 먼저 — 규칙에 맞는 지금 나눔은 그대로 남게(넘칠 땐 누구를 돌려도 규칙엔 맞음)."""
    rank = {x: i for i, x in enumerate(order)}
    out = []
    for p in sorted(todo, key=lambda x: (rank.get(pref.get(x.site_id), 99),
                                         0 if x.report_staff_id is not None and x.report_staff_id == pref.get(x.site_id) else 1, x.id)):
        staff_id = pick(pref.get(p.site_id), load, order, p.site_id)
        if staff_id:
            load[staff_id].add(p.site_id)
        out.append((p, staff_id))
    return out


def _pref_for(db: Session, plans: list[VisitPlan]) -> dict[int, int | None]:
    sites = db.query(Site).filter(Site.id.in_({p.site_id for p in plans})).all() if plans else []
    return preferred_map(db, sites)


def assign_new_plans(db: Session, company_id: int, plans: list[VisitPlan]) -> None:
    """보고서 담당자가 비어 있는 예정에 규칙대로 채운다(자동 배치·예정 추가 뒤). 날짜마다 그날 다른 예정·보고서를 센다. commit은 부르는 쪽."""
    todo = [p for p in plans if p.report_staff_id is None]
    if not todo:
        return
    db.flush()
    pref, order = _pref_for(db, todo), staff_order(db, company_id)
    by_date: dict[datetime.date, list[VisitPlan]] = defaultdict(list)
    for p in todo:
        by_date[p.plan_date].append(p)
    for date, day_plans in by_date.items():
        load = paper_load(db, company_id, date, exclude_plan_ids={p.id for p in day_plans})
        for p, staff_id in _share_out(day_plans, load, pref, order):
            p.report_staff_id = staff_id


def redistribute(db: Session, company_id: int, date: datetime.date) -> list[tuple[VisitPlan, int | None]]:
    """그날 보고서가 아직 없는 예정의 보고서 담당자를 처음부터 다시 나눈다(달력 [📝 보고서 담당 다시 나누기]) — (예정, 새 담당) 목록, 저장 안 함."""
    plans = db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date == date).all()
    reported = {sid for (sid,) in db.query(Report.site_id).join(Site, Site.id == Report.site_id).filter(
        Site.company_id == company_id, Report.guidance_date == date)}
    todo = [p for p in plans if p.site_id not in reported]
    load = paper_load(db, company_id, date, exclude_plan_ids={p.id for p in todo})
    return _share_out(todo, load, _pref_for(db, todo), staff_order(db, company_id))


def travelers(db: Session, company_id: int, start: datetime.date, end: datetime.date) -> dict[tuple[int, datetime.date], int]:
    """(현장, 날짜) → 실제 출장자(그날 그 현장 예정의 요원). 보고서의 출장자를 찾을 때 — 예정이 없으면 보고서 담당이 다녀온 것으로 본다."""
    out: dict[tuple[int, datetime.date], int] = {}
    for p in db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date >= start,
                                        VisitPlan.plan_date <= end, VisitPlan.staff_id.isnot(None)).order_by(VisitPlan.id):
        out.setdefault((p.site_id, p.plan_date), p.staff_id)
    return out
