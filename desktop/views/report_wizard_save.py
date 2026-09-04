"""ReportWizardView의 저장(DB 반영) / 산출물 생성(PDF·한글) 로직.

report_wizard_view.py에서 분리됨. _SaveGenerateMixin은 그 자체로는 동작하지 않고,
ReportWizardView가 이 믹스인을 상속해 self.xxx 위젯들의 값을 읽어 DB에 반영하거나
파일로 내보낸다.

워드(DOCX) 생성은 당분간 보고서 미리보기 흐름에서 빠져있다 — 필요해지면
core/report_builder.build_report_docx를 다시 연결하면 된다(그대로 남아있음). 한글(.hwp)은
Sub-phase 8부터 `build_report_hwp`(실제 서식 파일을 템플릿으로 재사용)로 지원한다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.db import BASE_DIR, SessionLocal
from core.models_db import (
    CurrentProcessEntry,
    Finding,
    Measurement,
    PreviousFinding,
    ProcessHazardEntry,
    ProvidedMaterial,
    Report,
    SafetyEducation,
    Site,
    SiteProcessDefault,
)
from core.report_builder import build_report
from core.report_builder_hwp import build_report_hwp
from desktop.dialogs.report_preview_dialog import ReportPreviewDialog
from desktop.widgets.signature_pad import move_or_reference
from desktop.workers.ai_worker import AIWorker, with_com


def _build_pdf_for_export(report_id: int, chosen_path: Path) -> Path:
    build_report(report_id, chosen_path)
    with SessionLocal() as session:
        report = session.get(Report, report_id)
        report.pdf_path = str(chosen_path)
        session.commit()
    return chosen_path


def _build_hwp_for_export(report_id: int, chosen_path: Path) -> Path:
    build_report_hwp(report_id, chosen_path)
    with SessionLocal() as session:
        report = session.get(Report, report_id)
        report.hwpx_path = str(chosen_path)
        session.commit()
    return chosen_path


class _SaveGenerateMixin:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _save(self, navigate: bool = True) -> None:
        if self._site_id is None:
            return

        with SessionLocal() as session:
            if self._report_id:
                report = session.get(Report, self._report_id)
            else:
                report = Report(site_id=self._site_id, visit_no=self.visit_no_input.value())
                session.add(report)

            report.visit_no = self.visit_no_input.value()
            report.guidance_date = self.guidance_date_input.date().toPyDate()
            report.prev_guidance_date = (
                None if self.prev_date_none_check.isChecked() else self.prev_date_input.date().toPyDate()
            )
            report.progress_rate = self.progress_input.value()
            report.assigned_staff_id = self.staff_combo.currentData()
            report.special_note = self.special_note_edit.toPlainText()
            report.findings_na = self.findings_header.na_button.isChecked()
            report.previous_findings_na = self.previous_header.na_button.isChecked()
            report.measurements_na = self.measurement_header.na_button.isChecked()
            report.materials_na = self.materials_header.na_button.isChecked()
            report.hazard_factors_na = self.hazard_header.na_button.isChecked()
            report.process_na = self.process_header.na_button.isChecked()
            report.major_hazard_na = self.major_hazard_header.na_button.isChecked()
            report.equipment_checks_na = self.equipment_header.na_button.isChecked()
            report.current_process_na = self.current_process_header.na_button.isChecked()
            report.notification_method = self.notification_method()
            report.notify_signee_name = self.notify_signee_input.text().strip()

            report.misc_overwork = self.misc_overwork_check.isChecked()
            report.misc_no_photo = self.misc_no_photo_check.isChecked()
            report.misc_other = self.misc_other_check.isChecked()
            report.misc_other_text = self.misc_other_input.text().strip()
            if self.accident_yes_check.isChecked():
                report.accident_status = "유"
            elif self.accident_no_check.isChecked():
                report.accident_status = "무"
            else:
                report.accident_status = ""
            report.accident_content = self.accident_content_input.text().strip()

            session.flush()

            notify_sig_final = BASE_DIR / "data" / "signatures" / f"report_{report.id}_notify.png"
            moved = move_or_reference(self.notify_signature_pad, notify_sig_final)
            if moved:
                report.notify_signature_path = moved
                report.notify_signature_source = self.notify_signature_pad.source

            existing_education = session.query(SafetyEducation).filter_by(report_id=report.id).first()
            attendee_text = self.attendee_input.text().strip()
            attendee_count = int(attendee_text) if attendee_text.isdigit() else None
            if existing_education:
                existing_education.photo_path = self.education_photo.photo_path
                existing_education.attendee_count = attendee_count
                existing_education.na_flag = self.education_header.na_button.isChecked()
                existing_education.location = self.education_location_input.text().strip()
                existing_education.content = self.education_content_input.text().strip()
                existing_education.material = self.education_material_input.text().strip()
            else:
                session.add(
                    SafetyEducation(
                        report_id=report.id,
                        photo_path=self.education_photo.photo_path,
                        attendee_count=attendee_count,
                        na_flag=self.education_header.na_button.isChecked(),
                        location=self.education_location_input.text().strip(),
                        content=self.education_content_input.text().strip(),
                        material=self.education_material_input.text().strip(),
                    )
                )

            session.query(Finding).filter_by(report_id=report.id).delete()
            for slot_widget in self.finding_slots:
                if not slot_widget.has_data():
                    continue
                session.add(
                    Finding(
                        report_id=report.id,
                        slot=slot_widget.slot,
                        photo_path=slot_widget.photo.photo_path,
                        description=slot_widget.description_input.text(),
                        title=slot_widget.title_input.text(),
                        content=slot_widget.content_edit.toPlainText(),
                        law_citation=slot_widget.law_input.text(),
                        likelihood=slot_widget.likelihood_buttons.value(),
                        severity=slot_widget.severity_buttons.value(),
                    )
                )

            session.query(PreviousFinding).filter_by(report_id=report.id).delete()
            active_previous = [s for s in self.previous_slots if s.is_active()]
            for slot_widget in active_previous:
                session.add(
                    PreviousFinding(
                        report_id=report.id,
                        slot=slot_widget.slot,
                        photo_path=slot_widget.photo.photo_path,
                        title=slot_widget.title_input.text(),
                        content=slot_widget.content_edit.toPlainText(),
                        action_result=slot_widget.action_input.text(),
                        confirmed=slot_widget.confirm_btn.isChecked(),
                        risk_level=slot_widget.risk_level(),
                    )
                )
            report.prev_guidance_implemented = (
                all(s.confirm_btn.isChecked() for s in active_previous) if active_previous else None
            )

            session.query(Measurement).filter_by(report_id=report.id).delete()
            for row in self.measurement_rows:
                if row.photo.photo_path or row.value_input.text().strip():
                    session.add(
                        Measurement(
                            report_id=report.id,
                            instrument_type=row.instrument_type,
                            photo_path=row.photo.photo_path,
                            value=row.value_input.text().strip(),
                        )
                    )

            session.query(ProvidedMaterial).filter_by(report_id=report.id).delete()
            for idx, material in enumerate(self._selected_materials, start=1):
                session.add(
                    ProvidedMaterial(report_id=report.id, slot=idx, material_id=material.id, title=material.title)
                )

            checked_factor_ids: list[str] = []
            for number, checkbox in self.hazard_checkboxes.items():
                if checkbox.isChecked():
                    checked_factor_ids.append(str(number))
            for number, line_checkboxes in self.hazard_line_checkboxes.items():
                for line_index, line_checkbox in enumerate(line_checkboxes):
                    if line_checkbox.isChecked():
                        checked_factor_ids.append(f"{number}-{line_index}")
            report.hazard_factor_checks = checked_factor_ids

            report.major_hazard_work_checks = [
                idx for idx, checkbox in enumerate(self.major_hazard_checkboxes) if checkbox.isChecked()
            ]
            report.machinery_checks = [
                {"checked": row.checkbox.isChecked(), "notes": row.evaluations()} for row in self.machinery_rows
            ]
            report.hand_tool_checks = [
                {"checked": row.checkbox.isChecked(), "notes": row.evaluations()} for row in self.hand_tool_rows
            ]
            report.hazmat_checks = [
                {"checked": row.checkbox.isChecked(), "notes": row.evaluations()} for row in self.hazmat_rows
            ]

            session.query(CurrentProcessEntry).filter_by(report_id=report.id).delete()
            for row in self.current_process_slots:
                if not row.has_data():
                    continue
                session.add(
                    CurrentProcessEntry(
                        report_id=report.id,
                        slot=row.slot,
                        process_name=row.name_input.text(),
                        hazard_text=row.hazard_edit.toPlainText(),
                        prevention_text=row.prevention_edit.toPlainText(),
                        risk_level=row.risk_level(),
                    )
                )

            session.query(ProcessHazardEntry).filter_by(report_id=report.id).delete()
            for process_slot in self.process_slots:
                if not process_slot.has_data():
                    continue
                session.add(
                    ProcessHazardEntry(
                        report_id=report.id,
                        slot=process_slot.slot,
                        process_name=process_slot.name_input.text(),
                        hazard_text=process_slot.hazard_edit.toPlainText(),
                        prevention_text=process_slot.prevention_edit.toPlainText(),
                        risk_level=process_slot.risk_level(),
                    )
                )

            # 12대 기인물 체크 상태와 진행공정은 현장에 저장해서 다음 회차에 자동 승계한다.
            site = session.get(Site, self._site_id)
            site.hazard_factor_checks = checked_factor_ids
            # 관리번호는 현장 단위로 고정 — 1회차에서만 입력값을 site에 반영, 이후 회차는 손대지 않는다.
            if report.visit_no <= 1:
                site.management_no = self.management_no_input.text().strip()
            session.query(SiteProcessDefault).filter_by(site_id=self._site_id).delete()
            for process_slot in self.process_slots:
                if not process_slot.has_data():
                    continue
                session.add(
                    SiteProcessDefault(
                        site_id=self._site_id,
                        slot=process_slot.slot,
                        process_name=process_slot.name_input.text(),
                        hazard_text=process_slot.hazard_edit.toPlainText(),
                        prevention_text=process_slot.prevention_edit.toPlainText(),
                        risk_level=process_slot.risk_level(),
                    )
                )

            session.commit()
            report_id = report.id

        self._report_id = report_id
        if navigate:
            self.report_saved.emit(self._site_id)

    def _on_confirm_toggled(self, checked: bool) -> None:
        self.generate_btn.setEnabled(checked)

    def _build_and_store_pdf(self, report_id: int) -> Path:
        """report_id의 PDF를 앱이 관리하는 고정 위치에 만들고, 그 경로를 Report에 저장한다.

        미리보기 모달이 "이 내용으로 PDF 재생성"을 누를 때마다 호출하므로, 매번 저장
        위치를 물어보지 않도록 고정 경로(`data/reports/site_<site_id>/report_<id>.pdf`)를
        쓴다. 이 경로가 현장상세 화면의 보고서 이력 "↓ PDF" 버튼이 여는 파일이 된다.
        """
        output_path = BASE_DIR / "data" / "reports" / f"site_{self._site_id}" / f"report_{report_id}.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        build_report(report_id, output_path)
        with SessionLocal() as session:
            report = session.get(Report, report_id)
            report.pdf_path = str(output_path)
            session.commit()
        return output_path

    def _export_pdf_as(self, on_finished=None) -> None:
        """사용자가 고른 위치에 PDF를 저장한다. 파일명은 "{현장명}_{회차}회차.pdf"를 기본값으로
        제안한다 (예: "코하이젠 군포부곡 수소충전소 구축공사_1회차.pdf").

        PDF 생성이 한글 자동화를 거치면서 몇 초 걸리므로(체감 지연 원인) 백그라운드에서
        돌린다 — 완료/실패는 메시지박스로 알린다. `on_finished`가 있으면 성공/실패/취소
        **어느 경우에도** 정확히 한 번 불러준다(호출자가 "작업 중" 상태를 안전하게 풀 수
        있도록 — 미리보기 창의 "PDF 생성"/"한글 파일 생성" 버튼이 이걸로 바쁨 표시를 관리한다)."""
        if not self._report_id:
            if on_finished:
                on_finished(None)
            return
        default_name = f"{self.site_name_label.text()}_{self.visit_no_input.value()}회차.pdf"
        default_path = str(Path.home() / "Desktop" / default_name)
        chosen, _ = QFileDialog.getSaveFileName(self, "PDF로 저장", default_path, "PDF 파일 (*.pdf)")
        if not chosen:
            if on_finished:
                on_finished(None)
            return
        chosen_path = Path(chosen)
        if chosen_path.suffix.lower() != ".pdf":
            chosen_path = chosen_path.with_suffix(".pdf")

        report_id = self._report_id
        self._export_worker = AIWorker(with_com(lambda: _build_pdf_for_export(report_id, chosen_path)))

        def _ok(path):
            QMessageBox.information(self, "저장 완료", f"PDF를 저장했습니다:\n{path}")
            if on_finished:
                on_finished(path)

        def _err(msg):
            QMessageBox.warning(self, "PDF 생성 실패", msg)
            if on_finished:
                on_finished(None)

        self._export_worker.finished_ok.connect(_ok)
        self._export_worker.finished_error.connect(_err)
        self._export_worker.start()

    def _export_hwp_as(self, on_finished=None) -> None:
        """사용자가 고른 위치에 한글(.hwp) 파일을 저장한다. `_export_pdf_as`와 동일한
        기본 파일명 규칙 + 백그라운드 실행 + `on_finished` 규칙을 쓴다."""
        if not self._report_id:
            if on_finished:
                on_finished(None)
            return
        default_name = f"{self.site_name_label.text()}_{self.visit_no_input.value()}회차.hwp"
        default_path = str(Path.home() / "Desktop" / default_name)
        chosen, _ = QFileDialog.getSaveFileName(self, "한글 파일로 저장", default_path, "한글 파일 (*.hwp)")
        if not chosen:
            if on_finished:
                on_finished(None)
            return
        chosen_path = Path(chosen)
        if chosen_path.suffix.lower() != ".hwp":
            chosen_path = chosen_path.with_suffix(".hwp")

        report_id = self._report_id
        self._export_worker = AIWorker(with_com(lambda: _build_hwp_for_export(report_id, chosen_path)))

        def _ok(path):
            QMessageBox.information(self, "저장 완료", f"한글 파일을 저장했습니다:\n{path}")
            if on_finished:
                on_finished(path)

        def _err(msg):
            QMessageBox.warning(self, "한글 파일 생성 실패", msg)
            if on_finished:
                on_finished(None)

        self._export_worker.finished_ok.connect(_ok)
        self._export_worker.finished_error.connect(_err)
        self._export_worker.start()

    def _open_preview(self) -> None:
        # 미리보기는 마법사를 떠나지 않고 반복해서 열어볼 수 있어야 하므로(수정하기 →
        # 다시 미리보기), 여기서는 site_detail로 되돌아가는 report_saved를 emit하지 않는다.
        self._save(navigate=False)
        if not self._report_id:
            return
        dialog = ReportPreviewDialog(self)
        dialog.exec()
