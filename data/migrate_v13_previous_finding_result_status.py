"""이전지적사항(previous_finding) "이행결과" 3단계 상태(확인불가/보완필요/이행완료)
컬럼 추가용 1회성 DB 마이그레이션 — 기존 `confirmed`(불리언) 컬럼을 대체한다.

기존 `confirmed=True`였던 행은 "이행완료"로, `False`였던 행은 "확인불가"로 이관한다.

실행:
    python -m data.migrate_v13_previous_finding_result_status
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "previous_finding": [
        ("result_status", "TEXT DEFAULT '확인불가'"),
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

        # 기존 confirmed 값을 새 컬럼으로 이관 (confirmed 컬럼이 있을 때만).
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(previous_finding)"))}
        if "confirmed" in existing:
            conn.execute(text("UPDATE previous_finding SET result_status = '이행완료' WHERE confirmed = 1"))
            conn.execute(text("UPDATE previous_finding SET result_status = '확인불가' WHERE confirmed = 0"))

        conn.commit()

    if added:
        print(f"컬럼 추가됨: {', '.join(added)}")
    else:
        print("추가할 컬럼 없음 (이미 최신 스키마).")


if __name__ == "__main__":
    migrate()
