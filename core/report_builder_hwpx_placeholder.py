"""사진 칸에 사진 대신 들어가는 안내 표시 — 점선 X자 틀 안에 문구가 있는 그림, 그리고 "-".

`사진촬영 불가(보안 등)`(현장 정책으로 사진을 못 찍는 보고서), `이전회차 기술지도 사항 없음`,
`개선 필요 이상의 위험성 없음`처럼 "칸 자체는 있어야 하는데 실제 사진이 없는" 경우에 쓴다. 한글의
"빈 그림틀" 모양(점선 대각선 X + 가운데 굵은 글씨)을 PNG로 그려서 사진과 똑같은 방식으로 칸에
넣는다 — 도형/글상자를 직접 만드는 것보다 한글 버전 차이에 덜 민감하다(Sub-phase 24 참고).
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_TMP_DIR = Path(tempfile.gettempdir()) / "claude" / "hwpx_placeholder"
_DPI = 200
_HWPUNIT_PER_INCH = 7200
_FONT_PT = 11
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\NanumGothicBold.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
)
_LINE_COLOR = (60, 60, 60)
_LINE_WIDTH_PX = 2
_DASH_PX = 4
_GAP_PX = 4

_DASH_PARA_PR_ID = "42"  # 가운데 정렬 문단 모양(위험성 표 헤더 칸과 같은 것)


def _load_font() -> ImageFont.ImageFont:
    size = round(_FONT_PT * _DPI / 72)
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _dotted_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    x0, y0 = start
    x1, y1 = end
    length = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1)
    step = _DASH_PX + _GAP_PX
    position = 0.0
    while position < length:
        a = position / length
        b = min(position + _DASH_PX, length) / length
        draw.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), fill=_LINE_COLOR, width=_LINE_WIDTH_PX)
        position += step


def render_frame_placeholder(text: str, box_width: int, box_height: int) -> Path:
    """`box_width`×`box_height`(HWPUNIT) 크기에 딱 맞는 점선 X자 틀 + 가운데 `text` 그림을 임시 PNG로 만들어 경로를 돌려준다.

    호출부가 이미지를 문서에 넣은 뒤 지워야 한다(`unlink`)."""
    width_px = max(round(box_width / _HWPUNIT_PER_INCH * _DPI), 2)
    height_px = max(round(box_height / _HWPUNIT_PER_INCH * _DPI), 2)
    image = Image.new("RGB", (width_px, height_px), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _dotted_line(draw, (0, 0), (width_px - 1, height_px - 1))
    _dotted_line(draw, (width_px - 1, 0), (0, height_px - 1))
    font = _load_font()
    draw.text((width_px / 2, height_px / 2), text, font=font, fill=(0, 0, 0), anchor="mm")

    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _TMP_DIR / f"{uuid.uuid4().hex}.png"
    image.save(out_path, "PNG")
    return out_path


def put_dash(doc, cell) -> None:
    """사진이 없는 빈 칸에 가운데 정렬된 굵은 "-"를 넣는다."""
    paragraph = cell.paragraphs[0]
    paragraph.text = "-"
    paragraph.para_pr_id_ref = _DASH_PARA_PR_ID
    style_id = doc.ensure_run_style(bold=True, size=10)
    for run in paragraph.runs:
        run.char_pr_id_ref = style_id
