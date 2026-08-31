"""KOSHA 산업안전포털의 공개 안전자료(포스터/카드뉴스류)를 내려받아
제공자료 라이브러리(MaterialLibrary)에 등록하는 1회성 시딩 스크립트.

공개 정부기관(고용노동부·안전보건공단) 배포용 안전 교육자료이며, 별도 인증 없이
접근 가능한 API를 그대로 사용한다. 실행:

    python -m data.seed_materials_kosha

여러 번 실행해도 이미 등록된 자료(title 기준)는 건너뛴다. 책자/PPT/영상처럼
용량이 큰 자료는 보고서 첨부용 포스터 라이브러리 취지에 안 맞아 다운로드 전에 걸러낸다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.db import SessionLocal, init_db
from core.models_db import MaterialLibrary
from core.thumbnail_generator import generate_pdf_thumbnail

API_BASE = "https://portal.kosha.or.kr/api/portal24/bizV/p/VCPDG01007"
FILE_API_BASE = "https://portal.kosha.or.kr/api/portal24/bizA/p/files"

MENU_CODES = ["01", "02", "03", "04", "05"]  # 제조업/건설업/서비스업/조선업/기타산업
# list1=OPS, list2=동영상, list3=책자, list4=교안(PPT), list5=기타. 동영상은 제외.
INCLUDED_LIST_KEYS = ["list1", "list3", "list4", "list5"]

# 실제 화면에서 본 자료들과 비슷한 걸 최대한 넓게 찾기 위한 검색어들.
SEARCH_KEYWORDS = [
    None,  # 검색어 없이 최신순 상위 항목
    "기준규칙",
    "안전수칙",
    "고위험요인",
    "예방가이드",
    "작업안전수칙",
    "화재폭발",
    "추락위험방지",
    "산업안전보건법령요지",
]

MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB — 포스터/카드뉴스 용도로 적당한 상한
MATERIALS_DIR = Path(__file__).resolve().parent.parent / "data" / "materials"
THUMBNAILS_DIR = MATERIALS_DIR / "thumbnails"


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_media_list(menu_code: str, search_val: str | None) -> list[dict]:
    payload = {
        "startDt": None, "endDt": None, "searchType": "all", "searchVal": search_val,
        "selectPeriod": "1", "menuMode": "1", "menuCode": menu_code,
        "ctgr01": 0, "arrCtgrStr01": "", "ctgr02": 0, "arrCtgrStr02": "",
        "ctgr03": 0, "arrCtgrStr03": "", "ctgr04": 0, "arrCtgrStr04": "",
        "ctgr05": 0, "arrCtgrStr05": "",
    }
    data = _post_json(f"{API_BASE}/selectMediaCateList", payload)
    payload_data = data.get("payload", {})
    items = []
    for key in INCLUDED_LIST_KEYS:
        items.extend(payload_data.get(key, []))
    return items


def _fetch_file_info(fileId: str) -> dict | None:
    data = _post_json(
        f"{FILE_API_BASE}/getFileList",
        {"fileId": fileId, "fileUploadType": "02", "atcflTaskColNm": "lastFile", "atcflSeTaskComCdNm": "Y"},
    )
    files = data.get("payload") or []
    return files[0] if files else None


def _download_if_small_enough(atcfl_no: str, atcfl_seq: int, dest: Path) -> bool:
    """MAX_FILE_SIZE보다 크면 중간에 중단하고 False를 반환한다 (대용량 낭비 방지)."""
    url = f"{FILE_API_BASE}/downloadAtchFile?atcflNo={atcfl_no}&atcflSeq={atcfl_seq}&isDirect=N&taskSeCd="
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_FILE_SIZE:
                print(f"  건너뜀(크기 {int(content_length) // 1024}KB > 제한): {dest.name}")
                return False

            chunks = []
            total = 0
            for chunk in iter(lambda: resp.read(65536), b""):
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    print(f"  건너뜀(스트리밍 중 크기 초과): {dest.name}")
                    return False
                chunks.append(chunk)
            dest.write_bytes(b"".join(chunks))
        return True
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  다운로드 실패: {e}")
        return False


def seed() -> None:
    init_db()
    MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    all_items: dict[str, dict] = {}  # title -> item (중복 제거)
    for menu_code in MENU_CODES:
        for keyword in SEARCH_KEYWORDS:
            try:
                items = _fetch_media_list(menu_code, keyword)
            except Exception as e:
                print(f"목록 조회 실패 (menuCode={menu_code}, keyword={keyword}): {e}")
                continue
            for item in items:
                title = item.get("contsTtlNm", "")
                if title and title not in all_items:
                    all_items[title] = item
            time.sleep(0.2)

    print(f"후보 자료 {len(all_items)}건 확인됨 (중복 제거 후)")

    with SessionLocal() as session:
        existing_titles = {m.title for m in session.query(MaterialLibrary).all()}

        added = 0
        for title, item in all_items.items():
            if title in existing_titles:
                continue

            file_info = _fetch_file_info(item.get("contsAtcflNo"))
            if not file_info:
                continue

            ext = file_info.get("atcflExtnNm", "bin")
            if ext.lower() in ("mp4", "avi", "mov", "wmv", "zip"):
                continue

            atcfl_seq = file_info.get("atcflSeq", 1)
            safe_name = "".join(c for c in title if c not in '\\/:*?"<>|')[:80]
            dest_path = MATERIALS_DIR / f"{item.get('contsAtcflNo')}_{safe_name}.{ext}"

            if not _download_if_small_enough(item.get("contsAtcflNo"), atcfl_seq, dest_path):
                if dest_path.exists():
                    dest_path.unlink()
                continue

            thumbnail_path = ""
            if ext.lower() in ("jpg", "jpeg", "png"):
                thumbnail_path = str(dest_path)
            elif ext.lower() == "pdf":
                thumb_dest = THUMBNAILS_DIR / f"{dest_path.stem}.png"
                if generate_pdf_thumbnail(dest_path, thumb_dest):
                    thumbnail_path = str(thumb_dest)

            tags = (item.get("srchKywdCn") or "").replace(" ", "")
            session.add(
                MaterialLibrary(
                    title=title,
                    file_path=str(dest_path),
                    thumbnail_path=thumbnail_path,
                    tags=tags,
                )
            )
            existing_titles.add(title)
            added += 1
            print(f"  등록: {title} ({ext})")
            time.sleep(0.2)

        session.commit()

    print(f"\n완료: {added}건 신규 등록됨 (전체 {len(existing_titles)}건)")


if __name__ == "__main__":
    seed()
