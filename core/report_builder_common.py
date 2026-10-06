"""PDF/DOCX 산출물 빌더가 공유하는 폰트·서식 헬퍼. report_builder_pdf.py와
report_builder_docx.py 양쪽에서 쓴다."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, TableStyle

FONT_REGULAR = "MalgunGothic"
FONT_BOLD = "MalgunGothic-Bold"
_FONTS_REGISTERED = False

_WINDOWS_FONT_DIR = Path(r"C:\Windows\Fonts")

HEADER_BG = colors.HexColor("#f3f4f6")
ACCENT = colors.HexColor("#4f46e5")


def ensure_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    regular = _WINDOWS_FONT_DIR / "malgun.ttf"
    bold = _WINDOWS_FONT_DIR / "malgunbd.ttf"
    if not regular.exists():
        raise RuntimeError(
            "맑은 고딕 폰트를 찾을 수 없습니다 (C:\\Windows\\Fonts\\malgun.ttf). "
            "Windows 환경에서 실행 중인지 확인하세요."
        )
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold) if bold.exists() else str(regular)))
    _FONTS_REGISTERED = True


def p(text: str, bold: bool = False, size: int = 9, align: str = "LEFT", color=colors.black) -> Paragraph:
    style = ParagraphStyle(
        name="cell",
        fontName=FONT_BOLD if bold else FONT_REGULAR,
        fontSize=size,
        leading=size + 4,
        alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
        textColor=color,
    )
    return Paragraph((text or "-").replace("\n", "<br/>"), style)


def scaled_image(path: str, max_width: float, max_height: float):
    if not path or not Path(path).exists():
        return p("(사진 없음)", align="CENTER")
    try:
        img = Image(path)
        ratio = min(max_width / img.imageWidth, max_height / img.imageHeight, 1.0)
        img.drawWidth = img.imageWidth * ratio
        img.drawHeight = img.imageHeight * ratio
        return img
    except Exception:
        return p("(이미지를 불러올 수 없음)", align="CENTER")


GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]
)


def section_title(number: int, text: str) -> Paragraph:
    style = ParagraphStyle(
        name="section",
        fontName=FONT_BOLD,
        fontSize=12,
        spaceAfter=4,
        spaceBefore=10,
    )
    return Paragraph(f"{number}. {text}", style)


def fmt_date(value) -> str:
    return value.strftime("%Y.%m.%d") if value else "-"


def fmt_amount(value: int | None) -> str:
    return f"{value:,}" if value is not None else "-"
