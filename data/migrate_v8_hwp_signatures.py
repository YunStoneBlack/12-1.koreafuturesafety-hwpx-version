"""Sub-phase 8(한글 템플릿 출력 + 관리번호/서명 GUI)용 1회성 DB 마이그레이션.

`site`/`staff`/`report`/`previous_finding`/`safety_education` 테이블에 새 컬럼을 추가한다.
`migrate_v7_report_format.py`와 동일한 패턴 — 이미 컬럼이 있으면 건너뛰므로 여러 번
실행해도 안전하다.

실행:
    python -m data.migrate_v8_hwp_signatures
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "site": [
        ("management_no", "TEXT DEFAULT ''"),
    ],
    "staff": [
        ("signature_path", "TEXT DEFAULT ''"),
        ("signature_source", "TEXT DEFAULT ''"),
    ],
    "report": [
        ("hwp_path", "TEXT DEFAULT ''"),
        ("notify_signee_name", "TEXT DEFAULT ''"),
        ("notify_signature_path", "TEXT DEFAULT ''"),
        ("notify_signature_source", "TEXT DEFAULT ''"),
    ],
    "previous_finding": [
        ("risk_level", "TEXT DEFAULT ''"),
    ],
    "safety_education": [
        ("location", "TEXT DEFAULT ''"),
        ("content", "TEXT DEFAULT ''"),
        ("material", "TEXT DEFAULT ''"),
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
