# -*- coding: utf-8 -*-
"""K2BClient: 불량사업장 통보, 사진/보고서 파일 첨부.

`core/k2b_client.py`의 600줄 초과 문제로 기능별 분리한 파일 중 하나(2026-09-16).
내용/셀렉터/실기록 주석은 원본에서 그대로 옮겼다."""
from __future__ import annotations

import datetime
from pathlib import Path

from server.k2b import selectors as sel
from server.k2b.base import K2BClientBase, ReportModificationExpiredError


class AttachmentMixin(K2BClientBase):
    def notify_bad_site(self, content: str, file_paths: list[str | Path] | None = None) -> None:
        """"불량사업장 통보" 체크박스를 켜고 신고내용을 입력한 뒤 파일을 첨부한다.

        주의: 이 체크박스는 클릭할 때마다 토글되고(값을 직접 읽어 켜져있는지 판별할 방법을
        못 찾음, CSS만으로는 체크 여부가 구분 안 됨), "+ 추가"로 만든 새 차수는 기본
        미체크 상태라고 가정한다(TODO: 기존 차수를 그대로 편집하는 경우 이미 체크돼있을
        수 있어 이 메서드가 실수로 꺼버릴 위험 -- 그런 경우는 미검증).

        신고내용 입력 방식이 특이하다(CONFIRMED, 2026-09-16): 실제 `<textarea>` 요소는
        Nexacro가 항상 `visibility:hidden`으로 그려서(이 영역을 가상 스크롤로 렌더링하는
        것으로 추정, 체크 여부와 무관하게 항상 이 상태) Playwright의 click()/fill()이
        "element is not visible"로 거부한다. 대신 바로 바깥의 보이는 컨테이너를 클릭해
        포커스만 주고, 실제 텍스트 입력은 키보드 이벤트(`page.keyboard`)로 보낸다 --
        이렇게 하면 내부 textarea 값에 정상 반영됨을 확인함."""
        page = self.page
        self.log("불량사업장 통보 체크 중...")
        checkbox = page.locator(sel.BAD_SITE_NOTIFY_CHECKBOX_ID)
        self._scroll_into_view(checkbox)
        checkbox.click()

        if content:
            self.log("불량사업장 신고내용 입력 중...")
            container = page.locator(sel.BAD_SITE_NOTIFY_CONTENT_CONTAINER_ID)
            self._scroll_into_view(container)
            container.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.type(content)

        if file_paths:
            self.log(f"불량사업장 첨부파일 {len(file_paths)}개 업로드 중...")
            button = page.locator(sel.BAD_SITE_NOTIFY_ATTACH_BUTTON_ID)
            self._scroll_into_view(button)
            with page.expect_file_chooser() as fc_info:
                button.click()
            fc_info.value.set_files([str(p) for p in file_paths])

    # K2B 자체 제약(실사용 중 발견, CONFIRMED, 2026-09-17): 파일선택창 한 번에 5개 이상
    # 고르면 "5건 이상의 파일 업로드는 허용되지 않습니다" 팝업으로 거부하고 아무것도
    # 첨부되지 않는다(부분첨부 아님, 전체 취소). "지적사항 사진" 등을 현장점검사진에
    # 합쳐 올리게 되면서(db_reader.py 참고) 4장을 넘는 경우가 실제로 생겨 발견함.
    # 그래서 한 번에 최대 4개씩 나눠 "사진첨부" 버튼을 여러 번 눌러 첨부한다.
    _MAX_FILES_PER_ATTACH = 4

    def attach_photos(self, category: str, file_paths: list[str | Path]) -> None:
        """category: '현장전경' | '현장점검' | '현장개선'

        사진첨부 버튼 클릭 -> 파일 선택창(file chooser)에서 다중 파일 선택(CONFIRMED,
        실제 파일 업로드까지 end-to-end 검증됨). 4장 초과 시 자동으로 여러 번 나눠 누른다."""
        button_id = sel.PHOTO_ATTACH_BUTTON_IDS.get(category)
        if button_id is None:
            raise ValueError(f"알 수 없는 사진 카테고리: {category}")
        if not file_paths:
            return
        self.log(f"{category} 사진 {len(file_paths)}장 첨부 중...")
        page = self.page
        button = page.locator(button_id).get_by_text(sel.PHOTO_ATTACH_BUTTON_TEXT)
        for i in range(0, len(file_paths), self._MAX_FILES_PER_ATTACH):
            chunk = file_paths[i : i + self._MAX_FILES_PER_ATTACH]
            self._scroll_into_view(button)
            with page.expect_file_chooser() as fc_info:
                button.click()
            file_chooser = fc_info.value
            file_chooser.set_files([str(p) for p in chunk])

    def attach_report_file(self, file_path: str | Path) -> None:
        """12-1에서 생성된 실제 결과보고서(PDF/hwpx) 파일을 "보고서" 섹션에 첨부한다.

        주의(CONFIRMED, 실제 화면에서 확인): 기술지도일 이후 7일이 지나면 보고서 수정이
        불가능해지고 이 버튼도 비활성화된다 -- 클릭해도 아무 반응 없이 파일선택창이 안
        뜬다(실사용 중 재현: 기존 차수를 그대로 열어 편집했다가 기한이 지나 있어서
        "Timeout ... waiting for event filechooser"만 나고 원인을 스크롤 문제로 착각한
        적 있음 -- 진짜 원인은 이 기한이었다). 그래서 실제 첨부 전에 기한을 먼저 확인해
        지났으면 명확한 예외를 던진다."""
        page = self.page
        deadline_text = page.locator(sel.REPORT_MODIFIABLE_UNTIL_INPUT_ID).input_value().strip()
        if deadline_text:
            try:
                deadline = datetime.date.fromisoformat(deadline_text)
                if deadline < datetime.date.today():
                    raise ReportModificationExpiredError(
                        f"보고서 수정가능 기한({deadline_text})이 지나 파일첨부 버튼이 "
                        f"비활성화되어 있습니다. 이 차수를 그대로 편집하는 대신 '새 차수로 "
                        f"추가'로 진행하세요(새 차수는 기술지도일이 오늘로 자동 설정되어 "
                        f"기한 안에 들어옵니다)."
                    )
            except ValueError:
                pass  # 날짜 형식이 예상과 다르면 확인을 건너뛰고 그냥 시도한다

        self.log(f"보고서 파일 첨부 중: {file_path}")
        button = page.locator(sel.REPORT_FILE_ATTACH_BUTTON_ID).get_by_text(sel.REPORT_FILE_ATTACH_BUTTON_TEXT)
        self._scroll_into_view(button)
        with page.expect_file_chooser() as fc_info:
            button.click()
        file_chooser = fc_info.value
        file_chooser.set_files(str(file_path))
