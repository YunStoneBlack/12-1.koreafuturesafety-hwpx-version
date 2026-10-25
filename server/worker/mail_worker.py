"""예약 메일 작업 프로그램(2026-10-25) — mail_job 중 예약 시각이 지난 것(queued)을 하나씩 보냄(server/api/mail_jobs.deliver).
시특법 보고서 내려받기 링크 메일·산안법 고객사 전송 예약. supervisor_entry의 별도 스레드. 서버 PC가 꺼져 있던 동안 지난 예약은 켜지면 바로 보냄.
"""
from __future__ import annotations

import datetime
import time
import traceback

from core import models_web  # noqa: F401 — 표 정의(DB 저장 때 필요)
from core.db import SessionLocal
from core.models_web import MailJob

POLL_SECONDS = 20


def _claim(db) -> int | None:
    now = datetime.datetime.now()
    job = (db.query(MailJob).filter(MailJob.status == "queued", MailJob.run_at.isnot(None), MailJob.run_at <= now)
           .order_by(MailJob.run_at, MailJob.id).with_for_update(skip_locked=True).first())
    if job is None:
        return None
    job.status = "sending"
    db.commit()
    return job.id


def run_forever() -> None:
    from server.api import mail_jobs

    print("[mail_worker] 시작")
    with SessionLocal() as db:  # 보내던 중 작업 프로그램이 멈춘 것 — 갔는지 모르므로 다시 안 보내고 알림(두 번 가는 것보다 낫게)
        for j in db.query(MailJob).filter(MailJob.status == "sending", MailJob.run_at.isnot(None)):
            j.status, j.message = "failed", "보내는 중에 작업 프로그램이 멈췄습니다 — 받는 사람에게 갔는지 확인한 뒤 필요하면 다시 보내세요."
        db.commit()
    while True:
        with SessionLocal() as db:
            job_id = _claim(db)
        if job_id is None:
            time.sleep(POLL_SECONDS)
            continue
        print(f"[mail_worker] 메일 {job_id}")
        try:
            with SessionLocal() as db:
                mail_jobs.deliver(db, db.get(MailJob, job_id))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            with SessionLocal() as db:
                j = db.get(MailJob, job_id)
                if j and j.status == "sending":
                    j.status, j.message = "failed", "작업 프로그램 오류"
                    db.commit()
