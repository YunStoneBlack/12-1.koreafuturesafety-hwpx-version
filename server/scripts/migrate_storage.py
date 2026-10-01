"""예전 저장 구조(data\\photos\\report_N, data\\reports, data\\signatures, data\\materials) → 현장·회차 폴더 구조로 한 번 옮기기(2026-10-01).

    python -m server.scripts.migrate_storage            # 목록만(아무것도 안 바꿈) — 옮길 파일·자리를 data/logs/storage_plan.txt에
    python -m server.scripts.migrate_storage --apply    # 실제로 옮기고 DB 경로를 고침
    python -m server.scripts.migrate_storage --site 141 # 그 현장만(시험용, --apply와 같이)

먼저 백업(server.scripts.backup + data 폴더 복사)하고, API·PDF 작업 프로그램을 새 코드로 재시작한 뒤에 돌린다
(새 코드는 예전 전체 경로·새 상대경로 둘 다 읽으므로 옮기기 전후 모두 화면이 그대로 동작).
규칙·옮기기 함수는 server/api/storage.py(현장명·회차를 바꿀 때 쓰는 것과 같은 함수).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from sqlalchemy import text

from core import config
from core.db import DATA_DIR, SessionLocal, engine
from core import models_web  # noqa: F401 — 회사·사용자 표 정의(현장 표가 가리킴 — 없으면 DB 저장이 실패함)
from core.models_db import Base, MaterialLibrary, Site, Staff
from core.stored_path import StoredPath, to_full, to_stored
from server.api import storage

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _path_columns():
    """StoredPath 칸 전부 — (표 이름, 칸 이름)."""
    for mapper in Base.registry.mappers:
        for col in mapper.columns:
            if isinstance(col.type, StoredPath):
                yield mapper.local_table.name, col.name


def _missing_count(db) -> tuple[int, int, list[str]]:
    """(경로 수, 파일 없는 수, 없는 것 예시)."""
    total, missing, examples = 0, 0, []
    for table, col in _path_columns():
        for (value,) in db.execute(text(f'select "{col}" from "{table}" where "{col}" is not null and "{col}" <> \'\'')):
            total += 1
            if not Path(to_full(value)).exists():
                missing += 1
                if len(examples) < 8:
                    examples.append(f"{table}.{col}: {value}")
    return total, missing, examples


def _move_file(src: Path, dest: Path, plan: list, apply: bool) -> None:
    if storage.same_path(src, dest) or not src.exists():
        return
    plan.append((str(src), str(dest)))
    if apply:
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--site", type=int)
    args = ap.parse_args()
    apply = args.apply
    plan: list[tuple[str, str]] = []

    with SessionLocal() as db:
        before = _missing_count(db)
        sites = db.query(Site).order_by(Site.id).all()
        if args.site:
            sites = [s for s in sites if s.id == args.site]
        # 1) 현장·회차 — 사진·PDF·한글·현장책임자 서명
        for site in sites:
            plan += storage.relocate_site(db, site, dry=not apply)
            if apply:
                db.commit()
        if not args.site:
            # 2) 요원 서명 → _서명
            for staff in db.query(Staff).all():
                if staff.signature_path and Path(staff.signature_path).exists():
                    dest = storage.SIGNATURE_DIR / Path(staff.signature_path).name
                    _move_file(Path(staff.signature_path), dest, plan, apply)
                    if apply:
                        staff.signature_path = str(dest)
            # 3) 결재 도장(설정값) → _서명
            company_ids = [cid for (cid,) in db.execute(text("select id from company"))]
            for cid in company_ids:
                for role in ("director", "ceo"):
                    path, source = config.get_company_signature(role, cid)
                    if path and Path(path).exists():
                        dest = storage.SIGNATURE_DIR / Path(path).name
                        _move_file(Path(path), dest, plan, apply)
                        if apply:
                            config.set_company_signature(role, str(dest), source, cid)
            # 4) 배포 자료 그림 data\materials → _자료실(폴더 구조 그대로)
            old_lib = DATA_DIR / "materials"
            for row in db.query(MaterialLibrary).all():
                for field in ("file_path", "thumbnail_path"):
                    cur = getattr(row, field)
                    if cur and Path(cur).exists() and storage._inside(cur, old_lib):
                        dest = storage.LIBRARY_DIR / Path(os.path.relpath(cur, old_lib))
                        _move_file(Path(cur), dest, plan, apply)
                        if apply:
                            setattr(row, field, str(dest))
            if apply:
                db.commit()
            # 5) 그대로 둔 전체 경로(파일이 없어진 것 등)도 저장소 안이면 상대경로로 적어 둔다
            if apply:
                with engine.begin() as conn:
                    for table, col in _path_columns():
                        rows = conn.execute(text(f'select id, "{col}" from "{table}" where "{col}" like \'%:%\''))
                        for rid, value in rows.fetchall():
                            stored = to_stored(value)
                            if stored != value:
                                conn.execute(text(f'update "{table}" set "{col}" = :v where id = :i'), {"v": stored, "i": rid})
                # 6) 다시 만들어지는 것 — 예전 작은 사진 폴더
                shutil.rmtree(DATA_DIR / "thumbs", ignore_errors=True)
        after = _missing_count(db)

    log = DATA_DIR / "logs" / "storage_plan.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(f"{a}\n  → {b}" for a, b in plan), encoding="utf-8")
    print(f"{'옮김' if apply else '옮길 예정'}: 파일 {len(plan)}개 (목록: {log})")
    for a, b in plan[:6]:
        print(f"  {os.path.relpath(a, DATA_DIR)}\n    → {os.path.relpath(b, DATA_DIR)}")
    print(f"DB 경로 {before[0]}개 중 파일 없는 것: 옮기기 전 {before[1]}개 → 후 {after[1]}개")
    for e in after[2]:
        print("  없음:", e)
    leftovers = [p for d in ("photos", "reports", "signatures", "materials") for p in (DATA_DIR / d).rglob("*") if p.is_file()] \
        if (DATA_DIR / "photos").exists() or (DATA_DIR / "reports").exists() else []
    if apply:
        print(f"예전 폴더에 남은 파일(DB가 안 쓰는 것 — 예전에 바꿔 넣고 남은 사진 등, 백업에 있음): {len(leftovers)}개")


if __name__ == "__main__":
    main()
