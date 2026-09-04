"""한글(.hwp) 템플릿 필드 채우기 — 표별 채우기 함수.

`data/build_hwp_template.py`가 만든 `data/templates/report_template.hwp`의 누름틀 필드는
`t{표번호}_{순번:03d}` 형식의 기계적 이름이다(`report_template_fields.json`에 각 필드가
원래 담고 있던 텍스트가 남아있어 의미를 역추적할 수 있다). 이 파일의 필드 번호 매핑은
실제 원본 문서(영중중학교 1차)를 표별로 다시 훑어(`t{표번호}_{순번}`, 주소, 원문을 나란히
뽑아본 뒤) 손으로 확인한 것이라 — 표 구조가 바뀌면(예: 템플릿을 다시 생성하면) 다시
확인해야 한다.

**현재 범위**: 표0(결재란, 텍스트는 없고 서명 이미지만 — `report_builder_hwp_images.py`
참고), 표1/2(현장·본사 정보), 표3(기술지도 개요), 표5(대형사고 위험작업 25종 — 아래 참고),
표6(17대 기인물), 표7/8/9(건설기계장비·위험기계기구·유해위험물질 안전조치 평가), 표12(현재
진행공정 상세, 최대 4항목), 표14(다음 방문시까지 발생하는 주요 진행공정 1~9), 표15(향후
진행공정 상세, 최대 4항목 — 표12와 완전히 같은 구조), 표16(TBM/장비사용, 계측자료 최대
2건). **표4(이전지적사항)·표13(헤더가 "유해 위험장소/유해위험요인/지적사항 재해예방
대책/이행결과"로 표4와 거의 동일 — 아마 7번 섹션 "현재 공정 내 현존하는 위험성 제거"
(지적사항)용으로 추정되지만 아직 확인 안 됨)는 아직 채우지 않는다** — 원본 실제 문서에서
이 부분들이 전부 빈 상태(이전지적사항 0건 등)라 순번만으로 정확한 의미를 확정할 근거가
없어 다음 라운드로 미뤘다(빈 누름틀 상태로 남는다 — 문서 자체는 정상,
`report_template_fields.json` 참고).

**표 번호가 세 번 조정된 적이 있다**: (1) 원래 5번 섹션 맨 위에 있던 "위험성 평가기준"
박스가 17대 기인물 표(표6) 안의 물리적 행 2개를 차지하고 있었는데, 사용자가 한글에서 그
박스를 직접 잘라 3종 장비표 뒤 · "현재 진행중인 공정" 앞으로 옮기면서 표7 이후 모든 표
번호가 한 칸씩 밀렸다(예전 표8/9/10 → 표7/8/9, 예전 표11~15 → 표12~16). (2) 표12(6번
"현재 진행중인 공정")의 옛 표(유해위험요인/현재안전보건조치/위험성수준/평가, 5줄)를 지우고
표15(8번 "향후 진행공정" 상세표)를 통째로 복사해 그 자리에 붙여넣었다 — 그 결과 표12가
표15와 완전히 같은 "이름행+예방대책행+'위험성' 서브라벨 행" 3행짜리 구조가 됐지만, 항목을
1개밖에 못 담았다. (3) 그래서 표12/표15를 둘 다 더 깔끔한 진행공정/유해·위험요인/예방
대책/위험성수준 4열 × 5행(헤더 1 + 항목 4) 구조로 다시 짰다 — 항목마다 완전히 독립된 행
이라(병합 셀도, 겹친 필드도 없음) 항목당 필드 4개(이름/유해위험요인/예방대책/위험성)가
`t{표}_{(항목번호-1)×4+1}`부터 규칙적으로 반복된다. 위험성수준 칸에는 "상/중/하" 세 줄이
이미 들어있어서 `_risk_checklist()`가 실제 값과 일치하는 줄만 ☑, 나머지는 ☐로 채운다.
이 세 번의 조정 후 표13 이후 번호는 처음(1번) 조정 이후로 안 바뀌었다. 이 파일의 필드
접두사는 전부 최신 번호·구조 기준이다 — 자세한 배경은 `data/build_hwp_template.py`의
`_SOURCE_HWP` 주석과 `data/build_hwp_template_table6.py`/`build_hwp_template_equipment.py`
참고.

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
    """필드에 텍스트를 채운다. `put_field_text()`는 순수 "\\n"을 줄바꿈으로 인식하지 않고
    조용히 무시한다(이 문서의 실제 줄바꿈은 항상 "\\r\\n"으로 저장돼 있음 — 실측으로 확인).
    마법사(QTextEdit)에서 입력한 여러 줄짜리 텍스트(유해·위험요인, 예방대책 등)가 보고서에서
    한 줄로 이어붙어 보이는 문제가 있어, 모든 필드에 공통으로 "\\n" → "\\r\\n" 정규화를 적용한다.
    """
    if hwp.field_exist(field_name):
        text = value or ""
        if "\n" in text:
            text = text.replace("\r\n", "\n").replace("\n", "\r\n")
        hwp.put_field_text(field_name, text)


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
    """표7/8/9(건설기계장비·위험기계기구·유해위험물질 안전조치 평가)의 표 제목 칸 + 표 안
    소제목 칸(A2).

    표 맨 위 제목 칸(t7_001/t8_001/t9_001)은 원래 텍스트가 있던 자리인데 데이터 셀과 똑같이
    필드화되면서 빈 채로 남아있었다 — 원본 실제 문서의 제목 문구를 그대로 복원한다.

    표 안 소제목 칸(t{표}_category, A2)은 원본 문서 자체에 오기(誤記)가 있다 — 표7(건설기계
    장비 항목들이 들어있는 표)의 A2도 표8과 똑같이 "위험기계기구"라고 적혀있어서, 실제 항목
    구성과 안 맞는 라벨이 그대로 보였다(사용자가 확인해준 오류). 세 표 다 항목 구성에 맞는
    이름으로 명시적으로 다시 채운다.
    """
    _put(hwp, "t7_001", "건설기계장비에 대한 안전보건 조치 평가")
    _put(hwp, "t8_001", "위험기계기구에 대한 안전보건 조치 평가")
    _put(hwp, "t9_001", "유해위험물질에 대한 안전보건 조치 평가")

    _put(hwp, "t7_category", "건설기계장비")
    _put(hwp, "t8_category", "위험기계기구")
    _put(hwp, "t9_category", "유해위험물질")


def fill_equipment_data_fields(hwp, report: Report) -> None:
    """표7/8/9 데이터 행 — 항목별 유/무(t{표}_eq{i}_flag) + 지도사항 줄별 평가(t{표}_eq{i}_eval{줄번호}).

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
        (7, report.machinery_checks),
        (8, report.hand_tool_checks),
        (9, report.hazmat_checks),
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


def _risk_checklist(risk_level: str) -> str:
    """위험성수준 칸의 "상\\n중\\n하" 세 줄 각각의 앞에 체크(☑/☐)를 붙인다 — 실제 risk_level과
    일치하는 한 줄만 ☑, 나머지는 ☐. `put_field_text()`에 순수 "\\n"만 넣으면 줄바꿈으로
    인식되지 않고(가로로 이어 붙다가 폭에 걸려서만 밀려 내려감) 이 문서에서 실제 줄바꿈은
    항상 "\\r\\n"으로 저장돼 있는 것과 같은 이유로 보여 "\\r\\n"을 쓴다(실측으로 확인).
    """
    return "\r\n".join(f"{'☑' if risk_level == label else '☐'}{label}" for label in ("상", "중", "하"))


def fill_current_process_fields(hwp, report: Report) -> None:
    """표12: 현재 진행공정에 대한 유해·위험요인 파악 및 대책 — 진행공정/유해·위험요인/
    예방대책/위험성수준 4열 × 최대 4항목행.

    사용자가 한글에서 표12를 표15(8번 "향후 진행공정" 상세표)와 완전히 같은 구조로 직접
    다시 짰다 — 항목마다 물리적으로 독립된 행(병합 셀도, 겹친 필드도 없음)이라 필드 이름이
    항목당 4개씩 규칙적으로 반복된다(1번 항목: t12_001~004, 2번: t12_005~008, ...). 위험성
    수준 칸은 "상\\n중\\n하" 세 줄이 이미 들어있는 자리라 `_risk_checklist()`로 해당 줄만
    체크 표시한다. 예방대책 칸(+2번째 필드)만 원본 글자 크기가 Height=900으로 다른 칸(1000)
    보다 작게 남아 있어 `_fix_char_shape()`로 맞춘다.
    """
    entries = sorted(
        (e for e in report.current_process_entries if e.process_name), key=lambda e: e.slot
    )
    for i, entry in enumerate(entries[:4]):
        base = i * 4 + 1
        _put(hwp, f"t12_{base:03d}", entry.process_name)
        _put(hwp, f"t12_{base + 1:03d}", entry.hazard_text)
        _put(hwp, f"t12_{base + 2:03d}", entry.prevention_text)
        _fix_char_shape(hwp, f"t12_{base + 2:03d}", height=1000)
        _put(hwp, f"t12_{base + 3:03d}", _risk_checklist(entry.risk_level))


def fill_future_process_summary_fields(hwp, report: Report) -> None:
    """표14: "다음 방문시까지 발생하는 주요 진행공정 1~9" 요약 박스.

    우리는 최대 4개 진행공정만 수집하므로 1~4번 자리만 채우고 5~9번은 비운다. 번호 라벨
    칸("2","5")이 원본에 " ."이 붙어있어 정적 문구로 안 걸리고 필드화된 것도 여기서
    깔끔한 숫자로 되돌린다.
    """
    _put(hwp, "t14_002", "2")
    _put(hwp, "t14_006", "5")

    value_fields = ["t14_001", "t14_003", "t14_004", "t14_005", "t14_007", "t14_008", "t14_009", "t14_010", "t14_011"]
    names = [e.process_name for e in sorted(report.process_entries, key=lambda e: e.slot) if e.process_name]
    for i, field in enumerate(value_fields):
        _put(hwp, field, names[i] if i < len(names) else "")


def fill_future_process_detail_fields(hwp, report: Report) -> None:
    """표15: 향후 진행공정에 대한 유해·위험요인 파악 및 대책 — 진행공정/유해·위험요인/
    예방대책/위험성수준 4열 × 최대 4항목행. `fill_current_process_fields()`(표12)와 완전히
    같은 구조·같은 필드 이름 패턴이다 — 자세한 설명은 그쪽 docstring 참고.
    """
    entries = sorted(
        (e for e in report.process_entries if e.process_name), key=lambda e: e.slot
    )
    for i, entry in enumerate(entries[:4]):
        base = i * 4 + 1
        _put(hwp, f"t15_{base:03d}", entry.process_name)
        _put(hwp, f"t15_{base + 1:03d}", entry.hazard_text)
        _put(hwp, f"t15_{base + 2:03d}", entry.prevention_text)
        _fix_char_shape(hwp, f"t15_{base + 2:03d}", height=1000)
        _put(hwp, f"t15_{base + 3:03d}", _risk_checklist(entry.risk_level))


_TBM_LABEL_RESTORE = {
    "t16_001": "○ 참석인원 :",
    "t16_003": "○ 교육장소 : ",
    "t16_005": "○ 교육내용 :",
    "t16_008": "○ 교육자료 :",
}
# 표16은 라벨과 값이 별개의 필드다(둘 다 잘못 필드화됨) — 슬롯(장비사용 1/2)마다
# 라벨 필드는 고정 문구로 되돌리고, 값 필드에만 실제 계측자료를 채운다. name/place 칸은
# 병합 셀 순회 특성상 같은 셀 주소(예: B5)에 필드가 두 번(dup) 생성돼 있는데, 예전엔 둘 다
# 같은 값으로 채웠더니 텍스트가 겹쳐서 두 번 찍히는 문제가 있었다(실측 확인 — 표12/15와
# 달리 이 dup는 "하나만 렌더링되고 나머지는 무시"가 아니라 "둘 다 렌더링"되는 경우였다).
# 그래서 각 항목당 실제로 렌더링에 쓰이는 첫 번째 필드만 채우고, 중복 필드는 원본 그대로
# 빈 문자열로 남겨둔다.
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
    "action": "○ 조치사항 :                       -",
}


def _put_all(hwp, field_names: list[str], value: str) -> None:
    for name in field_names:
        _put(hwp, name, value)


_EQUIPMENT_PASS_FAIL_FIELDS = {
    1: ("t16_pass1", "t16_fail1"),
    2: ("t16_pass2", "t16_fail2"),
}


def _equipment_verdict(measurement) -> str | None:
    """계측값이 정상범위 안인지 판정한다 — 판정 기준이 코드로 정해진 계측기만 판정하고,
    그 외(아직 기준 비교 로직이 없는 계측기)는 None(판정 보류, 둘 다 체크 해제)을 반환한다.

    - 가스농도측정기: `vision_analyzer._read_gas_meter_value()`가 이미 "정상범위"/
      "정상범위 초과" 판정까지 끝내 `value`에 그대로 담아준다.
    - 조도계: 75Lux 이상이 정상(사용자가 실제 기준을 확인해준 방향 — 산업안전보건기준에
      관한 규칙의 "그 밖의 작업" 조도기준과 일치). 값이 숫자로 안 읽히면 판정하지 않는다.
    """
    if measurement is None:
        return None
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


_FINDING_RISK_BANDS = [
    (1, 3, "하", "현상\n유지", (134, 239, 172)),  # 연두색(사용자 요청)
    (4, 5, "중", "개선\n필요", (251, 146, 60)),
    (6, 9, "상", "즉시\n개선", (248, 113, 113)),
]


def _finding_risk_band(score: int) -> tuple[str, str, tuple[int, int, int] | None]:
    for lo, hi, grade, label, color in _FINDING_RISK_BANDS:
        if lo <= score <= hi:
            return grade, label, color
    return "", "", None


def _fill_finding_risk(hwp, slot: int, finding) -> None:
    """지적사항 위험성 수준 표(가능성/중대성/위험성 값 + 등급/관리기준 라벨)를 채운다.

    사용자가 한글에서 직접 일반 표 칸으로 재구성해서(원래는 중첩 표라 표6과 같은 한계로
    코드로 못 건드렸다), 각 칸(가능성/중대성/위험성 값, 등급, 관리기준)이 전부 독립된
    필드다. 관리기준 칸(`finding{slot}_action`)에만 등급별 배경색(즉시개선=빨강/
    개선필요=주황/현상유지=연두)을 `hwp.cell_fill()`로 입힌다.
    """
    likelihood_field = f"finding{slot}_likelihood"
    severity_field = f"finding{slot}_severity"
    score_field = f"finding{slot}_score"
    grade_field = f"finding{slot}_grade"
    action_field = f"finding{slot}_action"

    if not finding or finding.likelihood is None or finding.severity is None:
        _put(hwp, likelihood_field, "")
        _put(hwp, severity_field, "")
        _put(hwp, score_field, "")
        _put(hwp, grade_field, "")
        _put(hwp, action_field, "")
        return

    score = finding.likelihood * finding.severity
    grade, label, color = _finding_risk_band(score)
    _put(hwp, likelihood_field, str(finding.likelihood))
    _put(hwp, severity_field, str(finding.severity))
    _put(hwp, score_field, str(score))
    _put(hwp, grade_field, grade)
    _put(hwp, action_field, label)
    if color and hwp.field_exist(action_field):
        hwp.move_to_field(action_field, text=True, start=True, select=False)
        hwp.TableCellBlock()
        hwp.cell_fill(color)


def _find_table_ctrl_by_field(hwp, verify_field: str, max_hops: int = 60):
    """`verify_field`가 들어있는 표 컨트롤(gso) 자체를 찾는다 — 표1~16처럼 번호가 매겨진
    일반(문서 흐름에 얹힌) 표도 `get_into_nth_table()`로 들어간 캐럿만으로는 표 컨트롤
    객체 자체(삭제 대상)를 못 얻는다. 문서 전체의 "표" 컨트롤을 훑으며 각 컨트롤의 앵커
    위치에서 안으로 들어가(MoveRight) 물리 셀을 순서대로 밟다가, `verify_field`란 이름의
    필드가 나오는 컨트롤을 찾으면 그 컨트롤을 반환한다.
    """
    for ctrl in hwp.ctrl_list:
        if ctrl.UserDesc != "표":
            continue
        try:
            hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
            hwp.HAction.Run("MoveRight")
            if not hwp.is_cell():
                continue
            if hwp.get_cur_field_name() == verify_field:
                return ctrl
            for _ in range(max_hops):
                if not hwp.HAction.Run("TableRightCell"):
                    break
                if hwp.get_cur_field_name() == verify_field:
                    return ctrl
        except Exception:
            continue
    return None


def _delete_paragraph_containing(hwp, text: str) -> bool:
    """`text`가 들어있는 문단 전체(문단 부호 포함)를 지운다 — 표 밖의 독립된 섹션 제목
    문단을 지울 때 쓴다.

    예전엔 이 문단을 지운 뒤 남는 빈 문단을 "실제 내용이 나올 때까지" 계속 마저 지우는
    반복 루프가 있었는데, 그 판정이 텍스트 유무만 봐서(`get_selected_text().strip()`)
    다음에 오는 표(예: 12대 기인물 표처럼 붕 떠있는/앵커된 표)의 앵커 문자를 "빈 문단"으로
    잘못 읽고 함께 지워버려 표 전체가 통째로 사라지는 사고가 실측으로 확인됐다. 그래서
    제목 문단 하나만 지우고 멈춘다 — 남는 빈 페이지 정리는 `_remove_blank_pages`가
    (실제 내용을 건드리지 않는지 매번 확인하면서) 별도로 맡는다.
    """
    hwp.MoveDocBegin()
    if not hwp.find(text):
        return False
    hwp.HAction.Run("MoveParaBegin")
    hwp.HAction.Run("MoveSelParaBegin")
    hwp.HAction.Run("MoveSelNextParaBegin")
    hwp.HAction.Run("Delete")
    return True


_COLLAPSE_ROW_HEIGHT_MM = 2.0


def _collapse_row_at(hwp, field: str) -> None:
    if not hwp.field_exist(field):
        return
    hwp.move_to_field(field, text=True, start=True, select=False)
    hwp.TableCellBlockRow()
    pset = hwp.hwp.HParameterSet.HShapeObject
    hwp.hwp.HAction.GetDefault("TablePropertyDialog", pset.HSet)
    pset.HSet.SetItem("ShapeType", 3)
    pset.HSet.SetItem("ShapeCellSize", 1)
    pset.ShapeTableCell.Height = hwp.hwp.MiliToHwpUnit(_COLLAPSE_ROW_HEIGHT_MM)
    hwp.hwp.HAction.Execute("TablePropertyDialog", pset.HSet)
    hwp.Cancel()
    _put(hwp, field, "")


def _collapse_table_rows(hwp, row_start_fields: list[str]) -> None:
    """표를 지우는 대신, 알려진 행 시작 필드들이 있는 행(+맨 위 헤더 행) 전부를 눈에 안
    띄는 높이(2mm)로 접는다 — 표12/표15는 `delete_ctrl`이 성공(True)을 돌려주는데도 실제로는
    안 지워지는 걸 실측으로 확인했다(사용자가 한글에서 직접 재구성한 표라 뭔가 보호 속성이
    남아있는 것으로 추정 — 정확한 원인은 못 찾음). 완전히 사라지진 않지만 실질적으로 안
    보이는 수준까지는 줄어든다. `data/build_hwp_template_layout_fixes.py`의
    `_set_process_table_row_heights`(45mm로 키우는 것)와 반대 방향으로 같은 기법을 쓴다.
    """
    if row_start_fields and hwp.field_exist(row_start_fields[0]):
        hwp.move_to_field(row_start_fields[0], text=True, start=True, select=False)
        hwp.HAction.Run("TableColBegin")
        hwp.HAction.Run("TableColPageUp")
        hwp.TableCellBlockRow()
        pset = hwp.hwp.HParameterSet.HShapeObject
        hwp.hwp.HAction.GetDefault("TablePropertyDialog", pset.HSet)
        pset.HSet.SetItem("ShapeType", 3)
        pset.HSet.SetItem("ShapeCellSize", 1)
        pset.ShapeTableCell.Height = hwp.hwp.MiliToHwpUnit(_COLLAPSE_ROW_HEIGHT_MM)
        hwp.hwp.HAction.Execute("TablePropertyDialog", pset.HSet)
        hwp.Cancel()
    for field in row_start_fields:
        _collapse_row_at(hwp, field)


def remove_na_sections(hwp, report: Report) -> None:
    """마법사에서 "해당사항없음"으로 체크한 섹션은 보고서에 표 자체가 안 보이게 지운다.

    반드시 각 표를 채우는 `fill_*` 함수보다 먼저 호출해야 한다 — 표를 지우면 그 안의
    필드도 같이 사라지므로, 지울 표는 미리 지우고 남은 표만 채우는 게 안전하다.

    표마다 제목이 표 안(A1 등)에 포함된 것도 있고(표6 12대기인물, 표7/8/9 장비) 표 밖의
    독립된 문단인 것도 있다(표5 대형사고위험작업, 표12 현재진행공정, 표14/15 향후진행공정)
    — 직접 하나씩 실측해서 확인한 결과이며, 표 밖 제목은 표를 지워도 안 없어지므로 따로
    지워야 한다.
    """
    if report.previous_findings_na:
        # 표를 먼저 지우고 제목 문단은 나중에 지운다 — 순서가 바뀌면(제목을 먼저 지우면)
        # `_delete_paragraph_containing`의 빈 문단 정리 루프가 아직 안 지워진 표의 셀
        # 텍스트까지 "지금 문단 내용"으로 잘못 읽어서(표가 그 문단에 캐럭터처럼 얹혀있어
        # 문단 경계 판정이 헷갈림) 빈 문단이 안 남아있다고 오판하고 정리를 건너뛴다 —
        # 실측으로 확인한 순서 의존성이다.
        ctrl = _find_table_ctrl_by_field(hwp, "t4_001")
        if ctrl:
            hwp.delete_ctrl(ctrl)
        _delete_paragraph_containing(hwp, "이전 기술지도 사항 이행여부")

    if report.major_hazard_na:
        ctrl = _find_table_ctrl_by_field(hwp, "t5_001")
        if ctrl:
            hwp.delete_ctrl(ctrl)
        _delete_paragraph_containing(hwp, "대형사고 위험작업 사항")

    if report.hazard_factors_na:
        # 표6(12대 기인물)은 삭제를 시도해도 실제로는 안 지워진다(원인 미상, 사용자가
        # 직접 재구성한 표 — 실측 확인). 구조가 복잡해(항목 17개×줄마다 다른 필드) 표12/15
        # 처럼 행 단위로 접는 것도 위험 부담이 커서, 이번엔 손대지 않고 그대로 둔다 — 표는
        # 남지만 `fill_hazard_factor_fields`가 체크 항목 없이 전부 빈 칸(☐)으로 채운다.
        pass

    if report.equipment_checks_na:
        for field in ("t7_category", "t8_category", "t9_category"):
            ctrl = _find_table_ctrl_by_field(hwp, field)
            if ctrl:
                hwp.delete_ctrl(ctrl)

    if report.current_process_na:
        ctrl = _find_table_ctrl_by_field(hwp, "t12_001")
        if ctrl and hwp.field_exist("t12_001"):
            # delete_ctrl이 성공을 반환해도 실제로 안 지워지는 경우가 있어(표12/15와 같은
            # 원인), 지운 뒤 필드가 정말 사라졌는지 확인하고 안 사라졌으면 행 접기로 대체한다.
            hwp.delete_ctrl(ctrl)
        if hwp.field_exist("t12_001"):
            _collapse_table_rows(hwp, ["t12_001", "t12_005", "t12_009", "t12_013"])
        _delete_paragraph_containing(hwp, "현재 진행공정에 대한 유해")

    if report.process_na:
        for field in ("t14_001", "t15_001"):
            ctrl = _find_table_ctrl_by_field(hwp, field)
            if ctrl and hwp.field_exist(field):
                hwp.delete_ctrl(ctrl)
        if hwp.field_exist("t15_001"):
            _collapse_table_rows(hwp, ["t15_001", "t15_005", "t15_009", "t15_013"])
        _delete_paragraph_containing(hwp, "향후 진행공정에 대한 유해")

    _remove_blank_pages(hwp)


def _remove_blank_pages(hwp, max_pages_to_check=40) -> None:
    """표/제목 삭제 뒤 페이지 사이에 남는 빈 페이지를 지운다.

    `_delete_paragraph_containing`의 문단 정리만으로는 빈 페이지가 안 없어지는 경우가
    실측으로 확인됐다(표 필드는 확실히 지워졌는데도 빈 페이지 자체는 남음) — 사용자가
    조판부호를 켜고 빈 페이지 위치에 커서를 둔 채 Delete 키를 선택 없이 그냥 눌러서
    페이지가 사라지는 걸 직접 확인해줬다. `is_empty_page()`로 실제 빈 페이지만 골라
    그 위치에서 같은 동작(선택 없는 Delete)을 한다. 이 시점(remove_na_sections 안)엔 아직
    어떤 이미지도 안 붙어있어서(서명·사진·제공자료 이미지는 fill_all 이후 단계에서 붙는다),
    이미지만 있고 글자는 없는 페이지를 빈 페이지로 잘못 지울 위험이 없다.

    같은 페이지에서 Delete를 두 번째 누르면(첫 번째로 안 지워지고 남은 경우) 근처에 있는
    복잡한 개체(예: 12대 기인물 표, 사용자가 직접 재구성한 표)의 확인 대화상자가 뜨면서
    자동화가 멈추는 경우가 실측으로 확인됐다(SetMessageBoxMode로도 못 막음) — 그래서 페이지당
    Delete는 딱 한 번만 시도하고, 그걸로도 안 없어지면 그 페이지는 포기하고 다음으로 넘어간다.
    """
    checked_pages: set[int] = set()
    for _ in range(max_pages_to_check):
        total = hwp.PageCount
        blank_page = None
        for page in range(1, total + 1):
            if page in checked_pages:
                continue
            hwp.goto_page(page)
            if hwp.is_empty_page():
                blank_page = page
                break
        if blank_page is None:
            return

        hwp.goto_page(blank_page)
        hwp.HAction.Run("MoveParaBegin")
        start_offset = hwp.hwp.GetPos()[2]
        hwp.HAction.Run("MoveSelParaBegin")
        hwp.HAction.Run("MoveSelParaEnd")
        para_text = hwp.get_selected_text(keep_select=False)
        end_offset = hwp.hwp.GetPos()[2]
        # 글자가 하나도 없어 보여도(get_selected_text가 빈 문자열이어도) 문단 안에 앵커된
        # 개체(표 등)의 앵커 문자가 있으면 커서 이동만으로 위치가 0에서 안 움직인다 — 그런
        # 경우까지 "빈 문단"으로 오판해서 지우면 그 개체 전체가 통째로 사라진다(실측으로
        # 확인된 사고: 12대 기인물 표가 이 문단 정리 때문에 사라짐). 문단 길이가 0일 때만
        # 진짜 빈 문단으로 보고 지운다.
        if para_text.strip() or end_offset != start_offset:
            checked_pages.add(blank_page)
            continue
        hwp.Cancel()
        hwp.HAction.Run("Delete")
        if hwp.PageCount >= total:
            # 페이지가 안 줄었으면 이 Delete는 아무 효과 없이 바로 뒤 문단(예: "5. 필수
            # 지도 확인 사항"의 "5.")의 서식만 깨뜨리는 부작용만 남긴 경우가 실측으로
            # 확인됐다 — 효과가 없었으면 무조건 되돌린다.
            hwp.HAction.Run("Undo")
            checked_pages.add(blank_page)


def _find_finding_table_ctrl(hwp, slot: int):
    """`finding{slot}_hazard` 필드가 들어있는 표 컨트롤(gso) 자체를 찾는다.

    지적사항 표는 문서 흐름에 얹힌 독립된(떠다니는) 표라 `get_into_nth_table()`로는 못 찾고
    (표1~16 번호 체계 밖), `create_field()`가 만든 필드도 표 전체가 아니라 그 안의 칸
    하나만 가리킨다. 그래서 문서 전체의 "표" 컨트롤을 훑으면서, 각 컨트롤의 앵커 위치로
    이동해본 뒤 그 표 안쪽으로 두 칸 이동했을 때의 필드 이름이 정확히 이 슬롯의 것과
    일치하는 컨트롤만 골라낸다(표1의 "유해위험요인" 배너 텍스트가 모든 지적사항 표에서
    똑같아 텍스트만으로는 구분이 안 됨).
    """
    target_field = f"finding{slot}_hazard"
    for ctrl in hwp.ctrl_list:
        if ctrl.UserDesc != "표":
            continue
        try:
            hwp.hwp.SetPosBySet(ctrl.GetAnchorPos(0))
            hwp.HAction.Run("MoveRight")
            if not hwp.is_cell():
                continue
            hwp.HAction.Run("TableRightCell")
            hwp.HAction.Run("TableRightCell")
            if hwp.get_cur_field_name() == target_field:
                return ctrl
        except Exception:
            continue
    return None


def remove_unused_finding_blocks(hwp, report: Report) -> None:
    """데이터가 없는 지적사항 슬롯의 표 전체를 문서에서 지운다 — 지적사항이 1건뿐이면
    2번 지적사항 표(사진 없이 빈 칸만 있는 블록)가 보고서에 통째로 안 보이게 하기 위함.
    반드시 `fill_finding_fields`/`fill_finding_images`보다 먼저 호출해야 한다 — 표를 지우면
    그 안의 필드도 같이 사라지므로, 남은 슬롯만 채우는 게 안전하다.

    템플릿에 지적사항 표 1~4번이 모두 있다(마법사가 지원하는 최대 슬롯 수와 동일).
    """
    findings_by_slot = {} if report.findings_na else {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        if slot in findings_by_slot:
            continue
        if not hwp.field_exist(f"finding{slot}_hazard"):
            continue
        ctrl = _find_finding_table_ctrl(hwp, slot)
        if ctrl:
            hwp.delete_ctrl(ctrl)


def fill_finding_fields(hwp, report: Report) -> None:
    """7번 "현재 공정 내 현존하는 위험성 제거" — 지적사항 1~4 항목의 유해위험요인/재해예방
    대책/위험성 수준(가능성·중대성·위험도+등급 배경색)을 채운다. 사진은
    `report_builder_hwp_images.fill_finding_images()`가 맡고, 이행결과(추후확인/즉시이행)는
    대응하는 DB 컬럼이 아직 없어 빈 채로 둔다.

    데이터 없는 슬롯의 표는 `remove_unused_finding_blocks()`가 이미 지웠으므로, 여기선
    남아있는 필드만 자연히 채워진다(`_put`/`hwp.field_exist` 체크가 없는 슬롯은 조용히
    건너뜀).

    표1~16 번호 체계 밖의 별도 표라 필드 이름이 `finding{slot}_*`로 따로 붙어있다
    (`data/build_hwp_template.py`의 t-접두사 규칙과 무관).
    """
    findings = {f.slot: f for f in report.findings}
    for slot in (1, 2, 3, 4):
        finding = findings.get(slot)
        _put(hwp, f"finding{slot}_hazard", finding.title if finding else "")
        _put(hwp, f"finding{slot}_countermeasure", finding.content if finding else "")
        _fill_finding_risk(hwp, slot, finding)


def fill_support_fields(hwp, report: Report) -> None:
    """표16: 사업장 지원 사항 — TBM(참석인원/장소/내용/자료) + 장비사용(최대 2건).

    `report_builder_pdf.py`의 `_build_support_section`과 같은 규칙(값이 있는 계측자료만,
    측정장소는 "현장 내" 고정, 조치사항은 "-" 고정, 안전기준은 `MeasurementStandard` 조회)을
    그대로 따른다. 교육장소 칸(표16 F2)은 원본 문서의 샘플 값("현장")이 문서 다른 곳의
    공통 정적 라벨과 우연히 겹쳐 템플릿 자동 생성 때 필드화가 안 됐던 자리라, 템플릿
    파일에 직접 `t16_edu_location` 필드를 만들어 넣었다(`data/build_hwp_template.py`의
    `_add_education_location_field()`가 재빌드 시에도 이 필드를 만든다). 장비사용(1)/(2)의
    "☑양호/☐불량" 체크박스도 같은 이유(체크박스 폼 컨트롤은 코드로 상태를 못 바꿈)로
    `t16_pass{1,2}`/`t16_fail{1,2}` 텍스트 필드로 대체했다 — 원래는 항상 "양호"가 체크된
    채 고정이었다.
    """
    for field, text in _TBM_LABEL_RESTORE.items():
        _put(hwp, field, text)

    education = report.safety_education
    _put(hwp, "t16_002", f"{education.attendee_count} 명" if education and education.attendee_count is not None else "")
    _put(hwp, "t16_edu_location", education.location if education else "")
    _put(hwp, "t16_006", education.content if education else "")
    _put(hwp, "t16_009", education.material if education else "")

    with SessionLocal() as session:
        standards = {s.instrument_type: s.standard_criteria for s in session.query(MeasurementStandard).all()}
    used = [m for m in report.measurements if m.value]

    for slot_no, fields in _EQUIPMENT_SLOTS.items():
        for key in ("name_label", "place_label", "value_label", "std_label", "action"):
            _put_all(hwp, fields[key], _EQUIPMENT_LABEL_TEXT[key])

        measurement = used[slot_no - 1] if slot_no - 1 < len(used) else None

        pass_field, fail_field = _EQUIPMENT_PASS_FAIL_FIELDS[slot_no]
        verdict = _equipment_verdict(measurement)
        _put(hwp, pass_field, f"{'☑' if verdict == '양호' else '☐'}양호")
        _put(hwp, fail_field, f"{'☑' if verdict == '불량' else '☐'}불량")

        if measurement is None:
            continue
        _put_all(hwp, fields["name_value"], measurement.instrument_type)
        _put_all(hwp, fields["place_value"], "현장 내")
        if measurement.instrument_type == "가스농도측정기":
            # "정상범위"/"정상범위 초과"는 이미 완결된 판정 문구라 단위(ppm)를 붙이지 않는다.
            _put_all(hwp, fields["value_value"], measurement.value)
        else:
            unit = next((u for name, u in MEASUREMENT_INSTRUMENTS if name == measurement.instrument_type), "")
            _put_all(hwp, fields["value_value"], f"{measurement.value} {unit}".strip())
        _put_all(hwp, fields["std_value"], standards.get(measurement.instrument_type, "-"))


def fill_all(hwp, report: Report, site: Site) -> None:
    fill_management_no(hwp, site)
    fill_site_fields(hwp, site)
    fill_company_fields(hwp, site)
    fill_signoff_fields(hwp, report, site)
    remove_na_sections(hwp, report)
    fill_major_hazard_work_fields(hwp, report)
    fill_hazard_factor_fields(hwp, report)
    fill_equipment_section_titles(hwp)
    fill_equipment_data_fields(hwp, report)
    fill_current_process_fields(hwp, report)
    fill_future_process_summary_fields(hwp, report)
    fill_future_process_detail_fields(hwp, report)
    remove_unused_finding_blocks(hwp, report)
    fill_finding_fields(hwp, report)
    fill_support_fields(hwp, report)
