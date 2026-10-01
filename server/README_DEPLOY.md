# 웹판(server/) 배포 가이드 — Milestone 1

이 문서는 "형 회사 파일럿"을 사용자분의 평소 쓰는 Windows PC에 처음 띄울 때, 그리고
나중에 전용 서버 PC로 옮길 때 순서대로 따라 하는 체크리스트다.

## 0. 사전 준비물

- PostgreSQL 설치 (로컬 설치 또는 Docker Desktop)
- 한글(한컴오피스) 설치 + 정품 인증
- 외부 주소는 그룹웨어 도메인 아래(`/report`)를 쓰므로 도메인 추가 구매 불필요(6번)
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

고객사 메일 전송(현장 화면 "📧 고객사 전송")을 쓰려면 추가로:

```
MAIL_SMTP_USER=kfsc21c@naver.com   ; 보내는 주소 = 네이버 로그인 아이디
MAIL_SMTP_PASSWORD=<애플리케이션 비밀번호 12자리>
; 선택: MAIL_CC(기본 = 보내는 주소), MAIL_FROM_NAME(기본 한국미래안전), MAIL_SMTP_HOST/PORT(기본 smtp.naver.com:465)
```

방문 달력 자동 배치·일정 변경·동선 짜기의 **거리 기준**(현장 좌표·도로 거리, 2026-10-01)을 쓰려면:

```
KAKAO_REST_API_KEY=<카카오 개발자 사이트 앱의 REST API 키>   ; 회사(사용자) 카카오 계정 앱 — 앱 설정에서 "카카오맵" 사용 ON
; 주소 → 좌표(dapi.kakao.com 로컬)와 자동차 도로 거리(apis-navi.kakaomobility.com 길찾기)에 같은 키를 쓴다.
; 없으면 거리 없이 예전처럼 주소의 시·군으로만 묶고, 동선 짜기는 직선거리도 못 구해 쓸 수 없다.
; SK_TMAP_APPKEY(SK 오픈API 티맵 키)는 시험용으로 받아 보관만 — 티맵 길안내는 키 없이 된다(핵심기술.md 15절).
```

네이버 메일 환경설정 → POP3/IMAP 설정 → "SMTP 사용"을 켜고, **네이버 ID 2단계 인증을 켠 뒤 애플리케이션 비밀번호**를 만들어 넣는다
(로그인 비밀번호는 SMTP가 535로 거부함). SMTP를 90일 안 쓰면 네이버가 자동으로 꺼 버리니, 전송 창에 "로그인 실패"가 뜨면 이 설정부터 확인.
비밀번호를 바꾼 뒤엔 API를 다시 시작해야 반영된다. (지도 기한 알림 메일은 2026-10-01 없앰.)

절대경로를 코드에 하드코딩하지 않는 게 이 설계의 핵심이다 — 나중에 다른 PC로 옮길 때
코드는 그대로 두고 이 환경변수들만 새 PC 값으로 바꾸면 된다.

## 3. DB 스키마 적용 (Alembic)

```
alembic -c server/alembic.ini upgrade head
```

(2026-10-01 기준 0013까지: 0003 `report_edit` — PDF 수정 전 버전 판단, 0004 `report_mail` — 고객사 메일 보낸 기록,
0010 `visit_plan.source` — 방문 예정 자동/고정(자동 배치, `pip install holidays` 필요 — requirements.txt),
0005 `report_submit_mark`·`staff_contact`·`deadline_alert` — 직접 제출함·요원 메일·지도 기한 알림 보낸 기록,
0006 `staff_gw_link` — 담당요원 ↔ 그룹웨어 직원, 0007 `visit_plan` — 방문 달력 예정, 0008 `site_contact` — 현장 발주처·감리단, 0009 `site_contact.visit_address` — 지도 방문 주소,
0011 `site_geo` — 현장 좌표(카카오), 0012 `site_distance` — 현장 사이 도로 거리(카카오 길찾기), 0013 `site_contact.first_visit_no` — 첫 지도 회차.
전부 표를 새로 만드는 것뿐이라 돌고 있는 서버에 영향 없이 먼저 적용해도 된다(적용 → API 재시작 → 화면).
명령 창에 `DATABASE_URL` 환경변수가 있어야 한다 — `.env.server`의 값을 넣고 실행.)

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

## 6. 외부 접속 — 그룹웨어 주소 `https://groupware.kfsc21c.com/report/` (2026-09-28 적용, 비용 0원)

```
직원 브라우저 → groupware.kfsc21c.com(AWS, nginx) ──SSH 역방향 통로──→ 이 PC 127.0.0.1:8000(웹판, /report 아래)
```

AWS는 **전달만** 하고 hwpx 생성·PDF 변환(한글)·사진/DB 저장은 전부 이 PC에서 한다(리눅스에선 한글 PDF 변환 불가 — 13번 프로젝트
기록 참고). 이 PC가 꺼져 있으면 `/report/`는 "잠시 연결할 수 없습니다" 안내 화면(502), 그룹웨어의 다른 메뉴는 정상. 주소는 고정.

**이 PC 쪽**
- 감시 스크립트 `-Relay`가 `ssh -N -R 127.0.0.1:18000:127.0.0.1:8000 ec2-user@15.164.246.22`를 유지(끊기면 20초 내 재연결, 실측 15초).
- 키·호스트 정보는 영문 경로 `C:\kfsc-relay\`(한글 사용자 경로에서 ssh가 known_hosts를 못 만드는 문제 회피, 폴더 권한은 이 사용자만):
  `relay_key`(통로 전용), `known_hosts`, `admin_key`(13번 폴더 `new_kfs_key.ppk`를 변환한 **서버 관리자 키** — 서버 설정을 바꿀 때만 사용).
- 웹판은 `WEB_BASE_PATH`(기본 `/report`) 아래에서 동작 — 사무실 LAN에서는 `http://<이 PC IP>:8000/report/`.

**AWS 서버 쪽** (설정 원본은 `server/deploy/`, 적용 전 백업은 서버 `~/backup-report-integration-20260928/`)
1. `/etc/nginx/conf.d/groupware.conf`의 443 블록, `location /` 위에 `nginx_report_locations.conf` 내용 삽입
   (**로그인 확인 location `/_gw_report_auth`에도 `client_max_body_size 30m;` 필수** — 없으면 1MB 넘는 사진 업로드가 500, 2026-09-29 수정·적용)
   (업로드 30MB, 응답 대기 180초, 통로 없으면 `/usr/share/nginx/kfsc-report/report_offline.html` 안내 화면 — 상태 코드는 502 유지)
   → `sudo nginx -t && sudo systemctl reload nginx`(무중단).
2. `~/.ssh/authorized_keys`에 통로 전용 키 1줄: `restrict,port-forwarding,permitlisten="127.0.0.1:18000",command="/bin/false" <relay_key.pub>`
   — 이 키로는 18000 포트 통로만 열 수 있고 명령 실행·다른 포트는 불가(실측 확인).
3. `/etc/ssh/sshd_config.d/60-report-relay.conf`(`ClientAliveInterval 30`, `ClientAliveCountMax 3`) — PC 전원이 갑자기 꺼졌을 때 끊긴 연결이
   18000 포트를 계속 붙잡는 걸 90초 안에 정리 → `sudo sshd -t && sudo systemctl reload sshd`.

되돌리기: 백업 폴더의 `groupware.conf`를 복원하고 nginx reload, `authorized_keys`에서 `kfsc-report-relay` 줄 삭제, `60-report-relay.conf` 삭제 후 sshd reload.

**그룹웨어 자동 로그인(2026-09-28 적용)** — 보고서 자체 로그인 없음, 그룹웨어의 하위 메뉴:
- nginx가 `/report/` 요청마다 `auth_request`로 그룹웨어 `/internal/report-auth`(13번 `ReportController`)에 로그인 여부를 묻고,
  로그인돼 있으면 `X-Gw-User/Name/Role` + `X-Relay-Secret`을 붙여 이 PC로 넘긴다. 안 돼 있으면 화면은 그룹웨어 `/login`, API는 401.
  그룹웨어 `/internal/` 은 외부에서 404. 설정 원본 `server/deploy/nginx_report_locations.conf`(`__RELAY_SECRET__`는 적용 시
  `server/.env.server`의 `GROUPWARE_RELAY_SECRET` 값으로 치환 — 서버 설정 파일은 root만 읽기 가능).
- 보고서 서버: `GROUPWARE_RELAY_SECRET`이 있으면 그룹웨어 모드(`server/api/deps.py`) — 비밀값이 맞는 요청의 헤더로 사용자를 알아보고
  처음 온 직원은 자동 등록(`user.email = "gw:<그룹웨어 아이디>"`, 회사 `GROUPWARE_COMPANY_ID`=1 한국미래안전), 자체 로그인은 403.
  사무실 LAN 직접 접속·헤더 위조는 401(실측).
- 화면 틀: 그룹웨어의 `/css/app.css` + 사이드바 조각(`/report-shell/sidebar`)을 그대로 끼워 넣음(`server/web/shell.js`) — 로고·메뉴·
  관리자 메뉴·프로필·로그아웃이 그룹웨어와 동일. 보고서 하위 메뉴(현장 목록/제출 현황/방문 달력/담당요원/설정)는 본문 위 탭.
- 그룹웨어가 보고서에 더 주는 것(같은 도메인이라 **브라우저가** 그룹웨어 로그인으로 받아 씀 — nginx·SSH 통로 변경 없음):
  `/report-shell/employees`(직원정보 목록 JSON + 로그인 아이디 — 담당요원 탭, 13번 `e0d92e5`), `/api/holidays?year=`(공휴일 — 방문 달력).
- 그룹웨어 배포(13번): 로컬 커밋 → GitHub push → 서버 `~/groupware-src`에서 `git pull` → `JAVA_HOME=/usr/lib/jvm/java-22-amazon-corretto.x86_64
  mvn -q clean package -DskipTests`(비대화형 ssh엔 JAVA_HOME이 없어 지정 필요) → `~/groupware/groupware.jar` 교체 → `sudo systemctl restart groupware`(실측 15초).
  교체 전 jar 백업: `~/backup-report-integration-20260928/groupware.jar.before`, `~/backup-staff-link-20260930/groupware.jar.before`.
  재시작 동안(약 15초) 그룹웨어 전체가 멈추므로 업무 시간엔 사용자에게 먼저 묻는다.

**Cloudflare 임시 주소**: 그룹웨어 자동 로그인 적용과 함께 껐다(바로가기에서 `-Tunnel` 제거). 감시 스크립트 기능은 남아 있어 필요하면 `-Tunnel`로 다시 켤 수 있으나,
그룹웨어 모드에선 nginx를 안 거친 요청이 전부 401이라 쓸모가 없다.

외부 주소로만 쓰므로 `server/.env.server`의 `SESSION_COOKIE_SECURE`는 이제 의미가 적다(그룹웨어 모드는 보고서 쿠키를 안 씀).

## 7. 백업 (매일 1회, Windows 작업 스케줄러)

```
python -m server.scripts.backup
```

저장소 루트 `backups/` 아래 DB 덤프가 쌓인다(git 무시 — API 키 등 실데이터 포함). pg_dump가 PATH에 없으면 `C:/Program Files/PostgreSQL/16/bin`을 쓴다. **DB 덤프에는 안 담기는 파일**(사진/PDF/서명)도
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
