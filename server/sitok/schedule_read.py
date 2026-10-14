"""구조 일람표 읽기(2026-10-14 형 2차 피드백 ④) — 시설물 도면 "구조 일람표"(PDF·그림)에서 AI에 보낼 그림을 고른다.

형이 보낸 실제 도면 두 종류:
① 일람표 쪽이 따로 있는 CAD PDF(글자 있음) — "일람표"·"SCHEDULE" 글자가 있는 쪽만 골라, 쪽 전체 그림 + 4등분 타일(각각 긴 변 ≤1568px)로 크게.
② 평면도 쪽 구석에 작은 일람표가 있는 CAD/스캔 PDF(글자 없음) — 1단계: 모든 쪽을 작게(800px, 쪽 번호 표시) 보여 "일람표가 있는 쪽과 그 위치(%)"를 AI에 묻고,
   2단계: 그 부분만 잘라 크게(긴 변 1568px, 세로로 길면 위·아래로 나눔) 다시 읽음.
그림 파일(jpg·png)은 ① 처럼 전체 + 4등분.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

SIDE = 1568  # Claude가 줄이지 않고 보는 긴 변
MAX_PAGES = 4  # 일람표 쪽으로 보낼 최대 쪽 수
KEYS = ("일람표", "일 람 표", "SCHEDULE", "Schedule", "LIST", "부재리스트")

LOCATE_PROMPT = """아래는 건축 구조도면 PDF의 쪽들을 작게 줄인 그림입니다(왼쪽 위에 쪽 번호). 구조 일람표(기둥·보·슬래브·벽체 부호와 단면 크기가 적힌 표 — "부재일람표"·"기둥 일람표"·"보 일람표" 등)가 있는 쪽을 찾아 주세요.
평면도 쪽 구석에 작은 표로 들어 있기도 합니다. 표가 있는 쪽마다 그 표가 차지하는 영역을 쪽의 가로·세로 백분율(0~100, 왼쪽 위가 0,0)로 적어 주세요. 여유 있게 잡아도 됩니다.
JSON 배열만: [{"page": 1, "x0": 8, "y0": 10, "x1": 28, "y1": 95, "what": "콘크리트 부재일람표"}, …]. 없으면 []."""


def _jpeg(im: Image.Image, side: int = SIDE, quality: int = 88) -> bytes:
    im = im.convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _render(page: pymupdf.Page, clip: pymupdf.Rect | None, side: int) -> Image.Image:
    rect = clip or page.rect
    zoom = side / max(rect.width, rect.height)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _tiles(im: Image.Image) -> list[bytes]:
    """전체 + 4등분(겹침 6%)."""
    w, h = im.size
    out = [_jpeg(im)]
    ox, oy = int(w * 0.06), int(h * 0.06)
    for (x0, y0, x1, y1) in ((0, 0, w // 2 + ox, h // 2 + oy), (w // 2 - ox, 0, w, h // 2 + oy), (0, h // 2 - oy, w // 2 + ox, h), (w // 2 - ox, h // 2 - oy, w, h)):
        out.append(_jpeg(im.crop((x0, y0, x1, y1))))
    return out


def _split_tall(im: Image.Image) -> list[Image.Image]:
    """세로로 긴 조각(일람표가 길게 내려감)은 위·아래로 나눠 글씨가 작아지지 않게."""
    w, h = im.size
    if h > w * 1.6:
        mid = h // 2
        ov = int(h * 0.05)
        return [im.crop((0, 0, w, mid + ov)), im.crop((0, mid - ov, w, h))]
    return [im]


def _thumbs(doc: pymupdf.Document, limit: int = 12) -> list[bytes]:
    out = []
    for i, pg in enumerate(doc):
        if i >= limit:
            break
        im = _render(pg, None, 800)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 70, 28], fill="yellow")
        d.text((6, 6), f"p{i + 1}", fill="black")
        out.append(_jpeg(im, 800, 80))
    return out


def images_for(paths: list[Path], company_id: int) -> tuple[str, list[bytes], list[str]]:
    """→ (글자, 그림들, 메모). 글자 있는 PDF는 일람표 쪽 + 타일, 글자 없는 PDF는 AI에게 위치를 묻고 그 부분을 크게."""
    from server.sitok import vision

    text, imgs, notes = [], [], []
    for p in paths:
        if p.suffix.lower() != ".pdf":
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((2400, 2400))
                imgs += _tiles(im)
            continue
        with pymupdf.open(p) as doc:
            pages_text = [pg.get_text() for pg in doc]
            has_text = sum(len(t.strip()) for t in pages_text) > 200 * max(1, doc.page_count) * 0.3
            picks = [i for i, t in enumerate(pages_text) if any(k in t for k in KEYS)]
            if has_text and picks:
                for i in picks[:MAX_PAGES]:
                    text.append(f"<{p.name} {i + 1}쪽>\n" + pages_text[i][:6000])
                    imgs += _tiles(_render(doc[i], None, 2400))
                notes.append(f"{p.name}: 일람표 글자가 있는 {len(picks)}쪽 중 {min(len(picks), MAX_PAGES)}쪽")
                continue
            # 글자가 없거나 일람표 쪽을 못 찾음 → AI에게 위치 묻기
            thumbs = _thumbs(doc)
            try:
                found = vision.ask_json(company_id, thumbs, LOCATE_PROMPT, max_tokens=4000, side=800, effort="medium")
            except Exception as err:  # noqa: BLE001
                notes.append(f"{p.name}: 일람표 위치를 못 찾음({str(err)[:60]}) — 앞 쪽들을 통째로")
                found = []
            if not isinstance(found, list):
                found = []
            boxes = []
            for x in found:
                try:
                    pg_no = int(x.get("page"))
                    x0, y0, x1, y1 = (float(x.get(k)) for k in ("x0", "y0", "x1", "y1"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if 1 <= pg_no <= doc.page_count and x1 > x0 and y1 > y0:
                    boxes.append((pg_no - 1, max(0.0, x0 - 2) / 100, max(0.0, y0 - 2) / 100, min(100.0, x1 + 2) / 100, min(100.0, y1 + 2) / 100))
            if not boxes:
                for i in range(min(doc.page_count, 2)):
                    imgs += _tiles(_render(doc[i], None, 2400))
                notes.append(f"{p.name}: 일람표 쪽을 못 찾아 앞 2쪽을 통째로")
                continue
            for (i, fx0, fy0, fx1, fy1) in boxes[:MAX_PAGES]:
                r = doc[i].rect
                clip = pymupdf.Rect(r.x0 + r.width * fx0, r.y0 + r.height * fy0, r.x0 + r.width * fx1, r.y0 + r.height * fy1)
                im = _render(doc[i], clip, 3000)
                for part in _split_tall(im):
                    imgs.append(_jpeg(part))
            notes.append(f"{p.name}: AI가 찾은 일람표 {len(boxes)}곳(쪽 {', '.join(str(b[0] + 1) for b in boxes[:MAX_PAGES])})을 크게")
    return "\n\n".join(text), imgs[:24], notes


def _selfcheck() -> None:
    im = Image.new("RGB", (2400, 1600), "white")
    assert len(_tiles(im)) == 5 and all(Image.open(io.BytesIO(b)).size[0] <= SIDE for b in _tiles(im))
    assert len(_split_tall(Image.new("RGB", (400, 1200), "white"))) == 2 and len(_split_tall(Image.new("RGB", (1200, 400), "white"))) == 1
    assert json.loads('[{"page": 1}]')[0]["page"] == 1
    print("일람표 그림 고르기 검증 통과")


if __name__ == "__main__":
    _selfcheck()
