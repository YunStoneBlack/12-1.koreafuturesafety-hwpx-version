"""보고서 화면 사진 칸용 작은 사진(썸네일) — 원본은 그대로 두고 보여주기용 사본만 만든다.

폰 원본 사진은 한 장 3~6MB라 보고서 하나(사진 10~13장)를 열 때마다 수십 MB를 받았다(이 PC →
SSH 터널 → AWS → 폰, 이 PC의 올리기 속도가 병목). 사진 칸은 64×48로 보이므로 긴 쪽 320px
JPEG(한 장 수십 KB)면 충분하다. 한글·PDF 만들기는 DB의 원본 경로를 그대로 쓰므로 영향 없음.

- 사진 GET 엔드포인트에 `?thumb=1`이 붙을 때만 썸네일, 없으면 지금처럼 원본(제공자료 "크게 보기" 등).
- 썸네일은 `data/thumbs/`(백업 대상 아님 — 언제든 다시 만들 수 있음)에 처음 요청될 때 만든다.
  원본의 수정 시각을 썸네일에 그대로 찍어 두고, 둘이 다르면(사진 교체·이월 복사) 다시 만든다.
- 응답은 `Cache-Control: no-cache` + ETag — 폰이 받아 둔 사진을 쓰되 매번 "바뀌었나"만 물어보고,
  안 바뀌었으면 304(본문 없음)로 끝난다. 그래서 화면은 주소에 매번 시각을 붙이지 않아도 된다.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import Request, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageOps

from core.db import BASE_DIR

THUMB_LONG_SIDE = 320
_THUMB_DIR = BASE_DIR / "data" / "thumbs"


def _thumb_path(src: Path) -> Path:
    try:
        rel = src.resolve().relative_to((BASE_DIR / "data").resolve())
        return _THUMB_DIR / (str(rel) + ".jpg")
    except ValueError:  # data/ 밖(있을 일은 없지만) — 경로 해시로 이름을 만든다
        return _THUMB_DIR / "other" / (hashlib.sha1(str(src.resolve()).encode()).hexdigest()[:20] + ".jpg")


def ensure_thumb(src: Path) -> Path | None:
    """썸네일 경로를 돌려준다(없거나 원본이 바뀌었으면 새로 만듦). 만들 수 없으면 None."""
    src_stat = src.stat()
    dest = _thumb_path(src)
    if dest.exists() and dest.stat().st_mtime_ns == src_stat.st_mtime_ns:
        return dest
    try:
        with Image.open(src) as img:
            img.draft("RGB", (THUMB_LONG_SIDE, THUMB_LONG_SIDE))  # JPEG은 디코딩 단계에서 줄여 빠르게
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, "white")
                bg.paste(img, mask=img.getchannel("A"))
                img = bg
            else:
                img = img.convert("RGB")
            img.thumbnail((THUMB_LONG_SIDE, THUMB_LONG_SIDE), Image.LANCZOS)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + f".{os.getpid()}.tmp")
            img.save(tmp, "JPEG", quality=80)
        os.replace(tmp, dest)
        os.utime(dest, ns=(src_stat.st_atime_ns, src_stat.st_mtime_ns))
        return dest
    except Exception:
        return None


def photo_response(request: Request, path: str | Path, thumb: bool) -> Response:
    """사진 GET 공용 응답 — `thumb`이면 썸네일(+ETag/304), 아니면 원본 그대로."""
    path = Path(path)
    if not thumb:
        return FileResponse(path)
    served = ensure_thumb(path) or path  # 못 만드는 사진(깨진 파일 등)은 원본으로라도 보여 준다
    st = served.stat()
    etag = '"' + hashlib.md5(f"{served}-{st.st_mtime_ns}-{st.st_size}".encode()).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(served, headers=headers)
