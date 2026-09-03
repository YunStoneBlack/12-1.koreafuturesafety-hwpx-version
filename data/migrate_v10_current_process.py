"""6번 섹션(현재 진행중인 공정)을 8번 섹션(향후 진행공정)과 같은 표 구조로 통일하기 위한
1회성 DB 마이그레이션 — `current_process_entry` 테이블에 `process_name`/`prevention_text`
컬럼을 추가한다.

`migrate_v9_misc_notes.py`와 동일한 패턴 — 이미 컬럼이 있으면 건너뛰므로 여러 번 실행해도
안전하다.

실행:
    python -m data.migrate_v10_current_process
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "current_process_entry": [
        ("process_name", "TEXT DEFAULT ''"),
        ("prevention_text", "TEXT DEFAULT ''"),
    ],
}


def migrate() -> None:
    init_db()

    with engine.connect() as conn:
        added: list[str] = []
        for table, columns in _NEW_COLUMNS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for column, ddl in columns:
                if column in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                added.append(f"{table}.{column}")
        conn.commit()

    if added:
        print(f"컬럼 추가됨: {', '.join(added)}")
    else:
        print("추가할 컬럼 없음 (이미 최신 스키마).")


if __name__ == "__main__":
    migrate()
