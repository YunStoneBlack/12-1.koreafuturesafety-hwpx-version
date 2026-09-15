"""고객 배포용 단일 exe를 빌드한다 — PyInstaller CLI를 직접 호출하는 대신 Python에서
`PyInstaller.__main__.run()`을 부르는 이유는, 이 프로젝트 경로 자체에 한글이 섞여 있어
(`c:\\Users\\윤석현1\\Desktop\\클로드 코딩\\...`) 셸에 넘기는 커맨드라인 문자열로 조립하면
따옴표/인코딩 문제가 생기기 쉽기 때문이다 — 여기서는 전부 파이썬 리스트 인자로 넘긴다.

**exe가 있는 폴더를 기준으로 데이터를 찾는다**(`core/db.py`의 `BASE_DIR` — 프로즌 상태에서는
`sys.executable`의 부모 폴더): 그래서 실제 데이터(`data/templates/report_template.hwp`,
`data/materials/`, `data/seed_reference_data.json`)는 PyInstaller로 실행 파일 안에 묶어
넣지 않고, 빌드가 끝난 뒤 `dist/<이름>/` 폴더에 있는 그대로 복사해 exe 옆에 둔다 — 그래야
고객이 이 폴더를 통째로 옮기거나 백업할 때 직관적이고, 나중에 업데이트할 때도 exe 파일만
새로 갈아끼우면 된다.

실행:
    python packaging/build_exe.py

결과: dist/한국미래안전_기술지도결과보고서/ 폴더에 exe + data/ 준비 완료. 이 폴더 전체를
고객에게 그대로 전달하면 된다(첫 실행 시 `data/app.db`가 자동으로 새로 만들어짐).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pyhwpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "한국미래안전_기술지도결과보고서"

PYHWPX_DIR = Path(pyhwpx.__file__).resolve().parent
ICON_PATH = PROJECT_ROOT / "desktop" / "assets" / "app_icon.ico"


def _run_pyinstaller() -> None:
    from PyInstaller.__main__ import run as pyinstaller_run

    args = [
        str(PROJECT_ROOT / "desktop" / "main.py"),
        "--name", APP_NAME,
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--icon", str(ICON_PATH),
        "--paths", str(PROJECT_ROOT),
        # pyhwpx가 `importlib.resources.files("pyhwpx")`로 자기 패키지 폴더에서 이 DLL을
        # 찾는데(한글 보안모듈 등록용), PyInstaller가 .py가 아닌 이 파일은 자동으로 안 담아서
        # 명시적으로 같은 상대 위치(pyhwpx/)에 넣어준다.
        "--add-data", f"{PYHWPX_DIR / 'FilePathCheckerModule.dll'};pyhwpx",
        # 이 파이썬 환경에 PyQt5도 같이 깔려있어(다른 프로젝트용으로 추정) PyInstaller가
        # "Qt 바인딩 두 개를 동시에 못 묶는다"며 중단시킨다 — 이 앱은 PyQt6만 쓰므로 명시적으로
        # 제외한다.
        "--exclude-module", "PyQt5",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--distpath", str(PROJECT_ROOT / "dist"),
        "--workpath", str(PROJECT_ROOT / "build"),
        "--specpath", str(PROJECT_ROOT / "packaging"),
    ]
    pyinstaller_run(args)


def _copy_runtime_data(dist_dir: Path) -> None:
    data_dir = dist_dir / "data"

    # dist 폴더에서 앱을 한 번이라도 직접 실행해본 적이 있으면 `app.db`가 그 실행 당시의
    # 절대경로(BASE_DIR)를 기준으로 만들어져 있다. 이 dist 폴더를 복사/압축해서 다른 위치나
    # 다른 PC로 옮기면 그 경로가 더 이상 안 맞아 제공자료 썸네일이 깨지고, 무엇보다 그때
    # 테스트하며 만든 실제 데이터(사업장/보고서 등)가 고객에게 그대로 전달되는 사고로 이어질
    # 수 있다. 매 빌드마다 지워서 고객 PC의 첫 실행이 항상 깨끗한 신규 DB로 시작하게 한다.
    stale_db = data_dir / "app.db"
    if stale_db.exists():
        stale_db.unlink()

    (data_dir / "templates").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "data" / "templates" / "report_template.hwp",
        data_dir / "templates" / "report_template.hwp",
    )
    # Sub-phase 19부터 미리보기·PDF·"한글 파일 생성" 세 경로 전부 report_builder_hwpx.py
    # (COM 불필요 엔진)가 이 파일을 읽는다 — .hwp만 복사하던 이전 빌드 스크립트로는 배포판이
    # 켜지자마자 "템플릿을 찾을 수 없음"으로 깨진다(실측 확인, 이번에 고침). .hwp는 옛 COM
    # 엔진의 예외 타입 재사용 목적으로만 남아있지만(core/report_builder.py 참고) 혹시 몰라
    # 그대로 같이 둔다.
    shutil.copy2(
        PROJECT_ROOT / "data" / "templates" / "report_template.hwpx",
        data_dir / "templates" / "report_template.hwpx",
    )

    materials_src = PROJECT_ROOT / "data" / "materials"
    if materials_src.exists():
        shutil.copytree(materials_src, data_dir / "materials", dirs_exist_ok=True)

    seed_json = PROJECT_ROOT / "data" / "seed_reference_data.json"
    if seed_json.exists():
        shutil.copy2(seed_json, data_dir / "seed_reference_data.json")


def main() -> None:
    _run_pyinstaller()
    dist_dir = PROJECT_ROOT / "dist" / APP_NAME
    _copy_runtime_data(dist_dir)
    print(f"\n완료: {dist_dir} 폴더 전체를 고객에게 전달하면 됩니다.")


if __name__ == "__main__":
    main()
