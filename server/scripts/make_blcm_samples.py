"""건축물관리점검 견본 — 제출한 보고서(생애이력시스템 [점검보고서 출력] 본문 PDF)에서 소항목마다 글·참고 사진을 뽑음(2026-10-30 사용자 "우리프라자를 기준으로
해당 항목 샘플 참고사진 보여주기", "AI 분석 내용이 수기로 작성된 보고서에 비해 너무 부족").

쓰는 법: python -I server/scripts/make_blcm_samples.py <본문 PDF> <참고 사진 폴더> [견본 이름]
  예) python -I server/scripts/make_blcm_samples.py report.pdf "data/_건축물관리점검/_참고사진" 우리프라자
  → server/blcm/samples.json {code: {from, ilglt, perf, basis, rm, photos: [{n, caption}]}} + 사진 폴더/{code}_{n}.jpg.
  글은 PDF 글자에 띄어쓰기가 없어 글자 사이 간격으로 되살림(글자 크기의 0.18 넘으면 띄움), 칸 안 줄바꿈은 붙임.
  사진 = 현황사진 칸 안 그림마다 바로 아래 설명 글(같은 칸). 다른 보고서로 바꾸면 다시 돌림 — 프로젝트 모듈을 안 씀(-I로 돌림, 받은 파일은 따로 둠)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parents[1] / "blcm" / "samples.json"
ITEMS = Path(__file__).resolve().parents[1] / "blcm" / "items.json"
CODE = re.compile(r"^\s*-\s*\d+\s*-\s*\n(3\.[1-5]\.\d+)\n")
sq = lambda x: re.sub(r"[\s·ㆍ・‧․,()\-]", "", x or "")  # noqa: E731
LABELS = {"개선방안에대한의견": "op", "개선방안에대한근거및관련법령등": "basis", "비고": "rm", "현황사진": "photo"}


def spaced(page: pymupdf.Page, rect: pymupdf.Rect) -> list[tuple[float, float, float, str]]:
    """칸 안 줄 [(y0, x0, y1, 글)] — 글자 사이 간격으로 띄어쓰기."""
    out = []
    for b in page.get_text("rawdict", clip=rect)["blocks"]:
        for ln in b.get("lines", []):
            s, prev = "", None
            for sp in ln["spans"]:
                for c in sp["chars"]:
                    cx, cy = (c["bbox"][0] + c["bbox"][2]) / 2, (c["bbox"][1] + c["bbox"][3]) / 2
                    if not (rect.x0 - 1 <= cx <= rect.x1 + 1 and rect.y0 - 1 <= cy <= rect.y1 + 1):
                        continue
                    if prev is not None and c["bbox"][0] - prev["bbox"][2] > sp["size"] * 0.18:
                        s += " "
                    s += c["c"]
                    prev = c
            if s.strip():
                out.append((ln["bbox"][1], ln["bbox"][0], ln["bbox"][3], s.strip()))
    out.sort()
    return out


def joined(lines: list) -> str:
    """칸 안 줄 → 한 글(줄바꿈 자리는 붙임 — 사이트가 글자 단위로 끊음)."""
    return "".join(t for _, _, _, t in lines).strip()


def item_pages(doc: pymupdf.Document) -> dict[str, list[int]]:
    pages: dict[str, list[int]] = {}
    cur = None
    for i in range(doc.page_count):
        m = CODE.match(doc[i].get_text())
        if m:
            cur = m.group(1)
            pages[cur] = []
        if cur:
            pages[cur].append(i)
    return pages


def read_item(doc: pymupdf.Document, pns: list[int]) -> dict:
    got = {"ilglt": "", "perf": "", "basis": "", "rm": "", "photos": [], "name": ""}
    for pn in pns:
        page = doc[pn]
        for t in page.find_tables().tables:
            rows = t.rows
            last = None  # 이름 칸이 여러 줄에 걸치면(현황사진 사진 여러 장) 아래 줄은 이름 칸이 None — 위 이름을 이어 씀
            for ri, r in enumerate(rows):
                cells = [pymupdf.Rect(c) for c in r.cells if c]
                if not cells:
                    continue
                texts = [sq(joined(spaced(page, c))) for c in cells]
                if "점검소항목" in texts[:-1] and not got["name"]:
                    got["name"] = joined(spaced(page, cells[texts.index("점검소항목") + 1]))
                if r.cells[0] is None and last == "photo":
                    key, val = "photo", cells[-1]
                else:
                    key = LABELS.get(texts[0])
                    last = key
                    if key is None or len(cells) < 2:
                        continue
                    val = cells[1]
                if key == "op":  # <개선사항(위법)> 다음 줄(칸 하나) = <성능개선사항>
                    got["ilglt"] = joined(spaced(page, val))
                    nxt = rows[ri + 1] if ri + 1 < len(rows) else None
                    nc = [pymupdf.Rect(c) for c in nxt.cells if c] if nxt else []
                    if nc and not LABELS.get(sq(joined(spaced(page, nc[0])))):
                        got["perf"] = joined(spaced(page, nc[-1]))
                elif key in ("basis", "rm"):
                    got[key] = joined(spaced(page, val))
                elif key == "photo":
                    imgs = sorted((pymupdf.Rect(x["bbox"]) & val for x in page.get_image_info()), key=lambda b: (round(b.y0), b.x0))
                    lines = spaced(page, val)
                    for b in imgs:
                        if b.width < 60 or b.height < 40:
                            continue
                        cap = [t for y0, x0, y1, t in lines if b.y1 - 2 <= y0 <= b.y1 + 30 and x0 < b.x1 and x0 + 20 > b.x0 - 60]
                        got["photos"].append({"rect": b, "page": pn, "caption": " ".join(cap)[:60]})
    return got


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    pdf, photo_dir = Path(sys.argv[1]), Path(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) > 3 else pdf.stem
    ours = json.loads(ITEMS.read_text(encoding="utf-8"))
    by_name = {sq(it["name"]): it["code"] for it in ours}
    codes = {it["code"] for it in ours}
    doc = pymupdf.open(pdf)
    photo_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for rcode, pns in item_pages(doc).items():
        got = read_item(doc, pns)
        name = sq(got["name"])
        code = by_name.get(name) or (rcode if rcode in codes and not name else None)
        if code is None:  # 보고서 이름이 다름(세부기준1 = 1-1·1-2 등) — 이름이 들어간 항목, 없으면 번호
            code = next((c for n, c in by_name.items() if name and (name in n or n in name)), rcode if rcode in codes else None)
        if code is None:
            print("짝 없음", rcode, got["name"])
            continue
        photos = []
        for n, ph in enumerate(got["photos"], 1):
            pix = doc[ph["page"]].get_pixmap(clip=ph["rect"], dpi=110)
            (photo_dir / f"{code}_{n}.jpg").write_bytes(pix.tobytes("jpg", jpg_quality=80))
            photos.append({"n": n, "file": f"{code}_{n}.jpg", "caption": ph["caption"]})
        out[code] = {"from": label, "name": got["name"], **{k: got[k] for k in ("ilglt", "perf", "basis", "rm")}, "photos": photos}
        print(code, got["name"][:14], "사진", len(photos), "| 위법", len(got["ilglt"]), "성능", len(got["perf"]), "근거", len(got["basis"]), "비고", len(got["rm"]))
    for it in ours:  # 보고서가 한데 묶은 항목(세부기준 1 = 1-1·1-2, 2 = 2-1~2-3) — 이름이 앞부분으로 맞는 견본을 같이 씀
        if it["code"] in out:
            continue
        mine = sq(it["name"])
        src = max((c for c, v in out.items() if sq(v["name"]) and mine.startswith(sq(v["name"]))), key=lambda c: len(sq(out[c]["name"])), default=None)
        if src:
            out[it["code"]] = {**out[src], "same_as": src}
            print(it["code"], it["name"], "← 견본", src)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("항목", len(out), "→", OUT)


if __name__ == "__main__":
    main()
