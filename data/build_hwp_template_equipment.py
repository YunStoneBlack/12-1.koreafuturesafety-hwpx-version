"""`build_hwp_template.py`에서 분리된 표7/8/9(건설기계장비·위험기계기구·유해위험물질)
전용 처리(원래 표8/9/10이었다가 위험성평가기준 박스 이동으로 한 칸씩 당겨졌다 — 아래
`_EQUIPMENT_TABLES` 주석 참고).

600줄을 넘겨 커진 `build_hwp_template.py`를 표별 전용 로직 단위로 쪼갠 것 중 하나 —
`build_template()`이 `_EQUIPMENT_TABLES`를 순회하며 이 모듈의 `_process_equipment_table()`을
표마다 호출한다.
"""

from __future__ import annotations

from core.constants import HAND_TOOL_ITEMS, HAZMAT_ITEMS, MACHINERY_EQUIPMENT_ITEMS
from data.hwp_template_common import _normalize

# 표7/8/9(건설기계장비/위험기계기구/유해위험물질) — 전용 처리 대상이라 `build_hwp_template.py`의
# `_SAFE_TABLE_INDEXES`(일반 라벨/데이터 판별 방식)에서 빼고 여기서 따로 처리한다.
#
# **표 번호가 원래 8/9/10이었다가 7/8/9로 한 칸씩 당겨졌다** — 5번 섹션 맨 위의 "위험성
# 평가기준" 박스를 사용자가 한글에서 직접 잘라 이 3종 장비표 뒤로 옮기면서, 표6(17대 기인물)
# 안에 있던 그 박스가 새 독립 표(정확히는 제목 1개 + 본문 1개, 표10/11)로 빠져나갔다 — 그
# 결과 이 3종 장비표는 물러난 자리를 그대로 물려받아 7/8/9가 됐다(`_SOURCE_HWP`가 가리키는
# "...수정-1.hwp" 기준, `build_hwp_template.py`의 소스 파일 주석 참고).
_EQUIPMENT_TABLES: dict[int, list[tuple[str, list[str]]]] = {
    7: MACHINERY_EQUIPMENT_ITEMS,
    8: HAND_TOOL_ITEMS,
    9: HAZMAT_ITEMS,
}


def _process_equipment_table(hwp, table_index: int, records: list[dict]) -> tuple[int, int]:
    """표8/9/10(건설기계장비/위험기계기구/유해위험물질) 공통 처리.

    A열(항목명)·C열(필수지도사항 문구)은 원본 그대로 두고 아예 건드리지 않는다 — 실제 문서의
    쉼표/불릿 표기(괄호 안에 또 쉼표가 있는 문구, "•" 대신 "·" 불릿을 쓰는 표10 등)가
    `core/constants.py` 문자열 재구성과 완전히 일치하지 않아 기존 `_process_table()`의 라벨
    매칭 방식으로는 표9 전체·표10 전체·표8 일부 항목의 지도사항 문구가 통째로 지워지는 것을
    실측으로 확인했다(주소 기반으로 아예 안 건드리는 이 함수로 대체해 원천 차단).

    B열(유/무)은 항목당 1칸(병합 셀), 표5와 같은 "선택 상자" 체크박스 컨트롤이 있어 표6과
    동일한 List-ID 범위 기반으로 지우고 그 자리에 필드(`t{표}_eq{i}_flag`)를 만든다. D열(평가)은
    항목당 물리적으로 여러 칸(지도사항 줄 수만큼, 병합 아님)이고, 마법사도 지도사항 줄마다
    독립된 양호/미흡 버튼을 두므로(항목당 하나로 합쳐 보여줬더니 실제 문서와 달라 보인다는
    피드백으로 되돌림) 줄 번호를 붙인 필드(`t{표}_eq{i}_eval{줄번호}`, 0-based)를 줄마다
    따로 만든다. "해당없음" 행(항목 목록 마지막 다음 행)은 체크박스가 없어 B열 스캔에 안
    잡히고, 그 행의 D칸은 이번 라운드는 손대지 않는다(연동할 마법사 쪽 데이터가 아직 없음).
    """
    items = _EQUIPMENT_TABLES[table_index]
    item_count = len(items)

    def _enter() -> None:
        hwp.MoveDocBegin()
        hwp.get_into_nth_table(table_index, select_cell=False)
        hwp.TableColBegin()
        hwp.TableColPageUp()

    def _read() -> str:
        hwp.TableCellBlock()
        return hwp.get_selected_text(keep_select=False)

    # --- 1차 스캔: List-ID 범위 + 셀 주소/텍스트 수집(읽기 전용) ---
    _enter()
    cells: list[tuple[str, str]] = []
    list_min = hwp.get_pos()[0]
    list_max = list_min
    addr = hwp.get_cell_addr()
    cells.append((addr, _read()))
    guard = 0
    while hwp.TableRightCell():
        list_max = max(list_max, hwp.get_pos()[0])
        addr = hwp.get_cell_addr()
        cells.append((addr, _read()))
        guard += 1
        if guard > 300:
            break

    # B2("유/무" 헤더 라벨)도 주소가 "B"로 시작해 함께 잡히므로 헤더 라벨 텍스트로 제외한다.
    b_rows = list(
        dict.fromkeys(int(a[1:]) for a, t in cells if a[0] == "B" and _normalize(t) != "유/무")
    )
    if len(b_rows) != item_count:
        raise RuntimeError(
            f"표{table_index}: 유/무 체크박스 {len(b_rows)}개 발견, 예상 항목 수 {item_count}개와 다릅니다"
        )
    special_rows = [int(a[1:]) for a, t in cells if a[0] == "A" and _normalize(t) == "해당없음"]
    upper_bound = special_rows[0] if special_rows else 10**6

    def _item_index_for_row(row: int) -> int | None:
        idx = None
        for i, b_row in enumerate(b_rows):
            if row >= b_row:
                idx = i
            else:
                break
        if idx is None or row >= upper_bound:
            return None
        return idx

    # --- 2차: 유/무 체크박스 컨트롤 제거(표6과 동일한 List-ID 범위 기반 필터링) ---
    hwp.MoveDocBegin()
    ctrl = hwp.HeadCtrl
    to_delete = []
    while ctrl:
        if ctrl.UserDesc == "선택 상자":
            anchor = ctrl.GetAnchorPos(0)
            lst = anchor.Item("List")
            if list_min <= lst <= list_max:
                to_delete.append(ctrl)
        ctrl = ctrl.Next
    for c in to_delete:
        hwp.delete_ctrl(c)
    removed = len(to_delete)

    # --- 3차: B/D열만 지우고 필드 생성 ---
    created = 0
    done_b: set[str] = set()

    def _clear_current() -> None:
        guard2 = 0
        while _read():
            hwp.HAction.Run("MoveSelLineBegin")
            hwp.HAction.Run("MoveSelLineEnd")
            hwp.HAction.Run("Delete")
            guard2 += 1
            if guard2 > 20:
                break

    def _handle() -> None:
        nonlocal created
        addr = hwp.get_cell_addr()
        col = addr[0]
        row = int(addr[1:])
        if addr == "A2":
            # 표 안 소제목 칸(예: "위험기계기구"). 원본 문서는 표8(건설기계장비)에도 표9와
            # 똑같이 "위험기계기구"라고 적혀있는 오기(誤記)가 있어 — 라벨 매칭으로는 걸러지지
            # 않으므로(정상적인 라벨 텍스트라 static_labels에 그대로 존재) 항상 필드화해서
            # `fill_equipment_section_titles()`가 표마다 맞는 이름으로 다시 채우게 한다.
            _clear_current()
            field_name = f"t{table_index}_category"
            ok = hwp.create_field(field_name)
            created += 1
            records.append({"field": field_name, "table": table_index, "addr": addr, "created": bool(ok)})
        elif col == "B":
            if addr in done_b:
                return
            done_b.add(addr)
            item_i = _item_index_for_row(row)
            if item_i is None:
                return
            _clear_current()
            field_name = f"t{table_index}_eq{item_i}_flag"
            ok = hwp.create_field(field_name)
            created += 1
            records.append({"field": field_name, "table": table_index, "addr": addr, "created": bool(ok)})
        elif col == "D":
            item_i = _item_index_for_row(row)
            if item_i is None:
                return
            line_i = row - b_rows[item_i]
            _clear_current()
            field_name = f"t{table_index}_eq{item_i}_eval{line_i}"
            ok = hwp.create_field(field_name)
            created += 1
            records.append({"field": field_name, "table": table_index, "addr": addr, "created": bool(ok)})

    _enter()
    _handle()
    guard = 0
    while hwp.TableRightCell():
        _handle()
        guard += 1
        if guard > 300:
            raise RuntimeError(f"표{table_index} 순회가 300칸을 넘었습니다 — 무한루프 의심")

    return removed, created
