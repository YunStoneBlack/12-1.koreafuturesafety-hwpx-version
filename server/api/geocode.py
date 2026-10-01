"""현장 주소 → 좌표(카카오 로컬 API, 2026-10-01) — 자동 배치·일정 변경의 거리 기준 묶기용. 키는 `.env.server` KAKAO_REST_API_KEY.

- 현장 주소는 "…41-26 고모리 일원", "(부곡동)465-4 수소충전소 구축공사현장"처럼 끝에 설명이 붙어 정확한 주소 검색이 안 된다 →
  괄호를 살린 것·지운 것 두 가지로, 뒤에서부터 단어를 하나씩 빼며 주소 검색 → 그래도 없으면 키워드 검색. 가장 구체적인(단어를 많이 쓴) 결과.
- 시·군 중심밖에 못 찾으면(단어 2개 이하) 좌표를 믿지 않는다(precise=False) — 거리 대신 예전처럼 시·군 기준으로 묶는다.
- 결과는 `site_geo`(alembic 0011)에 저장, 쓰는 주소(지도 방문 주소, 없으면 현장 주소)가 바뀌면 다시 찾는다. 키가 없거나 카카오가 안 되면 조용히 건너뛴다.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import urllib.parse
import urllib.request

from sqlalchemy.orm import Session

from core.models_db import Site
from core.models_web import SiteContact, SiteGeo

_URL_ADDR = "https://dapi.kakao.com/v2/local/search/address.json"
_URL_KEYWORD = "https://dapi.kakao.com/v2/local/search/keyword.json"


def _key() -> str:
    return os.environ.get("KAKAO_REST_API_KEY", "").strip()


def _search(url: str, query: str) -> list[dict]:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode({'query': query})}", headers={"Authorization": f"KakaoAK {_key()}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8")).get("documents", [])


def geocode(address: str) -> tuple[float, float, int, str] | None:
    """(위도, 경도, 맞은 단어 수, 찾은 주소) — 못 찾으면 None. 네트워크·키 오류는 예외."""
    variants = []
    for a in (re.sub(r"[()]", " ", address), re.sub(r"\(.*?\)", " ", address)):  # 괄호 살림 → 지움
        a = re.sub(r"\s+", " ", a).strip()
        if a and a not in variants:
            variants.append(a)
    best = None
    for url in (_URL_ADDR, _URL_KEYWORD):
        for a in variants:
            toks = a.split()
            for n in range(len(toks), 1, -1):
                if best and n <= best[2]:
                    break
                docs = _search(url, " ".join(toks[:n]))
                if docs:
                    d = docs[0]
                    best = (float(d["y"]), float(d["x"]), n, d.get("address_name") or d.get("place_name", ""))
                    break
        if best and best[2] > 2:
            break  # 주소 검색으로 충분히 구체적이면 키워드 검색은 안 함
    return best


def site_address(site: Site, visit_address: str | None) -> str:
    return (visit_address or site.address or "").strip()


def site_coords(db: Session, sites: dict[int, Site]) -> dict[int, tuple[float, float]]:
    """현장 → (위도, 경도) — 믿을 만한 것만(precise). 없거나 주소가 바뀐 현장은 지금 찾아서 저장한다(키 없으면 저장된 것만)."""
    if not sites:
        return {}
    va = dict(db.query(SiteContact.site_id, SiteContact.visit_address).filter(SiteContact.site_id.in_(list(sites))))
    rows = {g.site_id: g for g in db.query(SiteGeo).filter(SiteGeo.site_id.in_(list(sites)))}
    changed = False
    for sid, site in sites.items():
        addr = site_address(site, va.get(sid))
        g = rows.get(sid)
        if g is not None and g.address == addr:
            continue
        if not _key() or not addr:
            continue
        try:
            found = geocode(addr)
        except Exception:  # noqa: BLE001 — 카카오가 안 되면 이번엔 시·군 기준으로(다음에 다시 시도)
            continue
        if g is None:
            g = SiteGeo(site_id=sid)
            db.add(g)
            rows[sid] = g
        g.address = addr
        g.lat, g.lng = (found[0], found[1]) if found else (None, None)
        g.precise = bool(found and found[2] > 2)
        g.found = found[3] if found else ""
        g.updated_at = datetime.datetime.now()
        changed = True
    if changed:
        db.commit()
    return {sid: (g.lat, g.lng) for sid, g in rows.items() if g.precise and g.lat is not None}


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """두 좌표 사이 직선거리(km)."""
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))
