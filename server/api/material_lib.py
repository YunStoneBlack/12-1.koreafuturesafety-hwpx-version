"""제공자료 라이브러리 정리 규칙(2026-10-15 사용자·민재형 "자료 81개뿐, 추천이 공정과 안 맞음, 한 번에 많이 올리고 싶음").

형 Dropbox 교육자료 일괄 등록(scratchpad 1회)과 웹 [📤 자료 올리기](materials.py)가 같은 규칙을 쓴다.
- 받는 파일: PDF·JPG·PNG(파일 앞 글자로 판정 — 확장자 없는 PDF도 받음). **PDF는 4쪽까지** — 보고서 뒤에 쪽마다 붙으므로
  책자·작업절차서는 뺀다(사용자 "용량 크면 빼버려").
- 이름 다듬기: 앞 문서번호 "[2022-교육혁신실-700]"·"2018-교육미디어-616-"·"붙임1." 과 꼬리 "_웹용·(인쇄용)·_최종·(1)·_압축" 떼기
  — 자료 이름이 보고서 10번 교육내용 칸에 그대로 들어가기 때문.
- 겹침: 이름을 띄어쓰기·기호 빼고 비교해 같으면 건너뜀(웹용/인쇄용처럼 꼬리만 다른 것도 같은 자료).
- 분류: 형 Dropbox 폴더 이름을 바탕으로 한 분류(안전모·굴삭기·폭염…) — 제목·태그 글자로 그때그때 매김(기존 81개도 DB 손대지 않고 분류됨).
- 저장: 저장소 `_자료실`(core.db DATA_DIR) + thumbnails/<이름>_thumb.jpg(고르기 창용 작은 그림). 큰 그림은 긴 변 2400px로 줄여 저장.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from core.db import DATA_DIR
from core.models_db import MaterialLibrary
from core.thumbnail_generator import THUMBNAIL_WIDTH

MAX_PAGES = 4
IMAGE_MAX_SIDE = 2400

# (분류 이름, 제목·태그에서 찾는 말) — 이름은 형 Dropbox 폴더 이름을 최대한 그대로
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("추락", ("추락", "떨어", "개구부", "단부")),
    ("비계·안전난간", ("비계", "안전난간", "작업발판")),
    ("이동식사다리", ("사다리",)),
    ("고소작업대", ("고소작업대",)),
    ("굴삭기", ("굴착기", "굴삭기")),
    ("건설기계·차량", ("건설기계", "차량계", "펌프카", "덤프", "화물차", "롤러")),
    ("크레인·지게차", ("크레인", "지게차", "양중", "인양")),
    ("안전모", ("안전모",)),
    ("안전대", ("안전대",)),
    ("보호구", ("보호구", "안전화", "마스크", "보안경")),
    ("올바른 작업자세", ("작업자세", "근골격", "중량물", "취급 자세")),
    ("용접·화재", ("용접", "화재", "폭발", "불티", "소화")),
    ("감전·전기", ("감전", "전기", "전선")),
    ("폭염 온열질환", ("폭염", "온열")),
    ("혹한기 안전", ("한파", "한랭", "동절기", "혹한", "겨울")),
    ("장마철 안전수칙", ("장마", "호우", "강풍", "태풍")),
    ("밀폐공간 작업", ("밀폐",)),
    ("MSDS·화학물질", ("msds", "화학물질", "석면")),
    ("휴대용 연삭기", ("연삭기", "그라인", "절단기")),
    ("지붕공사", ("지붕", "채광창")),
    ("작업장 정리정돈", ("정리정돈", "조도", "작업장 안전")),
    ("위험표지판", ("표지판",)),
    ("해체·철거", ("해체", "철거", "붕괴")),
    ("끼임·부딪힘", ("끼여", "끼임", "부딪", "깔려", "낙하", "협착", "맞아")),
    ("미세먼지", ("미세먼지", "분진")),
    ("재해사례", ("재해사례", "사고사례", "속보", "quick message", "사망사고")),
    ("법령·기준", ("기준규칙", "산업안전보건법", "산안법", "이행사항", "법령")),
]


def categorize(text: str) -> list[str]:
    low = (text or "").lower()
    return [name for name, words in CATEGORIES if any(w in low for w in words)]


def categories_of(m: MaterialLibrary) -> list[str]:
    return categorize(f"{m.title} {m.tags or ''}")


_LEAD = [
    r"\[[^\]]*\]\s*[_\-]?\s*",                     # [2022-교육혁신실-700]
    r"\d{4}-[가-힣A-Za-z]+-\d+[\s_\-]*",            # 2018-교육미디어-616-
    r"\d{4}\.\d{1,2}\.\d{1,2}[\s_\-]*",             # 2018.02.07_
    r"\(\d+-\d+-\d+\)\s*\+?",                      # (1-2-0)
    r"\d+_\d+_",                                   # 20_11_
    r"[가-힣]-\d+-\d+-",                            # 업-2-732-
    r"붙임\s*\d*\.?\s*",                            # 붙임1.
    r"\d{6}\s+",                                   # 250725
    r"\d{4}_",                                     # 2604_
    r"\d+\.\s*",                                   # 4. / 10.
    r"\d+호[\s_]+",                               # 14호 (Quick Message 호수)
    r"\d{2,3}-(?=[가-힣])",                        # 01-안전모, 649-올바른
    r"\(최종\)\s*",
]
_TAIL = re.compile(
    r"[\s_\-]*\(?(웹용|인쇄용|인쇄|홈페이지용|홈페이지\s*게시|배포용|web|최종안|최종\d?|압축|\d페이지)\)?(?=$|[\s_\-(])",
    re.I,
)


def clean_title(filename: str) -> str:
    stem = re.sub(r"\.(pdf|jpe?g|png)$", "", Path(filename).name, flags=re.I)
    t = stem
    for _ in range(4):
        before = t
        for pat in _LEAD:
            t = re.sub("^" + pat, "", t)
        if t == before:
            break
    for _ in range(3):
        t = _TAIL.sub("", t)
    t = re.sub(r"\s*\(\d\)\s*$", "", t)
    t = re.sub(r"\s*\((\d{6}|\d{4}-[가-힣]+-\d+)\)\s*$", "", t)  # (260712)·(2016-직업건강-693)
    t = re.sub(r"(_\d)+$", "", t)
    t = re.sub(r"\bNM$", "", t)
    t = re.sub(r"[_+]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -_.")
    return t or stem


def norm_key(title: str) -> str:
    return re.sub(r"[\s_\-()\[\]·,.+~]+", "", clean_title(title)).lower()


def find_same(db: Session, title: str) -> MaterialLibrary | None:
    key = norm_key(title)
    if not key:
        return None
    for m in db.query(MaterialLibrary):
        k = norm_key(m.title)
        if k == key or (min(len(k), len(key)) >= 10 and (k in key or key in k)):
            return m
    return None


def file_kind(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data.startswith(b"\x89PNG"):
        return "png"
    return ""


def pdf_pages(data: bytes) -> int:
    with pymupdf.open(stream=data, filetype="pdf") as d:
        return d.page_count


def _safe_name(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', " ", title).strip()[:80] or "자료"


def _first_image(data: bytes, kind: str) -> Image.Image:
    if kind == "pdf":
        with pymupdf.open(stream=data, filetype="pdf") as d:
            page = d.load_page(0)
            zoom = THUMBNAIL_WIDTH * 2 / page.rect.width
            return Image.open(io.BytesIO(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")))
    return ImageOps.exif_transpose(Image.open(io.BytesIO(data)))


def add_material(db: Session, data: bytes, filename: str, title: str | None = None, tags: list[str] | None = None) -> tuple[MaterialLibrary | None, str]:
    """파일 하나를 라이브러리에 넣는다 → (새 자료, "") 또는 (None, 못 넣은 이유). commit은 부르는 쪽."""
    kind = file_kind(data)
    if not kind:
        return None, "PDF·JPG·PNG 파일만 넣을 수 있습니다"
    if kind == "pdf":
        try:
            n = pdf_pages(data)
        except Exception:  # noqa: BLE001
            return None, "PDF를 열 수 없습니다"
        if n > MAX_PAGES:
            return None, f"{n}쪽짜리 PDF — {MAX_PAGES}쪽 넘는 책자·절차서는 보고서가 길어져 넣지 않습니다"
    title = (title or clean_title(filename)).strip()
    same = find_same(db, title)
    if same:
        return None, f"이미 있는 자료와 같습니다: {same.title}"
    folder = DATA_DIR / "_자료실"
    (folder / "thumbnails").mkdir(parents=True, exist_ok=True)
    base = _safe_name(title)
    ext = ".pdf" if kind == "pdf" else ".jpg" if kind == "jpg" else ".png"
    dest, i = folder / f"{base}{ext}", 2
    while dest.exists():
        dest, i = folder / f"{base} ({i}){ext}", i + 1
    if kind != "pdf":
        img = _first_image(data, kind)
        if max(img.size) > IMAGE_MAX_SIDE or len(data) > 3_000_000:  # 폰·인쇄용 큰 그림 → 보고서 용량 지키기
            img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
            dest = dest.with_suffix(".jpg")
            img.convert("RGB").save(dest, "JPEG", quality=88)
        else:
            dest.write_bytes(data)
    else:
        dest.write_bytes(data)
    thumb = folder / "thumbnails" / f"{dest.stem}_thumb.jpg"
    try:
        img = _first_image(data, kind)
        img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 3))
        img.convert("RGB").save(thumb, "JPEG", quality=85)
    except Exception:  # noqa: BLE001 — 작은 그림이 없어도 원본으로 보임
        thumb = None
    tag_text = ",".join(dict.fromkeys([t for t in (tags or []) if t] + categorize(title)))
    row = MaterialLibrary(title=title, file_path=str(dest), thumbnail_path=str(thumb) if thumb else "", tags=tag_text)
    db.add(row)
    db.flush()
    return row, ""
