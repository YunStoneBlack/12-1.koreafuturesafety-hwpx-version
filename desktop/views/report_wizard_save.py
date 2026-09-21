"""ReportWizardView의 저장(DB 반영) / 산출물 생성(PDF·한글) 로직.

report_wizard_view.py에서 분리됨. _SaveGenerateMixin은 그 자체로는 동작하지 않고,
ReportWizardView가 이 믹스인을 상속해 self.xxx 위젯들의 값을 읽어 DB에 반영하거나
파일로 내보낸다.

워드(DOCX) 생성은 당분간 보고서 미리보기 흐름에서 빠져있다 — 필요해지면
core/report_builder.build_report_docx를 다시 연결하면 된다(그대로 남아있음). 한글(.hwpx)
내보내기는 Sub-phase 19부터 COM 없는 `build_report_hwpx`(python-hwpx)를 쓴다 — PDF
생성/미리보기는 python-hwpx에 PDF 변환 기능이 없어 여전히 `build_report_hwp`(COM)를 거친다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from core.db import BASE_DIR, SessionLocal
from core.models_db import (
    CurrentProcessEntry,
    CurrentProcessHazardItem,
    Finding,
    InspectionPhoto,
    Measurement,
    OverviewPhoto,
    PreviousFinding,
    ProcessHazardEntry,
    ProcessHazardItem,
    ProvidedMaterial,
    Report,
    SafetyEducation,
    Site,
    SiteProcessDefault,
)
from core.report_builder import build_report
from desktop.dialogs.report_preview_dialog import ReportPreviewDialog
from desktop.views.report_export import export_report_file
from desktop.widgets.photo_drop_zone import copy_photo_to_storage
from desktop.widgets.signature_pad import move_or_reference


class _SaveGenerateMixin:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _save(self, navigate: bool = True, validate: bool = True) -> bool:
        """마법사 내용을 DB에 저장한다. 저장했으면 True, 검증에 걸려 막았거나 저장할 게 없으면 False
        — 호출부는 False면 미리보기/내보내기 등 뒤따르는 동작을 이어가면 안 된다.

        `validate`(기본 켜짐)일 때 저장을 막는 경고(`report_wizard_validation._ValidationMixin`)가 있으면
        마법사 순서상 첫 번째 한 종류만 띄우고 저장하지 않는다(사용자 요청, 2026-09-21). 서명 단독
        저장처럼 도중 저장에는 끈다."""
        if self._site_id is None:
            return False

        if validate and self._show_validation_warning():
            return False

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
            report.overview_na = self.overview_header.na_button.isChecked()
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

            # 사진 원본이 드롭박스/네이버박스 같은 동기화 폴더에 있으면 나중에 이 경로로
            # 다시 읽으려 할 때 실패할 수 있어(2026-09-18, 실사용 중 발견 — 모든 사진이
            # 안 들어가는 버그의 원인), 저장 시점에 앱 데이터 폴더로 한 번 복사해둔다
            # (서명에 이미 쓰던 `move_or_reference`와 같은 이유). 복사가 실패해도 저장
            # 자체는 계속 진행하되(사용자가 입력한 다른 내용까지 날리면 안 되므로), 실패한
            # 사진 목록을 모아 저장이 끝난 뒤 사용자에게 콕 집어 알려준다 — 예전처럼
            # 조용히 실패해서 원인을 못 찾는 일이 없도록.
            photo_copy_failures: list[str] = []
            photo_dir = BASE_DIR / "data" / "photos" / f"report_{report.id}"

            def _stored_photo(source_path: str, slug: str, label: str) -> str:
                if not source_path:
                    return ""
                filename = f"{slug}{Path(source_path).suffix.lower()}"
                try:
                    return copy_photo_to_storage(source_path, photo_dir / filename)
                except OSError as e:
                    photo_copy_failures.append(f"{label}: {e}")
                    return source_path

            notify_sig_final = BASE_DIR / "data" / "signatures" / f"report_{report.id}_notify.png"
            moved = move_or_reference(self.notify_signature_pad, notify_sig_final)
            if moved:
                report.notify_signature_path = moved
                report.notify_signature_source = self.notify_signature_pad.source

            existing_education = session.query(SafetyEducation).filter_by(report_id=report.id).first()
            attendee_text = self.attendee_input.text().strip()
            attendee_count = int(attendee_text) if attendee_text.isdigit() else None
            education_photo_path = _stored_photo(self.education_photo.photo_path, "education", "안전교육 사진")
            if existing_education:
                existing_education.photo_path = education_photo_path
                existing_education.attendee_count = attendee_count
                existing_education.na_flag = self.education_header.na_button.isChecked()
                existing_education.location = self.education_location_input.text().strip()
                existing_education.content = self.education_content_input.text().strip()
                existing_education.material = self.education_material_input.text().strip()
            else:
                session.add(
                    SafetyEducation(
                        report_id=report.id,
                        photo_path=education_photo_path,
                        attendee_count=attendee_count,
                        na_flag=self.education_header.na_button.isChecked(),
                        location=self.education_location_input.text().strip(),
                        content=self.education_content_input.text().strip(),
                        material=self.education_material_input.text().strip(),
                    )
                )

            session.query(OverviewPhoto).filter_by(report_id=report.id).delete()
            for slot_widget in self.overview_photo_slots:
                if not slot_widget.is_active() or not slot_widget.photo.photo_path:
                    continue
                photo_path = _stored_photo(
                    slot_widget.photo.photo_path, f"overview_{slot_widget.slot}", f"전경사진 {slot_widget.slot}번"
                )
                session.add(OverviewPhoto(report_id=report.id, slot=slot_widget.slot, photo_path=photo_path))

            session.query(InspectionPhoto).filter_by(report_id=report.id).delete()
            for slot_widget in self.inspection_photo_slots:
                if not slot_widget.is_active() or not slot_widget.photo.photo_path:
                    continue
                photo_path = _stored_photo(
                    slot_widget.photo.photo_path, f"inspection_{slot_widget.slot}", f"점검사진 {slot_widget.slot}번"
                )
                session.add(InspectionPhoto(report_id=report.id, slot=slot_widget.slot, photo_path=photo_path))

            session.query(Finding).filter_by(report_id=report.id).delete()
            for slot_widget in self.finding_slots:
                if not slot_widget.has_data():
                    continue
                finding_photo_path = _stored_photo(
                    slot_widget.photo.photo_path, f"finding_{slot_widget.slot}", f"지적사항 사진 {slot_widget.slot}번"
                )
                session.add(
                    Finding(
                        report_id=report.id,
                        slot=slot_widget.slot,
                        photo_path=finding_photo_path,
                        description=slot_widget.description_input.text(),
                        title=slot_widget.title_input.text(),
                        content=slot_widget.content_edit.toPlainText(),
                        law_citation=slot_widget.law_input.text(),
                        likelihood=slot_widget.likelihood_buttons.value(),
                        severity=slot_widget.severity_buttons.value(),
                        action_status=slot_widget.action_status(),
                    )
                )

            session.query(PreviousFinding).filter_by(report_id=report.id).delete()
            active_previous = [s for s in self.previous_slots if s.is_active()]
            for slot_widget in active_previous:
                manual_likelihood, manual_severity = slot_widget.before_risk()
                previous_photo_path = _stored_photo(
                    slot_widget.photo.photo_path, f"previous_{slot_widget.slot}", f"이전지적사항 사진 {slot_widget.slot}번"
                )
                completion_photo_path = _stored_photo(
                    slot_widget.completion_photo.photo_path,
                    f"previous_{slot_widget.slot}_completion",
                    f"이전지적사항 {slot_widget.slot}번 이행완료 사진",
                )
                session.add(
                    PreviousFinding(
                        report_id=report.id,
                        slot=slot_widget.slot,
                        photo_path=previous_photo_path,
                        title=slot_widget.title_input.text(),
                        content=slot_widget.content_edit.toPlainText(),
                        result_status=slot_widget.result_status(),
                        source_finding_id=slot_widget.source_finding_id,
                        completion_photo_path=completion_photo_path,
                        manual_likelihood=manual_likelihood,
                        manual_severity=manual_severity,
                    )
                )
            report.prev_guidance_implemented = (
                all(s.result_status() == "이행완료" for s in active_previous) if active_previous else None
            )

            session.query(Measurement).filter_by(report_id=report.id).delete()
            for row in self.measurement_rows:
                if row.photo.photo_path or row.value_input.text().strip():
                    measurement_photo_path = _stored_photo(
                        row.photo.photo_path, f"measurement_{row.instrument_type}", f"{row.instrument_type} 사진"
                    )
                    session.add(
                        Measurement(
                            report_id=report.id,
                            instrument_type=row.instrument_type,
                            photo_path=measurement_photo_path,
                            value=row.value_input.text().strip(),
                            manual_verdict=row.verdict(),
                            manual_action=row.action_input.text().strip(),
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

            # 벌크 delete()는 ORM cascade를 안 타서 이 엔트리에 딸린 항목(items) 자식 행이
            # 고아로 남는다 — 인스턴스를 하나씩 지워야 relationship의
            # cascade="all, delete-orphan"이 실제로 작동해 자식 행까지 같이 지워진다.
            for old_entry in session.query(CurrentProcessEntry).filter_by(report_id=report.id).all():
                session.delete(old_entry)
            for row in self.current_process_slots:
                if not row.has_data():
                    continue
                current_process_photo_path = _stored_photo(
                    row.photo.photo_path, f"current_process_{row.slot}", f"현재 진행공정 사진 {row.slot}번"
                )
                entry = CurrentProcessEntry(
                    report_id=report.id,
                    slot=row.slot,
                    process_name=row.name_input.text(),
                    photo_path=current_process_photo_path,
                )
                entry.items = [
                    CurrentProcessHazardItem(
                        order=i, hazard=item["hazard"], prevention=item["prevention"], risk_level=item["risk_level"]
                    )
                    for i, item in enumerate(row.items_data(), start=1)
                ]
                session.add(entry)

            for old_entry in session.query(ProcessHazardEntry).filter_by(report_id=report.id).all():
                session.delete(old_entry)
            for process_slot in self.process_slots:
                if not process_slot.has_data():
                    continue
                process_photo_path = _stored_photo(
                    process_slot.photo.photo_path, f"process_{process_slot.slot}", f"향후 진행공정 사진 {process_slot.slot}번"
                )
                entry = ProcessHazardEntry(
                    report_id=report.id,
                    slot=process_slot.slot,
                    process_name=process_slot.name_input.text(),
                    photo_path=process_photo_path,
                )
                entry.items = [
                    ProcessHazardItem(
                        order=i, hazard=item["hazard"], prevention=item["prevention"], risk_level=item["risk_level"]
                    )
                    for i, item in enumerate(process_slot.items_data(), start=1)
                ]
                session.add(entry)

            # 12대 기인물 체크 상태와 진행공정은 현장에 저장해서 다음 회차에 자동 승계한다.
            site = session.get(Site, self._site_id)
            site.hazard_factor_checks = checked_factor_ids
            # 관리번호는 현장 단위로 공유되는 값이지만 어느 회차에서 수정해도 이 현장
            # 전체에 반영된다(사용자 요청 — 이전엔 1회차에서만 반영되고 이후 회차는
            # 수정해도 무시됐다).
            site.management_no = self.management_no_input.text().strip()
            # 공정명만 승계한다 — 사진·유해위험요인·예방대책은 AI가 그때그때 사진을 보고
            # 새로 작성하는 값이라, 지난 회차 것을 그대로 승계하면 현장 상태가 바뀌었는데도
            # 옛 위험요인이 남아있는 오해를 살 수 있다(사용자 요청, Sub-phase 20).
            session.query(SiteProcessDefault).filter_by(site_id=self._site_id).delete()
            for process_slot in self.process_slots:
                if not process_slot.has_data():
                    continue
                session.add(
                    SiteProcessDefault(
                        site_id=self._site_id,
                        slot=process_slot.slot,
                        process_name=process_slot.name_input.text(),
                    )
                )

            session.commit()
            report_id = report.id

        self._report_id = report_id
        if photo_copy_failures:
            # 예전엔 이 복사가 아예 없어서 실패가 조용히 사라지고 사진만 안 보였다
            # (2026-09-18, 실사용 배포판에서 발견) — 저장 자체는 그대로 성공시키되, 어떤
            # 사진이 왜 실패했는지 반드시 화면에 알린다.
            QMessageBox.warning(
                self,
                "사진 저장 실패",
                "다음 사진을 앱 폴더로 복사하지 못해 보고서에 반영되지 않았습니다:\n\n"
                + "\n".join(photo_copy_failures)
                + "\n\n드롭박스·네이버박스 등 동기화 폴더에 있는 사진이면, 완전히 다운로드된"
                " 상태인지 확인한 뒤 사진을 다시 선택해 저장해주세요.",
            )
        if navigate:
            self.report_saved.emit(self._site_id)
        return True

    def _on_save_button_clicked(self) -> None:
        """하단 "저장" 버튼 전용 핸들러 — 미리보기 창 안에서 자동으로 저장할 때
        (`_regenerate` 등, `navigate=False`로 직접 `_save()`를 부름)는 조용히 저장만 하고,
        사용자가 이 버튼을 직접 눌렀을 때만 "저장되었습니다" 안내를 띄운다(사용자 요청,
        2026-09-11) — 그동안 눌러도 반응이 없어 보인다는 피드백이 있었다. `navigate=False`로
        불러 저장 후에도 현장으로 돌아가지 않고 마법사 화면에 그대로 머문다(사용자 요청) —
        `_save()` 기본값(`navigate=True`)은 `report_saved`를 emit해 현장상세로 돌아가는데,
        저장 버튼을 직접 눌렀을 땐 계속 마법사에서 이어서 작업하고 싶어한다.

        미리보기가 비모달로 바뀌면서(`_open_preview`) 미리보기 창을 띄운 채로 마법사에서
        계속 내용을 고칠 수 있게 됐다 — 그 상태에서 이 저장 버튼을 누르면 열려 있는
        미리보기도 최신 내용으로 같이 갱신한다(사용자 요청, 미리보기 자체의 "미리보기
        갱신" 버튼을 또 누를 필요 없이)."""
        if not self._save(navigate=False):
            return
        if self._preview_dialog is not None:
            self._preview_dialog.refresh_from_wizard()
        QMessageBox.information(self, "저장 완료", "저장되었습니다.")

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
        """사용자가 고른 위치에 PDF를 저장한다. 파일명 기본값은 "{현장명}_{회차}회차.pdf"
        (예: "코하이젠 군포부곡 수소충전소 구축공사_1회차.pdf"). 실제 흐름(저장 위치 묻기 → 백그라운드 생성 +
        진행 창 → 완료 안내, `on_finished` 정확히 한 번 호출)은 `report_export.export_report_file` 공통."""
        if not self._report_id:
            if on_finished:
                on_finished(None)
            return
        export_report_file(
            self, self._report_id, "pdf", f"{self.site_name_label.text()}_{self.visit_no_input.value()}회차", on_finished
        )

    def _export_hwp_as(self, on_finished=None) -> None:
        """사용자가 고른 위치에 한글(.hwpx) 파일을 저장한다. `_export_pdf_as`와 같은 규칙 — COM 없는 신규
        엔진(`build_report_hwpx`)을 쓰므로 `with_com` 래핑이 필요 없다."""
        if not self._report_id:
            if on_finished:
                on_finished(None)
            return
        export_report_file(
            self, self._report_id, "hwpx", f"{self.site_name_label.text()}_{self.visit_no_input.value()}회차", on_finished
        )

    def _open_preview(self) -> None:
        # 미리보기는 마법사를 떠나지 않고 반복해서 열어볼 수 있어야 하므로(수정하기 →
        # 다시 미리보기), 여기서는 site_detail로 되돌아가는 report_saved를 emit하지 않는다.
        if not self._save(navigate=False) or not self._report_id:
            return

        if self._preview_dialog is not None:
            # 이미 열려 있으면 새로 안 만들고 그 창을 앞으로 가져오기만 한다 — 안 그러면
            # "미리보기" 버튼을 여러 번 눌렀을 때 창이 계속 쌓인다.
            self._preview_dialog.raise_()
            self._preview_dialog.activateWindow()
            return

        dialog = ReportPreviewDialog(self)
        # 비모달로 띄운다 — 미리보기를 열어둔 채로 마법사 창을 옮기거나 스크롤하거나 내용을
        # 계속 수정할 수 있어야 한다는 사용자 요청(이전엔 exec()라 마법사가 완전히 막혔다).
        # 내용을 고치면 마법사 "저장" 버튼(`_on_save_button_clicked`)이나 미리보기 자체의
        # "미리보기 갱신" 버튼으로 다시 반영하면 된다.
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.finished.connect(self._on_preview_dialog_closed)
        self._preview_dialog = dialog
        dialog.show()

    def _on_preview_dialog_closed(self, _result: int) -> None:
        self._preview_dialog = None
