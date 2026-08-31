"""보고서 작성 마법사의 각 섹션(전경사진, 안전교육 등)에 공통으로 쓰이는 헤더.

번호 배지 + 제목(+필수 표시) + 우측 '해당사항없음' 토글 버튼.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

_NA_STYLE_OFF = (
    "QPushButton { background: white; color: #6b7280; border: 1px solid #d1d5db; "
    "border-radius: 14px; padding: 4px 14px; }"
)
_NA_STYLE_ON = (
    "QPushButton { background: #4f46e5; color: white; border: 1px solid #4f46e5; "
    "border-radius: 14px; padding: 4px 14px; }"
)


class SectionHeader(QWidget):
    na_toggled = pyqtSignal(bool)

    def __init__(self, number: int, title: str, required: bool = True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        badge = QLabel(str(number))
        badge.setFixedSize(24, 24)
        badge.setStyleSheet(
            "background: #4f46e5; color: white; border-radius: 12px; font-weight: 600;"
        )
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)

        title_text = title + (" •" if required else "")
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-size: 15px; font-weight: 700; margin-left: 6px;")
        layout.addWidget(title_label)
        layout.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(
            "background: white; color: #6b7280; border: 1px solid #d1d5db; "
            "border-radius: 12px; padding: 3px 10px; font-size: 12px; margin-right: 6px;"
        )
        self.count_label.setVisible(False)
        layout.addWidget(self.count_label)

        self.na_button = QPushButton("해당사항없음")
        self.na_button.setCheckable(True)
        self.na_button.setStyleSheet(_NA_STYLE_OFF)
        self.na_button.toggled.connect(self._on_toggled)
        layout.addWidget(self.na_button)

    def _on_toggled(self, checked: bool) -> None:
        self.na_button.setText("✓ 해당사항없음" if checked else "해당사항없음")
        self.na_button.setStyleSheet(_NA_STYLE_ON if checked else _NA_STYLE_OFF)
        self.na_toggled.emit(checked)

    def set_checked(self, checked: bool) -> None:
        self.na_button.setChecked(checked)

    def set_count(self, current: int, total: int) -> None:
        self.count_label.setText(f"{current} / {total} 채움")
        self.count_label.setVisible(True)
