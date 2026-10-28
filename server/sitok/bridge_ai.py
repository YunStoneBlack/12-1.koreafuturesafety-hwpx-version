"""교량 정기안전점검 AI 초안(2026-10-29 사용자 "옹벽편 → 교량편 추가, 기능은 옹벽과 동일") — 옹벽판 wall_ai.py와 같은 결과 모양·같은 함수 이름.
현장 조사 결함(부위별 — kinds.BRIDGE_PARTS)으로 결과표·1.4.1~1.4.7 현장조사 결과 글·1.4.8 실시결과 요약표·1.6 유지관리방안·종합결론·등급(3종 15항목 bridge_manual) 초안.
결과는 점검자가 AI 초안 화면(js/sitok-ai.js — 절 이름은 서버 sections_list)에서 고쳐 확정. AI가 안 되면 fallback(결함으로 만든 고정 틀).
원본 = 정기안전점검_교량_원본.hwpx(형 10/29 — 공통편은 교량·옹벽·터널·절토사면 같이, 시설물편 교량편)."""
from __future__ import annotations

from server.sitok import kinds
from server.sitok.wall_ai import GRADES2, _bul, _line, apply_prev, letter, methods_rows, to_json, word  # noqa: F401 — 같은 이름으로 내보냄

__all__ = ["SECTIONS", "SUMMARY_ROWS", "FINDINGS", "apply_prev", "draft", "fallback", "letter", "letter3", "word", "to_json", "is_wall_ai", "section_list",
           "maint_plan"]  # wall_ai와 같은 이름(apply_prev·word·letter·to_json은 그대로 다시 내보냄)

SECTIONS = [("super", "1.4.1 상부구조(바닥판, 거더)"), ("sub", "1.4.2 하부구조(교대 및 교각, 주탑, 기초)"), ("bearing", "1.4.3 받침(교량받침)"),
            ("cable", "1.4.4 케이블(케이블, 정착구, 행어밴드, 새들)"), ("second", "1.4.5 2차부재(가로보 및 세로보)"),
            ("etc", "1.4.6 기타부재(신축이음, 배수시설, 난간 및 연석, 교면포장 등)"), ("public", "1.4.7 공중이 이용하는 부위")]
SUMMARY_ROWS = ["상부구조", "하부구조", "받침", "케이블", "2차부재", "기타부재", "공중이 이용하는시설"]  # 원본 1.4.8 요약표 줄(10×4 — 안전등급·종합의견 줄은 따로)
UNIT_TO_SECTION = {"상부구조": "super", "하부구조": "sub", "받침": "bearing", "케이블": "cable", "2차부재": "second", "기타부재": "etc", "공중이용시설": "public"}
FINDINGS = [("상부구조", "상부구조"), ("하부구조", "하부구조"), ("받침", "받  침"), ("케이블", "케이블"), ("2차부재", "2차부재"), ("기타부재", "기타부재")]  # 결과표·총괄표 점검 주요결과 6줄
SUMMARY_LABEL = "1.4.8"

PROMPT = """당신은 한국의 시설물 정기안전점검(시설물안전법) 보고서를 쓰는 책임기술자입니다. 아래 교량 이번 회차 외관조사 결과로 보고서 문장 초안을 쓰세요.

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
- 사실은 위 목록에 있는 것만. 없는 결함·숫자를 지어내지 말 것. 결함이 없는 부위는 "특이 손상이 없는 양호한 상태" 취지로 짧게.
- 그 부재가 없는 교량(케이블이 없는 거더교·슬래브교, 가로보·세로보가 없는 슬래브교 등)은 그 절·요약표 줄을 "해당 부재 없음"으로. 상부 형식으로 판단하고 모르면 결함·사진대로.
- 진행된 결함(진행)·새로 찾은 결함(신규)·보수 완료가 있으면 전회차 대비 변화를 반영.
- 교량 결함 낱말: 균열(0.3mm 미만/이상)·망상균열·백태·누수·박리·박락·층분리·철근노출·재료분리·파손·부식·도장박리·변형·세굴·침하·토사·이물질퇴적·배수불량·유간이상·볼트이완·탈락.
  기초 세굴·침하, 교각·교대 기울음, 받침 파손·신축기능 불량, 거더 단부 균열은 구조 안전성에 바로 이어지니 있으면 반드시 짚고 주의관찰·계측을 권고.
- 조치: 균열 0.3mm 미만 → 표면처리·주의관찰, 0.3mm 이상 → 주입보수, 박리·박락·철근노출 → 단면보수, 백태·누수 → 원인부 방수·주입, 강재 부식·도장박리 → 재도장,
  신축이음 토사·이물질 퇴적 → 청소, 배수구·배수관 막힘 → 배수시설 정비, 교면포장 손상 → 포장 보수, 난간 부식·이완 → 보수·재도장, 경미하면 주의관찰.
- 문장은 보고서 문어체("~조사되었다", "~판단된다"), 절마다 2~4문장. 지난 보고서를 베끼지 말고 이번 숫자·부위를 구체적으로.
- 결과표 "점검 주요결과"는 반드시 6줄: "⦁상부구조 : …", "⦁하부구조 : …", "⦁받  침 : …", "⦁케이블 : …", "⦁2차부재 : …", "⦁기타부재 : …"(각 70자 이내, 부재가 없으면 "해당 부재 없음").
- 요약표 "금회 점검 결과"·"조치필요사항"·"종합의견"은 이번 결함·상태양호 사진으로. "전회" 칸은 위 [전회 정기점검 결과]를 그대로(없으면 빈 글).
- 1.6 유지관리방안(maint_plan)은 이번 결함·상태양호 사진과 교량 형식으로 중점 유지관리방안 글머리 6~10줄(예: "⦁거더·바닥판 균열, 박리·박락, 철근노출 진행여부",
  "⦁교량받침 부식, 변형 및 신축기능 이상 여부", "⦁교대·교각 균열, 기초 세굴·침하 여부", "⦁신축이음 유간 이상 및 이물질 퇴적 여부", "⦁배수시설 막힘 여부 및 정비",
  하천교량이면 "⦁하상 세굴 및 기초 노출 여부", 케이블이 있으면 "⦁케이블·정착구 부식 및 손상 여부").
{items_rule}- 점검결과 등급(제2종시설물)은 양호·보통·미흡·불량 중 하나와 근거(중대결함 없고 국부 손상뿐이면 보통 양호, 주요부재(거더·바닥판·받침·교각·기초)에 진행성 결함이면 보통~미흡, 위험하면 불량).{grade_rule}

아래 JSON 객체 하나로만 답하세요(설명 없이):
{{"critical": "결과표 중대한 결함 칸 — 시행령 제18조제1항의 중대한 결함이 있을 때만 그 내용 한 줄, 없으면 \\"없음\\"만",
 "public": "결과표 공중이 이용하는 부위에 결함 칸 — 난간·보도·점검로·교면포장에 결함이 있을 때만 위치·결함 한 줄, 없으면 \\"없음\\"만",
 "findings": ["⦁상부구조 : …", "⦁하부구조 : …", "⦁받  침 : …", "⦁케이블 : …", "⦁2차부재 : …", "⦁기타부재 : …"],
 "repairs": ["결과표 주요 보수·보강 줄 1~3개(예: ⦁신축이음 이물질 제거)"],
 "next_focus": "참고사항 — 차기 점검 시 중점 확인 부위 한 줄(예: 거더 균열 및 받침부 추가 손상 발생 여부 점검)",
 "sections": {{"super": "1.4.1 상부구조(바닥판, 거더) 조사결과 글", "sub": "1.4.2 하부구조(교대·교각·주탑·기초) 글", "bearing": "1.4.3 받침 글", "cable": "1.4.4 케이블 글",
              "second": "1.4.5 2차부재(가로보·세로보) 글", "etc": "1.4.6 기타부재(신축이음·배수시설·난간 및 연석·교면포장) 글", "public": "1.4.7 공중이 이용하는 부위 글"}},
 "summary_rows": [{{"name": "상부구조", "prev": "⦁전회 결과(줄마다 ⦁)", "now": "⦁금회 결과", "action": "⦁조치필요사항"}}, {{"name": "하부구조", ...}}, {{"name": "받침", ...}}, {{"name": "케이블", ...}},
                  {{"name": "2차부재", ...}}, {{"name": "기타부재", ...}}, {{"name": "공중이 이용하는시설", ...}}],
 "summary_opinion": "실시결과 요약표 종합의견 한두 문장(⦁로 시작)",
 "maint_plan": ["⦁중점 유지관리방안 글머리 6~10줄"],
 "conclusion": {{"survey": ["종합결론 외관조사결과 글머리 1~3개(⦁)"], "repair": ["보수필요사항 글머리 1~3개(⦁)"], "urgent": "긴급점검 및 정밀안전진단 필요여부(예: ⦁필요치 않음)"}},
 "grade": "양호", "grade_reason": "근거"{items_spec}{methods_spec}}}"""

ITEMS_RULE = ("- 3종시설물: 안전등급은 아래 15항목 평가 점수로 프로그램이 계산(우수10·양호8·보통5·미흡2·불량0, 주요60·일반20·부대20, 9·7·5·3점 이상 A~D, "
              "5·6번이 미흡·불량이면 더 나쁜 쪽) — \"grade\"도 그 계산과 맞게(A는 양호로 적음).\n")
ITEMS_SPEC = """,
 "items": [{{"no": 항목번호, "rating": "우수|양호|보통|미흡|불량|해당없음", "repair": "○ 또는 ×", "opinion": "점검자 의견 15자 안팎(예: 일부 균열 발생)", "basis": "근거 결함 — 부위·번호·크기와 맞춘 기준(걸린 결함이 없으면 빈 글)"}} — 아래 15항목 전부],
 "eval_opinion": "안전등급 평가 종합의견 및 특기사항 한두 문장"

15항목 평가는 반드시 제3종시설물 정기안전점검 매뉴얼(2026) 교량·육교 평가방법대로 — 아래 원칙과 항목마다 적힌 a~e 기준으로(a=우수, b=양호, c=보통, d=미흡, e=불량).

{items}"""

MAINT_COMMON = ["⦁거더·바닥판 균열, 박리·박락, 철근노출 진행여부", "⦁교량받침 부식, 변형 및 신축기능 이상 여부", "⦁교대·교각 균열 및 기초 세굴·침하 여부",
                "⦁신축이음 유간 이상 및 토사·이물질 퇴적 여부", "⦁배수구·배수관 막힘 여부 및 배수시설 정비", "⦁교면포장 균열 및 파손 여부", "⦁난간·연석 파손, 부식 및 고정상태"]


def _names(by_unit: dict, u: str) -> str:
    return ", ".join(dict.fromkeys(f"{(d.get('member') or '').strip()} {d.get('dtype')}".strip() for d in by_unit.get(u, []))) or ""


def maint_plan(defects: list, form: str = "") -> list[str]:
    """1.6 유지관리방안 기본 글머리(AI 없을 때) — 공통 + 이번 결함으로 더하는 줄."""
    out = list(MAINT_COMMON)
    k = " ".join(f"{d.get('member') or ''} {d.get('dtype') or ''}" for d in defects)
    if any(w in k for w in ("케이블", "정착구", "행어", "새들")):
        out.insert(3, "⦁케이블·정착구 부식 및 손상 여부")
    if "세굴" in k or "하천" in k:
        out.append("⦁하상 세굴 및 기초 노출 여부")
    if "잡목" in k or "식생" in k:
        out.append("⦁교대 주변 잡목 및 식생 제거 여부")
    return out


def fallback(defects: list, prev_grade: str = "", public: str = "", eval_items: list | None = None, form: str = "") -> dict:
    """AI 없이 — 결함 목록으로 만든 고정 틀(점검자가 고침). eval_items(3종)면 15항목도 어림."""
    out = _fallback(defects, prev_grade, public)
    return _with_items(out, None, eval_items, form, defects) if eval_items else out


def _fallback(defects: list, prev_grade: str = "", public: str = "") -> dict:
    by_unit: dict[str, list] = {}
    for d in defects:
        if d.get("check") == "repaired" or kinds.is_record(d.get("dtype") or ""):
            continue
        by_unit.setdefault(d.get("floor") or "기타부재", []).append(d)
    sev = any(any(w in (d.get("dtype") or "") for w in ("세굴", "침하", "변형")) for d in defects)
    nm = {u: _names(by_unit, u) for u in kinds.BRIDGE_PARTS}
    for u, lst in by_unit.items():  # 사람이 더한 탭은 기타부재로
        if u not in nm:
            nm["기타부재"] = ", ".join(x for x in (nm.get("기타부재"), _names(by_unit, u)) if x)
    has_cable = bool(nm.get("케이블"))
    ok = lambda u: "특이 손상이 없는 양호한 상태임"  # noqa: E731
    line = lambda u: (nm[u] + " 등이 국부적으로 조사되었으나 구조적 문제는 없는 상태임" if nm.get(u) else ("해당 부재 없음" if u == "케이블" and not has_cable else ok(u)))  # noqa: E731
    findings = [f"⦁{label} : {line(u)}" for u, label in FINDINGS]
    acts = {"퇴적": "신축이음·배수구 이물질 제거", "막힘": "배수시설 정비", "부식": "강재 부식부 재도장", "박락": "단면보수", "박리": "단면보수",
            "철근노출": "단면보수", "누수": "누수부 방수·주입보수", "백태": "누수부 방수·주입보수"}
    repairs = list(dict.fromkeys(a for lst in by_unit.values() for d in lst for k, a in acts.items() if k in (d.get("dtype") or "")))
    repairs = [_bul(x) for x in repairs] or ["⦁주의관찰"]
    rowtxt = lambda u: _bul(nm.get(u) or ("해당 부재 없음" if u == "케이블" and not has_cable else "상태양호"))  # noqa: E731
    pub_txt = f"{public} 상태양호" if public else "해당 시설 양호"
    rows = [{"name": u, "prev": "⦁-", "now": rowtxt(u), "action": "⦁주의관찰" if nm.get(u) else "⦁-"} for u in kinds.BRIDGE_PARTS]
    rows.append({"name": "공중이 이용하는시설", "prev": "⦁-", "now": _bul(pub_txt), "action": "⦁주의관찰"})
    any_ = [nm[u] for u in kinds.BRIDGE_PARTS if nm.get(u)]
    grade = prev_grade if prev_grade in GRADES2 else ("보통" if sev else "양호")
    sec = {}
    for key, label in SECTIONS:
        if key == "public":
            sec[key] = f"공중이 이용하는 부위({public or '난간·보도·점검로 등'}) 조사결과 전반적으로 양호한 상태로 유지되고 있다."
            continue
        unit = next(u for u, k in UNIT_TO_SECTION.items() if k == key)
        part = label.split(" ", 1)[1]
        if key == "cable" and not has_cable:
            sec[key] = "본 교량은 케이블 부재가 없는 형식으로 해당 부재가 없다."
        elif nm.get(unit):
            sec[key] = f"{part} 외관조사 결과 {nm[unit]} 등이 국부적으로 조사되었으며, 구조적인 안전성에 영향을 미치는 손상은 없는 것으로 조사되었다. 손상의 진행 여부를 지속적으로 관찰하고 추후 일괄보수를 실시하는 것이 바람직할 것으로 판단된다."
        else:
            sec[key] = f"{part} 외관조사 결과 특이 손상은 조사되지 않았으며 전반적으로 양호한 상태로 조사되었다."
    return {"critical": "없음", "maint_plan": maint_plan(defects), "public": "없음", "findings": findings, "repairs": repairs,
            "next_focus": "균열 및 손상부의 추가 손상 발생 여부 점검", "sections": sec, "summary_rows": rows,
            "summary_opinion": "⦁점검결과 " + (", ".join(any_) + " 등이 조사되었으며, 손상의 진행성은 없는 것으로 조사되었다." if any_ else "특이 손상 없이 양호한 상태로 조사되었다."),
            "conclusion": {"survey": ["⦁점검결과 " + (", ".join(any_) + " 등의 손상이 조사되었으며, 손상의 진행성은 없는 것으로 조사되었다." if any_ else "특이 손상은 조사되지 않았다.")],
                           "repair": repairs if repairs != ["⦁주의관찰"] else ["⦁손상이 경미하므로 주의관찰"], "urgent": "⦁필요치 않음"},
            "grade": grade, "grade_reason": "중대한 결함 없이 국부적인 손상만 조사됨" if not sev else "진행성 결함이 있어 지속 관찰 필요"}


def _norm(raw: dict, defects: list, eval_items: list | None = None, form: str = "") -> dict:
    """AI 답 → 보고서가 쓰는 꼴(빈 칸은 fallback 값). eval_items(3종)면 15항목·등급(점수)도."""
    fb = _fallback(defects)
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


def _with_items(out: dict, raw: dict | None, eval_items: list, form: str, defects: list) -> dict:
    """15항목: 이름·영역은 매뉴얼 것, 평가·의견·보수필요·근거는 AI 답(없으면 결함으로 어림) → 등급은 점수로(bridge_manual.score)."""
    from server.sitok import bridge_manual

    ok = {"우수", "양호", "보통", "미흡", "불량", "해당없음"}
    got = {}
    for x in (raw or {}).get("items") or []:
        try:
            got[int(x.get("no"))] = x
        except (TypeError, ValueError):
            continue
    base = bridge_manual.default_ratings(eval_items, defects, form)
    items = []
    for it, dft in zip(eval_items, base):
        g = got.get(it["no"], {})
        rating = g.get("rating") if g.get("rating") in ok else dft["rating"]
        items.append({**it, "rating": rating, "repair": "○" if str(g.get("repair") or dft.get("repair")).strip() == "○" else "×",
                      "opinion": str(g.get("opinion") or dft.get("opinion") or "").strip()[:60], "basis": str(g.get("basis") or "").strip()[:120]})
    out["items"] = items
    out["eval_opinion"] = str((raw or {}).get("eval_opinion") or "").strip() or ("점검결과 " + ("중대한 결함 없이 국부적인 손상만 조사되어 " if out.get("grade") in ("양호", "우수") else "") + "안전등급 평가 결과와 같이 판정함")
    res = bridge_manual.score(items, form)
    if res.get("grade"):
        out["grade"] = res["grade"]
        out["grade_reason"] = (out.get("grade_reason") or "") + f" (15항목 점수 {res['total']}점: " + ", ".join(f"{g} {a}/{b}={v:g}" for g, (a, b, v) in res["groups"].items()) + f" → {res['grade']}등급" + (f", {res['forced']}" if res.get("forced") else "") + ")"
    return out


def draft(facility: str, period: str, defects: list, prev_captions: list[str], facts: str, company_id: int, target_grade: str = "", prev_grade: str = "",
          public: str = "", eval_items: list | None = None, form: str = "", prev_rows: dict | None = None, combos: list | None = None,
          price_list: list | None = None) -> dict:
    """wall_ai.draft와 같은 인자 — eval_items = 3종 15항목(bridge_manual.items_for)이면 항목 평가도 AI가(등급은 점수로), 2종이면 None."""
    from server.sitok import ai_draft, bridge_manual, vision

    rule = f"\n- 점검자가 요청한 등급: {target_grade} — 그 등급에 맞는 근거·문장으로." if target_grade else ""
    if eval_items:
        rule += "·15항목 평가(평가 점수 합이 이 등급이 나오게)" if target_grade else ""
    prompt = PROMPT.format(facility=facility, period=period, defects="\n".join(_line(d) for d in defects) or "(결함 없음)",
                           prev="\n".join(prev_captions) or "(없음)", facts=facts or "", grade_rule=rule,
                           prev_rows="\n".join(f"{k}: {v}" for k, v in (prev_rows or {}).items() if v) or "(전회차 없음 — 첫 회차)",
                           items_rule=ITEMS_RULE if eval_items else "", items_spec=ITEMS_SPEC.format(items=bridge_manual.criteria(eval_items, form)) if eval_items else "",
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
    out["wall"] = True  # 옹벽식 토목 정기 초안 표시(화면·저장이 같은 길) — 교량은 sections에 "super"
    out["bridge"] = True
    out["ai_ok"] = bool(raw)
    if combos:
        out["methods"] = methods_rows(raw, combos, price_list)
    return out


def section_list() -> list[list[str]]:
    return [list(x) for x in SECTIONS]


def letter3(grade: str, items: list | None = None, form: str = "") -> str:
    """3종 결과표 "등급" 칸 글자(A~E) — 15항목이 있으면 점수로, 없으면 글자 그대로나 말 → 글자."""
    if items:
        from server.sitok import bridge_manual

        got = bridge_manual.score(items, form).get("grade")
        if got:
            return got
    v = (grade or "").strip().upper()
    return v if v in ("A", "B", "C", "D", "E") else letter(grade)


def is_wall_ai(final: dict | None) -> bool:
    """교량 초안인지(옹벽판 is_wall_ai와 같은 자리) — sections에 상부구조 절."""
    return bool(final) and bool(final.get("wall")) and isinstance(final.get("sections"), dict) and "super" in final["sections"]


def _selfcheck() -> None:
    from server.sitok import bridge_manual

    ds = [{"floor": "상부구조", "member": "거더", "dtype": "균열", "width": "0.2", "check": "new"},
          {"floor": "기타부재", "member": "신축이음", "dtype": "토사·이물질퇴적", "check": "same"}]
    out = fallback(ds, "", "", bridge_manual.items_for())
    assert len(out["findings"]) == 6 and out["findings"][3].startswith("⦁케이블 : 해당 부재 없음")
    assert [r["name"] for r in out["summary_rows"]] == SUMMARY_ROWS and set(out["sections"]) == {k for k, _ in SECTIONS}
    assert len(out["items"]) == 15 and out["grade"] in "ABCDE" and is_wall_ai({**out, "wall": True})
    n = _norm({"findings": ["상부구조 : 균열"], "sections": {"super": "글"}, "grade": "보통"}, ds, None)
    assert n["findings"] == ["⦁상부구조 : 균열"] and n["sections"]["super"] == "글" and n["sections"]["sub"] and n["grade"] == "보통"
    print("교량 AI 초안 틀 검사 통과")


if __name__ == "__main__":
    _selfcheck()
