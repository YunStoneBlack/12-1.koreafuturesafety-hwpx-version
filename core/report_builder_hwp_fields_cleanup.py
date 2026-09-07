""""해당사항없음" 표/제목 정리 + 빈 페이지 정리 — `report_builder_hwp_fields.py`에서 분리됨
(875줄을 넘겨 이 프로젝트 관례상 600줄 기준으로 나눴다, 2026-09-08).

`remove_na_sections()`가 마법사에서 "해당사항없음"으로 체크된 섹션의 표/제목 문단을 지우고,
`_remove_blank_pages()`가 그 결과로 생긴 빈 페이지를 정리한다. 반드시 각 표를 채우는
`fill_*` 함수보다 먼저 호출해야 한다 — 표를 지우면 그 안의 필드도 같이 사라지므로, 지울
표는 미리 지우고 남은 표만 채우는 게 안전하다.
"""

from __future__ import annotations

from core.models_db import Report
from core.report_builder_hwp_fields import _put


def _find_table_ctrl_by_field(hwp, verify_field: str, max_hops: int = 60):
    """`verify_field`가 들어있는 표 컨트롤(gso) 자체를 찾는다 — 표1~16처럼 번호가 매겨진
    일반(문서 흐름에 얹힌) 표도 `get_into_nth_table()`로 들어간 캐럿만으로는 표 컨트롤
    객체 자체(삭제 대상)를 못 얻는다. 문서 전체의 "표" 컨트롤을 훑으며 각 컨트롤의 앵커
    위치에서 안으로 들어가(MoveRight) 물리 셀을 순서대로 밟다가, `verify_field`란 이름의
    필드가 나오는 컨트롤을 찾으면 그 컨트롤을 반환한다.
    """
    for ctrl in hwp.ctrl_list:
        if ctrl.UserDesc != "표":
            continue
        try:
            hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
            hwp.HAction.Run("MoveRight")
            if not hwp.is_cell():
                continue
            if hwp.get_cur_field_name() == verify_field:
                return ctrl
            for _ in range(max_hops):
                if not hwp.HAction.Run("TableRightCell"):
                    break
                if hwp.get_cur_field_name() == verify_field:
                    return ctrl
        except Exception:
            continue
    return None


def _delete_paragraph_containing(hwp, text: str) -> bool:
    """`text`가 들어있는 문단 전체(문단 부호 포함)를 지운다 — 표 밖의 독립된 섹션 제목
    문단을 지울 때 쓴다.

    예전엔 이 문단을 지운 뒤 남는 빈 문단을 "실제 내용이 나올 때까지" 계속 마저 지우는
    반복 루프가 있었는데, 그 판정이 텍스트 유무만 봐서(`get_selected_text().strip()`)
    다음에 오는 표(예: 12대 기인물 표처럼 붕 떠있는/앵커된 표)의 앵커 문자를 "빈 문단"으로
    잘못 읽고 함께 지워버려 표 전체가 통째로 사라지는 사고가 실측으로 확인됐다. 그래서
    제목 문단 하나만 지우고 멈춘다 — 남는 빈 페이지 정리는 `_remove_blank_pages`가
    (실제 내용을 건드리지 않는지 매번 확인하면서) 별도로 맡는다.
    """
    hwp.MoveDocBegin()
    if not hwp.find(text):
        return False
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelParaBegin")
    hwp.HAction.Run("MoveSelNextParaBegin")
    hwp.HAction.Run("Delete")
    return True


_COLLAPSE_ROW_HEIGHT_MM = 2.0


def _collapse_row_at(hwp, field: str) -> None:
    if not hwp.field_exist(field):
        return
    hwp.move_to_field(field, text=True, start=True, select=False)
    hwp.TableCellBlockRow()
    pset = hwp.hwp.HParameterSet.HShapeObject
    hwp.hwp.HAction.GetDefault("TablePropertyDialog", pset.HSet)
    pset.HSet.SetItem("ShapeType", 3)
    pset.HSet.SetItem("ShapeCellSize", 1)
    pset.ShapeTableCell.Height = hwp.hwp.MiliToHwpUnit(_COLLAPSE_ROW_HEIGHT_MM)
    hwp.hwp.HAction.Execute("TablePropertyDialog", pset.HSet)
    hwp.Cancel()
    _put(hwp, field, "")


def _collapse_table_rows(hwp, row_start_fields: list[str]) -> None:
    """표를 지우는 대신, 알려진 행 시작 필드들이 있는 행(+맨 위 헤더 행) 전부를 눈에 안
    띄는 높이(2mm)로 접는다 — 표12/표15는 `delete_ctrl`이 성공(True)을 돌려주는데도 실제로는
    안 지워지는 걸 실측으로 확인했다(사용자가 한글에서 직접 재구성한 표라 뭔가 보호 속성이
    남아있는 것으로 추정 — 정확한 원인은 못 찾음). 완전히 사라지진 않지만 실질적으로 안
    보이는 수준까지는 줄어든다. `data/build_hwp_template_layout_fixes.py`의
    `_set_process_table_row_heights`(45mm로 키우는 것)와 반대 방향으로 같은 기법을 쓴다.
    """
    if row_start_fields and hwp.field_exist(row_start_fields[0]):
        hwp.move_to_field(row_start_fields[0], text=True, start=True, select=False)
        hwp.HAction.Run("TableColBegin")
        hwp.HAction.Run("TableColPageUp")
        hwp.TableCellBlockRow()
        pset = hwp.hwp.HParameterSet.HShapeObject
        hwp.hwp.HAction.GetDefault("TablePropertyDialog", pset.HSet)
        pset.HSet.SetItem("ShapeType", 3)
        pset.HSet.SetItem("ShapeCellSize", 1)
        pset.ShapeTableCell.Height = hwp.hwp.MiliToHwpUnit(_COLLAPSE_ROW_HEIGHT_MM)
        hwp.hwp.HAction.Execute("TablePropertyDialog", pset.HSet)
        hwp.Cancel()
    for field in row_start_fields:
        _collapse_row_at(hwp, field)


def remove_na_sections(hwp, report: Report) -> None:
    """마법사에서 "해당사항없음"으로 체크한 섹션은 보고서에 표 자체가 안 보이게 지운다.

    반드시 각 표를 채우는 `fill_*` 함수보다 먼저 호출해야 한다 — 표를 지우면 그 안의
    필드도 같이 사라지므로, 지울 표는 미리 지우고 남은 표만 채우는 게 안전하다.

    표마다 제목이 표 안(A1 등)에 포함된 것도 있고(표6 12대기인물, 표7/8/9 장비) 표 밖의
    독립된 문단인 것도 있다(표5 대형사고위험작업, 표12 현재진행공정, 표14/15 향후진행공정)
    — 직접 하나씩 실측해서 확인한 결과이며, 표 밖 제목은 표를 지워도 안 없어지므로 따로
    지워야 한다.
    """
    if report.previous_findings_na:
        # 표 삭제는 `remove_unused_previous_finding_blocks()`(슬롯당 독립된 표4~7, 2026-09-07
        # 재구성)가 맡는다 — `fill_all()`에서 이 함수보다 나중에 호출되므로, 여기선 제목
        # 문단만 지운다.
        _delete_paragraph_containing(hwp, "이전 기술지도 사항 이행여부")

    if report.major_hazard_na:
        ctrl = _find_table_ctrl_by_field(hwp, "t5_001")
        if ctrl:
            hwp.delete_ctrl(ctrl)
        _delete_paragraph_containing(hwp, "대형사고 위험작업 사항")

    if report.hazard_factors_na:
        # 표6(12대 기인물)은 삭제를 시도해도 실제로는 안 지워진다(원인 미상, 사용자가
        # 직접 재구성한 표 — 실측 확인). 구조가 복잡해(항목 17개×줄마다 다른 필드) 표12/15
        # 처럼 행 단위로 접는 것도 위험 부담이 커서, 이번엔 손대지 않고 그대로 둔다 — 표는
        # 남지만 `fill_hazard_factor_fields`가 체크 항목 없이 전부 빈 칸(☐)으로 채운다.
        pass

    if report.equipment_checks_na:
        for field in ("t7_category", "t8_category", "t9_category"):
            ctrl = _find_table_ctrl_by_field(hwp, field)
            if ctrl:
                hwp.delete_ctrl(ctrl)

    if report.current_process_na:
        ctrl = _find_table_ctrl_by_field(hwp, "t12_001")
        if ctrl and hwp.field_exist("t12_001"):
            # delete_ctrl이 성공을 반환해도 실제로 안 지워지는 경우가 있어(표12/15와 같은
            # 원인), 지운 뒤 필드가 정말 사라졌는지 확인하고 안 사라졌으면 행 접기로 대체한다.
            hwp.delete_ctrl(ctrl)
        if hwp.field_exist("t12_001"):
            _collapse_table_rows(hwp, ["t12_001", "t12_005", "t12_009", "t12_013"])
        _delete_paragraph_containing(hwp, "현재 진행공정에 대한 유해")

    if report.process_na:
        for field in ("t14_001", "t15_001"):
            ctrl = _find_table_ctrl_by_field(hwp, field)
            if ctrl and hwp.field_exist(field):
                hwp.delete_ctrl(ctrl)
        if hwp.field_exist("t15_001"):
            _collapse_table_rows(hwp, ["t15_001", "t15_005", "t15_009", "t15_013"])
        _delete_paragraph_containing(hwp, "향후 진행공정에 대한 유해")

    _remove_blank_pages(hwp)


def _remove_blank_pages(hwp, max_pages_to_check=40) -> None:
    """표/제목 삭제 뒤 페이지 사이에 남는 빈 페이지를 지운다.

    `_delete_paragraph_containing`의 문단 정리만으로는 빈 페이지가 안 없어지는 경우가
    실측으로 확인됐다(표 필드는 확실히 지워졌는데도 빈 페이지 자체는 남음) — 사용자가
    조판부호를 켜고 빈 페이지 위치에 커서를 둔 채 Delete 키를 선택 없이 그냥 눌러서
    페이지가 사라지는 걸 직접 확인해줬다. `is_empty_page()`로 실제 빈 페이지만 골라
    그 위치에서 같은 동작(선택 없는 Delete)을 한다. 이 시점(remove_na_sections 안)엔 아직
    어떤 이미지도 안 붙어있어서(서명·사진·제공자료 이미지는 fill_all 이후 단계에서 붙는다),
    이미지만 있고 글자는 없는 페이지를 빈 페이지로 잘못 지울 위험이 없다.

    같은 페이지에서 Delete를 두 번째 누르면(첫 번째로 안 지워지고 남은 경우) 근처에 있는
    복잡한 개체(예: 12대 기인물 표, 사용자가 직접 재구성한 표)의 확인 대화상자가 뜨면서
    자동화가 멈추는 경우가 실측으로 확인됐다(SetMessageBoxMode로도 못 막음) — 그래서 페이지당
    Delete는 딱 한 번만 시도하고, 그걸로도 안 없어지면 그 페이지는 포기하고 다음으로 넘어간다.
    """
    checked_pages: set[int] = set()
    for _ in range(max_pages_to_check):
        total = hwp.PageCount
        blank_page = None
        for page in range(1, total + 1):
            if page in checked_pages:
                continue
            hwp.goto_page(page)
            if hwp.is_empty_page():
                blank_page = page
                break
        if blank_page is None:
            return

        hwp.goto_page(blank_page)
        hwp.HAction.Run("MoveParaBegin")
        start_offset = hwp.hwp.GetPos()[2]
        hwp.HAction.Run("MoveSelParaBegin")
        hwp.HAction.Run("MoveSelParaEnd")
        para_text = hwp.get_selected_text(keep_select=False)
        end_offset = hwp.hwp.GetPos()[2]
        # 글자가 하나도 없어 보여도(get_selected_text가 빈 문자열이어도) 문단 안에 앵커된
        # 개체(표 등)의 앵커 문자가 있으면 커서 이동만으로 위치가 0에서 안 움직인다 — 그런
        # 경우까지 "빈 문단"으로 오판해서 지우면 그 개체 전체가 통째로 사라진다(실측으로
        # 확인된 사고: 12대 기인물 표가 이 문단 정리 때문에 사라짐). 문단 길이가 0일 때만
        # 진짜 빈 문단으로 보고 지운다.
        if para_text.strip() or end_offset != start_offset:
            checked_pages.add(blank_page)
            continue
        hwp.Cancel()
        hwp.HAction.Run("Delete")
        if hwp.PageCount >= total:
            # 페이지가 안 줄었으면 이 Delete는 아무 효과 없이 바로 뒤 문단(예: "5. 필수
            # 지도 확인 사항"의 "5.")의 서식만 깨뜨리는 부작용만 남긴 경우가 실측으로
            # 확인됐다 — 효과가 없었으면 무조건 되돌린다.
            hwp.HAction.Run("Undo")
            checked_pages.add(blank_page)
