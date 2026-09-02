"""표3 "기타 특이사항" 행(공사기간 편중/사진촬영 불가/기타/재해발생현황)용 1회성 DB 마이그레이션.

`report` 테이블에 새 컬럼을 추가한다. `migrate_v8_hwp_signatures.py`와 동일한 패턴 — 이미
컬럼이 있으면 건너뛰므로 여러 번 실행해도 안전하다.

실행:
    python -m data.migrate_v9_misc_notes
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "report": [
        ("misc_overwork", "INTEGER DEFAULT 0"),
        ("misc_no_photo", "INTEGER DEFAULT 0"),
        ("misc_other", "INTEGER DEFAULT 0"),
        ("misc_other_text", "TEXT DEFAULT ''"),
        ("accident_status", "TEXT DEFAULT ''"),
        ("accident_content", "TEXT DEFAULT ''"),
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
