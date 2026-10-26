"""누름틀(칸) 찾기·채우기·표 칸 위치 빠르게 — 결과는 python-hwpx 원래 함수와 똑같이(2026-10-26 사용자 "속도도 중요하지만 정확도에서 조금이라도 문제가 생기면 안 돼").

python-hwpx는 칸 하나를 채울 때마다(`fill_form_field` — 고르려고 한 번, 결과를 돌려주려고 또 한 번) 또 첫 칸 찾기(`doc.fields.all`)마다 구역 전체를
파이썬 재귀로 훑고 칸 330개의 정보를 전부 새로 계산, 표 칸 위치(`table.cell`)는 칸 하나 볼 때마다 표 지도를 새로 그림 — 산안법 한 건 16초(작업내용.md 143차).
같은 결과를 내는 빠른 판:
① 칸 찾기(`_iter_form_field_matches` 바꿔 끼움): 문단 = lxml `iter("{*}p")`(재귀 판과 같은 차례·"이름공간 상관없이 p"), memogroup 안은 뺌,
   칸 길(run/ctrl/hp:fieldBegin)이 없는 문단은 건너뜀(문단 번호는 셈), 칸이 있는 문단은 원래 코드 그대로 → 결과 목록이 같음
② `fill_by_name`: 라이브러리 fill_form_field(name=)의 고르기·쓰기 그대로 — 칸 시작(hp:fieldBegin)을 바로 찾아 원래와 같은 자리(p/run/ctrl, memogroup 밖)인지 보고,
   이름은 칸마다 한 번 계산해 기억(칸 이름 = fieldBegin 속성·파라미터 — 채우기는 dirty만 바꾸고, 우리 코드는 칸 이름을 안 바꿈, 복사한 행은 칸 장치를 지움).
   "이름이 맞는 칸이 정확히 하나"일 때만 쓰므로 찾는 차례와 상관없음. 쓴 뒤 결과 보고용 두 번째 훑기는 뺌(문서를 안 바꾸는 읽기).
③ `first_field_begin`: `next(f for f in doc.fields.all if f.name == 이름)` — 그 이름 칸이 하나면 그 칸, 둘 이상이면 원래 차례(문단 차례)로 첫 칸
④ `cell_position`: `for r, c: try table.cell(r, c) … is tc` — 표 지도를 처음 볼 때 한 번만 그림(찾는 동안 문서가 안 바뀜), 지도 오류면 원래처럼 못 찾음
안전장치: 라이브러리 6.4.0이고 따라 한 함수 8개의 코드 지문이 검증한 것과 같을 때만 켬(install) — 라이브러리가 바뀌면 저절로 원래 판(느리지만 정확).
검증: 사진 번호(uuid4)를 고정하고 산안법 보고서 87건을 원래 판·빠른 판으로 만들어 한글 파일 바이트 비교(작업내용.md 144·145차).
"""
from __future__ import annotations

import hashlib
import inspect
from typing import Any, Iterator, NamedTuple

_VERIFIED_VERSION = "6.4.0"
_SOURCE_SHA = {  # 따라 한 라이브러리 함수 코드 지문(6.4.0) — fields 모듈
    "_iter_form_field_matches": "a6328052ca321ec9b5c962c16c31947cc59d340ad61347579def833f74382e7b",
    "fill_form_field": "68afa0f446e0c50fff50e1f97882ed50340b50216304be02f02bb508d2231657",
    "_select_form_field": "a669cc285dd92fa10a9c998f03038ea09ce0747f1b211a5c62cb0dba3e9246e9",
    "_form_field_payload": "68128d1ba4906b57b21e1dc02944588efd4ef12ce53f73ee0b0cde5e462c3df1",
    "list_form_fields": "7c3c4154ca4325bfd129da6ba1d07e2e832906962200ba7d935418a3cf863eba",
    "_form_field_from_match": "5c541daf44cd6ee1cc9026dda534c00a60e4ed2b6f96293d4b55b5384e127240",
}
_TABLE_SHA = {  # HwpxOxmlTable 메서드
    "cell": "6b3270c9f214e82d5239365a20b529a2d3e7e4eff8ac8f0453eea329b96372ad",
    "_grid_entry": "a235b514d56eac84b2180185ae8bd3c285d335b9f82c3668c94c3fbb0fad327b",
}

try:
    import hwpx as _hwpx
    from hwpx._document import fields as _f
    from hwpx.oxml.table import HwpxOxmlTable as _T
except Exception:  # noqa: BLE001 — 라이브러리가 없으면 아무것도 안 함
    _hwpx = _f = _T = None

_original = getattr(_f, "_iter_form_field_matches", None) if _f is not None else None
_FIELD_PATH = "{*}run/{*}ctrl/" + (_f._HP if _f is not None else "") + "fieldBegin"
_active = False


def _sha(func: Any) -> str:
    return hashlib.sha256(inspect.getsource(func).encode("utf-8")).hexdigest()


def verified() -> bool:
    """이 라이브러리가 검증한 판과 같은가(버전 + 따라 한 함수 코드 지문)."""
    if _f is None or _T is None or _original is None or getattr(_hwpx, "__version__", "") != _VERIFIED_VERSION:
        return False
    try:
        for name, sha in _SOURCE_SHA.items():
            if _sha(_original if name == "_iter_form_field_matches" else getattr(_f, name)) != sha:
                return False
        for name, sha in _TABLE_SHA.items():
            if _sha(getattr(_T, name)) != sha:
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


def _cache(doc: Any) -> dict | None:
    """칸 이름 기억(문서마다, fieldBegin 요소 → (이름, 안내문, 설명)) — 요소를 붙잡아 두니 같은 요소면 같은 키."""
    c = getattr(doc, "_kf_field_keys", None)
    if c is None:
        c = {}
        try:
            setattr(doc, "_kf_field_keys", c)
        except Exception:  # noqa: BLE001 — 붙일 수 없으면 기억 없이(매번 계산)
            return None
    return c


def _keys_of(field_begin: Any, cache: dict | None) -> tuple[str, str, str]:
    if cache is None:
        return _keys(field_begin)
    k = cache.get(field_begin)
    if k is None:
        k = cache[field_begin] = _keys(field_begin)
    return k


def _in_memogroup(p: Any, section_element: Any) -> bool:
    node = p.getparent()
    while node is not None and node is not section_element:
        if _f._local_name(node) == "memogroup":
            return True
        node = node.getparent()
    return False


def _direct(doc: Any) -> Iterator[tuple]:
    """_spots와 같은 칸들을 칸 시작(hp:fieldBegin)에서 바로 — (구역, 구역 번호, p, run, ctrl, fieldBegin). 차례는 문서 차례라 _spots와 다를 수 있음
    (표가 든 문단) — 차례가 상관없는 곳에만."""
    hp_fb = f"{_f._HP}fieldBegin"
    for section_index, section in enumerate(doc.sections):
        sec = section.element
        has_memo = sec.find(".//{*}memogroup") is not None
        for fb in sec.iter(hp_fb):
            ctrl = fb.getparent()
            if ctrl is None or _f._local_name(ctrl) != "ctrl":
                continue
            run = ctrl.getparent()
            if run is None or _f._local_name(run) != "run":
                continue
            p = run.getparent()
            if p is None or p is sec or _f._local_name(p) != "p":
                continue
            if has_memo and _in_memogroup(p, sec):
                continue
            if not _f._is_form_field_begin(ctrl, fb):
                continue
            yield section, section_index, p, run, ctrl, fb


def _spot_of(t: tuple) -> _Spot:
    """_direct 한 줄 → _payload에 넣을 자리(원래와 같은 runs·run 번호·ctrl 번호). 번호들(index 등)은 정보에만 들어가고 쓰기엔 안 씀."""
    section, section_index, p, run, ctrl, fb = t
    runs = [child for child in p if _f._local_name(child) == "run"]
    run_index = next(i for i, r in enumerate(runs) if r is run)
    child_index = next(i for i, c in enumerate(list(run)) if c is ctrl)
    return _Spot(-1, section, section_index, -1, -1, p, runs, run_index, child_index, ctrl, fb)


# ---------- ② 채우기 ----------
def fill_by_name(doc: Any, name: str, value: Any) -> None:
    """`doc.fill_form_field(value, name=name)`와 같은 일 — 없으면 LookupError("field-not-found"), 둘 이상이면 LookupError("field-ambiguous")
    (라이브러리처럼 쓰기 전에). 고르기 = _select_form_field(name=) 규칙(이름·안내문·설명 중 하나가 같음, 대소문자·앞뒤 빈칸 무시),
    쓰기 = fill_form_field의 fit_policy 없는 길 그대로."""
    wanted = (name or "").strip().casefold()
    cache = _cache(doc)
    hits = []
    if wanted:
        for t in _direct(doc):
            n, p, ins = _keys_of(t[5], cache)
            if wanted in {str(n).strip().casefold(), str(p).strip().casefold(), str(ins).strip().casefold()}:
                hits.append(t)
                if len(hits) > 1:
                    break
    if not hits:
        raise LookupError("field-not-found")
    if len(hits) > 1:
        raise LookupError("field-ambiguous")
    match = _payload(doc, _spot_of(hits[0]))
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
    cache = _cache(doc)
    found = [t[5] for t in _direct(doc) if _keys_of(t[5], cache)[0] == field_name]
    if not found:
        return None
    if len(found) == 1:
        return found[0]
    for s in _spots(doc):  # 같은 이름이 둘 이상 — 원래 차례(문단 차례)로 첫 칸
        if _keys_of(s.field_begin, cache)[0] == field_name:
            return s.field_begin
    return None


# ---------- ④ 표 칸 위치 ----------
_UNSET = object()


def cell_position(table: Any, tc_node: Any) -> tuple[int, int] | None:
    """`for r in range(row_count): for c in range(column_count): try: cell = table.cell(r, c) except: continue; if cell.element is tc_node`
    과 같은 (r, c) — table.cell이 부를 때마다 새로 그리는 표 지도(_build_cell_grid)를 처음 볼 때 한 번만(찾는 동안 문서가 안 바뀜).
    지도를 그리다 오류면 원래도 칸마다 오류 → 못 찾음(None)."""
    grid: Any = _UNSET
    for r in range(table.row_count):
        for c in range(table.column_count):
            if grid is _UNSET:
                try:
                    grid = table._build_cell_grid()
                except Exception:  # noqa: BLE001
                    grid = None
            if grid is None:
                continue
            entry = grid.get((r, c))
            if entry is not None and entry.cell.element is tc_node:
                return r, c
    return None
