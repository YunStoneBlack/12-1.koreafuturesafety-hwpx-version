"""이전지적사항(previous_finding) "이행 전 위험성" 수기 입력값(manual_likelihood/
manual_severity) 컬럼 추가용 1회성 DB 마이그레이션 — 원본(source_finding)이 없는 슬롯(+ 버튼
수기 추가, 옛 보고서 양식이라 이월이 안 된 경우)에서 3번 마법사로 직접 입력할 수 있게 한다.

실행:
    python -m data.migrate_v17_previous_finding_manual_risk
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "previous_finding": [
        ("manual_likelihood", "INTEGER"),
        ("manual_severity", "INTEGER"),
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
