"""현장 상세 화면 — '보고서 이력' / '현장 정보' 탭."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.db import SessionLocal
from core.models_db import Report, Site


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
        grid_frame = QFrame()
        self._info_grid = QGridLayout(grid_frame)
        self._info_grid.setHorizontalSpacing(24)
        self._info_grid.setVerticalSpacing(10)
        outer.addWidget(grid_frame)
        outer.addStretch()
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
            status_text = "확정" if report.status == "final" else "작성 중"
            text = QLabel(
                f"{report.visit_no}회차 · {_fmt_date(report.guidance_date)} · 공정률 {report.progress_rate or 0}% · {status_text}"
            )
            row_layout.addWidget(text)
            row_layout.addStretch()

            edit_btn = QPushButton("✎ 수정")
            edit_btn.clicked.connect(
                lambda _checked, rid=report.id: self.edit_report_requested.emit(self._site_id, rid)
            )
            row_layout.addWidget(edit_btn)

            for label, path in (("한글", report.hwpx_path), ("워드", report.docx_path), ("PDF", report.pdf_path)):
                btn = QPushButton(f"↓ {label}")
                btn.setEnabled(bool(path and Path(path).exists()))
                btn.clicked.connect(lambda _checked, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                row_layout.addWidget(btn)

            delete_btn = QPushButton("🗑 삭제")
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
