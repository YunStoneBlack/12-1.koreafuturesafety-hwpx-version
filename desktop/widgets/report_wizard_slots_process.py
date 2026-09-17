"""7번(현재 진행공정)/9번(향후 진행공정) 전용 슬롯 위젯 — `report_wizard_slots.py`가
Sub-phase 20(공정 사진+AI 분석 전면 개편)으로 600줄을 넘겨 이 파일로 분리했다
(`report_wizard_slots_previous_finding.py`와 같은 분리 패턴).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.vision_analyzer import analyze_process_hazards
from desktop.widgets.photo_drop_zone import PhotoDropZone
from desktop.widgets.report_wizard_slots import _badge_style, _limited_text_edit
from desktop.workers.ai_worker import AIWorker

_RISK_ITEM_OFF_STYLE = (
    "QPushButton { background: white; color: #6b7280; border: 1px solid #d1d5db; "
    "border-radius: 8px; padding: 1px 6px; font-size: 11px; }"
)


class _ProcessHazardItemRow:
    """진행공정 한 항목 — 유해·위험요인/예방대책/위험성이 한 벌로 묶인 위젯 3종.

    바깥(_ProcessSlot)의 hazard_cell/prevention_cell/risk_column은 표의 서로 다른 칼럼이라
    한 위젯으로 합칠 수 없다 — 이 클래스는 항목 하나에 딸린 세 위젯을 만들어 들고 있다가
    `_ProcessSlot._rebuild_item_layout()`이 인덱스 순서를 맞춰 세 칼럼에 나눠 꽂는다.
    삭제 버튼은 `on_remove(self)`로 부모에게 자기 자신을 알려 목록에서 빠지게 한다.
    """

    def __init__(
        self, hazard: str = "", prevention: str = "", risk_level: str = "", on_remove=None
    ):
        self.hazard_edit, hazard_counter = _limited_text_edit(80)
        self.hazard_edit.setPlaceholderText("유해·위험요인")
        self.hazard_edit.setPlainText(hazard)
        self.hazard_edit.setFixedHeight(50)
        self.hazard_widget = QWidget()
        hazard_col = QVBoxLayout(self.hazard_widget)
        hazard_col.setContentsMargins(0, 0, 0, 0)
        hazard_col.setSpacing(2)
        hazard_col.addWidget(self.hazard_edit)
        hazard_col.addWidget(hazard_counter)

        # 예방대책은 이 유해요인 하나에 여러 건(한 줄에 하나씩) 달릴 수 있어 hazard_edit보다
        # 넉넉한 글자수·높이를 준다 — 인쇄 시 줄 단위로 쪼개 각각 "•" 글머리를 붙인다
        # (core/report_builder_hwpx_fields_process.py의 _fill_process_entry_row 참고).
        self.prevention_edit, prevention_counter = _limited_text_edit(200)
        self.prevention_edit.setPlaceholderText("예방대책 (줄바꿈으로 여러 건 입력 가능)")
        self.prevention_edit.setPlainText(prevention)
        self.prevention_edit.setFixedHeight(70)
        self.prevention_widget = QWidget()
        prevention_col = QVBoxLayout(self.prevention_widget)
        prevention_col.setContentsMargins(0, 0, 0, 0)
        prevention_col.setSpacing(2)
        prevention_col.addWidget(self.prevention_edit)
        prevention_col.addWidget(prevention_counter)

        self.risk_widget = QWidget()
        risk_row = QHBoxLayout(self.risk_widget)
        risk_row.setContentsMargins(0, 0, 0, 0)
        risk_row.setSpacing(2)
        self.risk_buttons = QButtonGroup(self.risk_widget)
        self.risk_buttons.setExclusive(False)
        for label in ("상", "중", "하"):
            btn = QPushButton(label)
            btn.setAutoDefault(False)
            btn.setCheckable(True)
            btn.setChecked(label == risk_level)
            btn.setFixedWidth(30)
            btn.setStyleSheet(_badge_style(label) if btn.isChecked() else _RISK_ITEM_OFF_STYLE)
            btn.toggled.connect(self._update_risk_styles)
            btn.clicked.connect(lambda _checked, b=btn: self._on_risk_clicked(b))
            self.risk_buttons.addButton(btn)
            risk_row.addWidget(btn)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setAutoDefault(False)
        self.remove_btn.setFixedWidth(20)
        self.remove_btn.setStyleSheet("QPushButton { color: #ef4444; border: none; background: transparent; }")
        if on_remove is not None:
            self.remove_btn.clicked.connect(lambda: on_remove(self))
        risk_row.addWidget(self.remove_btn)

    def _on_risk_clicked(self, clicked_btn: QPushButton) -> None:
        if not clicked_btn.isChecked():
            return
        for btn in self.risk_buttons.buttons():
            if btn is not clicked_btn:
                btn.setChecked(False)

    def _update_risk_styles(self) -> None:
        for btn in self.risk_buttons.buttons():
            btn.setStyleSheet(_badge_style(btn.text()) if btn.isChecked() else _RISK_ITEM_OFF_STYLE)

    def risk_level(self) -> str:
        checked = next((b for b in self.risk_buttons.buttons() if b.isChecked()), None)
        return checked.text() if checked else ""

    def data(self) -> dict:
        return {
            "hazard": self.hazard_edit.toPlainText().strip(),
            "prevention": self.prevention_edit.toPlainText().strip(),
            "risk_level": self.risk_level(),
        }

    def is_empty(self) -> bool:
        return not self.hazard_edit.toPlainText().strip() and not self.prevention_edit.toPlainText().strip()


class _ProcessSlot(QFrame):
    """7번(현재 진행공정)/9번(향후 진행공정) 공용 "한 칸" (최대 4칸).

    Sub-phase 20: 공정 카탈로그에서 골라 쓰던 방식(내용이 부실하다는 실사용 피드백)을
    버리고, 공정 사진 + 공정명을 넣으면 AI가 유해·위험요인/예방대책/위험성을 항목별로
    여러 건(개수 가변) 한꺼번에 작성해주는 방식으로 전면 개편했다 — 각 항목은
    `_ProcessHazardItemRow`로 표현되고 사람이 항목을 추가/삭제/수정할 수 있다.
    옛 카탈로그 방식(`ProcessPickerDialog`, `ProcessCatalog`)은 코드·데이터 모두 지우지
    않고 남겨뒀다(나중에 다시 쓸 수도 있어서, 사용자 요청) — 이 슬롯이 더 이상 연결하지
    않을 뿐이다. 옛 방식으로 이미 저장된 보고서의 hazard_text/prevention_text/risk_level
    (엔트리 단일값)도 화면에는 더 이상 보여주지 않는다(그대로 DB에 남아있고,
    `report_builder_hwpx_fields_process.py`가 새 항목 데이터가 없을 때만 대체 표시로 쓴다).

    실제 사이트는 위쪽에 "몇 번 칸에 뭘 골랐는지"만 보여주는 압축된 2x2 표와, 그 아래에
    선택된 공정만 번호를 새로 매겨 나열하는 "진행공정/유해·위험요인/예방대책/위험성"
    4열 표, 이렇게 두 영역으로 나뉘어 있다 — 이 위젯은 두 영역에 쓰이는 위젯을 모두
    들고 있고, 실제 배치(어느 그리드/표에 넣을지)는 부모(ReportWizardView)가 한다.
    """

    changed = pyqtSignal()

    def __init__(self, slot: int):
        super().__init__()
        self.slot = slot
        self._worker: AIWorker | None = None
        self._item_rows: list[_ProcessHazardItemRow] = []
        self.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; }")

        self.layout_ = QVBoxLayout(self)

        # ---- 위쪽 2x2 압축 표 칸: 사진 + 공정명 + AI로 작성 + 초기화 ----
        self.photo = PhotoDropZone(f"{slot}번 공정 사진")
        self.layout_.addWidget(self.photo)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(f"{slot}번 공정 이름")
        self.name_input.textChanged.connect(self._on_name_changed)
        self.layout_.addWidget(self.name_input)

        btn_row = QHBoxLayout()
        self.ai_btn = QPushButton("✨ AI로 작성")
        self.ai_btn.setAutoDefault(False)
        self.ai_btn.clicked.connect(self._run_ai)
        self.reset_btn = QPushButton("✕ 초기화")
        self.reset_btn.setAutoDefault(False)
        self.reset_btn.setStyleSheet("QPushButton { color: #ef4444; }")
        self.reset_btn.clicked.connect(self.reset)
        btn_row.addWidget(self.ai_btn)
        btn_row.addWidget(self.reset_btn)
        self.layout_.addLayout(btn_row)

        self.item_count_label = QLabel("작성된 항목 없음")
        self.item_count_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        self.layout_.addWidget(self.item_count_label)

        # ---- 아래쪽 상세 표(진행공정/유해·위험요인/예방대책/위험성)에 쓰일 위젯들 ----
        # 이 위젯들은 self.layout_에 넣지 않는다 — ReportWizardView가 공통 표의
        # 해당 칸(cell)에 직접 addWidget 한다.
        self.detail_name_widget = QWidget()
        name_row = QHBoxLayout(self.detail_name_widget)
        name_row.setContentsMargins(8, 8, 8, 8)
        self.seq_label = QLabel("")
        self.seq_label.setStyleSheet("font-weight: 600; border: none; background: transparent;")
        self.name_display = QLabel("")
        self.name_display.setWordWrap(True)
        self.name_display.setStyleSheet("font-weight: 600; border: none; background: transparent;")
        name_row.addWidget(self.seq_label)
        name_row.addWidget(self.name_display, 1)

        self.hazard_cell = QWidget()
        self.hazard_layout = QVBoxLayout(self.hazard_cell)
        self.hazard_layout.setContentsMargins(8, 8, 8, 8)
        self.hazard_layout.setSpacing(4)

        self.prevention_cell = QWidget()
        self.prevention_layout = QVBoxLayout(self.prevention_cell)
        self.prevention_layout.setContentsMargins(8, 8, 8, 8)
        self.prevention_layout.setSpacing(4)

        self.risk_column = QWidget()
        self.risk_layout = QVBoxLayout(self.risk_column)
        self.risk_layout.setContentsMargins(8, 8, 8, 8)
        self.risk_layout.setSpacing(4)

        self.add_item_btn = QPushButton("+ 항목 추가")
        self.add_item_btn.setAutoDefault(False)
        self.add_item_btn.setStyleSheet(
            "QPushButton { background: #f5f3ff; color: #7c3aed; border: 1px dashed #c4b5fd; "
            "border-radius: 6px; padding: 4px; font-size: 11px; }"
        )
        self.add_item_btn.clicked.connect(lambda: self._add_item_row())

        self._rebuild_item_layout()

    def _on_name_changed(self, text: str) -> None:
        self.name_display.setText(text)
        self.changed.emit()

    def _add_item_row(self, hazard: str = "", prevention: str = "", risk_level: str = "") -> None:
        row = _ProcessHazardItemRow(hazard, prevention, risk_level, on_remove=self._remove_item_row)
        self._item_rows.append(row)
        self._rebuild_item_layout()

    def _remove_item_row(self, row: _ProcessHazardItemRow) -> None:
        if row in self._item_rows:
            self._item_rows.remove(row)
        self._rebuild_item_layout()

    def _rebuild_item_layout(self) -> None:
        for layout in (self.hazard_layout, self.prevention_layout, self.risk_layout):
            while layout.count():
                taken = layout.takeAt(0)
                widget = taken.widget()
                if widget is not None:
                    widget.setParent(None)
        for row in self._item_rows:
            self.hazard_layout.addWidget(row.hazard_widget)
            self.prevention_layout.addWidget(row.prevention_widget)
            self.risk_layout.addWidget(row.risk_widget)
        self.hazard_layout.addWidget(self.add_item_btn)
        count = len(self._item_rows)
        self.item_count_label.setText(f"{count}개 항목" if count else "작성된 항목 없음")

    def load_items(self, items: list[dict]) -> None:
        self._item_rows = [
            _ProcessHazardItemRow(
                item.get("hazard", ""), item.get("prevention", ""), item.get("risk_level", ""),
                on_remove=self._remove_item_row,
            )
            for item in items
        ]
        self._rebuild_item_layout()

    def items_data(self) -> list[dict]:
        return [row.data() for row in self._item_rows if not row.is_empty()]

    def has_data(self) -> bool:
        # 현장 정책상 사진을 못 올리는 현장이 있어(사용자 요청, 2026-09-17) 사진만 있고
        # 공정명이 비어있는 슬롯도 "채워짐"으로 봐야 저장 시 무시되지 않는다.
        return bool(self.name_input.text().strip()) or bool(self.photo.photo_path)

    def reset(self) -> None:
        self.photo.clear_photo()
        self.name_input.clear()
        self._item_rows = []
        self._rebuild_item_layout()
        self.changed.emit()

    def _run_ai(self) -> None:
        # 사진 + 공정명 둘 다 필수였지만, 현장 정책상 사진을 못 올리는 현장을 위해 사진만/
        # 공정명만/둘 다 중 하나만 있어도 작성할 수 있게 한다(사용자 요청, 2026-09-17).
        photo_path = self.photo.photo_path or None
        process_name = self.name_input.text().strip()
        if not photo_path and not process_name:
            QMessageBox.warning(self, "입력 필요", "공정 사진 또는 공정 이름 중 하나 이상을 입력해주세요.")
            return
        if not config.has_api_key():
            QMessageBox.warning(self, "API 키 필요", "'AI 관리' 화면에서 Claude API 키를 먼저 등록하세요.")
            return
        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("분석 중...")
        self._worker = AIWorker(lambda: analyze_process_hazards(photo_path, process_name))
        self._worker.finished_ok.connect(self._on_ai_done)
        self._worker.finished_error.connect(self._on_ai_error)
        self._worker.start()

    def _on_ai_done(self, items: list[dict]) -> None:
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("✨ AI로 작성")
        if not items:
            QMessageBox.information(
                self, "분석 실패", "사진에서 유해·위험요인을 찾지 못했습니다. 직접 입력해주세요."
            )
            return
        self.load_items(items)

    def _on_ai_error(self, message: str) -> None:
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("✨ AI로 작성")
        QMessageBox.warning(self, "AI 분석 실패", message)
