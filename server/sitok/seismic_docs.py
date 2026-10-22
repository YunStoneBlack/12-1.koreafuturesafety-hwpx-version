"""내진성능평가 서류 읽기(2026-10-21 사용자 — 별도 용역: 계약서·건축물대장·과업지시서·지반조사보고서 등에서 따오기).

- 용역계약서(나라장터 PDF, 글자 있음): contract_pdf(서류 자동화 것) + 계약방법·공동도급·용역기간 날수·발주처(두 줄로 꺾인 기관명).
- 건축물대장(정부24 PDF, 글자 있음): 명칭·주소·면적·구조·용도·층수·높이·지붕·사용승인일·내진설계 적용 여부·층별 현황·변동사항.
  글자 없는(스캔) 대장이면 빈 값 — 화면에서 직접.
- 지반조사보고서(외주 PDF, 견본 지오건설품질연구원 102쪽): 시추공(BH-n)마다 기반암 깊이·전단파속도·지반등급(DOWN HOLE TEST SHEET, KDS 17 10 00:2024 줄),
  적용심도(Result Analysis 합계), 조사위치도 그림, 사진대지 사진(그림 아래 설명 칸 글로 짝 — 시추전경·표준관입시험·시험기구설치·압축파타격·폐공전·폐공후),
  결과 표 그림(Result Analysis 쪽 위쪽). 10/21 사용자 "자동으로 찾고 확인 화면에서 바꾸기"로 정함 — 못 찾은 칸은 비우고 알림.
- 최소 조사 수량(과업지시서 <표 3-1> = 매뉴얼 3.2.2): 조사단위 = 층(지하 + 지상, 증축·익스팬션 따로는 사람이 고침).
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from server.sitok.report_build import _n

GROUND_SLOTS = (("drill", "시추전경", ("시추전경",)), ("spt", "표준관입시험 전경", ("표준관입시험",)), ("setup", "시험기구 설치", ("시험기구설치",)),
                ("pwave", "압축파 타격", ("압축파타격",)), ("before", "폐공 전 전경", ("폐공전",)), ("after", "폐공 후 전경", ("폐공후",)))


def _date(s: str) -> datetime.date | None:
    m = re.search(r"(\d{4})\s*[./\-년]\s*(\d{1,2})\s*[./\-월]\s*(\d{1,2})", s or "")
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _num(s: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s or "")
    return float(m.group().replace(",", "")) if m else None


def _plain(pdf: Path) -> str:
    import pymupdf

    with pymupdf.open(pdf) as d:
        return "\n".join(pg.get_text() for pg in d)


# ---------- 용역계약서 ----------
def read_contract(pdf: Path) -> dict:
    """{title, client, amount, contract_no, contract_date, start_date, end_date, days, method, joint, manager, phone} — 못 읽으면 빈 값."""
    from server.contract_docs import contract_pdf as C

    text = C.read_text(pdf)
    out = C.parse_text(text)
    raw = _plain(pdf)  # pymupdf 글 — 줄로 나뉜 칸(두 줄 기관명)
    m = re.search(r"<수요기관>\s*기\s*관\s*명\s*([^\n]+(?:\n(?![주전담F])[^\n]+)?)", raw) or re.search(r"기관명:\s*([^\n]+\n?[^\n:]*?)\n계약관", raw)
    client = re.sub(r"\s", "", m.group(1)) if m else out.get("client") or ""
    client = re.sub(r"^.+?교육청(?=.+교육지원청$)", "", client)  # "경기도교육청경기도동두천양주교육지원청" → 견본처럼 지원청만
    method = re.search(r"계약방법\s*:\s*(\S+)", text)
    joint = re.search(r"공동도급방식\s*:\s*(\S+)", text)
    days = re.search(r"용역기간\s*:.*?총차\s*(\d+)\s*일", text) or re.search(r"용역기간\s*:.*?(\d+)\s*일", text)
    title = (out.get("title") or "").strip()
    return {"title": title, "client": client, "amount": out.get("amount"), "contract_no": out.get("contract_no") or "",
            "contract_date": out.get("contract_date"), "start_date": out.get("start_date"), "end_date": out.get("end_date"),
            "days": int(days.group(1)) if days else None, "method": method.group(1) if method else "",
            "joint": joint.group(1) if joint else "", "manager": out.get("client_manager") or "", "phone": out.get("client_phone") or ""}


# ---------- 건축물대장 ----------
_FLOOR_ROW = re.compile(r"^(주|부)\s+(지하?\d+층?|지\d+|\d+층|옥탑\d*층?|지상\d+층)\s+(\S*구조)\s+(\S+)\s+([\d,]+(?:\.\d+)?)(?=\s|$)")


def _addr(s: str) -> str:
    """"경기도양주시 삼숭로38번길112" → "경기도 양주시 삼숭로38번길 112"(시·도·시군구·도로명·번호 사이 띄움)."""
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"^(.+?(?:특별시|광역시|특별자치시|특별자치도|도))", r"\1 ", s)
    s = re.sub(r"^(\S+ )(.+?[시군])(?=\S)", r"\1\2 ", s)
    s = re.sub(r"([시군] )(.+?구)(?=\S+(?:로|길))", r"\1\2 ", s)
    s = re.sub(r"((?:로|길))(\d+(?:-\d+)?)$", r"\1 \2", s)
    return s.strip()


def read_register(pdf: Path) -> dict:
    """건축물대장 → {name, address, lot_address, site_area, total_area, building_area, structure, use, below, above, height, roof,
    permit_date, start_date, approval_date, seismic_design, floors: [{kind, floor, structure, use, area}], changes: [{date, text}], text_ok}."""
    from server.contract_docs import contract_pdf as C

    t = C.read_text(pdf)
    raw = _plain(pdf)
    out: dict = {"text_ok": len(_n(t)) > 200}
    lines = [x.strip() for x in t.splitlines()]
    for i, ln in enumerate(lines):
        if not out.get("name") and re.search(r"\d+호/\d+가구/\d+세대", ln):
            out["name"] = re.sub(r"\s*\d+호/\d+가구/\d+세대.*$", "", ln).strip()
        if not out.get("address") and ln.startswith("대지위치") and "도로명주소" in ln and i + 1 < len(lines):
            v = lines[i + 1]
            m = re.findall(r"([가-힣]+(?:도|특별시|광역시|특별자치시)\s?[가-힣]+[시군구]\s?(?:[가-힣]+구\s?)?[가-힣0-9]+(?:로|길)\s?\d+(?:-\d+)?)", v)
            if m:
                out["address"] = _addr(m[-1])
            lot = re.match(r"(.+?(?:동|리|가))\s", v)
            out["lot_address"] = lot.group(1) if lot else ""
        if ln.startswith("※대지면적") and i + 1 < len(lines):
            a = re.findall(r"([\d,]+(?:\.\d+)?)\s*㎡", lines[i + 1])
            if a:
                out["site_area"] = _num(a[0])
            if len(a) > 1:
                out["total_area"] = _num(a[1])
        if ln.startswith("건축면적") and "주구조" in ln and i + 1 < len(lines):
            v = lines[i + 1]
            a = re.findall(r"([\d,]+(?:\.\d+)?)\s*㎡", v)
            if a:
                out["building_area"] = _num(a[0])
            m = re.search(r"(\S+구조)\s+(\S+)", v)
            if m:
                out["structure"], out["use"] = m.group(1), m.group(2)
            m = re.search(r"지하\s*:\s*(\d+)\s*층", v)
            out["below"] = int(m.group(1)) if m else 0
            m = re.search(r"지상\s*:\s*(\d+)\s*층", v)
            if m:
                out["above"] = int(m.group(1))
        if ln.startswith("※건폐율") and i + 1 < len(lines):
            m = re.search(r"([\d.]+)\s*m\s+(\S+)", lines[i + 1])
            if m:
                out["height"], out["roof"] = float(m.group(1)), m.group(2) if m.group(2) != "㎡" else ""
        m = _FLOOR_ROW.match(ln)
        if m:
            out.setdefault("floors", []).append({"kind": m.group(1), "floor": m.group(2), "structure": m.group(3), "use": m.group(4), "area": _num(m.group(5))})
    for key, label in (("permit_date", "허가일"), ("start_date", "착공일"), ("approval_date", "사용승인일")):
        i = t.find(label)
        d = _date(t[i:i + 400]) if i >= 0 else None
        out[key] = d
    m = re.search(r"내진설계적용\s*여부[^\n]*\n\s*(\S+)", t)
    out["seismic_design"] = m.group(1) if m and m.group(1) in ("적용", "비적용") else ""
    # 변동사항 — pymupdf 글(칸 순서대로, 띄어쓰기는 없음): 날짜 줄 + 내용 줄(여러 줄)
    i, j = raw.find("변동내용및원인"), raw.find("-이하여백-", raw.find("변동내용및원인") + 1)
    seg = raw[raw.find("변동내용및원인", i + 1) + 7:j] if i >= 0 and j > i else ""
    rows: list[dict] = []
    for part in [x.strip() for x in seg.splitlines() if x.strip()]:
        if re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}\.?", part):
            rows.append({"date": _date(part), "text": ""})
        elif rows:
            rows[-1]["text"] += part
    out["changes"] = [r for r in rows if r["text"] and not re.search(r"인허가시기|허가일|착공일|사용승인일", r["text"])]
    return out


REGISTER_PROMPT = """첨부한 PDF는 한국 건축물대장(일반건축물대장 갑·을 등, 스캔일 수 있음)입니다. 다음 값을 읽어 JSON 하나로만 답하세요(못 읽은 칸은 빈 글 또는 null):
{"name": "명칭", "address": "도로명주소(괄호 동 이름 빼고)", "lot_address": "대지위치", "site_area": 대지면적 숫자, "total_area": 연면적 숫자, "building_area": 건축면적 숫자,
 "structure": "주구조", "use": "주용도", "below": 지하 층수 숫자, "above": 지상 층수 숫자, "height": 높이 m 숫자, "roof": "지붕",
 "permit_date": "허가일 YYYY-MM-DD", "start_date": "착공일 YYYY-MM-DD", "approval_date": "사용승인일 YYYY-MM-DD", "seismic_design": "적용 또는 비적용",
 "floors": [{"kind": "주 또는 부", "floor": "지1·1층·옥탑1층처럼", "structure": "구조", "use": "용도", "area": 면적 숫자}],
 "changes": [{"date": "YYYY-MM-DD", "text": "변동내용 및 원인"}]}"""


def read_register_ai(pdf: Path, company_id: int) -> dict:
    """글자 없는(스캔) 건축물대장 → read_register와 같은 모양(AI, 약 30원 — 건 화면 [🤖 AI로 읽기])."""
    from server.sitok import reader

    d = reader._ask(pdf, REGISTER_PROMPT, company_id)
    num = lambda v: _num(str(v)) if v not in (None, "") else None  # noqa: E731
    out = {"text_ok": True, "ai": True}
    for k in ("name", "lot_address", "structure", "use", "roof"):
        out[k] = str(d.get(k) or "").strip()
    out["address"] = _addr(str(d.get("address") or ""))
    for k in ("site_area", "total_area", "building_area", "height"):
        out[k] = num(d.get(k))
    for k in ("below", "above"):
        v = num(d.get(k))
        out[k] = int(v) if v is not None else (0 if k == "below" else None)
    for k in ("permit_date", "start_date", "approval_date"):
        out[k] = _date(str(d.get(k) or ""))
    sd = str(d.get("seismic_design") or "").strip()
    out["seismic_design"] = sd if sd in ("적용", "비적용") else ""
    out["floors"] = [{"kind": str(x.get("kind") or "주"), "floor": str(x.get("floor") or ""), "structure": str(x.get("structure") or ""),
                      "use": str(x.get("use") or ""), "area": num(x.get("area"))} for x in d.get("floors") or [] if isinstance(x, dict)]
    out["changes"] = [{"date": _date(str(x.get("date") or "")), "text": str(x.get("text") or "").strip()} for x in d.get("changes") or [] if isinstance(x, dict) and x.get("text")]
    return {k: v for k, v in out.items() if v not in (None, "") or k in ("floors", "changes", "below")}


# ---------- 최소 조사 수량(매뉴얼 3.2.2 <표 3-1> — 10/22 형 "조사수량 산출기준") ----------
MEMBER_KINDS = ("보", "기둥", "벽체")  # 부재 규격 종별
REBAR_KINDS = ("보", "기둥", "보-기둥 접합부", "벽체")  # 철근배근 상태조사 종별(<표 3-1> 비고)


def survey_units(f) -> int:
    """조사단위 수 — 건물 칸 값(사람이 고침), 없으면 지상 층수(형 "단위는 층수" — 삼숭초 지하1·지상5 = 5, 견본 "교사동(5개층)"), 그것도 없으면 지하 + 지상."""
    reg = (f.ledger or {}).get("register") or {}
    try:
        v = int(float(reg.get("survey_units") or 0))
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else int(f.floors_above or 0) or int((f.floors_below or 0) + (f.floors_above or 0))


def sample_floors(f) -> list[int]:
    """조사단위 층(표본 층) — 지상 1층부터 단위 수만큼, 단위가 지상 층수보다 많으면 지하 1층부터 더함(아래 → 위 차례)."""
    below, above = int(f.floors_below or 0), int(f.floors_above or 0)
    u = survey_units(f)
    floors = list(range(1, above + 1))[:u]
    if u > len(floors):
        floors = [-b for b in range(min(below, u - len(floors)), 0, -1)] + floors
    return floors or [1]


def member_plan(f, saved: dict | None = None) -> dict:
    """부재 단면 칸 수 {"층|부재": 개수} — 표본 층 × 종별(보·기둥·벽체) × 3(도면 없으면 9) 위에 저장한 값(조사단위를 늘리면 새 층은 기본 칸)."""
    per = 3 if has_drawings(f) else 9
    return {**{f"{n}|{k}": per for n in sample_floors(f) for k in MEMBER_KINDS}, **(saved or {})}


def masonry_plan(f, saved: dict | None = None) -> dict:
    """층마다 조적 칸 수 {"층": 개수} — 표본 층 × 2개소(<표 3-1> 조사단위별 2개소 이상) 위에 저장 값."""
    return {**{str(n): 2 for n in sample_floors(f)}, **(saved or {})}


def has_drawings(f) -> bool:
    """도면 유무 — 건물 칸 값(보유·미보유), 비우면 구조도면·구조 일람표 칸에 파일이 있으면 보유."""
    v = ((f.ledger or {}).get("register") or {}).get("drawings")
    if v in ("보유", "미보유"):
        return v == "보유"
    return bool((f.drawings or {}).get("struct") or (f.drawings or {}).get("schedule"))


def min_counts(units: int, grade: str = "특등급", drawings: bool = True) -> dict:
    """조사단위 수 → {member, rebar, core, boring, masonry} 최소 개소 + how(계산식) — 부재 규격 = 3종 × 3개소(도면 없으면 9) × 단위,
    철근배근 = 4종 × 3개소 × 단위(도면 없어도 3개소), 코어 = max(단위, 6), 시추 = 특등급 2(그 밖 1), 조적 = 단위 × 2."""
    u = max(int(units or 0), 0)
    per = 3 if drawings else 9
    boring = 2 if grade == "특등급" else 1
    return {"member": u * len(MEMBER_KINDS) * per, "rebar": u * len(REBAR_KINDS) * 3, "core": max(u, 6), "boring": boring, "masonry": u * 2,
            "how": {"member": f"{len(MEMBER_KINDS)}종(보·기둥·벽체) × {per}개소{'' if drawings else '(도면 없음)'} × {u}단위",
                    "rebar": f"{len(REBAR_KINDS)}종(보·기둥·보-기둥 접합부·벽체) × 3개소 × {u}단위", "core": f"max({u}단위, 6)",
                    "boring": "특등급 2개소" if boring == 2 else "그 밖 등급 1개소", "masonry": f"{u}단위 × 2개소"}}


# ---------- 지반조사보고서 ----------
def _bh(s: str) -> str | None:
    m = re.search(r"BH\s*[—–\-]\s*(\d+)", s or "")
    return f"BH-{m.group(1)}" if m else None


def read_ground(pdf: Path, out_dir: Path) -> dict:
    """지반조사보고서 PDF → {holes: [{bh, depth, vs, cls, apply_depth, photos: {slot: png}, result: png}], map: png, warn: [...]}.
    그림은 out_dir에 PNG로(사진은 원본 그림, 위치도·결과 표는 그 자리를 200dpi로 잘라서)."""
    import pdfplumber
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    holes: dict[str, dict] = {}
    warn: list[str] = []
    res = {"map": "", "warn": warn}

    def hole(bh: str) -> dict:
        return holes.setdefault(bh, {"bh": bh, "depth": "", "vs": None, "cls": "", "apply_depth": None, "photos": {}, "result": "", "extra": []})

    with pymupdf.open(pdf) as doc, pdfplumber.open(str(pdf)) as pl:
        for pno in range(doc.page_count):
            pg = doc[pno]
            flat = _n(pg.get_text())
            # 값 — DOWN HOLE TEST SHEET(새 기준 KDS 17 10 00 줄을 먼저, 없으면 앞 줄)
            if "DOWNHOLETESTSHEET" in flat.upper():
                t = pl.pages[pno].extract_text(x_tolerance=1.5) or ""
                bh = _bh(t)
                if bh:
                    h = hole(bh)
                    part = t[t.find("KDS 17 10 00"):] if "KDS 17 10 00" in t else t
                    m = re.search(r"기반암\s*깊이\s*(\S+\s*이하|\S+)", part)
                    h["depth"] = m.group(1) if m else h["depth"]
                    m = re.search(r"Vs\)?_?m/sec\s*([\d.]+)", part)
                    h["vs"] = float(m.group(1)) if m else h["vs"]
                    m = re.search(r"지반등급\s*(S\d)", part)
                    h["cls"] = m.group(1) if m else h["cls"]
            # 결과 표 — Result Analysis 쪽 위쪽(제목부터 "★" 주석 줄 또는 "지반분류 환산Vs" 줄까지)
            if "RESULTANALYSIS" in flat.upper():
                t = pl.pages[pno].extract_text(x_tolerance=1.5) or ""
                bh = _bh(t)
                m = re.search(r"합계\s*([\d.]+)", t)
                if bh and m and hole(bh)["apply_depth"] is None:  # 적용심도 = 합계 줄(결과 쪽 둘째 장에 있음)
                    hole(bh)["apply_depth"] = float(m.group(1))
                if bh and not hole(bh)["result"]:
                    h = hole(bh)
                    words = pg.get_text("words")
                    top = min((w[1] for w in words if "하향식" in w[4] or "Down" in w[4]), default=pg.rect.y0 + 20) - 12
                    star = [w for w in words if w[4].startswith("★")]
                    if star:
                        y = max(w[3] for w in words if abs(w[1] - star[0][1]) < 30 and w[1] >= star[0][1] - 2) + 8
                    else:
                        cand = [w[3] for w in words if "환산" in w[4] or "합계" in w[4]]
                        y = (max(cand) + 10) if cand else pg.rect.y0 + pg.rect.height * 0.45
                    clip = pymupdf.Rect(pg.rect.x0 + 20, max(top, pg.rect.y0), pg.rect.x1 - 20, min(y, pg.rect.y1))
                    name = out_dir / f"result_{bh}.png"
                    pg.get_pixmap(dpi=200, clip=clip).save(name)
                    h["result"] = name.name
            # 사진대지 — 사진마다 아래 설명 칸 글(공번·공정)
            if "사진대지" in flat:
                words = pg.get_text("words")
                for k, im in enumerate(pg.get_images(full=True)):
                    for r in pg.get_image_rects(im[0]):
                        if r.width < 100 or r.height < 60:
                            continue
                        below = [w for w in words if r.x0 - 5 <= (w[0] + w[2]) / 2 <= r.x1 + 5 and r.y1 < w[1] < r.y1 + 75]
                        txt = " ".join(w[4] for w in sorted(below, key=lambda w: (round(w[1]), w[0])))
                        bh = _bh(txt)
                        if not bh:
                            continue
                        step = re.sub(r"[\d.]", "", re.sub(r"조사일자|공번|공정|시험위치|BH[—–\-]\d+", "", _n(txt)))  # 설명 칸 = 머리 + 날짜·공번·공정(글 순서가 섞여 숫자는 다 뺌)
                        name = out_dir / f"photo_{bh}_p{pno + 1}_{k}.png"
                        pg.get_pixmap(dpi=170, clip=r).save(name)
                        h = hole(bh)
                        h["extra"].append({"file": name.name, "caption": step, "page": pno + 1})
                        for slot, _label, keys in GROUND_SLOTS:
                            if slot not in h["photos"] and any(step == key for key in keys):
                                h["photos"][slot] = name.name
            # 조사위치도 — "조사위치도"가 든 쪽(제목만이면 다음 쪽)의 가장 큰 그림 자리
            if not res["map"] and "조사위치도" in flat and "목차" not in flat[:40] and "부록1." not in flat:
                for q in (pno, pno + 1):
                    if q >= doc.page_count:
                        break
                    p2 = doc[q]
                    rects = [r for im in p2.get_images(full=True) for r in p2.get_image_rects(im[0])
                             if r.width * r.height > p2.rect.width * p2.rect.height * 0.15]
                    if rects:
                        r = max(rects, key=lambda r: r.width * r.height)
                        name = out_dir / "map.png"
                        p2.get_pixmap(dpi=200, clip=r).save(name)
                        res["map"] = name.name
                        break
    res["holes"] = [holes[k] for k in sorted(holes, key=lambda b: int(b.split("-")[1]))]
    if not res["holes"]:
        warn.append("시추공(BH-1 등)을 못 찾았습니다 — 값과 사진은 직접 넣어 주세요")
    if not res["map"]:
        warn.append("조사위치도 그림을 못 찾았습니다")
    for h in res["holes"]:
        miss = [label for slot, label, _ in GROUND_SLOTS if slot not in h["photos"]]
        if miss:
            warn.append(f"{h['bh']} 사진 못 찾음: {'·'.join(miss)}")
        if h["vs"] is None:
            warn.append(f"{h['bh']} 전단파속도를 못 읽었습니다")
        if not h["result"]:
            warn.append(f"{h['bh']} 결과 표(Result Analysis)를 못 찾았습니다")
    return res


GROUND_NAMES = {"S1": "암반 지반", "S2": "얕고 단단한 지반", "S3": "얕고 연약한 지반", "S4": "깊고 단단한 지반", "S5": "깊고 연약한 지반",
                "S6": "부지 고유의 특성평가가 필요한 지반"}


def ground_phrase(holes: list[dict]) -> str:
    """"얕고 단단한 지반인 S2 지반(기반암 깊이 1~20이하, 전단파속도 BH-1 : 305.9m/s, BH-2 : 569.9m/s)" — 2.5 (3)·요약 지반 분석 글."""
    if not holes:
        return ""
    cls = holes[0].get("cls") or "S2"
    depth = (holes[0].get("depth") or "").replace(" ", "")
    vs = ", ".join(f"{h['bh']} : {h['vs']:g}m/s" for h in holes if h.get("vs") is not None)
    return f"{GROUND_NAMES.get(cls, '')}인 {cls} 지반(기반암 깊이 {depth}, 전단파속도 {vs})"


def ground_sentence(holes: list[dict]) -> str:
    """2.5 (3) 문장 — "지반조사결과를 토대로 얕고 단단한 지반인 S2 지반(기반암 깊이 1~20.0이하, 전단파속도 BH-1 : 305.9m/s, BH-2 : 569.9m/s)을 적용함."."""
    if not holes:
        return ""
    cls = holes[0].get("cls") or "S2"
    names = {"S1": "암반 지반", "S2": "얕고 단단한 지반", "S3": "얕고 연약한 지반", "S4": "깊고 단단한 지반", "S5": "깊고 연약한 지반", "S6": "부지 고유의 특성평가가 필요한 지반"}
    depth = (holes[0].get("depth") or "").replace(" ", "")
    vs = ", ".join(f"{h['bh']} : {h['vs']:g}m/s" for h in holes if h.get("vs") is not None)
    return f"지반조사결과를 토대로 {names.get(cls, '')}인 {cls} 지반(기반암 깊이 {depth}, 전단파속도 {vs})을 적용함."


def _selfcheck() -> None:
    assert _addr("경기도양주시 삼숭로38번길112") == "경기도 양주시 삼숭로38번길 112", _addr("경기도양주시 삼숭로38번길112")
    assert _addr("경기도 양주시 삼숭로38번길 112") == "경기도 양주시 삼숭로38번길 112"
    m = min_counts(5)  # 형 10/22 삼숭초: 규격 3×3×5 = 45(도면 있음, 없으면 3×9×5 = 135), 철근 4×3×5 = 60, 코어 6
    assert (m["member"], m["rebar"], m["core"], m["boring"], m["masonry"]) == (45, 60, 6, 2, 10), m
    assert min_counts(5, drawings=False)["member"] == 135 and min_counts(8, "1등급")["core"] == 8 and min_counts(8, "1등급")["boring"] == 1
    assert _bh("BH—1 시추전경") == "BH-1" and _date("2005.10.28.") == datetime.date(2005, 10, 28)
    assert "S2 지반(기반암 깊이 1~20이하, 전단파속도 BH-1 : 305.9m/s)" in ground_sentence([{"bh": "BH-1", "cls": "S2", "depth": "1~20 이하", "vs": 305.9}])


if __name__ == "__main__":
    _selfcheck()
    print("ok")
