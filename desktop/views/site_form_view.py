"""신규 현장 추가 화면 — 계약서 PDF 업로드 → AI 자동 인식 → 폼 자동 채움 → 저장."""

from __future__ import annotations

import datetime

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.contract_analyzer import extract_site_info
from core.db import SessionLocal
from core.models_db import Site, Staff
from desktop.workers.ai_worker import AIWorker


class _PdfUploadRow(QFrame):
    """계약서·공문 PDF 업로드 줄 — 클릭해서 고르는 것 외에 드래그앤드롭도 받는다(사용자 요청)."""

    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.lower().endswith(".pdf"):
            self.file_dropped.emit(path)


def _date_edit() -> QDateEdit:
    widget = QDateEdit()
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("yyyy-MM-dd")
    widget.setDate(QDate.currentDate())
    return widget


class SiteFormView(QWidget):
    back_requested = pyqtSignal()
    site_saved = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: AIWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        back_btn = QPushButton("← 현장 목록")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("신규 현장 추가")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        desc = QLabel("계약서 또는 공문 PDF를 올리면, AI가 현장 정보를 읽어 아래 항목에 자동으로 입력합니다.")
        desc.setStyleSheet("color: #6b7280;")
        root.addWidget(desc)

        upload_frame = _PdfUploadRow()
        upload_frame.setStyleSheet(
            "QFrame { border: 2px dashed #c7c7d1; border-radius: 8px; background: #fafafa; }"
        )
        upload_frame.file_dropped.connect(self._on_file_dropped)
        upload_row = QHBoxLayout(upload_frame)
        upload_row.setContentsMargins(12, 10, 12, 10)
        self.file_label = QLabel("선택된 파일 없음 (여기로 드래그하거나 파일 선택)")
        self.file_label.setStyleSheet("color: #6b7280; border: none; background: transparent;")
        pick_btn = QPushButton("파일 선택")
        pick_btn.clicked.connect(self._pick_file)
        upload_row.addWidget(self.file_label)
        upload_row.addStretch()
        upload_row.addWidget(pick_btn)
        root.addWidget(upload_frame)

        self.ai_status_label = QLabel("")
        self.ai_status_label.setStyleSheet("color: #4f46e5;")
        root.addWidget(self.ai_status_label)

        root.addWidget(self._build_form())

        save_row = QHBoxLayout()
        save_row.addStretch()
        save_btn = QPushButton("✓ 현장 저장")
        save_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; padding: 10px 24px; border-radius: 6px; }"
        )
        save_btn.clicked.connect(self._save_site)
        save_row.addWidget(save_btn)
        root.addLayout(save_row)
        root.addStretch()

    def _build_form(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }")
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 18, 20, 18)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        row = 0

        def add_section(label: str) -> None:
            nonlocal row
            section_label = QLabel(label)
            section_label.setStyleSheet("font-weight: 700; margin-top: 8px;")
            grid.addWidget(section_label, row, 0, 1, 4)
            row += 1

        def add_pair(label1: str, widget1: QWidget, label2: str, widget2: QWidget) -> None:
            nonlocal row
            grid.addWidget(QLabel(label1), row, 0)
            grid.addWidget(widget1, row, 1)
            grid.addWidget(QLabel(label2), row, 2)
            grid.addWidget(widget2, row, 3)
            row += 1

        add_section("현장")
        self.name_input = QLineEdit()
        self.site_mgmt_no_input = QLineEdit()
        add_pair("현장명", self.name_input, "사업장관리번호", self.site_mgmt_no_input)

        self.biz_start_no_input = QLineEdit()
        add_pair("", QLabel(""), "사업개시번호", self.biz_start_no_input)

        self.period_start_input = _date_edit()
        self.period_end_input = _date_edit()
        period_row = QHBoxLayout()
        period_row.addWidget(self.period_start_input)
        period_row.addWidget(QLabel("~"))
        period_row.addWidget(self.period_end_input)
        period_widget = QWidget()
        period_widget.setLayout(period_row)
        grid.addWidget(QLabel("공사기간"), row, 0)
        grid.addWidget(period_widget, row, 1, 1, 3)
        row += 1

        self.manager_name_input = QLineEdit()
        self.manager_phone_input = QLineEdit()
        self.manager_phone_input.setPlaceholderText("핸드폰 번호")
        self.manager_email_input = QLineEdit()
        self.manager_email_input.setPlaceholderText("이메일")
        contact_row = QHBoxLayout()
        contact_row.setContentsMargins(0, 0, 0, 0)
        contact_row.addWidget(self.manager_phone_input)
        contact_row.addWidget(self.manager_email_input)
        contact_widget = QWidget()
        contact_widget.setLayout(contact_row)
        add_pair("책임자", self.manager_name_input, "연락처(이메일)", contact_widget)

        self.address_input = QLineEdit()
        grid.addWidget(QLabel("주소"), row, 0)
        grid.addWidget(self.address_input, row, 1, 1, 3)
        row += 1

        add_section("본사")
        self.hq_company_input = QLineEdit()
        self.corp_reg_no_input = QLineEdit()
        add_pair("회사명", self.hq_company_input, "법인등록번호", self.corp_reg_no_input)

        self.biz_reg_no_input = QLineEdit()
        add_pair("", QLabel(""), "사업자등록번호", self.biz_reg_no_input)

        self.license_no_input = QLineEdit()
        self.hq_phone_input = QLineEdit()
        add_pair("면허번호", self.license_no_input, "연락처", self.hq_phone_input)

        self.hq_address_input = QLineEdit()
        grid.addWidget(QLabel("주소"), row, 0)
        grid.addWidget(self.hq_address_input, row, 1, 1, 3)
        row += 1

        add_section("기타")
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("숫자만 입력")
        self.amount_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9]*$")))
        self.guidance_count_input = QSpinBox()
        self.guidance_count_input.setRange(0, 999)
        add_pair("공사금액(원)", self.amount_input, "기술지도 총 횟수", self.guidance_count_input)

        self.staff_combo = QComboBox()
        self._reload_staff_combo()
        grid.addWidget(QLabel("담당요원"), row, 0)
        grid.addWidget(self.staff_combo, row, 1, 1, 3)
        row += 1

        return card

    def reset(self) -> None:
        self._worker = None
        self.file_label.setText("선택된 파일 없음")
        self.ai_status_label.setText("")
        for field in (
            self.name_input,
            self.site_mgmt_no_input,
            self.biz_start_no_input,
            self.manager_name_input,
            self.manager_phone_input,
            self.manager_email_input,
            self.address_input,
            self.hq_company_input,
            self.corp_reg_no_input,
            self.biz_reg_no_input,
            self.license_no_input,
            self.hq_phone_input,
            self.hq_address_input,
            self.amount_input,
        ):
            field.clear()
        today = QDate.currentDate()
        self.period_start_input.setDate(today)
        self.period_end_input.setDate(today)
        self.guidance_count_input.setValue(0)
        self._reload_staff_combo()

    def _reload_staff_combo(self) -> None:
        self.staff_combo.clear()
        self.staff_combo.addItem("선택 안 함", userData=None)
        with SessionLocal() as session:
            for staff in session.query(Staff).filter_by(active=True).all():
                self.staff_combo.addItem(f"{staff.name} ({staff.phone})", userData=staff.id)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "계약서·공문 PDF 선택", "", "PDF 파일 (*.pdf)")
        if not file_path:
            return
        self._on_file_dropped(file_path)

    def _on_file_dropped(self, file_path: str) -> None:
        self.file_label.setText(file_path.split("/")[-1])
        self._run_ai_extraction(file_path)

    def _run_ai_extraction(self, file_path: str) -> None:
        if not config.has_api_key():
            self.ai_status_label.setText("Claude API 키가 설정되어 있지 않습니다. 'AI 관리' 화면에서 먼저 등록하세요.")
            return

        self.ai_status_label.setText("AI가 문서를 분석하고 있습니다... (약 20초 소요)")
        self._worker = AIWorker(lambda: extract_site_info(file_path))
        self._worker.finished_ok.connect(self._on_extraction_done)
        self._worker.finished_error.connect(self._on_extraction_failed)
        self._worker.start()

    def _on_extraction_done(self, data: dict) -> None:
        self.ai_status_label.setText("AI 자동 인식이 완료되었습니다. 내용을 확인·수정한 뒤 저장하세요.")
        self.name_input.setText(data.get("name") or "")
        self.site_mgmt_no_input.setText(data.get("site_mgmt_no") or "")
        self.biz_start_no_input.setText(data.get("biz_start_no") or "")
        self.address_input.setText(data.get("address") or "")
        self.manager_name_input.setText(data.get("manager_name") or "")
        self.manager_phone_input.setText(data.get("manager_phone") or "")
        self.manager_email_input.setText(data.get("manager_email") or "")
        self.hq_company_input.setText(data.get("hq_company") or "")
        self.corp_reg_no_input.setText(data.get("corp_reg_no") or "")
        self.biz_reg_no_input.setText(data.get("biz_reg_no") or "")
        self.license_no_input.setText(data.get("license_no") or "")
        self.hq_phone_input.setText(data.get("hq_phone") or "")
        self.hq_address_input.setText(data.get("hq_address") or "")
        self.amount_input.setText(str(data.get("amount")) if data.get("amount") else "")
        self.guidance_count_input.setValue(data.get("total_guidance_count") or 0)

        for date_field, widget in (
            (data.get("period_start"), self.period_start_input),
            (data.get("period_end"), self.period_end_input),
        ):
            if date_field:
                try:
                    parsed = datetime.date.fromisoformat(date_field)
                    widget.setDate(QDate(parsed.year, parsed.month, parsed.day))
                except ValueError:
                    pass

    def _on_extraction_failed(self, message: str) -> None:
        self.ai_status_label.setText(f"AI 분석에 실패했습니다: {message}")

    def _save_site(self) -> None:
        with SessionLocal() as session:
            site = Site(
                name=self.name_input.text().strip(),
                address=self.address_input.text().strip(),
                period_start=self.period_start_input.date().toPyDate(),
                period_end=self.period_end_input.date().toPyDate(),
                amount=int(self.amount_input.text()) if self.amount_input.text() else None,
                site_mgmt_no=self.site_mgmt_no_input.text().strip(),
                biz_start_no=self.biz_start_no_input.text().strip(),
                manager_name=self.manager_name_input.text().strip(),
                manager_phone=self.manager_phone_input.text().strip(),
                manager_email=self.manager_email_input.text().strip(),
                hq_company=self.hq_company_input.text().strip(),
                corp_reg_no=self.corp_reg_no_input.text().strip(),
                biz_reg_no=self.biz_reg_no_input.text().strip(),
                license_no=self.license_no_input.text().strip(),
                hq_phone=self.hq_phone_input.text().strip(),
                hq_address=self.hq_address_input.text().strip(),
                total_guidance_count=self.guidance_count_input.value() or None,
                assigned_staff_id=self.staff_combo.currentData(),
            )
            session.add(site)
            session.commit()
            site_id = site.id
        self.site_saved.emit(site_id)
