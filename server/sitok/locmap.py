"""시특법 보고서 위치도(2026-10-11) — 처음 맡는 시설물은 틀의 지도가 다른 시설물 것이라 주소로 새로 만든다.
주소 → 좌표는 카카오 로컬(server/api/geocode.py), 지도 그림은 OpenStreetMap 타일 3×3을 이어 붙이고 가운데에 표시(출처 글 넣음).
같은 주소면 시설물 폴더에 만든 그림을 다시 씀."""
from __future__ import annotations

import hashlib
import io
import math
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TILE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
UA = "KFSC-sitok-report/1.0"  # OSM 타일 이용 규칙 — 앱 이름
ZOOM = 16
FONT = "C:/Windows/Fonts/malgunbd.ttf"


def _tile_xy(lat: float, lng: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lng + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _fetch(z: int, x: int, y: int) -> Image.Image:
    req = urllib.request.Request(TILE.format(z=z, x=x, y=y), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def render(lat: float, lng: float, name: str, w: int = 1200, h: int = 900, z: int = ZOOM) -> bytes:
    fx, fy = _tile_xy(lat, lng, z)
    x0, y0 = fx * 256 - w / 2, fy * 256 - h / 2  # 그림 왼쪽 위(전체 픽셀 좌표)
    img = Image.new("RGB", (w, h), "white")
    for tx in range(int(x0 // 256), int((x0 + w) // 256) + 1):
        for ty in range(int(y0 // 256), int((y0 + h) // 256) + 1):
            img.paste(_fetch(z, tx, ty), (int(tx * 256 - x0), int(ty * 256 - y0)))
    d = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    d.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), outline=(220, 30, 60), width=6)  # 대상 시설물 표시
    d.polygon([(cx, cy), (cx - 16, cy - 40), (cx + 16, cy - 40)], fill=(220, 30, 60))
    d.ellipse((cx - 22, cy - 70, cx + 22, cy - 26), fill=(220, 30, 60))
    d.ellipse((cx - 8, cy - 56, cx + 8, cy - 40), fill="white")
    try:
        f = ImageFont.truetype(FONT, 34)
        small = ImageFont.truetype(FONT, 18)
    except OSError:
        f = small = ImageFont.load_default()
    if name:
        tw = d.textlength(name, font=f)
        bx, by = cx - tw / 2 - 16, cy + 80
        d.rounded_rectangle((bx, by, bx + tw + 32, by + 54), radius=10, fill=(220, 30, 60))
        d.text((bx + 16, by + 7), name, font=f, fill="white")
    d.text((w - 260, h - 28), "© OpenStreetMap contributors", font=small, fill=(60, 60, 60))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


UPLOADED = "위치도_올린것.jpg"  # 점검자가 밖에서 만들어 올린 위치도(옹벽, 10/21 형 방법1) — 있으면 이게 우선


def map_for(address: str, name: str, folder: Path, latlng: tuple[float, float] | None = None) -> Path | None:
    """위치도 그림 파일(없으면 만듦) — latlng(점검자가 핀을 끌어 둔 좌표, 10/21 형 방법2)가 있으면 그 자리, 없으면 주소를 좌표로.
    좌표를 못 찾거나 지도를 못 받으면 None."""
    from server.api import geocode

    if latlng:
        key = f"{latlng[0]:.6f},{latlng[1]:.6f}"
    elif address:
        key = address
    else:
        return None
    p = folder / f"위치도_{hashlib.md5((key + name).encode()).hexdigest()[:8]}.jpg"
    if p.exists():
        return p
    if latlng:
        lat, lng = latlng
    else:
        g = geocode.geocode(address)
        if not g:
            return None
        lat, lng = g[0], g[1]
    try:
        data = render(lat, lng, name)
    except Exception:  # noqa: BLE001 — 지도 서버가 안 되면 틀 그림 그대로
        return None
    folder.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def pin_of(f) -> tuple[float, float] | None:
    """시설물에 저장한 핀 좌표(ledger.wall.lat/lng — 옹벽처럼 주소와 자리가 다른 시설물)."""
    w = (f.ledger or {}).get("wall") or {}
    try:
        return (float(w["lat"]), float(w["lng"])) if w.get("lat") and w.get("lng") else None
    except (TypeError, ValueError):
        return None


def facility_map(f, folder: Path) -> Path | None:
    """보고서에 넣을 위치도 — 올린 그림 > 핀 좌표 지도 > 주소 지도."""
    up = folder / UPLOADED
    if up.exists():
        return up
    return map_for(f.address or "", f.name, folder, pin_of(f))
