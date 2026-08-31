"""담당요원 관리 화면 — 등록하면 신규현장추가/보고서작성의 담당요원 드롭다운에 반영된다."""

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

from core.db import SessionLocal
from core.models_db import Staff


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

        title = QLabel("담당요원 관리")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        add_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("이름")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("연락처")
        add_btn = QPushButton("+ 추가")
        add_btn.clicked.connect(self._add_staff)
        add_row.addWidget(self.name_input)
        add_row.addWidget(self.phone_input)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        self._list_layout = QVBoxLayout()
        root.addLayout(self._list_layout)
        root.addStretch()

    def reload(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        with SessionLocal() as session:
            staff_list = session.query(Staff).order_by(Staff.name).all()

        for staff in staff_list:
            row = QFrame()
            row.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }")
            row_layout = QHBoxLayout(row)
            label = QLabel(f"{staff.name} ({staff.phone})" + ("" if staff.active else " — 비활성"))
            row_layout.addWidget(label)
            row_layout.addStretch()

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
            session.add(Staff(name=name, phone=self.phone_input.text().strip()))
            session.commit()
        self.name_input.clear()
        self.phone_input.clear()
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
