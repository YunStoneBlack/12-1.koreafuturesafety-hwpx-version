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
전/후 각각 가능성·중대성·위험성)은 `fill_previous_finding_fields()` 참고.

두 섹션 다 "이행결과" 칸은 실제 체크박스 폼 컨트롤을 코드로 못 바꾸는 문서 전체 공통
한계 때문에 "☑/☐" 텍스트로 표현한다(7번은 추후확인/즉시이행 두 줄, 3번은
확인불가/보완필요/이행완료 세 줄).
"""

from __future__ import annotations

from core.constants import FINDING_LOW_RISK_MAX_SCORE
from core.models_db import PreviousFinding, Report
from core.report_builder_hwp_fields import _fix_char_shape, _put
from core.report_builder_hwp_fields_cleanup import _find_table_ctrl_by_field

_FINDING_RISK_BANDS = [
    (1, FINDING_LOW_RISK_MAX_SCORE, "하", "현상\n유지", (134, 239, 172)),  # 연두색(사용자 요청)
    (4, 5, "중", "개선\n필요", (251, 146, 60)),
    (6, 9, "상", "즉시\n개선", (248, 113, 113)),
]


def _finding_risk_band(score: int) -> tuple[str, str, tuple[int, int, int] | None]:
    for lo, hi, grade, label, color in _FINDING_RISK_BANDS:
        if lo <= score <= hi:
            return grade, label, color
    return "", "", None


def _apply_risk_fields(
    hwp,
    fields: tuple[str, str, str, str, str],
    likelihood: int | None,
    severity: int | None,
) -> None:
    """가능성/중대성/위험성 값 + 등급/관리기준 5칸짜리 위험성 블록 공통 채우기 로직 —
    `finding{slot}_*`(7번)와 `previous_finding{slot}_{before,after}_*`(3번)가 전부 같은
    5칸 구조라 공유한다. 관리기준 칸에만 등급별 배경색(즉시개선=빨강/개선필요=주황/
    현상유지=연두)을 `hwp.cell_fill()`로 입힌다.
    """
    likelihood_field, severity_field, score_field, grade_field, action_field = fields

    if likelihood is None or severity is None:
        for field in fields:
            _put(hwp, field, "")
        return

    score = likelihood * severity
    grade, label, color = _finding_risk_band(score)
    _put(hwp, likelihood_field, str(likelihood))
    _put(hwp, severity_field, str(severity))
    _put(hwp, score_field, str(score))
    _put(hwp, grade_field, grade)
    _put(hwp, action_field, label)
    if color and hwp.field_exist(action_field):
        hwp.move_to_field(action_field, text=True, start=True, select=False)
        hwp.TableCellBlock()
        hwp.cell_fill(color)


def _fill_finding_risk(hwp, slot: int, finding) -> None:
    """지적사항 위험성 수준 표(가능성/중대성/위험도 값 + 등급/관리기준 라벨)를 채운다.

    사용자가 한글에서 직접 일반 표 칸으로 재구성해서(원래는 중첩 표라 표6과 같은 한계로
    코드로 못 건드렸다), 각 칸(가능성/중대성/위험성 값, 등급, 관리기준)이 전부 독립된
    필드다.
    """
    fields = (
        f"finding{slot}_likelihood",
        f"finding{slot}_severity",
        f"finding{slot}_score",
        f"finding{slot}_grade",
        f"finding{slot}_action",
    )
    likelihood = finding.likelihood if finding else None
    severity = finding.severity if finding else None
    _apply_risk_fields(hwp, fields, likelihood, severity)


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
    제목(A3)/내용(G3)/이행결과(G5)/이행 전 위험성(A7~C8)/이행 후 위험성(D7~F8)을 채운다.
    사진(A2 원본/G2 이행완료 증빙)은 텍스트 필드가 아니라
    `report_builder_hwp_images.fill_previous_finding_images()`가 맡는다.

    제목·내용·이행 전 위험성은 전부 원본(직전 회차) 지적사항에서 실시간으로 가져온다
    (`PreviousFinding.display_fields()`/`source_risk()`) — 직전 회차에서 이월된 경우
    (source_finding_id 있음) 원본이 그 사이 수정됐을 수 있어 항상 최신 값을 반영한다
    (마법사 쪽과 동일한 실시간 동기화 원칙). 이행 후 위험성은 조치 결과(확인불가/보완필요/
    이행완료)에 따라 `PreviousFinding.resolve_after_risk()`가 결정한다(사용자 설명,
    2026-09-08) — "이행완료"로 확정되면 그 안에서 무작위로 고른 가능성·중대성을 DB에
    캐시하므로, 이 함수를 여러 번 불러도(미리보기 갱신 등) 같은 값이 재사용된다.
    """
    previous = {p.slot: p for p in report.previous_findings}
    for slot in (1, 2, 3, 4):
        pf = previous.get(slot)
        title, content, _photo_path = pf.display_fields() if pf else ("", "", "")
        _put(hwp, f"previous_finding{slot}_title", title)
        _put(hwp, f"previous_finding{slot}_content", content)
        _fill_previous_finding_result(hwp, slot, pf)
        _fill_previous_finding_risk(hwp, slot, pf, "before", PreviousFinding.source_risk)
        _fill_previous_finding_risk(hwp, slot, pf, "after", PreviousFinding.resolve_after_risk)


_RISK_FIELD_HEIGHT = 900  # 실측: 이 표(사용자가 새로 짠 표)의 원래 글자 크기


def _center_bold_field(hwp, field_name: str) -> None:
    """위험성 칸의 숫자·등급·라벨을 가운데 정렬+굵게 만든다(사용자 요청, 2026-09-08) —
    이 표는 사용자가 새로 짠 표라 finding{slot} 표(원본 실제 문서에서 그대로 가져온 표,
    처음부터 가운데+굵게였음)와 달리 기본 서식(왼쪽 정렬, 안 굵음)이었다. "이행 후
    위험성"도 같은 규칙을 쓴다.

    "개선\\n필요"처럼 두 줄(두 문단)짜리 라벨은 `select=False`로 커서만 첫 줄에 두고
    문단 정렬을 적용하면 **첫 줄만 가운데로 오고 둘째 줄은 왼쪽에 남는다**(문단 정렬은
    문단 단위 속성이라 커서/선택이 걸친 문단에만 적용됨, 실측 확인) — 반드시 필드 전체를
    선택(`select=True`)한 채로 정렬을 적용해야 모든 줄이 같이 가운데로 온다.

    필드가 비어있으면(해당 슬롯 없음, 확인불가 등으로 `_apply_risk_fields`가 ""를 채운
    경우) 아무것도 안 하고 건너뛴다 — `move_to_field(..., select=True)`를 빈 필드에 쓰면
    선택 범위가 못 끝나고 뒤쪽 셀까지 번져 그 칸 글자 크기를 키워버리는 문제가 있다
    (`fill_signoff_fields()`의 담당요원 칸에서 실측으로 확인된 것과 같은 버그, 핵심기술.md
    참고).
    """
    if not hwp.field_exist(field_name):
        return
    if not hwp.get_field_text(field_name):
        return
    _fix_char_shape(hwp, field_name, height=_RISK_FIELD_HEIGHT, bold=1)
    hwp.move_to_field(field_name, text=True, start=True, select=True)
    hwp.HAction.Run("ParagraphShapeAlignCenter")


def _fill_previous_finding_risk(hwp, slot: int, previous_finding, prefix: str, risk_fn) -> None:
    """이행 전/후 위험성 칸을 채운다 — 두 블록이 필드 접두사(`before`/`after`)와 값을
    가져오는 방법만 다르고 나머지 구조(5칸 채우기 + 가운데정렬/굵게)는 완전히 같아서 공유
    한다.

    - "이행 전"(A7=가능성/B7=중대성/C7=위험성/A8=등급/C8=관리기준): `prefix="before"`,
      `risk_fn=PreviousFinding.source_risk` — 원본(직전 회차) 지적사항의 "현재의 위험성"을
      실시간으로 반영한다.
    - "이행 후"(D7=가능성/E7=중대성/F7=위험성/D8=등급/F8=관리기준): `prefix="after"`,
      `risk_fn=PreviousFinding.resolve_after_risk` — 조치 결과(확인불가/보완필요/이행완료)에
      따라 정해지며, "이행완료"인 경우 무작위로 고른 조합이 DB에 캐시되어 재호출해도 값이
      안 바뀐다.
    """
    fields = tuple(
        f"previous_finding{slot}_{prefix}_{suffix}"
        for suffix in ("likelihood", "severity", "score", "grade", "action")
    )
    likelihood, severity = risk_fn(previous_finding) if previous_finding else (None, None)
    _apply_risk_fields(hwp, fields, likelihood, severity)
    for field in fields:
        _center_bold_field(hwp, field)


def _fill_previous_finding_result(hwp, slot: int, previous_finding) -> None:
    """이행결과 칸 — "☑/☐ 확인불가·보완필요·이행완료" 세 줄 텍스트로 표현한다."""
    status = previous_finding.result_status if previous_finding else ""
    marks = {label: ("☑" if status == label else "☐") for label in ("확인불가", "보완필요", "이행완료")}
    text = "\n".join(f"{marks[label]} {label}" for label in ("확인불가", "보완필요", "이행완료"))
    _put(hwp, f"previous_finding{slot}_result", text if previous_finding else "")
