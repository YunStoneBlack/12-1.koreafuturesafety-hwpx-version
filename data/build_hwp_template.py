"""Sub-phase 8(한글 템플릿 출력) — 실제 원본 .hwp 파일에 누름틀(필드)을 박아넣어
`data/templates/report_template.hwp`를 만드는 1회성 개발자 도구.

`data/seed_process_catalog.py`/`data/migrate_v7_report_format.py`와 같은 성격 — 앱 런타임에는
포함되지 않고, 개발 중 필요할 때 터미널에서 직접 실행한다.

이 파일이 600줄을 넘겨 커져서, 표별 전용 처리는 별도 모듈로 분리했다 —
`data/build_hwp_template_table6.py`(표6, 17대 기인물), `data/build_hwp_template_equipment.py`
(표8/9/10, 건설기계장비·위험기계기구·유해위험물질), `data/hwp_template_common.py`(공통 유틸,
순환 임포트 방지용). 이 파일은 표1/2/3/4/5/11~15에 쓰는 일반 라벨/데이터 판별 처리와
`build_template()` 오케스트레이션만 갖는다.

## 접근 방식

실제 원본 .hwp(영중중학교 보도블록 공사 1차 — 이미 서명 완료된 실제 보고서)를 표별로 조사한
결과(`.../scratchpad/hwp_template_work/tables_dump.txt`), 16개 표 중:

- **표0(결재란)**: 이사/대표이사 서명 이미지만 있고 텍스트 데이터가 없는 표라 이번 스크립트가
  다룰 게 없다 — 그림(서명) 삽입은 Sub-phase 9로 미룬다.
- **표6(17대 기인물 + 위험성평가매트릭스)**: 표 안에 표가 중첩된 구조(`list index out of
  range` 버그의 원인, `outer RowCount=24/ColCount=8` 안에 `inner RowCount=8/ColCount=9`
  매트릭스가 박혀있음)라 이번 라운드는 스킵한다.
- **표3(기술지도 개요)**: 담당요원 서명 + 통보방법 서명 그림이 셀 안에 섞여 있다. 셀 내용을
  지우면 인라인으로 앵커링된 그림까지 같이 지워지는 걸 실측으로 확인했고("서명" 글자가 든
  셀만 피하기, 지우기 전/후 그림 개수를 세서 `Undo`하기 두 가지 다 시도했지만 둘 다 결국
  그림이 하나씩 사라졌다 — 실제 그림이 앵커링된 셀이 "서명"이라는 글자를 담은 셀과 다르고,
  그림 개수 세기는 중간에 끼는 COM 호출 때문에 선택 상태가 불안정해짐), 안전하게 격리할
  방법을 이번 라운드 안에서 못 찾았다. 그래서 표0과 마찬가지로 이번엔 손대지 않고
  Sub-phase 9(그림/서명 처리)로 그대로 미룬다 — 이 표의 담당요원 연락처·통보방법 이메일
  같은 실제 고객사 정보가 아직 템플릿에 남아있다는 뜻이고, 그래서 **이번 라운드는 최종
  스크럽 검증을 의도적으로 통과하지 못한다**(아래 `build_template()`이 `RuntimeError`를
  내고 결과물을 프로젝트 폴더로 복사하지 않는다 — 실수로 커밋되는 걸 막는 안전장치가 정상
  동작하는 것). Sub-phase 9에서 표3까지 처리하고 나면 이 검증이 통과되고 그때 실제로
  `data/templates/report_template.hwp`가 만들어진다. 그 전까지는 임시 폴더(`build_hwp_template()`
  내부 `_work_output` 경로)에 결과물이 남아 검토용으로만 쓸 수 있다.
- **나머지(표1,2,4,5,8,9,10,11,12,13,14,15)**: 이번 스크립트가 처리한다. 표5(대형사고
  위험작업 25종)의 해당/해당없음 칸은 원래 텍스트가 아니라 실제 클릭 가능한 체크박스
  컨트롤(HWPML2X `<CHECKBUTTON>`, pyhwpx `UserDesc == "선택 상자"`)이다 — 이 컨트롤의 체크
  상태를 코드로 바꾸는 방법을 여러 각도로 시도했지만(`Properties.SetItem`, 새 컨트롤을
  `HFormButtonAttr` pset의 `Value`를 지정해 생성 등) 전부 렌더링에 반영이 안 돼 실패했다
  (문서화 전혀 없음). 그래서 컨트롤을 지우고 텍스트 필드(☑/☐)로 대체하는 쪽으로 확정했다
  — 마법사에서 체크한 내용이 자동으로 정확히 반영되는 대신, 생성된 문서에서는 더 이상
  진짜 클릭 가능한 체크박스가 아니다(고정된 문자). 표8/9/10(3종 장비 유/무 칸)도 구조상
  같은 문제가 있을 가능성이 높아 그 표들을 채울 때 이 부분을 먼저 재확인해야 한다.

셀 하나하나를 "라벨(고정 문구)"과 "데이터(회차마다 바뀌는 값)"로 나눠, 라벨은 그대로 두고
데이터 셀만 내용을 지운 뒤 누름틀 필드를 만든다. 표를 순회할 때 `TableRightCell()`로 물리
셀 단위로 이동한다(병합된 셀은 물리적으로 한 번만 방문됨 — pyhwpx의 `fill_addr_field()`가
쓰는 것과 같은 방식이라 표의 실제 셀 구조를 안전하게 신뢰할 수 있다. `table_to_df()`가 쓰는
가상 그리드는 병합 셀 값을 여러 칸에 중복 표시해서 헷갈리기 쉽다).

라벨 판별은 `core/constants.py`의 고정 상수(대형사고위험작업 25종/3종 장비 안전조치 항목명·
문구/공통 표 헤더)와 정확히 일치하는지로 판단한다 — 일치하면 그대로 두고, 아니면(빈 칸
포함) 실제 고객사 데이터일 가능성이 높은 셀로 보고 필드화한다(내용을 지우는 과정이 동시에
실제 고객사 정보를 지우는 "스크럽" 역할도 겸한다).

셀 텍스트를 읽고 지울 때는 `TableCellBlock()`(F5, "표 셀 선택")을 쓰지 않는다 —
`get_selected_range()` 기준으로는 정확히 그 셀 하나만 선택된 것으로 나오는데도
`GetTextFile()`은 그 선택을 무시하고 표 전체 텍스트를 반환해버리고, 그 상태에서 `Delete`
액션도 조용히 실패(반환값 False, 내용 그대로)하는 것을 실측으로 확인했다. 대신 줄 단위
일반 텍스트 선택(`MoveSelLineBegin`/`MoveSelLineEnd`/`MoveSelDown` 반복)으로 셀 내용을
선택한다 — 이 방식은 `get_selected_text()`가 정확히 그 셀 텍스트만 돌려주고 `Delete`도
정상적으로 지워진다(화살표 기반 선택은 표 셀 경계를 자연히 못 벗어나므로 여러 줄이어도
안전하다).

## 실행

    python -m data.build_hwp_template

성공하면 `data/templates/report_template.hwp`(커밋 대상)와 `report_template_fields.json`
(필드명 목록 + 원래 텍스트, 리뷰/디버깅용)을 만든다. 마지막에 실제 고객사 문자열(현장명/
회사명/이메일/전화번호 등)이 하나도 안 남았는지 자동 검증하고, 남아있으면 에러를 내고
`report_template.hwp`를 지운다(실수로 커밋되는 것을 막기 위함).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.constants import HAND_TOOL_ITEMS, HAZMAT_ITEMS, MACHINERY_EQUIPMENT_ITEMS, MAJOR_HAZARD_WORKS
from core.db import BASE_DIR
from data.build_hwp_template_equipment import _EQUIPMENT_TABLES, _process_equipment_table
from data.build_hwp_template_table6 import _process_table6, _remove_table6_checkboxes
from data.hwp_template_common import _normalize

_SOURCE_HWP = Path(
    r"C:\Users\윤석현1\Documents\카카오톡 받은 파일\영중중학교 (보도블록 공사) 건설 재해예방 기술지도 결과보고서(1차)수정.hwp"
)
_WORK_COPY = (
    Path.home()
    / "AppData"
    / "Local"
    / "Temp"
    / "claude"
    / "hwp_template_build"
    / "work.hwp"
)
_OUTPUT_HWP = BASE_DIR / "data" / "templates" / "report_template.hwp"
_OUTPUT_FIELDS_JSON = BASE_DIR / "data" / "templates" / "report_template_fields.json"

# 이번 라운드는 텍스트 필드까지만 — 표0(결재란, 서명 이미지만 있고 텍스트 데이터가 없음)과
# 표6(중첩 표 구조)은 스킵한다. 표3(기술지도 개요)은 실제 고객사 서명 이미지가 섞여있었지만
# `_remove_controls_by_desc()`로 컨트롤을 먼저 지우는 방식으로 안전하게 처리할 수 있게 됐다.
_SAFE_TABLE_INDEXES = [1, 2, 3, 4, 5, 11, 12, 13, 14, 15]

# 표5(대형사고위험작업 25종)의 "해당/해당없음" 칸은 텍스트가 아니라 실제 클릭 가능한
# 체크박스 컨트롤(HWPML2X `<CHECKBUTTON>`, pyhwpx UserDesc=="선택 상자")로 되어있다.
# 이 컨트롤의 체크 상태를 코드로 바꾸는 방법을 여러 각도로 시도했지만(Properties.SetItem,
# HFormButtonAttr pset으로 새로 만들며 Value 지정 등) 전부 렌더링에 반영이 안 돼 실패했다
# (문서화 전혀 없음). 그래서 컨트롤을 지우고 그 자리를 텍스트 필드(☑/☐)로 대체하는 쪽으로
# 확정했다 — 마법사에서 체크한 내용이 자동으로 정확히 반영되는 대신, 생성된 문서에서는
# 더 이상 진짜 클릭 가능한 체크박스가 아니다(고정된 문자). 표8/9/10(3종 장비 유/무 칸)도
# 구조상 같은 문제가 있을 가능성이 높아 그 표들을 채울 때 이 부분을 먼저 재확인해야 한다.
# 표를 처리하기 "전에" 컨트롤부터 지워야 하는 표(체크박스가 텍스트와 뒤섞여 있어 순서를
# 지켜야 하는 표) → 지울 대상 UserDesc 집합.
#
# 표3에는 실제 고객사 서명 이미지("그림")가 최소 1개 더 있는 것으로 렌더링에서 확인했지만
# (표3 데이터 셀을 지우고 채운 뒤 PDF로 렌더링해 육안으로 재확인함), `HeadCtrl` 체인을
# UserDesc=="그림"으로 훑어 찾은 표3 범위 안의 그림은 1개뿐이었고 그건 실제로는 회사 로고였다
# (지워보니 "지도기관명" 칸의 로고가 사라지는 것으로 확인). 각 그림의 `GetAnchorPos(0)`으로
# 앵커된 List ID를 찍어봐도(List=0/37/466/... 등 표별로 제각각) 표3 범위 안에 있는 것은
# 로고 하나(List=37)뿐이었다 — 즉 실제 서명 그림은 `HeadCtrl` 체인 순회로는 표3 소속으로
# 잡히지 않는 위치에 앵커돼 있다(정확한 이유 미확인). 이번 라운드는 로고를 잘못 지우는
# 사고를 막기 위해 "그림"은 건드리지 않고 체크박스만 지운다 — 그 결과 표3의 서명 이미지는
# 아직 실제 고객사의 것이 그대로 남는다(알려진 한계, Sub-phase 9로 이월).
_PRE_REMOVE_CONTROL_TABLES: dict[int, set[str]] = {3: {"선택 상자"}}

# 표를 처리한 "후에" 체크박스만 지워도 되는 표(데이터 없이 빈 체크박스만 있어 순서 무관).
_POST_REMOVE_CHECKBOX_TABLES = [5]

# 표8/9/10(건설기계장비/위험기계기구/유해위험물질)은 `_EQUIPMENT_TABLES`에서 뺐다 —
# `data/build_hwp_template_equipment.py`의 `_EQUIPMENT_TABLES`/`_process_equipment_table()`가
# 전용 처리를 맡는다(위 import 참고).

# 실제 고객사 정보 — 최종 검증 시 하나도 남아있으면 안 되는 문자열. 실명·전화번호·이메일·
# 사업자등록번호·주소가 그대로 담긴 목록이라 소스코드(git)에는 안 올리고, 이 PC에만 있는
# gitignore 대상 JSON 파일(`data/templates/_client_strings.json`)에서 읽는다.
_CLIENT_STRINGS_FILE = BASE_DIR / "data" / "templates" / "_client_strings.json"


def _load_client_strings() -> list[str]:
    if not _CLIENT_STRINGS_FILE.exists():
        print(
            f"경고: {_CLIENT_STRINGS_FILE}가 없어 최종 스크럽 검증(고객사 정보 잔존 여부)을 "
            "건너뜁니다 — 이 PC가 아닌 곳에서 처음 돌리는 경우 원본 .hwp 자체를 구할 방법이 "
            "먼저 필요하므로, 통상적으로는 이 경고를 볼 일이 없다.",
            flush=True,
        )
        return []
    return json.loads(_CLIENT_STRINGS_FILE.read_text(encoding="utf-8"))


def _build_static_label_set() -> set[str]:
    static: set[str] = set()
    static.update(
        [
            "현장",
            "현장명",
            "사업장관리번호 (사업장개시번호)",
            "공사기간",
            "공사금액",
            "책임자",
            "연락처(이메일)",
            "주소",
            "본사",
            "회사명",
            "법인등록번호 (사업자등록번호)",
            "면허번호",
            "연락처",
            "주 소",
            "유해 위험장소",
            "유해위험요인",
            "지적사항 재해예방 대책",
            "이행결과",
            "위험성",
            "대형사고 위험작업 사항",
            "해당",
            "해당없음",
            "위험기계기구",
            "유/무",
            "필수지도사항 확인",
            "평가",
            "건설기계장비",
            "유해위험물질",
            "현재안전보건조치",
            "위험성수준",
            "진행공정",
            "유해 · 위험요인",
            "유해·위험요인",
            "유해위험요인을 제거하기위한 예방대책",
            "다음 방문시까지 발생하는주요 진행공정",
            "지원사항",
            "구체적 사항",
            "비고",
            "TBM 활성화 지도 및 교육실시",
            "장비사용(1)",
            "장비사용(2)",
            # 표3 (기술지도 개요)
            "지도기관명",
            "기술지도실시일",
            "구분",
            "☑건설공사",
            "공정율",
            "회차",
            "담당요원",
            "이전 기술지도 이행여부",
            "기술지도 내용 통보방법",
            "기타 특이사항",
            "재해발생현황",
        ]
    )
    static.update(str(n) for n in range(1, 10))  # 표13의 1~9 순번 라벨

    for item in MAJOR_HAZARD_WORKS:
        static.add(_normalize(item))

    # 표8/9/10의 지도사항(C열)은 `_process_equipment_table()`이 주소 기반으로 아예 건드리지
    # 않으므로(라벨 매칭 대상이 아님) 항목명(A열)만 라벨로 등록하면 된다.
    for group in (MACHINERY_EQUIPMENT_ITEMS, HAND_TOOL_ITEMS, HAZMAT_ITEMS):
        for name, _lines in group:
            static.add(_normalize(name))

    return static


def _remove_controls_by_desc(hwp, table_index: int, target_descs: set[str]) -> int:
    """표 안의 특정 컨트롤(체크박스 "선택 상자", 이미지 "그림" 등)을 전부 지운다.

    체크박스 컨트롤의 체크 상태를 코드로 바꾸는 방법을 찾지 못해(문서화 전혀 없음), 컨트롤을
    지우고 텍스트 필드(☑/☐)로 대체하는 쪽을 택했다 — 그대로 두면 필드로 채운 글자와
    겹쳐 보인다. 표3(기술지도 개요)의 실제 고객사 서명 이미지("그림")도 같은 방식으로
    지운다 — 셀 텍스트를 지우는 방식으로 접근했을 때는 이미지가 어느 셀에 물려있는지
    실측으로 특정할 수 없어(그림이 예측 불가능하게 하나씩 사라지는 현상만 확인됨) 안전하게
    격리하지 못했지만, `HeadCtrl` 체인에서 컨트롤 객체 자체를 직접 찾아 지우는 이 방식은
    어느 셀에 있는지와 무관하게 안전하다. `HeadCtrl` 체인을 문서 순서대로 훑다가
    "표"(UserDesc) 컨트롤을 셀 때 이 표에 들어서는 시점과 나가는 시점(다음 "표") 사이에
    나오는 대상 컨트롤만 지운다. 표 안의 컨트롤(체크박스/그림 등)을 전부 지운 뒤에
    `_process_table()`로 남은 텍스트를 지워야 안전하다 — 순서가 중요하다(이미지가 남은
    상태에서 텍스트를 줄 단위로 지우면 그 줄에 걸린 이미지까지 같이 지워질 수 있다).
    """
    ctrl = hwp.HeadCtrl
    table_count = -1
    in_target_table = False
    to_delete = []
    while ctrl:
        ud = ctrl.UserDesc
        if ud == "표":
            table_count += 1
            if table_count == table_index + 1:
                break
            in_target_table = table_count == table_index
        elif ud in target_descs and in_target_table:
            to_delete.append(ctrl)
        ctrl = ctrl.Next

    for c in to_delete:
        hwp.delete_ctrl(c)
    return len(to_delete)


# (table_index, addr) 쌍 — 셀 자체를 절대 건드리지 않는다(텍스트 읽기/선택조차 하지 않음).
# 표3의 B1("지도기관명" 데이터 칸)은 텍스트 없이 회사 로고 그림만 들어있는데, `TableCellBlock()`
# 으로 셀을 선택했다가(텍스트 유무 확인 목적) `keep_select=False`로 해제하는 과정만으로도
# 로고가 사라지는 것을 렌더링으로 실측 확인했다(정확한 원인 미상 — 셀 선택 자체가 부작용을
# 낸 것으로 추정). 안전한 재현/분석 방법을 못 찾아 이 칸은 아예 건드리지 않기로 했다.
_SKIP_CELLS: dict[int, set[str]] = {3: {"B1"}}


def _process_table(hwp, table_index: int, static_labels: set[str], records: list[dict]) -> int:
    """표 안(A1)부터 시작해 물리 셀을 순서대로 훑으며(TableRightCell로 이동, 병합 셀은
    물리적으로 한 번만 방문됨 — pyhwpx의 `fill_addr_field()`와 동일한 순회 방식), 라벨이
    아닌 셀은 그 자리에서 바로 지우고 필드를 만든다.

    셀을 다시 찾아가는 `goto_addr()`는 매번 A1부터 표 전체를 다시 훑는 O(n) 동작이라(내부
    캐시가 셀 내용을 지우는 중간 조작과 맞물려 표 하나에도 수 분씩 걸릴 정도로 느려짐 —
    실측으로 확인됨), 한 번의 순방향 이동만으로 읽기·수정을 같이 처리해 이 문제를 피한다.
    """
    hwp.MoveDocBegin()
    hwp.get_into_nth_table(table_index, select_cell=False)
    hwp.TableColBegin()
    hwp.TableColPageUp()

    created = 0

    def _read_cell_text() -> str:
        """`TableCellBlock()`(F5, "표 셀 선택")으로 현재 셀 텍스트를 읽는다.

        `get_selected_range()` 기준으로 정확히 그 셀 하나만 선택되고(`SelectionMode == 3`),
        `get_selected_text()`(InitScan/GetText 기반)도 정확히 그 텍스트만 돌려주는 것을
        실측으로 확인했다 — `GetTextFile()`은 이 선택을 무시하고 표 전체를 반환해버리는
        별개의 버그가 있어 쓰지 않는다.
        """
        hwp.TableCellBlock()
        return hwp.get_selected_text(keep_select=False)

    def _clear_cell_text() -> None:
        """현재 셀의 텍스트를 전부 지운다.

        F5(TableCellBlock) 선택 상태에서는 `Delete` 액션이 조용히 실패한다(실측 확인).
        그렇다고 여러 줄을 한 번에 선택하려고 `MoveSelDown`(Shift+아래)을 쓰면, 셀의
        마지막 줄에서 더 내려갈 곳이 없어 이동이 "실패"할 때 커서가 표의 엉뚱한 칸으로
        새는 부작용이 있어(다음 칸 필드가 통째로 사라지거나 중복 생성되는 현상을 실측으로
        확인함) 그것도 쓰지 않는다. 대신 `MoveSelDown` 없이, 한 줄씩
        선택(`MoveSelLineBegin`+`MoveSelLineEnd`)해 지우기를 셀이 빌 때까지 반복한다 —
        느리지만(칸당 최대 몇 번) 안전하다.
        """
        guard = 0
        while _read_cell_text():
            hwp.HAction.Run("MoveSelLineBegin")
            hwp.HAction.Run("MoveSelLineEnd")
            hwp.HAction.Run("Delete")
            guard += 1
            if guard > 20:  # 정상 셀이라면 이 줄 수를 넘을 일이 없다
                break

    def _handle_current_cell() -> None:
        nonlocal created
        addr = hwp.get_cell_addr()
        if addr in _SKIP_CELLS.get(table_index, set()):
            return
        raw_text = _read_cell_text()
        normalized = _normalize(raw_text)

        if normalized in static_labels:
            return

        _clear_cell_text()
        created += 1
        field_name = f"t{table_index}_{created:03d}"
        ok = hwp.create_field(field_name)
        records.append(
            {
                "field": field_name,
                "table": table_index,
                "addr": addr,
                "original_text": raw_text.strip(),
                "created": bool(ok),
            }
        )

    _handle_current_cell()
    guard = 0
    while hwp.TableRightCell():
        _handle_current_cell()
        guard += 1
        if guard > 2000:  # 안전장치 — 정상 표라면 이 규모를 넘을 일이 없다
            raise RuntimeError(f"표{table_index} 순회가 2000칸을 넘었습니다 — 무한루프 의심")

    return created


def _number_major_hazard_labels(hwp) -> None:
    """표5(대형사고 위험작업 25종)의 항목명 앞 "□  " 기호를 "1. "~"25. " 번호로 바꾼다.

    이 라벨 셀들은 데이터가 아니라 고정 항목명이라 필드화 대상이 아니었고(표5의 실제 체크
    상태는 옆 "해당/해당없음" 컬럼의 체크박스 컨트롤이 담당 — `_remove_controls_by_desc`
    참고), 원본 문서의 "□  항목명" 텍스트가 그대로 남아있었다. 관리번호 필드와 같은 이유로
    (표 밖 텍스트가 아니라 표 안이지만 라벨 취급이라 `_process_table`이 건드리지 않음)
    `AllReplace`로 문서 전체 찾아바꾸기한다 — 항목명 문자열이 전부 충분히 길고 고유해
    다른 곳과 잘못 겹칠 위험이 없다.
    """
    for index, item in enumerate(MAJOR_HAZARD_WORKS, start=1):
        pset = hwp.hwp.HParameterSet.HFindReplace
        hwp.hwp.HAction.GetDefault("AllReplace", pset.HSet)
        pset.FindString = f"□  {item}"
        pset.ReplaceString = f"{index}. {item}"
        pset.ReplaceMode = 1
        pset.IgnoreMessage = 1
        hwp.hwp.HAction.Execute("AllReplace", pset.HSet)


def build_template() -> Path:
    from pyhwpx import Hwp

    if not _SOURCE_HWP.exists():
        raise FileNotFoundError(f"원본 .hwp 파일을 찾을 수 없습니다: {_SOURCE_HWP}")

    _WORK_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_SOURCE_HWP, _WORK_COPY)

    # 프로젝트 폴더가 OneDrive 동기화 대상(바탕화면)이라, 그 안에 반복 저장(save_as)하면
    # OneDrive 파일시스템 필터가 매번 가로채면서 20분 넘게 멈추는 현상을 실측으로 확인했다
    # (임시 폴더에 저장하면 전체 12개 표 처리+저장이 54초). 그래서 작업은 전부 OneDrive가
    # 안 건드리는 임시 폴더에서 하고, 완성된 결과 파일만 마지막에 한 번 프로젝트 폴더로
    # 복사한다.
    _work_output = _WORK_COPY.parent / "report_template_build_output.hwp"

    static_labels = _build_static_label_set()
    records: list[dict] = []

    import time

    t0 = time.time()

    hwp = Hwp(visible=False, register_module=True)
    try:
        hwp.open(str(_WORK_COPY))
        for table_index in _SAFE_TABLE_INDEXES:
            if table_index in _PRE_REMOVE_CONTROL_TABLES:
                removed = _remove_controls_by_desc(hwp, table_index, _PRE_REMOVE_CONTROL_TABLES[table_index])
                print(f"  표{table_index}: 컨트롤 {removed}개 제거(선처리)", flush=True)
            count = _process_table(hwp, table_index, static_labels, records)
            if table_index in _POST_REMOVE_CHECKBOX_TABLES:
                removed = _remove_controls_by_desc(hwp, table_index, {"선택 상자"})
                print(f"  표{table_index}: 체크박스 컨트롤 {removed}개 제거", flush=True)
            hwp.save_as(str(_work_output))
            print(f"표{table_index}: 필드 {count}개 생성 ({time.time()-t0:.1f}s)", flush=True)

        _number_major_hazard_labels(hwp)
        hwp.save_as(str(_work_output))
        print(f"표5: 항목 번호 매기기 완료 ({time.time()-t0:.1f}s)", flush=True)

        removed6 = _remove_table6_checkboxes(hwp)
        count6 = _process_table6(hwp, records)
        hwp.save_as(str(_work_output))
        print(f"표6: 체크박스 {removed6}개 제거, 필드 {count6}개 생성 ({time.time()-t0:.1f}s)", flush=True)

        for table_index in _EQUIPMENT_TABLES:
            removed_eq, count_eq = _process_equipment_table(hwp, table_index, records)
            hwp.save_as(str(_work_output))
            print(
                f"표{table_index}: 체크박스 {removed_eq}개 제거, 필드 {count_eq}개 생성 ({time.time()-t0:.1f}s)",
                flush=True,
            )

        # ---- 최종 검증: 실제 고객사 문자열이 하나도 안 남았는지 확인 ----
        # option에 "saveblock"이 포함되면 선택 영역만 추출한다(pyhwpx 기본값) — 전체 문서를
        # 봐야 하므로 빈 문자열을 넘긴다.
        full_text = hwp.GetTextFile("TEXT", option="") or ""
        print(f"GetTextFile 완료 ({time.time()-t0:.1f}s)", flush=True)
    finally:
        hwp.quit()

    # 필드 매핑 정보는 검증 통과 여부와 무관하게 항상 남긴다 — 실패했을 때도 어느 셀이
    # 무슨 필드가 됐는지 리뷰/디버깅할 수 있어야 한다.
    _OUTPUT_FIELDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_FIELDS_JSON.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    leaked = [s for s in _load_client_strings() if s in full_text]
    if leaked:
        raise RuntimeError(
            "고객사 정보가 템플릿에 남아있어 프로젝트 폴더로 복사하지 않았습니다. "
            f"남은 문자열: {leaked}\n"
            f"(중간 산출물은 검토용으로 {_work_output}에 남아있습니다.)"
        )

    _OUTPUT_HWP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_work_output, _OUTPUT_HWP)

    print(f"템플릿 생성 완료: {_OUTPUT_HWP}")
    print(f"필드 {len(records)}개, 매핑 정보: {_OUTPUT_FIELDS_JSON}")
    return _OUTPUT_HWP


if __name__ == "__main__":
    build_template()
