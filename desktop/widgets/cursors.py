"""공용 커스텀 커서. 이미지 에셋 없이 QPainter로 직접 그려서 쓴다."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QPainter, QPen, QPixmap

_zoom_cursor_cache: QCursor | None = None


def zoom_cursor() -> QCursor:
    """돋보기(+) 모양 커서 — 클릭하면 크게 볼 수 있는 요소(썸네일 등)에 사용."""
    global _zoom_cursor_cache
    if _zoom_cursor_cache is not None:
        return _zoom_cursor_cache

    size = 24
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(Qt.GlobalColor.black)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setBrush(Qt.GlobalColor.white)
    painter.drawEllipse(1, 1, 13, 13)
    painter.drawLine(11, 11, 17, 17)

    small_pen = QPen(Qt.GlobalColor.black)
    small_pen.setWidth(1)
    painter.setPen(small_pen)
    painter.drawLine(4, 7, 10, 7)
    painter.drawLine(7, 4, 7, 10)
    painter.end()

    _zoom_cursor_cache = QCursor(pixmap, 7, 7)
    return _zoom_cursor_cache
