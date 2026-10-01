"""현장 주소 → 좌표(카카오 로컬 API, 2026-10-01) — 자동 배치·일정 변경의 거리 기준 묶기용. 키는 `.env.server` KAKAO_REST_API_KEY.

- 현장 주소는 "…41-26 고모리 일원", "(부곡동)465-4 수소충전소 구축공사현장"처럼 끝에 설명이 붙어 정확한 주소 검색이 안 된다 →
  괄호를 살린 것·지운 것 두 가지로, 뒤에서부터 단어를 하나씩 빼며 주소 검색 → 그래도 없으면 키워드 검색. 가장 구체적인(단어를 많이 쓴) 결과.
- 시·군 중심밖에 못 찾으면(단어 2개 이하) 좌표를 믿지 않는다(precise=False) — 거리 대신 예전처럼 시·군 기준으로 묶는다.
- 결과는 `site_geo`(alembic 0011)에 저장, 쓰는 주소(지도 방문 주소, 없으면 현장 주소)가 바뀌면 다시 찾는다. 키가 없거나 카카오가 안 되면 조용히 건너뛴다.
- 두 현장 사이 **도로 거리**(카카오모빌리티 자동차 길찾기, 같은 키) — `RoadDistance`: 필요한 쌍만 물어서 `site_distance`(alembic 0012)에 저장,
  좌표가 바뀌면 다시 묻고, 길찾기가 안 되면 직선거리로 대신(2026-10-01 사용자 "네비 기준 거리" — 시간은 교통에 따라 달라 안 씀).
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
from core.models_web import SiteContact, SiteDistance, SiteGeo

_URL_ADDR = "https://dapi.kakao.com/v2/local/search/address.json"
_URL_KEYWORD = "https://dapi.kakao.com/v2/local/search/keyword.json"
_URL_ROUTE = "https://apis-navi.kakaomobility.com/v1/directions"


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


def road_km(a: tuple[float, float], b: tuple[float, float]) -> float | None:
    """자동차 길찾기(추천 경로) 거리 km — 길이 없거나 실패하면 None."""
    q = urllib.parse.urlencode({"origin": f"{a[1]},{a[0]}", "destination": f"{b[1]},{b[0]}", "priority": "RECOMMEND"})
    req = urllib.request.Request(f"{_URL_ROUTE}?{q}", headers={"Authorization": f"KakaoAK {_key()}"})
    with urllib.request.urlopen(req, timeout=8) as r:
        route = json.loads(r.read().decode("utf-8"))["routes"][0]
    return route["summary"]["distance"] / 1000 if route.get("result_code") == 0 else None


class RoadDistance:
    """두 현장 사이 도로 거리(km) — 저장된 값 → 없거나 좌표가 바뀌었으면 길찾기 → 실패하면 직선거리. 좌표 모르면 None.
    한 번의 배치·창 열기 동안 묻는 건 같은 요원 현장끼리 정도라 많지 않다. 새로 물은 건 save()로 저장."""

    def __init__(self, db: Session, coords: dict[int, tuple[float, float]]):
        self.db, self.coords = db, coords
        ids = list(coords)
        self.rows = {(r.site_a, r.site_b): r for r in db.query(SiteDistance).filter(
            SiteDistance.site_a.in_(ids), SiteDistance.site_b.in_(ids))} if ids else {}
        self.memo: dict[tuple[int, int], float | None] = {}
        self.dirty = False
        self.failed = False  # 한 번 실패(키·한도·네트워크)하면 이번엔 더 묻지 않고 직선거리

    def __call__(self, x: int, y: int) -> float | None:
        if x == y:
            return 0.0
        a, b = (x, y) if x < y else (y, x)
        if (a, b) in self.memo:
            return self.memo[(a, b)]
        ca, cb = self.coords.get(a), self.coords.get(b)
        if not ca or not cb:
            self.memo[(a, b)] = None
            return None
        key = f"{ca[0]:.6f},{ca[1]:.6f}|{cb[0]:.6f},{cb[1]:.6f}"
        row = self.rows.get((a, b))
        if row is None or row.coords != key:
            found = None
            if _key() and not self.failed:
                try:
                    found = road_km(ca, cb)
                except Exception:  # noqa: BLE001 — 이번엔 직선거리로(다음에 다시 물음)
                    self.failed = True
            if found is not None or (_key() and not self.failed):
                if row is None:
                    row = SiteDistance(site_a=a, site_b=b)
                    self.db.add(row)
                    self.rows[(a, b)] = row
                row.coords, row.road_km, row.updated_at = key, found, datetime.datetime.now()
                self.dirty = True
        value = row.road_km if row is not None and row.coords == key and row.road_km is not None else km(ca, cb)
        self.memo[(a, b)] = value
        return value

    def save(self) -> None:
        if self.dirty:
            self.db.commit()
            self.dirty = False
