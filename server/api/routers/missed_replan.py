"""방문 달력 예정 정리 두 가지(2026-10-10 사용자·민재형) — 남은 횟수(총 횟수 − 다녀온 횟수)와 오늘 이후 예정 수를 맞춘다.

1) [🔁 지난 일정 재배치] — 날짜가 지났는데 보고서가 없는 예정("지난 예정").
   - `GET  /calendar/missed` — 건수(버튼 "지난 일정 재배치 N").
   - `POST /calendar/missed/replan` — body `dry_run`(True = 미리보기만). 현장마다 모자란 만큼은 지난 예정을 새 날짜로 옮기고(오래된 것부터,
     📌 고정 — [일정 변경]으로 옮긴 것과 같음), 넉넉하면(또는 진행 중이 아닌 현장이면) 지운다. 넣을 날이 없으면 그대로 둔다.
     (민재형: "지난 일정을 지워도 잔여횟수가 다 달력에 있나?" → 아님, 10/10 실데이터 6곳 모두 모자람)
2) "⚠ 예정이 모자란 현장 N곳" 안내 + [채워 넣기](민재형: 자동 배치가 일정 짜다 애매하면 횟수를 다 안 채워 넣는 듯 — 맞음, 규칙에 막히면
   넣을 수 있는 만큼만 넣고 넣은 뒤엔 다시 알려 주는 곳이 없었음).
   - `GET  /calendar/short` — 진행 중·준공 전 현장 중 남은 횟수 > 오늘 이후 예정 수인 곳.
   - `POST /calendar/short/fill` — body `site_ids`(없으면 전부)·`dry_run`. 모자란 횟수만큼 새 자동 예정을 더한다(기존 예정은 그대로).
     날짜는 그 현장 다른 방문과 간격이 고르게(남은 기간 ÷ 남은 횟수만큼은 떨어지게) → 그 안에선 같은 지역 출장에 붙이기 → 이른 날.

공통 날짜 규칙(DayPicker): 내일 ~ 마감(준공 − 자동 배치 "준공 며칠 전" 설정, 준공일 없으면 석 달), 주말·공휴일·징검다리 빼기, 그 현장이 이미 잡힌 날 빼기,
회사 하루 한도(report_staff.day_cap), 그 요원이 원래 안 나가는 날이면 하루 출장 인원(설정, 기본 2명)을 넘지 않게, 같은 지역 출장 궁합은
[일정 변경](server/api/routers/plan_change.py)과 같은 함수. 현장 자동 배치를 다시 돌리지 않는 이유: 그새 바뀐 규칙(하루 출장 인원 등) 때문에
기존 예정이 오히려 줄어든다(10/10 확인 — 19건 → 6건).
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import User, VisitPlan
from server.api.deps import get_current_user, get_db
from server.api.report_staff import assign_new_plans, day_cap, has_room, paper_load, preferred_map
from server.api.routers.plan_change import _compat, _day_sites, _together
from server.api.site_label import site_label
from server.api.site_pace_out import done_counts
from server.api.site_status import is_active
from server.api.visit_scheduler import blocked_days, korean_holidays

router = APIRouter(prefix="/calendar", tags=["plan-fix"])
DAY = datetime.timedelta(days=1)
JOIN_WINDOW_DAYS = 21  # 지난 일정은 내일부터 이 안의 같은 지역 출장에 붙인다(plan_change.SUGGEST_WINDOW_DAYS와 같은 폭)
FALLBACK_DAYS = 90  # 준공일이 없는 현장은 내일부터 석 달 안에서


class DayPicker:
    """내일 ~ 가장 늦은 마감 사이의 날짜별 출장 상황(DB 그대로 + 이번에 넣기로 한 것) — DB는 안 바꾼다."""

    def __init__(self, db: Session, company_id: int, today: datetime.date, sites: dict[int, Site], end: datetime.date):
        self.today, self.sites = today, sites
        self.start = today + DAY
        self.end = max(self.start, end)
        _, self.compat, self.dist = _compat(db, company_id, sites)
        self.blocked = blocked_days(self.start, self.end, korean_holidays({self.start.year, self.end.year}))
        self.busy, self.total = _day_sites(db, company_id, self.start, self.end, None)  # (요원, 날짜) → 현장들, 날짜 → 회사 전체 현장들
        self.cap = day_cap(db, company_id)
        self.max_travelers = config.get_plan_max_travelers(company_id)
        self.travelers: dict[datetime.date, set[int]] = defaultdict(set)
        for (staff, d), here in self.busy.items():
            if here:
                self.travelers[d].add(staff)

    def site_dates(self, site_id: int) -> list[datetime.date]:
        return sorted(d for d, here in self.total.items() if site_id in here)

    def candidates(self, site_id: int, staff_id: int | None, limit: datetime.date):
        """[(날짜, 같이 가는 현장 이름들, 같은 지역 출장인지)] — 갈 수 있는 날만."""
        out = []
        d = self.start
        while d <= min(limit, self.end):
            day_total = self.total.get(d, set())
            if not self.blocked.get(d) and site_id not in day_total and len(day_total) < self.cap:
                here = self.busy.get((staff_id, d), set()) if staff_id is not None else set()
                ok, far = _together(self.sites, self.compat, site_id, here)
                new_traveler = staff_id is not None and not here and staff_id not in self.travelers.get(d, set())
                if not far and not (new_traveler and len(self.travelers.get(d, set())) >= self.max_travelers):
                    out.append((d, [n for n, _ in ok], bool(ok)))
            d += DAY
        return out

    def take(self, site_id: int, staff_id: int | None, day: datetime.date) -> None:
        self.total[day].add(site_id)
        if staff_id is not None:
            self.busy[(staff_id, day)].add(site_id)
            self.travelers[day].add(staff_id)


def _limit(site: Site | None, today: datetime.date, finish: int) -> datetime.date:
    return site.period_end - datetime.timedelta(days=finish) if site and site.period_end else today + datetime.timedelta(days=FALLBACK_DAYS)


def _needs(db: Session, sites: list[Site], today: datetime.date) -> dict[int, tuple[int, int]]:
    """현장 → (남은 횟수, 오늘 이후(오늘 포함) 예정 수)."""
    ids = [s.id for s in sites]
    if not ids:
        return {}
    done = done_counts(db, ids)
    upcoming = Counter(sid for (sid,) in db.query(VisitPlan.site_id).filter(VisitPlan.site_id.in_(ids), VisitPlan.plan_date >= today))
    return {s.id: (max(0, (s.total_guidance_count or 0) - (done.get(s.id) or 0)), upcoming[s.id]) for s in sites}


def _short_label(why_limit: datetime.date, finish: int) -> str:
    return f"마감({why_limit.month}/{why_limit.day}, 준공 {finish}일 전)까지 넣을 날이 부족합니다"


# ---------- 1) 지난 일정 재배치 ----------

def _missed(db: Session, company_id: int, today: datetime.date) -> list[VisitPlan]:
    """지난 예정 = 오늘 전 날짜인데 그 현장·그 날짜 보고서가 없는 예정(방문 달력 state "missed"와 같은 기준)."""
    plans = (db.query(VisitPlan).filter(VisitPlan.company_id == company_id, VisitPlan.plan_date < today)
             .order_by(VisitPlan.plan_date, VisitPlan.id).all())
    if not plans:
        return []
    visited = set(db.query(Report.site_id, Report.guidance_date).filter(
        Report.site_id.in_({p.site_id for p in plans}), Report.guidance_date.isnot(None)))
    return [p for p in plans if (p.site_id, p.plan_date) not in visited]


@router.get("/missed")
def missed_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"count": len(_missed(db, user.company_id, datetime.date.today()))}


class ReplanIn(BaseModel):
    dry_run: bool = True


def _compute_missed(db: Session, company_id: int, today: datetime.date):
    """[(지난 예정, "move"|"delete"|"stuck", 새 날짜, 같이 가는 현장 이름들, 이유, 출장자)], 현장들, DayPicker.
    출장자는 원래 예정의 요원 — 그 요원으로 갈 날이 없으면(평소 출장이 없어 날마다 하루 출장 인원에 막히는 등) 그 현장 앞으로 예정의 요원으로."""
    missed = _missed(db, company_id, today)
    if not missed:
        return [], {}, None
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == company_id)}
    targets = [sites[sid] for sid in sorted({p.site_id for p in missed}) if sid in sites]
    finish = config.get_plan_finish_before_days(company_id)
    limits = {s.id: _limit(s, today, finish) for s in targets}
    picker = DayPicker(db, company_id, today, sites, max(limits.values(), default=today))
    need_left = {sid: (rem - up if is_active(sites[sid]) else 0) for sid, (rem, up) in _needs(db, targets, today).items()}
    first = preferred_map(db, targets)

    out = []
    for p in missed:  # 오래된 것부터 — 모자란 만큼만 옮기고 나머지는 지운다
        sid = p.site_id
        if need_left.get(sid, 0) <= 0:
            s = sites.get(sid)
            why = "진행 중이 아닌 현장" if s is not None and not is_active(s) else "남은 횟수만큼 앞으로 예정이 이미 있음"
            out.append((p, "delete", None, [], why, p.staff_id))
            continue
        pick, staff_id = None, p.staff_id
        for staff_id in dict.fromkeys([p.staff_id, _traveler(db, sites[sid], today, first)]):
            cands = picker.candidates(sid, staff_id, limits[sid])
            join = [c for c in cands if c[2] and (c[0] - today).days <= JOIN_WINDOW_DAYS]
            free = [c for c in cands if not c[1]]
            pick = join[0] if join else free[0] if free else cands[0] if cands else None
            if pick is not None:
                break
        if pick is None:
            out.append((p, "stuck", None, [], _short_label(limits[sid], finish), p.staff_id))
            continue
        picker.take(sid, staff_id, pick[0])
        need_left[sid] -= 1
        why = "같은 지역 출장에 붙임" if pick[2] else "그 요원이 비는 가장 이른 평일"
        out.append((p, "move", pick[0], pick[1], why if staff_id == p.staff_id else f"{why} · 출장자를 이 현장 다른 예정의 요원으로", staff_id))
    return out, sites, picker


@router.post("/missed/replan")
def replan(body: ReplanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    items, sites, picker = _compute_missed(db, user.company_id, today)
    names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == user.company_id))
    rows = [{
        "plan_id": p.id, "site_id": p.site_id, "site_name": site_label(sites[p.site_id]) if p.site_id in sites else "",
        "staff_name": names.get(staff, ""), "old_date": p.plan_date.isoformat(), "action": action,
        "new_date": day.isoformat() if day else "", "with": with_, "reason": why,
    } for p, action, day, with_, why, staff in items]
    counts = {k: sum(r["action"] == k for r in rows) for k in ("move", "delete", "stuck")}
    if not body.dry_run:
        for p, action, day, _, _, staff in items:
            if action == "delete":
                db.delete(p)
            elif action == "move":
                p.plan_date = day
                p.staff_id = staff
                p.source = "manual"  # 사람이 [일정 변경]으로 옮긴 것과 같이 📌 고정(자동 배치가 다시 짜지 않게)
                db.flush()
                # 그날 보고서 담당자가 이미 4곳이면 규칙대로 다시 고른다(PATCH /calendar/plans와 같음)
                if p.report_staff_id is not None and not has_room(
                        paper_load(db, user.company_id, day, exclude_plan_ids={p.id}), p.report_staff_id, p.site_id):
                    p.report_staff_id = None
                    assign_new_plans(db, user.company_id, [p])
        db.commit()
    if picker is not None:
        picker.dist.save()  # 이번에 새로 물은 도로 거리 저장(예정은 위에서 이미 확정 — 미리보기면 바뀐 것 없음)
    return {"ok": True, "dry_run": body.dry_run, "counts": counts, "items": rows}


# ---------- 2) 예정이 모자란 현장 ----------

def _short_sites(db: Session, company_id: int, today: datetime.date):
    """[(현장, 남은 횟수, 예정 수)] — 진행 중·준공 전·총 횟수 있음."""
    sites = [s for s in db.query(Site).filter(Site.company_id == company_id)
             if is_active(s) and s.total_guidance_count and s.period_end and s.period_end > today]
    needs = _needs(db, sites, today)
    return [(s, rem, up) for s in sites for rem, up in [needs[s.id]] if rem > up]


@router.get("/short")
def short_list(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == user.company_id))
    return sorted(({"site_id": s.id, "site_name": site_label(s), "staff_name": names.get(s.assigned_staff_id, ""),
                    "remaining": rem, "planned": up, "short": rem - up} for s, rem, up in _short_sites(db, user.company_id, today)),
                  key=lambda x: (-x["short"], x["staff_name"], x["site_name"]))


class FillIn(BaseModel):
    site_ids: list[int] | None = None  # 없으면 모자란 현장 전부
    dry_run: bool = True


def _traveler(db: Session, site: Site, today: datetime.date, first: dict[int, int | None]) -> int | None:
    """새 예정의 출장자 = 그 현장 앞으로 예정에 가장 많이 잡힌 요원, 없으면 1순위(직전 회차 보고서 담당 → 현장 담당)."""
    staff = Counter(sid for (sid,) in db.query(VisitPlan.staff_id).filter(
        VisitPlan.site_id == site.id, VisitPlan.plan_date >= today, VisitPlan.staff_id.isnot(None)))
    return staff.most_common(1)[0][0] if staff else first.get(site.id)


@router.post("/short/fill")
def fill(body: FillIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    cid = user.company_id
    short = [x for x in _short_sites(db, cid, today) if body.site_ids is None or x[0].id in body.site_ids]
    names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == cid))
    if not short:
        return {"ok": True, "dry_run": body.dry_run, "added": 0, "stuck": 0, "items": []}
    all_sites = {s.id: s for s in db.query(Site).filter(Site.company_id == cid)}
    finish = config.get_plan_finish_before_days(cid)
    limits = {s.id: _limit(s, today, finish) for s, _, _ in short}
    picker = DayPicker(db, cid, today, all_sites, max(limits.values()))
    first = preferred_map(db, [s for s, _, _ in short])
    items = []  # {site, staff_id, date|None, with, reason}
    for s, rem, up in sorted(short, key=lambda x: limits[x[0].id]):  # 마감이 이른 현장부터(자리가 더 귀함)
        staff_id = _traveler(db, s, today, first)
        gap = max(1, (limits[s.id] - today).days // max(1, rem))  # 고르게 — 남은 기간 ÷ 남은 횟수
        for _ in range(rem - up):
            cands = picker.candidates(s.id, staff_id, limits[s.id])
            if not cands:
                items.append({"site": s, "staff_id": staff_id, "date": None, "with": [], "reason": _short_label(limits[s.id], finish)})
                continue
            taken = picker.site_dates(s.id) + [today]
            spread = lambda d: min(min(abs((d - t).days) for t in taken), gap)  # 다른 방문과 떨어진 정도(간격 넘으면 똑같이 좋음)
            d, with_, joined = max(cands, key=lambda c: (spread(c[0]), c[2], -c[0].toordinal()))
            picker.take(s.id, staff_id, d)
            items.append({"site": s, "staff_id": staff_id, "date": d, "with": with_,
                          "reason": "같은 지역 출장에 붙임" if joined else "그 요원이 비는 날"})

    if not body.dry_run:
        added = []
        for it in items:
            if it["date"] is None:
                continue
            plan = VisitPlan(company_id=cid, site_id=it["site"].id, staff_id=it["staff_id"], plan_date=it["date"],
                             memo="", source="auto", created_by=user.display_name or "")
            db.add(plan)
            added.append(plan)
        assign_new_plans(db, cid, added)  # 보고서 담당자(한 사람 하루 4곳, 넘치면 순서대로)
        db.commit()
    picker.dist.save()
    rows = [{"site_id": it["site"].id, "site_name": site_label(it["site"]), "staff_name": names.get(it["staff_id"], ""),
             "date": it["date"].isoformat() if it["date"] else "", "with": it["with"], "reason": it["reason"]}
            for it in sorted(items, key=lambda it: (it["date"] or datetime.date.max, site_label(it["site"])))]
    return {"ok": True, "dry_run": body.dry_run, "added": sum(1 for it in items if it["date"]),
            "stuck": sum(1 for it in items if it["date"] is None), "items": rows}
