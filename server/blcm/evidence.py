"""건축물관리점검 해당없음 근거 그림(2026-10-30 사용자 "분류가 되면 해당없음의 근거 법령 캡처 및 관리대장 캡처 후 표기, 사유 적기" →
"사전검토가 끝나면 근거·캡처가 들어가는 시점·버튼" → [① 서류검토 확정]).

해당없음 항목마다(applicability 판정 why로):
- 건축물대장 — 근거 칸(허가일·사용승인일·주용도·지역·연면적 …) 둘레에 빨간 네모, 칸 둘레만 잘라 200dpi(쪽마다 한 장)
- 토지이용계획확인원 — "지역지구등 지정여부" 칸에 빨간 네모(방화지구·가로구역 높이·지구단위계획 판정일 때)
- 법령 조문 — 사유에 적힌 조문(건축법 시행령 제27조제1항 …)의 국가법령정보센터 화면(server/scripts/make_blcm_law_caps.py가 미리 찍어 둔 그림)
→ 그 항목 현황사진(evidence = "대장"|"확인원"|"법령", 늘 양호 — 판정 자동(apply_photos)에서 빠짐). 회사 제출 보고서도 해당없음 항목 현황사진에 대장 그림을 넣음(우리프라자)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from core.db import DATA_DIR

LAW_DIR = DATA_DIR / "_건축물관리점검" / "_법령캡처"
CITE = re.compile(r"((?:건축법|건축물의 설비기준 등에 관한 규칙|건축물의 피난·방화구조 등의 기준에 관한 규칙|녹색건축물 조성 지원법)(?: 시행령| 시행규칙)?)\s*(제\d+조(?:의\d+)?)(제\d+항)?")
# 판정 why → 대장 칸(머리 글자) — 값은 머리 아래 줄(건축주만 오른쪽)
WHY_LABELS = {
    "대지 200㎡ 미만": ["※대지면적", "대지면적"], "녹지지역": ["※지역"], "자연환경보전·농림·관리지역": ["※지역"], "공장·축사·가설": ["주용도"],
    "대지 조경 대상 아님": ["※대지면적", "대지면적", "※지역"], "대상 지역 아님": ["※지역"], "연면적 5천㎡ 미만": ["연면적"], "대상 용도 5천㎡ 미만": ["주용도", "연면적"],
    "면 지역": ["※지역"], "대지안의 공지 조문 없던 기간 허가": ["허가일"], "상업지역": ["※지역"], "주거지역·공동주택 아님": ["※지역", "주용도"],
    "허가일 2015.4.1 전": ["허가일"], "범죄예방 대상 용도 없음": ["주용도"], "대상 아파트 아님": ["주용도", "호수/가구수/세대수"],
    "대상 주택·오피스텔 없음": ["주용도"], "대상 용도 없음": ["주용도"], "일용품 소매점 없음": ["주용도"], "다중생활시설 없음": ["주용도"],
    "민간·받은 인증 없음": ["인증명", "건축주"], "구조·용도변경 없음": ["변동사항"], "허가 당시 내진설계 대상 아님": ["허가일", "층수", "연면적"],
    "피난층만·200㎡ 이하": ["층수", "연면적"], "고층건축물 아님": ["층수", "높이"], "연면적 1천㎡ 이하": ["연면적"], "주요구조부 내화·불연 아님": ["주구조"],
    "내화구조 대상 아님": ["주용도", "연면적"], "마감재 대상 아님": ["주용도", "층수"], "방화지구 아님": ["허가일"], "사용승인일 2014.11.29 전": ["사용승인일"],
    "실내건축 대상 용도 아님": ["주용도", "층수", "연면적"], "지하층 없음": ["층수"],
}
LAND_WHY = {"방화지구 아님", "가로구역 높이 지정 없음", "면 지역", "자연환경보전·농림·관리지역"}
WIDE = {"변동사항": (330, 130), "인증명": (210, 40)}  # 아래로 넓게 볼 칸(오른쪽 너비, 높이) — 변동사항은 표 가운데 머리라 왼쪽도 같은 만큼


def _label_box(words: list, label: str) -> pymupdf.Rect | None:
    w = next((v for v in words if v[4] == label), None)
    if w is None:
        return None
    r = pymupdf.Rect(w[:4])
    if label == "건축주":  # 같은 줄 오른쪽(이름·번호)
        for v in words:
            if abs((v[1] + v[3]) / 2 - (w[1] + w[3]) / 2) < 4 and w[2] < v[0] < w[2] + 220:
                r |= pymupdf.Rect(v[:4])
        return r
    width, height = WIDE.get(label, (150, 16))
    left = width if label == "변동사항" else 10
    for v in words:
        if w[0] - left <= v[0] <= w[0] + width and w[3] <= v[1] <= w[3] + height:
            r |= pymupdf.Rect(v[:4])
    if label == "인증명":  # 머리 줄(유효기간·성능) + 아래 빈 줄 — 인증이 없으면 칸이 비어 있음을 보이게
        for v in words:
            if abs(v[1] - w[1]) < 3 and w[2] < v[0] < w[0] + width:
                r |= pymupdf.Rect(v[:4])
        r.y1 = max(r.y1, w[3] + 34)
    return r


def register_shots(pdf: Path, labels: list[str]) -> list[tuple[bytes, str]]:
    """대장에서 칸 찾아 빨간 네모 + 둘레 잘라 JPG — [(그림, 설명)] 쪽마다 한 장(칸을 못 찾으면 [])."""
    doc = pymupdf.open(pdf)
    found: dict[int, list[tuple[str, pymupdf.Rect]]] = {}
    seen: set[str] = set()
    for lab in labels:
        base = lab.lstrip("※")
        if base in seen:  # ※대지면적 / 대지면적 둘 중 먼저 찾은 것만
            continue
        for pi, page in enumerate(doc):
            r = _label_box(page.get_text("words"), lab)
            if r is not None:
                found.setdefault(pi, []).append((base, r))
                seen.add(base)
                break
    out = []
    for pi, boxes in sorted(found.items()):
        page = doc[pi]
        u = pymupdf.Rect(boxes[0][1])
        for _, r in boxes:
            page.draw_rect(r + (-3, -3, 3, 3), color=(0.9, 0, 0), width=1.6)
            u |= r
        clip = (u + (-150, -55, 150, 55)) & page.rect
        if clip.width < 380:  # 너무 좁으면 옆으로 넓힘
            clip = (clip + (-(380 - clip.width) / 2, 0, (380 - clip.width) / 2, 0)) & page.rect
        out.append((page.get_pixmap(clip=clip, dpi=200).tobytes("jpg", jpg_quality=88), "건축물대장(" + "·".join(n for n, _ in boxes) + ")"))
    return out


def land_shot(pdf: Path) -> tuple[bytes, str] | None:
    """토지이용계획확인원 "지역지구등 지정여부" 칸에 빨간 네모."""
    doc = pymupdf.open(pdf)
    for page in doc:
        ws = page.get_text("words")
        a = next((w for w in ws if w[4].startswith("지역지구등")), None) or next((w for w in ws if w[4] == "지정여부"), None)
        if a is None:
            continue
        ends = [w for w in ws if w[1] > a[1] and (w[4].startswith("「토지이용규제") or w[4] == "확인도면")]
        bottom = min(w[1] for w in ends) - 2 if ends else a[3] + 120
        first = [w for w in ws if w[4].startswith("「국토의") and a[1] - 80 < w[1] < bottom]  # 첫 줄(국토계획법 지역·지구)은 머리 글자보다 위에 있음
        top = min([a[1]] + [w[1] for w in first]) - 6
        right = max((w[2] for w in ws if top <= w[1] <= bottom), default=page.rect.x1 - 30)
        box = pymupdf.Rect(a[0] - 4, top, right + 4, bottom)
        page.draw_rect(box, color=(0.9, 0, 0), width=1.6)
        clip = (box + (-20, -60, 20, 30)) & page.rect
        return page.get_pixmap(clip=clip, dpi=200).tobytes("jpg", jpg_quality=88), "토지이용계획확인원(지역·지구 지정여부)"
    return None


def law_shots(reason: str) -> list[tuple[Path, str]]:
    """사유 글에 적힌 조문 → 미리 찍어 둔 조문 그림 [(파일, 설명)] — 처음 나온 조문 하나(같은 법 시행령 …은 빼고)."""
    try:
        idx = json.loads((LAW_DIR / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    for m in CITE.finditer(reason or ""):
        key = f"{m[1]} {m[2]}{m[3] or ''}"
        x = idx.get(key) or idx.get(f"{m[1]} {m[2]}")
        f = LAW_DIR / x["file"] if x else None
        if f is not None and f.exists():
            return [(f, f"{key}({x.get('title') or ''})" if x.get("title") else key)]
    return []


def make(why: str, reason: str, register: Path | None, landuse: Path | None) -> list[tuple[bytes, str, str]]:
    """해당없음 항목 하나의 근거 그림 [(JPG, 설명, 종류 대장|확인원|법령)]."""
    out: list[tuple[bytes, str, str]] = []
    if landuse is not None and landuse.exists() and why in LAND_WHY:
        got = land_shot(landuse)
        if got:
            out.append((got[0], got[1], "확인원"))
    labels = WHY_LABELS.get(why) or []
    if labels and register is not None and register.exists():
        out += [(img, cap, "대장") for img, cap in register_shots(register, labels)]
    out += [(f.read_bytes(), cap, "법령") for f, cap in law_shots(reason)]
    return out
