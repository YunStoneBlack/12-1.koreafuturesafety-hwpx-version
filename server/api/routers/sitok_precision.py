"""시특법 정밀안전점검 ④ 입력(2026-10-13 밤) — 자료수집(2.2·2.3.2·2.3.4·전차 검토), 하중상태 사진(3.2.6), 공중이용·기타시설 등급(3.2.7~8). 항목은 server/sitok/precision.py.

- `GET  /sitok/reports/{id}/precision` — 회차 종류 + 항목·값 + 점검이력(FMS 올린 것 + 우리 지난 회차 자동) + 전회차 요약(자동/직접) + 하중 사진 + 등급.
- `PUT  /sitok/reports/{id}/precision` — docs·seismic·manage·prev_review·load.note·load 제목 저장(survey["precision"]).
- `POST /sitok/reports/{id}/precision/fms` — FMS 점검진단실적 xlsx → history.   `DELETE …/fms` — 비움.
- `POST /sitok/reports/{id}/precision/load-photo` (slot·file) / `DELETE …/load-photo?slot=` / `GET …/load-photo?slot=` — 하중상태 사진 4장(회차 폴더 하중상태/).
- `POST /sitok/reports/{id}/precision/grade` {group public|other, key, grade a~e|""} — parts["grades"].
- `POST /sitok/reports/{id}/precision/survey-photo` (key·slot·file) / `DELETE`·`GET …/survey-photo?key=&slot=` — 조사 전경 사진(【사진 2.1】·【사진 4.1~4.5】,
  형 10/14: 외관조사 2·부재규격 수직재/수평재·강도 수직재/수평재·탄산화 수직재 천공/피복두께·수평재 천공/피복두께·기울기 2·부등침하 2) — 회차 폴더 조사전경/.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _order, _report_dir, _require
from server.contract_docs import files
from server.sitok import parts as P, precision as PR

router = APIRouter(prefix="/sitok", tags=["sitok-precision"])
DIR = "하중상태"
DIR2 = "조사전경"


def _base(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r)


def _prev_auto(db: Session, r: SitokReport) -> dict | None:
    """우리 지난 회차(AI 초안이 있는 가장 최근 것) → 전차 점검 요약 자동."""
    rows = db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id).all()
    before = [x for x in rows if _order(x) < _order(r) and (x.ai or {}).get("findings")]
    if not before:
        return None
    x = max(before, key=_order)
    ai = x.ai or {}
    return {"year": x.year, "half": x.half, "kind": f"{x.kind or '정기'}안전점검", "grade": ai.get("grade") or "", "lines": ai.get("findings") or []}


def _history_auto(db: Session, r: SitokReport) -> list[dict]:
    """우리 지난 회차들 → 점검이력 줄(FMS 양식과 같은 키)."""
    rows = db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id).all()
    out = []
    for x in sorted((x for x in rows if _order(x) < _order(r) and x.status == "done"), key=_order, reverse=True):  # 만들다 실패한·빈 회차는 빼고(10/14 숭의)
        ai = x.ai or {}
        grade, findings = ai.get("grade") or "", ai.get("findings") or []
        if (not grade or not findings) and x.out_hwpx and Path(x.out_hwpx).exists():  # 끝난 회차는 그 보고서 결과표의 등급·주요결과(이미 낸 보고서 등록분도)
            try:
                from server.sitok import report_build as rb
                old = rb.read_old(Path(x.out_hwpx))
                grade, findings = grade or (old.grade or ""), findings or (old.findings or [])
            except Exception:  # noqa: BLE001 — 못 읽으면 빈 채로
                pass
        out.append({"kind": f"{x.kind or '정기'}안전점검", "start": x.period_start.isoformat() if x.period_start else "", "end": x.period_end.isoformat() if x.period_end else "",
                    "org": "(주)한국미래안전", "grade": grade, "result": "\n".join(findings), "repair": "", "auto": True, "year": x.year, "half": x.half})
    return out


def _out(db: Session, r: SitokReport) -> dict:
    p = PR.norm((r.survey or {}).get("precision"))
    base = _base(db, r)
    photos = []
    for i in range(PR.LOAD_SLOTS):
        ph = p["load"]["photos"][i] if i < len(p["load"]["photos"]) else {"file": "", "title": ""}
        photos.append({"slot": i, "title": ph["title"], "has": bool(ph["file"] and (base / ph["file"]).exists())})
    parts = P.norm(r.parts)
    grades = parts.get("grades") or {}
    from server.api.routers.sitok_defects import _defects_for_cost
    survey = [{"key": k, "caption": cap, "title": title,
               "slots": [{"slot": i, "title": t, "has": bool(p["survey"][k][i] and (base / p["survey"][k][i]).exists())} for i, t in enumerate(titles)]}
              for k, cap, title, titles in PR.SURVEY_PICS]
    return {"report": {"id": r.id, "year": r.year, "half": r.half, "kind": r.kind or "정기"},
            "survey": survey, "checklist_auto": PR.auto_checklist(_defects_for_cost(db, r.id)),
            "docs": [{"group": g, "key": k, "name": n, **(p["docs"].get(k) or {"status": "", "note": ""})} for g, k, n in PR.DOC_ITEMS],
            "doc_status": PR.DOC_STATUS, "seismic": p["seismic"], "seismic_options": PR.SEISMIC, "ynu": PR.YNU,
            "manage": p["manage"], "checklist": PR.CHECKLIST, "history": p["history"], "history_auto": _history_auto(db, r),
            "prev_review": p["prev_review"], "prev_auto": _prev_auto(db, r),
            "load": {"photos": photos, "note": p["load"]["note"], "default_note": PR.LOAD_DEFAULT_NOTE},
            "grades": {"public": [{"key": k, "name": n, "grade": grades.get(k, ""), "criteria": P.PUBLIC_CRITERIA[k][0]} for k, n in P.PUBLIC],
                       "other": [{"key": k, "name": n, "grade": grades.get(k, ""), "criteria": P.OTHER_CRITERIA.get(k, "")} for k, n in P.OTHER]}}


@router.get("/reports/{report_id}/precision")
def get_precision(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, report_id))


@router.put("/reports/{report_id}/precision")
def save_precision(report_id: int, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    cur = PR.norm((r.survey or {}).get("precision"))
    new = PR.norm(body)
    if "docs" in body:
        cur["docs"] = {**cur["docs"], **new["docs"]}  # 보낸 항목만 바꿈
    for k in ("seismic", "manage", "prev_review"):
        if k in body:
            cur[k] = new[k]
    if "load" in body:
        lo = body["load"] or {}
        if "note" in lo:
            cur["load"]["note"] = str(lo.get("note") or "").strip()
        if "titles" in lo:  # 제목만(사진 파일은 올리기 API가)
            titles = [str(t or "").strip() for t in (lo.get("titles") or [])][:PR.LOAD_SLOTS]
            while len(cur["load"]["photos"]) < len(titles):
                cur["load"]["photos"].append({"file": "", "title": ""})
            for i, t in enumerate(titles):
                cur["load"]["photos"][i]["title"] = t
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r)


@router.post("/reports/{report_id}/precision/fms")
def upload_fms(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "FMS 점검진단실적 엑셀(.xlsx)을 올려 주세요.")
    try:
        rows = PR.read_fms(file.file.read())
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"읽지 못했습니다: {str(err)[:150]}") from err
    cur = PR.norm((r.survey or {}).get("precision"))
    cur["history"] = rows
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r) | {"read": len(rows)}


@router.delete("/reports/{report_id}/precision/fms")
def delete_fms(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    cur = PR.norm((r.survey or {}).get("precision"))
    cur["history"] = []
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r)


def _slot(slot: int) -> int:
    if not 0 <= slot < PR.LOAD_SLOTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "사진 칸은 1~4입니다.")
    return slot


@router.post("/reports/{report_id}/precision/load-photo")
def add_load_photo(report_id: int, slot: int = Form(0), file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    slot = _slot(slot)
    cur = PR.norm((r.survey or {}).get("precision"))
    name = f"{DIR}/하중_{slot + 1}_{uuid.uuid4().hex[:8]}.jpg"
    files.save_jpeg(file.file.read(), file.filename or "", _base(db, r) / name)
    while len(cur["load"]["photos"]) <= slot:
        cur["load"]["photos"].append({"file": "", "title": ""})
    old = cur["load"]["photos"][slot].get("file")
    if old:
        (_base(db, r) / old).unlink(missing_ok=True)
    cur["load"]["photos"][slot]["file"] = name
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/precision/load-photo")
def delete_load_photo(report_id: int, slot: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    slot = _slot(slot)
    cur = PR.norm((r.survey or {}).get("precision"))
    if slot < len(cur["load"]["photos"]) and cur["load"]["photos"][slot].get("file"):
        (_base(db, r) / cur["load"]["photos"][slot]["file"]).unlink(missing_ok=True)
        cur["load"]["photos"][slot]["file"] = ""
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/precision/load-photo")
def get_load_photo(report_id: int, slot: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    slot = _slot(slot)
    cur = PR.norm((r.survey or {}).get("precision"))
    f = cur["load"]["photos"][slot]["file"] if slot < len(cur["load"]["photos"]) else ""
    p = _base(db, r) / f if f else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(p, media_type="image/jpeg")


def _survey_slot(key: str, slot: int) -> int:
    if key not in PR.SURVEY_KEYS or not 0 <= slot < PR.SURVEY_KEYS[key]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "조사 전경 사진 칸이 아닙니다.")
    return slot


@router.post("/reports/{report_id}/precision/survey-photo")
def add_survey_photo(report_id: int, key: str = Form(...), slot: int = Form(0), file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    slot = _survey_slot(key, slot)
    cur = PR.norm((r.survey or {}).get("precision"))
    name = f"{DIR2}/{key}_{slot + 1}_{uuid.uuid4().hex[:8]}.jpg"
    files.save_jpeg(file.file.read(), file.filename or "", _base(db, r) / name)
    old = cur["survey"][key][slot]
    if old:
        (_base(db, r) / old).unlink(missing_ok=True)
    cur["survey"][key][slot] = name
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/precision/survey-photo")
def delete_survey_photo(report_id: int, key: str, slot: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    slot = _survey_slot(key, slot)
    cur = PR.norm((r.survey or {}).get("precision"))
    if cur["survey"][key][slot]:
        (_base(db, r) / cur["survey"][key][slot]).unlink(missing_ok=True)
        cur["survey"][key][slot] = ""
    r.survey = {**(r.survey or {}), "precision": cur}
    db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/precision/survey-photo")
def get_survey_photo(report_id: int, key: str, slot: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    slot = _survey_slot(key, slot)
    cur = PR.norm((r.survey or {}).get("precision"))
    f = cur["survey"][key][slot]
    p = _base(db, r) / f if f else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(p, media_type="image/jpeg")


class GradeIn(BaseModel):
    group: str
    key: str
    grade: str = ""


@router.post("/reports/{report_id}/precision/grade")
def set_grade(report_id: int, body: GradeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """공중이용·기타시설 항목 등급(정밀 3.2.7~8, 표 6.44~6.47) — parts["grades"][key]."""
    r = _require(db, user, report_id)
    if (body.group == "public" and body.key not in dict(P.PUBLIC)) or (body.group == "other" and body.key not in dict(P.OTHER)) or body.group not in ("public", "other"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "항목이 맞지 않습니다.")
    g = (body.grade or "").strip().lower()
    if g and g not in PR.GRADES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "등급은 a~e입니다.")
    parts = P.norm(r.parts)
    grades = dict(parts.get("grades") or {})
    if g:
        grades[body.key] = g
    else:
        grades.pop(body.key, None)
    parts["grades"] = grades
    r.parts = parts
    db.commit()
    return _out(db, r)["grades"]
