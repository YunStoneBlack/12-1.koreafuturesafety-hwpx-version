"""노임단가 자동 갱신(2026-10-29 사용자 "공지 뜨면 자동 적용 — 1월 1일·9월 1일 무렵에만 잘 살피고") — 한국물가정보(kpi.or.kr) 노임단가 게시판.

- 엔지니어링 노임단가(연 1회, 12월 공표 · 1월 1일 적용): 게시판 CATE_CD=701318 "YYYY년 엔지니어링 노임단가 적용기준" → 첨부 「엔지니어링업체 임금실태조사 보고서」(한글)
  → 건설부문 문장 "기술등급별로 임금을 보면 기술사 ○원, 특급기술자 ○원, …"(2025.12 보고서 788줄 — 회사 견적서 엑셀 값과 같음 확인).
- 시중노임단가(반기 · 1월 1일·9월 1일 적용): 게시판 CATE_CD=7011 "YYYY년 상반기|하반기 공사(건설)부문 노임단가" → 첨부 「건설업 임금실태조사 보고서」(한글)
  → 개별 직종 표 "1002 보통인부 172,698 …"(맨 앞 = 최신 공표일) = 시특법 내역서 현지보조인부.
검사(셋 다 맞아야 자동 적용): 여덟 등급이 다 읽힘 · 등급 차례(기술사 > 특급 > 고급 > 중급 > 초급, 숙련 셋도 차례) · 지난 값과 ±15% 안. 어긋나면 적용 안 하고 알림만.
적용일 전에 찾으면(12월·8월) 적용일부터 쓰게 "다음 값"으로 두고(rates_with가 날짜를 보고 바꿈), 견적은 만들 때 연도·단가를 붙여 두어(estimates.create) 지난 견적 금액은 안 바뀜.
살피는 때 = 12·1월, 8·9월(하루 한 번, 견적 화면을 열 때 뒤에서) + 기준표 [지금 확인]."""
from __future__ import annotations

import datetime
import io
import re
import struct
import threading
import urllib.parse
import zlib

import requests

KPI = "https://www.kpi.or.kr/www/price/"
ENG_LIST = KPI + "wage_basis.asp?CATE_CD=701318"
CON_LIST = KPI + "wage_basis.asp?CATE_CD=7011"
UA = {"User-Agent": "Mozilla/5.0 (KFSC estimate rate check)"}
GRADES = ("기술사", "특급기술자", "고급기술자", "중급기술자", "초급기술자", "고급숙련기술자", "중급숙련기술자", "초급숙련기술자")
WATCH_MONTHS = (12, 1, 8, 9)
MAX_CHANGE = 0.15
_LOCK = threading.Lock()


def _get(url: str, referer: str | None = None) -> bytes:
    r = requests.get(url, headers={**UA, **({"Referer": referer} if referer else {})}, timeout=40)
    r.raise_for_status()
    return r.content


def posts(list_url: str) -> list[tuple[str, str]]:
    """게시판 글 [(제목, 상세 주소)] — 페이지는 EUC-KR."""
    html = _get(list_url).decode("euc-kr", "replace")
    out = []
    for m in re.finditer(r'href="([^"]*wage_basis_detail\.asp\?[^"]*)"[^>]*>(.*?)</a>', html, re.S):
        t = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
        if t:
            out.append((t, urllib.parse.urljoin(KPI, m.group(1).replace("&amp;", "&"))))
    return out


def attachment(detail_url: str) -> tuple[str, bytes]:
    """상세 글의 첫 첨부(한글) — 파일 이름이 EUC-KR이라 바이트 그대로 퍼센트 인코딩."""
    raw = _get(detail_url)
    m = re.search(rb'wage_basis_download\.asp\?file=([^"\'>]+)', raw)
    if not m:
        raise ValueError("첨부파일을 못 찾았습니다")
    name = m.group(1).decode("euc-kr", "replace")
    url = KPI + "wage_basis_download.asp?file=" + urllib.parse.quote(m.group(1), safe="._-")
    return name, _get(url, referer=detail_url)


def hwp_text(data: bytes) -> str:
    """HWP5(옛 .hwp) 본문 글자만 — BodyText/SectionN의 PARA_TEXT(67) 레코드(핵심기술 43절). 받은 파일은 데이터로만 읽음."""
    import olefile

    ole = olefile.OleFileIO(io.BytesIO(data))
    hdr = ole.openstream("FileHeader").read()
    compressed = bool(struct.unpack("<I", hdr[36:40])[0] & 1)
    secs = sorted([s for s in ole.listdir() if s[0] == "BodyText"], key=lambda s: int(re.sub(r"\D", "", s[1]) or 0))
    lines = []
    for s in secs:
        d = ole.openstream(s).read()
        if compressed:
            d = zlib.decompress(d, -15)
        i = 0
        while i + 4 <= len(d):
            h = struct.unpack("<I", d[i:i + 4])[0]
            i += 4
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            if size == 0xFFF:
                size = struct.unpack("<I", d[i:i + 4])[0]
                i += 4
            body = d[i:i + size]
            i += size
            if tag != 67:
                continue
            txt, j = [], 0
            while j + 2 <= len(body):
                c = struct.unpack("<H", body[j:j + 2])[0]
                if c < 32:
                    if c in (0, 10, 13):
                        j += 2
                        continue
                    j += 16 if c not in (24, 25, 26, 27, 28, 29, 30, 31) else 2
                    continue
                txt.append(chr(c))
                j += 2
            t = "".join(txt).strip()
            if t:
                lines.append(t)
    ole.close()
    return "\n".join(lines)


def parse_engineering(text: str) -> dict[str, int]:
    """건설부문 기술등급별 임금 — "건설부문 표본업체" 뒤 첫 "기술등급별로 임금을 보면 …" 문장."""
    i = text.find("건설부문 표본업체")
    if i < 0:
        return {}
    m = re.search(r"기술등급별로\s*임금을\s*보면(.*?)(?:으로\s*추정|\n)", text[i:i + 4000], re.S)
    if not m:
        return {}
    out = {}
    for g in GRADES:
        mm = re.search(rf"(?<![가-힣]){g}\s*([\d,]+)\s*원", m.group(1))
        if mm:
            out[g] = int(mm.group(1).replace(",", ""))
    return out


def parse_helper(text: str) -> int | None:
    """개별 직종 노임단가 표 "1002 보통인부 172,698 …" — 첫 숫자 = 최신 공표일 값."""
    m = re.search(r"\n1002\n보통인부\n([\d,]{5,9})\n", "\n" + text + "\n")
    return int(m.group(1).replace(",", "")) if m else None


def check_values(vals: dict[str, int], prev: dict | None, gap: int = 1) -> list[str]:
    """검사 — gap = 지난 값과 해 차이(허용 폭 = 1년당 ±15%, 2019년 표와 2026년이면 ±105%)."""
    probs = []
    limit = MAX_CHANGE * max(1, gap)
    miss = [g for g in GRADES if not vals.get(g)]
    if miss:
        probs.append("못 읽은 등급: " + ", ".join(miss))
        return probs
    main = [vals[g] for g in GRADES[:5]]
    skilled = [vals[g] for g in GRADES[5:]]
    if any(a <= b for a, b in zip(main, main[1:])):
        probs.append("기술사 > 특급 > 고급 > 중급 > 초급 차례가 아님")
    if any(a <= b for a, b in zip(skilled, skilled[1:])):
        probs.append("고급 > 중급 > 초급 숙련기술자 차례가 아님")
    for g in GRADES:
        p = (prev or {}).get(g)
        if p and abs(vals[g] - p) / p > limit:
            probs.append(f"{g} {p:,} → {vals[g]:,}원(±{int(limit * 100)}% 넘음)")
    return probs


def check_engineering(saved: dict) -> dict | None:
    """새 연도 공표가 있으면 {kind, year, values, problems, title, url, from} — 이미 있으면 None."""
    best = None
    for t, u in posts(ENG_LIST):
        m = re.match(r"(\d{4})년\s*엔지니어링\s*노임단가\s*적용기준", t)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), t, u)
    if best is None:
        return None
    year, title, url = best
    have = ((saved.get("labor") or {}).get(str(year))) or {}
    if have and all(have.get(g) for g in GRADES) and (saved.get("labor_auto") or {}).get(str(year)):
        return None  # 이미 넣음
    name, data = attachment(url)
    vals = parse_engineering(hwp_text(data))
    from server.estimate import calc as C
    merged = C.rates_with(saved)["labor"]  # 지난 값 = 이 연도보다 앞선 가장 늦은 연도(처음 값 포함)
    prev_year = max((int(y) for y in merged if int(y) < year), default=None)
    prev = merged.get(str(prev_year)) if prev_year else None
    return {"kind": "labor", "year": str(year), "values": vals, "problems": check_values(vals, prev, year - prev_year if prev_year else 1), "title": title, "url": url, "file": name,
            "from": f"{year}-01-01"}


def check_helper(saved: dict) -> dict | None:
    best = None
    for t, u in posts(CON_LIST):
        m = re.match(r"(\d{4})년\s*(상반기|하반기)\s*공사\(건설\)부문\s*노임단가", t)
        if m:
            key = (int(m.group(1)), 2 if m.group(2) == "하반기" else 1)
            if best is None or key > best[0]:
                best = (key, t, u)
    if best is None:
        return None
    (year, half), title, url = best
    tag = f"{year}-H{half}"
    if (saved.get("helper_key") or "") >= tag:
        return None
    name, data = attachment(url)
    val = parse_helper(hwp_text(data))
    probs = []
    cur = saved.get("helper_rate")
    if not val:
        probs.append("보통인부 단가를 못 읽음")
    elif cur and abs(val - float(cur)) / float(cur) > MAX_CHANGE and saved.get("helper_key"):
        probs.append(f"보통인부 {int(float(cur)):,} → {val:,}원(±{int(MAX_CHANGE * 100)}% 넘음)")
    return {"kind": "helper", "key": tag, "value": val, "problems": probs, "title": title, "url": url, "file": name,
            "from": f"{year}-09-01" if half == 2 else f"{year}-01-01"}


def apply(saved: dict, found: dict) -> dict:
    """찾은 값을 기준표에(검사 통과한 것만) — 적용일 전이면 '다음 값'으로(rates_with가 날짜 보고 바꿈)."""
    s = dict(saved or {})
    if found["kind"] == "labor":
        s.setdefault("labor", {})
        s["labor"] = {**s["labor"], found["year"]: found["values"]}
        s["labor_auto"] = {**(s.get("labor_auto") or {}), found["year"]: found["from"]}
        s["labor_next"] = {"year": found["year"], "from": found["from"]}
    else:
        s["helper_next"] = {"value": found["value"], "from": found["from"], "key": found["key"]}
        s["helper_key"] = found["key"]
    return s


def in_window(day: datetime.date) -> bool:
    return day.month in WATCH_MONTHS


def run(load, save, notify, force: bool = False) -> list[dict]:
    """한 번 살피기 — load() = 저장된 기준표, save(dict) = 저장, notify(list) = 알림 남기기. 돌려줌 = 이번에 찾은 것들."""
    if not _LOCK.acquire(blocking=False):
        return []
    try:
        found = []
        for fn in (check_engineering, check_helper):
            try:
                f = fn(load())
            except Exception as err:  # noqa: BLE001 — 사이트가 바뀌었거나 안 열림
                f = {"kind": "error", "problems": [f"{fn.__name__}: {str(err)[:160]}"]}
            if not f:
                continue
            f["at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if f["kind"] != "error" and not f["problems"]:
                save(apply(load(), f))
                f["applied"] = True
            else:
                f["applied"] = False
            found.append(f)
        notify(found)
        return found
    finally:
        _LOCK.release()
