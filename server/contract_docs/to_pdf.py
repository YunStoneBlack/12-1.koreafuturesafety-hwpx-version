"""엑셀 → PDF(LibreOffice, 2026-10-06). 이 PC의 Excel은 정품 인증이 안 돼 자동화가 인증 창에 막힌다 — LibreOffice는 무료라 형 회사 PC로
옮길 때도 설치만 하면 된다. 경로는 .env.server의 SOFFICE_PATH(없으면 기본 설치 위치).

한 번에 하나씩(잠금) — LibreOffice는 같은 사용자 설정 폴더로 동시에 두 개를 띄우면 하나가 조용히 실패한다. 사용자가 LibreOffice를 열어 둬도
부딪히지 않게 설정 폴더를 따로 쓴다(-env:UserInstallation). 실패하면 다른 방법으로 대신하지 않고 그대로 알린다(보고서 PDF와 같은 원칙).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from core.db import DATA_DIR

_LOCK = threading.Lock()
_PROFILE = DATA_DIR / "_시스템" / "libreoffice_profile"
_CANDIDATES = [r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]


def soffice_path() -> str:
    env = os.environ.get("SOFFICE_PATH", "").strip()
    for p in ([env] if env else []) + _CANDIDATES:
        if p and Path(p).exists():
            return p
    found = shutil.which("soffice")
    if found:
        return found
    raise RuntimeError("LibreOffice가 없어 PDF를 만들 수 없습니다 — LibreOffice를 설치하세요(엑셀 파일은 받을 수 있습니다).")


def xlsx_to_pdf(src: Path, dest: Path, timeout: int = 120) -> Path:
    exe = soffice_path()
    with _LOCK, tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "doc.xlsx"  # 한글·괄호 든 이름이 명령줄에서 꼬이지 않게 짧은 이름으로
        shutil.copyfile(src, work)
        _PROFILE.mkdir(parents=True, exist_ok=True)
        cmd = [exe, f"-env:UserInstallation={_PROFILE.as_uri()}", "--headless", "--norestore",
               "--convert-to", "pdf", "--outdir", tmp, str(work)]
        res = subprocess.run(cmd, capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = Path(tmp) / "doc.pdf"
        if not out.exists():
            msg = (res.stderr or res.stdout or b"").decode("utf-8", "replace").strip()[:300]
            raise RuntimeError(f"PDF 변환 실패(LibreOffice){': ' + msg if msg else ''}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), dest)
    return dest
