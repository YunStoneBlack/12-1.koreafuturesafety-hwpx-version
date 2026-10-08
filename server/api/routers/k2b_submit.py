"""K2B 제출(2026-10-01) — 현장 화면 보고서 줄 [K2B 제출]. 창에서 K2B 전용 항목을 고르면 대기열(k2b_submission)에 넣고,
이 PC 작업 프로그램(server/worker/k2b_worker.py)이 K2B에 새 차수로 입력·저장한다(server/k2b/runner.py).

- `GET /reports/{id}/k2b` — 창에 그릴 것: 보고서에서 가져가는 값 요약, 담당요원 K2B 계정 상태, 막는 이유(blockers),
  K2B 선택지(현재 작업공종·비계 종류·대형사고 위험작업), 이 보고서 제출 기록.
- `POST /reports/{id}/k2b` (multipart: options=JSON, files=불량사업장 첨부) — 대기열에 넣기. 현재 작업공종·비계 사용 여부는 K2B 필수.
- `GET /k2b-jobs/{id}` — 진행 상태(창이 2초마다), `GET /k2b-jobs/{id}/shot` — 저장 뒤(또는 실패) K2B 화면.
쓰기 요청이지만 보고서 내용을 바꾸지 않으므로 edit_tracking에서 "보고서 수정"으로 치지 않는다(`/k2b`).
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_db import Report
from core.models_web import K2bSubmission, StaffK2bAccount, User
from core.stored_path import to_full
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.api.routers.reports import pdf_outdated_map
from server.k2b import selectors as sel
from server.k2b.advice import advice
from server.k2b.submission import build_submission
from server.worker.k2b_worker import UPLOAD_DIR

router = APIRouter(tags=["k2b"])
_BAD_SITE_SUFFIXES = {".jpg", ".jpeg", ".gif", ".png", ".bmp", ".pdf"}  # K2B 제약(14번)


def _job_out(j: K2bSubmission) -> dict:
    return {
        "id": j.id, "status": j.status, "round_no": j.round_no, "message": j.message, "options": j.options or {},
        "hint": advice(j.message, j.log) if j.status == "failed" else "",  # 실패면 "이렇게 하세요" 한 줄(server/k2b/advice.py)
        "has_shot": bool(j.screenshot and Path(j.screenshot).exists()), "shots": len(_shot_paths(j)), "created_by": j.created_by,
        "created_at": j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else None,
        "finished_at": j.finished_at.strftime("%Y-%m-%d %H:%M") if j.finished_at else None,
    }


def _shot_paths(j: K2bSubmission) -> list[str]:
    """구역별 화면들(10/7부터), 예전 제출은 한 장(screenshot)."""
    paths = [to_full(p) for p in (j.screenshots or [])] or ([j.screenshot] if j.screenshot else [])
    return [p for p in paths if Path(p).exists()]


def _report(db: Session, user: User, report_id: int) -> Report:
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    return report


def _blockers(db: Session, report: Report) -> list[str]:
    out = []
    if report.status != "final" or not report.pdf_path or not Path(report.pdf_path).exists():
        out.append("PDF를 먼저 만드세요 — K2B에는 PDF가 올라갑니다.")
    elif pdf_outdated_map(db, [report])[report.id]:
        out.append("PDF를 만든 뒤 내용을 고쳤습니다 — 보고서 화면에서 PDF를 다시 만드세요.")
    if not report.assigned_staff_id:
        out.append("이 회차 담당요원이 없습니다 — 보고서에서 담당요원을 정하세요.")
    else:
        acc = db.get(StaffK2bAccount, report.assigned_staff_id)
        name = report.assigned_staff.name if report.assigned_staff else ""
        if acc is None or not acc.password_enc:
            out.append(f"{name}님의 K2B 계정이 없습니다 — 담당요원 탭에서 등록하세요.")
        elif acc.check_status == "fail":
            out.append(f"{name}님의 K2B 로그인 확인이 실패 상태입니다 — 담당요원 탭에서 다시 확인하세요.")
    if not report.guidance_date:
        out.append("기술지도일이 비어 있습니다.")
    if report.progress_rate is None:
        out.append("공정률이 비어 있습니다(K2B 필수).")
    if not report.notification_method:
        out.append("통보방법이 비어 있습니다(K2B 필수).")
    return out


@router.get("/reports/{report_id}/k2b")
def k2b_info(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _report(db, user, report_id)
    sub = build_submission(db, report)
    acc = db.get(StaffK2bAccount, report.assigned_staff_id) if report.assigned_staff_id else None
    jobs = db.query(K2bSubmission).filter(K2bSubmission.report_id == report_id).order_by(K2bSubmission.id.desc()).all()
    return {
        "summary": {
            "site_name": sub.site_name, "search_word": (sub.site_name.split() or [sub.site_name])[0], "visit_no": sub.visit_no,
            "guidance_date": sub.guidance_date, "staff_name": sub.staff_name, "progress_rate": sub.progress_rate,
            "site_manager": " ".join(x for x in (sub.site_manager_name, sub.site_manager_phone) if x),
            "notification_method": sub.notification_method,
            # 창의 "이전 기술지도 이행여부" 기본값 — 4번 이전지적사항 결과로 미리 고름(""이면 사람이 고름) + 그 이유
            "prev_guidance_default": sub.prev_guidance_auto,
            "prev_guidance_reason": sub.prev_guidance_reason,
            "special_note": sub.special_note,
            "site_amount": report.site.amount,  # 40억 이상이면 창에서 "경영책임자 통보일 확인" 안내(값은 비워 둠)
            "counts": {"지도건수": sub.guidance_count, "교육인원": sub.education_count, "배포자료건수": sub.material_count},
            "problems": len(sub.problem_texts),
            "no_photo": sub.no_photo,
            "photos": {"현장전경": len(sub.overview_photo_paths), "현장점검": len(sub.inspection_photo_paths), "현장개선": len(sub.improvement_photo_paths)},
            "pdf": Path(sub.report_pdf_path).name if sub.report_pdf_path else "",
        },
        "account": {"k2b_id": acc.k2b_id if acc else "", "check_status": acc.check_status if acc else "",
                    "checked_at": acc.checked_at.strftime("%m/%d %H:%M") if acc and acc.checked_at else None},
        "blockers": _blockers(db, report),
        "choices": {
            "current_process": sel.CURRENT_PROCESS_OPTIONS,
            "scaffold_types": list(sel.SCAFFOLD_TYPE_CHECKBOX_IDS),
            "hazard_by_occurrence": sel.MAJOR_HAZARD_WORK_OPTIONS_BY_OCCURRENCE,
        },
        "jobs": [_job_out(j) for j in jobs],
    }


@router.post("/reports/{report_id}/k2b")
async def k2b_submit(
    report_id: int,
    options: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = _report(db, user, report_id)
    try:
        o = json.loads(options)
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "입력값을 읽지 못했습니다.") from err
    problems = _blockers(db, report)
    if o.get("current_process") not in sel.CURRENT_PROCESS_OPTIONS:
        problems.append("현재 작업공종을 고르세요(K2B 필수).")
    if o.get("prev_guidance") not in ("이행", "불이행", "해당없음"):
        problems.append("이전 기술지도 이행여부를 고르세요(K2B 필수).")
    q, ceo_date, owner_date = o.get("ceo_notice_quarter"), o.get("ceo_notice_date") or "", o.get("owner_notice_date") or ""
    if q not in (None, 1, 2, 3, 4):
        problems.append("경영책임자 통보 분기를 다시 고르세요.")
    elif bool(q) != bool(ceo_date):
        problems.append("경영책임자(본사) 통보일은 분기와 날짜를 같이 고르세요(안 쓰면 둘 다 비움).")
    if owner_date and o.get("prev_guidance") != "불이행":
        problems.append("건설공사 발주자 통보일은 이전 기술지도 이행여부가 '불이행'일 때만 넣을 수 있습니다(K2B 규칙).")
    for label, d in (("경영책임자(본사) 통보일", ceo_date), ("건설공사 발주자 통보일", owner_date)):
        if d:
            try:
                datetime.date.fromisoformat(d)
            except ValueError:
                problems.append(f"{label} 날짜를 다시 고르세요.")
    if o.get("scaffold_usage") not in ("사용", "미사용"):
        problems.append("비계 사용 여부를 고르세요(K2B 필수).")
    elif o["scaffold_usage"] == "사용" and not o.get("scaffold_types"):
        problems.append("비계 종류를 하나 이상 고르세요.")
    for i, h in enumerate(o.get("major_hazard_works") or [], start=1):
        if h.get("hazard_work") not in sel.MAJOR_HAZARD_WORK_OPTIONS_BY_OCCURRENCE.get(h.get("occurrence_type"), []):
            problems.append(f"대형사고 위험작업 {i}번째 줄의 발생형태·작업을 고르세요.")
        try:
            if datetime.date.fromisoformat(h.get("start_date", "")) > datetime.date.fromisoformat(h.get("end_date", "")):
                problems.append(f"대형사고 위험작업 {i}번째 줄의 시작일이 종료일보다 늦습니다.")
        except ValueError:
            problems.append(f"대형사고 위험작업 {i}번째 줄의 시작일·종료일을 넣으세요.")
    if o.get("bad_site_notify") and not (o.get("bad_site_content") or "").strip():
        problems.append("불량사업장 통보 내용을 쓰세요.")
    for f in files:
        if Path(f.filename or "").suffix.lower() not in _BAD_SITE_SUFFIXES:
            problems.append(f"불량사업장 첨부는 jpg·png·gif·bmp·pdf만 됩니다: {f.filename}")
    if problems:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, " / ".join(problems))
    busy = db.query(K2bSubmission).filter(K2bSubmission.report_id == report_id,
                                          K2bSubmission.status.in_(("queued", "running"))).first()
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 보고서는 지금 K2B에 제출하는 중입니다 — 끝날 때까지 기다리세요.")
    keep = {k: o.get(k) for k in ("current_process", "scaffold_usage", "scaffold_types", "bad_site_notify",
                                  "bad_site_content", "major_hazard_works", "allow_round_mismatch", "prev_guidance",
                                  "ceo_notice_quarter", "ceo_notice_date", "owner_notice_date")}
    job = K2bSubmission(company_id=user.company_id, report_id=report_id, staff_id=report.assigned_staff_id,
                        status="queued", options=keep, created_by=user.display_name or "")
    db.add(job)
    db.flush()
    if o.get("bad_site_notify") and files:
        folder = UPLOAD_DIR / f"job_{job.id}"
        folder.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files, start=1):
            (folder / f"{i:02d}_{Path(f.filename).name}").write_bytes(await f.read())
    db.commit()
    return _job_out(job)


def _job(db: Session, user: User, job_id: int) -> K2bSubmission:
    job = db.get(K2bSubmission, job_id)
    if job is None or job.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "제출 기록을 찾을 수 없습니다.")
    return job


@router.get("/k2b-jobs/{job_id}")
def k2b_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    out = _job_out(job)
    if job.status == "queued":
        out["ahead"] = db.query(K2bSubmission).filter(K2bSubmission.status.in_(("queued", "running")),
                                                     K2bSubmission.id < job.id).count()
    return out


@router.get("/k2b-jobs/{job_id}/shot")
def k2b_job_shot(job_id: int, n: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """n번째 화면(1부터 — 구역별 여러 장, 10/7). 예전 제출은 한 장."""
    paths = _shot_paths(_job(db, user, job_id))
    if not 1 <= n <= len(paths):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "화면 사진이 없습니다.")
    return FileResponse(paths[n - 1], media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/k2b-jobs/{job_id}/shots")
def k2b_job_shots(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """화면 목록 — 크게 보기 창(js/photo-viewer.js openPhotoViewer)이 넘겨 보게. 이름 = 파일 이름 끝 구역 이름."""
    paths = _shot_paths(_job(db, user, job_id))
    return [{"n": i, "label": (Path(p).stem.split("_K2B제출", 1)[-1].lstrip("_").split("_", 1)[-1].replace("_", "·") or "K2B 화면")}
            for i, p in enumerate(paths, 1)]
