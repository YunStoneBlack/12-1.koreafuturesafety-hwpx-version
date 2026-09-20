"""HWPX 산출물에 실제 이미지를 삽입한다 — `report_builder_hwp_images.py`(pyhwpx/COM
버전)를 python-hwpx로 옮긴 버전.

담당요원 서명 도장(t3_005)·현장책임자 서명(t3_008)·제공자료(11번) 부록 페이지까지 전부
포팅 완료됐다. 담당요원/현장책임자 서명은 `paragraph.add_picture(..., treat_as_char=False,
pos_overrides={"horzRelTo": "PAPER", ...})`로 종이 기준 절대좌표에 배치한다 — COM 버전과
달리 페이지 여백을 빼면 안 된다(실측 확인: python-hwpx의 "PAPER"는 진짜 종이 끝 기준).

**포팅 방식**: pyhwpx는 캐럿을 필드/셀 위치로 옮겨(`move_to_field`, `TableRightCell` 등)
"현재 커서 위치"에 그림을 끼워 넣는 방식이었지만, python-hwpx는 살아있는 편집 캐럿이 없는
XML 문서 모델이라 그 방식 자체가 성립하지 않는다. 대신:
- 표는 `doc.tables.all[N]`(문서 순서, pyhwpx의 `get_into_nth_table(N)`과 동일한 인덱스 —
  실측으로 확인됨)로 바로 찾고, `table.cell(row, col)`(0-based)로 특정 칸에 접근한다.
- 필드가 있는 칸을 기준으로 상대 이동(왼쪽/위/오른쪽 몇 칸)해야 하는 경우
  (`_locate_field_cell`)는 그 필드의 `<hp:fieldBegin>` XML 요소에서 부모를 타고 올라가
  `<hp:tc>`(칸)/`<hp:tbl>`(표)을 찾은 뒤, 그 표 안에서 같은 XML 요소를 가진 칸을 찾아
  (row, col)을 역산한다.
- 기존 그림 삭제는 `cell.paragraphs[0].runs`를 훑어 `<hp:pic>`을 담은 run을 찾아
  `run.remove()`한다(실측 확인: `paragraph.clear_text()`는 텍스트만 지우고 그림은 안
  지운다).
- 크기는 원본의 `sizeoption=3`(칸 크기에 맞춰 비율 유지)을 `cell.width`/`cell.height`
  (HWPUNIT, 이미 `add_picture`가 받는 단위와 동일)를 상자로 삼아 종횡비를 유지하며 맞추는
  것으로 대체한다.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from core import config
from core.models_db import Report, Site
from core.thumbnail_generator import render_pdf_pages, resolve_material_path

_BOLD_TMP_DIR = Path(tempfile.gettempdir()) / "claude" / "hwp_signature_bold"


def _prepare_signature_image(image_path: str) -> str:
    """직접 그린 서명(투명 배경 위 얇은 획)을 굵고 진하게 다듬은 임시 PNG로 바꿔 반환한다.

    `report_builder_hwp_images.py`(pyhwpx 버전)의 동일 함수를 그대로 옮김 — 순수 PIL 로직이라
    COM과 무관하다. `SignaturePad`가 2px 펜으로 그린 획은 작은 크기(14mm 폭)로 축소되면
    가늘고 흐릿해 보인다. 배경이 상당 부분 투명한 이미지(=직접 그린 서명)만 골라 알파
    채널을 이진화하고 팽창시켜(획을 굵게) 순수 검정으로 다시 칠한다. 업로드한 사진(결재란
    도장, 현장 사진 등)은 보통 배경이 불투명해 이 조건에 안 걸리므로 원본 그대로 쓴다.
    인주 도장처럼 배경이 투명한 PNG는 불투명 영역의 평균 채도(彩度)로 손 서명과 구분한다
    (손 서명은 무채색에 가까운 검정 한 가지, 도장은 인주색 등 채도가 뚜렷함).
    """
    from PIL import Image, ImageFilter, ImageStat

    try:
        img = Image.open(image_path).convert("RGBA")
    except Exception:
        return image_path

    alpha = img.split()[-1]
    histogram = alpha.histogram()
    total = sum(histogram)
    if total == 0:
        return image_path
    transparent_ratio = sum(histogram[:40]) / total
    if transparent_ratio < 0.2:
        return image_path

    opaque_mask = alpha.point(lambda v: 255 if v > 128 else 0)
    saturation = img.convert("RGB").convert("HSV").split()[1]
    avg_saturation = ImageStat.Stat(saturation, mask=opaque_mask).mean[0]
    if avg_saturation > 30:
        return image_path

    bold_alpha = alpha.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(5))
    solid_black = Image.new("RGBA", img.size, (0, 0, 0, 0))
    solid_black.putalpha(bold_alpha)

    _BOLD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _BOLD_TMP_DIR / f"{uuid.uuid4().hex}.png"
    solid_black.save(out_path, "PNG")
    return str(out_path)


def _image_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return "jpg" if suffix == "jpeg" else suffix


def _register_image(doc, path: Path) -> str:
    """이미지를 문서에 등록한다 — 손그림 서명이면 `_prepare_signature_image`가 먼저
    굵게 다듬는다(사진/도장은 그 함수 자체의 안전장치로 원본 그대로 통과한다)."""
    prepared = Path(_prepare_signature_image(str(path)))
    return doc.add_image(prepared.read_bytes(), _image_format(prepared))


def _fit_size(image_path: str, box_w: int, box_h: int) -> tuple[int, int]:
    """이미지의 원본 비율을 유지하면서 (box_w, box_h) 상자 안에 들어가는 크기를 계산한다
    (HWPUNIT 단위 그대로 입출력 — `sizeoption=3`의 "칸 크기에 맞춰 비율 유지"에 대응)."""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            iw, ih = img.size
    except Exception:
        return box_w, box_h
    if iw <= 0 or ih <= 0:
        return box_w, box_h
    ratio = min(box_w / iw, box_h / ih)
    return round(iw * ratio), round(ih * ratio)


def _clear_pictures(paragraph) -> None:
    """문단 안의 그림(run 안의 `<hp:pic>`)을 전부 지운다 — `clear_text()`는 텍스트만
    지우고 그림은 안 지운다(실측 확인)."""
    for run in list(paragraph.runs):
        if any(isinstance(child.tag, str) and child.tag.endswith("}pic") for child in run.element):
            run.remove()


def _cell_inner_box(cell) -> tuple[int, int]:
    """칸의 실제 인쇄 가능 영역(칸 안쪽 여백 `<hp:cellMargin>`을 뺀 크기)을 구한다.

    `cell.width`/`cell.height`는 칸 바깥 크기라, 그대로 이미지 크기로 쓰면 칸 안쪽 여백만큼
    이미지가 테두리를 넘어가 보인다(실측 확인 — 결재란 도장이 칸보다 커 보이던 원인).
    """
    left = right = top = bottom = 0
    for child in cell.element:
        if isinstance(child.tag, str) and child.tag.endswith("}cellMargin"):
            left = int(child.get("left", 0) or 0)
            right = int(child.get("right", 0) or 0)
            top = int(child.get("top", 0) or 0)
            bottom = int(child.get("bottom", 0) or 0)
            break
    width = max(cell.width - left - right, 1)
    height = max(cell.height - top - bottom, 1)
    return width, height


_NATIVE_HWPUNIT_PER_PIXEL = 75  # 96dpi 기준: 7200 hwpunit/inch ÷ 96px/inch = 75


def _fix_img_dim(paragraph, image_path: str) -> None:
    """python-hwpx의 `add_picture()`가 만드는 `<hp:pic>`의 `<hp:imgClip>`을 바로잡는다.

    실제 한글이 만든 hwpx 파일과 직접 대조해서 찾은 문제 — `imgClip`(그림의 어느 영역을
    보여줄지 정하는 "원본 기준" 사각형)의 `right`/`bottom`은 우리가 화면에 표시하려는
    크기(`sz`)가 아니라 **원본 이미지의 실제 픽셀 크기 × 75(96dpi 환산)**여야 한다(실측:
    4032×3024 사진을 한글이 직접 넣었을 때 imgClip이 정확히 302400×226800 = 4032×75,
    3024×75였다). python-hwpx는 이 값을 화면 표시 크기와 같게 채워버리는데, 그러면 한글이
    "원본 중 이만큼만(대개 왼쪽 위 한 귀퉁이) 보여줘"로 오해해서 사진이 잘려 보인다 —
    도장·이전지적사항 사진·TBM 사진이 전부 이 문제였다. `imgDim`은 한글 정품 파일(빌드
    10.x/12.x 실측)에서 항상 `imgClip`의 right/bottom과 같은 값이라 똑같이 맞춘다 — 예전엔
    픽셀 수를 그대로 넣어 `imgClip`과 어긋나 있었다."""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            iw, ih = img.size
    except Exception:
        return
    if iw <= 0 or ih <= 0:
        return

    clip_right = iw * _NATIVE_HWPUNIT_PER_PIXEL
    clip_bottom = ih * _NATIVE_HWPUNIT_PER_PIXEL

    last_run = paragraph.runs[-1]
    for child in last_run.element:
        if isinstance(child.tag, str) and child.tag.endswith("}pic"):
            for sub in child:
                tag = sub.tag if isinstance(sub.tag, str) else ""
                if tag.endswith("}imgClip"):
                    sub.set("right", str(clip_right))
                    sub.set("bottom", str(clip_bottom))
                elif tag.endswith("}imgDim"):
                    sub.set("dimwidth", str(clip_right))
                    sub.set("dimheight", str(clip_bottom))


def _insert_fit_picture_in_cell(doc, cell, image_path: str) -> None:
    para = cell.paragraphs[0]
    _clear_pictures(para)
    box_w, box_h = _cell_inner_box(cell)
    width, height = _fit_size(image_path, box_w, box_h)
    item_id = _register_image(doc, Path(image_path))
    para.add_picture(item_id, width=width, height=height)
    _fix_img_dim(para, image_path)


_SIGNATURE_WIDTH_MM = 14
_HWPUNIT_PER_MM = 7200 / 25.4

# 표3 "담당요원" 값 칸(t3_005)의 종이 기준 절대좌표(mm) — pyhwpx 버전(report_builder_hwp_images.py)
# 에서 실측한 값을 그대로 재사용한다(문서 서식 자체는 안 바뀌었으므로 유효).
_STAFF_CELL_RIGHT_EDGE_MM = 194.08
_STAFF_ROW_CENTER_MM = 215.45

# 표3 "현장책임자(통보방법)" 서명(t3_008)의 종이 기준 절대좌표(mm) — 위와 동일한 이유로 재사용.
_NOTIFY_SIGNATURE_LEFT_EDGE_MM = 87.0
_NOTIFY_SIGNATURE_ROW_CENTER_MM = 241.04


def _mm(value: float) -> int:
    return round(value * _HWPUNIT_PER_MM)


def _insert_floating_signature(
    doc, field_name: str, image_path: str, *, left_mm: float, row_center_mm: float, width_mm: float
) -> None:
    """서명/도장 이미지를 문단 흐름과 무관하게 종이 기준 절대좌표에 글자 위로 겹쳐 띄운다.

    `paragraph.add_picture(..., treat_as_char=False, pos_overrides={...})`가 python-hwpx의
    "PAPER 기준 절대좌표 배치" 기능이다(라이브러리 자체 문서 문자열에 "도장을 글자 위에
    겹쳐 찍을 때"라고 명시돼 있음 — 정확히 이 용도로 설계됨). COM 버전은 `VertOffset`/
    `HorzOffset`이 여백을 뺀 본문 영역 기준이라 페이지 여백을 직접 빼야 했지만, python-hwpx의
    "PAPER"는 실측 확인 결과 진짜 종이 왼쪽/위쪽 끝 기준이었다 — 여백을 빼면 오히려 위치가
    틀어진다(실측: 담당요원 도장이 엉뚱한 행으로 튀고, 현장책임자 서명이 안 보이게 됨).

    이미지는 어떤 문단에 "속하는지"는 문서 흐름상의 소속일 뿐 화면 위치에는 영향이 없다
    (좌표가 절대값이므로) — 그래도 어떤 필드 근처에 넣을 이미지인지 문서 구조상 알아볼 수
    있도록 그 필드가 있는 칸의 문단에 붙인다.
    """
    from PIL import Image

    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    paragraph = table.cell(row, col).paragraphs[0]

    try:
        with Image.open(image_path) as img:
            iw, ih = img.size
    except Exception:
        return
    if iw <= 0 or ih <= 0:
        return
    height_mm = width_mm * ih / iw
    top_mm = row_center_mm - height_mm / 2

    horz_offset = _mm(left_mm)
    vert_offset = _mm(top_mm)

    item_id = _register_image(doc, Path(image_path))
    paragraph.add_picture(
        item_id,
        width=_mm(width_mm),
        height=_mm(height_mm),
        treat_as_char=False,
        pos_overrides={
            "horzRelTo": "PAPER",
            "vertRelTo": "PAPER",
            "horzAlign": "LEFT",
            "vertAlign": "TOP",
            "horzOffset": horz_offset,
            "vertOffset": vert_offset,
        },
        text_wrap="IN_FRONT_OF_TEXT",
    )
    _fix_img_dim(paragraph, image_path)


def _clear_cell_pictures(cell) -> None:
    _clear_pictures(cell.paragraphs[0])


def _parse_cell_addr(addr: str) -> tuple[int, int]:
    """"B1" 같은 셀 주소를 (row, col) 0-based 튜플로 바꾼다."""
    letters = "".join(c for c in addr if c.isalpha())
    digits = "".join(c for c in addr if c.isdigit())
    col = 0
    for ch in letters.upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(digits) - 1, col - 1


def _locate_field_cell(doc, field_name: str):
    """`field_name` 누름틀 필드가 들어있는 (table, row, col)을 찾는다 — 필드가 없거나
    표 안에 없으면 None."""
    field = next((f for f in doc.fields.all if f.name == field_name), None)
    if field is None:
        return None

    node = field.element
    tc_node = None
    tbl_node = None
    while node is not None:
        tag = node.tag if isinstance(node.tag, str) else ""
        if tc_node is None and tag.endswith("}tc"):
            tc_node = node
        if tag.endswith("}tbl"):
            tbl_node = node
            break
        node = node.getparent()
    if tc_node is None or tbl_node is None:
        return None

    for table in doc.tables.all:
        if table.element is not tbl_node:
            continue
        for r in range(table.row_count):
            for c in range(table.column_count):
                try:
                    cell = table.cell(r, c)
                except Exception:
                    continue
                if cell.element is tc_node:
                    return table, r, c
    return None


_SITE_PHOTO_CELLS = {1: "B1", 2: "C1", 3: "B2", 4: "C2"}
_OVERVIEW_PHOTO_TABLE_INDEX = 4
_INSPECTION_PHOTO_TABLE_INDEX = 5


def fill_overview_inspection_images(doc, report: Report) -> None:
    """3. 전경사진 및 점검사진 — 표4(전경사진)/표5(점검사진)의 2x2 사진 칸."""
    overview = {p.slot: p for p in report.overview_photos}
    table = doc.tables.all[_OVERVIEW_PHOTO_TABLE_INDEX]
    for slot, addr in _SITE_PHOTO_CELLS.items():
        row, col = _parse_cell_addr(addr)
        cell = table.cell(row, col)
        _clear_cell_pictures(cell)
        photo = overview.get(slot)
        if photo and photo.photo_path and Path(photo.photo_path).exists():
            _insert_fit_picture_in_cell(doc, cell, photo.photo_path)

    inspection = {p.slot: p for p in report.inspection_photos}
    table = doc.tables.all[_INSPECTION_PHOTO_TABLE_INDEX]
    for slot, addr in _SITE_PHOTO_CELLS.items():
        row, col = _parse_cell_addr(addr)
        cell = table.cell(row, col)
        _clear_cell_pictures(cell)
        photo = inspection.get(slot)
        if photo and photo.photo_path and Path(photo.photo_path).exists():
            _insert_fit_picture_in_cell(doc, cell, photo.photo_path)


def fill_finding_images(doc, report: Report) -> None:
    """지적사항 표(8번) 각 항목의 사진 칸(유해위험요인 칸 왼쪽)."""
    findings = {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        located = _locate_field_cell(doc, f"finding{slot}_hazard")
        if located is None:
            continue
        table, row, col = located
        if col == 0:
            continue
        cell = table.cell(row, col - 1)
        _clear_cell_pictures(cell)
        finding = findings.get(slot)
        if finding and finding.photo_path and Path(finding.photo_path).exists():
            _insert_fit_picture_in_cell(doc, cell, finding.photo_path)


_PREVIOUS_FINDING_PHOTO_FIELDS = {slot: (f"previous_finding{slot}_title", f"previous_finding{slot}_content") for slot in (1, 2, 3, 4)}


def fill_previous_finding_images(doc, report: Report) -> None:
    """4번 "이전 기술지도 사항 이행여부" — 표4~7의 원본 지적사항 사진(제목 칸 위)/이행완료
    증빙 사진(내용 칸 위). 사진 칸의 실제 크기(비율 유지)에 맞춰 채운다 — 예전(pyhwpx) 버전은
    "한 페이지에 두 건이 들어와야 한다"는 이유로 세로 45mm 고정 상한을 뒀지만, 지금 템플릿의
    실제 칸 높이(약 53mm)가 이미 그 조건에 맞게 짜여 있어 칸 크기를 그대로 쓰는 편이 더
    꽉 차 보이면서도 안전하다(실측 확인)."""
    previous = {p.slot: p for p in report.previous_findings}
    for slot, (title_field, content_field) in _PREVIOUS_FINDING_PHOTO_FIELDS.items():
        title_loc = _locate_field_cell(doc, title_field)
        content_loc = _locate_field_cell(doc, content_field)
        pf = previous.get(slot)

        if title_loc is not None:
            table, row, col = title_loc
            if row > 0:
                cell = table.cell(row - 1, col)
                _clear_cell_pictures(cell)
                if pf:
                    _, _, photo_path = pf.display_fields()
                    if photo_path and Path(photo_path).exists():
                        _insert_fit_picture_in_cell(doc, cell, photo_path)

        if content_loc is not None:
            table, row, col = content_loc
            if row > 0:
                cell = table.cell(row - 1, col)
                _clear_cell_pictures(cell)
                if pf and pf.completion_photo_path and Path(pf.completion_photo_path).exists():
                    _insert_fit_picture_in_cell(doc, cell, pf.completion_photo_path)


_TBM_PHOTO_ANCHOR_FIELD = "t16_002"


def fill_support_images(doc, report: Report) -> None:
    """10. 사업장 지원 사항 — TBM 행의 비고 칸(그 행의 맨 오른쪽 칸).

    예전엔 "참석인원 칸(t16_002)에서 오른쪽으로 3칸"이라는 고정 칸 수로 비고 칸을
    찾았는데, 사용자가 한글에서 그 행의 칸 경계선을 직접 드래그해 폭을 조정하자 한글이
    폭만 바꾼 게 아니라 그 행 자체를 8칸에서 11칸으로 더 잘게 쪼개버려서(실측 확인)
    "오른쪽 3칸"이 더 이상 비고 칸을 안 가리키게 됐다 — 그 결과 새로 올린 TBM 사진이
    "교육장소" 밑 엉뚱한 칸에 들어가고, 원래 지워야 할 원본 샘플 사진은 진짜 비고 칸에
    그대로 남아있는 버그로 나타났다(실사용 확인, 2026-09-16). 표 칸 개수가 바뀌어도
    깨지지 않도록, "그 행의 마지막 칸"(비고는 항상 맨 오른쪽 — 표 설계상 고정)으로
    찾는 방식으로 바꿨다.
    """
    located = _locate_field_cell(doc, _TBM_PHOTO_ANCHOR_FIELD)
    if located is None:
        return
    table, row, _col = located
    cell = table.cell(row, table.column_count - 1)
    _clear_cell_pictures(cell)

    education = report.safety_education
    if education and education.photo_path and Path(education.photo_path).exists():
        _insert_fit_picture_in_cell(doc, cell, education.photo_path)


def fill_signoff_images(doc, report: Report, site: Site) -> None:
    """결재란(표0) 이사/대표이사 도장 + 담당요원/현장책임자 서명(글자 위 겹침 배치)."""
    table = doc.tables.all[0]

    director_path, _ = config.get_company_signature("director")
    if director_path and Path(director_path).exists():
        row, col = _parse_cell_addr("B2")
        _insert_fit_picture_in_cell(doc, table.cell(row, col), director_path)

    ceo_path, _ = config.get_company_signature("ceo")
    if ceo_path and Path(ceo_path).exists():
        row, col = _parse_cell_addr("C2")
        _insert_fit_picture_in_cell(doc, table.cell(row, col), ceo_path)

    staff = report.assigned_staff
    if staff and staff.signature_path and Path(staff.signature_path).exists():
        _insert_floating_signature(
            doc,
            "t3_005",
            staff.signature_path,
            left_mm=_STAFF_CELL_RIGHT_EDGE_MM - _SIGNATURE_WIDTH_MM,
            row_center_mm=_STAFF_ROW_CENTER_MM,
            width_mm=_SIGNATURE_WIDTH_MM,
        )

    if report.notify_signature_path and Path(report.notify_signature_path).exists():
        _insert_floating_signature(
            doc,
            "t3_008",
            report.notify_signature_path,
            left_mm=_NOTIFY_SIGNATURE_LEFT_EDGE_MM,
            row_center_mm=_NOTIFY_SIGNATURE_ROW_CENTER_MM,
            width_mm=_SIGNATURE_WIDTH_MM,
        )


_MATERIAL_APPENDIX_WIDTH_MM = 180
_MATERIAL_APPENDIX_HEIGHT_MM = 250
_MATERIAL_FIRST_APPENDIX_HEIGHT_MM = 230  # 제목 줄이 같이 들어가는 첫 장만 이미지를 살짝 줄인다
_MATERIAL_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_MATERIAL_PDF_RENDER_WIDTH_PX = 1600  # 인쇄 품질(A4 폭 기준 약 193dpi)로 렌더링
_SECTION_TITLE_FONT = "HY견고딕"
_SECTION_TITLE_HEIGHT = 1300  # 13pt


def _material_appendix_pages(source_path: Path) -> list[Path]:
    """제공자료 한 건을 부록에 넣을 이미지 파일 목록으로 바꾼다.

    jpg/png 등은 원본 파일 그대로 1장, PDF는 `render_pdf_pages()`(pymupdf, 미리보기 모달과
    같은 렌더러)로 페이지마다 임시 PNG로 렌더링해 여러 장이 된다. 반환된 경로 중 원본이
    아니라 새로 만든 임시 파일은 호출부가 다 쓰고 나면 지워야 한다(`fill_material_appendix`의
    `finally` 참고)."""
    suffix = source_path.suffix.lower()
    if suffix in _MATERIAL_IMAGE_SUFFIXES:
        return [source_path]
    if suffix == ".pdf":
        tmp_dir = Path(tempfile.gettempdir()) / "claude" / "hwpx_material_pdf"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        pages = render_pdf_pages(source_path, width=_MATERIAL_PDF_RENDER_WIDTH_PX)
        paths = []
        for page_bytes in pages:
            out_path = tmp_dir / f"{uuid.uuid4().hex}.png"
            out_path.write_bytes(page_bytes)
            paths.append(out_path)
        return paths
    return []


def fill_material_appendix(doc, report: Report) -> None:
    """11번 "제공자료"에서 고른 포스터/카드뉴스를 문서 맨 끝에 새 페이지로 붙인다.

    선택된 자료가 1개면 최소 1페이지, 2개면 최소 2페이지가 추가된다(PDF는 페이지 수만큼
    더 늘어난다). 첫 장 맨 위에는 본문의 다른 번호 제목과 같은 서체·크기(HY견고딕 13pt)로
    "11. 제공자료" 제목을 붙인다 — 그래서 첫 장만 이미지 높이를 살짝 줄여 제목과 함께 한
    페이지에 들어가게 한다. 페이지 나누기는 새로 추가하는 문단에
    `page_break_before=True`를 걸어서 만든다(COM 버전의 `BreakPage` 액션에 대응).
    """
    if report.materials_na:
        return
    is_first = True
    temp_paths: list[Path] = []
    try:
        for pm in report.provided_materials:
            source_path: str | Path | None = pm.custom_photo_path
            if source_path and Path(source_path).exists():
                pass
            elif pm.material:
                source_path = resolve_material_path(pm.material.file_path)
            else:
                source_path = None
            if not source_path:
                continue
            source_path = Path(source_path)
            page_paths = _material_appendix_pages(source_path)
            if source_path.suffix.lower() == ".pdf":
                temp_paths.extend(page_paths)

            for page_path in page_paths:
                height_mm = _MATERIAL_APPENDIX_HEIGHT_MM
                if is_first:
                    # 제목과 첫 이미지를 별도 문단 둘로 나누면(문단1=제목, 문단2=그림) 한글이
                    # 둘을 다른 페이지로 갈라버리는 문제가 실측 확인됐다(`keep_with_next`를
                    # 걸어도 안 붙음) — 대신 제목 문단 하나 안에 줄바꿈("\n")으로 다음 줄을
                    # 만들고, 그 같은 문단에 그림을 이어 붙인다(COM 버전의
                    # "insert_text→BreakPara→insert_picture" 연속 흐름과 동일한 구조).
                    title_para = doc.add_paragraph("11. 제공자료\n")
                    title_index = len(list(doc.paragraphs)) - 1
                    doc.set_paragraph_format(paragraph_index=title_index, page_break_before=True)
                    title_style = doc.ensure_run_style(font=_SECTION_TITLE_FONT, size=_SECTION_TITLE_HEIGHT / 100)
                    for run in title_para.runs:
                        run.char_pr_id_ref = title_style
                    pic_para = title_para
                    height_mm = _MATERIAL_FIRST_APPENDIX_HEIGHT_MM
                    is_first = False
                else:
                    pic_para = doc.add_paragraph("")
                    pic_index = len(list(doc.paragraphs)) - 1
                    doc.set_paragraph_format(paragraph_index=pic_index, page_break_before=True)

                item_id = _register_image(doc, page_path)
                pic_para.add_picture(item_id, width=_mm(_MATERIAL_APPENDIX_WIDTH_MM), height=_mm(height_mm))
                _fix_img_dim(pic_para, str(page_path))
    finally:
        for temp_path in temp_paths:
            try:
                temp_path.unlink()
            except OSError:
                pass
