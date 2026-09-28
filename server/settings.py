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

SESSION_COOKIE_NAME = "session_id"
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
