"""API 키/AI 설정 로딩.

배포된 프로그램은 사용자마다 각자의 Claude API 키를 앱의 "AI 관리" 화면에서 입력해
로컬 DB(app_setting 테이블)에 저장한다. 개발 중에는 .env의 ANTHROPIC_API_KEY를
기본값(fallback)으로 사용할 수 있다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"

_KEY_API_KEY = "api_key"
_KEY_AI_ENABLED = "ai_enabled"
_KEY_LAW_API_OC = "law_api_oc"


def _get_setting(key: str) -> str | None:
    from core.db import SessionLocal
    from core.models_db import AppSetting

    with SessionLocal() as session:
        row = session.query(AppSetting).filter_by(key=key).first()
        return row.value if row else None


def _set_setting(key: str, value: str) -> None:
    from core.db import SessionLocal
    from core.models_db import AppSetting

    with SessionLocal() as session:
        row = session.query(AppSetting).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value))
        session.commit()


def get_api_key() -> str:
    stored = (_get_setting(_KEY_API_KEY) or "").strip()
    if stored:
        return stored

    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not env_key:
        raise RuntimeError(
            "Claude API 키가 설정되어 있지 않습니다. 앱의 'AI 관리' 화면에서 API 키를 입력하세요."
        )
    return env_key


def set_api_key(value: str) -> None:
    _set_setting(_KEY_API_KEY, value.strip())


def get_raw_api_key() -> str:
    """설정 화면에 미리 채워 넣기용. 없으면 예외 없이 빈 문자열을 반환한다."""
    return (_get_setting(_KEY_API_KEY) or "").strip()


def has_api_key() -> bool:
    try:
        return bool(get_api_key())
    except RuntimeError:
        return False


def get_ai_enabled() -> bool:
    stored = _get_setting(_KEY_AI_ENABLED)
    if stored is None:
        return True
    return stored == "1"


def set_ai_enabled(enabled: bool) -> None:
    _set_setting(_KEY_AI_ENABLED, "1" if enabled else "0")


def get_model_name() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_law_api_oc() -> str:
    """국가법령정보센터 Open API의 OC(신청 시 발급된 이메일 ID). open.law.go.kr에서 각자 발급."""
    return (_get_setting(_KEY_LAW_API_OC) or "").strip()


def set_law_api_oc(value: str) -> None:
    _set_setting(_KEY_LAW_API_OC, value.strip())
