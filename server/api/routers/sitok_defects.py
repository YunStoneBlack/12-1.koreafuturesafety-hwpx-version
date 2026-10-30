"""시특법 현장 결함 조사(2026-10-10 5단계) — 현장 폰 화면(sitok-field.html?report=)과 결함 표(SitokDefect).

- `GET  /sitok/reports/{id}/defects` — 그 회차 결함 전부(층·번호 순) + 요약.
- `POST /sitok/reports/{id}/defects/import` — 지난 보고서 PDF(외관조사 사진첩이 든 것)에서 전회차 결함·사진 가져오기(server/sitok/album_read.py).
- `POST /sitok/reports/{id}/defects/reprev` — 전회차 PDF만 다시(10/20 민재형): 층·번호가 같은 결함의 전회차 값·사진만 바꾸고 이번 회차(확인·이번 사진·원인·신규)는 그대로.
- `POST /sitok/reports/{id}/defects/carry` — 직전 회차 결함을 전회차로 가져오기(이 시스템으로 만든 회차가 있을 때).
- `POST /sitok/reports/{id}/defects/import-current` — 금회차 결함 사진첩 PDF → 이번 결함·사진(내진 10/26, 시특법 10/30 — 현장조사를 프로그램 밖에서 마친 회차).
  전회차·금회차는 순서 없이 둘 다: 반대쪽이 이미 있으면 층·번호가 같고 부재나 결함유형이 같은 줄끼리 한 결함으로 합침(put_album·_join).
- `POST /sitok/reports/{id}/defects` — 새로 찾은 결함(신규). `PATCH/DELETE /sitok/defects/{id}`(지우면 같은 층 뒤 번호 당김, 10/22), `POST /sitok/defects/{id}/photo`,
  `GET /sitok/defects/{id}/photo/{now|prev}`, `POST/DELETE /sitok/defects/{id}/photo/prev` — 전회차 사진 하나씩 올리기·지우기(10/22).
- `POST /sitok/reports/{id}/defects/depths` {items: [{id, depth}]} — 깊이 한꺼번에(10/22 — 불러온 박리·박락에 깊이가 없을 때, 빈칸은 건너뜀).
- `POST /sitok/reports/{id}/vocab` — 부재·결함유형 목록에 추가("이 보고서에만" / "회사 전체 목록에", 10/12).
- `POST /sitok/reports/{id}/defects/remap/suggest`, `POST .../defects/remap` — 지난 보고서에서 온 목록 밖 이름(수직균열·벽체 등)을 조합별로 한꺼번에(AI 제안 → 점검자 확인).
현장 확인(check): same 그대로(비고 기존) · grew 진행(크기 다시, 기존) · repaired 보수 완료(비고 보수, 크기 "-") · new 신규.
물량 자동(인수인계 10/10): 균열류 = 길이 × 개수(m), 면적 결함(누수·백태·박리·박락·층분리·재료분리·철근노출·부식 등) = 폭 × 길이 × 개수(㎡, 폭·길이 m).
부재·결함유형은 고정 목록(server/sitok/kinds.py 기본값 + 설정 탭 회사 목록 + 그 회차에만 추가한 것)에서만 — 목록 밖 값은 저장 안 받음(10/12).
원인은 고정 목록 없이 AI가 사진마다 구체적으로(cause) + 근거 한 줄(cause_note, 1.3 본문·종합결론에 씀) — 사용자 10/12 "획일적이면 오히려 안 좋음".
옹벽(10/20, kinds.is_wall): 층 대신 **부위**(kinds.WALL_PARTS — floor 칸 그대로), 구분은 주요·일반·부대시설, 부재·결함유형은 옹벽 목록(wall_member·wall_dtype),
면적률 없음, 사진 AI는 옹벽 프롬프트(ANALYZE_WALL). 화면은 서버가 주는 fam·parts·unit_label로 글자를 바꿈.
"""

from __future__ import annotations

import datetime
import threading
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokDefect, SitokFacility, SitokReport, User
from server.api.deps import get_current_user, get_db
from server.api.routers.sitok import base_areas
from server.api.routers.sitok_reports import _order, _report_dir, _require as _require_report
from server.api.routers.sitok_settings import add_vocab, vocab_names, vocab_out, vocab_rows
from server.contract_docs import files
from server.sitok import album_read, kinds, learn

router = APIRouter(prefix="/sitok", tags=["sitok"])
AREA_WORDS = ("누수", "백태", "백화", "박리", "박락", "층분리", "재료분리", "철근노출", "부식", "들뜸", "탈락", "파손", "오염",
              "유출", "식생", "퇴적", "배부름", "세굴", "마감불량", "철망")  # 뒤 7개 = 옹벽(폭·길이 m로 면적)
FIELDS = ("floor", "part", "member", "dtype", "count", "width", "length", "depth", "area_ratio", "cause", "cause_note", "progress", "note", "zone")
DEPTH_WORDS = ("박리", "박락", "층분리")  # 깊이(mm) 칸이 있는 결함유형 — 정밀 상태평가 기준(박리 0.5/1.0/2.5, 박락·층분리 15/20/25mm, 10/13)
CHECKS = ("", "same", "grew", "repaired", "new")
MARK = {"same": "기존", "grew": "기존", "repaired": "보수", "new": "신규"}
FLOOR_ORDER = ("옥상", "옥탑", "지상", "지하")
CRACK_WIDTH_M = 0.25  # 균열 보수물량 면적 환산 폭(m) — 길이 × 0.25 = ㎡(형 10/14 "균열은 길이로 재는데 보수물량은 폭 0.25로 면적 환산")
COST_MARKUP = 1.2  # 개략공사비 보수물량 할증 20%(형 10/14)


def is_area(dtype: str) -> bool:
    return any(w in (dtype or "") for w in AREA_WORDS)


def _num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def calc_qty(dtype: str, count: str, width: str, length: str) -> str:
    n, w, ln = _num(count), _num(width), _num(length)
    if n is None or ln is None:
        return ""
    if is_area(dtype):
        return f"{w * ln * n:.2f}" if w is not None else ""
    return f"{ln * n:.2f}"


SLAB_WORDS = ("슬라브", "슬래브", "보", "바닥", "천장", "천정", "지붕")


def calc_ratio(dtype: str, member: str, count: str, width: str, length: str, bases: tuple[float, float]) -> str:
    """면적률(%) = 결함 면적 ÷ 기준 면적 × 100 — 균열은 길이 × 0.25 × 개수(사용자 10/10), 면적 결함은 폭 × 길이 × 개수.
    기준 면적은 부재가 슬래브·보·바닥·천장이면 슬래브 한 칸, 아니면 벽 한 면(sitok.base_areas)."""
    n, w, ln = _num(count), _num(width), _num(length)
    if n is None or ln is None:
        return ""
    area = (w * ln * n if w is not None else None) if is_area(dtype) else ln * 0.25 * n
    if area is None:
        return ""
    base = bases[1] if any(x in (member or "") for x in SLAB_WORDS) else bases[0]
    return f"{area / base * 100:.1f}".rstrip("0").rstrip(".") if base else ""


TAB_PRESETS = ["외부", "정면", "배면", "좌측면", "우측면", "측면", "내부"]  # [＋ 탭] 고르기(10/21 사용자 "외부, 정면, 배면 등")


def is_custom_unit(floor: str) -> bool:
    """사람이 [＋ 탭]으로 만든 탭(외부·정면·배면…) — 층(옥상·지상·지하·N층)이나 옹벽·교량 부위가 아닌 이름."""
    import re
    f = (floor or "").strip()
    return bool(f) and f not in kinds.WALL_PARTS and f not in kinds.BRIDGE_PARTS and not re.search(r"\d|옥상|옥탑|지붕|지하|지상|층$", f)


def floor_key(floor: str) -> tuple:
    """옥상 → 지상 높은 층 → 지하 깊은 층 순(사진첩 순서). 옹벽 부위는 kinds.WALL_PARTS 순(지반 및 기초부 → 전면부 → …), 교량은 BRIDGE_PARTS 순.
    사람이 만든 탭(외부·정면·배면…)은 맨 뒤(TAB_PRESETS 순, 그 밖은 이름 순)."""
    import re
    if floor in kinds.WALL_PARTS:
        return (-1, kinds.WALL_PARTS.index(floor))
    if floor in kinds.BRIDGE_PARTS:  # 교량 부위(10/29) — 상부구조 → 하부구조 → 받침 → 케이블 → 2차부재 → 기타부재("2차부재"가 층 번호로 읽혀 맨 앞에 오던 것)
        return (-1, kinds.BRIDGE_PARTS.index(floor))
    if is_custom_unit(floor):
        return (3, TAB_PRESETS.index(floor) if floor in TAB_PRESETS else len(TAB_PRESETS))
    m = re.search(r"(\d+)", floor or "")
    k = int(m[1]) if m else 0
    if floor.startswith(("옥상", "옥탑", "지붕")):
        return (0, 0)
    if floor.startswith("지하"):
        return (2, k)
    return (1, -k)


def facility_zones(f: SitokFacility | None, rows: list | None = None) -> list[str]:
    """동(구역) 차례(10/30 사용자 "시설물은 1개인데 연결된 동으로 동이 여러 개 — 동마다 결함현황표") — 시설물 ledger["zones"] + 결함에만 있는 동. 없으면 []."""
    out = [z for z in ((f.ledger or {}).get("zones") or [] if f is not None else []) if z]
    for d in rows or []:
        if getattr(d, "zone", "") and d.zone not in out:
            out.append(d.zone)
    return out


def where(d) -> str:
    """결함 자리 글 — 동이 있으면 "통계청 지상8층"."""
    z = getattr(d, "zone", "") or ""
    return f"{z} {d.floor}" if z else d.floor


def _fpre(zone: str, floor: str, seq: int) -> str:
    """결함 사진 파일 이름 앞 "층_NN_" — 동이 있으면 "동_층_NN_"(동마다 층·번호가 겹침, 10/30)."""
    import re
    z = re.sub(r'[\\/:*?"<>|\s]+', "", zone or "")
    return f"{z + '_' if z else ''}{floor}_{seq:02d}_"


def _fname(zone: str, floor: str, seq: int, tag: str) -> str:
    """결함 사진 파일 이름 "층_NN_금회.jpg"(동이 있으면 앞에 동)."""
    return f"{_fpre(zone, floor, seq)}{tag}.jpg"


def _save_zones(f: SitokFacility, zones: list[str]) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    led = dict(f.ledger or {})
    led["zones"] = zones
    f.ledger = led
    flag_modified(f, "ledger")


def _add_zones(f: SitokFacility, names: list[str]) -> None:
    """시설물 동 차례 끝에 없는 동만 더함(새 결함·동 옮기기·사진첩 간지)."""
    have = facility_zones(f)
    new = [z for z in dict.fromkeys(names) if z and z not in have]
    if new:
        _save_zones(f, have + new)


def _last_seq(db: Session, report_id: int, zone: str, floor: str, skip: int | None = None) -> int:
    """동·층의 끝 번호(skip = 셈에서 뺄 결함 id — 옮기는 결함)."""
    q = db.query(SitokDefect.seq).filter(SitokDefect.report_id == report_id, SitokDefect.zone == (zone or ""), SitokDefect.floor == floor)
    if skip is not None:
        q = q.filter(SitokDefect.id != skip)
    return max((x for (x,) in q), default=0)


def _photo_dir(db: Session, r: SitokReport) -> Path:
    return _report_dir(db.get(SitokFacility, r.facility_id), r) / "결함사진"


def _fam(db: Session, r: SitokReport) -> str:
    """결함 목록 묶음 — "" 건축물 / "wall" 옹벽(kinds.family_of)."""
    return kinds.family_of(db.get(SitokFacility, r.facility_id))


def _out(d: SitokDefect) -> dict:
    return {"id": d.id, **{k: getattr(d, k) for k in FIELDS}, "seq": d.seq, "qty": d.qty, "mark": d.mark, "check": d.check,
            "prev": d.prev or None, "has_photo": bool(d.photo and Path(d.photo).exists()),
            "has_prev_photo": bool(d.prev_photo and Path(d.prev_photo).exists()), "starred": d.starred,
            "prev_v": int(Path(d.prev_photo).stat().st_mtime) if d.prev_photo and Path(d.prev_photo).exists() else 0,  # 사진 주소 ?v= — 파일이 바뀌면 새로 받게(10/20 사진 바로잡기)
            "checked_by": d.checked_by,
            "brick": d.brick or None, "is_brick": _is_brick(d),  # 치장벽돌 결함 — 카드에 수직연속/층간구분·상태등급(10/26)
            "ts": max(int(d.checked_at.timestamp()) if d.checked_at else 0,  # 이번 사진 주소 ?t= — 사진을 돌리면(파일 시각) 새로 받게(10/23)
                      int(Path(d.photo).stat().st_mtime) if d.photo and Path(d.photo).exists() else 0)}


def _rows(db: Session, report_id: int) -> list[SitokDefect]:
    """동(시설물 차례, 동 없는 줄 먼저) → 층(옥상 → 지상 위층 → 지하) → 번호."""
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == report_id).all()
    r = db.get(SitokReport, report_id)
    zs = facility_zones(db.get(SitokFacility, r.facility_id) if r else None, rows)
    return sorted(rows, key=lambda d: (zs.index(d.zone) if d.zone in zs else -1, floor_key(d.floor), d.floor, d.seq, d.id))


WALL_PROGRESSIVE = ("배부름", "침하", "세굴", "전도", "활동")  # 옹벽 진행성 구조 결함 — 주의관찰이라도 우선순위 2


def _wall_action(t: str, width: str) -> str:
    """옹벽 조치 기본 문구(견본 2026 상반기 요약표·결과표 낱말) — AI 초안이 바꿀 수 있음."""
    if any(w in t for w in WALL_PROGRESSIVE) or "마감불량" in t or "단차" in t:
        return "주의관찰"
    if "식생" in t:
        return "잡목 및 식생제거"
    if "퇴적" in t:
        return "배수로 정비"
    if "유출" in t:
        return "충진보수"
    if "실링" in t:
        return "실링재 재시공"
    if "이격" in t:
        return "이격부 실링보수"
    if "파손" in t:
        return "블록 국부보수"
    if "백태" in t:
        return "표면세척"
    if "누수" in t:
        return "배수공 정비"
    if "철근" in t:
        return "단면복구"
    if "철망" in t:
        return "철망 보수"
    if "균열" in t:
        w = _num(width)
        return "에폭시주입보수" if w is not None and w >= 0.3 else "표면처리"
    return "주의관찰"


def default_action(dtype: str, width: str, part: str = "") -> str:
    """조치 필요사항 기본 문구 — 6단계 AI 초안 전까지·AI 실패 때(민재형 10/10: 고정 문구는 기본값으로만, 실제는 AI → 점검자 확인).
    견본 9쪽 문구에 맞춤. 균열은 폭 0.3mm 기준 표면처리 / 에폭시주입보수 — 미장·마감·조적 균열은 주입 대신 탄성실링(견본: 비구조체 균열 V-Cut 후 탄성씰링).
    part가 옹벽 구분(주요·일반·부대시설)이면 옹벽 문구(10/20)."""
    t = dtype or ""
    if kinds.is_record(t) or kinds.is_repaired_type(t):
        return "주의관찰"
    if part in kinds.WALL_SECTIONS:
        return _wall_action(t, width)
    if any(w in t for w in ("누수", "백태", "백화")):
        return "마감재 재시공"
    if any(w in t for w in ("철근", "층분리", "재료분리")):
        return "단면복구"
    if "부식" in t:
        return "표면정리 후 재도장"
    if any(w in t for w in ("박리", "박락")):
        return "표면처리"
    if "이격" in t:
        return "탄성실링 보수"
    if any(w in t for w in ("파손", "탈락", "들뜸")):
        return "마감재 재시공"
    if "높이부족" in t:
        return "난간 보강"
    if "균열" in t:
        w = _num(width)
        wide = w is not None and w >= 0.3
        if kinds.is_finish_crack(t):
            return "탄성실링 보수" if wide else "표면처리"
        return "에폭시주입보수" if wide else "표면처리"
    return "주의관찰"


def _wide(dtype: str, width: str) -> bool:
    w = _num(width)
    return "균열" in (dtype or "") and w is not None and w >= 0.3


def method_key(part: str, member: str, dtype: str, width: str) -> str:
    """보수공법을 정하는 묶음 — 구분·부재·결함유형(+균열은 폭 0.3mm 이상 여부)."""
    return "|".join((part or "-", member or "-", (dtype or "").replace(" ", ""), "0.3이상" if _wide(dtype, width) else ""))


def method_combos(db: Session, report_id: int) -> list[dict]:
    """AI에 줄 묶음 [{key, part, member, dtype, wide, count, qty, unit, max_width, causes, default}]."""
    out: dict = {}
    for d in _defects_for_cost(db, report_id):
        k = method_key(d.part, d.member, d.dtype, d.width)
        g = out.setdefault(k, {"key": k, "part": d.part or "-", "member": d.member or "-", "dtype": d.dtype, "wide": _wide(d.dtype, d.width),
                               "count": 0, "qty": 0.0, "unit": "㎡" if is_area(d.dtype) else "m", "max_width": None, "causes": [],
                               "default": default_action(d.dtype, d.width, d.part)})
        g["count"] += 1
        g["qty"] = round(g["qty"] + (_num(d.qty) or 0), 2)
        w = _num(d.width)
        if w is not None:
            g["max_width"] = w if g["max_width"] is None else max(g["max_width"], w)
        if d.cause and d.cause not in g["causes"]:
            g["causes"].append(d.cause)
    return list(out.values())


def method_map(rows: list | None) -> dict:
    """AI 초안(점검자가 고친) methods → {key: (공법, 1식 금액 또는 None)}."""
    return {r["key"]: ((r.get("method") or "").strip(), r.get("lump")) for r in rows or [] if r.get("key") and (r.get("method") or "").strip()}


def action_of(d: SitokDefect, methods: dict | None) -> str:
    m = (methods or {}).get(method_key(d.part, d.member, d.dtype, d.width))
    return m[0] if m else default_action(d.dtype, d.width, d.part)


def summary_rows(db: Session, report_id: int, methods: dict | None = None) -> list:
    """9쪽 요약표 줄 [(층, 구분, 부재, [결함유형들], [조치들])] — 보수 완료는 뺌, 층은 위층부터, 안에서는 처음 나온 순."""
    groups: dict = {}
    for d in _defects_for_cost(db, report_id):  # 보수 완료·기록용 사진("실외기 현황" 등)은 결함 아님
        key = (d.floor, d.part or "-", d.member or "-")
        g = groups.setdefault(key, {"types": [], "acts": []})
        if d.dtype.replace(" ", "") not in [x.replace(" ", "") for x in g["types"]]:
            g["types"].append(d.dtype)
            g["acts"].append(action_of(d, methods))
    order: list = []  # 층 안에서 구분끼리 모이게
    for key in groups:
        if key not in order:
            same = [k for k in groups if k[:2] == key[:2]]
            order += [k for k in same if k not in order]
    return [(k[0], k[1], k[2], groups[k]["types"], groups[k]["acts"]) for k in order]


def priority(d: SitokDefect, methods: dict | None = None) -> int:
    """보수 우선순위 기본값(6단계 AI 전까지) — 1은 긴급용으로 비움. 구조 결함 철근노출·박락·층분리·균열폭 0.3mm 이상 = 2, 그 밖 구조 결함 = 3,
    나머지 4(비구조체, 구조체라도 미장·마감 균열 — 견본 숭의교회 1.5: 내력벽 미장균열 4순위)."""
    act = action_of(d, methods)
    if not kinds.counts_for_rating(d.part, d.dtype):
        return 4
    if any(x in (d.dtype or "") for x in WALL_PROGRESSIVE) and d.part in kinds.WALL_SECTIONS:
        return 2  # 옹벽 배부름·침하·세굴·전도·활동 — 주의관찰이라도 앞순위(10/20)
    if act == "주의관찰":
        return 4
    w = _num(d.width)
    if any(x in (d.dtype or "") for x in ("철근", "박락", "층분리")) or ("균열" in (d.dtype or "") and w is not None and w >= 0.3):
        return 2
    return 3


def missing_photo_note(db: Session, report_id: int) -> str:
    """이번 회차 사진이 없는 결함 안내(보고서 만들 때 경고, 10/14) — "결함 57건 중 이번 사진 없음 3건(지상3층 1번, …)". 없으면 ""."""
    rows = _rows(db, report_id)
    miss = [d for d in rows if not (d.photo and Path(d.photo).exists()) and not (d.check == "repaired" or d.mark == "보수")]
    if not miss:
        return ""
    where_ = ", ".join(f"{where(d)} {d.seq}번" for d in miss[:3]) + (f" 외 {len(miss) - 3}건" if len(miss) > 3 else "")  # 짧게(10/15 "글자 늘어뜨리지 말고")
    return f"결함 {len(rows)}건 중 이번 회차 사진 없음 {len(miss)}건({where_}) — 사진 칸은 비움"


def _defects_for_cost(db: Session, report_id: int) -> list[SitokDefect]:
    return [d for d in _rows(db, report_id) if not (d.check == "repaired" or d.mark == "보수" or not d.dtype
                                                     or kinds.is_record(d.dtype) or kinds.is_repaired_type(d.dtype))]


def priority_rows(db: Session, report_id: int, methods: dict | None = None) -> list:
    """보수물량 및 우선순위 표 줄 [(층, 결함유형, 손상내용, 적용공법, 물량, 단위, 우선순위)] — 층·부재·결함유형별로 물량 합침."""
    groups: dict = {}
    for d in _defects_for_cost(db, report_id):
        key = (d.floor, "구조적결함" if kinds.counts_for_rating(d.part, d.dtype) else "비구조적결함", f"{d.member} {d.dtype}".strip())
        act = action_of(d, methods)
        g = groups.setdefault(key, {"qty": 0.0, "act": act, "unit": "㎡" if is_area(d.dtype) else "m", "prio": 4})
        g["qty"] += _num(d.qty) or 0
        g["prio"] = min(g["prio"], priority(d, methods))
        if _wide(d.dtype, d.width) and g["act"] != act:
            g["act"] = act  # 한 묶음에 0.3mm 넘는 균열이 있으면 그 공법(주입)
    out = []
    for (floor, kind, content), g in groups.items():
        watch = g["act"] == "주의관찰"
        out.append((floor, kind, content, g["act"], "-" if watch or not g["qty"] else f"{g['qty']:.2f}", "-" if watch else g["unit"], str(g["prio"])))
    return out


def cost_rows(db: Session, report_id: int, prices: list, methods: dict | None = None) -> tuple[list, int]:
    """개략공사비 줄 [(구분, 결함 내용, 보수방안, 물량, 단위, 단가, 금액)] + 직접공사비 합계 — 구분(구조체/비구조체)·공법별로 물량 합침,
    단가는 보수 단가표(공법 이름이 같은 것). 주의관찰은 뺌. 단가표에 없는 공법은 "1식" — AI 초안이 추정한 1식 금액(점검자가 고친 것)이 있으면 그 금액,
    없으면 단가·금액 "-"(점검자가 넣음)."""
    table = {p.method.replace(" ", ""): p for p in prices}
    groups: dict = {}
    for d in _defects_for_cost(db, report_id):
        act = action_of(d, methods)
        if act == "주의관찰":
            continue
        g = groups.setdefault((d.part or "-", act), {"types": [], "qty": 0.0, "lump": 0, "lump_keys": set()})
        p = table.get(act.replace(" ", ""))
        q = _num(d.qty) or 0
        if p is not None and not is_area(d.dtype) and (p.unit or "").strip() in ("㎡", "m2", "m²"):
            q = q * CRACK_WIDTH_M  # 균열은 길이로 재지만 보수물량은 폭 0.25m로 보고 면적 환산해 면적 단가(형 10/14)
        q *= COST_MARKUP  # 조사된 보수물량에 20% 할증(형 10/14)
        k = method_key(d.part, d.member, d.dtype, d.width)
        lump = ((methods or {}).get(k) or ("", None))[1]
        if lump and k not in g["lump_keys"]:  # 1식 금액은 묶음마다 한 번
            g["lump"] += int(lump)
            g["lump_keys"].add(k)
        if d.dtype not in g["types"]:
            g["types"].append(d.dtype)
        g["qty"] += q
    rows, direct = [], 0
    for (part, act), g in groups.items():
        p = table.get(act.replace(" ", ""))
        desc = "·".join(g["types"][:2]) + (f" 외 {len(g['types']) - 2}종" if len(g["types"]) > 2 else "")  # 칸이 좁아 두 줄 안에
        if p is None or not p.price:
            if g["lump"]:
                direct += g["lump"]
                rows.append((part, desc, act, "1", "식", f"{g['lump']:,}", f"{g['lump']:,}"))
            else:
                rows.append((part, desc, act, "1", "식", "-", "-"))
            continue
        amount = round(g["qty"] * p.price)
        direct += amount
        rows.append((part, desc, act, f"{g['qty']:.2f}", p.unit, f"{p.price:,}", f"{amount:,}"))
    return rows, direct


def rep_photos(db: Session, report_id: int, per: int = 4) -> dict:
    """1.3 대표사진 {항목 키: [(사진, "층 부재 결함유형")]} — ★ → 진행·신규 → 구조체 → 물량 큰 순, 이번 사진(없으면 전회차)."""
    from server.sitok.ai_draft import category_of

    out: dict = {}
    for d in sorted(_defects_for_cost(db, report_id),
                    key=lambda d: (not d.starred, d.check not in ("grew", "new"), d.part != "구조체", -(_num(d.qty) or 0))):
        photo = d.photo if d.photo and Path(d.photo).exists() else ""  # 이번 회차 사진만(사용자 10/14 — 전회차 사진이 섞이면 안 찍은 걸 못 잡음)
        if not photo:
            continue
        lst = out.setdefault(category_of(d.part, d.member, d.dtype), [])
        if len(lst) < per:
            lst.append((photo, f"{where(d)} {d.member} {d.dtype}".strip() + ("(진행)" if d.check == "grew" else "(신규)" if d.check == "new" else "")))
    return out


def album_floors(db: Session, report_id: int, zones: bool = False) -> list[tuple]:
    """사진첩용 층별 줄(server/sitok/album_make.py) — 번호 순, 사진번호는 층마다 1부터, 보수 완료는 "보수완료"·크기 "-".
    동이 있으면 동·층마다(10/30) — zones=True면 [(동, 층, 줄)](사진첩이 동마다 간지), 아니면 [("동 층", 줄)]."""
    out: list[tuple[str, str, list[dict]]] = []
    for d in _rows(db, report_id):
        if not out or out[-1][0] != (d.zone or "") or out[-1][1] != d.floor:
            out.append((d.zone or "", d.floor, []))
        rows = out[-1][2]
        rep = d.check == "repaired" or d.mark == "보수"
        base = (d.dtype or "").strip()
        rep_type = "보수완료" if base in ("", "-") or kinds.is_repaired_type(base) else f"{base}(보수완료)"  # 보수완료는 원래 결함유형 뒤에 붙임 "이격(보수완료)"(10/30 민재형)
        rows.append({"번호": str(d.seq), "구분": d.part, "부재": d.member, "결함유형": rep_type if rep else kinds.type_with_depth(d.dtype, d.depth),  # 깊이 = "파손(D=0.9mm)"(10/22)
                     "_rep": rep, "_same": (not rep) and (d.progress or "").startswith("비진행"),  # 사진 없을 때 사진칸 글(보수완료 X·"전회차와 동일")용 — album_make
                     "개수": "-" if rep else d.count, "폭": "-" if rep else d.width, "길이": "-" if rep else d.length,
                     "물량": "-" if rep else d.qty, "면적률": "-" if rep else d.area_ratio, "결함원인": "-" if rep else d.cause,
                     "진행유무": "-" if rep else d.progress, "비고": d.mark, "사진번호": f"사진{len(rows) + 1}",
                     "_photo": d.photo if d.photo and Path(d.photo).exists() else "",  # 사진첩도 이번 사진만, 없으면 빈 칸(사용자 10/14 "비우기")
                     # 전회차 비교 사진대장(album_make.compare_pages)용
                     "_now_photo": d.photo if d.photo and Path(d.photo).exists() else "", "_prev_photo": d.prev_photo,
                     "_prev": d.prev or {}, "_check": d.check, "_compare": bool(d.prev) and not (d.dtype or "").rstrip().endswith("현황")
                     and (kinds.is_main_part(d.part) or d.check == "grew" or d.starred)})
    return out if zones else [((f"{z} {fl}" if z else fl), rows) for z, fl, rows in out]


@router.get("/reports/{report_id}/defects")
def list_defects(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    rows = _rows(db, r.id)
    fam = kinds.family_of(f)
    voc = vocab_rows(db, r.company_id, r.id, fam)
    return {"report": {"id": r.id, "year": r.year, "half": r.half, "facility": f.name, "facility_id": f.id},
            "survey_only": bool(f.survey_only), "tab_presets": TAB_PRESETS,  # 결함조사만(0061) — 화면이 결함 조사 탭만 보임
            "seismic": r.half == "성능평가", "seismic_only": bool(getattr(f, "seismic_only", False)),  # 내진성능평가 회차(10/21) — 결함 조사 탭만, 전회차 가져오기 없이
            "defects": [_out(d) for d in rows], "floors": facility_floors(f), "importing": _importing(r.id) or wall_review(r),
            "zones": facility_zones(f, rows),  # 동(구역) — 시설물 1개 안 연결된 동(10/30), 없으면 []
            "fam": fam, "unit_label": kinds.unit_label(fam), "parts": list(kinds.parts_of(fam)),  # 옹벽 = 부위·주요/일반/부대시설(10/20)
            "unit_part": kinds.unit_parts(fam),  # 옹벽·교량(10/29) 부위 → 구분
            "members": [v.name for v in voc if v.base_kind == "member"], "types": [v.name for v in voc if v.base_kind == "dtype"], "vocab": vocab_out(voc),
            "part_of": kinds.part_map(fam),
            "summary": {"total": len(rows), "unchecked": sum(1 for d in rows if not d.check),
                        **{k: sum(1 for d in rows if d.check == k) for k in CHECKS if k}}}


def _require_empty(db: Session, r: SitokReport) -> None:
    if db.query(SitokDefect).filter(SitokDefect.report_id == r.id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 결함 목록이 있습니다 — 다시 가져오려면 목록을 먼저 비우세요.")


def side_block(rows: list[SitokDefect], current: bool) -> str:
    """전회차·금회차 가져오기를 막는 까닭(10/30 사용자 "현장조사 끝난 경우도 전회차와 금회차 둘 다") — 비었거나 반대쪽만 있으면 "".
    금회차 = 줄이 모두 가져온 전회차 결함이고 이번 회차 확인·사진이 하나도 없을 때, 전회차 = 전회차 값이 든 줄이 하나도 없을 때."""
    if current and any(d.check or d.photo or not d.prev for d in rows):
        return "이번 회차 결함(확인·사진·신규)이 이미 있습니다 — 금회차 사진첩은 결함이 없거나 전회차만 가져온 회차에 넣습니다."
    if not current and any(d.prev for d in rows):
        return "전회차 결함이 이미 있습니다 — 바꾸려면 [📄 전회차 PDF만 다시 올리기]를 쓰세요."
    return ""


def _require_side(db: Session, r: SitokReport, current: bool) -> None:
    why = side_block(_rows(db, r.id), current)
    if why:
        raise HTTPException(status.HTTP_409_CONFLICT, why)


@router.post("/reports/{report_id}/defects/import")
def import_pdf(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    if kinds.civil_fam(_fam(db, r)):  # 옹벽·교량은 부록 사진첩(사진 + 설명) 읽기 — PDF·한글 파일, 확인 창(10/20·10/29)
        from server.api.routers.sitok_wall_import import start as start_wall

        return start_wall(report_id, file, user, db)
    _require_side(db, r, current=False)  # 비었거나 금회차만 있을 때(10/30 — 금회차가 있으면 층·번호로 맞춰 붙임)
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지난 보고서 PDF(외관조사 사진첩이 든 것)를 올려 주세요.")
    try:
        state, msg = start_import(db, r, data, user.company_id)
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    out = list_defects(report_id, user, db)
    return {**out, "importing": IMPORTS[r.id]} if state == "running" else {**out, "merged": msg} if msg else out


@router.post("/reports/{report_id}/defects/import-current")
def import_current(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """외부 결함 사진첩 → 이번 결함(10/26 민재형 — 내진성능평가는 1회차라 전회차가 없음, "성능평가 중간에 시작한 사람들이 조사 밖에서 한 거
    있으면 그거 가져올 수 있게"). 읽기는 전회차 가져오기와 같음(우리 사진첩 양식 바로, 다른 양식 AI 1~3분), 넣을 때만 이번 결함·이번 사진으로.
    시특법(10/30 사용자 "현장점검 완료하고 보고서 작성만 남은 경우") — 전회차를 먼저 가져왔으면 층·번호로 맞춰 그 결함의 이번 값·사진으로."""
    r = _require_report(db, user, report_id)
    if kinds.civil_fam(_fam(db, r)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "옹벽·교량은 금회차 사진첩 가져오기가 아직 없습니다 — 건축물 시설물에서 씁니다.")
    _require_side(db, r, current=True)
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "결함 사진첩 PDF(층별 결함 현황표·결함사진표가 든 것)를 올려 주세요.")
    try:
        state, msg = start_import(db, r, data, user.company_id, current=True)
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    out = list_defects(report_id, user, db)
    return {**out, "importing": IMPORTS[r.id]} if state == "running" else {**out, "merged": msg} if msg else out


def start_import(db: Session, r: SitokReport, data: bytes, company_id: int, current: bool = False) -> tuple[str, str]:
    """지난 보고서 PDF → 이 회차 전회차 결함(current = 금회차 사진첩 → 이번 결함). 우리 사진첩이면 바로("done", 결과 글), 타회사 양식이면 AI가
    결함현황표·사진대장을 읽음(1~3분이라 백그라운드 — "running"). 결함표를 못 찾으면 ValueError. 현장 조사 화면·새 등록(10/12 — 이전 회차가 타회사 PDF)이 같이 씀."""
    album = album_read.read(data)
    if album.rows:
        return "done", put_album(db, r, album, current=current)
    import pymupdf

    from server.sitok import foreign_read

    if not foreign_read.defect_tables(pymupdf.open(stream=data, filetype="pdf")):
        raise ValueError("PDF에서 결함현황표를 찾지 못했습니다 — 외관조사 결과(결함 표)가 든 보고서 PDF인지 확인하세요.")
    if IMPORTS.get(r.id, {}).get("state") == "running":
        raise ValueError("이미 읽는 중입니다.")
    IMPORTS[r.id] = {"state": "running", "msg": f"{'다른' if current else '타회사'} 양식 — AI가 결함현황표·사진대장을 읽는 중(1~3분)"}
    threading.Thread(target=_import_foreign, args=(r.id, data, company_id), kwargs={"current": current}, daemon=True).start()
    return "running", ""


IMPORTS: dict[int, dict] = {}  # 회차 id → 타회사 PDF 읽기 상태 {state: running/failed/note, msg}


def wall_review(r: SitokReport) -> dict | None:
    """옹벽 전회차 가져오기 확인 대기(survey["wall_import"], sitok_wall_import) — API가 다시 떠도 남음."""
    s = (r.survey or {}).get("wall_import")
    return {"state": "review", "msg": f"지난 보고서 사진 {len(s['rows'])}장을 읽었습니다 — 부위·결함유형을 확인하고 넣으세요"} \
        if isinstance(s, dict) and isinstance(s.get("rows"), list) else None


def _importing(rid: int) -> dict | None:
    """읽기 상태 — "note"(전회차만 다시 — 결과·실패 글)는 한 번 알려 주고 지움."""
    st = IMPORTS.get(rid)
    if st and st.get("state") == "note":
        IMPORTS.pop(rid, None)
    return st


def _import_foreign(report_id: int, data: bytes, company_id: int, merge: bool = False, current: bool = False) -> None:
    from core.db import SessionLocal
    from server.sitok import foreign_read

    db = SessionLocal()
    try:
        r = db.get(SitokReport, report_id)
        album = foreign_read.read(data, company_id, vocab_names(db, company_id, report_id, _fam(db, r)))
        if not album.rows:
            raise ValueError("결함 줄을 하나도 읽지 못했습니다")
        if merge:  # 전회차 PDF만 다시(10/20)
            IMPORTS[report_id] = {"state": "note", "msg": merge_text(_merge_album(db, r, album))}
            return
        msg = put_album(db, r, album, current=current)  # 그 사이 반대쪽이 아닌 결함이 들어왔으면 ValueError(넣지 않음)
        if msg:  # 금회차·합친 결과 — 결함 화면에 한 번 알림
            IMPORTS[report_id] = {"state": "note", "msg": msg}
        else:
            IMPORTS.pop(report_id, None)
    except Exception as err:  # noqa: BLE001 — 이유를 화면에
        traceback.print_exc()
        why = str(err).splitlines()[0][:150]
        db.rollback()
        has = db.query(SitokDefect).filter(SitokDefect.report_id == report_id).first() is not None  # 합치려던 것(10/30) — 결함 화면에 한 번 알림
        if merge:
            IMPORTS[report_id] = {"state": "note", "msg": f"전회차 PDF를 읽지 못했습니다(바뀐 것 없음): {why}"}
        elif current:
            IMPORTS[report_id] = {"state": "note", "msg": f"결함 사진첩을 읽지 못했습니다(바뀐 것 없음): {why}"}
        elif has:
            IMPORTS[report_id] = {"state": "note", "msg": f"전회차 PDF를 읽지 못했습니다(바뀐 것 없음): {why}"}
        else:
            IMPORTS[report_id] = {"state": "failed", "msg": f"타회사 PDF를 읽지 못했습니다: {why}"}
    finally:
        db.close()


def _album_defect(r: SitokReport, floor: str, seq: int, v: dict, zone: str = "") -> SitokDefect:
    """사진첩 한 줄 값 → 결함(전회차·금회차 가져오기·전회차 PDF만 다시 공통 — 결함유형 "파손(D=0.9mm)"은 결함유형 + 깊이, 10/22). 비고·전회차 값·확인은 부르는 쪽이."""
    dt, dep = kinds.split_depth(v.get("결함유형") or "")
    g = lambda k: v.get(k) or ""  # noqa: E731
    return SitokDefect(report_id=r.id, floor=floor, zone=zone or "", seq=seq, part=g("구분"), member=g("부재"), dtype=kinds.norm(dt), count=g("개수"), width=g("폭"),
                       length=g("길이"), depth=dep, qty=g("물량"), area_ratio=g("면적률"), cause=g("결함원인"), progress=g("진행유무"))


def _save_album(db: Session, r: SitokReport, album, current: bool = False) -> None:
    """읽은 사진첩 결함 → 이 회차 결함. 기본 = 전회차(prev 값·전회차 사진), current = 이번 결함(10/26 내진 외부 사진첩 — 새로 찾은 결함처럼
    check "new"·이번 사진, 비고는 사진첩 값이 기존·신규·보수면 그대로 아니면 "신규", 진행유무가 비면 비진행성)."""
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    for row in album.rows:
        v = row.values
        d = _album_defect(r, row.floor, row.seq, v, row.zone)
        d.mark, d.prev = v["비고"], None if current else dict(v)
        if current:
            d.mark = v["비고"] if v["비고"] in ("기존", "신규", "보수") else "신규"
            d.check, d.checked_at = CUR_CHECK.get(d.mark, "new"), now  # 비고 기존 = 비진행·보수 = 보수 완료(10/30 — 시특법 금회차는 기존이 많음)
            d.progress = v["진행유무"] or "비진행성"
        if row.photo_png:
            p = folder / _fname(row.zone, row.floor, row.seq, "금회" if current else "전회차")
            p.write_bytes(row.photo_png)
            if current:
                d.photo = str(p)
            else:
                d.prev_photo = str(p)
        db.add(d)
    db.commit()


CUR_CHECK = {"기존": "same", "보수": "repaired", "신규": "new"}  # 금회차 사진첩 비고 → 현장 확인


def put_album(db: Session, r: SitokReport, album, current: bool = False) -> str:
    """읽은 사진첩 → 이 회차. 비었으면 그대로(_save_album), 반대쪽(전회차↔금회차)이 있으면 층·번호로 맞춰 합침(_join, 10/30 사용자).
    결과 글 — 비었을 때 전회차는 ""(가져오기 화면이 바로 목록으로). 막히면(side_block) ValueError."""
    rows = _rows(db, r.id)
    why = side_block(rows, current)
    if why:
        raise ValueError(why)
    note = _zoned(db, r, album)
    if not rows:
        _save_album(db, r, album, current=current)
        msg = f"결함 사진첩에서 결함 {len(album.rows)}개를 넣었습니다 — 층·부재·결함유형·사진을 확인하세요" if current else ""
        return " · ".join(x for x in (note, msg) if x)
    items = [(row.zone, row.floor, row.seq, row.values, row.photo_png) for row in album.rows]
    return " · ".join(x for x in (note, join_text(_join(db, r, rows, items, current), current)) if x)


def _zoned(db: Session, r: SitokReport, album) -> str:
    """사진첩이 동 간지("1. 통계청" …)로 나뉘어 있으면(10/30) — 묶음(동마다 건물이 따로)이면 이 건물 이름과 맞는 동 부분만(동 칸은 비움),
    아니면(시설물 1개 안 연결된 동) 동 차례를 시설물에 더함. 알림 글(없으면 ""). 묶음인데 맞는 동이 없으면 ValueError(섞이지 않게)."""
    zones = list(dict.fromkeys(row.zone for row in album.rows if row.zone))
    if not zones:
        return ""
    f = db.get(SitokFacility, r.facility_id)
    if f.group_id:
        name = _key(f.name)
        hit = next((z for z in zones if _key(z) and (_key(z) in name or name in _key(z))), None)
        if hit is None:
            raise ValueError(f"사진첩이 동 {len(zones)}개({', '.join(zones)})로 나뉘어 있는데 이 건물({f.name})과 이름이 맞는 동이 없습니다 — 그 동 부분만 든 PDF를 올려 주세요.")
        album.rows = [row for row in album.rows if row.zone == hit]
        for row in album.rows:
            row.zone = ""
        return f"사진첩 동 {len(zones)}개 중 '{hit}' 부분만 가져왔습니다"
    _add_zones(f, zones)
    return f"동 {len(zones)}개({', '.join(zones)})로 나눠 가져왔습니다"


def _key(t: str) -> str:
    import re
    return re.sub(r"\s", "", t or "")


def _same_def(d: SitokDefect, v: dict) -> bool:
    """층·번호가 같은 두 줄이 같은 결함인지 — 부재가 같거나 결함유형이 같으면(보수완료는 결함유형을 안 봄)."""
    t1, t2 = (_key(kinds.norm(kinds.split_depth(x or "")[0])) for x in (d.dtype, v.get("결함유형")))
    m1 = _key(d.member)
    return bool(m1 and m1 == _key(v.get("부재"))) or bool(t1 and t1 == t2 and not t1.startswith("보수"))


def _differ(a: str, b: str) -> bool:
    """크기 칸 두 값이 다른지 — 둘 다 있을 때만, 숫자는 0.3 = 0.30."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    try:
        return abs(float(a.replace(",", "")) - float(b.replace(",", ""))) > 1e-9
    except ValueError:
        return a != b


def _photo_into(folder: Path, zone: str, floor: str, seq: int, photo, tag: str) -> str:
    """사진첩 사진(바이트) → 결함사진 폴더 파일, 직전 회차 사진(경로)은 그대로."""
    if isinstance(photo, bytes) and photo:
        p = folder / _fname(zone, floor, seq, tag)
        p.write_bytes(photo)
        return str(p)
    return photo or ""


def _join(db: Session, r: SitokReport, rows: list[SitokDefect], items: list, current: bool) -> dict:
    """전회차·금회차 합치기(10/30 사용자 "전회차와 금회차 둘 다") — items = [(동, 층, 번호, 값, 사진 바이트|경로)](동 = 시설물 안 연결된 동, 없으면 "").
    층·번호가 같고 부재나 결함유형이 같으면 한 결함: 금회차면 그 결함의 이번 값·사진·확인(비고 보수 = 보수 완료, 크기가 바뀌었거나 진행성 = 진행, 아니면 비진행),
    전회차면 그 결함의 전회차 값·사진(금회차 비고가 기존·보수인 줄만). 못 맞춘 줄은 더함 — 번호는 금회차 사진첩 번호가 먼저(겹친 전회차 줄은 그 층 끝 번호 뒤로)."""
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    have = {(d.zone or "", d.floor, d.seq): d for d in rows}
    c = {"items": len(items), "matched": 0, "same": 0, "grew": 0, "repaired": 0, "added": 0, "left": 0, "moved": 0}
    pairs, rest, used = [], [], set()
    for it in items:
        zone, floor, seq, v, _photo = it
        d = have.get((zone or "", floor, seq))
        ok = d is not None and d.id not in used and _same_def(d, v) and (
            (v.get("비고") or "") != "신규" if current else d.mark in ("기존", "보수"))
        if ok:
            used.add(d.id)
            pairs.append((d, it))
        else:
            rest.append(it)
    last: dict[tuple[str, str], int] = {}  # (동, 층) → 끝 번호
    for d in rows:
        last[(d.zone or "", d.floor)] = max(last.get((d.zone or "", d.floor), 0), d.seq)
    for zone, floor, seq, _v, _p in items:
        last[(zone or "", floor)] = max(last.get((zone or "", floor), 0), seq)

    def next_seq(zone: str, floor: str) -> int:
        last[(zone or "", floor)] = last.get((zone or "", floor), 0) + 1
        return last[(zone or "", floor)]

    taken = {(d.zone or "", d.floor, d.seq) for d in rows}
    if current:  # 금회차 번호가 먼저 — 그 번호에 맞추지 못한 전회차 줄이 있으면 뒤로
        want = {(z or "", f, s) for z, f, s, _v, _p in rest}
        for d in rows:
            if d.id not in used and (d.zone or "", d.floor, d.seq) in want:
                taken.discard((d.zone or "", d.floor, d.seq))
                d.seq = next_seq(d.zone, d.floor)
                taken.add((d.zone or "", d.floor, d.seq))
                c["moved"] += 1
    for d, (_zone, floor, seq, v, photo) in pairs:
        c["matched"] += 1
        if current:
            mark = v.get("비고") or ""
            if mark == "보수" or kinds.norm(v.get("결함유형") or "").startswith("보수"):
                d.check, d.mark = "repaired", "보수"
                d.count = d.width = d.length = d.depth = d.qty = d.area_ratio = ""
            else:
                dt, dep = kinds.split_depth(v.get("결함유형") or "")
                for attr, k in (("part", "구분"), ("member", "부재"), ("count", "개수"), ("width", "폭"), ("length", "길이"), ("qty", "물량"),
                                ("area_ratio", "면적률"), ("cause", "결함원인")):
                    if v.get(k):
                        setattr(d, attr, v[k])
                if dt:
                    d.dtype, d.depth = kinds.norm(dt), dep or d.depth
                prev = d.prev or {}
                grew = v.get("진행유무") == "진행성" or any(_differ(v.get(k), prev.get(k)) for k in ("개수", "폭", "길이"))
                d.check, d.mark = ("grew" if grew else "same"), "기존"
                d.progress = v.get("진행유무") or ("진행성" if grew else "비진행성")
            d.checked_at = now
            d.photo = _photo_into(folder, d.zone, d.floor, d.seq, photo, "금회") or d.photo
            c[d.check] += 1
        else:
            d.prev = dict(v)
            d.prev_photo = _photo_into(folder, d.zone, d.floor, d.seq, photo, "전회차") or d.prev_photo
            if d.check == "repaired":  # 보수 완료 줄 — 결함유형은 전회차 것으로(사진첩 "보수완료" 대신)
                dt, _dep = kinds.split_depth(v.get("결함유형") or "")
                if dt and kinds.norm(d.dtype or "").startswith("보수"):
                    d.dtype = kinds.norm(dt)
            elif d.check in ("same", "grew"):
                grew = d.progress == "진행성" or any(_differ(getattr(d, a), v.get(k)) for a, k in (("count", "개수"), ("width", "폭"), ("length", "길이")))
                d.check = "grew" if grew else "same"
    for zone, floor, seq, v, photo in rest:
        zone = zone or ""
        if (zone, floor, seq) in taken:
            seq = next_seq(zone, floor)
        taken.add((zone, floor, seq))
        d = _album_defect(r, floor, seq, v, zone)
        if current:  # 금회차에만 있는 줄 — 비고대로(기존인데 전회차를 못 찾은 줄도 기존)
            d.mark = v.get("비고") if v.get("비고") in CUR_CHECK else "신규"
            d.check, d.checked_at = CUR_CHECK[d.mark], now
            d.progress = d.progress or "비진행성"
            d.photo = _photo_into(folder, zone, floor, seq, photo, "금회")
        else:  # 전회차에만 있는 줄 — 확인 전(현장에서 보수됐는지·빠졌는지 점검자가)
            d.mark, d.prev = "기존", dict(v)
            d.prev_photo = _photo_into(folder, zone, floor, seq, photo, "전회차")
        db.add(d)
        c["added"] += 1
    c["left"] = sum(1 for d in rows if d.id not in used) if current else 0
    db.commit()
    return c


def join_text(c: dict, current: bool) -> str:
    """합친 결과 한 줄(짧게) — 결함 화면 머리줄에."""
    if current:
        return (f"금회차 결함 {c['items']}줄 — 전회차와 맞춘 {c['matched']}(비진행 {c['same']}·진행 {c['grew']}·보수 {c['repaired']})"
                + (f" · 새로 더한 {c['added']}" if c["added"] else "")
                + (f" · 금회차에 없는 전회차 {c['left']}줄은 확인 전" + (f"(번호가 겹친 {c['moved']}줄은 뒤 번호로)" if c["moved"] else "") if c["left"] else ""))
    return (f"전회차 결함 {c['items']}줄 — 금회차와 맞춘 {c['matched']}"
            + (f" · 전회차에만 있는 {c['added']}줄은 확인 전으로 더함" if c["added"] else ""))


# 전회차 값(SitokDefect.prev 열쇠) ↔ 이번 칸 — 다시 올린 전회차 PDF로 바꿀 때 "가져온 뒤 아무도 손대지 않은 칸"을 가림
PREV_FIELDS = (("part", "구분"), ("member", "부재"), ("dtype", "결함유형"), ("count", "개수"), ("width", "폭"), ("length", "길이"), ("qty", "물량"),
               ("area_ratio", "면적률"), ("cause", "결함원인"), ("progress", "진행유무"), ("mark", "비고"))


def _merge_album(db: Session, r: SitokReport, album) -> dict:
    """전회차 PDF만 다시(10/20 민재형 "이번 회차 찍은 게 지워지면 안 됨 — 전회차 파일만 다시 올리는 기능"):
    층·번호가 같은 결함의 전회차 값(prev)·전회차 사진을 새 PDF로. 이번 회차(확인·이번 사진·원인 추천·신규 결함)는 그대로 —
    확인 안 한 줄은 가져온 뒤 아무도 손대지 않은 칸(지금 값 == 예전 전회차 값)만 새 값으로. 새 PDF에만 있는 줄은 더하고, 새 PDF에 없는 줄은 지우지 않음."""
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id).all()
    _zoned(db, r, album)  # 동 간지(10/30) — 묶음이면 이 건물 부분만
    have = {(d.zone or "", d.floor, d.seq): d for d in rows if d.prev}
    taken = {(d.zone or "", d.floor, d.seq) for d in rows}
    upd = photos = added = 0
    seen = set()
    for row in album.rows:
        v = row.values
        key = (row.zone or "", row.floor, row.seq)
        d = have.get(key)
        if d is None:  # 새 PDF에만 있는 줄 — 번호가 신규 결함과 겹치면 그 동·층 끝 번호 다음으로
            seq = row.seq if key not in taken else max(s for z, f, s in taken if (z, f) == key[:2]) + 1
            taken.add((key[0], row.floor, seq))
            d = _album_defect(r, row.floor, seq, v, key[0])
            d.mark, d.prev = v["비고"], dict(v)
            if row.photo_png:
                p = folder / _fname(key[0], row.floor, seq, "전회차")
                p.write_bytes(row.photo_png)
                d.prev_photo = str(p)
            db.add(d)
            added += 1
            continue
        seen.add(key)
        old = d.prev or {}
        if not d.check:
            for attr, k in PREV_FIELDS:
                before, after = old.get(k) or "", v.get(k) or ""
                if attr == "dtype":
                    before, after = kinds.norm(kinds.split_depth(before)[0]), kinds.norm(kinds.split_depth(after)[0])
                if (getattr(d, attr) or "") == before:
                    setattr(d, attr, after)
        ob, nb = kinds.split_depth(old.get("결함유형") or "")[1], kinds.split_depth(v.get("결함유형") or "")[1]
        if (d.depth or "") == ob:  # 깊이도 손대지 않은 것만 새 PDF 값으로(10/22)
            d.depth = nb
        d.prev = dict(v)
        if row.photo_png:
            cur = Path(d.prev_photo) if d.prev_photo else None
            if not (cur and cur.exists() and cur.read_bytes() == row.photo_png):
                photos += 1
            p = folder / _fname(row.zone, row.floor, row.seq, "전회차")
            p.write_bytes(row.photo_png)
            d.prev_photo = str(p)
        upd += 1
    db.commit()
    return {"updated": upd, "photos": photos, "added": added, "missing": sum(1 for k in have if k not in seen)}


def merge_text(m: dict) -> str:
    return (f"전회차 PDF로 바꿨습니다 — 전회차 값 {m['updated']}줄 · 사진 바뀜 {m['photos']}장"
            + (f" · 새 줄 {m['added']}" if m["added"] else "") + (f" · 새 PDF에 없는 줄 {m['missing']}(그대로 둠)" if m["missing"] else "")
            + ". 이번 회차에 확인·찍은 것과 원인은 그대로입니다.")


@router.post("/reports/{report_id}/defects/reprev")
def reprev_pdf(report_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[📄 전회차 PDF만 다시 올리기](10/20 민재형) — 우리 사진첩이면 바로, 타회사 양식이면 AI가 읽고(1~3분, 뒤에서) 같은 방식으로 합침."""
    r = _require_report(db, user, report_id)
    if not any(d.prev for d in db.query(SitokDefect).filter(SitokDefect.report_id == r.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "전회차에서 가져온 결함이 없습니다 — [전회차 결함 가져오기]를 쓰세요.")
    data = file.file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지난 보고서 PDF(외관조사 사진첩이 든 것)를 올려 주세요.")
    album = album_read.read(data)
    if album.rows:
        msg = merge_text(_merge_album(db, r, album))
        return {**list_defects(report_id, user, db), "merged": msg}
    import pymupdf

    from server.sitok import foreign_read

    if not foreign_read.defect_tables(pymupdf.open(stream=data, filetype="pdf")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF에서 결함현황표를 찾지 못했습니다 — 외관조사 결과(결함 표)가 든 보고서 PDF인지 확인하세요.")
    if IMPORTS.get(r.id, {}).get("state") == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 읽는 중입니다.")
    IMPORTS[r.id] = {"state": "running", "msg": "타회사 양식 — AI가 결함현황표·사진대장을 읽는 중(1~3분, 전회차만 바꿈)"}
    threading.Thread(target=_import_foreign, args=(r.id, data, user.company_id, True), daemon=True).start()
    return {**list_defects(report_id, user, db), "importing": IMPORTS[r.id]}


@router.post("/reports/{report_id}/defects/carry")
def carry(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    _require_side(db, r, current=False)  # 비었거나 금회차만 있을 때(10/30 — 금회차가 있으면 층·번호로 맞춰 붙임)
    older = [x for x in db.query(SitokReport).filter(SitokReport.facility_id == r.facility_id, SitokReport.id != r.id)
             if _order(x) < _order(r) and db.query(SitokDefect).filter(SitokDefect.report_id == x.id).first()]
    if not older:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "결함 목록이 있는 지난 회차가 없습니다 — 지난 보고서 PDF에서 가져오세요.")
    prev = max(older, key=_order)
    now_rows = _rows(db, r.id)
    items = []
    for x in _rows(db, prev.id):
        if x.check == "repaired":
            continue  # 보수 완료된 것은 다음 회차엔 안 가져감
        vals = {"번호": str(x.seq), "구분": x.part, "부재": x.member, "결함유형": x.dtype, "개수": x.count, "폭": x.width, "길이": x.length,
                "물량": x.qty, "면적률": x.area_ratio, "결함원인": x.cause, "진행유무": x.progress, "비고": x.mark}
        if now_rows:
            items.append((x.zone or "", x.floor, x.seq, vals, x.photo or x.prev_photo))
            continue
        db.add(SitokDefect(report_id=r.id, floor=x.floor, zone=x.zone or "", seq=x.seq, part=x.part, member=x.member, dtype=x.dtype, count=x.count,
                           width=x.width, length=x.length, depth=x.depth, qty=x.qty, area_ratio=x.area_ratio, cause=x.cause, progress=x.progress,
                           mark="기존", prev=vals, prev_photo=x.photo or x.prev_photo))
    if now_rows:  # 금회차를 먼저 넣은 회차 — 층·번호로 맞춰 붙임(10/30)
        msg = join_text(_join(db, r, now_rows, items, False), False)
        return {**list_defects(report_id, user, db), "merged": msg}
    db.commit()
    return list_defects(report_id, user, db)


@router.delete("/reports/{report_id}/defects")
def clear(report_id: int, force: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """목록 비우기(다시 가져오기 전 — 10/16 민재형 "다른 보고서 결함표를 잘못 넣으면 고칠 수 없음") — 현장에서 확인한 줄이 있으면 force(화면이 개수를 보여 주고 다시 물음)일 때만."""
    r = _require_report(db, user, report_id)
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id).all()
    if any(d.check for d in rows) and not force:
        raise HTTPException(status.HTTP_409_CONFLICT, "현장에서 확인한 결함이 있어 비울 수 없습니다.")
    IMPORTS.pop(r.id, None)  # 타회사 PDF 읽기 실패 표시도 지움
    for d in rows:
        db.delete(d)
    db.commit()
    return {"ok": True}


def _is_brick(d: SitokDefect) -> bool:
    from server.sitok import good as G

    return G.is_brick({"part": d.part, "member": d.member, "dtype": d.dtype, "note": d.note})


class DefectIn(BaseModel):
    floor: str | None = None
    zone: str | None = None  # 동(10/30) — 시설물 안 연결된 동, 빈 글 = 동 없음
    part: str | None = None
    member: str | None = None
    dtype: str | None = None
    count: str | None = None
    width: str | None = None
    length: str | None = None
    depth: str | None = None  # 깊이 mm — 박리·박락·층분리만(0043)
    area_ratio: str | None = None
    cause: str | None = None
    cause_note: str | None = None
    progress: str | None = None
    note: str | None = None
    check: str | None = None
    starred: bool | None = None
    ai_guess: dict | None = None  # [+ 신규] 사진 AI 첫 추천 {part, member, dtype, token} — 교정 기록(server/sitok/learn.py, 10/12)
    client_key: str | None = None  # [+ 신규] 창마다 하나 — 신호가 약해 응답만 못 받고 [추가]를 다시 눌러도 두 번 안 생기게(10/22)
    brick: dict | None = None  # 치장벽돌 결함 {type: 수직연속|층간구분, grade: 2~5}(10/26 — 점검자가 고친 것, 비운 값은 지움)


NEW_KEYS: dict[str, tuple[int, float]] = {}  # 신규 결함 client_key → (결함 id, 시각) — 1시간 기억(API 메모리, 재시작하면 비움)


def _require(db: Session, user: User, defect_id: int) -> tuple[SitokDefect, SitokReport]:
    d = db.get(SitokDefect, defect_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "결함을 찾을 수 없습니다.")
    return d, _require_report(db, user, d.report_id)


def _apply(d: SitokDefect, body: DefectIn, user: User, bases: tuple[float, float] | None = None, allowed: dict | None = None) -> None:
    data = body.model_dump(exclude_unset=True)
    data.pop("ai_guess", None)  # 결함 칸이 아님 — add_defect가 따로
    if "brick" in data:  # 치장벽돌 구분·등급(10/26) — 점검자가 등급을 고치면 by = 이름(AI 근거는 지움)
        from server.sitok import good as G

        b = dict(d.brick or {})
        nb = data.pop("brick") or {}
        if "type" in nb:
            if nb["type"] not in (*G.BRICK_TYPES, "", None):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "치장벽돌 구분은 수직연속·층간구분 중 하나입니다.")
            b["type"] = nb["type"] or ""
        if "grade" in nb:
            g = int(nb["grade"] or 0)
            if g and g not in G.BRICK_GRADES:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "치장벽돌 상태등급은 2~5입니다.")
            if g != int(b.get("grade") or 0):
                b.update({"grade": g or None, "by": (user.display_name or "점검자") if g else "", "why": ""})
        d.brick = {k: v for k, v in b.items() if v not in ("", None)} or None
    if "check" in data and data["check"] not in CHECKS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "확인 값이 올바르지 않습니다.")
    for k in ("member", "dtype") if allowed else ():  # 고정 목록(바꿀 때만 — 지난 보고서에서 온 목록 밖 값은 그대로 둘 수 있음)
        v = (data.get(k) or "").strip()
        if v and v != (getattr(d, k) or "") and v not in allowed[k] and not (k == "dtype" and kinds.is_record(v)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"목록에 없는 {kinds.KINDS[k]}입니다: {v} — [+ 새로 추가]로 목록에 먼저 넣으세요.")
    if "cause" in data and "cause_note" not in data and (data["cause"] or "").strip() != (d.cause or ""):
        d.cause_note = ""  # 점검자가 원인을 고치면 AI 근거는 안 맞음
    for k, v in data.items():
        setattr(d, k, v.strip() if isinstance(v, str) else v)
    if "check" in data:
        d.mark = MARK.get(d.check, d.mark)
        if not d.prev and d.check != "repaired":  # 이번에 새로 찾은 결함은 [비진행]·[진행]을 눌러도 결함현황표 비고 "신규"(10/21 사용자)
            d.mark = "신규"
        if d.check == "same" and d.prev:  # 비진행(옛 "그대로") = 전회차 크기
            d.count, d.width, d.length = d.prev.get("개수", d.count), d.prev.get("폭", d.width), d.prev.get("길이", d.length)
        d.checked_by, d.checked_at = user.display_name or "", datetime.datetime.now()
        if d.check == "grew":  # 크기가 커졌으면 진행성
            d.progress = "진행성"
        elif d.check == "same":  # [비진행](10/21 사용자 — 단추 이름 "그대로" → "비진행")
            d.progress = "비진행성"
        elif d.prev and d.prev.get("진행유무"):
            d.progress = d.prev["진행유무"]
    if d.check == "repaired":
        d.count = d.width = d.length = d.depth = d.qty = d.area_ratio = ""
    else:
        d.qty = calc_qty(d.dtype, d.count, d.width, d.length) or d.qty
        if bases is not None and d.check in ("grew", "new"):  # 크기를 새로 잰 것만 다시(그대로·전회차 값은 전회차 면적률 유지)
            d.area_ratio = calc_ratio(d.dtype, d.member, d.count, d.width, d.length, bases) or d.area_ratio


@router.post("/defects/{defect_id}/brick-ai")
def brick_ai(defect_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """치장벽돌 결함 사진(이번, 없으면 전회차)을 AI가 보고 상태등급 2~5(보수·보강·교체·즉시 교체) — 점검자가 바꿀 수 있음(10/26 민재형)."""
    from server.sitok import ai_draft

    d, r = _require(db, user, defect_id)
    if not _is_brick(d):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "치장벽돌 결함이 아닙니다 — 부재를 치장벽돌로 고른 결함만 됩니다.")
    path = next((Path(p) for p in (d.photo, d.prev_photo) if p and Path(p).exists()), None)
    if path is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "사진이 없습니다 — 결함 사진을 먼저 찍으세요.")
    info = f"{where(d)} {d.seq}번 · {d.member} · {d.dtype} · 개소 {d.count or '-'} · 폭 {d.width or '-'} · 길이 {d.length or '-'}"
    try:
        grade, why = ai_draft.brick_grade(user.company_id, path.read_bytes(), info)
    except Exception as e:  # noqa: BLE001 — 화면에 안내(400 — 5xx면 nginx 화면)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"AI 등급 판단을 못 했습니다: {str(e)[:120]}") from e
    d.brick = {**(d.brick or {}), "grade": grade, "by": "AI", "why": why}
    db.commit()
    return _out(d)


@router.post("/reports/{report_id}/defects")
def add_defect(report_id: int, body: DefectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    fam = kinds.family_of(f)
    if not (body.floor or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{kinds.unit_label(fam)}을(를) 고르세요.")
    key = (body.client_key or "").strip()[:80]
    now = time.time()
    for k in [k for k, (_, t) in NEW_KEYS.items() if now - t > 3600]:
        NEW_KEYS.pop(k, None)
    if key and key in NEW_KEYS:  # 같은 창의 [추가]를 다시 누름 — 처음 것이 이미 저장됐으면 그것을 돌려줌(10/22 신호 약할 때)
        old = db.get(SitokDefect, NEW_KEYS[key][0])
        if old is not None and old.report_id == r.id:
            return _out(old)
    zone = (body.zone or "").strip()
    last = _last_seq(db, r.id, zone, body.floor.strip())  # 번호는 동·층마다(10/30)
    _add_zones(f, [zone])
    d = SitokDefect(report_id=r.id, seq=last + 1, check="new", mark="신규", progress="비진행성")  # 진행유무 기본(10/21 형 — 신규도 칸이 비지 않게, [진행]을 누르면 진행성)
    _apply(d, body.model_copy(update={"check": "new"}), user, None if kinds.civil_fam(fam) else base_areas(f), vocab_names(db, r.company_id, r.id, fam))
    d.ai_guess = learn.guess_from(body.ai_guess)
    db.add(d)
    db.flush()
    learn.sync(db, d, r.company_id, user.display_name or "")  # AI 추천과 다르게 넣었으면 회사 교정 기록
    db.commit()
    if key:
        NEW_KEYS[key] = (d.id, now)
    return _out(d)


@router.patch("/defects/{defect_id}")
def update_defect(defect_id: int, body: DefectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, r = _require(db, user, defect_id)
    f = db.get(SitokFacility, r.facility_id)
    fam = kinds.family_of(f)
    old = (d.zone or "", d.floor, d.seq)
    _apply(d, body, user, None if kinds.civil_fam(fam) else base_areas(f), vocab_names(db, r.company_id, r.id, fam))  # 옹벽·교량은 면적률 없음
    if (d.zone or "", d.floor) != old[:2]:  # 동(10/30)·층을 옮김 — 그 자리 끝 번호로, 사진 파일 이름도, 원래 자리 뒤 번호는 당김
        d.zone = d.zone or ""
        d.seq = _last_seq(db, r.id, d.zone, d.floor, skip=d.id) + 1
        pre = _fpre(old[0], old[1], old[2])
        for attr in ("photo", "prev_photo"):
            path = getattr(d, attr)
            if path and _own_file(db, r, path) and Path(path).name.startswith(pre) and Path(path).exists():
                dst = Path(path).with_name(_fpre(d.zone, d.floor, d.seq) + Path(path).name[len(pre):])
                Path(path).replace(dst)
                setattr(d, attr, str(dst))
        _add_zones(f, [d.zone])
        db.flush()
        renumber(db, r, old[1], old[2], old[0])
    learn.sync(db, d, r.company_id, user.display_name or "")  # 나중에 분류를 고쳐도 교정 기록에
    db.commit()
    return _out(d)


REMAP_PROMPT = """시설물 정기안전점검 결함현황표의 (구분, 부재, 결함유형) 이름을 우리 회사 고정 목록 이름으로 맞추려 합니다(지난 보고서 이름이 제각각).
조합마다 바꿀 이름을 JSON 배열 하나로만 답하세요(설명 없이): [{{"no": 번호, "part": "구조체" 또는 "비구조체", "member": "부재", "dtype": "결함유형"}}]
- member는 반드시 이 중 하나 그대로: {members}
  (벽체는 비구조체면 조적벽, 구조체면 내력벽 / 보는 큰보 / "기둥/벽체"처럼 둘이면 앞의 것 / 창대·몰딩·마감면은 마감재 / 천장·바닥은 슬라브)
- dtype은 반드시 이 중 하나 그대로: {types}
  (수직·수평·경사·층간·개구부·창틀하부·"보 균열"처럼 방향·위치가 붙은 균열은 그것을 빼고: 조적벽·파라펫 조적이면 조적균열, 원문에 미장이 있으면 미장균열,
   마감면이면 마감균열, 구조체 콘크리트(슬라브·보·기둥·내력벽)면 균열 / 마감박락·몰탈 탈락은 박락 / 들뜸은 층분리 / 체수·누수흔적·백화는 누수·백태)
- part는 바꾼 부재 기준(내력벽·기둥·큰보·작은보·슬라브·계단·강재 = 구조체, 조적벽·파라펫·마감재 = 비구조체).
- 기록용("○○ 현황")·보수완료 결함유형은 그대로.
[조합 — 번호 | 구분 | 부재 | 결함유형 | 건수]
{rows}"""


def _off_combos(db: Session, r: SitokReport) -> tuple[list[dict], dict]:
    allowed = vocab_names(db, r.company_id, r.id, _fam(db, r))
    parts = kinds.parts_of(_fam(db, r))
    combos: dict = {}
    for d in _rows(db, r.id):
        off = (d.member and d.member not in allowed["member"]) or (d.dtype not in allowed["dtype"] and not kinds.is_record(d.dtype)) \
            or d.part not in parts
        if off:
            k = (d.part or "", d.member or "", d.dtype or "")
            combos[k] = combos.get(k, 0) + 1
    return [{"part": p, "member": m, "dtype": t, "count": n} for (p, m, t), n in sorted(combos.items(), key=lambda x: -x[1])], allowed


@router.post("/reports/{report_id}/defects/remap/suggest")
def remap_suggest(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """목록 밖 이름(지난 보고서에서 온 수직균열·벽체 등) — 조합별로 AI가 목록 이름을 제안(저장 안 함, 점검자가 확인하고 [바꾸기])."""
    from server.sitok import vision

    r = _require_report(db, user, report_id)
    combos, allowed = _off_combos(db, r)
    fam = _fam(db, r)
    parts = kinds.parts_of(fam)
    if not combos:
        return {"combos": []}
    rows = "\n".join(f"{i} | {c['part']} | {c['member']} | {c['dtype']} | {c['count']}" for i, c in enumerate(combos, 1))
    try:
        got = vision.ask_json(user.company_id, [], REMAP_PROMPT.format(members=", ".join(allowed["member"]), types=", ".join(allowed["dtype"]), rows=rows),
                              max_tokens=8000)
    except Exception:  # noqa: BLE001 — AI가 안 되면 제안 없이(점검자가 직접 고름)
        got = []
    by_no = {int(g["no"]): g for g in got if isinstance(g, dict) and str(g.get("no", "")).isdigit()} if isinstance(got, list) else {}
    for i, c in enumerate(combos, 1):
        g = by_no.get(i, {})
        member, dtype = _text(g.get("member")), _text(g.get("dtype"))
        member = member if member in allowed["member"] else (c["member"] if c["member"] in allowed["member"] else "")
        dtype = dtype if dtype in allowed["dtype"] or (kinds.is_record(dtype) and dtype == c["dtype"]) else (c["dtype"] if c["dtype"] in allowed["dtype"] else "")
        part = g.get("part") if g.get("part") in parts else (c["part"] if c["part"] in parts else kinds.default_part(member, fam) or parts[-1])
        c["to"] = {"part": part, "member": member, "dtype": dtype}
    return {"combos": combos}


class RemapIn(BaseModel):
    maps: list[dict]  # [{part, member, dtype, to: {part, member, dtype}}]


@router.post("/reports/{report_id}/defects/remap")
def remap(report_id: int, body: RemapIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """조합별로 이름 한꺼번에 바꾸기 — 바꿀 이름은 목록 안(기록용 "○○ 현황"은 그대로 둘 수 있음). 전회차 원래 이름은 prev에 남아 있음."""
    r = _require_report(db, user, report_id)
    fam = _fam(db, r)
    allowed = vocab_names(db, r.company_id, r.id, fam)
    plan = {}
    for m in body.maps:
        to = m.get("to") or {}
        tp, tm, tt = (str(to.get(k) or "").strip() for k in ("part", "member", "dtype"))
        if tp not in kinds.parts_of(fam) or (tm and tm not in allowed["member"]) or not tt \
                or (tt not in allowed["dtype"] and not (kinds.is_record(tt) and tt == m.get("dtype"))):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"바꿀 이름이 목록에 없습니다: {m.get('member')} {m.get('dtype')} → {tm} {tt}")
        plan[(m.get("part") or "", m.get("member") or "", m.get("dtype") or "")] = (tp, tm, tt)
    n = 0
    for d in _rows(db, r.id):
        to = plan.get((d.part or "", d.member or "", d.dtype or ""))
        if to:
            d.part, d.member, d.dtype = to
            n += 1
    db.commit()
    return {**list_defects(report_id, user, db), "changed": n}


class VocabAdd(BaseModel):
    kind: str  # member / dtype
    name: str
    scope: str = "report"  # report = 이 보고서에만 / company = 회사 전체 목록에


class DepthItem(BaseModel):
    id: int
    depth: str = ""


class DepthsIn(BaseModel):
    items: list[DepthItem]


@router.post("/reports/{report_id}/defects/depths")
def set_depths(report_id: int, body: DepthsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """깊이 한꺼번에 넣기(10/22 민재형·사용자 "불러온 데이터에 깊이가 안 적혔으면 목록 밖 이름 바꾸기처럼 한꺼번에") — 빈칸은 건너뜀, 숫자(mm)만."""
    r = _require_report(db, user, report_id)
    want = {it.id: it.depth.strip().replace(",", ".") for it in body.items if it.depth.strip()}  # 쉼표는 소수점으로(0,8 → 0.8)
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id, SitokDefect.id.in_(list(want))).all() if want else []
    for d in rows:
        v = _num(want[d.id])
        if v is None or v < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{d.floor} {d.seq}번 깊이는 숫자(mm)로 넣어 주세요: {want[d.id]}")
        d.depth = want[d.id]
    db.commit()
    return {"saved": len(rows)}


@router.post("/reports/{report_id}/vocab")
def add_report_vocab(report_id: int, body: VocabAdd, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """현장에서 목록에 없는 부재·결함유형 추가 — 점검자가 "이 보고서에만 / 회사 전체 목록에" 고름(사용자 10/12)."""
    r = _require_report(db, user, report_id)
    fam = _fam(db, r)
    add_vocab(db, r.company_id, body.kind, body.name, None if body.scope == "company" else r.id, fam)
    return vocab_out(vocab_rows(db, r.company_id, r.id, fam))


@router.delete("/defects/{defect_id}")
def delete_defect(defect_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """결함 지우기 — 불러온 것·신규 모두(10/22 사용자 "인테리어 공사 등으로 보수가 많이 이루어졌을 때 불러온 항목을 지우면 한 칸씩 당겨지게").
    보고서에서 아예 빠짐(보수완료로 남기려면 [보수 완료]). 같은 층 뒤 번호를 하나씩 당김(사진번호는 원래 층마다 차례)."""
    d, r = _require(db, user, defect_id)
    for path in (d.photo, d.prev_photo):
        if path and _own_file(db, r, path):  # 직전 회차에서 이어 온 전회차 사진(그 회차 파일)은 안 지움
            Path(path).unlink(missing_ok=True)
    floor, gone, zone = d.floor, d.seq, d.zone or ""
    db.delete(d)
    db.flush()
    moved = renumber(db, r, floor, gone, zone)
    db.commit()
    return {"ok": True, "renumbered": moved}


def renumber(db: Session, r: SitokReport, floor: str, gone: int, zone: str = "") -> int:
    """지운 번호(gone) 뒤 같은 층 결함 번호를 하나씩 당김(10/22). 사진 파일 이름(층_NN_금회·전회차.jpg — 올릴 때 번호로 지음)도 같이 바꿔
    다음에 찍은 사진이 다른 결함 사진을 덮지 않게 — 앞 번호부터 차례로(바꿀 이름 자리는 지운 결함 것이거나 방금 옮긴 것이라 비어 있음)."""
    rows = db.query(SitokDefect).filter(SitokDefect.report_id == r.id, SitokDefect.floor == floor, SitokDefect.zone == (zone or ""),
                                        SitokDefect.seq > gone).order_by(SitokDefect.seq).all()  # 같은 동·층만(10/30)
    for d in rows:
        old, new = d.seq, d.seq - 1
        pre = _fpre(zone, floor, old)
        for attr in ("photo", "prev_photo"):
            path = getattr(d, attr)
            if not path or not _own_file(db, r, path):
                continue
            src = Path(path)
            if src.name.startswith(pre) and src.exists():
                dst = src.with_name(_fpre(zone, floor, new) + src.name[len(pre):])
                src.replace(dst)
                setattr(d, attr, str(dst))
        d.seq = new
    db.flush()
    return len(rows)


@router.post("/defects/{defect_id}/photo")
def upload_photo(defect_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, r = _require(db, user, defect_id)
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / _fname(d.zone, d.floor, d.seq, "금회")
    p.write_bytes(files.to_jpeg(file.file.read(), file.filename or ""))
    d.photo = str(p)
    d.checked_at = datetime.datetime.now()
    db.commit()
    return _out(d)


def _own_file(db: Session, r: SitokReport, path: str) -> bool:
    """이 회차 사진 폴더 안 파일인가 — 직전 회차에서 이어 온 전회차 사진(carry)은 그 회차 파일이라 지우지 않고 연결만 끊음."""
    try:
        return Path(path).resolve().parent == _photo_dir(db, r).resolve()
    except OSError:
        return False


@router.post("/defects/{defect_id}/photo/prev")
def upload_prev_photo(defect_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """전회차 사진 직접 올리기(10/22 사용자 — 지난 보고서에서 잘못 가져왔거나 못 가져왔을 때). 판정·이번 사진은 그대로."""
    d, r = _require(db, user, defect_id)
    folder = _photo_dir(db, r)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / _fname(d.zone, d.floor, d.seq, "전회차")
    p.write_bytes(files.to_jpeg(file.file.read(), file.filename or ""))
    d.prev_photo = str(p)
    db.commit()
    return _out(d)


@router.delete("/defects/{defect_id}/photo/prev")
def delete_prev_photo(defect_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """전회차 사진 지우기(10/22 사용자 — 사진대장 "보수" 칸에 엉뚱한 자리가 들어온 것 같은 경우 방어)."""
    d, r = _require(db, user, defect_id)
    if d.prev_photo and _own_file(db, r, d.prev_photo):
        Path(d.prev_photo).unlink(missing_ok=True)
    d.prev_photo = ""
    db.commit()
    return _out(d)


@router.get("/defects/{defect_id}/photo/{which}")
def photo(defect_id: int, which: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d, _ = _require(db, user, defect_id)
    path = d.photo if which == "now" else d.prev_photo
    if not path or not Path(path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(path, media_type="image/jpeg")


# 옛 고정 원인 낱말 — 이 중 하나면 "뭉뚱그린 원인"으로 보고 [🤖 원인 추천]이 사진을 보고 구체적으로 바꿈(점검자가 직접 쓴 구체적인 원인은 그대로)
GENERIC_CAUSES = {"건조수축균열", "건조수축", "온도균열", "시공불량", "노후화", "노후", "균열부누수", "방수층노후", "배수불량", "피복두께부족", "중성화", "동결융해",
                  "외력·충격", "외력", "충격", "부등침하", "과하중", "누수", "재료분리", "-"}
CAUSE_RULE = """원인은 구체적으로 — 같은 누수·균열이라도 사진에서 보이는 위치·모양·흔적에 따라 원인이 다릅니다. "노후화"·"건조수축균열"처럼 뻔한 한 낱말로 뭉뚱그리지 말 것.
- cause: 결함현황표 원인 칸(좁음) — 20자 안팎(예: "창호 상부 실링 노후로 빗물 유입", "상부 배관 이음부 누수", "개구부 모서리 응력집중", "옥상 방수층 들뜸으로 슬라브 누수")
- cause_note: 그 원인으로 본 근거 한 줄(위치·모양·흔적, 60자 안팎 — 보고서 1.3 본문·종합결론에 씀. "사진에서"·"사진상" 같은 말 없이 점검자가 직접 본 문장)"""
CAUSE_PROMPT = """시설물 정기안전점검 외관조사 결함 {n}개입니다. 사진은 아래 목록의 "사진 N" 순서대로 붙어 있습니다.
결함마다 원인을 쓰세요.
{rule}
사진이 없는 결함은 결함 정보만으로 조심스럽게(근거 끝에 "추정"이라고).
JSON 배열 하나로만 답하세요(설명 없이): [{{"id": 번호, "cause": "원인", "cause_note": "근거"}}]

[결함 — id | 층 | 구분 | 부재 | 결함유형 | 폭 | 길이 | 진행 | 지금 원인 | 사진]
{rows}"""


def _photo_of(d: SitokDefect) -> str:
    return d.photo if d.photo and Path(d.photo).exists() else d.prev_photo if d.prev_photo and Path(d.prev_photo).exists() else ""


def _vague(cause: str) -> bool:
    return not (cause or "").strip() or (cause or "").replace(" ", "") in GENERIC_CAUSES


@router.post("/reports/{report_id}/defects/causes")
def suggest_causes(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI 결함원인 추천 — 원인이 비었거나 뭉뚱그린 낱말(노후화·건조수축균열 등)인 결함만, 사진(이번 것, 없으면 전회차)을 보고 구체적인 원인 + 근거.
    5개씩 묶어 동시에(사진이 많아 한 번에는 못 보냄). 바꾼 목록을 돌려줌(점검자가 카드에서 다시 고칠 수 있음)."""
    from concurrent.futures import ThreadPoolExecutor

    from server.sitok import vision

    r = _require_report(db, user, report_id)
    rows = [d for d in _defects_for_cost(db, r.id) if _vague(d.cause)]
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "원인을 다시 볼 결함이 없습니다 — 비었거나 뭉뚱그린 원인(노후화·건조수축균열 등)만 AI가 바꿉니다.")
    chunks = [rows[i:i + 5] for i in range(0, len(rows), 5)]

    def one(chunk: list[SitokDefect]) -> list:
        imgs, lines = [], []
        for d in chunk:
            p = _photo_of(d)
            if p:
                imgs.append(Path(p).read_bytes())
            lines.append(f"{d.id} | {d.floor} | {d.part} | {d.member} | {d.dtype} | {d.width} | {d.length} | {d.progress} | {d.cause or '(없음)'} | "
                         + (f"사진 {len(imgs)}" if p else "사진 없음"))
        got = vision.ask_json(user.company_id, imgs, CAUSE_PROMPT.format(n=len(chunk), rule=CAUSE_RULE, rows="\n".join(lines)), max_tokens=4000, writing=True)
        return [g for g in got if isinstance(g, dict)] if isinstance(got, list) else []

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            got = [g for part in pool.map(one, chunks) for g in part]
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"원인을 추천하지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    by_id = {d.id: d for d in rows}
    changed = []
    for g in got:
        d = by_id.get(int(g.get("id", 0)) if str(g.get("id", "")).isdigit() else 0)
        cause = str(g.get("cause") or "").strip()
        if d is None or not cause or cause == d.cause:
            continue
        changed.append({"id": d.id, "floor": d.floor, "seq": d.seq, "what": f"{d.member} {d.dtype}".strip(), "before": d.cause, "after": cause,
                        "note": str(g.get("cause_note") or "").strip()})
        d.cause, d.cause_note = cause, str(g.get("cause_note") or "").strip()
    db.commit()
    return {"changed": changed, "asked": len(rows)}


# ---------- 전회차 없이 시작·사진 AI 분석(2026-10-11, 10/12 고정 목록) ----------
WIDTH_BANDS = ["0.1", "0.2", "0.3", "0.5", "1.0"]


def facility_floors(f: SitokFacility) -> list[str]:
    """관리대장 층수로 층 목록(옥상 → 지상 위층부터 → 지하) — 전회차 결함이 없는 층도 고를 수 있게. 옹벽은 부위 목록(kinds.WALL_PARTS).
    + 사람이 [＋ 탭]으로 더한 탭(ledger.units_extra — 외부·정면·배면…), − 🗑로 지운 기본 탭(ledger.units_hidden). 시설물에 두어 다음 회차도 같음(10/21)."""
    led = f.ledger or {}
    if kinds.is_civil(f):  # 옹벽 WALL_PARTS · 교량 BRIDGE_PARTS(10/29)
        base = kinds.units_of(kinds.family_of(f))
    else:
        base = ["옥상층"] + [f"지상{n}층" for n in range(int(f.floors_above or 0), 0, -1)] + [f"지하{n}층" for n in range(1, int(f.floors_below or 0) + 1)]
        if len(base) == 1:
            base = []
    hidden = set(led.get("units_hidden") or [])
    extra = [x for x in led.get("units_extra") or [] if x]
    out = [u for u in dict.fromkeys(base + extra) if u not in hidden]
    return sorted(out, key=lambda u: (floor_key(u), extra.index(u) if u in extra else 0))  # 만든 탭끼리는 만든 순


class UnitIn(BaseModel):
    name: str


def _unit_name(s: str) -> str:
    import re
    name = re.sub(r"\s+", " ", s or "").strip()[:30]
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "탭 이름을 넣으세요.")
    return name


def _save_units(db: Session, f: SitokFacility, extra: list[str], hidden: list[str]) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    led = dict(f.ledger or {})
    led["units_extra"], led["units_hidden"] = extra, hidden
    f.ledger = led
    flag_modified(f, "ledger")


@router.post("/reports/{report_id}/units")
def add_unit(report_id: int, body: UnitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """층 탭 [＋ 탭] — 외부·정면·배면 같은 이름이나 빠진 층(지상5층)을 탭으로. 지웠던 기본 탭이면 다시 보이기만."""
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    name = _unit_name(body.name)
    led = f.ledger or {}
    extra, hidden = list(led.get("units_extra") or []), [u for u in led.get("units_hidden") or [] if u != name]
    if name in facility_floors(f):
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{name}' 탭은 이미 있습니다.")
    if name not in extra:
        extra.append(name)
    _save_units(db, f, extra, hidden)
    db.commit()
    return {"floors": facility_floors(f), "name": name}


@router.post("/reports/{report_id}/units/delete")
def delete_unit(report_id: int, body: UnitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """층 탭 🗑 — 결함이 하나도 없는 탭만(있으면 409). 더한 탭은 목록에서 빼고, 관리대장 층수로 생긴 기본 탭은 숨김에 넣음."""
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    name = _unit_name(body.name)
    n = db.query(SitokDefect).filter(SitokDefect.report_id == r.id, SitokDefect.floor == name).count()
    if n:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{name}'에 결함이 {n}개 있어 지울 수 없습니다 — 결함 카드를 먼저 지우세요.")
    led = f.ledger or {}
    extra, hidden = [u for u in led.get("units_extra") or [] if u != name], list(led.get("units_hidden") or [])
    if name in facility_floors(f) and name not in (led.get("units_extra") or []) and name not in hidden:
        hidden.append(name)
    _save_units(db, f, extra, hidden)
    db.commit()
    return {"floors": facility_floors(f)}


@router.post("/reports/{report_id}/zones")
def add_zone(report_id: int, body: UnitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """동 [＋ 동](10/30) — 시설물 1개 안 연결된 동(통계청·선거관리위원회 …). 시설물에 두어 다음 회차도 같음."""
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    name = _unit_name(body.name)
    zs = facility_zones(f, _rows(db, r.id))
    if name in zs:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{name}' 동은 이미 있습니다.")
    _save_zones(f, zs + [name])
    db.commit()
    return {"zones": zs + [name], "name": name}


@router.post("/reports/{report_id}/zones/delete")
def delete_zone(report_id: int, body: UnitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """동 지우기 — 이 회차에 그 동 결함이 하나도 없을 때만(있으면 409)."""
    r = _require_report(db, user, report_id)
    f = db.get(SitokFacility, r.facility_id)
    name = _unit_name(body.name)
    n = db.query(SitokDefect).filter(SitokDefect.report_id == r.id, SitokDefect.zone == name).count()
    if n:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{name}' 동에 결함이 {n}개 있어 지울 수 없습니다 — 결함 카드를 먼저 옮기거나 지우세요.")
    _save_zones(f, [z for z in facility_zones(f) if z != name])
    db.commit()
    return {"zones": facility_zones(f, _rows(db, r.id))}


ANALYZE = """시설물 정기안전점검 현장에서 점검자가 찍은 결함 사진입니다({where}). 사진을 보고 결함현황표 한 줄의 초안을 JSON 객체 하나로만 답하세요(설명 없이).
{{"is_defect": 결함이면 true, 결함이 아니라 전경·설비·상태 기록용 사진이면 false,
 "part": "구조체" 또는 "비구조체" — 부재 기준(철근콘크리트 내력벽·기둥·큰보·작은보·슬라브·계단·강재 = 구조체, 조적벽·파라펫·마감재 = 비구조체),
 "member": 부재 — 반드시 이 목록 중 하나 그대로: {members},
 "dtype": 결함유형 — 반드시 이 목록 중 하나 그대로: {types} (기록용 사진이면 "○○ 현황", 예: "실외기 현황"),
 "new_member": 목록에 맞는 부재가 정말 없을 때만 제안할 이름(짧게, 이때 member는 ""), 아니면 null,
 "new_dtype": 목록에 맞는 결함유형이 정말 없을 때만 제안할 이름(짧게, 이때 dtype은 ""), 아니면 null,
 "cause": 원인(아래 규칙), "cause_note": 근거(아래 규칙),
 "width": 균열이면 폭 구간(mm) "0.1"·"0.2"·"0.3"·"0.5"·"1.0" 중 하나(1.0은 1mm 이상), 균열이 아니면 null,
 "count": 사진에 보이는 같은 결함 개수(정수, 보통 1),
 "note": "사진에서 본 것 한 줄(점검자 참고용 — 균열 방향(수직·수평·경사)은 여기에)"}}
결함유형 고르는 법(구조체 균열만 상태평가 개수에 들어가므로 중요):
- 균열 = 콘크리트 구조체 자체의 균열(노출 콘크리트, 또는 곧고 길게 이어지거나 개구부 모서리에서 사선으로 뻗는 등 구조 균열 모양).
  미장균열 = 콘크리트 위 미장(모르타르)층만 갈라진 것(가늘고 불규칙·그물 모양) — 구조체 부재라도 미장층 균열이면 미장균열.
  마감균열 = 도장·타일·석고보드 등 마감재 균열. 조적균열 = 벽돌·블록·줄눈이 갈라진 것. 수직·수평·경사 같은 방향은 결함유형에 쓰지 말 것.
- 박리 = 표면이 얇게 벗겨짐, 박락 = 콘크리트 조각이 떨어져 나감, 층분리 = 표층이 들떠 분리(아직 안 떨어짐), 재료분리 = 곰보·골재 노출,
  이격 = 서로 다른 부재·재료 사이가 벌어짐(기둥-조적벽, 창호 주변), 누수·백태 = 물 흐른 자국·얼룩·백화, 높이부족 = 난간·파라펫 높이 기준 미달.
- 누수·백태의 구분·부재: {leak_rule} — 구조체 콘크리트면에서 직접 새는 것만 구조체(슬라브·내력벽 등),
  천장재·도배·도장 등 마감재의 누수흔적이나 배관·설비 누수·결로 얼룩은 부재 마감재·비구조체(note에 배관 누수 등 추정 원인).
{cause_rule}
폭은 사진만으로는 어림이므로 보이는 굵기로 가장 가까운 구간을 고르세요(머리카락 굵기 ≈ 0.1, 연필 선 ≈ 0.3, 뚜렷이 벌어짐 ≥ 0.5)."""

ANALYZE_WALL = """옹벽(시특법 2종·3종 시설물) 정기안전점검 현장에서 점검자가 찍은 결함 사진입니다({where}). 사진을 보고 결함 한 줄의 초안을 JSON 객체 하나로만 답하세요(설명 없이).
{{"is_defect": 결함이면 true, 결함이 아니라 전경·상태 기록용 사진이면 false,
 "part": "주요시설" 또는 "일반시설" 또는 "부대시설" — 부재 기준(블록·콘크리트·기초·뒷채움·채움재·철망 = 주요시설(전면부·지반 및 기초부),
   배수공·배수로·집수정·소단·보호콘크리트·사면 = 일반시설, 안전펜스·낙석방지망·점검로 = 부대시설),
 "member": 부재 — 반드시 이 목록 중 하나 그대로: {members},
 "dtype": 결함유형 — 반드시 이 목록 중 하나 그대로: {types} (기록용 사진이면 "○○ 현황", 예: "기초부 현황"),
 "new_member": 목록에 맞는 부재가 정말 없을 때만 제안할 이름(짧게, 이때 member는 ""), 아니면 null,
 "new_dtype": 목록에 맞는 결함유형이 정말 없을 때만 제안할 이름(짧게, 이때 dtype은 ""), 아니면 null,
 "cause": 원인(아래 규칙), "cause_note": 근거(아래 규칙),
 "width": 균열이면 폭 구간(mm) "0.1"·"0.2"·"0.3"·"0.5"·"1.0" 중 하나(1.0은 1mm 이상), 균열이 아니면 null,
 "count": 사진에 보이는 같은 결함 개수(정수, 보통 1),
 "note": "사진에서 본 것 한 줄(점검자 참고용)"}}
결함유형 고르는 법(옹벽 세부지침·3종 매뉴얼 옹벽 체크리스트 기준):
- 균열 = 블록·콘크리트 전면부가 갈라진 것(보강토 블록 한 장 안의 균열도 균열), 파손 = 블록 모서리·단부가 깨져 떨어짐, 이격 = 블록끼리·줄눈이 벌어짐,
  백태 = 흰 석회 자국, 누수 = 물 흐른 자국·젖음, 철근노출 = 콘크리트 옹벽 철근이 드러남, 채움재유출 = 블록 뒷채움 자갈이 틈으로 흘러나옴,
  토사유출 = 흙이 빠져나와 배면·기초가 패임, 실링재탈락 = 신축이음 실링이 떨어짐, 잡목식생 = 전면·상부·소단의 잡목·넝쿨, 토사·낙엽퇴적 = 배수로·집수정 막힘,
  배부름 = 전면부가 불룩하게 변형, 침하·세굴 = 기초 지반이 내려앉거나 물에 파임, 전도·경사 = 옹벽이 기울어짐, 활동 = 옹벽이 밀려남, 철망손상 = 돌망태 철망 끊어짐,
  마감불량 = 블록 쌓기·채움이 고르지 않음, 단차 = 상부 활용부지·소단에 턱이 생김.
- 배부름·침하·세굴·전도·경사·활동은 진행성 구조 결함이라 조금이라도 보이면 note에 "진행성 확인 필요"라고 적을 것.
{cause_rule}
폭은 사진만으로는 어림이므로 보이는 굵기로 가장 가까운 구간을 고르세요(머리카락 굵기 ≈ 0.1, 연필 선 ≈ 0.3, 뚜렷이 벌어짐 ≥ 0.5)."""

ANALYZE_BRIDGE = """교량(시특법 2종·3종 시설물) 정기안전점검 현장에서 점검자가 찍은 결함 사진입니다({where}). 사진을 보고 결함 한 줄의 초안을 JSON 객체 하나로만 답하세요(설명 없이).
{{"is_defect": 결함이면 true, 결함이 아니라 전경·상태 기록용 사진이면 false,
 "part": "주요시설" 또는 "일반시설" 또는 "부대시설" — 부재 기준(바닥판·거더·케이블·정착구·받침·교대·교각·날개벽·주탑·기초 = 주요시설,
   교면포장·신축이음·후타재·가로보·세로보·배수시설·난간·연석 = 일반시설, 옹벽·비탈면·방음벽·점검로 = 부대시설),
 "member": 부재 — 반드시 이 목록 중 하나 그대로: {members},
 "dtype": 결함유형 — 반드시 이 목록 중 하나 그대로: {types} (기록용 사진이면 "○○ 현황", 예: "교량받침 현황"),
 "new_member": 목록에 맞는 부재가 정말 없을 때만 제안할 이름(짧게, 이때 member는 ""), 아니면 null,
 "new_dtype": 목록에 맞는 결함유형이 정말 없을 때만 제안할 이름(짧게, 이때 dtype은 ""), 아니면 null,
 "cause": 원인(아래 규칙), "cause_note": 근거(아래 규칙),
 "width": 균열이면 폭 구간(mm) "0.1"·"0.2"·"0.3"·"0.5"·"1.0" 중 하나(1.0은 1mm 이상), 균열이 아니면 null,
 "count": 사진에 보이는 같은 결함 개수(정수, 보통 1),
 "note": "사진에서 본 것 한 줄(점검자 참고용)"}}
결함유형 고르는 법(교량 세부지침·3종 매뉴얼 교량·육교 체크리스트 기준):
- 균열 = 콘크리트가 한 방향으로 갈라짐, 망상균열 = 거북등처럼 그물 모양 균열(바닥판 하면·교면에 흔함), 백태 = 흰 석회 자국, 누수 = 물 흐른 자국·젖음,
  박리 = 표면 시멘트풀이 얇게 벗겨짐, 박락 = 콘크리트 조각이 떨어져 나감, 층분리 = 들떠 두드리면 빈 소리, 철근노출 = 철근이 드러남, 재료분리 = 골재가 몰려 곰보,
  파손 = 모서리·연석·난간이 깨짐, 부식 = 강재·받침·난간·배수관 녹, 도장박리 = 강재 도장이 벗겨짐, 변형 = 강재·난간이 휘거나 받침이 기울어짐,
  세굴 = 하천 기초 주변이 물에 파임, 침하 = 교대 뒤·기초가 내려앉음, 토사·이물질퇴적 = 신축이음 유간·배수구·받침 주변에 흙·낙엽이 쌓임,
  배수불량 = 배수구 막힘·물고임, 유간이상 = 신축이음 틈이 너무 좁거나 넓음, 볼트이완·탈락 = 강재 연결 볼트가 풀리거나 빠짐, 잡목식생 = 교대 주변 잡목·넝쿨.
- 기초 세굴·침하, 교각·교대 기울음, 받침 파손·이탈, 거더 단부 균열은 구조 안전에 바로 이어지니 조금이라도 보이면 note에 "진행성 확인 필요"라고 적을 것.
{cause_rule}
폭은 사진만으로는 어림이므로 보이는 굵기로 가장 가까운 구간을 고르세요(머리카락 굵기 ≈ 0.1, 연필 선 ≈ 0.3, 뚜렷이 벌어짐 ≥ 0.5)."""

GREW = """같은 결함 자리를 전회차와 이번에 찍은 사진입니다(첫째 = 전회차, 둘째 = 이번). 전회차 기록: {prev}.
JSON 객체 하나로만 답하세요(설명 없이): {{"grew": 이번이 전회차보다 커졌으면(길어짐·넓어짐·개수 늘어남) true, 아니면 false,
 "width": 균열이면 이번 폭 구간 "0.1"·"0.2"·"0.3"·"0.5"·"1.0" 중 하나, 균열이 아니면 null, "note": "달라진 점 한 줄"}}"""


def _analyze_prompt(where: str, allowed: dict, fam: str = "") -> str:
    from server.sitok.manual3 import LEAK_RULE

    if fam == "wall":
        return ANALYZE_WALL.format(where=where, members=", ".join(allowed["member"]), types=", ".join(allowed["dtype"]), cause_rule=CAUSE_RULE)
    if fam == "bridge":
        return ANALYZE_BRIDGE.format(where=where, members=", ".join(allowed["member"]), types=", ".join(allowed["dtype"]), cause_rule=CAUSE_RULE)
    return ANALYZE.format(where=where, members=", ".join(allowed["member"]), types=", ".join(allowed["dtype"]), cause_rule=CAUSE_RULE, leak_rule=LEAK_RULE)


def _text(v) -> str:
    s = str(v or "").strip()
    return "" if s.lower() in ("null", "none") else s


def _analysis(raw: dict, allowed: dict, fam: str = "") -> dict:
    """AI 답 정리 — 부재·결함유형이 목록 밖이면 비우고 "제안"(new_*)으로 돌림(점검자가 목록에서 고르거나 추가)."""
    w = _text(raw.get("width"))
    try:
        cnt = str(int(float(raw.get("count") or 1)))
    except (TypeError, ValueError):
        cnt = "1"
    out = {"is_defect": bool(raw.get("is_defect", True)), "cause": _text(raw.get("cause")), "cause_note": _text(raw.get("cause_note")),
           "width": w if w in WIDTH_BANDS else "", "count": cnt, "note": _text(raw.get("note"))}
    for k, nk in (("member", "new_member"), ("dtype", "new_dtype")):
        v, new = _text(raw.get(k)), _text(raw.get(nk))
        if v and v not in allowed[k] and not (k == "dtype" and kinds.is_record(v)):
            v, new = "", new or v
        if not v and new in allowed[k]:
            v, new = new, ""
        out[k], out[nk] = v, new
    parts = kinds.parts_of(fam)
    part = raw.get("part") if raw.get("part") in parts else ""
    out["part"] = part or kinds.default_part(out["member"], fam) or parts[-1]
    return out


@router.post("/reports/{report_id}/defects/analyze")
def analyze_new(report_id: int, file: UploadFile = File(...), floor: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """[+ 신규]에서 사진을 찍으면 — AI가 구분·부재·결함유형(목록 안에서, 없으면 제안)·원인·근거·폭 구간 초안(저장은 안 함, 점검자가 확인하고 [추가])."""
    from server.sitok import vision

    r = _require_report(db, user, report_id)
    fam = _fam(db, r)
    allowed = vocab_names(db, r.company_id, r.id, fam)
    unit = kinds.unit_label(fam)
    jpg = files.to_jpeg(file.file.read(), file.filename or "")
    try:
        raw = vision.ask_json(user.company_id, [jpg], _analyze_prompt(f"{unit}: {floor}" if floor else f"{unit} 미상", allowed, fam), writing=True)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"사진을 분석하지 못했습니다: {str(err).splitlines()[0][:150]}") from err
    a = _analysis(raw, allowed, fam)
    first = {k: a[k] for k in ("part", "member", "dtype")}
    a["guess"] = {**first, "token": learn.save_pending(jpg)}  # [추가] 때 같이 오면 결함에 붙여 교정 기록 비교(10/12)
    rows = learn.examples(db, r.company_id, first["part"], first["member"], first["dtype"]) if first["dtype"] else []
    if rows:  # 같은 추천을 점검자가 고친 기록이 있으면 그 사진들과 비교해 다시 판단(분류만 — 원인은 그대로, 사용자 10/12)
        try:
            again = learn.recheck(user.company_id, jpg, first, rows, allowed, kinds.parts_of(fam))
            b = _analysis({**raw, "part": again.get("part"), "member": again.get("member"), "dtype": again.get("dtype"),
                           "new_member": None, "new_dtype": None}, allowed, fam)
            if again.get("same_case") and b["dtype"] and (b["part"], b["member"], b["dtype"]) != (first["part"], first["member"], first["dtype"]):
                a.update({k: b[k] for k in ("part", "member", "dtype")}, new_member="", new_dtype="")
                a["learned"] = (f"회사 교정 기록 {len(rows)}건(비슷한 사진)을 보고 '{' · '.join(x for x in first.values() if x)}' → "
                                f"'{' · '.join(x for x in (b['part'], b['member'], b['dtype']) if x)}'로 바꿨습니다 — {_text(again.get('why'))}")
            else:  # 비교했지만 다른 경우 — 그대로(왜 안 바꿨는지 점검자가 알게)
                a["learned"] = f"회사 교정 기록 {len(rows)}건과 비교했지만 다른 경우라 AI 판단 그대로 — {_text(again.get('why'))}"
        except Exception:  # noqa: BLE001 — 다시 판단을 못 하면 첫 추천 그대로
            pass
    return a


@router.post("/defects/{defect_id}/analyze")
def analyze_again(defect_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """전회차 결함을 이번에 다시 찍은 뒤 — 전회차 사진과 비교해 진행 여부·이번 폭 구간 추천(저장은 안 함)."""
    from server.sitok import vision

    d, r = _require(db, user, defect_id)
    if not d.photo or not Path(d.photo).exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이번 사진을 먼저 찍으세요.")
    imgs = [Path(d.prev_photo).read_bytes()] if d.prev_photo and Path(d.prev_photo).exists() else []
    prev = ", ".join(f"{k} {v}" for k, v in (d.prev or {}).items() if k in ("결함유형", "개수", "폭", "길이") and v) or "없음"
    try:
        if imgs:
            raw = vision.ask_json(user.company_id, imgs + [Path(d.photo).read_bytes()], GREW.format(prev=prev), writing=True)
            w = _text(raw.get("width"))
            return {"grew": bool(raw.get("grew")), "width": w if w in WIDTH_BANDS else "", "note": _text(raw.get("note"))}
        fam = _fam(db, r)
        allowed = vocab_names(db, r.company_id, r.id, fam)
        a = _analysis(vision.ask_json(user.company_id, [Path(d.photo).read_bytes()], _analyze_prompt(f"{kinds.unit_label(fam)}: {d.floor}", allowed, fam), writing=True), allowed, fam)
        return {"grew": None, "width": a["width"], "note": a["note"]}
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"사진을 분석하지 못했습니다: {str(err).splitlines()[0][:150]}") from err
