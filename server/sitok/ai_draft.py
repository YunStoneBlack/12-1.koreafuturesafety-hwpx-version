"""시특법 보고서 AI 초안(2026-10-11 6단계) — 현장 조사 결함으로 결과표·외관조사 서술·종합결론 초안 → 점검자가 고쳐 확정(민재형 10/10:
"획일적인(복붙 느낌) 보고서 → 차별성 있는 보고서", 고정 문구는 AI 실패 때 기본값으로만).

draft(...) — 결함을 1.3 항목(균열·누수·박리박락·강재·비구조체·공중이용·기타)으로 나눠 숫자(개수·최대 폭·물량·층·진행/신규/보수)를 만들고,
지난 회차 문장은 말투 참고로만 주며 "그대로 베끼지 말 것"을 지시. 결과는 JSON(점검자가 고치는 화면 = js/sitok-ai.js).
안전등급 정의(시설물안전법 시행령 별표 8)·등급 표기(2종 낱말·3종 글자)도 여기.
"""
from __future__ import annotations

import json
import re

from server.sitok import kinds, manual3


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
GRADES2 = ("양호", "보통", "미흡", "불량")  # 2종 정기 결과 — A~E·우수와 별개(형 10/16 "2종은 A~B가 없어 — 애초에 양호 보통 미흡 불량"), 속은 B~E로 저장


def is_type2(template: str) -> bool:
    return not (template or "").startswith("3종")


def category_of(part: str, member: str, dtype: str) -> str:
    """결함 하나가 1.3의 어느 항목인지."""
    t, m = dtype or "", member or ""
    if any(x in m for x in ("난간", "옹벽", "환기구", "점검로", "석축", "비탈")) or "높이부족" in t:
        return "public"
    if "강재" in m or ("부식" in t and "철근" not in t):
        return "steel"
    if any(x in t for x in ("누수", "백태", "백화", "체수")):
        return "leak"
    if part == "구조체" and any(x in t for x in ("박리", "박락", "층분리", "재료분리", "철근", "탈락")):
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
    if is_type2(template) and letter == "A":  # 2종에 우수(A)는 없음 — 양호
        letter = "B"
    word, desc = GRADES.get(letter, ("", ""))
    return (letter if template.startswith("3종") else word), desc


def grade_label(letter: str, template: str) -> str:
    """요약문·화면 등급 글 — 3종 글자(B), 2종 낱말(양호·보통·미흡·불량)."""
    return grade_text(letter, template)[0] or "-"


def to_letter(value: str, template: str) -> str:
    """AI·화면 등급 값 → 저장 글자. 2종은 낱말(양호…)이나 글자, A는 B로."""
    v = (value or "").replace("등급", "").strip()
    g = WORD_TO_LETTER.get(v) or (v.upper()[:1] if v[:1].upper() in "ABCDE" else "")
    return "B" if is_type2(template) and g == "A" else g


def stats(defects: list) -> dict:
    """항목별 숫자 — defects = [{part, member, dtype, floor, count, width, length, qty, check, mark, progress, cause, cause_note}].
    rated = 상태평가에 드는 구조 결함 수(구조체라도 미장·마감 균열은 뺌 — kinds.counts_for_rating)."""
    out = {k: {"name": n, "count": 0, "rated": 0, "floors": [], "types": {}, "max_width": None, "qty": 0.0, "grew": 0, "new": 0, "repaired": 0, "items": []}
           for k, _, n in CATEGORIES}
    for d in defects:
        if kinds.is_record(d.get("dtype")):
            continue
        k = category_of(d.get("part"), d.get("member"), d.get("dtype"))
        s = out[k]
        if d.get("check") == "repaired" or d.get("mark") == "보수" or kinds.is_repaired_type(d.get("dtype")):
            s["repaired"] += 1
            continue
        s["count"] += 1
        s["rated"] += kinds.counts_for_rating(d.get("part"), d.get("dtype"))
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
                              f" 원인 {d.get('cause')}{f'(근거: {n})' if (n := d.get('cause_note')) else ''} {d.get('progress')} {d.get('mark')}")
    for s in out.values():
        s["qty"] = round(s["qty"], 2)
    return out


PROMPT = """당신은 한국의 시설물 정기안전점검(시설물안전법) 보고서를 쓰는 책임기술자입니다. 아래 이번 회차 외관조사 결과로 보고서 문장 초안을 쓰세요.

[시설물] {facility}
[이번 회차] {period}
[항목별 결함 집계 — 이번 회차 현장 조사]
{stats}
{parts}

[지난 회차 보고서 문장 — 말투·형식 참고용. 같은 문장을 그대로 베끼지 말고, 이번 숫자에 맞게 새로 쓰세요]
{old}

규칙:
- 사실은 위 집계에 있는 것만. 없는 결함·숫자를 지어내지 말 것. 결함이 0개인 항목은 "조사 결과 특이사항이 없었다/양호" 취지로 짧게.
- 진행된 결함(진행)·새로 찾은 결함(신규)·보수 완료가 있으면 그 사실을 반영(전회차 대비 변화).
- 균열폭 0.3mm 미만은 표면처리, 0.3mm 이상은 주입 보수가 일반적. 면적 결함(누수·박리 등)은 마감재 재시공·단면복구 등.
- 원인은 결함마다 적힌 원인·근거를 살려 구체적으로 — "건조수축균열·노후화" 같은 한 낱말로 뭉뚱그리지 말 것.
- 구조체라도 미장균열·마감균열·조적균열은 마감층 결함이라 구조 결함이 아님(집계의 "상태평가 대상"에서 빠짐) — 구조안전성 판단·등급·18항목의 구조부재 항목은
  상태평가 대상 결함으로, 마감층 결함은 18항목의 마감재·칸막이벽 항목에서.
- {leak_rule} — 마감재 누수흔적·배관 누수를 "구조체 누수"로 쓰지 말 것.
- 문장은 보고서 문어체("~조사되었다", "~권고한다"), 항목마다 2~4문장. 매번 같은 틀이 되지 않게 시설물·층·부재를 구체적으로.
- 공중이 이용하는 부위·기타시설 현장 사진 판단이 있으면 sections.public·sections.other·결과표 public은 그 판단(항목·상태)을 근거로 구체적으로
  (해당없음 항목은 "해당없음", 사진이 없는 항목은 언급하지 말 것). 결함 집계의 공중이용·기타 결함도 함께.
  보고서 글에는 a~e 같은 평가 글자를 쓰지 말고 상태를 말로(예: "전반적으로 양호한 상태로 유지되고 있다", "일부 균열 등이 발생한 것으로 조사되었다").
{grade_rule}

아래 JSON 객체 하나로만 답하세요(설명 없이):
{{"critical": "결과표 중대한 결함 칸 — 시행령 제18조제1항의 중대한 결함이 있을 때만 그 내용 한 줄, 없으면 \"없음\"만(다른 말 붙이지 말 것)",
 "public": "결과표 공중이 이용하는 부위에 결함 칸 — 시행령 제18조제2항의 공중이 이용하는 부위 결함이 있을 때만 위치·결함 한 줄, 없으면 \"없음\"만",
 "findings": ["결과표 점검 주요결과 글머리 3~4개 — 결과표 칸이 좁아 한 쪽에 들어가야 하므로 각 120자 이내 한두 문장"],
 "repairs": ["결과표 주요 보수·보강 줄 2~3개, 각 60자 이내(예: - 구조체(콘크리트) 균열 : 표면처리공법(0.3mm미만), 에폭시 주입(0.3mm이상))"],
 "next_focus": "차기 정기점검 시 중점 점검부위(한 줄)",
 "sections": {{"crack": "", "leak": "", "spall": "", "steel": "", "nonstruct": "", "public": "", "other": ""}},
 "conclusion": ["종합결론 글머리 — 항목별 한 개씩(결함 없는 항목도 짧게)"],
 "grade": "{grade_pick}", "grade_reason": "근거"{items_spec}}}"""

ITEMS_SPEC = """,
 "items": [{{"no": 항목번호, "rating": "우수|양호|보통|미흡|불량|해당없음", "repair": "○ 또는 ×", "opinion": "점검자 의견 15자 안팎(예: 일부 균열 발생)", "basis": "근거 결함 — 아래 결함 목록의 층·번호와 크기(예: 지상5층 2·5번 균열 최대 0.3mm), 걸린 결함이 없으면 빈 글"}} — 아래 18항목 전부],
 "eval_opinion": "안전등급 평가 종합의견 한두 문장"

3종은 안전등급을 아래 18항목 평가 점수로 프로그램이 계산합니다(우수10·양호8·보통5·미흡2·불량0, 주요60·일반20·부대20, 9·7·5·3점 이상 A~D) — "grade"도 그 계산과 맞게.
18항목 평가는 반드시 제3종시설물 정기안전점검 매뉴얼(2026) 평가방법대로 — 아래 원칙과 항목마다 적힌 a~e 기준으로.

{items}"""


FACILITY_SPEC = """,
 "facility": [{{"no": 항목번호, "has": true 또는 false, "state": "있으면 상태(유형·크기·추정원인) — 표 칸이 좁아 20자 이내(예: 창대 몰탈 탈락, 시공불량)", "where": "있으면 층·결함 번호만(외관망도·사진대장 번호 같음, 예: 지상1층 4번 / 옥상 16·22번)"}} — 아래 {n}항목 전부]

[1.4 기타 부대시설 상태조사 항목 — 지난 회차 있다/없다] 아래 결함 목록에 해당하는 결함이 있을 때만 있다(true), 없으면 false(지어내지 말 것):
{items}"""

DEFECTS_BLOCK = """

[결함 목록(18항목 근거·1.4 표에 씀) — 층 번호 | 구분 | 부재 | 결함유형 | 개수 | 폭 | 길이 | 원인(근거) | 진행 | 상태평가]
{defects}"""


METHOD_SPEC = """,
 "methods": [{{"no": 묶음번호, "method": "보수공법", "lump": 단가표에 없는 공법일 때만 그 묶음 전체 1식 금액(원, 정수) 아니면 null}} — 아래 묶음 전부]

[보수공법 — 9쪽 조치 필요사항·보수 우선순위·개략공사비에 같이 씀] 묶음마다 보수공법을 정하세요.
- 되도록 회사 단가표의 공법 이름 그대로(그래야 단가로 계산됨): {prices}
- 단가표에 맞는 공법이 없을 때만 새 공법 이름(예: 방수층 부분 재시공, 배수구 정비, 창호 실링 교체)과 그 묶음 전체의 1식 금액(시중 일반 단가 기준 개략)을 넣으세요.
- 경미하고 진행성이 없어 보수가 필요 없으면 "주의관찰". 균열 0.3mm 미만 = 표면처리, 0.3mm 이상 = 에폭시주입보수가 기본.
[묶음 — 번호 | 구분 | 부재 | 결함유형 | 개수 | 물량 | 최대 폭 | 원인 | 기본 공법]
{combos}"""


GRADE_RULE3 = "- 안전등급은 A~E 중 추천 하나와 근거 한두 문장. 등급 이름: A 우수, B 양호, C 보통, D 미흡, E 불량(중대결함 없고 비구조체 위주면 보통 B~C)."
GRADE_RULE2 = ("- 점검결과 등급(제2종시설물)은 양호·보통·미흡·불량 중 하나와 근거 한두 문장 — 2종은 A~E·우수가 없는 별개 체계"
               "(중대결함 없고 비구조체 위주면 보통 양호~보통, 주요부재 결함으로 긴급 보수가 필요하면 미흡, 위험하면 불량).")


def draft(facility: str, period: str, defects: list, old_text: str, company_id: int, eval_items: list | None = None,
          fac_items: list | None = None, combos: list | None = None, price_list: list | None = None, parts_facts: str = "", template: str = "3종일반",
          target: str = "") -> dict:
    """target = 점검자가 정한 등급 글자(A~E) — 등급 재산정 요청(10/19 형 "AI 등급이 맞지 않다고 판단되면 한 단계 상향·하향 요청")."""
    st = stats(defects)
    lines = []
    for k, _, n in CATEGORIES:
        s = st[k]
        types = ", ".join(f"{t} {c}건" for t, c in list(s["types"].items())[:10]) or "없음"
        lines.append(f"- {n}({k}): 결함 {s['count']}건(상태평가 대상 구조 결함 {s['rated']}건), 층 {', '.join(s['floors']) or '-'}, 종류 {types}, "
                     f"최대 폭 {s['max_width'] if s['max_width'] is not None else '-'}, "
                     f"물량 합 {s['qty']}, 진행 {s['grew']} · 신규 {s['new']} · 보수 완료 {s['repaired']}\n  예: " + " / ".join(s["items"][:6]))
    spec = ITEMS_SPEC.format(items=manual3.criteria(eval_items)) if eval_items else ""  # 18항목 = 매뉴얼 4.6 a~e 기준(10/19)
    if fac_items:
        spec += FACILITY_SPEC.format(n=len(fac_items), items="\n".join(f"{it['no']}. {it['name']} (지난 {'있다' if it['has'] else '없다'})" for it in fac_items))
    if eval_items or fac_items:
        rows = "\n".join(f"{d.get('floor')} {d.get('seq')}번 | {d.get('part')} | {d.get('member')} | {d.get('dtype')} | {d.get('count')} | {d.get('width')} | "
                         f"{d.get('length')} | {d.get('cause')}{f'({n})' if (n := d.get('cause_note')) else ''} | {d.get('progress')} | "
                         f"{'대상' if kinds.counts_for_rating(d.get('part'), d.get('dtype')) else '제외'}" for d in defects
                         if d.get("check") != "repaired" and not kinds.is_record(d.get("dtype")) and not kinds.is_repaired_type(d.get("dtype")))
        spec += DEFECTS_BLOCK.format(defects=rows or "(없음)")
    if combos:
        spec += METHOD_SPEC.format(prices=", ".join(f"{m}({u} {p:,}원)" if p else m for m, u, p in price_list or []),
                                   combos="\n".join(f"{i} | {c['part']} | {c['member']} | {c['dtype']}{' (0.3mm 이상)' if c['wide'] else ''} | {c['count']}개소 | "
                                                     f"{c['qty']}{c['unit']} | {c['max_width'] if c['max_width'] is not None else '-'} | {', '.join(c['causes']) or '-'} | "
                                                     f"{c['default']}" for i, c in enumerate(combos, 1)))
    two = is_type2(template) and not eval_items
    rule = GRADE_RULE2 if two else GRADE_RULE3
    if target:  # 등급 재산정 요청(10/19 형)
        label = grade_label(target, template)
        rule += (f"\n- 점검자 등급 재산정 요청: 이번 등급은 {label}(으)로 정했다. grade는 \"{label if two else target}\"로 하고, 등급 근거·결과표·종합결론"
                 + ("·18항목 평가(평가 점수 합이 이 등급이 나오게)" if eval_items else "") + "를 모두 이 등급에 맞게. 결함 사실·숫자는 바꾸지 말고 판단·표현만.")
    prompt = PROMPT.format(facility=facility, period=period, stats="\n".join(lines), parts=parts_facts, old=old_text[:6000] or "(없음)", items_spec=spec,
                           grade_rule=rule, leak_rule=manual3.LEAK_RULE, grade_pick="양호|보통|미흡|불량 중 하나" if two else "A~E 중 하나")
    from server.sitok import vision

    text = vision.ask(company_id, [], prompt, max_tokens=32000, writing=True)  # 3종 18항목·1.4·보수공법까지 쓰면 답이 김
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("AI 답에서 JSON을 찾지 못했습니다.")
    data = json.loads(m.group(0))
    data["sections"] = {k: str((data.get("sections") or {}).get(k) or "").strip() for k, _, _ in CATEGORIES}
    for k in ("findings", "repairs", "conclusion"):
        data[k] = [str(x).strip() for x in (data.get(k) or []) if str(x).strip()]
    for k in ("critical", "public", "next_focus", "grade_reason"):
        data[k] = str(data.get(k) or "").strip()
    data["grade"] = to_letter(str(data.get("grade") or ""), template)
    data["stats"] = {k: {x: st[k][x] for x in ("count", "grew", "new", "repaired", "max_width", "qty")} for k in st}
    if eval_items:  # 항목 이름·영역은 지난 보고서 표 것, 평가만 AI
        got = {int(x.get("no", 0)): x for x in (data.get("items") or []) if str(x.get("no", "")).isdigit() or isinstance(x.get("no"), int)}
        ok = {"우수", "양호", "보통", "미흡", "불량", "해당없음"}
        data["items"] = [{**it, "rating": got.get(it["no"], {}).get("rating") if got.get(it["no"], {}).get("rating") in ok else it["rating"],
                          "repair": "○" if str(got.get(it["no"], {}).get("repair", "")).strip() in ("○", "O", "o", "유") else "×",
                          "opinion": str(got.get(it["no"], {}).get("opinion") or "").strip(),
                          "basis": str(got.get(it["no"], {}).get("basis") or "").strip()} for it in eval_items]
        data["eval_opinion"] = str(data.get("eval_opinion") or "").strip()
        # 3종 등급은 18항목 점수로 정해짐(AI가 따로 고른 등급과 어긋나지 않게 근거도 점수로)
        from server.sitok.report_build import eval_score
        res = eval_score(data["items"])
        if res["grade"]:
            data["grade"] = res["grade"]
            data["grade_reason"] = (f"18항목 평가 종합 {res['total']:g}점("
                                    + ", ".join(f"{g} {a}/{b}={v:g}" for g, (a, b, v) in res["groups"].items()) + f") → {res['grade']}등급")
    else:
        data.pop("items", None)
    if fac_items:  # 항목 이름은 지난 보고서 표 것
        got = {int(x["no"]): x for x in (data.get("facility") or []) if str(x.get("no", "")).isdigit() or isinstance(x.get("no"), int)}
        data["facility"] = [{"no": it["no"], "name": it["name"], "has": bool(got.get(it["no"], {}).get("has")),
                             "state": str(got.get(it["no"], {}).get("state") or "").strip(), "where": str(got.get(it["no"], {}).get("where") or "").strip()}
                            for it in fac_items]
    else:
        data.pop("facility", None)
    if combos:  # 묶음 정보는 프로그램 것, 공법·1식 금액만 AI
        known = {m.replace(" ", "") for m, _, _ in price_list or []}
        got = {int(x["no"]): x for x in (data.get("methods") or []) if str(x.get("no", "")).isdigit() or isinstance(x.get("no"), int)}
        rows = []
        for i, c in enumerate(combos, 1):
            g = got.get(i, {})
            method = str(g.get("method") or "").strip() or c["default"]
            try:
                lump = int(float(str(g.get("lump") or 0).replace(",", ""))) if method.replace(" ", "") not in known else None
            except ValueError:
                lump = None
            rows.append({**{k: c[k] for k in ("key", "part", "member", "dtype", "wide", "count", "qty", "unit")}, "method": method, "lump": lump or None})
        data["methods"] = rows
    else:
        data.pop("methods", None)
    return data


SUMMARY_PROMPT = """당신은 한국의 시설물 정기안전점검(시설물안전법) 보고서를 쓰는 책임기술자입니다. 보고서 앞 "요약문 3.6 결언"의 본문을 쓰세요.
결언 첫 문단("금회 점검은 … 점검결과를 요약하면 다음과 같다.")은 이미 있으니 그 다음 문단들만 씁니다.

[용역] {title}
[시설물별 결과 — {n}개]
{rows}

규칙:
- 시설물마다의 종합결론·점검 주요결과를 묶어서 쓰되, 위에 없는 사실·숫자를 지어내지 말 것. 보고서 문어체("~판단된다", "~바람직할 것으로 판단된다").
- 문단 3개 안팎:
  1) "금번 {year}년 {half} 시설물 정기안전점검 점검결과, 전체 {n}개 시설물에 발생된 손상들은 …(주된 원인)… 구조안전성 판단 … 보수 필요 여부" (시설물이 하나면 "대상 시설물에").
  2) 등급별로 — 낮게 평가된 시설물(이름)과 그 결함·조치(관리주체가 유지관리계획에 따라 보수 …), 그 이외 시설물(이름)은 보고서 공법을 토대로 유지관리 계획 … .
  3) "이 외의 시설물에 대해서는 주기적인 점검을 통한 관찰로 유지관리를 실시한다면, 시설물의 사용성에는 문제가 없을 것으로 판단된다." 취지로 마무리.
- 등급 표기: {grade_note}
아래 JSON 하나로만 답하세요(설명 없이): {{"paragraphs": ["문단1", "문단2", "문단3"]}}"""


def summary_conclusion(title: str, year: int, half: str, rows: list[dict], template: str, company_id: int) -> list[str]:
    """요약문 3.6 결언 본문(10/16 민재형 "각 시설물의 결론을 묶어 AI 작성") — rows = [{name, grade, conclusion, findings}] 동마다."""
    from server.sitok import vision

    lines = "\n".join(f"- {x['name']} | 금회 등급 {x['grade'] or '-'} | 종합결론: {' / '.join(x.get('conclusion') or [])[:700]} | 주요결과: {' / '.join(x.get('findings') or [])[:500]}"
                      for x in rows)
    note = "2종 — 양호·보통·미흡·불량(낱말 그대로, \"등급\"을 붙이지 않음)" if is_type2(template) else "3종 — A~E 글자에 \"등급\"(예: B등급)"
    text = vision.ask(company_id, [], SUMMARY_PROMPT.format(title=title, year=year, half=half, n=len(rows), rows=lines, grade_note=note), max_tokens=4000, writing=True)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("AI 답에서 JSON을 찾지 못했습니다.")
    return [str(x).strip() for x in (json.loads(m.group(0)).get("paragraphs") or []) if str(x).strip()]
