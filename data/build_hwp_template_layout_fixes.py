"""표16(사업장 지원 사항)/표12·15(진행공정 상세표) 후처리 — `_process_table()`의 일반
라벨/데이터 판별 루프로는 못 잡는 세 가지를 `build_hwp_template.py`에서 분리했다:

1. `_add_education_location_field`: 표16 F2(교육장소 값)가 원래 샘플 값("현장")이 문서
   다른 곳의 공통 정적 라벨과 우연히 겹쳐 필드화가 안 됐던 자리.
2. `_set_process_table_row_heights`: 표12/15 항목행이 "-3" 소스 문서의 긴 샘플 문구에
   맞춰진 높이(140.68mm)를 그대로 물려받아 실제 짧은 내용으로는 표 안이 휑하게 비었던 것.
3. `_convert_equipment_pass_fail_checkboxes`: 표16 장비사용(1)/(2)의 "☑양호/☐불량"이
   HWP 체크박스 폼 컨트롤이라 코드로 체크 상태를 못 바꾸는(`build_hwp_template.py` 모듈
   docstring 참고) 문제 — 컨트롤을 지우고 텍스트 필드로 대체한다.

`build_hwp_template.build_template()`이 메인 필드 생성 루프를 마친 뒤 이 세 함수를
순서대로 호출한다.
"""

from __future__ import annotations


def _goto_table_cell(hwp, table_index: int, addr: str) -> bool:
    """표의 A1부터 오른쪽으로 훑어 지정된 셀 주소까지 캐럿을 이동시킨다."""
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
    return True


def _add_education_location_field(hwp) -> None:
    """표16 F2(교육장소 값 칸)에 `t16_edu_location` 필드를 만든다.

    이 칸의 원본 샘플 값("현장")이 문서 다른 곳의 공통 정적 라벨과 우연히 겹쳐
    `_process_table()`이 "라벨"로 오인해 건너뛴 자리다 — `t16_003`("○ 교육장소 :" 라벨)
    바로 오른쪽 칸이라 그 필드로 이동한 뒤 한 칸 우측으로 이동해 처리한다.
    """
    if not hwp.field_exist("t16_003"):
        return
    hwp.move_to_field("t16_003", text=True, start=True, select=False)
    hwp.HAction.Run("TableRightCell")
    if hwp.get_cell_addr() != "F2":
        return

    def _read_cell_text() -> str:
        hwp.TableCellBlock()
        return hwp.get_selected_text(keep_select=False)

    guard = 0
    while _read_cell_text():
        hwp.HAction.Run("MoveSelLineBegin")
        hwp.HAction.Run("MoveSelLineEnd")
        hwp.HAction.Run("Delete")
        guard += 1
        if guard > 200:
            break
    hwp.create_field("t16_edu_location")


_PROCESS_TABLE_ROW_FIELDS = [
    "t12_001", "t12_005", "t12_009", "t12_013",
    "t15_001", "t15_005", "t15_009", "t15_013",
]
_PROCESS_TABLE_ROW_HEIGHT_MM = 45.0


def _set_process_table_row_heights(hwp) -> None:
    """표12/표15(6번·8번 진행공정 상세표)의 4개 항목행 높이를 45mm로 낮춘다.

    "-3" 소스 문서에서 이 행들을 복사해 만들 때 원본의 긴 샘플 문구에 맞춰진 높이
    (140.68mm)가 그대로 딸려와, 실제 보고서의 짧은 내용으로는 표 안이 휑하게 비어 보였다
    (사용자 피드백). 45mm는 최솟값일 뿐이라 이보다 긴 내용은 자동으로 더 늘어난다(실측
    확인: 6줄짜리 긴 문구를 넣어도 잘리지 않고 행이 늘어남). `set_row_height()`는 캐럿이
    셀 안에 있기만 해서는 적용되지 않고 `TableCellBlockRow()`로 행 전체를 블록 선택한
    뒤에야 적용된다(pyhwpx의 `set_col_width()`가 컬럼에 대해 하는 것과 동일한 패턴).
    """
    for name in _PROCESS_TABLE_ROW_FIELDS:
        if not hwp.field_exist(name):
            continue
        hwp.move_to_field(name, text=True, start=True, select=False)
        hwp.TableCellBlockRow()
        pset = hwp.hwp.HParameterSet.HShapeObject
        hwp.hwp.HAction.GetDefault("TablePropertyDialog", pset.HSet)
        pset.HSet.SetItem("ShapeType", 3)
        pset.HSet.SetItem("ShapeCellSize", 1)
        pset.ShapeTableCell.Height = hwp.hwp.MiliToHwpUnit(_PROCESS_TABLE_ROW_HEIGHT_MM)
        hwp.hwp.HAction.Execute("TablePropertyDialog", pset.HSet)
        hwp.Cancel()


_EQUIPMENT_PASS_FAIL_CELLS = {
    "t16_pass1": "H5",
    "t16_fail1": "H6",
    "t16_pass2": "H9",
    "t16_fail2": "H10",
}


def _convert_equipment_pass_fail_checkboxes(hwp) -> None:
    """표16 장비사용(1)/(2)의 "☑양호"/"☐불량" 체크박스(H5/H6/H9/H10)를 데이터로 채울 수
    있는 텍스트 필드로 바꾼다.

    HWP 체크박스 폼 컨트롤("선택 상자")은 체크 상태를 코드로 바꾸는 방법을 찾지 못해
    (`build_hwp_template.py` 모듈 docstring 참고 — 표5/6/8~10과 동일하게 문서화된 한계),
    컨트롤을 지우고 "☑양호"/"☐불량" 같은 고정 텍스트를 담는 필드로 대체하는 이 문서 전체의
    공통 해법을 여기도 그대로 적용한다. 지금까지 이 두 칸은 원본 실제 고객사 문서의 체크
    상태(항상 "양호"가 체크됨)가 그대로 남아있어 데이터와 무관하게 항상 "양호"로 보였다.
    """
    for field_name, addr in _EQUIPMENT_PASS_FAIL_CELLS.items():
        if not _goto_table_cell(hwp, 16, addr):
            continue
        list_id = hwp.get_pos()[0]
        for ctrl in hwp.ctrl_list:
            if ctrl.UserDesc != "선택 상자":
                continue
            try:
                hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
            except Exception:
                continue
            if hwp.get_pos()[0] == list_id:
                hwp.delete_ctrl(ctrl)

        if not _goto_table_cell(hwp, 16, addr):
            continue
        hwp.create_field(field_name)
