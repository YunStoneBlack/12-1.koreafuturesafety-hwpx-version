"""대시보드(홈) 화면 — 통계 카드, 현장 목록/검색/상태 필터."""

from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func

from core.db import SessionLocal
from core.models_db import Report, Site

_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
_STATUS_TABS = ["진행중", "완료", "보류"]


class _StatCard(QFrame):
    def __init__(self, accent: str, value: str, label: str, sub: str):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background: white; border: 1px solid #e5e7eb; border-left: 4px solid {accent}; "
            f"border-radius: 8px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        label_widget = QLabel(label)
        label_widget.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.sub_label = QLabel(sub)
        self.sub_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(label_widget)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)


class _SiteCard(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, site: Site, report_summary: str):
        super().__init__()
        self._site_id = site.id
        self.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }"
            "QFrame:hover { border-color: #4f46e5; }"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        name = QLabel(site.name or "(이름 없음)")
        name.setStyleSheet("font-size: 14px; font-weight: 600;")
        sub = QLabel(report_summary)
        sub.setStyleSheet("color: #9ca3af; font-size: 12px;")
        layout.addWidget(name)
        layout.addWidget(sub)

    def mousePressEvent(self, event):  # noqa: N802 (Qt override)
        self.clicked.emit(self._site_id)
        super().mousePressEvent(event)


class DashboardView(QWidget):
    new_site_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    staff_requested = pyqtSignal()
    site_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_status = "진행중"
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        today = datetime.date.today()
        weekday = _WEEKDAYS_KO[today.weekday()]
        date_label = QLabel(f"{today.year}년 {today.month}월 {today.day}일 ({weekday})")
        date_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.greeting_label = QLabel("한국미래안전님, 안녕하세요")
        self.greeting_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #6b7280;")
        header_text.addWidget(date_label)
        header_text.addWidget(self.greeting_label)
        header_text.addWidget(self.summary_label)
        header_row.addLayout(header_text)
        header_row.addStretch()

        staff_btn = QPushButton("👥 담당요원")
        staff_btn.clicked.connect(self.staff_requested.emit)
        settings_btn = QPushButton("⚙ AI 관리")
        settings_btn.clicked.connect(self.settings_requested.emit)
        new_site_btn = QPushButton("+ 신규현장 추가")
        new_site_btn.setStyleSheet(
            "QPushButton { background: #111827; color: white; padding: 8px 16px; border-radius: 6px; }"
        )
        new_site_btn.clicked.connect(self.new_site_requested.emit)
        header_row.addWidget(staff_btn)
        header_row.addWidget(settings_btn)
        header_row.addWidget(new_site_btn)
        root.addLayout(header_row)

        stats_row = QHBoxLayout()
        self.stat_total = _StatCard("#3b82f6", "0개", "전체 현장", "")
        self.stat_progress = _StatCard("#8b5cf6", "0%", "평균 공정률", "전체 현장 평균")
        self.stat_reports = _StatCard("#10b981", "0건", "작성 보고서", "시스템 내 저장된 보고서")
        self.stat_missing = _StatCard("#ef4444", "0개", "보고서 미작성", "")
        for card in (self.stat_total, self.stat_progress, self.stat_reports, self.stat_missing):
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        list_label = QLabel("현장 목록")
        list_label.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 8px;")
        root.addWidget(list_label)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("현장명으로 검색...")
        self.search_input.textChanged.connect(self.refresh)
        search_row.addWidget(self.search_input)
        root.addLayout(search_row)

        tabs_row = QHBoxLayout()
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons: dict[str, QPushButton] = {}
        for status in _STATUS_TABS:
            btn = QPushButton(status)
            btn.setCheckable(True)
            btn.setChecked(status == self._active_status)
            btn.clicked.connect(lambda _checked, s=status: self._on_tab_clicked(s))
            self._tab_group.addButton(btn)
            self._tab_buttons[status] = btn
            tabs_row.addWidget(btn)
        tabs_row.addStretch()
        root.addLayout(tabs_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        root.addWidget(scroll)

    def _on_tab_clicked(self, status: str) -> None:
        self._active_status = status
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            all_sites = session.query(Site).all()
            total_count = len(all_sites)
            in_progress_count = sum(1 for s in all_sites if s.status == "진행중")
            report_count = session.query(Report).count()
            sites_with_reports = {r[0] for r in session.query(Report.site_id).distinct().all()}
            missing_count = total_count - len(sites_with_reports)

            avg_progress = (
                session.query(func.avg(Report.progress_rate)).scalar() if report_count else None
            )

            self.summary_label.setText(f"한국미래안전 · {total_count}개 현장을 관리하고 있습니다")
            self.stat_total.value_label.setText(f"{total_count}개")
            self.stat_total.sub_label.setText(f"진행중 {in_progress_count}개")
            self.stat_progress.value_label.setText(f"{round(avg_progress or 0)}%")
            self.stat_reports.value_label.setText(f"{report_count}건")
            self.stat_missing.value_label.setText(f"{missing_count}개")

            for status, btn in self._tab_buttons.items():
                count = sum(1 for s in all_sites if s.status == status)
                btn.setText(f"{status}인 현장 {count}" if status == "진행중" else f"{status}된 현장 {count}")

            keyword = self.search_input.text().strip()
            filtered = [
                s
                for s in all_sites
                if s.status == self._active_status and (keyword in (s.name or "") if keyword else True)
            ]

            while self._list_layout.count() > 1:
                item = self._list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for site in filtered:
                report_count_for_site = (
                    session.query(Report).filter(Report.site_id == site.id).count()
                )
                summary = f"{report_count_for_site}건 작성됨" if report_count_for_site else "작성된 보고서 없음"
                card = _SiteCard(site, summary)
                card.clicked.connect(self.site_selected.emit)
                self._list_layout.insertWidget(self._list_layout.count() - 1, card)
