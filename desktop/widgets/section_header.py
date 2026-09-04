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

    def __init__(
        self,
        number: int | None,
        title: str,
        required: bool = True,
        show_na_button: bool = True,
        parent=None,
    ):
        """`number`가 None이면 번호 배지를 안 그린다 — 큰 섹션의 하위 항목(예: "5-3. ...")처럼
        독립된 번호가 아니라 상위 섹션에 속한 소제목으로 표시하고 싶을 때 쓴다(해당사항없음
        토글은 그대로 유지).

        `show_na_button=False`면 '해당사항없음' 버튼을 화면에 안 보이게 숨긴다 — 버튼 자체는
        그대로 만들어두므로 `na_button.isChecked()`/`set_checked()`를 쓰는 저장·불러오기
        로직(예: 9번/9-1/9-2)은 그대로 동작한다."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if number is not None:
            badge = QLabel(str(number))
            badge.setFixedSize(24, 24)
            badge.setStyleSheet(
                "background: #4f46e5; color: white; border-radius: 12px; font-weight: 600;"
            )
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(badge)

        # margin-left는 배지와 제목 사이 간격용이라 배지가 없을 때(number=None, 예: "5-3.")는
        # 빼야 상위 소제목(예: "5-1.", "5-2.")과 왼쪽 시작선이 맞는다(사용자 요청으로 확인됨).
        title_margin = "margin-left: 6px; " if number is not None else ""
        title_text = title + (" •" if required else "")
        title_label = QLabel(title_text)
        title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; {title_margin}border: none; background: transparent;"
        )
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
        self.na_button.setVisible(show_na_button)
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
