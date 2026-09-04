"""ReportWizardView의 신규 섹션 UI 조립 로직 — Sub-phase 8(한글 템플릿 출력 + 관리번호/서명 GUI)
에서 추가된 부분: 통보방법·통보방법 서명, 담당요원/결재란 서명 상태 표시.

`report_wizard_sections.py`/`report_wizard_sections2.py`와 같은 mixin 분리 패턴을 그대로
따른다. ReportWizardView가 이 mixin도 함께 상속한다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.constants import NOTIFICATION_METHODS
from desktop.dialogs.staff_picker_dialog import StaffPickerDialog
from desktop.widgets.signature_pad import SignaturePad


class _ClickableFrame(QFrame):
    """마우스 클릭에 반응하는 QFrame — 담당요원 서명 미리보기 카드를 눌러 담당요원을 고르는 데 쓴다."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

_METHOD_STYLE_OFF = (
    "QPushButton { background: white; color: #6b7280; border: 1px solid #d1d5db; "
    "border-radius: 10px; padding: 2px 10px; font-size: 12px; }"
)
_METHOD_STYLE_ON = (
    "QPushButton { background: #4f46e5; color: white; border: 1px solid #4f46e5; "
    "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
)


def _readonly_signature_preview(label_text: str, clickable: bool = False) -> tuple[QFrame, QLabel]:
    """담당요원/결재란처럼 다른 화면에서 등록해 재사용하는 서명의 읽기전용 미리보기 카드.

    clickable=True면 카드를 눌러 다른 동작(담당요원 선택 등)을 트리거할 수 있게 `clicked` 시그널을
    가진 _ClickableFrame으로 만든다.
    """
    frame = _ClickableFrame() if clickable else QFrame()
    frame.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(4)

    title = QLabel(label_text)
    title.setStyleSheet("font-weight: 600; font-size: 12px; border: none; background: transparent;")
    layout.addWidget(title)

    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("color: #6b7280; font-size: 11px; border: none; background: transparent;")
    layout.addWidget(status)

    return frame, status


def _numbered_header(number: int, title: str) -> QWidget:
    """`SectionHeader`(해당사항없음 토글 포함)를 안 쓰는 간단한 번호+제목 헤더.

    결재·통보 정보/기타 특이사항 둘 다 "해당없음" 개념이 없는 상시 항목이라 토글 버튼이
    필요 없다 — `report_wizard_sections.py`의 "무제"(구 기타 특이사항, 11번) 섹션이 쓰는
    수동 배지 패턴을 그대로 재사용한다.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    badge = QLabel(str(number))
    badge.setFixedSize(24, 24)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet("background: #4f46e5; color: white; border-radius: 12px; font-weight: 600;")
    row.addWidget(badge)
    title_label = QLabel(title)
    title_label.setStyleSheet(
        "font-size: 15px; font-weight: 700; margin-left: 6px; border: none; background: transparent;"
    )
    row.addWidget(title_label)
    row.addStretch()
    widget = QWidget()
    widget.setLayout(row)
    return widget


def _set_readonly_signature_status(label: QLabel, registered: bool, unregistered_text: str) -> None:
    if registered:
        label.setText("✓ 등록됨")
        label.setStyleSheet("color: #16a34a; font-size: 11px; border: none; background: transparent;")
    else:
        label.setText(unregistered_text)
        label.setStyleSheet("color: #ef4444; font-size: 11px; border: none; background: transparent;")


class _SectionBuilderMixin3:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _build_signoff_section(self) -> QFrame:
        header = _numbered_header(1, "결재 · 통보 정보")

        # 통보방법
        method_row = QHBoxLayout()
        method_label = QLabel("현장책임자 통보방법")
        method_label.setStyleSheet("border: none; background: transparent;")
        method_row.addWidget(method_label)
        self.notification_buttons = QButtonGroup(self)
        self.notification_buttons.setExclusive(True)
        for method in NOTIFICATION_METHODS:
            btn = QPushButton(method)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_METHOD_STYLE_OFF)
            btn.toggled.connect(self._update_notification_button_styles)
            self.notification_buttons.addButton(btn)
            method_row.addWidget(btn)
        method_row.addStretch()
        method_widget = QWidget()
        method_widget.setLayout(method_row)

        # 통보방법 성명 + 서명
        name_row = QHBoxLayout()
        name_label = QLabel("현장책임자 성명")
        name_label.setStyleSheet("border: none; background: transparent;")
        name_row.addWidget(name_label)
        self.notify_signee_input = QLineEdit()
        self.notify_signee_input.setPlaceholderText("예: 현장 책임자 이름")
        name_row.addWidget(self.notify_signee_input)
        name_widget = QWidget()
        name_widget.setLayout(name_row)

        notify_sig_col = QVBoxLayout()
        notify_sig_label = QLabel("현장책임자 서명")
        notify_sig_label.setStyleSheet("border: none; background: transparent;")
        notify_sig_col.addWidget(notify_sig_label)
        self.notify_signature_pad = SignaturePad()
        notify_sig_col.addWidget(self.notify_signature_pad)
        notify_sig_save_btn = QPushButton("저장")
        notify_sig_save_btn.clicked.connect(self._save_notify_signature)
        notify_sig_col.addWidget(notify_sig_save_btn)
        self.notify_signature_status_label = QLabel("")
        self.notify_signature_status_label.setStyleSheet("border: none; background: transparent;")
        notify_sig_col.addWidget(self.notify_signature_status_label)
        notify_sig_widget = QWidget()
        notify_sig_widget.setLayout(notify_sig_col)

        self.notify_signature_pad.signature_changed.connect(self._on_notify_signature_changed)

        # 담당요원/결재란 — 여기서는 편집 불가, 상태만 노출(각각 담당요원 관리/AI 관리 화면에서 등록)
        previews_row = QHBoxLayout()
        self._staff_signature_frame, self._staff_signature_status = _readonly_signature_preview(
            "담당요원 서명", clickable=True
        )
        self._staff_signature_frame.clicked.connect(self._open_staff_picker)
        previews_row.addWidget(self._staff_signature_frame)
        self._director_signature_frame, self._director_signature_status = _readonly_signature_preview(
            "결재란 — 이사"
        )
        previews_row.addWidget(self._director_signature_frame)
        self._ceo_signature_frame, self._ceo_signature_status = _readonly_signature_preview("결재란 — 대표이사")
        previews_row.addWidget(self._ceo_signature_frame)
        previews_widget = QWidget()
        previews_widget.setLayout(previews_row)

        return self._card(header, method_widget, name_widget, notify_sig_widget, previews_widget)

    def _build_misc_note_section(self) -> QFrame:
        header = _numbered_header(2, "기타 특이사항")

        grid = QFrame()
        grid.setStyleSheet("QFrame { background: white; border: 1px solid #d1d5db; border-radius: 6px; }")
        grid_layout = QVBoxLayout(grid)
        grid_layout.setContentsMargins(14, 12, 14, 12)
        grid_layout.setSpacing(10)

        overwork_row = QHBoxLayout()
        self.misc_overwork_check = QCheckBox("공사기간 편중, 조기준공 등")
        self.misc_no_photo_check = QCheckBox("사진촬영 불가 (보안 등)")
        overwork_row.addWidget(self.misc_overwork_check)
        overwork_row.addWidget(self.misc_no_photo_check)
        overwork_row.addStretch()
        grid_layout.addLayout(overwork_row)

        other_row = QHBoxLayout()
        self.misc_other_check = QCheckBox("기타")
        self.misc_other_check.setFixedWidth(70)
        self.misc_other_input = QLineEdit()
        self.misc_other_input.setPlaceholderText("내용 입력")
        other_row.addWidget(self.misc_other_check)
        other_row.addWidget(self.misc_other_input)
        grid_layout.addLayout(other_row)

        accident_row = QHBoxLayout()
        accident_label = QLabel("재해발생현황")
        accident_label.setStyleSheet("border: none; background: transparent;")
        accident_row.addWidget(accident_label)
        self.accident_buttons = QButtonGroup(self)
        self.accident_buttons.setExclusive(True)
        self.accident_yes_check = QCheckBox("유")
        self.accident_no_check = QCheckBox("무")
        self.accident_no_check.setChecked(True)
        self.accident_buttons.addButton(self.accident_yes_check)
        self.accident_buttons.addButton(self.accident_no_check)
        accident_row.addWidget(self.accident_yes_check)
        accident_row.addWidget(self.accident_no_check)
        self.accident_content_input = QLineEdit()
        self.accident_content_input.setPlaceholderText("내용 입력")
        accident_row.addWidget(self.accident_content_input)
        grid_layout.addLayout(accident_row)

        return self._card(header, grid)

    def _save_notify_signature(self) -> None:
        self._save(navigate=False)
        self._set_notify_signature_status(self.notify_signature_pad.has_signature())

    def _on_notify_signature_changed(self, path: str) -> None:
        if path:
            return
        self._set_notify_signature_status(False)

    def _set_notify_signature_status(self, saved: bool) -> None:
        if saved:
            self.notify_signature_status_label.setText("서명이 저장되었습니다.")
            self.notify_signature_status_label.setStyleSheet(
                "color: #16a34a; border: none; background: transparent;"
            )
        else:
            self.notify_signature_status_label.setText("서명을 등록해주세요.")
            self.notify_signature_status_label.setStyleSheet(
                "color: #ef4444; border: none; background: transparent;"
            )

    def _open_staff_picker(self) -> None:
        dialog = StaffPickerDialog(self)
        if dialog.exec() and dialog.selected_staff_id is not None:
            idx = self.staff_combo.findData(dialog.selected_staff_id)
            if idx >= 0:
                self.staff_combo.setCurrentIndex(idx)

    def _update_notification_button_styles(self) -> None:
        for btn in self.notification_buttons.buttons():
            btn.setStyleSheet(_METHOD_STYLE_ON if btn.isChecked() else _METHOD_STYLE_OFF)

    def notification_method(self) -> str:
        checked = self.notification_buttons.checkedButton()
        return checked.text() if checked else ""

    def set_notification_method(self, value: str) -> None:
        for btn in self.notification_buttons.buttons():
            btn.setChecked(btn.text() == value)

    def _refresh_signoff_previews(self, staff_id: int | None) -> None:
        """담당요원 서명(선택된 담당요원 기준)/결재란 서명(회사 고정값) 등록 상태를 갱신한다."""
        from core.db import SessionLocal
        from core.models_db import Staff

        staff_path = ""
        if staff_id:
            with SessionLocal() as session:
                staff = session.get(Staff, staff_id)
                staff_path = staff.signature_path if staff else ""
        _set_readonly_signature_status(
            self._staff_signature_status, bool(staff_path), "미등록 — 담당요원 관리 화면에서 등록하세요."
        )

        director_path, _ = config.get_company_signature("director")
        _set_readonly_signature_status(
            self._director_signature_status, bool(director_path), "미등록 — AI 관리 화면에서 등록하세요."
        )
        ceo_path, _ = config.get_company_signature("ceo")
        _set_readonly_signature_status(
            self._ceo_signature_status, bool(ceo_path), "미등록 — AI 관리 화면에서 등록하세요."
        )
