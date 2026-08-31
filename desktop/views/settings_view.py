"""AI 관리 화면 — Claude API 키 입력/저장, AI 기능 전체 on/off.

배포된 프로그램을 쓰는 각 사용자가 자기 API 키를 여기서 로컬에 저장한다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import config
from desktop.widgets.toggle_switch import ToggleSwitch

_CONSOLE_KEYS_URL = "https://console.anthropic.com/settings/keys"
_LAW_API_URL = "https://open.law.go.kr/LSO/main.do"


class SettingsView(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)

        back_btn = QPushButton("← 뒤로")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("AI 관리")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        subtitle = QLabel("Claude API 키 및 AI 기능 설정을 관리합니다.")
        subtitle.setStyleSheet("color: #6b7280;")
        root.addWidget(subtitle)

        section = QLabel("Claude API 설정")
        section.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 10px;")
        root.addWidget(section)

        card = QFrame()
        card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(14)

        key_label = QLabel("API 키")
        key_label.setStyleSheet("font-weight: 600;")
        card_layout.addWidget(key_label)

        desc_row = QHBoxLayout()
        desc = QLabel("Anthropic Console에서 발급받은 Claude API 키를 입력하세요.")
        desc.setStyleSheet("color: #6b7280;")
        link = QPushButton("키 발급받기 →")
        link.setFlat(True)
        link.setStyleSheet("color: #4f46e5; text-align: left;")
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_CONSOLE_KEYS_URL)))
        desc_row.addWidget(desc)
        desc_row.addWidget(link)
        desc_row.addStretch()
        card_layout.addLayout(desc_row)

        input_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("sk-ant-...")
        self.toggle_visibility_btn = QPushButton("👁")
        self.toggle_visibility_btn.setFixedWidth(36)
        self.toggle_visibility_btn.clicked.connect(self._toggle_visibility)
        self.save_btn = QPushButton("저장")
        self.save_btn.setStyleSheet(
            "QPushButton { background: #3b2f2a; color: white; padding: 8px 18px; border-radius: 6px; }"
        )
        self.save_btn.clicked.connect(self._save_key)
        input_row.addWidget(self.key_input)
        input_row.addWidget(self.toggle_visibility_btn)
        input_row.addWidget(self.save_btn)
        card_layout.addLayout(input_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #16a34a;")
        card_layout.addWidget(self.status_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #e5e7eb;")
        card_layout.addWidget(divider)

        toggle_row = QHBoxLayout()
        toggle_text = QVBoxLayout()
        ai_label = QLabel("AI 기능 사용")
        ai_label.setStyleSheet("font-weight: 600;")
        ai_desc = QLabel("AI 기능 전체를 활성화하거나 비활성화합니다.")
        ai_desc.setStyleSheet("color: #6b7280;")
        toggle_text.addWidget(ai_label)
        toggle_text.addWidget(ai_desc)
        toggle_row.addLayout(toggle_text)
        toggle_row.addStretch()
        self.ai_enabled_toggle = ToggleSwitch()
        self.ai_enabled_toggle.toggled.connect(self._on_ai_enabled_toggled)
        toggle_row.addWidget(self.ai_enabled_toggle)
        card_layout.addLayout(toggle_row)

        root.addWidget(card)

        law_section = QLabel("법령 검색 API 설정 (선택)")
        law_section.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 10px;")
        root.addWidget(law_section)

        law_card = QFrame()
        law_card.setStyleSheet("QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }")
        law_layout = QVBoxLayout(law_card)
        law_layout.setContentsMargins(20, 18, 20, 18)
        law_layout.setSpacing(10)

        law_desc_row = QHBoxLayout()
        law_desc = QLabel("지적사항 법령 검색에 쓰이는 국가법령정보센터 OC 키를 입력하세요.")
        law_desc.setStyleSheet("color: #6b7280;")
        law_link = QPushButton("키 발급받기 →")
        law_link.setFlat(True)
        law_link.setStyleSheet("color: #4f46e5; text-align: left;")
        law_link.setCursor(Qt.CursorShape.PointingHandCursor)
        law_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_LAW_API_URL)))
        law_desc_row.addWidget(law_desc)
        law_desc_row.addWidget(law_link)
        law_desc_row.addStretch()
        law_layout.addLayout(law_desc_row)

        law_input_row = QHBoxLayout()
        self.law_oc_input = QLineEdit()
        self.law_oc_input.setPlaceholderText("OC (발급 시 등록한 이메일 아이디)")
        self.law_save_btn = QPushButton("저장")
        self.law_save_btn.clicked.connect(self._save_law_oc)
        law_input_row.addWidget(self.law_oc_input)
        law_input_row.addWidget(self.law_save_btn)
        law_layout.addLayout(law_input_row)

        self.law_status_label = QLabel("")
        self.law_status_label.setStyleSheet("color: #16a34a;")
        law_layout.addWidget(self.law_status_label)

        root.addWidget(law_card)
        root.addStretch()

    def reload(self) -> None:
        self.key_input.setText(config.get_raw_api_key())
        self.ai_enabled_toggle.blockSignals(True)
        self.ai_enabled_toggle.setChecked(config.get_ai_enabled())
        self.ai_enabled_toggle.blockSignals(False)
        self.law_oc_input.setText(config.get_law_api_oc())

    def _toggle_visibility(self) -> None:
        if self.key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def _save_key(self) -> None:
        config.set_api_key(self.key_input.text())
        self.status_label.setText("저장되었습니다.")

    def _on_ai_enabled_toggled(self, checked: bool) -> None:
        config.set_ai_enabled(checked)

    def _save_law_oc(self) -> None:
        config.set_law_api_oc(self.law_oc_input.text())
        self.law_status_label.setText("저장되었습니다.")
