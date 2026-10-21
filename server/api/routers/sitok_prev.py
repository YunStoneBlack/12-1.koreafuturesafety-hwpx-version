"""전회차 보고서 PDF(2026-10-18 민재형) — 시설물 현황 창·면담·변경사항 조사 창의 같은 칸(동 회차마다 하나). 읽기는 server/sitok/prev_pdf.py.

회차 화면 [지난 보고서 한글 올리기]를 없애고(우리 틀로 세팅한 뒤엔 무의미 — 형), 처음 세팅할 때 전회차가 있으면(우리 회사·타사) 이 PDF로.
직전 회차를 이 프로그램으로 만들었거나 예전에 한글을 올린 회차(_prior)는 그 한글 값을 그대로 씀 — PDF 칸은 그런 회차가 아닐 때만 보임.

- `GET    /sitok/reports/{id}/prev-pdf` — {has_prior, has, name, read: {at, pages, counts} | None}
- `POST   /sitok/reports/{id}/prev-pdf` — 올리기(PDF만 — 다시 올리면 읽은 값 지움, AI 안 씀)
- `DELETE /sitok/reports/{id}/prev-pdf` · `GET …/prev-pdf/file`
- `POST   /sitok/reports/{id}/prev-pdf/read` — AI로 읽기(다시 읽기) — 1.2.7 지난 이력 [🤖 읽기]
- `POST   /sitok/reports/{id}/survey/changes/prev` — 1.2.8 초안(저장 안 함, 처음이면 읽고) — 건축물대장 초안과 같은 모양
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _prior, _report_dir, _require
from server.sitok import master, prev_pdf, report_build as rb

router = APIRouter(prefix="/sitok", tags=["sitok"])


def prev_file(db: Session, r: SitokReport) -> Path:
    return prev_pdf.path(_report_dir(db.get(SitokFacility, r.facility_id), r))


def _status(db: Session, r: SitokReport) -> dict:
    p = prev_file(db, r)
    pv = (r.survey or {}).get("prev")
    read = None
    if pv:
        read = {"at": pv.get("at"), "pages": pv.get("pages") or [],
                "counts": {"fields": sum(1 for v in (pv.get("fields") or {}).values() if v not in ("", "-")), "checks": len(pv.get("checks") or {}),
                           "uses": len(pv.get("uses") or []), "history": len(pv.get("history") or []), "repairs": len(pv.get("repairs") or []),
                           "changes": len(pv.get("changes") or {}), "grade": ((pv.get("report") or {}).get("grade") or "")}}
    return {"has_prior": _prior(r) is not None, "prior_note": r.source_note if _prior(r) is not None else "",
            "has": p.exists(), "name": (r.survey or {}).get("prev_name") or (p.name if p.exists() else ""), "read": read}


def ensure_prev(db: Session, user: User, r: SitokReport, force: bool = False) -> dict:
    """읽은 값(없거나 force면 AI로 한 번 읽어 저장)."""
    if (r.survey or {}).get("prev") and not force:
        return r.survey["prev"]
    p = prev_file(db, r)
    if not p.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "전회차 보고서 PDF를 먼저 올리세요.")
    from server.sitok import detail

    m = master.master_path()
    if not m.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회사 원본 템플릿이 없습니다 — 시특법 설정에서 올리세요.")
    labels = [it["label"] for it in rb.read_survey(m)["change_items"]]
    f = db.get(SitokFacility, r.facility_id)
    try:
        pv = prev_pdf.read(p, user.company_id, f.name, detail.read(m), labels)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"전회차 보고서 PDF를 읽지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    r.survey = {**(r.survey or {}), "prev": pv}
    db.commit()
    return pv


@router.get("/reports/{report_id}/prev-pdf")
def get_prev(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _status(db, _require(db, user, report_id))


@router.post("/reports/{report_id}/prev-pdf")
def upload_prev(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "전회차 보고서는 PDF로 올려 주세요(한글이면 PDF로 저장해서).")
    p = prev_file(db, r)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    _seed_drawings(db, r, p)
    sv = {k: v for k, v in (r.survey or {}).items() if k != "prev"}  # 다시 올리면 전에 읽은 값은 버림
    sv["prev_name"] = file.filename or prev_pdf.NAME
    r.survey = sv
    db.commit()
    return _status(db, r)


def _seed_drawings(db: Session, r: SitokReport, pdf: Path) -> int:
    """옹벽(10/21 형): 전회차 보고서의 1.2.4 뒤 도면 쪽을 시설물 첨부 도면에(아직 없을 때만)."""
    from server.api.routers.sitok import _facility_dir
    from server.sitok import kinds, wall_drawings

    f = db.get(SitokFacility, r.facility_id)
    if f is None or not kinds.is_wall(f):
        return 0
    try:
        return wall_drawings.seed(f, _facility_dir(f), pdf)
    except Exception:  # noqa: BLE001
        return 0


@router.delete("/reports/{report_id}/prev-pdf")
def delete_prev(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    prev_file(db, r).unlink(missing_ok=True)
    r.survey = {k: v for k, v in (r.survey or {}).items() if k not in ("prev", "prev_name")}
    db.commit()
    return _status(db, r)


@router.get("/reports/{report_id}/prev-pdf/file")
def prev_pdf_file(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    p = prev_file(db, r)
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "전회차 보고서 PDF가 없습니다.")
    return FileResponse(p, media_type="application/pdf", content_disposition_type="inline", filename=p.name)


@router.post("/reports/{report_id}/prev-pdf/read")
def read_prev(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    ensure_prev(db, user, r, force=True)
    return _status(db, r)


@router.post("/reports/{report_id}/survey/changes/prev")
def changes_prev(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """1.2.8 초안(저장 안 함) — 전회차 보고서의 변경사항 표(변경사항없음이 아닌 항목). 점검자가 창에서 확인하고 저장."""
    r = _require(db, user, report_id)
    pv = ensure_prev(db, user, r)
    return {"changes": pv.get("changes") or {}, "events": [], "missing": []}
