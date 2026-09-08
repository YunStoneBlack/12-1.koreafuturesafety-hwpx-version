"""기존 보고서를 마법사에 불러오는 로직 — `report_wizard_view.py`에서 분리됨(691줄을
넘겨 이 프로젝트 관례상 600줄 기준으로 나눴다, 2026-09-08).

`_LoadReportMixin`은 `ReportWizardView`(report_wizard_view.py)에 섞여 들어가므로, 여기
메서드들은 그쪽에서 만든 위젯(self.previous_slots, self.finding_slots 등)과
`report_wizard_sections*.py`/`report_wizard_save.py`의 다른 메서드(`_apply_hazard_checks`,
`_refresh_signoff_previews` 등)를 자유롭게 참조한다 — 파이썬 믹스인 패턴이라 실제 실행 시
`ReportWizardView` 인스턴스에 전부 존재한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QDate

from core.models_db import PreviousFinding, Report


class _LoadReportMixin:
    def _reconcile_previous_findings(self, session, site_id: int, visit_no: int, existing_report: Report | None) -> None:
        """이전지적사항 슬롯을 채운다 — 직전 회차(이 회차 미만 중 가장 최근 회차)의 "현재"
        지적사항을 매번 다시 읽어 실시간으로 반영한다(제목·내용·사진). 직전 회차 지적사항이
        이 보고서를 저장한 뒤에 추가·삭제·수정됐어도 다시 열 때마다 그 시점의 최신 구성으로
        맞춘다 — 제목/내용만 갱신하고 개수는 그대로 두면(과거 구현) 새로 추가된 지적사항이
        영영 안 보이는 문제가 있었다(실측 확인).

        이행결과(확인불가/보완필요/이행완료)는 이 보고서에서 직접 기록하는 후속조치 정보라
        원본과 무관하다 — 이미 저장된 `PreviousFinding`이 있으면 같은 원본(source_finding_id)에
        매칭해 그대로 이어받는다. 원본 없이 "+" 버튼으로 수기 추가한 항목은 그대로 보존한다.
        """
        prev_report = (
            session.query(Report)
            .filter(Report.site_id == site_id, Report.visit_no < visit_no)
            .order_by(Report.visit_no.desc())
            .first()
        )
        prior_findings = sorted(prev_report.findings, key=lambda f: f.slot) if prev_report else []

        existing_by_source: dict[int, PreviousFinding] = {}
        manual_entries: list[PreviousFinding] = []
        if existing_report:
            for pf in existing_report.previous_findings:
                if pf.source_finding_id:
                    existing_by_source[pf.source_finding_id] = pf
                else:
                    manual_entries.append(pf)

        entries: list[dict] = []
        for finding in prior_findings[:4]:
            existing = existing_by_source.get(finding.id)
            entries.append(
                {
                    "title": finding.title,
                    "content": finding.content,
                    "photo_path": finding.photo_path,
                    "source_finding_id": finding.id,
                    "result_status": existing.result_status if existing else "",
                    "completion_photo_path": existing.completion_photo_path if existing else "",
                }
            )
        for pf in manual_entries[: max(0, 4 - len(entries))]:
            entries.append(
                {
                    "title": pf.title,
                    "content": pf.content,
                    "photo_path": pf.photo_path,
                    "source_finding_id": None,
                    "result_status": pf.result_status,
                    "completion_photo_path": pf.completion_photo_path,
                }
            )

        for slot in self.previous_slots:
            slot.clear()
            slot.set_active(False)
        for slot_widget, entry in zip(self.previous_slots, entries):
            slot_widget.set_active(True)
            if entry["photo_path"]:
                slot_widget.photo.set_photo(entry["photo_path"])
            if entry["completion_photo_path"]:
                slot_widget.completion_photo.set_photo(entry["completion_photo_path"])
            slot_widget.title_input.setText(entry["title"])
            slot_widget.content_edit.setPlainText(entry["content"])
            slot_widget.set_result_status(entry["result_status"])
            slot_widget.source_finding_id = entry["source_finding_id"]
        self._update_previous_add_btn()

        if prev_report is None:
            self.previous_hint_label.setText("1회차 보고서입니다. 이전 지적사항이 없습니다.")
        elif prior_findings:
            self.previous_hint_label.setText(
                f"{prev_report.visit_no}회차 지적사항 {len(prior_findings)}건을 이월했습니다. "
                "조치 결과를 확인하고 입력하세요."
            )
        else:
            self.previous_hint_label.setText(
                "이전 회차 지적사항이 없습니다. 직접 넣으실 항목이 있으면 아래 버튼으로 추가하세요."
            )

    def _load_existing_report(self, report: Report, session) -> None:
        """기존 보고서를 수정 모드로 불러온다 — '새 회차' 기본값을 실제 저장값으로 덮어쓴다."""
        self.visit_no_input.setValue(report.visit_no)
        if report.prev_guidance_date:
            self.prev_date_none_check.setChecked(False)
            self.prev_date_input.setDate(QDate(report.prev_guidance_date))
        else:
            self.prev_date_none_check.setChecked(True)
        self._apply_management_no_editability(
            report.visit_no, report.site.management_no if report.site else ""
        )

        self.set_notification_method(report.notification_method)
        self.notify_signee_input.setText(
            report.notify_signee_name or (report.site.manager_name if report.site else "")
        )
        if report.notify_signature_path:
            self.notify_signature_pad.load_existing(report.notify_signature_path)
            self._set_notify_signature_status(True)
        else:
            self.notify_signature_pad.clear_signature()
            self._set_notify_signature_status(False)
        self._refresh_signoff_previews(report.assigned_staff_id)

        self.misc_overwork_check.setChecked(report.misc_overwork)
        self.misc_no_photo_check.setChecked(report.misc_no_photo)
        self.misc_other_check.setChecked(report.misc_other)
        self.misc_other_input.setText(report.misc_other_text)
        self.accident_yes_check.setChecked(report.accident_status == "유")
        self.accident_no_check.setChecked(report.accident_status == "무")
        self.accident_content_input.setText(report.accident_content)

        if report.guidance_date:
            self.guidance_date_input.setDate(QDate(report.guidance_date.year, report.guidance_date.month, report.guidance_date.day))
        self.progress_input.setValue(report.progress_rate or 0)
        if report.assigned_staff_id:
            idx = self.staff_combo.findData(report.assigned_staff_id)
            if idx >= 0:
                self.staff_combo.setCurrentIndex(idx)

        major_hazard_checked = set(report.major_hazard_work_checks or [])
        for idx, checkbox in enumerate(self.major_hazard_checkboxes):
            checkbox.setChecked(idx in major_hazard_checked)
        self.major_hazard_header.set_checked(report.major_hazard_na)

        for rows, saved in (
            (self.machinery_rows, report.machinery_checks or []),
            (self.hand_tool_rows, report.hand_tool_checks or []),
            (self.hazmat_rows, report.hazmat_checks or []),
        ):
            for row, entry in zip(rows, saved):
                row.checkbox.setChecked(bool(entry.get("checked")))
                row.set_evaluations(entry.get("notes") or [])
        self.equipment_header.set_checked(report.equipment_checks_na)

        for process_slot in self.current_process_slots:
            process_slot.reset()
        current_process_by_slot = {e.slot: e for e in report.current_process_entries}
        for process_slot in self.current_process_slots:
            e = current_process_by_slot.get(process_slot.slot)
            if e:
                process_slot.load_data(
                    {
                        "process_name": e.process_name,
                        "hazard_text": e.hazard_text,
                        "prevention_text": e.prevention_text,
                        "risk_level": e.risk_level,
                    }
                )
        self.current_process_header.set_checked(report.current_process_na)

        if report.safety_education:
            if report.safety_education.photo_path:
                self.education_photo.set_photo(report.safety_education.photo_path)
            self.attendee_input.setText(
                str(report.safety_education.attendee_count) if report.safety_education.attendee_count is not None else ""
            )
            self.education_header.set_checked(report.safety_education.na_flag)
            self.education_location_input.setText(report.safety_education.location)
            self.education_content_input.setText(report.safety_education.content)
            self.education_material_input.setText(report.safety_education.material)

        findings_by_slot = {f.slot: f for f in report.findings}
        for slot_widget in self.finding_slots:
            slot_widget.set_active(False)
        for slot_widget in self.finding_slots:
            f = findings_by_slot.get(slot_widget.slot)
            if not f:
                continue
            slot_widget.set_active(True)
            if f.photo_path:
                slot_widget.photo.set_photo(f.photo_path)
            slot_widget.description_input.setText(f.description)
            slot_widget.title_input.setText(f.title)
            slot_widget.content_edit.setPlainText(f.content)
            slot_widget.law_input.setText(f.law_citation)
            slot_widget.likelihood_buttons.set_value(f.likelihood)
            slot_widget.severity_buttons.set_value(f.severity)
            slot_widget.set_action_status(f.action_status)
        self._update_finding_add_btn()
        self.findings_header.set_checked(report.findings_na)

        self.special_note_edit.setPlainText(report.special_note)

        self._reconcile_previous_findings(session, report.site_id, report.visit_no, existing_report=report)
        self.previous_header.set_checked(report.previous_findings_na)

        measurements_by_type = {m.instrument_type: m for m in report.measurements}
        for row in self.measurement_rows:
            m = measurements_by_type.get(row.instrument_type)
            if m:
                if m.photo_path:
                    row.photo.set_photo(m.photo_path)
                row.value_input.setText(m.value)
        self.measurement_header.set_checked(report.measurements_na)

        self._selected_materials = list(
            [pm.material for pm in report.provided_materials if pm.material_id and pm.material]
        )
        self._update_materials_summary()
        self.materials_header.set_checked(report.materials_na)

        self._apply_hazard_checks(set(report.hazard_factor_checks or []))
        self.hazard_header.set_checked(report.hazard_factors_na)

        for process_slot in self.process_slots:
            process_slot.reset()
        process_by_slot = {e.slot: e for e in report.process_entries}
        for process_slot in self.process_slots:
            e = process_by_slot.get(process_slot.slot)
            if e:
                process_slot.load_data(
                    {
                        "process_name": e.process_name,
                        "hazard_text": e.hazard_text,
                        "prevention_text": e.prevention_text,
                        "risk_level": e.risk_level,
                    }
                )
        self.process_header.set_checked(report.process_na)
