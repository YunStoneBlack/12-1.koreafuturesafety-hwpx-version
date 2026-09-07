"""진행공정 선택 모달 — 공정 카탈로그(실제 서비스 데이터, 284건)에서 검색/카테고리
필터로 골라 선택. 카탈로그에 없는 공정은 "+ 새 공정 등록"으로 직접 추가하면 다음부터
검색에 잡힌다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func

from core.db import SessionLocal
from core.hangul_match import matches as hangul_matches
from core.models_db import ProcessCatalog
from desktop.widgets.debounced_search_input import DebouncedSearchInput

_CHIP_STYLE_OFF = (
    "QPushButton { background: white; color: #4b5563; border: 1px solid #d1d5db; "
    "border-radius: 14px; padding: 3px 12px; font-size: 12px; }"
)
_CHIP_STYLE_ON = (
    "QPushButton { background: #4f46e5; color: white; border: 1px solid #4f46e5; "
    "border-radius: 14px; padding: 3px 12px; font-size: 12px; }"
)

# report_wizard_view.py의 _RISK_BADGE_COLORS와 동일한 배색 (실제 사이트 기준).
_RISK_BADGE_COLORS = {
    "상": ("#dc2626", "#fef2f2", "#fecaca"),
    "중": ("#b45309", "#fffbeb", "#fde68a"),
    "하": ("#16a34a", "#f0fdf4", "#bbf7d0"),
}


def _risk_badge_style(level: str) -> str:
    fg, bg, border = _RISK_BADGE_COLORS.get(level, ("#6b7280", "#f9fafb", "#e5e7eb"))
    return (
        f"QLabel {{ color: {fg}; background: {bg}; border: 1px solid {border}; "
        "border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 12px; }"
    )


def _risk_button_style(level: str) -> str:
    fg, bg, border = _RISK_BADGE_COLORS.get(level, ("#6b7280", "#f9fafb", "#e5e7eb"))
    return (
        f"QPushButton {{ color: {fg}; background: {bg}; border: 1px solid {border}; "
        "border-radius: 10px; padding: 2px 8px; font-weight: 600; font-size: 12px; }"
    )


class _ProcessRow(QWidget):
    """공정 목록 한 줄 (setItemWidget 대상). QLabel만으로 구성돼도 클릭/더블클릭이
    QListWidget까지 전달되지 않는 경우가 있어(자식 위젯이 이벤트를 먼저 받음),
    이 위젯이 직접 선택/적용을 처리한다."""

    def __init__(self, dialog: "ProcessPickerDialog", list_item: QListWidgetItem):
        super().__init__()
        self._dialog = dialog
        self._list_item = list_item

    def mousePressEvent(self, event) -> None:
        self._dialog.result_list.setCurrentItem(self._list_item)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._dialog.result_list.setCurrentItem(self._list_item)
        self._dialog._apply()
        super().mouseDoubleClickEvent(event)


class ProcessPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("공정 선택")
        self.resize(680, 620)
        self.selected: dict | None = None
        self._active_category: str | None = None  # None = 전체
        self._build_ui()
        self._load_categories()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.search_input = DebouncedSearchInput(delay_ms=250)
        self.search_input.setPlaceholderText("공정명으로 검색 (예: 굴착, 도장, 방수...)")
        self.search_input.search_triggered.connect(self._search)
        layout.addWidget(self.search_input)

        chip_scroll = QScrollArea()
        chip_scroll.setWidgetResizable(True)
        chip_scroll.setFixedHeight(110)
        chip_container = QWidget()
        self._chip_layout = QGridLayout(chip_container)
        self._chip_layout.setSpacing(6)
        chip_scroll.setWidget(chip_container)
        layout.addWidget(chip_scroll)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.count_label)

        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(lambda _item: self._apply())
        layout.addWidget(self.result_list, stretch=1)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #9ca3af;")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        add_row = QHBoxLayout()
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("카탈로그에 없으면 새 공정명을 입력...")
        add_btn = QPushButton("+ 새 공정 등록")
        add_btn.clicked.connect(self._add_new)
        add_row.addWidget(self.new_name_input, stretch=1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        detail_row = QHBoxLayout()
        self.new_hazard_input = QTextEdit()
        self.new_hazard_input.setPlaceholderText("유해위험요인 (세부 내용) — 항목이 여러 개면 Enter로 줄바꿈")
        self.new_hazard_input.setFixedHeight(60)
        self.new_prevention_input = QTextEdit()
        self.new_prevention_input.setPlaceholderText("예방대책 — 항목이 여러 개면 Enter로 줄바꿈")
        self.new_prevention_input.setFixedHeight(60)
        detail_row.addWidget(self.new_hazard_input, stretch=1)
        detail_row.addWidget(self.new_prevention_input, stretch=1)
        self.new_risk_buttons = QButtonGroup(self)
        self.new_risk_buttons.setExclusive(True)
        for label in ("상", "중", "하"):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(36)
            btn.setStyleSheet(_risk_button_style(""))
            btn.toggled.connect(lambda checked, b=btn: b.setStyleSheet(_risk_button_style(b.text() if checked else "")))
            self.new_risk_buttons.addButton(btn)
            detail_row.addWidget(btn)
        layout.addLayout(detail_row)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        apply_btn = QPushButton("✓ 선택")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        bottom_row.addWidget(apply_btn)
        layout.addLayout(bottom_row)

    def _load_categories(self) -> None:
        with SessionLocal() as session:
            total = session.query(ProcessCatalog).count()
            # 카테고리 칩도 실제 사이트의 원래 버튼 순서(카테고리 안에서 가장 먼저 나온
            # 공정의 sort_order 기준)와 동일하게 정렬한다.
            rows = (
                session.query(ProcessCatalog.category, func.count(), func.min(ProcessCatalog.sort_order))
                .group_by(ProcessCatalog.category)
                .order_by(func.min(ProcessCatalog.sort_order))
                .all()
            )
            rows = [(cat, cnt) for cat, cnt, _min_order in rows]

        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        columns = 3
        entries = [("전체", total, None)] + [(cat or "(미분류)", cnt, cat) for cat, cnt in rows]
        for idx, (label, count, value) in enumerate(entries):
            btn = QPushButton(f"{label} {count}")
            btn.setCheckable(True)
            btn.setChecked(value is None)
            btn.setStyleSheet(_CHIP_STYLE_ON if value is None else _CHIP_STYLE_OFF)
            btn.clicked.connect(lambda _checked, v=value: self._on_category_clicked(v))
            self._chip_group.addButton(btn)
            self._chip_layout.addWidget(btn, idx // columns, idx % columns)

    def _on_category_clicked(self, category: str | None) -> None:
        self._active_category = category
        for btn in self._chip_group.buttons():
            is_active = btn.isChecked()
            btn.setStyleSheet(_CHIP_STYLE_ON if is_active else _CHIP_STYLE_OFF)
        self._search()

    def _search(self) -> None:
        keyword = self.search_input.current_text().strip()
        with SessionLocal() as session:
            query = session.query(ProcessCatalog)
            if self._active_category:
                query = query.filter(ProcessCatalog.category == self._active_category)
            rows = query.order_by(ProcessCatalog.sort_order).all()
        # 자모 단위 매칭은 SQL LIKE로 못 하므로(원본 텍스트가 아니라 분해한 자모열끼리
        # 비교해야 함) 파이썬에서 거른다. 카탈로그가 284건뿐이라 성능은 문제없다.
        items = [row for row in rows if hangul_matches(keyword, row.process_name)][:200]

        self.result_list.clear()
        if not items:
            self.hint_label.setText(
                "검색 결과가 없습니다. 공정 카탈로그에 없으면 아래에서 공정명을 직접 입력해 등록하세요."
            )
        else:
            self.hint_label.setText("")

        label = self._active_category or "전체"
        self.count_label.setText(f"{len(items)}개 · {label}")

        for item in items:
            # 목록에는 실제 사이트처럼 첫 줄만 짧게 보여준다. 선택 시 넘어가는 hazard_text는
            # 아래 setData에서 전체(여러 줄)를 그대로 쓰므로 정보 손실은 없다.
            first_line = item.hazard_text.split("\n", 1)[0].lstrip("-").strip()

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 6, 10, 6)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_label = QLabel(item.process_name)
            name_label.setStyleSheet("font-weight: 600;")
            desc_label = QLabel(first_line[:60])
            desc_label.setStyleSheet("color: #6b7280; font-size: 12px;")
            text_col.addWidget(name_label)
            text_col.addWidget(desc_label)
            row_layout.addLayout(text_col, stretch=1)
            if item.default_risk_level:
                badge = QLabel(item.default_risk_level)
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setStyleSheet(_risk_badge_style(item.default_risk_level))
                row_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)

            # 직접 등록한 항목만 지울 수 있게 한다 — 시딩된 카탈로그(284건)는 이 화면에서
            # 실수로 지워지면 안 되므로 대상에서 뺀다.
            if item.category == "직접 등록":
                del_btn = QPushButton("🗑")
                del_btn.setFixedWidth(28)
                del_btn.setToolTip("이 항목 삭제")
                del_btn.clicked.connect(
                    lambda _checked, cid=item.id, nm=item.process_name: self._delete_catalog_item(cid, nm)
                )
                row_layout.addWidget(del_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

            list_item = QListWidgetItem()
            list_item.setData(
                1000,
                {
                    "process_name": item.process_name,
                    "hazard_text": item.hazard_text,
                    "prevention_text": item.prevention_text,
                    "risk_level": item.default_risk_level,
                },
            )
            list_item.setSizeHint(row_widget.sizeHint())
            self.result_list.addItem(list_item)
            self.result_list.setItemWidget(list_item, row_widget)

    def _add_new(self) -> None:
        name = self.new_name_input.text().strip()
        if not name:
            return
        hazard_text = self.new_hazard_input.toPlainText().strip()
        prevention_text = self.new_prevention_input.toPlainText().strip()
        risk_btn = self.new_risk_buttons.checkedButton()
        risk_level = risk_btn.text() if risk_btn else ""
        with SessionLocal() as session:
            session.add(
                ProcessCatalog(
                    category="직접 등록",
                    process_name=name,
                    hazard_text=hazard_text,
                    prevention_text=prevention_text,
                    default_risk_level=risk_level,
                    reviewed=bool(hazard_text),
                )
            )
            session.commit()
        self.new_name_input.clear()
        self.new_hazard_input.clear()
        self.new_prevention_input.clear()
        for btn in self.new_risk_buttons.buttons():
            btn.setChecked(False)
            btn.setStyleSheet(_risk_button_style(""))
        self._search()
        QMessageBox.information(self, "등록 완료", f"'{name}' 공정을 카탈로그에 등록했습니다.")

    def _delete_catalog_item(self, catalog_id: int, name: str) -> None:
        reply = QMessageBox.question(self, "공정 삭제", f"'{name}' 공정을 카탈로그에서 삭제하시겠습니까?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as session:
            row = session.get(ProcessCatalog, catalog_id)
            if row:
                session.delete(row)
                session.commit()
        self._search()

    def _apply(self) -> None:
        item = self.result_list.currentItem()
        if not item:
            return
        self.selected = item.data(1000)
        self.accept()
