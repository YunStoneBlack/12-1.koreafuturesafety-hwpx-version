# 한국미래안전 기술지도 결과보고서 자동화 (데스크톱 앱)

건설재해예방전문지도기관 기술지도 결과보고서를 회차별로 작성하는 데스크톱 프로그램(PyQt6).
회사가 기존에 쓰던 웹 시스템의 화면/흐름을 그대로 재현하고, AI 초안 생성 + 사람 최종 검토 원칙을 유지한다.

자세한 설계는 `C:\Users\윤석현1\.claude\plans\magical-puzzling-corbato.md`, 진행상황은 `작업내용.md`,
핵심 기술 요소는 `핵심기술.md` 참고.

## 설치 및 실행

```bash
pip install -r requirements.txt
python -m desktop.main
```

## API 키

배포된 프로그램은 각 사용자가 앱 안의 **"AI 관리"** 화면에서 자기 Claude API 키를 입력해 로컬에 저장한다
(`data/app.db`). 개발 중에는 `.env`의 `ANTHROPIC_API_KEY`를 fallback으로 사용할 수도 있다
(`.env.example` 참고, 실제 `.env`는 git에 커밋하지 않음).

## 구조

- `core/` — UI에 의존하지 않는 핵심 로직 (DB 스키마, AI 분석, 설정)
  - `db.py`, `models_db.py` — SQLite 스키마(SQLAlchemy)
  - `contract_analyzer.py` — 계약서 PDF → 신규현장추가 폼 필드 AI 추출
  - `report_extractor.py` / `report_import.py` — 과거 보고서 PDF → 회차 데이터 AI 추출 / 현장 매칭·저장
    ("이전 보고서 업로드" 기능용)
  - `report_builder.py` — 재수출 창구(`build_report`/`build_report_docx`). 실제 구현은
    `report_builder_common.py`(공통 헬퍼) / `report_builder_pdf.py`(PDF, 실제 표준 서식 9섹션) /
    `report_builder_docx.py`(DOCX, 아직 예전 7섹션 — 미리보기 흐름에 연결 안 돼있어 우선순위 낮음)
  - `hangul_match.py` — 자모 단위 부분일치 검색 (조합 중인 글자도 검색 가능)
  - `config.py` — API 키/설정 관리
- `desktop/` — PyQt6 UI
  - `main.py` — 앱 진입점
  - `views/` — 화면 (대시보드, 신규현장추가, 현장상세, 보고서 작성 마법사, 이전 보고서 업로드, AI 관리)
    - 보고서 작성 마법사는 파일 하나가 너무 커지지 않도록 나뉘어 있음: `report_wizard_view.py`
      (메인 뷰, 회차 불러오기/AI 액션), `report_wizard_sections.py`(1~9번 섹션),
      `report_wizard_sections2.py`(Sub-phase 7에서 추가된 신규 섹션 3개),
      `report_wizard_save.py`(DB 저장 + PDF 생성)
  - `dialogs/` — 법령 검색 / 공정 선택 / 제공자료 선택 / 보고서 미리보기 모달
  - `workers/` — AI 호출을 백그라운드 스레드로 실행하는 워커
  - `widgets/` — 재사용 UI 컴포넌트 (`report_wizard_slots.py`에 보고서 마법사 하위 "한 칸" 위젯들 포함)
- `data/` — 로컬 DB 파일, 참조 데이터(계측기준 등), `migrate_v7_report_format.py`(Sub-phase 7 스키마 마이그레이션)

## 진행 상황

- **Sub-phase 1 (완료)**: DB 스키마, 대시보드, 신규현장추가(AI 자동추출), 현장상세, AI 관리(API 키 설정)
- **Sub-phase 2 (완료)**: 보고서 작성 마법사 1~4단계(전경/안전교육/지적사항/특이사항) + AI 연동
- **Sub-phase 3 (완료)**: 5~9단계(이전지적사항 자동승계, 계측자료+AI 판독, 제공자료 라이브러리+추천, 12대기인물, 진행공정+법령검색) — 회차 간 12대기인물/진행공정 자동 승계까지 검증됨
- **Sub-phase 4 (완료)**: "AI 생성물 반드시 확인" 체크박스 게이트 + PDF 생성(reportlab, 실제 산출물과 동일한 7섹션 구조 — 실 데이터로 텍스트 검증 완료) + DOCX 생성(python-docx) + 생성 후 PDF 자동으로 열기 + 보고서 이력에서 수정/한글/워드/PDF 열기·삭제
- **Sub-phase 5 (완료)**: 담당요원 관리 화면 (대시보드에서 "👥 담당요원")
- **Sub-phase 6 (완료)**: 이전 보고서 업로드 (대시보드에서 "⬆ 이전 보고서 업로드") — 과거 기술지도
  결과보고서 PDF 여러 개를 올리면 `core/report_extractor.py`가 AI로 현장/회차/지적사항 등을
  통째로 추출하고, `core/report_import.py`가 사업장관리번호(없으면 현장명 폴백)로 기존 현장에
  매칭하거나 신규 생성 + 같은 회차 중복 자동 스킵. 검토는 핵심 필드(현장명/회차/지도일/공정률)만
  가볍게 하고, 세부 내용은 등록 후 보고서 작성 마법사에서 수정.
  - 남은 것: 보고서 미리보기 화면 안에서의 워드/한글(DOCX/HWPX) 생성(현재 PDF만 지원)
- **Sub-phase 7 (진행 중)**: 실제 사용자가 쓰는 최신 표준 서식(9섹션)에 맞춰 보고서 양식 전면 개편.
  스키마(대형사고위험작업 25종/기인물 12→17개/건설기계장비·위험기계기구·유해위험물질 3종 안전조치표/
  현재진행중공정 섹션) + 마법사 입력화면 + PDF 생성까지 새 구조로 완료, 실제 9페이지를 렌더링해
  실제 서식과 육안 대조 확인함. 사용자 피드백 "완벽하진 않은데 조금 더 다듬어야겠다"로 다음 세션에서
  구체 내용 받아 이어갈 예정.
  - 남은 것: DOCX를 9섹션 구조로 맞추기, 보고서 관리번호·서명 등록/입력·결재라인(다음 라운드로
    미루기로 확정)

### 한글(HWPX) 출력 — 현재 이 PC에서는 안 됨, 확인 필요
DOCX를 한글에서 열어 HWPX로 저장하는 방식(`core/hwpx_exporter.py`, pyhwpx)으로 시도했는데,
**이 PC의 한글에서 DOCX(OOXML) 파일 열기 자체가 실패**합니다 (빈 문서로 테스트해도 동일).
반면 한글 고유 포맷(.hwp) 저장/열기는 COM 자동화로 정상 동작하는 것까지 확인했습니다 —
즉 자동화 자체는 되는데 "MS오피스 문서 가져오기" 필터만 막혀있는 것으로 보입니다.
→ **한글에서 직접 아무 .docx 파일이나 열어보시고 어떤 메시지가 뜨는지 알려주시면**, 그에 맞춰 고치거나
(예: 호환 필터 설치 안내) 아니면 한글 API로 직접 문서를 만드는 방식으로 다시 짜야 합니다.
현재는 PDF/DOCX만 생성되고 HWPX는 실패 메시지만 뜨도록 안전하게 처리해뒀습니다(앱이 죽지 않음).

### 참조 데이터 현황
- **제공자료 라이브러리(`MaterialLibrary`)**: 채워짐 — 사용자가 직접 고른 81개 포스터/카드뉴스 (`data/materials/`, 파일명=제목)
- **공정 카탈로그(`ProcessCatalog`)**: 채워짐 — 실제 서비스(jidobiseo.co.kr)에서 Playwright(CDP)로 직접 추출한 284건, 32개 카테고리, 유해위험요인·예방대책 전체 텍스트 포함. 재구성하려면 `data/seed_process_catalog.py` 참고(원본 JSON 3종 필요)
- **법령 캐시**: 채워짐 — 실제 국가법령정보센터 OC 키로 "산업안전보건기준에 관한 규칙" 690개 조문(666조까지)
  캐싱 완료. `AI 관리`에서 OC 키 확인/재발급, 법령 검색 모달에서 '캐시 새로고침'으로 다시 채울 수 있음
