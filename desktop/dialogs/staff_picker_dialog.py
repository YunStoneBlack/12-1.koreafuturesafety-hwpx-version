"""담당요원 선택 모달 — 등록된 담당요원 목록에서 하나를 골라 보고서에 배정한다."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from core.db import SessionLocal
from core.models_db import Staff


class StaffPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_staff_id: int | None = None
        self.setWindowTitle("담당요원 선택")
        self._build_ui()
        self._load_staff()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("담당요원 선택")
        title.setStyleSheet("font-size: 16px; font-weight: 700; border: none; background: transparent;")
        layout.addWidget(title)

        hint = QLabel("보고서에 배정할 담당요원을 선택하세요. 이름/연락처/서명이 함께 반영됩니다.")
        hint.setStyleSheet("color: #6b7280; font-size: 12px; border: none; background: transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._confirm())
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        select_btn = QPushButton("선택")
        select_btn.setStyleSheet("background: #2563eb; color: white; font-weight: 600;")
        select_btn.clicked.connect(self._confirm)
        btn_row.addWidget(select_btn)
        layout.addLayout(btn_row)

    def _load_staff(self) -> None:
        with SessionLocal() as session:
            staff_list = session.query(Staff).filter_by(active=True).order_by(Staff.name).all()
            for staff in staff_list:
                sig_mark = " ✓ 서명 등록됨" if staff.signature_path else " — 서명 미등록"
                item = QListWidgetItem(f"{staff.name} ({staff.phone}){sig_mark}")
                item.setData(Qt.ItemDataRole.UserRole, staff.id)
                self.list_widget.addItem(item)

    def _confirm(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        self.selected_staff_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
