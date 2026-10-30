"""지난 보고서 PDF의 외관조사 사진첩(부록2) 읽기(2026-10-10 5단계) — 층별 "[지상2층 결함 현황표]"(번호~사진번호 13칸)와
"[지상2층 결함사진표]"(사진 6장 + 사진번호·결함유형·개소·폭·길이·물량)를 읽어 전회차 결함 목록 + 사진으로.

사진첩은 한글 밖(구글 스프레드시트)에서 만들어 PDF로 합친 것이라 글자가 살아 있다(평택 견본 94~106쪽). 사진은 결함사진표 쪽에서
"사진N" 설명 칸마다 같은 열(가로가 겹침) 바로 위의 그림을 짝지어 그 자리를 잘라 낸다(원본 그림이 돌아가 있거나 커도 보이는 그대로).
예전엔 그림을 위쪽 끝 좌표 → 왼쪽 차례로 늘어놓고 설명 칸 차례와 맞췄는데, 같은 줄 그림의 위쪽 끝이 1pt만 달라도(칸 가운데 맞춤) 순서가 뒤바뀌어
사진이 서로 바뀌었음(10/20 형 검수 — 의정부시 스포츠센터 87쪽 지상3층 사진5 569pt·사진6 568pt). 외관망도 위치와 이어지니 위치로 짝지음.
사진 칸에 그림 대신 "보수" 글자만 있는 쪽(10/22 양주덕산초 지상1층 사진13~18)은 사진 없음 — 예전 예비 규칙(못 짝지은 칸끼리 남은 그림을 차례로)이
쪽 아래로 거의 다 벗어난 그림을 사진13에 붙여 표 모서리를 잘라 넣었음 → 같은 열·바로 위(사이에 다른 설명 칸 없음)만, 그림은 쪽 안에 보이는 부분만.
10/30 사용자: 시설물 1개 안 연결된 동마다 간지("1. 통계청" · "2. 선거관리위원회" …)를 넣고 동마다 층별 표 — 층 이름(지붕층·지상8층)이 동마다 겹쳐
한 층으로 섞이고 사진이 서로 덮였음 → 간지 쪽 글("N. 이름", 묶음 "부록2-N. 이름")을 동으로(Row.zone), 사진도 (동, 층, 사진N)으로.
사진첩 간지("…사진첩")·다른 부록 간지("부록.3 …")를 만나면 동을 비움(보고서 PDF 통째로 올려도 부록1 간지 등이 동이 되지 않게).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

HEAD = ["번호", "구분", "부재", "결함유형", "개수", "폭", "길이", "물량", "면적률", "결함원인", "진행유무", "비고", "사진번호"]


@dataclass
class Row:
    floor: str
    seq: int
    values: dict
    photo_no: str = ""
    photo_png: bytes | None = None
    zone: str = ""  # 동 간지 이름(10/30) — 없으면 ""


ZONE_RE = re.compile(r"(?:부록\s*\d+\s*-\s*)?\d{1,2}\s*\.\s*(\S.{0,30})")  # 동 간지 "1. 통계청" · 묶음 "부록2-1. 본관동"


def zone_of(text: str) -> str | None:
    """간지 쪽(글이 짧은 쪽) → 동 이름 / "" (사진첩·다른 부록 간지 — 동을 비움) / None(간지 아님)."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t or len(t) > 40:
        return None
    if "사진첩" in t or "외관망도" in t or re.match(r"부록\s*\.?\s*\d+\s*(?!-)", t):
        return ""
    m = ZONE_RE.fullmatch(t)
    return m[1].strip() if m else None


@dataclass
class Album:
    rows: list[Row] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


def _floor(text: str) -> str:
    m = re.search(r"\[\s*(.+?)\s*결함\s*(현황표|사진표)\s*\]", text or "")
    f = m[1].replace(" ", "") if m else ""
    return "옥상층" if f in ("지붕층", "지붕", "옥상", "옥탑층") else f  # 지난 보고서 "지붕층" → 우리 층 이름 "옥상층"(형 10/14)


def _clean(v) -> str:
    return " ".join(str(v or "").split())


ABOVE_GAP = 80  # 설명 칸 위쪽 끝과 그 위 그림 아래쪽 끝 사이 최대 간격(pt) — 견본·의정부 33pt


def match(imgs: list, caps: list[tuple]) -> list[tuple]:
    """그림(Rect)과 설명 칸 [(Rect, "사진N")] → [(그림 Rect, "사진N")]. 설명 칸마다 같은 열(가로가 겹침)에서 바로 위(ABOVE_GAP 안, 가장 가까운) 그림,
    못 찾은 칸은 간격 제한 없이 같은 열 위쪽 그림 중 가장 가까운 것 — 그 사이에 다른 설명 칸이 없을 때만(그림 없는 "보수" 칸은 사진 없음)."""
    used: set[int] = set()
    out, left = [], []
    order = sorted(caps, key=lambda c: (round(c[0].y0), c[0].x0))
    col = lambda im, cap: im.x0 < cap.x1 and im.x1 > cap.x0  # noqa: E731 — 같은 열(가로가 겹침)
    for cap, no in order:
        cand = [(cap.y0 - im.y1, k) for k, im in enumerate(imgs) if k not in used and col(im, cap) and -8 <= cap.y0 - im.y1 <= ABOVE_GAP]
        if cand:
            k = min(cand)[1]
            used.add(k)
            out.append((imgs[k], no))
        else:
            left.append((cap, no))
    for cap, no in left:
        cand = [(cap.y0 - im.y1, k) for k, im in enumerate(imgs) if k not in used and col(im, cap) and im.y1 <= cap.y0 + 8
                and not any(o is not cap and col(im, o) and im.y1 - 8 <= o.y0 < cap.y0 for o, _ in caps)]
        if cand:
            k = min(cand)[1]
            used.add(k)
            out.append((imgs[k], no))
    return out


def read(pdf_bytes: bytes) -> Album:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = Album()
    photos: dict[tuple[str, str, str], bytes] = {}  # (동, 층, "사진3") → PNG
    zone = ""
    for pn, page in enumerate(doc):
        text = page.get_text()
        z = zone_of(text)
        if z is not None:  # 간지 — 동 바뀜(10/30)
            zone = z
            continue
        if "결함 현황표" not in text and "결함사진표" not in text and "결함 사진표" not in text:
            continue
        floor = _floor(text)
        if not floor:
            continue
        out.pages.append(pn)
        tables = page.find_tables().tables
        if "현황표" in text and "사진표" not in text:
            for t in tables:
                for r in t.extract():
                    cells = [_clean(c) for c in r]
                    if len(cells) < 13 or not cells[0].isdigit():
                        continue
                    vals = dict(zip(HEAD, cells[:13]))
                    out.rows.append(Row(floor, int(cells[0]), {k: ("" if v == "-" else v) for k, v in vals.items()}, cells[12], zone=zone))
        else:
            caps = []  # [(설명 칸 Rect, "사진N")]
            for t in tables:
                for row in t.rows:
                    for cell in row.cells:
                        if cell is None:
                            continue
                        txt = _clean(page.get_textbox(cell))
                        if re.fullmatch(r"사진\s*\d+", txt):
                            caps.append((pymupdf.Rect(cell), txt.replace(" ", "")))
            imgs = [r for r in (pymupdf.Rect(i["bbox"]) & page.rect for i in page.get_image_info()) if r.width > 40 and r.height > 20]  # 쪽 안에 보이는 부분만
            for rect, no in match(imgs, caps):
                photos[(zone, floor, no)] = page.get_pixmap(clip=rect, dpi=150).tobytes("jpg")
    for r in out.rows:
        r.photo_png = photos.get((r.zone, r.floor, r.photo_no.replace(" ", "")))
    return out
