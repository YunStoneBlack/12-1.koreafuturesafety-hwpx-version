"""사진 업로드 위젯 — 드래그앤드롭 또는 클릭으로 사진 선택, 썸네일 미리보기, 삭제."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget

_IMAGE_FILTER = "이미지 파일 (*.jpg *.jpeg *.png *.webp *.gif)"


class PhotoDropZone(QWidget):
    photo_changed = pyqtSignal(str)  # 빈 문자열이면 삭제됨

    def __init__(self, placeholder: str = "사진 업로드", parent=None):
        super().__init__(parent)
        self._photo_path = ""
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.box = QLabel(f"📷\n{placeholder}\nDrag & Drop")
        self.box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.box.setFixedSize(180, 140)
        self.box.setStyleSheet(
            "QLabel { border: 1px dashed #d1d5db; border-radius: 8px; color: #9ca3af; background: #fafafa; }"
        )
        self.box.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.box, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.upload_btn = QPushButton("↑ 사진 업로드")
        self.upload_btn.clicked.connect(self._browse)
        layout.addWidget(self.upload_btn)

        self.delete_btn = QPushButton("✕ 사진 삭제")
        self.delete_btn.setStyleSheet("color: #ef4444;")
        self.delete_btn.clicked.connect(self.clear_photo)
        self.delete_btn.setVisible(False)
        layout.addWidget(self.delete_btn)

    def mousePressEvent(self, event):  # noqa: N802 (Qt override)
        if self.box.geometry().contains(event.pos()):
            self._browse()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.set_photo(urls[0].toLocalFile())

    def _browse(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "사진 선택", "", _IMAGE_FILTER)
        if file_path:
            self.set_photo(file_path)

    def set_photo(self, path: str) -> None:
        self._photo_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.box.setPixmap(
                pixmap.scaled(
                    self.box.width() - 8,
                    self.box.height() - 8,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.delete_btn.setVisible(True)
        self.photo_changed.emit(path)

    def clear_photo(self) -> None:
        self._photo_path = ""
        self.box.setPixmap(QPixmap())
        self.box.setText("📷\n사진 업로드\nDrag & Drop")
        self.delete_btn.setVisible(False)
        self.photo_changed.emit("")

    @property
    def photo_path(self) -> str:
        return self._photo_path
