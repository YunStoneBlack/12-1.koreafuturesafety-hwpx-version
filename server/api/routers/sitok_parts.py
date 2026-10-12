"""시특법 현장 화면 [공중이용]·[기타시설] 탭(2026-10-12 사용자, alembic 0037 sitok_report.parts) — 항목·내용은 server/sitok/parts.py.

- `GET    /sitok/reports/{id}/parts` — 공중이용 4항목(사진·해당없음)·기타시설(마감재 2·부착물 등 2).
- `POST   /sitok/reports/{id}/parts/photo` — form group(public|other)·key·slot(기타시설 0·1) + file → 그 칸 사진(있으면 바꿈).
- `DELETE /sitok/reports/{id}/parts/photo?group=&key=&slot=` — 그 칸 사진 지우기.
- `POST   /sitok/reports/{id}/parts/none` — {key, none} 공중이용 항목 해당없음 켜고 끄기(켜면 사진 지움).
- `GET    /sitok/reports/{id}/parts/photo?group=&key=&slot=` — 사진.
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
from server.api.routers.sitok_reports import _report_dir, _require
from server.contract_docs import files
from server.sitok import parts as P

router = APIRouter(prefix="/sitok", tags=["sitok"])
DIR = "공중이용_기타시설"


def base_dir(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r)


def _out(db: Session, r: SitokReport) -> dict:
    p = P.norm(r.parts)
    base = base_dir(db, r)
    pub = []
    for k, name in P.PUBLIC:
        it = p["public"].get(k) or {}
        crit, grades = P.PUBLIC_CRITERIA[k]
        pub.append({"key": k, "name": name, "has": bool(it.get("file") and (base / it["file"]).exists()), "none": bool(it.get("none")),
                    "hint": crit.split(" / ")[0]})
    other = [{"key": k, "name": name, "slots": [bool((base / x).exists()) for x in p["other"][k]] + [False] * (P.OTHER_SLOTS - len(p["other"][k]))}
             for k, name in P.OTHER]
    return {"public": pub, "other": other}


def _path(db: Session, r: SitokReport, group: str, key: str, slot: int) -> Path | None:
    p = P.norm(r.parts)
    if group == "public":
        f = (p["public"].get(key) or {}).get("file")
    else:
        lst = p["other"].get(key) or []
        f = lst[slot] if 0 <= slot < len(lst) else None
    return base_dir(db, r) / f if f else None


def _check(group: str, key: str) -> None:
    if (group == "public" and key not in dict(P.PUBLIC)) or (group == "other" and key not in dict(P.OTHER)) or group not in ("public", "other"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "항목이 맞지 않습니다.")


@router.get("/reports/{report_id}/parts")
def get_parts(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, report_id))


@router.post("/reports/{report_id}/parts/photo")
def add_photo(report_id: int, group: str = Form(...), key: str = Form(...), slot: int = Form(0), file: UploadFile = File(...),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check(group, key)
    r = _require(db, user, report_id)
    p = P.norm(r.parts)
    name = f"{DIR}/{group}_{key}_{uuid.uuid4().hex[:8]}.jpg"
    files.save_jpeg(file.file.read(), file.filename or "", base_dir(db, r) / name)
    old = _path(db, r, group, key, slot)
    if group == "public":
        p["public"][key] = {"file": name}
    else:
        lst = p["other"][key]
        if 0 <= slot < len(lst):
            lst[slot] = name
        else:
            lst.append(name)
        p["other"][key] = lst[:P.OTHER_SLOTS]
    if old is not None:
        old.unlink(missing_ok=True)
    r.parts = p
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/parts/photo")
def delete_photo(report_id: int, group: str, key: str, slot: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check(group, key)
    r = _require(db, user, report_id)
    p = P.norm(r.parts)
    old = _path(db, r, group, key, slot)
    if group == "public":
        p["public"].pop(key, None)
    elif 0 <= slot < len(p["other"][key]):
        p["other"][key].pop(slot)
    if old is not None:
        old.unlink(missing_ok=True)
    r.parts = p
    db.commit()
    return _out(db, r)


class NoneIn(BaseModel):
    key: str
    none: bool


@router.post("/reports/{report_id}/parts/none")
def set_none(report_id: int, body: NoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check("public", body.key)
    r = _require(db, user, report_id)
    p = P.norm(r.parts)
    old = _path(db, r, "public", body.key, 0)
    if body.none:
        p["public"][body.key] = {"none": True}
        if old is not None:
            old.unlink(missing_ok=True)
    else:
        p["public"].pop(body.key, None)
    r.parts = p
    db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/parts/photo")
def photo(report_id: int, group: str, key: str, slot: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check(group, key)
    path = _path(db, _require(db, user, report_id), group, key, slot)
    if path is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(path, media_type="image/jpeg")
