"""옹벽 정기안전점검 AI 초안(2026-10-20 옹벽 3단계) — 현장 조사 결함(부위별)으로 결과표·1.4 현장조사 결과 글·실시결과 요약표·종합결론·등급 초안.
결과 JSON은 점검자가 AI 초안 화면(js/sitok-ai.js — 옹벽 항목 이름은 서버 sections_list)에서 고쳐 확정. AI가 안 되면 fallback(결함으로 만든 고정 틀)."""
from __future__ import annotations

import json
import re

from server.sitok import kinds

SECTIONS = [("found", "1.4.1 지반 및 기초부"), ("front", "1.4.2 옹벽 전면부"), ("etc", "1.4.3 기타(주변영향인자·점검로·배수시설)"), ("public", "1.4.4 공중이 이용하는 부위")]
SUMMARY_ROWS = ["전면부", "상부", "기초/지반", "배수시설", "공중이 이용하는시설"]
UNIT_TO_ROW = {"전면부": "전면부", "상부": "상부", "지반 및 기초부": "기초/지반", "배수시설": "배수시설", "기타": "배수시설"}
UNIT_TO_SECTION = {"지반 및 기초부": "found", "전면부": "front", "공중이용시설": "public"}
GRADES2 = ("양호", "보통", "미흡", "불량")

PROMPT = """당신은 한국의 시설물 정기안전점검(시설물안전법) 보고서를 쓰는 책임기술자입니다. 아래 옹벽 이번 회차 외관조사 결과로 보고서 문장 초안을 쓰세요.

[시설물] {facility}
[이번 회차] {period}
[부위별 결함 — 이번 회차 현장 조사(부위 | 구분 | 부재 | 결함유형 | 개수 | 폭 | 길이 | 확인(그대로·진행·보수완료·신규) | 원인(근거))]
{defects}
[전회차 사진 설명(지난 보고서 사진첩) — 전회 결과 참고]
{prev}
{facts}

규칙:
- 사실은 위 목록에 있는 것만. 없는 결함·숫자를 지어내지 말 것. 결함이 없는 부위는 "침하·활동·세굴 등이 발생하지 않은 양호한 상태" 취지로 짧게.
- 진행된 결함(진행)·새로 찾은 결함(신규)·보수 완료가 있으면 전회차 대비 변화를 반영.
- 옹벽 결함 낱말: 블록 균열(0.3mm 미만/이상)·단부파손·이격·백태·채움재유출·실링재탈락·잡목식생·토사·낙엽퇴적·배부름·침하·세굴·전도·경사·활동.
  배부름·침하·세굴·전도·경사·활동은 구조 안전성에 바로 이어지는 진행성 결함이라 있으면 반드시 짚고 주의관찰·계측을 권고.
- 조치: 잡목식생 → 잡목 및 식생제거, 배수로 퇴적 → 배수로 정비, 채움재유출 → 충진보수, 이격 → 실링보수, 균열 0.3mm 미만 → 표면처리·주의관찰, 0.3mm 이상 → 주입보수, 경미하면 주의관찰.
- 문장은 보고서 문어체("~조사되었다", "~판단된다"), 절마다 2~4문장. 지난 보고서를 베끼지 말고 이번 숫자·부위를 구체적으로.
- 결과표 "점검 주요결과"는 반드시 4줄: "⦁기초부 : …", "⦁상  부 : …", "⦁전면부 : …", "⦁기  타 : …"(각 80자 이내).
- 점검결과 등급(제2종시설물)은 양호·보통·미흡·불량 중 하나와 근거(중대결함 없고 국부 손상뿐이면 보통 양호, 주요부(전면부·기초)에 진행성 결함이면 보통~미흡, 위험하면 불량).{grade_rule}

아래 JSON 객체 하나로만 답하세요(설명 없이):
{{"critical": "결과표 중대결함 칸(예: 없음)",
 "public": "결과표 공중이 이용하는 부위에 결함 칸 한 문장(펜스·점검로·도로포장 — 없으면 해당없음)",
 "findings": ["⦁기초부 : …", "⦁상  부 : …", "⦁전면부 : …", "⦁기  타 : …"],
 "repairs": ["결과표 주요 보수·보강 줄 1~3개(예: ⦁잡목 및 식생제거)"],
 "next_focus": "참고사항 — 차기 점검 시 중점 확인 부위 한 줄(예: 균열 및 이격부 추가 손상 발생 여부 점검)",
 "sections": {{"found": "1.4.1 지반 및 기초부 조사결과 글", "front": "1.4.2 옹벽 전면부 조사결과 글", "etc": "1.4.3 기타(배수시설·사면·점검로) 조사결과 글", "public": "1.4.4 공중이 이용하는 부위 글"}},
 "summary_rows": [{{"name": "전면부", "prev": "⦁전회 결과(줄마다 ⦁)", "now": "⦁금회 결과", "action": "⦁조치필요사항"}}, {{"name": "상부", ...}}, {{"name": "기초/지반", ...}}, {{"name": "배수시설", ...}}, {{"name": "공중이 이용하는시설", ...}}],
 "summary_opinion": "실시결과 요약표 종합의견 한두 문장(⦁로 시작)",
 "conclusion": {{"survey": ["종합결론 외관조사결과 글머리 1~3개(⦁)"], "repair": ["보수필요사항 글머리 1~3개(⦁)"], "urgent": "긴급점검 및 정밀안전진단 필요여부(예: ⦁필요치 않음)"}},
 "grade": "양호", "grade_reason": "근거"}}"""


def _line(d: dict) -> str:
    chk = {"same": "그대로", "grew": "진행", "repaired": "보수완료", "new": "신규"}.get(d.get("check") or "", "미확인")
    cause = (d.get("cause") or "") + (f"({d['cause_note']})" if d.get("cause_note") else "")
    return f"{d.get('floor')} | {d.get('part')} | {d.get('member') or '-'} | {d.get('dtype')} | {d.get('count') or '-'} | {d.get('width') or '-'} | {d.get('length') or '-'} | {chk} | {cause}"


def _bul(s: str) -> str:
    s = (s or "").strip()
    return s if not s or s.startswith("⦁") else "⦁" + s


def _norm(raw: dict, defects: list) -> dict:
    """AI 답 → 보고서가 쓰는 꼴(빈 칸은 fallback 값)."""
    fb = fallback(defects, "")
    out = dict(fb)
    if not isinstance(raw, dict):
        return out
    for k in ("critical", "public", "next_focus", "summary_opinion", "grade_reason"):
        if str(raw.get(k) or "").strip():
            out[k] = str(raw[k]).strip()
    for k in ("findings", "repairs"):
        v = raw.get(k)
        if isinstance(v, list) and v:
            out[k] = [_bul(str(x)) for x in v if str(x).strip()]
    sec = raw.get("sections") if isinstance(raw.get("sections"), dict) else {}
    out["sections"] = {k: str(sec.get(k) or fb["sections"][k]).strip() for k, _ in SECTIONS}
    rows = raw.get("summary_rows") if isinstance(raw.get("summary_rows"), list) else []
    by = {str(r.get("name") or "").replace(" ", ""): r for r in rows if isinstance(r, dict)}
    out["summary_rows"] = [{"name": n, **{k: _bul(str(by.get(n.replace(" ", ""), {}).get(k) or fb_row.get(k) or "")) for k in ("prev", "now", "action")}}
                           for n, fb_row in zip(SUMMARY_ROWS, fb["summary_rows"])]
    con = raw.get("conclusion") if isinstance(raw.get("conclusion"), dict) else {}
    out["conclusion"] = {"survey": [_bul(str(x)) for x in (con.get("survey") or fb["conclusion"]["survey"]) if str(x).strip()],
                         "repair": [_bul(str(x)) for x in (con.get("repair") or fb["conclusion"]["repair"]) if str(x).strip()],
                         "urgent": _bul(str(con.get("urgent") or fb["conclusion"]["urgent"]))}
    g = str(raw.get("grade") or "").strip()
    out["grade"] = g if g in GRADES2 else fb["grade"]
    return out


def fallback(defects: list, prev_grade: str = "", public: str = "") -> dict:
    """AI 없이 — 결함 목록으로 만든 고정 틀(점검자가 고침). public = 공중이용 탭 사진 항목 이름들(쉼표) — 없으면 양호."""
    by_unit: dict[str, list] = {}
    for d in defects:
        if d.get("check") == "repaired" or kinds.is_record(d.get("dtype") or ""):
            continue
        by_unit.setdefault(d.get("floor") or "기타", []).append(d)
    names = lambda u: ", ".join(dict.fromkeys(f"{(d.get('member') or '').strip()} {d.get('dtype')}".strip() for d in by_unit.get(u, []))) or ""  # noqa: E731
    sev = any(any(w in (d.get("dtype") or "") for w in ("배부름", "침하", "세굴", "전도", "활동")) for d in defects)
    base = names("지반 및 기초부")
    front = names("전면부")
    top = names("상부")
    drain = names("배수시설") or names("기타")
    pub_txt = f"{public} 상태양호" if public else "해당 시설 양호"
    findings = [f"⦁기초부 : {base + ' 발생' if base else '침하, 활동, 세굴 등이 발생하지 않은 양호한 상태임'}",
                f"⦁상  부 : {top or '상태양호'}",
                f"⦁전면부 : {front + ' 등이 국부적으로 발생하였으나, 전도, 경사, 배부름이 없는 양호한 상태임' if front and not sev else (front + ' 발생 — 진행성 확인 필요' if front else '상태양호')}",
                f"⦁기  타 : {drain + ' 발생' if drain else '배수시설 및 사면 상태양호'}"]
    acts = {"잡목식생": "잡목 및 식생제거", "퇴적": "배수로 정비", "유출": "충진보수", "이격": "이격부 실링보수"}
    repairs = list(dict.fromkeys(a for u in by_unit.values() for d in u for k, a in acts.items() if k in (d.get("dtype") or ""))) or ["⦁주의관찰"]
    repairs = [_bul(x) for x in repairs]
    rowtxt = lambda u: _bul(names(u) or "상태양호")  # noqa: E731
    rows = [{"name": "전면부", "prev": "⦁-", "now": rowtxt("전면부"), "action": "⦁주의관찰"},
            {"name": "상부", "prev": "⦁-", "now": rowtxt("상부"), "action": "⦁잡목식생 제거" if top else "⦁주의관찰"},
            {"name": "기초/지반", "prev": "⦁-", "now": rowtxt("지반 및 기초부"), "action": "⦁주의관찰"},
            {"name": "배수시설", "prev": "⦁-", "now": _bul(drain or "상태양호"), "action": "⦁배수로 정비" if "퇴적" in drain else "⦁주의관찰"},
            {"name": "공중이 이용하는시설", "prev": "⦁-", "now": _bul(pub_txt), "action": "⦁주의관찰"}]
    grade = prev_grade if prev_grade in GRADES2 else ("보통" if sev else "양호")
    return {"critical": "⦁없음", "public": "⦁" + (f"{public} 전반적으로 양호한 상태" if public else "전반적으로 양호한 상태"), "findings": findings, "repairs": repairs,
            "next_focus": "균열 및 이격부 추가 손상 발생 여부 점검",
            "sections": {"found": f"지반 및 기초부 조사결과, {base + '이(가) 조사되었으나 ' if base else ''}침하·활동·세굴 등 구조적 이상은 없는 양호한 상태로 조사되었다.",
                         "front": f"옹벽 전면부 외관조사 결과 {front + ' 등이 국부적으로 조사되었으며, ' if front else '특이 손상은 조사되지 않았으며, '}"
                                  "전도·경사·배부름 등 구조적인 변형은 없는 것으로 조사되었다. 손상의 진행 여부를 지속적으로 관찰하고 추후 일괄보수를 실시하는 것이 바람직할 것으로 판단된다.",
                         "etc": f"주변영향인자(배수시설 및 사면상태 등) 조사결과 {drain + ' 등이 조사되었으며, ' if drain else '특이사항은 없었으며, '}사면·안전펜스 등은 양호한 상태로 조사되었다.",
                         "public": f"공중이 이용하는 부위({public or '추락방지시설·점검로 등'}) 조사결과 전반적으로 양호한 상태로 유지되고 있다."},
            "summary_rows": rows, "summary_opinion": "⦁점검결과 " + (", ".join(x for x in (front, top, drain) if x) or "특이 손상 없이") + " 조사되었으며, 손상의 진행성은 없는 것으로 조사되었다.",
            "conclusion": {"survey": ["⦁점검결과 " + (", ".join(x for x in (front, top, base, drain) if x) + " 등의 손상이 조사되었으며, 손상의 진행성은 없는 것으로 조사되었다." if any((front, top, base, drain)) else "특이 손상은 조사되지 않았다.")],
                           "repair": repairs if repairs != ["⦁주의관찰"] else ["⦁손상이 경미하므로 주의관찰"],
                           "urgent": "⦁필요치 않음"},
            "grade": grade, "grade_reason": "중대한 결함 없이 국부적인 손상만 조사됨" if not sev else "진행성 결함이 있어 지속 관찰 필요"}


def draft(facility: str, period: str, defects: list, prev_captions: list[str], facts: str, company_id: int, target_grade: str = "", prev_grade: str = "",
          public: str = "") -> dict:
    from server.sitok import vision

    rule = f"\n- 점검자가 요청한 등급: {target_grade} — 그 등급에 맞는 근거·문장으로." if target_grade else ""
    prompt = PROMPT.format(facility=facility, period=period, defects="\n".join(_line(d) for d in defects) or "(결함 없음)",
                           prev="\n".join(prev_captions) or "(없음)", facts=facts or "", grade_rule=rule)
    try:
        raw = vision.ask_json(company_id, [], prompt, max_tokens=6000)
    except Exception:  # noqa: BLE001
        raw = None
    out = _norm(raw, defects) if raw else fallback(defects, prev_grade, public)
    out["wall"] = True
    out["ai_ok"] = bool(raw)
    return out


def section_list() -> list[list[str]]:
    return [list(x) for x in SECTIONS]


def letter(grade_word: str) -> str:
    return {"양호": "B", "보통": "C", "미흡": "D", "불량": "E"}.get(grade_word, "")


def word(letter_or_word: str) -> str:
    v = (letter_or_word or "").strip()
    if v in GRADES2:
        return v
    return {"A": "양호", "B": "양호", "C": "보통", "D": "미흡", "E": "불량"}.get(v.upper(), "")


def is_wall_ai(final: dict | None) -> bool:
    return bool(final) and bool(final.get("wall")) and isinstance(final.get("sections"), dict) and "front" in final["sections"]


def to_json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False)


_ = re
