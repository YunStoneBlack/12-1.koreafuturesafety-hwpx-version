"""매일 예약작업(Windows 작업 스케줄러)으로 돌릴 백업 스크립트.

DB는 pg_dump로 실제 파일을 만들고, 사진/PDF/서명처럼 DB에 안 담기는 파일들은 "이 폴더도
같이 백업해야 한다"는 걸 매번 출력해서 잊지 않게 한다. 나중에 전용 서버 PC로 이전할 때
"DB 복원(pg_restore) + 이 폴더들 복사 + 환경변수 맞추기"가 이전 절차 전체다
(server/README_DEPLOY.md 참고) — 이 스크립트 자체가 다른 곳으로 파일을 옮기지는 않는다,
이 PC 안에 덤프를 쌓아두는 것까지가 1차 범위다.

실행: `python -m server.scripts.backup` (Windows 작업 스케줄러에 등록해서 매일 자동 실행)"""

from __future__ import annotations

import datetime
import subprocess
import sys

# Windows 작업 스케줄러(콘솔 없음)에서 돌 때 한글 print()가 cp949 인코딩 오류로 죽는 걸
# 막는다 — server/worker/render_worker.py와 같은 이유(2026-09-28 실제 재현).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.db import BASE_DIR, DATABASE_URL

BACKUP_DIR = BASE_DIR / "backups"


def main() -> None:
    if not DATABASE_URL:
        print("DATABASE_URL이 설정되어 있지 않습니다(SQLite 데스크톱 모드) — 백업 대상 아님.")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_path = BACKUP_DIR / f"db_{stamp}.dump"

    subprocess.run(["pg_dump", DATABASE_URL, "-Fc", "-f", str(dump_path)], check=True)
    print(f"DB 백업 완료: {dump_path}")

    print("아래 폴더도 같이 백업(복사)해야 합니다 — pg_dump에는 안 포함됨:")
    for name in ("photos", "reports", "signatures", "templates"):
        print(f"  - {BASE_DIR / 'data' / name}")


if __name__ == "__main__":
    main()
