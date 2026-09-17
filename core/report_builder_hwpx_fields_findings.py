"""8번(지적사항)/4번(이전지적사항) 표 채우기 — `report_builder_hwp_fields_findings.py`
(pyhwpx/COM 버전)를 python-hwpx로 옮긴 버전.

`remove_unused_finding_blocks()`/`remove_unused_previous_finding_blocks()`(빈 슬롯 표
삭제)는 한때(Sub-phase 21) 지적사항 1~4번 슬롯이 표 하나를 공유하는 구조라 슬롯 단위
삭제가 다른 슬롯의 데이터까지 지워버려서 아무것도 안 지우는 no-op이었다. 2026-09-18에
현재 템플릿을 다시 실측해보니 각 슬롯이 이제 서로 다른 `<hp:tbl>`(표 자체가 슬롯별로
분리됨 — 각 표의 `id` 속성이 전부 다름)이라 슬롯별 삭제를 되살렸다. 다만 표 2개(예:
슬롯1/슬롯2)가 문단 하나를 같이 쓰고 있어서(각각 다른 run) 문단째 지우는
`_remove_table_by_field`는 여전히 위험하다 — 대신 그 표가 든 run 하나만 지우는
`_remove_table_run_by_field`(신규)를 쓴다.

값 조립 규칙 자체는 원본과 동일 — 자세한 배경 설명은 `report_builder_hwp_fields_findings.py`
docstring을 그대로 참고할 것.
"""

from __future__ import annotations

from core.constants import FINDING_LOW_RISK_MAX_SCORE
from core.models_db import PreviousFinding, Report
from core.report_builder_hwpx_fields import _put
from core.report_builder_hwpx_fields_cleanup import _remove_table_run_by_field
from core.report_builder_hwpx_images import _locate_field_cell

_FINDING_RISK_BANDS = [
    (1, FINDING_LOW_RISK_MAX_SCORE, "하", "현상\n유지", "#86EFAC"),
    (4, 5, "중", "개선\n필요", "#FB923C"),
    (6, 9, "상", "즉시\n개선", "#F87171"),
]

# "가능성"/"중대성"/"위험성" 표 헤더 칸의 문단 모양 id — 이미 가운데 정렬이라 재사용한다.
_RISK_CENTER_PARA_PR_ID = "42"
_RISK_BOLD_CHAR_STYLE_KWARGS = {"bold": True, "size": 9}


def _finding_risk_band(score: int) -> tuple[str, str, str | None]:
    for lo, hi, grade, label, color in _FINDING_RISK_BANDS:
        if lo <= score <= hi:
            return grade, label, color
    return "", "", None


def _fill_cell_color(doc, field_name: str, color: str) -> None:
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    table.set_cell_shading(row, col, color)


def _center_bold_field(doc, field_name: str) -> None:
    """위험성 칸의 숫자·등급·라벨을 가운데 정렬+굵게 만든다(사용자 요청) — 이 표(4번
    이전지적사항)는 사용자가 새로 짠 표라 finding{slot} 표(원본 실제 문서에서 그대로 가져온
    표, 처음부터 가운데+굵게였음)와 달리 기본 서식(왼쪽 정렬, 안 굵음)이었다."""
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    cell = table.cell(row, col)
    if not cell.text.strip():
        return
    style_id = doc.ensure_run_style(**_RISK_BOLD_CHAR_STYLE_KWARGS)
    for para in cell.paragraphs:
        para.para_pr_id_ref = _RISK_CENTER_PARA_PR_ID
        for run in para.runs:
            run.char_pr_id_ref = style_id


def _apply_risk_fields(
    doc,
    fields: tuple[str, str, str, str, str],
    likelihood: int | None,
    severity: int | None,
) -> None:
    """가능성/중대성/위험성 값 + 등급/관리기준 5칸짜리 위험성 블록 공통 채우기 로직. 관리기준
    칸에만 등급별 배경색(즉시개선=빨강/개선필요=주황/현상유지=연두)을 입힌다."""
    likelihood_field, severity_field, score_field, grade_field, action_field = fields

    if likelihood is None or severity is None:
        for field in fields:
            _put(doc, field, "")
        return

    score = likelihood * severity
    grade, label, color = _finding_risk_band(score)
    _put(doc, likelihood_field, str(likelihood))
    _put(doc, severity_field, str(severity))
    _put(doc, score_field, str(score))
    _put(doc, grade_field, grade)
    _put(doc, action_field, label)
    if color:
        _fill_cell_color(doc, action_field, color)


def _fill_finding_risk(doc, slot: int, finding) -> None:
    fields = (
        f"finding{slot}_likelihood",
        f"finding{slot}_severity",
        f"finding{slot}_score",
        f"finding{slot}_grade",
        f"finding{slot}_action",
    )
    likelihood = finding.likelihood if finding else None
    severity = finding.severity if finding else None
    _apply_risk_fields(doc, fields, likelihood, severity)


def remove_unused_finding_blocks(doc, report: Report) -> None:
    """데이터가 없는 지적사항(8번) 슬롯의 표를 지운다 — 내용이 1건이라도 있으면 그
    슬롯만 표시되고 나머지 빈 슬롯은 아예 안 보여야 한다(사용자 요청, 2026-09-18).

    한때(Sub-phase 21) 1~4번 슬롯이 표 하나를 공유해 슬롯 단위 삭제가 다른 슬롯 데이터까지
    지워버리는 버그가 있었지만, 지금 템플릿은 슬롯마다 서로 다른 `<hp:tbl>`이다(실측
    확인 — `finding1_hazard`~`finding4_hazard`가 가리키는 표의 `id` 속성이 전부 다름).
    다만 표 2개(슬롯1&2, 슬롯3&4)가 문단 하나를 같이 쓰고 있어서 `_remove_table_by_field`
    (문단째 삭제)를 쓰면 여전히 옆 슬롯까지 같이 지워진다 — 그 표의 run 하나만 지우는
    `_remove_table_run_by_field`를 쓴다. `fill_finding_fields`보다 먼저 호출해야 한다
    (`fill_all` 참고) — 채우기 전에 지워야 아직 빈 슬롯인 채로 삭제 대상을 판단할 수
    있다. 저장 시(`report_wizard_save.py`) 데이터가 없는 슬롯은 애초에 `Finding` 행
    자체를 안 만들므로, `report.findings`에 없는 slot 번호가 곧 "빈 슬롯"이다.
    """
    findings_by_slot = {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        if slot not in findings_by_slot:
            _remove_table_run_by_field(doc, f"finding{slot}_hazard")


def remove_unused_previous_finding_blocks(doc, report: Report) -> None:
    """`remove_unused_finding_blocks`와 같은 이유·같은 방식으로 이전지적사항(4번) 빈
    슬롯의 표를 지운다 — 표4~7도 슬롯마다 서로 다른 표지만 2개씩 문단을 같이 써서
    `_remove_table_run_by_field`가 필요하다(실측 확인). `previous_findings_na` 체크
    시에도 저장 시 슬롯이 전부 비어있으므로(활성 슬롯이 없으면 `PreviousFinding` 행
    자체가 없음) 이 함수 하나로 자연히 표 4개가 다 지워진다 — `remove_na_sections`는
    그래서 이 섹션 제목만 지우고 표 삭제는 여기에 맡긴다."""
    previous_by_slot = {p.slot: p for p in report.previous_findings}
    for slot in (1, 2, 3, 4):
        if slot not in previous_by_slot:
            _remove_table_run_by_field(doc, f"previous_finding{slot}_title")


def fill_finding_fields(doc, report: Report) -> None:
    """8번 "현재 공정 내 현존하는 위험성 제거" — 지적사항 1~4 항목."""
    findings = {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        finding = findings.get(slot)
        _put(doc, f"finding{slot}_hazard", finding.title if finding else "")
        _put(doc, f"finding{slot}_countermeasure", finding.content if finding else "")
        _fill_finding_risk(doc, slot, finding)
        _fill_finding_result(doc, slot, finding)


def _fill_finding_result(doc, slot: int, finding) -> None:
    status = finding.action_status if finding else ""
    later_mark = "☑" if status == "추후확인" else "☐"
    now_mark = "☑" if status == "즉시이행" else "☐"
    _put(doc, f"finding{slot}_result", f"{later_mark} 추후확인\n{now_mark} 즉시이행" if finding else "")


_TITLE_NORMAL_PARA_PR_ID = "40"  # 슬롯1 제목 칸의 문단 모양 — 슬롯2~4는 번호매기기(41)가 섞여있어 통일한다
_TITLE_NORMAL_CHAR_PR_ID = "36"  # 슬롯1 제목/내용 칸과 같은 글자 모양(9pt, 글머리 기호 없음)


def _normalize_previous_finding_title_style(doc, field_name: str) -> None:
    """슬롯2~4의 제목 칸(`previous_finding{slot}_title`)이 원본 템플릿에서 슬롯1과 다른
    문단/글자 모양(번호매기기 41번 + 10pt)을 쓰고 있어, 화면에 앞에 네모 글머리 기호가
    붙고 글자 크기도 달라 보였다(실측 확인 — 사용자 피드백). 슬롯1(및 모든 슬롯의 내용
    칸)과 같은 스타일(문단 40번/글자 36번)로 맞춘다."""
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    cell = table.cell(row, col)
    for para in cell.paragraphs:
        para.para_pr_id_ref = _TITLE_NORMAL_PARA_PR_ID
        for run in para.runs:
            run.char_pr_id_ref = _TITLE_NORMAL_CHAR_PR_ID


def fill_previous_finding_fields(doc, report: Report) -> None:
    """4번 "이전 기술지도 사항 이행여부" — 슬롯당 독립된 표(표4~7)."""
    previous = {p.slot: p for p in report.previous_findings}
    for slot in (1, 2, 3, 4):
        pf = previous.get(slot)
        title, content, _photo_path = pf.display_fields() if pf else ("", "", "")
        _put(doc, f"previous_finding{slot}_title", title)
        _normalize_previous_finding_title_style(doc, f"previous_finding{slot}_title")
        _put(doc, f"previous_finding{slot}_content", content)
        _fill_previous_finding_result(doc, slot, pf)
        _fill_previous_finding_risk(doc, slot, pf, "before", PreviousFinding.source_risk)
        _fill_previous_finding_risk(doc, slot, pf, "after", PreviousFinding.resolve_after_risk)


def _fill_previous_finding_risk(doc, slot: int, previous_finding, prefix: str, risk_fn) -> None:
    fields = tuple(
        f"previous_finding{slot}_{prefix}_{suffix}"
        for suffix in ("likelihood", "severity", "score", "grade", "action")
    )
    likelihood, severity = risk_fn(previous_finding) if previous_finding else (None, None)
    _apply_risk_fields(doc, fields, likelihood, severity)
    for field in fields:
        _center_bold_field(doc, field)


def _fill_previous_finding_result(doc, slot: int, previous_finding) -> None:
    status = previous_finding.result_status if previous_finding else ""
    marks = {label: ("☑" if status == label else "☐") for label in ("확인불가", "보완필요", "이행완료")}
    text = "\n".join(f"{marks[label]} {label}" for label in ("확인불가", "보완필요", "이행완료"))
    _put(doc, f"previous_finding{slot}_result", text if previous_finding else "")
