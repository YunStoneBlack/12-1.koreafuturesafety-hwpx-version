"""시특법 회차 칸 [✓ 조사 완료]·[✓ 작성 완료](2026-10-18 민재형 — "조사완료 버튼", "나머지도 마찬가지", "완료버튼 생성해서 미기재항목 말해주고 조사완료 누르면 체크").

회차 화면 칸(현장 조사·재료시험·상태평가·면담·변경사항·시설물 현황·AI 초안) ✓는 이 버튼으로만 — 전엔 결함 줄·저장한 값이 하나라도 있으면 ✓라
전회차 결함을 가져오기만 해도 끝난 것처럼 보였음(양주덕산초 교사동(본관) 125개 가져옴·확인 0).
누를 때마다 빠진(미기재) 항목을 예외 없이 보여 줌(형 "해당이 있는데 안 한 건지 없어서 안 한 건지는 경고를 듣고 점검자가 판단") — 화면이 [이어서 하기]·[완료]를
몇 번이든 묻고, 경고가 남아 있어도 [완료]면 완료. 완료 = survey["steps"][칸] {at, by}(server/sitok/steps.py, 동마다).
현장 조사만: 묶음의 동이 다 완료되면 제출 현황 [현장점검](submit.field)에 날짜 → 방문 달력 그 반기 칸을 채움(sitok_status.visit_done — 형 "달력에서 빼면 이력 파악이 안 됨").

- `GET  /sitok/reports/{id}/steps/{step}` — {step, done, unit: {total, done}, field}(완료 표시만)
- `GET  /sitok/reports/{id}/steps/{step}/check` — 위 + missing: [{title, text, target}](target = 현장 조사 탭 또는 화면 칸 id)
- `POST /sitok/reports/{id}/steps/{step}/done` {done: bool} — 완료 / 완료 취소
"""
from __future__ import annotations

import datetime
import re
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokDefect, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok_defects import floor_key
from server.api.routers.sitok_parts import _out as parts_out
from server.api.routers.sitok_reports import _book_lead, _detail_out, _prior, _register, _report_dir, _require
from server.api.routers.sitok_status import _unit_reports, visits_after_mark
from server.sitok import master, parts as P, precision as PR, report_build as rb, steps

router = APIRouter(prefix="/sitok", tags=["sitok"])
TAB = {"defects": "🔍 결함 조사", "overview": "🏢 전경사진", "public": "🚶 공중이용", "other": "🧱 기타시설", "docs": "📋 자료수집", "load": "⚖ 하중상태", "survey": "📷 조사 전경"}


def _names(xs: list[str], n: int = 4) -> str:
    return " · ".join(xs[:n]) + (f" 외 {len(xs) - n}개" if len(xs) > n else "")


class _Miss(list):
    def add(self, title: str, text: str, target: str = "") -> None:
        self.append({"title": title, "text": text, "target": target})


# ---------- 칸마다 빠진 항목 ----------

def _field(db: Session, r: SitokReport) -> _Miss:
    """현장 조사 — 결함 확인·이번 사진, 전경, 공중이용, 기타시설(정밀은 자료수집·내진·하중·조사 전경·등급까지)."""
    out = _Miss()
    add = lambda tab, text: out.add(TAB[tab], text, tab)  # noqa: E731
    rows = db.query(SitokDefect.floor, SitokDefect.check, SitokDefect.photo, SitokDefect.prev_photo).filter(SitokDefect.report_id == r.id).all()
    by_floor = lambda c: " · ".join(f"{fl} {n}" for fl, n in sorted(c.items(), key=lambda x: floor_key(x[0])))  # noqa: E731
    ok = lambda ph: bool(ph and Path(ph).exists())  # noqa: E731
    if not rows:
        add("defects", "결함이 하나도 없습니다 — 전회차 결함을 가져오지 않았거나 신규 결함을 넣지 않았습니다")
    else:
        left = Counter(fl for fl, c, _, _ in rows if not c)
        if left:
            add("defects", f"현장 확인 안 한 결함 {sum(left.values())}개 — {by_floor(left)}")
        # 형 요청1 "이전 회차가 있을 경우 금회차 사진이 안 찍힌 곳" — 전회차 사진이 있는데 이번 사진이 없는 결함을 층별로
        noshot = Counter(fl for fl, _, ph, pph in rows if ok(pph) and not ok(ph))
        if noshot:
            add("defects", f"전회차 사진은 있는데 이번 사진을 안 찍은 결함 {sum(noshot.values())}개 — {by_floor(noshot)}")
        other = sum(1 for _, _, ph, pph in rows if not ok(pph) and not ok(ph))
        if other:
            add("defects", f"이번 사진이 없는 결함(전회차 사진도 없음) {other}개")
    if not r.overview:
        add("overview", "전경사진 0장 — 안 찍으면 지난 회차 사진이 그대로 들어갑니다")
    po = parts_out(db, r)
    pub = [p["name"] for p in po["public"] if not p["has"] and not p["none"]]
    if pub:
        add("public", f"사진도 [해당없음]도 아닌 항목 — {' · '.join(pub)}")
    if any(not all(o["slots"]) for o in po["other"]):
        add("other", " · ".join(f"{o['name']} {sum(o['slots'])}/{len(o['slots'])}장" for o in po["other"]) + " — 빈 칸은 보고서에 \"-\"")
    if (r.kind or "정기") == "정밀":
        p = PR.norm((r.survey or {}).get("precision"))
        base = _report_dir(db.get(SitokFacility, r.facility_id), r)
        has = lambda f: bool(f and (base / f).exists())  # noqa: E731
        docs = [n for _, k, n in PR.DOC_ITEMS if not (p["docs"].get(k) or {}).get("status")]
        if docs:
            add("docs", f"보관 여부를 안 고른 자료 {len(docs)}개 — {_names(docs, 3)}")
        if not p["seismic"]["status"]:
            add("docs", "내진설계 적용 여부를 안 골랐습니다")
        n = sum(1 for ph in p["load"]["photos"] if has(ph["file"]))
        if n < PR.LOAD_SLOTS:
            add("load", f"사용하중 현황사진 {n}/{PR.LOAD_SLOTS}장")
        groups = [(f"{cap} {title}", sum(1 for f in p["survey"][k] if has(f)), len(titles)) for k, cap, title, titles in PR.SURVEY_PICS]
        empty = [f"{name} {n}/{total}" for name, n, total in groups if n < total]
        if empty:
            add("survey", f"조사 전경 사진 {sum(n for _, n, _ in groups)}/{sum(t for _, _, t in groups)}장 — {' · '.join(empty)}")
        grades = P.norm(r.parts).get("grades") or {}
        g_pub = [x["name"] for x in po["public"] if not x["none"] and not grades.get(x["key"])]
        if g_pub:
            add("public", f"상태평가 등급을 안 고른 항목 — {' · '.join(g_pub)}")
        g_oth = [n for k, n in P.OTHER if not grades.get(k)]
        if g_oth:
            add("other", f"등급을 안 고른 항목 — {' · '.join(g_oth)}")
    return out


def _tests(db: Session, r: SitokReport) -> _Miss:
    """재료시험 — 표본층 수(기준), 표마다 값이 다 찬 줄 수 / 기준 수량, 빈 칸 있는 줄, 탄산화 사진."""
    from server.api.routers.sitok_tests import _view

    out = _Miss()
    v = _view(db, r)
    inp, q = v["input"], v["sample"]["quantity"]
    need, n = v["sample"]["need"], v["sample"]["count"]
    if not n:
        out.add("1. 표본층", "표본층을 안 골랐습니다" + (f" — 기준 {need}개" if need else ""), "st-sample")
    elif need and n < need:
        out.add("1. 표본층", f"표본층 {n}개 — 기준 {need}개", "st-sample")

    def table(title, target, key, rows, full):
        filled = sum(1 for x in rows if full(x))
        empty = len(rows) - filled
        if empty or filled < q[key]["need"]:
            out.add(title, f"값이 다 찬 줄 {filled}개 / 기준 {q[key]['need']}개" + (f" · 빈 칸이 있는 줄 {empty}개" if empty else ""), target)

    table("2. 부재 규격", "st-section", "section", inp["sections"], lambda x: x["design"] and x["measured"] and x["position"])
    table("3. 콘크리트 강도", "st-strength", "strength", inp["strength"]["rows"], lambda x: x["est"] is not None and x["position"])
    table("4. 탄산화", "st-carb", "carbonation", inp["carbonation"]["rows"], lambda x: x["cover"] is not None and x["depth"] is not None and x["position"])
    nophoto = sum(1 for x in inp["carbonation"]["rows"] if not x["photo"])
    if nophoto:
        out.add("4. 탄산화", f"사진이 없는 줄 {nophoto}개 — 부록 탄산화 사진현황에 빈 칸", "st-carb")
    table("5. 기울기", "st-tilt", "tilt", inp["tilt"]["rows"], lambda x: x["height"] is not None and x["disp"] is not None and x["label"])
    if not inp["settlement"]["floor"]:
        out.add("6. 부등침하", "측정한 층을 안 골랐습니다", "st-sett")
    table("6. 부등침하", "st-sett", "settlement", inp["settlement"]["sections"], lambda s: all(x is not None for x in s["levels"]))
    return out


def _rating(db: Session, r: SitokReport) -> _Miss:
    """상태평가 — 저장 여부(전회차 개수 그대로인지), 표본층별 부재 개수, 표본층에 안 들어간 결함, 전회차 등급, 결과 등급."""
    from server.api.routers.sitok_rating import _compute

    out = _Miss()
    v = _compute(db, r)
    if not (r.rating or {}).get("counts"):
        out.add("1. 부재 전체 개수", "아직 저장하지 않았습니다" + (" — 지금 칸은 전회차 개수 그대로" if v["carried"] else ""), "sr-counts")
    zero_floors, zero_cells = [], 0
    for fl in v["sample_floors"]:
        row = v["counts"].get(str(fl["floor"])) or {}
        if not any(row.values()):
            zero_floors.append(fl["label"])
        else:
            zero_cells += sum(1 for m in v["members"] if not row.get(m))
    if not v["sample_floors"]:
        out.add("1. 부재 전체 개수", "표본층이 없습니다 — 재료시험에서 표본층을 먼저 고르세요", "sr-counts")
    if zero_floors:
        out.add("1. 부재 전체 개수", f"부재 개수를 하나도 안 넣은 표본층 — {' · '.join(zero_floors)}", "sr-counts")
    if zero_cells:
        out.add("1. 부재 전체 개수", f"개수가 0인 부재 칸 {zero_cells}개 — 그 부재가 없으면 그대로", "sr-counts")
    if v["unassigned"]:
        out.add("3. 근거", f"표본층에 안 들어간 결함 {len(v['unassigned'])}개 — 결함 층이 표본층 범위 밖", "sr-detail")
    if not v["prev_grade"] and not v["prev_auto"]:
        out.add("2. 평가결과", "전회차 등급이 비었습니다", "sr-result")
    if not ((v["result"] or {}).get("total") or {}).get("grade"):
        out.add("2. 평가결과", "상태평가 등급이 나오지 않았습니다", "sr-result")
    return out


def _survey(db: Session, r: SitokReport) -> _Miss:
    """면담·변경사항 — 저장 여부, 1.2.7 이번 보수 줄·빈 칸, 1.2.8 체크·변경전·위치 빈 칸, 건축물대장."""
    out = _Miss()
    sv = r.survey or {}
    if "repairs" not in sv and "changes" not in sv:
        out.add("면담·변경사항 조사", "아직 저장하지 않았습니다")
    _prev_miss(db, r, out, "전회차 보고서 PDF", "1.2.7 [🤖 지난 이력 읽기] 또는 1.2.8 [🤖 전회차 보고서로 초안]")
    reps = sv.get("repairs") or []
    if not reps:
        out.add("1.2.7 보수·보강 이력", "이번 회차 보수 줄이 없습니다 — 관리주체 면담에서 보수한 게 없으면 그대로")
    holes = sum(1 for x in reps if not all((x.get(k) or "").strip() for k in ("period", "kind", "method", "where")))
    if holes:
        out.add("1.2.7 보수·보강 이력", f"보수기간·공사종류·보수방안·위치 중 빈 칸이 있는 줄 {holes}개")
    m = master.master_path()
    items = rb.read_survey(m)["change_items"] if m.exists() else []
    ch = sv.get("changes") or {}
    if items and not ch:
        out.add("1.2.8 변경사항", "체크한 항목이 없습니다 — 보고서에 전부 \"변경사항없음\"")
    part = [k for k, c in ch.items() if not (c.get("before") or "").strip() or not (c.get("where") or "").strip()]
    if part:
        out.add("1.2.8 변경사항", f"변경전·위치가 빈 항목 — {_names(part)}")
    if items and not _register(db.get(SitokFacility, r.facility_id)).exists():
        out.add("1.2.8 변경사항", "건축물대장이 없어 변동사항과 대조하지 못했습니다(시설물 정보·서류에서 올림)")
    return out


def _prev_miss(db: Session, r: SitokReport, out: _Miss, title: str, button: str) -> None:
    """전회차 보고서 PDF(10/18) — 전회차 한글(직전 회차·예전에 올린 것)이 없는 회차만: 안 올렸거나 올렸는데 안 읽음."""
    from server.api.routers.sitok_prev import prev_file

    if _prior(r) is not None:
        return
    if not prev_file(db, r).exists():
        out.add(title, "전회차 보고서 PDF가 없습니다 — 처음 점검이면 그대로, 전회차가 있으면(우리 회사·타사) 그 동 쪽 PDF를 올리세요")
    elif not (r.survey or {}).get("prev"):
        out.add(title, f"올린 전회차 보고서 PDF를 아직 안 읽었습니다 — {button}")


def _same(a: str, b: str) -> bool:
    n = lambda s: re.sub(r"\.(?=\D|$)", "", re.sub(r"(\.\d*?)0+(?=\D|$)", r"\1", re.sub(r"[\s,㎡ㆍ·]", "", str(s or ""))))  # noqa: E731 — 창(sitok-detail.js same)과 같게
    return n(a) == n(b)


def _detail(db: Session, r: SitokReport) -> _Miss:
    """시설물 현황 — 저장 여부, 빈 칸("-"), 전회차 보고서와 다른 칸, 보관·관리 실태 안 고름, 용도현황."""
    from server.api.routers.sitok import _facility_dir
    from server.sitok import drawings as D

    out = _Miss()
    d = _detail_out(db, r)
    f = db.get(SitokFacility, r.facility_id)
    if not d["saved"]:
        out.add("시설물 현황", "아직 저장하지 않았습니다 — 지금 칸은 관리대장·전회차 보고서 값")
    _prev_miss(db, r, out, "첨부 — 전회차 보고서 PDF", "[🤖 채우기]")
    # 형 요청1 "구조일반사항·건축개요 첨부 없을 때 하이픈으로 가는 거 맞는지" — 어느 첨부가 없어서 어느 칸이 "-"인지
    dash = lambda words: [x["label"] for x in d["fields"] if (x["value"] or "-").strip() in ("", "-") and any(w in x["label"] for w in words)]  # noqa: E731
    if not D.items(f, "struct", _facility_dir(f)):
        hit = dash(("콘크리트", "철근", "철골", "기초", "지하깊이", "기둥", "지하수위", "슬래브", "방수"))
        out.add("첨부 — 구조일반사항·건축개요 도면", "도면이 없습니다" + (f" — 도면에서 읽는 칸이 \"-\"로 나감: {_names(hit, 6)}" if hit else "")
                + " (시설물 등록·정보에서 올림)")
    if not d["has_register"]:
        out.add("첨부 — 건축물대장 PDF", "건축물대장이 없습니다 — 층별 용도현황·면적과 1.2.8 변동사항을 못 읽음(시설물 등록·정보에서 올림)")
    if not d["has_ledger"]:
        hit = dash(("관리번호", "관리 책임자", "준공", "건축면적", "연면적", "층수", "주용도", "구조형식", "최고높이"))
        out.add("첨부 — 시설물관리대장", "관리대장이 없습니다" + (f" — 관리대장에서 읽는 칸이 \"-\": {_names(hit, 6)}" if hit else ""))
    blank = [f["label"] for f in d["fields"] if (f["value"] or "-").strip() in ("", "-")]
    if blank:
        out.add("1.1 현황표", f"빈 칸(\"-\") {len(blank)}개 — {_names(blank)}")
    diff = [f["label"] for f in d["fields"] if f["prior"] and f["prior"] != "-" and f["value"] and f["value"] != "-" and not _same(f["prior"], f["value"])]
    if diff:
        out.add("1.1 현황표", f"전회차 보고서와 다른 칸 {len(diff)}개 — {_names(diff)}")
    nochk = [c["label"].rstrip(" :") for c in d["checks"] if c["selected"] is None]
    if nochk:
        out.add("1.2.1~1.2.3 보관·관리 실태", f"안 고른 항목 — {_names(nochk)}")
    uses = d["uses"] or []
    if not uses:
        out.add("용도현황", "층 줄이 없습니다")
    holes = sum(1 for u in uses if not all(str(x or "").strip() for x in u[:3]))
    if holes:
        out.add("용도현황", f"층·바닥면적·주용도 중 빈 칸이 있는 줄 {holes}개")
    if not (d["uses_total"] or "").strip():
        out.add("용도현황", "연면적 합계가 비었습니다")
    return out


def _ai(db: Session, r: SitokReport) -> _Miss:
    """AI 초안 — 초안 있음·사람이 확인해 저장함, 비어 있는 글 칸(정기 결과표·1.3 서술·종합결론·등급·보수공법·요약문 결언 / 정밀 22항목)."""
    from server.sitok import precision_ai

    out = _Miss()
    ai = r.ai or {}
    final = ai.get("final") or {}
    if (r.kind or "정기") == "정밀":
        if not (ai.get("draft") or {}).get("made_at"):
            out.add("AI 초안", "AI가 아직 쓰지 않았습니다 — 지금은 결함·시험·상태평가 값으로 만든 기본 글")
        if not final.get("edited_at"):
            out.add("AI 초안", "글을 확인하고 [저장]한 적이 없습니다")
        empty = [lab for k, lab, _ in precision_ai.ITEMS if not str((final.get("precision") or {}).get(k) or "").strip()] if final.get("precision") else []
        if empty:
            out.add("22항목", f"빈 글 {len(empty)}개 — {_names(empty)}")
        return out
    if not final:
        out.add("AI 초안", "초안이 없습니다 — [AI 초안 만들기]")
        return out
    if not final.get("edited_at"):
        out.add("AI 초안", "AI가 쓴 글을 확인하고 [저장]한 적이 없습니다")
    labels = {"critical": "중대결함", "public": "공중이 이용하는 부위", "findings": "점검 주요결과", "repairs": "주요 보수·보강", "next_focus": "차기 중점 점검부위"}
    empty = [lab for k, lab in labels.items() if not final.get(k)]
    if empty:
        out.add("결과표", f"빈 칸 — {' · '.join(empty)}")
    if not final.get("items") and not final.get("grade"):
        out.add("결과표", "안전등급을 고르지 않았습니다(지난 보고서 그대로)")
    secs = {"crack": "1) 균열", "leak": "2) 누수·백화", "spall": "3) 박리·박락", "steel": "4) 강재", "nonstruct": "5) 비구조체", "public": "6) 공중이용", "other": "7) 기타시설"}
    es = [lab for k, lab in secs.items() if not str((final.get("sections") or {}).get(k) or "").strip()]
    if es:
        out.add("1.3 외관조사 서술", f"빈 항목 — {' · '.join(es)}")
    nometh = [f"{m.get('member', '')} {m.get('dtype', '')}".strip() for m in final.get("methods") or [] if not (m.get("method") or "").strip()]
    if nometh:
        out.add("보수공법", f"공법이 빈 줄 {len(nometh)}개 — {_names(nometh, 3)}")
    nograde = [x.get("name", "") for x in final.get("parts") or [] if not x.get("grade")]
    if nograde:
        out.add("공중이용·기타시설 판단", f"등급이 빈 항목 — {_names(nograde)}")
    if not final.get("conclusion"):
        out.add("종합결론", "종합결론이 비었습니다")
    lead = _book_lead(db, r)
    if not (((lead.ai or {}).get("summary") if lead is not None else None) or {}).get("conclusion"):
        out.add("요약문 결언", "비었습니다 — 비우면 기본 문장")
    return out


CHECKS = {"field": _field, "tests": _tests, "rating": _rating, "survey": _survey, "detail": _detail, "ai": _ai}


def _state(db: Session, r: SitokReport, step: str) -> dict:
    reps = _unit_reports(db, r)
    return {"step": step, "done": steps.get(r, step), "unit": {"total": len(reps), "done": sum(1 for x in reps if steps.get(x, step))},
            "field": (r.submit or {}).get("field") if step == "field" else None}


def _step(step: str) -> str:
    if step not in CHECKS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 칸입니다.")
    return step


@router.get("/reports/{report_id}/steps/{step}")
def state(report_id: int, step: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """완료 표시만(가벼움) — 화면·창이 처음 그릴 때."""
    return _state(db, _require(db, user, report_id), _step(step))


@router.get("/reports/{report_id}/steps/{step}/check")
def check(report_id: int, step: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    return {**_state(db, r, _step(step)), "missing": CHECKS[step](db, r)}


class DoneIn(BaseModel):
    done: bool = True


@router.post("/reports/{report_id}/steps/{step}/done")
def done(report_id: int, step: str, body: DoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require(db, user, report_id)
    _step(step)
    by = user.display_name or ""
    steps.put(r, step, {"at": datetime.date.today().isoformat(), "by": by} if body.done else None)
    db.commit()
    if step == "field":
        _field_unit(db, user, r, body.done, by)
    return _state(db, r, step)


def _field_unit(db: Session, user: User, r: SitokReport, done_: bool, by: str) -> None:
    """현장 조사 — 묶음의 동이 다 완료되면 제출 현황 [현장점검] + 달력 칸, 한 동이라도 다시 열면 [현장점검]도 풂(달력 칸은 그 자리에 빈 칸)."""
    reps = _unit_reports(db, r)
    marked = any((x.submit or {}).get("field") for x in reps)
    if done_:
        dones = [steps.get(x, "field") for x in reps]
        if all(dones) and not marked:
            day = max(d["at"] for d in dones)
            for x in reps:
                x.submit = {**(x.submit or {}), "field": {"at": day, "by": by}}
            db.commit()
            visits_after_mark(db, user, reps, True, "field", datetime.date.fromisoformat(day))
    elif marked:
        for x in reps:
            sub = dict(x.submit or {})
            sub.pop("field", None)
            x.submit = sub
        db.commit()
        visits_after_mark(db, user, reps, False, "field")
