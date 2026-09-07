"""7번(지적사항)/3번(이전지적사항) 표 채우기 — `report_builder_hwp_fields.py`에서 분리됨
(875줄을 넘겨 이 프로젝트 관례상 600줄 기준으로 나눴다, 2026-09-08).

**7번 지적사항(finding{slot}_*)**: 표1~16 번호 체계 밖의 독립된(문서 흐름에 얹힌) 표라
`get_into_nth_table()`로 못 찾는다 — `_find_finding_table_ctrl()`이 앵커 위치 기준으로
직접 찾는다. 데이터 없는 슬롯의 표는 `remove_unused_finding_blocks()`가 미리 지운다.

**3번 이전지적사항(previous_finding{slot}_*)**: 2026-09-07에 슬롯당 독립된 번호표 4개
(표4~7)로 재구성됐다 — 표1~19 번호 체계 안의 일반 표라 `_find_table_ctrl_by_field()`
(`report_builder_hwp_fields.py`)로 찾는다. 제목(A3)/내용(G3)은
`PreviousFinding.display_fields()`로 가져온다 — 직전 회차에서 이월된 경우(source_finding_id
있음) 원본 지적사항이 그 사이 수정됐을 수 있어 항상 최신 값을 반영한다(마법사와 동일한
실시간 동기화 원칙). 사진(A2 원본/G2 이행완료 증빙)은 텍스트 필드가 아니라
`report_builder_hwp_images.fill_previous_finding_images()`가 맡는다. "위험성 수준"(이행
전/후 각각 가능성·중대성·위험성)은 아직 미정이라 손대지 않는다.

두 섹션 다 "이행결과" 칸은 실제 체크박스 폼 컨트롤을 코드로 못 바꾸는 문서 전체 공통
한계 때문에 "☑/☐" 텍스트로 표현한다(7번은 추후확인/즉시이행 두 줄, 3번은
확인불가/보완필요/이행완료 세 줄).
"""

from __future__ import annotations

from core.models_db import Report
from core.report_builder_hwp_fields import _put
from core.report_builder_hwp_fields_cleanup import _find_table_ctrl_by_field

_FINDING_RISK_BANDS = [
    (1, 3, "하", "현상\n유지", (134, 239, 172)),  # 연두색(사용자 요청)
    (4, 5, "중", "개선\n필요", (251, 146, 60)),
    (6, 9, "상", "즉시\n개선", (248, 113, 113)),
]


def _finding_risk_band(score: int) -> tuple[str, str, tuple[int, int, int] | None]:
    for lo, hi, grade, label, color in _FINDING_RISK_BANDS:
        if lo <= score <= hi:
            return grade, label, color
    return "", "", None


def _fill_finding_risk(hwp, slot: int, finding) -> None:
    """지적사항 위험성 수준 표(가능성/중대성/위험성 값 + 등급/관리기준 라벨)를 채운다.

    사용자가 한글에서 직접 일반 표 칸으로 재구성해서(원래는 중첩 표라 표6과 같은 한계로
    코드로 못 건드렸다), 각 칸(가능성/중대성/위험성 값, 등급, 관리기준)이 전부 독립된
    필드다. 관리기준 칸(`finding{slot}_action`)에만 등급별 배경색(즉시개선=빨강/
    개선필요=주황/현상유지=연두)을 `hwp.cell_fill()`로 입힌다.
    """
    likelihood_field = f"finding{slot}_likelihood"
    severity_field = f"finding{slot}_severity"
    score_field = f"finding{slot}_score"
    grade_field = f"finding{slot}_grade"
    action_field = f"finding{slot}_action"

    if not finding or finding.likelihood is None or finding.severity is None:
        _put(hwp, likelihood_field, "")
        _put(hwp, severity_field, "")
        _put(hwp, score_field, "")
        _put(hwp, grade_field, "")
        _put(hwp, action_field, "")
        return

    score = finding.likelihood * finding.severity
    grade, label, color = _finding_risk_band(score)
    _put(hwp, likelihood_field, str(finding.likelihood))
    _put(hwp, severity_field, str(finding.severity))
    _put(hwp, score_field, str(score))
    _put(hwp, grade_field, grade)
    _put(hwp, action_field, label)
    if color and hwp.field_exist(action_field):
        hwp.move_to_field(action_field, text=True, start=True, select=False)
        hwp.TableCellBlock()
        hwp.cell_fill(color)


def _find_finding_table_ctrl(hwp, slot: int):
    """`finding{slot}_hazard` 필드가 들어있는 표 컨트롤(gso) 자체를 찾는다.

    지적사항 표는 문서 흐름에 얹힌 독립된(떠다니는) 표라 `get_into_nth_table()`로는 못 찾고
    (표1~16 번호 체계 밖), `create_field()`가 만든 필드도 표 전체가 아니라 그 안의 칸
    하나만 가리킨다. 그래서 문서 전체의 "표" 컨트롤을 훑으면서, 각 컨트롤의 앵커 위치로
    이동해본 뒤 그 표 안쪽으로 두 칸 이동했을 때의 필드 이름이 정확히 이 슬롯의 것과
    일치하는 컨트롤만 골라낸다(표1의 "유해위험요인" 배너 텍스트가 모든 지적사항 표에서
    똑같아 텍스트만으로는 구분이 안 됨).
    """
    target_field = f"finding{slot}_hazard"
    for ctrl in hwp.ctrl_list:
        if ctrl.UserDesc != "표":
            continue
        try:
            hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
            hwp.HAction.Run("MoveRight")
            if not hwp.is_cell():
                continue
            hwp.HAction.Run("TableRightCell")
            hwp.HAction.Run("TableRightCell")
            if hwp.get_cur_field_name() == target_field:
                return ctrl
        except Exception:
            continue
    return None


def remove_unused_finding_blocks(hwp, report: Report) -> None:
    """데이터가 없는 지적사항 슬롯의 표 전체를 문서에서 지운다 — 지적사항이 1건뿐이면
    2번 지적사항 표(사진 없이 빈 칸만 있는 블록)가 보고서에 통째로 안 보이게 하기 위함.
    반드시 `fill_finding_fields`/`fill_finding_images`보다 먼저 호출해야 한다 — 표를 지우면
    그 안의 필드도 같이 사라지므로, 남은 슬롯만 채우는 게 안전하다.

    템플릿에 지적사항 표 1~4번이 모두 있다(마법사가 지원하는 최대 슬롯 수와 동일).
    """
    findings_by_slot = {} if report.findings_na else {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        if slot in findings_by_slot:
            continue
        if not hwp.field_exist(f"finding{slot}_hazard"):
            continue
        ctrl = _find_finding_table_ctrl(hwp, slot)
        if ctrl:
            hwp.delete_ctrl(ctrl)


def remove_unused_previous_finding_blocks(hwp, report: Report) -> None:
    """데이터가 없는 이전지적사항 슬롯의 표 전체를 지운다(2026-09-07 재구성 — 슬롯당 독립된
    번호표 4개, 표4~7 — `finding{slot}` 표와 달리 표1~19 번호 체계 안의 일반 표라
    `_find_table_ctrl_by_field()`로 찾는다). `previous_findings_na` 체크 시 4개 전부,
    아니면 실제 데이터 없는 슬롯만 지운다. 반드시 `fill_previous_finding_fields`보다 먼저
    호출해야 한다.
    """
    previous_by_slot = {} if report.previous_findings_na else {p.slot: p for p in report.previous_findings}
    for slot in (1, 2, 3, 4):
        if slot in previous_by_slot:
            continue
        if not hwp.field_exist(f"previous_finding{slot}_result"):
            continue
        ctrl = _find_table_ctrl_by_field(hwp, f"previous_finding{slot}_result")
        if ctrl:
            hwp.delete_ctrl(ctrl)


def fill_finding_fields(hwp, report: Report) -> None:
    """7번 "현재 공정 내 현존하는 위험성 제거" — 지적사항 1~4 항목의 유해위험요인/재해예방
    대책/위험성 수준(가능성·중대성·위험도+등급 배경색)/이행결과(추후확인·즉시이행)를 채운다.
    사진은 `report_builder_hwp_images.fill_finding_images()`가 맡는다.

    데이터 없는 슬롯의 표는 `remove_unused_finding_blocks()`가 이미 지웠으므로, 여기선
    남아있는 필드만 자연히 채워진다(`_put`/`hwp.field_exist` 체크가 없는 슬롯은 조용히
    건너뜀).

    표1~16 번호 체계 밖의 별도 표라 필드 이름이 `finding{slot}_*`로 따로 붙어있다
    (`data/build_hwp_template.py`의 t-접두사 규칙과 무관). 이행결과 칸(`finding{slot}_result`)은
    원래 완전히 빈 칸이라 필드 자체가 없었던 자리라 `data/build_hwp_template_layout_fixes.py`의
    `_add_finding_result_fields()`로 별도로 만들었다 — 실제 체크박스 폼 컨트롤은 코드로 상태를
    못 바꾸므로(문서 전체 공통 한계) "☑/☐" 두 줄짜리 고정 텍스트로 표현한다.
    """
    findings = {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        finding = findings.get(slot)
        _put(hwp, f"finding{slot}_hazard", finding.title if finding else "")
        _put(hwp, f"finding{slot}_countermeasure", finding.content if finding else "")
        _fill_finding_risk(hwp, slot, finding)
        _fill_finding_result(hwp, slot, finding)


def _fill_finding_result(hwp, slot: int, finding) -> None:
    """이행결과 칸 — 실제 체크박스는 못 쓰므로 "☑/☐ 추후확인·즉시이행" 두 줄 텍스트로 표현한다."""
    status = finding.action_status if finding else ""
    later_mark = "☑" if status == "추후확인" else "☐"
    now_mark = "☑" if status == "즉시이행" else "☐"
    _put(hwp, f"finding{slot}_result", f"{later_mark} 추후확인\n{now_mark} 즉시이행" if finding else "")


def fill_previous_finding_fields(hwp, report: Report) -> None:
    """3번 "이전 기술지도 사항 이행여부" — 슬롯당 독립된 표(표4~7, 2026-09-07 재구성)의
    제목(A3)/내용(G3)/이행결과(G5)를 채운다. 사진(A2 원본/G2 이행완료 증빙)은 텍스트
    필드가 아니라 `report_builder_hwp_images.fill_previous_finding_images()`가 맡는다.

    제목·내용은 `PreviousFinding.display_fields()`로 가져온다 — 직전 회차에서 이월된
    경우(source_finding_id 있음) 원본 지적사항이 그 사이 수정됐을 수 있어 항상 최신 값을
    반영한다(마법사 쪽과 동일한 실시간 동기화 원칙).
    """
    previous = {p.slot: p for p in report.previous_findings}
    for slot in (1, 2, 3, 4):
        pf = previous.get(slot)
        title, content, _photo_path = pf.display_fields() if pf else ("", "", "")
        _put(hwp, f"previous_finding{slot}_title", title)
        _put(hwp, f"previous_finding{slot}_content", content)
        _fill_previous_finding_result(hwp, slot, pf)


def _fill_previous_finding_result(hwp, slot: int, previous_finding) -> None:
    """이행결과 칸 — "☑/☐ 확인불가·보완필요·이행완료" 세 줄 텍스트로 표현한다."""
    status = previous_finding.result_status if previous_finding else ""
    marks = {label: ("☑" if status == label else "☐") for label in ("확인불가", "보완필요", "이행완료")}
    text = "\n".join(f"{marks[label]} {label}" for label in ("확인불가", "보완필요", "이행완료"))
    _put(hwp, f"previous_finding{slot}_result", text if previous_finding else "")
