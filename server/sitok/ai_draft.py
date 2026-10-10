"""시특법 보고서 AI 초안(2026-10-11 6단계) — 현장 조사 결함으로 결과표·외관조사 서술·종합결론 초안 → 점검자가 고쳐 확정(민재형 10/10:
"획일적인(복붙 느낌) 보고서 → 차별성 있는 보고서", 고정 문구는 AI 실패 때 기본값으로만).

draft(...) — 결함을 1.3 항목(균열·누수·박리박락·강재·비구조체·공중이용·기타)으로 나눠 숫자(개수·최대 폭·물량·층·진행/신규/보수)를 만들고,
지난 회차 문장은 말투 참고로만 주며 "그대로 베끼지 말 것"을 지시. 결과는 JSON(점검자가 고치는 화면 = js/sitok-ai.js).
안전등급 정의(시설물안전법 시행령 별표 8)·등급 표기(2종 낱말·3종 글자)도 여기.
"""
from __future__ import annotations

import json
import re

from anthropic import Anthropic

from core.config import get_api_key, get_model_name

CATEGORIES = [  # (키, 1.3 제목에 들어 있는 낱말, 이름)
    ("crack", ("균열",), "콘크리트 구조체 균열"),
    ("leak", ("누수", "백화"), "누수 및 백화"),
    ("spall", ("박리", "박락", "바락", "철근"), "콘크리트 박리·박락 및 철근노출·부식"),
    ("steel", ("강재",), "강재구조 노후상태"),
    ("nonstruct", ("비구조체",), "비구조체"),
    ("public", ("공중",), "공중이 이용하는 부위 및 부대시설"),
    ("other", ("기타",), "기타시설"),
]
GRADES = {"A": ("우수", "문제점이 없는 최상의 상태"),
          "B": ("양호", "보조부재에 경미한 결함이 발생하였으나 기능 발휘에는 지장이 없으며, 내구성 증진을 위하여 일부의 보수가 필요한 상태"),
          "C": ("보통", "주요부재에 경미한 결함 또는 보조부재에 광범위한 결함이 발생하였으나 전체적인 시설물의 안전에는 지장이 없으며, "
                      "주요부재에 내구성, 기능성 저하 방지를 위한 보수가 필요하거나 보조부재에 간단한 보강이 필요한 상태"),
          "D": ("미흡", "주요부재에 결함이 발생하여 긴급한 보수·보강이 필요하며 사용제한 여부를 결정하여야 하는 상태"),
          "E": ("불량", "주요부재에 발생한 심각한 결함으로 인하여 시설물의 안전에 위험이 있어 즉각 사용을 금지하고 보강 또는 개축을 하여야 하는 상태")}
WORD_TO_LETTER = {w: k for k, (w, _) in GRADES.items()}


def category_of(part: str, member: str, dtype: str) -> str:
    """결함 하나가 1.3의 어느 항목인지."""
    t, m = dtype or "", member or ""
    if any(x in m for x in ("난간", "옹벽", "환기구", "점검로", "석축", "비탈")):
        return "public"
    if "강재" in m or ("부식" in t and "철근" not in t):
        return "steel"
    if any(x in t for x in ("누수", "백태", "백화", "체수")):
        return "leak"
    if part == "구조체" and any(x in t for x in ("박리", "박락", "철근", "탈락")):
        return "spall"
    if part == "구조체" and "균열" in t:
        return "crack"
    if part == "비구조체" or any(x in m for x in ("조적", "마감", "칸막이")):
        return "nonstruct"
    return "other"


def section_key(heading: str) -> str | None:
    """1.3 제목 글("1)콘크리트 구조체 균열 조사결과" 등) → 항목 키. 비구조체·공중·기타를 먼저 봄(균열 낱말이 겹치지 않게)."""
    h = heading.replace(" ", "")
    for key in ("nonstruct", "public", "other", "steel", "leak", "spall", "crack"):
        words = dict((k, w) for k, w, _ in CATEGORIES)[key]
        if any(w in h for w in words):
            return key
    return None


def grade_text(letter: str, template: str) -> tuple[str, str]:
    """(결과표·종합결론에 쓸 등급 글, 등급 정의) — 2종은 낱말(보통), 3종은 글자(B)."""
    word, desc = GRADES.get(letter, ("", ""))
    return (letter if template.startswith("3종") else word), desc


def stats(defects: list) -> dict:
    """항목별 숫자 — defects = [{part, member, dtype, floor, count, width, length, qty, check, mark, progress, cause}]."""
    out = {k: {"name": n, "count": 0, "floors": [], "types": {}, "max_width": None, "qty": 0.0, "grew": 0, "new": 0, "repaired": 0, "items": []}
           for k, _, n in CATEGORIES}
    for d in defects:
        if (d.get("dtype") or "").rstrip().endswith("현황"):
            continue
        k = category_of(d.get("part"), d.get("member"), d.get("dtype"))
        s = out[k]
        if d.get("check") == "repaired" or d.get("mark") == "보수":
            s["repaired"] += 1
            continue
        s["count"] += 1
        if d.get("floor") and d["floor"] not in s["floors"]:
            s["floors"].append(d["floor"])
        key = f"{d.get('member', '')} {d.get('dtype', '')}".strip()
        s["types"][key] = s["types"].get(key, 0) + 1
        try:
            w = float(d.get("width") or "")
            s["max_width"] = w if s["max_width"] is None else max(s["max_width"], w)
        except ValueError:
            pass
        try:
            s["qty"] += float(d.get("qty") or 0)
        except ValueError:
            pass
        s["grew"] += d.get("check") == "grew"
        s["new"] += d.get("check") == "new"
        if len(s["items"]) < 12:
            s["items"].append(f"{d.get('floor')} {d.get('member')} {d.get('dtype')} 개수 {d.get('count')} 폭 {d.get('width')} 길이 {d.get('length')}"
                              f" 원인 {d.get('cause')} {d.get('progress')} {d.get('mark')}")
    for s in out.values():
        s["qty"] = round(s["qty"], 2)
    return out


PROMPT = """당신은 한국의 시설물 정기안전점검(시설물안전법) 보고서를 쓰는 책임기술자입니다. 아래 이번 회차 외관조사 결과로 보고서 문장 초안을 쓰세요.

[시설물] {facility}
[이번 회차] {period}
[항목별 결함 집계 — 이번 회차 현장 조사]
{stats}

[지난 회차 보고서 문장 — 말투·형식 참고용. 같은 문장을 그대로 베끼지 말고, 이번 숫자에 맞게 새로 쓰세요]
{old}

규칙:
- 사실은 위 집계에 있는 것만. 없는 결함·숫자를 지어내지 말 것. 결함이 0개인 항목은 "조사 결과 특이사항이 없었다/양호" 취지로 짧게.
- 진행된 결함(진행)·새로 찾은 결함(신규)·보수 완료가 있으면 그 사실을 반영(전회차 대비 변화).
- 균열폭 0.3mm 미만은 표면처리, 0.3mm 이상은 주입 보수가 일반적. 면적 결함(누수·박리 등)은 마감재 재시공·단면복구 등.
- 문장은 보고서 문어체("~조사되었다", "~권고한다"), 항목마다 2~4문장. 매번 같은 틀이 되지 않게 시설물·층·부재를 구체적으로.
- 안전등급은 A~E 중 추천 하나와 근거 한두 문장. 등급 이름: A 우수, B 양호, C 보통, D 미흡, E 불량(중대결함 없고 비구조체 위주면 보통 B~C).

아래 JSON 객체 하나로만 답하세요(설명 없이):
{{"critical": "결과표 중대결함 칸(예: 없음 / 일상적인 유지관리 실시)",
 "public": "결과표 공중이 이용하는 부위 칸 한두 문장",
 "findings": ["결과표 점검 주요결과 글머리 3~4개 — 결과표 칸이 좁아 한 쪽에 들어가야 하므로 각 120자 이내 한두 문장"],
 "repairs": ["결과표 주요 보수·보강 줄 2~3개, 각 60자 이내(예: - 구조체(콘크리트) 균열 : 표면처리공법(0.3mm미만), 에폭시 주입(0.3mm이상))"],
 "next_focus": "차기 정기점검 시 중점 점검부위(한 줄)",
 "sections": {{"crack": "", "leak": "", "spall": "", "steel": "", "nonstruct": "", "public": "", "other": ""}},
 "conclusion": ["종합결론 글머리 — 항목별 한 개씩(결함 없는 항목도 짧게)"],
 "grade": "A~E 중 하나", "grade_reason": "근거"}}"""


def draft(facility: str, period: str, defects: list, old_text: str, company_id: int) -> dict:
    st = stats(defects)
    lines = []
    for k, _, n in CATEGORIES:
        s = st[k]
        types = ", ".join(f"{t} {c}건" for t, c in list(s["types"].items())[:10]) or "없음"
        lines.append(f"- {n}({k}): 결함 {s['count']}건, 층 {', '.join(s['floors']) or '-'}, 종류 {types}, 최대 폭 {s['max_width'] if s['max_width'] is not None else '-'}, "
                     f"물량 합 {s['qty']}, 진행 {s['grew']} · 신규 {s['new']} · 보수 완료 {s['repaired']}\n  예: " + " / ".join(s["items"][:6]))
    prompt = PROMPT.format(facility=facility, period=period, stats="\n".join(lines), old=old_text[:6000] or "(없음)")
    client = Anthropic(api_key=get_api_key(company_id))
    resp = client.messages.create(model=get_model_name(), max_tokens=12000, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("AI 답에서 JSON을 찾지 못했습니다.")
    data = json.loads(m.group(0))
    data["sections"] = {k: str((data.get("sections") or {}).get(k) or "").strip() for k, _, _ in CATEGORIES}
    for k in ("findings", "repairs", "conclusion"):
        data[k] = [str(x).strip() for x in (data.get(k) or []) if str(x).strip()]
    for k in ("critical", "public", "next_focus", "grade_reason"):
        data[k] = str(data.get(k) or "").strip()
    g = str(data.get("grade") or "").strip().upper()[:1]
    data["grade"] = g if g in GRADES else ""
    data["stats"] = {k: {x: st[k][x] for x in ("count", "grew", "new", "repaired", "max_width", "qty")} for k in st}
    return data
