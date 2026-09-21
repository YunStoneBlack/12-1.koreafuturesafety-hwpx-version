"""보고서 산출물(PDF·한글 파일)을 "저장 위치를 물어 → 저장된 최신 내용으로 새로 만들어 → 그 위치에 저장"하는
공통 흐름 — 마법사 미리보기 창의 "PDF 생성"/"한글 파일 생성"과 현장 상세 보고서 이력의 "↓ 한글"/"↓ PDF"
버튼이 같이 쓴다.

예전엔 이력 버튼이 마지막 미리보기 때 만들어 둔 파일(`pdf_path`/`hwpx_path`)만 열어서, 수정 후 저장만 하고
미리보기를 안 누르면 예전 내용이 내려받아지고 한글 버튼은 아예 꺼져 있었다(사용자, 2026-09-21). 이제는
누를 때마다 DB에 저장된 최신 데이터로 새로 만든다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.db import SessionLocal
from core.models_db import Report
from core.report_builder import build_report
from core.report_builder_hwpx import build_report_hwpx
from desktop.dialogs.saving_progress_dialog import SavingProgressDialog
from desktop.workers.ai_worker import AIWorker, with_com

# 종류 → (확장자, 저장 창 제목, 저장 창 필터, 진행 창 문구, 성공 안내, 실패 창 제목)
_KINDS = {
    "pdf": (".pdf", "PDF로 저장", "PDF 파일 (*.pdf)", "PDF 파일을 저장하는 중입니다...", "PDF를 저장했습니다", "PDF 생성 실패"),
    "hwpx": (
        ".hwpx",
        "한글 파일로 저장",
        "한글 hwpx 파일 (*.hwpx)",
        "한글 파일을 저장하는 중입니다...",
        "한글 파일을 저장했습니다",
        "한글 파일 생성 실패",
    ),
}


def _build_pdf_for_export(report_id: int, chosen_path: Path) -> Path:
    build_report(report_id, chosen_path)
    with SessionLocal() as session:
        report = session.get(Report, report_id)
        report.pdf_path = str(chosen_path)
        session.commit()
    return chosen_path


def _build_hwp_for_export(report_id: int, chosen_path: Path) -> Path:
    """COM(pyhwpx) 없이 순수 파이썬으로 .hwpx를 만드는 신규 엔진(Sub-phase 18)으로 생성한다
    — `build_report_hwp`(한글 프로그램 COM 자동화, .hwp)는 더 이상 이 버튼에서 쓰지 않는다.
    PDF 생성/미리보기는 python-hwpx에 PDF 변환 기능이 없어 여전히 COM 경로를 쓴다."""
    build_report_hwpx(report_id, chosen_path)
    with SessionLocal() as session:
        report = session.get(Report, report_id)
        report.hwpx_path = str(chosen_path)
        session.commit()
    return chosen_path


def export_report_file(parent, report_id: int, kind: str, default_stem: str, on_finished=None) -> None:
    """`kind`("pdf"|"hwpx") 파일을 사용자가 고른 위치에 최신 저장 내용으로 만든다.

    파일명 기본값은 "{default_stem}.{확장자}", 기본 위치는 바탕화면. 파일 생성이 몇 초 걸릴 수 있어(특히 PDF는
    한글 자동화를 거침) 백그라운드에서 돌리고 진행 창을 띄운다. `on_finished`가 있으면 성공/실패/취소
    **어느 경우에도** 정확히 한 번 불러준다(성공이면 저장 경로, 아니면 None)."""
    suffix, dialog_title, name_filter, progress_text, done_text, error_title = _KINDS[kind]
    default_path = str(Path.home() / "Desktop" / f"{default_stem}{suffix}")
    chosen, _ = QFileDialog.getSaveFileName(parent, dialog_title, default_path, name_filter)
    if not chosen:
        if on_finished:
            on_finished(None)
        return
    chosen_path = Path(chosen)
    if chosen_path.suffix.lower() != suffix:
        chosen_path = chosen_path.with_suffix(suffix)

    if kind == "pdf":
        task = with_com(lambda: _build_pdf_for_export(report_id, chosen_path))
    else:
        task = lambda: _build_hwp_for_export(report_id, chosen_path)  # noqa: E731
    # 작업이 끝나기 전에 워커가 가비지 컬렉션되지 않도록 부모가 들고 있는다.
    parent._export_worker = AIWorker(task)

    # 저장 위치를 고르고 나서 실제 파일이 만들어지기까지 몇 초 걸리는데, 그동안 아무 표시가 없어 "오류가 난
    # 줄 알았다"는 피드백이 있었다(2026-09-15) — 이 모달이 그 사이를 채운다(끝나면 알아서 닫힌다).
    progress_dialog = SavingProgressDialog(progress_text, parent=parent)

    def _ok(path):
        progress_dialog.finish()
        QMessageBox.information(parent, "저장 완료", f"{done_text}:\n{path}")
        if on_finished:
            on_finished(path)

    def _err(message):
        progress_dialog.fail()
        QMessageBox.warning(parent, error_title, message)
        if on_finished:
            on_finished(None)

    parent._export_worker.finished_ok.connect(_ok)
    parent._export_worker.finished_error.connect(_err)
    parent._export_worker.start()
    progress_dialog.exec()
