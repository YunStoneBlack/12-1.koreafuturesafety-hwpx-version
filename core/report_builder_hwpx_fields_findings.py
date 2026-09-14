"""8번(지적사항)/4번(이전지적사항) 표 채우기 — `report_builder_hwp_fields_findings.py`
(pyhwpx/COM 버전)를 python-hwpx로 옮긴 버전.

`remove_unused_finding_blocks()`/`remove_unused_previous_finding_blocks()`(빈 슬롯 표
삭제)는 `report_builder_hwpx_fields_cleanup.py`의 `_remove_table_by_field()`(표를 감싸는
문단을 `doc.remove_paragraph()`로 직접 지움 — COM의 `delete_ctrl()`처럼 "성공했다는데
실제로는 안 지워지는" 문제가 없다)를 그대로 가져다 쓴다.

값 조립 규칙 자체는 원본과 동일 — 자세한 배경 설명은 `report_builder_hwp_fields_findings.py`
docstring을 그대로 참고할 것.
"""

from __future__ import annotations

from core.constants import FINDING_LOW_RISK_MAX_SCORE
from core.models_db import PreviousFinding, Report
from core.report_builder_hwpx_fields import _put
from core.report_builder_hwpx_fields_cleanup import _remove_table_by_field
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
    """데이터가 없는 지적사항 슬롯의 표 전체를 지운다 — 지적사항이 0건이면(1~4번 전부
    미사용) 1·2번(같은 페이지)까지 지우면 "8. 현재 공정 내 현존하는 위험성 제거" 제목만
    남고 아래가 빈 페이지가 되므로, 이 경우엔 1·2번은 지우지 않고 빈 칸으로 남긴다(내용은
    `fill_finding_fields`가 빈 문자열로 채워 자연히 공란으로 보인다) — 3·4번은 그대로
    지운다. 반드시 `fill_finding_fields`보다 먼저 호출해야 한다."""
    findings_by_slot = {} if report.findings_na else {f.slot: f for f in report.findings}
    keep_blank_slots = {1, 2} if not findings_by_slot else set()
    for slot in (1, 2, 3, 4):
        if slot in findings_by_slot or slot in keep_blank_slots:
            continue
        _remove_table_by_field(doc, f"finding{slot}_hazard")


def remove_unused_previous_finding_blocks(doc, report: Report) -> None:
    """데이터가 없는 이전지적사항 슬롯의 표 전체를 지운다 — `remove_unused_finding_blocks`와
    같은 원칙(0건이면 1·2번은 빈 칸으로 남기고 3·4번만 지움). 반드시
    `fill_previous_finding_fields`보다 먼저 호출해야 한다."""
    previous_by_slot = {} if report.previous_findings_na else {p.slot: p for p in report.previous_findings}
    keep_blank_slots = {1, 2} if not previous_by_slot else set()
    for slot in (1, 2, 3, 4):
        if slot in previous_by_slot or slot in keep_blank_slots:
            continue
        _remove_table_by_field(doc, f"previous_finding{slot}_result")


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
