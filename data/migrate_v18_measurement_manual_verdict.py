"""계측자료(measurement) "장비사용 양호/불량" 수동 판정값(manual_verdict) 컬럼 추가용
1회성 DB 마이그레이션 — 10번 "사업장 지원 사항" 표16 장비사용 칸의 양호/불량 판정을
자동계산(조도계/가스농도측정기만) 대신 마법사에서 직접 선택할 수 있게 한다.

실행:
    python -m data.migrate_v18_measurement_manual_verdict
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "measurement": [
        ("manual_verdict", "TEXT DEFAULT ''"),
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
