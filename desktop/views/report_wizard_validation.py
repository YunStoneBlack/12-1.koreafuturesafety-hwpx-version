"""보고서 마법사 저장 전 검증 — 경고는 마법사 화면 순서(위→아래)대로 검사해 **가장 먼저 걸리는 한 종류만** 띄운다.

여러 경고를 한꺼번에 띄우면 복잡해서(사용자 요청, 2026-09-21), 저장 버튼을 누를 때마다 첫 번째 종류 하나만
알리고 그걸 해결한 뒤 다시 저장하면 그다음 종류가 뜬다. 같은 종류에 걸린 항목은 한 창에 모아서 적는다. 새 경고를
추가할 땐 `_validation_checks()` 목록의 마법사 순서에 맞는 자리에 한 줄만 끼우면 된다.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget

_PREVIOUS_FINDING_SECTION = "4. 이전지적사항"
_EQUIPMENT_SECTION = "6. 위험성평가 기준 및 12대 기인물 (6-3 안전조치 평가)"


class _ValidationMixin:
    """ReportWizardView 전용 — 단독으로 인스턴스화하지 않는다."""

    def _validation_checks(self) -> list:
        """(마법사 번호·제목, 검사 함수) 목록 — 화면 순서대로. 검사 함수는 문제가 없으면 None, 있으면
        (경고 본문, 문제 위치로 스크롤할 위젯)을 돌려준다."""
        return [
            (_PREVIOUS_FINDING_SECTION, self._check_previous_finding_blank),
            (_PREVIOUS_FINDING_SECTION, self._check_previous_finding_result),
            (_EQUIPMENT_SECTION, self._check_equipment_evaluation),
        ]

    def _first_validation_warning(self) -> tuple[str, str, QWidget | None] | None:
        for section, check in self._validation_checks():
            found = check()
            if found:
                body, widget = found
                return section, body, widget
        return None

    def _show_validation_warning(self) -> bool:
        """저장을 막아야 하는 경고가 있으면 첫 번째 한 종류를 띄우고 True를 돌려준다."""
        warning = self._first_validation_warning()
        if warning is None:
            return False
        section, body, widget = warning
        QMessageBox.warning(self, "확인 필요", f"[{section}]\n\n{body}")
        if widget is not None:
            self.scroll_area.ensureWidgetVisible(widget)
        return True

    # ---- 4. 이전지적사항 ----

    def _active_previous_slots(self) -> list:
        return [slot for slot in self.previous_slots if slot.is_active()]

    def _check_previous_finding_blank(self):
        """"+ 이전지적사항 추가"만 눌러 칸을 열어 두고 아무것도 안 채운 슬롯."""
        blanks = [slot for slot in self._active_previous_slots() if slot.is_blank()]
        if not blanks:
            return None
        names = ", ".join(f"{slot.slot}번" for slot in blanks)
        return f"이전지적사항 {names}: 미입력된 전회차 지적사항이 있습니다. 입력 혹은 삭제해주세요.", blanks[0]

    def _check_previous_finding_result(self):
        """내용은 있는데 이행결과(확인불가/보완필요/이행완료)를 안 고른 슬롯. 빈 슬롯은 위 검사가 먼저 잡는다."""
        missing = [slot for slot in self._active_previous_slots() if not slot.is_blank() and not slot.result_status()]
        if not missing:
            return None
        names = ", ".join(f"{slot.slot}번" for slot in missing)
        return f"이전지적사항 {names}: 이행 결과를 선택해주세요.", missing[0]

    # ---- 6-3. 건설기계장비·위험기계기구·유해위험물질 평가 ----

    def _equipment_evaluation_problems(self) -> list[tuple[str, object]]:
        """유로 체크돼 있는데 지도사항 평가(양호/미흡)를 안 고른 장비/기구/물질 (표시 이름, 행 컨트롤)."""
        problems = []
        for group, rows in (
            ("건설기계장비", self.machinery_rows),
            ("위험기계기구", self.hand_tool_rows),
            ("유해위험물질", self.hazmat_rows),
        ):
            problems.extend((f"{group} - {row.item_name}", row) for row in rows if row.missing_evaluation())
        return problems

    def _check_equipment_evaluation(self):
        problems = self._equipment_evaluation_problems()
        if not problems:
            return None
        body = (
            "유로 체크된 항목 중 평가(양호/미흡)를 고르지 않은 지도사항이 있습니다.\n"
            "모든 지도사항의 평가를 선택해주세요.\n\n"
            + "\n".join(f"· {name}" for name, _row in problems)
        )
        return body, problems[0][1].checkbox
