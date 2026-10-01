"""K2B(k2b.kosha.or.kr) 실제 화면 셀렉터.

`record_flow.py`(Playwright codegen) 녹화 결과(`data/recorded_flow.py`)에서 추출.
이 사이트는 Nexacro 기반이라 요소 id가 `mainframe_VFrameSet_MainFrame_<모듈코드>_form_tab_..._<필드코드>`
패턴이다. 목록화면의 모듈코드 `103015010`은 세션이 바뀌어도 고정이지만, 상세입력 모달의
모듈코드(예: `EBP00130_P01`)는 Nexacro가 세션마다 다르게 배정하는 프레임 인스턴스 번호로
보여 고정값이 아니다(2026-09-16 발견, `_modal()` 헬퍼 참고) -- 그래서 상세 모달 쪽 상수는
전체 id가 아니라 `_modal()`로 만든 "id 끝부분 일치" attribute selector를 쓴다.

각 상수 옆에 확인 상태를 표시:
  CONFIRMED - 실제 녹화에서 동작 확인됨
  GUESS     - 다른 필드와의 패턴 유추, 실사용 전 검증 필요
  TODO      - 아직 모름, 추가 확인 필요
"""

from __future__ import annotations

# --- 로그인 (CONFIRMED) ---
LOGIN_ID_INPUT = "#mainframe_VFrameSet_LoginFrame_form_div_Login_div_box_edt_mber_id_input"
LOGIN_PW_INPUT = "#mainframe_VFrameSet_LoginFrame_form_div_Login_div_box_edt_password_input"
LOGIN_BUTTON_TEXT = "로그인"  # get_by_text(..., exact=True)

# --- 메뉴 이동 (CONFIRMED) ---
MENU_GUIDANCE_SUPPORT_TEXT = "건설재해예방전문기관 기술지원"
MENU_TREE_ITEM_ID = (
    "#mainframe_VFrameSet_MainFrame_form_div_Form_div_Left_grd_Menu_body_gridrow_1_cell_1_1_controltreeTextBoxElement"
)
MENU_GUIDANCE_ITEM_TEXT = "재해예방기관 기술지도"

# --- 검색 화면 (CONFIRMED, 모듈코드 103015010) ---
SEARCH_SITE_NAME_INPUT = (
    "#mainframe_VFrameSet_MainFrame_form_div_Form_div_Work_103015010_div_Work_div_Search_edt_ENTRPS_NM_input"
)
SEARCH_BUTTON_CONTAINER_ID = (
    "#mainframe_VFrameSet_MainFrame_form_div_Form_div_Work_103015010_div_Work_div_Search_btn_SearchTextBoxElement"
)
SEARCH_BUTTON_TEXT = "조회"

# 결과 행 선택 - CONFIRMED: 체크박스 없이 현장명 텍스트가 있는 행을 그냥 클릭하면 선택되고
# (218건 중 특정 행 클릭 -> 아래 패널에 해당 데이터 로드 확인됨) 상세보기가 그 행을 연다.
DETAIL_VIEW_BUTTON_TEXT = "상세보기"  # CONFIRMED

# --- 상세 모달 ---
# 주의(2026-09-16 발견, 중요): 모달의 모듈코드(예: EBP00130_P01)는 고정된 화면 코드가
# 아니라 Nexacro가 세션마다 동적으로 배정하는 프레임 인스턴스 번호로 보인다 -- 2026-09-15엔
# EBP00130_P01이었는데 2026-09-16 같은 화면을 다시 열어보니 EBP00120_P01로 확인됨(실측:
# 이전 하드코딩 셀렉터가 새 세션에서 0건 매치). 그래서 전체 모듈코드 접두사로 고정하지
# 않고, 뒤쪽의 안정적인 접미사(`_form_tab_Main_tabpage1_...`)만으로 attribute selector
# (`[id$=...]`)를 만들어 어느 세션에서든 매치되도록 한다. (검색화면의 "103015010"은 반대로
# 세션이 바뀌어도 동일함을 확인했으므로 그쪽은 그대로 둔다.)
_MODAL_ID_SUFFIX = "_form_tab_Main_tabpage1"


def _modal(id_suffix: str) -> str:
    """상세 모달 안의 요소를 id 끝부분 일치로 찾는 CSS attribute selector를 만든다."""
    return f"[id$='{_MODAL_ID_SUFFIX}{id_suffix}']"


ADD_ROUND_BUTTON_ID = _modal("_btn_AddTextBoxElement")
ADD_ROUND_BUTTON_TEXT = "추가"

# 기술지도일 - "+추가" 클릭 시 오늘 날짜로 자동 채워짐(CONFIRMED). 캘린더 아이콘 클릭 ->
# 팝업(해당 월 달력, 헤더 "◀ YYYY.MM ▶" + 요일/날짜 그리드) -> 원하는 날짜 클릭 -> 필드에
# 반영(CONFIRMED, 같은 달/다른 달 모두 실기록으로 검증: 09-09 -> 09-20, 이후 다른 달로도
# 이동해 날짜 선택 검증함).
# 팝업 내부 요소도 위 _modal()과 같은 이유로 접미사 매칭을 쓴다(팝업 id 자체가
# `..._cal_TCHGUD_YMD_popupcalendar_...` 형태로 모달 접두사에 종속됨).
GUIDANCE_DATE_CALENDAR_BUTTON_ID = _modal("_cal_TCHGUD_YMD_dropbuttonAlignImageElement")
GUIDANCE_DATE_CALENDAR_YEAR_ID = _modal("_cal_TCHGUD_YMD_popupcalendar_header_yearStatic")  # 텍스트 "YYYY."
GUIDANCE_DATE_CALENDAR_MONTH_ID = _modal("_cal_TCHGUD_YMD_popupcalendar_header_monthStatic")  # 텍스트 "MM"
GUIDANCE_DATE_CALENDAR_PREV_BUTTON_ID = _modal("_cal_TCHGUD_YMD_popupcalendar_header_prevbutton")
GUIDANCE_DATE_CALENDAR_NEXT_BUTTON_ID = _modal("_cal_TCHGUD_YMD_popupcalendar_header_nextbutton")
# 주의(CONFIRMED, DOM 전체 스캔으로 확인): 날짜 셀은 Nexacro 특성상 42칸(6주 x 7일) 전부
# **동일한 id**를 공유한다(중복 id, 개별 구분 불가) -- 그래서 텍스트로 찾으면 이전달/다음달
# 잔여일과 겹쳐 모호하다(예: 이번 달 마지막 날이 30/31이면 그리드 맨 앞의 "지난달 30/31"과
# 텍스트가 같아 `.first`가 엉뚱한 셀을 고를 수 있음). 대신 attribute selector로 전체 42칸을
# 가져와서, 목표 월 1일의 요일로 계산한 그리드 인덱스를 `.nth()`로 지정해 정확히 찾는다
# (K2BClient.set_guidance_date 참고).
GUIDANCE_DATE_CALENDAR_DAY_CELLS = _modal("_cal_TCHGUD_YMD_popupcalendar_body_daystatic")

PROGRESS_RATE_INPUT_ID = _modal("_edt_PROCS_RAT_CVALUE_input")  # CONFIRMED, .fill("70") 동작

# 점검자 - CONFIRMED readonly (입력 시도해도 값이 안 바뀜, is_editable()=False, readonly
# 속성 존재). 로그인한 K2B 계정의 실명이 자동으로 들어가는 것으로 추정(기존 차수마다 값이
# 다른 건 그 회차를 저장할 때 로그인했던 계정이 달랐기 때문으로 보임 -- 검증은 아직 TODO,
# 고객에게 "담당요원별로 K2B 계정이 따로 있는지" 확인 필요). 그때까지 이 필드는 채우려
# 시도하지 않는다.
INSPECTOR_NAME_INPUT_ID = _modal("_edt_INSCTR_NM_input")  # CONFIRMED readonly -- 채우지 말 것

SITE_MANAGER_NAME_INPUT_ID = _modal("_edt_SPT_RSPNBER_NM_input")  # CONFIRMED, 편집 가능
SPECIAL_NOTE_INPUT_ID = _modal("_edt_PARTCLR_MATTER_CN_input")  # CONFIRMED (특이사항)
# 지도건수·교육인원·배포자료건수 — 새 차수에서 셋 다 빈 칸, 편집 가능(readOnly·disabled 아님) CONFIRMED 2026-10-02
GUIDANCE_COUNT_INPUT_ID = _modal("_edt_CCH_NOCS_input")  # 지도건수
EDUCATION_COUNT_INPUT_ID = _modal("_edt_PREARNGE_NMPR_CNT_input")  # 교육인원
DISTRIBUTED_MATERIAL_COUNT_INPUT_ID = _modal("_edt_WDTB_DATA_NOCS_input")  # 배포자료건수

# 현장책임자 연락처 - CONFIRMED. 겉보기엔 3칸(지역-국번-번호)처럼 보이지만 실제로는
# **마스크 입력(msk_) 단일 필드 하나**다. 빈 값일 때 placeholder가 "___-____-____"로
# 표시돼 3칸처럼 보였을 뿐. 숫자만 순서대로 press_sequentially하면 마스크가 자동으로
# 하이픈을 넣어준다(실기록: "01099998888" 입력 -> "010-9999-8888"로 정확히 반영, 원복 완료).
SITE_MANAGER_PHONE_INPUT_ID = _modal("_msk_SPT_RSPNBER_TELNO_input")

CURRENT_PROCESS_DROPDOWN_ID = _modal("_cbo_NOW_OPERT_PROCS_dropbutton") + " > div"  # CONFIRMED
# 옵션 선택은 드롭다운 클릭 후 get_by_text(옵션명)으로 선택 (CONFIRMED, 예: "굴착공사")
CURRENT_PROCESS_OPTIONS = [
    "가설공사", "굴착공사", "골조공사", "마감공사", "부대토목공사", "실내인테리어공사", "기타공사",
]  # CONFIRMED (드롭다운 전체 목록 실화면 확인)

# 비계사용현황/비계종류.
# "사용"/"미사용" 라디오는 그룹 전체가 같은 id(rdo_SCFDG_USE_YN_item)로 묶여 개별 id가
# 없어 텍스트 클릭으로 처리해야 한다(GUIDANCE_DATE 등과 달리 id 지정 불가).
SCAFFOLD_USAGE_RADIO_GROUP_TEXT = {"사용": "사용", "미사용": "미사용"}  # get_by_text(exact=True)로 클릭
# 버그 수정(2026-09-16, 중요): Day1엔 이 체크박스가 "상세모달이 아니라 뒤에 깔린 검색화면
# 모듈(103015010) DOM에 속한다"고 기록했는데 -- 이건 **틀렸다**. DOM 전체를 "강관비계"
# 텍스트로 검색해보니 똑같은 문구가 실제로 2곳에 존재함:
#   1) `..._103015010_div_Work_CURR_SCFDG_INSTL_STLE_CMMN_CD_5` (검색화면 소속, id에
#      "CURR_" 접두사 있음) -- 화면 좌표가 모달 창 범위(x=280~1000) **밖**(x=1120)에 있어
#      Nexacro의 모달 배경 딤(dim) 오버레이(반투명 회색, z-index 1000002)에 항상 가려져
#      있다. `document.elementFromPoint()`로 실측: 이 좌표를 클릭하면 체크박스가 아니라
#      그 오버레이가 이벤트를 받는다 -- Playwright가 아무리 정확히 좌표를 계산해 클릭해도
#      절대 안 먹히는 이유였음(반면 사람이 실제로 화면을 보고 클릭하면 "보이는" 진짜
#      체크박스, 즉 아래 2번을 클릭하게 되므로 성공했던 것 -- 셀렉터가 가리키는 요소와
#      화면에 실제로 보이는 요소가 서로 다른 요소였다).
#   2) `..._EBP00130_P01_form_tab_Main_tabpage1_SCFDG_INSTL_STLE_CMMN_CD_5` ("CURR_" 접두사
#      없음) -- **상세모달 소속**, 화면 좌표가 모달 범위 안(x=797)이라 실제로 보이고
#      클릭 가능한 진짜 체크박스. `_modal()`로 접미사 매칭.
SCAFFOLD_TYPE_CHECKBOX_IDS = {
    "강관비계": _modal("_SCFDG_INSTL_STLE_CMMN_CD_5_chkimg") + " > div",  # CONFIRMED(수정됨)
    "시스템비계": _modal("_SCFDG_INSTL_STLE_CMMN_CD_6_chkimg") + " > div",  # CONFIRMED(수정됨)
}  # "사용" 선택 후에만 클릭 가능(미사용 상태에서는 비활성화됨)

# 현장책임자 등 통보방법 체크박스 - 전체 CONFIRMED: 003=전자우편은 실제 저장된 데이터
# (마산3리 2회차)로, 001/002/004/005는 각 라벨 옆 요소의 실제 id를 직접 조회해 확인.
NOTIFICATION_METHOD_CHECKBOX_IDS = {
    "직접전달": _modal("_chk01_001_chkimg") + " > div",  # CONFIRMED
    "등기우편": _modal("_chk01_002_chkimg") + " > div",  # CONFIRMED
    "전자우편": _modal("_chk01_003_chkimg") + " > div",  # CONFIRMED
    "모바일": _modal("_chk01_004_chkimg") + " > div",  # CONFIRMED
    "기타": _modal("_chk01_005_chkimg") + " > div",  # CONFIRMED
}

# 이전 기술지도 이행여부 체크박스. 코드 체계가 대칭적(Y/N)이 아니라 0/1/N임을 DOM 전체
# id 스캔으로 먼저 찾음(chk02_0/chk02_1/chk02_N 세 개만 존재).
# 버그 수정(2026-09-16): Day1엔 "chk02_N=불이행/chk02_0=해당없음"으로 기록했는데, 실제로는
# **반대**였다 -- 오늘 각 요소의 실제 textContent를 DOM에서 직접 읽어 chk02_0="불이행",
# chk02_N="해당없음"임을 확인(CONFIRMED). 이 때문에 그동안 "불이행"을 넣으면 실제로는
# "해당없음" 체크박스가 클릭돼, 정작 "불이행"은 항상 체크가 안 된 채로 남아있었다(사용자가
# 실제 화면에서 발견 신고).
PREV_GUIDANCE_IMPLEMENTED_CHECKBOX_IDS = {
    "이행": _modal("_chk02_1_chkimg") + " > div",  # CONFIRMED
    "불이행": _modal("_chk02_0_chkimg") + " > div",  # CONFIRMED(수정됨, 2026-09-16)
    "해당없음": _modal("_chk02_N_chkimg") + " > div",  # CONFIRMED(수정됨, 2026-09-16)
}

# 사진첨부 버튼 3종 - CONFIRMED (실제 화면 스크롤로 순서/섹션 확인 완료):
# imgAdd=현장전경, imgAdd2=현장점검, imgAdd3=현장개선.
PHOTO_ATTACH_BUTTON_IDS = {
    "현장전경": _modal("_btn_imgAddTextBoxElement"),  # CONFIRMED
    "현장점검": _modal("_btn_imgAdd2TextBoxElement"),  # CONFIRMED
    "현장개선": _modal("_btn_imgAdd3TextBoxElement"),  # CONFIRMED
}
PHOTO_ATTACH_BUTTON_TEXT = "사진첨부"

# 대형사고 위험작업 - CONFIRMED 전체 흐름 (추가 -> 발생형태/위험작업/예정시기 각각 설정 ->
# 제거까지 실기록으로 검증, 2026-09-16 그리드 구조 전체 재확인).
# "추가" 클릭 시 새 행이 맨 아래에 추가된다(업무영역="재해예방 기술지도" 고정값 자동 채움,
# 발생형태="전체" 기본값, 대형사고 위험작업="선택" 플레이스홀더, 예정시기 시작/종료 둘 다
# 오늘 날짜로 자동 채움). 각 행의 id는 `..._grd_List_body_gridrow_{행번호}_cell_{행번호}_{열번호}`
# 형태(행번호는 0부터, 열: 0=순번 1=업무영역 2=발생형태 3=대형사고위험작업 4=예정시기시작
# 5=예정시기종료) -- 여러 행을 만들 때 이 인덱스로 정확한 행을 지정한다.
# 주의(실기록): 어떤 셀이든 편집모드(드롭다운/캘린더 열림)로 남아있는 상태에서 "+ 추가"를
# 누르면 무시되고 새 행이 안 생긴다 -- 다른 곳(예: 섹션 제목)을 먼저 클릭해 편집모드를
# 벗어난 뒤 추가해야 한다(add_major_hazard_work에 반영함).
MAJOR_HAZARD_WORK_ADD_BUTTON_ID = _modal("_div_Cnstrc_btn_AddTextBoxElement")  # CONFIRMED
MAJOR_HAZARD_WORK_TITLE_ID = _modal("_div_Cnstrc_div_Title_Static00")  # CONFIRMED, 편집모드 벗어나려 클릭용
MAJOR_HAZARD_WORK_REMOVE_BUTTON_TEXT = "제거"  # CONFIRMED (같은 영역 내 버튼, 텍스트로 클릭)
MAJOR_HAZARD_WORK_NA_CHECKBOX_TEXT = "해당없음"  # 존재만 CONFIRMED, 동작은 TODO
MAJOR_HAZARD_WORK_OPTIONS = [
    "비계 설치 및 해체",
    "거푸집동바리(작업발판 일체형 거푸집 포함) 설치 및 해체",
    "흙막이지보공(내공 단면적 2㎡미만 터널 지보공 포함) 설치 및 해체",
    "기타 추락위험 장소·작업(달비계 작업, 지붕공사 등)",
    "밀폐공간 및 화재·폭발",
]  # CONFIRMED
MAJOR_HAZARD_WORK_OCCURRENCE_TYPES = ["전체", "붕괴", "도괴", "낙하", "질식"]  # CONFIRMED, 드롭다운 클릭해 실제 확인

# 발생형태를 먼저 선택해야 대형사고위험작업 드롭다운의 선택지가 그에 맞게 필터링된다
# (사이트 자체 동작, CONFIRMED — 스크린샷 5장으로 각 발생형태별 실제 노출 항목 확인 후,
# 디버그 스크립트로 실제 DOM 텍스트를 코드포인트 단위까지 대조해 재검증함, 2026-09-16).
# "전체"는 5개 항목 전부 노출.
#
# 주의(실기록, 2026-09-16): 스크린샷만 보고 옮겨적은 "흙막이지보공(내공단면적 ...)"
# 문자열에 "내공"과 "단면적" 사이 띄어쓰기가 빠져 있었다 -- get_by_text(exact=True)가
# 계속 못 찾아 30초 타임아웃 후 자동화가 멈추는 원인이었음. 사람 눈에는 스크린샷 속
# 좁은 폰트로 붙어있는 것처럼 보여도 실제 사이트 텍스트엔 공백이 있었다(코드포인트 비교로
# 확인). 교훈: 사이트 텍스트를 손으로 옮겨적은 문자열은 exact 매칭 전에 실제 DOM
# textContent와 코드포인트 단위로 대조해볼 것 -- 스크린샷 눈대중은 공백/특수문자
# 오타를 놓치기 쉽다.
MAJOR_HAZARD_WORK_OPTIONS_BY_OCCURRENCE: dict[str, list[str]] = {
    "전체": MAJOR_HAZARD_WORK_OPTIONS,
    "붕괴": ["비계 설치 및 해체"],
    "도괴": [
        "거푸집동바리(작업발판 일체형 거푸집 포함) 설치 및 해체",
        "흙막이지보공(내공 단면적 2㎡미만 터널 지보공 포함) 설치 및 해체",
    ],
    "낙하": ["기타 추락위험 장소·작업(달비계 작업, 지붕공사 등)"],
    "질식": ["밀폐공간 및 화재·폭발"],
}  # CONFIRMED


def major_hazard_cell(row: int, col: int) -> str:
    """대형사고 위험작업 그리드 셀 접미사 매칭 selector. col: 2=발생형태 3=대형사고위험작업
    4=예정시기시작 5=예정시기종료 (0=순번/1=업무영역은 자동값이라 안 씀)."""
    return _modal(f"_div_Cnstrc_grd_List_body_gridrow_{row}_cell_{row}_{col}")


# 발생형태(열2)/대형사고위험작업(열3) 셀을 클릭하면 그리드 공용 콤보 오버레이가 그 위에
# 뜬다(모든 행이 같은 id를 공유 -- 클릭한 셀 위치로 옮겨 그려짐, CONFIRMED).
MAJOR_HAZARD_WORK_CELL_COMBO_ID = _modal("_div_Cnstrc_grd_List_controlcombo")
# 예정시기(열4/5) 셀을 클릭하면 그리드 공용 캘린더 오버레이가 뜬다 -- 기술지도일 캘린더와
# 완전히 같은 구조(header 연/월 + prev/next 버튼 + 42칸 중복id 날짜 그리드), CONFIRMED.
MAJOR_HAZARD_WORK_CALENDAR_DROPBUTTON_ID = _modal("_div_Cnstrc_grd_List_controlcalendar_dropbutton")
MAJOR_HAZARD_WORK_CALENDAR_YEAR_ID = _modal("_div_Cnstrc_grd_List_controlcalendar_popupcalendar_header_yearStatic")
MAJOR_HAZARD_WORK_CALENDAR_MONTH_ID = _modal("_div_Cnstrc_grd_List_controlcalendar_popupcalendar_header_monthStatic")
MAJOR_HAZARD_WORK_CALENDAR_PREV_BUTTON_ID = _modal("_div_Cnstrc_grd_List_controlcalendar_popupcalendar_header_prevbutton")
MAJOR_HAZARD_WORK_CALENDAR_NEXT_BUTTON_ID = _modal("_div_Cnstrc_grd_List_controlcalendar_popupcalendar_header_nextbutton")
MAJOR_HAZARD_WORK_CALENDAR_DAY_CELLS = _modal("_div_Cnstrc_grd_List_controlcalendar_popupcalendar_body_daystatic")

# 불량사업장 통보 -- 상세모달(_modal()) 소속, DOM 전체 스캔으로 확인(전부 CONFIRMED,
# 2026-09-16). 체크박스 체크 -> 신고내용/처리상태/신고일/첨부파일 목록 섹션이 나타난다.
BAD_SITE_NOTIFY_CHECKBOX_ID = _modal("_Chk_Bnotice_chkimg") + " > div"  # CONFIRMED
# 신고내용 -- 실제 입력 요소(<textarea>, id 끝 "_Txa_Notice_textarea")는 항상
# visibility:hidden으로 보고돼(Nexacro가 이 영역을 가상 스크롤로 그리는 것으로 추정,
# 체크 여부와 무관), Playwright의 기본 click()/fill()이 "element is not visible"로
# 거부한다. 대신 바로 바깥 컨테이너(id 끝 "_Txa_Notice", 이건 실제로 visible)를 클릭해
# 포커스를 준 뒤 키보드로 입력하면 내부 textarea 값에 정상 반영됨(CONFIRMED, 실기록:
# 클릭 후 page.keyboard.type()으로 입력 -> textarea.value에 그대로 저장됨 확인).
BAD_SITE_NOTIFY_CONTENT_CONTAINER_ID = _modal("_Txa_Notice")  # CONFIRMED (여기를 클릭해서 포커스)
BAD_SITE_NOTIFY_CONTENT_TEXTAREA_ID = _modal("_Txa_Notice_textarea")  # CONFIRMED이지만 직접 클릭 금지(위 설명)
BAD_SITE_NOTIFY_ATTACH_BUTTON_ID = _modal("_btn_errAdd")  # CONFIRMED, "불량사업장 사진 및 보고서 첨부"

# 보고서 파일첨부 - CONFIRMED. "보고서" 섹션(맨 아래, 현장개선 사진 다음)의 파일첨부 버튼.
# 12-1에서 생성된 실제 결과보고서 파일이 여기 들어간다.
# 형식 CONFIRMED: HWP/HWPX는 첨부 자체가 안 되고 **PDF만 가능**(실사용 중 확인) -- 더 이상
# "미확정" 아님, report_file_path는 항상 PDF를 쓴다(db_reader.py 참고).
# 실제 데이터로 확인된 제약: "기술지도일 이후 7일 초과 시 보고서 수정 불가" -- 자동화
# 스케줄링 시 이 기한 안에 제출해야 함.
REPORT_FILE_ATTACH_BUTTON_ID = _modal("_btn_etcAddTextBoxElement")  # CONFIRMED
REPORT_FILE_ATTACH_BUTTON_TEXT = "파일첨부"
# "보고서 수정가능 기한" 표시 필드 -- CONFIRMED(MDFCN_POSBL_YMD = 수정가능일). 이 날짜가
# 지나면 REPORT_FILE_ATTACH_BUTTON이 비활성화돼 클릭해도 반응이 없다(실사용 중 재현:
# 기존 차수를 그대로 열어 편집했더니 기한이 지나있어 "파일첨부"를 눌러도 파일선택창이
# 전혀 안 뜨고 filechooser 이벤트 타임아웃만 남 -- 스크롤 문제가 아니었음).
REPORT_MODIFIABLE_UNTIL_INPUT_ID = _modal("_cal_MDFCN_POSBL_YMD_calendaredit_input")

# 최종 저장(=제출) - 의도적으로 이 파일에 셀렉터를 넣지 않는다.
# 모든 기능이 검증된 뒤 마지막 단계에서만 추가한다 (README "개발 단계 안내" 참고).
SAVE_SUBMIT_BUTTON_ID = None  # 의도적 미구현

# 로그인 주소(14번 core/config.py에서 옮김)
K2B_LOGIN_URL = "https://k2b.kosha.or.kr/"

# --- 웹판에서 실측해 추가(2026-10-01, 코하이젠 시험 6차수 저장·삭제) ---
# 대형사고 위험작업이 없을 때 체크 — 안 하면 저장 때 "[대형사고 위험작업] 항목이 존재하지 않습니다 … [해당없음]을 체크해주세요"(CONFIRMED).
# (위 MAJOR_HAZARD_WORK_NA_CHECKBOX_TEXT 주석과 달리 새 차수에서 기본 체크가 아님)
MAJOR_HAZARD_NONE_CHECKBOX = "[id$='tabpage1_div_Cnstrc_chk_NTextBoxElement']"
ROUND_NO_INPUT = "[id$='tabpage1_edt_SORT_ORDR_input']"  # 차수(새 차수 추가 뒤 K2B가 매긴 번호) CONFIRMED
DETAIL_SAVE_BUTTON = "[id$='tabpage1_btn_SaveTextBoxElement']"  # 상세내용 [+ 추가][삭제][저장]의 저장 CONFIRMED
# 알림·확인 창: 버튼 id 안에 문구가 들어 있다 — "…EBP00130_P01_저장하시겠습니까?_form_div_Btn_btn_confirmTextBoxElement"(CONFIRMED).
# 저장 순서: [저장] → "저장하시겠습니까?" [확인] → "정상적으로 저장되었습니다." [확인]. 필수 칸이 비면 그 문구 한 개짜리 창
# (실측: "비계사용현황을 입력해주세요.", 대형사고 위험작업 해당없음). 필수: 기술지도일·점검자·공정률·현재 작업공종·비계사용현황·통보방법·이전 지도 이행여부.
POPUP_CONFIRM_BUTTONS = "[id*='_form_'][id$='btn_confirmTextBoxElement']"
SAVE_ASK_TEXT = "저장하시겠습니까"
SAVE_DONE_TEXT = "정상적으로 저장"

# --- 문제점 및 개선 요청사항(2026-10-02 실측, 저장 없이) ---
# [+ 추가]마다 맨 아래에 줄이 생긴다. 열: 0=번호 1=문제점 및 개선 요청사항 2=삭제. 1열 셀을 두 번 누르면 편집 textarea가 뜨고
# 키보드 입력·Enter 줄바꿈이 그대로 들어감 — 다른 줄의 번호 칸을 누르면 값이 셀에 확정(CONFIRMED, "제목\r\n\r\n내용").
PROBLEM_ADD_BUTTON = "[id$='tabpage1_btn_reqAddTextBoxElement']"


def problem_cell(row: int, col: int) -> str:
    return f"[id$='tabpage1_grd_DS_EBP0110_R03_body_gridrow_{row}_cell_{row}_{col}']"
