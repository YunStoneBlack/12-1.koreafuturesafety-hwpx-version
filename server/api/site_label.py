"""화면에 보이는 현장 이름 앞 관리번호(2026-10-01 사용자) — "26-12)_고모지구 수리시설개보수사업 토목공사".

관리번호 줄이기: "연도-숫자"면 연도는 뒤 두 자리, 숫자는 앞 0을 뺀다(2026-0000046 → 26-46, 24-000025 → 24-25, 25-120 그대로).
그 밖의 모양(26-M5 등)은 그대로. 관리번호가 없으면 이름만. 화면 표시용 — 보고서 표지·고객사 메일에는 안 쓴다(표지엔 관리번호 칸이 따로).
같은 규칙이 화면 쪽 app.js `siteLabel`에도 있다(현장 목록·현장 화면은 현장 정보를 그대로 받아서 화면이 붙임).
"""

from __future__ import annotations

import re

_NUM = re.compile(r"^(\d{2}|\d{4})-0*(\d+)$")


def short_mgmt(management_no: str | None) -> str:
    m = (management_no or "").strip()
    found = _NUM.match(m)
    return f"{found.group(1)[-2:]}-{found.group(2)}" if found else m


def site_label(site) -> str:
    """현장(Site) → "26-12)_현장명"(관리번호 없으면 현장명)."""
    short = short_mgmt(getattr(site, "management_no", ""))
    return f"{short})_{site.name}" if short else site.name
