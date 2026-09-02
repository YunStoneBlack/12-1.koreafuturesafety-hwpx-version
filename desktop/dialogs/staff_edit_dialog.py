"""담당요원 정보 수정 모달 — 이름/연락처만 수정한다(서명은 StaffSignatureDialog에서 별도 관리)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.db import SessionLocal
from core.models_db import Staff


class StaffEditDialog(QDialog):
    def __init__(self, staff_id: int, staff_name: str, parent=None):
        super().__init__(parent)
        self._staff_id = staff_id
        self.setWindowTitle(f"{staff_name} 정보 수정")
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("담당요원 정보 수정")
        title.setStyleSheet("font-size: 16px; font-weight: 700; border: none; background: transparent;")
        layout.addWidget(title)

        name_label = QLabel("이름")
        name_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(name_label)
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        phone_label = QLabel("연락처")
        phone_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(phone_label)
        self.phone_input = QLineEdit()
        layout.addWidget(self.phone_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("저장")
        save_btn.setStyleSheet("background: #2563eb; color: white; font-weight: 600;")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _load_existing(self) -> None:
        with SessionLocal() as session:
            staff = session.get(Staff, self._staff_id)
            if staff:
                self.name_input.setText(staff.name)
                self.phone_input.setText(staff.phone)

    def _save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "이름 필요", "담당요원 이름을 입력하세요.")
            return
        with SessionLocal() as session:
            staff = session.get(Staff, self._staff_id)
            if staff:
                staff.name = name
                staff.phone = self.phone_input.text().strip()
                session.commit()
        self.accept()
