"""시특법 FMS 제출(2026-10-15 — 시특법 7단계, 사용자 "시작"). 회차 화면 "📤 FMS 제출" 칸이 씀(js/sitok-fms.js).

- 회사 FMS 계정: app_setting fms_id·fms_pw(암호화 — server/api/k2b_secret, K2B와 같은 열쇠). 바꾸기는 그룹웨어 관리자만.
- 관리주체 FMS 계정: 시설물 카드(sitok_facility.fms_owner_id·fms_owner_pw, 형 10/15) — 있으면 승인까지 자동, 없으면 승인요청까지.
- 미리보기 GET /sitok/reports/{id}/fms = 같이 내는 회차(묶음 동, 있는 것만) → server/sitok/fms.payload + e-보고서 파일 계획 + 계정·기록.
- 제출 POST /sitok/reports/{id}/fms {stage: practice|contract|result, stop_before_request} → fms_submission 대기열 →
  작업 프로그램(server/worker/fms_worker.py)이 하나씩. 같은 묶음에 진행 중인 작업이 있으면 409.
- 대표자 바로잡기 POST …/fms/rep = 마지막 연습에서 읽은 FMS 대표자로 계약 대표자를 바꿈(민재형 "대표자는 FMS 기준 — 다르면 경고·바꾸기").
"""
from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_db import AppSetting
from core.models_web import FmsSubmission, SitokContract, SitokFacility, SitokReport, User
from server.api import k2b_secret
from server.api.deps import get_current_user, get_db, is_groupware_admin

router = APIRouter(prefix="/sitok", tags=["sitok"])
STAGES = ("practice", "contract", "result")
STAGE_LABEL = {"practice": "연습(채워 보기)", "contract": "계약 등록", "result": "실적 보고"}


def _setting(db: Session, company_id: int, key: str) -> AppSetting | None:
    return db.query(AppSetting).filter(AppSetting.company_id == company_id, AppSetting.key == key).first()


def company_cred(db: Session, company_id: int) -> tuple[str, str] | None:
    a, b = _setting(db, company_id, "fms_id"), _setting(db, company_id, "fms_pw")
    if not a or not a.value or not b or not b.value:
        return None
    return a.value, k2b_secret.decrypt(b.value)


def owner_cred(f: SitokFacility) -> tuple[str, str] | None:
    if not f.fms_owner_id or not f.fms_owner_pw:
        return None
    return f.fms_owner_id, k2b_secret.decrypt(f.fms_owner_pw)


def together(db: Session, r: SitokReport) -> list[SitokReport]:
    """같이 내는 회차 — 묶음 동의 같은 해·반기 회차(있는 것만, 묶음 순서). 묶음이 아니면 이 회차 하나."""
    f = db.get(SitokFacility, r.facility_id)
    if not f.group_id:
        return [r]
    mates = db.query(SitokFacility).filter(SitokFacility.group_id == f.group_id).order_by(SitokFacility.group_order, SitokFacility.id).all()
    out = []
    for m in mates:
        x = r if m.id == f.id else db.query(SitokReport).filter(SitokReport.facility_id == m.id, SitokReport.year == r.year, SitokReport.half == r.half).first()
        if x is not None:
            out.append(x)
    return out


def _require(db: Session, user: User, rid: int) -> SitokReport:
    r = db.get(SitokReport, rid)
    if r is None or r.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "회차를 찾을 수 없습니다.")
    return r


def _result_practice(j: FmsSubmission) -> bool:
    """계약 번호가 생긴 뒤의 연습(실적 화면 채워 보기, 10/25)."""
    return j.stage == "practice" and (j.options or {}).get("target") == "result"


def _job_out(j: FmsSubmission) -> dict:
    label = "실적 연습(채워 보기)" if _result_practice(j) else STAGE_LABEL.get(j.stage, j.stage)
    return {"id": j.id, "stage": j.stage, "stage_label": label, "status": j.status, "message": j.message,
            "project_no": j.project_no, "result": j.result or {}, "log": (j.log or "").splitlines()[-40:], "shots": len(j.shots or []),
            "created_by": j.created_by, "created_at": j.created_at.strftime("%m-%d %H:%M") if j.created_at else "",
            "run_at": j.run_at.strftime("%Y-%m-%d %H:%M") if j.run_at else "", "retry": bool((j.options or {}).get("retry")),
            "finished_at": j.finished_at.strftime("%H:%M") if j.finished_at else ""}


def _deadline(r: SitokReport) -> dict | None:
    """실적보고 기한 — 점검기간 마지막 날부터 30일 안(넘으면 과태료, 10/25 사용자). {start, end, days_left}."""
    if not r.period_end:
        return None
    end = r.period_end + datetime.timedelta(days=30)
    return {"start": r.period_end.isoformat(), "end": end.isoformat(), "days_left": (end - datetime.date.today()).days}


def _jobs(db: Session, reps: list[SitokReport]) -> list[FmsSubmission]:
    ids = {r.id for r in reps}
    rows = db.query(FmsSubmission).filter(FmsSubmission.company_id == reps[0].company_id).order_by(FmsSubmission.id.desc()).limit(60).all()
    return [j for j in rows if ids & set(j.report_ids or [])][:10]


@router.get("/reports/{rid}/fms/file")
def fms_file(rid: int, folder: str, name: str, dl: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """e-보고서로 나눌 파일 하나 — 누르면 미리보기(창에서 PDF), dl=1이면 내려받기(10/25 민재형). 대가내역서는 서류 자동화 계약의 대가내역서.pdf."""
    from urllib.parse import quote

    from fastapi.responses import Response

    from server.sitok import fms

    r = _require(db, user, rid)
    disp = lambda: ("attachment" if dl else "inline") + f"; filename*=UTF-8''{quote(name + '.pdf')}"  # noqa: E731
    if folder == "계약서 및 대가내역서" and name == "대가내역서":
        files, notes = fms.contract_files(db, together(db, r))
        if not files:
            raise HTTPException(status.HTTP_404_NOT_FOUND, (notes or ["대가내역서가 없습니다."])[0])
        return Response(Path(files[0]["file"]).read_bytes(), media_type="application/pdf", headers={"Content-Disposition": disp()})
    pdf = Path(r.out_pdf) if r.out_pdf else None
    if pdf is None or not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서(합본 PDF)를 아직 만들지 않았습니다.")
    data = fms.split_file(pdf, folder, name, r.kind or "정기")
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그 파일이 없습니다 — 보고서를 다시 만들었으면 화면을 새로 고치세요.")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": disp()})


@router.get("/reports/{rid}/fms")
def fms_info(rid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from server.sitok import fms

    r = _require(db, user, rid)
    reps = together(db, r)
    payload = fms.payload(db, reps)
    notes = list(payload["notes"])
    # e-보고서 파일 계획(합본 PDF 쪽 글로 나누기 — 미리보기는 계획만)
    plan, pdf = [], Path(r.out_pdf) if r.out_pdf else None
    if pdf and pdf.exists():
        try:
            plan = [{"folder": x["folder"], "name": x["name"], "pages": sum(b - a + 1 for a, b in x["pages"])} for x in fms.split_plan(pdf, r.kind or "정기")]
        except Exception as e:  # noqa: BLE001
            notes.append(f"합본 PDF를 나누지 못했습니다: {str(e)[:80]}")
    else:
        notes.append("보고서(합본 PDF)를 아직 만들지 않았습니다 — 실적 보고 전에 만드세요")
    from core.models_web import SitokDocContract
    q = db.query(SitokDocContract)
    doc = (q.filter(SitokDocContract.report_contract_id == r.contract_id).first() if r.contract_id else None) \
        or q.filter(SitokDocContract.facility_id.in_([x.facility_id for x in reps])).order_by(SitokDocContract.id.desc()).first()
    if doc is None:
        notes.append("대가내역서: 이어진 서류 자동화 계약이 없어 못 만듭니다 — 서류 자동화 · 시특법 계약에서 만드세요")
    else:
        plan.insert(0, {"folder": "계약서 및 대가내역서", "name": "대가내역서", "pages": 1, "doc_contract": doc.id})
    facs = [db.get(SitokFacility, x.facility_id) for x in reps]
    jobs = _jobs(db, reps)
    last_practice = next((j for j in jobs if j.stage == "practice" and j.status == "done" and not _result_practice(j)), None)  # FMS 대표자는 계약 연습에서
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    rep = {"ours": c.rep_name if c else "", "fms": (last_practice.result or {}).get("fms_rep", "") if last_practice else ""}
    rep["differs"] = bool(rep["ours"] and rep["fms"] and rep["ours"].replace(" ", "") != rep["fms"].replace(" ", ""))
    has_company = bool(_setting(db, user.company_id, "fms_id") and (_setting(db, user.company_id, "fms_id").value or ""))
    state = r.fms or {}
    ids = {f.id for f in facs if f.fms_owner_id and f.fms_owner_pw}
    from server.api.routers.sitok import card_facilities
    seen, choices = set(), []
    for x in card_facilities(db, facs[0]):  # 같은 카드의 다른 보고서(보고서 1·2 따로 내는 시설물)에 넣어 둔 계정 — 골라 쓰기(아이디만 보냄)
        if x.id in {f.id for f in facs} or not (x.fms_owner_id and x.fms_owner_pw) or x.fms_owner_id in seen:
            continue
        seen.add(x.fms_owner_id)
        choices.append({"facility_id": x.id, "facility": x.name, "owner_id": x.fms_owner_id})
    owner_ids = sorted({f.fms_owner_id for f in facs if f.fms_owner_id and f.fms_owner_pw})
    return {"reports": [{"id": x.id, "facility": f.name, "fms_no": f.fms_no, "owner_account": f.id in ids,
                         "owner_id": f.fms_owner_id, "facility_id": f.id} for x, f in zip(reps, facs)],
            "owner": {"id": next((f.fms_owner_id for f in facs if f.id in ids), ""), "all": len(ids) == len(facs), "mixed": len(owner_ids) > 1,
                      "choices": choices},  # 발주처 계정 한 줄(같이 내는 동 공통 — 작업 프로그램은 계정 있는 첫 동 것을 씀)
            "payload": payload, "files": plan, "notes": notes, "rep": rep, "state": state, "deadline": _deadline(r),
            "accounts": {"company": has_company, "company_id": (_setting(db, user.company_id, "fms_id").value if has_company else ""),
                         "is_admin": is_groupware_admin(request)},
            "jobs": [_job_out(j) for j in jobs]}


class SubmitIn(BaseModel):
    stage: str
    stop_before_request: bool = True
    run_at: str | None = None  # 예약 "2026-11-20T07:00"(10/25) — 비면 바로


@router.post("/reports/{rid}/fms")
def fms_submit(rid: int, body: SubmitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, rid)
    if body.stage not in STAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "단계를 고르세요.")
    if not company_cred(db, user.company_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회사 FMS 계정이 없습니다 — 이 칸의 [회사 FMS 계정]에서 넣어 주세요(관리자).")
    reps = together(db, r)
    ids = [x.id for x in reps]
    run_at = None
    if body.run_at:
        try:
            run_at = datetime.datetime.fromisoformat(body.run_at)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "예약 날짜·시각이 맞지 않습니다.") from err
        if body.stage == "practice":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "연습은 예약하지 않습니다 — 바로 하세요.")
    when = run_at or datetime.datetime.now()
    jobs = _jobs(db, reps)
    if any(j.status == "running" for j in jobs) and run_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 회차는 지금 FMS 작업 중입니다 — 끝날 때까지 기다리세요.")
    if any(j.status == "queued" and j.stage == body.stage for j in jobs):
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 단계가 이미 대기(예약) 중입니다 — 그 예약을 취소한 뒤 다시 하세요.")
    state = r.fms or {}
    if body.stage == "result":
        planned = any(j.status in ("queued", "running") and j.stage == "contract" and (j.run_at or j.created_at) <= when for j in jobs)
        if not state.get("project_no") and not planned:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "FMS 계약 번호가 없습니다 — 먼저 [FMS 계약 등록]을 하거나 그보다 앞서 예약하세요.")
        if r.period_end and when.date() < r.period_end:  # FMS 실적보고는 점검기간 마지막 날부터(10/25 사용자)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"실적보고는 점검기간 마지막 날({r.period_end:%Y-%m-%d})부터 됩니다 — 그날 이후로 예약하세요.")
    if body.stage == "result" and not (r.out_pdf and Path(r.out_pdf).exists()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "보고서(합본 PDF)를 먼저 만드세요 — e-보고서 파일이 거기서 나옵니다.")
    opts = {"stop_before_request": bool(body.stop_before_request)}
    if body.stage == "practice" and state.get("project_no"):
        opts["target"] = "result"  # 계약 등록 뒤 연습 = 실적 화면 채워 보기(10/25 민재형 "실적보고도 연습이 생기는지?")
    j = FmsSubmission(company_id=user.company_id, report_ids=ids, stage=body.stage, status="queued", run_at=run_at,
                      options=opts, project_no=state.get("project_no", ""),
                      created_by=user.display_name or "")
    db.add(j)
    db.commit()
    return _job_out(j)


@router.delete("/fms-jobs/{jid}")
def fms_job_cancel(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """대기(예약) 중인 FMS 작업 취소(10/25) — 시작한 작업은 못 멈춤."""
    j = db.get(FmsSubmission, jid)
    if j is None or j.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업이 없습니다.")
    if j.status != "queued":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 시작했거나 끝난 작업은 취소할 수 없습니다.")
    j.status, j.message, j.finished_at = "cancelled", f"예약 취소 — {user.display_name or ''}", datetime.datetime.now()
    db.commit()
    return _job_out(j)


@router.get("/fms-jobs/{jid}")
def fms_job(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(FmsSubmission, jid)
    if j is None or j.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업이 없습니다.")
    return _job_out(j)


@router.get("/fms-jobs/{jid}/shot")
def fms_job_shot(jid: int, n: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from core.stored_path import to_full

    j = db.get(FmsSubmission, jid)
    if j is None or j.company_id != user.company_id or not j.shots or not (1 <= n <= len(j.shots)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "화면이 없습니다.")
    p = Path(to_full(j.shots[n - 1]))
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "화면 파일이 없습니다.")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})


class CredIn(BaseModel):
    user_id: str
    password: str = ""


@router.put("/fms/account")
def save_company_account(body: CredIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_groupware_admin(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "회사 FMS 계정은 그룹웨어 관리자만 바꿀 수 있습니다.")
    uid = body.user_id.strip()
    if not uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "아이디를 넣어 주세요.")
    for key, val in (("fms_id", uid), ("fms_pw", k2b_secret.encrypt(body.password) if body.password else None)):
        if val is None:
            continue
        row = _setting(db, user.company_id, key)
        if row is None:
            db.add(AppSetting(company_id=user.company_id, key=key, value=val))
        else:
            row.value = val
    if not body.password and not _setting(db, user.company_id, "fms_pw"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "비밀번호를 넣어 주세요.")
    db.commit()
    return {"ok": True, "user_id": uid}


@router.put("/facilities/{fid}/fms-owner")
def save_owner_account(fid: int, body: CredIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """관리주체 FMS 계정(시설물 카드) — 아이디를 비우면 지움(그 시설물은 승인요청까지만)."""
    f = db.get(SitokFacility, fid)
    if f is None or f.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "시설물을 찾을 수 없습니다.")
    uid = body.user_id.strip()
    if not uid:
        f.fms_owner_id, f.fms_owner_pw = "", ""
    else:
        if body.password:
            f.fms_owner_pw = k2b_secret.encrypt(body.password)
        elif not f.fms_owner_pw or f.fms_owner_id != uid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "비밀번호를 넣어 주세요.")
        f.fms_owner_id = uid
    db.commit()
    return {"ok": True, "owner_id": f.fms_owner_id, "has_pw": bool(f.fms_owner_pw)}


class OwnerIn(BaseModel):
    user_id: str = ""
    password: str = ""
    from_facility_id: int | None = None  # 같은 카드 다른 보고서 계정 그대로 쓰기(비밀번호는 서버 안에서만 복사)


@router.put("/reports/{rid}/fms/owner")
def save_owner(rid: int, body: OwnerIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """발주처(관리주체) FMS 계정 — 같이 내는 동(묶음이면 전부, 아니면 이 회차 시설물)에 같은 계정을 저장(10/25). 아이디를 비우면 지움."""
    from server.api.routers.sitok import card_facilities

    r = _require(db, user, rid)
    facs = [db.get(SitokFacility, x.facility_id) for x in together(db, r)]
    if body.from_facility_id:
        src = db.get(SitokFacility, body.from_facility_id)
        if src is None or src.company_id != user.company_id or src.id not in {x.id for x in card_facilities(db, facs[0])} or not (src.fms_owner_id and src.fms_owner_pw):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "그 시설물에 쓸 계정이 없습니다.")
        uid, pw = src.fms_owner_id, src.fms_owner_pw
    else:
        uid = body.user_id.strip()
        pw = k2b_secret.encrypt(body.password) if body.password else ""
        if uid and not pw:  # 비밀번호를 안 넣으면 — 이미 같은 아이디로 저장된 동의 비밀번호를 씀
            pw = next((f.fms_owner_pw for f in facs if f.fms_owner_id == uid and f.fms_owner_pw), "")
            if not pw:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "비밀번호를 넣어 주세요.")
    for f in facs:
        f.fms_owner_id, f.fms_owner_pw = (uid, pw) if uid else ("", "")
    db.commit()
    return {"ok": True, "owner_id": uid, "facilities": len(facs)}


@router.post("/reports/{rid}/fms/rep")
def fix_rep(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """계약 대표자를 마지막 연습에서 읽은 FMS 대표자로(FMS 기준)."""
    r = _require(db, user, rid)
    jobs = _jobs(db, together(db, r))
    last = next((j for j in jobs if j.stage == "practice" and j.status == "done" and (j.result or {}).get("fms_rep")), None)
    if last is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "FMS 대표자를 아직 모릅니다 — [연습(채워 보기)]를 먼저 하세요.")
    c = db.get(SitokContract, r.contract_id) if r.contract_id else None
    if c is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이 회차에 계약이 없습니다.")
    c.rep_name = last.result["fms_rep"]
    db.commit()
    return {"ok": True, "rep_name": c.rep_name, "at": datetime.datetime.now().isoformat(timespec="seconds")}
