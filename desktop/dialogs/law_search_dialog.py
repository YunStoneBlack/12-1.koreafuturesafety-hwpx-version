"""법령 검색 모달 — 로컬 캐시(law_article_cache)에서 조번호/키워드로 검색해 선택.

실제 사이트처럼 카드형 목록으로 보여주고, 카드를 클릭하면 그 카드가 펼쳐지며 전체
조문을 보여준다(아코디언 방식). 펼쳐져(선택되어) 있는 카드가 "적용하기"를 눌렀을 때
반영되는 대상이다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.law_lookup import DEFAULT_LAW_NAME, LawApiError, refresh_law_cache, search_cached_articles

_CARD_STYLE_OFF = "QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }"
_CARD_STYLE_ON = "QFrame { background: #f5f3ff; border: 1px solid #7c3aed; border-radius: 8px; }"


def _article_label(article) -> str:
    return f"제{article.article_no}({article.title})" if article.title else f"제{article.article_no}"


class _ArticleCard(QFrame):
    def __init__(self, dialog: "LawSearchDialog", article):
        super().__init__()
        self._dialog = dialog
        self.article = article
        self.setStyleSheet(_CARD_STYLE_OFF)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # QLabel은 내부적으로 QFrame을 상속하기 때문에, 라벨에 스타일시트를 지정하는
        # 순간 부모 카드의 "QFrame { border: ...; background: ... }" 규칙까지 함께
        # 물려받아 라벨마다 테두리 상자가 하나씩 더 생기는 문제가 있다. 그래서 색상/굵기
        # 외에 border/background도 명시적으로 꺼둔다.
        _label_reset = "border: none; background: transparent;"

        self.title_label = QLabel(_article_label(article))
        self.title_label.setStyleSheet(f"font-weight: 700; {_label_reset}")
        layout.addWidget(self.title_label)

        first_line = article.content.split("\n", 1)[0]
        self.preview_label = QLabel(first_line)
        self.preview_label.setStyleSheet(f"color: #6b7280; {_label_reset}")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        self.full_label = QLabel(article.content)
        self.full_label.setWordWrap(True)
        self.full_label.setStyleSheet(f"color: #374151; {_label_reset}")
        self.full_label.setVisible(False)
        layout.addWidget(self.full_label)

    def set_expanded(self, expanded: bool) -> None:
        self.preview_label.setVisible(not expanded)
        self.full_label.setVisible(expanded)
        self.setStyleSheet(_CARD_STYLE_ON if expanded else _CARD_STYLE_OFF)

    def mousePressEvent(self, event) -> None:
        self._dialog._select_card(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._dialog._select_card(self)
        self._dialog._apply()
        super().mouseDoubleClickEvent(event)


class LawSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("기준규칙 법령")
        self.resize(620, 640)
        self.selected_text: str | None = None
        self._cards: list[_ArticleCard] = []
        self._selected_card: _ArticleCard | None = None
        self._build_ui()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 이 다이얼로그는 스타일 지정된 QFrame 카드(예: 지적사항 칸)를 parent로 열리는데,
        # QLabel도 내부적으로 QFrame이라 라벨에 스타일시트를 지정하면(색상/굵기만 지정해도)
        # 그 부모 카드의 border/background까지 새어 들어온다. 명시적으로 꺼둔다.
        _label_reset = "border: none; background: transparent;"

        header_row = QHBoxLayout()
        title = QLabel("기준규칙 법령")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; {_label_reset}")
        header_row.addWidget(title)
        header_row.addStretch()
        apply_btn = QPushButton("✓ 적용하기")
        apply_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; border-radius: 6px; "
            "padding: 6px 14px; font-weight: 600; }"
        )
        apply_btn.clicked.connect(self._apply)
        header_row.addWidget(apply_btn)
        layout.addLayout(header_row)

        hint = QLabel("조항을 눌러 내용을 확인한 뒤 적용하기를 누르세요")
        hint.setStyleSheet(f"color: #9ca3af; font-size: 12px; {_label_reset}")
        layout.addWidget(hint)

        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("조번호 또는 키워드로 검색 (예: 3조, 추락)")
        self.search_input.textChanged.connect(self._search)
        refresh_btn = QPushButton("↻ 캐시 새로고침")
        refresh_btn.setToolTip("국가법령정보센터 API로 법령 전문을 다시 받아옵니다 (AI 관리에서 OC 키 필요)")
        refresh_btn.clicked.connect(self._refresh_cache)
        top_row.addWidget(self.search_input)
        top_row.addWidget(refresh_btn)
        layout.addLayout(top_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: #f9fafb; border: 1px solid #e5e7eb; }")
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll, stretch=1)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet(f"color: #9ca3af; {_label_reset}")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        cancel_btn = QPushButton("닫기")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        layout.addLayout(bottom_row)

    def _clear_cards(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards = []
        self._selected_card = None

    def _search(self) -> None:
        articles = search_cached_articles(self.search_input.text().strip())
        self._clear_cards()
        if not articles:
            self.hint_label.setText(
                "검색 결과가 없습니다. 캐시가 비어있다면 'AI 관리'에서 법령 API 키를 등록한 뒤 "
                "'캐시 새로고침'을 눌러 법령 전문을 먼저 받아오세요."
            )
        else:
            self.hint_label.setText("")
        for article in articles:
            card = _ArticleCard(self, article)
            self.list_layout.addWidget(card)
            self._cards.append(card)
        self.list_layout.addStretch()

    def _select_card(self, card: _ArticleCard) -> None:
        if self._selected_card is card:
            return
        if self._selected_card is not None:
            self._selected_card.set_expanded(False)
        card.set_expanded(True)
        self._selected_card = card

    def _refresh_cache(self) -> None:
        try:
            count = refresh_law_cache(DEFAULT_LAW_NAME)
        except LawApiError as e:
            QMessageBox.warning(self, "법령 API 오류", str(e))
            return
        QMessageBox.information(self, "완료", f"{count}개 조문을 받아왔습니다.")
        self._search()

    def _apply(self) -> None:
        if not self._selected_card:
            QMessageBox.information(self, "선택 필요", "적용할 조항을 먼저 눌러 선택하세요.")
            return
        article = self._selected_card.article
        self.selected_text = f"{article.law_name} {_article_label(article)}"
        self.accept()
