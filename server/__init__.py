"""웹판 패키지. 서버 전용 환경변수 파일 `server/.env.server`(git 제외)가 있으면 여기서 먼저 읽는다 —
API(`uvicorn server.api.main:app`)든 워커(`python -m server.worker...`)든 `server` 패키지를 가장 먼저
임포트하므로, `core/db.py`가 `DATABASE_URL`을 읽기 전에 값이 채워진다.

루트 `.env`에 넣지 않는 이유: 루트 `.env`는 데스크톱 앱도 읽어서(`core/config.py`), 거기 `DATABASE_URL`을
넣으면 이 PC에서 데스크톱 앱을 실행해도 SQLite 대신 웹판 PostgreSQL에 붙어버린다.
이미 설정된 환경변수는 덮어쓰지 않는다(명령줄에서 직접 준 값이 우선)."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env.server"), override=False)
