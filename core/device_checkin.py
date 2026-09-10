"""사용 현황 파악용 기기 체크인 — InfiniTech 공통 구조(6.3 프로젝트, 디바이스등록서버)에
앱 실행 시 1회 기기정보(MAC/사용자명/호스트명/IP)를 백그라운드로 보고한다.

"11. 구글메시지 자동화 프로그램"의 `app/auth_client.py`(+ 7.네이버쇼핑검색데이터수집/
8.네이버부동산크롤링도 동일 패턴)와 완전히 같은 프로토콜 — 서버(`app.py`)가 요청 바디의
`app` 필드를 파일명으로 써서 `devices/<app>.json`에 기기별(맥주소 기준)로 자동 저장한다.
`APP_NAME`을 "12. 한국미래안전 기술지도결과보고서"로 맞춰서 그 서버에 이 이름의 파일이
새로 생기게 한다.

URL/API 키를 그 프로젝트들처럼 `.env`에 두지 않고 코드에 직접 넣은 이유: 이건 고객이 보거나
설정할 필요가 전혀 없는 내부 관제용 값이라, exe와 별도로 `.env` 파일을 챙겨서 같이 배포해야
하는 번거로움을 만들 이유가 없다(고객이 실수로 지우거나 옮기면 조용히 기능만 빠지는 게
낫다).

실패(오프라인, 서버 다운 등)해도 앱 실행에는 전혀 영향이 없다 — 조용히 무시한다.
"""

from __future__ import annotations

import getpass
import json
import socket
import threading
import urllib.request
import uuid
from datetime import datetime

APP_NAME = "12. 한국미래안전 기술지도결과보고서"
_CHECKIN_URL = "https://ig-monitor.duckdns.org/checkin"
_API_KEY = "17b4ffe14f9fe5e357a5ce592c9835d685ee87148f131711"
_TIMEOUT_SECONDS = 5


def _local_ip() -> str:
    # 실제로 데이터를 보내지는 않고, OS 라우팅 테이블만 이용해 외부로 나갈 때 쓰일 로컬
    # IP를 알아낸다(UDP는 connect해도 핸드셰이크가 없어 패킷이 실제로 나가지 않음).
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def _mac_address() -> str:
    mac_int = uuid.getnode()
    return ":".join(f"{(mac_int >> shift) & 0xFF:02X}" for shift in range(40, -8, -8))


def _collect_device_info() -> dict:
    return {
        "app": APP_NAME,
        "mac": _mac_address(),
        "username": getpass.getuser(),
        "hostname": socket.gethostname(),
        "local_ip": _local_ip(),
        "client_time": datetime.now().isoformat(),
    }


def _checkin_worker() -> None:
    """백그라운드 스레드 안에서 전부 실행된다 — 기기정보 수집(`_collect_device_info()`)까지
    이 안에서 해야 한다. 스레드를 만들기 *전에* 호출자 스레드(메인 스레드)에서 미리 수집해
    `Thread(args=...)`로 넘기면, `getpass.getuser()`/`socket.gethostname()` 등이 (드문 실행
    환경에서) 예외를 던질 때 그 예외가 스레드 생성 전에 곧바로 앱을 죽인다 — "체크인 실패가
    앱 실행에 전혀 영향 없다"는 이 모듈의 약속이 깨진다. 모든 실패 지점을 스레드 안으로
    옮기고 폭넓게 잡아야 그 약속이 실제로 지켜진다.
    """
    try:
        info = _collect_device_info()
        req = urllib.request.Request(
            _CHECKIN_URL,
            data=json.dumps(info).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": _API_KEY,
                # ngrok/일부 터널이 브라우저가 아닌 요청도 경고 페이지로 가로채는 것을 방지
                "ngrok-skip-browser-warning": "true",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - 사용 현황 파악용 부가 기능, 어떤 이유로든 실패해도 앱은 계속 돼야 함
        pass


def send_checkin_async() -> None:
    """앱 시작 시 1회 호출한다. 백그라운드 스레드로 전송하고 응답을 기다리지 않으므로,
    서버가 꺼져있거나 네트워크가 없어도 앱 실행에는 전혀 영향을 주지 않는다.
    """
    threading.Thread(target=_checkin_worker, daemon=True).start()
