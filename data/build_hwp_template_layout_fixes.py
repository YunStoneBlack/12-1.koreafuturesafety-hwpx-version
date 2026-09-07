"""표16(사업장 지원 사항)/표12·15(진행공정 상세표)/지적사항 표 후처리 — `_process_table()`의
일반 라벨/데이터 판별 루프로는 못 잡는 항목들을 `build_hwp_template.py`에서 분리했다:

1. `_add_education_location_field`: 표16 F2(교육장소 값)가 원래 샘플 값("현장")이 문서
   다른 곳의 공통 정적 라벨과 우연히 겹쳐 필드화가 안 됐던 자리.
2. `_set_process_table_row_heights`: 표12/15 항목행이 "-3" 소스 문서의 긴 샘플 문구에
   맞춰진 높이(140.68mm)를 그대로 물려받아 실제 짧은 내용으로는 표 안이 휑하게 비었던 것.
3. `_convert_equipment_pass_fail_checkboxes`: 표16 장비사용(1)/(2)의 "☑양호/☐불량"이
   HWP 체크박스 폼 컨트롤이라 코드로 체크 상태를 못 바꾸는(`build_hwp_template.py` 모듈
   docstring 참고) 문제 — 컨트롤을 지우고 텍스트 필드로 대체한다.
4. `_add_finding_result_fields`: 지적사항 표(1~4번)의 "이행결과" 칸이 완전히 빈 칸이라
   필드 자체가 없던 것 — `finding{slot}_result` 필드를 새로 만든다.

`build_hwp_template.build_template()`이 메인 필드 생성 루프를 마친 뒤 이 함수들을
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


def _add_finding_result_fields(hwp) -> None:
    """지적사항 표(1~4번, 문서 흐름 밖 독립 표)의 "이행결과" 칸에 `finding{slot}_result`
    필드를 만든다.

    이 칸은 원본 문서에서 완전히 빈 칸(라벨도 내용도 없음)이라 다른 칸들과 달리
    `_process_table()`은 물론 finding{slot}_* 필드 생성 로직에서도 인식할 실마리가 없어
    빠져 있었다(체크박스 컨트롤도 없음 — 실측으로 확인: 이 칸의 list_id에 대응하는
    "선택 상자" 컨트롤이 문서 전체에 없음). `finding{slot}_hazard` 필드 위치에서
    `TableRightCell`을 6번 이동하면 이 칸(이행결과 값 칸)에 도착한다(실측 확인: hazard →
    지적사항 재해예방 대책 라벨 → 위험성 수준 라벨 → 이행결과 라벨 → countermeasure →
    risk → 이행결과 값 칸).
    """
    for slot in (1, 2, 3, 4):
        hazard_field = f"finding{slot}_hazard"
        if not hwp.field_exist(hazard_field):
            continue
        result_field = f"finding{slot}_result"
        if hwp.field_exist(result_field):
            continue
        hwp.move_to_field(hazard_field, text=True, start=True, select=False)
        for _ in range(6):
            hwp.HAction.Run("TableRightCell")
        hwp.create_field(result_field)


_PREVIOUS_FINDING_RESULT_TABLES = {1: 4, 2: 5, 3: 6, 4: 7}


def _add_previous_finding_result_fields(hwp) -> None:
    """이전지적사항 표(2026-09-07 재구성 — 슬롯당 독립된 번호표 4개, 표4~7)의 "이행결과"
    칸(G5, "위험성 수준"과 짝을 이루는 큰 칸 — G4가 "이행결과" 라벨, G5가 그 값 칸으로
    A5~F8 "위험성 수준" 블록과 같은 세로 범위에 걸쳐 있다)에 `previous_finding{slot}_result`
    필드를 만든다.

    사용자가 한글에서 표4(구 "표4/표13" 통합본)를 슬롯당 표 하나로 완전히 새로 짰다 —
    표 A1="전 회차 지적사항"(사진+내용), G1="이행 결과" 라벨. A2=원본 지적사항 사진,
    A3=제목(유해위험요인), G2=이행완료 증빙 사진, G3=재해예방 대책 내용
    (`_add_previous_finding_content_fields` 참고). A4="위험성 수준"/G4="이행결과" 라벨 +
    그 아래 값 칸들. "위험성 수준"(이행 전/이행 후 각각 가능성·중대성·위험성)은 아직
    미정(사용자가 나중에 설명 예정이라 손대지 않음). "이행결과" 값은 마법사에서 고른
    상태(확인불가/보완필요/이행완료)를 "☑/☐" 세 줄 텍스트로 표현할 계획이라(체크박스 폼
    컨트롤은 코드로 상태를 못 바꾸는 문서 전체 공통 한계), G5에 필드를 만들어둔다.
    """
    for slot, table_index in _PREVIOUS_FINDING_RESULT_TABLES.items():
        field_name = f"previous_finding{slot}_result"
        if hwp.field_exist(field_name):
            continue
        if not _goto_table_cell(hwp, table_index, "G5"):
            continue
        hwp.create_field(field_name)


def _add_previous_finding_content_fields(hwp) -> None:
    """이전지적사항 표(표4~7)의 A3(제목)/G3(내용) 칸에 `previous_finding{slot}_title`/
    `previous_finding{slot}_content` 필드를 만든다.

    A2(원본 사진)/G2(이행완료 증빙 사진)는 텍스트 필드가 아니라 이미지 삽입 대상이라
    여기서 다루지 않는다 — `report_builder_hwp_images.py`가 A3/G3 필드를 기준점 삼아
    (`MoveUp`으로 한 칸 위로 이동) 사진을 넣는다(표 삭제로 순서 번호가 밀려도 안전하도록
    `get_into_nth_table()` 대신 필드 기준 상대 이동을 쓴다 — `TableUpCell`은 이 표에서
    안 먹혀서 `MoveUp`으로 확인함).
    """
    for slot, table_index in _PREVIOUS_FINDING_RESULT_TABLES.items():
        for field_name, addr in (
            (f"previous_finding{slot}_title", "A3"),
            (f"previous_finding{slot}_content", "G3"),
        ):
            if hwp.field_exist(field_name):
                continue
            if not _goto_table_cell(hwp, table_index, addr):
                continue
            hwp.create_field(field_name)


def _remove_previous_finding_bullets(hwp) -> None:
    """이전지적사항 표(표4~7)의 G2(이행완료 사진 칸)에 남아있던 글머리표(HeadingType=3,
    "■")를 지운다.

    실측 확인: A2(원본 사진 칸)는 글머리표가 없지만 G2에는 원본 문서의 글머리표 문단
    서식이 남아있었다(문단에 실제 텍스트가 있든 없든 상관없이 문단 모양 자체에 붙어있는
    서식이라 `get_selected_text()`로는 안 잡히고 `get_heading_string()`으로만 확인됨) —
    사진이 없는 슬롯에서 G2에 글머리표만 덩그러니 보이는 문제를 없앤다.

    A3(제목)/G3(내용)의 글머리표는 그대로 둔다 — 처음엔 이것도 같이 지웠는데, 실제
    텍스트 앞의 "■"는 이 문서 전체의 지적사항류 항목에 공통으로 쓰이는 정상적인 스타일이라
    사용자가 되살려 달라고 정정함(2026-09-07).
    """
    for slot, table_index in _PREVIOUS_FINDING_RESULT_TABLES.items():
        field_name = f"previous_finding{slot}_content"
        if not hwp.field_exist(field_name):
            continue
        hwp.move_to_field(field_name, text=True, start=True, select=False)
        hwp.HAction.Run("MoveUp")  # G3 -> G2
        if not hwp.get_heading_string():
            continue
        pset = hwp.hwp.HParameterSet.HParaShape
        hwp.hwp.HAction.GetDefault("ParagraphShape", pset.HSet)
        pset.HeadingType = 0
        hwp.hwp.HAction.Execute("ParagraphShape", pset.HSet)
