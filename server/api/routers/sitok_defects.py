"""시특법 현장 결함 조사(2026-10-10 5단계) — 현장 폰 화면(sitok-field.html?report=)과 결함 표(SitokDefect).

- `GET  /sitok/reports/{id}/defects` — 그 회차 결함 전부(층·번호 순) + 요약.
- `POST /sitok/reports/{id}/defects/import` — 지난 보고서 PDF(외관조사 사진첩이 든 것)에서 전회차 결함·사진 가져오기(server/sitok/album_read.py).
- `POST /sitok/reports/{id}/defects/carry` — 직전 회차 결함을 전회차로 가져오기(이 시스템으로 만든 회차가 있을 때).
- `POST /sitok/reports/{id}/defects` — 새로 찾은 결함(신규). `PATCH/DELETE /sitok/defects/{id}`, `POST /sitok/defects/{id}/photo`,
  `GET /sitok/defects/{id}/photo/{now|prev}`.
현장 확인(check): same 그대로(비고 기존) · grew 진행(크기 다시, 기존) · repaired 보수 완료(비고 보수, 크기 "-") · new 신규.
물량 자동(인수인계 10/10): 균열류 = 길이 × 개수(m), 면적 결함(누수·백태·박리·박락·철근노출·부식·도장박리 등) = 폭 × 길이 × 개수(㎡, 폭·길이 m).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokDefect, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import base_areas
from server.api.routers.sitok_reports import _order, _report_dir, _require as _require_report
from server.contract_docs import files
from server.sitok import album_read

router = APIRouter(prefix="/sitok", tags=["sitok"])
AREA_WORDS = ("누수", "백태", "백화", "박리", "박락", "철근노출", "부식", "들뜸", "탈락", "파손", "오염")
FIELDS = ("floor", "part", "member", "dtype", "count", "width", "length", "area_ratio", "cause", "progress", "note")
CHECKS = ("", "same", "grew", "repaired", "new")
MARK = {"same": "기존", "grew": "기존", "repaired": "보수", "new": "신규"}
FLOOR_ORDER = ("옥상", "옥탑", "지상", "지하")


def is_area(dtype: str) -> bool:
    return any(w in (dtype or "") for w in AREA_WORDS)


def _num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def calc_qty(dtype: str, count: str, width: str, length: str) -> str:
    n, w, ln = _num(count), _num(width), _num(length)
    if n is None or ln is None:
        return ""
    if is_area(dtype):
        return f"{w * ln * n:.2f}" if w is not None else ""
    return f"{ln * n:.2f}"


SLAB_WORDS = ("슬라브", "슬래브", "보", "바닥", "천장", "천정", "지붕")


def calc_ratio(dtype: str, member: str, count: str, width: str, length: str, bases: tuple[float, float]) -> str:
    """면적률(%) = 결함 면적 ÷ 기준 면적 × 100 — 균열은 길이 × 0.25 × 개수(사용자 10/10), 면적 결함은 폭 × 길이 × 개수.
    기준 면적은 부재가 슬래브·보·바닥·천장이면 슬래브 한 칸, 아니면 벽 한 면(sitok.base_areas)."""
    n, w, ln = _num(count), _num(width), _num(length)
    if n is None or ln is None:
        return ""
    area = (w * ln * n if w is not None else None) if is_area(dtype) else ln * 0.25 * n
    if area is None:
        return ""
    base = bases[1] if any(x in (member or "") for x in SLAB_WORDS) else bases[0]
    return f"{area / base * 100:.1f}".rstrip("0").rstrip(".") if base else ""


def floor_key(floor: str) -> tuple:
    """옥상 → 지상 높은 층 → 지하 깊은 층 순(사진첩 순서)."""
    import re
    m = re.search(r"(\d+)", floor or "")
    k = int(m[1]) if m else 0
    if floor.startswith(("옥상", "옥탑", "지붕")):
        return (0, 0)
    if floor.startswith("지하"):
        return (2, k)
    return (1, -k)


def _photo_dir(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r) / "결함사진"


def _out(d: SitokDefect) -> dict:
    return {"id": d.id, **{k: getattr(d, k) for k in FIELDS}, "seq": d.seq, "qty": d.qty, "mark": d.mark, "check": d.check,
            "prev": d.prev or None, "has_photo": bool(d.photo and Path(d.photo).exists()),
            "has_prev_photo": bool(d.prev_photo and Path(d.prev_photo).exists()), "starred": d.starred,
            "checked_by": d.checked_by, "ts": int(d.checked_at.timestamp()) if d.checked_at else 0}


def _rows(db: Session, report_id: int) -> list[SitokDefect]:
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == report_id).all()
    return sorted(rows, key=lambda d: (floor_key(d.floor), d.floor, d.seq, d.id))


def default_action(dtype: str, width: str) -> str:
    """조치 필요사항 기본 문구 — 6단계 AI 초안 전까지·AI 실패 때(민재형 10/10: 고정 문구는 기본값으로만, 실제는 AI → 점검자 확인).
    견본 9쪽 문구에 맞춤. 균열은 폭 0.3mm 기준 표면처리 / 에폭시주입보수."""
    t = dtype or ""
    if any(w in t for w in ("누수", "백태", "백화")):
        return "마감재 재시공"
    if "철근" in t:
        return "단면복구"
    if "부식" in t:
        return "표면정리 후 재도장"
    if any(w in t for w in ("박리", "박락")):
        return "표면처리"
    if "이격" in t:
        return "탄성실링 보수"
    if any(w in t for w in ("파손", "탈락", "들뜸")):
        return "마감재 재시공"
    if "균열" in t:
        w = _num(width)
        return "에폭시주입보수" if w is not None and w >= 0.3 else "표면처리"
    return "주의관찰"


def summary_rows(db: Session, report_id: int) -> list:
    """9쪽 요약표 줄 [(층, 구분, 부재, [결함유형들], [조치들])] — 보수 완료는 뺌, 층은 위층부터, 안에서는 처음 나온 순."""
    groups: dict = {}
    for d in _rows(db, report_id):
        if d.check == "repaired" or d.mark == "보수" or not d.dtype or d.dtype.rstrip().endswith("현황"):
            continue  # 보수 완료·기록용 사진("실외기 현황" 등)은 결함 아님
        key = (d.floor, d.part or "-", d.member or "-")
        g = groups.setdefault(key, {"types": [], "acts": []})
        if d.dtype.replace(" ", "") not in [x.replace(" ", "") for x in g["types"]]:
            g["types"].append(d.dtype)
            g["acts"].append(default_action(d.dtype, d.width))
    order: list = []  # 층 안에서 구분끼리 모이게
    for key in groups:
        if key not in order:
            same = [k for k in groups if k[:2] == key[:2]]
            order += [k for k in same if k not in order]
    return [(k[0], k[1], k[2], groups[k]["types"], groups[k]["acts"]) for k in order]


def album_floors(db: Session, report_id: int) -> list[tuple[str, list[dict]]]:
    """사진첩용 층별 줄(server/sitok/album_make.py) — 번호 순, 사진번호는 층마다 1부터, 보수 완료는 "보수완료"·크기 "-"."""
    out: list[tuple[str, list[dict]]] = []
    for d in _rows(db, report_id):
        if not out or out[-1][0] != d.floor:
            out.append((d.floor, []))
        rows = out[-1][1]
        rep = d.check == "repaired" or d.mark == "보수"
        rows.append({"번호": str(d.seq), "구분": d.part, "부재": d.member, "결함유형": "보수완료" if rep else d.dtype,
                     "개수": "-" if rep else d.count, "폭": "-" if rep else d.width, "길이": "-" if rep else d.length,
                     "물량": "-" if rep else d.qty, "면적률": "-" if rep else d.area_ratio, "결함원인": "-" if rep else d.cause,
                     "진행유무": "-" if rep else d.progress, "비고": d.mark, "사진번호": f"사진{len(rows) + 1}",
                     "_photo": d.photo if d.photo and Path(d.photo).exists() else d.prev_photo,
                     # 전회차 비교 사진대장(album_make.compare_pages)용
                     "_now_photo": d.photo if d.photo and Path(d.photo).exists() else "", "_prev_photo": d.prev_photo,
                     "_prev": d.prev or {}, "_check": d.check, "_compare": bool(d.prev) and not (d.dtype or "").rstrip().endswith("현황")
                     and (d.part == "구조체" or d.check == "grew" or d.starred)})
    return out


@router.get("/reports/{report_id}/defects")
def list_defects(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    rows = _rows(db, r.id)
    return {"report": {"id": r.id, "year": r.year, "half": r.half, "facility": f.name, "facility_id": f.id},
            "defects": [_out(d) for d in rows],
            "summary": {"total": len(rows), "unchecked": sum(1 for d in rows if not d.check),
                        **{k: sum(1 for d in rows if d.check == k) for k in CHECKS if k}}}


def _require_empty(db: Session, r: SitokReport) -> None:
    if db.query(SitokDefect).filter(SitokDefect.report_id == r.id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 결함 목록이 있습니다 — 다시 가져오려면 목록을 먼저 비우세요.")


@router.post("/reports/{report_id}/defects/import")
def import_pdf(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    _require_empty(db, r)
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지난 보고서 PDF(외관조사 사진첩이 든 것)를 올려 주세요.")
    album = album_read.read(data)
    if not album.rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF에서 '[○○층 결함 현황표]'를 찾지 못했습니다 — 외관조사 사진첩이 든 PDF인지 확인하세요.")
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    for row in album.rows:
        v = row.values
        d = SitokDefect(report_id=r.id, floor=row.floor, seq=row.seq, part=v["구분"], member=v["부재"], dtype=v["결함유형"],
                        count=v["개수"], width=v["폭"], length=v["길이"], qty=v["물량"], area_ratio=v["면적률"], cause=v["결함원인"],
                        progress=v["진행유무"], mark=v["비고"], prev=dict(v))
        if row.photo_png:
            p = folder / f"{row.floor}_{row.seq:02d}_전회차.jpg"
            p.write_bytes(row.photo_png)
            d.prev_photo = str(p)
        db.add(d)
    db.commit()
    return list_defects(report_id, user, db)


@router.post("/reports/{report_id}/defects/carry")
def carry(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    _require_empty(db, r)
    older = [x for x in db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id)
             if _order(x) < _order(r) and db.query(SitokDefect).filter(SitokDefect.report_id == x.id).first()]
    if not older:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "결함 목록이 있는 지난 회차가 없습니다 — 지난 보고서 PDF에서 가져오세요.")
    prev = max(older, key=_order)
    for x in _rows(db, prev.id):
        if x.check == "repaired":
            continue  # 보수 완료된 것은 다음 회차엔 안 가져감
        vals = {"번호": str(x.seq), "구분": x.part, "부재": x.member, "결함유형": x.dtype, "개수": x.count, "폭": x.width, "길이": x.length,
                "물량": x.qty, "면적률": x.area_ratio, "결함원인": x.cause, "진행유무": x.progress, "비고": x.mark}
        db.add(SitokDefect(report_id=r.id, floor=x.floor, seq=x.seq, part=x.part, member=x.member, dtype=x.dtype, count=x.count,
                           width=x.width, length=x.length, qty=x.qty, area_ratio=x.area_ratio, cause=x.cause, progress=x.progress,
                           mark="기존", prev=vals, prev_photo=x.photo or x.prev_photo))
    db.commit()
    return list_defects(report_id, user, db)


@router.delete("/reports/{report_id}/defects")
def clear(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """목록 비우기(다시 가져오기 전) — 이미 현장에서 확인한 줄이 있으면 막음."""
    r = _require_report(db, user, report_id)
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id).all()
    if any(d.check for d in rows):
        raise HTTPException(status.HTTP_409_CONFLICT, "현장에서 확인한 결함이 있어 비울 수 없습니다.")
    for d in rows:
        db.delete(d)
    db.commit()
    return {"ok": True}


class DefectIn(BaseModel):
    floor: str | None = None
    part: str | None = None
    member: str | None = None
    dtype: str | None = None
    count: str | None = None
    width: str | None = None
    length: str | None = None
    area_ratio: str | None = None
    cause: str | None = None
    progress: str | None = None
    note: str | None = None
    check: str | None = None
    starred: bool | None = None


def _require(db: Session, user: User, defect_id: int) -> tuple[SitokDefect, SitokReport]:
    d = db.get(SitokDefect, defect_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "결함을 찾을 수 없습니다.")
    return d, _require_report(db, user, d.report_id)


def _apply(d: SitokDefect, body: DefectIn, user: User, bases: tuple[float, float] | None = None) -> None:
    data = body.model_dump(exclude_unset=True)
    if "check" in data and data["check"] not in CHECKS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "확인 값이 올바르지 않습니다.")
    for k, v in data.items():
        setattr(d, k, v.strip() if isinstance(v, str) else v)
    if "check" in data:
        d.mark = MARK.get(d.check, d.mark)
        if d.check == "same" and d.prev:  # 그대로 = 전회차 크기
            d.count, d.width, d.length = d.prev.get("개수", d.count), d.prev.get("폭", d.width), d.prev.get("길이", d.length)
        d.checked_by, d.checked_at = user.display_name or "", datetime.datetime.now()
    if d.check == "repaired":
        d.count = d.width = d.length = d.qty = d.area_ratio = ""
    else:
        d.qty = calc_qty(d.dtype, d.count, d.width, d.length) or d.qty
        if bases is not None and d.check in ("grew", "new"):  # 크기를 새로 잰 것만 다시(그대로·전회차 값은 전회차 면적률 유지)
            d.area_ratio = calc_ratio(d.dtype, d.member, d.count, d.width, d.length, bases) or d.area_ratio


@router.post("/reports/{report_id}/defects")
def add_defect(report_id: int, body: DefectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    if not (body.floor or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "층을 고르세요.")
    last = max((d.seq for d in db.query(SitokDefect).filter(SitokDefect.report_id == r.id, SitokDefect.floor == body.floor.strip())), default=0)
    d = SitokDefect(report_id=r.id, seq=last + 1, check="new", mark="신규")
    _apply(d, body.model_copy(update={"check": "new"}), user, base_areas(db.get(SitokFacility, r.facility_id)))
    db.add(d)
    db.commit()
    return _out(d)


@router.patch("/defects/{defect_id}")
def update_defect(defect_id: int, body: DefectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, r = _require(db, user, defect_id)
    _apply(d, body, user, base_areas(db.get(SitokFacility, r.facility_id)))
    db.commit()
    return _out(d)


@router.delete("/defects/{defect_id}")
def delete_defect(defect_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, _ = _require(db, user, defect_id)
    if d.photo:
        Path(d.photo).unlink(missing_ok=True)
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.post("/defects/{defect_id}/photo")
def upload_photo(defect_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, r = _require(db, user, defect_id)
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{d.floor}_{d.seq:02d}_금회.jpg"
    p.write_bytes(files.to_jpeg(file.file.read(), file.filename or ""))
    d.photo = str(p)
    d.checked_at = datetime.datetime.now()
    db.commit()
    return _out(d)


@router.get("/defects/{defect_id}/photo/{which}")
def photo(defect_id: int, which: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, _ = _require(db, user, defect_id)
    path = d.photo if which == "now" else d.prev_photo
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(path, media_type="image/jpeg")
