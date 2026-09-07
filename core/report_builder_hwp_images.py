"""한글(.hwp) 산출물에 실제 이미지를 삽입한다 — 결재란(이사/대표이사), 담당요원,
현장책임자(통보방법) 서명 + 표16 TBM 비고 칸의 안전교육 사진.

`report_builder_hwp_fields.py`는 텍스트 필드만 채운다. 이미지는 `put_field_text()`로는
넣을 수 없어 `hwp.insert_picture()`로 커서 위치에 직접 삽입하는 별도 단계로 분리했다.

- **결재란(표0, 이사/대표이사)**: B2/C2가 각각 이사/대표이사 서명 전용 빈 셀이라(표0은
  텍스트 필드화 대상이 아니었음 — `build_hwp_template.py` 참고), 그 셀 안으로 커서를 이동해
  셀 크기에 맞춰(`sizeoption=3`, 비율 유지) 삽입한다.
- **담당요원 서명**: `report_builder_hwp_fields.fill_signoff_fields()`가 t3_005 필드에
  "{이름}     "(이름 + 여백)만 써두므로, 그 필드 끝으로 이동해 이어서 삽입한다.
- **현장책임자(통보방법) 서명**: t3_008 필드가 "☑직접전달    (성함:   {이름}     서명:
  (연락처: {전화번호} )" 형태의 합성 문자열이라(원본 문서의 체크박스 캡션이 컨트롤 삭제와
  함께 사라져 이 함수가 라벨까지 전부 재조립함 — `fill_signoff_fields` 참고), "서명:" 바로
  뒤 여백 자리에 삽입해야 한다. 필드 시작에서 "서명:"까지의 정확한 문자 수를 파이썬에서 직접
  계산해(이름 길이에 따라 달라지므로 하드코딩하지 않음) 그만큼 `MoveRight`로 이동한 뒤
  삽입한다.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from core import config
from core.models_db import Report, Site

_SIGNATURE_WIDTH_MM = 14
_SIGNATURE_HEIGHT_MM = 6

_BOLD_TMP_DIR = Path(tempfile.gettempdir()) / "claude" / "hwp_signature_bold"


def _prepare_signature_image(image_path: str) -> str:
    """직접 그린 서명(투명 배경 위 얇은 획)을 굵고 진하게 다듬은 임시 PNG로 바꿔 반환한다.

    `SignaturePad`가 2px 펜으로 그린 획은 원본 그대로 문서에 삽입하면 작은 크기(14x6mm)로
    축소되면서 가늘고 흐릿해 보인다. 배경이 상당 부분 투명한 이미지(=직접 그린 서명)만
    골라 알파 채널을 이진화(반투명 안티에일리어싱 제거)하고 팽창시켜(획을 굵게) 순수
    검정으로 다시 칠한다. 업로드한 사진(예: 촬영한 서명, 신분증 사진)은 보통 배경이
    불투명해 이 조건에 안 걸리므로 원본 그대로 쓴다 — 사진을 잘못 새까맣게 칠하는 사고를
    막기 위한 안전장치.
    """
    from PIL import Image, ImageFilter

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
        # 배경이 대부분 불투명 — 그린 서명이 아니라 사진일 가능성이 높아 그대로 둔다.
        return image_path

    bold_alpha = alpha.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(5))
    solid_black = Image.new("RGBA", img.size, (0, 0, 0, 0))
    solid_black.putalpha(bold_alpha)

    _BOLD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _BOLD_TMP_DIR / f"{uuid.uuid4().hex}.png"
    solid_black.save(out_path, "PNG")
    return str(out_path)


def _insert_in_cell(hwp, table_index: int, addr: str, image_path: str) -> bool:
    hwp.MoveDocBegin()
    hwp.get_into_nth_table(table_index, select_cell=False)
    hwp.TableColBegin()
    hwp.TableColPageUp()

    guard = 0
    while hwp.get_cell_addr() != addr:
        if not hwp.TableRightCell():
            return False
        guard += 1
        if guard > 200:
            return False

    hwp.insert_picture(_prepare_signature_image(image_path), treat_as_char=True, sizeoption=3)
    return True


def _insert_after_field_text(hwp, field_name: str, image_path: str) -> bool:
    if not hwp.field_exist(field_name):
        return False
    hwp.move_to_field(field_name, text=True, start=False, select=False)
    hwp.insert_picture(
        _prepare_signature_image(image_path),
        treat_as_char=True,
        sizeoption=1,
        width=_SIGNATURE_WIDTH_MM,
        height=_SIGNATURE_HEIGHT_MM,
    )
    return True


def _insert_at_field_offset(hwp, field_name: str, offset: int, image_path: str) -> bool:
    if not hwp.field_exist(field_name):
        return False
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    for _ in range(offset):
        hwp.HAction.Run("MoveRight")
    hwp.insert_picture(
        _prepare_signature_image(image_path),
        treat_as_char=True,
        sizeoption=1,
        width=_SIGNATURE_WIDTH_MM,
        height=_SIGNATURE_HEIGHT_MM,
    )
    return True


def _delete_picture_at_cell(hwp, table_index: int, addr: str) -> None:
    """지정된 표/셀에 앵커된 그림(gso) 컨트롤을 찾아 지운다.

    셀 주소 문자열("G2")만으로 문서 전체를 훑으면 다른 표의 우연히 같은 주소를 가진 셀과
    섞일 수 있어, 먼저 그 표·셀까지 실제로 캐럿을 이동시켜 얻은 List ID(칸마다 고유한 문단
    리스트 식별자, `get_pos()`의 첫 번째 값)로 앵커 위치를 비교한다.
    """
    hwp.MoveDocBegin()
    hwp.get_into_nth_table(table_index, select_cell=False)
    hwp.TableColBegin()
    hwp.TableColPageUp()
    guard = 0
    while hwp.get_cell_addr() != addr:
        if not hwp.TableRightCell():
            return
        guard += 1
        if guard > 200:
            return
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


def fill_support_images(hwp, report: Report) -> None:
    """표16 TBM 행의 비고 칸(G2) — 원본 문서에 남아있던 실제 샘플 사진(다른 현장의 실제
    안전교육 사진)을 지우고, 이번 보고서에 안전교육 사진이 업로드돼 있으면 그 자리에
    채워 넣는다. 샘플 사진을 지우는 건 업로드 사진이 없을 때도 항상 하는데, 무관한 다른
    현장 사진이 마치 이 보고서의 실제 사진인 것처럼 남아있으면 안 되기 때문이다.
    """
    _delete_picture_at_cell(hwp, 16, "G2")

    education = report.safety_education
    if education and education.photo_path and Path(education.photo_path).exists():
        _insert_in_cell(hwp, 16, "G2", education.photo_path)


_MATERIAL_APPENDIX_WIDTH_MM = 180
_MATERIAL_APPENDIX_HEIGHT_MM = 250
_MATERIAL_FIRST_APPENDIX_HEIGHT_MM = 230  # 제목 줄이 같이 들어가는 첫 장만 이미지를 살짝 줄인다
_MATERIAL_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_SECTION_TITLE_FONT = "HY견고딕"
_SECTION_TITLE_HEIGHT_PT = 13


def fill_material_appendix(hwp, report: Report) -> None:
    """10번 "제공자료"에서 고른 포스터/카드뉴스를 문서 맨 끝에 한 장씩 새 페이지로 붙인다.

    `report_builder_pdf._build_material_appendix()`와 같은 원칙 — 선택된 자료가 1개면 1페이지,
    2개면 2페이지가 추가된다(없으면 아무것도 안 붙인다). 원본 이미지가 없는(직접 업로드
    없이 라이브러리만 고른 경우 `custom_photo_path`가 비어있어 `material.file_path`로
    대체) 경우와, 파일 형식이 이미지가 아닌 경우(PDF 등)는 건너뛴다. 첫 장 맨 위에는
    본문의 다른 번호 제목(7·8·9번 등)과 같은 서체·크기(HY견고딕 13pt)로 "10. 제공자료"
    제목을 붙인다 — 그래서 첫 장만 이미지 높이를 살짝 줄여 제목과 함께 한 페이지에 들어가게
    한다. "해당사항없음"으로 체크된 보고서는 고른 자료가 있어도 전부 건너뛴다.
    """
    if report.materials_na:
        return
    is_first = True
    for pm in report.provided_materials:
        source_path = pm.custom_photo_path
        if not source_path and pm.material:
            source_path = pm.material.file_path
        if not source_path or not Path(source_path).exists():
            continue
        if Path(source_path).suffix.lower() not in _MATERIAL_IMAGE_SUFFIXES:
            continue
        hwp.MoveDocEnd()
        hwp.HAction.Run("BreakPage")
        height = _MATERIAL_APPENDIX_HEIGHT_MM
        if is_first:
            hwp.insert_text("10. 제공자료")
            hwp.HAction.Run("MoveLineBegin")
            hwp.HAction.Run("MoveSelLineEnd")
            hwp.set_font(FaceName=_SECTION_TITLE_FONT, Height=_SECTION_TITLE_HEIGHT_PT, Bold=False)
            hwp.HAction.Run("MoveLineEnd")
            hwp.HAction.Run("BreakPara")
            height = _MATERIAL_FIRST_APPENDIX_HEIGHT_MM
            is_first = False
        hwp.insert_picture(
            source_path,
            treat_as_char=True,
            sizeoption=1,
            width=_MATERIAL_APPENDIX_WIDTH_MM,
            height=height,
        )


def _delete_picture_near_field(hwp, field_name: str) -> None:
    """`field_name` 셀의 왼쪽 칸(사진 칸)에 앵커된 그림을 지운다.

    지적사항 표(7번, "현재 공정 내 현존하는 위험성 제거")는 표1~16 번호 체계 밖에 있는
    별도 표라 `get_into_nth_table()`로 못 찾는다 — 대신 이미 만들어둔 텍스트 필드
    (`finding{n}_hazard`)를 기준점 삼아 왼쪽 칸(사진 칸, A열)으로 한 칸 이동해 List ID로
    특정한다(`_delete_picture_at_cell`과 같은 방식).
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


def fill_finding_images(hwp, report: Report) -> None:
    """지적사항 표(7번) 각 항목의 사진 칸 — 항상 기존 그림을 먼저 지우고(빈 슬롯이면 지운
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
    """3번 "이전 기술지도 사항 이행여부" — 표4~7의 A2(원본 지적사항 사진)/G2(이행완료
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


def fill_signoff_images(hwp, report: Report, site: Site) -> None:
    director_path, _ = config.get_company_signature("director")
    if director_path and Path(director_path).exists():
        _insert_in_cell(hwp, 0, "B2", director_path)

    ceo_path, _ = config.get_company_signature("ceo")
    if ceo_path and Path(ceo_path).exists():
        _insert_in_cell(hwp, 0, "C2", ceo_path)

    staff = report.assigned_staff
    if staff and staff.signature_path and Path(staff.signature_path).exists():
        _insert_after_field_text(hwp, "t3_005", staff.signature_path)

    if report.notify_signature_path and Path(report.notify_signature_path).exists():
        method = report.notification_method
        signee = report.notify_signee_name or (site.manager_name if site else "")
        prefix = f"{'☑' if method == '직접전달' else '☐'}직접전달    (성함:   {signee}     서명:"
        _insert_at_field_offset(hwp, "t3_008", len(prefix), report.notify_signature_path)
