"""4. 이전지적사항 자동 이월 — 데스크톱 `desktop/views/report_wizard_load.py::
_reconcile_previous_findings`와 같은 규칙을 웹판(DB 직접 갱신)으로 옮긴 것.

- 직전 회차(같은 현장, 이 회차 미만 중 가장 최근)의 8번 지적사항 중 내용이 있는 것을 최대
  4건 매번 다시 읽어 슬롯 1번부터 채운다 — 원본이 그 사이 추가·삭제·수정돼도 목록을 열 때마다
  최신 구성으로 맞춘다(데스크톱과 동일한 "실시간 반영").
- 이미 이월돼 있던 항목은 같은 원본(source_finding_id)에 매칭해 이 보고서에서 입력한 후속조치
  정보(조치결과/이행완료 사진/이행 후 위험성 캐시)를 그대로 이어받는다.
- 원본 없이 직접 입력한 항목은 이월 항목 뒤 슬롯으로 보존한다. 4칸을 넘으면 데스크톱과 같이
  넘치는 수기 항목은 버린다(이월 항목 우선).

웹 8번은 행을 지우지 않고 내용만 비우는 방식이라(`findings.py`), "내용이 빈 지적사항"은
삭제된 것으로 보고 이월에서 뺀다.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from core.models_db import Finding, PreviousFinding, Report

MAX_SLOTS = 4


def _finding_has_content(finding: Finding) -> bool:
    return bool((finding.title or "").strip() or (finding.content or "").strip() or finding.photo_path)


def is_active(pf: PreviousFinding) -> bool:
    """보고서에 실제로 나갈 항목인지 — 이월 항목이거나, 수기 항목인데 뭐라도 입력돼 있는 경우."""
    return bool(
        pf.source_finding_id
        or (pf.title or "").strip()
        or (pf.content or "").strip()
        or pf.photo_path
        or pf.completion_photo_path
        or pf.result_status
    )


def owns_file(pf: PreviousFinding, path: str) -> bool:
    """이 행이 직접 업로드한 파일인지 — 이월 항목의 photo_path는 원본(직전 회차) 지적사항의
    파일이라 여기서 지우면 원본 보고서 사진이 사라진다."""
    if not path:
        return False
    if pf.source_finding_id and pf.source_finding and path == pf.source_finding.photo_path:
        return False
    return True


def _drop(db: Session, pf: PreviousFinding) -> None:
    for path in (pf.photo_path, pf.completion_photo_path):
        if owns_file(pf, path):
            Path(path).unlink(missing_ok=True)
    db.delete(pf)


def find_previous_report(db: Session, report: Report) -> Report | None:
    return (
        db.query(Report)
        .filter(Report.site_id == report.site_id, Report.visit_no < report.visit_no)
        .order_by(Report.visit_no.desc())
        .first()
    )


def _invalidate_after_cache_if_stale(pf: PreviousFinding) -> None:
    """"이행 후" 캐시가 지금의 "이행 전" 값보다 크면(원본 위험성이 그 사이 낮아짐) 다시 뽑게 비운다
    — compute_after_risk()의 "이행 후 ≤ 이행 전" 조건이 깨진 값을 계속 재사용하지 않도록."""
    before_likelihood, before_severity = pf.source_risk()
    if pf.after_likelihood is None or pf.after_severity is None:
        return
    if (
        before_likelihood is None
        or before_severity is None
        or pf.after_likelihood > before_likelihood
        or pf.after_severity > before_severity
    ):
        pf.after_likelihood = pf.after_severity = None


def sync_implemented_flag(report: Report, rows: list[PreviousFinding]) -> None:
    """표지의 "이전 기술지도 이행여부" — 데스크톱 저장 로직(report_wizard_save.py)과 같은 규칙:
    이전지적사항이 하나라도 있으면 전부 이행완료일 때만 True, 없으면 None."""
    active = [pf for pf in rows if is_active(pf)]
    report.prev_guidance_implemented = all(pf.result_status == "이행완료" for pf in active) if active else None


def reconcile_previous_findings(db: Session, report: Report) -> Report | None:
    """직전 회차 지적사항을 이 보고서의 이전지적사항 슬롯에 이월한다. 직전 회차 보고서를 반환한다
    (없으면 None — 화면 안내 문구용). 바뀐 게 있으면 커밋까지 한다."""
    prev_report = find_previous_report(db, report)
    prior: list[Finding] = []
    if prev_report is not None:
        prior = (
            db.query(Finding).filter(Finding.report_id == prev_report.id).order_by(Finding.slot).all()
        )
        prior = [f for f in prior if _finding_has_content(f)][:MAX_SLOTS]

    existing = (
        db.query(PreviousFinding)
        .filter(PreviousFinding.report_id == report.id)
        .order_by(PreviousFinding.slot)
        .all()
    )
    by_source: dict[int, PreviousFinding] = {}
    manual: list[PreviousFinding] = []
    leftovers: list[PreviousFinding] = []
    for pf in existing:
        if pf.source_finding_id and pf.source_finding_id not in by_source:
            by_source[pf.source_finding_id] = pf
        elif not pf.source_finding_id and is_active(pf):
            manual.append(pf)
        else:
            leftovers.append(pf)  # 빈 수기 칸, 같은 원본 중복 행

    ordered: list[PreviousFinding] = []
    for finding in prior:
        pf = by_source.pop(finding.id, None)
        if pf is None:
            pf = PreviousFinding(report_id=report.id, source_finding_id=finding.id)
            db.add(pf)
        # 스냅샷도 최신으로 맞춰둔다 — 렌더러는 display_fields()로 원본을 직접 읽지만, 원본이
        # 나중에 사라지면 이 스냅샷이 대신 쓰인다.
        pf.source_finding = finding
        pf.title, pf.content, pf.photo_path = finding.title, finding.content, finding.photo_path
        _invalidate_after_cache_if_stale(pf)
        ordered.append(pf)

    room = MAX_SLOTS - len(ordered)
    ordered.extend(manual[:room])
    leftovers.extend(manual[room:])
    leftovers.extend(by_source.values())  # 원본이 비워졌거나 4건 밖으로 밀려난 이월 항목

    for slot, pf in enumerate(ordered, start=1):
        pf.slot = slot
    for pf in leftovers:
        _drop(db, pf)

    sync_implemented_flag(report, ordered)
    for pf in ordered:
        pf.resolve_after_risk()  # "이행완료"면 이행 후 위험성을 1회 확정해 캐시

    if db.new or db.dirty or db.deleted:
        db.commit()
    return prev_report
