"""과거 보고서 PDF 여러 개를 드래그앤드롭 또는 "파일 선택"으로 한 번에 고르는 위젯.

PhotoDropZone은 이미지 전용·단일 파일 고정이라 이 용도(PDF, 여러 개)에는 안 맞아서
새로 만들었다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

_PDF_FILTER = "PDF 파일 (*.pdf)"
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


class PdfDropZone(QFrame):
    files_selected = pyqtSignal(list)  # list[str] — 크기/확장자 검사를 통과한 경로만 담긴다

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            "QFrame { border: 2px dashed #c7c7d1; border-radius: 10px; background: #fafafa; }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(24, 32, 24, 32)

        icon = QLabel("☁")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 28px; border: none; background: transparent;")
        layout.addWidget(icon)

        title = QLabel("PDF 파일을 여기로 드래그하세요")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: 700; border: none; background: transparent;")
        layout.addWidget(title)

        sub = QLabel("여러 개 한 번에 선택 가능 · 파일당 10MB 이하")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #9ca3af; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(sub)

        browse_btn = QPushButton("파일 선택")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; border-radius: 6px; padding: 8px 20px; "
            "font-weight: 600; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        browse_btn.clicked.connect(self._browse)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self._emit_valid(paths)

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF 파일 선택", "", _PDF_FILTER)
        if paths:
            self._emit_valid(paths)

    def _emit_valid(self, paths: list[str]) -> None:
        valid: list[str] = []
        rejected: list[str] = []
        for p in paths:
            path = Path(p)
            if path.suffix.lower() != ".pdf":
                rejected.append(f"{path.name} (PDF 아님)")
                continue
            if path.exists() and path.stat().st_size > MAX_FILE_SIZE_BYTES:
                rejected.append(f"{path.name} (10MB 초과)")
                continue
            valid.append(p)
        if rejected:
            QMessageBox.warning(self, "일부 파일 제외됨", "다음 파일은 제외했습니다:\n" + "\n".join(rejected))
        if valid:
            self.files_selected.emit(valid)
