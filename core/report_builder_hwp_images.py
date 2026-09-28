"""한글(.hwp) 산출물에 실제 이미지를 삽입한다 — 결재란(이사/대표이사), 담당요원,
현장책임자(통보방법) 서명 + 표16 TBM 비고 칸의 안전교육 사진.

전경/점검사진·지적사항·이전지적사항·제공자료 부록의 사진 칸 채우기는
`report_builder_hwp_images_findings.py`로 분리돼 있다(합치면 600줄을 넘어서 나눔) —
`report_builder_hwp.py`가 두 파일을 함께 불러 쓴다.

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

담당요원 서명은 도장 이미지라 찌그러뜨리면 안 되는데, 그 칸(세로 6mm)은 원본 비율을
지키기엔 너무 좁다. 그래서 원본 비율 그대로, 칸 경계를 넘어가도 좋으니 이름 옆에 겹쳐
넣고 — 표 선이 도장 위에 그려지도록 뒤로 보낸다.

**시행착오 기록** (같은 실수를 반복하지 않기 위해 남겨둔다):

1. 일단 "글자처럼" 삽입한 뒤 `TreatAsChar=False`로 꺼서 띄우는 방법 자체는 필요하다(그림을
   문단/표 흐름에서 완전히 빼내야 찌그러뜨리지 않고 칸 밖으로 낼 수 있다).
2. 처음에 `VertRelTo="Para"`/`HorzRelTo="Column"`(칸 기준 상대 위치)으로 띄웠더니, 화면에
   보이는 위치는 그럴듯한데 **한글의 페이지 나누기 계산에는 여전히 그 그림 크기가 그
   문단에 딸린 것으로 잡혀서** 문서 전체 페이지 수가 늘어나고, 그 여파로 옆의 "이름" 글자
   위치까지 밀리는 부작용이 있었다(직접 재현 테스트로 확인). "뒤로 보내기"는 그리는
   순서(z-order)만 바꿀 뿐 페이지 분량 계산에서 빼주지는 않는다.
3. 그래서 `VertRelTo`/`HorzRelTo`를 **"Page"(종이 자체 기준 절대좌표)**로 바꿨다 — 문단/표
   흐름과 완전히 무관해져서 페이지 수가 더 이상 안 늘어난다. 대신 이제 위치를 "몇 번째
   글자 뒤"가 아니라 "종이 위 몇 mm 지점"으로 직접 지정해야 한다.
4. 표3(기술지도 개요)은 항상 첫 페이지, 표1·표2 바로 아래 고정된 자리에 있고 그 위 내용도
   보고서마다 구조가 똑같아서(사용자 확인), "담당요원" 칸의 종이 기준 좌표를 실측해서
   상수로 고정해도 된다 — `_STAFF_CELL_RIGHT_EDGE_MM`/`_STAFF_ROW_CENTER_MM`가 그 값이다
   (실제 템플릿을 열어 PDF로 뽑은 뒤 표 테두리선의 좌표를 직접 측정해 구했다).
5. `VertOffset`/`HorzOffset`는 종이 맨 가장자리가 아니라 **본문 영역 시작점(여백 뺀 자리)
   기준**이었다 — 종이 절대좌표로 계산한 값에서 이 문서의 위/왼쪽 여백(TopMargin/
   LeftMargin, 실측 20mm/15mm)을 빼줘야 정확한 자리에 앉는다. 여백은 하드코딩하지 않고
   `HSecDef`에서 매번 읽어온다(템플릿 여백이 바뀌어도 안 깨지도록).

현장책임자(통보방법) 서명은 도장이 아니라 그 옆에 "(연락처: ...)" 텍스트가 더 이어지는
문장 중간 자리라 "칸 기준 좌표"라는 전제 자체가 안 맞아 이 방식을 안 쓰고 그대로 뒀다
(기존처럼 14x6mm 고정 크기, 찌그러짐 있음 — 필요해지면 그때 손본다).
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from core import config
from core.models_db import Report, Site
from core.thumbnail_generator import render_pdf_pages, resolve_material_path

_SIGNATURE_WIDTH_MM = 14
_SIGNATURE_HEIGHT_MM = 6

# "10. 사업장 지원 사항"(TBM/장비사용) 표의 TBM 비고 사진 칸(G2) — 예전엔 이 표를 고정
# 인덱스(`get_into_nth_table`)로 찾았는데, 지적사항/이전지적사항이 4건 미만이라 빈 슬롯 표가
# `fill_all()` 안에서 지워지면(remove_unused_finding_blocks 등) 그 시점 이후의 모든 표 인덱스가
# 삭제된 개수만큼 밀린다는 걸 놓치고 있었다 — 표4/5(전경·점검사진) 추가로 표 개수 자체가
# 늘어나는 변경뿐 아니라, **같은 문서 안에서 슬롯 개수에 따라 표가 지워지는 것만으로도** 인덱스가
# 흔들린다(실측 확인: 지적사항 0건 + 이전지적사항 2건인 보고서에서 TBM 사진이 옛 샘플 그대로
# 남아있던 버그, 2026-09-11). 그래서 인덱스 대신, 같은 행에 이미 있는 텍스트 필드(`t16_002`,
# 참석인원 — D열)를 기준점 삼아 오른쪽으로 3칸(D→E→F→G) 이동해 G2를 찾는다(`_find_finding_table_ctrl`
# 등과 같은 "필드 앵커" 원칙 — 표1~19 번호 체계 밖 표뿐 아니라 번호 체계 안 표도 슬롯 삭제로
# 흔들릴 수 있으면 인덱스보다 필드 앵커가 안전하다).
_TBM_PHOTO_ANCHOR_FIELD = "t16_002"
_TBM_PHOTO_ANCHOR_RIGHT_STEPS = 3

# 표3 "담당요원" 값 칸(t3_005)의 종이 기준 절대좌표(mm) — 실제 템플릿을 PDF로 뽑아 표
# 테두리선 좌표를 실측해서 구한 값. 위 모듈 docstring "시행착오 기록" 5번 참고.
_STAFF_CELL_RIGHT_EDGE_MM = 194.08  # 담당요원 값 칸 오른쪽 테두리 (종이 왼쪽 기준)
_STAFF_ROW_CENTER_MM = 215.45  # 담당요원 행 세로 중앙 (종이 위쪽 기준)

# 표3 "현장책임자(통보방법)" 서명(t3_008)의 종이 기준 절대좌표(mm) — "서명:" 뒤 4칸
# 띄운 위치를 실제 렌더링에서 실측했다(피드백으로 정한 위치라 이름 길이가 크게 다르면
# 다소 밀릴 수 있음). "직접전달" 체크박스를 t3_020으로 옮기고 표3 행 높이도 줄인 뒤
# (2026-09-10) "서명:"/"연락처:" 위치가 달라져서 재실측했다 — 템플릿을 또 구조 변경하면
# 다시 어긋날 수 있으니, 실제 렌더링에서 "서명:"과 "연락처:" 사이 빈 자리에 잘 들어가는지
# 확인할 것.
_NOTIFY_SIGNATURE_LEFT_EDGE_MM = 87.0
_NOTIFY_SIGNATURE_ROW_CENTER_MM = 241.04

_BOLD_TMP_DIR = Path(tempfile.gettempdir()) / "claude" / "hwp_signature_bold"


def _prepare_signature_image(image_path: str) -> str:
    """직접 그린 서명(투명 배경 위 얇은 획)을 굵고 진하게 다듬은 임시 PNG로 바꿔 반환한다.

    `SignaturePad`가 2px 펜으로 그린 획은 원본 그대로 문서에 삽입하면 작은 크기(14x6mm)로
    축소되면서 가늘고 흐릿해 보인다. 배경이 상당 부분 투명한 이미지(=직접 그린 서명)만
    골라 알파 채널을 이진화(반투명 안티에일리어싱 제거)하고 팽창시켜(획을 굵게) 순수
    검정으로 다시 칠한다. 업로드한 사진(예: 촬영한 서명, 신분증 사진)은 보통 배경이
    불투명해 이 조건에 안 걸리므로 원본 그대로 쓴다 — 사진을 잘못 새까맣게 칠하는 사고를
    막기 위한 안전장치.

    다만 인주 도장처럼 배경이 투명한 PNG로 업로드된 이미지는 배경 투명도만으로는 손으로
    그린 서명과 구분이 안 된다 — 그런 이미지까지 이 로직을 타면 색과 무늬가 있는 도장이
    검정 뭉개진 원으로 바뀌어버린다. 손 서명은 펜 색 하나(대개 무채색에 가까운 검정)뿐이고
    도장은 인주 색(빨강 등) 채도가 뚜렷하므로, 불투명 영역의 평균 채도를 봐서 색이 있으면
    도장/사진으로 보고 원본을 그대로 쓴다.
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
        # 배경이 대부분 불투명 — 그린 서명이 아니라 사진일 가능성이 높아 그대로 둔다.
        return image_path

    opaque_mask = alpha.point(lambda v: 255 if v > 128 else 0)
    saturation = img.convert("RGB").convert("HSV").split()[1]
    avg_saturation = ImageStat.Stat(saturation, mask=opaque_mask).mean[0]
    if avg_saturation > 30:
        # 색이 뚜렷함 — 도장 인주 색 등 실제 이미지로 보고 원본을 그대로 쓴다.
        return image_path

    bold_alpha = alpha.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(5))
    solid_black = Image.new("RGBA", img.size, (0, 0, 0, 0))
    solid_black.putalpha(bold_alpha)

    _BOLD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _BOLD_TMP_DIR / f"{uuid.uuid4().hex}.png"
    solid_black.save(out_path, "PNG")
    return str(out_path)


def _aspect_preserving_height(image_path: str, width_mm: float) -> float:
    """`width_mm`으로 가로를 고정했을 때, 원본 비율을 유지하는 세로 길이(mm)를 계산한다."""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            w, h = img.size
    except Exception:
        return _SIGNATURE_HEIGHT_MM
    if w <= 0 or h <= 0:
        return _SIGNATURE_HEIGHT_MM
    return width_mm * h / w


def _dock_picture_at_page_position(
    hwp, ctrl, left_edge_mm: float, row_center_mm: float, width_mm: float, height_mm: float
) -> None:
    """작게 삽입해둔 그림을 종이 기준 절대좌표로 띄운 뒤, 그제서야 실제 크기로 키운다.

    `left_edge_mm`/`row_center_mm`은 종이 왼쪽/위쪽을 기준으로 한 목표 위치의 물리적 좌표
    (여백 포함). `VertOffset`/`HorzOffset`은 여백을 뺀 본문 영역 기준이라 여기서 현재
    문서의 TopMargin/LeftMargin을 읽어와 빼준다. 자세한 이유는 위 모듈 docstring 참고.
    """
    try:
        sec_def = hwp.hwp.HParameterSet.HSecDef
        hwp.hwp.HAction.GetDefault("PageSetup", sec_def.HSet)
        left_margin_mm = hwp.HwpUnitToMili(sec_def.PageDef.LeftMargin)
        top_margin_mm = hwp.HwpUnitToMili(sec_def.PageDef.TopMargin)

        horz_offset_mm = left_edge_mm - left_margin_mm
        vert_offset_mm = (row_center_mm - height_mm / 2) - top_margin_mm

        pset = ctrl.Properties
        pset.SetItem("TreatAsChar", False)
        pset.SetItem("VertRelTo", hwp.hwp.VertRel("Page"))
        pset.SetItem("HorzRelTo", hwp.hwp.HorzRel("Page"))
        pset.SetItem("VertOffset", hwp.MiliToHwpUnit(vert_offset_mm))
        pset.SetItem("HorzOffset", hwp.MiliToHwpUnit(horz_offset_mm))
        pset.SetItem("TextWrap", 2)  # 그림을 글 뒤로
        pset.SetItem("Width", hwp.MiliToHwpUnit(width_mm))
        pset.SetItem("Height", hwp.MiliToHwpUnit(height_mm))
        ctrl.Properties = pset
    except Exception:
        pass


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
    prepared = _prepare_signature_image(image_path)
    target_height = _aspect_preserving_height(prepared, _SIGNATURE_WIDTH_MM)
    # 처음엔 원래 줄 높이(6mm)만큼만 작게 넣어 삽입 직후(아직 "글자처럼"인 채) 문서
    # 분량 계산에 영향을 최소화한 뒤, 종이 절대좌표로 띄우고 나서 실제(비율 유지)
    # 크기로 키운다 — 이유는 위 모듈 docstring "시행착오 기록" 참고.
    ctrl = hwp.insert_picture(
        prepared,
        treat_as_char=True,
        sizeoption=1,
        width=_SIGNATURE_WIDTH_MM,
        height=_SIGNATURE_HEIGHT_MM,
    )
    _dock_picture_at_page_position(
        hwp,
        ctrl,
        _STAFF_CELL_RIGHT_EDGE_MM - _SIGNATURE_WIDTH_MM,
        _STAFF_ROW_CENTER_MM,
        _SIGNATURE_WIDTH_MM,
        target_height,
    )
    return True


def _insert_at_field_offset(hwp, field_name: str, offset: int, image_path: str) -> bool:
    if not hwp.field_exist(field_name):
        return False
    hwp.move_to_field(field_name, text=True, start=True, select=False)
    for _ in range(offset):
        hwp.HAction.Run("MoveRight")
    prepared = _prepare_signature_image(image_path)
    target_height = _aspect_preserving_height(prepared, _SIGNATURE_WIDTH_MM)
    # 담당요원 서명과 같은 이유로 작게 넣었다가 종이 절대좌표로 띄우고 키운다 — 위 모듈
    # docstring "시행착오 기록" 참고. 다만 이 자리는 "서명:" 뒤 문장 중간이라 이름 길이가
    # 달라지면 좌표가 다소 어긋날 수 있다("담당요원"처럼 칸 오른쪽 끝에 못 붙임).
    ctrl = hwp.insert_picture(
        prepared,
        treat_as_char=True,
        sizeoption=1,
        width=_SIGNATURE_WIDTH_MM,
        height=_SIGNATURE_HEIGHT_MM,
    )
    _dock_picture_at_page_position(
        hwp, ctrl, _NOTIFY_SIGNATURE_LEFT_EDGE_MM, _NOTIFY_SIGNATURE_ROW_CENTER_MM, _SIGNATURE_WIDTH_MM, target_height
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


def _move_to_tbm_photo_cell(hwp) -> bool:
    if not hwp.field_exist(_TBM_PHOTO_ANCHOR_FIELD):
        return False
    hwp.move_to_field(_TBM_PHOTO_ANCHOR_FIELD, text=True, start=True, select=False)
    for _ in range(_TBM_PHOTO_ANCHOR_RIGHT_STEPS):
        if not hwp.TableRightCell():
            return False
    return True


def fill_support_images(hwp, report: Report) -> None:
    """TBM 행의 비고 칸(G2) — 원본 문서에 남아있던 실제 샘플 사진(다른 현장의 실제
    안전교육 사진)을 지우고, 이번 보고서에 안전교육 사진이 업로드돼 있으면 그 자리에
    채워 넣는다. 샘플 사진을 지우는 건 업로드 사진이 없을 때도 항상 하는데, 무관한 다른
    현장 사진이 마치 이 보고서의 실제 사진인 것처럼 남아있으면 안 되기 때문이다.

    표를 문서 내 고정 인덱스가 아니라 같은 행의 텍스트 필드(`t16_002`)를 기준점 삼아
    찾는다 — 이유는 `_TBM_PHOTO_ANCHOR_FIELD` 정의부 주석 참고.
    """
    if not _move_to_tbm_photo_cell(hwp):
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

    education = report.safety_education
    if education and education.photo_path and Path(education.photo_path).exists():
        if _move_to_tbm_photo_cell(hwp):
            hwp.insert_picture(_prepare_signature_image(education.photo_path), treat_as_char=True, sizeoption=3)


def fill_signoff_images(hwp, report: Report, site: Site) -> None:
    company_id = site.company_id if site else None  # 웹판 회사별 도장(데스크톱은 항상 None)
    director_path, _ = config.get_company_signature("director", company_id)
    if director_path and Path(director_path).exists():
        _insert_in_cell(hwp, 0, "B2", director_path)

    ceo_path, _ = config.get_company_signature("ceo", company_id)
    if ceo_path and Path(ceo_path).exists():
        _insert_in_cell(hwp, 0, "C2", ceo_path)

    staff = report.assigned_staff
    if staff and staff.signature_path and Path(staff.signature_path).exists():
        _insert_after_field_text(hwp, "t3_005", staff.signature_path)

    if report.notify_signature_path and Path(report.notify_signature_path).exists():
        signee = report.notify_signee_name or (site.manager_name if site else "")
        # t3_008이 "성명:   {signee}     서명:..."로 바뀌었다(fill_signoff_fields 참고 —
        # "직접전달" 체크박스는 이제 별도 필드 t3_020으로 빠졌다). prefix는 그 최신 내용과
        # 정확히 맞아야 "서명:" 뒤 커서 위치가 맞는다.
        prefix = f"성명:   {signee}     서명:"
        # "서명:" 바로 뒤가 아니라 4칸 더 오른쪽으로 띄워서 넣는다(피드백) — "서명:" 뒤에
        # 이미 공백이 14칸 있어 그 안에서 4칸만 더 이동해도 "연락처:" 앞까지 여유가 남는다.
        _insert_at_field_offset(hwp, "t3_008", len(prefix) + 4, report.notify_signature_path)
