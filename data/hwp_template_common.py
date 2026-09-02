"""`build_hwp_template.py`와 표별 전용 처리 모듈(`build_hwp_template_table6.py`,
`build_hwp_template_equipment.py`)이 공통으로 쓰는 아주 작은 유틸리티.

순환 임포트를 피하려고 분리했다 — `build_hwp_template.py`가 표별 모듈의 함수를 호출하는
쪽(orchestrator)이라, 표별 모듈이 거꾸로 `build_hwp_template.py`에서 `_normalize`를 가져오면
순환 참조가 생긴다.
"""

from __future__ import annotations

import re

_BULLET_CHARS = "□•○☑✓"


def _normalize(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.replace("\r\n", " ").replace("\n", " ")).strip()
    return collapsed.lstrip(_BULLET_CHARS).strip()
