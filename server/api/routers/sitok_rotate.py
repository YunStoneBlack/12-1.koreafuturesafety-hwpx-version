"""시특법 현장 조사 사진 돌리기(2026-10-23 형 "세로로 찍힌 사진 폰에서 확인 불가 → 사진 돌리기 기능(산안법 자동화에 있는 기능)").

화면은 사진 주소(GET …/photo)를 그대로 보냄 — `POST /sitok/rotate {src}` → 그 주소의 GET 함수로 파일을 찾고(권한 확인도 그 함수가) 산안법과 같은
`photo_rotate.rotate_file`(원본을 세운 뒤 오른쪽 90도, 같은 파일에 덮어씀). 돌릴 수 있는 사진: 결함 이번 사진·전회차 사진(이 회차 폴더 안 것만 —
직전 회차에서 이어 온 사진은 그 회차 파일), 전경사진, 상태양호, 내진보강, 공중이용·기타시설. 화면 js/sitok-photos.js(크게 보기 창 [↻ 돌리기]).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import User
from server.api.deps import get_current_user, get_db
from server.api.routers.photo_rotate import rotate_file

router = APIRouter(prefix="/sitok", tags=["sitok"])


class RotateIn(BaseModel):
    src: str


def _file(src: str, user: User, db: Session) -> Path:
    """사진 주소 → 파일(그 주소의 GET 함수가 권한 확인·파일 찾기)."""
    from server.api.routers import sitok_defects, sitok_good, sitok_overview, sitok_parts

    u = urlparse(src)
    path = re.sub(r"^.*?/api(?=/sitok/)", "", u.path)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    resp = None
    if m := re.fullmatch(r"/sitok/defects/(\d+)/photo/(now|prev)", path):
        d, r = sitok_defects._require(db, user, int(m[1]))
        if m[2] == "prev" and not (d.prev_photo and sitok_defects._own_file(db, r, d.prev_photo)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "직전 회차에서 이어 온 전회차 사진은 여기서 못 돌립니다 — [＋]로 다시 올리세요.")
        resp = sitok_defects.photo(int(m[1]), m[2], user=user, db=db)
    elif m := re.fullmatch(r"/sitok/reports/(\d+)/overview/(\w+)/photo", path):
        resp = sitok_overview.photo(int(m[1]), m[2], q.get("which", "now"), user=user, db=db)
    elif m := re.fullmatch(r"/sitok/reports/(\d+)/good/photo", path):
        resp = sitok_good.good_photo(int(m[1]), q.get("key", ""), int(q.get("idx", -1)), user=user, db=db)
    elif m := re.fullmatch(r"/sitok/reports/(\d+)/seismic/photo", path):
        resp = sitok_good.seismic_photo(int(m[1]), int(q.get("slot", -1)), user=user, db=db)
    elif m := re.fullmatch(r"/sitok/reports/(\d+)/parts/photo", path):
        resp = sitok_parts.photo(int(m[1]), q.get("group", ""), q.get("key", ""), int(q.get("slot", 0)), q.get("which", "now"), user=user, db=db)
    if resp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이 사진은 돌릴 수 없습니다.")
    return Path(resp.path)


@router.post("/rotate")
def rotate(body: RotateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rotate_file(str(_file(body.src, user, db)))
    return {"ok": True}
