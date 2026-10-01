"""매일 예약작업(Windows 작업 스케줄러)으로 돌릴 백업 스크립트.

DB는 pg_dump로 실제 파일을 만들고, 사진/PDF/서명처럼 DB에 안 담기는 파일들은 "이 폴더도
같이 백업해야 한다"는 걸 매번 출력해서 잊지 않게 한다. 나중에 전용 서버 PC로 이전할 때
"DB 복원(pg_restore) + 이 폴더들 복사 + 환경변수 맞추기"가 이전 절차 전체다
(server/README_DEPLOY.md 참고) — 이 스크립트 자체가 다른 곳으로 파일을 옮기지는 않는다,
이 PC 안에 덤프를 쌓아두는 것까지가 1차 범위다.

실행: `python -m server.scripts.backup` (Windows 작업 스케줄러에 등록해서 매일 자동 실행)"""

from __future__ import annotations

import datetime
import shutil
import re
import subprocess
import sys

# Windows 작업 스케줄러(콘솔 없음)에서 돌 때 한글 print()가 cp949 인코딩 오류로 죽는 걸
# 막는다 — server/worker/render_worker.py와 같은 이유(2026-09-28 실제 재현).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.db import BASE_DIR, DATA_DIR, DATABASE_URL

BACKUP_DIR = BASE_DIR / "backups"


def main() -> None:
    if not DATABASE_URL:
        print("DATABASE_URL이 설정되어 있지 않습니다(SQLite 데스크톱 모드) — 백업 대상 아님.")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_path = BACKUP_DIR / f"db_{stamp}.dump"

    # DATABASE_URL은 SQLAlchemy 형식("postgresql+psycopg://...")이라 pg_dump가 못 알아본다 → 드라이버 표기를 떼고 넘긴다
    # (2026-09-29 실제로 이 때문에 백업이 실패했음). pg_dump가 PATH에 없으면 기본 설치 위치(PostgreSQL 16)를 쓴다.
    libpq_url = re.sub(r"^postgresql\+\w+://", "postgresql://", DATABASE_URL)
    pg_dump = shutil.which("pg_dump") or "C:/Program Files/PostgreSQL/16/bin/pg_dump.exe"
    # 윈도우판 pg_dump는 주소를 맨 앞 위치 인자로 주면 뒤 옵션을 "인자가 너무 많다"며 거부한다 → -d로 넘긴다
    subprocess.run([pg_dump, "-Fc", "-f", str(dump_path), "-d", libpq_url], check=True)
    print(f"DB 백업 완료: {dump_path}")

    # 파일 저장소(2026-10-01 server/api/storage.py) — 현장 폴더들 + _서명 + _자료실(_시스템은 다시 만들어지므로 빼도 됨)
    print("아래 저장소 폴더도 같이 백업(복사)해야 합니다 — pg_dump에는 안 포함됨(_시스템 폴더는 빼도 됨):")
    print(f"  - {DATA_DIR}  (현장 폴더들, _서명, _자료실)")
    print(f"  - {BASE_DIR / 'data' / 'templates'}  (한글 양식)")


if __name__ == "__main__":
    main()
