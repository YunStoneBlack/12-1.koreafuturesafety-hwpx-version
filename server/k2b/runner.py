"""K2B 제출 실행(2026-10-01) — 14번 `desktop/worker.py`의 순서 그대로: 로그인 → 기술지도 메뉴 → 현장 검색(첫 단어)·행 고르기(띄어쓰기 무시 전체 이름)
→ 상세보기 → 새 차수 추가(항상 — K2B 차수 번호와 우리 회차 번호는 별개라 기존 차수 덮어쓰기는 안 함) → 값 입력 → 사진·PDF 첨부.

웹판에서 새로: save=True면 K2B [저장] → "저장하시겠습니까?" [확인] → 저장된 새 차수 화면을 찍어 돌려준다(사용자 2026-10-01: 저장 직후가 아니라
확인 뒤 새 차수 정보가 보이는 화면). save=False면 저장 직전 화면만 찍고 끝(아무것도 저장 안 됨 — 처음 맞춰 볼 때·점검용).
화면 없는 크롬(headless)으로 이 PC에서 돈다. 단계마다 log(글)를 남기고, shots=True면 단계 화면도 찍는다(첫 실측용).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from server.k2b import selectors as sel
from server.k2b.client import K2BClient, open_browser
from server.k2b.submission import K2BSubmission


@dataclass
class RunResult:
    ok: bool
    saved: bool
    message: str
    screenshot: str = ""
    log: list[str] = field(default_factory=list)
    round_no: int | None = None  # K2B가 매긴 새 차수 번호


def _wait_popup(page, timeout_s: int = 20):
    """K2B 알림·확인 창이 뜨길 기다려 (문구, 확인 버튼 위치)를 돌려준다. 버튼 id 안에 문구가 있다(selectors.POPUP_CONFIRM_BUTTONS)."""
    for _ in range(timeout_s * 2):
        page.wait_for_timeout(500)
        found = page.evaluate("""(sel) => [...document.querySelectorAll(sel)].map(e => { const r = e.getBoundingClientRect();
            return {id: e.id, x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width}; }).filter(b => b.w > 0)""", sel.POPUP_CONFIRM_BUTTONS)
        if found:
            b = found[-1]
            text = b["id"].split("_P01_", 1)[-1].split("_form_", 1)[0] if "_P01_" in b["id"] else b["id"]
            return text, b
    return None, None


def run(sub: K2BSubmission, k2b_id: str, password: str, shot_dir: Path, save: bool = False,
        shots: bool = False, headless: bool = True, allow_round_mismatch: bool = False) -> RunResult:
    """allow_round_mismatch: K2B가 매긴 새 차수 번호가 웹 회차(sub.visit_no)와 달라도 저장할지. 기본은 다르면 저장하지 않고 멈춘다
    (사용자 2026-10-01: 실제 업무에선 웹 회차 = K2B 차수 — 다르면 이미 올렸거나 회차가 어긋난 것)."""
    lines: list[str] = []
    shot_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        lines.append(f"{datetime.datetime.now():%H:%M:%S} {msg}")

    step = [0]

    def snap(page, name: str) -> str:
        step[0] += 1
        path = shot_dir / f"{step[0]:02d}_{name}.png"
        page.screenshot(path=str(path))
        return str(path)

    playwright = browser = None
    page = None
    round_no = None
    try:
        playwright, browser, page = open_browser(headless=headless)
        page.set_default_timeout(30000)
        c = K2BClient(page, log=log)
        c.login(k2b_id, password)
        c.go_to_guidance_menu()
        page.wait_for_timeout(1500)
        c.search_site(sub.site_name)
        page.wait_for_timeout(1500)
        c.select_result_row(sub.site_name)
        page.wait_for_timeout(1000)
        if shots:
            snap(page, "현장선택")
        c.open_detail()
        page.wait_for_timeout(2500)
        if shots:
            snap(page, "상세보기")
        c.add_new_round()
        page.wait_for_timeout(1500)
        round_text = page.locator(sel.ROUND_NO_INPUT).input_value().strip()
        round_no = int(round_text) if round_text.isdigit() else None
        log(f"K2B 새 차수 번호: {round_text}")
        prev_choice = sub.manual.prev_guidance or sub.prev_guidance_auto
        if round_no and round_no > 1 and prev_choice == "해당없음":  # K2B는 해당없음을 1차수에서만 받음(실측) — 저장 누르기 전에 멈춤
            shot = snap(page, "해당없음불가")
            return RunResult(False, False, f"K2B {round_text}차수에서는 이전 기술지도 이행여부를 '해당없음'으로 낼 수 없습니다 — "
                             "'이행' 또는 '불이행'으로 바꿔 다시 제출하세요.", shot, lines, round_no)
        if round_no != sub.visit_no and not allow_round_mismatch:
            shot = snap(page, "차수다름")
            return RunResult(False, False, f"K2B 새 차수는 {round_text}차인데 웹 보고서는 {sub.visit_no}회차라 저장하지 않았습니다 — "
                             "K2B에 이미 올렸거나 회차가 어긋났는지 확인하세요(그래도 올리려면 '차수가 달라도 저장'을 켜고 다시).", shot, lines, round_no)
        if shots:
            snap(page, "차수추가")
        if sub.guidance_date:
            c.set_guidance_date(datetime.date.fromisoformat(sub.guidance_date))
        if sub.progress_rate is not None:
            c.fill_progress_rate(sub.progress_rate)
        if sub.site_manager_name:
            c.fill_site_manager_name(sub.site_manager_name)
        if sub.site_manager_phone:
            c.fill_site_manager_phone(sub.site_manager_phone)
        if sub.special_note:
            c.fill_special_note(sub.special_note)
        m = sub.manual
        if m.current_process:
            c.select_current_process(m.current_process)
        if sub.notification_method:
            c.check_notification_method(sub.notification_method)
        c.set_ceo_notice(m.ceo_notice_quarter, datetime.date.fromisoformat(m.ceo_notice_date) if m.ceo_notice_date else None)
        if m.scaffold_usage:
            c.set_scaffold_usage(m.scaffold_usage == "사용", m.scaffold_types)
        # K2B 필수 — 창에서 고른 값(manual.prev_guidance), 없으면 4번 결과로 미리 고른 값(submission.prev_guidance_auto)
        if prev_choice:
            c.check_prev_guidance_implemented(prev_choice)
        if m.owner_notice_date and prev_choice == "불이행":  # K2B가 불이행일 때만 칸을 켜 줌
            c.set_owner_notice(datetime.date.fromisoformat(m.owner_notice_date))
        c.fill_counts(sub.guidance_count, sub.education_count, sub.material_count)
        if m.bad_site_notify:
            c.notify_bad_site(m.bad_site_content, m.bad_site_files)
        for hz in m.major_hazard_works:
            c.add_major_hazard_work(hz.occurrence_type, hz.hazard_work,
                                    datetime.date.fromisoformat(hz.start_date), datetime.date.fromisoformat(hz.end_date))
        if shots:
            snap(page, "입력")
        if sub.overview_photo_paths:
            c.attach_photos("현장전경", sub.overview_photo_paths)
        if sub.inspection_photo_paths:
            c.attach_photos("현장점검", sub.inspection_photo_paths)
        if sub.improvement_photo_paths:
            c.attach_photos("현장개선", sub.improvement_photo_paths)
        if sub.report_pdf_path:
            c.attach_report_file(sub.report_pdf_path)
        c.add_problem_requests(sub.problem_texts)
        if not m.major_hazard_works:
            log("대형사고 위험작업 '해당없음' 체크")
            none_box = page.locator(sel.MAJOR_HAZARD_NONE_CHECKBOX)
            c._scroll_into_view(none_box)
            none_box.click()
        page.wait_for_timeout(1500)
        before_save = snap(page, "저장직전")
        if not save:
            log("저장하지 않고 끝냄(점검 모드)")
            return RunResult(True, False, "K2B에 입력까지 했습니다(저장 안 함 — 점검 모드).", before_save, lines, round_no)
        log("저장 누름")
        save_btn = page.locator(sel.DETAIL_SAVE_BUTTON)
        c._scroll_into_view(save_btn)
        save_btn.click()
        done = False
        for _ in range(4):  # 저장하시겠습니까? → 정상적으로 저장되었습니다. (또는 필수 칸 안내 한 개)
            text, button = _wait_popup(page)
            if text is None:
                break
            log(f"K2B 창: {text}")
            page.mouse.click(button["x"], button["y"])
            page.wait_for_timeout(1500)
            if sel.SAVE_DONE_TEXT in text:
                done = True
                break
            if sel.SAVE_ASK_TEXT not in text:
                shot = snap(page, "저장안됨")
                return RunResult(False, False, f"K2B가 저장을 막았습니다 — {text}", shot, lines, round_no)
        if not done:
            shot = snap(page, "저장확인안됨")
            return RunResult(False, False, "K2B에서 '정상적으로 저장되었습니다' 창을 못 봤습니다 — 화면을 확인하세요.", shot, lines, round_no)
        page.wait_for_timeout(2000)
        c._scroll_into_view(page.locator(sel.DETAIL_SAVE_BUTTON))  # 새 차수 정보(상세내용) 위쪽이 보이게
        page.wait_for_timeout(800)
        saved_shot = snap(page, "저장완료")
        return RunResult(True, True, f"K2B {round_no}차수로 저장했습니다.", saved_shot, lines, round_no)
    except Exception as err:  # noqa: BLE001 — 어느 단계에서 멈췄는지 화면과 함께 돌려준다
        shot = ""
        if page is not None:
            try:
                shot = snap(page, "실패")
            except Exception:  # noqa: BLE001
                pass
        log(f"실패: {err}")
        return RunResult(False, False, str(err).splitlines()[0][:300], shot, lines, round_no)
    finally:
        try:
            if browser is not None and browser.is_connected():
                browser.close()
        except Exception:  # noqa: BLE001
            pass
        if playwright is not None:
            playwright.stop()
