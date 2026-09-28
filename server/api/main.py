"""웹판 API 진입점. 실행: `uvicorn server.api.main:app --host 127.0.0.1 --port 8000`

이 프로세스는 PDF 렌더링(한글 COM 자동화)을 절대 직접 하지 않는다 — report_job 테이블에
"queued" 행만 넣고 즉시 응답하며, 실제 렌더링은 완전히 분리된 server/worker/render_worker.py
프로세스가 처리한다(느린 COM 작업이 이 웹 서버의 이벤트 루프를 막지 않도록).

API는 전부 `/api` 아래에 두고, 그 외 경로는 `server/web/`의 정적 파일(Milestone 1 최소
프론트엔드 — 로그인/현장/보고서 화면)을 그대로 서빙한다. 같은 오리진에서 서빙하기 때문에
CORS 없이도 세션 쿠키가 그대로 동작한다."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api.routers import (
    ai,
    auth,
    findings,
    jobs,
    materials,
    photos,
    previous_findings,
    process_entries,
    report_manage,
    reports,
    settings,
    sites,
    staff,
    support,
)
from server.settings import CORS_ORIGINS

app = FastAPI(title="한국미래안전 보고서 자동화 - 웹판 API")


@app.on_event("startup")
def _seed_reference_data() -> None:
    # 계측기준/제공자료 라이브러리 등 공용 참조 데이터(없을 때만 채움, core/db.py 참고)
    from core.db import seed_shared_reference_data

    seed_shared_reference_data()

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router, prefix="/api")
app.include_router(sites.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(staff.router, prefix="/api")
app.include_router(photos.overview_router, prefix="/api")
app.include_router(photos.inspection_router, prefix="/api")
app.include_router(previous_findings.router, prefix="/api")
app.include_router(process_entries.current_process_router, prefix="/api")
app.include_router(process_entries.future_process_router, prefix="/api")
app.include_router(findings.router, prefix="/api")
app.include_router(support.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(materials.router, prefix="/api")
app.include_router(report_manage.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


# 정적 프론트엔드는 마지막에 등록한다 — API 라우터가 먼저 매칭되도록.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
