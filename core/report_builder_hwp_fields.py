"""한글(.hwp) 템플릿 필드 채우기 — 표별 채우기 함수.

`data/build_hwp_template.py`가 만든 `data/templates/report_template.hwp`의 누름틀 필드는
`t{표번호}_{순번:03d}` 형식의 기계적 이름이다(`report_template_fields.json`에 각 필드가
원래 담고 있던 텍스트가 남아있어 의미를 역추적할 수 있다). 이 파일의 필드 번호 매핑은
실제 원본 문서(영중중학교 1차)를 표별로 다시 훑어(`t{표번호}_{순번}`, 주소, 원문을 나란히
뽑아본 뒤) 손으로 확인한 것이라 — 표 구조가 바뀌면(예: 템플릿을 다시 생성하면) 다시
확인해야 한다.

**현재 범위**: 표1/2(현장·본사 정보), 표5(대형사고 위험작업 25종 — 아래 참고), 표11(현재
진행중인 공정, 최대 4슬롯), 표13(다음 방문시까지 발생하는 주요 진행공정 1~9), 표14(향후
진행공정 상세 — 첫 번째 슬롯만, 표 구조상 한 슬롯 분량밖에 없음), 표15(TBM/장비사용,
계측자료 최대 2건). **표4(이전지적사항)·표8/9/10(3종 장비 안전조치 평가)·표12(현재진행공정
보조표, 표11과 역할이 겹쳐 보이나 정확한 용도 미확인)는 아직 채우지 않는다** — 원본 실제
문서에서 이 부분들이 전부 빈 상태(이전지적사항 0건 등)라 순번만으로 정확한 의미를 확정할
근거가 없었고, 3종 장비표는 항목마다 안내문구가 1~3줄로 늘어나는 병합 구조라 순번 매핑이
특히 위험해 다음 라운드로 미뤘다(빈 누름틀 상태로 남는다 — 문서 자체는 정상,
`report_template_fields.json` 참고).

**표5(대형사고 위험작업 25종)는 실제로는 텍스트가 아니라 클릭 가능한 체크박스 컨트롤이었다**
(HWPML2X `<CHECKBUTTON>`) — 이 컨트롤의 체크 상태를 코드로 바꾸는 방법을 여러 각도로
시도했지만 찾지 못해(`data/build_hwp_template.py` 모듈 docstring 참고), 컨트롤을 지우고
이 파일이 텍스트(☑/☐)로 채우는 쪽으로 확정했다 — 마법사 데이터는 자동으로 정확히
반영되지만, 생성된 문서에서는 더 이상 진짜 클릭 가능한 체크박스가 아니다.
"""

from __future__ import annotations

from core.constants import FIXED_HAZARD_FACTORS, MAJOR_HAZARD_WORKS, MEASUREMENT_INSTRUMENTS
from core.db import SessionLocal
from core.models_db import MeasurementStandard, Report, Site


def _put(hwp, field_name: str, value: str) -> None:
    if hwp.field_exist(field_name):
        hwp.put_field_text(field_name, value or "")


def _fix_char_shape(hwp, field_name: str, height: int = 1100, bold: int = 0, color: int = 0) -> None:
    """필드 위치의 글자 모양(크기/굵기/색)을 표의 다른 데이터 칸과 동일하게 맞춘다.

    표3의 L3("담당요원") 칸은 원본 문서에서 실제 고객사 담당자 이름을 손글씨처럼 보이도록
    굵고 크고 회색인 글자 모양(Height=1300, Bold=1, TextColor=회색)을 쓰고 있었다 —
    텍스트만 갈아끼우면 그 글자 모양이 그대로 남아 다른 칸과 눈에 띄게 달라 보인다.
    """
    if not hwp.field_exist(field_name):
        return
    hwp.move_to_field(field_name, text=True, start=True, select=True)
    cs = hwp.hwp.HParameterSet.HCharShape
    hwp.hwp.HAction.GetDefault("CharShape", cs.HSet)
    cs.Height = height
    cs.Bold = bold
    cs.TextColor = color
    hwp.hwp.HAction.Execute("CharShape", cs.HSet)


_MANAGEMENT_NO_PLACEHOLDER = "2026-0000056"


def fill_management_no(hwp, site: Site) -> None:
    """표 밖 제목 문단("1. 기술지도 대상사업장 [ 관리번호 ... ]")의 관리번호를 채운다.

    이 문단은 표 셀이 아니라 `build_hwp_template.py`의 표 단위 필드화 대상에서 빠져있어,
    원본 실제 문서(영중중학교 1차)의 관리번호 텍스트가 필드화되지 않은 채 그대로 남아있다.
    전체 문서 찾아바꾸기로 그 잔존 텍스트를 site.management_no로 치환한다 — pyhwpx의
    `find_replace_all`은 내부적으로 `FindDlg` 액션을 먼저 실행하는데, 숨겨진(visible=False)
    인스턴스에서 대화상자 관련 액션이 무한 대기를 유발한 전례가 있어(핵심기술.md 참고) 직접
    `AllReplace` HAction만 실행한다.
    """
    if not site.management_no:
        return
    pset = hwp.hwp.HParameterSet.HFindReplace
    hwp.hwp.HAction.GetDefault("AllReplace", pset.HSet)
    pset.FindString = _MANAGEMENT_NO_PLACEHOLDER
    pset.ReplaceString = site.management_no
    pset.ReplaceMode = 1
    pset.IgnoreMessage = 1
    hwp.hwp.HAction.Execute("AllReplace", pset.HSet)


def fill_site_fields(hwp, site: Site) -> None:
    """표1: 기술지도 대상사업장(현장 정보)."""
    period = ""
    if site.period_start or site.period_end:
        start = site.period_start.strftime("%Y-%m-%d") if site.period_start else "-"
        end = site.period_end.strftime("%Y-%m-%d") if site.period_end else "-"
        period = f"{start} ~ {end}"

    _put(hwp, "t1_001", site.name)
    _put(hwp, "t1_002", site.site_mgmt_no)
    _put(hwp, "t1_004", site.biz_start_no)
    _put(hwp, "t1_005", period)
    _put(hwp, "t1_006", f"{site.amount:,}원" if site.amount is not None else "")
    _put(hwp, "t1_007", site.manager_name)
    _put(hwp, "t1_008", site.manager_phone)
    _put(hwp, "t1_010", site.manager_email)
    _put(hwp, "t1_011", site.address)


def fill_signoff_fields(hwp, report: Report, site: Site) -> None:
    """표3: 기술지도 개요(담당요원/통보방법/이행여부/기타특이사항/재해발생현황).

    이 표는 체크박스 컨트롤의 캡션(예: "이행"/"직접전달"/"등기우편")이 컨트롤 자체 속성이라
    `build_hwp_template.py`가 컨트롤을 지울 때 라벨 글자까지 같이 사라졌다 — 그래서 표5와
    달리 라벨 문구까지 이 함수가 전부 다시 조립해서 써야 한다(원본 문서의 정확한 띄어쓰기를
    `report_template_fields.json`의 `original_text`에서 그대로 옮겨왔다).

    "기타 특이사항"(공사기간 편중 등)·"재해발생현황"(유/무)은 마법사가 아직 수집하지 않는
    데이터라 지어내지 않고 전부 미체크(☐) 상태로 남긴다 — 값이 생기면 그때 마법사 필드를
    추가하고 이 함수도 연결한다.
    """
    if report.guidance_date:
        _put(hwp, "t3_001", report.guidance_date.strftime("%y 년  %m 월  %d 일"))
    _put(hwp, "t3_002", "☑건설공사")
    if report.progress_rate is not None:
        _put(hwp, "t3_003", f"{report.progress_rate} %")
    total = site.total_guidance_count or ""
    _put(hwp, "t3_004", f"총 (  {total}  )회차 중 (  {report.visit_no}  )회")

    staff_name = report.assigned_staff.name if report.assigned_staff else ""
    _put(hwp, "t3_005", f"{staff_name}     " if staff_name else "")
    _fix_char_shape(hwp, "t3_005")
    staff_phone = report.assigned_staff.phone if report.assigned_staff else ""
    _put(hwp, "t3_007", staff_phone)

    implemented = report.prev_guidance_implemented
    _put(
        hwp,
        "t3_006",
        f"{'☑' if implemented is True else '☐'}이행    "
        f"☐일부 이행    "
        f"{'☑' if implemented is False else '☐'}불이행",
    )

    method = report.notification_method
    signee = report.notify_signee_name or (site.manager_name if site else "")
    _put(
        hwp,
        "t3_008",
        f"{'☑' if method == '직접전달' else '☐'}직접전달    "
        f"(성함:   {signee}     서명:              (연락처: {site.manager_phone} )",
    )
    _put(hwp, "t3_009", f"{'☑' if method == '등기우편' else '☐'}등기우편")
    _put(hwp, "t3_010", f"{'☑' if method == '모바일' else '☐'}모바일")
    _put(hwp, "t3_011", f"{'☑' if method == '기타' else '☐'}기타")
    _put(hwp, "t3_012", f"{'☑' if method == '전자우편' else '☐'}전자우편")
    _put(hwp, "t3_013", f"( {site.manager_email} )")

    _put(hwp, "t3_014", f"{'☑' if report.misc_overwork else '☐'}공사기간 편중, 조기준공 등")
    _put(hwp, "t3_015", f"{'☑' if report.misc_no_photo else '☐'}사진촬영 불가 (보안 등)")
    _put(hwp, "t3_016", f"{'☑' if report.misc_other else '☐'}기타")
    other_text = report.misc_other_text or ""
    other_pad = 12 if not other_text else 0
    _put(hwp, "t3_017", "(" + other_text + " " * other_pad + ")")
    _put(
        hwp,
        "t3_018",
        f"{'☑' if report.accident_status == '유' else '☐'}유    "
        f"{'☑' if report.accident_status == '무' else '☐'}무",
    )
    accident_content = report.accident_content or ""
    content_pad = 8 if not accident_content else 0
    _put(hwp, "t3_019", "(내용:" + accident_content + " " * content_pad + ")")


def fill_company_fields(hwp, site: Site) -> None:
    """표2: 기술지도 대상사업장(본사/시공사 정보)."""
    _put(hwp, "t2_001", site.hq_company)
    _put(hwp, "t2_002", site.corp_reg_no)
    _put(hwp, "t2_004", site.biz_reg_no)
    _put(hwp, "t2_005", site.license_no)
    _put(hwp, "t2_006", site.hq_phone)
    _put(hwp, "t2_007", site.hq_address)


def fill_major_hazard_work_fields(hwp, report: Report) -> None:
    """표5: 대형사고 위험작업 사항 25종 — 항목마다 해당/해당없음 두 칸.

    필드 순번 t5_002~t5_051(50개)이 MAJOR_HAZARD_WORKS 순서대로 (해당, 해당없음) 쌍으로
    반복된다(t5_001은 표 제목 셀이 잘못 필드화된 것이라 건드리지 않는다).
    """
    checked = set(report.major_hazard_work_checks or [])
    for idx in range(len(MAJOR_HAZARD_WORKS)):
        is_checked = idx in checked
        base = 2 + idx * 2
        # 실제 원본 문서는 채워진 사각형(■/□)이 아니라 체크 표시 박스(☑/☐)를 쓴다 —
        # 원본에서 지운 체크박스 컨트롤 대신 이 글자로 시각적으로 맞춘다.
        _put(hwp, f"t5_{base:03d}", "☑" if is_checked else "☐")
        _put(hwp, f"t5_{base + 1:03d}", "☐" if is_checked else "☑")


def fill_equipment_section_titles(hwp) -> None:
    """표8/9/10(건설기계장비·위험기계기구·유해위험물질 안전조치 평가)의 표 제목 칸 + 표 안
    소제목 칸(A2).

    표 맨 위 제목 칸(t8_001/t9_001/t10_001)은 원래 텍스트가 있던 자리인데 데이터 셀과 똑같이
    필드화되면서 빈 채로 남아있었다 — 원본 실제 문서의 제목 문구를 그대로 복원한다.

    표 안 소제목 칸(t{표}_category, A2)은 원본 문서 자체에 오기(誤記)가 있다 — 표8(건설기계
    장비 항목들이 들어있는 표)의 A2도 표9와 똑같이 "위험기계기구"라고 적혀있어서, 실제 항목
    구성과 안 맞는 라벨이 그대로 보였다(사용자가 확인해준 오류). 세 표 다 항목 구성에 맞는
    이름으로 명시적으로 다시 채운다.
    """
    _put(hwp, "t8_001", "건설기계장비에 대한 안전보건 조치 평가")
    _put(hwp, "t9_001", "위험기계기구에 대한 안전보건 조치 평가")
    _put(hwp, "t10_001", "유해위험물질에 대한 안전보건 조치 평가")

    _put(hwp, "t8_category", "건설기계장비")
    _put(hwp, "t9_category", "위험기계기구")
    _put(hwp, "t10_category", "유해위험물질")


def fill_equipment_data_fields(hwp, report: Report) -> None:
    """표8/9/10 데이터 행 — 항목별 유/무(t{표}_eq{i}_flag) + 지도사항 줄별 평가(t{표}_eq{i}_eval{줄번호}).

    `data/build_hwp_template.py`의 `_process_equipment_table()`이 항목마다 체크박스 1개를
    지우고 유/무 필드를 만들었다(원래 클릭 가능한 체크박스였던 자리라 표5/표6과 같은 이유로
    글자로 대체 — "유"/"무" 텍스트로 채워봤더니 다른 표들과 달리 눈에 띄게 지저분해 보인다는
    피드백으로 다른 표와 같은 ☑/☐ 표기로 되돌렸다). 평가는 항목 하나에 지도사항 줄만큼
    독립된 필드(마법사도 줄마다 독립된 양호/미흡 버튼을 둔다 — 항목당 하나로 합쳐 보여줬더니
    실제 문서 구조와 달라 보인다는 피드백으로 되돌림). `report.machinery_checks` 등은
    `{"checked": bool, "notes": [str, ...]}` 딕셔너리 목록이고, 바깥 순서는
    `core/constants.py`의 항목 순서, `notes` 순서는 그 항목의 지도사항 줄 순서와 1:1로
    대응한다(마법사 쪽 `self.machinery_rows`가 그대로 만들어지므로).
    """
    for table_index, checks in (
        (8, report.machinery_checks),
        (9, report.hand_tool_checks),
        (10, report.hazmat_checks),
    ):
        for i, entry in enumerate(checks or []):
            _put(hwp, f"t{table_index}_eq{i}_flag", "☑" if entry.get("checked") else "☐")
            for j, note in enumerate(entry.get("notes") or []):
                _put(hwp, f"t{table_index}_eq{i}_eval{j}", note or "")


def fill_hazard_factor_fields(hwp, report: Report) -> None:
    """표6: 17대 기인물과 필수 지도사항 — 기인물 자체 체크(t6_{N}_f) + 지도사항 줄별 체크
    (t6_{N}_l{줄번호}). `report.hazard_factor_checks`는 문자열 목록이고 "N"은 기인물 자체,
    "N-M"은 그 기인물의 M번째(0-based) 지도사항 줄을 뜻한다(`_apply_hazard_checks` 참고).

    16번(작업전 TBM)·17번(위험성 평가 결과 공유)은 원본 문서에 체크박스 칸 자체가 없어서
    (표6 조사 결과, `data/build_hwp_template.py`의 `_TABLE6_CHECKBOX_MAP` 참고) 대응하는
    필드가 없다 — `_put()`이 `field_exist()`로 걸러내므로 조용히 건너뛴다.
    """
    checked = set(report.hazard_factor_checks or [])
    for number, _name, lines in FIXED_HAZARD_FACTORS:
        _put(hwp, f"t6_{number}_f", "☑" if str(number) in checked else "☐")
        for line_index in range(len(lines)):
            mark = "☑" if f"{number}-{line_index}" in checked else "☐"
            _put(hwp, f"t6_{number}_l{line_index}", mark)


def fill_current_process_fields(hwp, report: Report) -> None:
    """표11: 현재 진행중인 공정 유해위험요인 파악 (최대 4슬롯).

    필드 t11_003이 공정명, t11_004~019가 4슬롯 × (유해위험요인/현재안전보건조치/위험성수준/평가)
    순서로 반복된다. 실제 원본 문서는 5번째 슬롯(t11_020~023)도 있었지만 우리 DB 모델
    (`CurrentProcessEntry`)이 최대 4슬롯까지만 지원해 5번째는 채우지 않는다.
    """
    _put(hwp, "t11_003", report.current_process_name)
    entries_by_slot = {e.slot: e for e in report.current_process_entries}
    for slot in range(1, 5):
        base = 4 + (slot - 1) * 4
        entry = entries_by_slot.get(slot)
        _put(hwp, f"t11_{base:03d}", entry.hazard_text if entry else "")
        _put(hwp, f"t11_{base + 1:03d}", entry.measure_text if entry else "")
        _put(hwp, f"t11_{base + 2:03d}", entry.risk_level if entry else "")
        _put(hwp, f"t11_{base + 3:03d}", entry.evaluation if entry else "")


def fill_future_process_summary_fields(hwp, report: Report) -> None:
    """표13: "다음 방문시까지 발생하는 주요 진행공정 1~9" 요약 박스.

    우리는 최대 4개 진행공정만 수집하므로 1~4번 자리만 채우고 5~9번은 비운다. 번호 라벨
    칸("2","5")이 원본에 " ."이 붙어있어 정적 문구로 안 걸리고 필드화된 것도 여기서
    깔끔한 숫자로 되돌린다.
    """
    _put(hwp, "t13_002", "2")
    _put(hwp, "t13_006", "5")

    value_fields = ["t13_001", "t13_003", "t13_004", "t13_005", "t13_007", "t13_008", "t13_009", "t13_010", "t13_011"]
    names = [e.process_name for e in sorted(report.process_entries, key=lambda e: e.slot) if e.process_name]
    for i, field in enumerate(value_fields):
        _put(hwp, field, names[i] if i < len(names) else "")


def fill_future_process_detail_fields(hwp, report: Report) -> None:
    """표14: 향후진행공정 상세(진행공정/유해·위험요인/예방대책/위험성) — 표 구조상 한 슬롯
    분량만 있어 첫 번째로 채워진 진행공정 하나만 반영한다."""
    entries = sorted(
        (e for e in report.process_entries if e.process_name), key=lambda e: e.slot
    )
    if not entries:
        return
    entry = entries[0]
    _put(hwp, "t14_001", entry.process_name)
    for field in ("t14_002", "t14_004", "t14_007"):
        _put(hwp, field, entry.hazard_text)
    for field in ("t14_003", "t14_005", "t14_008"):
        _put(hwp, field, entry.prevention_text)
    _put(hwp, "t14_006", entry.risk_level)


_TBM_LABEL_RESTORE = {
    "t15_001": "○ 참석인원 :",
    "t15_003": "○ 교육장소 : ",
    "t15_005": "○ 교육내용 :",
    "t15_008": "○ 교육자료 :",
}
# 표15는 라벨과 값이 별개의 필드다(둘 다 잘못 필드화됨) — 슬롯(장비사용 1/2)마다
# 라벨 필드는 고정 문구로 되돌리고, 값 필드에만 실제 계측자료를 채운다. 병합 셀 순회
# 특성상 같은 항목이 여러 번(dup) 나오는데, 전부 같은 값으로 채워 일관성을 맞춘다.
_EQUIPMENT_SLOTS = {
    1: {
        "name_label": ["t15_011", "t15_016"],
        "name_value": ["t15_012", "t15_017"],
        "place_label": ["t15_013", "t15_018"],
        "place_value": ["t15_014", "t15_019"],
        "value_label": ["t15_021"],
        "value_value": ["t15_022"],
        "std_label": ["t15_023"],
        "std_value": ["t15_024"],
        "action": ["t15_026"],
    },
    2: {
        "name_label": ["t15_027", "t15_032"],
        "name_value": ["t15_028", "t15_033"],
        "place_label": ["t15_029", "t15_034"],
        "place_value": ["t15_030", "t15_035"],
        "value_label": ["t15_037"],
        "value_value": ["t15_038"],
        "std_label": ["t15_039"],
        "std_value": ["t15_040"],
        "action": ["t15_042"],
    },
}
_EQUIPMENT_LABEL_TEXT = {
    "name_label": "○ 장비명 :",
    "place_label": "○ 측정장소:\r\n   (공도구)",
    "value_label": "○ 측정치 :",
    "std_label": "○ 안전기준 :",
    "action": "○ 조치사항 :                       -",
}


def _put_all(hwp, field_names: list[str], value: str) -> None:
    for name in field_names:
        _put(hwp, name, value)


def fill_support_fields(hwp, report: Report) -> None:
    """표15: 사업장 지원 사항 — TBM(참석인원/장소/내용/자료) + 장비사용(최대 2건).

    `report_builder_pdf.py`의 `_build_support_section`과 같은 규칙(값이 있는 계측자료만,
    측정장소는 "현장 내" 고정, 조치사항은 "-" 고정, 안전기준은 `MeasurementStandard` 조회)을
    그대로 따른다. 교육장소 값("현장")은 원본 문서에서 우리 공통 정적 라벨("현장")과
    우연히 겹쳐 애초에 필드화되지 않았다 — 채울 수 있는 필드가 없어 템플릿에 박힌 값 그대로
    남는다(알려진 사소한 한계).
    """
    for field, text in _TBM_LABEL_RESTORE.items():
        _put(hwp, field, text)

    education = report.safety_education
    _put(hwp, "t15_002", f"{education.attendee_count} 명" if education and education.attendee_count is not None else "")
    _put(hwp, "t15_006", education.content if education else "")
    _put(hwp, "t15_009", education.material if education else "")

    with SessionLocal() as session:
        standards = {s.instrument_type: s.standard_criteria for s in session.query(MeasurementStandard).all()}
    used = [m for m in report.measurements if m.value]

    for slot_no, fields in _EQUIPMENT_SLOTS.items():
        for key in ("name_label", "place_label", "value_label", "std_label", "action"):
            _put_all(hwp, fields[key], _EQUIPMENT_LABEL_TEXT[key])

        measurement = used[slot_no - 1] if slot_no - 1 < len(used) else None
        if measurement is None:
            continue
        unit = next((u for name, u in MEASUREMENT_INSTRUMENTS if name == measurement.instrument_type), "")
        _put_all(hwp, fields["name_value"], measurement.instrument_type)
        _put_all(hwp, fields["place_value"], "현장 내")
        _put_all(hwp, fields["value_value"], f"{measurement.value} {unit}".strip())
        _put_all(hwp, fields["std_value"], standards.get(measurement.instrument_type, "-"))


def fill_all(hwp, report: Report, site: Site) -> None:
    fill_management_no(hwp, site)
    fill_site_fields(hwp, site)
    fill_company_fields(hwp, site)
    fill_signoff_fields(hwp, report, site)
    fill_major_hazard_work_fields(hwp, report)
    fill_hazard_factor_fields(hwp, report)
    fill_equipment_section_titles(hwp)
    fill_equipment_data_fields(hwp, report)
    fill_current_process_fields(hwp, report)
    fill_future_process_summary_fields(hwp, report)
    fill_future_process_detail_fields(hwp, report)
    fill_support_fields(hwp, report)
