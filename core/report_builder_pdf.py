"""Report(회차 보고서)를 실제 표준 서식(9섹션)과 동일한 PDF로 렌더링하는 모듈 (reportlab).

레이아웃은 사용자가 실제로 쓰는 최신 기술지도 결과보고서 PDF(영중중학교 보도블록 공사
1차/2차)를 그대로 기준으로 삼았다. 관리번호·서명·결재란은 아직 넣지 않았다(다음 라운드).

섹션 구성(실제 서식과 동일한 번호):
1. 기술지도 대상사업장  2. 기술지도 개요  3. 이전 기술지도 사항 이행여부
4. 대형사고 위험작업 사항  5. 위험성평가 기준 및 사망사고 다발 기인물 필수 지도사항
   (+ 건설기계장비·위험기계기구·유해위험물질 안전조치 평가)
6. 현재 진행중인 공정 유해위험요인 파악  7. 현재 공정 내 현존하는 위험성 제거
8. 향후 진행공정에 대한 유해·위험요인 파악 및 대책  9. 사업장 지원 사항 등 기타 사항
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.constants import (
    FIXED_HAZARD_FACTORS,
    HAND_TOOL_ITEMS,
    HAZMAT_ITEMS,
    MACHINERY_EQUIPMENT_ITEMS,
    MAJOR_HAZARD_WORKS,
    MEASUREMENT_INSTRUMENTS,
    NOTIFICATION_METHODS,
)
from core.db import SessionLocal
from core.models_db import MeasurementStandard, Report
from core.report_builder_common import (
    FONT_BOLD,
    GRID,
    HEADER_BG,
    ensure_fonts,
    fmt_amount,
    fmt_date,
    p,
    scaled_image,
    section_title,
)


def _grid_style(extra: list | None = None) -> TableStyle:
    return TableStyle(GRID.getCommands() + (extra or []))


def _build_site_section(site) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")
    table = Table(
        [
            [label("현장"), label("현장명"), p(site.name), label("사업장관리번호\n(사업개시번호)"), p(f"{site.site_mgmt_no}\n{site.biz_start_no}")],
            ["", label("공사기간"), p(f"{fmt_date(site.period_start)} ~ {fmt_date(site.period_end)}"), label("공사금액"), p(fmt_amount(site.amount))],
            ["", label("책임자"), p(site.manager_name), label("연락처\n(이메일)"), p(f"{site.manager_phone}\n{site.manager_email}")],
            ["", label("주소"), p(site.address, align="LEFT"), "", ""],
            [label("본사"), label("회사명"), p(site.hq_company), label("법인등록번호\n(사업자등록번호)"), p(f"{site.corp_reg_no}\n{site.biz_reg_no}")],
            ["", label("면허번호"), p(site.license_no), label("연락처"), p(site.hq_phone)],
            ["", label("주소"), p(site.hq_address, align="LEFT"), "", ""],
        ],
        colWidths=[16 * mm, 26 * mm, 55 * mm, 30 * mm, 43 * mm],
    )
    style = _grid_style()
    style.add("SPAN", (0, 0), (0, 3))
    style.add("SPAN", (0, 4), (0, 6))
    style.add("SPAN", (2, 3), (4, 3))
    style.add("SPAN", (2, 6), (4, 6))
    style.add("BACKGROUND", (0, 0), (0, -1), HEADER_BG)
    style.add("BACKGROUND", (1, 0), (1, -1), HEADER_BG)
    style.add("BACKGROUND", (3, 0), (3, -1), HEADER_BG)
    table.setStyle(style)
    return [section_title(1, "기술지도 대상사업장"), table]


def _build_overview_meta_section(report: Report, site) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")
    guidance_type = "■ 건설 / □ 전기·정보통신"
    implemented = "□ 이행 / □ 불이행"
    if report.prev_guidance_implemented is True:
        implemented = "■ 이행 / □ 불이행"
    elif report.prev_guidance_implemented is False:
        implemented = "□ 이행 / ■ 불이행"

    method_text = " / ".join(
        f"{'■' if m == report.notification_method else '□'} {m}" for m in NOTIFICATION_METHODS
    )

    staff_name = report.assigned_staff.name if report.assigned_staff else "-"
    staff_phone = report.assigned_staff.phone if report.assigned_staff else "-"

    table = Table(
        [
            [label("지도기관명"), p("(주)한국미래안전"), label("기술지도실시일"), p(fmt_date(report.guidance_date))],
            [label("구분"), p(guidance_type), label("공정률"), p(f"({report.progress_rate or 0})%")],
            [label("횟수"), p(f"({report.visit_no})회차 / 총({site.total_guidance_count or '-'})회"), label("담당 요원"), p(staff_name)],
            [label("이전 기술지도\n이행여부"), p(implemented), label("연락처"), p(staff_phone)],
            [label("현장책임자 등\n통보방법"), p(method_text, align="LEFT"), "", ""],
            [label("기타 특이사항"), p(report.special_note, align="LEFT"), "", ""],
        ],
        colWidths=[26 * mm, 71 * mm, 26 * mm, 47 * mm],
    )
    style = _grid_style()
    style.add("SPAN", (1, 4), (3, 4))
    style.add("SPAN", (1, 5), (3, 5))
    style.add("BACKGROUND", (0, 0), (0, -1), HEADER_BG)
    style.add("BACKGROUND", (2, 0), (2, 3), HEADER_BG)
    table.setStyle(style)
    return [section_title(2, "기술지도 개요"), table]


def _build_previous_findings_section(report: Report) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")
    rows = [[label("지도일\n(확인일)"), label("유해·위험요인/\n지적사진"), label("지적사항"), label("조치내용"), label("이행결과")]]
    previous = {pf.slot: pf for pf in report.previous_findings}
    for slot in range(1, 5):
        pf = previous.get(slot)
        if pf:
            photo_cell = scaled_image(pf.photo_path, 28 * mm, 20 * mm) if pf.photo_path else p(pf.title, size=8)
            rows.append([p(fmt_date(report.guidance_date), size=8), photo_cell, p(pf.content, size=8), p(pf.action_result, size=8), p("이행" if pf.confirmed else "-", size=8)])
        else:
            rows.append(["", "", "", "", ""])
    table = Table(rows, colWidths=[20 * mm, 32 * mm, 60 * mm, 30 * mm, 20 * mm], rowHeights=[10 * mm] + [22 * mm] * 4)
    table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))
    return [section_title(3, "이전 기술지도 사항 이행여부"), table]


def _build_major_hazard_work_section(report: Report) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")
    checked = set(report.major_hazard_work_checks or [])
    rows = [[label("대형사고 위험작업 사항"), label("해당"), label("해당없음")]]
    for idx, work in enumerate(MAJOR_HAZARD_WORKS):
        is_checked = idx in checked
        rows.append(
            [
                p(work, size=8),
                p("■" if is_checked else "□", align="CENTER"),
                p("□" if is_checked else "■", align="CENTER"),
            ]
        )
    table = Table(rows, colWidths=[130 * mm, 20 * mm, 20 * mm])
    table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))
    return [section_title(4, "대형사고 위험작업 사항"), table]


def _build_risk_and_hazard_section(report: Report) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")

    matrix_rows = [
        [label("빈도/강도"), label("1"), label("2"), label("3")],
        [label("1"), p("1", align="CENTER"), p("2", align="CENTER"), p("3", align="CENTER")],
        [label("2"), p("2", align="CENTER"), p("4", align="CENTER"), p("6", align="CENTER")],
        [label("3"), p("3", align="CENTER"), p("6", align="CENTER"), p("9", align="CENTER")],
    ]
    matrix_table = Table(matrix_rows, colWidths=[18 * mm, 14 * mm, 14 * mm, 14 * mm])
    matrix_table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG), ("BACKGROUND", (0, 0), (0, -1), HEADER_BG)]))

    level_rows = [
        [label("위험성 수준"), label("관리기준")],
        [p("1~2 (하)", align="CENTER"), p("현재상태유지", align="CENTER")],
        [p("3~4 (중)", align="CENTER"), p("개선", align="CENTER")],
        [p("6~9 (상)", align="CENTER"), p("즉시개선", align="CENTER")],
    ]
    level_table = Table(level_rows, colWidths=[35 * mm, 35 * mm])
    level_table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))

    header_row = Table([[matrix_table, level_table]], colWidths=[65 * mm, 95 * mm])
    header_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    checked = set(report.hazard_factor_checks or [])
    hazard_rows = [[label("구분"), label("사망사고 다발 기인물"), label("필수 지도사항")]]
    for number, name, lines in FIXED_HAZARD_FACTORS:
        mark = "■" if str(number) in checked else "□"
        hazard_rows.append([p(mark, align="CENTER"), p(f"{number}. {name}", size=8), p(", ".join(lines), size=8)])
    hazard_table = Table(hazard_rows, colWidths=[14 * mm, 55 * mm, 91 * mm])
    hazard_table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))

    flowables: list = [
        section_title(5, "위험성평가 기준 및 사망사고 다발 기인물 필수 지도사항"),
        header_row,
        Spacer(1, 4 * mm),
        hazard_table,
        Spacer(1, 6 * mm),
    ]

    for title, items, saved in (
        ("건설기계장비에 대한 안전보건 조치 평가", MACHINERY_EQUIPMENT_ITEMS, report.machinery_checks or []),
        ("위험기계기구에 대한 안전보건 조치 평가", HAND_TOOL_ITEMS, report.hand_tool_checks or []),
        ("유해위험물질에 대한 안전보건 조치 평가", HAZMAT_ITEMS, report.hazmat_checks or []),
    ):
        rows = [[label("항목"), label("유/무"), label("필수지도사항 확인"), label("평가")]]
        for idx, (name, lines) in enumerate(items):
            entry = saved[idx] if idx < len(saved) else {}
            mark = "■" if entry.get("checked") else "□"
            note = "/".join(n for n in (entry.get("notes") or []) if n) or "-"
            rows.append(
                [p(name.replace("\n", " "), size=8), p(mark, align="CENTER"), p(", ".join(lines), size=7), p(note, size=8, align="CENTER")]
            )
        table = Table(rows, colWidths=[38 * mm, 12 * mm, 90 * mm, 20 * mm])
        table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))
        flowables += [p(title, bold=True, size=10), Spacer(1, 2 * mm), table, Spacer(1, 4 * mm)]

    return flowables


def _build_current_process_section(report: Report) -> list:
    """6. 현재 진행공정에 대한 유해위험요인 파악 및 대책 — 8번(`_build_process_section`)과
    완전히 같은 구조(진행공정/유해·위험요인/예방대책/위험성 표, 사진 없음)로 통일했다.
    원래 있던 사진 2장은 사용자 요청으로 없앴다."""
    label = lambda t: p(t, bold=True, align="CENTER")

    rows = [[label("진행공정"), label("유해·위험요인"), label("예방대책"), label("위험성수준")]]
    for entry in report.current_process_entries:
        rows.append([p(entry.process_name, size=8), p(entry.hazard_text, size=8), p(entry.prevention_text, size=8), p(entry.risk_level, size=8, align="CENTER")])
    while len(rows) < 5:
        rows.append(["", "", "", ""])
    table = Table(rows, colWidths=[30 * mm, 55 * mm, 55 * mm, 22 * mm], rowHeights=[10 * mm] + [20 * mm] * 4)
    table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))

    return [
        section_title(6, "현재 진행공정에 대한 유해·위험요인 파악 및 대책"),
        table,
    ]


def _build_current_risk_section(report: Report) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")
    rows = [[label("유해·위험요인\n지적사진"), label("지적사항(개선대책)"), label("비고")]]
    findings = {f.slot: f for f in report.findings}
    for slot in range(1, 5):
        f = findings.get(slot)
        if f:
            photo_cell = scaled_image(f.photo_path, 28 * mm, 20 * mm)
            content = f"{f.title}\n{f.content}"
            if f.law_citation:
                content += f"\n* {f.law_citation}"
            risk_text = ""
            if f.risk_score is not None:
                risk_text = f"가능성 {f.likelihood} / 중대성 {f.severity}\n위험성 {f.risk_score}"
            rows.append([photo_cell, p(content, size=8), p(risk_text, size=8, align="CENTER")])
        else:
            rows.append(["", "", ""])
    table = Table(rows, colWidths=[32 * mm, 100 * mm, 30 * mm], rowHeights=[10 * mm] + [26 * mm] * 4)
    table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))
    return [section_title(7, "현재 공정 내 현존하는 위험성 제거"), table]


def _build_process_section(report: Report) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")

    names = [e.process_name for e in report.process_entries if e.process_name]
    label_col = Table([[p("다음 방문시까지\n발생하는주요\n진행공정", bold=True, align="CENTER")]], rowHeights=[27 * mm])
    grid_rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            row.append(p(str(i + 1), align="CENTER", size=8))
            row.append(p(names[i] if i < len(names) else "", size=8))
        grid_rows.append(row)
    summary_table = Table(grid_rows, colWidths=[7 * mm, 36 * mm] * 3, rowHeights=[9 * mm] * 3)
    summary_table.setStyle(_grid_style())
    combined = Table([[label_col, summary_table]], colWidths=[24 * mm, 129 * mm])
    combined.setStyle(_grid_style())

    rows = [[label("진행공정"), label("유해·위험요인"), label("예방대책"), label("위험성수준")]]
    for entry in report.process_entries:
        rows.append([p(entry.process_name, size=8), p(entry.hazard_text, size=8), p(entry.prevention_text, size=8), p(entry.risk_level, size=8, align="CENTER")])
    while len(rows) < 5:
        rows.append(["", "", "", ""])
    process_table = Table(rows, colWidths=[30 * mm, 55 * mm, 55 * mm, 22 * mm], rowHeights=[10 * mm] + [20 * mm] * 4)
    process_table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))

    return [
        section_title(8, "향후 진행공정에 대한 유해·위험요인 파악 및 대책"),
        combined,
        Spacer(1, 4 * mm),
        process_table,
    ]


def _build_support_section(report: Report, session) -> list:
    label = lambda t: p(t, bold=True, align="CENTER")
    education = report.safety_education

    attendee_text = str(education.attendee_count) if education and education.attendee_count is not None else "-"
    tbm_photo = scaled_image(education.photo_path if education else "", 40 * mm, 30 * mm)
    tbm_table = Table(
        [[label("TBM 활성화\n지도 및\n교육실시"), p(f"○ 참석인원 : {attendee_text} 명"), tbm_photo]],
        colWidths=[26 * mm, 90 * mm, 50 * mm],
        rowHeights=[30 * mm],
    )
    tbm_table.setStyle(_grid_style([("BACKGROUND", (0, 0), (0, -1), HEADER_BG)]))

    standards = {s.instrument_type: s.standard_criteria for s in session.query(MeasurementStandard).all()}
    used_measurements = [m for m in report.measurements if m.value]
    equipment_rows = [[label("장비명"), label("측정장소"), label("측정치"), label("안전기준"), label("조치사항")]]
    for m in used_measurements:
        unit = next((u for name, u in MEASUREMENT_INSTRUMENTS if name == m.instrument_type), "")
        equipment_rows.append(
            [
                p(m.instrument_type, size=8),
                p("현장 내", align="CENTER", size=8),
                p(f"{m.value} {unit}".strip(), align="CENTER", size=8),
                p(standards.get(m.instrument_type, "-"), size=8),
                p("-", size=8),
            ]
        )
    if not used_measurements:
        equipment_rows.append([p("-", size=8)] * 5)
    equipment_table = Table(equipment_rows, colWidths=[28 * mm, 20 * mm, 25 * mm, 55 * mm, 14 * mm])
    equipment_table.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), HEADER_BG)]))

    material_names = "\n".join(f"- {m.title}" for m in report.provided_materials) or "-"

    return [
        section_title(9, "사업장 지원 사항 등 기타 사항"),
        tbm_table,
        Spacer(1, 4 * mm),
        p("장비사용", bold=True, size=10),
        Spacer(1, 2 * mm),
        equipment_table,
        Spacer(1, 4 * mm),
        p("자료배포", bold=True, size=10),
        p(material_names, size=8),
    ]


def _build_material_appendix(report: Report) -> list:
    flowables: list = []
    for material in report.provided_materials:
        source_path = material.custom_photo_path
        if not source_path and material.material:
            source_path = material.material.file_path
        if source_path and Path(source_path).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            flowables.append(PageBreak())
            flowables.append(scaled_image(source_path, 170 * mm, 250 * mm))
    return flowables


def build_report(report_id: int, output_path: str | Path) -> Path:
    """Report 하나를 실제 산출물(9섹션)과 동일한 구조의 PDF로 생성한다."""
    ensure_fonts()

    with SessionLocal() as session:
        report = session.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id}를 찾을 수 없습니다.")
        site = report.site

        story: list = []
        title_style = ParagraphStyle(name="title", fontName=FONT_BOLD, fontSize=16, alignment=1, spaceAfter=10)
        story.append(Paragraph("건설재해예방전문지도기관 기술지도 결과보고서", title_style))

        story += _build_site_section(site)
        story.append(Spacer(1, 4 * mm))
        story += _build_overview_meta_section(report, site)

        story.append(PageBreak())
        story += _build_previous_findings_section(report)

        story.append(PageBreak())
        story += _build_major_hazard_work_section(report)

        story.append(PageBreak())
        story += _build_risk_and_hazard_section(report)

        story.append(PageBreak())
        story += _build_current_process_section(report)

        story.append(PageBreak())
        story += _build_current_risk_section(report)

        story.append(PageBreak())
        story += _build_process_section(report)

        story.append(PageBreak())
        story += _build_support_section(report, session)

        story += _build_material_appendix(report)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )
        doc.build(story)

        report.pdf_path = str(output_path)
        report.status = "final"
        session.commit()

    return output_path
