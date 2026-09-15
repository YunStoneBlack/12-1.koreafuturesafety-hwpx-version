"""7번(현재 진행공정)/9번(향후 진행공정) 마법사를 카탈로그 선택 방식에서 "사진+공정명 →
AI로 유해위험요인/예방대책/위험성 다건 작성" 방식으로 개편하면서 필요해진 DB 변경.

- `process_hazard_entry`/`current_process_entry`에 `photo_path` 컬럼 추가(AI 분석에 쓴 공정
  사진 경로).
- 항목별(유해요인-예방대책-위험성 한 벌) 다건 데이터를 담을 신규 테이블
  `process_hazard_item`/`current_process_hazard_item`은 `init_db()`(Base.metadata.create_all)가
  자동으로 만들어주므로 여기선 ALTER만 처리한다.

기존 `hazard_text`/`prevention_text`/`risk_level`(엔트리 단일값 컬럼)은 그대로 남겨둔다 — 옛
방식으로 이미 저장된 보고서 데이터를 보존하기 위함이며, 새 코드는 더 이상 채우지 않는다.

실행:
    python -m data.migrate_v19_process_ai_rework
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import engine, init_db

_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "process_hazard_entry": [
        ("photo_path", "TEXT DEFAULT ''"),
    ],
    "current_process_entry": [
        ("photo_path", "TEXT DEFAULT ''"),
    ],
}


def migrate() -> None:
    init_db()  # 신규 테이블(process_hazard_item/current_process_hazard_item)은 여기서 생성됨

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
