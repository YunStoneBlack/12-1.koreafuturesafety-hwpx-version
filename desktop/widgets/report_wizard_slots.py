"""보고서 작성 마법사 각 섹션의 "한 칸" 단위 위젯들 (지적사항/이전지적사항/계측자료/진행공정).

report_wizard_view.py에서 분리됨 — ReportWizardView는 이 위젯들을 조립해 화면을 구성하고,
저장/불러오기 시 이 위젯들의 값을 읽고 쓴다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
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
    QWidget,
)

from core import config
from core.models_db import Finding
from core.vision_analyzer import analyze_finding, read_measurement_value
from desktop.dialogs.law_search_dialog import LawSearchDialog
from desktop.dialogs.process_picker_dialog import ProcessPickerDialog
from desktop.widgets.photo_drop_zone import PhotoDropZone
from desktop.workers.ai_worker import AIWorker

_RISK_BANDS = [(1, 3, "현상유지", "#374151"), (4, 5, "개선필요", "#ea580c"), (6, 9, "즉시개선", "#dc2626")]


def _risk_band(score: int) -> tuple[str, str]:
    for lo, hi, label, color in _RISK_BANDS:
        if lo <= score <= hi:
            return label, color
    return "", "#6b7280"


def _limited_text_edit(limit: int) -> tuple[QTextEdit, QLabel]:
    edit = QTextEdit()
    edit.setFixedHeight(70)
    counter = QLabel(f"0 / {limit}")
    counter.setStyleSheet("color: #9ca3af; font-size: 11px;")

    def _on_changed() -> None:
        text = edit.toPlainText()
        if len(text) > limit:
            cursor = edit.textCursor()
            pos = cursor.position()
            edit.blockSignals(True)
            edit.setPlainText(text[:limit])
            cursor.setPosition(min(pos, limit))
            edit.setTextCursor(cursor)
            edit.blockSignals(False)
            text = text[:limit]
        counter.setText(f"{len(text)} / {limit}")

    edit.textChanged.connect(_on_changed)
    return edit, counter


class _RiskButtons(QWidget):
    def __init__(self, label: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for value in (1, 2, 3):
            btn = QPushButton(str(value))
            btn.setCheckable(True)
            btn.setFixedWidth(28)
            self.group.addButton(btn, value)
            layout.addWidget(btn)

    def value(self) -> int | None:
        checked = self.group.checkedButton()
        return self.group.id(checked) if checked else None

    def set_value(self, value: int | None) -> None:
        if value is None:
            self.group.setExclusive(False)
            for btn in self.group.buttons():
                btn.setChecked(False)
            self.group.setExclusive(True)
            return
        btn = self.group.button(value)
        if btn:
            btn.setChecked(True)


class _FindingSlot(QFrame):
    def __init__(self, slot: int):
        super().__init__()
        self.slot = slot
        self._worker: AIWorker | None = None
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        layout = QVBoxLayout(self)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(f"지적사항 {slot}"))
        title_row.addStretch()
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedWidth(32)
        self.delete_btn.clicked.connect(self._delete)
        title_row.addWidget(self.delete_btn)
        layout.addLayout(title_row)

        body_row = QHBoxLayout()
        self.photo = PhotoDropZone(f"지적사항 {slot} 사진")
        body_row.addWidget(self.photo)

        form_col = QVBoxLayout()
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("설명 (예: 개구부 안전난간 미설치)")
        self.ai_button = QPushButton("✨ AI추천")
        self.ai_button.clicked.connect(self._run_ai)
        desc_row = QHBoxLayout()
        desc_row.addWidget(self.description_input)
        desc_row.addWidget(self.ai_button)
        form_col.addLayout(desc_row)

        self.title_input = QLineEdit()
        self.title_input.setMaxLength(30)
        self.title_input.setPlaceholderText("제목을 입력하거나 AI추천을 눌러주세요")
        form_col.addWidget(self.title_input)

        self.content_edit, self.content_counter = _limited_text_edit(110)
        self.content_edit.setPlaceholderText("개선대책 내용을 입력하거나 AI추천을 눌러주세요")
        form_col.addWidget(self.content_edit)
        form_col.addWidget(self.content_counter)

        law_row = QHBoxLayout()
        self.law_input = QLineEdit()
        self.law_input.setPlaceholderText("관련 법령을 입력하거나 AI추천을 눌러주세요")
        law_search_btn = QPushButton("🔍 검색")
        law_search_btn.clicked.connect(self._open_law_search)
        law_row.addWidget(self.law_input)
        law_row.addWidget(law_search_btn)
        form_col.addLayout(law_row)

        body_row.addLayout(form_col, stretch=1)

        risk_col = QVBoxLayout()
        risk_col.addWidget(QLabel("위험성 평가"))
        self.likelihood_buttons = _RiskButtons("가능성")
        self.severity_buttons = _RiskButtons("중대성")
        risk_col.addWidget(self.likelihood_buttons)
        risk_col.addWidget(self.severity_buttons)
        self.risk_score_label = QLabel("-")
        self.risk_score_label.setStyleSheet("font-weight: 700; font-size: 16px;")
        risk_col.addWidget(self.risk_score_label)
        self.likelihood_buttons.group.buttonToggled.connect(self._update_risk_score)
        self.severity_buttons.group.buttonToggled.connect(self._update_risk_score)
        body_row.addLayout(risk_col)

        layout.addLayout(body_row)

        self._active = False
        self.setVisible(False)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setVisible(active)

    def is_active(self) -> bool:
        return self._active

    def clear(self) -> None:
        self.photo.clear_photo()
        self.description_input.clear()
        self.title_input.clear()
        self.content_edit.clear()
        self.law_input.clear()
        self.likelihood_buttons.set_value(None)
        self.severity_buttons.set_value(None)

    def _delete(self) -> None:
        self.clear()
        self.set_active(False)

    def _update_risk_score(self) -> None:
        likelihood = self.likelihood_buttons.value()
        severity = self.severity_buttons.value()
        if likelihood is None or severity is None:
            self.risk_score_label.setText("-")
            self.risk_score_label.setStyleSheet("font-weight: 700; font-size: 16px;")
            return
        score = likelihood * severity
        label, color = _risk_band(score)
        self.risk_score_label.setText(f"{score} ({label})" if label else str(score))
        self.risk_score_label.setStyleSheet(f"font-weight: 700; font-size: 16px; color: {color};")

    def _run_ai(self) -> None:
        if not self.photo.photo_path:
            QMessageBox.warning(self, "사진 필요", "먼저 사진을 업로드해주세요.")
            return
        if not config.has_api_key():
            QMessageBox.warning(self, "API 키 필요", "'AI 관리' 화면에서 Claude API 키를 먼저 등록하세요.")
            return
        self.ai_button.setEnabled(False)
        self.ai_button.setText("분석 중...")
        photo_path = self.photo.photo_path
        description = self.description_input.text()
        self._worker = AIWorker(lambda: analyze_finding(photo_path, description))
        self._worker.finished_ok.connect(self._on_ai_done)
        self._worker.finished_error.connect(self._on_ai_error)
        self._worker.start()

    def _on_ai_done(self, result: dict) -> None:
        self.ai_button.setEnabled(True)
        self.ai_button.setText("✨ AI추천")
        self.title_input.setText(result.get("title", ""))
        self.content_edit.setPlainText(result.get("content", ""))
        if result.get("law_citation"):
            self.law_input.setText(result["law_citation"])
        if result.get("likelihood") is not None:
            self.likelihood_buttons.set_value(result["likelihood"])
        if result.get("severity") is not None:
            self.severity_buttons.set_value(result["severity"])

    def _on_ai_error(self, message: str) -> None:
        self.ai_button.setEnabled(True)
        self.ai_button.setText("✨ AI추천")
        QMessageBox.warning(self, "AI 분석 실패", message)

    def _open_law_search(self) -> None:
        dialog = LawSearchDialog(self)
        if dialog.exec() and dialog.selected_text:
            self.law_input.setText(dialog.selected_text)

    def has_data(self) -> bool:
        return bool(self.photo.photo_path or self.title_input.text() or self.content_edit.toPlainText())


class _PreviousFindingSlot(QFrame):
    """5. 이전지적사항 한 건 — 직전 회차 지적사항을 이월받거나 수기로 추가."""

    def __init__(self, slot: int):
        super().__init__()
        self.slot = slot
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        layout = QHBoxLayout(self)
        self.photo = PhotoDropZone(f"이전지적사항 {slot} 사진")
        layout.addWidget(self.photo)

        form_col = QVBoxLayout()
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("지적사항 제목")
        form_col.addWidget(self.title_input)
        self.content_edit = QTextEdit()
        self.content_edit.setFixedHeight(50)
        form_col.addWidget(self.content_edit)
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("조치 결과"))
        self.action_input = QLineEdit("조치완료")
        action_row.addWidget(self.action_input)
        action_row.addWidget(QLabel("위험성"))
        self.risk_buttons = QButtonGroup(self)
        self.risk_buttons.setExclusive(True)
        for label in ("상", "중", "하"):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_badge_style(""))
            btn.toggled.connect(self._update_risk_badge_styles)
            self.risk_buttons.addButton(btn)
            action_row.addWidget(btn)
        form_col.addLayout(action_row)
        layout.addLayout(form_col, stretch=1)

        button_col = QVBoxLayout()
        self.confirm_btn = QPushButton("확인 필요")
        self.confirm_btn.setCheckable(True)
        self.confirm_btn.toggled.connect(self._on_confirm_toggled)
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedWidth(32)
        self.delete_btn.clicked.connect(self._delete)
        button_col.addWidget(self.confirm_btn)
        button_col.addWidget(self.delete_btn)
        layout.addLayout(button_col)

        self._active = False
        self.setVisible(False)

    def _update_risk_badge_styles(self) -> None:
        for btn in self.risk_buttons.buttons():
            btn.setStyleSheet(_badge_style(btn.text() if btn.isChecked() else ""))

    def risk_level(self) -> str:
        checked = self.risk_buttons.checkedButton()
        return checked.text() if checked else ""

    def set_risk_level(self, level: str) -> None:
        for btn in self.risk_buttons.buttons():
            btn.setChecked(btn.text() == level)

    def _on_confirm_toggled(self, checked: bool) -> None:
        if checked and not self.photo.photo_path:
            reply = QMessageBox.question(
                self,
                "사진 없음",
                "이 지적사항에는 사진이 없습니다. 사진 없이 확인 처리하시겠습니까?\n"
                "(취소를 누르고 사진을 직접 업로드할 수도 있습니다.)",
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.confirm_btn.blockSignals(True)
                self.confirm_btn.setChecked(False)
                self.confirm_btn.blockSignals(False)
                return
        self.confirm_btn.setText("✓ 확인됨" if checked else "확인 필요")

    def _delete(self) -> None:
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setVisible(active)

    def is_active(self) -> bool:
        return self._active

    def load_from_finding(self, finding: Finding) -> None:
        self.set_active(True)
        if finding.photo_path:
            self.photo.set_photo(finding.photo_path)
        self.title_input.setText(finding.title)
        self.content_edit.setPlainText(finding.content)
        self.action_input.setText("조치완료")
        self.confirm_btn.setChecked(False)
        self.set_risk_level("")


class _MeasurementRow(QFrame):
    """6. 계측자료 한 항목 (7종 고정)."""

    def __init__(self, instrument_type: str, unit: str, standard_criteria: str):
        super().__init__()
        self.instrument_type = instrument_type
        self._worker: AIWorker | None = None
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{instrument_type} ({unit})"))
        if standard_criteria:
            std_label = QLabel(f"측정기준: {standard_criteria}")
            std_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
            layout.addWidget(std_label)

        self.photo = PhotoDropZone(instrument_type)
        layout.addWidget(self.photo)

        row = QHBoxLayout()
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText(f"측정값 ({unit})")
        self.read_btn = QPushButton("✨ AI로 읽기")
        self.read_btn.clicked.connect(self._run_read)
        row.addWidget(self.value_input)
        row.addWidget(self.read_btn)
        layout.addLayout(row)

    def _run_read(self) -> None:
        if not self.photo.photo_path:
            QMessageBox.warning(self, "사진 필요", "먼저 계측장비 사진을 업로드해주세요.")
            return
        if not config.has_api_key():
            QMessageBox.warning(self, "API 키 필요", "'AI 관리' 화면에서 Claude API 키를 먼저 등록하세요.")
            return
        self.read_btn.setEnabled(False)
        self.read_btn.setText("읽는 중...")
        photo_path = self.photo.photo_path
        instrument_type = self.instrument_type
        self._worker = AIWorker(lambda: read_measurement_value(photo_path, instrument_type))
        self._worker.finished_ok.connect(self._on_read_done)
        self._worker.finished_error.connect(self._on_read_error)
        self._worker.start()

    def _on_read_done(self, value: str | None) -> None:
        self.read_btn.setEnabled(True)
        self.read_btn.setText("✨ AI로 읽기")
        if value is None:
            QMessageBox.information(self, "인식 실패", "사진에서 측정값을 읽지 못했습니다. 직접 입력해주세요.")
        else:
            self.value_input.setText(value)

    def _on_read_error(self, message: str) -> None:
        self.read_btn.setEnabled(True)
        self.read_btn.setText("✨ AI로 읽기")
        QMessageBox.warning(self, "AI 분석 실패", message)


_RISK_BADGE_COLORS = {
    "상": ("#dc2626", "#fef2f2", "#fecaca"),
    "중": ("#b45309", "#fffbeb", "#fde68a"),
    "하": ("#16a34a", "#f0fdf4", "#bbf7d0"),
}


def _badge_style(level: str) -> str:
    fg, bg, border = _RISK_BADGE_COLORS.get(level, ("#6b7280", "#f9fafb", "#e5e7eb"))
    return (
        f"QPushButton {{ color: {fg}; background: {bg}; border: 1px solid {border}; "
        "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
    )


class _ProcessSlot(QFrame):
    """9. 진행공정 한 칸 (최대 4칸).

    실제 사이트는 위쪽에 "몇 번 칸에 뭘 골랐는지"만 보여주는 압축된 2x2 표와, 그 아래에
    선택된 공정만 번호를 새로 매겨 나열하는 "진행공정/유해·위험요인/예방대책/위험성"
    4열 표, 이렇게 두 영역으로 나뉘어 있다. 이 위젯은 두 영역에 쓰이는 위젯을 모두
    들고 있고, 실제 배치(어느 그리드/표에 넣을지)는 부모(ReportWizardView)가 한다.
    """

    changed = pyqtSignal()

    def __init__(self, slot: int):
        super().__init__()
        self.slot = slot
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        self.layout_ = QVBoxLayout(self)

        # ---- 위쪽 2x2 압축 표 칸 ----
        # 비어있을 때: 연보라색 "+ 추가" 버튼 (기본 버튼 크롬을 쓰면 아무것도 안 골랐는데도
        # 이미 선택된 것처럼 강조되어 보이는 문제가 있어 스타일/기본버튼 여부를 명시적으로 정한다)
        self.pick_btn = QPushButton(f"+ {slot}번 칸 공정 선택")
        self.pick_btn.setAutoDefault(False)
        self.pick_btn.setDefault(False)
        self.pick_btn.setStyleSheet(
            "QPushButton { background: #f5f3ff; color: #7c3aed; border: 1px dashed #c4b5fd; "
            "border-radius: 6px; padding: 8px; font-weight: 600; }"
            "QPushButton:hover { background: #ede9fe; }"
        )
        self.pick_btn.clicked.connect(self._open_picker)
        self.layout_.addWidget(self.pick_btn)

        # 채워졌을 때: 공정명 + 위험도 배지 + 빼기 버튼 한 줄 (교체는 아래 상세 표에서
        # 이름·내용을 직접 고쳐 쓰면 되므로 여기서는 빼기만 남긴다 — 실제 사이트와 동일)
        self.header_widget = QWidget()
        header_row = QHBoxLayout(self.header_widget)
        header_row.setContentsMargins(0, 0, 0, 0)
        self.name_label = QLabel("")
        self.name_label.setStyleSheet("font-weight: 600;")
        self.risk_badge = QPushButton("")
        self.risk_badge.setEnabled(False)
        self.risk_badge.setFlat(True)
        remove_btn = QPushButton("✕")
        remove_btn.setAutoDefault(False)
        remove_btn.setFixedWidth(24)
        remove_btn.setStyleSheet("QPushButton { color: #ef4444; }")
        remove_btn.clicked.connect(self.reset)
        header_row.addWidget(self.name_label, stretch=1)
        header_row.addWidget(self.risk_badge)
        header_row.addWidget(remove_btn)
        self.layout_.addWidget(self.header_widget)

        self._set_fields_visible(False)

        # ---- 아래쪽 상세 표(진행공정/유해·위험요인/예방대책/위험성)에 쓰일 위젯들 ----
        # 이 위젯들은 self.layout_에 넣지 않는다 — ReportWizardView가 공통 표의
        # 해당 칸(cell)에 직접 addWidget 한다.
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("진행공정 이름")
        self.name_input.setStyleSheet(
            "QLineEdit { border: none; background: transparent; font-weight: 600; padding: 0; }"
        )
        self.hazard_edit, self.hazard_counter = _limited_text_edit(200)
        self.hazard_edit.setPlaceholderText("유해·위험요인")
        self.prevention_edit, self.prevention_counter = _limited_text_edit(200)
        self.prevention_edit.setPlaceholderText("예방대책")
        self.name_input.textChanged.connect(lambda text: self.name_label.setText(text))

        self.detail_name_widget = QWidget()
        name_row = QHBoxLayout(self.detail_name_widget)
        name_row.setContentsMargins(8, 8, 8, 8)
        self.seq_label = QLabel("")
        self.seq_label.setStyleSheet("font-weight: 600; border: none; background: transparent;")
        name_row.addWidget(self.seq_label)
        name_row.addWidget(self.name_input, stretch=1)

        self.hazard_cell = QWidget()
        hazard_col = QVBoxLayout(self.hazard_cell)
        hazard_col.setContentsMargins(8, 8, 8, 8)
        hazard_col.setSpacing(2)
        hazard_col.addWidget(self.hazard_edit)
        hazard_col.addWidget(self.hazard_counter)

        self.prevention_cell = QWidget()
        prevention_col = QVBoxLayout(self.prevention_cell)
        prevention_col.setContentsMargins(8, 8, 8, 8)
        prevention_col.setSpacing(2)
        prevention_col.addWidget(self.prevention_edit)
        prevention_col.addWidget(self.prevention_counter)

        self.risk_buttons = QButtonGroup(self)
        self.risk_buttons.setExclusive(True)
        self.risk_column = QWidget()
        risk_col_layout = QVBoxLayout(self.risk_column)
        risk_col_layout.setContentsMargins(8, 8, 8, 8)
        risk_col_layout.setSpacing(4)
        for label in ("상", "중", "하"):
            btn = QPushButton(label)
            btn.setAutoDefault(False)
            btn.setCheckable(True)
            btn.setFixedWidth(44)
            btn.setStyleSheet(_badge_style(""))
            btn.toggled.connect(self._update_badge)
            self.risk_buttons.addButton(btn)
            risk_col_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _set_fields_visible(self, visible: bool) -> None:
        self.header_widget.setVisible(visible)
        self.pick_btn.setVisible(not visible)

    def _update_badge(self) -> None:
        level = self.risk_level()
        self.risk_badge.setText(level or "-")
        self.risk_badge.setStyleSheet(_badge_style(level))
        for btn in self.risk_buttons.buttons():
            btn.setStyleSheet(_badge_style(btn.text() if btn.isChecked() else ""))

    def _open_picker(self) -> None:
        dialog = ProcessPickerDialog(self)
        if dialog.exec() and dialog.selected:
            self.load_data(dialog.selected)

    def load_data(self, data: dict) -> None:
        self.name_input.setText(data.get("process_name", ""))
        self.hazard_edit.setPlainText(data.get("hazard_text", ""))
        self.prevention_edit.setPlainText(data.get("prevention_text", ""))
        risk_level = data.get("risk_level", "")
        for btn in self.risk_buttons.buttons():
            btn.setChecked(btn.text() == risk_level)
        self._update_badge()
        self._set_fields_visible(True)
        self.changed.emit()

    def risk_level(self) -> str:
        checked = self.risk_buttons.checkedButton()
        return checked.text() if checked else ""

    def has_data(self) -> bool:
        return bool(self.name_input.text())

    def reset(self) -> None:
        self.name_input.clear()
        self.hazard_edit.clear()
        self.prevention_edit.clear()
        self.risk_buttons.setExclusive(False)
        for btn in self.risk_buttons.buttons():
            btn.setChecked(False)
        self.risk_buttons.setExclusive(True)
        self._update_badge()
        self._set_fields_visible(False)
        self.changed.emit()
