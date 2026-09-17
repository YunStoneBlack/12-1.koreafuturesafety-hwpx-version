"""사진 업로드 위젯 — 드래그앤드롭 또는 클릭으로 사진 선택, 썸네일 미리보기, 삭제."""

from __future__ import annotations

import shutil
from pathlib import Path

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


def copy_photo_to_storage(source_path: str, final_path: Path) -> str:
    """업로드한 사진 원본을 앱 데이터 폴더(`final_path`)로 복사해, 이 앱이 원본 경로를
    영원히 신뢰할 수 있다고 가정하지 않게 한다(`signature_pad.move_or_reference`와 같은
    이유·같은 패턴). 실사용 중 드롭박스/네이버박스 같은 동기화 폴더에서 고른 사진이
    보고서 생성 시점엔 전부 안 들어가는 버그로 발견됐다(2026-09-18) — 동기화 폴더는
    탐색기에 파일이 있는 것처럼 보여도 일반 파일 접근과 다르게 동작할 수 있어, 원본
    경로를 계속 참조하는 대신 저장 시점에 한 번 앱 폴더 안으로 복사해 자기완결적으로
    만든다. 서명과 달리 사진은 항상 사용자의 원본 파일이므로 옮기지 않고 복사만 한다.
    실패하면 예외를 그대로 올린다 — 호출부가 사용자에게 어떤 사진인지 콕 집어 알려줄 수
    있도록 여기서 조용히 삼키지 않는다.
    """
    if not source_path:
        return ""
    source = Path(source_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == final_path.resolve():
        return str(final_path)
    shutil.copy2(str(source), str(final_path))
    return str(final_path)
