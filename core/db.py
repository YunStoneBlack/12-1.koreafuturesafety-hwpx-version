"""SQLite 연결/세션 관리. 데스크톱 앱은 로컬 단일 DB 파일(data/app.db)을 사용한다."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "app.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """테이블 생성 + 참조 데이터(계측기준) 시딩. 앱 시작 시 1회 호출."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    from core import models_db  # noqa: F401  (테이블 등록을 위해 임포트 필요)

    Base.metadata.create_all(engine)
    _seed_measurement_standards()


def _seed_measurement_standards() -> None:
    from core.models_db import MeasurementStandard
    from data.measurement_standards import MEASUREMENT_STANDARDS

    with SessionLocal() as session:
        if session.query(MeasurementStandard).count() > 0:
            return
        for instrument_type, criteria in MEASUREMENT_STANDARDS.items():
            session.add(MeasurementStandard(instrument_type=instrument_type, standard_criteria=criteria))
        session.commit()
