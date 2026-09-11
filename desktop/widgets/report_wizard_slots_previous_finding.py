"""마법사 5번 "이전지적사항" 한 칸 위젯 — `report_wizard_slots.py`에서 분리됨(638줄을
넘겨 이 프로젝트 관례상 600줄 기준으로 나눴다, 2026-09-08).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
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

from core.models_db import compute_after_risk
from desktop.widgets.photo_drop_zone import PhotoDropZone
from desktop.widgets.report_wizard_slots import _RiskButtons, _action_status_style, _risk_band


def _score_label_style(color: str = "#111827") -> str:
    return f"font-weight: 700; font-size: 16px; color: {color}; border: none; background: transparent;"


def _score_text_and_color(likelihood: int | None, severity: int | None) -> tuple[str, str]:
    if likelihood is None or severity is None:
        return "-", "#111827"
    score = likelihood * severity
    label, color = _risk_band(score)
    return (f"{score} ({label})" if label else str(score)), color


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

        risk_row = QHBoxLayout()
        before_col = QVBoxLayout()
        before_label = QLabel("이행 전 위험성")
        before_label.setStyleSheet("border: none; background: transparent;")
        before_col.addWidget(before_label)
        self.before_likelihood_buttons = _RiskButtons("가능성")
        self.before_severity_buttons = _RiskButtons("중대성")
        before_col.addWidget(self.before_likelihood_buttons)
        before_col.addWidget(self.before_severity_buttons)
        self.before_score_label = QLabel("-")
        self.before_score_label.setStyleSheet(_score_label_style())
        before_col.addWidget(self.before_score_label)
        self.before_likelihood_buttons.group.buttonToggled.connect(self._on_before_risk_changed)
        self.before_severity_buttons.group.buttonToggled.connect(self._on_before_risk_changed)
        risk_row.addLayout(before_col)

        after_col = QVBoxLayout()
        after_label = QLabel("이행 후 위험성")
        after_label.setStyleSheet("border: none; background: transparent;")
        after_col.addWidget(after_label)
        # 사용자가 직접 정하는 값이 아니라 "이행 전" 위험성 + 이행결과에서 자동 계산되는
        # 값이라(compute_after_risk 참고) 클릭 못 하게 잠가둔다 — 값은 코드로만 바뀐다.
        self.after_likelihood_buttons = _RiskButtons("가능성")
        self.after_severity_buttons = _RiskButtons("중대성")
        self.after_likelihood_buttons.setEnabled(False)
        self.after_severity_buttons.setEnabled(False)
        after_col.addWidget(self.after_likelihood_buttons)
        after_col.addWidget(self.after_severity_buttons)
        self.after_score_label = QLabel("-")
        self.after_score_label.setStyleSheet(_score_label_style())
        after_col.addWidget(self.after_score_label)
        risk_row.addLayout(after_col)
        form_col.addLayout(risk_row)

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

        completion_col = QVBoxLayout()
        completion_label = QLabel("이행결과 사진")
        completion_label.setStyleSheet("border: none; background: transparent;")
        completion_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        completion_col.addWidget(completion_label)
        self.completion_photo = PhotoDropZone(f"이전지적사항 {slot} 이행완료 사진")
        completion_col.addWidget(self.completion_photo)
        body_row.addLayout(completion_col)
        layout.addLayout(body_row)

        self._active = False
        self.source_finding_id: int | None = None
        # "이행완료"로 확정된 "이행 후 위험성" 값 캐시 — compute_after_risk()가 매번 새로
        # 무작위로 뽑지 않고 재사용하도록(이행결과 버튼을 이랬다저랬다 눌러도 값이 안 바뀌게).
        # "이행 전" 값이 바뀌면(_on_before_risk_changed) 무효화해 다시 뽑게 한다.
        self._after_cache: tuple[int | None, int | None] = (None, None)
        self.setVisible(False)

    def _on_before_risk_changed(self, *_args) -> None:
        before_likelihood = self.before_likelihood_buttons.value()
        before_severity = self.before_severity_buttons.value()
        text, color = _score_text_and_color(before_likelihood, before_severity)
        self.before_score_label.setText(text)
        self.before_score_label.setStyleSheet(_score_label_style(color))
        self._after_cache = (None, None)
        self._update_after_risk_display()

    def _update_after_risk_display(self) -> None:
        before_likelihood = self.before_likelihood_buttons.value()
        before_severity = self.before_severity_buttons.value()
        cached_likelihood, cached_severity = self._after_cache
        after_likelihood, after_severity = compute_after_risk(
            before_likelihood, before_severity, self.result_status(), cached_likelihood, cached_severity
        )
        if self.result_status() == "이행완료" and after_likelihood is not None:
            self._after_cache = (after_likelihood, after_severity)
        self.after_likelihood_buttons.set_value(after_likelihood)
        self.after_severity_buttons.set_value(after_severity)
        text, color = _score_text_and_color(after_likelihood, after_severity)
        self.after_score_label.setText(text)
        self.after_score_label.setStyleSheet(_score_label_style(color))

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
        for b in self.result_status_buttons.buttons():
            b.setStyleSheet(_action_status_style(b.isChecked()))
        self._update_after_risk_display()

    def result_status(self) -> str:
        checked = self.result_status_buttons.checkedButton()
        return checked.text() if checked else ""

    def set_result_status(self, status: str) -> None:
        for btn in self.result_status_buttons.buttons():
            btn.setChecked(btn.text() == status)

    def before_risk(self) -> tuple[int | None, int | None]:
        return self.before_likelihood_buttons.value(), self.before_severity_buttons.value()

    def set_before_risk(self, likelihood: int | None, severity: int | None, *, editable: bool) -> None:
        """"이행 전 위험성" 표시값을 채운다. 원본(source_finding)이 있으면 그 값을 그대로
        보여주되 실시간 동기화 원칙(원본이 나중에 바뀌면 다시 열 때 최신 값 반영)을 지키기
        위해 클릭 못 하게 잠그고, 원본이 없으면(수기 추가) 사용자가 직접 고를 수 있게 연다."""
        self.before_likelihood_buttons.set_value(likelihood)
        self.before_severity_buttons.set_value(severity)
        self.before_likelihood_buttons.setEnabled(editable)
        self.before_severity_buttons.setEnabled(editable)
        self._after_cache = (None, None)
        self._update_after_risk_display()

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
        self.set_before_risk(None, None, editable=True)
