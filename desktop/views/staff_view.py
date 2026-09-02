"""담당요원 및 서명관리 화면 — 담당요원 등록/서명(요원별)과 결재선(이사/대표이사) 서명을 함께 관리한다.

담당요원을 등록하면 신규현장추가/보고서작성의 담당요원 드롭다운에 반영된다.
결재선 서명은 한 번 등록하면 모든 보고서에 자동으로 반영된다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.db import BASE_DIR, SessionLocal
from core.models_db import Staff
from desktop.dialogs.staff_edit_dialog import StaffEditDialog
from desktop.dialogs.staff_signature_dialog import StaffSignatureDialog
from desktop.widgets.signature_pad import SignaturePad, move_or_reference


class StaffView(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)

        back_btn = QPushButton("← 뒤로")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("담당요원 및 서명관리")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        staff_section = QLabel("담당요원")
        staff_section.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 10px;")
        root.addWidget(staff_section)

        add_card = QFrame()
        add_card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }")
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(20, 18, 20, 18)
        add_layout.setSpacing(10)

        info_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("이름")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("연락처")
        info_row.addWidget(self.name_input)
        info_row.addWidget(self.phone_input)
        add_layout.addLayout(info_row)

        new_sig_label = QLabel("서명")
        new_sig_label.setStyleSheet("font-weight: 600; border: none; background: transparent;")
        add_layout.addWidget(new_sig_label)
        self.new_staff_pad = SignaturePad()
        add_layout.addWidget(self.new_staff_pad)

        add_btn = QPushButton("+ 추가")
        add_btn.clicked.connect(self._add_staff)
        add_layout.addWidget(add_btn)

        root.addWidget(add_card)

        self._list_layout = QVBoxLayout()
        root.addLayout(self._list_layout)

        sig_section = QLabel("결재선 서명")
        sig_section.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 10px;")
        root.addWidget(sig_section)

        sig_card = QFrame()
        sig_card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }")
        sig_layout = QVBoxLayout(sig_card)
        sig_layout.setContentsMargins(20, 18, 20, 18)
        sig_layout.setSpacing(10)

        sig_desc = QLabel("결재란(이사/대표이사) 서명을 한 번 등록하면 모든 보고서에 자동으로 반영됩니다.")
        sig_desc.setStyleSheet("color: #6b7280; border: none; background: transparent;")
        sig_layout.addWidget(sig_desc)

        sig_row = QHBoxLayout()

        director_col = QVBoxLayout()
        director_label = QLabel("이사")
        director_label.setStyleSheet("font-weight: 600; border: none; background: transparent;")
        director_col.addWidget(director_label)
        self.director_pad = SignaturePad()
        director_col.addWidget(self.director_pad)
        director_save = QPushButton("저장")
        director_save.clicked.connect(lambda: self._save_company_signature("director"))
        director_col.addWidget(director_save)
        self.director_status_label = QLabel("")
        self.director_status_label.setStyleSheet("border: none; background: transparent;")
        director_col.addWidget(self.director_status_label)
        sig_row.addLayout(director_col)

        ceo_col = QVBoxLayout()
        ceo_label = QLabel("대표이사")
        ceo_label.setStyleSheet("font-weight: 600; border: none; background: transparent;")
        ceo_col.addWidget(ceo_label)
        self.ceo_pad = SignaturePad()
        ceo_col.addWidget(self.ceo_pad)
        ceo_save = QPushButton("저장")
        ceo_save.clicked.connect(lambda: self._save_company_signature("ceo"))
        ceo_col.addWidget(ceo_save)
        self.ceo_status_label = QLabel("")
        self.ceo_status_label.setStyleSheet("border: none; background: transparent;")
        ceo_col.addWidget(self.ceo_status_label)
        sig_row.addLayout(ceo_col)

        sig_layout.addLayout(sig_row)

        self.director_pad.signature_changed.connect(
            lambda path: self._on_signature_changed("director", path)
        )
        self.ceo_pad.signature_changed.connect(lambda path: self._on_signature_changed("ceo", path))

        root.addWidget(sig_card)
        root.addStretch()

    def reload(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        with SessionLocal() as session:
            staff_list = session.query(Staff).order_by(Staff.name).all()

        director_path, _ = config.get_company_signature("director")
        if director_path:
            self.director_pad.load_existing(director_path)
        self._set_signature_status(self.director_status_label, bool(director_path))
        ceo_path, _ = config.get_company_signature("ceo")
        if ceo_path:
            self.ceo_pad.load_existing(ceo_path)
        self._set_signature_status(self.ceo_status_label, bool(ceo_path))

        for staff in staff_list:
            row = QFrame()
            row.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }")
            row_layout = QHBoxLayout(row)
            label = QLabel(f"{staff.name} ({staff.phone})" + ("" if staff.active else " — 비활성"))
            row_layout.addWidget(label)
            if staff.signature_path:
                sig_badge = QLabel("✓ 서명 등록됨")
                sig_badge.setStyleSheet("color: #16a34a; font-size: 12px;")
                row_layout.addWidget(sig_badge)
            row_layout.addStretch()

            edit_btn = QPushButton("수정")
            edit_btn.clicked.connect(
                lambda _checked, sid=staff.id, name=staff.name: self._edit_staff(sid, name)
            )
            row_layout.addWidget(edit_btn)

            sig_btn = QPushButton("서명 등록")
            sig_btn.clicked.connect(
                lambda _checked, sid=staff.id, name=staff.name: self._edit_signature(sid, name)
            )
            row_layout.addWidget(sig_btn)

            toggle_btn = QPushButton("비활성화" if staff.active else "활성화")
            toggle_btn.clicked.connect(lambda _checked, sid=staff.id: self._toggle_active(sid))
            row_layout.addWidget(toggle_btn)

            delete_btn = QPushButton("🗑 삭제")
            delete_btn.clicked.connect(lambda _checked, sid=staff.id: self._delete_staff(sid))
            row_layout.addWidget(delete_btn)

            self._list_layout.addWidget(row)

    def _add_staff(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "이름 필요", "담당요원 이름을 입력하세요.")
            return
        with SessionLocal() as session:
            staff = Staff(name=name, phone=self.phone_input.text().strip())
            session.add(staff)
            session.flush()
            if self.new_staff_pad.has_signature():
                final_path = BASE_DIR / "data" / "signatures" / f"staff_{staff.id}.png"
                path = move_or_reference(self.new_staff_pad, final_path)
                staff.signature_path = path
                staff.signature_source = self.new_staff_pad.source if path else ""
            session.commit()
        self.name_input.clear()
        self.phone_input.clear()
        self.new_staff_pad.clear_signature()
        self.reload()

    def _edit_staff(self, staff_id: int, staff_name: str) -> None:
        dialog = StaffEditDialog(staff_id, staff_name, self)
        if dialog.exec():
            self.reload()

    def _edit_signature(self, staff_id: int, staff_name: str) -> None:
        dialog = StaffSignatureDialog(staff_id, staff_name, self)
        if dialog.exec():
            self.reload()

    def _toggle_active(self, staff_id: int) -> None:
        with SessionLocal() as session:
            staff = session.get(Staff, staff_id)
            if staff:
                staff.active = not staff.active
                session.commit()
        self.reload()

    def _delete_staff(self, staff_id: int) -> None:
        reply = QMessageBox.question(
            self, "담당요원 삭제", "삭제하시겠습니까? 이미 배정된 현장/보고서에서는 담당요원이 빈 값으로 표시됩니다."
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as session:
            staff = session.get(Staff, staff_id)
            if staff:
                session.delete(staff)
                session.commit()
        self.reload()

    def _save_company_signature(self, role: str) -> None:
        pad = self.director_pad if role == "director" else self.ceo_pad
        status_label = self.director_status_label if role == "director" else self.ceo_status_label
        final_path = BASE_DIR / "data" / "signatures" / f"company_{role}.png"
        path = move_or_reference(pad, final_path)
        config.set_company_signature(role, path, pad.source if path else "")
        self._set_signature_status(status_label, bool(path))

    def _on_signature_changed(self, role: str, path: str) -> None:
        if path:
            return
        status_label = self.director_status_label if role == "director" else self.ceo_status_label
        self._set_signature_status(status_label, False)

    def _set_signature_status(self, label: QLabel, saved: bool) -> None:
        if saved:
            label.setText("서명이 저장되었습니다.")
            label.setStyleSheet("color: #16a34a; border: none; background: transparent;")
        else:
            label.setText("서명을 등록해주세요.")
            label.setStyleSheet("color: #ef4444; border: none; background: transparent;")
