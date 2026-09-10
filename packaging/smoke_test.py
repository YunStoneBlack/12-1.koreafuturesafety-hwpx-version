"""exe로 얼린(frozen) 상태에서 실제 한글 자동화 파이프라인이 동작하는지 확인하는 1회성
스모크 테스트 — GUI를 못 띄우는 환경에서 클릭 없이 검증하려고 만들었다. 임시 Site/Report를
만들어 실제 PDF를 뽑아본 뒤 결과를 콘솔에 찍는다.
"""

from __future__ import annotations

import sys
import traceback

print("BASE_DIR/DB_PATH 확인 중...")
from core.db import BASE_DIR, DB_PATH, SessionLocal, init_db  # noqa: E402

print("BASE_DIR:", BASE_DIR)
print("DB_PATH:", DB_PATH)

init_db()

from core.models_db import Report, Site  # noqa: E402

with SessionLocal() as session:
    site = Site(name="스모크테스트 현장", management_no="TEST-0001")
    session.add(site)
    session.commit()
    report = Report(site_id=site.id, visit_no=1)
    session.add(report)
    session.commit()
    report_id = report.id

print("테스트용 Site/Report 생성 완료, report_id =", report_id)

from core.report_builder_hwp import build_report_pdf_via_hwp, HwpBuildError  # noqa: E402

out_path = BASE_DIR / "smoke_test_output.pdf"
try:
    build_report_pdf_via_hwp(report_id, out_path)
    print("성공: PDF 생성됨 ->", out_path, "(존재:", out_path.exists(), ")")
except HwpBuildError as e:
    print("실패(HwpBuildError):", e)
    traceback.print_exc()
    sys.exit(1)
except Exception as e:  # noqa: BLE001
    print("실패(예외):", e)
    traceback.print_exc()
    sys.exit(1)

# 테스트로 만든 Site/Report 정리
with SessionLocal() as session:
    session.query(Report).filter_by(id=report_id).delete()
    session.query(Site).filter_by(id=site.id).delete()
    session.commit()
print("테스트 데이터 정리 완료")
