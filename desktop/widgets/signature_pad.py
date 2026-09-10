"""서명 캡처 위젯 — 마우스로 그리거나 이미지 파일을 첨부해 서명을 등록한다.

외부 드로잉 라이브러리 없이 QPainter/QPixmap만으로 자유곡선을 그린다(PyQt6 표준 기능만 사용).
`PhotoDropZone`과 같은 관례로, 위젯 자체는 파일을 최종 위치로 옮기지 않는다 — 그린 서명은
임시 PNG로만 저장해두고, 실제 저장 경로 확정(`move_or_reference`)은 이 위젯을 쓰는 화면의
저장 로직이 담당한다.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from core.db import BASE_DIR

_IMAGE_FILTER = "이미지 파일 (*.jpg *.jpeg *.png *.webp *.gif)"
_TMP_DIR = BASE_DIR / "data" / "signatures" / "_tmp"


class _SignatureCanvas(QWidget):
    """자유곡선을 그리는 캔버스. 획을 뗄 때마다 stroke_finished를 낸다."""

    stroke_finished = pyqtSignal()

    def __init__(self, width: int = 360, height: int = 140, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._pixmap = QPixmap(width, height)
        self._pixmap.fill(Qt.GlobalColor.transparent)
        self._last_point: QPoint | None = None
        self._drawing_enabled = True

    def set_drawing_enabled(self, enabled: bool) -> None:
        self._drawing_enabled = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ForbiddenCursor)

    def pixmap(self) -> QPixmap:
        return self._pixmap

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def clear(self) -> None:
        self._pixmap = QPixmap(self.width(), self.height())
        self._pixmap.fill(Qt.GlobalColor.transparent)
        self.update()

    def has_ink(self) -> bool:
        image = self._pixmap.toImage()
        if image.isNull():
            return False
        for y in range(0, image.height(), 4):
            for x in range(0, image.width(), 4):
                if image.pixelColor(x, y).alpha() > 0:
                    return True
        return False

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.setPen(QPen(Qt.GlobalColor.lightGray))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._drawing_enabled or event.button() != Qt.MouseButton.LeftButton:
            return
        self._last_point = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._drawing_enabled or self._last_point is None:
            return
        current = event.position().toPoint()
        painter = QPainter(self._pixmap)
        painter.setPen(
            QPen(
                Qt.GlobalColor.black,
                2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawLine(self._last_point, current)
        painter.end()
        self._last_point = current
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._drawing_enabled:
            return
        self._last_point = None
        self.stroke_finished.emit()


class SignaturePad(QWidget):
    """서명 캡처 위젯 — 마우스로 그리거나 이미지를 첨부한다."""

    signature_changed = pyqtSignal(str)  # 빈 문자열이면 삭제됨

    def __init__(self, parent=None):
        super().__init__(parent)
        self._signature_path = ""
        self._source = ""  # "drawn" | "uploaded" | "existing"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.canvas = _SignatureCanvas()
        self.canvas.stroke_finished.connect(self._on_stroke_finished)
        layout.addWidget(self.canvas)

        btn_row = QHBoxLayout()
        self.upload_btn = QPushButton("이미지 첨부")
        self.upload_btn.clicked.connect(self._browse)
        btn_row.addWidget(self.upload_btn)

        self.clear_btn = QPushButton("지우기")
        self.clear_btn.setStyleSheet("color: #ef4444;")
        self.clear_btn.clicked.connect(self.clear_signature)
        btn_row.addWidget(self.clear_btn)
        layout.addLayout(btn_row)

    def _on_stroke_finished(self) -> None:
        if not self.canvas.has_ink():
            return
        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = _TMP_DIR / f"{uuid.uuid4().hex}.png"
        self.canvas.pixmap().save(str(tmp_path), "PNG")
        self._signature_path = str(tmp_path)
        self._source = "drawn"
        self.signature_changed.emit(self._signature_path)

    def _browse(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "서명 이미지 선택", "", _IMAGE_FILTER)
        if not file_path:
            return
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return
        self._show_readonly_preview(pixmap)
        self._signature_path = file_path
        self._source = "uploaded"
        self.signature_changed.emit(self._signature_path)

    def _show_readonly_preview(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.canvas.width(),
            self.canvas.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.canvas.set_pixmap(scaled)
        self.canvas.set_drawing_enabled(False)

    def clear_signature(self) -> None:
        self.canvas.clear()
        self.canvas.set_drawing_enabled(True)
        self._signature_path = ""
        self._source = ""
        self.signature_changed.emit("")

    def load_existing(self, path: str) -> None:
        """DB에 이미 저장된 서명을 읽기전용 프리뷰로 띄운다(마법사 등에서 재사용 표시용)."""
        if not path or not Path(path).exists():
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self._show_readonly_preview(pixmap)
        self._signature_path = path
        self._source = "existing"

    @property
    def signature_path(self) -> str:
        return self._signature_path

    @property
    def source(self) -> str:
        return self._source

    def has_signature(self) -> bool:
        return bool(self._signature_path)


def move_or_reference(pad: SignaturePad, final_path: Path) -> str:
    """pad의 서명을 최종 위치(`final_path`)로 확정한다.

    source=="drawn"이면 임시 PNG를 final_path로 옮기고, "uploaded"/"existing"이면 원본을
    final_path로 복사해둔다. 예전에는 "uploaded"/"existing"일 때 원본 경로를 참조만 하고
    끝냈는데, 그러면 사용자가 파일 선택으로 고른 원본(바탕화면/다운로드 등)이 나중에 옮겨지거나
    지워지거나 이 앱이 다른 PC로 배포될 때 서명이 깨진다 — 제공자료 라이브러리와 같은 이유로
    앱 데이터 폴더 안에 자기완결적으로 두도록 고쳤다.

    미리보기 화면 등에서 `_save()`가 반복 호출될 수 있으므로, 옮기거나 복사한 뒤에는 pad
    내부 상태를 "existing"으로 갱신해 다음 호출부터는 이미 확정된 파일을 다시 옮기거나
    자기 자신에 복사하려다 실패하지 않도록 한다.
    """
    if not pad.has_signature():
        return ""

    final_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = Path(pad.signature_path)

    if pad.source == "drawn":
        shutil.move(str(source_path), str(final_path))
    elif source_path.resolve() != final_path.resolve():
        shutil.copy2(str(source_path), str(final_path))

    pad._signature_path = str(final_path)  # noqa: SLF001 (같은 모듈 내부 상태 갱신)
    pad._source = "existing"  # noqa: SLF001
    return str(final_path)
