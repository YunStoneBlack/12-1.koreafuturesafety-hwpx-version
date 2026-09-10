"""마법사 5번 "이전지적사항" 한 칸 위젯 — `report_wizard_slots.py`에서 분리됨(638줄을
넘겨 이 프로젝트 관례상 600줄 기준으로 나눴다, 2026-09-08).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from desktop.widgets.photo_drop_zone import PhotoDropZone
from desktop.widgets.report_wizard_slots import _action_status_style


class _PreviousFindingSlot(QFrame):
    """5. 이전지적사항 한 건 — 직전 회차 지적사항을 이월받거나 수기로 추가."""

    def __init__(self, slot: int):
        super().__init__()
        self.slot = slot
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        layout = QVBoxLayout(self)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(f"이전지적사항 {slot}"))
        title_row.addStretch()
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedWidth(32)
        self.delete_btn.clicked.connect(self._delete)
        title_row.addWidget(self.delete_btn)
        layout.addLayout(title_row)

        body_row = QHBoxLayout()
        self.photo = PhotoDropZone(f"이전지적사항 {slot} 사진")
        body_row.addWidget(self.photo)

        form_col = QVBoxLayout()
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("지적사항 제목")
        form_col.addWidget(self.title_input)
        self.content_edit = QTextEdit()
        self.content_edit.setFixedHeight(50)
        form_col.addWidget(self.content_edit)
        action_row = QHBoxLayout()
        result_label = QLabel("이행결과")
        result_label.setStyleSheet("border: none; background: transparent;")
        action_row.addWidget(result_label)
        self.result_status_buttons = QButtonGroup(self)
        self.result_status_buttons.setExclusive(True)
        for status in ("확인불가", "보완필요", "이행완료"):
            btn = QPushButton(status)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_action_status_style(False))
            btn.toggled.connect(self._on_result_status_toggled)
            self.result_status_buttons.addButton(btn)
            action_row.addWidget(btn)
        form_col.addLayout(action_row)
        body_row.addLayout(form_col, stretch=1)

        self.completion_photo = PhotoDropZone(f"이전지적사항 {slot} 이행완료 사진")
        body_row.addWidget(self.completion_photo)
        layout.addLayout(body_row)

        self._active = False
        self.source_finding_id: int | None = None
        self.setVisible(False)

    def _on_result_status_toggled(self, checked: bool) -> None:
        btn = self.sender()
        if checked and btn.text() == "이행완료" and not self.photo.photo_path:
            reply = QMessageBox.question(
                self,
                "사진 없음",
                "이 지적사항에는 사진이 없습니다. 사진 없이 이행완료로 처리하시겠습니까?\n"
                "(취소를 누르고 사진을 직접 업로드할 수도 있습니다.)",
            )
            if reply != QMessageBox.StandardButton.Yes:
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                return
        for b in self.result_status_buttons.buttons():
            b.setStyleSheet(_action_status_style(b.isChecked()))

    def result_status(self) -> str:
        checked = self.result_status_buttons.checkedButton()
        return checked.text() if checked else ""

    def set_result_status(self, status: str) -> None:
        for btn in self.result_status_buttons.buttons():
            btn.setChecked(btn.text() == status)

    def _delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            "정말로 삭제하시겠습니까?\n사진과 입력한 내용이 모두 지워지며 되돌릴 수 없습니다.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.clear()
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setVisible(active)

    def is_active(self) -> bool:
        return self._active

    def clear(self) -> None:
        """슬롯 위젯을 재사용하기 전(비활성화·리셋 시) 이전 사진/입력값을 지운다.

        `set_active(False)`만으로는 위젯이 숨겨질 뿐 사진(`PhotoDropZone`)·입력 필드는
        그대로 남아있어, 나중에 이 슬롯이 다시 활성화되면(예: "+ 추가" 버튼, 새 보고서
        작성 시 리셋) 이전 회차/이전 보고서의 사진이 그대로 다시 보이는 문제가 있었다.
        """
        self.photo.clear_photo()
        self.completion_photo.clear_photo()
        self.title_input.clear()
        self.content_edit.clear()
        self.set_result_status("")
        self.source_finding_id = None
