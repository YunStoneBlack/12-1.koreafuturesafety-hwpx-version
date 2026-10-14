"""시특법 정밀안전점검 본문 글(2026-10-13 밤, ⑤ 단계) — 결함·재료시험·상태평가 값으로 다산은혜교회 보고서 문장 틀에 맞춘 기본 글.
AI 초안(ai["precision"])이 있으면 그 키가 덮어씀. 키: crack·leak·spall·steel·nonstruct·load·public·other(3.2.x 본문·3.1 분석 표·5.1.1 나·결과표),
section·strength·carb·carb_life·tilt·settle(4.x 나. 결과 분석·5.1.1·7.2.x), summary(결과표 책임기술자 종합의견), overall(5.2·7.4), conclusion(7.5),
prev_compare(전차 비교 검토 칸), limit·special·suggest·diag(사용제한 필요성 표).
"""
from __future__ import annotations

from server.sitok import condition


def _floors_text(floors: list[str]) -> str:
    fl = sorted(set(f for f in floors if f), key=lambda s: (condition.floor_key(s) is None, condition.floor_key(s) or 0))
    return "·".join(fl[:4]) + (f" 외 {len(fl) - 4}개 층" if len(fl) > 4 else "") if fl else "일부 층"


def _members_text(members: list[str]) -> str:
    ms = []
    for m in members:
        if m and m not in ms:
            ms.append(m)
    return "·".join(ms[:3]) + (" 등" if len(ms) > 3 else "") if ms else "일부 부재"


def _group(defects: list, pick) -> list:
    return [d for d in defects if pick(d)]


def defect_texts(defects: list, grades: dict | None = None, structure: str = "") -> dict:
    """결함현황표 줄(SitokDefect) → 3.2.1~3.2.8 문장. grades = 공중이용·기타시설 등급 {key: a~e}."""
    g = grades or {}
    out = {}
    cracks = _group(defects, lambda d: d.part == "구조체" and "균열" in (d.dtype or ""))
    if cracks:
        wide = [d for d in cracks if condition._num(d.width) and condition._num(d.width) >= 0.3]
        out["crack"] = (f"콘크리트 구조체에 대한 정밀육안조사 결과 {_floors_text([d.floor for d in cracks])}의 {_members_text([d.member for d in cracks])}에서 "
                        f"{_members_text([d.dtype for d in cracks])} {sum(int(condition._num(d.count) or 1) for d in cracks)}개소가 조사되었다. "
                        + ("일부 균열은 폭 0.3mm 이상으로 주입공법 등의 보수가 필요하며, 보수 후 지속적인 주의관찰을 권고한다."
                           if wide else "균열폭이 0.3mm 미만이고 면적률 20% 미만으로 구조안전성에 영향이 크다고 판단되지는 않는다. "
                           "지속적인 주의관찰 및 중장기적인 계획을 세워 표면처리 등의 보수공법을 활용하여 유지관리할 것을 권고한다."))
    else:
        out["crack"] = "콘크리트 구조체에 대한 정밀육안조사 결과 구조체 균열은 조사되지 않았으며 전반적으로 양호한 상태로 조사되었다."
    leaks = _group(defects, lambda d: any(w in (d.dtype or "") for w in ("누수", "백태", "백화")))
    out["leak"] = (f"시설물의 누수 및 백화에 대하여 조사한 결과 {_floors_text([d.floor for d in leaks])}의 {_members_text([d.member for d in leaks])} 부분에서 "
                   "누수흔적 등이 조사되었다. 당장 구조적으로 긴급한 보수가 필요하지는 않으나 장마철 누수의 진행 여부를 확인하여 보수의 유무를 판단할 필요가 있다."
                   if leaks else "시설물의 누수 및 백화에 대하여 조사한 결과 전반적으로 양호한 상태로 조사되었다.")
    spalls = _group(defects, lambda d: d.part == "구조체" and any(w in (d.dtype or "") for w in ("박리", "박락", "층분리", "철근")))
    out["spall"] = (f"구조체의 박리·박락, 철근노출 등을 조사한 결과 {_floors_text([d.floor for d in spalls])}의 {_members_text([d.member for d in spalls])}에서 "
                    f"{_members_text([d.dtype for d in spalls])}이 조사되었다. 구조안전성에는 영향이 없을 것으로 판단되나 지속적인 주의관찰 및 "
                    "중장기적인 계획을 세워 단면복구 등의 보수공법을 활용하여 유지관리할 것을 권고한다."
                    if spalls else "구조체의 박리·박락, 철근노출 등을 조사한 결과 전반적으로 양호한 상태를 유지하고 있었다.")
    steels = _group(defects, lambda d: (d.member or "") == "강재")
    is_steel = any(w in (structure or "") for w in ("철골", "강구조", "SRC"))
    out["steel"] = ("강재구조에 대한 조사 결과 " + (f"{_floors_text([d.floor for d in steels])}에서 {_members_text([d.dtype for d in steels])}이 조사되었다." if steels
                                             else "부식·도장 상태 등 전반적으로 양호한 상태로 조사되었다.")
                    if is_steel or steels else "본 시설물은 강재구조는 해당없는 것으로 확인되었다.")
    out["steel_na"] = not (is_steel or steels)
    non = _group(defects, lambda d: d.part == "비구조체")
    out["nonstruct"] = (f"본 시설물의 비구조체 칸막이벽, 마감재, 조적벽체 등을 정밀육안조사한 결과 전도위험 및 붕괴위험성이 있는 구간은 조사되지 않았으나 "
                        f"일부 {_members_text([d.dtype for d in non])} 등이 조사되었다. 구조안전성에는 영향이 없으나 사용성 및 미관상 장기적인 유지관리계획을 세워 유지보수할 것을 권고한다."
                        if non else "본 시설물의 비구조체 칸막이벽, 마감재, 조적벽체 등을 정밀육안조사한 결과 전도위험 및 붕괴위험성이 있는 구간은 조사되지 않았으며 전반적으로 양호한 상태로 조사되었다.")
    pub_bad = [k for k in ("fall", "road", "joint", "vent") if g.get(k) in ("c", "d", "e")]
    out["public"] = ("시설 내외부 추락방지시설(계단난간, 옥상난간 등), 도로포장, 신축이음부, 환기구 등의 덮개를 조사한 결과 "
                     + ("일부 항목에서 보수가 필요한 손상이 조사되어 보수 후 유지관리할 것을 권고한다." if pub_bad
                        else "전반적으로 양호한 상태로 유지되고 있는 것으로 조사되었다."))
    out["other"] = ("본 시설물의 기타시설 점검결과 마감재 및 부착물 등 " + ("일부 보수가 필요한 손상이 조사되었다." if any(g.get(k) in ("c", "d", "e") for k in ("finish", "attach"))
                                                            else "전반적으로 양호한 것으로 조사되었다."))
    return out


def test_texts(tv: dict) -> dict:
    """재료시험 보기(tests.compute) → 4.x 나. 결과 분석 문장."""
    out = {}
    secs = tv["sections"]
    ng = [s for s in secs if s.get("ok") is False]
    conc = [s for s in secs if s.get("member") != "강재"]
    lost = bool(conc) and not any(s.get("design") for s in conc)  # 설계도면 칸이 다 비면 설계도서 유실(숭의 견본 문장, 10/14)
    out["section"] = ("본 대상 구조물은 설계도서가 유실된 것으로 확인되어 기존 도면과의 비교·분석 검토는 불가능하였다. 이에 따라 현장 실측 조사를 통해 부재 규격을 조사하였으며, "
                      "정밀육안조사 결과 부재의 처짐 등 단면부족에 의한 내구성 저하 현상은 조사되지 않았다. 지속적인 주의관찰을 통한 유지관리를 권고한다." if lost
                      else "시설물의 현장 부재 규격 실측 조사결과 설계도서의 규격과 동일하게 시공된 것으로 조사되었다." if secs and not ng
                      else f"시설물의 현장 부재 규격 실측 조사결과 {len(ng)}개소에서 설계도서와 차이가 조사되었으나 상태평가 기준 "
                           f"{(tv['sections_grade'] or 'a').upper()}등급으로 구조안전성에 미치는 영향은 크지 않은 것으로 판단된다." if secs
                      else "부재 규격 조사 결과가 없다.")
    st = tv["strength"]
    sm = st["summary"]
    if sm["count"]:
        designs = sorted({r["design"] for r in st["rows"] if r.get("design")})
        dtext = f"{designs[0]:g}~{designs[-1]:g}MPa" if len(designs) > 1 else (f"{designs[0]:g}MPa" if designs else "설계기준강도")
        good = (st["grade"] or "a") == "a"
        out["strength"] = (f"슈미트해머를 이용한 압축강도 시험결과 추정 압축강도는 {sm['min']}~{sm['max']}MPa로 측정되었다. 이는 설계기준강도 {dtext}를 "
                           + ("상회하여 만족하는 값으로 상태평가 결과 A등급으로 조사되었다." if good else f"기준으로 상태평가 결과 {st['grade'].upper()}등급으로 조사되었다.")
                           + " 비파괴 측정방법은 콘크리트의 상태, 탄산화, 온도 등에 영향을 받으므로 시험의 정확성과 안전성 확보를 위하여 본 보고서에 수록된 측정 매뉴얼에 따라 실시하였다.")
    else:
        out["strength"] = "콘크리트 강도 조사 결과가 없다."
    c = tv["carbonation"]
    cs = c["summary"]
    if cs["count"]:
        lives = [r["life_text"] for r in c["rows"] if r.get("life_text")]
        over = all(x == "100년 이상" for x in lives) if lives else False
        grade_counts = {}
        for r in c["rows"]:
            if r.get("grade"):
                grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1
        gtext = ", ".join(f"{g.upper()}등급 {n}개소" for g, n in sorted(grade_counts.items()))
        out["carb"] = (f"표본층 구조부재 총 {cs['count']}개소에 대하여 탄산화 시험을 시행한 결과, 콘크리트 탄산화 깊이는 {cs['min']}mm~{cs['max']}mm로 측정되었다. "
                       f"{gtext}로 평가되었으며, 측정오차 및 마감면(미장·견출·페인트)의 두께를 고려하면 내구성 저하 여부는 대체적으로 양호한 상태로 판단된다.")
        out["carb_life"] = ("측정된 탄산화 깊이를 고려하여 잔존수명을 예측한 결과 " + ("평균 100년 이상으로 추정되며" if over else "일부 개소에서 100년 미만으로 추정되나")
                            + " 철근노출 및 콘크리트 박락된 부위가 발생되지 않아 부식 및 노후화 진행이 진전될 우려는 거의 없는 것으로 판단된다.")
    else:
        out["carb"], out["carb_life"] = "탄산화 시험 결과가 없다.", ""
    t = tv["tilt"]
    if t["range"]["min_n"]:
        out["tilt"] = (f"점검대상 건물의 기울기는 1/{t['range']['min_n']:,}~1/{t['range']['max_n']:,}으로 측정되어 {(t['grade'] or 'a').upper()}등급으로 평가되었다. "
                       "건물 기울기 측정값은 구조물의 구조적 손상이 예상되는 한계인 1/150 이내로 모두 만족하였고, "
                       + (t["note"] or "해당 시설물 지반상태 및 내외부 균열조사 결과 기울기의 구조적 손상이 아닌 시공상의 오차로 판단되어 전반적으로 양호한 상태를 유지하고 있는 것으로 판단된다."))
    else:
        out["tilt"] = "기울기 조사 결과가 없다."
    s = tv["settlement"]
    if s["range"]["max_disp"] is not None:
        out["settle"] = (f"부등침하 조사는 {s['floor_label'] or '최하층'} 바닥에서 조사하였으며 X, Y방향 조사결과 구간별로 {s['range']['min_disp']:g}㎜~{s['range']['max_disp']:g}㎜의 변위가 조사되었으나 "
                         "기둥, 보, 벽체 및 바닥 하부 슬래브에 과도한 변형·변위가 관찰되지 않아 부등침하로 인한 구조물의 피해는 없는 것으로 사료된다. "
                         + (s["note"] or "구간별 변위는 바닥마감 시공오차 및 구배 등으로 인한 차이가 반영된 것으로 판단된다.") + " 향후 지속적인 계측관리를 통하여 변위 진행여부를 확인하는 것이 필요하다.")
    else:
        out["settle"] = "부등침하 조사 결과가 없다."
    return out


def rating_texts(result: dict | None, prev_grade: str, name: str, year: int, completion_text: str, first: bool) -> dict:
    out = {}
    if result and result.get("total"):
        letter = result["total"]["grade"]
        word = {"A": "우수", "B": "양호", "C": "보통", "D": "미흡", "E": "불량"}.get(letter, "")
        out["overall"] = f"본 시설물의 외관조사, 재료시험 및 측정에 의한 상태평가 프로그램 결과와 책임기술자 소견을 종합하여 평가한 결과 안전등급은 “{letter}등급”으로 평가되었다."
        out["conclusion"] = (f"{name}에 대한 정밀안전점검 결과, 안전등급은 {letter}등급({word})으로 평가되었으며, 현재 긴급 정밀안전진단이나 사용제한 등의 조치는 "
                             "필요치 않은 것으로 판단된다." if letter in "ABC" else
                             f"{name}에 대한 정밀안전점검 결과, 안전등급은 {letter}등급({word})으로 평가되어 보수·보강 후 재평가 또는 정밀안전진단 등의 조치가 필요한 것으로 판단된다.")
        out["summary"] = (f"본 시설물에 대한 정밀안전점검 결과, 안전등급은 {letter}등급({word})으로 평가되었으며, 조사된 손상들의 경우 구조적인 문제점은 없는 상태이나 "
                          "추가손상방지 및 내구성 확보를 위해 보수 및 지속적인 주의관찰이 요구된다. "
                          "외관조사 결과 구조체의 균열·누수·박리 등은 대부분 경미한 수준이며, 비구조체(조적벽·마감재)의 미장균열·이격 등은 사용성 및 미관 측면에서 보수가 필요한 상태이다. "
                          "재료시험(부재 규격·콘크리트 강도·탄산화) 및 기울기·부등침하 조사 결과는 세부지침의 평가 기준을 만족하여 구조적 안전성에는 문제가 없는 것으로 판단된다. "
                          "시설물의 공용기간 및 등급을 감안하여 중·장기적인 보수계획을 수립하고, 손상부에 대한 적절한 보수조치 후 정기적인 점검을 통해 손상의 진행 여부를 "
                          "확인하는 등 지속적인 유지관리를 실시하는 것이 바람직하다.")  # 요약표 칸(8~10줄)에 맞게 종합결론 요약을 덧붙임(사용자 10/14)
        out["grade_letter"] = letter
        out["grade_score"] = result["total"]["score"]
        out["diag"] = "불필요" if letter in "ABC" else "필요"
    else:
        out["overall"] = out["conclusion"] = out["summary"] = "상태평가 결과가 없어 안전등급을 산정하지 못했다."
        out["grade_letter"], out["grade_score"], out["diag"] = "", None, "-"
    out["prev_compare"] = (f"{completion_text} 준공 건축물로 이번 회차가 첫 회차 정밀안전점검이며 전차 비교 대상이 없다." if first or not prev_grade
                           else f"전차 점검 안전등급 {prev_grade}등급에서 이번 회차 {out['grade_letter'] or '-'}등급으로 " + ("변동 없이 유지되고 있다." if prev_grade == out["grade_letter"] else "변동되었다."))
    out["limit"] = "중대결함은 없는 것으로 조사되었고, 사용제한 불필요." if out["grade_letter"] in ("A", "B", "C") else "사용제한 여부에 대한 책임기술자 검토가 필요하다."
    out["special"] = "조사된 결함은 유지관리계획에 따라 보수하고 지속적인 주의관찰이 필요하다."
    out["suggest"] = "향후 건물이 존속하는 기간동안 보수구간의 정기적인 점검을 실시하여 손상의 진행 여부를 확인하고, 유지관리계획에 따라 보수·보강할 것을 건의한다."
    return out


def findings(texts: dict) -> list[str]:
    """결과표 "점검 주요결과" 글머리 8줄(다산 순서: 균열·누수·박리박락·강재·비구조체·하중·기타시설·재료시험)."""
    return [texts.get(k, "") for k in ("crack", "leak", "spall", "steel", "nonstruct", "load", "other", "tests_summary") if texts.get(k)]


def all_texts(defects: list, tv: dict, result: dict | None, *, grades: dict, structure: str, load_note: str, prev_grade: str, name: str, year: int,
              completion_text: str, first: bool, ai: dict | None) -> dict:
    t = {}
    t.update(defect_texts(defects, grades, structure))
    t.update(test_texts(tv))
    steel_secs = [s for s in tv["sections"] if s.get("member") == "강재"]  # 재료시험 규격에 강재 줄(트러스 앵글 등)이 있으면 강재구조 있음(숭의 10/14)
    if t.get("steel_na") and steel_secs:
        t["steel"] = ("본 시설물은 일부 구간이 강재구조(트러스 등)로 되어 있으며, 강재 부재 규격 조사 결과 " + ("설계값과 일치하고 " if all(s.get("ok") is not False for s in steel_secs) else "일부 차이가 있으나 ")
                      + "부식·도장 상태 등 전반적으로 양호한 것으로 조사되었다.")
        t["steel_na"] = False
    t.update(rating_texts(result, prev_grade, name, year, completion_text, first))
    t["load"] = load_note or "본 시설물의 하중상태 등에 대한 조사결과 용도변경 이력은 없는 것으로 확인되었고, 현장에서도 추가하중에 대한 확인결과 준공도서와 동일한 것으로 조사되었다."
    gs = [g for g in (tv["sections_grade"], tv["strength"]["grade"], tv["carbonation"]["grade"], tv["tilt"]["grade"], tv["settlement"]["grade"]) if g]
    t["tests_summary"] = f"재료시험 조사 결과 {min(gs).upper()}~{max(gs).upper()}등급으로 " + ("양호한 상태로 조사되었다." if max(gs) <= "b" else "일부 항목에서 보수·관찰이 필요한 것으로 조사되었다.") if gs else ""
    for k, v in ((ai or {}).get("precision") or {}).items():  # AI 초안(점검자가 고친 것)이 덮어씀
        if isinstance(v, str) and v.strip():
            t[k] = v.strip()
    return t
