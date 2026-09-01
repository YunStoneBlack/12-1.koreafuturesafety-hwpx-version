"""제공자료 전체보기 모달 — 썸네일 그리드에서 검색해 최대 N개 선택, 새 자료 등록도 여기서."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.db import SessionLocal
from core.hangul_match import matches as hangul_matches
from core.models_db import MaterialLibrary
from desktop.widgets.cursors import zoom_cursor
from desktop.widgets.debounced_search_input import DebouncedSearchInput

_CARD_STYLE = "QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }"
_SELECT_STYLE_OFF = "QPushButton { background: #2563eb; color: white; border-radius: 4px; padding: 4px; }"
_SELECT_STYLE_ON = "QPushButton { background: #16a34a; color: white; border-radius: 4px; padding: 4px; }"


class ClickableThumb(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):  # noqa: N802 (Qt override)
        self.clicked.emit()
        super().mousePressEvent(event)


class MaterialPreviewDialog(QDialog):
    """썸네일을 클릭했을 때 원본을 크게 보여주는 모달."""

    def __init__(self, material: MaterialLibrary, parent=None):
        super().__init__(parent)
        self.setWindowTitle(material.title)

        layout = QVBoxLayout(self)
        title = QLabel(material.title)
        title.setStyleSheet("font-weight: 700; font-size: 14px;")
        title.setWordWrap(True)
        layout.addWidget(title)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = self._load_large_pixmap(material)
        if pixmap and not pixmap.isNull():
            # 이미지 전체가 스크롤 없이 한 화면에 다 보이도록, 화면 크기에 맞춰 축소한다.
            screen = self.screen() or QApplication.primaryScreen()
            available = screen.availableGeometry()
            max_width = int(available.width() * 0.85)
            max_height = int(available.height() * 0.85) - 80  # 제목/닫기 버튼 높이 여유

            fitted = pixmap.scaled(
                max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            image_label.setPixmap(fitted)
            self.resize(fitted.width() + 32, fitted.height() + 96)
        else:
            image_label.setText("미리보기를 표시할 수 없습니다.")
            self.resize(400, 200)

        layout.addWidget(image_label, stretch=1)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _load_large_pixmap(self, material: MaterialLibrary) -> QPixmap | None:
        path = Path(material.file_path)
        suffix = path.suffix.lower()
        if suffix in (".jpg", ".jpeg", ".png") and path.exists():
            return QPixmap(str(path))
        if suffix == ".pdf" and path.exists():
            try:
                import pymupdf

                doc = pymupdf.open(str(path))
                page = doc.load_page(0)
                zoom = 900 / page.rect.width
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                image = QPixmap()
                image.loadFromData(pix.tobytes("png"))
                doc.close()
                return image
            except Exception:
                pass
        if material.thumbnail_path and Path(material.thumbnail_path).exists():
            return QPixmap(material.thumbnail_path)
        return None


class _MaterialCard(QFrame):
    def __init__(self, material: MaterialLibrary, selected: bool, on_toggle):
        super().__init__()
        self.material_id = material.id
        self._material = material
        self._on_toggle = on_toggle
        self.setStyleSheet(_CARD_STYLE)
        self.setFixedWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        thumb = ClickableThumb()
        thumb.setFixedSize(134, 100)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("background: #f3f4f6; border-radius: 4px;")
        thumb.setCursor(zoom_cursor())
        thumb.clicked.connect(self._open_preview)
        pixmap = QPixmap(material.thumbnail_path) if material.thumbnail_path else QPixmap()
        if material.thumbnail_path and not pixmap.isNull():
            thumb.setPixmap(
                pixmap.scaled(134, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            thumb.setText("📄")
            thumb.setStyleSheet(thumb.styleSheet() + "font-size: 28px; color: #9ca3af;")
        layout.addWidget(thumb)

        title = QLabel(material.title)
        title.setWordWrap(True)
        title.setFixedHeight(48)
        title.setStyleSheet("font-size: 11px;")
        layout.addWidget(title)

        self.select_btn = QPushButton()
        self.select_btn.clicked.connect(lambda: self._on_toggle(self.material_id))
        layout.addWidget(self.select_btn)
        self.set_selected(selected)

    def _open_preview(self) -> None:
        dialog = MaterialPreviewDialog(self._material, self)
        dialog.exec()

    def set_selected(self, selected: bool) -> None:
        self.select_btn.setText("✓ 선택됨 (빼기)" if selected else "선택")
        self.select_btn.setStyleSheet(_SELECT_STYLE_ON if selected else _SELECT_STYLE_OFF)


class MaterialPickerDialog(QDialog):
    def __init__(self, max_select: int = 2, already_selected: list[int] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("제공자료 전체보기")
        self.resize(680, 640)
        self.max_select = max_select
        self.selected_ids: set[int] = set(already_selected or [])
        self._cards: dict[int, _MaterialCard] = {}
        self._build_ui()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self.count_label)

        # 타이핑할 때마다 즉시 다시 그리면 카드 100여개를 매번 다시 렌더링하게 되어
        # 눈에 띄게 끊긴다. 입력이 잠깐 멈췄을 때만 실제로 검색하도록 디바운스한다.
        # 한글 IME 조합 중간 상태(예: "안전" 입력 중 "안"만 잡히는 것)도 함께 방지한다.
        self.search_input = DebouncedSearchInput(delay_ms=250)
        self.search_input.setPlaceholderText("제목으로 좁히기")
        self.search_input.search_triggered.connect(self._search)
        layout.addWidget(self.search_input)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(10)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, stretch=1)

        register_row = QHBoxLayout()
        self.new_title_input = QLineEdit()
        self.new_title_input.setPlaceholderText("새 자료 제목")
        self.new_tags_input = QLineEdit()
        self.new_tags_input.setPlaceholderText("태그(쉼표 구분)")
        pick_file_btn = QPushButton("파일 선택")
        pick_file_btn.clicked.connect(self._register_material)
        register_row.addWidget(self.new_title_input)
        register_row.addWidget(self.new_tags_input)
        register_row.addWidget(pick_file_btn)
        layout.addLayout(register_row)

        bottom_row = QHBoxLayout()
        self.selection_label = QLabel("")
        self.selection_label.setStyleSheet("color: #6b7280;")
        bottom_row.addWidget(self.selection_label)
        bottom_row.addStretch()
        done_btn = QPushButton("완료")
        done_btn.clicked.connect(self.accept)
        bottom_row.addWidget(done_btn)
        layout.addLayout(bottom_row)

    def _search(self) -> None:
        keyword = self.search_input.current_text().strip()
        with SessionLocal() as session:
            all_items = session.query(MaterialLibrary).order_by(MaterialLibrary.id.desc()).all()
        # 자모 단위 매칭은 SQL LIKE로 못 하므로(원본 텍스트가 아니라 분해한 자모열끼리
        # 비교해야 함) 파이썬에서 거른다. 라이브러리가 81건뿐이라 성능은 문제없다.
        items = [m for m in all_items if hangul_matches(keyword, m.title)][:120]
        total = len(all_items)

        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cards: dict[int, _MaterialCard] = {}
        columns = 4
        for idx, material in enumerate(items):
            card = _MaterialCard(material, material.id in self.selected_ids, self._toggle_material)
            self._cards[material.id] = card
            self._grid_layout.addWidget(card, idx // columns, idx % columns)

        if keyword:
            self.count_label.setText(f"{len(items)}개 / 전체 {total}개 · 최대 {self.max_select}개 선택")
        else:
            self.count_label.setText(f"전체 {total}개 · 최대 {self.max_select}개 선택")
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        remaining = self.max_select - len(self.selected_ids)
        self.selection_label.setText(f"{len(self.selected_ids)}개 담김 · {remaining}개 더 담을 수 있습니다")

    def _toggle_material(self, material_id: int) -> None:
        if material_id in self.selected_ids:
            self.selected_ids.discard(material_id)
        elif len(self.selected_ids) < self.max_select:
            self.selected_ids.add(material_id)
        else:
            QMessageBox.information(self, "선택 제한", f"최대 {self.max_select}개까지 선택할 수 있습니다.")
            return
        # 카드 100여개를 통째로 다시 그리지 않고, 상태가 바뀐 카드만 갱신한다.
        card = self._cards.get(material_id)
        if card:
            card.set_selected(material_id in self.selected_ids)
        self._update_selection_label()

    def _register_material(self) -> None:
        title = self.new_title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "제목 필요", "자료 제목을 먼저 입력하세요.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "자료 파일 선택")
        if not file_path:
            return

        from core.thumbnail_generator import generate_image_thumbnail, generate_pdf_thumbnail

        thumbnail_path = ""
        suffix = Path(file_path).suffix.lower()
        thumbs_dir = Path(file_path).resolve().parent.parent / "materials" / "thumbnails"
        if suffix in (".jpg", ".jpeg", ".png"):
            thumb_dest = thumbs_dir / f"{Path(file_path).stem}_thumb.jpg"
            if generate_image_thumbnail(file_path, thumb_dest):
                thumbnail_path = str(thumb_dest)
        elif suffix == ".pdf":
            thumb_dest = thumbs_dir / f"{Path(file_path).stem}.png"
            if generate_pdf_thumbnail(file_path, thumb_dest):
                thumbnail_path = str(thumb_dest)

        with SessionLocal() as session:
            session.add(
                MaterialLibrary(
                    title=title,
                    file_path=file_path,
                    thumbnail_path=thumbnail_path,
                    tags=self.new_tags_input.text().strip(),
                )
            )
            session.commit()
        self.new_title_input.clear()
        self.new_tags_input.clear()
        self._search()

    def get_selected_materials(self) -> list[MaterialLibrary]:
        with SessionLocal() as session:
            return (
                session.query(MaterialLibrary).filter(MaterialLibrary.id.in_(self.selected_ids)).all()
                if self.selected_ids
                else []
            )
