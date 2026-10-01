"""웹판 API 진입점. 실행: `uvicorn server.api.main:app --host 127.0.0.1 --port 8000`

이 프로세스는 PDF 렌더링(한글 COM 자동화)을 절대 직접 하지 않는다 — report_job 테이블에
"queued" 행만 넣고 즉시 응답하며, 실제 렌더링은 완전히 분리된 server/worker/render_worker.py
프로세스가 처리한다(느린 COM 작업이 이 웹 서버의 이벤트 루프를 막지 않도록).

API는 `/api` 아래, 그 외 경로는 `server/web/`의 정적 화면 — 둘 다 `WEB_BASE_PATH`(기본 `/report`) 아래에
올린다(`app`이 `web_app`을 그 경로에 마운트). 그룹웨어 nginx가 `https://groupware.kfsc21c.com/report/...`를 경로
그대로 이 서버로 넘기기 때문. 같은 오리진이라 CORS 없이 세션 쿠키가 동작한다. 화면 쪽은 주소를 상대 경로 +
`app.js`의 `BASE`로 만들어서 경로가 바뀌어도 코드 수정이 필요 없다."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api.edit_tracking import track_report_edits
from server.api.routers import (
    ai,
    auth,
    auto_plan,
    calendar,
    findings,
    jobs,
    materials,
    photo_rotate,
    photos,
    plan_change,
    route_plan,
    previous_findings,
    process_entries,
    report_mail,
    submission,
    report_manage,
    reports,
    settings,
    site_contacts,
    sites,
    staff,
    staff_groupware,
    support,
)
from server.settings import CORS_ORIGINS, WEB_BASE_PATH

web_app = FastAPI(
    title="한국미래안전 보고서 자동화 - 웹판 API",
    # 그룹웨어 도메인으로 외부에 공개되므로 자동 API 문서(/docs 등)는 끈다
    docs_url=None, redoc_url=None, openapi_url=None,
)

if CORS_ORIGINS:
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 보고서 "마지막 수정 시각" 기록(현장 화면 "PDF 수정 전 버전" 표시용) — server/api/edit_tracking.py
web_app.middleware("http")(track_report_edits)

web_app.include_router(auth.router, prefix="/api")
web_app.include_router(sites.router, prefix="/api")
web_app.include_router(site_contacts.router, prefix="/api")
web_app.include_router(reports.router, prefix="/api")
web_app.include_router(jobs.router, prefix="/api")
web_app.include_router(settings.router, prefix="/api")
web_app.include_router(staff.router, prefix="/api")
web_app.include_router(staff_groupware.router, prefix="/api")
web_app.include_router(photos.overview_router, prefix="/api")
web_app.include_router(photos.inspection_router, prefix="/api")
web_app.include_router(photo_rotate.router, prefix="/api")
web_app.include_router(previous_findings.router, prefix="/api")
web_app.include_router(process_entries.current_process_router, prefix="/api")
web_app.include_router(process_entries.future_process_router, prefix="/api")
web_app.include_router(findings.router, prefix="/api")
web_app.include_router(support.router, prefix="/api")
web_app.include_router(ai.router, prefix="/api")
web_app.include_router(materials.router, prefix="/api")
web_app.include_router(report_manage.router, prefix="/api")
web_app.include_router(report_mail.router, prefix="/api")
web_app.include_router(submission.router, prefix="/api")
web_app.include_router(calendar.router, prefix="/api")
web_app.include_router(auto_plan.router, prefix="/api")
web_app.include_router(plan_change.router, prefix="/api")
web_app.include_router(route_plan.router, prefix="/api")


@web_app.get("/api/health")
def health():
    return {"ok": True}


# 정적 프론트엔드는 마지막에 등록한다 — API 라우터가 먼저 매칭되도록.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class RevalidatingStaticFiles(StaticFiles):
    """화면 파일(html/js/css/이미지)에 `Cache-Control: no-cache`를 붙인다 — 브라우저가 쓰기 전에 매번 바뀌었는지 물어보게.
    안 붙이면 브라우저가 알아서 한동안 옛 파일을 그대로 써서, 화면을 고친 뒤 직원 화면엔 한참 반영이 안 됐다
    (2026-09-29 서명 칸 잠금이 강력 새로고침 전까지 안 보임). 안 바뀌었으면 ETag로 304만 오가서 속도 차이는 거의 없다."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


web_app.mount("/", RevalidatingStaticFiles(directory=WEB_DIR, html=True), name="web")

# 바깥 앱: WEB_BASE_PATH 아래에 웹판 전체를 올리고, 루트/경로 끝 슬래시 없는 주소는 "…/report/"로 보낸다
# (화면이 상대 주소를 쓰므로 "/report"가 아니라 "/report/"여야 "dashboard.html"이 "/report/dashboard.html"로 풀린다).
app = FastAPI(title="한국미래안전 보고서 자동화", docs_url=None, redoc_url=None, openapi_url=None)


@app.on_event("startup")
def _seed_reference_data() -> None:
    # 계측기준/제공자료 라이브러리 등 공용 참조 데이터(없을 때만 채움, core/db.py 참고).
    # 마운트된 하위 앱(web_app)의 startup은 실행되지 않으므로 바깥 앱에 둔다.
    from core.db import seed_shared_reference_data

    seed_shared_reference_data()


if WEB_BASE_PATH:

    @app.get("/")
    @app.get(WEB_BASE_PATH)
    def _to_base():
        return RedirectResponse(f"{WEB_BASE_PATH}/")

    app.mount(WEB_BASE_PATH, web_app)
else:
    app.mount("/", web_app)
