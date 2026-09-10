"""제공자료 라이브러리 관리(추가/수정/삭제) 모달 — `material_picker_dialog.py`가 600줄을
넘겨 분리했다. "전체보기"(선택) 쪽은 그 파일에 그대로 두고, 라이브러리 자체를 고치는
쪽만 여기로 옮겼다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
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

from core.db import BASE_DIR, SessionLocal
from core.hangul_match import matches as hangul_matches
from core.models_db import MaterialLibrary
from core.thumbnail_generator import generate_image_thumbnail, generate_pdf_thumbnail, resolve_material_path
from desktop.widgets.debounced_search_input import DebouncedSearchInput

_CARD_STYLE = "QFrame { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }"
_SELECT_STYLE_OFF = "QPushButton { background: #2563eb; color: white; border-radius: 4px; padding: 4px; }"
_MATERIAL_FILE_FILTER = "이미지/PDF (*.jpg *.jpeg *.png *.pdf)"
_MATERIAL_SUFFIXES = (".jpg", ".jpeg", ".png", ".pdf")


def _copy_into_library(source_file_path: str) -> tuple[str, str]:
    """선택한 원본 파일을 `data/materials/` 안으로 복사하고 썸네일을 새로 만든다.

    원본을 라이브러리 폴더 밖(바탕화면/다운로드 등)에 그대로 둔 채 경로만 저장하면, 그
    파일이 나중에 옮겨지거나 지워졌을 때 자료가 깨진다. 반환값은 (복사된 파일의 절대경로,
    생성된 썸네일 경로 또는 빈 문자열).
    """
    source = Path(source_file_path)
    materials_dir = BASE_DIR / "data" / "materials"
    thumbs_dir = materials_dir / "thumbnails"
    materials_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    dest = materials_dir / source.name
    counter = 1
    while dest.exists():
        dest = materials_dir / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    shutil.copy2(source, dest)

    thumbnail_path = ""
    suffix = dest.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png"):
        thumb_dest = thumbs_dir / f"{dest.stem}_thumb.jpg"
        if generate_image_thumbnail(dest, thumb_dest):
            thumbnail_path = str(thumb_dest)
    elif suffix == ".pdf":
        thumb_dest = thumbs_dir / f"{dest.stem}.png"
        if generate_pdf_thumbnail(dest, thumb_dest):
            thumbnail_path = str(thumb_dest)

    return str(dest), thumbnail_path


class _DropZone(QFrame):
    """파일 탐색기에서 이미지/PDF를 끌어다 놓을 수 있는 영역."""

    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self.setStyleSheet(
            "QFrame { border: 2px dashed #cbd5e1; border-radius: 8px; background: #f9fafb; }"
        )

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label = QLabel("여기에 이미지를 끌어다 놓거나\n아래 '파일 선택' 버튼을 눌러 선택하세요")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #9ca3af; border: none;")
        layout.addWidget(self._hint_label)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("border: none;")
        self._preview_label.hide()
        layout.addWidget(self._preview_label)

    def dragEnterEvent(self, event):  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802 (Qt override)
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self.file_dropped.emit(path)

    def show_preview(self, file_path: str) -> None:
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            self._hint_label.setText(Path(file_path).name)
            self._preview_label.hide()
            self._hint_label.show()
            return
        self._hint_label.hide()
        self._preview_label.setPixmap(
            pixmap.scaled(220, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        self._preview_label.show()


class MaterialAddDialog(QDialog):
    """제공자료 라이브러리에 새 자료를 등록하는 모달 — 파일 선택/드래그앤드롭 + 제목/태그 입력."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("제공자료 추가")
        self.resize(420, 460)
        self.selected_file_path: str | None = None

        layout = QVBoxLayout(self)

        self.drop_zone = _DropZone()
        self.drop_zone.file_dropped.connect(self._set_file)
        layout.addWidget(self.drop_zone)

        pick_file_btn = QPushButton("파일 선택")
        pick_file_btn.clicked.connect(self._pick_file)
        layout.addWidget(pick_file_btn)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("새 자료 제목")
        layout.addWidget(self.title_input)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("태그(쉼표 구분)")
        layout.addWidget(self.tags_input)
        tags_hint = QLabel("키워드를 입력하면 AI추천기능을 통해 관련 자료를 자동으로 추천하는데 쓰입니다.")
        tags_hint.setWordWrap(True)
        tags_hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(tags_hint)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        register_btn = QPushButton("등록")
        register_btn.setStyleSheet(_SELECT_STYLE_OFF)
        register_btn.clicked.connect(self._on_register)
        btn_row.addWidget(register_btn)
        layout.addLayout(btn_row)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "자료 파일 선택", filter=_MATERIAL_FILE_FILTER)
        if file_path:
            self._set_file(file_path)

    def _set_file(self, file_path: str) -> None:
        if Path(file_path).suffix.lower() not in _MATERIAL_SUFFIXES:
            QMessageBox.warning(self, "지원하지 않는 형식", "이미지(jpg/png) 또는 PDF 파일만 등록할 수 있습니다.")
            return
        self.selected_file_path = file_path
        self.drop_zone.show_preview(file_path)
        if not self.title_input.text().strip():
            self.title_input.setText(Path(file_path).stem)

    def _on_register(self) -> None:
        if not self.selected_file_path:
            QMessageBox.warning(self, "파일 필요", "등록할 파일을 선택하거나 끌어다 놓으세요.")
            return
        if not self.title_input.text().strip():
            QMessageBox.warning(self, "제목 필요", "자료 제목을 입력하세요.")
            return
        self.accept()

    @property
    def title(self) -> str:
        return self.title_input.text().strip()

    @property
    def tags(self) -> str:
        return self.tags_input.text().strip()


class _MaterialDeleteCard(QFrame):
    def __init__(self, material: MaterialLibrary):
        super().__init__()
        self.material_id = material.id
        self.setStyleSheet(_CARD_STYLE)
        self.setFixedWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        thumb = QLabel()
        thumb.setFixedSize(134, 100)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("background: #f3f4f6; border-radius: 4px;")
        thumb_path = resolve_material_path(material.thumbnail_path)
        pixmap = QPixmap(str(thumb_path)) if thumb_path else QPixmap()
        if thumb_path and not pixmap.isNull():
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

        self.checkbox = QCheckBox("삭제 대상으로 선택")
        layout.addWidget(self.checkbox)


class MaterialDeleteDialog(QDialog):
    """제공자료 라이브러리에서 자료를 골라 통째로 삭제하는 모달."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("제공자료 삭제")
        self.resize(680, 640)
        self._cards: dict[int, _MaterialDeleteCard] = {}
        self._build_ui()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self.count_label)

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

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        delete_btn = QPushButton("선택 삭제")
        delete_btn.setStyleSheet("QPushButton { background: #dc2626; color: white; border-radius: 4px; padding: 6px 12px; }")
        delete_btn.clicked.connect(self._delete_checked)
        bottom_row.addWidget(delete_btn)
        layout.addLayout(bottom_row)

    def _search(self) -> None:
        keyword = self.search_input.current_text().strip()
        with SessionLocal() as session:
            all_items = session.query(MaterialLibrary).order_by(MaterialLibrary.id.desc()).all()
        items = [m for m in all_items if hangul_matches(keyword, m.title)][:120]

        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cards = {}
        columns = 4
        for idx, material in enumerate(items):
            card = _MaterialDeleteCard(material)
            self._cards[material.id] = card
            self._grid_layout.addWidget(card, idx // columns, idx % columns)

        total = len(all_items)
        if keyword:
            self.count_label.setText(f"{len(items)}개 / 전체 {total}개")
        else:
            self.count_label.setText(f"전체 {total}개")

    def _delete_checked(self) -> None:
        checked_ids = [material_id for material_id, card in self._cards.items() if card.checkbox.isChecked()]
        if not checked_ids:
            QMessageBox.information(self, "선택 필요", "삭제할 자료를 먼저 체크하세요.")
            return
        answer = QMessageBox.question(
            self,
            "삭제 확인",
            f"선택한 자료 {len(checked_ids)}개를 라이브러리에서 삭제하시겠습니까?\n(이미 생성된 보고서에는 영향이 없습니다)",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as session:
            session.query(MaterialLibrary).filter(MaterialLibrary.id.in_(checked_ids)).delete(
                synchronize_session=False
            )
            session.commit()
        self.deleted_ids = checked_ids
        self.accept()


class MaterialEditDialog(QDialog):
    """기존 제공자료 하나의 제목/태그/원본 파일을 고치는 모달."""

    def __init__(self, material: MaterialLibrary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("제공자료 수정")
        self.resize(420, 460)
        self.material_id = material.id
        self.selected_file_path: str | None = None  # None이면 기존 파일을 그대로 둔다

        layout = QVBoxLayout(self)

        self.drop_zone = _DropZone()
        self.drop_zone.file_dropped.connect(self._set_file)
        layout.addWidget(self.drop_zone)

        existing_path = resolve_material_path(material.thumbnail_path) or resolve_material_path(material.file_path)
        if existing_path:
            self.drop_zone.show_preview(str(existing_path))

        pick_file_btn = QPushButton("새 파일로 교체")
        pick_file_btn.clicked.connect(self._pick_file)
        layout.addWidget(pick_file_btn)

        self.title_input = QLineEdit(material.title)
        self.title_input.setPlaceholderText("자료 제목")
        layout.addWidget(self.title_input)

        self.tags_input = QLineEdit(material.tags)
        self.tags_input.setPlaceholderText("태그(쉼표 구분)")
        layout.addWidget(self.tags_input)
        tags_hint = QLabel("키워드를 입력하면 AI추천기능을 통해 관련 자료를 자동으로 추천하는데 쓰입니다.")
        tags_hint.setWordWrap(True)
        tags_hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(tags_hint)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(_SELECT_STYLE_OFF)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "새 자료 파일 선택", filter=_MATERIAL_FILE_FILTER)
        if file_path:
            self._set_file(file_path)

    def _set_file(self, file_path: str) -> None:
        if Path(file_path).suffix.lower() not in _MATERIAL_SUFFIXES:
            QMessageBox.warning(self, "지원하지 않는 형식", "이미지(jpg/png) 또는 PDF 파일만 등록할 수 있습니다.")
            return
        self.selected_file_path = file_path
        self.drop_zone.show_preview(file_path)

    def _on_save(self) -> None:
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "제목 필요", "자료 제목을 입력하세요.")
            return

        with SessionLocal() as session:
            material = session.get(MaterialLibrary, self.material_id)
            if material is None:
                self.reject()
                return
            material.title = title
            material.tags = self.tags_input.text().strip()
            if self.selected_file_path:
                material.file_path, material.thumbnail_path = _copy_into_library(self.selected_file_path)
            session.commit()
        self.accept()


class _MaterialEditCard(QFrame):
    def __init__(self, material: MaterialLibrary, on_edit):
        super().__init__()
        self.material_id = material.id
        self.setStyleSheet(_CARD_STYLE)
        self.setFixedWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        thumb = QLabel()
        thumb.setFixedSize(134, 100)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("background: #f3f4f6; border-radius: 4px;")
        thumb_path = resolve_material_path(material.thumbnail_path)
        pixmap = QPixmap(str(thumb_path)) if thumb_path else QPixmap()
        if thumb_path and not pixmap.isNull():
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

        edit_btn = QPushButton("수정")
        edit_btn.setStyleSheet(_SELECT_STYLE_OFF)
        edit_btn.clicked.connect(lambda: on_edit(self.material_id))
        layout.addWidget(edit_btn)


class MaterialEditListDialog(QDialog):
    """수정할 자료를 고르는 모달 — 카드를 누르면 `MaterialEditDialog`가 뜬다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("제공자료 수정")
        self.resize(680, 640)
        self._cards: dict[int, _MaterialEditCard] = {}
        self._build_ui()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self.count_label)

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

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

    def _search(self) -> None:
        keyword = self.search_input.current_text().strip()
        with SessionLocal() as session:
            all_items = session.query(MaterialLibrary).order_by(MaterialLibrary.id.desc()).all()
        items = [m for m in all_items if hangul_matches(keyword, m.title)][:120]

        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cards = {}
        columns = 4
        for idx, material in enumerate(items):
            card = _MaterialEditCard(material, self._open_edit)
            self._cards[material.id] = card
            self._grid_layout.addWidget(card, idx // columns, idx % columns)

        total = len(all_items)
        if keyword:
            self.count_label.setText(f"{len(items)}개 / 전체 {total}개")
        else:
            self.count_label.setText(f"전체 {total}개")

    def _open_edit(self, material_id: int) -> None:
        with SessionLocal() as session:
            material = session.get(MaterialLibrary, material_id)
        if material is None:
            return
        dialog = MaterialEditDialog(material, self)
        if dialog.exec():
            self._search()
