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
- likelihood(가능성)와 severity(중대성)는 아래 기준으로 1~3 중 하나를 고르세요.
  가능성(빈도): 1=발생 가능성이 거의 없음 / 2=발생 가능성 있음 / 3=일반적 또는 반복적으로 발생
  중대성(강도): 1=아차사고·무상해·응급조치를 요하는 상해 또는 질병 초래 /
  2=의학적인 치료를 요하는 상해 또는 장애를 일으키는 질병 /
  3=사망·중대한 상해 또는 생명을 위협하는 직업성질병 초래 위험

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{{
  "title": "지적사항 제목 (30자 이내)",
  "content": "지적사항 및 개선대책 (110자 이내)",
  "law_citation": "관련 법령 조항 (확신 없으면 빈 문자열)",
  "likelihood": "가능성 1~3 중 하나(정수)",
  "severity": "중대성 1~3 중 하나(정수)"
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

{{"value": "읽은 값(단위 제외, 숫자/문자 그대로) 또는 null"}}"""

PROCESS_HAZARD_PROMPT = """당신은 건설재해예방 기술지도를 보조하는 전문가입니다.
첨부된 사진은 "{process_name}" 공정 현장 사진입니다. 이 공정에서 실제로 확인되거나 이
공정에서 통상적으로 발생하는 유해·위험요인과 그에 대한 예방대책을 분석하세요.

중요한 규칙:
- 사진에서 실제로 확인되는 위험요인, 또는 이 공정에서 산업안전보건 기준상 통상적으로
  요구되는 위험요인만 작성하세요. 근거 없이 지어내지 마세요.
- 사진 화질이 나쁘거나 공정명이 모호해 판단이 아예 불가능하면 items를 빈 배열로 응답하세요.
- 유해·위험요인(hazard)은 사진과 공정에서 실제로 확인되는 만큼만 작성하세요 — 개수를
  채우려고 억지로 늘리지 마세요. 2~3개만 확인되면 2~3개만 적는 게 맞습니다. 너무 많이
  찾아지더라도 중요도 순으로 최대 5개까지만 추리세요. 같거나 거의 같은 내용을 표현만
  바꿔 반복하지 마세요 — 각 hazard는 반드시 서로 구별되는 내용이어야 합니다. 서로 다른
  위험 상황을 접속사("및", "그리고" 등)로 이어붙여 한 hazard 안에 여러 상황을 욱여넣지
  마세요 — 그런 경우 별도의 hazard 항목으로 나누세요.
- preventions는 반드시 JSON 배열이며, 그 위험요인에 필요한 조치가 여러 개면 배열
  원소도 여러 개여야 합니다 — "부품 정리, 점검 실시, 표지판 설치"처럼 쉼표나 접속사로
  이어붙여 배열 원소 1개에 다 몰아넣지 마세요. 서로 다른 조치는 각각 별도의 배열
  원소(preventions[0], preventions[1], ...)로 나누세요. 위험성 수준(risk)은 그
  위험요인 전체에 대해 1개만 고르세요.
- hazard 문장과 각 prevention 배열 원소는 각각 하나의 완결된 조치만 담아 50자
  이내로 간결하게 작성하세요.
- risk(위험성 수준)는 아래 기준으로 "상"/"중"/"하" 중 하나만 고르세요.
  상=중대재해로 이어질 수 있는 고위험 / 중=상해를 유발할 수 있는 위험 / 하=경미한 위험

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{{
  "items": [
    {{"hazard": "유해·위험요인 (50자 이내)", "preventions": ["예방대책1 (50자 이내)", "예방대책2 (50자 이내)"], "risk": "상|중|하"}}
  ]
}}"""

_GAS_METER_TYPE = "가스농도측정기"

GAS_METER_READ_PROMPT = """첨부된 사진은 4종 복합가스측정기의 디스플레이 사진입니다.
화면에는 보통 4개의 측정값이 동시에 표시됩니다:
- EX: 가연성가스 농도, %LEL 단위
- O2: 산소 농도, %VOL 단위
- H2S: 황화수소 농도, ppm 단위
- CO: 일산화탄소 농도, ppm 단위

화면에서 이 4개 값의 숫자 부분만 각각 읽어주세요(단위·기호 제외, 숫자만). 화면이 흐리거나
꺼져 있거나 특정 값을 읽을 수 없으면 그 값만 null로 응답하세요. 절대 추측하지 마세요.

반드시 아래 JSON 스키마와 동일한 형식의 JSON 객체만 응답하세요. 다른 설명 텍스트는 포함하지 마세요.

{{"ex": "숫자 또는 null", "o2": "숫자 또는 null", "h2s": "숫자 또는 null", "co": "숫자 또는 null"}}"""

# (하한, 상한) — None이면 그쪽 경계 없음. 지도자가 실제 장비 화면을 보며 불러준 정상범위.
_GAS_METER_RANGES: dict[str, tuple[float | None, float | None]] = {
    "ex": (None, 10),  # 가연성가스: 10%LEL 이하
    "o2": (19.5, 23.5),  # 산소: 19.5~23.5%
    "h2s": (None, 10),  # 황화수소: 10ppm 이하
    "co": (None, 50),  # 일산화탄소: 50ppm 이하
}


def _read_gas_meter_value(image_b64: str, media_type: str, model: str | None) -> str | None:
    """4종 복합가스측정기는 화면 하나에 EX/O2/H2S/CO 네 값이 동시에 표시돼 일반
    단일값 프롬프트로는 인식이 잘 안 됐다(실측 확인). 네 값을 각각 읽어 전부 정상범위
    안이면 "정상범위", 하나라도 벗어나면 "정상범위 초과"를 반환한다 — 네 값 중 하나라도
    못 읽으면(화면 일부가 안 보이는 등) 안전 판단을 잘못 내릴 수 있으므로 절대 추측하지
    않고 None을 반환한다(다른 계측기와 동일하게 "직접 입력해주세요" 안내로 이어짐).
    """
    raw_response = _call_claude(image_b64, media_type, GAS_METER_READ_PROMPT, model=model)
    data = _parse_json_object(raw_response)

    readings: dict[str, float] = {}
    for key in ("ex", "o2", "h2s", "co"):
        raw = data.get(key)
        if raw in (None, "null", ""):
            continue
        try:
            readings[key] = float(str(raw).strip())
        except ValueError:
            continue

    if len(readings) < 4:
        return None

    all_normal = all(
        (low is None or value >= low) and (high is None or value <= high)
        for key, value in readings.items()
        for low, high in [_GAS_METER_RANGES[key]]
    )
    return "정상범위" if all_normal else "정상범위 초과"


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


def _call_claude(
    image_b64: str, media_type: str, prompt: str, model: str | None = None, max_tokens: int = 1024
) -> str:
    """실제 Claude API 호출. 분리해두면 테스트할 때 이 함수만 mocking하면 된다."""
    client = Anthropic(api_key=get_api_key())
    response = client.messages.create(
        model=model or get_model_name(),
        max_tokens=max_tokens,
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


def _clamp_1_3(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return min(3, max(1, n))


def analyze_finding(photo_path: str | Path, description: str, model: str | None = None) -> dict:
    """사진 + 지도자 설명으로 지적사항 제목/내용/관련법령/위험성평가(가능성·중대성)를 추천한다."""
    image_b64, media_type = _encode_image(photo_path)
    prompt = FINDING_PROMPT.format(description=description or "(설명 없음)")
    raw_response = _call_claude(image_b64, media_type, prompt, model=model)
    data = _parse_json_object(raw_response)
    return {
        "title": (data.get("title") or "")[:30],
        "content": (data.get("content") or "")[:110],
        "law_citation": data.get("law_citation") or "",
        "likelihood": _clamp_1_3(data.get("likelihood")),
        "severity": _clamp_1_3(data.get("severity")),
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


def analyze_process_hazards(photo_path: str | Path, process_name: str, model: str | None = None) -> list[dict]:
    """공정 사진 + 공정명으로 유해·위험요인(항목)마다 예방대책 여러 건 + 위험성 1개를
    추천한다(7번 현재진행공정/9번 향후진행공정 공용 — 두 섹션 모두 같은 표 구조라
    프롬프트도 공용). 반환값의 각 항목은 `{"hazard": str, "prevention": str, "risk_level": str}`
    — `prevention`은 그 유해요인에 딸린 예방대책 여러 줄을 "\\n"으로 이어붙인 문자열이다
    (표 렌더링 시 줄 단위로 다시 쪼갠다, `core/report_builder_hwpx_fields.py` 참고).

    최대 5개까지만 반환한다(실사용 중 AI가 같은 위험요인을 문구만 바꿔 반복해서 15개까지
    내놓은 사례가 있어, 사용자 요청으로 상한을 뒀다) — hazard 텍스트가 동일하거나 거의
    같은 항목은 먼저 하나로 합쳐 버린 뒤에 5개로 자른다. 순서를 반대로 하면(자르고 나서
    중복 제거) 반복된 항목 때문에 정작 서로 다른 위험요인이 잘려나갈 수 있다.

    항목 개수가 많다 보니(최대 5개, 각 여러 예방대책) Claude가 드물게 JSON 문법을 살짝
    틀리는 경우가 있었다(실사용 중 콤마 하나 빠뜨림 확인) — 사람이 매번 "AI로 작성"을
    다시 눌러야 하는 번거로움 없이, 파싱에 실패하면 같은 사진으로 최대 2번까지 조용히
    다시 요청한다(사용자 요청). 재시도까지 다 실패하면 그제서야 예외를 올려 위쪽
    (`_ProcessSlot._on_ai_error`)에서 실패 안내를 띄운다.
    """
    image_b64, media_type = _encode_image(photo_path)
    prompt = PROCESS_HAZARD_PROMPT.format(process_name=process_name or "(공정명 미입력)")

    data = None
    last_error: ValueError | None = None
    for _attempt in range(3):
        # 유해요인 최대 5개 × 예방대책 여러 건이라 다른 analyze_* 함수보다 응답이 훨씬
        # 길다 — 기본값(1024)으로는 답변이 중간에 잘려 JSON 자체가 깨지는 경우가 실사용
        # 중 확인됐다(재시도로도 안 고쳐짐 — 같은 프롬프트면 매번 비슷한 길이에서 잘리므로).
        raw_response = _call_claude(image_b64, media_type, prompt, model=model, max_tokens=4096)
        try:
            data = _parse_json_object(raw_response)
            break
        except ValueError as e:
            last_error = e
    if data is None:
        raise last_error
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return []

    items: list[dict] = []
    seen_hazards: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        hazard = str(raw_item.get("hazard") or "").strip()
        if not hazard:
            continue
        dedup_key = re.sub(r"\s+", "", hazard)
        if dedup_key in seen_hazards:
            continue

        raw_preventions = raw_item.get("preventions")
        if not isinstance(raw_preventions, list):
            single = raw_item.get("prevention")
            raw_preventions = [single] if single else []
        preventions = [str(p).strip()[:80] for p in raw_preventions if str(p or "").strip()]

        risk = raw_item.get("risk") or ""
        if risk not in ("상", "중", "하"):
            risk = ""
        if not preventions and not risk:
            continue

        seen_hazards.add(dedup_key)
        items.append({"hazard": hazard[:80], "prevention": "\n".join(preventions), "risk_level": risk})
    return items[:5]


def read_measurement_value(photo_path: str | Path, instrument_type: str, model: str | None = None) -> str | None:
    """계측장비 디스플레이 사진에서 측정값을 읽는다. 판단이 어려우면 None을 반환한다.

    한때 '조도계'는 화면 숫자 그대로가 아니라 1000을 곱해야 실제 lux값이라고 보고
    파이썬에서 별도로 ×1000을 했었다(AI에겐 화면 숫자만 읽게 하고 계산은 코드가 맡는
    구조) — 그런데 실제 조도계 화면에 뜨는 "X1000" 표시를 AI가 이미 같이 읽어서 그 배율을
    반영한 최종값(예: 21300)을 돌려주고 있었다는 게 실측으로 확인됐다. 그 상태에서 코드가
    또 ×1000을 하면서 값이 100만 단위로 부풀려지는 이중 곱셈 버그가 있었다(사용자 확인,
    2026-09-11) — 조도계도 다른 계측기와 동일하게 AI가 돌려준 값을 그대로 쓰도록 되돌렸다.
    """
    image_b64, media_type = _encode_image(photo_path)
    if instrument_type == _GAS_METER_TYPE:
        return _read_gas_meter_value(image_b64, media_type, model)
    prompt = MEASUREMENT_READ_PROMPT.format(instrument_type=instrument_type)
    raw_response = _call_claude(image_b64, media_type, prompt, model=model)
    data = _parse_json_object(raw_response)
    value = data.get("value")
    if value in (None, "null", ""):
        return None
    return str(value)
