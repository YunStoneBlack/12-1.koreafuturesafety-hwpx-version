"""API 키/AI 설정 로딩.

배포된 프로그램은 사용자마다 각자의 Claude API 키를 앱의 "AI 관리" 화면에서 입력해
로컬 DB(app_setting 테이블)에 저장한다. 개발 중에는 .env의 ANTHROPIC_API_KEY를
기본값(fallback)으로 사용할 수 있다.

Sub-phase 33(웹판): `app_setting`이 (company_id, key) 복합 유니크로 바뀌면서, 이 모듈의
읽기/쓰기 함수들도 선택적 `company_id` 인자를 받는다. 데스크톱 exe는 항상 호출부에서
company_id를 안 넘기므로 기본값 None(=company_id가 NULL인 그 행)으로 예전과 동일하게
동작 — 하위호환이 깨지지 않는다. 웹판(server/)만 로그인한 사용자의 company_id를 넘겨서
회사별로 다른 API 키를 쓸 수 있게 한다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"

_KEY_API_KEY = "api_key"
_KEY_AI_ENABLED = "ai_enabled"
_KEY_LAW_API_OC = "law_api_oc"


def _get_setting(key: str, company_id: int | None = None) -> str | None:
    from core.db import SessionLocal
    from core.models_db import AppSetting

    with SessionLocal() as session:
        row = session.query(AppSetting).filter_by(key=key, company_id=company_id).first()
        return row.value if row else None


def _set_setting(key: str, value: str, company_id: int | None = None) -> None:
    from core.db import SessionLocal
    from core.models_db import AppSetting

    with SessionLocal() as session:
        row = session.query(AppSetting).filter_by(key=key, company_id=company_id).first()
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value, company_id=company_id))
        session.commit()


def get_api_key(company_id: int | None = None) -> str:
    stored = (_get_setting(_KEY_API_KEY, company_id) or "").strip()
    if stored:
        return stored

    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not env_key:
        raise RuntimeError(
            "Claude API 키가 설정되어 있지 않습니다. 앱의 'AI 관리' 화면에서 API 키를 입력하세요."
        )
    return env_key


def set_api_key(value: str, company_id: int | None = None) -> None:
    _set_setting(_KEY_API_KEY, value.strip(), company_id)


def get_raw_api_key(company_id: int | None = None) -> str:
    """설정 화면에 미리 채워 넣기용. 없으면 예외 없이 빈 문자열을 반환한다."""
    return (_get_setting(_KEY_API_KEY, company_id) or "").strip()


def has_api_key(company_id: int | None = None) -> bool:
    try:
        return bool(get_api_key(company_id))
    except RuntimeError:
        return False


# 웹판 현장 삭제 비밀번호(회사별, bcrypt 해시만 저장 — server/api/security.py). 데스크톱 exe는 안 씀.
_KEY_SITE_DELETE_PASSWORD = "site_delete_password_hash"


def get_site_delete_password_hash(company_id: int | None = None) -> str:
    return (_get_setting(_KEY_SITE_DELETE_PASSWORD, company_id) or "").strip()


def set_site_delete_password_hash(value: str, company_id: int | None = None) -> None:
    _set_setting(_KEY_SITE_DELETE_PASSWORD, value, company_id)


# ---------- 알림 설정(웹판) — 2026-10-01 15일 지도 기한 알림은 없앰, 값(관리자 메일 등)은 다른 알림에서 다시 쓰려고 보존 ----------
_KEY_DEADLINE_IMMINENT_DAYS = "deadline_imminent_days"
_KEY_DEADLINE_ALERT_ENABLED = "deadline_alert_enabled"
_KEY_DEADLINE_ADMIN_EMAIL = "deadline_alert_admin_email"
DEFAULT_IMMINENT_DAYS = 3  # 기한 D-3부터 "임박"(사용자 2026-09-29 "일단 D-3, 나중에 조정")


def get_deadline_imminent_days(company_id: int | None = None) -> int:
    try:
        return max(0, int(_get_setting(_KEY_DEADLINE_IMMINENT_DAYS, company_id) or DEFAULT_IMMINENT_DAYS))
    except ValueError:
        return DEFAULT_IMMINENT_DAYS


def set_deadline_imminent_days(days: int, company_id: int | None = None) -> None:
    _set_setting(_KEY_DEADLINE_IMMINENT_DAYS, str(int(days)), company_id)


def get_deadline_alert_enabled(company_id: int | None = None) -> bool:
    return (_get_setting(_KEY_DEADLINE_ALERT_ENABLED, company_id) or "1") == "1"  # 기본 켜짐


def set_deadline_alert_enabled(enabled: bool, company_id: int | None = None) -> None:
    _set_setting(_KEY_DEADLINE_ALERT_ENABLED, "1" if enabled else "0", company_id)


def get_deadline_admin_email(company_id: int | None = None) -> str:
    return (_get_setting(_KEY_DEADLINE_ADMIN_EMAIL, company_id) or "").strip()


def set_deadline_admin_email(value: str, company_id: int | None = None) -> None:
    _set_setting(_KEY_DEADLINE_ADMIN_EMAIL, value.strip(), company_id)


# ---------- 지도 출장 자동 배치(웹판 server/api/visit_scheduler.py) — 마지막 지도를 준공 며칠 전까지 마칠지(사용자 2026-10-01 "기본 2주, 언제든 변경") ----------
_KEY_PLAN_FINISH_BEFORE_DAYS = "plan_finish_before_days"
DEFAULT_PLAN_FINISH_BEFORE_DAYS = 14


def get_plan_finish_before_days(company_id: int | None = None) -> int:
    try:
        return max(0, int(_get_setting(_KEY_PLAN_FINISH_BEFORE_DAYS, company_id) or DEFAULT_PLAN_FINISH_BEFORE_DAYS))
    except ValueError:
        return DEFAULT_PLAN_FINISH_BEFORE_DAYS


def set_plan_finish_before_days(days: int, company_id: int | None = None) -> None:
    _set_setting(_KEY_PLAN_FINISH_BEFORE_DAYS, str(int(days)), company_id)


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


def get_company_signature(role: str, company_id: int | None = None) -> tuple[str, str]:
    """결재란(이사/대표이사) 서명 — 회사 전체 고정값. role: "director" | "ceo".

    반환값: (signature_path, source). 등록 안 됐으면 ("", "").
    """
    path = (_get_setting(f"signature_{role}_path", company_id) or "").strip()
    source = (_get_setting(f"signature_{role}_source", company_id) or "").strip()
    return path, source


def set_company_signature(role: str, path: str, source: str, company_id: int | None = None) -> None:
    _set_setting(f"signature_{role}_path", path, company_id)
    _set_setting(f"signature_{role}_source", source, company_id)
