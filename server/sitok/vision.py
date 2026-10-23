"""시특법 AI 호출 한 곳(2026-10-11) — 그림 몇 장(없어도 됨) + 질문 → 답 글/JSON. 스트리밍(긴 답은 SDK가 요구).
쓰는 곳: AI 초안(ai_draft), 결함 사진 분석·원인 추천(sitok_defects), 전경사진 제목·실명판(sitok_overview), 타회사 PDF 결함표(foreign_read),
시설물 현황 채우기(detail). 관리대장·계약서 PDF 읽기는 core.contract_analyzer(server/sitok/reader.py)."""
from __future__ import annotations

import base64
import io
import json
import re

from PIL import Image, ImageOps

from core.report_style import WRITING_STYLE, clean_text  # 보고서 글 말투(산안법 core/vision_analyzer도 같이 씀)


def _jpeg(data: bytes, side: int = 1200) -> str:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


MIN_TOKENS = 16000  # 생각(thinking)이 켜진 모델(sonnet 5 등)은 생각 토큰도 max_tokens에 들어가서, 작으면 생각만 하다 끊겨 답이 빔(10/14 일람표 11줄에서 4000 전부 thinking)


def ask(company_id: int, images: list[bytes], prompt: str, max_tokens: int = 8000, side: int = 1200, effort: str | None = None,
        writing: bool = False) -> str:
    """그림들 + 질문 → 답 글 전부. side = 긴 변(px) — 일람표처럼 작은 글씨는 1568(10/14). effort = low·medium·high(생각 깊이, 비우면 모델 기본).
    writing = 보고서에 들어갈 글(AI 초안·원인·점검표·종합의견 …) — 말투 규칙(WRITING_STYLE)을 system으로 주고 답에서 제3자 표현을 지움(clean_text).
    답이 비고 max_tokens로 끊겼으면(생각만 하다 끝) 상한을 두 배로 한 번 더."""
    from anthropic import Anthropic

    from core.config import get_api_key, get_model_name, has_api_key

    if not has_api_key(company_id):
        raise RuntimeError("Claude API 키가 없습니다 — 보고서 자동화 설정 탭에서 등록하세요.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(b, side)}} for b in images]
    content.append({"type": "text", "text": prompt})
    client = Anthropic(api_key=get_api_key(company_id))
    extra = {"output_config": {"effort": effort}} if effort else {}
    if writing:
        extra["system"] = WRITING_STYLE
    limit = max(max_tokens, MIN_TOKENS)
    for attempt in range(2):
        with client.messages.stream(model=get_model_name(), max_tokens=limit, messages=[{"role": "user", "content": content}], **extra) as stream:
            resp = stream.get_final_message()
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text or resp.stop_reason != "max_tokens":
            return clean_text(text) if writing else text
        limit *= 2
    return ""


def ask_json(company_id: int, images: list[bytes], prompt: str, max_tokens: int = 8000, side: int = 1200, effort: str | None = None,
             writing: bool = False):
    """답에서 JSON(객체 또는 배열) 하나를 꺼냄. 배열이 중간에 끊겼으면 완성된 항목까지. writing = ask와 같음(보고서 글 말투)."""
    text = ask(company_id, images, prompt, max_tokens, side, effort, writing)
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    items = re.findall(r"\{[^{}]*\}", text, re.S)  # 끊긴 배열 — 객체 단위로 건짐
    if items:
        out = []
        for it in items:
            try:
                out.append(json.loads(it))
            except json.JSONDecodeError:
                continue
        if out:
            return out
    raise ValueError("AI 답에서 JSON을 찾지 못했습니다." + (f" (답 {len(text)}자)" if text else " (답이 비었음)"))
