"""PDF 렌더링 워커 — API 프로세스(server/api/main.py)와 완전히 분리된 별도 프로세스로
실행한다. report_job 테이블(core/models_db.py의 ReportJob)을 폴링하며 큐에 쌓인 작업을
하나씩 순서대로 처리한다 — 한글 COM 인스턴스는 한 번에 하나만 안정적으로 동작하므로
의도적으로 순차 처리(동시에 여러 개 돌리지 않음)다.

실행: `python -m server.worker.render_worker`
Windows에서는 이 프로세스를 NSSM으로 서비스 등록해서 자동 재시작되게 한다
(server/README_DEPLOY.md 참고). 크래시에도 계속 살아있게 하려면
server/worker/supervisor_entry.py를 대신 실행해도 된다.

실패 시 절대 다른 서식으로 조용히 대체하지 않는다 — core/report_builder.py의
build_report()가 HwpNotAvailableError(한글 자체가 아예 없을 때)만 구분해서 예전
reportlab 서식으로 내려가고, 그 외 에러(일시적 COM 오류 등)는 그대로 올리는 기존 설계를
그대로 신뢰한다. 이 워커는 그 예외를 그대로 받아서 report_job.error_message에 남기고,
사용자가 프론트엔드에서 "다시 시도"를 누르게 한다."""

from __future__ import annotations

import datetime
import sys
import time
import traceback

# 이 스크립트의 print()엔 한글/em dash가 섞여있는데, Windows에서 콘솔 없이(NSSM 서비스로,
# 또는 파일로 리다이렉트해서) 실행하면 표준출력 인코딩이 시스템 코드페이지(cp949)로 잡혀
# `UnicodeEncodeError`로 죽는다 — 실제로 이 PC에서 재현(2026-09-28). PYTHONIOENCODING
# 환경변수로도 고칠 수 있지만, 서비스 등록 시 깜빡 안 챙길 수 있어 코드 자체가 방어하게 한다.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.db import BASE_DIR, SessionLocal
from core.models_db import Report
from core.models_web import ReportJob
from core.report_builder import build_report
from desktop.workers.ai_worker import with_com

POLL_INTERVAL_SECONDS = 1.5


def _claim_next_job(db) -> tuple[int, int] | None:
    """대기중인 작업 하나를 "rendering"으로 바꾸고 (job_id, report_id)를 반환한다.
    `with_for_update(skip_locked=True)`는 PostgreSQL 전용 — 이 워커는 웹판(Postgres) 전용
    프로세스라 SQLite 데스크톱 경로에서는 쓰지 않는다."""
    job = (
        db.query(ReportJob)
        .filter(ReportJob.status == "queued")
        .order_by(ReportJob.created_at)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    job.status = "rendering"
    job.started_at = datetime.datetime.now()
    db.commit()
    return job.id, job.report_id


def _render(job_id: int, report_id: int) -> None:
    output_dir = BASE_DIR / "data" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"report_{report_id}.pdf"

    with SessionLocal() as db:
        job = db.get(ReportJob, job_id)
        try:
            with_com(lambda: build_report(report_id, output_path))()
            # build_report()(특히 한글 COM 경로인 build_report_pdf_via_hwpx)는 report.status만
            # 갱신하고 pdf_path는 스스로 저장하지 않는다 — 데스크톱 앱도 report_export.py의
            # _build_pdf_for_export()에서 호출부가 직접 pdf_path를 저장해주는 것과 같은 이유로,
            # 여기서도 호출부(워커)가 책임진다.
            report = db.get(Report, report_id)
            report.pdf_path = str(output_path)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 -- 어떤 예외든 그대로 기록, 워커 루프는 계속 돌아야 함
            job.status = "failed"
            job.error_message = f"{exc}\n{traceback.format_exc()}"
        finally:
            job.finished_at = datetime.datetime.now()
            db.commit()


def run_forever() -> None:
    print("[render_worker] 시작 — report_job 테이블 폴링 중...")
    while True:
        with SessionLocal() as db:
            claimed = _claim_next_job(db)
        if claimed is not None:
            job_id, report_id = claimed
            print(f"[render_worker] job {job_id} (report {report_id}) 렌더링 시작")
            _render(job_id, report_id)
            print(f"[render_worker] job {job_id} 완료")
        else:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
