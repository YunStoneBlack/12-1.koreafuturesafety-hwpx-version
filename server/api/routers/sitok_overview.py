"""시특법 회차 전경사진(2026-10-11, alembic 0032 sitok_report.overview) — 현장 화면 [🏢 전경사진] 탭.

장수 제한 없이 찍고(인수인계 10/10) 보고서 10쪽 위치도 아래 = 첫 장, 11쪽 = 한 쪽 6장씩(모자란 칸은 흰 그림·"-").
사진 제목: 폰 키보드 🎤 음성·타이핑·지난 회차 제목 고르기 / [🏷 실명판] 찍으면 AI가 실 이름을 읽어 넣기(실명판 사진은 저장 안 함) /
제목 없이 넘어간 사진은 [🤖 제목 추천] — AI가 사진 보고 "○○ 전경사진"(ai=True로 표시, 점검자가 고치면 풀림).

- `GET    /sitok/reports/{id}/overview` — 사진 목록 + 지난 회차 제목(고르기용).
- `POST   /sitok/reports/{id}/overview` — 사진 올리기(여러 장 = 여러 번).
- `PATCH  /sitok/reports/{id}/overview/{pid}` — 제목 / 순서(move -1·+1). `DELETE` 같은 주소.
- `GET    /sitok/reports/{id}/overview/{pid}/photo`.
- `POST   /sitok/reports/{id}/overview/nameplate` — 실명판 사진 → {"title"}.
- `POST   /sitok/reports/{id}/overview/suggest` — 제목 빈 사진마다 AI 추천.
"""

from __future__ import annotations

import re
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from lxml import etree
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_reports import _previous, _report_dir, _require
from server.contract_docs import files
from server.sitok import report_build as rb

router = APIRouter(prefix="/sitok", tags=["sitok"])
DIR = "전경사진"


def _dir(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r)


def photos(db: Session, r: SitokReport) -> list[tuple[str, str]]:
    """보고서 만들 때 — [(사진 경로, 제목)] 순서대로, 파일 있는 것만."""
    base = _dir(db, r)
    return [(str(base / p["file"]), p.get("title") or "") for p in (r.overview or []) if (base / p["file"]).exists()]


def _titles_from_hwpx(path: str) -> list[str]:
    """지난 보고서 11쪽 전경 표의 【제목】들."""
    if not path or not Path(path).exists():
        return []
    try:
        with zipfile.ZipFile(path) as z:
            root = etree.fromstring(z.read(rb._sections(z)[0]))
    except Exception:  # noqa: BLE001 — 제목 목록은 없어도 됨
        return []
    out = []
    for tbl in root.iter(f"{{{rb.HP}}}tbl"):
        cells = rb._cells(tbl)
        if "전경사진" not in rb._cell_text(cells.get((0, 0), tbl)):
            continue
        for (r, _), tc in sorted(cells.items()):
            m = re.fullmatch(r"\s*【\s*(.+?)\s*】\s*", rb._cell_text(tc)) if r else None
            if m and m[1] not in out:
                out.append(m[1])
    return out


WALL_TITLES = ["시점측 전경", "종점측 전경", "시점측 상부 전경", "전면부 전경", "소단 전경", "배수시설 전경"]  # 옹벽 견본 1.2.3 전경 6장(10/20)
BRIDGE_TITLES = ["교량 전경", "교량 측면 전경", "교면 전경", "하부구조 전경", "시점부 전경", "종점부 전경"]  # 교량 1.2.3 전경 6장(10/29)


def _out(db: Session, r: SitokReport) -> dict:
    from core.models_web import SitokFacility
    from server.sitok import kinds

    prev = _previous(db, r)
    fac = db.get(SitokFacility, r.facility_id)
    wall = kinds.is_civil(fac)  # 옹벽·교량(10/29)
    titles = [p.get("title") for p in (prev.overview or []) if p.get("title")] if prev and prev.overview else []
    titles += [t for t in _titles_from_hwpx(r.source_hwpx) if t not in titles]
    if wall:
        titles += [t for t in (BRIDGE_TITLES if kinds.is_bridge(fac) else WALL_TITLES) if t not in titles]
    base = _dir(db, r)
    return {"photos": [{"id": p["id"], "title": p.get("title") or "", "ai": bool(p.get("ai")), "main": bool(p.get("main")), "has_now": bool(p.get("file") and (base / p["file"]).exists()),
                        "has_prev": bool(p.get("prev_file") and (base / p["prev_file"]).exists())} for p in (r.overview or [])],
            "titles": titles, "wall": wall}


@router.post("/reports/{report_id}/overview/{pid}/photo")
def add_now_photo(report_id: int, pid: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """전회차 사진(가져온 것) 칸에 이번 사진 찍기(옹벽 10/21 민재형 요청1) — 같은 줄의 file을 채움(prev_file은 둠)."""
    r = _require(db, user, report_id)
    rows = [dict(p) for p in (r.overview or [])]
    i = next((k for k, p in enumerate(rows) if p["id"] == pid), None)
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    if rows[i].get("file"):
        (_dir(db, r) / rows[i]["file"]).unlink(missing_ok=True)
    files.save_jpeg(file.file.read(), file.filename or "", _dir(db, r) / DIR / f"{pid}_now.jpg")
    rows[i]["file"] = f"{DIR}/{pid}_now.jpg"
    r.overview = rows
    db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/overview")
def get_overview(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _require(db, user, report_id))


@router.post("/reports/{report_id}/overview")
def add_photo(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    pid = uuid.uuid4().hex[:10]
    files.save_jpeg(file.file.read(), file.filename or "", _dir(db, r) / DIR / f"{pid}.jpg")
    r.overview = [*(r.overview or []), {"id": pid, "file": f"{DIR}/{pid}.jpg", "title": "", "ai": False}]
    db.commit()
    return _out(db, r)


class PhotoIn(BaseModel):
    title: str | None = None
    move: int = 0
    first: bool = False  # ★ 대표 — 맨 앞으로(표지·위치도 아래·상태평가가 첫 장을 씀, 10/23 형 "점검자가 고른 전경사진이 메인으로")


@router.patch("/reports/{report_id}/overview/{pid}")
def patch_photo(report_id: int, pid: str, body: PhotoIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    rows = [dict(p) for p in (r.overview or [])]
    i = next((k for k, p in enumerate(rows) if p["id"] == pid), None)
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    if body.title is not None:
        rows[i]["title"], rows[i]["ai"] = body.title.strip().strip("【】").strip(), False
    j = i + (1 if body.move > 0 else -1 if body.move < 0 else 0)
    if 0 <= j < len(rows) and j != i:
        rows[i], rows[j] = rows[j], rows[i]
    if body.first and i:
        rows.insert(0, rows.pop(i))
    if body.first or (body.move and 0 in (i, j)):  # 첫 장을 사람이 정함 — 보고서 만들 때 "대표 안 골랐음" 안내 안 띄움
        for k, row in enumerate(rows):
            row["main"] = k == 0
    r.overview = rows
    db.commit()
    return _out(db, r)


@router.delete("/reports/{report_id}/overview/{pid}")
def delete_photo(report_id: int, pid: str, which: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """줄 지우기. which=now면 전회차 사진이 있는 줄에서 이번 사진만 지움(옹벽)."""
    r = _require(db, user, report_id)
    rows = [dict(p) for p in (r.overview or [])]
    for p in rows:
        if p["id"] == pid:
            if p.get("file"):
                (_dir(db, r) / p["file"]).unlink(missing_ok=True)
            if which == "now" and p.get("prev_file"):
                p["file"] = ""
            elif p.get("prev_file"):
                (_dir(db, r) / p["prev_file"]).unlink(missing_ok=True)
    r.overview = [p for p in rows if p["id"] != pid or (which == "now" and p.get("prev_file"))]
    db.commit()
    return _out(db, r)


@router.get("/reports/{report_id}/overview/{pid}/photo")
def photo(report_id: int, pid: str, which: str = "now", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    p = next((x for x in r.overview or [] if x["id"] == pid), None)
    f = (p.get("prev_file") if which == "prev" else p.get("file")) if p else None
    path = _dir(db, r) / f if f else None
    if path is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(path, media_type="image/jpeg")


def _ask(company_id: int, jpg: bytes, prompt: str) -> str:
    """사진 한 장 + 질문 → 짧은 답(마지막 줄)."""
    from server.sitok import vision

    text = vision.ask(company_id, [jpg], prompt, max_tokens=4000)
    return text.splitlines()[-1].strip().strip('"“”【】 ') if text else ""


NAMEPLATE = """이 사진은 건물 안 실(방) 출입문 옆의 실명판입니다. 실 이름만 한 줄로 답하세요(설명 없이).
층이 같이 적혀 있으면 "3층 돌봄교실"처럼 앞에 붙이고, 영문·호실 번호만 있으면 그대로. 읽을 수 없으면 "?"."""
SUGGEST = """이 사진은 시설물 정기안전점검 보고서의 전경사진입니다. 보고서 사진 제목을 한 줄로만 답하세요(설명 없이).
형식: "○○ 전경사진"(예: 교사동 전경사진, 옥상 전경사진, 지하주차장 전경사진, 계단실 전경사진, 기계실 전경사진, 교실 전경사진).
참고로 이 시설의 지난 회차 제목들: {titles}"""


@router.post("/reports/{report_id}/overview/nameplate")
def nameplate(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require(db, user, report_id)
    try:
        name = _ask(user.company_id, files.to_jpeg(file.file.read(), file.filename or ""), NAMEPLATE)
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"실명판을 읽지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    if not name or name == "?":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "실명판 글자를 읽지 못했습니다 — 가까이에서 다시 찍거나 직접 적어 주세요.")
    return {"title": name if name.endswith("전경사진") else f"{name} 전경사진"}


@router.post("/reports/{report_id}/overview/suggest")
def suggest(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    base = _dir(db, r)
    titles = ", ".join(_out(db, r)["titles"][:30]) or "(없음)"
    rows = [dict(p) for p in (r.overview or [])]
    done = 0
    for p in rows:
        path = base / p["file"]
        if p.get("title") or not path.exists():
            continue
        try:
            t = _ask(user.company_id, path.read_bytes(), SUGGEST.format(titles=titles))
        except Exception as err:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"제목을 추천하지 못했습니다: {str(err).splitlines()[0][:150]}") from err
        if t:
            p["title"], p["ai"] = t, True
            done += 1
    r.overview = rows
    db.commit()
    return {**_out(db, r), "done": done}
