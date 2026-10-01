"""보고서 "마지막 수정 시각" 기록 — 현장 화면의 "PDF 수정 전 버전" 표시용(core.models_web.ReportEdit).

보고서 내용을 바꾸는 API는 섹션·사진·서명마다 수십 개라 하나하나 고치지 않고, 미들웨어 하나가 성공한 저장 요청을 보고 기록한다:
  - POST/PATCH/PUT/DELETE `/api/reports/{id}/...` 가 성공(4xx/5xx 아님)하면 그 보고서를 "수정됨"으로.
    단 AI 분석(`/ai/...`, 입력칸만 채우고 저장 안 함)·PDF 생성(`/render`)·고객사 메일 전송(`/mail`)·"직접 제출함" 표시(`/submit-mark`)·K2B 제출(`/k2b`)·보고서 삭제 자체는 제외.
  - PATCH `/api/sites/{id}`(현장 정보 수정) — 표지에 들어가므로 그 현장 보고서 전부를 "수정됨"으로.
성공한 요청만 보므로 권한 검사는 원래 API가 이미 한 셈이다.
"""

from __future__ import annotations

import datetime
import re

from sqlalchemy.dialects.postgresql import insert as pg_insert
from starlette.concurrency import run_in_threadpool

from core.db import SessionLocal
from core.models_db import Report
from core.models_web import ReportEdit

_REPORT_PATH = re.compile(r"/api/reports/(\d+)(/[^?]*)?$")
_SITE_PATH = re.compile(r"/api/sites/(\d+)$")
_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def edited_report_ids(method: str, path: str) -> tuple[list[int], int | None]:
    """(바로 알 수 있는 보고서 id들, 현장 id) — 현장 id가 있으면 그 현장 보고서 전부."""
    if method not in _WRITE_METHODS:
        return [], None
    m = _REPORT_PATH.search(path)
    if m:
        rest = m.group(2) or ""
        if rest.startswith("/render") or rest.startswith("/ai/") or rest.startswith("/mail") or rest.startswith("/submit-mark") or rest.startswith("/k2b") or (rest in ("", "/") and method == "DELETE"):
            return [], None
        return [int(m.group(1))], None
    m = _SITE_PATH.search(path)
    if m and method == "PATCH":
        return [], int(m.group(1))
    return [], None


def mark_edited(report_ids: list[int], site_id: int | None) -> None:
    now = datetime.datetime.now()
    with SessionLocal() as db:
        ids = list(report_ids)
        if site_id is not None:
            ids += [rid for (rid,) in db.query(Report.id).filter(Report.site_id == site_id)]
        for rid in ids:
            db.execute(
                pg_insert(ReportEdit).values(report_id=rid, edited_at=now)
                .on_conflict_do_update(index_elements=[ReportEdit.report_id], set_={"edited_at": now})
            )
        db.commit()


async def track_report_edits(request, call_next):
    response = await call_next(request)
    if response.status_code < 400:
        ids, site_id = edited_report_ids(request.method, request.url.path)
        if ids or site_id is not None:
            try:
                await run_in_threadpool(mark_edited, ids, site_id)
            except Exception:  # noqa: BLE001 — 표시용 기록이라 실패해도 저장 응답은 그대로 돌려준다
                pass
    return response
