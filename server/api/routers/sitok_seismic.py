"""내진성능평가 현장시험(2026-10-21 형 "내진성능평가로 새로 항목 만들기") — 성능평가 회차(반기 칸·종류 "성능평가")의 철근탐사.
(부재규격·코어·조적은 다음 단계에 같은 화면으로.)

- `GET   /sitok/reports/{id}/seismic` — 철근탐사 줄 + 일람표 칸(고르기용) + 층 + 필요 수량
- `PATCH /sitok/reports/{id}/seismic/rebar` {rows} — 줄 저장(설계값은 일람표에서 자동, 사람이 고친 줄은 그대로)
- `POST  /sitok/reports/{id}/seismic/rebar/{row}/capture/{line}` — 탐사기 화면 캡처 → 조사값·피복(server/sitok/rebar_capture, AI 약 10원)
- `GET   /sitok/reports/{id}/seismic/rebar/{row}/capture/{line}` — 올린 캡처, `DELETE` — 캡처 지우기(10/22, 읽어 넣은 값은 그대로)
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
from server.sitok import seismic_docs as SD

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
                                    "at": {str(n): RS.marks_at(x, n) for n in floors + [RS.FLOOR_TOP]},  # 층마다 그 층 부호(10/28 — 1-5G1A는 1층 "1G1A", 그 층이 아니면 빈 목록)
                                    "position": x.get("position") or "", "confirmed": x["confirmed"], "check_ok": x["check"]["ok"]} for x in sv["items"]]},
            "lines": RV.LINES, "kinds": list(RV.KINDS), "seeded": data["seeded"], "rows": rows,
            "counts": RV.counts(data["rows"], SD.sample_floors(f, "rebar"))}  # 표본 층 × 4종(10/22, 철근배근 조사단위)


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
    cur = _rebar(r)
    old = {x["id"]: x for x in cur["rows"]}
    data = RV.normalize({"rows": body.rows, "seeded": cur["seeded"]})
    for row in data["rows"]:
        prev = old.get(row["id"])
        row["captures"] = prev["captures"] if prev else ["", ""]  # 캡처 파일 이름은 서버만 정함
        RV.fill_design(row, sch)
    _put(r, data)
    db.commit()
    return _out(db, r)


class PlanIn(BaseModel):
    plan: dict | None = None
    default: bool = False


@router.post("/reports/{report_id}/seismic/rebar/plan")
def rebar_plan(report_id: int, body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """칸 수대로 줄 맞추기(10/22 형 "표본층 종별마다 칸 생성, 수량 조정") — default(또는 plan 없음)면 표본 층 × 4종 × 3. 쓴 줄은 안 지움."""
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    plan = RV.default_plan(SD.sample_floors(f, "rebar")) if body.default or not body.plan else body.plan
    _put(r, {"rows": RV.apply_plan(_rebar(r)["rows"], plan), "seeded": True})
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


@router.delete("/reports/{report_id}/seismic/rebar/{row_id}/capture/{line}")
def delete_capture(report_id: int, row_id: str, line: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """캡처 지우기(10/22 사용자 "사진 넣고 넣은 거 삭제 가능하도록") — 파일과 그 줄 캡처 알림만, 읽어 넣은 조사값·피복은 그대로(직접 고치거나 다시 올리면 덮음)."""
    if line not in (0, 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "줄은 0 또는 1입니다.")
    r = _require(db, user, report_id)
    data, i = _row(r, row_id)
    row = data["rows"][i]
    rel = row["captures"][line]
    if rel:
        base = _report_dir(db.get(SitokFacility, r.facility_id), r)
        p = (base / rel).resolve()
        if base.resolve() in p.parents:
            p.unlink(missing_ok=True)
    row["captures"][line] = ""
    head = f"{RV.LINES[row['kind']][line]}: "
    row["warn"] = [w for w in row.get("warn") or [] if not w.startswith(head)]
    data["rows"][i] = row
    _put(r, data)
    db.commit()
    return _out(db, r)


@router.post("/reports/{report_id}/seismic/rebar/{row_id}/clear")
def clear_row(report_id: int, row_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """카드 비우기(10/26 민재형 "전체 수량은 수량표에서만" — 카드 지우기 대신) — 층·부재·자리(RC 번호)는 그대로, 일람표 칸·설계·조사값·피복·실측불가·캡처(파일도)·비고를 지움."""
    r = _require(db, user, report_id)
    data, i = _row(r, row_id)
    row = data["rows"][i]
    base = _report_dir(db.get(SitokFacility, r.facility_id), r)
    for rel in row["captures"]:
        p = (base / rel).resolve() if rel else None
        if p is not None and base.resolve() in p.parents:
            p.unlink(missing_ok=True)
    data["rows"][i] = RV.norm_row({"id": row["id"], "kind": row["kind"], "floor": row["floor"]}, row["no"])
    _put(r, data)
    db.commit()
    return _out(db, r)


VENDOR_KEYS = {"body": ("외주 결과물 한글", (".hwp", ".hwpx"))}  # 3~7장만 또는 견본 전체(seismic_vendor가 가려 씀) — 다음: GEN 부록·내역서·지반조사보고서 PDF


@router.post("/reports/{report_id}/seismic/files/{key}")
def upload_vendor(report_id: int, key: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """외주 결과물 올리기 — body = 외주 한글(3~7장만 또는 우리 견본 전체에 외주 몫까지 쓴 것 — 만들 때 server/sitok/seismic_vendor가 가려
    앞 외주 몫은 옮기고 3~7장은 한글이 끼워 넣음, 값 검토). 회차 폴더 외주/에 보관, survey.seismic_files. 올리면 어떤 파일인지 바로 알려 줌."""
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
    return {"ok": True, "files": {k: Path(str(v)).name for k, v in files.items() if v}, "kind": _vendor_kind(dest)}


def _vendor_kind(path: Path) -> str:
    """올린 외주 한글이 어떤 것인지 한 줄(.hwpx만 바로 — .hwp는 만들 때 한글로 바꿔 봄)."""
    from server.sitok import seismic_vendor as SV
    from server.sitok.wall_build import Hwpx

    if path.suffix.lower() != ".hwpx":
        return "올렸습니다(.hwp — 보고서 만들 때 3~7장만인지 견본 전체인지 살펴 씁니다)."
    try:
        info = SV.analyze(Hwpx(path))
    except Exception:  # noqa: BLE001
        return "올렸지만 한글 내용을 읽지 못했습니다 — 파일을 확인해 주세요."
    if info["full"]:
        return "견본 전체 모양입니다 — 결과표 나~마·확인서·체크리스트를 옮기고 3~7장을 끼워 넣습니다."
    if info["chapter3"] is not None:
        return "3~7장만 있는 파일입니다 — 3~7장을 끼워 넣습니다(결과표 나~마·체크리스트는 견본 값)."
    return "\"제3장\"을 못 찾았습니다 — 외주 결과물이 맞는지 확인해 주세요."


@router.get("/reports/{report_id}/seismic/rebar.xlsx")
def rebar_xlsx(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    data = _rebar(r)
    if not data["rows"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "철근탐사 줄이 없습니다.")
    body = RV.xlsx(RV.report_rows(data["rows"]), f"{f.name} 철근배근 상태조사")  # 결과 있는 줄만(빈 칸 뺌)
    from urllib.parse import quote

    name = quote(f"{f.name}_철근배근 상태조사.xlsx")
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})
