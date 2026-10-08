"""보고서 합본(2026-10-08 사용자 — 완수계에 붙일 기술지도보고서를 직원이 직접 합쳐 올리니 40회차 199MB로 올리기 한도에 걸림).

현장 화면 보고서 목록 [📚 보고서 합본 만들기] → 창(js/report-bundle.js)에서 회차 현황을 보고 [합본 만들기]를 눌러야 만든다(사용자 — 바로 만들지 않음):
- 이 시스템은 현장 중간 회차부터 쓰는 경우가 대부분(15회차 현장에 11회차부터) → 그 전 회차는 직원이 원래 갖고 있던 보고서(대부분 한글 → PDF)를 올린다.
  파일 이름은 믿지 않고(제멋대로 — 사용자) 표준 서식 첫 장 "총 ( 15 )회차 중 ( 4 )회"를 읽어 회차를 정하고, 여러 회차를 합친 파일은 쪽마다 읽어 회차별로 나눈다.
  못 읽은 파일은 창에서 회차를 적는다. 시스템 보고서와 회차가 겹치면 시스템 것(사용자 (가)). 올린 것은 현장 폴더 "예전 보고서\\05회차_원래이름.pdf"에 남겨 다음에도 씀.
- 합본: 회차 순서대로, PDF 없는 시스템 회차·빈 회차는 빠지고 알림, "수정 전 버전"은 있는 PDF 그대로 넣고 알림(사용자 (나)),
  사진만 150dpi(contract_docs/pdf_shrink.py — 글자·표·도장·서명 그대로). 현장 폴더 "26-1)_현장명_보고서합본.pdf",
  이 현장에 연결된 용역 계약이 있으면 완수계 붙임 "기술지도보고서" 칸에 "00_보고서 합본(자동).pdf"(다시 만들면 바뀜, 직접 올린 파일은 그대로).

- `GET  /sites/{id}/report-bundle` — 합본 정보 + 회차 현황(plan)
- `POST /sites/{id}/report-bundle` — 만들기
- `GET  /sites/{id}/report-bundle.pdf[?inline=1]` — 받기·보기
- `POST /sites/{id}/report-bundle/old` (파일 하나[, visit_no]) — 예전 보고서 올리기 → 회차 읽어 저장(창의 회차 칸을 눌러 올리면 visit_no — 그 회차로 통째로)
- `POST /sites/{id}/report-bundle/old/{이름}/visit {visit_no}` — 못 읽은 파일 회차 정하기, `DELETE …/old/{이름}`, `GET …/old/{이름}` 보기
"""
from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_db import Site
from core.models_web import ServiceContract, User
from server.api import repo, storage
from server.api.deps import get_current_user, get_db
from server.api.routers.reports import pdf_outdated_map
from server.contract_docs import attachments, files, pdf_shrink

router = APIRouter(tags=["report-bundle"])
AUTO_NAME = "00_보고서 합본(자동).pdf"  # 완수계 붙임 칸에 넣는 이름(다시 만들면 덮어씀)
OLD_DIR = "예전 보고서"
UNKNOWN = "미확인"
# 표준 서식 "회차  총 (  10  )회차 중 (  4  )회" — 띄어쓰기·괄호 안 공백이 제각각이어도
_VISIT = re.compile(r"총\s*\(?\s*(\d+)\s*\)?\s*회\s*차\s*중\s*\(?\s*(\d+)\s*\)?\s*회")
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _site(db: Session, user: User, site_id: int) -> Site:
    site = repo.get_site(db, user.company_id, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "현장을 찾을 수 없습니다.")
    return site


def bundle_path(db: Session, site: Site) -> Path:
    return storage.site_dir(db, site) / f"{storage.site_folder_name(db, site)}_보고서합본.pdf"


def old_dir(db: Session, site: Site) -> Path:
    return storage.site_dir(db, site) / OLD_DIR


def _pages(path: Path) -> int:
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return 0


def _old_files(db: Session, site: Site) -> tuple[dict[int, Path], list[Path]]:
    """올려 둔 예전 보고서 — ({회차: 파일}, 회차 못 읽은 파일들)."""
    d = old_dir(db, site)
    by_visit: dict[int, Path] = {}
    unknown: list[Path] = []
    if d.exists():
        for p in sorted(d.glob("*.pdf")):
            m = re.match(r"(\d+)회차_", p.name)
            if m:
                by_visit[int(m.group(1))] = p
            elif p.name.startswith(UNKNOWN):
                unknown.append(p)
    return by_visit, unknown


def _title(p: Path) -> str:
    return p.stem.split("_", 1)[-1]


def plan(db: Session, user: User, site: Site) -> dict:
    """창의 회차 현황 — 회차마다 시스템(PDF 있음/없음/수정 전)·올린 예전 보고서·빈 회차."""
    reports = repo.list_reports_for_site(db, user.company_id, site.id)
    outdated = pdf_outdated_map(db, reports) if reports else {}
    system = {r.visit_no: r for r in reports}
    old, unknown = _old_files(db, site)
    last = max([*system, *old, 0])
    rows = []
    for n in range(1, last + 1):
        r = system.get(n)
        has_pdf = bool(r and r.pdf_path and Path(r.pdf_path).exists())
        if has_pdf:
            kind = "outdated" if outdated.get(r.id) else "system"
        elif n in old:
            kind = "old"
        else:
            kind = "nopdf" if r else "missing"
        rows.append({"visit_no": n, "kind": kind, "old": old[n].name if n in old else "", "report_id": r.id if has_pdf else None,
                     "old_title": _title(old[n]) if n in old else "", "old_pages": _pages(old[n]) if n in old else 0,
                     "old_hidden": n in old and has_pdf})  # 겹치면 시스템 것(사용자 (가)) — 올린 쪽은 안 들어감
    first_system = min(system) if system else None
    return {
        "rows": rows, "last": last, "first_system": first_system, "total_visits": site.total_guidance_count,
        "unknown": [{"name": p.name, "title": _title(p.with_name(p.name[len(UNKNOWN) + 1:])), "pages": _pages(p)} for p in unknown],
        "included": [x["visit_no"] for x in rows if x["kind"] in ("system", "outdated", "old")],
    }


def _info(db: Session, site: Site) -> dict:
    path = bundle_path(db, site)
    if not path.exists():
        return {"exists": False}
    st = path.stat()
    return {"exists": True, "pages": _pages(path), "size_mb": round(st.st_size / 1e6, 1),
            "made_at": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")}


@router.get("/sites/{site_id}/report-bundle")
def bundle_info(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _site(db, user, site_id)
    return _info(db, site) | {"plan": plan(db, user, site)}


@router.post("/sites/{site_id}/report-bundle")
def make_bundle(site_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _site(db, user, site_id)
    pl = plan(db, user, site)
    system = {r.visit_no: r for r in repo.list_reports_for_site(db, user.company_id, site.id)}
    old, _ = _old_files(db, site)
    parts: list[Path] = []
    for row in pl["rows"]:
        n = row["visit_no"]
        if row["kind"] in ("system", "outdated"):
            parts.append(Path(system[n].pdf_path))
        elif row["kind"] == "old":
            parts.append(old[n])
    if not parts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "합칠 보고서가 없습니다 — PDF를 만들거나 예전 보고서를 올리세요.")
    out = pymupdf.open()
    raw = 0
    for p in parts:
        raw += p.stat().st_size
        with pymupdf.open(p) as doc:
            out.insert_pdf(doc)
    pdf_shrink.shrink_doc(out)
    dest = bundle_path(db, site)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.pdf")
    out.save(tmp, garbage=3, deflate=True)
    out.close()
    tmp.replace(dest)

    contract = db.query(ServiceContract).filter(ServiceContract.site_id == site.id).first()
    if contract is not None:  # 연결된 계약의 완수계 붙임 "기술지도보고서" 칸에 자동으로
        slot = attachments.slot_dir(files.contract_dir(contract), "done", "report")
        slot.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, slot / AUTO_NAME)
    rows = pl["rows"]
    return _info(db, site) | {
        "plan": pl, "count": len(parts), "raw_mb": round(raw / 1e6, 1),
        "skipped": [x["visit_no"] for x in rows if x["kind"] in ("nopdf", "missing")],
        "outdated": [x["visit_no"] for x in rows if x["kind"] == "outdated"],
        "contract": {"id": contract.id, "title": contract.title} if contract is not None else None,
    }


@router.get("/sites/{site_id}/report-bundle.pdf")
def download_bundle(site_id: int, inline: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _site(db, user, site_id)
    path = bundle_path(db, site)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 만든 보고서 합본이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline" if inline else "attachment")


# ---------- 예전 보고서(이 시스템 전 회차) ----------
def _clean_title(name: str) -> str:
    return _BAD.sub("_", Path(name).stem).strip(" .")[:40] or "보고서"


def split_by_visit(doc: pymupdf.Document) -> list[tuple[int | None, int, int]]:
    """쪽마다 회차 표시를 읽어 [(회차|None, 시작 쪽, 끝 쪽)] — 회차가 바뀌는 쪽에서 나눔. 첫 표시 전 쪽들은 회차 None."""
    chunks: list[list] = []
    for i, page in enumerate(doc):
        m = _VISIT.search(page.get_text())
        n = int(m.group(2)) if m else None
        if not chunks or (n is not None and n != chunks[-1][0]):
            chunks.append([n, i, i])
        else:
            chunks[-1][2] = i
    return [tuple(c) for c in chunks]


@router.post("/sites/{site_id}/report-bundle/old")
def upload_old(site_id: int, file: UploadFile = File(...), visit_no: int | None = Form(None), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """예전 보고서 올리기(파일 하나 — 여러 개는 창이 하나씩). PDF·한글·그림 등(완수계 붙임과 같은 변환), 큰 PDF는 사진을 줄여 둠.
    visit_no가 있으면(창의 회차 칸을 눌러 올림 — 10/8 사용자) 내용을 읽지 않고 파일 전체를 그 회차로."""
    site = _site(db, user, site_id)
    if visit_no is not None and not 1 <= visit_no <= 999:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회차가 맞지 않습니다.")
    name = file.filename or "보고서.pdf"
    try:
        data = attachments.to_pdf_bytes(file.file.read(), name)
    except (ValueError, RuntimeError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    if len(data) > attachments.SHRINK_OVER:
        data = pdf_shrink.shrink_bytes(data)
    d = old_dir(db, site)
    d.mkdir(parents=True, exist_ok=True)
    title = _clean_title(name)
    found: list[int] = []
    unknown = False
    with pymupdf.open(stream=data, filetype="pdf") as src:
        chunks = [(visit_no, 0, src.page_count - 1)] if visit_no else split_by_visit(src)
        for n, a, b in chunks:
            part = pymupdf.open()
            part.insert_pdf(src, from_page=a, to_page=b)
            if n is None:
                dest = d / f"{UNKNOWN}_{datetime.datetime.now():%H%M%S%f}_{title}.pdf"
                unknown = True
            else:
                for old in d.glob(f"{n:02d}회차_*.pdf"):  # 같은 회차를 다시 올리면 바꿈
                    old.unlink()
                dest = d / f"{n:02d}회차_{title}.pdf"
                found.append(n)
            part.save(dest, garbage=3, deflate=True)
            part.close()
    system = {r.visit_no for r in repo.list_reports_for_site(db, user.company_id, site.id)
              if r.pdf_path and Path(r.pdf_path).exists()}
    return {"plan": plan(db, user, site), "read": found, "unknown": unknown, "dup_system": sorted(set(found) & system)}


def _old_file(db: Session, site: Site, name: str) -> Path:
    path = old_dir(db, site) / Path(name).name
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다.")
    return path


@router.post("/sites/{site_id}/report-bundle/old/{name}/visit")
def set_old_visit(site_id: int, name: str, visit_no: int = Body(..., embed=True), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """회차를 못 읽은 파일 → 직원이 적은 회차로(같은 회차가 있으면 바꿈)."""
    site = _site(db, user, site_id)
    if not 1 <= visit_no <= 999:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "회차를 숫자로 적으세요.")
    path = _old_file(db, site, name)
    for old in path.parent.glob(f"{visit_no:02d}회차_*.pdf"):
        if old != path:
            old.unlink()
    title = path.stem.split("_", 2)[-1] if path.name.startswith(UNKNOWN) else _title(path)
    path.rename(path.with_name(f"{visit_no:02d}회차_{title}.pdf"))
    return {"plan": plan(db, user, site)}


@router.delete("/sites/{site_id}/report-bundle/old/{name}")
def delete_old(site_id: int, name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    site = _site(db, user, site_id)
    _old_file(db, site, name).unlink()
    return {"plan": plan(db, user, site)}


@router.get("/sites/{site_id}/report-bundle/old/{name}")
def view_old(site_id: int, name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    path = _old_file(db, _site(db, user, site_id), name)
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")
