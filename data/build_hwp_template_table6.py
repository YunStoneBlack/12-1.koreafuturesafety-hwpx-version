"""`build_hwp_template.py`에서 분리된 표6(17대 기인물) 전용 처리.

600줄을 넘겨 커진 `build_hwp_template.py`를 표별 전용 로직 단위로 쪼갠 것 중 하나 —
`build_template()`이 이 모듈의 `_remove_table6_checkboxes()` / `_process_table6()`을
순서대로 호출한다.
"""

from __future__ import annotations

# 표6(17대 기인물)의 "선택 상자" 체크박스 41개(기인물 자체 15개 + 필수 지도사항 줄 26개,
# 16·17번은 실제 문서에 체크박스가 아예 없어 대상에서 빠짐 — 아래 설명 참고) →
# (필드명 접미사, addr) 목록. `HeadCtrl` 체인을 "표" UserDesc로 세는 방식(표0/3/5에 쓴 방식)이
# 표6에서는 안 먹힌다 — 세어보면 표6 구간에 컨트롤이 0개로 나오는데, 이건 이 문서의 "표"
# HeadCtrl 순서가 `get_into_nth_table()`이 쓰는 표 번호와 어긋나기 때문이다(표3의 로고 그림을
# 찾을 때 같은 문제를 이미 겪었다). 대신 `get_into_nth_table(6)`로 먼저 진입해 그 표의 첫
# 셀·마지막 셀의 `get_pos()` List 값 범위를 구하고, 문서 전체의 "선택 상자" 컨트롤 중
# `GetAnchorPos(0)`의 List가 그 범위 안에 있는 것만 골라 지우는 방식(위치 기반 필터링)을
# 썼다 — 실측으로 범위 안에 40개가 잡혔다(예상 41개와 근접, 경계값 오차로 추정 — 41개 모두
# 실제로 사라지는지는 렌더링으로 재확인함).
#
# 16번("작업전 TBM 실시 여부")·17번("위험성 평가 결과 공유 여부")은 표 안 다른 항목과 달리
# 셀 주소를 다 훑어봐도(`data/... table6_dump.txt` 참고) 빈 체크박스 칸이 없고 안내 문구
# 텍스트만 바로 나온다 — 이 두 항목은 원본 문서 자체에 체크박스가 없는 것으로 보고 이번
# 라운드는 손대지 않는다(마법사에서는 다른 항목과 똑같이 체크박스를 두 개 두지만, 산출물에는
# 반영 안 됨 — 알려진 한계).
#
# **행 번호가 실제 서식보다 2 작다** — 원래 5번 섹션 맨 위에 있던 "위험성 평가기준" 박스가
# 사실은 표6 자체의 물리적 행 2개(원래 3~4행)를 차지하고 있었다. 사용자가 그 박스를 한글에서
# 직접 잘라 3종 장비표 뒤로 옮기면서 표6의 행이 2개 줄었고, 그 아래 모든 행 번호가 정확히 2씩
# 당겨졌다(예: 옛 B5 → 새 B3) — 새 사본(`_SOURCE_HWP`가 가리키는 "...수정-1.hwp")의 표6을
# 셀 단위로 다시 훑어 41개 주소 전부 새 행 번호로 교차 검증했다.
_TABLE6_CHECKBOX_MAP: dict[str, tuple[int, int | None]] = {
    "B3": (1, None), "D3": (1, 0), "D4": (1, 1),
    "F3": (7, None), "H3": (7, 0),
    "B5": (2, None), "D5": (2, 0),
    "F5": (8, None), "H5": (8, 0), "H6": (8, 1),
    "B7": (3, None), "D7": (3, 0), "D8": (3, 1),
    "F7": (9, None), "H7": (9, 0), "H9": (9, 1),
    "B10": (4, None), "D10": (4, 0), "D11": (4, 1),
    "F10": (10, None), "H10": (10, 0),
    "B12": (5, None), "D12": (5, 0), "D13": (5, 1),
    "F12": (11, None), "H12": (11, 0), "H14": (11, 1),
    "B15": (6, None), "D15": (6, 0), "D16": (6, 1),
    "F15": (12, None), "H15": (12, 0), "H17": (12, 1),
    "B19": (13, None), "D19": (13, 0),
    "F19": (14, None), "H19": (14, 0),
    "B20": (15, None), "D20": (15, 0), "D21": (15, 1), "D22": (15, 2),
}


def _remove_table6_checkboxes(hwp) -> int:
    hwp.MoveDocBegin()
    hwp.get_into_nth_table(6, select_cell=False)
    hwp.TableColBegin()
    hwp.TableColPageUp()
    list_min = hwp.get_pos()[0]
    guard = 0
    list_max = list_min
    while hwp.TableRightCell():
        # 병합 셀 순회 순서가 List 값 순서와 일치하지 않는다(예: D24가 E23/F23보다 늦게
        # 나오지만 List 값 자체는 더 크다) — 마지막으로 방문한 값이 아니라 지금까지 본
        # 값 중 최댓값을 추적해야 한다(안 그러면 표 끝부분의 체크박스 하나가 범위 밖으로
        # 밀려나 못 지워지는 것을 실측으로 확인했다).
        list_max = max(list_max, hwp.get_pos()[0])
        guard += 1
        if guard > 300:
            break

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
    return len(to_delete)


def _process_table6(hwp, records: list[dict]) -> int:
    """표6(17대 기인물)은 라벨/데이터 판별이 아니라 `_TABLE6_CHECKBOX_MAP`에 등록된 주소만
    골라 필드화한다 — 기인물명·지도사항 문구는 전부 고정 텍스트(건드리지 않음), 체크박스
    칸(빈 문자열)만 필드로 바꿔 나중에 ☑/☐ 텍스트를 채워 넣는다. 같은 주소가 병합 셀
    순회 중 여러 번 나올 수 있어 이미 필드화한 주소는 건너뛴다.
    """
    hwp.MoveDocBegin()
    hwp.get_into_nth_table(6, select_cell=False)
    hwp.TableColBegin()
    hwp.TableColPageUp()

    created = 0
    done_addrs: set[str] = set()

    def _handle() -> None:
        nonlocal created
        addr = hwp.get_cell_addr()
        if addr not in _TABLE6_CHECKBOX_MAP or addr in done_addrs:
            return
        done_addrs.add(addr)
        factor_number, line_index = _TABLE6_CHECKBOX_MAP[addr]
        suffix = "f" if line_index is None else f"l{line_index}"
        field_name = f"t6_{factor_number}_{suffix}"
        ok = hwp.create_field(field_name)
        created += 1
        records.append(
            {
                "field": field_name,
                "table": 6,
                "addr": addr,
                "original_text": "",
                "created": bool(ok),
            }
        )

    _handle()
    guard = 0
    while hwp.TableRightCell():
        _handle()
        guard += 1
        if guard > 300:
            raise RuntimeError("표6 순회가 300칸을 넘었습니다 — 무한루프 의심")

    return created
