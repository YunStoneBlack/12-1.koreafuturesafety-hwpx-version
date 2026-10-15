"""SafetyMan 자동 실행 — sfm 파일 열기 → 평가수행 → 숨은 엑셀 결과(시트 값 2차원) → 저장 안 하고 닫기.
43차 요령: 엑셀 "인증 마법사" 창은 보이는 즉시 닫음(COM 막힘), 이미지 경로는 이 PC 파일, Ctrl+A는 다른 이름 저장이라 쓰지 않음."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import psutil
import pythoncom
import win32com.client
import win32con
import win32gui
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

ROOT = Path(r"C:\Users\윤석현1\Documents\카카오톡 받은 파일\정밀점검 레퍼런스")
EXE = ROOT / "out" / "SafetyMan.exe"
TITLE = "종합평가 시스템"


def _wins():
    return Desktop(backend="win32").windows()


def main_win(timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in _wins():
            try:
                if TITLE in w.window_text():
                    return w
            except Exception:
                pass
        time.sleep(0.3)
    raise RuntimeError("SafetyMan 창이 안 뜸")


def msgboxes():
    out = []
    for w in _wins():
        try:
            if w.is_visible() and w.class_name() == "#32770" and w.window_text() in ("SafetyMan", "건축물 종합평가 시스템"):
                out.append(w)
        except Exception:
            pass
    return out


def close_msgboxes(answer_no=False):
    texts = []
    for w in msgboxes():
        txt = " ".join(c.window_text() for c in w.descendants() if c.class_name() == "Static" and c.window_text())
        texts.append(txt)
        btns = [c for c in w.descendants() if c.class_name() == "Button"]
        pick = None
        if answer_no:
            pick = next((c for c in btns if "아니" in c.window_text() or "No" in c.window_text()), None)
        pick = pick or (btns[0] if btns else None)
        if pick:
            try:
                pick.click()
            except Exception:
                pick.click_input()
        time.sleep(0.4)
    return texts


def kill_all():
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").upper()
        if n in ("SAFETYMAN.EXE", "EXCEL.EXE"):
            try:
                p.kill()
            except Exception:
                pass
    time.sleep(1.0)


class Wizard:
    """엑셀 인증 마법사 닫기(다른 스레드)."""

    def __init__(self):
        self.stop = False
        self.n = 0
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        def cb(h, _):
            try:
                if win32gui.IsWindowVisible(h) and "인증 마법사" in win32gui.GetWindowText(h):
                    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                    self.n += 1
            except Exception:
                pass
        while not self.stop:
            try:
                win32gui.EnumWindows(cb, None)
            except Exception:
                pass
            time.sleep(0.03)


def open_file(sfm: Path, settle: float = 2.0):
    """SafetyMan 띄워 sfm 열기 → 주 창(최대화). 안내 창이 뜨면 글을 돌려줌."""
    subprocess.Popen([str(EXE)], cwd=str(ROOT))
    m = main_win()
    time.sleep(1.5)
    m.set_focus()
    try:
        m.maximize()
    except Exception:
        pass
    send_keys("^o")
    dlg = None
    for _ in range(30):
        time.sleep(0.3)
        dlg = next((w for w in _wins() if w.class_name() == "#32770" and w.is_visible() and ("열기" in w.window_text() or "Open" in w.window_text())), None)
        if dlg:
            break
    if dlg is None:
        raise RuntimeError("열기 창이 안 뜸")
    dlg.set_focus()
    next(c for c in dlg.descendants() if c.class_name() == "Edit").set_edit_text(str(sfm))
    time.sleep(0.3)
    send_keys("{ENTER}")
    time.sleep(settle)
    return main_win(), close_msgboxes()


def run(sfm: Path, settle: float = 2.0) -> list[list]:
    """sfm 열어 평가수행 → Sheet1 값(행 목록). SafetyMan·엑셀은 끝나면 모두 끔."""
    kill_all()
    wz = Wizard()
    try:
        subprocess.Popen([str(EXE)], cwd=str(ROOT))
        m = main_win()
        time.sleep(1.5)
        m.set_focus()
        send_keys("^o")
        dlg = None
        for _ in range(30):
            time.sleep(0.3)
            dlg = next((w for w in _wins() if w.class_name() == "#32770" and w.is_visible() and ("열기" in w.window_text() or "Open" in w.window_text())), None)
            if dlg:
                break
        if dlg is None:
            raise RuntimeError("열기 창이 안 뜸")
        dlg.set_focus()
        next(c for c in dlg.descendants() if c.class_name() == "Edit").set_edit_text(str(sfm))
        time.sleep(0.3)
        send_keys("{ENTER}")
        time.sleep(settle)
        t = close_msgboxes()
        if t:
            print("   열 때 안내:", t)
        m = main_win()
        m.set_focus()
        tree = next(c for c in m.descendants() if c.class_name() == "SysTreeView32")
        tree.roots()[0].click_input()
        time.sleep(0.4)
        send_keys("%"); time.sleep(0.25); send_keys("{RIGHT}"); time.sleep(0.25); send_keys("{DOWN}"); time.sleep(0.3)
        send_keys("{ENTER}")
        vals, last, same = None, -1, 0
        t0 = time.time()
        while time.time() - t0 < 90:
            time.sleep(1.0)
            if msgboxes():
                print("   평가 안내:", close_msgboxes())
            try:
                pythoncom.CoInitialize()
                x = win32com.client.GetActiveObject("Excel.Application")
                if x.Workbooks.Count:
                    v = x.Workbooks(1).Sheets(1).UsedRange.Value
                    n = sum(1 for r in (v or ()) for c in r if c not in (None, ""))
                    same = same + 1 if n == last and n > 60 else 0
                    last = n
                    vals = [list(r) for r in v] if v else None
                    if same >= 3:  # 채운 칸 수가 3초 동안 그대로 = 끝
                        break
            except Exception:
                pass
        return vals or []
    finally:
        wz.stop = True
        kill_all()
