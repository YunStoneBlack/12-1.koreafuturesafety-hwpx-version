"""시특법 FMS 제출 작업 프로그램(2026-10-15) — fms_submission 대기열(queued)을 하나씩 꺼내 이 PC에서 FMS에 입력(server/sitok/fms_bot.py).

K2B 작업 프로그램처럼 supervisor_entry의 별도 스레드로 돈다(한글 COM은 주 스레드). 한 번에 하나씩 — FMS는 같은 아이디로 새로 로그인하면
이전 접속을 끊어서 동시에 두 개를 돌리면 서로 끊긴다.
화면·나눈 e-보고서 파일은 저장소 _시스템/fms/job_N/. 끝나면 같이 낸 회차마다 sitok_report.fms에 FMS 계약 번호·단계 결과를 적는다.
"""
from __future__ import annotations

import datetime
import time
import traceback
from pathlib import Path

from core import models_web  # noqa: F401 — 회사·사용자 표 정의(DB 저장 때 필요)
from core.db import DATA_DIR, SessionLocal
from core.models_web import FmsSubmission, SitokFacility, SitokReport
from core.stored_path import to_stored

POLL_SECONDS = 4
ROOT = DATA_DIR / "_시스템" / "fms"


def _claim(db) -> int | None:
    from sqlalchemy import or_

    now = datetime.datetime.now()
    job = (db.query(FmsSubmission).filter(FmsSubmission.status == "queued", or_(FmsSubmission.run_at.is_(None), FmsSubmission.run_at <= now))  # 예약은 그 시각부터(10/25)
           .order_by(FmsSubmission.run_at.nullsfirst(), FmsSubmission.id).with_for_update(skip_locked=True).first())
    if job is None:
        return None
    job.status = "running"
    job.started_at = datetime.datetime.now()
    db.commit()
    return job.id


def _process(job_id: int) -> None:
    from server.api.routers.sitok_fms import company_cred, owner_cred
    from server.sitok import fms, fms_bot

    with SessionLocal() as db:
        job = db.get(FmsSubmission, job_id)
        reps = [db.get(SitokReport, i) for i in (job.report_ids or [])]
        reps = [r for r in reps if r is not None]
        base = ROOT / f"job_{job.id}"
        try:
            if not reps:
                raise RuntimeError("회차가 없습니다.")
            cred = company_cred(db, job.company_id)
            if not cred:
                raise RuntimeError("회사 FMS 계정이 없습니다.")
            payload = fms.payload(db, reps)
            facs = [db.get(SitokFacility, r.facility_id) for r in reps]
            owner = next((oc for f in facs if (oc := owner_cred(f))), None)
            opts = job.options or {}
            if job.stage == "practice":
                res = fms_bot.practice(payload, *cred, base / "shots")
                ok = True
                msg = "연습 끝 — FMS에 아무것도 저장하지 않았습니다."
                if not res.get("owner", {}).get("ok"):
                    ok, msg = False, f"FMS 관리주체 찾기에서 \"{payload['contract']['mng_main_nm']}\"를 못 찾았습니다."
                miss = [n for n, v in (res.get("facilities") or {}).items() if n != "_all" and v.get("missing")]
                if miss:
                    msg += f" FMS에서 못 찾은 시설물 번호: {', '.join(miss)}."
                emiss = [n for n, v in (res.get("engineers") or {}).items() if v.get("missing")]
                if emiss:
                    msg += f" FMS 기술자 목록에 없는 사람: {', '.join(emiss)}."
                diffs = fms.apply_engineers(payload, res.get("engineers") or {})
                res["engineer_diffs"] = diffs
                job.result = {k: res.get(k) for k in ("fms_rep", "fms_phone", "filled", "facilities", "engineers", "engineer_diffs", "owner")}
                job.status, job.message = ("done" if ok else "failed"), msg
                job.log = "\n".join(res.get("log") or [])
                job.shots = [to_stored(s) for s in res.get("shots") or []]
            else:
                files = None
                if job.stage == "result" and not (job.project_no or (reps[0].fms or {}).get("project_no")):
                    raise RuntimeError("FMS 계약 번호가 없습니다 — 계약 등록이 아직 안 끝났습니다(예약이면 계약 등록 뒤로 다시 예약)")
                if job.stage == "result":
                    r0 = reps[0]
                    made = fms.write_split(Path(r0.out_pdf), base / "files", r0.kind or "정기")
                    extra, notes = fms.contract_files(db, reps)
                    files = extra + [{"folder": m["folder"], "name": m["name"], "file": m["file"]} for m in made]
                out = fms_bot.submit(job.stage, payload, cred, owner, base / "shots", project_no=job.project_no or (reps[0].fms or {}).get("project_no", ""),
                                     files=files, stop_before_request=bool(opts.get("stop_before_request")))
                job.project_no = out.get("project_no") or job.project_no
                job.status = "done" if out.get("ok") else "failed"
                job.message = out.get("message") or out.get("step") or ""
                job.result = {"step": out.get("step"), "alerts": (out.get("alerts") or [])[-10:], "owner": bool(owner)}
                job.log = "\n".join(out.get("log") or [])
                job.shots = [to_stored(s) for s in out.get("shots") or []]
                for r in reps:  # 회차마다 FMS 상태
                    st = dict(r.fms or {})
                    if job.project_no:
                        st["project_no"] = job.project_no
                    st[job.stage] = {"status": job.status, "step": out.get("step"), "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                     "by": job.created_by, "job": job.id}
                    r.fms = st
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            first = next((ln.strip() for ln in str(e).splitlines() if ln.strip() and not ln.strip().startswith("=")), type(e).__name__)
            job.message = f"작업 오류: {first[:160]}"  # 첫 줄만(10/15 — Playwright "==== logs ====" 덩어리는 아래 기록에)
            job.log = (job.log or "") + "\n" + traceback.format_exc()[-1500:]
        job.finished_at = datetime.datetime.now()
        opts = job.options or {}
        if job.status == "failed" and job.run_at and job.stage != "practice" and not opts.get("retry"):  # 예약 작업이 실패하면 다음 날 아침 7시에 한 번 더(10/25)
            nxt = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(7, 0))
            db.add(FmsSubmission(company_id=job.company_id, report_ids=job.report_ids, stage=job.stage, status="queued", run_at=nxt,
                                 options={**opts, "retry": 1, "retry_of": job.id}, project_no=job.project_no, created_by=job.created_by))
            job.message = (job.message or "") + f" — {nxt:%m/%d %H:%M}에 한 번 더 합니다"
        db.commit()


def run_forever() -> None:
    print("[fms_worker] 시작")
    while True:
        with SessionLocal() as db:
            job_id = _claim(db)
        if job_id is None:
            time.sleep(POLL_SECONDS)
            continue
        print(f"[fms_worker] 작업 {job_id}")
        try:
            _process(job_id)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            with SessionLocal() as db:
                j = db.get(FmsSubmission, job_id)
                if j and j.status == "running":
                    j.status, j.message, j.finished_at = "failed", "작업 프로그램 오류", datetime.datetime.now()
                    db.commit()
