"""시특법 AI 호출 한 곳(2026-10-11) — 그림 몇 장(없어도 됨) + 질문 → 답 글/JSON. 스트리밍(긴 답은 SDK가 요구).
쓰는 곳: AI 초안(ai_draft), 결함 사진 분석·원인 추천(sitok_defects), 전경사진 제목·실명판(sitok_overview), 타회사 PDF 결함표(foreign_read),
시설물 현황 채우기(detail). 관리대장·계약서 PDF 읽기는 core.contract_analyzer(server/sitok/reader.py)."""
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

    from core.config import get_api_key, get_model_name, has_api_key

    if not has_api_key(company_id):
        raise RuntimeError("Claude API 키가 없습니다 — 보고서 자동화 설정 탭에서 등록하세요.")
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
