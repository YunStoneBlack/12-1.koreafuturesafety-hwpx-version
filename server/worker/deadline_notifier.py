"""지도 기한 알림 메일 — 평일 아침 9시(이 PC가 꺼져 있었으면 켜진 뒤 첫 확인 때), 렌더 워커 루프에서 1분마다 `tick()`.

규칙(사용자 결정 2026-09-29):
- 현장마다 단계별로 한 번씩: d3(기한 임박 — 설정 일수 전, 기본 D-3) · dday(기한 당일) · over(초과 첫날).
  같은 (현장, 기한, 단계, 경로)는 두 번 안 보냄(deadline_alert). 한 번에 가장 급한 단계만(PC가 며칠 꺼져 있었어도 지난 단계를 몰아 보내지 않음).
- 기한 알림이 주말에 걸리면 금요일에 미리(d3·dday만 — "초과"는 실제로 지난 뒤 월요일에).
- 받는 사람: 해당 현장 담당요원(요원 메일, staff_contact) + 관리자(설정 탭 "관리자 알림 메일", 전체 목록). 사람마다 한 통으로 모아서.
  보낼 게 없는 날은 안 보냄. 설정에서 알림을 끄면 안 보냄.
- 경로는 지금 메일뿐. 문자/카카오 알림톡은 유료 결정 뒤 channel="sms"로 같은 계획(`plan`)을 한 번 더 돌리면 된다(보류).
"""

from __future__ import annotations

import datetime
import time
import traceback

from core import config
from core.db import SessionLocal
from core.models_web import Company, DeadlineAlert, StaffContact
from server import settings as app_settings
from server.api import mailer
from server.api.deadlines import SiteDeadline, site_deadlines

SEND_HOUR = 9
CHECK_EVERY_SECONDS = 60
RETRY_AFTER_FAIL_SECONDS = 30 * 60
KIND_LABEL = {"d3": "⏰ 기한 임박", "dday": "⏰ 오늘이 기한", "over": "⚠ 기한 초과"}
WEEKDAY = "월화수목금토일"

_last_check = 0.0
_done: dict[int, datetime.date] = {}  # 회사별 오늘 알림을 끝낸 날
_retry_at: dict[int, float] = {}


def due_kind(d: SiteDeadline, imminent_days: int, today: datetime.date) -> str | None:
    """오늘 보낼 단계(가장 급한 것 하나) 또는 None. 금요일엔 주말(토·일)에 걸리는 d3·dday를 당겨 온다."""
    pull_to = today + datetime.timedelta(days=2) if today.weekday() == 4 else today
    if d.deadline < today:
        return "over"
    if d.deadline <= pull_to:
        return "dday"
    if d.deadline - datetime.timedelta(days=imminent_days) <= pull_to:
        return "d3"
    return None


def plan(db, company_id: int, today: datetime.date, channel: str = "mail") -> list[tuple[SiteDeadline, str]]:
    """오늘 보낼 (현장 기한, 단계) — 이미 보낸 것 제외."""
    imminent_days = config.get_deadline_imminent_days(company_id)
    out = []
    for d in site_deadlines(db, company_id, today):
        kind = due_kind(d, imminent_days, today)
        if kind is None:
            continue
        sent = db.query(DeadlineAlert.id).filter_by(site_id=d.site_id, deadline=d.deadline, kind=kind, channel=channel).first()
        if not sent:
            out.append((d, kind))
    return out


def _date_text(day: datetime.date) -> str:
    return f"{day.month}/{day.day}({WEEKDAY[day.weekday()]})"


def _line(d: SiteDeadline, kind: str) -> str:
    if d.days_left < 0:
        when = f"기한 {_date_text(d.deadline)}, {-d.days_left}일 지남"
    elif d.days_left == 0:
        when = f"기한 오늘 {_date_text(d.deadline)}"
    else:
        when = f"기한 {_date_text(d.deadline)}, D-{d.days_left}"
    last = f"마지막 지도 {_date_text(d.last_date)} {d.last_visit_no}회차" if d.last_date else "아직 지도 기록 없음(공사 시작일 기준)"
    return f"{KIND_LABEL[kind]} — {d.site_name} (담당 {d.staff_name or '미지정'})\n    {when} · {last}"


def _compose(items: list[tuple[SiteDeadline, str]], today: datetime.date) -> tuple[str, str]:
    over = sum(k == "over" for _, k in items)
    near = len(items) - over
    parts = ([f"임박 {near}곳"] if near else []) + ([f"초과 {over}곳"] if over else [])
    subject = f"[{app_settings.MAIL_FROM_NAME}] 기술지도 기한 알림 — {' · '.join(parts) or '없음'} ({today.month}/{today.day})"
    order = {"over": 0, "dday": 1, "d3": 2}
    lines = [_line(d, k) for d, k in sorted(items, key=lambda x: (order[x[1]], x[0].days_left))]
    body = (
        "안녕하세요. 기술지도 기한(마지막 지도일 + 15일)이 가까운 현장을 알려 드립니다.\n\n"
        + ("\n\n".join(lines) if lines else "지금 임박하거나 초과된 현장이 없습니다.")
        + f"\n\n제출 현황 보기: {app_settings.PUBLIC_BASE_URL}/status.html\n"
        "(이 메일은 보고서 자동화가 자동으로 보냈습니다. 알림 설정은 보고서 자동화 → 설정 탭)"
    )
    return subject, body


def _admin_emails(company_id: int) -> list[str]:
    return [a.strip() for a in config.get_deadline_admin_email(company_id).split(",") if a.strip()]


def run_company(company_id: int, today: datetime.date) -> bool:
    """오늘 알림을 보낸다. 끝났으면(보냈거나 보낼 게 없음) True, 메일이 전부 실패했으면 False(나중에 다시)."""
    with SessionLocal() as db:
        items = plan(db, company_id, today)
        if not items:
            return True
        # 받는 사람별로 모으기 — 요원은 자기 현장만, 관리자는 전부(같은 주소면 하나로)
        staff_email = dict(db.query(StaffContact.staff_id, StaffContact.email))
        inbox: dict[str, tuple[str, list]] = {}
        for addr in _admin_emails(company_id):
            inbox.setdefault(addr.lower(), (addr, []))[1].extend(items)
        for d, kind in items:
            addr = (staff_email.get(d.staff_id) or "").strip() if d.staff_id else ""
            if addr and mailer.valid_email(addr):
                bucket = inbox.setdefault(addr.lower(), (addr, []))[1]
                if (d, kind) not in bucket:
                    bucket.append((d, kind))
        if not inbox:
            print(f"[deadline_notifier] 회사 {company_id}: 알림 {len(items)}건이 있지만 받을 메일이 없음(요원·관리자 메일 미등록)")
            return True
        delivered: dict[tuple[int, str], list[str]] = {}
        for addr, bucket in inbox.values():
            subject, body = _compose(bucket, today)
            try:
                refused = mailer.send_mail([addr], "", subject, body)
            except mailer.MailError as e:
                print(f"[deadline_notifier] {addr} 메일 실패: {e}")
                continue
            if refused:
                print(f"[deadline_notifier] {addr} 거부됨")
                continue
            for d, kind in bucket:
                delivered.setdefault((d.site_id, kind), []).append(addr)
        if not delivered:
            return False
        now = datetime.datetime.now()
        for d, kind in items:
            if (d.site_id, kind) in delivered:
                db.add(DeadlineAlert(site_id=d.site_id, deadline=d.deadline, kind=kind, channel="mail",
                                     sent_at=now, recipients=", ".join(delivered[(d.site_id, kind)])))
        db.commit()
        print(f"[deadline_notifier] 회사 {company_id}: {len(delivered)}건 알림 → {len(inbox)}명")
        return True


def tick(now: datetime.datetime | None = None) -> None:
    """워커 루프에서 자주 불러도 된다(1분에 한 번만 실제 확인)."""
    global _last_check
    if time.monotonic() - _last_check < CHECK_EVERY_SECONDS:
        return
    _last_check = time.monotonic()
    now = now or datetime.datetime.now()
    today = now.date()
    if today.weekday() >= 5 or now.hour < SEND_HOUR or not mailer.is_configured():
        return
    try:
        with SessionLocal() as db:
            company_ids = [cid for (cid,) in db.query(Company.id)]
        for cid in company_ids:
            if _done.get(cid) == today or time.monotonic() < _retry_at.get(cid, 0):
                continue
            if not config.get_deadline_alert_enabled(cid):
                _done[cid] = today
                continue
            if run_company(cid, today):
                _done[cid] = today
            else:
                _retry_at[cid] = time.monotonic() + RETRY_AFTER_FAIL_SECONDS
    except Exception:  # noqa: BLE001 — 알림이 실패해도 PDF 렌더 루프는 계속 돌아야 함
        print(f"[deadline_notifier] 오류\n{traceback.format_exc()}")


def send_test(company_id: int) -> dict:
    """설정 탭 [시험 메일 보내기] — 지금 임박·초과 현장 전부를 관리자 알림 메일로(기록 안 남김)."""
    if not mailer.is_configured():
        raise ValueError("메일 보내기 설정이 아직 안 됐습니다(회사 네이버 메일 연결 필요).")
    admins = _admin_emails(company_id)
    if not admins:
        raise ValueError("관리자 알림 메일을 먼저 저장하세요.")
    today = datetime.date.today()
    with SessionLocal() as db:
        items = [(d, "over" if d.stage == "over" else ("dday" if d.days_left == 0 else "d3"))
                 for d in site_deadlines(db, company_id, today) if d.stage != "ok"]
    subject, body = _compose(items, today)
    try:
        mailer.send_mail(admins, "", "[시험] " + subject, body)
    except mailer.MailError as e:
        raise ValueError(str(e)) from e
    return {"ok": True, "to": admins, "count": len(items)}
