""""해당사항없음" 표/제목 정리 + 빈 슬롯 표 삭제 — `report_builder_hwp_fields_cleanup.py`
(pyhwpx/COM 버전)를 python-hwpx로 옮긴 버전.

**COM 버전과 달리 이번 포팅에서 달라진 점**: COM 버전은 `delete_ctrl()`이 성공을 반환해도
실제로는 안 지워지는 표가 있어서(표6 12대 기인물, 표12/15) 표6은 아예 포기하고 표12/15는
"행을 2mm로 접어서 안 보이게" 하는 우회를 썼다. python-hwpx는 표를 감싸는 문단 자체를
`doc.remove_paragraph()`로 XML에서 직접 지우므로 이런 우회가 필요 없다 — 표6도 이번엔
정상적으로 지운다.

**빈 페이지 정리(`_remove_blank_pages`)가 이번 포팅에는 없다**: COM 버전은 살아있는
편집기 캐럼/페이지 계산 위에서 "표를 지운 자리에 빈 페이지가 남는" 문제가 있어 별도로
빈 페이지를 찾아 지워야 했다. python-hwpx는 페이지 개념이 없는 순수 XML 문서 모델이라
(렌더링은 한글이 열 때 처음 계산) 문단을 통째로 지우면 그 문단이 차지하던 공간 자체가
사라진다 — 실측 확인 결과 별도 빈 페이지 정리 없이도 빈 페이지가 남지 않았다.
"""

from __future__ import annotations

import re

from core.models_db import Report

_HEADING_RE = re.compile(r"^\d+\.\s")


def _local_name(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_table_by_field(doc, field_name: str):
    """`field_name` 누름틀 필드가 들어있는 표(`HwpxOxmlTable`) 자체를 찾는다."""
    field = next((f for f in doc.fields.all if f.name == field_name), None)
    if field is None:
        return None

    node = field.element
    tbl_node = None
    while node is not None:
        if _local_name(node.tag) == "tbl":
            tbl_node = node
            break
        node = node.getparent()
    if tbl_node is None:
        return None

    for table in doc.tables.all:
        if table.element is tbl_node:
            return table
    return None


def _find_anchor_paragraph(doc, table) -> object | None:
    """표를 담고 있는 최상위 문단(표를 지우려면 이 문단을 지워야 한다)을 찾는다."""
    for paragraph in doc.paragraphs:
        for t in paragraph.tables:
            if t.element is table.element:
                return paragraph
    return None


def _remove_table_by_field(doc, field_name: str) -> bool:
    table = _find_table_by_field(doc, field_name)
    if table is None:
        return False
    paragraph = _find_anchor_paragraph(doc, table)
    if paragraph is None:
        return False
    doc.remove_paragraph(paragraph)
    return True


def _remove_table_run_by_field(doc, field_name: str) -> bool:
    """`_remove_table_by_field`와 달리 표를 담은 문단 전체가 아니라, 그 표(`<hp:tbl>`)
    노드 하나만 지운다 — 지적사항(8번)/이전지적사항(4번) 표는 슬롯 2개(1&2, 3&4)가
    문단 하나는 물론 **run 하나까지** 같이 쓴다(실측 확인: 한 run의 자식이
    `[tbl, tbl, t]` — 표 2개가 같은 run 안에 나란히 들어있고 뒤에 빈 텍스트 노드가
    붙음). `_remove_table_by_field`(문단째 삭제)는 물론, run 단위로 지워도 옆 슬롯
    표까지 같이 사라진다(2026-09-18, 실사용 전 검증 중 발견 — 슬롯 2에 데이터가 있어도
    슬롯 1을 지우려다 같이 지워짐) — 그래서 run이 아니라 표 노드 자체만 그 run에서
    떼어낸다. 표를 지우고 나서 그 문단에 표가 하나도 안 남으면(두 슬롯 다 빈 경우)
    문단 자체도 마저 지운다 — 빈 문단이 차지하는 줄바꿈 한 칸이 남는 걸 막는다.
    """
    table = _find_table_by_field(doc, field_name)
    if table is None:
        return False
    paragraph = _find_anchor_paragraph(doc, table)
    if paragraph is None:
        return False
    tbl_element = table.element
    tbl_element.getparent().remove(tbl_element)
    if not list(paragraph.tables):
        doc.remove_paragraph(paragraph)
    return True


def _remove_paragraph_containing(doc, text: str) -> bool:
    """`text`가 들어있는(표가 아닌, 표 밖) 문단을 지운다 — 독립된 섹션 제목 문단을 지울 때
    쓴다. 표 안 문단은 `doc.paragraphs`(최상위 문단만 순회)에 안 잡히므로 안전하다."""
    for paragraph in doc.paragraphs:
        if text in (paragraph.text or ""):
            doc.remove_paragraph(paragraph)
            return True
    return False


def remove_na_sections(doc, report: Report) -> None:
    """마법사에서 "해당사항없음"으로 체크한 섹션은 표(+표 밖 제목이 있는 경우 그것도)를
    통째로 지운다. 반드시 각 표를 채우는 `fill_*` 함수보다 먼저 호출해야 한다."""
    # 이전지적사항(4번)/지적사항(8번)의 "해당사항없음"은 마법사에서 버튼을 숨겼고(2026-09-21),
    # 하나도 없을 땐 제목만 남기지 않고 "없음" 안내 표를 그대로 보여준다 — 그래서 예전에 저장된
    # 보고서에 `previous_findings_na`가 켜져 있어도 제목을 지우지 않는다.
    if report.major_hazard_na:
        _remove_table_by_field(doc, "t5_001")
        _remove_paragraph_containing(doc, "대형사고 위험작업 사항")

    if report.hazard_factors_na:
        # COM 버전은 이 표(12대 기인물)를 못 지워서 포기했지만, python-hwpx는 문단을 직접
        # 지우므로 정상적으로 지울 수 있다 — 제목이 표 A1 안에 있어 별도 제목 문단은 없다.
        _remove_table_by_field(doc, "t6_1_f")

    if report.equipment_checks_na:
        for field in ("t7_category", "t8_category", "t9_category"):
            _remove_table_by_field(doc, field)

    if report.current_process_na:
        _remove_table_by_field(doc, "t12_001")
        _remove_paragraph_containing(doc, "현재 진행공정에 대한 유해")

    if report.process_na:
        _remove_table_by_field(doc, "t14_001")
        _remove_table_by_field(doc, "t15_001")
        _remove_paragraph_containing(doc, "향후 진행공정에 대한 유해")


def apply_heading_keep_with_next(doc) -> None:
    """"1. ...", "2. ..." 같은 번호 섹션 제목 문단에 "다음 문단과 함께"(keep_with_next)를
    걸어, 제목만 페이지 맨 아래에 혼자 남고 바로 뒤에 오는 표가 다음 페이지로 넘어가는
    현상을 막는다(실측 확인 — 8번 표 뒤 "9. 향후 진행공정..." 제목이 이 문제였다).

    제목 바로 다음 문단만 묶으면 부족하다 — 제목과 표 사이에 빈 문단("↵")이 하나 끼어있는
    구조라(실측 확인), keep_with_next는 "바로 다음 문단"까지만 묶어주므로 제목→빈 문단만
    묶이고 정작 표가 있는 문단까지는 안 이어진다. 그래서 제목부터 시작해 표를 포함한
    문단(`paragraph.tables`가 있는 문단)을 만날 때까지 연속으로 keep_with_next를 걸어
    사슬처럼 전부 이어준다(중간에 다른 제목을 만나면 그 전에서 멈춘다 — 다음 섹션까지
    잘못 끌려오지 않도록).

    표/문단을 지운 뒤(`remove_na_sections` 등) 최상위 문단 목록이 바뀌므로, 인덱스를
    미리 계산해두지 않고 이 함수를 호출하는 시점에 다시 훑는다.
    """
    paragraphs = list(doc.paragraphs)
    for index, paragraph in enumerate(paragraphs):
        text = (paragraph.text or "").strip()
        if not _HEADING_RE.match(text):
            continue
        i = index
        while i + 1 < len(paragraphs):
            doc.set_paragraph_format(paragraph_index=i, keep_with_next=True)
            nxt = paragraphs[i + 1]
            if list(nxt.tables) or _HEADING_RE.match((nxt.text or "").strip()):
                break
            i += 1


def force_future_process_heading_page_break(doc) -> None:
    """"9. 향후 진행공정..." 제목 문단에 `page_break_before`를 강제로 걸어 항상 새 페이지
    맨 위에서 시작하게 한다.

    지적사항(8번)이 몇 건이냐에 따라 8번 표 길이가 들쭉날쭉해지고(빈 슬롯을 표에 남기던
    시절도, 지금처럼 `remove_unused_finding_blocks`가 빈 슬롯 표를 지우는 지금도 마찬가지
    — 오히려 지금은 슬롯 개수만큼 표 자체가 사라지므로 길이 편차가 더 크다), 그 결과
    "9." 제목이 8번 표 페이지 맨 아래에 겨우 낑겨 들어가는 경우가 생겼다(실사용 확인,
    2026-09-16). `apply_heading_keep_with_next`의 연쇄 keep_with_next
    (제목→빈 문단→표)만으로는 이 경계 케이스를 못 잡아서, "9." 제목만은 아예 무조건 새
    페이지에서 시작하도록 명시적으로 강제한다 — 8번 표가 몇 줄이든 결과가 항상 같아
    keep_with_next 연쇄의 신뢰성 문제에 기대지 않아도 된다.
    """
    for index, paragraph in enumerate(doc.paragraphs):
        text = (paragraph.text or "").strip()
        if _HEADING_RE.match(text) and text.split(".", 1)[0] == "9":
            doc.set_paragraph_format(paragraph_index=index, page_break_before=True)
            break
