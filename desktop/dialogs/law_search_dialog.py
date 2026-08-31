"""법령 검색 모달 — 로컬 캐시(law_article_cache)에서 조번호/키워드로 검색해 선택."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.law_lookup import DEFAULT_LAW_NAME, LawApiError, refresh_law_cache, search_cached_articles


class LawSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("기준규칙 법령")
        self.resize(560, 500)
        self.selected_text: str | None = None
        self._build_ui()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

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

        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(lambda _item: self._apply())
        layout.addWidget(self.result_list)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #9ca3af;")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        apply_btn = QPushButton("✓ 적용하기")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("닫기")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        bottom_row.addWidget(apply_btn)
        layout.addLayout(bottom_row)

    def _search(self) -> None:
        articles = search_cached_articles(self.search_input.text().strip())
        self.result_list.clear()
        if not articles:
            self.hint_label.setText(
                "검색 결과가 없습니다. 캐시가 비어있다면 'AI 관리'에서 법령 API 키를 등록한 뒤 "
                "'캐시 새로고침'을 눌러 법령 전문을 먼저 받아오세요."
            )
        else:
            self.hint_label.setText("")
        for article in articles:
            item = QListWidgetItem(f"제{article.article_no}조({article.title})\n{article.content[:80]}")
            item.setData(1000, f"{article.law_name} 제{article.article_no}조({article.title})")
            self.result_list.addItem(item)

    def _refresh_cache(self) -> None:
        try:
            count = refresh_law_cache(DEFAULT_LAW_NAME)
        except LawApiError as e:
            QMessageBox.warning(self, "법령 API 오류", str(e))
            return
        QMessageBox.information(self, "완료", f"{count}개 조문을 받아왔습니다.")
        self._search()

    def _apply(self) -> None:
        item = self.result_list.currentItem()
        if not item:
            return
        self.selected_text = item.data(1000)
        self.accept()
