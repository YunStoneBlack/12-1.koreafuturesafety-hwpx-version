"""방문 예정의 보고서 담당자 채우기(2026-10-02, alembic 0016 뒤 한 번 — 운영 DB는 이미 채움) — 날짜마다 달력 [📝 보고서 담당 다시 나누기]와
같은 규칙으로(server/api/report_staff.redistribute): 직전 회차 보고서 담당 → 현장 담당, 그 사람이 그날 4곳이면 보고서 담당 순서에서 여유 있는 사람.
보고서를 이미 만든 현장·날짜는 건드리지 않는다.

실행: (프로젝트 폴더에서, .env.server의 DATABASE_URL로) python -m server.scripts.fill_report_staff [--dry-run]
"""
from __future__ import annotations

import sys
from collections import Counter

from core import models_web  # noqa: F401 — 회사 표 정의(외래키)
from core.db import SessionLocal
from core.models_db import Staff
from core.models_web import VisitPlan
from server.api.report_staff import redistribute


def main(dry_run: bool) -> None:
    with SessionLocal() as db:
        names = dict(db.query(Staff.id, Staff.name))
        for (cid,) in db.query(VisitPlan.company_id).distinct():
            dates = sorted(d for (d,) in db.query(VisitPlan.plan_date).filter(VisitPlan.company_id == cid).distinct())
            changed: Counter = Counter()
            for d in dates:
                for p, new in redistribute(db, cid, d):
                    if p.report_staff_id != new:
                        p.report_staff_id = new
                        changed[names.get(new, "비어 있음(그날 모두 4곳)")] += 1
                db.flush()
            print(f"회사 {cid}: 날짜 {len(dates)}일, 바뀐 예정 {sum(changed.values())}건 — " + ", ".join(f"{k} {v}" for k, v in changed.most_common()))
        if dry_run:
            db.rollback()
            print("(--dry-run — 저장 안 함)")
        else:
            db.commit()
            print("저장했습니다.")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
