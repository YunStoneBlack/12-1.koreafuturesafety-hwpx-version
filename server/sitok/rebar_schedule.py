"""구조 일람표 부재 목록(2026-10-21 사용자·민재형 — 내진성능평가 철근탐사) — 시설물 도면 "구조 일람표"(drawings.schedule)를 쪽마다 AI가 읽어
기둥·보·벽체 칸(부호 × 층 × 위치)마다 치수·주근·대근·늑근·벽근을 시설물에 저장(ledger["rebar_schedule"]). 철근탐사 화면이 이 목록으로 설계값을 채움.

10/21 시험(설계사가 다른 일람표 17개, 견본 `시특법 견본\\정밀\\기둥보벽일람표`): 글자 값은 CAD·책 스캔·손그림 옛 스캔까지 거의 다 맞음,
단면 그림 점 개수는 AI가 못 믿게 셈(큰 기둥은 적게, 스캔은 모서리 갈고리와 헷갈림) → 정한 방식(사용자 "응 시작"):
- 글자 값 = AI 자동. 보 하부근이 한 줄이면 글자 총수 그대로(확인 필요 없음).
- 기둥 변별(단변·장변) 점 개수, 두 줄 하부근의 아래 줄 개수 = AI 제안 + 건물마다 부재 종류별 한 번 사람이 단면 그림 보고 확인(confirmed).
- 검산: 기둥 2 × (단변 + 장변) − 4 = 주근 총수(어긋나면 표시).
쪽마다 AI 한 번(claude 모델·회사 키 = server.sitok.vision과 같음), 쪽 전체 + 4등분 확대(3136px 렌더, schedule_read._tiles). 시험 비용 쪽당 약 120원.
단면 그림 위치 box(쪽 화면 기준 백분율)를 같이 받아 확인 화면에 잘라 보여 줌(get_pixmap clip = 화면 좌표 — 회전된 쪽도 그대로, 10/21 시험).
"""
from __future__ import annotations

import datetime
import io
import json
import re
import uuid
from pathlib import Path

KINDS = ("기둥", "보", "벽체")
MAX_PAGES = 20  # 한 번에 읽을 쪽(일람표만 모은 PDF 기준 충분)

PROMPT = """아래 그림은 건축 구조도면 일람표 한 쪽입니다(첫 그림 = 쪽 전체, 나머지 4장 = 4등분 확대, 서로 조금 겹침).
기둥·보·벽체(옹벽 포함) 일람표의 칸마다 값을 읽어 주세요. 설계사마다 표 모양과 이름이 다릅니다:
대근 = 띠철근 = HOOP = TIE, 보조대근은 hoop_aux에 따로, 늑근 = STIRRUP, 단부 = END·END(BOTH)·BOTH-END·END(INT.)·END(EXT.)·양단부, 중앙부 = CENTER·CEN.·MID, ALL = 전구간.

규칙
- 칸 하나(부호 × 층 × 위치)가 한 줄. 빈 칸·대각선으로 지운 칸은 넣지 말 것. 층 칸이 화살표·"상동"·"〃"로 "다른 층과 같음"을 나타내면 그 층도 줄을 만들고 값은 같게, same_as에 기준 층.
- 부호 칸이 여러 칸에 걸쳐 합쳐져 있으면 그 아래 칸들만 그 부호입니다(옆 부호 칸으로 넘기지 말 것).
- 기둥: size "b×h"(mm, 원형 "∅500"), main = 주근 글자 그대로("12-HD25"), short_side·long_side = 단면 그림에서 짧은 변·긴 변 한 변에 놓인 철근 점 개수(모서리 포함, 정사각형이면 둘 다, 원형·이형이면 null),
  hoop = 대근 글자("HD10@300"), hoop_end = 단부(L/4구간·단부 등) 대근 글자(없으면 ""), hoop_aux = 보조대근 글자(없으면 "").
- 보: size "b×h", position(단부·중앙부·전체·단부(내부)·단부(외부) — 칸 머리 글에 맞게), top = 상부근 글자, bottom = 하부근 글자, bottom_row = 단면 그림 맨 아래 줄 점 개수, bottom_layers = 하부근 줄 수(1 또는 2), stirrup = 늑근 글자.
- 벽체: thickness = 그 층 벽 두께(mm 숫자), vertical = 수직근 글자, horizontal = 수평근 글자(외측·내측이 따로면 "HD10@300 / HD10@300").
- floors는 도면 표기 그대로("1층", "2~5", "PIT층/지하층", "R", "6F 이상"), marks는 칸의 부호 전부(["C1","C2"]).
- box = 그 칸의 단면 그림(기둥·보, 벽체는 그 줄)을 감싸는 상자 — 첫 그림(쪽 전체) 기준 백분율 [x0, y0, x1, y1](0~100, 왼쪽 위 0,0), 조금 여유 있게.
- 흐려서 확실하지 않은 값은 읽은 대로 쓰고 그 필드 이름을 unsure 배열에.
JSON만 답하세요:
{{"sheet": "기둥|보|벽체|옹벽|슬래브|섞임", "items": [{{"kind": "기둥", "marks": ["C1","C2"], "floors": "1층", "position": "", "size": "400×500", "main": "10-HD19", "short_side": 3, "long_side": 4, "hoop": "HD10@300", "hoop_end": "", "hoop_aux": "", "same_as": "", "box": [10.2, 20.5, 14.0, 26.1], "unsure": []}}, …]}}
보·벽체 줄은 그 부재 필드만. 슬래브만 있는 쪽이면 items는 빈 배열.
{text}"""

FIELDS = {
    "기둥": ("size", "main", "short_side", "long_side", "hoop", "hoop_end", "hoop_aux"),
    "보": ("size", "position", "top", "bottom", "bottom_row", "bottom_layers", "stirrup"),
    "벽체": ("thickness", "vertical", "horizontal"),
}
INT_FIELDS = ("short_side", "long_side", "bottom_row", "bottom_layers", "thickness")


# ---------- 글자 도우미 ----------
def bar_count(text) -> int | None:
    """"12-HD25" → 12, "3-SHD22" → 3, "HD22-2EA"·"HD22 - 12EA"·"4EA" → 2·12·4(10/27 덕계고 도면 — 굵기 먼저, 개수 뒤 EA). 없으면 None."""
    t = str(text or "")
    m = re.match(r"\s*(\d+)\s*[-−–‐]", t) or re.search(r"(\d+)\s*EA", t, re.I)
    return int(m.group(1)) if m else None


def spacing(text) -> int | None:
    """"HD10@300"·"2-HD10@200"·"HD16+19 @100"·"HD10@300 / HD10@300" → 간격 mm(첫 값)."""
    m = re.search(r"@\s*(\d{2,4})", str(text or ""))
    return int(m.group(1)) if m else None


def _int(v):
    try:
        n = int(round(float(v)))
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


FLOOR_TOP = 999  # 지붕·옥탑·R·"이상"


def floor_range(text: str) -> tuple[int, int] | None:
    """도면 층 표기 → (아래층, 위층) 정수(지하 = 음수, 지붕·옥탑 = 999). "1~4"·"2~5층"·"지하6층~지하2층"·"B1F~2F"·"6F 이상"·"PIT층/지하층"·"R"·"옥탑층".
    모르면 None(철근탐사 화면은 그 부재를 모든 층 후보로)."""
    t = re.sub(r"\s", "", str(text or "")).upper()
    if not t:
        return None
    if re.fullmatch(r"(R|RF|ROOF|지붕층?|옥탑층?|PH|PHF|옥상층?)", t):
        return FLOOR_TOP, FLOOR_TOP
    if "PIT" in t or t in ("지하층", "지하"):
        return -9, -1

    def one(s: str) -> int | None:
        s = s.replace("층", "").replace("F", "")
        m = re.fullmatch(r"(?:지하|B)(\d+)", s)
        if m:
            return -int(m.group(1))
        m = re.fullmatch(r"(?:지상)?(\d+)", s)
        if m:
            return int(m.group(1))
        if s in ("R", "지붕", "옥탑", "옥상", "PH"):
            return FLOOR_TOP
        return None

    up = "이상" in t
    t = t.replace("이상", "").replace("이하", "")
    parts = re.split(r"[~∼\-]", t, maxsplit=1)
    if len(parts) == 2:
        a, b = one(parts[0]), one(parts[1])
        if a is None or b is None:
            return None
        return (min(a, b), max(a, b))
    a = one(t)
    if a is None:
        return None
    return (a, FLOOR_TOP) if up else (a, a)


def survey_floors(below: int, above: int) -> list[int]:
    """화면에 층별 부호(at)를 줄 층 — 지하 아래층부터 지상 위층 + 지붕."""
    return [-b for b in range(below or 0, 0, -1)] + list(range(1, (above or 0) + 1)) + [FLOOR_TOP]


def floor_label(n: int) -> str:
    return "지붕층" if n >= FLOOR_TOP else (f"지하{-n}층" if n < 0 else f"지상{n}층")


# ---------- 부호 앞 층 표시(10/28 사용자 "1-5G1A는 1층에선 1G1A로, PG1은 지하·RG1은 지붕으로 나눠서", "n은 모든 층 — R-nG1은 지붕과 모든 층의 G1") ----------
_TOK = r"PHR|PH|R|P|B\d+|n|\d+"
_SCOPED = re.compile(rf"^(?P<a>{_TOK})(?:(?P<sep>[-~])(?P<b>{_TOK}))?(?P<base>[A-Z]{{1,3}}\d.*)$")
ALL_LO = -99  # n = 모든 층(지하 포함)


def mark_scope(mark: str) -> dict | None:
    """부호 앞 층 표시 → {"lo","hi","pit","top","base","label","toks"} — 층 표시가 없으면(C1·G1·B1·5nC1) None.
    1-5G1A·4~1G1A = 범위, R~1G2 = 1층~지붕, R-nG1 = 지붕 + 모든 층, PG1 = 지하(PIT), RG1·PHRG2 = 지붕·옥탑지붕, 2G6·B1G1 = 그 층."""
    m = _SCOPED.match(str(mark or "").strip())
    if not m:
        return None
    toks = [m["a"]] + ([m["b"]] if m["b"] else [])
    floors, pit, top, every = [], False, False, False
    for t in toks:
        if t == "n":
            every = True
        elif t == "P":
            pit = True
        elif t in ("R", "PH", "PHR"):
            top = True
        elif t.startswith("B"):
            floors.append(-int(t[1:]))
        else:
            floors.append(int(t))
    if every:
        lo, hi = ALL_LO, FLOOR_TOP - 1
    elif floors and m["sep"] and top and len(floors) == 1:  # R~1 = 1층~지붕
        lo, hi = floors[0], FLOOR_TOP - 1
    elif floors:
        lo, hi = min(floors), max(floors)
    else:
        lo = hi = None
    roof = "옥탑지붕" if "PHR" in toks else "지붕"
    if every:
        label = "모든 층" + (f"·{roof}" if top else "")
    elif lo is not None:
        lab = lambda n: f"지하{-n}" if n < 0 else str(n)  # noqa: E731
        label = (lab(lo) if lo == hi else f"{lab(lo)}~{lab(hi) if hi < FLOOR_TOP - 1 else '지붕'}") + ("" if lo != hi or hi >= FLOOR_TOP - 1 else "층")
        if top and hi < FLOOR_TOP - 1:
            label += f"·{roof}"
    else:
        label = "·".join(x for x in (("지하" if pit else ""), (roof if top else "")) if x)
    return {"lo": lo, "hi": hi, "pit": pit, "top": top, "base": m["base"], "label": label, "toks": toks}


def scope_has(sc: dict, floor: int) -> bool:
    if floor >= FLOOR_TOP:
        return sc["top"] or (sc["hi"] is not None and sc["hi"] >= FLOOR_TOP - 1 and "R" in sc["toks"])
    if floor < 0 and sc["pit"]:
        return True
    return sc["lo"] is not None and sc["lo"] <= floor <= sc["hi"] and floor != 0


def floor_mark(mark: str, floor: int) -> str | None:
    """그 층에서 쓸 부호 — 1-5G1A → 1층 "1G1A", R~1G2 → 지붕 "RG2", PG1 → 지하 "PG1". 층 표시가 없으면 그대로, 그 층이 아니면 None."""
    sc = mark_scope(mark)
    if sc is None:
        return mark
    if not scope_has(sc, floor):
        return None
    if floor >= FLOOR_TOP:
        tok = "PHR" if "PHR" in sc["toks"] else "PH" if "PH" in sc["toks"] else "R"
    elif floor < 0:
        tok = "P" if sc["pit"] and not any(t.startswith("B") for t in sc["toks"]) else f"B{-floor}"
    else:
        tok = str(floor)
    return tok + sc["base"]


def _covers(sc: dict, rng: tuple[int, int]) -> bool:
    """부호 층 표시(sc)가 칸 층 범위(rng)와 한 층이라도 겹치는지."""
    if rng[1] >= FLOOR_TOP and scope_has(sc, FLOOR_TOP):
        return True
    return any(scope_has(sc, n) for n in range(max(rng[0], -20), min(rng[1], 80) + 1) if n)


def marks_at(it: dict, floor: int | None) -> list[str]:
    """일람표 칸의 부호 중 그 층 것(층 부호로 바꿔서). 층 표시 없는 부호는 칸의 층 범위(floors)를 따름. floor가 None이면 부호 그대로."""
    if floor is None:
        return list(it.get("marks") or [])
    rng = floor_range(it.get("floors") or "")
    out = []
    for mk in it.get("marks") or []:
        sc = mark_scope(mk)
        if sc is not None and rng is not None and not _covers(sc, rng):  # 부호 층 표시와 칸 층이 전혀 안 겹치면 칸 층을 따름(RCG1 · 2층 — 2층 높이 지붕 보)
            sc = None
        if sc is None:
            if rng is None or rng[0] <= floor <= rng[1]:
                out.append(mk)
        else:
            fm = floor_mark(mk, floor)
            if fm:
                out.append(fm)
    return list(dict.fromkeys(out))


def split_scopes(items: list[dict]) -> list[dict]:
    """한 칸에 층 표시가 다른 부호가 섞이면(PG1, RG1, 1-5G1 · R, 1~5) 층 표시마다 칸을 나눔 — 값(크기·철근)은 같이, 층 = 그 부호의 층 이름.
    첫 묶음은 번호(id) 그대로(이미 고른 칸이 그대로 가리키게). 같은 층 표시끼리는 한 칸(R~1G2, R~1G3)."""
    out = []
    for it in items:
        groups: dict[str, list[str]] = {}
        for mk in it.get("marks") or []:
            sc = mark_scope(mk)
            groups.setdefault(sc["label"] if sc else "", []).append(mk)
        if len(groups) <= 1:
            out.append(it)
            continue
        for k, (label, ms) in enumerate(groups.items()):
            out.append({**it, "id": it["id"] if k == 0 else f"{it['id']}{k}", "marks": ms, "floors": label or it.get("floors") or ""})
    return out


# ---------- 정리·검산 ----------
def normalize_item(raw: dict, pg: int | None = None) -> dict | None:
    kind = str(raw.get("kind") or "").strip()
    if kind in ("옹벽", "벽", "WALL"):
        kind = "벽체"
    if kind not in KINDS:
        return None
    marks = raw.get("marks") or []
    if isinstance(marks, str):
        marks = [m.strip() for m in re.split(r"[,/]", marks) if m.strip()]
    it = {"id": raw.get("id") or uuid.uuid4().hex[:8], "kind": kind, "marks": [str(m).strip()[:20] for m in marks if str(m).strip()][:8],
          "floors": str(raw.get("floors") or "").strip()[:30], "same_as": str(raw.get("same_as") or "").strip()[:30]}
    for k in FIELDS[kind]:
        v = raw.get(k)
        it[k] = _int(v) if k in INT_FIELDS else str(v or "").strip()[:60]
    if kind == "벽체" and it.get("thickness") is None:
        it["thickness"] = _int(re.sub(r"[^\d.]", "", str(raw.get("thickness") or "")) or None)
    box = raw.get("box")
    it["box"] = [max(0.0, min(100.0, float(v))) for v in box] if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box) else None
    it["pg"] = raw.get("pg", pg)
    it["unsure"] = [str(u) for u in (raw.get("unsure") or []) if str(u) in FIELDS[kind] or u in ("marks", "floors")][:10]
    it["confirmed"] = bool(raw.get("confirmed")) if "confirmed" in raw else default_confirmed(it)
    it["by"] = str(raw.get("by") or "")
    return it


def default_confirmed(it: dict) -> bool:
    """처음 읽었을 때 사람 확인이 필요 없는 칸 — 벽체, 하부근 한 줄인 보(글자 총수 그대로). 기둥은 늘 확인(변별 점 개수)."""
    if it["kind"] == "벽체":
        return not it["unsure"]
    if it["kind"] == "보":
        return (it.get("bottom_layers") or 1) == 1 and not it["unsure"]
    return False


def check(it: dict) -> dict:
    """검산·확인 필요 이유 — {ok: bool|None, why: 글}."""
    if it["kind"] == "기둥":
        n, s, l_ = bar_count(it.get("main")), it.get("short_side"), it.get("long_side")
        if str(it.get("size") or "").startswith(("∅", "Ø", "φ", "D")):
            return {"ok": True, "why": "원형 — 주근 총수 그대로"}
        if n is None:
            return {"ok": None, "why": "주근 글자에서 개수를 못 읽음"}
        if not s or not l_:
            return {"ok": False, "why": "단변·장변 점 개수를 넣으세요"}
        calc = 2 * (s + l_) - 4
        return {"ok": calc == n, "why": "" if calc == n else f"2×(단변 {s} + 장변 {l_}) − 4 = {calc} ≠ 주근 {n}"}
    if it["kind"] == "보":
        n, row, layers = bar_count(it.get("bottom")), it.get("bottom_row"), it.get("bottom_layers") or 1
        if n is None:
            return {"ok": None, "why": "하부근 글자에서 개수를 못 읽음"}
        if layers == 1:
            return {"ok": True, "why": ""}
        if not row:
            return {"ok": False, "why": "두 줄 — 아래 줄 점 개수를 넣으세요"}
        return {"ok": row < n, "why": "" if row < n else f"아래 줄 {row} ≥ 하부근 {n}"}
    return {"ok": True, "why": ""}


def design(it: dict, position: str = "", side: str = "") -> dict:
    """철근탐사 한 시험의 설계값 — 두 줄 {label, value} (견본 표: 기둥 주근 EA·대근 @, 보 하부근 EA(복)·늑근 @, 벽체 수직근 @·수평근 @).
    position = 단부/중앙부(기둥 대근 간격), side = 단변/장변(기둥)."""
    if it["kind"] == "기둥":
        cnt = it.get("long_side") if side == "장변" else it.get("short_side")
        hoop = (it.get("hoop_end") or it.get("hoop")) if position == "단부" else it.get("hoop")
        return {"rows": [{"label": "주근", "value": f"{cnt}EA" if cnt else ""}, {"label": "대근", "value": f"@{spacing(hoop)}" if spacing(hoop) else ""}]}
    if it["kind"] == "보":
        n, layers, row = bar_count(it.get("bottom")), it.get("bottom_layers") or 1, it.get("bottom_row")
        val = f"{row}EA(복)" if layers == 2 and row else (f"{n}EA" if n else "")
        return {"rows": [{"label": "하부근", "value": val}, {"label": "늑근", "value": f"@{spacing(it.get('stirrup'))}" if spacing(it.get("stirrup")) else ""}]}
    return {"rows": [{"label": "수직근", "value": f"@{spacing(it.get('vertical'))}" if spacing(it.get("vertical")) else ""},
                     {"label": "수평근", "value": f"@{spacing(it.get('horizontal'))}" if spacing(it.get("horizontal")) else ""}]}


def preview(it: dict) -> str:
    """확인 화면 한 줄 — 철근탐사에 들어갈 설계값(기둥은 두 변·두 위치)."""
    if it["kind"] == "기둥":
        a, b = design(it, "중앙부", "단변")["rows"], design(it, "단부", "장변")["rows"]
        hoop = a[1]["value"] + (f" · 단부 {b[1]['value']}" if b[1]["value"] and b[1]["value"] != a[1]["value"] else "")
        return f"단변 주근 {a[0]['value'] or '?'} · 장변 {b[0]['value'] or '?'} · 대근 {hoop or '?'}"
    rows = design(it)["rows"]
    return " · ".join(f"{r['label']} {r['value'] or '?'}" for r in rows)


def view(data: dict | None) -> dict:
    """화면에 줄 값 — items에 check 붙이고 종류·부호 순."""
    data = data or {}
    items = []
    for raw in data.get("items") or []:
        it = normalize_item(raw)
        if it:
            items.append({**it, "check": check(it), "preview": preview(it)})
    order = {k: i for i, k in enumerate(KINDS)}
    items.sort(key=lambda x: (order[x["kind"]], x["marks"][0] if x["marks"] else "", -((floor_range(x["floors"]) or (0, 0))[1])))
    need = sum(1 for x in items if not x["confirmed"] or x["check"]["ok"] is False)
    return {"status": data.get("status") or "", "message": data.get("message") or "", "read_at": data.get("read_at") or "",
            "pages": data.get("pages") or [], "items": items, "need": need, "cost": data.get("cost")}


# ---------- 읽기 ----------
def schedule_pages(files: list[dict]) -> list[dict]:
    """[{src(도면 id), name, page}] — PDF는 쪽마다, 그림은 한 장. 최대 MAX_PAGES."""
    import pymupdf

    out = []
    for it in files:
        p = Path(it["path"])
        if p.suffix.lower() == ".pdf":
            with pymupdf.open(p) as d:
                out += [{"src": it["id"], "name": it.get("name") or p.name, "page": i} for i in range(d.page_count)]
        else:
            out.append({"src": it["id"], "name": it.get("name") or p.name, "page": 0})
    return out[:MAX_PAGES]


def page_image(path: Path, page: int, side: int = 3136):
    """쪽 그림(PIL, 화면 방향) — PDF는 렌더, 그림 파일은 그대로."""
    from PIL import Image, ImageOps

    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as d:
            pg = d[page]
            z = side / max(pg.rect.width, pg.rect.height)
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples), pg.get_text().strip()
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    im.thumbnail((side, side))
    return im, ""


def read_page(company_id: int, path: Path, page: int) -> tuple[list[dict], dict]:
    """한 쪽 → 줄들, 토큰 {in, out}. AI 호출은 vision.ask와 같은 길(모델·키·스트리밍)에 토큰 수만 더 받음."""
    from anthropic import Anthropic

    from core.config import get_api_key, get_model_name, has_api_key
    from server.sitok import schedule_read, vision

    if not has_api_key(company_id):
        raise RuntimeError("Claude API 키가 없습니다 — 보고서 자동화 설정 탭에서 등록하세요.")
    im, text = page_image(path, page)
    imgs = schedule_read._tiles(im)
    prompt = PROMPT.format(text=("도면 글자(순서 뒤섞임):\n" + text[:12000]) if len(text) > 100 else "(글자 없음 — 그림으로)")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": vision._jpeg(b, 1568)}} for b in imgs]
    content.append({"type": "text", "text": prompt})
    client = Anthropic(api_key=get_api_key(company_id))
    with client.messages.stream(model=get_model_name(), max_tokens=32000, messages=[{"role": "user", "content": content}],
                                output_config={"effort": "medium"}) as stream:
        resp = stream.get_final_message()
    answer = "".join(b.text for b in resp.content if b.type == "text").strip()
    m = re.search(r"\{.*\}", answer, re.S)
    raw = json.loads(m.group(0)) if m else {}
    return list(raw.get("items") or []), {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}


def inherit_same(items: list[dict]) -> list[dict]:
    """"아래층과 같음"(화살표·상동·〃) 칸 — 같은 부호의 기준 층 칸에서 빈 값과 단면 그림 위치를 이어받음(10/21 시험: 화살표 칸은 점 개수를 비워 둠)."""
    def key(t: str) -> str:
        return re.sub(r"\s|층|F", "", str(t or "")).upper()

    for it in items:
        if not it.get("same_as"):
            continue
        src = next((x for x in items if x is not it and x["kind"] == it["kind"] and set(x["marks"]) & set(it["marks"])
                    and (key(x["floors"]) == key(it["same_as"]) or floor_range(x["floors"]) == floor_range(it["same_as"]))
                    and (x.get("position") or "") == (it.get("position") or "")), None)
        if src is None:
            continue
        for k in FIELDS[it["kind"]]:
            if k != "position" and it.get(k) in (None, "") and src.get(k) not in (None, ""):
                it[k] = src[k]
        if src.get("box"):
            it["box"], it["pg"] = src["box"], src.get("pg")
    return items


def merge_confirmed(old_items: list[dict], new_items: list[dict]) -> list[dict]:
    """다시 읽을 때 사람이 확인·고친 줄은 살림 — 같은 종류·부호·층·위치면 확인한 값으로."""
    keep = {(x["kind"], tuple(x["marks"]), x["floors"], x.get("position") or ""): x for x in old_items if x.get("confirmed") and x.get("by")}
    out = []
    for it in new_items:
        k = (it["kind"], tuple(it["marks"]), it["floors"], it.get("position") or "")
        if k in keep:
            out.append({**keep.pop(k), "box": it.get("box"), "pg": it.get("pg")})
        else:
            out.append(it)
    return out + list(keep.values())  # 새로 못 찾은 확인 줄도 남김


def crop_png(path: Path, page: int, box: list[float], margin: float = 0.12, side: int = 900) -> bytes:
    """단면 그림 자르기(box = 쪽 화면 기준 백분율, 여유 margin 배) → PNG."""
    x0, y0, x1, y1 = box
    mx, my = (x1 - x0) * margin, (y1 - y0) * margin
    x0, y0, x1, y1 = max(0, x0 - mx), max(0, y0 - my), min(100, x1 + mx), min(100, y1 + my)
    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as d:
            pg = d[page]
            W, H = pg.rect.width, pg.rect.height
            clip = pymupdf.Rect(W * x0 / 100, H * y0 / 100, W * x1 / 100, H * y1 / 100)  # 화면 좌표(회전 반영) 그대로
            z = side / max(clip.width, clip.height, 1)
            return pg.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False).tobytes("png")
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    part = im.crop((int(w * x0 / 100), int(h * y0 / 100), int(w * x1 / 100), int(h * y1 / 100)))
    part.thumbnail((side, side))
    buf = io.BytesIO()
    part.save(buf, "PNG")
    return buf.getvalue()


def stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _selfcheck() -> None:
    assert bar_count("12-HD25") == 12 and bar_count("3 - SHD22") == 3 and bar_count("HD10@300") is None
    assert bar_count("HD22-2EA") == 2 and bar_count("HD22 - 12EA") == 12 and bar_count("4ea") == 4 and bar_count("HD22") is None
    assert spacing("2-HD10@200") == 200 and spacing("HD16+19 @100") == 100 and spacing("HD10 @300 / HD10@300") == 300 and spacing("12-HD25") is None
    assert floor_range("1~4") == (1, 4) and floor_range("지하6층~지하2층") == (-6, -2) and floor_range("6F 이상") == (6, FLOOR_TOP)
    assert floor_range("PIT층/지하층") == (-9, -1) and floor_range("R") == (FLOOR_TOP, FLOOR_TOP) and floor_range("B1F~2F") == (-1, 2)
    assert floor_range("옥탑층") == (FLOOR_TOP, FLOOR_TOP) and floor_range("3층") == (3, 3) and floor_range("11~이상") is None
    c = normalize_item({"kind": "기둥", "marks": ["C1", "C2"], "floors": "1층", "size": "400×500", "main": "10-HD19", "short_side": 3, "long_side": 4, "hoop": "HD10@300", "hoop_end": "HD10@150"})
    assert check(c)["ok"] and not c["confirmed"]
    assert design(c, "단부", "단변")["rows"] == [{"label": "주근", "value": "3EA"}, {"label": "대근", "value": "@150"}]
    assert design(c, "중앙부", "장변")["rows"][0]["value"] == "4EA" and design(c, "중앙부", "장변")["rows"][1]["value"] == "@300"
    b = normalize_item({"kind": "보", "marks": ["G1"], "floors": "2~5", "position": "중앙부", "bottom": "7-HD19", "bottom_row": 5, "bottom_layers": 2, "stirrup": "HD10@200"})
    assert design(b)["rows"] == [{"label": "하부근", "value": "5EA(복)"}, {"label": "늑근", "value": "@200"}] and not b["confirmed"] and check(b)["ok"]
    b1 = normalize_item({"kind": "보", "marks": ["G1"], "floors": "2~5", "position": "단부", "bottom": "3-HD19", "bottom_layers": 1, "stirrup": "HD10@150"})
    assert b1["confirmed"] and design(b1)["rows"][0]["value"] == "3EA"
    w = normalize_item({"kind": "옹벽", "marks": ["SW1"], "floors": "2층", "thickness": "200", "vertical": "HD13 @200", "horizontal": "HD10 @300"})
    assert w["kind"] == "벽체" and w["thickness"] == 200 and design(w)["rows"][1]["value"] == "@300"
    up = normalize_item({"kind": "기둥", "marks": ["C1A"], "floors": "2층", "main": "", "same_as": "지하2층", "box": [1, 1, 2, 2]})
    base = normalize_item({"kind": "기둥", "marks": ["C1A"], "floors": "지하2층", "main": "12-HD25", "short_side": 4, "long_side": 4, "hoop": "HD10@300", "box": [5, 80, 9, 95]})
    inherit_same([up, base])
    assert up["main"] == "12-HD25" and up["short_side"] == 4 and up["box"] == [5, 80, 9, 95] and check(up)["ok"]
    bad = normalize_item({"kind": "기둥", "marks": ["C6"], "floors": "1층", "main": "16-HD25", "short_side": 3, "long_side": 3})
    assert check(bad)["ok"] is False and "≠" in check(bad)["why"]


if __name__ == "__main__":
    _selfcheck()
    print("ok")
