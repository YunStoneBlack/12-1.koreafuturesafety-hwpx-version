"""형 회사 파일럿 1회 시딩 스크립트.

실행 전에 아래 PILOT_* 값을 실제 회사명/영문 slug/직원 이메일로 바꿔서 실행한다.
실행: `python -m server.seed_pilot` (DATABASE_URL 환경변수가 Postgres를 가리키는 상태에서)

이미 같은 slug의 회사가 있으면 아무것도 안 하고 끝난다 — 재실행해도 안전(중복 생성 안 됨)."""

from __future__ import annotations

import getpass
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.db import Base, SessionLocal, engine
from core.models_web import Company, User
from server.api.security import hash_password

PILOT_COMPANY_NAME = "형회사"  # TODO: 실제 회사명으로 교체
PILOT_COMPANY_SLUG = "hyung-company"  # TODO: 서브도메인으로 쓸 영문 slug로 교체 (예: hyungcompany)
PILOT_EMPLOYEE_EMAILS = [
    "employee1@example.com",
    "employee2@example.com",
    "employee3@example.com",
    "employee4@example.com",
    "employee5@example.com",
]  # TODO: 실제 직원 이메일 5개로 교체


def main() -> None:
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        existing = db.query(Company).filter(Company.slug == PILOT_COMPANY_SLUG).first()
        if existing is not None:
            print(f"이미 존재하는 회사입니다: {existing.name} (id={existing.id}) — 아무것도 안 함.")
            return

        company = Company(name=PILOT_COMPANY_NAME, slug=PILOT_COMPANY_SLUG)
        db.add(company)
        db.commit()
        db.refresh(company)
        print(f"회사 생성: {company.name} (id={company.id})")

        for email in PILOT_EMPLOYEE_EMAILS:
            password = getpass.getpass(f"{email} 초기 비밀번호 입력: ")
            db.add(
                User(
                    company_id=company.id,
                    email=email,
                    password_hash=hash_password(password),
                    display_name=email.split("@")[0],
                )
            )
        db.commit()
        print(f"직원 {len(PILOT_EMPLOYEE_EMAILS)}명 계정 생성 완료.")


if __name__ == "__main__":
    main()
