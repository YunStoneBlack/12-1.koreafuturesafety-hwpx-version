"""시특법 부록 외관망도 첨부(2026-10-23 사용자 "부록 외관망도 첨부해서 합본하는 기능 — 일단 외관망도 프로그램 기능 만들기 전까지 활용").

회차 화면 [📐 부록 외관망도]에 PDF·그림(여러 개)을 올리면 보고서를 만들 때 합본의 부록 "외관망도" 간지(정기 "부록3-2. 외 관 망 도") 뒤에 끼움 —
간지가 없는 틀(옹벽 등)이면 "기타 부록 참고자료" 간지 뒤(기타 부록 첫 자료), 그것도 없으면 맨 뒤. 그림은 A4(가로 그림이면 가로 쪽)에 여백 두고 맞춤.

- `GET    /sitok/reports/{id}/maps` — [{idx, name, pages}]
- `POST   /sitok/reports/{id}/maps` (file) — 하나 더(PDF·jpg·png)
- `DELETE /sitok/reports/{id}/maps/{idx}` · `GET /sitok/reports/{id}/maps/{idx}` — 지우기·보기
- `POST   /sitok/reports/{id}/maps/{idx}/zone` {zone} — 동(10/30, 시설물 1개 안 연결된 동 — 사진첩처럼 "N. 동 이름" 간지 뒤에 그 동 망도, 동 없는 파일은 간지 없이 맨 앞)
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db

router = APIRouter(prefix="/sitok", tags=["sitok"])
KEY = "appearance_maps"  # 회차 survey — [{file(회차 폴더 상대), name}]
DIR = "부록_외관망도"
A4 = (595.3, 841.9)


def _base(db: Session, r: SitokReport) -> Path:
    from server.api.routers.sitok_reports import _report_dir

    return _report_dir(db.get(SitokFacility, r.facility_id), r)


def _rows(r: SitokReport) -> list[dict]:
    return [x for x in ((r.survey or {}).get(KEY) or []) if isinstance(x, dict) and x.get("file")]


def map_files(db: Session, r: SitokReport) -> list[Path]:
    base = _base(db, r)
    return [base / x["file"] for x in _rows(r) if (base / x["file"]).exists()]


def _pages(p: Path) -> int:
    if p.suffix.lower() != ".pdf":
        return 1
    try:
        with pymupdf.open(p) as d:
            return d.page_count
    except Exception:  # noqa: BLE001
        return 0


def _zones(db: Session, r: SitokReport) -> list[str]:
    """회차 시설물의 동 차례(10/30) — 결함 동과 같은 함수(sitok_defects.facility_zones)."""
    from server.api.routers.sitok_defects import _rows as defect_rows, facility_zones

    return facility_zones(db.get(SitokFacility, r.facility_id), defect_rows(db, r.id))


def _out(db: Session, r: SitokReport) -> dict:
    base = _base(db, r)
    return {"files": [{"idx": i, "name": x.get("name") or Path(x["file"]).name, "pages": _pages(base / x["file"]), "zone": x.get("zone") or ""}
                      for i, x in enumerate(_rows(r)) if (base / x["file"]).exists()],
            "zones": _zones(db, r)}


def _require(db: Session, user: User, report_id: int) -> SitokReport:
    from server.api.routers.sitok_reports import _require as req

    return req(db, user, report_id)


@router.get("/reports/{report_id}/maps")
def get_maps(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, report_id))


@router.post("/reports/{report_id}/maps")
def add_map(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    data = file.file.read()
    name = file.filename or "외관망도"
    ext = Path(name).suffix.lower()
    if data.startswith(b"%PDF"):
        ext = ".pdf"
    elif ext not in (".jpg", ".jpeg", ".png"):
        try:
            with pymupdf.open(stream=data) as d:  # 확장자가 이상한 그림
                ext = ".png" if d.metadata.get("format", "").lower().startswith("png") else ".jpg"
        except Exception as err:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "외관망도는 PDF나 그림(jpg·png)으로 올려 주세요.") from err
    rel = f"{DIR}/{re.sub(r'[^0-9A-Za-z가-힣_-]+', '_', Path(name).stem)[:40]}_{uuid.uuid4().hex[:6]}{ext}"
    dest = _base(db, r) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    if ext == ".pdf" and _pages(dest) == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF를 열 수 없습니다 — 파일을 확인하세요.")
    r.survey = {**(r.survey or {}), KEY: _rows(r) + [{"file": rel, "name": name}]}
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/maps/{idx}")
def del_map(report_id: int, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    rows = _rows(r)
    if not 0 <= idx < len(rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    (_base(db, r) / rows[idx]["file"]).unlink(missing_ok=True)
    r.survey = {**(r.survey or {}), KEY: rows[:idx] + rows[idx + 1:]}
    db.commit()
    return _out(db, r)


class ZoneIn(BaseModel):
    zone: str = ""


@router.post("/reports/{report_id}/maps/{idx}/zone")
def set_map_zone(report_id: int, idx: int, body: ZoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """외관망도 파일의 동(10/30) — 빈 글 = 동 없음(간지 없이 맨 앞)."""
    r = _require(db, user, report_id)
    rows = _rows(r)
    if not 0 <= idx < len(rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    zone = (body.zone or "").strip()
    if zone and zone not in _zones(db, r):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{zone}' 동이 없습니다 — 현장 조사 화면의 동 칩에서 먼저 더하세요.")
    rows[idx] = {**rows[idx], "zone": zone}
    r.survey = {**(r.survey or {}), KEY: rows}
    db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/maps/{idx}")
def get_map(report_id: int, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    rows = _rows(r)
    p = _base(db, r) / rows[idx]["file"] if 0 <= idx < len(rows) else None
    if p is None or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return FileResponse(p, media_type="application/pdf" if p.suffix.lower() == ".pdf" else "image/jpeg", content_disposition_type="inline", filename=rows[idx].get("name") or p.name)


def insert_maps(db: Session, reps: list[SitokReport], pdf: Path, names: list[str] | None = None) -> bool:
    """합본 PDF에 회차들(묶음이면 동 차례)의 외관망도를 끼움 — "외관망도/외관조사망도" 간지 뒤, 없으면 "기타 부록 참고자료" 간지 뒤, 없으면 맨 뒤. 끼웠으면 True.
    names(묶음 동 이름)를 주고 동이 둘 이상이면 동마다 "부록3-2-k. 동 이름" 간지 + 그 동 망도(사진첩 "부록2-k." 간지와 같은 모양, 10/23 형 "외관망도 간지 사진첩과 동일하게").
    회차 하나에 동(시설물 1개 안 연결된 동, 10/30)이 있으면 사진첩과 같은 "N. 동 이름" 간지(album_make._zone_page) 뒤에 그 동 파일 — 동 없는 파일은 간지 없이 맨 앞."""
    from server.sitok.album_make import _zone_page
    from server.sitok.precision_merge import _divider_page

    per = [(k, x, map_files(db, x)) for k, x in enumerate(reps, 1)]
    files = [p for _, _, fs in per for p in fs]
    if not files or not pdf.exists():
        return False
    norm = lambda t: re.sub(r"\s+", "", t or "")  # noqa: E731 — 간지는 "외 관 망 도"처럼 띄어 씀
    doc = pymupdf.open(pdf)
    short = lambda i: len(doc[i].get_text().strip()) < 160 and "부록" in doc[i].get_text()  # noqa: E731
    at = next((i + 1 for i in range(len(doc) - 1, -1, -1) if short(i) and any(k in norm(doc[i].get_text()) for k in ("외관망도", "외관조사망도"))), None)
    if at is None:  # 뒤에서부터 — 앞쪽 목차(▣ 부록 줄)가 아니라 실제 간지. 그 간지 뒤(기타 부록 첫 자료로)
        at = next((i + 1 for i in range(len(doc) - 1, -1, -1) if short(i) and "기타부록참고자료" in norm(doc[i].get_text())), len(doc))
    num = re.search(r"부록\s*([\d\-]+)\s*\.", doc[at - 1].get_text()) if 0 < at <= len(doc) else None
    add = pymupdf.open()
    for k, x, fs in per:
        if not fs:
            continue
        if names and len(reps) > 1 and 0 < at <= len(doc):
            _divider_page(add, doc[at - 1], f"부록{num[1]}-{k}. {names[k - 1]}" if num else f"{names[k - 1]} 외관망도")
        zs = _zones(db, x) if len(reps) == 1 else []
        if zs and any(row.get("zone") for row in _rows(x)):  # 동마다 간지(10/30) — 동 차례, 동 없는 파일 먼저
            base = _base(db, x)
            by = {z: [base / row["file"] for row in _rows(x) if (row.get("zone") or "") == z and (base / row["file"]).exists()] for z in ["", *zs]}
            _add_files(add, by[""])
            for n, z in enumerate(zs, 1):
                if by[z]:
                    _zone_page(add, f"{n}. {z}")
                    _add_files(add, by[z])
            continue
        _add_files(add, fs)
    doc.insert_pdf(add, start_at=at)
    add.close()
    tmp = pdf.with_suffix(".maps.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return True


def _add_files(add, files: list[Path]) -> None:
    """올린 외관망도(PDF는 그대로, 그림은 A4 한 쪽에 비율대로 — 가로 그림이면 가로 쪽)를 add 끝에."""
    for p in files:
        if p.suffix.lower() == ".pdf":
            with pymupdf.open(p) as s:
                add.insert_pdf(s)
            continue
        with pymupdf.open(p) as im:
            w, h = im[0].rect.width, im[0].rect.height
        pw, ph = (A4[1], A4[0]) if w > h else A4
        page = add.new_page(width=pw, height=ph)
        page.insert_image(pymupdf.Rect(28, 28, pw - 28, ph - 28), filename=str(p), keep_proportion=True)
