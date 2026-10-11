"""시특법 사진 AI(2026-10-11) — 사진 한 장(또는 몇 장) + 질문 → 답 글. 전경사진 제목·실명판(sitok_overview), 현장 결함 사진 분석(sitok_defects)이 같이 씀."""
from __future__ import annotations

import base64
import io
import json
import re

from PIL import Image, ImageOps


def _jpeg(data: bytes, side: int = 1200) -> str:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def ask(company_id: int, images: list[bytes], prompt: str, max_tokens: int = 8000) -> str:
    """그림들 + 질문 → 답 글 전부."""
    from anthropic import Anthropic

    from core.config import get_api_key, get_model_name

    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(b)}} for b in images]
    content.append({"type": "text", "text": prompt})
    client = Anthropic(api_key=get_api_key(company_id))
    with client.messages.stream(model=get_model_name(), max_tokens=max_tokens, messages=[{"role": "user", "content": content}]) as stream:
        resp = stream.get_final_message()
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def ask_json(company_id: int, images: list[bytes], prompt: str, max_tokens: int = 8000):
    """답에서 JSON(객체 또는 배열) 하나를 꺼냄."""
    text = ask(company_id, images, prompt, max_tokens)
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        raise ValueError("AI 답에서 JSON을 찾지 못했습니다.")
    return json.loads(m.group(0))
