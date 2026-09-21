"""사진 칸에 사진 대신 들어가는 안내 표시 — 칸의 대각선 테두리로 그린 X 틀 안의 문구, 그리고 "-".

`사진촬영 불가(보안 등)`(현장 정책으로 사진을 못 찍는 보고서), `이전회차 기술지도 사항 없음`, `개선 필요 이상의
위험성 없음`, `확인불가`/`보완필요`처럼 "칸 자체는 있어야 하는데 실제 사진이 없는" 경우에 쓴다. 한글 표 칸의 "대각선"
테두리(↘·↗ 두 줄)를 켜고 그 칸에 가운데 정렬된 글자를 넣는다 — 처음엔 X 틀 모양을 이미지로 그려 넣었지만
(Sub-phase 25), 칸 모서리에서 모서리까지 정확히 그어지고 벡터라 PDF에서도 흐려지지 않으며(한글 2018/2024 PDF는
이미지를 96dpi로 뭉갠다 — Sub-phase 26) 이미지 파일도 안 들어가서 사장님 제안(2026-09-21)으로 이 방식으로 바꿨다.
"""

from __future__ import annotations

import copy

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_DASH_PARA_PR_ID = "42"  # 가운데 정렬 문단 모양(위험성 표 헤더 칸과 같은 것)
_DIAGONAL_WIDTH = "0.12 mm"
_DIAGONAL_COLOR = "#000000"
_FRAME_TEXT_SIZE_PT = 11


def _diagonal_border_fill_id(doc, base_id: str) -> str:
    """`base_id` 테두리 설정을 복사해 대각선 두 줄(slash·backSlash)만 켠 새 설정의 id를 돌려준다.

    같은 기준 설정에서 만든 것은 문서 하나 안에서 재사용한다(칸마다 새로 만들지 않음)."""
    cache = doc.__dict__.setdefault("_diagonal_border_fill_ids", {})
    if base_id in cache:
        return cache[base_id]

    header = doc._root.headers[0]
    container = header._border_fills_element(create=True)
    base = next(bf for bf in container if bf.get("id") == base_id)
    clone = copy.deepcopy(base)
    new_id = header._allocate_border_fill_id(container)
    clone.set("id", new_id)
    for name in ("slash", "backSlash"):
        clone.find(f"{_HH}{name}").set("type", "CENTER")
    diagonal = clone.find(f"{_HH}diagonal")
    if diagonal is None:
        diagonal = clone.makeelement(f"{_HH}diagonal", {})
        clone.find(f"{_HH}bottomBorder").addnext(diagonal)
    diagonal.set("type", "SOLID")
    diagonal.set("width", _DIAGONAL_WIDTH)
    diagonal.set("color", _DIAGONAL_COLOR)
    container.append(clone)
    container.set("itemCnt", str(len(container)))
    header.mark_dirty()
    cache[base_id] = new_id
    return new_id


def put_frame_text(doc, cell, text: str) -> None:
    """칸(`cell`)에 X자 대각선 테두리를 켜고 가운데 정렬된 굵은 글자를 넣는다."""
    cell.element.set("borderFillIDRef", _diagonal_border_fill_id(doc, cell.element.get("borderFillIDRef")))
    paragraph = cell.paragraphs[0]
    paragraph.text = text
    paragraph.para_pr_id_ref = _DASH_PARA_PR_ID
    style_id = doc.ensure_run_style(bold=True, size=_FRAME_TEXT_SIZE_PT)
    for run in paragraph.runs:
        run.char_pr_id_ref = style_id
    cell.table.mark_dirty()


def put_dash(doc, cell) -> None:
    """사진이 없는 빈 칸에 가운데 정렬된 굵은 "-"를 넣는다."""
    paragraph = cell.paragraphs[0]
    paragraph.text = "-"
    paragraph.para_pr_id_ref = _DASH_PARA_PR_ID
    style_id = doc.ensure_run_style(bold=True, size=10)
    for run in paragraph.runs:
        run.char_pr_id_ref = style_id
