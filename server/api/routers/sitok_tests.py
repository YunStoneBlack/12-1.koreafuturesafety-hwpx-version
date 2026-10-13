"""시특법 정밀안전점검 재료시험(2026-10-13 밤, ② 단계) — 회차 하나의 표본층·부재 규격·강도·탄산화·기울기·부등침하.

- `GET /sitok/reports/{id}/tests` — 입력 + 계산값(server/sitok/tests.compute) + 시설물(층수·연면적·준공일).
- `PATCH /sitok/reports/{id}/tests` — 입력 통째로 저장(정리해서) → 계산값 돌려줌.
- `POST /sitok/reports/{id}/tests/schmidt` — 슈미트 시험성과표 xlsx → 강도 줄(server/sitok/schmidt.read), 파일은 회차 폴더에 보관.
화면 sitok-tests.html(js/sitok-tests.js). 정밀 회차 카드의 [📐 재료시험]."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _report_dir, _require
from server.sitok import schmidt, tests

router = APIRouter(prefix="/sitok", tags=["sitok-tests"])


class TestsIn(BaseModel):
    tests: dict


def _view(db: Session, r: SitokReport) -> dict:
    f = db.get(SitokFacility, r.facility_id)
    v = tests.compute(r.tests, above=f.floors_above or 0, below=f.floors_below or 0, area=f.total_area or 0,
                      kind="정밀안전진단" if "진단" in (r.kind or "") else "정밀안전점검", completion=f.completion_date, when=r.period_start or r.report_date)
    v["report"] = {"id": r.id, "year": r.year, "half": r.half, "kind": r.kind or "정기", "facility_id": f.id, "facility_name": f.name, "structure": f.structure}
    v["input"] = tests.normalize(r.tests)
    return v


@router.get("/reports/{report_id}/tests")
def get_tests(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    return _view(db, r)


@router.patch("/reports/{report_id}/tests")
def save_tests(report_id: int, body: TestsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    data = tests.normalize(body.tests)
    if not data["strength"]["rows"] and data["sample"]["floors"] and not (r.tests or {}).get("strength", {}).get("rows"):
        data["strength"]["rows"] = tests.default_strength_rows(data["sample"]["floors"])  # 표본층을 처음 고르면 강도 기본 줄
    r.tests = data
    db.commit()
    return _view(db, r)


@router.post("/reports/{report_id}/tests/schmidt")
def upload_schmidt(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """슈미트 시험성과표 xlsx → 강도 줄 채우기(위치·보정반발경도·재료학회·건축학회·추정강도). 층·부재부위·설계강도는 남겨 둠."""
    name = file.filename or "강도측정결과.xlsx"
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "슈미트 시험성과표 엑셀(.xlsx)을 올려 주세요.")
    r = _require(db, user, report_id)
    data = file.file.read()
    try:
        spots = schmidt.read(data)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"시험성과표를 읽지 못했습니다: {str(err)[:150]}") from err
    f = db.get(SitokFacility, r.facility_id)
    dest = _report_dir(f, r) / "재료시험" / "슈미트_시험성과표.xlsx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    cur = tests.normalize(r.tests)
    cur["strength"]["rows"] = tests.spots_to_rows(spots, cur["sample"]["floors"], cur["strength"]["rows"])
    cur["strength"]["file"] = name
    r.tests = cur
    db.commit()
    return _view(db, r) | {"read": len(spots)}


@router.delete("/reports/{report_id}/tests/schmidt")
def delete_schmidt(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """올린 성과표 빼기(강도 값은 비우고 줄은 남김)."""
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    shutil.rmtree(_report_dir(f, r) / "재료시험", ignore_errors=True)
    cur = tests.normalize(r.tests)
    for row in cur["strength"]["rows"]:
        row.update({"position": "", "r0": None, "fc_mat": None, "fc_arch": None, "est": None})
    cur["strength"]["file"] = ""
    r.tests = cur
    db.commit()
    return _view(db, r)
