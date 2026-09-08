"""pyhwpx COM 자동화가 남기는 숨은(visible=False) 한글 프로세스를 정리한다.

`Hwp(visible=False, ...)`로 띄운 프로세스가 `quit()`(+ `gc.collect()` + `sleep(0.5)`,
`report_builder_hwp.py` 참고) 후에도 완전히 안 죽고 남아있는 경우가 가끔 있다(근본 원인
미파악, 작업내용.md의 "알려진 이슈" 참고). 이 상태로 남아있으면, 나중에 새 `Hwp()` 세션을
띄우거나 사용자가 .hwp 파일을 직접 열 때 윈도우가 이 숨은 프로세스를 재사용해버려 — 창이
전혀 안 뜨는 것처럼 보이는 문제로 이어진다.

원인을 고치는 대신, 매번 새 자동화 세션을 시작하기 직전(과 앱 시작 시)에 "창이 하나도 안
보이는" Hwp.exe 프로세스를 미리 청소한다 — 그러면 다음 `Hwp()` 호출이 좀비를 재사용할 일이
없다.

**안전장치**: 창이 하나라도 실제로 보이는(`IsWindowVisible`) 프로세스는 절대 건드리지 않는다
— 사용자가 직접 열어서 작업 중인 진짜 한글 창을 실수로 죽이면 안 되기 때문이다. 실측 확인:
`visible=False`로 띄운 자동화 세션은 메인 문서창을 포함해 모든 창이 `IsWindowVisible=False`로
뜬다 — 그래서 이 판별 기준이 유효하다. (반대로, 자동화 세션이 지금 이 순간 실제로 빌드
작업 중이어도 창은 여전히 안 보이는 상태다 — 이 모듈은 항상 "새 세션을 시작하기 직전"에만
호출해서, 아직 만들지도 않은 우리 자신의 새 프로세스를 실수로 죽일 여지를 없앤다. 이 앱은
버튼 비활성화로 보고서 빌드를 한 번에 하나씩만 진행하므로, 다른 스레드의 진행 중인 빌드를
잘못 죽일 동시성 위험도 낮다.)
"""

from __future__ import annotations

import subprocess

import win32gui
import win32process

_PROCESS_NAME = "Hwp.exe"


def _hwp_pids() -> set[int]:
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {_PROCESS_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        fields = [f.strip('"') for f in line.strip().split(",")]
        if len(fields) >= 2 and fields[0].lower() == _PROCESS_NAME.lower():
            try:
                pids.add(int(fields[1]))
            except ValueError:
                continue
    return pids


def _pids_with_visible_window() -> set[int]:
    """창이 하나라도 보이는 프로세스의 PID 집합 — 전체 창을 한 번만 훑어서 구한다(PID마다
    따로 `EnumWindows`를 돌리면 프로세스 수만큼 창 전체를 반복해서 훑게 된다)."""
    visible: set[int] = set()

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            visible.add(pid)
        return True

    win32gui.EnumWindows(_cb, None)
    return visible


def kill_orphaned_hwp_processes() -> int:
    """창이 하나도 안 보이는 Hwp.exe 프로세스를 강제 종료하고, 종료한 개수를 반환한다.

    앱 시작 시(`desktop/main.py`)와 새 자동화 세션을 만들기 직전(`report_builder_hwp.py`
    `_fill_and_save`)에 호출한다.
    """
    orphans = _hwp_pids() - _pids_with_visible_window()
    if not orphans:
        return 0
    args = ["taskkill", "/F"]
    for pid in orphans:
        args += ["/PID", str(pid)]
    subprocess.run(args, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return len(orphans)
