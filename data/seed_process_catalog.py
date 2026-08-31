"""실제 서비스(jidobiseo.co.kr)의 진행공정 카탈로그(284건)를 ProcessCatalog에 반영하는
1회성 시딩 스크립트. 원본 데이터는 사용자가 로그인한 브라우저에서 Playwright(CDP)로 직접
추출한 JSON 3종(공정명+위험등급, 카테고리 매핑, 공정명+전체 유해요인/예방대책)을 병합해서 만든다.

실행:
    python -m data.seed_process_catalog <raw_json> <category_json> <full_json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.db import SessionLocal, init_db
from core.models_db import ProcessCatalog

_RISK_MAP = {"상": "상", "중": "중", "하": "하"}


def _load(path: str) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed(raw_path: str, category_path: str, full_path: str) -> None:
    init_db()

    raw_items = _load(raw_path)  # [{name, hazard, risk}, ...] (미리보기용, risk만 신뢰)
    category_map = _load(category_path)  # {category: [name, ...]}
    full_items = _load(full_path)  # [{name, hazard_full, prevention_full}, ...]

    risk_by_name = {item["name"]: item.get("risk", "") for item in raw_items}

    # 이름으로 카테고리를 매핑하면 같은 공정명이 두 카테고리에 동시에 존재하는 경우
    # (예: "콘크리트 타설 및 양생"이 신축·증축 공사(종합)와 철근콘크리트(골조)공사
    # 양쪽에 다 있음) 뒤쪽 항목이 앞쪽 항목의 카테고리로 뭉개져버린다. 실제 사이트의
    # "전체" 목록은 category_mapping.json의 카테고리 순서대로 각 카테고리의 항목을
    # 이어붙인 것과 정확히 일치하므로(검증됨: 누적 개수 구간이 sort_order와 그대로
    # 대응), 이름이 아니라 순서(구간)로 카테고리를 매긴다.
    category_ranges: list[tuple[str, int, int]] = []
    cursor = 0
    for category, names in category_map.items():
        category_ranges.append((category, cursor, cursor + len(names)))
        cursor += len(names)

    def category_for_index(idx: int) -> str:
        for category, start, end in category_ranges:
            if start <= idx < end:
                return category
        return ""

    with SessionLocal() as session:
        existing = session.query(ProcessCatalog).count()
        if existing:
            print(f"기존 ProcessCatalog {existing}건 삭제 후 재구성합니다.")
            session.query(ProcessCatalog).delete()

        added = 0
        skipped = 0
        for order, item in enumerate(full_items):
            name = item.get("name")
            hazard = item.get("hazard_full")
            prevention = item.get("prevention_full")
            if not name or not hazard or not prevention:
                skipped += 1
                continue

            session.add(
                ProcessCatalog(
                    category=category_for_index(order),
                    construction_type="",
                    process_name=name,
                    hazard_text=hazard,
                    prevention_text=prevention,
                    default_risk_level=_RISK_MAP.get(risk_by_name.get(name, ""), ""),
                    reviewed=True,
                    sort_order=order,
                )
            )
            added += 1

        session.commit()

    print(f"등록: {added}건, 건너뜀(데이터 누락): {skipped}건")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("사용법: python -m data.seed_process_catalog <raw_json> <category_json> <full_json>")
        raise SystemExit(1)
    seed(sys.argv[1], sys.argv[2], sys.argv[3])
