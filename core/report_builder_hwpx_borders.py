"""보고서 안 모든 표의 테두리 굵기·좌우 위치를 한 규칙으로 통일한다(사용자 요청 2026-09-21).

템플릿의 표들은 굵기가 제각각이었다 — 3번 사진 표는 선이 전부 굵고, 4번/8번/5·6번 표는 전부 얇고, 2번 표만 "바깥 굵게·안쪽 얇게"였다.
규칙: **표 맨 바깥 테두리만 0.4mm, 안쪽 선은 0.12mm.** 칸의 배경색·대각선(X 틀)·"선 없음"(NONE) 설정은 그대로 두고 선 굵기만 바꾼다.
표 안에 넣은 표(10번 기준표 2개)도 각자 하나의 표로 보고 같은 규칙을 적용한다.

같은 이유로 좌우 위치도 맞춘다 — 4번 이전지적사항 첫째 표만 바깥 여백이 283이고 나머지가 141이라 0.5mm씩 어긋나 있었다.
모든 채우기가 끝난 뒤 마지막에 한 번 부른다(빈 슬롯 표 삭제 등이 모두 끝난 상태에서 실제로 남은 표만 대상).
"""

from __future__ import annotations

import copy

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_THICK_MM = 0.4
_THIN_MM = 0.12
_SIDES = ("left", "right", "top", "bottom")
_STANDARD_OUT_MARGIN = "283"  # 대부분의 표(1번·2번·3번·10번 등)가 쓰는 좌우 바깥 여백


def _width_mm(width_attr: str | None) -> float:
    try:
        return float((width_attr or "0").split()[0])
    except ValueError:
        return 0.0


def _is_nested(tbl) -> bool:
    return any(a.tag == f"{_HP}tc" for a in tbl.iterancestors())


def _border_fill_index(header) -> tuple[object, dict[str, object]]:
    container = header._border_fills_element(create=False)
    by_id = {}
    if container is not None:
        for element in container:
            if isinstance(element.tag, str) and element.tag.endswith("}borderFill"):
                by_id[element.get("id")] = element
    return container, by_id


def _styled_copy_id(container, by_id, cache, original_id: str, outer: tuple[bool, ...]) -> str:
    """`original_id` 모양에서 바깥 변은 굵게, 안쪽 변은 얇게 바꾼 borderFill의 id(없으면 복제해서 만든다)."""
    key = (original_id, outer)
    if key in cache:
        return cache[key]
    original = by_id[original_id]
    clone = copy.deepcopy(original)
    changed = False
    for side, is_outer in zip(_SIDES, outer):
        border = next(
            (c for c in clone if isinstance(c.tag, str) and c.tag.endswith(f"}}{side}Border")), None
        )
        if border is None or border.get("type") == "NONE":
            continue
        target = _THICK_MM if is_outer else _THIN_MM
        if abs(_width_mm(border.get("width")) - target) > 1e-6:
            border.set("width", f"{target} mm")
            changed = True
    if not changed:
        cache[key] = original_id
        return original_id
    new_id = str(max(int(i) for i in by_id) + 1)
    clone.set("id", new_id)
    container.append(clone)
    by_id[new_id] = clone
    container.set("itemCnt", str(len(by_id)))
    cache[key] = new_id
    return new_id


def _normalize_borders(tbl, container, by_id, cache) -> bool:
    rows, cols = int(tbl.get("rowCnt", 0)), int(tbl.get("colCnt", 0))
    changed = False
    for tr in tbl.findall(f"{_HP}tr"):
        for tc in tr.findall(f"{_HP}tc"):
            original_id = tc.get("borderFillIDRef")
            addr, span = tc.find(f"{_HP}cellAddr"), tc.find(f"{_HP}cellSpan")
            if original_id not in by_id or addr is None:
                continue
            col, row = int(addr.get("colAddr")), int(addr.get("rowAddr"))
            col_span = int(span.get("colSpan", 1)) if span is not None else 1
            row_span = int(span.get("rowSpan", 1)) if span is not None else 1
            outer = (col == 0, col + col_span >= cols, row == 0, row + row_span >= rows)
            new_id = _styled_copy_id(container, by_id, cache, original_id, outer)
            if new_id != original_id:
                tc.set("borderFillIDRef", new_id)
                changed = True
    return changed


def _align_left_right(tbl) -> bool:
    """글자처럼 취급되는 최상위 표의 좌우 바깥 여백(141/283 혼재)과 위치 보정을 통일한다."""
    changed = False
    out = next((c for c in tbl if isinstance(c.tag, str) and c.tag.endswith("}outMargin")), None)
    if out is not None:
        for side in ("left", "right"):
            if out.get(side) == "141":
                out.set(side, _STANDARD_OUT_MARGIN)
                changed = True
    pos = next((c for c in tbl if isinstance(c.tag, str) and c.tag.endswith("}pos")), None)
    if pos is not None and pos.get("treatAsChar") == "1" and pos.get("horzOffset") in ("2", "3"):
        pos.set("horzOffset", "0")
        changed = True
    return changed


def normalize_table_styles(doc) -> None:
    header = doc.parts.headers[0]
    container, by_id = _border_fill_index(header)
    cache: dict = {}
    header_changed = False
    for section in doc.sections:
        section_changed = False
        for tbl in list(section.element.iter(f"{_HP}tbl")):
            before = len(by_id)
            if container is not None and _normalize_borders(tbl, container, by_id, cache):
                section_changed = True
            header_changed = header_changed or len(by_id) != before
            if not _is_nested(tbl) and _align_left_right(tbl):
                section_changed = True
        if section_changed:
            section.mark_dirty()
    if header_changed:
        header.mark_dirty()
