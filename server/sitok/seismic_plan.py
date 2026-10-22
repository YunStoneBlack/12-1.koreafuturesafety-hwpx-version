"""내진성능평가 과업수행계획서 자동 만들기(2026-10-22 사용자 "1 2 3 진행해" — 1 = 과업수행계획서 자동).

원본 = master "성능평가수행계획서"(견본 삼숭초 교사동 과업수행계획서 한글). 채우는 곳: 표지·머리말 용역명·발주처·연월, 1.2.1·3.1 과업기간(날수),
1.3 대상시설물 현황(학교명·건물명·건축년도·구조·층수·연면적·내진등급), 1.4 위치도(현장 사진 칸 위치도 + 주소), 3.1 일정표 머리 날수,
3.2 과업참여기술진(기술자). 2장 방법·3.3 투입장비는 견본 글 그대로. 건 화면 서류 칸 [📝 자동으로 만들기]와 보고서 부록 2(올린 파일이 없을 때)가 씀.
"""
from __future__ import annotations

import re
from pathlib import Path

from server.sitok import report_build as rb
from server.sitok import seismic_field as SF
from server.sitok import seismic_fill as SFL

SAMPLE_PERIOD = "2025년 10월 24일 ~ 2026년 01월 02일(71일간)"


def _kor(d) -> str:
    return f"{d.year}년 {d.month:02d}월 {d.day:02d}일"


def build_plan(db, r, f, dest: Path) -> Path:
    from server.sitok import master
    from server.sitok import seismic_build as SB
    from server.sitok.wall_build import Hwpx

    src = master.master_path("성능평가수행계획서")
    if not src.exists():
        raise ValueError("과업수행계획서 원본이 없습니다(보고서 자동화 설정 > 원본).")
    d = SB.gather(db, r, f)
    sc = (r.survey or {}).get("seismic_contract") or {}
    reg = (f.ledger or {}).get("register") or {}
    field = SF.normalize((r.survey or {}).get("seismic_field"))
    doc = Hwpx(src)
    root = doc.root
    with SFL.borders_for(doc):  # 기술자 줄 지울 때 끝줄 굵은 선(10/22)
        _fill(doc, root, d, sc, reg, field, r, f)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    return dest


def _fill(doc, root, d: dict, sc: dict, reg: dict, field: dict, r, f) -> None:
    from server.sitok import seismic_build as SB

    SB.replace_globals(doc, d)
    if d.get("period_start") and d.get("period_end"):
        days = sc.get("days") or ((d["period_end"] - d["period_start"]).days + 1)
        SFL.replace_loose(doc, SAMPLE_PERIOD, f"{_kor(d['period_start'])} ~ {_kor(d['period_end'])}({days}일간)")
    else:
        days = sc.get("days") or 71
    grade = reg.get("grade") or "특등급"
    for t in SFL._outer(root):
        cells = rb._cells(t)
        head = [SFL._n(rb._cell_text(cells.get((0, c), t))) for c in range(7)]
        if head[:3] == ["학교명", "건물명", "건축년도"]:  # 1.3 대상시설물 현황
            parts = d["name"].split(maxsplit=1)
            floors = (f"지하{d['below']}/" if d.get("below") else "") + f"{d.get('above') or 0}층"  # 칸이 좁음 — 견본 "5층"
            structure = (d.get("structure") or "-").replace("콘크리트구조", "콘크리트조")  # 견본 "철근콘크리트조"
            for c, v in enumerate((parts[0], parts[1] if len(parts) > 1 else "-", f"{d['completion'].year}" if d.get("completion") else "-",
                                   structure, floors, f"{d['area']:,.2f}" if d.get("area") else "-", f"내진 {grade}")):
                SFL._set(cells, (1, c), v)
        elif t.get("rowCnt") == "3" and t.get("colCnt") == "1" and rb._pic_slots(t):  # 1.4 위치도
            SFL._set(cells, (0, 0), d["name"])
            SFL._set(cells, (2, 0), d.get("address") or "-")
            from server.api.routers.sitok_reports import _report_dir

            img = SFL.map_image(f, field, _report_dir(f, r))  # 현장 사진 칸 위치도 > 📍 위치도(깃발·주소, 10/22)
            if img is not None:
                SFL._put(doc, rb._pic_slots(t)[0][1], img, crop=False)
        elif SFL._n(rb._cell_text(cells.get((0, 0), t))) == "과업내용" and t.get("colCnt") == "21":  # 3.1 일정표 머리
            SFL._set(cells, (0, 1), f"과업기간({days}일간)")
            step = max(round(days / 6), 1)
            marks = sorted(c for (r0, c) in cells if r0 == 1 and c >= 1)
            for k, c in enumerate(marks):
                SFL._set(cells, (1, c), f"{days if k == len(marks) - 1 else step * (k + 1)}일")
        elif head[:3] == ["연번", "참여구분", "성명"] and d.get("persons"):  # 3.2 과업참여기술진
            people = d["persons"]
            SFL._resize_tail(t, 1, len(people))
            cells = rb._cells(t)
            for k, p in enumerate(people):
                for c, v in enumerate((str(k + 1), "책임기술인" if k == 0 else "참여기술인", " ".join(p["name"]), p.get("qual") or "", "")):
                    SFL._set(cells, (1 + k, c), v)


def _selfcheck() -> None:
    import datetime

    assert _kor(datetime.date(2025, 10, 24)) == "2025년 10월 24일"
    assert re.sub(r"\s", "", SAMPLE_PERIOD) == "2025년10월24일~2026년01월02일(71일간)"


if __name__ == "__main__":
    _selfcheck()
    print("ok")
