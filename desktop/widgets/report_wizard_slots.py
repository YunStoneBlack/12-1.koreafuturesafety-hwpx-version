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
from core.vision_analyzer import analyze_finding, analyze_process_hazards, read_measurement_value
from desktop.dialogs.law_search_dialog import LawSearchDialog
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

        risk_col.addWidget(QLabel("이행결과"))
        self.action_status_buttons = QButtonGroup(self)
        self.action_status_buttons.setExclusive(True)
        for status in ("추후확인", "즉시이행"):
            btn = QPushButton(status)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_action_status_style(False))
            btn.toggled.connect(lambda checked, b=btn: b.setStyleSheet(_action_status_style(checked)))
            if status == "추후확인":
                btn.setChecked(True)
            self.action_status_buttons.addButton(btn)
            risk_col.addWidget(btn)

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
        self.set_action_status("추후확인")

    def action_status(self) -> str:
        checked = self.action_status_buttons.checkedButton()
        return checked.text() if checked else "추후확인"

    def set_action_status(self, status: str) -> None:
        for btn in self.action_status_buttons.buttons():
            btn.setChecked(btn.text() == status)

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


_VERDICT_STYLE_OFF = (
    "QPushButton { background: white; color: #6b7280; border: 1px solid #d1d5db; "
    "border-radius: 10px; padding: 2px 10px; font-size: 12px; }"
)
_VERDICT_STYLE_ON = (
    "QPushButton { background: #4f46e5; color: white; border: 1px solid #4f46e5; "
    "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
)


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

        verdict_row = QHBoxLayout()
        verdict_row.addWidget(QLabel("장비사용 판정:"))
        # 조도계/가스농도측정기는 측정값으로 자동판정되지만(core.report_builder_hwpx_fields
        # ._equipment_verdict), 그 외 장비는 자동판정 근거가 없어 표16 양호/불량 칸이 항상
        # 빈칸이었다 — 여기서 수동으로 고르면 자동판정보다 우선한다. 같은 버튼을 다시 누르면
        # 선택 해제(다시 자동판정/빈칸으로) — _EquipmentEvalCell(report_wizard_sections2.py)과
        # 같은 패턴.
        self.verdict_buttons = QButtonGroup(self)
        self.verdict_buttons.setExclusive(False)
        for label in ("양호", "불량"):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setStyleSheet(_VERDICT_STYLE_OFF)
            btn.toggled.connect(self._update_verdict_styles)
            btn.clicked.connect(lambda _checked, b=btn: self._on_verdict_clicked(b))
            self.verdict_buttons.addButton(btn)
            verdict_row.addWidget(btn)
        verdict_row.addWidget(QLabel("(미선택 시 자동판정)"))
        verdict_row.addStretch()
        layout.addLayout(verdict_row)

        # 표16 "조치사항" 칸이 항상 "-"로만 나가던 것을 수기로 입력할 수 있게 한다(사용자
        # 요청, 장비사용 판정 바로 아래 배치).
        layout.addWidget(QLabel("조치사항:"))
        self.action_input = QLineEdit()
        self.action_input.setPlaceholderText("예: 이상 없음 확인, 관리자 통보 후 조치 등 (미입력 시 '-')")
        layout.addWidget(self.action_input)

    def _on_verdict_clicked(self, clicked_btn: QPushButton) -> None:
        if not clicked_btn.isChecked():
            return
        for btn in self.verdict_buttons.buttons():
            if btn is not clicked_btn:
                btn.setChecked(False)

    def _update_verdict_styles(self) -> None:
        for btn in self.verdict_buttons.buttons():
            btn.setStyleSheet(_VERDICT_STYLE_ON if btn.isChecked() else _VERDICT_STYLE_OFF)

    def verdict(self) -> str:
        checked = next((b for b in self.verdict_buttons.buttons() if b.isChecked()), None)
        return checked.text() if checked else ""

    def set_verdict(self, value: str) -> None:
        for btn in self.verdict_buttons.buttons():
            btn.setChecked(btn.text() == value)

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


def _action_status_style(checked: bool) -> str:
    if checked:
        return (
            "QPushButton { color: #4f46e5; background: #eef2ff; border: 1px solid #c7d2fe; "
            "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
        )
    return (
        "QPushButton { color: #6b7280; background: #f9fafb; border: 1px solid #e5e7eb; "
        "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
    )



class _SitePhotoSlot(QFrame):
    """3번 "전경사진 및 점검사항"의 사진 한 칸 — 사진 업로드/삭제 외에 다른 입력이 없는
    가장 단순한 슬롯(제목/내용/위험성 없음). `label`은 "전경사진"/"점검사진" 중 하나."""

    def __init__(self, label: str, slot: int):
        super().__init__()
        self.slot = slot
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        layout = QVBoxLayout(self)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(f"{label} {slot}"))
        title_row.addStretch()
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedWidth(32)
        self.delete_btn.clicked.connect(self._delete)
        title_row.addWidget(self.delete_btn)
        layout.addLayout(title_row)

        self.photo = PhotoDropZone(f"{label} {slot}")
        layout.addWidget(self.photo, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._active = False
        self.setVisible(False)

    def set_retain_size(self, retain: bool) -> None:
        """비활성 상태(setVisible(False))에서도 이 칸이 차지하던 자리를 그대로 남겨둘지
        정한다. 전경사진/점검사진을 같은 행(QGridLayout)에 나란히 두는데, 한쪽만
        활성화되면 반대쪽 칸이 레이아웃 크기 계산에서 완전히 빠져 그 행 높이가 활성화된
        쪽에 안 맞고 반대쪽만 눌려 보이는 비대칭 문제가 있었다(실측 확인) — 그래서 "같은
        행의 둘 중 하나라도 활성화"일 때만 켜서, 그 행에서만 반대쪽도 같은 높이를
        차지하게 한다(항상 켜두면 둘 다 비어있을 때도 4칸 분량 높이가 통째로 남아 불필요한
        빈 공간이 생긴다 — `_build_overview_section`의 `_sync_photo_row_symmetry` 참고)."""
        size_policy = self.sizePolicy()
        size_policy.setRetainSizeWhenHidden(retain)
        self.setSizePolicy(size_policy)

    def _delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            "정말로 삭제하시겠습니까?\n사진이 지워지며 되돌릴 수 없습니다.",
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
        self.photo.clear_photo()
