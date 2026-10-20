"""FMS "시설물관리대장(옹벽)" 글자 PDF → 옹벽 제원(2026-10-20 옹벽 3단계). AI 없이 낱말 규칙(FMS 출력본은 글자 PDF — 563·157·217 확인).
그림 PDF(예전 보고서 부록 인쇄본 — 관급-30 보강토옹벽-2)는 빈 dict → 시설물 정보에서 손으로. 읽은 값은 sitok_facility.ledger["wall"]에(DB 칸 안 늘림)."""
from __future__ import annotations

import re
from pathlib import Path

KEYS = ("fms_no", "class_no", "kind_text", "facility_class", "owner", "builder", "project", "form", "material", "length", "height", "base_width",
        "route", "surround", "attached", "coord_start", "coord_end")
LABELS = {"fms_no": "시설물번호", "class_no": "종별", "kind_text": "종류", "owner": "관리주체", "builder": "시공자", "project": "공사명", "form": "옹벽형식",
          "material": "재료", "length": "연장(m)", "height": "지면노출높이(m)", "base_width": "저판폭(m)", "route": "노선", "surround": "주변환경", "attached": "부대시설"}


def _sq(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _num(s: str) -> str:
    try:
        v = float(s)
    except (TypeError, ValueError):
        return ""
    return f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v)}.0"


def kind_text_of(facility_class: str) -> str:
    """시설물종류 글("…건축물옹벽"·"…도로옹벽"·"…부대시설이 아닌 옹벽") → 결과표 "종류" 칸(건축물옹벽 / 도로옹벽 / 기타옹벽)."""
    c = _sq(facility_class)
    if "건축물옹벽" in c:
        return "건축물옹벽"
    if "도로옹벽" in c:
        return "도로옹벽"
    for w in ("철도", "항만", "댐"):
        if f"{w}옹벽" in c:
            return f"{w}옹벽"
    return "기타옹벽"


def parse_text(text: str) -> dict:
    out: dict = {}
    t = " ".join((text or "").split())
    if "시설물관리대장" not in _sq(t) and "옹벽" not in t:
        return out
    m = re.search(r"(RW\d{4}-\d{7})", t)
    if m:
        out["fms_no"] = m[1]
    m = re.search(r"(\d)종\s*옹벽", t)
    if m:
        out["class_no"] = m[1]
    m = re.search(r"RW\d{4}-\d{7}\s+(.+?)\s+(\d)종\s+옹벽", t)
    if m:
        cls = m[1]
        cls = cls[cls.find("지면"):] if "지면" in cls else cls
        out["facility_class"] = re.sub(r"\s+", "", cls) if len(cls) < 120 else ""
        out["kind_text"] = kind_text_of(cls)
    m = re.search(r"관리주체\s*:\s*(.+?)\s+소\s*유\s*자", t)
    if m:
        out["owner"] = " ".join(m[1].split())
    m = re.search(r"총공사비\(백만원\)\s+(.+?)\s+내진정보", t)
    if m:
        toks = [x for x in m[1].split() if x not in ("~",)]
        toks = [x for x in toks if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)]
        if toks and re.fullmatch(r"[\d,]+", toks[-1]):
            toks = toks[:-1]
        if toks:
            out["builder"] = toks[-1]
    m = re.search(r"공사감독[^\s]*\s+(?:아니오|예)?\s*(.*?)\s+기타\s+기본현황", t)
    if m:
        seg = re.sub(r"\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2}", "", m[1])
        mm = re.search(r"((?:[^\s()]+\s+){0,2}[^\s()]*공사(?:\s*\([^)]*\))?)\s+\S+\s*$", seg.strip()) or re.search(r"((?:[^\s()]+\s+){0,2}[^\s()]*공사(?:\s*\([^)]*\))?)", seg)
        if mm:
            out["project"] = " ".join(mm[1].split())
    m = re.search(r"횡단선형\s+(\S+)\s+([^\s(]+(?:\([^)]*\))?)", t)
    if m:
        out["form"], out["material"] = m[1], m[2]
    m = re.search(r"앞\s+뒤\s+앞\s+뒤\s+([\d.]+)\s+([\d.]+)(?:\s+([\d.]+))?", t)
    if m:
        out["length"], out["height"] = _num(m[1]), _num(m[2])
    m = re.search(r"인접\s*보호\s*시설물\s*현황.*?외이격거리\(m\)\s+(.+?)\s+\d단\s+배수공", t)
    if m and not re.fullmatch(r"[\d\s.]*", m[1]):
        out["attached"] = re.sub(r"(\s+[\d.]+)+\s*$", "", " ".join(m[1].split()))
    return out


def read(pdf_path: str | Path) -> dict:
    """관리대장 PDF → 제원 dict(글자가 없으면 빈 dict)."""
    import pymupdf

    p = Path(pdf_path) if pdf_path else None
    if not p or not p.exists():
        return {}
    try:
        with pymupdf.open(str(p)) as doc:
            text = "".join(page.get_text() for page in doc)
    except Exception:  # noqa: BLE001
        return {}
    return parse_text(text) if len(text.strip()) > 200 else {}


def form_text(spec: dict, structure: str = "") -> str:
    """현황표 "옹벽형식" 칸 — 재료(보강토·철근콘크리트) + 형식(블록쌓기·역T형)."""
    mat = (spec.get("material") or "").split("(")[0].strip()
    form = spec.get("form") or ""
    if mat and form:
        return f"{mat} 옹벽({form})" if mat not in form else f"{form} 옹벽"
    return structure or form or mat or "-"
