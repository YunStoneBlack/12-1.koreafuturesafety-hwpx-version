"""한글(.hwp) 산출물의 사진 칸 채우기 — 전경/점검사진(표4·5), 지적사항(표8), 이전
지적사항(표4~7), 제공자료 부록(11번).

`report_builder_hwp_images.py`(결재란·담당요원·TBM 서명/사진)에서 분리한 파일이다 —
그쪽은 "필드 하나에 이미지 하나"인 서명류이고, 이쪽은 슬롯 개수만큼 반복되는 사진 칸
채우기라 성격이 다르고 합쳐서 600줄을 넘겨 나눴다. 두 파일 모두
`report_builder_hwp.py`가 함께 불러 쓴다.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from core.models_db import Report
from core.thumbnail_generator import render_pdf_pages, resolve_material_path

_MATERIAL_APPENDIX_WIDTH_MM = 180
_MATERIAL_APPENDIX_HEIGHT_MM = 250
_MATERIAL_FIRST_APPENDIX_HEIGHT_MM = 230  # 제목 줄이 같이 들어가는 첫 장만 이미지를 살짝 줄인다
_MATERIAL_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_MATERIAL_PDF_RENDER_WIDTH_PX = 1600  # 인쇄 품질(A4 폭 기준 약 193dpi)로 렌더링
_SECTION_TITLE_FONT = "HY견고딕"
_SECTION_TITLE_HEIGHT_PT = 13


def _material_appendix_pages(source_path: Path) -> list[Path]:
    """제공자료 한 건을 부록에 넣을 이미지 파일 목록으로 바꾼다.

    jpg/png 등은 원본 파일 그대로 1장, PDF는 `render_pdf_pages()`(pymupdf, 미리보기 모달과
    같은 렌더러)로 페이지마다 임시 PNG로 렌더링해 여러 장이 된다 — `insert_picture()`가
    파일 경로만 받고 PDF 자체는 못 넣으므로, 어차피 그림으로 바꿔서 넣어야 한다. 반환된
    경로 중 원본이 아니라 새로 만든 임시 파일은 호출부가 다 쓰고 나면 지워야 한다
    (`fill_material_appendix`의 `finally` 참고).
    """
    suffix = source_path.suffix.lower()
    if suffix in _MATERIAL_IMAGE_SUFFIXES:
        return [source_path]
    if suffix == ".pdf":
        tmp_dir = Path(tempfile.gettempdir()) / "claude" / "hwp_material_pdf"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        pages = render_pdf_pages(source_path, width=_MATERIAL_PDF_RENDER_WIDTH_PX)
        paths = []
        for page_bytes in pages:
            out_path = tmp_dir / f"{uuid.uuid4().hex}.png"
            out_path.write_bytes(page_bytes)
            paths.append(out_path)
        return paths
    return []


def fill_material_appendix(hwp, report: Report) -> None:
    """11번 "제공자료"에서 고른 포스터/카드뉴스를 문서 맨 끝에 새 페이지로 붙인다.

    `report_builder_pdf._build_material_appendix()`와 같은 원칙 — 선택된 자료가 1개면 최소
    1페이지, 2개면 최소 2페이지가 추가된다(없으면 아무것도 안 붙인다. PDF는 페이지 수만큼
    더 늘어난다 — `_material_appendix_pages` 참고). 원본 이미지가 없는(직접 업로드 없이
    라이브러리만 고른 경우 `custom_photo_path`가 비어있어 `material.file_path`로 대체)
    경우는 건너뛴다. 첫 장 맨 위에는 본문의 다른 번호 제목(8·9·10번 등)과 같은 서체·크기
    (HY견고딕 13pt)로 "11. 제공자료" 제목을 붙인다 — 그래서 첫 장만 이미지 높이를 살짝
    줄여 제목과 함께 한 페이지에 들어가게 한다. "해당사항없음"으로 체크된 보고서는 고른
    자료가 있어도 전부 건너뛴다.
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
                hwp.MoveDocEnd()
                hwp.HAction.Run("BreakPage")
                height = _MATERIAL_APPENDIX_HEIGHT_MM
                if is_first:
                    hwp.insert_text("11. 제공자료")
                    hwp.HAction.Run("MoveLineBegin")
                    hwp.HAction.Run("MoveSelLineEnd")
                    hwp.set_font(FaceName=_SECTION_TITLE_FONT, Height=_SECTION_TITLE_HEIGHT_PT, Bold=False)
                    hwp.HAction.Run("MoveLineEnd")
                    hwp.HAction.Run("BreakPara")
                    height = _MATERIAL_FIRST_APPENDIX_HEIGHT_MM
                    is_first = False
                hwp.insert_picture(
                    str(page_path),
                    treat_as_char=True,
                    sizeoption=1,
                    width=_MATERIAL_APPENDIX_WIDTH_MM,
                    height=height,
                )
    finally:
        for temp_path in temp_paths:
            try:
                temp_path.unlink()
            except OSError:
                pass


def _delete_picture_near_field(hwp, field_name: str) -> None:
    """`field_name` 셀의 왼쪽 칸(사진 칸)에 앵커된 그림을 지운다.

    지적사항 표(8번, "현재 공정 내 현존하는 위험성 제거")는 표1~16 번호 체계 밖에 있는
    별도 표라 `get_into_nth_table()`로 못 찾는다 — 대신 이미 만들어둔 텍스트 필드
    (`finding{n}_hazard`)를 기준점 삼아 왼쪽 칸(사진 칸, A열)으로 한 칸 이동해 List ID로
    특정한다(`report_builder_hwp_images._delete_picture_at_cell`과 같은 방식).
    """
    if not hwp.field_exist(field_name):
        return
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    hwp.HAction.Run("TableLeftCell")
    list_id = hwp.get_pos()[0]
    for ctrl in hwp.ctrl_list:
        if ctrl.UserDesc != "그림":
            continue
        try:
            hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
        except Exception:
            continue
        if hwp.get_pos()[0] == list_id:
            hwp.delete_ctrl(ctrl)


def _insert_picture_near_field(hwp, field_name: str, image_path: str) -> bool:
    if not hwp.field_exist(field_name):
        return False
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    hwp.HAction.Run("TableLeftCell")
    hwp.insert_picture(image_path, treat_as_char=True, sizeoption=3)
    return True


_OVERVIEW_PHOTO_TABLE_INDEX = 4
_INSPECTION_PHOTO_TABLE_INDEX = 5
_SITE_PHOTO_CELLS = {1: "B1", 2: "C1", 3: "B2", 4: "C2"}


def fill_overview_inspection_images(hwp, report: Report) -> None:
    """3. 전경사진 및 점검사진 — 표4(전경사진)/표5(점검사진)의 2x2 사진 칸(B1/C1/B2/C2,
    순서대로 1~4번, 사용자가 한글에서 직접 짠 표)을 채운다. A열은 "전경 사진"/"점검 사진"
    라벨 칸(세로 병합)이라 필드 없이 표 인덱스+셀 주소로 바로 찾아간다
    (`report_builder_hwp_images._insert_in_cell`). 항상 기존 그림을 먼저 지우고(빈 슬롯이면
    지운 채로 둠) 업로드된 사진이 있으면 채워 넣는다(`fill_finding_images`와 같은 원칙)."""
    from core.report_builder_hwp_images import _delete_picture_at_cell, _insert_in_cell

    overview = {p.slot: p for p in report.overview_photos}
    for slot, addr in _SITE_PHOTO_CELLS.items():
        _delete_picture_at_cell(hwp, _OVERVIEW_PHOTO_TABLE_INDEX, addr)
        photo = overview.get(slot)
        if photo and photo.photo_path and Path(photo.photo_path).exists():
            _insert_in_cell(hwp, _OVERVIEW_PHOTO_TABLE_INDEX, addr, photo.photo_path)

    inspection = {p.slot: p for p in report.inspection_photos}
    for slot, addr in _SITE_PHOTO_CELLS.items():
        _delete_picture_at_cell(hwp, _INSPECTION_PHOTO_TABLE_INDEX, addr)
        photo = inspection.get(slot)
        if photo and photo.photo_path and Path(photo.photo_path).exists():
            _insert_in_cell(hwp, _INSPECTION_PHOTO_TABLE_INDEX, addr, photo.photo_path)


def fill_finding_images(hwp, report: Report) -> None:
    """지적사항 표(8번) 각 항목의 사진 칸 — 항상 기존 그림을 먼저 지우고(빈 슬롯이면 지운
    채로 둠), 지적사항에 업로드된 사진이 있으면 채워 넣는다. `fill_support_images`와 같은
    원칙(무관한 샘플 사진이 남지 않도록)."""
    findings = {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        field_name = f"finding{slot}_hazard"
        _delete_picture_near_field(hwp, field_name)
        finding = findings.get(slot)
        if finding and finding.photo_path and Path(finding.photo_path).exists():
            _insert_picture_near_field(hwp, field_name, finding.photo_path)


def _delete_picture_above_field(hwp, field_name: str) -> None:
    """`field_name` 칸의 바로 위 칸(사진 칸)에 앵커된 그림을 지운다.

    이전지적사항 표(표4~7)는 표1~19 번호 체계 안의 일반 표지만,
    `remove_unused_previous_finding_blocks()`가 빈 슬롯의 표를 통째로 지우면 뒤 슬롯의
    순서 번호가 앞으로 밀린다 — 그래서 `get_into_nth_table()`(순서 기반) 대신 이미 만들어둔
    텍스트 필드(제목 A3/내용 G3)를 기준점 삼아 `MoveUp`으로 한 칸 위(사진 칸, A2/G2)로
    이동해 List ID로 특정한다(`_delete_picture_near_field`와 같은 방식, 방향만 다름).
    """
    if not hwp.field_exist(field_name):
        return
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    hwp.HAction.Run("MoveUp")
    list_id = hwp.get_pos()[0]
    for ctrl in hwp.ctrl_list:
        if ctrl.UserDesc != "그림":
            continue
        try:
            hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
        except Exception:
            continue
        if hwp.get_pos()[0] == list_id:
            hwp.delete_ctrl(ctrl)

    # 원본 문서에 남아있던 "▪" 같은 빈 글머리 기호 — 사진이 없는 슬롯이어도(즉, 이 뒤에
    # `_insert_picture_above_field`가 호출되지 않는 경우에도) 항상 지운다.
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    hwp.HAction.Run("MoveUp")
    _clear_cell_text(hwp)


_PREVIOUS_FINDING_PHOTO_MAX_WIDTH_MM = 93.64  # 실측한 사진 칸(A2/G2) 너비 — 가로 상한(안전판)
_PREVIOUS_FINDING_PHOTO_MAX_HEIGHT_MM = 45.0  # 한 페이지에 두 건이 들어오도록 맞춘 세로 상한


def _fit_picture_size(image_path: str, max_width_mm: float, max_height_mm: float) -> tuple[float, float]:
    """이미지의 실제 가로세로 비율을 유지하면서, 세로를 `max_height_mm`(행 높이 예산)에
    맞춰 채우는 크기를 계산한다 — 가로는 셀 너비(`max_width_mm`)를 넘지 않는 한도 안에서
    세로 기준으로 정해진다(사용자 요청: 좌우 폭이 아니라 상하 높이에 맞출 것 — 사진마다
    비율이 달라 폭 기준으로 맞추면 세로 여백이 들쭉날쭉해 보인다).

    `insert_picture(sizeoption=3)`("셀 크기에 맞춰 비율 유지 확대/축소")는 셀 너비에 맞춰
    비율을 유지하다 보니 사진 한 장의 행 높이가 121.72mm까지 늘어나는 문제가 있었다(실측
    확인) — 이전지적사항 두 건이 한 페이지에 들어와야 하는데 한 건이 거의 페이지 하나를 다
    차지해버렸다. 그래서 셀 크기가 아니라 이 함수로 직접 계산한 크기를 `sizeoption=1`
    (지정 크기)로 넘긴다.
    """
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            width, height = img.size
    except Exception:
        return max_width_mm, max_height_mm
    if width <= 0 or height <= 0:
        return max_width_mm, max_height_mm
    ratio = min(max_width_mm / width, max_height_mm / height)
    return width * ratio, height * ratio


def _clear_cell_text(hwp) -> None:
    """현재 캐럿이 있는 칸의 텍스트를 지운다(원본 문서에 남아있던 "▪" 같은 빈 글머리
    기호 등) — 사진을 넣기 전에 호출해 사진 옆에 엉뚱한 글자가 같이 남지 않게 한다.
    `_add_education_location_field`(build_hwp_template_layout_fixes.py)와 같은 안전한
    한 줄씩 선택→삭제 패턴 — `TableCellBlock`으로 통째로 선택해 한 번에 지우면 앵커된
    개체(그림 등)까지 같이 지워질 위험이 있다.
    """
    guard = 0
    while guard < 200:
        hwp.TableCellBlock()
        text = hwp.get_selected_text(keep_select=False)
        if not text:
            break
        hwp.HAction.Run("MoveSelLineBegin")
        hwp.HAction.Run("MoveSelLineEnd")
        hwp.HAction.Run("Delete")
        guard += 1


def _insert_picture_above_field(hwp, field_name: str, image_path: str) -> bool:
    if not hwp.field_exist(field_name):
        return False
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    hwp.HAction.Run("MoveUp")
    _clear_cell_text(hwp)
    hwp.HAction.Run("ParagraphShapeAlignCenter")  # 사진이 칸 왼쪽에 붙지 않고 가운데 오도록
    width, height = _fit_picture_size(
        image_path, _PREVIOUS_FINDING_PHOTO_MAX_WIDTH_MM, _PREVIOUS_FINDING_PHOTO_MAX_HEIGHT_MM
    )
    hwp.insert_picture(image_path, treat_as_char=True, sizeoption=1, width=width, height=height)
    return True


_PREVIOUS_FINDING_PHOTO_FIELDS = {
    slot: (f"previous_finding{slot}_title", f"previous_finding{slot}_content") for slot in (1, 2, 3, 4)
}


def fill_previous_finding_images(hwp, report: Report) -> None:
    """4번 "이전 기술지도 사항 이행여부" — 표4~7의 A2(원본 지적사항 사진)/G2(이행완료
    증빙 사진)를 채운다.

    원본 사진은 `PreviousFinding.display_fields()`로 가져온다 — 직전 회차에서 이월된
    경우(source_finding_id 있음) 원본이 그 사이 수정됐을 수 있어 항상 최신 값을 반영한다
    (마법사·텍스트 필드와 동일한 실시간 동기화 원칙). 이행완료 증빙 사진은 이 보고서에서
    직접 업로드하는 값이라 원본과 무관하다. 항상 기존 그림을 먼저 지우고(빈 슬롯이면 지운
    채로 둠) 업로드된 사진이 있으면 채워 넣는다(`fill_finding_images`와 같은 원칙).
    """
    previous = {p.slot: p for p in report.previous_findings}
    for slot, (title_field, content_field) in _PREVIOUS_FINDING_PHOTO_FIELDS.items():
        _delete_picture_above_field(hwp, title_field)
        _delete_picture_above_field(hwp, content_field)
        pf = previous.get(slot)
        if not pf:
            continue
        _, _, photo_path = pf.display_fields()
        if photo_path and Path(photo_path).exists():
            _insert_picture_above_field(hwp, title_field, photo_path)
        if pf.completion_photo_path and Path(pf.completion_photo_path).exists():
            _insert_picture_above_field(hwp, content_field, pf.completion_photo_path)
