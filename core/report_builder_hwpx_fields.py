"""HWPX 산출물 필드 채우기 — `report_builder_hwp_fields.py`(pyhwpx/COM 버전)를
python-hwpx(순수 파이썬, COM 불필요)로 옮긴 버전.

COM 전용 처리(`_fix_char_shape`)도 포팅 완료 — 표3 담당요원 칸/표12·15 예방대책 칸 모두
`run.char_pr_id_ref`를 직접 지정하는 방식으로 옮겼다(문서에 이미 있는 스타일을 재사용하거나
`doc.ensure_run_style()`로 새 스타일을 만들어 적용).

그 외 로직(필드 이름 체계, 값 조립 규칙)은 원본과 동일하다 — 자세한 배경 설명은
`report_builder_hwp_fields.py`의 docstring을 그대로 참고할 것.
"""

from __future__ import annotations

from copy import deepcopy

from core.constants import FIXED_HAZARD_FACTORS, MAJOR_HAZARD_WORKS, MEASUREMENT_INSTRUMENTS
from core.db import SessionLocal
from core.models_db import MeasurementStandard, Report, Site
from core.report_builder_hwpx_images import _locate_field_cell


def _put(doc, field_name: str, value: str) -> None:
    """필드에 텍스트를 채운다. 필드가 템플릿에 없으면 조용히 건너뛴다(원본과 동일한
    `field_exist()` 가드 — 표6의 16·17번처럼 애초에 필드가 없는 자리가 있다).
    """
    try:
        doc.fill_form_field(value or "", name=field_name)
    except Exception:
        pass


def _fix_char_shape(doc, field_name: str, char_pr_id_ref: str) -> None:
    """필드 위치의 글자 모양을 다른 칸과 같은 스타일로 맞춘다.

    표3 "담당요원" 칸(t3_005)은 원본 실제 문서에서 고객사 담당자 이름을 손글씨처럼 보이게
    굵고 크고 회색인 글자 모양(Height=1300, TextColor=회색, Bold)을 쓰고 있었다(실측 확인) —
    값만 갈아끼우면 그 글자 모양이 그대로 남아 다른 칸과 눈에 띄게 달라 보인다. 새 스타일을
    만드는 대신, 이미 문서 안에 있는 "정상적인" 칸의 문자 모양 id를 그대로 재사용한다(예:
    t3_007 연락처 칸의 id="1" — Height=1000, TextColor=검정, Bold 없음).
    """
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    cell = table.cell(row, col)
    for para in cell.paragraphs:
        for run in para.runs:
            run.char_pr_id_ref = char_pr_id_ref


def _fix_para_shape(doc, field_name: str, para_pr_id_ref: str) -> None:
    """필드가 있는 문단의 정렬 등 문단 모양을 다른 칸과 같은 스타일로 맞춘다.

    표3 담당요원 칸(t3_005)은 원본 문서에서 오른쪽 정렬(연락처 칸과 다른 para_pr_id)이라
    이름을 넣으면 칸 오른쪽에 붙어버린다(실측 확인 — 연락처 칸의 "0"과 세로선이 맞아야
    한다는 피드백). 연락처 칸(t3_007)처럼 왼쪽 정렬인 문단 모양 id를 재사용한다."""
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    cell = table.cell(row, col)
    for para in cell.paragraphs:
        para.para_pr_id_ref = para_pr_id_ref




_MANAGEMENT_NO_PLACEHOLDER = "2026-0000056"


def fill_management_no(doc, site: Site) -> None:
    """표 밖 제목 문단의 관리번호를 전체 문서 찾아바꾸기로 채운다."""
    if not site.management_no:
        return
    doc.replace_text_in_runs(_MANAGEMENT_NO_PLACEHOLDER, site.management_no)




# 이메일이 길수록 셀이 줄바꿈되며 표가 다음 페이지로 밀리는 문제를 막기 위해, 길이 구간별로
# 폰트를 단계적으로 줄인다(사용자 요청, 2026-09-17). 고정폭 1단계(8pt)로는 표3 통보방법
# 칸처럼 실제 가용 폭이 좁은 자리에서 여전히 줄바꿈되는 경우가 실측으로 확인돼, 아주 길면
# 더 작게 줄이는 계단식으로 바꿨다. (하한, 크기) 순으로 정렬 — 길이가 하한을 넘는 마지막
# 구간의 크기를 쓴다.
_EMAIL_FONT_TIERS: list[tuple[int, int]] = [
    (20, 9),  # 21자부터
    (25, 8),  # 26자부터
    (29, 7),  # 30자부터
]


def _email_font_size_for(value: str) -> int | None:
    """길이에 맞는 폰트 크기(pt)를 고른다 — 기본 크기(10pt)로 충분하면 None."""
    length = len(value or "")
    size = None
    for min_len, tier_size in _EMAIL_FONT_TIERS:
        if length > min_len:
            size = tier_size
    return size


def _shrink_cell_font_if_long(doc, field_name: str, value: str) -> None:
    """긴 텍스트(예: 이메일)가 셀 안에서 줄바꿈되며 표 전체가 다음 페이지로 밀리는 문제를
    막기 위해, 길이 구간에 맞는 크기로 그 칸 전체 폰트를 줄인다(사용자 요청, 2026-09-17).
    표 폭 자체를 코드로 늘리는 방법은 시도했다가 python-hwpx로 `cellSz.width`를 건드리면
    폭 합이 맞는데도 표가 페이지 밖으로 밀리는 원인불명 렌더링 버그를 만난 적이 있어
    (TBM 표, Sub-phase 21) 폭 조정 대신 폰트 축소로 우회한다.
    """
    size = _email_font_size_for(value)
    if size is None:
        return
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    cell = table.cell(row, col)
    style_id = doc.ensure_run_style(size=size)
    for para in cell.paragraphs:
        for run in para.runs:
            run.char_pr_id_ref = style_id


def _shrink_field_run_if_long(doc, field_name: str, value: str) -> None:
    """`_shrink_cell_font_if_long`과 달리 칸(cell) 전체가 아니라 그 필드 자신의 run만
    골라 길이 구간에 맞는 크기로 줄인다 — 표3 통보방법 칸(t3_013 이메일)처럼 같은 칸에
    체크박스 라벨("☑전자우편" 등, t3_012)이 함께 들어있어 그 라벨까지 같이 작아지면 안
    되는 경우에 쓴다(사용자 요청, 2026-09-17). 방금 채운 값과 텍스트가 일치하는 run만
    골라서 적용하는 방식이라, 값 자체가 그 칸 안에서 유일한 문자열이어야 한다(이메일처럼).
    """
    size = _email_font_size_for(value)
    if size is None:
        return
    located = _locate_field_cell(doc, field_name)
    if located is None:
        return
    table, row, col = located
    cell = table.cell(row, col)
    style_id = doc.ensure_run_style(size=size)
    for para in cell.paragraphs:
        for run in para.runs:
            if run.text and value.strip() in run.text:
                run.char_pr_id_ref = style_id


def fill_site_fields(doc, site: Site) -> None:
    """표1: 기술지도 대상사업장(현장 정보)."""
    period = ""
    if site.period_start or site.period_end:
        start = site.period_start.strftime("%Y-%m-%d") if site.period_start else "-"
        end = site.period_end.strftime("%Y-%m-%d") if site.period_end else "-"
        period = f"{start} ~ {end}"

    _put(doc, "t1_001", site.name)
    _put(doc, "t1_002", site.site_mgmt_no)
    _put(doc, "t1_004", site.biz_start_no)
    _put(doc, "t1_005", period)
    _put(doc, "t1_006", f"{site.amount:,}원" if site.amount is not None else "")
    _put(doc, "t1_007", site.manager_name)
    _put(doc, "t1_008", site.manager_phone)
    _put(doc, "t1_010", site.manager_email)
    _shrink_cell_font_if_long(doc, "t1_010", site.manager_email)
    _put(doc, "t1_011", site.address)


def fill_signoff_fields(doc, report: Report, site: Site) -> None:
    """표3: 기술지도 개요(담당요원/통보방법/이행여부/기타특이사항/재해발생현황)."""
    if report.guidance_date:
        _put(doc, "t3_001", report.guidance_date.strftime("%y 년  %m 월  %d 일"))
    _put(doc, "t3_002", "☑건설공사")
    if report.progress_rate is not None:
        _put(doc, "t3_003", f"{report.progress_rate} %")
    total = site.total_guidance_count or ""
    _put(doc, "t3_004", f"총 (  {total}  )회차 중 (  {report.visit_no}  )회")

    staff_name = report.assigned_staff.name if report.assigned_staff else ""
    _put(doc, "t3_005", staff_name)
    _fix_char_shape(doc, "t3_005", "1")  # 다른 칸과 같은 검정/보통굵기 스타일로 맞춘다
    _fix_para_shape(doc, "t3_005", "0")  # 연락처 칸과 같은 왼쪽 정렬로 맞춘다
    staff_phone = report.assigned_staff.phone if report.assigned_staff else ""
    _put(doc, "t3_007", staff_phone)

    implemented = report.prev_guidance_implemented
    _put(
        doc,
        "t3_006",
        f"{'☑' if implemented is True else '☐'}이행    "
        f"☐일부 이행    "
        f"{'☑' if implemented is False else '☐'}불이행",
    )

    method = report.notification_method
    signee = report.notify_signee_name or (site.manager_name if site else "")
    _put(
        doc,
        "t3_008",
        f"성명:   {signee}     서명:              연락처: {site.manager_phone} ",
    )
    _put(doc, "t3_020", f"{'☑' if method == '직접전달' else '☐'}직접전달")
    _put(doc, "t3_009", f"{'☑' if method == '등기우편' else '☐'}등기우편")
    _put(doc, "t3_010", f"{'☑' if method == '모바일' else '☐'}모바일")
    _put(doc, "t3_011", f"{'☑' if method == '기타' else '☐'}기타")
    _put(doc, "t3_012", f"{'☑' if method == '전자우편' else '☐'}전자우편")
    email_paren = f"( {site.manager_email} )"
    _put(doc, "t3_013", email_paren)
    # 체크박스 라벨(t3_012 등)과 같은 칸에 있어 칸 전체를 줄이면 라벨까지 작아진다 —
    # 이메일 run만 콕 집어 줄인다.
    _shrink_field_run_if_long(doc, "t3_013", email_paren)

    _put(doc, "t3_014", f"{'☑' if report.misc_overwork else '☐'}공사기간 편중, 조기준공 등")
    _put(doc, "t3_015", f"{'☑' if report.misc_no_photo else '☐'}사진촬영 불가 (보안 등)")
    _put(doc, "t3_016", f"{'☑' if report.misc_other else '☐'}기타")
    other_text = report.misc_other_text or ""
    other_pad = 12 if not other_text else 0
    _put(doc, "t3_017", "(" + other_text + " " * other_pad + ")")
    _put(
        doc,
        "t3_018",
        f"{'☑' if report.accident_status == '유' else '☐'}유    "
        f"{'☑' if report.accident_status == '무' else '☐'}무",
    )
    accident_content = report.accident_content or ""
    content_pad = 8 if not accident_content else 0
    _put(doc, "t3_019", "(내용:" + accident_content + " " * content_pad + ")")


def fill_company_fields(doc, site: Site) -> None:
    """표2: 기술지도 대상사업장(본사/시공사 정보)."""
    _put(doc, "t2_001", site.hq_company)
    _put(doc, "t2_002", site.corp_reg_no)
    _put(doc, "t2_004", site.biz_reg_no)
    _put(doc, "t2_005", site.license_no)
    _put(doc, "t2_006", site.hq_phone)
    _put(doc, "t2_007", site.hq_address)


def fill_major_hazard_work_fields(doc, report: Report) -> None:
    """표5: 대형사고 위험작업 사항 25종 — 항목마다 해당/해당없음 두 칸."""
    checked = set(report.major_hazard_work_checks or [])
    for idx in range(len(MAJOR_HAZARD_WORKS)):
        is_checked = idx in checked
        base = 2 + idx * 2
        _put(doc, f"t5_{base:03d}", "☑" if is_checked else "☐")
        _put(doc, f"t5_{base + 1:03d}", "☐" if is_checked else "☑")


def fill_equipment_section_titles(doc) -> None:
    """표7/8/9(건설기계장비·위험기계기구·유해위험물질 안전조치 평가)의 표 제목 칸 + 소제목 칸."""
    _put(doc, "t7_001", "건설기계장비에 대한 안전보건 조치 평가")
    _put(doc, "t8_001", "위험기계기구에 대한 안전보건 조치 평가")
    _put(doc, "t9_001", "유해위험물질에 대한 안전보건 조치 평가")

    _put(doc, "t7_category", "건설기계장비")
    _put(doc, "t8_category", "위험기계기구")
    _put(doc, "t9_category", "유해위험물질")


def fill_equipment_data_fields(doc, report: Report) -> None:
    """표7/8/9 데이터 행 — 항목별 유/무(t{표}_eq{i}_flag) + 지도사항 줄별 평가(t{표}_eq{i}_eval{줄번호})."""
    for table_index, checks in (
        (7, report.machinery_checks),
        (8, report.hand_tool_checks),
        (9, report.hazmat_checks),
    ):
        for i, entry in enumerate(checks or []):
            _put(doc, f"t{table_index}_eq{i}_flag", "☑" if entry.get("checked") else "☐")
            for j, note in enumerate(entry.get("notes") or []):
                _put(doc, f"t{table_index}_eq{i}_eval{j}", note or "")


def fill_hazard_factor_fields(doc, report: Report) -> None:
    """표6: 17대 기인물과 필수 지도사항 — 기인물 자체 체크(t6_{N}_f) + 지도사항 줄별 체크(t6_{N}_l{줄번호})."""
    checked = set(report.hazard_factor_checks or [])
    for number, _name, lines in FIXED_HAZARD_FACTORS:
        _put(doc, f"t6_{number}_f", "☑" if str(number) in checked else "☐")
        for line_index in range(len(lines)):
            mark = "☑" if f"{number}-{line_index}" in checked else "☐"
            _put(doc, f"t6_{number}_l{line_index}", mark)




_TBM_LABEL_RESTORE = {
    "t16_001": "○ 참석인원 :",
    "t16_003": "○ 교육장소 : ",
    "t16_005": "○ 교육내용 :",
    "t16_008": "○ 교육자료 :",
}
_EQUIPMENT_SLOTS = {
    1: {
        "name_label": ["t16_011"],
        "name_value": ["t16_012"],
        "place_label": ["t16_013"],
        "place_value": ["t16_014"],
        "value_label": ["t16_021"],
        "value_value": ["t16_022"],
        "std_label": ["t16_023"],
        "std_value": ["t16_024"],
        "action": ["t16_026"],
    },
    2: {
        "name_label": ["t16_027"],
        "name_value": ["t16_028"],
        "place_label": ["t16_029"],
        "place_value": ["t16_030"],
        "value_label": ["t16_037"],
        "value_value": ["t16_038"],
        "std_label": ["t16_039"],
        "std_value": ["t16_040"],
        "action": ["t16_042"],
    },
}
_EQUIPMENT_LABEL_TEXT = {
    "name_label": "○ 장비명 :",
    "place_label": "○ 측정장소 :",
    "value_label": "○ 측정치 :",
    "std_label": "○ 안전기준 :",
}
_ACTION_LABEL_PREFIX = "○ 조치사항 :                       "


def _put_all(doc, field_names: list[str], value: str) -> None:
    for name in field_names:
        _put(doc, name, value)


_EQUIPMENT_PASS_FAIL_FIELDS = {
    1: ("t16_pass1", "t16_fail1"),
    2: ("t16_pass2", "t16_fail2"),
}


def _equipment_verdict(measurement) -> str | None:
    if measurement is None:
        return None
    manual = getattr(measurement, "manual_verdict", "") or ""
    if manual in ("양호", "불량"):
        return manual
    if measurement.instrument_type == "가스농도측정기":
        if measurement.value == "정상범위":
            return "양호"
        if measurement.value == "정상범위 초과":
            return "불량"
        return None
    if measurement.instrument_type == "조도계":
        try:
            value = float(str(measurement.value).strip())
        except ValueError:
            return None
        return "양호" if value >= 75 else "불량"
    return None


def fill_support_fields(doc, report: Report) -> None:
    """표16: 사업장 지원 사항 — TBM(참석인원/장소/내용/자료) + 장비사용(최대 2건).

    "○ 참석인원 : [값]"/"○ 교육장소 : [값]" 칸 폭은 한때 여기서 코드로 재조정했었다 —
    참석인원 값 칸(원래 8653 hwpunit)이 "1 명"류 짧은 값엔 너무 넓어서, 그만큼 교육장소
    값 칸(원래 3276)이 좁아 "현장사무실" 같은 흔한 값도 한 글자씩 줄바꿈됐다(실사용 확인,
    2026-09-16). 그런데 코드로 이 칸(교육장소 값 칸, 사진 병합칸 바로 앞)을 넓히면 폭
    합계는 정확히 똑같이 맞아떨어지는데도 늘어난 만큼 표 전체가 페이지 밖으로 밀려나는
    한글 자체의 렌더링 문제가 있어서(원인 불명, 실측으로 재현·확인만 함), 코드 수정을
    포기하고 **템플릿 파일(`report_template.hwpx`) 자체를 한글에서 직접 열어 표 칸
    경계선을 손으로 드래그해 재조정**했다 — 한글 자신의 편집기로 조정하면 이 문제가
    안 생긴다. 그래서 이 함수는 이제 폭을 안 건드리고 텍스트만 채운다.
    """
    for field, text in _TBM_LABEL_RESTORE.items():
        _put(doc, field, text)

    education = report.safety_education
    _put(doc, "t16_002", f"{education.attendee_count} 명" if education and education.attendee_count is not None else "")
    _put(doc, "t16_edu_location", education.location if education else "")
    _put(doc, "t16_006", education.content if education else "")
    _put(doc, "t16_009", education.material if education else "")

    with SessionLocal() as session:
        standards = {s.instrument_type: s.standard_criteria for s in session.query(MeasurementStandard).all()}
    used = [m for m in report.measurements if m.value]

    for slot_no, fields in _EQUIPMENT_SLOTS.items():
        for key in ("name_label", "place_label", "value_label", "std_label"):
            _put_all(doc, fields[key], _EQUIPMENT_LABEL_TEXT[key])

        measurement = used[slot_no - 1] if slot_no - 1 < len(used) else None

        # 조치사항은 예전엔 항상 "-"로 고정돼 있었다 — 사용자 요청으로 마법사에서 직접
        # 입력한 내용(manual_action)이 있으면 그걸 쓰고, 없으면 그대로 "-"를 보여준다.
        action_text = (getattr(measurement, "manual_action", "") or "").strip() if measurement else ""
        _put_all(doc, fields["action"], _ACTION_LABEL_PREFIX + (action_text or "-"))

        pass_field, fail_field = _EQUIPMENT_PASS_FAIL_FIELDS[slot_no]
        verdict = _equipment_verdict(measurement)
        _put(doc, pass_field, f"{'☑' if verdict == '양호' else '☐'}양호")
        _put(doc, fail_field, f"{'☑' if verdict == '불량' else '☐'}불량")

        if measurement is None:
            continue
        _put_all(doc, fields["name_value"], measurement.instrument_type)
        _put_all(doc, fields["place_value"], "현장 내")
        if measurement.instrument_type == "가스농도측정기":
            _put_all(doc, fields["value_value"], measurement.value)
        else:
            unit = next((u for name, u in MEASUREMENT_INSTRUMENTS if name == measurement.instrument_type), "")
            _put_all(doc, fields["value_value"], f"{measurement.value} {unit}".strip())
        _put_all(doc, fields["std_value"], standards.get(measurement.instrument_type, "-"))


def fill_all(doc, report: Report, site: Site) -> None:
    """3단계 포팅 범위 — 빈 슬롯 표 삭제까지 추가됨. 일부 칸 글자스타일(굵게/가운데정렬/
    배경색)은 아직 없다(다음 단계).
    """
    from core.report_builder_hwpx_fields_cleanup import (
        apply_heading_keep_with_next,
        force_future_process_heading_page_break,
        remove_na_sections,
    )
    from core.report_builder_hwpx_fields_findings import (
        fill_finding_fields,
        fill_previous_finding_fields,
        remove_unused_finding_blocks,
        remove_unused_previous_finding_blocks,
    )
    from core.report_builder_hwpx_fields_process import (
        fill_current_process_fields,
        fill_future_process_detail_fields,
        fill_future_process_summary_fields,
    )

    fill_management_no(doc, site)
    fill_site_fields(doc, site)
    fill_company_fields(doc, site)
    fill_signoff_fields(doc, report, site)
    remove_na_sections(doc, report)
    remove_unused_previous_finding_blocks(doc, report)
    fill_previous_finding_fields(doc, report)
    fill_major_hazard_work_fields(doc, report)
    fill_hazard_factor_fields(doc, report)
    fill_equipment_section_titles(doc)
    fill_equipment_data_fields(doc, report)
    fill_current_process_fields(doc, report)
    fill_future_process_summary_fields(doc, report)
    fill_future_process_detail_fields(doc, report)
    remove_unused_finding_blocks(doc, report)
    fill_finding_fields(doc, report)
    fill_support_fields(doc, report)
    apply_heading_keep_with_next(doc)
    force_future_process_heading_page_break(doc)
