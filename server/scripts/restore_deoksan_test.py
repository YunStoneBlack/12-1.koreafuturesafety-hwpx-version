"""양주덕산초 2026 하반기 시험 데이터 되돌리기(2026-10-21) — 10/19 형 검토용으로 채운 회차 104(본관)·252(서관)·253(급식실)을 그 전 백업으로.

백업 = data/_시험백업/dk_backup_20261019.json(10/19 13:05, 시험 전 — 회차 칸 22개·결함 줄·회차 폴더 파일 목록·방문 일정). 분권 배정도 회차 survey 안이라 같이 돌아감.
- 회차 칸: 백업 값으로(현장점검일·AI 초안·전경·면담·분권·만든 파일 이름 등 — 10/20 형이 넣은 현장점검일 10/23도 지워짐).
- 결함 줄: 지금 줄을 지우고 백업 줄을 같은 id로 다시 넣음(백업 125줄 = 전회차 가져오기로 들어온 것).
- 회차 폴더: 백업 목록에 없는 파일(시험 중 생긴 사진·보고서·분권 등)은 지우지 않고 data/_시험백업/deoksan_되돌림_<시각>/회차/로 옮김.
  백업 뒤에 없어진 파일은 되살릴 수 없어 이름만 알려 줌.
- 방문 일정: 백업에 있던 줄(id 11)의 날짜·자동 표시만 되돌림. 그 뒤에 더 생긴 줄은 실제 일정일 수 있어 보여 주기만 함.

    python -m server.scripts.restore_deoksan_test           # 바뀔 것만 보여 줌(DB·파일 안 바꿈)
    python -m server.scripts.restore_deoksan_test --apply   # 실제로 되돌림(보고서 만드는 중이면 안 함)
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import server.settings  # noqa: E402,F401
from sqlalchemy import Date, DateTime  # noqa: E402

from core.db import DATA_DIR, SessionLocal  # noqa: E402
from core.models_web import SitokDefect, SitokFacility, SitokReport, SitokVisit  # noqa: E402

BACKUP = DATA_DIR / "_시험백업" / "dk_backup_20261019.json"
REPORTS = (104, 252, 253)


def _typed(model, col: str, v):
    """JSON에 글자로 들어간 날짜·시각을 칸 형식으로."""
    if v in (None, ""):
        return None if v is None else v
    t = model.__table__.columns[col].type
    if isinstance(t, DateTime) and isinstance(v, str):
        return datetime.datetime.fromisoformat(v)
    if isinstance(t, Date) and isinstance(v, str):
        return datetime.date.fromisoformat(v[:10])
    return v


def _short(v) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else str(v)
    return s if len(s) <= 60 else s[:57] + "…"


def _report_dir(db, r: SitokReport) -> Path:
    from server.api.routers.sitok_reports import _report_dir

    return _report_dir(db.get(SitokFacility, r.facility_id), r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 되돌림(없으면 보여 주기만)")
    a = ap.parse_args()
    if not BACKUP.exists():
        print("백업 파일이 없습니다:", BACKUP)
        return 1
    bk = json.loads(BACKUP.read_text(encoding="utf-8"))
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash = DATA_DIR / "_시험백업" / f"deoksan_되돌림_{stamp}"
    with SessionLocal() as db:
        busy = [r.id for r in db.query(SitokReport).filter(SitokReport.id.in_(REPORTS)) if r.status == "running"]
        busy += [r.id for r in db.query(SitokReport).filter(SitokReport.id.in_(REPORTS)) if ((r.survey or {}).get("split") or {}).get("status") == "running"]
        if busy:
            print("보고서·분권을 만드는 중입니다 — 끝난 뒤에 다시:", busy)
            return 2
        moves: list[tuple[Path, Path]] = []
        for rid in REPORTS:
            r = db.get(SitokReport, rid)
            f = db.get(SitokFacility, r.facility_id)
            old = bk["reports"][str(rid)]
            print(f"\n== 회차 {rid} {f.name}")
            changed = [(c, getattr(r, c), _typed(SitokReport, c, v)) for c, v in old.items() if getattr(r, c) != _typed(SitokReport, c, v)]
            for c, now, want in changed:
                print(f"  칸 {c}: {_short(now)}  →  {_short(want)}")
                if a.apply:
                    setattr(r, c, want)
            if not changed:
                print("  칸: 바뀐 것 없음")
            # 결함
            now_d = db.query(SitokDefect).filter(SitokDefect.report_id == rid).all()
            old_d = bk["defects"][str(rid)]
            print(f"  결함: 지금 {len(now_d)}줄 → 백업 {len(old_d)}줄")
            if a.apply:
                for d in now_d:
                    db.delete(d)
                db.flush()
                for row in old_d:
                    clash = db.get(SitokDefect, row["id"])
                    if clash is not None:  # 다른 회차가 그 id를 쓰고 있으면 새 id로
                        row = {k: v for k, v in row.items() if k != "id"}
                    db.add(SitokDefect(**{k: _typed(SitokDefect, k, v) for k, v in row.items()}))
            # 파일
            folder = _report_dir(db, r)
            keep = {Path(p).as_posix() for p in bk["files"][str(rid)]["list"]}
            have = {p.relative_to(folder).as_posix(): p for p in folder.rglob("*") if p.is_file()} if folder.exists() else {}
            extra = sorted(k for k in have if k not in keep)
            gone = sorted(k for k in keep if k not in have)
            print(f"  파일: 폴더 {folder}")
            print(f"        백업 {len(keep)}개 · 지금 {len(have)}개 · 옮길 것(시험 중 생김) {len(extra)}개 · 없어진 것 {len(gone)}개")
            for k in extra[:12]:
                print("        + ", k)
            if len(extra) > 12:
                print(f"        + … {len(extra) - 12}개 더")
            for k in gone[:12]:
                print("        - (되살릴 수 없음)", k)
            moves += [(have[k], trash / str(rid) / k) for k in extra]
        # 방문 일정
        ids = {db.get(SitokReport, i).facility_id for i in REPORTS}
        old_v = {v["id"]: v for v in bk["visits"]}
        print("\n== 방문 일정")
        for v in db.query(SitokVisit).filter(SitokVisit.facility_id.in_(ids)).order_by(SitokVisit.plan_date):
            o = old_v.pop(v.id, None)
            if o is None:
                print(f"  (백업 뒤 생긴 줄 — 그대로 둠) id {v.id} 시설물 {v.facility_id} {v.year} {v.half} {v.plan_date} {v.source}")
            elif str(v.plan_date) != o["plan_date"] or v.source != o["source"]:
                print(f"  id {v.id}: {v.plan_date} {v.source}  →  {o['plan_date']} {o['source']}")
                if a.apply:
                    v.plan_date, v.source = datetime.date.fromisoformat(o["plan_date"]), o["source"]
            else:
                print(f"  id {v.id}: 그대로 {v.plan_date} {v.source}")
        for o in old_v.values():
            print(f"  (백업엔 있고 지금 없음 — 다시 안 만듦) id {o['id']} {o['plan_date']}")
        if not a.apply:
            db.rollback()
            print("\n보여 주기만 했습니다. 실제로 되돌리려면 --apply")
            return 0
        db.commit()
    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    print(f"\n되돌렸습니다. 옮긴 파일 {len(moves)}개 → {trash if moves else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
