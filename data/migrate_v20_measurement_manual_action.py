"""계측자료(measurement) "장비사용 조치사항" 수기 입력값(manual_action) 컬럼 추가용
1회성 DB 마이그레이션 — 10번 "사업장 지원 사항" 표16 장비사용 칸의 조치사항이 항상 "-"로
고정돼 있던 것을 마법사에서 직접 입력할 수 있게 한다.

실행:
    python -m data.migrate_v20_measurement_manual_action
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "measurement": [
        ("manual_action", "TEXT DEFAULT ''"),
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
