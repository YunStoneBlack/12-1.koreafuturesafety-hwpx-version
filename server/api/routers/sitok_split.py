"""시특법 분권(2026-10-19 민재형) — 묶음 보고서와 같은 내용으로 일부 동만 따로 묶은 책을 성과품으로 더 줌(디지털 파일·제본용).

형: "분권은 시설물을 분류해 보고서를 작성하는 개념이 아니라 성과품에 추가로 분권도 필요하다는 요청 — FMS 등재 안 함, 제출 관리 필요 없음,
보고서 구성은 현행 유지, 헷갈리지 않게 기능 분리, 개별·묶어서·한 개만 작성자가 구성". 시안(회차 화면 📚 분권 칸) 그대로.
- 동마다 몇 권째에 넣을지(0 = 안 넣음) → 같은 권 = 한 책. 저장은 묶음 대표 동 회차 survey["split"].
- 만들기: 묶음 보고서를 만들 때 동마다 만든 "(이 동만)" 한글(survey.single_hwpx)로 — 1동은 그대로, 여러 동은 merge.merge로 다시 묶고
  묶음과 같은 뒤처리(머리말·쪽 넘김·목차 쪽 번호·도면·요약문·관리대장·계약서·사진첩·표지/책등 따로). 현장 조사·AI 초안은 다시 안 함,
  요약문 결언은 기본 문장(묶음 결언 AI는 다른 동 얘기도 있어서). 표지·용역명은 동 개수 규칙(merge.cover_name).
- 정밀(10/21): 묶음 정밀 보고서를 만들 때 만든 동별 본문 한글(survey.single_hwpx)을 precision_merge.merge_body로 다시 묶어 본문 PDF·도면·쪽 검사,
  동별 부록 PDF(survey.appendix_hwpx 옆 .pdf — 관리대장·사진첩·측정데이터 등 이미 끼운 것)를 merge_appendix_pdfs로 이어 부록, 본문 + 부록 = 합본(묶음 정밀과 같은 차례).
- 파일: 대표 동 회차 폴더/분권/N권/.

- `GET  /sitok/reports/{id}/split` — {available, why, buildings, assign, books, status, message}
- `POST /sitok/reports/{id}/split` {assign: {동 id: 권(0 = 안 함)}} — 권 번호는 1부터 차례로 다시 매김
- `POST /sitok/reports/{id}/split/build` — 권마다 만들기(백그라운드)
- `GET  /sitok/reports/{id}/split/file?k=&kind=pdf|hwpx|cover`
"""
from __future__ import annotations

import copy
import datetime
import re
import shutil
import threading
import traceback
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models_web import SitokContract, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers import sitok_reports as SR

router = APIRouter(prefix="/sitok", tags=["sitok"])
_RUNNING: set[int] = set()  # 지금 이 서버에서 만드는 대표 동 회차 — DB엔 "running"인데 여기 없으면 서버가 다시 시작돼 끊긴 것


def _lead(db: Session, r: SitokReport) -> SitokReport:
    return SR._book_lead(db, r) or r


def _cfg(r: SitokReport) -> dict:
    sp = copy.deepcopy((r.survey or {}).get("split") or {})
    cfg = {"assign": {str(k): int(v) for k, v in (sp.get("assign") or {}).items() if int(v or 0) > 0},
           "books": dict(sp.get("books") or {}), "status": sp.get("status") or "", "message": sp.get("message") or ""}
    if cfg["status"] == "running" and r.id not in _RUNNING:
        cfg["status"], cfg["message"] = "failed", "만드는 중에 서버가 다시 시작돼 멈췄습니다 — [분권 만들기]를 다시 누르세요."
    return cfg


def _put(r: SitokReport, cfg: dict) -> None:
    """저장 — 새 사본으로(같은 dict를 고쳐 넣으면 SQLAlchemy가 바뀐 게 없다고 보고 UPDATE를 안 함: 만들기 중 상태가 "1권 만드는 중"에 멈췄던 것, 10/19)."""
    r.survey = {**(r.survey or {}), "split": copy.deepcopy(cfg)}


def _books(pairs: list, assign: dict) -> list[tuple[int, list]]:
    """[(권, [(동, 회차)])] — 권 번호 순, 동은 묶음 순서."""
    out: dict[int, list] = {}
    for m, x in pairs:
        k = assign.get(str(m.id), 0)
        if k > 0:
            out.setdefault(k, []).append((m, x))
    return sorted(out.items())


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _cover_name(sub: list) -> str:
    from server.api.routers.sitok_compose import default_name
    from server.sitok import merge

    names = [m.name for m, _ in sub]
    return merge.cover_name([{"name": n} for n in names], default_name(names))


def _is_wall(db: Session, lead: SitokReport) -> bool:
    from server.sitok import kinds

    f = db.get(SitokFacility, lead.facility_id)
    return bool(f) and kinds.is_wall(f)


def _why_not(db: Session, lead: SitokReport, pairs: list) -> str:
    block = SR._template_block(db, lead)  # 틀 없는 시설물(교량·수리 등, 형 10/21)
    if block:
        return block
    if len(pairs) < 2:
        return "묶음(2동 이상) 보고서만 분권할 수 있습니다."
    if _is_wall(db, lead):  # 옹벽은 동별 한글 없이 원본에서 바로 묶음(wall_build.build_many, 10/21) — 묶음을 먼저 안 만들어도 됨
        return ""
    if lead.status != "done" or not lead.out_pdf:
        return "묶음 보고서를 먼저 만드세요 — 그때 만든 동별 한글로 분권을 묶습니다."
    miss = [m.name for m, x in pairs if not Path(str((x.survey or {}).get("single_hwpx") or "")).exists()]
    if miss:
        return "동별 한글이 없습니다(" + ", ".join(miss) + ") — 묶음 보고서를 다시 만드세요."
    if (lead.kind or "정기") == "정밀":
        miss = [m.name for m, x in pairs if not _appendix_pdf(x).exists()]
        if miss:
            return "동별 부록 PDF가 없습니다(" + ", ".join(miss) + ") — 묶음 보고서를 다시 만드세요."
    return ""


def _appendix_pdf(x: SitokReport) -> Path:
    """정밀 묶음 만들 때 동마다 만든 부록 PDF(끼울 자료까지 들어간 것)."""
    a = str((x.survey or {}).get("appendix_hwpx") or "")
    return Path(a).with_suffix(".pdf") if a else Path("")


def _out(db: Session, lead: SitokReport) -> dict:
    pairs = SR._group_reports(db, lead)
    cfg = _cfg(lead)
    books = []
    for k, sub in _books(pairs, cfg["assign"]):
        made = cfg["books"].get(str(k)) or {}
        same = made.get("ids") == [m.id for m, _ in sub]  # 구성이 바뀌면 옛 파일은 안 보여 줌(다시 만들어야)
        name = _cover_name(sub)
        books.append({"k": k, "ids": [m.id for m, _ in sub], "names": [m.name for m, _ in sub], "title": SR.service_title(name, lead),
                      "made_at": made.get("made_at") if same else "", "pages": made.get("pages") if same else None,
                      "has_pdf": same and Path(str(made.get("pdf") or "")).exists(), "has_hwpx": same and Path(str(made.get("hwpx") or "")).exists(),
                      "has_cover": same and Path(str(made.get("cover") or "")).exists(), "message": made.get("message") if same else "",
                      "stale": bool(same and made.get("made_at") and lead.made_at and made["made_at"] < lead.made_at.strftime("%Y-%m-%d %H:%M"))})  # 묶음을 다시 만든 뒤 옛 분권
    why = _why_not(db, lead, pairs)
    return {"available": not why, "why": why, "lead_id": lead.id, "kind": lead.kind or "정기", "wall": _is_wall(db, lead),
            "buildings": [{"id": m.id, "name": m.name} for m, _ in pairs], "assign": cfg["assign"], "books": books,
            "status": cfg["status"], "message": cfg["message"]}


@router.get("/reports/{report_id}/split")
def get_split(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _lead(db, SR._require(db, user, report_id)))


class SplitIn(BaseModel):
    assign: dict[str, int]


@router.post("/reports/{report_id}/split")
def save_split(report_id: int, body: SplitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = _lead(db, SR._require(db, user, report_id))
    if _cfg(lead)["status"] == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "분권을 만드는 중입니다 — 끝난 뒤에 바꾸세요.")
    ids = {str(m.id) for m, _ in SR._group_reports(db, lead)}
    raw = {k: int(v) for k, v in body.assign.items() if k in ids and int(v or 0) > 0}
    renum = {k: i for i, k in enumerate(sorted(set(raw.values())), 1)}  # 1권·3권만 고르면 1·2권으로
    cfg = _cfg(lead)
    cfg["assign"] = {k: renum[v] for k, v in raw.items()}
    _put(lead, cfg)
    db.commit()
    return _out(db, lead)


def _build_one(db: Session, lead: SitokReport, k: int, sub: list) -> dict:
    """한 권 — 동별 한글 → (여러 동이면 다시 묶기) → PDF·요약문·부록·표지 따로. 묶음 만들기(SR._run_group_build)와 같은 차례."""
    from server.sitok import layout_fix, merge, summary_doc

    warn: list[str] = []
    name = _cover_name(sub)
    title = SR.service_title(name, lead)
    lead_f = db.get(SitokFacility, lead.facility_id)
    folder = SR._report_dir(lead_f, lead) / "분권" / f"{k}권"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)  # 옛 파일(표지 PDF 이름이 바뀌어도 남지 않게)
    folder.mkdir(parents=True, exist_ok=True)
    base = _safe(f"{lead.year}년 {lead.half} {lead.kind or '정기'}안전점검 보고서_{name}(분권 {k})")
    hwpx, pdf = folder / f"{base}.hwpx", folder / f"{base}.pdf"
    if _is_wall(db, lead):  # 옹벽 — 원본에서 바로(현장 조사·AI 초안 값은 회차 것 그대로)
        from server.sitok import wall_build

        _, wtitle = SR.wall_book_name(db, sub, lead)
        hwpx, pdf, warn, _ = wall_build.build_many(db, sub, folder, name=name, title=wtitle if len(sub) > 1 else "", tag=f"(분권 {k})")
        pages = pymupdf.open(pdf).page_count
        return {"ids": [m.id for m, _ in sub], "pdf": str(pdf), "hwpx": str(hwpx), "cover": "", "pages": pages,
                "made_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "message": SR._done_msg(f"{k}권 {len(sub)}곳 {pages}쪽", "합본", {"": []}, warn)}
    if (lead.kind or "정기") == "정밀":
        return _build_precision(db, lead, k, sub, folder, base)
    parts = []
    for i, (m, x) in enumerate(sub, 1):
        floors = " / ".join(s for s in (f"B{m.floors_below}F" if m.floors_below else "", f"{m.floors_above}F" if m.floors_above else "") if s)
        parts.append({"hwpx": Path(x.survey["single_hwpx"]), "name": m.name, "title": SR.service_title(m.name, x), "area": m.total_area or 0,
                      "row": [str(i), m.name, f"{m.completion_date.year}년" if m.completion_date else "-", floors or "-",
                              f"{m.total_area:,.2f}㎡" if m.total_area else "-", m.structure or "-"]})
    if len(parts) == 1:  # 한 동 — 그 동 한글(표지·용역명 = 시설물명) 그대로
        shutil.copy(parts[0]["hwpx"], hwpx)
    else:
        from server.api.routers.sitok_compose import default_name

        warn += merge.merge(parts, hwpx, default_name([m.name for m, _ in sub]), title)
    summary_doc.add_toc_line(hwpx)
    SR._convert_pushing(hwpx, pdf)  # 머리말 한 줄·쪽 넘김·목차 쪽 번호까지(묶음과 같음)
    drawn = SR._insert_drawings(pdf, [(i, m) for i, (m, _) in enumerate(sub, 1)])
    warn = SR._page_check(pdf, hwpx, drawn) + warn
    SR._add_summary(db, sub, title, hwpx, pdf, warn, book=True)
    contracts = []
    for _, y in sub:
        c = db.get(SitokContract, y.contract_id) if y.contract_id else None
        if c is not None and c.contract_pdf and c.contract_pdf not in contracts:
            contracts.append(c.contract_pdf)
    merged = SR._merge(pdf, [m.ledger_pdf for m, _ in sub], contracts, [(m.fms_no, m.name) for m, _ in sub], warn)
    if SR._insert_albums(db, [y for _, y in sub], [m.name for m, _ in sub], pdf):
        merged.append("외관조사 사진첩")
    from server.api.routers.sitok_maps import insert_maps
    if insert_maps(db, [y for _, y in sub], pdf):  # 부록 외관망도(10/23)
        merged.append("외관망도")
    cover = None
    try:
        cover = layout_fix.split_cover_pdf(pdf, title)  # 표지 + 책등 따로(묶음과 같음, 회차 cover_pdf는 안 건드림)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    pages = pymupdf.open(pdf).page_count
    return {"ids": [m.id for m, _ in sub], "pdf": str(pdf), "hwpx": str(hwpx), "cover": str(cover) if cover else "", "pages": pages,
            "made_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "message": SR._done_msg(f"{k}권 {len(sub)}동 {pages}쪽", "합본", {"": merged}, warn)}


def _build_precision(db: Session, lead: SitokReport, k: int, sub: list, folder: Path, base: str) -> dict:
    """정밀 한 권 — 동별 본문 한글 → (여러 동이면 merge_body) → 본문 PDF(빈 자리 당기기)·도면·쪽 검사, 동별 부록 PDF → (여러 동이면 merge_appendix_pdfs), 합본.
    묶음 정밀 만들기(SR._run_precision_group_build)의 뒷부분과 같음 — 본문·부록 한글을 다시 만들지 않음(현장 조사·AI 초안 값은 묶음 때 것)."""
    from server.api.routers.sitok_compose import default_name
    from server.sitok import drawings as D
    from server.sitok import precision_merge
    from server.sitok import report_build as rb

    warn: list[str] = []
    name = _cover_name(sub)
    title = SR.service_title(name, lead)
    hwpx, pdf = folder / f"{base}(본문).hwpx", folder / f"{base}(본문).pdf"
    singles = [Path(x.survey["single_hwpx"]) for _, x in sub]
    if len(sub) == 1:  # 한 동 — 그 동 본문 한글(표지·용역명 = 시설물명) 그대로
        shutil.copy(singles[0], hwpx)
    else:
        parts = [{"hwpx": h, "name": m.name, "title": rb.read_old(h).title} for h, (m, _) in zip(singles, sub)]
        warn += precision_merge.merge_body(parts, hwpx, default_name([m.name for m, _ in sub]), title)
    SR._convert_pushing(hwpx, pdf, precision=True)
    chapters = [(i, [it["path"] for it in D.items(m, "attach", SR._facility_dir(m))]) for i, (m, _) in enumerate(sub, 1)]
    with pymupdf.open(pdf) as doc:  # 동마다 "1.2 시설물 관련도면 [후면첨부]" 쪽 — i번째 것(묶음 정밀과 같음)
        hits = [i for i, pg in enumerate(doc) if pg.search_for("시설물 관련도면") and pg.search_for("후면첨부")]
    drawn = D.insert(pdf, chapters, finder=lambda pg, n: n <= len(hits) and pg.number == hits[n - 1]) if any(p for _, p in chapters) else []
    warn = SR._page_check(pdf, hwpx, drawn) + warn
    body_pages = pymupdf.open(pdf).page_count
    apdf = folder / f"{base}(부록).pdf"
    apdfs = [(m.name, _appendix_pdf(x)) for m, x in sub]
    if len(apdfs) == 1:
        shutil.copy(apdfs[0][1], apdf)
    else:
        warn += precision_merge.merge_appendix_pdfs(apdfs, apdf)
    full = folder / f"{base}_합본.pdf"
    with pymupdf.open(pdf) as a, pymupdf.open(apdf) as b, pymupdf.open() as out:
        out.insert_pdf(a)
        out.insert_pdf(b)
        out.save(full, garbage=3, deflate=True)
    pages = pymupdf.open(full).page_count
    return {"ids": [m.id for m, _ in sub], "pdf": str(full), "hwpx": str(hwpx), "cover": "", "pages": pages,
            "made_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "message": SR._done_msg(f"{k}권 {len(sub)}동 {pages}쪽(본문 {body_pages})", "합본", {"": []}, warn)}


def _run(lead_id: int) -> None:
    try:
        _run_books(lead_id)
    finally:
        _RUNNING.discard(lead_id)


def _run_books(lead_id: int) -> None:
    with SessionLocal() as db:
        lead = db.get(SitokReport, lead_id)
        cfg = _cfg(lead)
        try:
            pairs = SR._group_reports(db, lead)
            books = _books(pairs, cfg["assign"])
            for n, (k, sub) in enumerate(books, 1):
                cfg["message"] = f"{k}권 만드는 중 — {n}/{len(books)}권(권마다 몇 분)…"
                _put(lead, cfg)
                db.commit()
                cfg["books"][str(k)] = _build_one(db, lead, k, sub)
                _put(lead, cfg)
                db.commit()
            keep = {str(k) for k, _ in books}
            cfg["books"] = {k: v for k, v in cfg["books"].items() if k in keep}
            cfg["status"], cfg["message"] = "done", f"분권 {len(books)}권 만듦"
        except Exception as err:  # noqa: BLE001 — 이유를 남김
            traceback.print_exc()
            cfg["status"], cfg["message"] = "failed", f"분권을 만들지 못했습니다: {str(err).splitlines()[0][:200]}"
        _put(lead, cfg)
        db.commit()


@router.post("/reports/{report_id}/split/build")
def build_split(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = _lead(db, SR._require(db, user, report_id))
    pairs = SR._group_reports(db, lead)
    why = _why_not(db, lead, pairs)
    if why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, why)
    cfg = _cfg(lead)
    if cfg["status"] == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 분권을 만드는 중입니다.")
    if not _books(pairs, cfg["assign"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "분권에 넣은 동이 없습니다 — 동마다 몇 권째에 넣을지 고르세요.")
    cfg["status"], cfg["message"] = "running", "분권 만드는 중…"
    _put(lead, cfg)
    db.commit()
    _RUNNING.add(lead.id)
    threading.Thread(target=_run, args=(lead.id,), daemon=True).start()
    return _out(db, lead)


@router.get("/reports/{report_id}/split/file")
def split_file(report_id: int, k: int, kind: str = "pdf", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = _lead(db, SR._require(db, user, report_id))
    made = _cfg(lead)["books"].get(str(k)) or {}
    p = Path(str(made.get({"pdf": "pdf", "hwpx": "hwpx", "cover": "cover"}.get(kind, "pdf")) or ""))
    if not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일이 없습니다 — [분권 만들기]를 누르세요.")
    media = "application/pdf" if p.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(p, media_type=media, filename=p.name)
