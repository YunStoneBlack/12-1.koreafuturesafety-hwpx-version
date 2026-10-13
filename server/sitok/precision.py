"""시특법 정밀안전점검 ④ — 정기에 없는 입력(2026-10-13 밤, 사용자 "추천대로"): 2장 자료수집(2.2 자료 목록·2.3.2 내진·2.3.4 사용·관리실태·전차 점검 보고서 검토),
3.2.6 하중상태 사진 4장, 3.2.7~8 공중이용·기타시설 등급. 항목·문구는 다산은혜교회 26년 상반기 보고서 그대로. 저장은 SitokReport.survey["precision"](마이그레이션 없음),
등급은 SitokReport.parts["grades"]. 화면 sitok-field.html [📋 자료수집]·[⚖ 하중상태] 탭 + 공중이용·기타시설 탭의 등급 칸(js/sitok-precision.js), 서버 sitok_precision.py.
"""
from __future__ import annotations

import io

# 2.2 자료수집 목록(표 2.1) — (구분, 키, 자료)
DOC_ITEMS = [
    ("시공관련자료", "build", "시공관련자료"), ("시공관련자료", "quality", "품질관리자료"), ("시공관련자료", "accident", "사고기록"), ("시공관련자료", "operate", "운영기록"),
    ("설계도서", "dwg_common", "공통 — 위치도(배치도)·평면도·단면도"), ("설계도서", "dwg_arch", "건축도면 — 배치도·평면도·입면도·단면도"),
    ("설계도서", "dwg_struct", "구조도면 — 평면·단면도·배근도·접합 상세도"), ("설계도서", "dwg_mech", "기계설비도면 — 승강기·냉난방·환기"),
    ("설계도서", "dwg_elec", "전기설비도면 — 조명·통신·방송·변전"), ("설계도서", "dwg_fire", "소방설비도면 — 방화구획·소화전·스프링클러"),
    ("설계도서", "dwg_water", "급배수설비도면 — 계통도·수조·정화조"),
    ("유지관련자료", "ledger", "시설물관리대장"), ("유지관련자료", "past", "기존 점검 자료"), ("유지관련자료", "repair", "보수·보강 및 용도변경 자료"),
]
DOC_STATUS = ("보유", "미보유", "해당없음")
SEISMIC = ("적용", "미적용", "불명")
YNU = ("무", "유", "불명")
# 2.3.4 4) 부대 점검사항(유지관리자 면담) — 건축분야 25항목, 값 "없다(양호)" / "있다(불량)"
CHECKLIST = [
    "바닥 포장부위 침하 및 균열현상", "건물 전체의 부동침하 현상", "외부 옹벽(축대)의 균열현상", "하수관로 및 맨홀의 배수·청소 상태", "외벽의 전도위험 부위",
    "옥외 간판의 고정 상태", "외벽 타일의 탈락 부위", "외벽 모르터 또는 콘크리트의 탈락 부위", "외벽 창문 유리의 파손", "옥상 ROOF DRAIN의 상태",
    "옥상에 하중(물건)의 과적 여부", "옥상과 파라펫의 균열", "외벽 벽돌 줄눈의 경사방향 균열", "외벽의 백화 현상", "내부 창·문의 작동 상태",
    "건물 내부의 진동 여부", "천정재(텍스류)의 탈락 및 갈라짐 상태", "벽지 및 천정지가 찢어진 곳 유무", "실내의 하중(물건)의 과적 여부", "건물에서 뚝뚝하는 소리",
    "누수되는 곳의 유무", "녹물이 흘러나오는 곳의 유무", "코킹이 갑자기 떨어진 곳의 유무", "외부 석재에 균열 또는 변형 유무", "슬래브·보·기둥·벽체의 들뜬 현상",
]
LOAD_SLOTS = 4  # 3.2.6 사용하중 현황사진 4장(다산: 옥상·식당·믿음실·지하주차장)
LOAD_DEFAULT_NOTE = "용도변경 이력은 없는 것으로 확인되었고, 현장에서도 추가하중에 대한 확인결과 준공도서와 동일한 것으로 조사되었다."
GRADES = ("a", "b", "c", "d", "e")


def empty() -> dict:
    return {"docs": {}, "seismic": {"status": "", "note": ""}, "manage": {"use_change": "무", "struct_change": "무", "surround_change": "무", "checklist": {}, "note": ""},
            "prev_review": {"text": ""}, "history": [], "load": {"photos": [], "note": ""}}


def norm(p: dict | None) -> dict:
    """저장 모양 맞추기(모르는 키·값은 버림)."""
    p = p or {}
    out = empty()
    keys = {k for _, k, _ in DOC_ITEMS}
    for k, v in (p.get("docs") or {}).items():
        if k in keys and isinstance(v, dict):
            out["docs"][k] = {"status": v.get("status") if v.get("status") in DOC_STATUS else "", "note": str(v.get("note") or "").strip()}
    s = p.get("seismic") or {}
    out["seismic"] = {"status": s.get("status") if s.get("status") in SEISMIC else "", "note": str(s.get("note") or "").strip()}
    m = p.get("manage") or {}
    out["manage"] = {k: (m.get(k) if m.get(k) in YNU else "무") for k in ("use_change", "struct_change", "surround_change")}
    out["manage"]["checklist"] = {str(i): bool(v) for i, v in (m.get("checklist") or {}).items() if str(i).isdigit() and int(i) < len(CHECKLIST)}
    out["manage"]["note"] = str(m.get("note") or "").strip()
    out["prev_review"] = {"text": str((p.get("prev_review") or {}).get("text") or "").strip()}
    out["history"] = [h for h in (p.get("history") or []) if isinstance(h, dict)]
    lo = p.get("load") or {}
    photos = []
    for ph in (lo.get("photos") or [])[:LOAD_SLOTS]:
        if isinstance(ph, dict):
            photos.append({"file": str(ph.get("file") or ""), "title": str(ph.get("title") or "").strip()})
    out["load"] = {"photos": photos, "note": str(lo.get("note") or "").strip()}
    return out


def read_fms(data: bytes) -> list[dict]:
    """FMS 점검진단실적 엑셀(전회차 보고서.xlsx) → [{no, kind, start, end, org, chief, cost, grade, result, repair}] — 머리글 "점검진단구분" 줄 아래."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.worksheets[0]
    head = None
    for r in range(1, min(ws.max_row, 10) + 1):
        vals = [str(ws.cell(r, c).value or "").replace(" ", "") for c in range(1, ws.max_column + 1)]
        if any("점검진단구분" in v for v in vals):
            head = (r, vals)
            break
    if head is None:
        raise ValueError("점검진단실적 양식이 아닙니다(머리글 '점검진단구분'이 없음).")
    r0, vals = head
    col = {}
    for i, v in enumerate(vals, 1):
        for key, words in (("kind", ("점검진단구분",)), ("start", ("시작일",)), ("end", ("종료일",)), ("org", ("점검진단기관",)), ("chief", ("책임기술자",)),
                           ("cost", ("비용",)), ("grade", ("안전등급",)), ("result", ("주요점검진단결과",)), ("repair", ("주요보수보강안",))):
            if key not in col and any(w in v for w in words):
                col[key] = i
    rows = []
    for r in range(r0 + 1, ws.max_row + 1):
        get = lambda k: str(ws.cell(r, col[k]).value or "").strip() if k in col else ""  # noqa: E731
        if not get("kind") and not get("start"):
            continue
        rows.append({"no": len(rows) + 1, "kind": get("kind"), "start": get("start")[:10], "end": get("end")[:10], "org": get("org"), "chief": get("chief"),
                     "cost": get("cost"), "grade": get("grade").replace("등급", ""), "result": get("result"), "repair": get("repair")})
    if not rows:
        raise ValueError("점검진단실적에 줄이 없습니다.")
    return rows


def _selfcheck() -> None:
    assert len(CHECKLIST) == 25 and len(DOC_ITEMS) == 14
    n = norm({"docs": {"ledger": {"status": "보유", "note": "컴퓨터 파일"}, "zzz": {"status": "보유"}}, "manage": {"use_change": "유", "checklist": {"3": True, "99": True}},
              "load": {"photos": [{"file": "a.jpg", "title": "옥상"}], "note": ""}})
    assert list(n["docs"]) == ["ledger"] and n["manage"]["use_change"] == "유" and n["manage"]["checklist"] == {"3": True} and n["load"]["photos"][0]["title"] == "옥상"
    rows = read_fms(open(r"C:\Users\윤석현1\Desktop\시특법 견본\정밀\전회차 보고서.xlsx", "rb").read())
    assert len(rows) == 3 and rows[0]["grade"] == "C" and rows[2]["org"] == "(주)한국미래안전건설" and rows[0]["start"] == "2022-10-04", rows[0]
    print("정밀 입력 검증 통과")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    _selfcheck()
