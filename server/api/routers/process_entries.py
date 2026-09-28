"""7. 현재 진행공정 / 9. 향후 진행공정에 대한 유해·위험요인 파악 및 대책 (각 최대 4공정).

데스크톱(`desktop/views/report_wizard_sections2.py::_build_current_process_section`)도
"9번과 완전히 같은 방식(공정명 + 항목별 유해요인/예방대책/위험성)"이라고 명시하고 있고,
원래 있던 사진 업로드도 9번과 맞추려고 없앴다 — 그래서 `_build_process_router()` 하나로
7번(`CurrentProcessEntry`/`CurrentProcessHazardItem`)/9번(`ProcessHazardEntry`/
`ProcessHazardItem`) 라우터를 둘 다 찍어낸다(Sub-phase 36의 photos.py와 같은 패턴).

"✨ AI로 작성"은 `ai.py`의 `POST /reports/{id}/ai/process-hazards`(결과를 화면에 채우기만 하고
저장은 여기 PATCH로)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.models_db import CurrentProcessEntry, CurrentProcessHazardItem, ProcessHazardEntry, ProcessHazardItem
from core.models_web import User
from server.api import repo
from server.api.report_defaults import record_site_process_name
from server.api.deps import get_current_user, get_db
from server.schemas.process_entry import ProcessEntryIn, ProcessEntryOut

_SLOT_RANGE = range(1, 5)


def _build_process_router(category: str, entry_model, item_model, record_site_default: bool = False) -> APIRouter:
    """`record_site_default`: 9번(향후 진행공정)만 — 공정명을 현장에 기록해 다음 회차가 이어받는다
    (데스크톱과 같이 7번 현재 진행공정은 승계 안 함, report_defaults.py 참고)."""
    router = APIRouter(prefix=f"/reports/{{report_id}}/{category}", tags=["process"])

    def _require_report(db: Session, company_id: int, report_id: int):
        report = repo.get_report(db, company_id, report_id)
        if report is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다.")
        return report

    def _to_out(slot: int, entry) -> ProcessEntryOut:
        if entry is None:
            return ProcessEntryOut(slot=slot)
        return ProcessEntryOut(
            slot=slot,
            process_name=entry.process_name,
            items=[{"hazard": i.hazard, "prevention": i.prevention, "risk_level": i.risk_level} for i in entry.items],
        )

    @router.get("", response_model=list[ProcessEntryOut])
    def list_entries(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        _require_report(db, user.company_id, report_id)
        return [_to_out(slot, repo.get_process_entry(db, entry_model, report_id, slot)) for slot in _SLOT_RANGE]

    @router.patch("/{slot}", response_model=ProcessEntryOut)
    def update_entry(
        report_id: int,
        slot: int,
        body: ProcessEntryIn,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        report = _require_report(db, user.company_id, report_id)
        if slot not in _SLOT_RANGE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~4여야 합니다.")
        entry = repo.upsert_process_entry(
            db, entry_model, item_model, report_id, slot, body.process_name, [i.model_dump() for i in body.items]
        )
        if record_site_default:
            record_site_process_name(db, report, slot, body.process_name)
        return _to_out(slot, entry)

    return router


current_process_router = _build_process_router("current-process", CurrentProcessEntry, CurrentProcessHazardItem)
future_process_router = _build_process_router(
    "future-process", ProcessHazardEntry, ProcessHazardItem, record_site_default=True
)
