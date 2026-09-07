"""현장 상세 화면 — '보고서 이력' / '현장 정보' 탭."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDate, QRegularExpression, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.db import SessionLocal
from core.models_db import Report, Site, Staff


def _fmt_amount(value: int | None) -> str:
    return f"{value:,}" if value is not None else "-"


def _fmt_date(value) -> str:
    return value.strftime("%Y.%m.%d") if value else "-"


class SiteDetailView(QWidget):
    back_requested = pyqtSignal()
    new_report_requested = pyqtSignal(int)
    edit_report_requested = pyqtSignal(int, int)  # site_id, report_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._site_id: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        back_btn = QPushButton("← 현장 목록")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        self.name_label = QLabel("")
        self.name_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.address_label = QLabel("")
        self.address_label.setStyleSheet("color: #6b7280;")
        header_text.addWidget(self.name_label)
        header_text.addWidget(self.address_label)
        header_row.addLayout(header_text)
        header_row.addStretch()

        new_report_btn = QPushButton("+ 새 보고서 작성")
        new_report_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; padding: 8px 16px; border-radius: 6px; }"
        )
        new_report_btn.clicked.connect(lambda: self.new_report_requested.emit(self._site_id))
        header_row.addWidget(new_report_btn)
        root.addLayout(header_row)

        self.tabs = QTabWidget()
        self.report_history_widget = self._build_report_history_tab()
        self.site_info_widget = self._build_site_info_tab()
        self.tabs.addTab(self.report_history_widget, "보고서 이력")
        self.tabs.addTab(self.site_info_widget, "현장 정보")
        root.addWidget(self.tabs)

    def _build_report_history_tab(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        note = QLabel("ⓘ 플랫폼에서 작성한 보고서만 수정이 가능합니다")
        note.setStyleSheet("color: #9ca3af; font-size: 12px;")
        layout.addWidget(note)
        self._history_list_layout = QVBoxLayout()
        layout.addLayout(self._history_list_layout)
        self._empty_label = QLabel("작성된 보고서가 없습니다.")
        self._empty_label.setStyleSheet("color: #9ca3af;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)
        layout.addStretch()
        return wrapper

    def _build_site_info_tab(self) -> QWidget:
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.info_edit_btn = QPushButton("✎ 정보 수정")
        self.info_edit_btn.clicked.connect(self._enter_site_info_edit_mode)
        self.info_save_btn = QPushButton("💾 저장")
        self.info_save_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; padding: 6px 14px; border-radius: 6px; }"
        )
        self.info_save_btn.clicked.connect(self._save_site_info)
        self.info_save_btn.setVisible(False)
        self.info_cancel_btn = QPushButton("취소")
        self.info_cancel_btn.clicked.connect(self._cancel_site_info_edit)
        self.info_cancel_btn.setVisible(False)
        btn_row.addWidget(self.info_edit_btn)
        btn_row.addWidget(self.info_save_btn)
        btn_row.addWidget(self.info_cancel_btn)
        outer.addLayout(btn_row)

        grid_frame = QFrame()
        self._info_grid = QGridLayout(grid_frame)
        self._info_grid.setHorizontalSpacing(24)
        self._info_grid.setVerticalSpacing(10)
        outer.addWidget(grid_frame)
        outer.addStretch()

        self._editing_site_info = False
        self._info_edit_widgets: dict[str, QWidget] = {}
        return wrapper

    def load_site(self, site_id: int) -> None:
        self._site_id = site_id
        with SessionLocal() as session:
            site = session.get(Site, site_id)
            if site is None:
                return
            self.name_label.setText(site.name or "(이름 없음)")
            self.address_label.setText(site.address or "")

            self._fill_site_info(site)

            reports = (
                session.query(Report).filter(Report.site_id == site_id).order_by(Report.visit_no).all()
            )
            self._fill_report_history(reports)
        self._set_info_edit_mode(False)

    def _fill_site_info(self, site: Site) -> None:
        while self._info_grid.count():
            item = self._info_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = [
            ("현장명", site.name, "공사기간", f"{_fmt_date(site.period_start)} ~ {_fmt_date(site.period_end)}"),
            ("공사금액(원)", _fmt_amount(site.amount), "사업장관리번호", site.site_mgmt_no),
            ("사업개시번호", site.biz_start_no, "현장소재지", site.address),
            ("총 기술지도횟수", str(site.total_guidance_count or "-"), "담당요원", site.assigned_staff.name if site.assigned_staff else "-"),
            ("현장책임자", site.manager_name, "책임자연락처", site.manager_phone),
            ("책임자이메일", site.manager_email, "건설업체명", site.hq_company),
            ("건설면허번호", site.license_no, "법인등록번호", site.corp_reg_no),
            ("사업자등록번호", site.biz_reg_no, "본사연락처", site.hq_phone),
            ("본사주소", site.hq_address, "", ""),
        ]
        for row_idx, (l1, v1, l2, v2) in enumerate(rows):
            self._add_info_cell(row_idx, 0, l1, v1)
            if l2:
                self._add_info_cell(row_idx, 2, l2, v2)

    def _add_info_cell(self, row: int, col: int, label: str, value: str | None) -> None:
        label_widget = QLabel(label)
        label_widget.setStyleSheet("color: #9ca3af; font-size: 11px;")
        value_widget = QLabel(value or "-")
        value_widget.setStyleSheet("font-size: 13px; font-weight: 600;")
        cell = QVBoxLayout()
        cell.setSpacing(2)
        cell.addWidget(label_widget)
        cell.addWidget(value_widget)
        cell_widget = QWidget()
        cell_widget.setLayout(cell)
        self._info_grid.addWidget(cell_widget, row, col)

    def _add_edit_cell(self, row: int, col: int, label: str, widget: QWidget, colspan: int = 1) -> None:
        label_widget = QLabel(label)
        label_widget.setStyleSheet("color: #9ca3af; font-size: 11px;")
        cell = QVBoxLayout()
        cell.setSpacing(2)
        cell.addWidget(label_widget)
        cell.addWidget(widget)
        cell_widget = QWidget()
        cell_widget.setLayout(cell)
        self._info_grid.addWidget(cell_widget, row, col, 1, colspan)

    def _set_info_edit_mode(self, editing: bool) -> None:
        self._editing_site_info = editing
        self.info_edit_btn.setVisible(not editing)
        self.info_save_btn.setVisible(editing)
        self.info_cancel_btn.setVisible(editing)

    def _enter_site_info_edit_mode(self) -> None:
        with SessionLocal() as session:
            site = session.get(Site, self._site_id)
            if site is None:
                return
            self._build_site_info_edit_form(site)
        self._set_info_edit_mode(True)

    def _cancel_site_info_edit(self) -> None:
        self.load_site(self._site_id)

    def _build_site_info_edit_form(self, site: Site) -> None:
        while self._info_grid.count():
            item = self._info_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        w: dict[str, QWidget] = {}

        def line(value: str | None) -> QLineEdit:
            return QLineEdit(value or "")

        for key, value in (
            ("name", site.name),
            ("site_mgmt_no", site.site_mgmt_no),
            ("biz_start_no", site.biz_start_no),
            ("address", site.address),
            ("manager_name", site.manager_name),
            ("manager_phone", site.manager_phone),
            ("manager_email", site.manager_email),
            ("hq_company", site.hq_company),
            ("license_no", site.license_no),
            ("corp_reg_no", site.corp_reg_no),
            ("biz_reg_no", site.biz_reg_no),
            ("hq_phone", site.hq_phone),
            ("hq_address", site.hq_address),
        ):
            w[key] = line(value)

        w["amount"] = QLineEdit(str(site.amount) if site.amount is not None else "")
        w["amount"].setPlaceholderText("숫자만 입력")
        w["amount"].setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9]*$")))

        w["total_guidance_count"] = QSpinBox()
        w["total_guidance_count"].setRange(0, 999)
        w["total_guidance_count"].setValue(site.total_guidance_count or 0)

        today = QDate.currentDate()
        w["period_start"] = QDateEdit()
        w["period_start"].setCalendarPopup(True)
        w["period_start"].setDisplayFormat("yyyy-MM-dd")
        w["period_start"].setDate(QDate(site.period_start) if site.period_start else today)
        w["period_end"] = QDateEdit()
        w["period_end"].setCalendarPopup(True)
        w["period_end"].setDisplayFormat("yyyy-MM-dd")
        w["period_end"].setDate(QDate(site.period_end) if site.period_end else today)
        period_row = QHBoxLayout()
        period_row.setContentsMargins(0, 0, 0, 0)
        period_row.addWidget(w["period_start"])
        period_row.addWidget(QLabel("~"))
        period_row.addWidget(w["period_end"])
        period_widget = QWidget()
        period_widget.setLayout(period_row)

        w["assigned_staff_id"] = QComboBox()
        w["assigned_staff_id"].addItem("선택 안 함", userData=None)
        with SessionLocal() as session:
            for staff in session.query(Staff).filter_by(active=True).all():
                w["assigned_staff_id"].addItem(f"{staff.name} ({staff.phone})", userData=staff.id)
        if site.assigned_staff_id:
            idx = w["assigned_staff_id"].findData(site.assigned_staff_id)
            if idx >= 0:
                w["assigned_staff_id"].setCurrentIndex(idx)

        self._info_edit_widgets = w

        self._add_edit_cell(0, 0, "현장명", w["name"])
        self._add_edit_cell(0, 2, "공사기간", period_widget)
        self._add_edit_cell(1, 0, "공사금액(원)", w["amount"])
        self._add_edit_cell(1, 2, "사업장관리번호", w["site_mgmt_no"])
        self._add_edit_cell(2, 0, "사업개시번호", w["biz_start_no"])
        self._add_edit_cell(2, 2, "현장소재지", w["address"])
        self._add_edit_cell(3, 0, "총 기술지도횟수", w["total_guidance_count"])
        self._add_edit_cell(3, 2, "담당요원", w["assigned_staff_id"])
        self._add_edit_cell(4, 0, "현장책임자", w["manager_name"])
        self._add_edit_cell(4, 2, "책임자연락처", w["manager_phone"])
        self._add_edit_cell(5, 0, "책임자이메일", w["manager_email"])
        self._add_edit_cell(5, 2, "건설업체명", w["hq_company"])
        self._add_edit_cell(6, 0, "건설면허번호", w["license_no"])
        self._add_edit_cell(6, 2, "법인등록번호", w["corp_reg_no"])
        self._add_edit_cell(7, 0, "사업자등록번호", w["biz_reg_no"])
        self._add_edit_cell(7, 2, "본사연락처", w["hq_phone"])
        self._add_edit_cell(8, 0, "본사주소", w["hq_address"], colspan=3)

    def _save_site_info(self) -> None:
        w = self._info_edit_widgets
        with SessionLocal() as session:
            site = session.get(Site, self._site_id)
            if site is None:
                return
            site.name = w["name"].text().strip()
            site.period_start = w["period_start"].date().toPyDate()
            site.period_end = w["period_end"].date().toPyDate()
            amount_text = w["amount"].text().strip()
            site.amount = int(amount_text) if amount_text else None
            site.site_mgmt_no = w["site_mgmt_no"].text().strip()
            site.biz_start_no = w["biz_start_no"].text().strip()
            site.address = w["address"].text().strip()
            site.total_guidance_count = w["total_guidance_count"].value() or None
            site.assigned_staff_id = w["assigned_staff_id"].currentData()
            site.manager_name = w["manager_name"].text().strip()
            site.manager_phone = w["manager_phone"].text().strip()
            site.manager_email = w["manager_email"].text().strip()
            site.hq_company = w["hq_company"].text().strip()
            site.license_no = w["license_no"].text().strip()
            site.corp_reg_no = w["corp_reg_no"].text().strip()
            site.biz_reg_no = w["biz_reg_no"].text().strip()
            site.hq_phone = w["hq_phone"].text().strip()
            site.hq_address = w["hq_address"].text().strip()
            session.commit()
        self.load_site(self._site_id)

    def _fill_report_history(self, reports: list[Report]) -> None:
        while self._history_list_layout.count():
            item = self._history_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._empty_label.setVisible(not reports)

        for report in reports:
            row = QFrame()
            row.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 13, 12, 13)  # 기본 대비 위아래 여백 1.2배(사용자 요청)
            status_text = "확정" if report.status == "final" else "작성 중"
            text = QLabel(
                f"{report.visit_no}회차 · {_fmt_date(report.guidance_date)} · 공정률 {report.progress_rate or 0}% · {status_text}"
            )
            # font-weight:700 — "1회차 · ... · 확정" 텍스트만 볼드 처리(사용자 요청)
            text.setStyleSheet("border: none; background: transparent; font-size: 15px; font-weight: 700;")
            row_layout.addWidget(text)
            row_layout.addStretch()

            _btn_font_style = "QPushButton { font-size: 15px; }"  # 버튼 글자도 같은 크기로(사용자 요청)

            edit_btn = QPushButton("✎ 수정")
            edit_btn.setStyleSheet(_btn_font_style)
            edit_btn.clicked.connect(
                lambda _checked, rid=report.id: self.edit_report_requested.emit(self._site_id, rid)
            )
            row_layout.addWidget(edit_btn)

            # 워드(DOCX)는 최신 실제 서식과 안 맞는 예전 산출물이라 목록에서 숨긴다(사용자 요청).
            for label, path in (("한글", report.hwpx_path), ("PDF", report.pdf_path)):
                btn = QPushButton(f"↓ {label}")
                btn.setStyleSheet(_btn_font_style)
                btn.setEnabled(bool(path and Path(path).exists()))
                btn.clicked.connect(lambda _checked, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                row_layout.addWidget(btn)

            delete_btn = QPushButton("🗑 삭제")
            delete_btn.setStyleSheet(_btn_font_style)
            delete_btn.clicked.connect(lambda _checked, rid=report.id: self._delete_report(rid))
            row_layout.addWidget(delete_btn)

            self._history_list_layout.addWidget(row)

    def _delete_report(self, report_id: int) -> None:
        reply = QMessageBox.question(self, "보고서 삭제", "이 보고서를 삭제하시겠습니까?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as session:
            report = session.get(Report, report_id)
            if report:
                session.delete(report)
                session.commit()
        self.load_site(self._site_id)
