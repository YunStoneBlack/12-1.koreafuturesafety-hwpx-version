"""건축물관리점검 견본 더하기(2026-10-30 사용자 "우리프라자를 견본으로 해서 해당사항이 없으면 견본사진이 안 나옴 — 적정한 견본사진 2장 정도") —
우리프라자에서 해당없음이라 현장 견본 사진이 없던 항목에, 회사의 다른 제출 보고서(드롭박스 4.보고서/4. 건축물관리법) 중 그 항목을 실제로 점검한 건의 현황사진 2장씩.

쓰는 법: python -I server/scripts/add_blcm_samples.py <드롭박스 4. 건축물관리법 폴더> <참고 사진 폴더> [--dry 미리보기 폴더]
  → samples.json의 그 항목 photos = (우리프라자 서류 그림 — 건축물 대장·토지이용계획 확인원 등은 그대로) + 아래 PICKS 사진(사진마다 from = 어느 보고서),
    설명 없는 우리프라자 그림은 뺌. 글(위법·성능·근거·비고)은 우리프라자 것 그대로(해당없음 사유 견본). make_blcm_samples.py를 다시 돌리면 이것도 다시 돌릴 것.
고르기 기준: 그 항목이 적용대상인 용도의 건물(범죄예방 1-1 = 100세대 이상 아파트, 1-2 = 오피스텔, 2-1 = 교육연구시설 …), 설명이 구체적인 사진."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("mbs", HERE.with_name("make_blcm_samples.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
SAMPLES = HERE.parents[1] / "blcm" / "samples.json"

R = {  # 보고서(드롭박스 폴더 안 상대 경로) → 견본 이름
    "jung": ("2023/1.정자푸르지오시티3차/보고서/정자동3차 푸르지오 시티 D동 .pdf", "정자 푸르지오시티 D동"),
    "yuseong": ("2023/2.의정부 유성벨로스 공동주택/보고서/건축물 정기점검보고서.pdf", "의정부 유성벨로스"),
    "sina": ("2024/10.구리시 인창동 교육연구시설(신아월드코아)/보고서/신아월드코아 건축물 관리점검 보고서.pdf", "구리 신아월드코아"),
    "jeongmok": ("2024/9.정목 e-미지 주상복합 아파트/보고서/정목이미지 주상복합아파트 건축물관리점검 보고서.pdf", "정목 e-미지 주상복합"),
    "buksuwon": ("2025/예장건축사사무소/4.북수원아이파크101동/보고서/건축물관리점검 보고서.pdf", "북수원아이파크 101동"),
    "bucheon": ("2025/한국미래안전/14. 2025년 부천종합운동장 건축물 정기점검 용역/보고서/건출물관리점검 보고서-부천시춘의동체육공원 체육관.pdf", "부천 춘의동체육공원 체육관"),
    "pyeongtaek": ("2025/한국미래안전/16.평택그랜드메디컬타워/보고서/그랜드메디컬타워 건축물관리점검 보고서.pdf", "평택 그랜드메디컬타워"),
    "lh": ("2026/1.한국미래안전/1.건축물관리점검/3.LH행복주택청년이룸 1단지/보고서/report (6).pdf", "LH행복주택 청년이룸 1단지"),
    "sejong": ("2024/21.세종교육센터/보고서/보고서.pdf", "세종교육센터"),
}
# 우리 항목 → [(보고서, 그 보고서의 항목 번호, 현황사진 차례(0부터), 설명 바꾸기 또는 None)]
PICKS = {
    "3.1.3": [("jung", "3.1.3", 0, None), ("jung", "3.1.3", 1, None)],
    "3.1.15": [("jeongmok", "3.1.15", 0, None), ("lh", "3.1.15", 5, None)],
    "3.1.16": [("buksuwon", "3.1.16", 0, None), ("buksuwon", "3.1.16", 3, None)],
    "3.1.17": [("jung", "3.1.16", 0, None), ("jung", "3.1.16", 1, None)],
    "3.1.18": [("sina", "3.1.17", 0, None), ("sina", "3.1.17", 1, None)],
    "3.1.19": [("jung", "3.1.17", 2, None), ("jung", "3.1.17", 1, None)],
    "3.1.20": [("sina", "3.1.17", 2, None), ("sina", "3.1.17", 3, None)],
    "3.4.1": [("buksuwon", "3.4.1", 2, None), ("bucheon", "3.4.1", 2, None)],
    "3.4.2": [("yuseong", "3.4.2", 0, None), ("lh", "3.4.2", 0, None)],
    "3.4.6": [("bucheon", "3.4.6", 0, None), ("jung", "3.4.6", 0, None)],
    "3.4.9": [("jung", "3.4.9", 0, None), ("jung", "3.4.9", 1, None)],
    "3.5.3": [("pyeongtaek", "3.5.3", 0, "건물 전경(층수·높이 확인)")],  # 준초고층·초고층이 아닌 건물 — 피난안전구역 사진은 회사 보고서에 없음
    "3.5.8": [("jung", "3.5.8", 0, None), ("jung", "3.5.8", 1, None)],
    "3.2.7": [("sejong", "3.2.7", 0, None), ("sejong", "3.2.7", 1, None)],  # 10/30 — 우리프라자 "방송설비"는 화재수신기(P형1급) 사진이라 바꿈
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    base, out = Path(sys.argv[1]), Path(sys.argv[2])
    src_dir = Path(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else out  # 지금 견본 사진 폴더(미리보기 때)
    dry = "--dry" in sys.argv
    out.mkdir(parents=True, exist_ok=True)
    samples = json.loads(SAMPLES.read_text(encoding="utf-8"))
    cache: dict[str, tuple] = {}

    def item(key: str, rcode: str) -> tuple:
        if key not in cache:
            doc = pymupdf.open(base / R[key][0])
            cache[key] = (doc, M.item_pages(doc))
        doc, pages = cache[key]
        return doc, M.read_item(doc, pages[rcode])

    # 1) 남길 우리프라자 서류 그림(건축물 대장·토지이용계획 확인원 …)을 먼저 읽어 둠 — 새 사진이 같은 파일 이름을 덮기 전에
    keep: dict[str, list] = {}
    for code in PICKS:
        keep[code] = [(p, (src_dir / p["file"]).read_bytes()) for p in (samples.get(code) or {}).get("photos") or []
                      if p.get("caption") and M.re.search(r"확인원", p["caption"]) and (src_dir / p["file"]).exists()]
        # 10/30 — 우리프라자 "건축물 대장"(해당없음 근거)은 뺌: 적용대상 건물에선 쓸데없이 도면 칸·"도면 없음" 경고가 생김(해당없음 근거 캡처는 따로)
    # 2) 새 사진(다른 보고서) + 서류 그림 — 번호 1부터
    for code, picks in PICKS.items():
        cur = dict(samples.get(code) or {})
        photos = []
        for key, rcode, idx, cap in picks:
            doc, got = item(key, rcode)
            ph = got["photos"][idx]
            n = len(photos) + 1
            name = f"{code}_{n}.jpg"
            (out / name).write_bytes(doc[ph["page"]].get_pixmap(clip=ph["rect"], dpi=110).tobytes("jpg", jpg_quality=80))
            photos.append({"n": n, "file": name, "caption": cap or ph["caption"], "from": R[key][1]})
            print(code, n, R[key][1], "·", cap or ph["caption"])
        for p, data in keep[code]:
            n = len(photos) + 1
            name = f"{code}_{n}.jpg"
            (out / name).write_bytes(data)
            photos.append({**p, "n": n, "file": name})
            print(code, n, "(우리프라자 서류)", p["caption"])
        cur.pop("same_as", None)
        cur["photos"] = photos
        samples[code] = cur
    if not dry:
        SAMPLES.write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")
        print("samples.json 갱신")


if __name__ == "__main__":
    main()
