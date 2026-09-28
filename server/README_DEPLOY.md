# 웹판(server/) 배포 가이드 — Milestone 1

이 문서는 "형 회사 파일럿"을 사용자분의 평소 쓰는 Windows PC에 처음 띄울 때, 그리고
나중에 전용 서버 PC로 옮길 때 순서대로 따라 하는 체크리스트다.

## 0. 사전 준비물

- PostgreSQL 설치 (로컬 설치 또는 Docker Desktop)
- 한글(한컴오피스) 설치 + 정품 인증
- 도메인 1개 (Cloudflare Tunnel용 서브도메인을 붙일 것) — 아직 없으면 이 단계는 나중에 해도 됨
- Python 패키지: `pip install -r requirements.txt` (server/ 관련 패키지 포함되어 있음)

## 1. 한글 프로그램 1회 수동 설정 (필수, 자동화 불가)

한글 실행 → **보안 → 문서 보안 설정 → 낮음**으로 변경.

이걸 안 하면 PDF 자동 생성이 응답 없는 보안 팝업에 걸려 영원히 멈춘다(`visible=False`로
떠서 그 팝업을 아무도 클릭할 수 없기 때문 — `core/report_builder_hwpx.py`의 설명 참고).

## 2. 환경변수 설정

```
DATABASE_URL=postgresql+psycopg://<사용자>:<비밀번호>@localhost/report_db
SESSION_SECRET=<아무 긴 랜덤 문자열>
DATA_DIR=<사진/PDF/서명 등을 저장할 폴더, 비워두면 기본값(코드 위치 기준 data/) 사용>
CORS_ORIGINS=<프론트엔드를 API와 다른 도메인에서 서빙할 때만, 콤마로 구분>
SESSION_COOKIE_SECURE=true   ; Cloudflare Tunnel(HTTPS)로 쓸 땐 true 유지. localhost가
                             ; 아닌 http 주소(사무실 LAN IP 등)로 잠깐 테스트할 때만
                             ; false로 내려서 씀 — 그 상태로 실제 서비스하면 안 됨.
```

절대경로를 코드에 하드코딩하지 않는 게 이 설계의 핵심이다 — 나중에 다른 PC로 옮길 때
코드는 그대로 두고 이 환경변수들만 새 PC 값으로 바꾸면 된다.

## 3. DB 스키마 적용 (Alembic)

```
alembic -c server/alembic.ini upgrade head
```

## 4. 파일럿 회사/직원 계정 시딩

`server/seed_pilot.py`를 열어서 `PILOT_COMPANY_NAME`/`PILOT_COMPANY_SLUG`/
`PILOT_EMPLOYEE_EMAILS`를 형 회사 실제 값으로 바꾼 뒤:

```
python -m server.seed_pilot
```

직원별 초기 비밀번호를 입력받는다(터미널에 안 보임). 이후 그 이메일/비밀번호로 로그인.

## 5. 프로세스 2개를 Windows 서비스로 등록 (NSSM)

평소 쓰는 PC가 재부팅되거나 로그오프돼도 살아남게 하려면 일반 터미널 창에 띄워두지 말고
[NSSM](https://nssm.cc/)으로 등록한다.

```
nssm install ReportApi   python.exe   "-m uvicorn server.api.main:app --host 127.0.0.1 --port 8000"
nssm install ReportWorker python.exe  "-m server.worker.supervisor_entry"
nssm start ReportApi
nssm start ReportWorker
```

API는 `127.0.0.1`(로컬)에만 바인딩 — LAN/인터넷에 직접 노출하지 않는다. 외부 접속은
Cloudflare Tunnel이 대신 담당한다(6번).

## 6. Cloudflare Tunnel로 외부 접속 열기

```
cloudflared tunnel login
cloudflared tunnel create report-tunnel
cloudflared tunnel route dns report-tunnel hyung-company.<도메인>
cloudflared service install
```

터널 설정(`config.yml`)에서 `hyung-company.<도메인>` → `http://127.0.0.1:8000`으로 연결.
HTTPS 인증서는 Cloudflare가 자동 처리 — 이 PC에서 인증서 관리 안 해도 됨.

## 7. 백업 (매일 1회, Windows 작업 스케줄러)

```
python -m server.scripts.backup
```

`data/backups/` 아래 DB 덤프가 쌓인다. **DB 덤프에는 안 담기는 파일**(사진/PDF/서명)도
같이 챙겨야 한다 — 스크립트 실행 시 그 폴더 목록을 출력해준다:
`data/photos`, `data/reports`, `data/signatures`, `data/templates`

## 8. 나중에 전용 서버 PC로 이전할 때

1. 새 PC에 PostgreSQL + 한글 + cloudflared + NSSM 설치, 이 저장소 그대로 복사
2. 최신 DB 덤프를 새 PC로 옮겨서 `pg_restore`
3. 위 4개 데이터 폴더를 새 PC로 그대로 복사
4. 환경변수(2번)를 새 PC 값으로 설정
5. 5~6번(NSSM 서비스, Cloudflare Tunnel)을 새 PC에서 다시 등록 — 도메인은 그대로 재사용
   가능(터널이 가리키는 대상만 새 PC로 바뀌는 것)
6. 새 PC에서 정상 동작 확인 후, 예전 PC의 서비스 중지

코드를 고칠 필요가 없어야 한다 — 만약 이전 중에 코드를 고쳐야 하는 상황이 생기면, 그건
어딘가에 절대경로/설정값이 하드코딩되어 있었다는 뜻이니 그 자리를 찾아서 환경변수로
바꿔야 한다.
