"""보고서 이력 관리 — 데스크톱 현장상세 "보고서 이력"(`desktop/views/site_detail_view.py`)의 "↓ 한글", "🗑 삭제".

- 한글(.hwpx): COM 없이 순수 파이썬 엔진(`build_report_hwpx`, 데스크톱 "↓ 한글"과 같은 함수)이라 렌더 워커/큐
  없이 요청 안에서 바로 만든다(수 초). 누를 때마다 저장된 최신 내용으로 새로 만든다(데스크톱과 동일).
- 삭제: 자식 테이블은 ORM cascade로 같이 지워지지만, PostgreSQL은 외래키를 실제로 검사해서 두 가지를
  먼저 정리해야 한다(데스크톱 SQLite는 검사 안 해서 문제가 드러나지 않았음) —
  ① 다음 회차 4번 이전지적사항이 이 보고서의 8번 지적사항을 가리키는 연결(끊어도 이월 내용은 저장된
  사본(title/content/photo_path)으로 남는다 — PreviousFinding.display_fields 참고, 단 사진 파일은 이
  보고서 폴더에 있으므로 지우지 않고 남겨둔다), ② PDF 렌더 작업 기록(report_job).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.models_db import Finding, PreviousFinding
from core.models_web import ReportJob, User
from core.db import BASE_DIR
from core.report_builder_hwpx import build_report_hwpx
from server.api import repo
from server.api.deps import get_current_user, get_db

router = APIRouter(prefix="/reports/{report_id}", tags=["report-manage"])


def download_name(report, suffix: str) -> str:
    site_name = (report.site.name if report.site else "") or "보고서"
    safe = "".join(ch for ch in site_name if ch not in '\\/:*?"<>|').strip() or "보고서"
    return f"{safe}_{report.visit_no}회차{suffix}"


# 한글 받기는 2단계(2026-09-29 사용자 — 누르면 몇 초 아무 반응이 없다가 저장 창이 떠서 답답함):
#   1) GET .../hwpx/prepare — 최신 내용으로 만들어 PDF 옆 `report_{id}.hwpx`에 잠깐 두고 받기 번호(token=파일 수정 시각)를 돌려준다.
#      화면은 그동안 "만드는 중… N초"를 보여 준다. GET인 이유: 쓰기 요청이면 edit_tracking이 "보고서 수정"으로 기록해 PDF가 수정 전 버전으로 보임.
#   2) GET .../hwpx?token=… — 준비된 파일을 바로 준다(폰·카카오톡 브라우저도 일반 받기라 저장 창이 뜬다). token이 없거나 안 맞으면 예전처럼 즉석 생성.
def prepared_hwpx_path(report_id: int) -> Path:
    return BASE_DIR / "data" / "reports" / f"report_{report_id}.hwpx"


@router.get("/hwpx/prepare")
def prepare_hwpx(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    out = prepared_hwpx_path(report_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".hwpx.tmp")
    try:
        build_report_hwpx(report_id, tmp)
        tmp.replace(out)
    except Exception as err:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"한글 파일을 만들지 못했습니다: {err}") from err
    return {"token": str(out.stat().st_mtime_ns)}


@router.get("/hwpx")
def download_hwpx(
    report_id: int,
    background: BackgroundTasks,
    token: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    prepared = prepared_hwpx_path(report_id)
    if token and prepared.exists() and str(prepared.stat().st_mtime_ns) == token:
        return FileResponse(prepared, media_type="application/hwp+zip", filename=download_name(report, ".hwpx"))
    tmp_dir = tempfile.TemporaryDirectory()
    out = Path(tmp_dir.name) / "report.hwpx"
    try:
        build_report_hwpx(report_id, out)
    except Exception as err:  # noqa: BLE001
        tmp_dir.cleanup()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"한글 파일을 만들지 못했습니다: {err}") from err
    background.add_task(tmp_dir.cleanup)  # 응답을 다 보낸 뒤 임시 파일 정리
    return FileResponse(out, media_type="application/hwp+zip", filename=download_name(report, ".hwpx"))


@router.get("/pdf")
def download_pdf(
    report_id: int, inline: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """마지막으로 만든 PDF 받기(현장 화면 보고서 목록의 "PDF 생성됨"을 누를 때). 새로 만들지 않고 저장된 파일을 그대로 준다.
    inline=true면 내려받지 않고 브라우저 안에서 연다(보고서 화면 "미리보기")."""
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    if not report.pdf_path or not Path(report.pdf_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 만든 PDF가 없습니다. 보고서 화면에서 'PDF 생성'을 먼저 누르세요.")
    return FileResponse(
        report.pdf_path, media_type="application/pdf", filename=download_name(report, ".pdf"),
        content_disposition_type="inline" if inline else "attachment",
    )


# ---------- 폰 미리보기용 쪽별 이미지 ----------
# 폰 브라우저(안드로이드 크롬, 카카오톡 안 브라우저 등)는 PDF를 화면에 못 띄우고 내려받아 버려서(2026-09-29 사용자),
# 미리보기 창에 PDF 대신 쪽별 JPG를 보여 준다. 마지막으로 만든 PDF를 PyMuPDF로 바꿔 PDF 옆 "<pdf이름>_preview/" 폴더에 두고,
# PDF가 새로 만들어졌을 때(수정 시각이 바뀌면)만 다시 바꾼다. 보고서/현장 삭제 때 폴더도 같이 지운다(preview_dir 사용).
PREVIEW_ZOOM = 2.0  # A4 한 쪽 약 1190px 폭 — 폰에서 두 손가락으로 키워도 글자가 읽히는 정도


def preview_dir(pdf_path: str) -> Path:
    p = Path(pdf_path)
    return p.with_name(p.stem + "_preview")


def _ensure_preview_pages(pdf_path: str) -> tuple[Path, int, str]:
    """(폴더, 쪽 수, 판 번호) — 판 번호는 PDF 수정 시각(브라우저 캐시가 옛 이미지를 쓰지 않게 주소에 붙임)."""
    import fitz  # PyMuPDF — 여기서만 쓰므로 필요할 때 불러온다

    folder = preview_dir(pdf_path)
    version = str(int(Path(pdf_path).stat().st_mtime))
    stamp = folder / "version.txt"
    if stamp.exists() and stamp.read_text(encoding="utf-8").strip() == version:
        return folder, len(list(folder.glob("p*.jpg"))), version
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            page.get_pixmap(matrix=fitz.Matrix(PREVIEW_ZOOM, PREVIEW_ZOOM)).save(str(folder / f"p{i}.jpg"), jpg_quality=80)
        count = doc.page_count
    stamp.write_text(version, encoding="utf-8")
    return folder, count, version


def _report_pdf_or_404(db: Session, company_id: int, report_id: int):
    report = repo.get_report(db, company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    if not report.pdf_path or not Path(report.pdf_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 만든 PDF가 없습니다. 보고서 화면에서 'PDF 생성'을 먼저 누르세요.")
    return report


@router.get("/pdf-pages")
def pdf_pages(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _report_pdf_or_404(db, user.company_id, report_id)
    _, count, version = _ensure_preview_pages(report.pdf_path)
    return {"count": count, "version": version}


@router.get("/pdf-pages/{page}.jpg")
def pdf_page_image(report_id: int, page: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = _report_pdf_or_404(db, user.company_id, report_id)
    folder, count, _ = _ensure_preview_pages(report.pdf_path)
    if not 1 <= page <= count:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 쪽입니다.")
    return FileResponse(folder / f"p{page}.jpg", media_type="image/jpeg")


@router.delete("")
def delete_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = repo.get_report(db, user.company_id, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
    finding_ids = [f.id for f in db.query(Finding.id).filter(Finding.report_id == report_id)]
    if finding_ids:
        db.query(PreviousFinding).filter(
            PreviousFinding.source_finding_id.in_(finding_ids), PreviousFinding.report_id != report_id
        ).update({PreviousFinding.source_finding_id: None}, synchronize_session=False)
    db.query(ReportJob).filter(ReportJob.report_id == report_id).delete(synchronize_session=False)
    for path in (report.pdf_path, report.notify_signature_path):
        if path:
            Path(path).unlink(missing_ok=True)
    if report.pdf_path:
        shutil.rmtree(preview_dir(report.pdf_path), ignore_errors=True)
    prepared_hwpx_path(report_id).unlink(missing_ok=True)
    db.delete(report)
    db.commit()
    return {"ok": True}
