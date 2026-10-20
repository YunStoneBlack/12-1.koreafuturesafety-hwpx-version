"""시특법 결함 사진 분류 교정 기록(2026-10-12 사용자 — "점검자가 바꿔 등록하면 학습해서 다음 사진 분석에", 원인 추천은 안 함).

AI를 다시 학습시키는 게 아니라 회사 교정 기록을 쌓아 다음 분석 때 같이 보여 줌:
1) [+ 신규] 사진 분석 — AI 첫 추천(구분·부재·결함유형) + 사진 작은 사본(token) → 화면이 [추가] 때 같이 보냄 → sitok_defect.ai_guess.
2) 저장·고칠 때 추천과 다르면 sitok_correction(AI 추천 → 점검자 값, 사진 사본) — 같아지면 지움(sync).
3) 다음 사진에서 AI 첫 추천과 같은 추천을 고친 기록이 있으면 그 사진들(최대 4장)을 같이 보여 주고 다시 판단(recheck) — 이 사진도 그 경우면 고친 쪽으로.
설정 탭 "사진 분류 교정 기록"에서 묶음별로 보고 잘못 쌓인 것은 지움.
"""
from __future__ import annotations

import datetime
import io
import secrets
import shutil
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from core.models_web import SitokCorrection, SitokDefect

MAX_EXAMPLES = 4


def _dir() -> Path:
    from server.api.routers.sitok import ROOT
    return ROOT / "_교정사진"


def _thumb(jpg: bytes, side: int = 720) -> bytes:
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(jpg))).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def save_pending(jpg: bytes) -> str:
    """분석한 사진의 작은 사본을 임시로(하루 지나면 지움) → token."""
    tmp = _dir() / "_임시"
    tmp.mkdir(parents=True, exist_ok=True)
    old = datetime.datetime.now().timestamp() - 86400
    for p in tmp.glob("*.jpg"):
        if p.stat().st_mtime < old:
            p.unlink(missing_ok=True)
    token = secrets.token_hex(10)
    (tmp / f"{token}.jpg").write_bytes(_thumb(jpg))
    return token


def claim(token: str | None) -> str:
    """임시 사본을 교정 사진 폴더로 옮겨 경로(없으면 "")."""
    if not token or not token.isalnum():
        return ""
    src = _dir() / "_임시" / f"{token}.jpg"
    if not src.exists():
        return ""
    dest = _dir() / f"{token}.jpg"
    shutil.move(str(src), dest)
    return str(dest)


def guess_from(body_guess: dict | None) -> dict | None:
    """화면이 보낸 ai_guess {part, member, dtype, token} → 결함에 붙일 {part, member, dtype, thumb}."""
    if not body_guess or not body_guess.get("dtype"):
        return None
    return {"part": str(body_guess.get("part") or ""), "member": str(body_guess.get("member") or ""), "dtype": str(body_guess.get("dtype") or ""),
            "thumb": claim(body_guess.get("token"))}


def sync(db: Session, d: SitokDefect, company_id: int, by: str) -> None:
    """결함 값이 AI 첫 추천과 다르면 교정 기록(있으면 고침), 같으면 지움."""
    g = d.ai_guess or {}
    row = db.query(SitokCorrection).filter(SitokCorrection.defect_id == d.id).first() if d.id else None
    if not g.get("dtype"):
        return
    differs = (d.part or "", d.member or "", d.dtype or "") != (g.get("part", ""), g.get("member", ""), g.get("dtype", ""))
    if not differs:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        row = SitokCorrection(company_id=company_id, defect_id=d.id, ai_part=g.get("part", ""), ai_member=g.get("member", ""), ai_dtype=g.get("dtype", ""),
                              thumb=g.get("thumb") or "", created_by=by)
        db.add(row)
    row.part, row.member, row.dtype = d.part or "", d.member or "", d.dtype or ""


def examples(db: Session, company_id: int, part: str, member: str, dtype: str) -> list[SitokCorrection]:
    """AI가 같은 추천을 했다가 점검자가 고친 기록 — 많이 고친 값 순, 같은 값 안에선 최근 순, 사진 있는 것만 최대 MAX_EXAMPLES."""
    rows = [c for c in db.query(SitokCorrection).filter(SitokCorrection.company_id == company_id, SitokCorrection.ai_dtype == dtype,
                                                         SitokCorrection.ai_member == member, SitokCorrection.ai_part == part)
            .order_by(SitokCorrection.created_at.desc()) if c.thumb and Path(c.thumb).exists()]
    freq = Counter((c.part, c.member, c.dtype) for c in rows)
    rows.sort(key=lambda c: -freq[(c.part, c.member, c.dtype)])
    return rows[:MAX_EXAMPLES]


RECHECK = """시설물 정기안전점검 결함 사진 분류입니다. 첫째 사진이 이번에 찍은 사진이고, AI는 처음에 "{guess}"로 봤습니다.
그런데 이 회사 점검자들은 AI가 같은 "{guess}"로 본 아래 사진들을 다르게 고쳐 등록했습니다(회사 판단 기준):
{examples}
이번 사진이 위 고친 사진들과 같은 경우(같은 부위·같은 모양의 결함)면 점검자가 고친 값으로, 다른 경우면 처음 판단 그대로 답하세요.
- member는 반드시 이 목록 중 하나 그대로: {members}
- dtype은 반드시 이 목록 중 하나 그대로: {types}
JSON 객체 하나로만 답하세요(설명 없이): {{"part": {parts}, "member": "부재", "dtype": "결함유형", "same_case": 고친 사진들과 같은 경우면 true, "why": "판단 근거 한 줄"}}"""


def recheck(company_id: int, jpg: bytes, first: dict, rows: list[SitokCorrection], allowed: dict, parts=("구조체", "비구조체")) -> dict:
    """회사 교정 기록 사진들과 비교해 다시 판단 → {part, member, dtype, same_case, why}. parts = 구분 값들(옹벽은 주요·일반·부대시설, 10/20)."""
    from server.sitok import vision

    imgs = [jpg] + [Path(c.thumb).read_bytes() for c in rows]
    guess = f"{first['part']} · {first['member'] or '-'} · {first['dtype']}"
    ex = "\n".join(f"- {i}번째 사진: 점검자가 \"{c.part} · {c.member or '-'} · {c.dtype}\"로 고침" for i, c in enumerate(rows, 2))
    return vision.ask_json(company_id, imgs, RECHECK.format(guess=guess, examples=ex, members=", ".join(allowed["member"]),
                                                             types=", ".join(allowed["dtype"]), parts=" 또는 ".join(f'"{p}"' for p in parts)))


def groups(db: Session, company_id: int) -> list[dict]:
    """설정 탭 — (AI 추천 → 점검자 값) 묶음별 건수·기록들, 많은 순."""
    out: dict = {}
    for c in db.query(SitokCorrection).filter(SitokCorrection.company_id == company_id).order_by(SitokCorrection.created_at.desc()):
        k = ((c.ai_part, c.ai_member, c.ai_dtype), (c.part, c.member, c.dtype))
        g = out.setdefault(k, {"ai": " · ".join(x for x in k[0] if x), "to": " · ".join(x for x in k[1] if x), "items": []})
        g["items"].append({"id": c.id, "by": c.created_by, "at": c.created_at.strftime("%Y-%m-%d"), "has_photo": bool(c.thumb and Path(c.thumb).exists())})
    return sorted(out.values(), key=lambda g: -len(g["items"]))
