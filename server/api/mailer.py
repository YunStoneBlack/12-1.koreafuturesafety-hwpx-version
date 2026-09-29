"""보고서 PDF 메일 보내기 — 회사 네이버 메일(@naver.com)의 SMTP로(설정은 server/settings.py의 MAIL_*).

보낸 메일은 네이버 메일 "보낸메일함"에도 남는다(메일 앱이 보내는 것과 같은 방식). 제목·본문 문구는
사용자가 나중에 정해 주기로 함(2026-09-29) — 그때 아래 `mail_subject`/`mail_body`만 고치면 된다.
"""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from server import settings

_EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")


class MailError(Exception):
    """화면에 그대로 보여 줄 한국어 안내."""


def is_configured() -> bool:
    return bool(settings.MAIL_SMTP_USER and settings.MAIL_SMTP_PASSWORD)


def valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match(addr or ""))


def cc_for(to_addrs: list[str]) -> str:
    """참조 — 받는 사람 중에 이미 있으면 두 번 보내지 않는다."""
    cc = settings.MAIL_CC
    return "" if not cc or cc.lower() in (a.lower() for a in to_addrs) else cc


def mail_subject(site_name: str, visit_no: int) -> str:
    return f"[{settings.MAIL_FROM_NAME}] {site_name} {visit_no}회차 기술지도 결과보고서"


def mail_body(site_name: str, visit_no: int) -> str:
    return (
        "안녕하세요.\n\n"
        f"{site_name} {visit_no}회차 기술지도 결과보고서를 첨부하여 보내드립니다.\n\n"
        f"{settings.MAIL_FROM_NAME} 드림"
    )


def send_pdf(to_addrs: list[str], cc_addr: str, subject: str, body: str, pdf_path: Path, filename: str) -> list[str]:
    """PDF 한 개를 첨부해 받는 사람 모두에게 한 통으로 보낸다(서로 보임). 실패하면 MailError(화면용 안내).
    돌려주는 값: 메일 서버가 거부한 주소들(일부만 거부되면 나머지에겐 이미 간 것 — 화면에 따로 알림)."""
    return send_mail(to_addrs, cc_addr, subject, body, attachment=(Path(pdf_path).read_bytes(), filename))


def send_mail(to_addrs: list[str], cc_addr: str, subject: str, body: str,
              attachment: tuple[bytes, str] | None = None) -> list[str]:
    """메일 한 통(PDF 첨부 선택) — 고객사 전송·지도 기한 알림(server/worker/deadline_notifier.py) 공용."""
    msg = EmailMessage()
    msg["From"] = formataddr((settings.MAIL_FROM_NAME, settings.MAIL_SMTP_USER))  # 네이버는 로그인 계정과 같은 보내는 주소만 허용
    msg["To"] = ", ".join(to_addrs)
    if cc_addr:
        msg["Cc"] = cc_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment is not None:
        msg.add_attachment(attachment[0], maintype="application", subtype="pdf", filename=attachment[1])
    try:
        # local_hostname — 기본값은 이 PC 이름인데 한글이 섞여 있으면 EHLO 단계에서 UnicodeEncodeError(ASCII만 가능)
        with smtplib.SMTP_SSL(
            settings.MAIL_SMTP_HOST, settings.MAIL_SMTP_PORT, local_hostname="localhost", timeout=60
        ) as smtp:
            smtp.login(settings.MAIL_SMTP_USER, settings.MAIL_SMTP_PASSWORD)
            refused = smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise MailError(
            "회사 네이버 메일 로그인에 실패했습니다. 네이버 메일의 'SMTP 사용' 설정과 서버에 넣은 (애플리케이션) 비밀번호를 확인하세요."
        ) from e
    except smtplib.SMTPRecipientsRefused as e:
        raise MailError(f"받는 주소를 메일 서버가 거부했습니다: {', '.join(e.recipients)}") from e
    except smtplib.SMTPDataError as e:
        raise MailError(f"메일 서버가 메일을 받지 않았습니다(첨부 용량 등). ({e.smtp_code})") from e
    except (smtplib.SMTPException, OSError) as e:
        raise MailError("메일 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.") from e
    except Exception as e:  # 예상 못 한 오류도 화면엔 안내 문구로(원인은 API 로그에)
        raise MailError(f"메일을 보내지 못했습니다({type(e).__name__}). 관리자에게 알려 주세요.") from e
    return list(refused)
