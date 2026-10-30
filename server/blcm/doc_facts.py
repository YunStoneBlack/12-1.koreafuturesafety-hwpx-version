"""건축물관리점검 점검 목록 — 서류(건축물대장·토지이용계획확인원)에서 현장·면담 질문의 답을 미리 읽기
(2026-10-30 사용자 "현장 면담 확인이라고 되어 있는 건 사전판단이 안 되는 거야?" → "응 시작").

읽는 것(답 = 있음/없음 + 근거 글, 점검자가 화면에서 바꾸면 그 답이 이김):
- 대장 승강기(승용·비상용 대수, 칸 위치로) → elevator 있음(0·빈칸이면 모름 — 옛 건물은 안 적은 대장이 많음)
- 대장 건축물 인증 현황(인증명 + 유효기간) → certs 있음 / 새 서식인데 빈칸이면 없음(에너지성능지표 EPI는 인증 아님)
- 대장 건축주(칸 위치로) → public_owner: 지자체·교육청·공사·공단 = 있음, 주민번호(개인)·주식회사 = 없음(지은 때 건축주라 바뀌었을 수 있음 — 근거에 적음)
- 대장 변동사항(날짜 줄 + 내용, 집합 표제부처럼 칸이 섞인 대장도) → unauth_change 있음(증축·개축·대수선·구조변경·용도변경)
- 토지이용계획확인원(토지이음 출력 PDF, 글자 있는 것) "지역지구등 지정여부" 칸만 → fire_district·street_height·district_plan 있음/없음
  (범례·유의사항에는 이웃 땅 지구·"지구단위계획구역에 해당하는 경우" 같은 문구가 있어 문서 전체를 보면 틀림 — 회사 보고서 확인원 53개 중 글자 PDF 45개로 확인)
- 확인원이 없으면 대장 지구·구역 칸에 방화지구·지구단위계획구역이 적혀 있을 때만 있음(빈칸은 모름)."""
from __future__ import annotations

import datetime
import functools
import re
from pathlib import Path

import pymupdf

CERT_RE = re.compile(r"(녹색건축|건축물에너지효율등급|제로에너지건축물|지능형건축물)인증(\d{4}\.\d{1,2}\.\d{1,2}\.?~\d{4}\.\d{1,2}\.\d{1,2}\.?)")
CERT_NAME = {"녹색건축": "녹색건축", "건축물에너지효율등급": "에너지효율등급", "제로에너지건축물": "제로에너지", "지능형건축물": "지능형"}
PUBLIC_RE = re.compile(r"특별시|광역시|특별자치[시도]|^[가-힣]{1,5}(도|시|군|구)(청|청장|장|지사|수)?$|교육(청|감|지원청)|대한민국|국토교통부|국방부|조달청|"
                       r"도시공사|도시개발공사|토지주택공사|한국[가-힣]*(공사|공단)|[가-힣]+공단$|지방자치단체")
PRIVATE_RE = re.compile(r"\d{6}-[0-4]|(19|20)\d{6}\*|주식회사|\(주\)|㈜|유한회사")  # 주민번호·생년월일(개인), 법인번호·회사
NOT_NAME = re.compile(r"^(구분|옥내|옥외|인근|면제|자주식|기계식|※+)$")
CHANGE_RE = re.compile(r"증축|개축|대수선|구조변경|용도변경|철거")
DATE_LINE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?")
LABEL_LINE = re.compile(r"^(대지위치|명칭|호수|지번|도로명|구분|건축주|설계자|공사감리자|공사시공자|※|변동|그밖의|발급|■|\(\d+쪽)")


def _words(doc) -> list:
    return [(pi, w) for pi, p in enumerate(doc) for w in p.get_text("words")]


def _elevators(ws: list) -> dict | None:
    """승강기 칸 — "승용 [n] 대 비상용 [m] 대"(숫자는 머리 글자 아래 줄, 승용~비상용 사이 / 비상용 오른쪽)."""
    for pi, w in ws:
        if w[4] != "승용":
            continue
        emg = next((v for p2, v in ws if p2 == pi and v[4] == "비상용" and abs(v[1] - w[1]) < 4 and v[0] > w[0]), None)
        if emg is None:
            continue
        nums = [(v[0], int(v[4])) for p2, v in ws if p2 == pi and re.fullmatch(r"\d{1,3}", v[4]) and w[1] - 2 <= v[1] <= w[3] + 16]
        a = sum(n for x, n in nums if w[0] - 5 <= x < emg[0] - 2)
        b = sum(n for x, n in nums if emg[0] - 2 <= x <= emg[2] + 70)
        return {"passenger": a, "emergency": b}
    return None


def _builder(ws: list) -> str:
    """건축주 칸 — 같은 줄 오른쪽 낱말(이름 + 번호, 옆 주차장 칸 글자·가린 ※ 빼고)."""
    for pi, w in ws:
        if w[4] != "건축주":
            continue
        row = sorted((v for p2, v in ws if p2 == pi and abs((v[1] + v[3]) / 2 - (w[1] + w[3]) / 2) < 4 and w[2] < v[0] < w[2] + 220
                      and not NOT_NAME.match(v[4])), key=lambda v: v[0])
        if row:
            return " ".join(v[4] for v in row[:2])
    return ""


def changes(raw: str) -> list[dict]:
    """변동사항 — 날짜 줄 다음 줄이 내용(괄호가 안 닫히면 다음 줄까지). 칸이 섞인 대장(집합 표제부)도 날짜+내용 짝으로 찾음."""
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    out: list[dict] = []
    for i, ln in enumerate(lines[:-1]):
        m = DATE_LINE.fullmatch(ln)
        nx = lines[i + 1]
        if not m or not re.match(r"[가-힣\[]", nx) or LABEL_LINE.match(nx) or "인허가" in nx:
            continue
        text, k = nx, i + 2
        while text.count("(") > text.count(")") and k < len(lines) and k < i + 5 and not DATE_LINE.fullmatch(lines[k]) and not LABEL_LINE.match(lines[k]):
            text += lines[k]
            k += 1
        try:
            day = datetime.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            continue
        if not any(c["date"] == day and c["text"] == text for c in out):
            out.append({"date": day, "text": text})
    return out


def _flat(doc) -> str:
    return "".join(p.get_text() for p in doc)


@functools.lru_cache(maxsize=64)
def _register(path: str, mtime: int, size: int) -> dict:  # noqa: ARG001 — mtime·size는 캐시 열쇠
    doc = pymupdf.open(path)
    ws = _words(doc)
    raw = _flat(doc)
    flat = re.sub(r"\s+", "", raw)
    certs = [f"{CERT_NAME[m[1]]}({m[2]})" for m in CERT_RE.finditer(flat)]
    return {"elevators": _elevators(ws), "builder": _builder(ws), "certs": list(dict.fromkeys(certs)),
            "cert_form": "인증명유효기간성능" in flat, "changes": changes(raw)}


def land_section(text: str) -> str:
    """토지이용계획확인원 "지역지구등 지정여부" 칸 글(범례·유의사항 빼고)."""
    a = text.find("지정여부")
    if a < 0:
        return ""
    ends = [x for x in (text.find("토지이용규제 기본법 시행령", a), text.find("확인도면", a)) if x > a]
    return re.sub(r"\s+", " ", text[a + 4:min(ends)] if ends else "").strip(" 「")


@functools.lru_cache(maxsize=64)
def _land(path: str, mtime: int, size: int) -> dict:  # noqa: ARG001
    doc = pymupdf.open(path)
    text = _flat(doc)
    sec = land_section(text)
    if not sec:
        return {"text_ok": False}
    m = re.search(r"소재지\s*(.+)", text)
    return {"text_ok": True, "address": (m[1].strip() if m else ""), "section": sec[:600],
            "fire_district": "방화지구" in sec, "street_height": "가로구역" in sec, "district_plan": "지구단위계획구역" in sec}


def _key(p: Path) -> tuple:
    s = p.stat()
    return str(p), s.st_mtime_ns, s.st_size


def read(register: Path | None, landuse: Path | None, b: dict | None = None) -> dict:
    """{"auto": {key: {"v": 있음|없음, "src": 근거}}, "changes": [...], "land": {...}|None, "register": {...}|None}."""
    b = b or {}
    auto: dict = {}
    reg = land = None
    if register is not None and register.exists():
        try:
            reg = _register(*_key(register))
        except Exception:  # noqa: BLE001 — 못 읽으면 질문 그대로
            reg = None
    if landuse is not None and landuse.exists():
        try:
            land = _land(*_key(landuse))
        except Exception:  # noqa: BLE001
            land = {"text_ok": False}
    if reg:
        el = reg["elevators"]
        if el and (el["passenger"] or el["emergency"]):
            auto["elevator"] = {"v": "있음", "src": f"건축물대장 승강기 승용 {el['passenger']}대·비상용 {el['emergency']}대"}
        if reg["certs"]:
            auto["certs"] = {"v": "있음", "src": "건축물대장 인증 현황 — " + ", ".join(reg["certs"])}
        elif reg["cert_form"]:
            auto["certs"] = {"v": "없음", "src": "건축물대장 건축물 인증 현황 빈칸"}
        who = reg["builder"]
        name = who.split(" ")[0] if who and not re.match(r"[\d*]", who) else ""
        if name and PUBLIC_RE.search(name):
            auto["public_owner"] = {"v": "있음", "src": f"건축물대장 건축주 {name}(지은 때 건축주 — 지금 소유자와 다르면 바꾸세요)"}
        elif who and PRIVATE_RE.search(who):
            auto["public_owner"] = {"v": "없음", "src": f"건축물대장 건축주 {name or '(이름 가림)'} — 민간(지은 때 건축주 — 지금 소유자와 다르면 바꾸세요)"}
        ch = [c for c in _merge(b.get("changes"), reg["changes"]) if CHANGE_RE.search(c["text"])]
        if ch:
            more = f" 외 {len(ch) - 1}건" if len(ch) > 1 else ""
            auto["unauth_change"] = {"v": "있음", "src": f"건축물대장 변동사항 {ch[0]['date'].replace('-', '.')} {ch[0]['text'][:60]}{more}"}
    if land and land.get("text_ok"):
        for k, lab in (("fire_district", "방화지구"), ("street_height", "가로구역별 최고높이"), ("district_plan", "지구단위계획구역")):
            auto[k] = {"v": "있음" if land[k] else "없음", "src": f"토지이용계획확인원 지정여부 — {lab} {'있음' if land[k] else '없음'}"}
    else:
        zone = " ".join(str(b.get(k) or "") for k in ("district", "area_zone"))
        if "방화지구" in zone:
            auto["fire_district"] = {"v": "있음", "src": "건축물대장 지구 칸 — 방화지구"}
        if "지구단위계획" in zone:
            auto["district_plan"] = {"v": "있음", "src": "건축물대장 구역 칸 — 지구단위계획구역"}
    return {"auto": auto, "changes": _merge(b.get("changes"), (reg or {}).get("changes")), "land": land, "register": reg}


def _merge(old: list | None, new: list | None) -> list[dict]:
    """저장된 변동사항(예전 읽기) + 다시 읽은 것 — 같은 날·같은 첫 글이면 하나."""
    out: list[dict] = []
    for c in (old or []) + (new or []):
        d = str(c.get("date") or "")[:10]
        t = str(c.get("text") or "")
        if t and not any(x["date"] == d and x["text"][:15] == t[:15] for x in out):
            out.append({"date": d, "text": t})
    return out
