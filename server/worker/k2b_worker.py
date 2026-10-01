"""K2B 제출 작업 프로그램(2026-10-01) — k2b_submission 대기열(queued)을 하나씩 꺼내 이 PC에서 K2B에 입력·저장(server/k2b/runner.py).

PDF 렌더 작업 프로그램(render_worker)과 같은 프로세스(supervisor_entry)의 별도 스레드로 돈다 — 한글 COM은 주 스레드,
K2B(Playwright 크롬)는 이 스레드. 한 번에 하나씩(같은 계정 동시 로그인·K2B 부하 방지).
결과 화면은 보고서 회차 폴더에 "…_05회차_K2B제출.png"(성공) / "…_K2B제출실패.png"로 둔다(storage 규칙 — 탐색기에서 바로 확인).
"""
from __future__ import annotations

import datetime
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from core import models_web  # noqa: F401 — 회사·사용자 표 정의(DB 저장 때 필요)
from core.db import DATA_DIR, SessionLocal
from core.models_db import Report
from core.models_web import K2bSubmission, StaffK2bAccount
from server.api import k2b_secret, storage
from server.k2b.runner import run
from server.k2b.submission import MajorHazardWork, ManualFields, build_submission

POLL_SECONDS = 3
UPLOAD_DIR = DATA_DIR / "_시스템" / "k2b"  # 창에서 올린 불량사업장 첨부(job_N/)


def _manual(options: dict | None, job_id: int) -> tuple[ManualFields, bool]:
    o = options or {}
    files_dir = UPLOAD_DIR / f"job_{job_id}"
    files = sorted(str(p) for p in files_dir.glob("*")) if files_dir.exists() else []
    manual = ManualFields(
        current_process=o.get("current_process", ""),
        scaffold_usage=o.get("scaffold_usage", ""),
        scaffold_types=list(o.get("scaffold_types") or []),
        bad_site_notify=bool(o.get("bad_site_notify")),
        bad_site_content=o.get("bad_site_content", ""),
        bad_site_files=files,
        major_hazard_works=[MajorHazardWork(**h) for h in (o.get("major_hazard_works") or [])],
        prev_guidance=o.get("prev_guidance", ""),
    )
    return manual, bool(o.get("allow_round_mismatch"))


def _claim(db) -> int | None:
    job = (db.query(K2bSubmission).filter(K2bSubmission.status == "queued")
           .order_by(K2bSubmission.id).with_for_update(skip_locked=True).first())
    if job is None:
        return None
    job.status = "running"
    job.started_at = datetime.datetime.now()
    db.commit()
    return job.id


def _process(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(K2bSubmission, job_id)
        report = db.get(Report, job.report_id)
        try:
            acc = db.get(StaffK2bAccount, job.staff_id) if job.staff_id else None
            if acc is None or not acc.password_enc:
                raise RuntimeError("담당요원 K2B 계정이 없습니다 — 담당요원 탭에서 등록하세요.")
            manual, allow = _manual(job.options, job.id)
            sub = build_submission(db, report, manual)
            with tempfile.TemporaryDirectory() as tmp:
                result = run(sub, acc.k2b_id, k2b_secret.decrypt(acc.password_enc), Path(tmp), save=True,
                             allow_round_mismatch=allow)
                if result.screenshot and Path(result.screenshot).exists():
                    folder = storage.report_dir(db, report)
                    folder.mkdir(parents=True, exist_ok=True)
                    name = f"{storage.report_base(db, report)}_K2B제출{'' if result.saved else '실패'}.png"
                    dest = folder / name
                    shutil.copyfile(result.screenshot, dest)
                    job.screenshot = str(dest)
            job.status = "done" if result.saved else "failed"
            job.message = result.message
            job.round_no = result.round_no
            job.log = "\n".join(result.log)[-20000:]
        except Exception as err:  # noqa: BLE001 — 어떤 이유든 기록하고 다음 작업으로
            job.status = "failed"
            job.message = str(err).splitlines()[0][:300] if str(err) else type(err).__name__
            job.log = traceback.format_exc()[-20000:]
        finally:
            job.finished_at = datetime.datetime.now()
            db.commit()
        shutil.rmtree(UPLOAD_DIR / f"job_{job_id}", ignore_errors=True)


def run_forever() -> None:
    print("[k2b_worker] 시작 — k2b_submission 대기열 확인 중...")
    with SessionLocal() as db:  # 작업 프로그램이 도중에 꺼졌다 켜지면 running으로 남은 것 → 실패 처리(K2B에 저장됐는지 모르므로 사람이 확인)
        for job in db.query(K2bSubmission).filter(K2bSubmission.status == "running"):
            job.status = "failed"
            job.message = "작업 프로그램이 도중에 다시 시작됐습니다 — K2B에 저장됐는지 직접 확인한 뒤 필요하면 다시 제출하세요."
            job.finished_at = datetime.datetime.now()
        db.commit()
    while True:
        try:
            with SessionLocal() as db:
                job_id = _claim(db)
            if job_id is None:
                time.sleep(POLL_SECONDS)
                continue
            print(f"[k2b_worker] 제출 {job_id} 시작")
            _process(job_id)
            print(f"[k2b_worker] 제출 {job_id} 끝")
        except Exception:  # noqa: BLE001 — DB 연결 끊김 등, 잠시 쉬고 계속
            traceback.print_exc()
            time.sleep(10)
