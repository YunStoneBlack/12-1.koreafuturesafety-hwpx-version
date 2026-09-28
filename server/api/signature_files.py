"""서명/도장 이미지 저장 공용 헬퍼 — 담당요원 서명, 결재란(이사·대표이사) 도장.

데스크톱 서명칸(`desktop/widgets/signature_pad.py`)처럼 "직접 그리기"(캔버스 PNG)와 "이미지 올리기"
(도장 스캔 등 JPG/PNG) 둘 다 받는다. 올린 이미지는 형식과 무관하게 PNG로 변환해 고정 경로에 저장한다
(확장자와 실제 형식이 어긋나지 않게, 투명 배경 유지). `source`("drawn"|"uploaded")는 데스크톱과
같은 값으로 기록만 한다(렌더러는 구분 없이 같은 방식으로 넣는다).
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps

from core.db import BASE_DIR

SIGNATURE_DIR = BASE_DIR / "data" / "signatures"
_MAX_SIDE = 1200  # 도장 스캔 원본이 커도 결재란 칸은 작다 — 용량만 줄이고 화질엔 영향 없음


async def save_signature_upload(file: UploadFile, filename: str) -> Path:
    data = await file.read()
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGBA")
            img.thumbnail((_MAX_SIDE, _MAX_SIDE))
            SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)
            dest = SIGNATURE_DIR / filename
            img.save(dest, "PNG")
    except (OSError, ValueError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미지 파일만 등록할 수 있습니다.") from err
    return dest


def normalize_source(source: str) -> str:
    return source if source in ("drawn", "uploaded") else "drawn"
