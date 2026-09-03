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
