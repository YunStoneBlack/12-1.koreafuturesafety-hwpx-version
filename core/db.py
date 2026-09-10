"""SQLite 연결/세션 관리. 데스크톱 앱은 로컬 단일 DB 파일(data/app.db)을 사용한다."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

if getattr(sys, "frozen", False):
    # PyInstaller로 빌드된 exe — `sys._MEIPASS`(onefile 압축 해제 임시 폴더)를 쓰면 앱을
    # 껐다 켤 때마다 그 폴더가 통째로 새로 만들어져 DB/사진/서명 등 사용자 데이터가 전부
    # 사라진다. exe 파일이 있는 폴더를 기준으로 삼아야 재실행해도 데이터가 그대로 남는다.
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "app.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """테이블 생성 + 참조 데이터(계측기준/공정 카탈로그/제공자료 라이브러리) 시딩. 앱 시작
    시 1회 호출."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    from core import models_db  # noqa: F401  (테이블 등록을 위해 임포트 필요)

    Base.metadata.create_all(engine)
    _seed_measurement_standards()
    _seed_reference_data()


def _seed_measurement_standards() -> None:
    from core.models_db import MeasurementStandard
    from data.measurement_standards import MEASUREMENT_STANDARDS

    with SessionLocal() as session:
        if session.query(MeasurementStandard).count() > 0:
            return
        for instrument_type, criteria in MEASUREMENT_STANDARDS.items():
            session.add(MeasurementStandard(instrument_type=instrument_type, standard_criteria=criteria))
        session.commit()


def _seed_reference_data() -> None:
    """공정 카탈로그(ProcessCatalog)/제공자료 라이브러리(MaterialLibrary) — 고객사마다
    새로 만드는 데이터가 아니라 프로그램에 내장된 공용 참고 자료라, 개발 중 모아둔 것을
    `data/seed_reference_data.json`(+ 실제 이미지 파일이 있는 `data/materials/`)으로
    그대로 배포한다. 이 JSON이 없는 개발 환경(아직 안 만든 경우)에서는 조용히 건너뛴다.
    """
    import json

    from core.models_db import MaterialLibrary, ProcessCatalog

    seed_path = BASE_DIR / "data" / "seed_reference_data.json"
    if not seed_path.exists():
        return
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    materials_dir = BASE_DIR / "data" / "materials"

    with SessionLocal() as session:
        if session.query(ProcessCatalog).count() == 0:
            for entry in data.get("process_catalog", []):
                session.add(ProcessCatalog(**entry))
            session.commit()

        if session.query(MaterialLibrary).count() == 0:
            for entry in data.get("materials", []):
                session.add(
                    MaterialLibrary(
                        title=entry["title"],
                        file_path=str(materials_dir / entry["file_rel"]),
                        thumbnail_path=str(materials_dir / entry["thumbnail_rel"])
                        if entry.get("thumbnail_rel")
                        else "",
                        tags=entry.get("tags", ""),
                    )
                )
            session.commit()
