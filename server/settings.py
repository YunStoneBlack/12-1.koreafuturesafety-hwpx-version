"""웹판(server/) 전역 설정 — 전부 환경변수로 받는다. 코드에 절대경로/비밀값을 하드코딩하지
않아야, 나중에 이 서버를 전용 PC로 옮길 때 코드는 그대로 두고 환경변수만 새로 맞춰서
이전할 수 있다(server/README_DEPLOY.md의 "다른 PC로 이전" 절차 참고)."""

from __future__ import annotations

import os

SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
if not SESSION_SECRET:
    raise RuntimeError(
        "SESSION_SECRET 환경변수가 없습니다 — 세션 쿠키 서명에 쓰이는 비밀값이라 반드시 "
        "설정해야 합니다. 예: 아무 긴 랜덤 문자열."
    )

# 그룹웨어(groupware.kfsc21c.com)와 같은 도메인의 /report 아래에서 서비스하므로, 그룹웨어 쿠키와
# 헷갈리지 않게 이름을 구분하고(예전 "session_id") 쿠키 경로도 WEB_BASE_PATH로 좁힌다.
SESSION_COOKIE_NAME = "kfsc_report_session"

# 웹판 전체(화면+API)를 올리는 경로 — 그룹웨어 nginx가 https://groupware.kfsc21c.com/report/... 를 그대로
# 이 PC로 넘기므로 기본값 "/report". 로컬/사무실 LAN에서도 http://<IP>:8000/report/ 로 접속한다.
WEB_BASE_PATH = "/" + os.environ.get("WEB_BASE_PATH", "/report").strip().strip("/")
if WEB_BASE_PATH == "/":
    WEB_BASE_PATH = ""
SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "24") or 24)

# Cloudflare Tunnel(HTTPS)로 배포하면 True가 맞다(기본값). 다만 "Secure" 쿠키는 HTTPS가
# 아닌 주소(예: 사무실 LAN 내부 IP http://192.168.x.x:8000)에서는 브라우저가 아예 저장을
# 안 해서 로그인이 계속 풀리는 것처럼 보인다 — localhost/127.0.0.1은 브라우저가 예외로
# 봐줘서 괜찮지만, 그 외 http 주소로 당장 테스트해야 할 때만 SESSION_COOKIE_SECURE=false로
# 잠깐 꺼두고 쓴다(그 상태로 실제 서비스하면 안 됨 — 쿠키가 평문으로 오간다).
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").strip().lower() != "false"

# 콤마로 구분된 허용 origin 목록. 프론트엔드를 API와 다른 도메인/포트에서 서빙할 때만
# 필요하다 — 비워두면 CORS 미들웨어 자체를 안 붙인다(같은 오리진에서 서빙하면 필요 없음).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# 그룹웨어 자동 로그인 — 값이 있으면 "그룹웨어 모드": 그룹웨어 nginx가 로그인 확인(auth_request) 후 붙여주는
# X-Relay-Secret(이 값과 같아야 함) + X-Gw-User/X-Gw-Name/X-Gw-Role 헤더로 사용자를 알아보고, 보고서 자체 로그인은 막는다.
# 비밀값은 nginx 설정(서버)과 여기 두 곳에만 둔다 — 사무실 LAN·임시 주소 등 nginx를 안 거친 요청은 헤더를 흉내 내도 통과 못 함.
GROUPWARE_RELAY_SECRET = os.environ.get("GROUPWARE_RELAY_SECRET", "").strip()
# 그룹웨어 직원이 처음 들어오면 자동으로 만들어지는 보고서 사용자가 속할 회사(company.id) — 한국미래안전
GROUPWARE_COMPANY_ID = int(os.environ.get("GROUPWARE_COMPANY_ID", "1") or 1)


# 고객사에 보고서 PDF 메일 보내기(현장 화면 "📧 고객사 전송", server/api/mailer.py) — 회사 네이버 메일(@naver.com)의 SMTP로 보낸다
# (일반 네이버 메일엔 발송용 공개 API가 없음). 네이버 메일 환경설정 → POP3/IMAP 설정에서 "SMTP 사용"을 켜야 하고,
# 2단계 인증을 쓰는 계정이면 로그인 비밀번호 대신 "애플리케이션 비밀번호"를 넣는다. 비워 두면 전송 버튼이 "설정 안 됨"을 알린다.
MAIL_SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "smtp.naver.com").strip()
MAIL_SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "465") or 465)
MAIL_SMTP_USER = os.environ.get("MAIL_SMTP_USER", "").strip()  # 보내는 주소 = 로그인 아이디(예: xxx@naver.com)
MAIL_SMTP_PASSWORD = os.environ.get("MAIL_SMTP_PASSWORD", "").strip()
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "한국미래안전").strip()
# 참조(CC) — 기본은 보내는 회사 메일 자신(보낸메일함 외에 받은메일함에도 남아 회사에서 확인하기 쉽게)
MAIL_CC = os.environ.get("MAIL_CC", MAIL_SMTP_USER).strip()

# 알림 메일 등에 넣는 바깥 주소(제출 현황 링크 등) — 그룹웨어의 "보고서 자동화" 메뉴 주소
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://groupware.kfsc21c.com/report").strip().rstrip("/")
