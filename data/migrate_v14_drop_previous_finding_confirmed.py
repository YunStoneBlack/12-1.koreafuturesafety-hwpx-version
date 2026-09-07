"""이전지적사항(previous_finding)의 옛 `confirmed`(불리언) 컬럼을 지운다.

`migrate_v13_previous_finding_result_status.py`가 그 값을 `result_status`로 이관한 뒤
모델에서 `confirmed`를 완전히 뺐는데, 실제 SQLite 테이블에는 이 컬럼이 NOT NULL로 남아있어
ORM이 값을 안 채우면 INSERT가 전부 실패하는 문제가 있었다(실측 확인 — "미리보기" 클릭 시
`sqlite3.IntegrityError: NOT NULL constraint failed: previous_finding.confirmed`).

SQLite 3.35+ 는 `ALTER TABLE ... DROP COLUMN`을 지원한다.

실행:
    python -m data.migrate_v14_drop_previous_finding_confirmed
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db


def migrate() -> None:
    init_db()

    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(previous_finding)"))}
        if "confirmed" in existing:
            conn.execute(text("ALTER TABLE previous_finding DROP COLUMN confirmed"))
            conn.commit()
            print("컬럼 제거됨: previous_finding.confirmed")
        else:
            print("이미 제거됨 (confirmed 컬럼 없음).")


if __name__ == "__main__":
    migrate()
