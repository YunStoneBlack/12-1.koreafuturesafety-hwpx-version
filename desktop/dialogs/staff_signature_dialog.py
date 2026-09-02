"""담당요원 서명 등록 모달 — SignaturePad로 그리거나 이미지 첨부 후 저장."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.db import BASE_DIR, SessionLocal
from core.models_db import Staff
from desktop.widgets.signature_pad import SignaturePad, move_or_reference


class StaffSignatureDialog(QDialog):
    def __init__(self, staff_id: int, staff_name: str, parent=None):
        super().__init__(parent)
        self._staff_id = staff_id
        self.setWindowTitle(f"{staff_name} 서명 등록")
        self._build_ui(staff_name)
        self._load_existing()

    def _build_ui(self, staff_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"{staff_name} 서명")
        title.setStyleSheet("font-size: 16px; font-weight: 700; border: none; background: transparent;")
        layout.addWidget(title)

        hint = QLabel("마우스로 그리거나 서명 이미지 파일을 첨부하세요. 한 번 등록하면 이 요원이 들어가는\n모든 보고서에 자동으로 반영됩니다.")
        hint.setStyleSheet("color: #6b7280; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(hint)

        self.pad = SignaturePad()
        layout.addWidget(self.pad)

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
            if staff and staff.signature_path:
                self.pad.load_existing(staff.signature_path)

    def _save(self) -> None:
        final_path = BASE_DIR / "data" / "signatures" / f"staff_{self._staff_id}.png"
        path = move_or_reference(self.pad, final_path)
        with SessionLocal() as session:
            staff = session.get(Staff, self._staff_id)
            if staff:
                staff.signature_path = path
                staff.signature_source = self.pad.source if path else ""
                session.commit()
        self.accept()
