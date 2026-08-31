"""iOS 스타일 on/off 토글 스위치. QCheckBox를 스타일시트로 토글 모양으로 그린다."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox

_STYLE = """
QCheckBox::indicator {
    width: 44px;
    height: 24px;
    border-radius: 12px;
    background-color: #d1d5db;
}
QCheckBox::indicator:checked {
    background-color: #4f46e5;
}
"""


class ToggleSwitch(QCheckBox):
    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLE)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
