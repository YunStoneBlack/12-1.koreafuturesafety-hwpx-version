"""건축물관리점검 — 건축물대장 PDF → 건축물 개요(생애이력시스템 "건축물 개요" 칸 + 항목 기준값).

내진 seismic_docs.read_register(글자 PDF — 명칭·주소·대지면적·연면적·건축면적·구조·용도·층수·높이·허가일·사용승인일·내진설계 적용 여부·층별·변동사항)에
건축물관리점검에 더 쓰는 칸을 글자 규칙으로 더함: 건폐율·용적률(%)·조경면적·공개공지 면적·건축선후퇴 면적/거리·지역·지구·구역·호수/가구수/세대수·용적률산정용 연면적.
대장 표는 "머리 줄 다음 줄에 값" 모양(정부24 일반건축물대장 갑). 글자 없는(스캔) 대장은 read_register_ai(AI 약 30원)."""
from __future__ import annotations

import re
from pathlib import Path

NUM = r"([\d,]+(?:\.\d+)?)"
KEYS = ("site_area", "total_area", "far_area", "building_area", "coverage", "far", "landscape_area", "open_space_area", "setback_area", "setback_dist",
        "zone", "district", "area_zone", "households", "structure", "use", "above", "below", "height", "permit_date", "approval_date", "seismic_design")
LABEL = {"site_area": "대지면적(㎡)", "total_area": "연면적(㎡)", "far_area": "용적률산정용 연면적(㎡)", "building_area": "건축면적(㎡)", "coverage": "건폐율(%)",
         "far": "용적률(%)", "landscape_area": "조경면적(㎡)", "open_space_area": "공개공지·공간 면적(㎡)", "setback_area": "건축선후퇴면적(㎡)",
         "setback_dist": "건축선후퇴거리(m)", "zone": "용도지역", "district": "용도지구", "area_zone": "구역", "households": "호수/가구수/세대수",
         "structure": "구조", "use": "주용도", "above": "지상 층수", "below": "지하 층수", "height": "높이(m)", "permit_date": "허가일",
         "approval_date": "사용승인일", "seismic_design": "내진설계 적용 여부"}


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def extra(text: str) -> dict:
    """대장 글에서 건축물관리점검에 더 쓰는 칸."""
    out: dict = {}
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for i, ln in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if ln.startswith("※대지면적") and "※지역" in ln:  # "6,559 ㎡ 3,257.11 ㎡ 자연녹지지역 경관지구"
            rest = re.sub(rf"^{NUM}\s*㎡\s*{NUM}?\s*㎡?\s*", "", nxt)
            words = rest.split()
            out["zone"] = next((w for w in words if w.endswith("지역")), "")
            out["district"] = next((w for w in words if w.endswith("지구")), "")
            out["area_zone"] = next((w for w in words if w.endswith("구역")), "")
        elif ln.startswith("건축면적") and "용적률산정용" in ln:
            a = re.findall(rf"{NUM}\s*㎡", nxt)
            if len(a) > 1:
                out["far_area"] = _num(a[1])
        elif ln.startswith("※건폐율") and "※용적률" in ln:
            p = re.findall(rf"{NUM}\s*%", nxt)
            if p:
                out["coverage"] = _num(p[0])
            if len(p) > 1:
                out["far"] = _num(p[1])
        elif ln.startswith("※조경면적"):  # "123.4 ㎡ 45 ㎡ 12 ㎡ 3 m" — 빈 칸은 단위만
            vals = re.findall(rf"(?:{NUM}\s*)?(㎡|m)(?![²\w])", nxt)
            keys = ("landscape_area", "open_space_area", "setback_area", "setback_dist")
            for k, (v, _u) in zip(keys, vals):
                if v:
                    out[k] = _num(v)
        if not out.get("households"):
            m = re.search(r"(\d+)호/(\d+)가구/(\d+)세대", ln)
            if m:
                out["households"] = f"{m[1]}호/{m[2]}가구/{m[3]}세대"
    return out


def read(pdf: Path, company_id: int | None = None, use_ai: bool = False) -> dict:
    """건축물대장 → 개요 dict(KEYS + name·address·floors·changes·text_ok). 글자가 없고 use_ai면 AI로(약 30원)."""
    from server.contract_docs import contract_pdf as C
    from server.sitok import seismic_docs as SD

    base = SD.read_register(pdf)
    if not base.get("text_ok"):
        if use_ai and company_id is not None:
            base = SD.read_register_ai(pdf, company_id)
        return {**base, "text_ok": bool(base.get("text_ok"))}
    out = {**base, **extra(C.read_text(pdf))}
    for k in ("permit_date", "approval_date", "start_date"):
        v = out.get(k)
        out[k] = v.isoformat() if hasattr(v, "isoformat") else (v or "")
    for ch in out.get("changes") or []:
        v = ch.get("date")
        ch["date"] = v.isoformat() if hasattr(v, "isoformat") else (v or "")
    return out


def facts(b: dict | None) -> str:
    """AI 물음용 — 건축물 개요 한 줄씩."""
    b = b or {}
    rows = [f"- 명칭: {b.get('name') or '-'} / 위치: {b.get('address') or '-'}"]
    for k in KEYS:
        v = b.get(k)
        if v not in (None, "", []):
            rows.append(f"- {LABEL[k]}: {v}")
    if b.get("floors"):
        rows.append("- 층별: " + ", ".join(f"{x.get('floor')} {x.get('use')} {x.get('area')}㎡" for x in b["floors"][:12]))
    if b.get("changes"):
        rows.append("- 변동사항: " + " / ".join(f"{x.get('date')} {x.get('text')}" for x in b["changes"][:8]))
    return "\n".join(rows)
