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
[전회 정기점검 결과 — 요약표 "전회" 칸(전회차 보고서 그대로, 바꾸지 말 것)]
{prev_rows}
{facts}

규칙:
- 사실은 위 목록에 있는 것만. 없는 결함·숫자를 지어내지 말 것. 결함이 없는 부위는 "침하·활동·세굴 등이 발생하지 않은 양호한 상태" 취지로 짧게.
- 진행된 결함(진행)·새로 찾은 결함(신규)·보수 완료가 있으면 전회차 대비 변화를 반영.
- 옹벽 결함 낱말: 블록 균열(0.3mm 미만/이상)·단부파손·이격·백태·채움재유출·실링재탈락·잡목식생·토사·낙엽퇴적·배부름·침하·세굴·전도·경사·활동.
  배부름·침하·세굴·전도·경사·활동은 구조 안전성에 바로 이어지는 진행성 결함이라 있으면 반드시 짚고 주의관찰·계측을 권고.
- 조치: 잡목식생 → 잡목 및 식생제거, 배수로 퇴적 → 배수로 정비, 채움재유출 → 충진보수, 이격 → 실링보수, 균열 0.3mm 미만 → 표면처리·주의관찰, 0.3mm 이상 → 주입보수, 경미하면 주의관찰.
- 문장은 보고서 문어체("~조사되었다", "~판단된다"), 절마다 2~4문장. 지난 보고서를 베끼지 말고 이번 숫자·부위를 구체적으로.
- 결과표 "점검 주요결과"는 반드시 4줄: "⦁기초부 : …", "⦁상  부 : …", "⦁전면부 : …", "⦁기  타 : …"(각 80자 이내).
- 요약표 "금회 점검 결과"·"조치필요사항"·"종합의견"은 이번 결함·상태양호 사진으로. "전회" 칸은 위 [전회 정기점검 결과]를 그대로(없으면 빈 글).
- 1.5 유지관리방안(maint_plan)은 이번 결함·상태양호 사진과 옹벽 형식으로 중점 유지관리방안 글머리 6~10줄(예: "⦁균열, 이격, 백태, 진행여부", "⦁기울기, 배부름 진행여부",
  "⦁기초 침하, 활동, 노출 여부", "⦁배수불량으로 인한 체수 및 월류", 보강토면 "⦁보강토 블록 균열, 이격, 채움재 유출 진행여부", 잡목이 있으면 "⦁잡목 및 식생 제거 여부").
{items_rule}- 점검결과 등급(제2종시설물)은 양호·보통·미흡·불량 중 하나와 근거(중대결함 없고 국부 손상뿐이면 보통 양호, 주요부(전면부·기초)에 진행성 결함이면 보통~미흡, 위험하면 불량).{grade_rule}

아래 JSON 객체 하나로만 답하세요(설명 없이):
{{"critical": "결과표 중대한 결함 칸 — 시행령 제18조제1항의 중대한 결함이 있을 때만 그 내용 한 줄, 없으면 \"없음\"만",
 "public": "결과표 공중이 이용하는 부위에 결함 칸 — 펜스·점검로·도로포장에 결함이 있을 때만 위치·결함 한 줄, 없으면 \"없음\"만",
 "findings": ["⦁기초부 : …", "⦁상  부 : …", "⦁전면부 : …", "⦁기  타 : …"],
 "repairs": ["결과표 주요 보수·보강 줄 1~3개(예: ⦁잡목 및 식생제거)"],
 "next_focus": "참고사항 — 차기 점검 시 중점 확인 부위 한 줄(예: 균열 및 이격부 추가 손상 발생 여부 점검)",
 "sections": {{"found": "1.4.1 지반 및 기초부 조사결과 글", "front": "1.4.2 옹벽 전면부 조사결과 글", "etc": "1.4.3 기타(배수시설·사면·점검로) 조사결과 글", "public": "1.4.4 공중이 이용하는 부위 글"}},
 "summary_rows": [{{"name": "전면부", "prev": "⦁전회 결과(줄마다 ⦁)", "now": "⦁금회 결과", "action": "⦁조치필요사항"}}, {{"name": "상부", ...}}, {{"name": "기초/지반", ...}}, {{"name": "배수시설", ...}}, {{"name": "공중이 이용하는시설", ...}}],
 "summary_opinion": "실시결과 요약표 종합의견 한두 문장(⦁로 시작)",
 "maint_plan": ["⦁중점 유지관리방안 글머리 6~10줄"],
 "conclusion": {{"survey": ["종합결론 외관조사결과 글머리 1~3개(⦁)"], "repair": ["보수필요사항 글머리 1~3개(⦁)"], "urgent": "긴급점검 및 정밀안전진단 필요여부(예: ⦁필요치 않음)"}},
 "grade": "양호", "grade_reason": "근거"{items_spec}{methods_spec}}}"""

ITEMS_RULE = "- 3종시설물: 안전등급은 아래 18항목 평가 점수로 프로그램이 계산(우수10·양호8·보통5·미흡2·불량0, 주요60·일반20·부대20, 9·7·5·3점 이상 A~D) — \"grade\"도 그 계산과 맞게(A는 양호로 적음).\n"
ITEMS_SPEC = """,
 "items": [{{"no": 항목번호, "rating": "우수|양호|보통|미흡|불량|해당없음", "repair": "○ 또는 ×", "opinion": "점검자 의견 15자 안팎(예: 일부 균열 발생)", "basis": "근거 결함 — 부위·번호·크기와 맞춘 기준(걸린 결함이 없으면 빈 글)"}} — 아래 18항목 전부],
 "eval_opinion": "안전등급 평가 종합의견 및 특기사항 한두 문장"

18항목 평가는 반드시 제3종시설물 정기안전점검 매뉴얼(2026) 옹벽 평가방법대로 — 아래 원칙과 항목마다 적힌 a~e 기준으로.

{items}"""


def _line(d: dict) -> str:
    chk = {"same": "그대로", "grew": "진행", "repaired": "보수완료", "new": "신규"}.get(d.get("check") or "", "미확인")
    cause = (d.get("cause") or "") + (f"({d['cause_note']})" if d.get("cause_note") else "")
    return f"{d.get('floor')} | {d.get('part')} | {d.get('member') or '-'} | {d.get('dtype')} | {d.get('count') or '-'} | {d.get('width') or '-'} | {d.get('length') or '-'} | {chk} | {cause}"


def _bul(s: str) -> str:
    s = (s or "").strip()
    return s if not s or s.startswith("⦁") else "⦁" + s


def _norm(raw: dict, defects: list, eval_items: list | None = None, form: str = "") -> dict:
    """AI 답 → 보고서가 쓰는 꼴(빈 칸은 fallback 값). eval_items(3종)면 18항목·등급(점수)도."""
    fb = fallback(defects, "", "", None, form)
    out = dict(fb)
    if not isinstance(raw, dict):
        return _with_items(out, None, eval_items, form, defects) if eval_items else out
    for k in ("critical", "public", "next_focus", "summary_opinion", "grade_reason"):
        if str(raw.get(k) or "").strip():
            out[k] = str(raw[k]).strip()
    for k in ("findings", "repairs", "maint_plan"):
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
    return _with_items(out, raw, eval_items, form, defects) if eval_items else out


def fallback(defects: list, prev_grade: str = "", public: str = "", eval_items: list | None = None, form: str = "") -> dict:
    """AI 없이 — 결함 목록으로 만든 고정 틀(점검자가 고침). public = 공중이용 탭 사진 항목 이름들(쉼표) — 없으면 양호. eval_items(3종)면 18항목도 어림."""
    out = _fallback(defects, prev_grade, public, form)
    return _with_items(out, None, eval_items, form, defects) if eval_items else out


def _fallback(defects: list, prev_grade: str = "", public: str = "", form: str = "") -> dict:
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
    return {"critical": "없음", "maint_plan": maint_plan(defects, form), "public": "없음", "findings": findings, "repairs": repairs,  # 작성방법 — 결함이 없으면 "없음"(10/21)
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


MAINT_COMMON = ["⦁균열, 이격, 백태, 진행여부", "⦁기울기, 배부름 진행여부", "⦁기초 침하, 활동, 노출 여부",
                "⦁수평활동력의 증가 및 옹벽과 지반의 마찰저항 감소에 의한 활동 여부 확인", "⦁추가적인 수평활동력의 증가 및 저항력 감소에 의한 계획선형오차 여부 확인",
                "⦁기초지반 토립자의 이동에 의한 세굴 발생 여부 확인", "⦁배면 지반의 침하에 의한 전면부 배부름 발생 여부 확인", "⦁배수불량으로 인한 체수 및 월류", "⦁배수로 정비 여부"]
MAINT_FORM = {"보강토": "⦁보강토 블록 균열, 이격, 채움재 유출 진행여부", "콘크리트": "⦁콘크리트 균열, 박락, 철근노출 진행여부",
              "석축": "⦁석재 이탈, 줄눈 탈락 진행여부", "돌망태": "⦁철망 부식·파손, 채움돌 유실 진행여부"}


def maint_plan(defects: list, form: str = "") -> list[str]:
    """1.5 유지관리방안 기본 글머리(AI 없을 때) — 형식 줄 + 공통 + 이번 결함(잡목·퇴적)으로 더하는 줄."""
    out = ([MAINT_FORM[form]] if form in MAINT_FORM else []) + list(MAINT_COMMON)
    kinds_ = " ".join(str(d.get("dtype") or "") for d in defects)
    if "잡목" in kinds_ or "식생" in kinds_:
        out.append("⦁잡목 및 식생 제거 여부")
    if "퇴적" in kinds_:
        out.append("⦁배수로 낙엽·토사 퇴적 제거 여부")
    return out


def apply_prev(out: dict, ps: dict | None) -> dict:
    """요약표 "전회" 칸을 자료(prev_summary: 전회차 회차 > 전회차 PDF)로 — AI가 쓴 전회 글은 버림. 없으면(첫 회차) 빈 글 + src none(표엔 "전회차 없음")."""
    ps = ps or {"rows": {}, "label": "", "src": "none", "grade": ""}
    rows = ps.get("rows") or {}
    sq = lambda s: (s or "").replace(" ", "")  # noqa: E731
    for row in out.get("summary_rows") or []:
        hit = next((v for k, v in rows.items() if sq(k) == sq(row.get("name"))), None)
        row["prev"] = _bul(hit) if hit and hit.strip("⦁ -") else ("" if ps.get("src") == "none" else row.get("prev") or "")
    out["summary_prev_src"] = ps.get("src") or "none"
    out["summary_prev_label"] = ps.get("label") or ""
    if ps.get("grade"):
        out["summary_prev_grade"] = ps["grade"]
    return out


def draft(facility: str, period: str, defects: list, prev_captions: list[str], facts: str, company_id: int, target_grade: str = "", prev_grade: str = "",
          public: str = "", eval_items: list | None = None, form: str = "", prev_rows: dict | None = None, combos: list | None = None,
          price_list: list | None = None) -> dict:
    """eval_items = 3종 18항목(wall_manual.items_for — 제외항목은 해당없음)이면 항목 평가도 AI가(등급은 점수로), 2종이면 None.
    prev_rows = 요약표 전회 칸 {부재명: 글}(wall_collect.prev_summary — AI에게 보여 주고 결과에도 그대로 넣음).
    combos/price_list = 보수공법 묶음(sitok_defects.method_combos)·단가표 — 건축물처럼 묶음마다 공법(단가표 이름이면 단가, 아니면 1식 금액) → 1.6 개략공사비(형 10/21)."""
    from server.sitok import ai_draft, vision, wall_manual

    rule = f"\n- 점검자가 요청한 등급: {target_grade} — 그 등급에 맞는 근거·문장으로." if target_grade else ""
    if eval_items:
        rule += "·18항목 평가(평가 점수 합이 이 등급이 나오게)" if target_grade else ""
    prompt = PROMPT.format(facility=facility, period=period, defects="\n".join(_line(d) for d in defects) or "(결함 없음)",
                           prev="\n".join(prev_captions) or "(없음)", facts=facts or "", grade_rule=rule,
                           prev_rows="\n".join(f"{k}: {v}" for k, v in (prev_rows or {}).items() if v) or "(전회차 없음 — 첫 회차)",
                           items_rule=ITEMS_RULE if eval_items else "", items_spec=ITEMS_SPEC.format(items=wall_manual.criteria(eval_items, form)) if eval_items else "",
                           methods_spec=ai_draft.METHOD_SPEC.format(
                               prices=", ".join(f"{m}({u} {p:,}원)" if p else m for m, u, p in price_list or []),
                               combos="\n".join(f"{i} | {c['part']} | {c['member']} | {c['dtype']}{' (0.3mm 이상)' if c['wide'] else ''} | {c['count']}개소 | "
                                                 f"{c['qty']}{c['unit']} | {c['max_width'] if c['max_width'] is not None else '-'} | {', '.join(c['causes']) or '-'} | "
                                                 f"{c['default']}" for i, c in enumerate(combos, 1))) if combos else "")
    try:
        raw = vision.ask_json(company_id, [], prompt, max_tokens=8000 if eval_items else 6000, writing=True)
    except Exception:  # noqa: BLE001
        raw = None
    out = _norm(raw, defects, eval_items, form) if raw else fallback(defects, prev_grade, public, eval_items, form)
    out["wall"] = True
    out["ai_ok"] = bool(raw)
    if combos:
        out["methods"] = methods_rows(raw, combos, price_list)
    return out


def methods_rows(raw: dict | None, combos: list, price_list: list | None) -> list[dict]:
    """묶음 정보는 프로그램 것, 공법·1식 금액만 AI 답(없으면 기본 공법) — ai_draft와 같은 꼴(AI 창 보수공법 줄·cost_rows)."""
    known = {m.replace(" ", "") for m, _, _ in price_list or []}
    got = {}
    for x in (raw or {}).get("methods") or []:
        try:
            got[int(x.get("no"))] = x
        except (TypeError, ValueError):
            continue
    rows = []
    for i, c in enumerate(combos, 1):
        g = got.get(i, {})
        method = str(g.get("method") or "").strip() or c["default"]
        try:
            lump = int(float(str(g.get("lump") or 0).replace(",", ""))) if method.replace(" ", "") not in known else None
        except ValueError:
            lump = None
        rows.append({**{k: c[k] for k in ("key", "part", "member", "dtype", "wide", "count", "qty", "unit")}, "method": method, "lump": lump or None})
    return rows


def _with_items(out: dict, raw: dict | None, eval_items: list, form: str, defects: list) -> dict:
    """18항목: 이름·영역·제외는 매뉴얼 것, 평가·의견·보수필요·근거는 AI 답(없으면 결함으로 어림) → 등급은 점수로(wall_manual.score)."""
    from server.sitok import wall_manual

    ok = {"우수", "양호", "보통", "미흡", "불량", "해당없음"}
    got = {}
    for x in (raw or {}).get("items") or []:
        try:
            got[int(x.get("no"))] = x
        except (TypeError, ValueError):
            continue
    base = wall_manual.default_ratings(eval_items, defects, form)
    ex = wall_manual.EXCLUDE.get(form, set())
    items = []
    for it, dft in zip(eval_items, base):
        g = got.get(it["no"], {})
        rating = g.get("rating") if g.get("rating") in ok else dft["rating"]
        if it["no"] in ex:
            rating = "해당없음"
        items.append({**it, "rating": rating, "repair": "○" if str(g.get("repair") or dft.get("repair")).strip() == "○" else "×",
                      "opinion": str(g.get("opinion") or dft.get("opinion") or "").strip()[:60], "basis": str(g.get("basis") or "").strip()[:120]})
    out["items"] = items
    out["eval_opinion"] = str((raw or {}).get("eval_opinion") or "").strip() or ("점검결과 " + ("중대한 결함 없이 국부적인 손상만 조사되어 " if out.get("grade") in ("양호", "우수") else "") + "안전등급 평가 결과와 같이 판정함")
    res = wall_manual.score(items, form)
    if res.get("grade"):
        out["grade"] = res["grade"]  # 글자(A~E) — 결과표 3종 등급 칸, 요약표·요약문은 word()로
        out["grade_reason"] = (out.get("grade_reason") or "") + f" (18항목 점수 {res['total']}점: " + ", ".join(f"{g} {a}/{b}={v:g}" for g, (a, b, v) in res["groups"].items()) + f" → {res['grade']}등급" + (f", {res['forced']}" if res.get("forced") else "") + ")"
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


def letter3(grade: str, items: list | None = None, form: str = "") -> str:
    """3종 결과표 "등급" 칸 글자(A~E) — 18항목이 있으면 점수로, 없으면 글자 그대로나 말 → 글자."""
    if items:
        from server.sitok import wall_manual

        got = wall_manual.score(items, form).get("grade")
        if got:
            return got
    v = (grade or "").strip().upper()
    return v if v in ("A", "B", "C", "D", "E") else letter(grade)


def is_wall_ai(final: dict | None) -> bool:
    return bool(final) and bool(final.get("wall")) and isinstance(final.get("sections"), dict) and "front" in final["sections"]


def to_json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False)


_ = re
