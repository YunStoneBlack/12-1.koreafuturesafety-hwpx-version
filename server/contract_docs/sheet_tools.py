"""양식 시트 손질 — openpyxl로 연 회사 양식(착수계·완수계)의 그림·도장·찌꺼기를 다룬다.

양식 속 그림(10/6 확인):
- 둥근 대표이사 도장(237×238 그림) — 시트마다 인쇄 범위 밖(오른쪽)에 놓여 있다. [도장 넣기]면 "대표 이 인 숙 (인)" 위나
  "원본대조필" 칸 오른쪽에 새로 놓고, 양식에 있던 것은 늘 지운다(빼기면 인쇄 뒤 실제 도장).
- 원본대조필 칸(209×64), 감독경유 칸(475×280), 갑지 네모 직인·로고 — 그대로 둔다.
- 증명서·자격증 사진 — 시트에서 가장 큰 그림. 올린 파일로 바꾼다(같은 자리·같은 비율 — 비율이 다르면 흰 여백을 붙임).

좌표: 열 너비(글자 수) → 픽셀 ≈ 너비×7+5, 행 높이(pt) → 픽셀 = pt×96/72. 도장처럼 몇 픽셀 어긋나도 되는 곳에만 쓴다.
"""
from __future__ import annotations

import io
from copy import copy
from pathlib import Path

from openpyxl.cell.cell import MergedCell
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image as PILImage

SEAL_PX = (237, 238)
SEAL_SIZE = 66  # 인쇄 때 도장 크기(픽셀, 약 17mm)
MAX_DOC_PX = 1600  # 증명서 그림 긴 변 — 파일이 너무 커지지 않게(A4 한 장에 충분)


def col_px(ws: Worksheet, col: int) -> float:
    """열(1부터) 너비 픽셀."""
    dim = ws.column_dimensions.get(get_column_letter(col))
    width = dim.width if dim is not None and dim.width else (ws.sheet_format.defaultColWidth or 8.43)
    if dim is not None and dim.hidden:
        return 0
    return width * 7 + 5


def row_px(ws: Worksheet, row: int) -> float:
    dim = ws.row_dimensions.get(row)
    pt = dim.height if dim is not None and dim.height else (ws.sheet_format.defaultRowHeight or 15)
    if dim is not None and dim.hidden:
        return 0
    return pt * 96 / 72


def col_x(ws: Worksheet, col: int) -> float:
    """열(1부터) 왼쪽 끝 x 픽셀."""
    return sum(col_px(ws, c) for c in range(1, col))


def row_y(ws: Worksheet, row: int) -> float:
    return sum(row_px(ws, r) for r in range(1, row))


def _marker(ws: Worksheet, x: float, y: float) -> AnchorMarker:
    col, left = 1, x
    while left >= col_px(ws, col) and col < 200:
        left -= col_px(ws, col)
        col += 1
    row, top = 1, y
    while top >= row_px(ws, row) and row < 2000:
        top -= row_px(ws, row)
        row += 1
    return AnchorMarker(col=col - 1, colOff=pixels_to_EMU(max(0, left)), row=row - 1, rowOff=pixels_to_EMU(max(0, top)))


def print_bounds(ws: Worksheet) -> tuple[int, int]:
    """인쇄 범위의 (마지막 열, 마지막 행) — 1부터."""
    area = ws.print_area
    if not area:
        return ws.max_column, ws.max_row
    ref = (area[0] if isinstance(area, (list, tuple)) else area).split("!")[-1].replace("$", "")
    _, _, max_col, max_row = range_boundaries(ref)
    return max_col, max_row


def clear_outside_print(ws: Worksheet) -> None:
    """인쇄 범위 오른쪽 칸의 값 지우기 — 양식을 다른 현장에서 베껴 오며 남은 찌꺼기(화현초·초가팔2리 등, 인쇄엔 안 나옴)."""
    max_col, _ = print_bounds(ws)
    for row in ws.iter_rows(min_col=max_col + 1):
        for c in row:
            if c.value is not None and not isinstance(c, MergedCell):
                c.value = None


def img_bytes(img: XLImage) -> bytes:
    """그림 바이트. openpyxl은 한 번 읽으면 파일을 닫아 두 번째(저장 때 포함)에 실패하므로 읽은 뒤 새 BytesIO로 되돌려 둔다."""
    data = getattr(img, "_kfsc_bytes", None)
    if data is None:
        data = img._data()
        img._kfsc_bytes = data
    img.ref = io.BytesIO(data)
    return data


def _px(img: XLImage) -> tuple[int, int]:
    try:
        with PILImage.open(io.BytesIO(img_bytes(img))) as p:
            return p.size
    except Exception:  # noqa: BLE001
        return (0, 0)


def is_seal(img: XLImage) -> bool:
    return _px(img) == SEAL_PX


def seal_bytes(wb) -> bytes | None:
    """양식에 들어 있는 둥근 대표이사 도장 그림(첫 번째)."""
    for ws in wb.worksheets:
        for img in ws._images:
            if is_seal(img):
                return img_bytes(img)
    return None


def remove_seals(ws: Worksheet) -> None:
    ws._images = [img for img in ws._images if not is_seal(img)]


def _anchor_box(ws: Worksheet, img: XLImage) -> tuple[float, float, float, float]:
    """그림의 (x, y, 너비, 높이) 픽셀 — 두 칸 기준 위치만(양식 그림은 전부 두 칸 기준)."""
    a = img.anchor
    fx = col_x(ws, a._from.col + 1) + a._from.colOff / 9525
    fy = row_y(ws, a._from.row + 1) + a._from.rowOff / 9525
    to = getattr(a, "to", None)
    if to is None:
        return fx, fy, 0, 0
    tx = col_x(ws, to.col + 1) + to.colOff / 9525
    ty = row_y(ws, to.row + 1) + to.rowOff / 9525
    return fx, fy, tx - fx, ty - fy


def main_image(ws: Worksheet) -> XLImage | None:
    """증명서·자격증 사진 — 인쇄 범위 안에서 가장 큰 그림(도장 빼고)."""
    max_col, _ = print_bounds(ws)
    best, area = None, 0.0
    for img in ws._images:
        if is_seal(img) or img.anchor._from.col >= max_col:
            continue
        _, _, w, h = _anchor_box(ws, img)
        if w * h > area:
            best, area = img, w * h
    return best


def find_image(ws: Worksheet, px: tuple[int, int]) -> XLImage | None:
    for img in ws._images:
        if _px(img) == px:
            return img
    return None


def _fit(src: str | Path | bytes, box_w: float, box_h: float) -> bytes:
    """올린 그림을 칸 비율에 맞춰 흰 여백을 붙인 JPEG(늘어나 보이지 않게)."""
    with PILImage.open(io.BytesIO(src) if isinstance(src, bytes) else str(src)) as p:
        p = p.convert("RGB")
        p.thumbnail((MAX_DOC_PX, MAX_DOC_PX))
        w, h = p.size
        if box_w > 0 and box_h > 0:
            ratio = box_w / box_h
            if w / h > ratio:  # 그림이 더 넓음 → 위아래 여백
                canvas = PILImage.new("RGB", (w, round(w / ratio)), "white")
                canvas.paste(p, (0, (canvas.height - h) // 2))
            else:
                canvas = PILImage.new("RGB", (round(h * ratio), h), "white")
                canvas.paste(p, ((canvas.width - w) // 2, 0))
            p = canvas
        buf = io.BytesIO()
        p.save(buf, "JPEG", quality=88)
        return buf.getvalue()


def replace_image(ws: Worksheet, old: XLImage, src: str | Path | bytes) -> None:
    """old 그림 자리에 src(파일 경로·바이트)를 넣는다 — 위치·크기는 old 그대로."""
    _, _, w, h = _anchor_box(ws, old)
    new = XLImage(io.BytesIO(_fit(src, w, h)))
    new.anchor = old.anchor
    ws._images[ws._images.index(old)] = new


def drop_image(ws: Worksheet, img: XLImage | None) -> None:
    if img is not None and img in ws._images:
        ws._images.remove(img)


def add_image_copy(ws: Worksheet, img: XLImage) -> None:
    """다른 시트 그림을 같은 자리에 복사(시트 복사 때 — openpyxl copy_worksheet는 그림을 안 옮김)."""
    new = XLImage(io.BytesIO(img_bytes(img)))
    new.anchor = copy(img.anchor)
    ws._images.append(new)


def place_seal(ws: Worksheet, seal: bytes, cx: float, cy: float, size: int = SEAL_SIZE) -> None:
    """도장 그림을 (cx, cy) 픽셀이 가운데가 되게 놓는다."""
    img = XLImage(io.BytesIO(seal))
    img.anchor = OneCellAnchor(_from=_marker(ws, cx - size / 2, cy - size / 2),
                               ext=XDRPositiveSize2D(pixels_to_EMU(size), pixels_to_EMU(size)))
    ws._images.append(img)


def merged_right_x(ws: Worksheet, coord: str) -> float:
    """칸(병합이면 병합 범위)의 오른쪽 끝 x 픽셀."""
    cell = ws[coord]
    for rng in ws.merged_cells.ranges:
        if cell.coordinate in rng:
            return col_x(ws, rng.max_col + 1)
    return col_x(ws, cell.column + 1)


def seal_on_text_end(ws: Worksheet, coord: str, seal: bytes, back_px: float = 46) -> None:
    """오른쪽 정렬된 "대표 이 인 숙 (인)" 칸 — 글자 끝 "(인)" 위에 도장(끝에서 back_px 안쪽이 가운데)."""
    cell = ws[coord]
    cx = merged_right_x(ws, coord) - back_px
    cy = row_y(ws, cell.row) + row_px(ws, cell.row) / 2
    place_seal(ws, seal, cx, cy)


def seal_on_original_box(ws: Worksheet, seal: bytes) -> bool:
    """"원본대조필" 칸(209×64 그림)의 오른쪽 빈 칸 위에 도장. 칸이 없으면 False."""
    box = find_image(ws, (209, 64))
    if box is None:
        return False
    x, y, w, h = _anchor_box(ws, box)
    place_seal(ws, seal, x + w * 0.78, y + h / 2)
    return True
