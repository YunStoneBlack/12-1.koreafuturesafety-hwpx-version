"""지적사항 내용을 바탕으로 제공자료 라이브러리에서 관련 자료를 추천하는 모듈.

라이브러리 규모가 아직 작고(사용자가 직접 등록), 별도 임베딩 인프라를 둘 정도는 아니라서
제목/태그 키워드 겹침 기반의 단순한 점수 매기기로 충분하다. 나중에 라이브러리가 커지면
임베딩 기반 검색으로 교체할 수 있다.
"""

from __future__ import annotations

import re

from core.models_db import MaterialLibrary


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text))


def recommend_materials(
    findings: list[dict], library_items: list[MaterialLibrary], limit: int = 4
) -> list[MaterialLibrary]:
    """지적사항(title/content) 키워드와 자료명/태그가 겹치는 순서로 자료를 추천한다."""
    query_tokens: set[str] = set()
    for f in findings:
        query_tokens |= _tokenize(f.get("title", ""))
        query_tokens |= _tokenize(f.get("content", ""))

    if not query_tokens:
        return library_items[:limit]

    scored: list[tuple[int, MaterialLibrary]] = []
    for item in library_items:
        item_tokens = _tokenize(item.title) | _tokenize(item.tags)
        score = len(query_tokens & item_tokens)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]
