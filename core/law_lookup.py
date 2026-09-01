"""국가법령정보센터 Open API로 법령 조문을 가져와 로컬에 캐싱하는 모듈.

동작 방식: "산업안전보건기준에 관한 규칙" 같은 법령 하나를 통째로 한 번 가져와서
LawArticleCache 테이블에 저장해두고, 이후 검색/필터는 전부 로컬 캐시에서 처리한다
(매번 API를 두드리지 않고, 실제 화면에서 본 "조문번호/키워드로 검색" UX를 그대로 구현).

주의: open.law.go.kr에서 발급받는 OC 키가 있어야 동작한다 (AI 관리 > 법령 API 설정).
아직 실제 키로 검증하지 못했으므로, 응답 스키마가 문서와 다를 경우를 대비해 파싱을
방어적으로 작성했다 — 배포 전 실제 키로 한 번 확인이 필요하다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from core import config
from core.db import SessionLocal
from core.models_db import LawArticleCache

LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"

DEFAULT_LAW_NAME = "산업안전보건기준에 관한 규칙"


class LawApiError(RuntimeError):
    pass


def _get_json(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(f"{url}?{query}", timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        raise LawApiError(f"국가법령정보센터 API 호출에 실패했습니다: {e}") from e


def _find_law_mst(law_name: str, oc: str) -> str:
    data = _get_json(LAW_SEARCH_URL, {"OC": oc, "target": "law", "type": "JSON", "query": law_name})
    laws = data.get("LawSearch", {}).get("law", [])
    if isinstance(laws, dict):
        laws = [laws]
    for law in laws:
        if law.get("법령명한글", "").strip() == law_name:
            return law.get("법령일련번호")
    if laws:
        return laws[0].get("법령일련번호")
    raise LawApiError(f"'{law_name}' 법령을 찾지 못했습니다.")


def refresh_law_cache(law_name: str = DEFAULT_LAW_NAME) -> int:
    """법령 하나의 전체 조문을 API로 가져와 LawArticleCache에 저장(갱신)한다. 저장된 조문 수를 반환.

    실제 응답을 받아보니 "조문단위" 배열에는 실제 조문 말고도 편·장·절 제목이 "조문여부":
    "전문"인 항목으로 섞여 들어오고(제목 없이 번호만 있어 그대로 두면 "제1조()" 같은 가짜
    항목이 생김), 항(①②...)이 있는 조문은 본문이 "조문내용"이 아니라 "항" 배열에 나뉘어
    들어온다(그대로 두면 본문이 통째로 비어서 캐시에서 빠짐). 그래서:
    - "조문여부"가 "조문"인 것만 실제 법 조항으로 취급한다.
    - "항" 배열이 있으면 조문 머리글(조문내용) 뒤에 각 항 내용을 이어붙여 본문을 완성한다.
    - "조문가지번호"(예: 제4조의2)가 있으면 article_no에 "의N"까지 포함해 "제4조"와 "제4조의2"가
      같은 번호로 겹치지 않게 한다.
    """
    oc = config.get_law_api_oc()
    if not oc:
        raise LawApiError("국가법령정보센터 API 키(OC)가 설정되어 있지 않습니다. 'AI 관리' 화면에서 등록하세요.")

    mst = _find_law_mst(law_name, oc)
    data = _get_json(LAW_SERVICE_URL, {"OC": oc, "target": "law", "type": "JSON", "MST": mst})

    raw_articles = data.get("법령", {}).get("조문", {}).get("조문단위", [])
    if isinstance(raw_articles, dict):
        raw_articles = [raw_articles]

    saved = 0
    with SessionLocal() as session:
        session.query(LawArticleCache).filter_by(law_name=law_name).delete()
        for article in raw_articles:
            if article.get("조문여부") != "조문":
                continue  # 편/장/절 제목 등 구조적 헤더는 실제 조문이 아니므로 제외

            base_no = (article.get("조문번호") or "").strip()
            branch_no = (article.get("조문가지번호") or "").strip()
            if not base_no:
                continue
            article_no = f"{base_no}조" + (f"의{branch_no}" if branch_no else "")
            title = (article.get("조문제목") or "").strip()

            header = (article.get("조문내용") or "").strip()
            clauses = article.get("항") or []
            if isinstance(clauses, dict):
                clauses = [clauses]
            clause_lines = [c.get("항내용", "").strip() for c in clauses if c.get("항내용", "").strip()]
            content = "\n".join([header] + clause_lines) if clause_lines else header
            if not content:
                continue

            session.add(
                LawArticleCache(law_name=law_name, article_no=article_no, title=title, content=content)
            )
            saved += 1
        session.commit()
    return saved


def search_cached_articles(keyword: str, law_name: str = DEFAULT_LAW_NAME) -> list[LawArticleCache]:
    """로컬 캐시에서 조문번호 또는 제목/본문 키워드로 검색한다."""
    with SessionLocal() as session:
        query = session.query(LawArticleCache).filter_by(law_name=law_name)
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                (LawArticleCache.article_no.like(like))
                | (LawArticleCache.title.like(like))
                | (LawArticleCache.content.like(like))
            )
        # 검색어 없이 전체를 볼 때도 법령 조문(현재 690개, 666조까지) 전부가 보여야 하므로
        # 넉넉하게 잡는다 — 예전 50건 제한 때문에 뒤쪽 조문이 안 보이는 문제가 있었다.
        return query.order_by(LawArticleCache.id).limit(1000).all()
