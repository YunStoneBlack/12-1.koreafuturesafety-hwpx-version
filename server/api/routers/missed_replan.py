"""방문 달력 [🔁 지난 일정 재배치](2026-10-10 사용자·민재형) — 날짜가 지났는데 보고서가 없는 예정("지난 예정")을 한 번에 정리.

- `GET  /calendar/missed` — 지난 예정 건수(버튼에 "지난 일정 재배치 N"으로).
- `POST /calendar/missed/replan` — body `dry_run`: True면 미리보기만(저장 안 함), False면 같은 계산으로 저장.

현장마다 "남은 횟수(총 횟수 − 다녀온 횟수) − 오늘 이후 예정 수" = 모자란 횟수(민재형: 지워도 잔여 횟수가 다 달력에 있나? → 아님).
- 모자란 만큼은 지난 예정을 **새 날짜로 옮긴다**(오래된 것부터, 📌 고정 — [일정 변경]으로 옮긴 것과 같음).
  날짜 = 내일부터 마감(준공 − 자동 배치 "준공 며칠 전" 설정)까지에서 같은 요원의 같은 지역 출장에 붙이기 → 그 요원이 비는 가장 이른 평일.
  주말·공휴일·징검다리, 회사 하루 한도, 그 현장이 이미 잡힌 날은 뺀다. 넣을 날이 없으면 그대로 둔다("넣을 날이 부족").
- 이미 넉넉하면(또는 진행 중이 아닌 현장이면) 지난 예정은 **지운다**.
다른 예정은 건드리지 않는다 — 현장 자동 배치를 다시 돌리면 그새 바뀐 규칙(하루 출장 인원 등) 때문에 기존 예정이 줄어들 수 있어서(10/10 확인).
규칙·궁합은 [일정 변경](server/api/routers/plan_change.py)과 같은 함수를 쓴다.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import config
from core.models_db import Report, Site, Staff
from core.models_web import User, VisitPlan
from server.api.deps import get_current_user, get_db
from server.api.report_staff import assign_new_plans, day_cap, has_room, paper_load
from server.api.routers.plan_change import _compat, _day_sites, _together
from server.api.site_label import site_label
from server.api.site_pace_out import done_counts
from server.api.site_status import is_active
from server.api.visit_scheduler import blocked_days, korean_holidays

router = APIRouter(prefix="/calendar", tags=["missed-replan"])
DAY = datetime.timedelta(days=1)
JOIN_WINDOW_DAYS = 21  # 같은 지역 출장에 붙일 땐 내일부터 이 안에서 찾는다(plan_change.SUGGEST_WINDOW_DAYS와 같은 폭)
FALLBACK_DAYS = 90  # 준공일이 없는 현장은 내일부터 석 달 안에서


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


def _compute(db: Session, company_id: int, today: datetime.date):
    """[(지난 예정, 할 일 "move"|"delete"|"stuck", 새 날짜, 같이 가는 현장 이름들, 이유)], 현장들, 거리 — DB는 안 바꾼다."""
    missed = _missed(db, company_id, today)
    if not missed:
        return [], {}, None
    sites = {s.id: s for s in db.query(Site).filter(Site.company_id == company_id)}
    site_ids = sorted({p.site_id for p in missed})
    done = done_counts(db, site_ids)
    upcoming = defaultdict(int)  # 오늘 이후(오늘 포함) 예정 수
    for (sid,) in db.query(VisitPlan.site_id).filter(VisitPlan.site_id.in_(site_ids), VisitPlan.plan_date >= today):
        upcoming[sid] += 1
    finish = config.get_plan_finish_before_days(company_id)
    start = today + DAY
    limits = {}
    for sid in site_ids:
        s = sites.get(sid)
        limits[sid] = (s.period_end - datetime.timedelta(days=finish)) if s and s.period_end else today + datetime.timedelta(days=FALLBACK_DAYS)
    end = max([start, *limits.values()])

    _, compat, dist = _compat(db, company_id, sites)
    blocked = blocked_days(start, end, korean_holidays({start.year, end.year}))
    busy, total = _day_sites(db, company_id, start, end, None)  # (요원, 날짜) → 현장들, 날짜 → 회사 전체 현장들
    cap = day_cap(db, company_id)

    out = []
    need_left = {}
    for sid in site_ids:
        s = sites.get(sid)
        remaining = max(0, (s.total_guidance_count or 0) - (done.get(sid) or 0)) if s else 0
        need_left[sid] = remaining - upcoming[sid] if s and is_active(s) else 0
    for p in missed:  # 오래된 것부터 — 모자란 만큼만 옮기고 나머지는 지운다
        sid = p.site_id
        if need_left[sid] <= 0:
            s = sites.get(sid)
            why = "진행 중이 아닌 현장" if s is not None and not is_active(s) else "남은 횟수만큼 앞으로 예정이 이미 있음"
            out.append((p, "delete", None, [], why))
            continue
        limit = limits[sid]
        cands = []
        d = start
        while d <= limit:
            day_total = total.get(d, set())
            if not blocked.get(d) and sid not in day_total and len(day_total) < cap:
                here = busy.get((p.staff_id, d), set()) if p.staff_id is not None else set()
                ok, far = _together(sites, compat, sid, here)
                cands.append((d, here, ok, far))
            d += DAY
        join = [c for c in cands if c[2] and not c[3] and (c[0] - today).days <= JOIN_WINDOW_DAYS]
        free = [c for c in cands if not c[1]]
        pick = join[0] if join else free[0] if free else None
        if pick is None:
            out.append((p, "stuck", None, [], f"마감({limit.month}/{limit.day}, 준공 {finish}일 전)까지 넣을 날이 부족합니다"))
            continue
        day = pick[0]
        total[day].add(sid)
        if p.staff_id is not None:
            busy[(p.staff_id, day)].add(sid)
        need_left[sid] -= 1
        out.append((p, "move", day, [n for n, _ in pick[2]], "같은 지역 출장에 붙임" if pick[2] else "그 요원이 비는 가장 이른 평일"))
    return out, sites, dist


@router.post("/missed/replan")
def replan(body: ReplanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    items, sites, dist = _compute(db, user.company_id, today)
    names = dict(db.query(Staff.id, Staff.name).filter(Staff.company_id == user.company_id))
    rows = [{
        "plan_id": p.id, "site_id": p.site_id, "site_name": site_label(sites[p.site_id]) if p.site_id in sites else "",
        "staff_name": names.get(p.staff_id, ""), "old_date": p.plan_date.isoformat(), "action": action,
        "new_date": day.isoformat() if day else "", "with": with_, "reason": why,
    } for p, action, day, with_, why in items]
    counts = {k: sum(r["action"] == k for r in rows) for k in ("move", "delete", "stuck")}
    if not body.dry_run:
        for p, action, day, _, _ in items:
            if action == "delete":
                db.delete(p)
            elif action == "move":
                p.plan_date = day
                p.source = "manual"  # 사람이 [일정 변경]으로 옮긴 것과 같이 📌 고정(자동 배치가 다시 짜지 않게)
                db.flush()
                # 그날 보고서 담당자가 이미 4곳이면 규칙대로 다시 고른다(PATCH /calendar/plans와 같음)
                if p.report_staff_id is not None and not has_room(
                        paper_load(db, user.company_id, day, exclude_plan_ids={p.id}), p.report_staff_id, p.site_id):
                    p.report_staff_id = None
                    assign_new_plans(db, user.company_id, [p])
        db.commit()
    if dist is not None:
        dist.save()  # 이번에 새로 물은 도로 거리 저장(예정은 위에서 이미 확정 — 미리보기면 바뀐 것 없음)
    return {"ok": True, "dry_run": body.dry_run, "counts": counts, "items": rows}
