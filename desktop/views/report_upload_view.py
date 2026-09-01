"""이전 보고서 업로드 — 과거 기술지도 결과보고서 PDF 여러 개를 올리면 AI가 읽어 현장/회차를
자동으로 등록한다. 실제 사이트 화면 구성(3단계 안내 → 드래그드롭 → 안내 문구)을 그대로 따른다.

검토 범위는 핵심 필드만(현장명·매칭 상태·회차·지도일·공정률) — 지적사항 등 세부 내용은
등록 후 기존 보고서 작성 마법사에서 고친다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.db import SessionLocal
from core.models_db import Report
from core.report_extractor import extract_report_info
from core.report_import import commit_extracted, preview_match
from desktop.widgets.pdf_drop_zone import PdfDropZone
from desktop.workers.ai_worker import AIWorker

_STEP_CARDS = [
    (1, "PDF 업로드", "보고서 파일을 여러 개 한번에"),
    (2, "AI 자동 인식", "현장정보·회차·지도일·지적사항·제공자료 자동으로 추출"),
    (3, "자동 정리 완료", "현장목록·보고서이력에 바로 표시"),
]

_INFO_BULLETS = [
    "사업장관리번호가 같은 보고서는 같은 현장으로 자동 그룹핑되어 회차 이력이 한 곳에 모입니다 "
    "(번호를 못 읽은 보고서는 현장명으로 이어붙입니다)",
    "현장 목록에 공정률·최근 지도일·전체 회차 수가 자동으로 표시됩니다",
    "업로드하신 원본 PDF는 보관하지 않습니다 — 지적사항·회차 정보만 텍스트로 옮겨 담고 파일은 "
    "즉시 버립니다. 원본은 직접 보관해주세요.",
    "다음 회차 작성 시 이전 지적사항이 자동으로 이어집니다",
    "이미 등록된 현장·회차는 건너뛰어 중복 없이 안전하게 반복 업로드할 수 있습니다",
]

_STATUS_STYLE = {
    "신규": "color: #2563eb; background: #eff6ff; border: 1px solid #bfdbfe;",
    "매칭": "color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0;",
    "중복": "color: #9ca3af; background: #f3f4f6; border: 1px solid #e5e7eb;",
    "실패": "color: #dc2626; background: #fef2f2; border: 1px solid #fecaca;",
}


def _status_badge(text: str, kind: str) -> QLabel:
    badge = QLabel(text)
    badge.setStyleSheet(
        f"{_STATUS_STYLE[kind]} border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 600;"
    )
    return badge


class _FileRow(QFrame):
    def __init__(self, path: str, on_checkbox_toggled=None):
        super().__init__()
        self.path = path
        self.extracted: dict | None = None
        self.include_checkbox: QCheckBox | None = None
        self.name_input: QLineEdit | None = None
        self.visit_input: QSpinBox | None = None
        self.date_input: QDateEdit | None = None
        self.progress_input: QSpinBox | None = None
        self.duplicate_report_id: int | None = None
        self._duplicate = False
        self._badge_label: QLabel | None = None
        self._on_checkbox_toggled = on_checkbox_toggled

        self.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)

        self.status_row = QHBoxLayout()
        self.status_label = QLabel(f"📄 {Path(path).name} — 대기 중")
        self.status_label.setStyleSheet("border: none; background: transparent;")
        self.status_row.addWidget(self.status_label)
        self.status_row.addStretch()
        self._layout.addLayout(self.status_row)

        self._review_container: QWidget | None = None

    def set_status(self, text: str) -> None:
        self.status_label.setText(f"📄 {Path(self.path).name} — {text}")

    def show_failure(self, message: str) -> None:
        self.set_status("실패")
        self.status_row.addWidget(_status_badge("실패", "실패"))
        err = QLabel(message)
        err.setWordWrap(True)
        err.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        err.setCursor(Qt.CursorShape.IBeamCursor)
        err.setStyleSheet("color: #dc2626; font-size: 12px; border: none; background: transparent;")
        self._layout.addWidget(err)

    def show_review(self, extracted: dict, match_info: dict) -> None:
        self.extracted = extracted
        self.set_status("분석 완료")

        review = QWidget()
        row = QHBoxLayout(review)
        row.setContentsMargins(0, 8, 0, 0)

        self.include_checkbox = QCheckBox("포함")
        self.include_checkbox.toggled.connect(self._notify_checkbox_toggled)
        row.addWidget(self.include_checkbox)

        self.name_input = QLineEdit(match_info["site_name"])
        row.addWidget(QLabel("현장명"))
        row.addWidget(self.name_input, stretch=2)

        self.visit_input = QSpinBox()
        self.visit_input.setRange(1, 999)
        self.visit_input.setValue(extracted["report"].get("visit_no") or 1)
        row.addWidget(QLabel("회차"))
        row.addWidget(self.visit_input)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        guidance_date = extracted["report"].get("guidance_date")
        from PyQt6.QtCore import QDate

        parsed = QDate.fromString(guidance_date, "yyyy-MM-dd") if guidance_date else QDate()
        self.date_input.setDate(parsed if parsed.isValid() else QDate.currentDate())
        row.addWidget(QLabel("지도일"))
        row.addWidget(self.date_input)

        self.progress_input = QSpinBox()
        self.progress_input.setRange(0, 100)
        self.progress_input.setSuffix("%")
        self.progress_input.setValue(extracted["report"].get("progress_rate") or 0)
        row.addWidget(QLabel("공정률"))
        row.addWidget(self.progress_input)

        self._layout.addWidget(review)
        self._review_container = review

        self._apply_match_state(match_info)

    def _notify_checkbox_toggled(self) -> None:
        if self._on_checkbox_toggled:
            self._on_checkbox_toggled()

    def _apply_match_state(self, match_info: dict) -> None:
        """중복 여부에 따라 배지를 갱신한다.

        체크박스는 중복 여부와 상관없이 항상 켤 수 있다 — "포함"(등록 대상) 또는
        "삭제 대상"(목록에서 빼기, 중복이면 기존 보고서도 함께 삭제) 두 가지 의미로
        모두 쓰인다. 필드도 항상 편집 가능하게 둔다.
        """
        self.duplicate_report_id = match_info["duplicate_report_id"]
        is_duplicate = self.duplicate_report_id is not None
        self._duplicate = is_duplicate

        if self._badge_label is not None:
            self.status_row.removeWidget(self._badge_label)
            self._badge_label.deleteLater()
        if is_duplicate:
            self._badge_label = _status_badge("중복 — 이미 등록됨", "중복")
        elif match_info["is_new_site"]:
            self._badge_label = _status_badge("신규 현장", "신규")
        else:
            self._badge_label = _status_badge("기존 현장에 추가", "매칭")
        self.status_row.addWidget(self._badge_label)

        if self.include_checkbox is not None:
            self.include_checkbox.blockSignals(True)
            self.include_checkbox.setChecked(not is_duplicate)
            self.include_checkbox.blockSignals(False)

    def is_ready_to_commit(self) -> bool:
        return (
            self.extracted is not None
            and not self._duplicate
            and self.include_checkbox is not None
            and self.include_checkbox.isChecked()
        )

    def is_checked(self) -> bool:
        return self.include_checkbox is not None and self.include_checkbox.isChecked()

    def apply_edits_to_extracted(self) -> dict:
        """검토 화면에서 고친 값을 추출된 dict에 반영해 돌려준다."""
        assert self.extracted is not None
        self.extracted["site"]["name"] = self.name_input.text().strip() or self.extracted["site"]["name"]
        self.extracted["report"]["visit_no"] = self.visit_input.value()
        self.extracted["report"]["guidance_date"] = self.date_input.date().toString("yyyy-MM-dd")
        self.extracted["report"]["progress_rate"] = self.progress_input.value()
        return self.extracted


class ReportUploadView(QWidget):
    back_requested = pyqtSignal()
    upload_completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: list[str] = []
        self._rows: dict[str, _FileRow] = {}
        self._worker: AIWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        back_btn = QPushButton("← 현장 목록")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("이전 보고서 업로드")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        desc = QLabel(
            "과거에 작성한 기술지도 보고서 PDF를 올리면, AI가 현장 정보를 읽어 자동으로 정리합니다.\n"
            "분석이 끝나면 등록 전에 추출된 내용을 확인·수정할 수 있습니다. 여기서 업로드된 정보는 "
            "저장되지 않습니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6b7280; font-size: 12px;")
        root.addWidget(desc)

        steps_row = QHBoxLayout()
        for number, step_title, step_desc in _STEP_CARDS:
            card = QFrame()
            card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }")
            card_layout = QVBoxLayout(card)
            card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge = QLabel(str(number))
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "background: #111827; color: white; border-radius: 14px; font-weight: 700; "
                "border: none;"
            )
            card_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignHCenter)
            step_title_label = QLabel(step_title)
            step_title_label.setStyleSheet("font-weight: 700; border: none; background: transparent;")
            step_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(step_title_label)
            step_desc_label = QLabel(step_desc)
            step_desc_label.setWordWrap(True)
            step_desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_desc_label.setStyleSheet("color: #6b7280; font-size: 11px; border: none; background: transparent;")
            card_layout.addWidget(step_desc_label)
            steps_row.addWidget(card)
        root.addLayout(steps_row)

        self.drop_zone = PdfDropZone()
        self.drop_zone.files_selected.connect(self._on_files_selected)
        root.addWidget(self.drop_zone)

        info_frame = QFrame()
        info_frame.setStyleSheet(
            "QFrame { background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 8px; }"
        )
        info_layout = QVBoxLayout(info_frame)
        info_title = QLabel("업로드 완료 후 이렇게 정리됩니다")
        info_title.setStyleSheet("font-weight: 700; border: none; background: transparent;")
        info_layout.addWidget(info_title)
        for bullet in _INFO_BULLETS:
            label = QLabel(f"•  {bullet}")
            label.setWordWrap(True)
            label.setStyleSheet("color: #4c1d95; font-size: 12px; border: none; background: transparent;")
            info_layout.addWidget(label)
        root.addWidget(info_frame)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_container)
        root.addWidget(scroll, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.delete_btn = QPushButton("🗑 선택된 항목 삭제")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet(
            "QPushButton { color: #ef4444; border: 1px solid #fecaca; border-radius: 6px; "
            "padding: 10px 16px; }"
            "QPushButton:hover:enabled { background: #fef2f2; }"
            "QPushButton:disabled { color: #d1d5db; border-color: #e5e7eb; }"
        )
        self.delete_btn.clicked.connect(self._delete_selected)
        bottom_row.addWidget(self.delete_btn)
        self.register_btn = QPushButton("✓ 등록")
        self.register_btn.setEnabled(False)
        self.register_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; padding: 10px 24px; border-radius: 6px; "
            "font-weight: 600; }"
            "QPushButton:disabled { background: #c7c7c7; }"
        )
        self.register_btn.clicked.connect(self._register_all)
        bottom_row.addWidget(self.register_btn)
        root.addLayout(bottom_row)

    # ---- 업로드/분석 ----

    def _on_files_selected(self, paths: list[str]) -> None:
        if not config.has_api_key():
            QMessageBox.warning(self, "API 키 필요", "'AI 관리' 화면에서 Claude API 키를 먼저 등록하세요.")
            return

        new_paths = [p for p in paths if p not in self._rows]
        if not new_paths:
            QMessageBox.information(self, "이미 추가됨", "선택한 파일은 이미 아래 목록에 있습니다.")
            return

        for path in new_paths:
            row = _FileRow(path, on_checkbox_toggled=self._update_action_buttons)
            self._rows[path] = row
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
            self._queue.append(path)

        if self._worker is None:
            self._process_next()

    def _process_next(self) -> None:
        if not self._queue:
            self._worker = None
            self._update_action_buttons()
            return
        path = self._queue.pop(0)
        row = self._rows[path]
        row.set_status("AI가 분석 중...")

        self._worker = AIWorker(lambda p=path: extract_report_info(p))
        self._worker.finished_ok.connect(lambda result, p=path: self._on_extract_done(p, result))
        self._worker.finished_error.connect(lambda message, p=path: self._on_extract_error(p, message))
        self._worker.start()

    def _on_extract_done(self, path: str, extracted: dict) -> None:
        row = self._rows[path]
        match_info = preview_match(extracted)
        row.show_review(extracted, match_info)
        self._process_next()

    def _on_extract_error(self, path: str, message: str) -> None:
        self._rows[path].show_failure(message)
        self._process_next()

    def _update_action_buttons(self) -> None:
        self.register_btn.setEnabled(any(r.is_ready_to_commit() for r in self._rows.values()))
        self.delete_btn.setEnabled(any(r.is_checked() for r in self._rows.values()))

    # ---- 선택된 항목 삭제 ----

    def _delete_selected(self) -> None:
        targets = [r for r in self._rows.values() if r.is_checked()]
        if not targets:
            return
        already_registered = [r for r in targets if r.duplicate_report_id is not None]
        if already_registered:
            message = (
                f"선택한 {len(targets)}건을 목록에서 제거합니다. 이 중 {len(already_registered)}건은 "
                "이미 등록된 보고서라 그 보고서도 함께 삭제됩니다. 계속하시겠습니까?"
            )
        else:
            message = f"선택한 {len(targets)}건을 목록에서 제거합니다. 계속하시겠습니까?"
        reply = QMessageBox.question(self, "선택 항목 삭제", message)
        if reply != QMessageBox.StandardButton.Yes:
            return

        if already_registered:
            with SessionLocal() as session:
                for row in already_registered:
                    report = session.get(Report, row.duplicate_report_id)
                    if report:
                        session.delete(report)
                session.commit()

        for row in targets:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
            del self._rows[row.path]
        self._update_action_buttons()
        QMessageBox.information(self, "삭제 완료", "선택한 항목을 삭제했습니다.")

    # ---- 등록 ----

    def _register_all(self) -> None:
        target_rows = [row for row in self._rows.values() if row.is_ready_to_commit()]
        if not target_rows:
            QMessageBox.information(self, "등록할 항목 없음", "등록할 보고서를 하나 이상 선택하세요.")
            return

        registered = 0
        skipped = 0
        failed: list[str] = []
        done_rows: list[_FileRow] = []
        for row in target_rows:
            try:
                extracted = row.apply_edits_to_extracted()
                result = commit_extracted(extracted)
            except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여줄 에러 메시지
                failed.append(f"{Path(row.path).name}: {e}")
                continue
            if result["skipped"]:
                skipped += 1
            else:
                registered += 1
            done_rows.append(row)

        # 등록(또는 등록 시점에 중복으로 판명되어 건너뜀) 처리된 항목은 목록에서 뺀다.
        # 실패한 항목은 원인을 보고 고칠 수 있도록 그대로 남겨둔다.
        for row in done_rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
            del self._rows[row.path]
        self._update_action_buttons()

        message = f"{registered}건 등록 완료"
        if skipped:
            message += f", {skipped}건 중복 건너뜀"
        if failed:
            message += "\n\n실패(목록에 남아있음):\n" + "\n".join(failed)
        QMessageBox.information(self, "등록 결과", message)

        if registered:
            self.upload_completed.emit()
