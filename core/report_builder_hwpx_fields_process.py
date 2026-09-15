"""표12(7번 현재 진행공정)/표15(9번 향후 진행공정) 채우기 — Sub-phase 20에서
`report_builder_hwpx_fields.py`가 600줄을 넘겨 이 파일로 분리했다(이 프로젝트의 다른
`_findings.py`/`_cleanup.py` 분리와 같은 패턴).

Sub-phase 20: 공정 사진 + AI 분석으로 유해요인 1개에 예방대책이 여러 건(가변 개수) 달릴 수
있게 되면서, "빈 줄을 세어 넣어 칸을 맞추는" 텍스트 기반 정렬 방식(글자 수로 줄바꿈을
추정)이 실측으로 확인된 한계가 있었다(자간·커닝을 완벽히 재현 못 함) — 유해요인마다 실제
표 행(row)을 만들고 공정명 칸은 그 행들에 걸쳐 세로 병합(rowspan)하는 구조로 바꿔서, 정렬을
한글 표 엔진에 완전히 맡긴다(`insert_hazard_rows`/`remove_process_row`/`merge_cells`).
"""

from __future__ import annotations

from copy import deepcopy

from core.models_db import Report
from core.report_builder_hwpx_fields import _put
from core.report_builder_hwpx_images import _locate_field_cell


def _set_cell_vert_align(cell, align: str) -> None:
    """칸(cell)의 세로 정렬(`<hp:subList vertAlign="...">`)을 직접 바꾼다 — python-hwpx는
    이 속성에 대한 고수준 API가 없어(`run.char_pr_id_ref`류와 달리) XML을 직접 만져야 한다
    (`_cell_inner_box`(report_builder_hwpx_images.py)가 `cellMargin`을 읽을 때 쓰는 것과
    같은 "태그 이름 접미사로 자식 element 찾기" 패턴).
    """
    for child in cell.element:
        if isinstance(child.tag, str) and child.tag.endswith("}subList"):
            child.set("vertAlign", align)
            break


def _set_cell_char_shape(cell, char_pr_id_ref: str) -> None:
    """칸(cell)의 모든 run 글자 모양을 지정한 스타일 id로 맞춘다."""
    for para in cell.paragraphs:
        for run in para.runs:
            run.char_pr_id_ref = char_pr_id_ref


def _set_cell_para_shape(cell, para_pr_id_ref: str) -> None:
    """칸(cell)의 모든 문단 모양을 지정한 스타일 id로 맞춘다.

    표12/15 유해·위험요인/예방대책 칸의 원래 문단 모양(id 36/37)은 "내어쓰기"
    (`<hc:intent>`가 음수)가 걸려 있다 — 원래는 글머리점 하나짜리 문장이 줄바꿈될 때 이어지는
    줄을 글머리점이 아니라 그 뒤 텍스트에 맞추려는 의도였겠지만, Sub-phase 20부터 한 칸 안에
    여러 개의 독립된 글머리점 줄(예방대책 여러 건)을 넣게 되면서 2번째 글머리점부터도 전부
    "이어지는 줄"로 취급돼 오른쪽으로 밀려 보이는 문제가 생겼다(사용자 실측 확인). 내어쓰기가
    없는(intent=0) 기존 문단 모양(id 2/34 — 정렬·줄간격·테두리는 36/37과 동일, intent만 0)을
    재사용한다(`_fix_para_shape`와 같은 "새로 안 만들고 문서에 이미 있는 스타일 재사용" 원칙).
    """
    for para in cell.paragraphs:
        para.para_pr_id_ref = para_pr_id_ref


def _set_cell_min_height(cell, height: int) -> None:
    """칸의 `<hp:cellSz height="...">`(최소 높이, hwpunit)를 줄인다 — 한글 표는 이 값을
    "최소"로 다뤄 실제 내용이 더 길면 자동으로 늘어나므로 작게 줄여도 잘릴 걱정은 없다."""
    for child in cell.element:
        if isinstance(child.tag, str) and child.tag.endswith("}cellSz"):
            child.set("height", str(height))
            break


def _strip_field_controls(tc_element) -> None:
    """표 행을 복제(`deepcopy`)하면 복제본이 원본과 같은 이름·id의 누름틀 필드
    (`<hp:ctrl><hp:fieldBegin name="t12_..." .../></hp:ctrl>`)를 그대로 들고 있게 된다 —
    새로 끼워 넣는 행은 필드로 채우지 않고 `cell.text`에 직접 쓸 것이므로(같은 이름의 필드가
    문서에 중복되면 안 되니) 그 필드 컨트롤 자체를 제거한다."""
    for run in tc_element.iter():
        if not (isinstance(run.tag, str) and run.tag.endswith("}run")):
            continue
        for ctrl in [c for c in run if isinstance(c.tag, str) and c.tag.endswith("}ctrl")]:
            run.remove(ctrl)


def insert_hazard_rows(table, process_row: int, hazard_count: int) -> None:
    """`process_row`(0-based) 한 행을 유해요인 개수(`hazard_count`)만큼의 행으로 늘린다.

    Sub-phase 20: 유해요인마다 예방대책 줄 수가 달라 "빈 줄을 세어 넣어 칸을 맞추는" 이전
    방식은 문장 줄바꿈을 글자 수만으로 정확히 예측할 수 없어 실측으로 확인된 한계가 있었다
    (자간·커닝을 완벽히 재현 못 함). 유해요인마다 실제 표 행을 만들면 그 행의 높이는 한글
    표 엔진이 알아서 맞춰주므로(같은 행의 칸은 항상 같은 줄에서 시작) 이 문제 자체가
    사라진다 — 공정명 칸은 `table.merge_cells()`로 새 행들에 걸쳐 세로 병합(rowspan)한다
    (호출부 `fill_current_process_fields`/`fill_future_process_detail_fields` 참고).

    python-hwpx에 표에 행을 추가하는 고수준 API가 없다(있는 건 셀 병합/분할뿐) — 원본 행을
    `deepcopy`해서 끼워 넣고, 그 아래 있던 행들의 `<hp:cellAddr rowAddr>`를 밀어준 뒤,
    표 전체의 `<hp:tbl rowCnt="...">`를 보정하는 저수준 방식을 쓴다(`row_count`/`cell()`이
    이 속성을 우선 읽으므로 안 늘리면 새 행에 `table.cell()`로 접근할 때 IndexError가 난다).
    `data/templates/report_template.hwpx`(표12)로 실제 저장·재오픈·구조검증까지 거쳐
    확인했다.
    """
    if hazard_count <= 1:
        return
    row_elements = [
        child for child in table.element if isinstance(child.tag, str) and child.tag.endswith("}tr")
    ]
    ref_row_el = row_elements[process_row]
    extra = hazard_count - 1

    for row_el in row_elements[process_row + 1 :]:
        for tc in row_el:
            if not (isinstance(tc.tag, str) and tc.tag.endswith("}tc")):
                continue
            for child in tc:
                if isinstance(child.tag, str) and child.tag.endswith("}cellAddr"):
                    child.set("rowAddr", str(int(child.get("rowAddr", "0")) + extra))

    insert_at = list(table.element).index(ref_row_el) + 1
    for k in range(1, hazard_count):
        clone = deepcopy(ref_row_el)
        for tc in clone:
            if not (isinstance(tc.tag, str) and tc.tag.endswith("}tc")):
                continue
            for child in tc:
                if isinstance(child.tag, str) and child.tag.endswith("}cellAddr"):
                    child.set("rowAddr", str(process_row + k))
            _strip_field_controls(tc)
        table.element.insert(insert_at, clone)
        insert_at += 1

    table.element.set("rowCnt", str(int(table.element.get("rowCnt", "0")) + extra))
    table.mark_dirty()


def remove_process_row(table, row_index: int) -> None:
    """`row_index`(0-based) 행 하나를 표에서 완전히 지운다 — `insert_hazard_rows`의 반대
    동작(행을 이어붙이는 대신 떼어낸다). 향후공정/현재공정 항목이 1개 이상 있지만 4개
    미만이면, 채워지지 않은 나머지 슬롯을 빈 칸으로 남겨두지 않고 표에서 아예 없앤다
    (사용자 요청) — 항목이 0개(전부 빈 칸)일 때는 표 구조를 그대로 유지하는 기존 동작과
    대비된다(호출부 `_remove_unused_process_slots` 참고, 그쪽에서 0개인 경우를 걸러낸다).
    """
    row_elements = [
        child for child in table.element if isinstance(child.tag, str) and child.tag.endswith("}tr")
    ]
    target = row_elements[row_index]
    table.element.remove(target)

    for row_el in row_elements[row_index + 1 :]:
        for tc in row_el:
            if not (isinstance(tc.tag, str) and tc.tag.endswith("}tc")):
                continue
            for child in tc:
                if isinstance(child.tag, str) and child.tag.endswith("}cellAddr"):
                    child.set("rowAddr", str(int(child.get("rowAddr", "0")) - 1))

    table.element.set("rowCnt", str(int(table.element.get("rowCnt", "0")) - 1))
    table.mark_dirty()


def _remove_unused_process_slots(doc, field_prefix: str, filled_count: int) -> None:
    """항목(공정)이 1개 이상 있지만 4개 미만이면, 채워지지 않은 나머지 슬롯(빈 칸)을
    표에서 아예 지운다. 뒤쪽 슬롯(4번)부터 지워야 아직 안 지운 앞쪽 슬롯의 위치가
    안 흔들린다(`remove_process_row`는 지운 행 아래쪽 행들의 `rowAddr`만 당기므로,
    뒤에서부터 지우면 앞쪽엔 영향이 없다). 호출부가 `filled_count >= 1`일 때만 불러야
    한다 — 0개(전부 빈 칸)면 표 구조를 그대로 유지하는 게 기존 동작(사용자 요청)이다.
    """
    for i in range(3, filled_count - 1, -1):
        base = i * 4 + 1
        located = _locate_field_cell(doc, f"{field_prefix}_{base:03d}")
        if located is None:
            continue
        table, row, _col = located
        remove_process_row(table, row)


_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _borderfill_hide_edges(doc, base_id: str, hide_top: bool, hide_bottom: bool, cache: dict) -> str:
    """`base_id`(borderFillIDRef) 정의를 복제해 위/아래 중 지정된 쪽만 안 보이게(`NONE`)
    바꾼 새 borderFill id를 돌려준다 — 왼쪽/오른쪽/반대쪽 테두리와 두께는 원본 그대로
    유지한다(표12/15 데이터 칸은 아래쪽만 굵은 0.4mm라 균일폭 헬퍼로는 재현이 안 돼 직접
    복제한다). 같은 공정 안에서 유해요인마다 실제 행이 여러 개로 늘어나면서(Sub-phase 20)
    그 사이 경계선이 그대로 보이면 "여러 행"처럼 보여 원래 의도(하나의 공정, 유해요인
    여러 건)와 다르게 읽힌다는 피드백으로 추가 — 첫 행의 위쪽/마지막 행의 아래쪽(다른
    공정과의 경계)만 남기고 나머지는 지운다. `cache`로 같은 조합을 반복 생성하지 않는다."""
    if not hide_top and not hide_bottom:
        return base_id
    key = (base_id, hide_top, hide_bottom)
    if key in cache:
        return cache[key]

    header = doc.parts.headers[0]
    ref_list = header.element.find(f"{_HH}refList")
    border_fills = ref_list.find(f"{_HH}borderFills")
    source = next(bf for bf in border_fills.findall(f"{_HH}borderFill") if bf.get("id") == str(base_id))
    clone = deepcopy(source)
    existing_ids = {
        int(bf.get("id")) for bf in border_fills.findall(f"{_HH}borderFill") if (bf.get("id") or "").isdigit()
    }
    new_id = str(max(existing_ids) + 1)
    clone.set("id", new_id)
    if hide_top:
        top = clone.find(f"{_HH}topBorder")
        if top is not None:
            top.set("type", "NONE")
    if hide_bottom:
        bottom = clone.find(f"{_HH}bottomBorder")
        if bottom is not None:
            bottom.set("type", "NONE")
    border_fills.append(clone)
    border_fills.set("itemCnt", str(len(border_fills.findall(f"{_HH}borderFill"))))
    header.mark_dirty()

    cache[key] = new_id
    return new_id


def _adjust_process_table_header(table, risk_width: int, freed_each: int) -> None:
    """표12/15 헤더 행 "위험성수준"을 "위험성"으로 줄이고(사용자 요청), 위험성 칸 폭을
    `risk_width`로 줄인 뒤 그만큼(`freed_each`씩)을 유해요인·예방대책 칸에 나눠준다.

    `doc.replace_text_in_runs()`는 표 밖(최상위) 문단만 훑기 때문에(실측 확인 — 헤더 텍스트가
    바뀌지 않았음) 표 안 칸은 `cell.text`로 직접 써야 한다. 폭 조정은 헤더 행 포함 모든
    행에 동일하게 적용해야 표 세로선이 어긋나지 않는다 — `insert_hazard_rows()`가 원본
    행을 복제하므로, 유해요인 개수만큼 행이 늘어나기 *전에* 이 조정을 먼저 해야 복제된
    행도 조정된 폭을 그대로 물려받는다(호출부 참고).
    """
    table.cell(0, 3).text = "위험성"

    def _resize(cell, delta: int) -> None:
        for child in cell.element:
            if isinstance(child.tag, str) and child.tag.endswith("}cellSz"):
                child.set("width", str(int(child.get("width", 0)) + delta))
                break

    for row_index in range(table.row_count):
        try:
            hazard_cell = table.cell(row_index, 1)
            prevention_cell = table.cell(row_index, 2)
            risk_cell = table.cell(row_index, 3)
        except Exception:
            continue
        _resize(hazard_cell, freed_each)
        _resize(prevention_cell, freed_each)
        for child in risk_cell.element:
            if isinstance(child.tag, str) and child.tag.endswith("}cellSz"):
                child.set("width", str(risk_width))
                break


def _risk_checklist(risk_level: str) -> str:
    """위험성수준 칸의 "상\\n중\\n하" 세 줄 각각의 앞에 체크(☑/☐)를 붙인다 — 실제 risk_level과
    일치하는 한 줄만 ☑, 나머지는 ☐. python-hwpx는 순수 "\\n"을 줄바꿈으로 정상 처리하므로
    (pyhwpx와 달리) "\\r\\n" 우회가 필요 없다. 옛 방식(엔트리 단일값, `items` 없음) 전용.
    """
    return "\n".join(f"{'☑' if risk_level == label else '☐'}{label}" for label in ("상", "중", "하"))


_PROCESS_HAZARD_PARA_PR = "36"  # 원래 이 칸의 문단 모양 — 내어쓰기 있음(줄바꿈된 줄이 글머리점
# 대신 그 뒤 텍스트 시작 위치에 맞춰짐). 유해요인 칸은 항목당 문단이 1개뿐이라 내어쓰기가
# 여러 글머리점을 밀어내는 부작용이 없다 — 오히려 사용자가 원하는 동작(사용자 요청).
_PROCESS_PREVENTION_PARA_PR = "37"  # 예방대책 칸의 원래 문단 모양(내어쓰기 있음). 예방대책
# 여러 개는 이제 `split_paragraphs=True`로 진짜 별도 문단이라(cell_prevention.set_text 호출부
# 참고), 각 문단이 자기 자신의 줄바꿈만 내어쓰기하고 다음 글머리점(별도 문단)까지 밀어내지
# 않는다 — id 2/34(내어쓰기 없앤 버전)를 임시로 썼다가, 문단을 분리한 뒤에는 원래
# 내어쓰기가 있는 편이 더 낫다는 사용자 피드백으로 되돌렸다.


def _fill_process_entry_row(doc, table, row: int, entry, border_fill_cache: dict) -> None:
    """공정 하나(entry)를 표12/15의 실제 행(들)에 채운다.

    Sub-phase 20: 유해요인 개수만큼 실제 표 행을 늘리고(`insert_hazard_rows`) 공정명 칸은
    그 행들에 걸쳐 세로 병합(rowspan)한다 — 텍스트에 빈 줄을 세어 넣어 칸을 맞추던 이전
    방식(글자 수로 줄바꿈을 추정)은 실측으로 확인된 한계가 있어(자간·커닝을 완벽히
    재현 못 함) 표 구조 자체로 바꿨다. 행이 같으면 칸은 항상 같은 줄에서 시작하므로
    한글 표 엔진이 알아서 정확히 맞춰준다.

    예방대책 여러 줄은 진짜로 서로 다른 문단(paragraph)으로 나눠 넣는다(`split_paragraphs=True`)
    — 한 문단 안에 "\\n"만 넣으면 원래 문단 모양의 내어쓰기 때문에 2번째 글머리점부터
    첫 글머리점과 위치가 안 맞는다(사용자 실측 확인) — 별도 문단이면 각자 자기 왼쪽 끝에서
    시작해서 이 문제가 없다. 유해요인 칸도 예방대책과 통일감 있게 글머리점(•)을 붙인다
    (사용자 요청).

    공정명 칸은 위아래 가운데 정렬 그대로 둔다(사용자 확인 — 여러 행에 걸쳐 병합되므로
    가운데가 자연스럽다). 유해요인이 2건 이상이면 그 사이 경계선은 안 보이게 지운다
    (`border_fill_cache`) — 첫 행 위쪽/마지막 행 아래쪽(다른 공정과의 경계)만 남긴다.

    `entry.items`가 비어있고 옛 단일값(`hazard_text`)이 남아있으면(옛 카탈로그 방식으로
    저장된 보고서) 행을 늘리지 않고 그 옛 방식 그대로 표시한다 — 옛 데이터를 지우지 않고
    남겨둔 이유(core/models_db.py 참고)가 바로 이 대체 표시다.
    """
    items = list(entry.items)
    prevention_style = doc.ensure_run_style(size=10)

    if not items and entry.hazard_text:
        cell_hazard = table.cell(row, 1)
        cell_prevention = table.cell(row, 2)
        cell_risk = table.cell(row, 3)
        cell_hazard.text = entry.hazard_text
        cell_prevention.text = entry.prevention_text
        _set_cell_char_shape(cell_prevention, prevention_style)
        cell_risk.text = _risk_checklist(entry.risk_level)
        for cell in (cell_hazard, cell_prevention, cell_risk):
            _set_cell_vert_align(cell, "TOP")
        table.cell(row, 0).text = entry.process_name
        return

    hazard_count = max(1, len(items))
    insert_hazard_rows(table, row, hazard_count)
    for k in range(hazard_count):
        item = items[k] if k < len(items) else None
        cell_hazard = table.cell(row + k, 1)
        cell_prevention = table.cell(row + k, 2)
        cell_risk = table.cell(row + k, 3)

        if hazard_count > 1:
            # 옛 설계(공정 1개 = 표 1행에 여러 줄이 다 들어감)용으로 넉넉하게 잡힌 행 높이를
            # 유해요인 1개당 행 1개로 쪼갠 새 행들이 그대로 물려받으면, 짧은 유해요인은
            # 실제 내용보다 훨씬 큰 빈 여백이 아래에 남는다(실측 확인) — 한글 표는 이 값을
            # "최소" 높이로 다루므로 작게 줄여도 실제 내용이 더 길면 자동으로 늘어난다.
            for col in (0, 1, 2, 3):
                _set_cell_min_height(table.cell(row + k, col), 1200)

            # 같은 공정 안 유해요인 행 사이 경계선은 숨긴다 — 첫 행의 위쪽/마지막 행의
            # 아래쪽(다른 공정과의 경계)만 원래 테두리를 유지한다.
            hide_top = k > 0
            hide_bottom = k < hazard_count - 1
            if hide_top or hide_bottom:
                for cell in (cell_hazard, cell_prevention, cell_risk):
                    base_id = cell.element.get("borderFillIDRef")
                    if base_id:
                        new_id = _borderfill_hide_edges(doc, base_id, hide_top, hide_bottom, border_fill_cache)
                        cell.element.set("borderFillIDRef", new_id)

        # 마지막 유해요인이 아니면 끝에 빈 줄을 하나 더 둔다 — 같은 공정 안에서 유해요인
        # 행 사이 경계선을 숨기다 보니(위) 유해요인1의 예방대책들과 유해요인2가 바로 붙어
        # 보여 구분이 안 된다는 피드백(사용자 확인) — 세 칸(유해요인/예방대책/위험성) 모두
        # 똑같이 한 줄씩 여백을 둬야 다음 항목이 세 칸에서 계속 같은 줄에서 시작한다.
        trailing_gap = k < hazard_count - 1

        hazard_text = f"• {item.hazard}" if item and item.hazard else ""
        if trailing_gap:
            hazard_text += "\n"
        cell_hazard.text = hazard_text
        _set_cell_para_shape(cell_hazard, _PROCESS_HAZARD_PARA_PR)

        preventions = (
            [p.strip() for p in (item.prevention or "").split("\n") if p.strip()] if item else []
        )
        bullet_lines = [f"• {p}" for p in preventions]
        if trailing_gap:
            bullet_lines.append("")
        if bullet_lines:
            cell_prevention.set_text("\n".join(bullet_lines), split_paragraphs=True)
        else:
            cell_prevention.text = ""
        _set_cell_char_shape(cell_prevention, prevention_style)
        _set_cell_para_shape(cell_prevention, _PROCESS_PREVENTION_PARA_PR)

        risk_text = item.risk_level if item and item.risk_level else "-"
        if trailing_gap:
            risk_text += "\n"
        cell_risk.text = risk_text

        for cell in (cell_hazard, cell_prevention, cell_risk):
            _set_cell_vert_align(cell, "TOP")

    if hazard_count > 1:
        table.merge_cells(row, 0, row + hazard_count - 1, 0)
    table.cell(row, 0).text = entry.process_name


def fill_current_process_fields(doc, report: Report) -> None:
    """표12: 현재 진행공정에 대한 유해·위험요인 파악 및 대책."""
    entries = sorted(
        (e for e in report.current_process_entries if e.process_name), key=lambda e: e.slot
    )[:4]
    header_located = _locate_field_cell(doc, "t12_001")
    if header_located is None:
        return
    header_table, _row, _col = header_located
    # 데이터 유무와 무관하게 표 자체(헤더 포함)에 항상 적용한다 — 이전엔 첫 항목을 채울 때만
    # 실행돼서, 향후공정 데이터가 하나도 없는(전부 빈 칸) 보고서는 헤더 폭 조정이 안 먹는
    # 버그가 있었다(실측 확인). 행이 늘어나기 전에 먼저 해야 `insert_hazard_rows()`가
    # 복제하는 행도 조정된 폭을 그대로 물려받는다.
    _adjust_process_table_header(header_table, risk_width=4400, freed_each=933)

    border_fill_cache: dict = {}
    for i, entry in enumerate(entries):
        base = i * 4 + 1
        located = _locate_field_cell(doc, f"t12_{base:03d}")
        if located is None:
            continue
        table, row, _col = located
        _fill_process_entry_row(doc, table, row, entry, border_fill_cache)

    if entries:
        # 항목이 0개(전부 빈 칸)면 표를 그대로 유지하지만, 1개 이상 있는데 4개 미만이면
        # 채워지지 않은 나머지 슬롯은 빈 칸으로 남기지 않고 아예 지운다(사용자 요청).
        _remove_unused_process_slots(doc, "t12", len(entries))


def fill_future_process_summary_fields(doc, report: Report) -> None:
    """표14: "다음 방문시까지 발생하는 주요 진행공정 1~9" 요약 박스."""
    _put(doc, "t14_002", "2")
    _put(doc, "t14_006", "5")

    value_fields = ["t14_001", "t14_003", "t14_004", "t14_005", "t14_007", "t14_008", "t14_009", "t14_010", "t14_011"]
    names = [e.process_name for e in sorted(report.process_entries, key=lambda e: e.slot) if e.process_name]
    for i, field in enumerate(value_fields):
        _put(doc, field, names[i] if i < len(names) else "")


def fill_future_process_detail_fields(doc, report: Report) -> None:
    """표15: 향후 진행공정에 대한 유해·위험요인 파악 및 대책 — 표12와 동일 구조."""
    entries = sorted(
        (e for e in report.process_entries if e.process_name), key=lambda e: e.slot
    )[:4]
    header_located = _locate_field_cell(doc, "t15_001")
    if header_located is None:
        return
    header_table, _row, _col = header_located
    _adjust_process_table_header(header_table, risk_width=4400, freed_each=933)

    border_fill_cache: dict = {}
    for i, entry in enumerate(entries):
        base = i * 4 + 1
        located = _locate_field_cell(doc, f"t15_{base:03d}")
        if located is None:
            continue
        table, row, _col = located
        _fill_process_entry_row(doc, table, row, entry, border_fill_cache)

    if entries:
        _remove_unused_process_slots(doc, "t15", len(entries))
