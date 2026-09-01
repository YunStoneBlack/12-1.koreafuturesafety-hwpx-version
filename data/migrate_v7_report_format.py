"""Sub-phase 7(실제 표준 서식 9섹션 개편)용 1회성 DB 마이그레이션.

`core/db.py`의 `init_db()`는 `Base.metadata.create_all()`만 실행하는데, 이건 새 테이블
(`current_process_photo`, `current_process_entry`)은 만들어주지만 이미 존재하는 `report`
테이블에 새 컬럼을 추가해주지는 않는다(오늘 `process_catalog.sort_order` 추가 때도 겪은
문제). 그래서 `report` 테이블에 필요한 컬럼들을 이 스크립트로 한 번 추가한다.

실행:
    python -m data.migrate_v7_report_format
이미 컬럼이 있으면 건너뛰므로 여러 번 실행해도 안전하다.
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS = [
    ("major_hazard_work_checks", "TEXT DEFAULT '[]'"),
    ("machinery_checks", "TEXT DEFAULT '[]'"),
    ("hand_tool_checks", "TEXT DEFAULT '[]'"),
    ("hazmat_checks", "TEXT DEFAULT '[]'"),
    ("current_process_name", "TEXT DEFAULT ''"),
    ("major_hazard_na", "BOOLEAN DEFAULT 0"),
    ("equipment_checks_na", "BOOLEAN DEFAULT 0"),
    ("current_process_na", "BOOLEAN DEFAULT 0"),
]


def migrate() -> None:
    # 새 테이블(current_process_photo/current_process_entry)은 create_all이 알아서 만든다.
    init_db()

    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(report)"))}
        added = []
        for column, ddl in _NEW_COLUMNS:
            if column in existing:
                continue
            conn.execute(text(f"ALTER TABLE report ADD COLUMN {column} {ddl}"))
            added.append(column)
        conn.commit()

    if added:
        print(f"report 테이블에 컬럼 추가됨: {', '.join(added)}")
    else:
        print("추가할 컬럼 없음 (이미 최신 스키마).")


if __name__ == "__main__":
    migrate()
