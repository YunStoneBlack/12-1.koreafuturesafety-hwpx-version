"""누름틀(칸) 찾기·채우기 빠르게 — 결과는 python-hwpx 원래 함수와 똑같이(2026-10-26 사용자 "속도도 중요하지만 정확도에서 조금이라도 문제가 생기면 안 돼").

python-hwpx는 칸 하나를 채울 때마다(`fill_form_field` — 고르려고 한 번, 결과를 돌려주려고 또 한 번) 또 첫 칸 찾기(`doc.fields.all`)마다 구역 전체를
파이썬 재귀로 훑고 칸 330개의 정보(이름·현재 값·위치)를 전부 새로 계산 — 산안법 보고서 한 건 PDF 22초 중 16초(작업내용.md 143차). 같은 결과를 내는 빠른 판:
① 칸 찾기(`_iter_form_field_matches` 바꿔 끼움): 문단 = lxml `iter("{*}p")`(C로 앞에서부터 — 재귀 판과 같은 차례·"이름공간 상관없이 p"), memogroup 안은 뺌,
   칸 길(run/ctrl/hp:fieldBegin)이 없는 문단은 건너뜀(문단 번호는 그대로 셈), 칸이 있는 문단은 원래 코드 그대로 → 결과 목록이 같음(87건 63,178번 대조 0건 다름)
② `fill_by_name`: 라이브러리 fill_form_field(name=)의 고르기·쓰기를 그대로 — 이름이 맞는 칸만 자세히 계산, 쓴 뒤 결과 보고용 두 번째 훑기는 뺌(문서를 안 바꾸는 읽기)
③ `first_field_begin`: `next(f for f in doc.fields.all if f.name == 이름)`과 같은 칸 — 앞에서부터 보다 처음 맞으면 멈춤
안전장치: 라이브러리 6.4.0이고 따라 한 함수 6개의 코드 지문이 검증한 것과 같을 때만 켬(install) — 라이브러리가 바뀌면 저절로 원래 판(느리지만 정확).
검증: 사진 번호(uuid4)를 고정하고 산안법 보고서 87건을 원래 판·빠른 판으로 만들어 한글 파일 바이트 비교(작업내용.md 144차).
"""
from __future__ import annotations

import hashlib
import inspect
from typing import Any, Iterator, NamedTuple

_VERIFIED_VERSION = "6.4.0"
_SOURCE_SHA = {  # 따라 한 라이브러리 함수 코드 지문(6.4.0)
    "_iter_form_field_matches": "a6328052ca321ec9b5c962c16c31947cc59d340ad61347579def833f74382e7b",
    "fill_form_field": "68afa0f446e0c50fff50e1f97882ed50340b50216304be02f02bb508d2231657",
    "_select_form_field": "a669cc285dd92fa10a9c998f03038ea09ce0747f1b211a5c62cb0dba3e9246e9",
    "_form_field_payload": "68128d1ba4906b57b21e1dc02944588efd4ef12ce53f73ee0b0cde5e462c3df1",
    "list_form_fields": "7c3c4154ca4325bfd129da6ba1d07e2e832906962200ba7d935418a3cf863eba",
    "_form_field_from_match": "5c541daf44cd6ee1cc9026dda534c00a60e4ed2b6f96293d4b55b5384e127240",
}

try:
    import hwpx as _hwpx
    from hwpx._document import fields as _f
except Exception:  # noqa: BLE001 — 라이브러리가 없으면 아무것도 안 함
    _hwpx = _f = None

_original = getattr(_f, "_iter_form_field_matches", None) if _f is not None else None
_FIELD_PATH = "{*}run/{*}ctrl/" + (_f._HP if _f is not None else "") + "fieldBegin"
_active = False


def verified() -> bool:
    """이 라이브러리가 검증한 판과 같은가(버전 + 따라 한 함수 코드 지문)."""
    if _f is None or _original is None or getattr(_hwpx, "__version__", "") != _VERIFIED_VERSION:
        return False
    try:
        for name, sha in _SOURCE_SHA.items():
            func = _original if name == "_iter_form_field_matches" else getattr(_f, name)
            if hashlib.sha256(inspect.getsource(func).encode("utf-8")).hexdigest() != sha:
                return False
    except (OSError, TypeError, AttributeError):
        return False
    return True


def active() -> bool:
    return _active


def install() -> bool:
    """검증한 라이브러리면 빠른 판으로(여러 번 불러도 됨). 켰으면 True."""
    global _active
    if not verified():
        return False
    _f._iter_form_field_matches = fast_iter_form_field_matches
    _active = True
    return True


def uninstall() -> None:
    global _active
    if _f is not None and _original is not None:
        _f._iter_form_field_matches = _original
    _active = False


# ---------- ① 칸 찾기 ----------
def _content_paragraphs(section_element: Any) -> Iterator[Any]:
    """재귀 판 iter_content_paragraphs와 같은 문단을 같은 차례로 — 자기 자신은 안 냄, memogroup 안은 뺌."""
    skip: set = set()
    for memo in section_element.iter("{*}memogroup"):
        if memo is not section_element:
            skip.update(memo.iter("{*}p"))
    for p in section_element.iter("{*}p"):
        if p is section_element or (skip and p in skip):
            continue
        yield p


class _Spot(NamedTuple):
    """칸 하나의 자리 — 원래 _iter_form_field_matches가 payload를 만들 때 쓰는 값들."""
    index: int
    section: Any
    section_index: int
    paragraph_index: int
    paragraph_index_in_section: int
    paragraph_element: Any
    runs: list
    run_index: int
    child_index: int
    ctrl: Any
    field_begin: Any


def _spots(doc: Any) -> Iterator[_Spot]:
    """문서의 칸을 원래와 같은 차례로(정보 계산 없이 자리만) — index = 원래 목록의 번호."""
    index = 0
    paragraph_index = 0
    for section_index, section in enumerate(doc.sections):
        direct_indexes = {paragraph.element: i for i, paragraph in enumerate(section.paragraphs)}
        for paragraph_element in _content_paragraphs(section.element):
            if paragraph_element.find(_FIELD_PATH) is not None:
                runs = [child for child in paragraph_element if _f._local_name(child) == "run"]
                for run_index, run in enumerate(runs):
                    for child_index, child in enumerate(list(run)):
                        if _f._local_name(child) != "ctrl":
                            continue
                        for field_begin in child.findall(f"{_f._HP}fieldBegin"):
                            if not _f._is_form_field_begin(child, field_begin):
                                continue
                            yield _Spot(index, section, section_index, paragraph_index, direct_indexes.get(paragraph_element, -1),
                                        paragraph_element, runs, run_index, child_index, child, field_begin)
                            index += 1
            paragraph_index += 1


def _payload(doc: Any, s: _Spot) -> dict[str, Any]:
    """칸 하나의 정보 — 원래 _iter_form_field_matches의 안쪽 그대로(라이브러리 내부 함수 그대로 부름)."""
    paragraph = _f.HwpxOxmlParagraph(s.paragraph_element, s.section)
    end_position = _f._find_field_end_position(doc, s.runs, begin_run_index=s.run_index, begin_child_index=s.child_index,
                                               field_begin=s.field_begin)
    end_run_index: int | None = None
    end_child_index: int | None = None
    if end_position is not None:
        end_run_index, end_child_index, _field_end = end_position
    text_nodes = _f._field_text_nodes(doc, s.runs, begin_run_index=s.run_index, begin_child_index=s.child_index,
                                      end_run_index=end_run_index, end_child_index=end_child_index)
    current_value = "".join("".join(node.itertext()) for node in text_nodes)
    payload = _f._form_field_payload(
        doc, index=s.index, section_index=s.section_index, paragraph_index=s.paragraph_index,
        paragraph_index_in_section=s.paragraph_index_in_section, run_index=s.run_index, child_index=s.child_index,
        ctrl=s.ctrl, field_begin=s.field_begin, current_value=current_value, has_end=end_position is not None,
    )
    payload["_paragraph"] = paragraph
    payload["_runs"] = s.runs
    payload["_begin_run_index"] = s.run_index
    payload["_begin_child_index"] = s.child_index
    payload["_end_run_index"] = end_run_index
    payload["_end_child_index"] = end_child_index
    payload["_text_nodes"] = text_nodes
    return payload


def fast_iter_form_field_matches(doc: Any) -> list[dict[str, Any]]:
    return [_payload(doc, s) for s in _spots(doc)]


# ---------- 이름(_form_field_payload의 name·prompt·instruction 계산 그대로) ----------
def _name(field_begin: Any, parameters: list) -> str:
    name = _f._first_attr(field_begin, _f._FORM_FIELD_NAME_ATTRS)
    if not name:
        name = _f._field_parameter_value(parameters, "fieldName", "fieldname", "field_name", "name", "title")
    return name


def _keys(field_begin: Any) -> tuple[str, str, str]:
    parameters = _f._field_parameters(field_begin)
    name = _name(field_begin, parameters)
    prompt = _f._first_attr(field_begin, _f._FORM_FIELD_PROMPT_ATTRS)
    if not prompt:
        prompt = _f._field_parameter_value(parameters, "Direction", *_f._FORM_FIELD_PARAM_NAMES)
    instruction = _f._field_parameter_value(parameters, "instruction", "guide", "help", "description", "desc")
    if not instruction:
        instruction = prompt
    return name, prompt, instruction


# ---------- ② 채우기 ----------
def fill_by_name(doc: Any, name: str, value: Any) -> None:
    """`doc.fill_form_field(value, name=name)`와 같은 일 — 없으면 LookupError("field-not-found"), 둘 이상이면 LookupError("field-ambiguous")
    (라이브러리처럼 쓰기 전에). 고르기 = _select_form_field(name=) 규칙(이름·안내문·설명 중 하나가 같음, 대소문자·앞뒤 빈칸 무시),
    쓰기 = fill_form_field의 fit_policy 없는 길 그대로."""
    wanted = (name or "").strip().casefold()
    hit = None
    count = 0
    for s in _spots(doc):
        n, p, ins = _keys(s.field_begin)
        if wanted and wanted in {str(n).strip().casefold(), str(p).strip().casefold(), str(ins).strip().casefold()}:
            count += 1
            if hit is None:
                hit = s
    if count == 0:
        raise LookupError("field-not-found")
    if count > 1:
        raise LookupError("field-ambiguous")
    match = _payload(doc, hit)
    paragraph = match["_paragraph"]
    runs = match["_runs"]
    write_value = str(value)
    text_nodes: list[Any] = match.get("_text_nodes", [])
    sanitized = _f._sanitize_field_text(write_value)
    if text_nodes:
        primary = text_nodes[0]
        primary.text = sanitized
        for child in list(primary):
            child.tail = ""
        for node in text_nodes[1:]:
            node.text = ""
            for child in list(node):
                child.tail = ""
        if match.get("is_placeholder"):
            begin_run = runs[int(match["_begin_run_index"])]
            begin_ref = begin_run.get("charPrIDRef")
            primary_run = primary.getparent()
            if begin_ref is not None and primary_run is not None:
                primary_run.set("charPrIDRef", begin_ref)
    else:
        _f._insert_form_field_text_run(doc, match, sanitized)
    field_begin = match.get("_field_begin")
    if field_begin is not None:
        field_begin.set("dirty", "1")
    _f._clear_form_field_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()


# ---------- ③ 첫 칸 ----------
def first_field_begin(doc: Any, field_name: str) -> Any | None:
    """`next((f for f in doc.fields.all if f.name == field_name), None).element`과 같은 fieldBegin(없으면 None)."""
    for s in _spots(doc):
        if _name(s.field_begin, _f._field_parameters(s.field_begin)) == field_name:
            return s.field_begin
    return None
