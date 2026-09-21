"""마법사 담당요원 선택 — 같은 지도일에 한 요원이 맡는 현장은 최대 4개(사용자 요청 2026-09-21).

규칙 자체(계산)는 `core/staff_load.py`. 여기는 화면 쪽 동작이다:
- 담당요원 목록에 그 지도일 기준 "현재 맡은 다른 현장 수/4"를 미리 표시하고, 4곳을 이미 맡은 요원은 "4/4 마감"으로 보여준다.
- 마감된 요원을 고르면 그 요원이 맡은 현장 이름을 알리는 경고창을 띄우고 선택을 되돌린다.
- 지도일을 바꿔서 지금 고른 요원이 마감이 되면 "선택 안 함"으로 되돌리고 알린다.
- 저장된 보고서를 다시 열 때는 검사하지 않는다(예전 데이터가 4곳을 넘어도 열고 저장할 수 있어야 한다). 새 보고서의 기본 담당요원(현장 기본값)이
  그날 마감이면 그때는 되돌린다.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from core.db import SessionLocal
from core.staff_load import MAX_SITES_PER_STAFF_PER_DAY, is_full, other_site_names

_BASE_TEXT_ROLE = Qt.ItemDataRole.UserRole + 1


class _StaffLimitMixin:
    _staff_limit_active = False
    _last_staff_index = 0

    def _guidance_date_py(self):
        return self.guidance_date_input.date().toPyDate()

    def _refresh_staff_combo_labels(self) -> None:
        """각 담당요원 이름 옆에 그 지도일 기준 "현재 맡은 다른 현장 수/4"(가득 차면 "4/4 마감")를 붙인다."""
        date = self._guidance_date_py()
        combo = self.staff_combo
        combo.blockSignals(True)
        try:
            with SessionLocal() as session:
                for index in range(combo.count()):
                    staff_id = combo.itemData(index)
                    if staff_id is None:
                        continue
                    base = combo.itemData(index, _BASE_TEXT_ROLE) or combo.itemText(index)
                    combo.setItemData(index, base, _BASE_TEXT_ROLE)
                    names = other_site_names(session, staff_id, date, self._site_id)
                    suffix = f" · {MAX_SITES_PER_STAFF_PER_DAY}/{MAX_SITES_PER_STAFF_PER_DAY} 마감" if is_full(names) else f" · {len(names)}/{MAX_SITES_PER_STAFF_PER_DAY}"
                    combo.setItemText(index, base + suffix)
        finally:
            combo.blockSignals(False)

    def _full_site_names(self, staff_id) -> list[str] | None:
        """그 요원이 이 지도일에 이미 마감이면 맡은 현장 이름 목록, 아니면 None."""
        if staff_id is None:
            return None
        with SessionLocal() as session:
            names = other_site_names(session, staff_id, self._guidance_date_py(), self._site_id)
        return names if is_full(names) else None

    def _warn_staff_full(self, staff_index: int, names: list[str]) -> None:
        staff_label = self.staff_combo.itemData(staff_index, _BASE_TEXT_ROLE) or self.staff_combo.itemText(staff_index)
        staff_name = staff_label.split(" (")[0]
        date_text = self._guidance_date_py().strftime("%Y-%m-%d")
        listing = "\n".join(f"  • {name}" for name in names)
        QMessageBox.warning(
            self,
            "담당요원 배정 불가",
            f"{staff_name} 담당요원은 {date_text}에 이미 {MAX_SITES_PER_STAFF_PER_DAY}개 현장을 맡고 있어 "
            f"더 맡을 수 없습니다.\n\n{listing}\n\n다른 담당요원을 선택하거나 지도일을 바꿔 주세요.",
        )

    def _on_staff_changed(self, index: int) -> None:
        """담당요원 콤보 선택 — 마감된 요원이면 경고 후 직전 선택으로 되돌린다."""
        if self._staff_limit_active:
            names = self._full_site_names(self.staff_combo.itemData(index))
            if names is not None:
                self._warn_staff_full(index, names)
                self.staff_combo.blockSignals(True)
                self.staff_combo.setCurrentIndex(self._last_staff_index)
                self.staff_combo.blockSignals(False)
                self._refresh_signoff_previews(self.staff_combo.currentData())
                return
        self._last_staff_index = self.staff_combo.currentIndex()
        self._refresh_signoff_previews(self.staff_combo.currentData())

    def _on_guidance_date_changed(self, *_args) -> None:
        """지도일을 바꾸면 목록 표시를 다시 계산하고, 지금 고른 요원이 마감이 되면 "선택 안 함"으로 되돌린다."""
        if not self._staff_limit_active:
            return
        self._refresh_staff_combo_labels()
        index = self.staff_combo.currentIndex()
        names = self._full_site_names(self.staff_combo.itemData(index))
        if names is not None:
            self._warn_staff_full(index, names)
            self.staff_combo.setCurrentIndex(0)  # "선택 안 함" — _on_staff_changed가 되돌림 기록·서명 미리보기 갱신

    def _activate_staff_limit(self, *, check_current: bool) -> None:
        """`load_for_site`가 끝난 뒤 호출 — 이제부터의 변경을 검사하고 목록 표시를 계산한다.
        `check_current`(새 보고서)면 기본 담당요원이 그 지도일에 마감인지도 확인한다."""
        self._staff_limit_active = True
        self._refresh_staff_combo_labels()
        self._last_staff_index = self.staff_combo.currentIndex()
        if check_current:
            index = self.staff_combo.currentIndex()
            names = self._full_site_names(self.staff_combo.itemData(index))
            if names is not None:
                self._warn_staff_full(index, names)
                self.staff_combo.setCurrentIndex(0)
