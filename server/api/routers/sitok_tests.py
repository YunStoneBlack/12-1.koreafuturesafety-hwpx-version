"""시특법 정밀안전점검 재료시험(2026-10-13 밤, ② 단계) — 회차 하나의 표본층·부재 규격·강도·탄산화·기울기·부등침하.

- `GET /sitok/reports/{id}/tests` — 입력 + 계산값(server/sitok/tests.compute) + 시설물(층수·연면적·준공일).
- `PATCH /sitok/reports/{id}/tests` — 입력 통째로 저장(정리해서) → 계산값 돌려줌.
- `POST /sitok/reports/{id}/tests/schmidt` — 슈미트 시험성과표 xlsx → 강도 줄(server/sitok/schmidt.read), 파일은 회차 폴더에 보관.
- `POST /sitok/reports/{id}/tests/schedule` — 시설물 도면 "구조 일람표"(schedule)를 AI가 읽어 빈 설계도면 칸 채우기(10/14 형 피드백).
- `POST/GET/DELETE /sitok/reports/{id}/tests/carb-photo/{i}` — 탄산화 줄 i의 사진(회차 폴더 재료시험/탄산화_*.jpg) → 부록 3-1 탄산화 사진현황 PDF(server/sitok/carb_photos.py, 10/14).
GET·PATCH 모두 tests.sync_defaults — 표본층에 맞춰 기본 줄(값 있는 줄은 그대로).
화면 sitok-tests.html(js/sitok-tests.js). 정밀 회차 카드의 [📐 재료시험]."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import _facility_dir
from server.api.routers.sitok_reports import _report_dir, _require
from server.sitok import drawings as D
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
    data = tests.normalize(r.tests)
    if tests.sync_defaults(data):  # 표본층은 골랐는데 기본 줄이 없던 회차(10/14 전)도 열면 채워짐
        r.tests = data
        db.commit()
    return _view(db, r)


@router.patch("/reports/{report_id}/tests")
def save_tests(report_id: int, body: TestsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    data = tests.normalize(body.tests)
    tests.sync_defaults(data)  # 표본층에 맞춰 기본 줄(모자란 것만)
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


@router.post("/reports/{report_id}/tests/schedule")
def fill_from_schedule(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """시설물 도면 "구조 일람표" → AI가 표본층·부재별 설계 치수를 읽어 빈 설계도면 칸만 채움(위치 칸이 비면 부재 기호)."""
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    paths = [it["path"] for it in D.items(f, "schedule", _facility_dir(f))]
    if not paths:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "구조 일람표 도면이 없습니다 — 🏢 시설물 현황 창의 도면 칸에 올리세요.")
    cur = tests.normalize(r.tests)
    tests.sync_defaults(cur)
    if not any(not x["design"] and x["member"] for x in cur["sections"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 설계도면 칸이 없습니다(표본층을 먼저 고르거나, 지우고 싶은 칸을 비우세요).")
    text, imgs = D.for_ai(paths, max_pages=6)
    try:
        n = tests.schedule_fill(cur, f.name, r.company_id, text, imgs)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"일람표를 읽지 못했습니다: {str(err)[:150]}") from err
    r.tests = cur
    db.commit()
    return _view(db, r) | {"filled": n}


@router.delete("/reports/{report_id}/tests/schmidt")
def delete_schmidt(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """올린 성과표 빼기(강도 값은 비우고 줄은 남김)."""
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    (_report_dir(f, r) / "재료시험" / "슈미트_시험성과표.xlsx").unlink(missing_ok=True)  # 탄산화 사진이 같은 폴더라 xlsx만(10/14)
    cur = tests.normalize(r.tests)
    for row in cur["strength"]["rows"]:
        row.update({"position": "", "r0": None, "fc_mat": None, "fc_arch": None, "est": None})
    cur["strength"]["file"] = ""
    r.tests = cur
    db.commit()
    return _view(db, r)


# ---- 탄산화 사진(10/14) — 부록 3-1 탄산화 사진현황 ----

def _carb_row(r: SitokReport, i: int) -> tuple[dict, dict]:
    cur = tests.normalize(r.tests)
    rows = cur["carbonation"]["rows"]
    if i < 0 or i >= len(rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "그 탄산화 줄이 없습니다.")
    return cur, rows[i]


@router.post("/reports/{report_id}/tests/carb-photo/{i}")
def upload_carb_photo(report_id: int, i: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """탄산화 줄 i 사진 올리기(바꾸면 전 사진은 지움). JPG로 줄여 저장(server/contract_docs/files.save_jpeg)."""
    from server.contract_docs import files

    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    cur, row = _carb_row(r, i)
    folder = _report_dir(f, r) / "재료시험"
    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "사진이 비었습니다.")
    name = f"탄산화_{uuid.uuid4().hex[:8]}.jpg"
    try:
        files.save_jpeg(data, file.filename or name, folder / name)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"사진을 읽지 못했습니다: {str(err)[:100]}") from err
    if row.get("photo"):
        (folder / row["photo"]).unlink(missing_ok=True)
    row["photo"] = name
    r.tests = cur
    db.commit()
    return _view(db, r)


@router.get("/reports/{report_id}/tests/carb-photo/{i}")
def carb_photo(report_id: int, i: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    _, row = _carb_row(r, i)
    p = _report_dir(f, r) / "재료시험" / (row.get("photo") or "없음")
    if not row.get("photo") or not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(p, media_type="image/jpeg", content_disposition_type="inline", filename=f"탄산화 C{i + 1}.jpg")


@router.delete("/reports/{report_id}/tests/carb-photo/{i}")
def delete_carb_photo(report_id: int, i: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    cur, row = _carb_row(r, i)
    if row.get("photo"):
        (_report_dir(f, r) / "재료시험" / row["photo"]).unlink(missing_ok=True)
    row["photo"] = ""
    r.tests = cur
    db.commit()
    return _view(db, r)


def carb_photo_pdf(db: Session, r: SitokReport, f: SitokFacility, dest):
    """부록 3-1 탄산화 사진현황 PDF — 사진 있는 줄만, 없으면 None(sitok_reports._precision_appendix_pdf가 부름)."""
    from server.sitok import carb_photos

    folder = _report_dir(f, r) / "재료시험"
    cur = tests.normalize(r.tests)
    rows = [{"label": f"C{i + 1}", "photo": folder / x["photo"], "depth": x["depth"], "cover": x["cover"]} for i, x in enumerate(cur["carbonation"]["rows"]) if x.get("photo")]
    return carb_photos.make_pdf(dest, f.name, rows)
