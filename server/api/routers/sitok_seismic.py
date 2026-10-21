"""내진성능평가 현장시험(2026-10-21 형 "내진성능평가로 새로 항목 만들기") — 성능평가 회차(반기 칸·종류 "성능평가")의 철근탐사.
(부재규격·코어·조적은 다음 단계에 같은 화면으로.)

- `GET   /sitok/reports/{id}/seismic` — 철근탐사 줄 + 일람표 칸(고르기용) + 층 + 필요 수량
- `PATCH /sitok/reports/{id}/seismic/rebar` {rows} — 줄 저장(설계값은 일람표에서 자동, 사람이 고친 줄은 그대로)
- `POST  /sitok/reports/{id}/seismic/rebar/{row}/capture/{line}` — 탐사기 화면 캡처 → 조사값·피복(server/sitok/rebar_capture, AI 약 10원)
- `GET   /sitok/reports/{id}/seismic/rebar/{row}/capture/{line}` — 올린 캡처
- `GET   /sitok/reports/{id}/seismic/rebar.xlsx` — 철근배근 상태조사 표(본문 2.2.2 = 부록, 같은 표)
화면 sitok-seismic.html(js/sitok-seismic.js). 값은 회차 survey["rebar"](재료시험 tests는 저장 때 모르는 칸을 지워서 따로).
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _report_dir, _require
from server.sitok import rebar_schedule as RS
from server.sitok import rebar_survey as RV

router = APIRouter(prefix="/sitok", tags=["sitok-seismic"])


def _floors(f: SitokFacility, schedule: dict | None) -> list[int]:
    """조사 층 — 지하 아래층부터 지상 위층까지(관리대장 층수), 없으면 일람표 층 표기에서."""
    below, above = f.floors_below or 0, f.floors_above or 0
    if below or above:
        return [-b for b in range(below, 0, -1)] + list(range(1, above + 1))
    seen = set()
    for it in RS.view(schedule).get("items") or []:
        rng = RS.floor_range(it["floors"])
        if rng and rng[1] < RS.FLOOR_TOP and rng[1] - rng[0] < 40:
            seen |= {n for n in range(rng[0], rng[1] + 1) if n}
    return sorted(seen)


def _rebar(r: SitokReport) -> dict:
    return RV.normalize((r.survey or {}).get("rebar"))


def _put(r: SitokReport, data: dict) -> None:
    r.survey = {**(r.survey or {}), "rebar": data}


def _out(db: Session, r: SitokReport) -> dict:
    f = db.get(SitokFacility, r.facility_id)
    sch = (f.ledger or {}).get("rebar_schedule")
    sv = RS.view(sch)
    data = _rebar(r)
    floors = _floors(f, sch)
    rows = [{**x, "mismatch": RV.mismatch(x)} for x in data["rows"]]
    return {"report": {"id": r.id, "year": r.year, "half": r.half, "kind": r.kind or "정기", "facility_id": f.id, "facility_name": f.name},
            "floors": [{"n": n, "label": RS.floor_label(n)} for n in floors],
            "schedule": {"count": len(sv["items"]), "need": sv["need"], "read_at": sv["read_at"],
                         "items": [{"id": x["id"], "kind": x["kind"], "marks": x["marks"], "floors": x["floors"], "range": RS.floor_range(x["floors"]),
                                    "position": x.get("position") or "", "confirmed": x["confirmed"], "check_ok": x["check"]["ok"]} for x in sv["items"]]},
            "lines": RV.LINES, "rows": rows, "counts": RV.counts(data["rows"], floors)}


@router.get("/reports/{report_id}/seismic")
def get_seismic(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, report_id))


class RowsIn(BaseModel):
    rows: list[dict]


@router.patch("/reports/{report_id}/seismic/rebar")
def save_rebar(report_id: int, body: RowsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    sch = (f.ledger or {}).get("rebar_schedule")
    old = {x["id"]: x for x in _rebar(r)["rows"]}
    data = RV.normalize({"rows": body.rows})
    for row in data["rows"]:
        prev = old.get(row["id"])
        row["captures"] = prev["captures"] if prev else ["", ""]  # 캡처 파일 이름은 서버만 정함
        RV.fill_design(row, sch)
    _put(r, data)
    db.commit()
    return _out(db, r)


def _row(r: SitokReport, row_id: str) -> tuple[dict, int]:
    data = _rebar(r)
    for i, x in enumerate(data["rows"]):
        if x["id"] == row_id:
            return data, i
    raise HTTPException(status.HTTP_404_NOT_FOUND, "그 줄이 없습니다 — 화면을 새로 고치세요.")


@router.post("/reports/{report_id}/seismic/rebar/{row_id}/capture/{line}")
def upload_capture(report_id: int, row_id: str, line: int, file: UploadFile = File(...), user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    from server.sitok import rebar_capture

    if line not in (0, 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "줄은 0 또는 1입니다.")
    r = _require(db, user, report_id)
    data, i = _row(r, row_id)
    try:
        im = Image.open(io.BytesIO(file.file.read())).convert("RGB")
    except (UnidentifiedImageError, OSError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "탐사기 화면 캡처 그림(png·jpg)을 올려 주세요.") from err
    f = db.get(SitokFacility, r.facility_id)
    row = data["rows"][i]
    rel = f"철근탐사/RC{row['no']}_{line + 1}_{uuid.uuid4().hex[:6]}.png"
    dest = _report_dir(f, r) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")
    png = dest.read_bytes()
    try:
        got = rebar_capture.read(r.company_id, png)
    except Exception as err:  # noqa: BLE001 — 캡처는 남기고 값은 직접
        got = {"warn": [f"캡처를 읽지 못했습니다(값은 직접): {str(err).splitlines()[0][:100]}"]}
    row["captures"][line] = rel
    RV.apply_capture(row, line, got)
    data["rows"][i] = row
    _put(r, data)
    db.commit()
    return _out(db, r) | {"read": {k: got.get(k) for k in ("count", "spacing", "cover", "bar_spacings", "covers", "warn")}}


@router.get("/reports/{report_id}/seismic/rebar/{row_id}/capture/{line}")
def get_capture(report_id: int, row_id: str, line: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    data, i = _row(r, row_id)
    rel = data["rows"][i]["captures"][line] if line in (0, 1) else ""
    p = _report_dir(db.get(SitokFacility, r.facility_id), r) / rel if rel else None
    if p is None or not Path(p).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "캡처가 없습니다.")
    return FileResponse(p, media_type="image/png")


VENDOR_KEYS = {"body": ("외주 3~7장 한글", (".hwp", ".hwpx"))}  # 다음 단계: 결과표·체크리스트 한글, GEN 부록·내역서·지반조사보고서 PDF


@router.post("/reports/{report_id}/seismic/files/{key}")
def upload_vendor(report_id: int, key: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """외주 결과물 올리기 — body = 3~7장 한글(만들 때 우리 1~2장 끝에 한글이 끼워 넣음). 회차 폴더 외주/에 보관, survey.seismic_files."""
    if key not in VENDOR_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "올릴 수 있는 것: " + ", ".join(v[0] for v in VENDOR_KEYS.values()))
    label, exts = VENDOR_KEYS[key]
    name = file.filename or "외주.hwp"
    ext = Path(name).suffix.lower()
    if ext not in exts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label}은(는) {'·'.join(exts)} 파일로 올려 주세요.")
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    dest = _report_dir(f, r) / "외주" / f"{Path(name).stem[:60]}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file.file.read())
    files = dict((r.survey or {}).get("seismic_files") or {})
    files[key] = str(dest)
    r.survey = {**(r.survey or {}), "seismic_files": files}
    db.commit()
    return {"ok": True, "files": {k: Path(str(v)).name for k, v in files.items() if v}}


@router.get("/reports/{report_id}/seismic/rebar.xlsx")
def rebar_xlsx(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    data = _rebar(r)
    if not data["rows"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "철근탐사 줄이 없습니다.")
    body = RV.xlsx(data["rows"], f"{f.name} 철근배근 상태조사")
    from urllib.parse import quote

    name = quote(f"{f.name}_철근배근 상태조사.xlsx")
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})
