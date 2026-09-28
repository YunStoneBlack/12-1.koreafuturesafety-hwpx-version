"""7. 현재 진행공정 / 9. 향후 진행공정에 대한 유해·위험요인 파악 및 대책 (각 최대 4공정).

데스크톱(`desktop/views/report_wizard_sections2.py::_build_current_process_section`)도
"9번과 완전히 같은 방식(공정명 + 항목별 유해요인/예방대책/위험성)"이라고 명시하고 있고,
원래 있던 사진 업로드도 9번과 맞추려고 없앴다 — 그래서 `_build_process_router()` 하나로
7번(`CurrentProcessEntry`/`CurrentProcessHazardItem`)/9번(`ProcessHazardEntry`/
`ProcessHazardItem`) 라우터를 둘 다 찍어낸다(Sub-phase 36의 photos.py와 같은 패턴).

**이번 1차 포팅 범위 밖(의도적으로 미룸)**: 데스크톱은 공정 사진을 Claude Vision으로 분석해
유해요인/예방대책/위험성 항목을 자동 생성하는 "AI로 작성" 버튼이 있다. 지금은 항목을
수동으로 입력·추가·삭제하는 것만 지원 — 모델의 `items` 구조 자체가 AI 결과든 수동 입력이든
똑같이 담기게 설계되어 있어(순서만 있는 평범한 목록), 나중에 AI 버튼을 추가해도 지금 만든
수동 입력 UI/데이터와 충돌하지 않는다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.models_db import CurrentProcessEntry, CurrentProcessHazardItem, ProcessHazardEntry, ProcessHazardItem
from core.models_web import User
from server.api import repo
from server.api.deps import get_current_user, get_db
from server.schemas.process_entry import ProcessEntryIn, ProcessEntryOut

_SLOT_RANGE = range(1, 5)


def _build_process_router(category: str, entry_model, item_model) -> APIRouter:
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
        _require_report(db, user.company_id, report_id)
        if slot not in _SLOT_RANGE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "slot은 1~4여야 합니다.")
        entry = repo.upsert_process_entry(
            db, entry_model, item_model, report_id, slot, body.process_name, [i.model_dump() for i in body.items]
        )
        return _to_out(slot, entry)

    return router


current_process_router = _build_process_router("current-process", CurrentProcessEntry, CurrentProcessHazardItem)
future_process_router = _build_process_router("future-process", ProcessHazardEntry, ProcessHazardItem)
