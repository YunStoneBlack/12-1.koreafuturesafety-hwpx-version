"""현장 사진을 Claude Vision으로 분석하는 모듈 (지적사항 AI추천 / 안전교육 인원수 세기).

핵심 원칙: 사진에서 판단이 어려우면 절대 지어내지 말고 정직하게 실패를 알린다.
실제 웹 시스템에서 무관한 사진을 넣었을 때 "안전점검 위반사항 확인 어려운 이미지"로
응답하고, 인원을 못 세면 "사진에서 인원을 읽지 못했습니다"로 응답한 동작을 그대로 따른다.
API 호출부(_call_claude)를 분리해서 나중에 테스트 시 mocking하기 쉽게 했다.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path

from anthropic import Anthropic

from core.config import get_api_key, get_model_name

_SUPPORTED_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

FINDING_PROMPT = """당신은 건설재해예방 기술지도를 보조하는 전문가입니다.
첨부된 현장 사진과 지도자가 적은 설명을 참고해 지적사항을 작성하세요.

지도자 설명: {description}

중요한 규칙:
- 사진 화질이 나쁘거나, 설명이 모호하거나, 사진에서 위반사항을 특정하기 어려우면
  절대 위반사항을 지어내지 마세요. 대신 "안전점검 위반사항 확인 어려운 이미지"처럼
  판단이 곤란하다는 취지로 제목/내용을 작성하고, 향후 촬영 시 개선할 점(근접 촬영,
  각도 조정 등)을 안내하세요.
- 사진과 설명이 충분하면 실제 위반사항과 구체적인 개선대책을 작성하세요.
- law_citation은 관련 있다고 판단되는 산업안전보건 관련 법령·규칙 조항명을 간단히
  적되, 확신이 없으면 빈 문자열로 두세요("산업안전보건기준에 관한 규칙 제OO조(...)" 형식 권장).

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{{
  "title": "지적사항 제목 (30자 이내)",
  "content": "지적사항 및 개선대책 (110자 이내)",
  "law_citation": "관련 법령 조항 (확신 없으면 빈 문자열)"
}}"""

PEOPLE_COUNT_PROMPT = """첨부된 사진에서 사람이 몇 명 보이는지 세어주세요.
사람을 명확히 셀 수 없는 사진(사람이 없거나, 너무 흐리거나, 사람과 무관한 사진 등)이면
절대 추측하지 말고 count를 null로 응답하세요.

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{"count": "숫자 또는 null"}"""

MEASUREMENT_READ_PROMPT = """첨부된 사진은 '{instrument_type}'의 측정 화면(디스플레이) 사진입니다.
화면에 표시된 측정값(숫자)을 읽어주세요. 화면이 흐리거나, 꺼져 있거나, 숫자를 명확히
읽을 수 없으면 절대 추측하지 말고 value를 null로 응답하세요.

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{"value": "읽은 값(단위 제외, 숫자/문자 그대로) 또는 null"}"""


def _encode_image(photo_path: str | Path) -> tuple[str, str]:
    path = Path(photo_path)
    if not path.exists():
        raise FileNotFoundError(f"사진 파일을 찾을 수 없습니다: {path}")

    media_type = _SUPPORTED_MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        media_type = mimetypes.guess_type(path.name)[0]
    if media_type is None or not media_type.startswith("image/"):
        raise ValueError(f"지원하지 않는 이미지 형식입니다: {path.suffix}")

    image_b64 = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return image_b64, media_type


def _call_claude(image_b64: str, media_type: str, prompt: str, model: str | None = None) -> str:
    """실제 Claude API 호출. 분리해두면 테스트할 때 이 함수만 mocking하면 된다."""
    client = Anthropic(api_key=get_api_key())
    response = client.messages.create(
        model=model or get_model_name(),
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답에서 JSON을 파싱하지 못했습니다: {e}\n원본 응답: {raw_text}") from e

    if not isinstance(data, dict):
        raise ValueError(f"JSON 객체가 아닌 응답을 받았습니다: {raw_text}")
    return data


def analyze_finding(photo_path: str | Path, description: str, model: str | None = None) -> dict:
    """사진 + 지도자 설명으로 지적사항 제목/내용/관련법령을 추천한다."""
    image_b64, media_type = _encode_image(photo_path)
    prompt = FINDING_PROMPT.format(description=description or "(설명 없음)")
    raw_response = _call_claude(image_b64, media_type, prompt, model=model)
    data = _parse_json_object(raw_response)
    return {
        "title": (data.get("title") or "")[:30],
        "content": (data.get("content") or "")[:110],
        "law_citation": data.get("law_citation") or "",
    }


def count_people(photo_path: str | Path, model: str | None = None) -> int | None:
    """사진 속 인원 수를 센다. 판단이 어려우면 None(=UI에서 '읽지 못함' 표시)을 반환한다."""
    image_b64, media_type = _encode_image(photo_path)
    raw_response = _call_claude(image_b64, media_type, PEOPLE_COUNT_PROMPT, model=model)
    data = _parse_json_object(raw_response)
    count = data.get("count")
    if count in (None, "null", ""):
        return None
    try:
        return int(count)
    except (TypeError, ValueError):
        return None


def read_measurement_value(photo_path: str | Path, instrument_type: str, model: str | None = None) -> str | None:
    """계측장비 디스플레이 사진에서 측정값을 읽는다. 판단이 어려우면 None을 반환한다."""
    image_b64, media_type = _encode_image(photo_path)
    prompt = MEASUREMENT_READ_PROMPT.format(instrument_type=instrument_type)
    raw_response = _call_claude(image_b64, media_type, prompt, model=model)
    data = _parse_json_object(raw_response)
    value = data.get("value")
    if value in (None, "null", ""):
        return None
    return str(value)
