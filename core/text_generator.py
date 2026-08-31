"""지적사항 목록을 근거로 '기타 특이사항' 종합 코멘트를 생성하는 모듈."""

from __future__ import annotations

from anthropic import Anthropic

from core.config import get_api_key, get_model_name

SPECIAL_NOTE_PROMPT = """당신은 건설재해예방 기술지도 보고서를 작성하는 전문가입니다.
아래 지적사항 목록을 바탕으로 오늘 현장 점검에 대한 종합 코멘트를 작성하세요.

지적사항 목록:
{findings_text}

반드시 160자 이내의 한국어 문장으로만 응답하세요. JSON이나 다른 설명 없이 코멘트 본문만 출력하세요."""


def generate_special_note(findings: list[dict], model: str | None = None) -> str:
    """지적사항(title/content) 목록으로 160자 이내 종합 코멘트를 생성한다."""
    if not findings:
        findings_text = "(지적사항 없음 — 전반적인 현장 상황에 대해 간단히 코멘트하세요)"
    else:
        findings_text = "\n".join(
            f"- {f.get('title', '')}: {f.get('content', '')}" for f in findings if f.get("title") or f.get("content")
        )

    client = Anthropic(api_key=get_api_key())
    response = client.messages.create(
        model=model or get_model_name(),
        max_tokens=300,
        messages=[{"role": "user", "content": SPECIAL_NOTE_PROMPT.format(findings_text=findings_text)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text[:160]
