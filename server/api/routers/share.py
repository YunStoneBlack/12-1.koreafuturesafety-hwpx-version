"""메일로 보낸 보고서 내려받기 링크(2026-10-25, server/api/mail_jobs.py) — 받는 사람(발주처)이 로그인 없이 여는 유일한 길.

그룹웨어 nginx가 `/report/share/`만 로그인 확인(auth_request) 없이 넘기고 사용자·비밀값 헤더는 지움(server/deploy/nginx_report_locations.conf).
여기 두 주소 말고는 그대로 로그인이 필요함. 토큰(32자 무작위)을 모르면 열 수 없고, 기한이 지나거나 [링크 끊기]면 안내만.
파일은 열 때의 합본(보낸 뒤 다시 만들었으면 새 것). 내려받은 횟수를 셈(이어받기 요청은 처음 한 번만).

- `GET /share/{token}` — 내려받기 화면(보고서 이름·크기·기한, [내려받기]·[바로 보기])
- `GET /share/{token}/file` — PDF(?view=1 이면 브라우저에서 바로 보기)
"""
from __future__ import annotations

import datetime
import html
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from core.models_web import MailJob, SitokReport
from server import settings as app_settings
from server.api import mail_jobs
from server.api.deps import get_db

router = APIRouter(tags=["share"])
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,64}")
HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"}


def _find(db: Session, token: str) -> tuple[MailJob | None, SitokReport | None, str]:
    """(메일, 회차, 못 여는 이유)."""
    if not TOKEN_RE.fullmatch(token or ""):
        return None, None, "없는 링크입니다. 메일에 있는 주소 그대로 열어 주세요."
    j = db.query(MailJob).filter(MailJob.token == token, MailJob.kind == "sitok").first()
    if j is None or j.status != "done":
        return None, None, "없는 링크입니다. 메일에 있는 주소 그대로 열어 주세요."
    if not j.expires_at or j.expires_at <= datetime.datetime.now():
        return j, None, "내려받기 기한이 지난 링크입니다."
    r = db.get(SitokReport, j.report_id)
    if r is None:
        return j, None, "보고서를 찾을 수 없습니다."
    if mail_jobs.sitok_pdf(r) is None:
        return j, r, "보고서를 다시 만드는 중입니다. 잠시 뒤 다시 열어 주세요."
    return j, r, ""


def _page(title: str, inner: str, code: int = 200) -> HTMLResponse:
    company = html.escape(app_settings.MAIL_FROM_NAME)
    doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{html.escape(title)} - {company}</title>
<style>
:root {{ --ink:#1d2433; --muted:#667085; --line:#e4e7ec; --blue:#2f6fe4; --paper:#f5f7fb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif; }}
.wrap {{ max-width:560px; margin:0 auto; padding:40px 16px; }}
.brand {{ font-weight:700; color:var(--blue); font-size:15px; margin-bottom:14px; }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:14px; padding:24px 22px; box-shadow:0 4px 18px rgba(16,24,40,.06); }}
h1 {{ font-size:19px; line-height:1.45; margin:0 0 14px; word-break:keep-all; }}
.meta {{ display:grid; grid-template-columns:72px 1fr; gap:6px 10px; font-size:14px; margin:0 0 20px; }}
.meta dt {{ color:var(--muted); }} .meta dd {{ margin:0; word-break:break-all; }}
.btns {{ display:flex; flex-wrap:wrap; gap:8px; }}
.btn {{ display:inline-flex; align-items:center; justify-content:center; padding:12px 20px; border-radius:10px; font-size:15px; font-weight:700;
  text-decoration:none; border:1px solid var(--blue); color:var(--blue); background:#fff; flex:1 1 160px; }}
.btn.main {{ background:var(--blue); color:#fff; }}
.note {{ font-size:13px; color:var(--muted); margin-top:16px; line-height:1.6; }}
.msg {{ font-size:15px; line-height:1.6; margin:0; }}
</style></head><body><div class="wrap"><div class="brand">{company}</div><div class="card">{inner}</div></div></body></html>"""
    return HTMLResponse(doc, status_code=code, headers=HEADERS)


@router.get("/share/{token}", response_class=HTMLResponse)
def share_page(token: str, db: Session = Depends(get_db)):
    j, r, why = _find(db, token)
    contact = html.escape(app_settings.MAIL_SMTP_USER)
    if why:
        tail = f" 다시 필요하시면 {html.escape(app_settings.MAIL_FROM_NAME)}({contact})로 연락해 주세요." if j is not None else ""
        return _page("보고서 내려받기", f'<h1>보고서 내려받기</h1><p class="msg">{html.escape(why)}{tail}</p>', 410 if j is not None else 404)
    pdf = mail_jobs.sitok_pdf(r)
    exp = j.expires_at
    title = mail_jobs.sitok_title(r)
    inner = f"""<h1>{html.escape(title)}</h1>
<dl class="meta"><dt>파일</dt><dd>{html.escape(pdf.name)}</dd><dt>크기</dt><dd>{mail_jobs.size_text(pdf.stat().st_size)}</dd>
<dt>기한</dt><dd>{exp.year}년 {exp.month}월 {exp.day}일까지</dd></dl>
<div class="btns"><a class="btn main" href="{html.escape(token)}/file">⬇ 내려받기</a><a class="btn" href="{html.escape(token)}/file?view=1" target="_blank" rel="noopener">바로 보기</a></div>
<p class="note">파일이 커서 휴대폰 데이터로는 시간이 걸릴 수 있습니다. 문의: {contact}</p>"""
    return _page(title, inner)


@router.get("/share/{token}/file")
def share_file(request: Request, token: str, view: int = 0, db: Session = Depends(get_db)):
    j, r, why = _find(db, token)
    if why:
        return share_page(token, db)
    rng = request.headers.get("range", "")
    if not rng or rng.replace(" ", "").startswith("bytes=0-"):  # 이어받기·PDF 보기의 부분 요청은 처음 한 번만 셈
        j.downloads = (j.downloads or 0) + 1
        j.last_download_at = datetime.datetime.now()
        db.commit()
    pdf = mail_jobs.sitok_pdf(r)
    return FileResponse(pdf, media_type="application/pdf", filename=pdf.name,
                        content_disposition_type="inline" if view else "attachment", headers=HEADERS)
