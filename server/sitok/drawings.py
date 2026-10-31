"""시특법 시설물 도면(2026-10-12 사용자, alembic 0039 sitok_facility.drawings) — 시설물에 한 번 올려 다음 회차에도 쓰고, 증축·인테리어 등으로
바뀌면 시설물 현황 창에서 바꿈(이미 만든 보고서는 그대로, 다음에 만들 때부터).

- attach(첨부 도면 — 평·입·단면도): 보고서 PDF의 "N.2.9 관련 설계도면" 쪽 바로 뒤에 끼움(그림은 한 장 한 쪽, 가로·세로는 그림대로). 없으면 한글의
  "-후면첨부-"를 "-"로.
- struct(구조일반사항·건축개요 도면): 시설물 현황 [🤖 채우기]가 관리대장·건축물대장과 같이 읽음(글자 + 쪽 그림 — 스캔 도면도).
- schedule(구조 일람표, 10/14 형): 정밀 재료시험 [🤖 일람표에서 설계 치수 채우기]가 읽음(server/sitok/tests.schedule_fill).
"""
from __future__ import annotations

import datetime
import io
import uuid
from pathlib import Path

KINDS = ("attach", "struct", "schedule")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp")


def items(f, kind: str, base: Path) -> list[dict]:
    """[{id, file, name, at, path}] 순서대로, 파일 있는 것만."""
    out = []
    for it in ((f.drawings or {}).get(kind) or []):
        p = base / it["file"]
        if p.exists():
            out.append({**it, "path": p})
    return out


def add(f, kind: str, base: Path, data: bytes, name: str) -> None:
    ext = Path(name).suffix.lower()
    if data.startswith(b"%PDF"):
        ext = ".pdf"
    elif ext not in IMAGE_EXT:
        raise ValueError("도면은 PDF 또는 그림(jpg·png 등)으로 올려 주세요.")
    did = uuid.uuid4().hex[:10]
    keep = ext if ext == ".pdf" else _image_ext(data)  # 도면 그림은 원본 화질 그대로(10/29 사용자 "관련도면 화질 유지" — 전엔 사진처럼 2000px로 줄여 JPG)
    rel = f"도면/{kind}_{did}{keep or '.jpg'}"
    dest = base / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if keep:
        dest.write_bytes(data)
    else:
        _full_jpeg(data, dest)
    d = dict(f.drawings or {})
    d[kind] = [*(d.get(kind) or []), {"id": did, "file": rel, "name": name, "at": datetime.date.today().isoformat()}]
    f.drawings = d


def _image_ext(data: bytes) -> str:
    """그대로 둘 수 있는 그림이면 그 확장자(JPG는 돌림 정보가 없을 때만, PNG) — 아니면 ""(원래 크기 JPG로 바꿈)."""
    import io

    from PIL import Image

    try:
        im = Image.open(io.BytesIO(data))
        if im.format == "JPEG" and (im.getexif() or {}).get(274, 1) == 1 and im.mode in ("RGB", "L"):
            return ".jpg"
        if im.format == "PNG" and im.mode in ("RGB", "L", "P", "RGBA"):
            return ".png"
    except Exception as err:  # noqa: BLE001
        raise ValueError("도면 그림을 읽지 못했습니다 — PDF 또는 JPG·PNG로 올려 주세요.") from err
    return ""


def _full_jpeg(data: bytes, dest: Path) -> None:
    """원래 크기 그대로 JPG(돌림 정보는 풀고, 투명은 흰 바탕) — 줄이지 않음."""
    import io

    from PIL import Image, ImageOps

    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            im = Image.new("RGB", rgba.size, "white")
            im.paste(rgba, mask=rgba.split()[-1])
        im.convert("RGB").save(dest, "JPEG", quality=95)
    except Exception as err:  # noqa: BLE001
        raise ValueError("도면 그림을 읽지 못했습니다 — PDF 또는 JPG·PNG로 올려 주세요.") from err


def remove(f, kind: str, base: Path, did: str) -> None:
    d = dict(f.drawings or {})
    for it in d.get(kind) or []:
        if it["id"] == did:
            (base / it["file"]).unlink(missing_ok=True)
    d[kind] = [it for it in d.get(kind) or [] if it["id"] != did]
    f.drawings = d


def move(f, kind: str, did: str, step: int) -> None:
    d = dict(f.drawings or {})
    lst = list(d.get(kind) or [])
    i = next((k for k, it in enumerate(lst) if it["id"] == did), None)
    if i is not None and 0 <= i + step < len(lst):
        lst[i], lst[i + step] = lst[i + step], lst[i]
    d[kind] = lst
    f.drawings = d


def has_content(pg) -> bool:
    """PDF 쪽에 선·그림·글 중 하나라도 있는지 — 아무것도 없는 빈 쪽은 도면으로 끼우지 않음(10/31 민재형 "71쪽 빈 쪽")."""
    return bool(pg.get_drawings() or pg.get_images() or pg.get_text().strip())


def pages_of(path: Path) -> int:
    if path.suffix.lower() != ".pdf":
        return 1
    import pymupdf

    with pymupdf.open(path) as doc:
        return sum(1 for pg in doc if has_content(pg))  # 빈 쪽은 안 끼우니 뺌


def insert(pdf: Path, chapters: list[tuple[int, list[Path]]], finder=None) -> list[int]:
    """보고서 PDF의 "N.2.9 관련 설계도면" 쪽(시설물편 N장) 바로 뒤에 도면 쪽들을 끼움 → 끼운 쪽 번호들(0부터, 쪽 검사에서 뺌).
    목차·장 표지에도 "N.2.9"가 있을 수 있어 "후면첨부"가 같이 있는 쪽만. finder(pg, n) → bool 을 주면 그 조건으로 쪽을 찾음(정밀 "1.2 시설물 관련도면", 10/13)."""
    import pymupdf

    doc = pymupdf.open(pdf)
    plan = []
    for n, paths in chapters:
        if not paths:
            continue
        if finder is not None:
            at = next((i for i, pg in enumerate(doc) if finder(pg, n)), None)
        else:
            at = next((i for i, pg in enumerate(doc) if pg.search_for(f"{n}.2.9") and pg.search_for("관련 설계도면") and pg.search_for("후면첨부")), None)
        if at is not None:
            plan.append((at, paths))
    inserted: list[int] = []
    for at, paths in sorted(plan, key=lambda x: -x[0]):  # 뒤에서부터 끼워 앞 쪽 번호가 안 밀리게
        pos = at + 1
        added = 0
        for p in paths:
            if p.suffix.lower() == ".pdf":
                with pymupdf.open(p) as src:
                    for k in range(src.page_count):
                        pg = src[k]
                        if not has_content(pg):
                            continue  # 올린 도면 PDF 속 완전히 빈 쪽은 안 끼움(10/31 민재형 "71쪽 빈 쪽")
                        doc.insert_pdf(src, from_page=k, to_page=k, start_at=pos + added)
                        added += 1
            else:
                from PIL import Image

                with Image.open(p) as im:
                    w, h = im.size
                W, H = (842, 595) if w > h else (595, 842)  # A4 가로·세로
                page = doc.new_page(pno=pos + added, width=W, height=H)
                m = 20
                page.insert_image(pymupdf.Rect(m, m, W - m, H - m), filename=str(p), keep_proportion=True)
                added += 1
        inserted = [x + added if x >= pos else x for x in inserted] + list(range(pos, pos + added))
    tmp = pdf.with_suffix(".drw.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return sorted(inserted)


def for_ai(paths: list[Path], max_pages: int = 4) -> tuple[str, list[bytes]]:
    """시설물 현황 AI용 — (글자, 쪽 그림 JPG들). 구조일반사항은 표·주기가 많아 그림으로도 봄(스캔 도면은 그림으로만)."""
    import pymupdf
    from PIL import Image

    text, imgs = [], []
    for p in paths:
        if p.suffix.lower() == ".pdf":
            with pymupdf.open(p) as doc:
                text.append(f"<{p.name}>\n" + "\n".join(pg.get_text() for pg in doc)[:12000])
                for pg in list(doc)[:max_pages - len(imgs)] if len(imgs) < max_pages else []:
                    zoom = min(2.0, 1600 / max(pg.rect.width, pg.rect.height))
                    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                    imgs.append(pix.tobytes("jpeg"))
        elif len(imgs) < max_pages:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((1600, 1600))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=85)
                imgs.append(buf.getvalue())
    return "\n\n".join(text), imgs
