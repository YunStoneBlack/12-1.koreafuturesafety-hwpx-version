"""ReportWizardView의 저장(DB 반영) / 산출물 생성(PDF·DOCX·HWPX) 로직.

report_wizard_view.py에서 분리됨. _SaveGenerateMixin은 그 자체로는 동작하지 않고,
ReportWizardView가 이 믹스인을 상속해 self.xxx 위젯들의 값을 읽어 DB에 반영하거나
파일로 내보낸다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.constants import FIXED_HAZARD_FACTORS
from core.db import SessionLocal
from core.hwpx_exporter import HwpxExportError, convert_docx_to_hwpx
from core.models_db import (
    Finding,
    Measurement,
    OverviewPhoto,
    PreviousFinding,
    ProcessHazardEntry,
    ProvidedMaterial,
    Report,
    SafetyEducation,
    Site,
    SiteProcessDefault,
)
from core.report_builder import build_report, build_report_docx


class _SaveGenerateMixin:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _save(self, navigate: bool = True) -> None:
        if self._site_id is None:
            return

        with SessionLocal() as session:
            if self._report_id:
                report = session.get(Report, self._report_id)
            else:
                report = Report(site_id=self._site_id, visit_no=int(self.visit_no_label.text()))
                session.add(report)

            report.guidance_date = self.guidance_date_input.date().toPyDate()
            report.progress_rate = self.progress_input.value()
            report.assigned_staff_id = self.staff_combo.currentData()
            report.special_note = self.special_note_edit.toPlainText()
            report.overview_na = self.overview_header.na_button.isChecked()
            report.findings_na = self.findings_header.na_button.isChecked()
            report.previous_findings_na = self.previous_header.na_button.isChecked()
            report.measurements_na = self.measurement_header.na_button.isChecked()
            report.materials_na = self.materials_header.na_button.isChecked()
            report.hazard_factors_na = self.hazard_header.na_button.isChecked()
            report.process_na = self.process_header.na_button.isChecked()

            session.flush()

            session.query(OverviewPhoto).filter_by(report_id=report.id).delete()
            for slot, zone in ((1, self.overview_photo_1), (2, self.overview_photo_2)):
                if zone.photo_path:
                    session.add(OverviewPhoto(report_id=report.id, slot=slot, photo_path=zone.photo_path))

            existing_education = session.query(SafetyEducation).filter_by(report_id=report.id).first()
            attendee_text = self.attendee_input.text().strip()
            attendee_count = int(attendee_text) if attendee_text.isdigit() else None
            if existing_education:
                existing_education.photo_path = self.education_photo.photo_path
                existing_education.attendee_count = attendee_count
                existing_education.na_flag = self.education_header.na_button.isChecked()
            else:
                session.add(
                    SafetyEducation(
                        report_id=report.id,
                        photo_path=self.education_photo.photo_path,
                        attendee_count=attendee_count,
                        na_flag=self.education_header.na_button.isChecked(),
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

            checked_factor_numbers = [
                number
                for checkbox, (number, _name, _action) in zip(self.hazard_checkboxes, FIXED_HAZARD_FACTORS)
                if checkbox.isChecked()
            ]
            report.hazard_factor_checks = checked_factor_numbers

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
            site.hazard_factor_checks = checked_factor_numbers
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

    def _generate_pdf(self) -> None:
        self._save(navigate=False)
        if not self._report_id:
            return

        default_dir_name = f"{self.site_name_label.text()}_{self.visit_no_label.text()}회차"
        directory = QFileDialog.getExistingDirectory(self, "보고서 저장 위치 선택")
        if not directory:
            return

        base_path = Path(directory) / default_dir_name
        generated: list[str] = []
        failed: list[str] = []

        try:
            pdf_path = build_report(self._report_id, f"{base_path}.pdf")
            generated.append(f"PDF: {pdf_path}")
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여줄 에러 메시지
            failed.append(f"PDF 생성 실패: {e}")
            pdf_path = None

        try:
            docx_path = build_report_docx(self._report_id, f"{base_path}.docx")
            generated.append(f"워드(DOCX): {docx_path}")
        except Exception as e:  # noqa: BLE001
            failed.append(f"워드(DOCX) 생성 실패: {e}")
            docx_path = None

        if docx_path is not None:
            try:
                hwpx_path = convert_docx_to_hwpx(docx_path, f"{base_path}.hwpx")
                generated.append(f"한글(HWPX): {hwpx_path}")
            except HwpxExportError as e:
                failed.append(f"한글(HWPX) 생성 실패: {e}")

        message = "다음 파일이 생성되었습니다:\n" + "\n".join(generated) if generated else ""
        if failed:
            message += ("\n\n" if message else "") + "실패한 항목:\n" + "\n".join(failed)
        QMessageBox.information(self, "보고서 생성 결과", message or "생성된 파일이 없습니다.")

        if pdf_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
        self.report_saved.emit(self._site_id)
