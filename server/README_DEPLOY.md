# 웹판(server/) 배포 가이드 — Milestone 1

이 문서는 "형 회사 파일럿"을 사용자분의 평소 쓰는 Windows PC에 처음 띄울 때, 그리고
나중에 전용 서버 PC로 옮길 때 순서대로 따라 하는 체크리스트다.

## 0. 사전 준비물

- PostgreSQL 설치 (로컬 설치 또는 Docker Desktop)
- 한글(한컴오피스) 설치 + 정품 인증
- 도메인 1개 (고정 주소용, 연 1~2만 원) — 없으면 Cloudflare 임시 주소로 시험 가능(6번)
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

## 5. 자동 실행·감시 (로그인 시 자동 시작, 꺼지면 다시 켜기)

`server/scripts/web_watchdog.ps1`이 API 서버·PDF 렌더 워커·(선택) Cloudflare 터널을 띄우고, 꺼지면 20초 안에 다시
띄운다. 로그는 `data/logs/`(직전 실행분은 `.prev`), 감시 기록은 `data/logs/watchdog.log`.

**Windows 서비스(NSSM)로 하지 않는 이유**: PDF 워커는 한글 프로그램을 자동 조작하는데, 서비스(로그인 화면이 없는 세션)에서는
한글 자동화가 안 되는 경우가 흔하다 — 로그인한 사용자 세션에서 돌아야 한다. 이 방식은 관리자 권한도 필요 없다.

1. 환경변수는 `server/.env.server`에(예시: `server/.env.server.example`, git 제외) — `server/__init__.py`가 자동으로 읽는다.
   루트 `.env`에 `DATABASE_URL`을 넣으면 안 된다(데스크톱 앱까지 PostgreSQL에 붙어버림).
2. 시작프로그램 폴더(`shell:startup`)에 바로가기 등록 — 대상:
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "<저장소>\server\scripts\web_watchdog.ps1" -Tunnel`
   (2026-09-28 이 PC에 "한국미래안전 보고서 웹판.lnk"로 등록됨)
3. **재부팅 후 아무도 로그인 안 해도 켜지게 하려면 Windows 자동 로그인**을 켜야 한다(사용자가 직접 설정 — `netplwiz`
   또는 Microsoft 공식 Autologon 도구). 그리고 전원 설정에서 **절전 모드 "안 함"**(PC가 잠들면 접속이 끊긴다).

수동 재시작: 작업 관리자에서 `powershell`(web_watchdog)·`python`(uvicorn/supervisor_entry)·`cloudflared`를 끝낸 뒤 바로가기 실행.
⚠️ `core/` 렌더러 코드를 고치면 워커도 재시작해야 반영된다.

## 6. Cloudflare Tunnel로 외부 접속 열기 (비용: 터널 무료, 고정 주소엔 도메인 연 1~2만 원)

**지금(시험 단계) — 임시 주소, 도메인 불필요**: `cloudflared.exe`(설치 불필요, 공식 배포본을 `%LOCALAPPDATA%\cloudflared\`에
둠)를 감시 스크립트가 `-Tunnel`로 띄운다. `https://<무작위>.trycloudflare.com` 주소가 생기고 **재시작할 때마다 바뀐다** —
현재 주소는 `data/logs/tunnel_url.txt`. 가동률 보장이 없는 시험용이다.

**도메인을 정한 뒤 — 고정 주소**(Cloudflare 무료 계정 필요):

```
cloudflared tunnel login
cloudflared tunnel create report-tunnel
cloudflared tunnel route dns report-tunnel <원하는 하위주소>.<도메인>
```

터널 설정(`config.yml`)에서 그 주소 → `http://127.0.0.1:8000`으로 연결하고, 감시 스크립트의 터널 실행 인수를
`tunnel run report-tunnel`로 바꾼다. HTTPS 인증서는 Cloudflare가 자동 처리. 회사 기존 도메인(그룹웨어)의 하위 주소를 쓰려면
그 도메인의 네임서버를 Cloudflare로 옮겨야 해서(무료 요금제 기준) 기존 그룹웨어·홈페이지 주소 설정에 영향 — 도메인 관리자와 상의.

⚠️ 외부에 여는 순간 누구나 로그인 화면에 접근할 수 있다 — 시험용 계정(`employee1~5@example.com` / 동일 비밀번호)은
실사용 전에 반드시 실제 계정·각자 다른 비밀번호로 바꿀 것(4번 재시딩). 외부 주소로만 쓰게 되면 `SESSION_COOKIE_SECURE=true`.

## 7. 백업 (매일 1회, Windows 작업 스케줄러)

```
python -m server.scripts.backup
```

`data/backups/` 아래 DB 덤프가 쌓인다. **DB 덤프에는 안 담기는 파일**(사진/PDF/서명)도
같이 챙겨야 한다 — 스크립트 실행 시 그 폴더 목록을 출력해준다:
`data/photos`, `data/reports`, `data/signatures`, `data/templates`

## 8. 나중에 전용 서버 PC로 이전할 때

1. 새 PC에 PostgreSQL + 한글 + cloudflared 설치, 이 저장소 그대로 복사(+ `server/.env.server`)
2. 최신 DB 덤프를 새 PC로 옮겨서 `pg_restore`
3. 위 4개 데이터 폴더를 새 PC로 그대로 복사
4. 환경변수(2번)를 새 PC 값으로 설정
5. 5~6번(시작프로그램 바로가기·자동 로그인, Cloudflare Tunnel)을 새 PC에서 다시 등록 — 도메인은 그대로 재사용
   가능(터널이 가리키는 대상만 새 PC로 바뀌는 것)
6. 새 PC에서 정상 동작 확인 후, 예전 PC의 서비스 중지

코드를 고칠 필요가 없어야 한다 — 만약 이전 중에 코드를 고쳐야 하는 상황이 생기면, 그건
어딘가에 절대경로/설정값이 하드코딩되어 있었다는 뜻이니 그 자리를 찾아서 환경변수로
바꿔야 한다.
