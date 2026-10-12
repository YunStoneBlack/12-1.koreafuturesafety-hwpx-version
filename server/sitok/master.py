"""시특법 회사 원본 템플릿(2026-10-12 — 사용자·민재형 "판 다시 잡기" ③).

모든 회차를 회사 원본 하나로 만든다(지난 보고서를 통째로 복사하면 오타·복붙 오류가 대물림). 원본 = 학교(3종) 보고서 — 상태평가(1.5 18항목)와
치장벽돌(1.7)이 다 있는 것. 3종 일반은 치장벽돌만, 2종은 상태평가·치장벽돌을 빼서 쓴다(민재형: 검토는 한 번만). 지난 보고서는 데이터만 가져온다.

- 원본 파일: data/_시특법/_회사템플릿/정기안전점검_원본.hwpx(바꾸면 옛것은 같은 폴더 _지난원본/에 날짜 붙여 보관). 설정 탭에서 받기·올리기(형 검토).
- make_from(): 처음 원본 만들기 — 광숭초 2026 상반기 보고서에서 복붙 흔적 고치고(안산대학교 머리글·1.2.6 "제2종 업무시설"·"바락"·"해당없는 것을
  확인되었다") 1.3을 평택 방식으로(6) 공중이 이용하는 부위 및 부대시설 → 7) 기타시설 → 8) 외관조사 결과의 분석, 결과의 분석 표에 기타시설 줄).
  같은 파일 안의 문단·표를 복제하므로 한글 서식 번호(header.xml)가 그대로 맞음.
"""
from __future__ import annotations

import copy
import datetime
import io
import re
import shutil
import zipfile
from pathlib import Path

from lxml import etree

from server.sitok import report_build as rb

HP = rb.HP

TEXT_FIXES = [  # (틀린 글, 고친 글) — 광숭초 2026 상반기 보고서에서 찾은 것
    ("2024년 하반기 안산대학교 정기안전점검 용역", "2026년 광숭초등학교 상반기 제3종시설물 정기안전점검 용역"),
    ("제2종에 해당하는 업무시설 및 근린생활시설", "제3종에 해당하는 교육연구시설"),
    ("해당없는 것을 확인되었다", "해당없는 것으로 확인되었다"),
    ("박리, 바락", "박리, 박락"),
]
OTHER_TEXT = "본 시설물의 기타시설 점검결과 마감재 및 부착물 등 전반적으로 양호한 것으로 조사되었다."


def master_dir() -> Path:
    from server.api.routers.sitok import ROOT
    return ROOT / "_회사템플릿"


def master_path() -> Path:
    return master_dir() / "정기안전점검_원본.hwpx"


def shrink(data: bytes, side: int = 1800, min_bytes: int = 600_000) -> bytes:
    """원본 안 큰 그림(BMP 무압축 등)을 JPG로 줄임 — 광숭초 보고서 그대로면 283MB(그림 279MB). 그림 id는 그대로, 파일 이름·형식만(content.hpf도)."""
    from PIL import Image

    src = zipfile.ZipFile(io.BytesIO(data))
    renamed: dict[str, str] = {}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in src.infolist():
            b = src.read(info.filename)
            name = info.filename
            if name.startswith("BinData/") and info.file_size >= min_bytes and Path(name).suffix.lower() in (".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
                try:
                    img = Image.open(io.BytesIO(b))
                    img = img.convert("RGB")
                    img.thumbnail((side, side))
                    buf = io.BytesIO()
                    img.save(buf, "JPEG", quality=88)
                    new = str(Path(name).with_suffix(".jpg")).replace("\\", "/")
                    if len(buf.getvalue()) < len(b):
                        b, renamed[name] = buf.getvalue(), new
                        name = new
                except Exception:  # noqa: BLE001 — 못 여는 그림은 그대로
                    pass
            if info.filename == "Contents/content.hpf":
                continue
            zi = zipfile.ZipInfo(name, date_time=info.date_time)
            zout.writestr(zi, b, compress_type=zipfile.ZIP_STORED if name == "mimetype" or name.startswith("BinData/") else zipfile.ZIP_DEFLATED)
        hpf = src.read("Contents/content.hpf").decode("utf-8")
        for old, new in renamed.items():
            hpf = re.sub(rf'href="{re.escape(old)}"(\s+media-type=")[^"]*"', f'href="{new}"\\g<1>image/jpg"', hpf)
        zout.writestr("Contents/content.hpf", hpf.encode("utf-8"))
    return out.getvalue()


def install(data: bytes) -> Path:
    """새 원본 넣기(큰 그림은 줄여서) — 지금 원본은 _지난원본/에 날짜 붙여 보관."""
    data = shrink(data)
    p = master_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        old = master_dir() / "_지난원본" / f"정기안전점검_원본_{datetime.datetime.fromtimestamp(p.stat().st_mtime):%Y%m%d_%H%M%S}.hwpx"
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, old)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)
    return p


def info() -> dict:
    p = master_path()
    if not p.exists():
        return {"exists": False}
    return {"exists": True, "updated": f"{datetime.datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}", "size_mb": round(p.stat().st_size / 1e6, 1)}


CHECKS = [  # (이름, 찾는 방법) — 형이 한글에서 고쳐 올린 원본에 프로그램이 채우는 자리가 다 있는지
    ("결과표(가. 일반현황)", lambda roots, tops: rb._find_result_table(roots) is not None),
    ("1.2.6 기실시 점검결과 표", lambda roots, tops: any(rb._cell_text(rb._cells(t).get((0, 0), t)).replace(" ", "") == "점검의종류"
                                                       for r in roots for t in r.iter(f"{{{HP}}}tbl"))),
    ("1.2.7 보수·보강 이력 표", lambda roots, tops: rb._repair_table(roots) is not None),
    ("1.2.8 변경사항 표 3개", lambda roots, tops: len(rb._change_tables(roots)) >= 3),
    ("1.3 7) 기타시설", lambda roots, tops: any(re.match(r"7\)\s*기타시설", t) for t in tops)),
    ("1.3 외관조사 결과의 분석 표", lambda roots, tops: any(re.sub(r"\s", "", rb._cell_text(rb._cells(t).get((0, 0), t))) == "조사항목"
                                                        for r in roots for t in r.iter(f"{{{HP}}}tbl"))),
    ("1.4 기타 부대시설 상태조사 표", lambda roots, tops: rb._facility_table(roots) is not None),
    ("1.5 안전등급 평가 및 결과(18항목)", lambda roots, tops: rb._eval_tables(roots)[1] is not None),
    ("1.7 치장벽돌 안전점검", lambda roots, tops: any(re.match(r"1\.\d\s*.*치장벽돌", t) for t in tops)),
]


def check(hwpx: Path) -> list[str]:
    """없는 자리 이름들(다 있으면 [])."""
    with zipfile.ZipFile(hwpx) as z:
        roots = [etree.fromstring(z.read(n)) for n in rb._sections(z)]
    tops = [rb._top_text(p).strip() for r in roots for p in r if p.tag == f"{{{HP}}}p"]
    return [name for name, ok in CHECKS if not ok(roots, tops)]


def _fix_texts(root) -> int:
    n = 0
    for t in root.iter(rb.T):
        for pc in rb._pieces(t):
            s = pc.text
            for o, nw in TEXT_FIXES:
                if o in s:
                    s = s.replace(o, nw)
            if s != pc.text:
                pc.text = s
                n += 1
    return n


def _restructure_13(root) -> int:
    """1.3 — 6) 공중이 이용하는 부위 → "… 및 부대시설", 그 뒤에 7) 기타시설(제목·글·사진 표 복제), 결과의 분석 → 8), 분석 표에 기타시설 줄."""
    tops = [p for p in root if p.tag == f"{{{HP}}}p"]
    idx = {i: rb._top_text(p).strip() for i, p in enumerate(tops)}
    i6 = next((i for i, t in idx.items() if re.match(r"6\)\s*공중이\s*이용하는\s*부위\s*$", t)), None)
    if i6 is None:
        return 0
    i8 = next(i for i in range(i6 + 1, len(tops)) if re.match(r"\d\)\s*외관조사\s*결과의\s*분석", idx[i]))
    block = tops[i6:i8]  # 제목·글·사진 표(사이 빈 문단 포함)
    rb._set_para(block[0], "6) 공중이 이용하는 부위 및 부대시설")
    clones = [copy.deepcopy(p) for p in block]
    for q in clones:
        rb._new_ids(q)
    rb._set_para(clones[0], "7) 기타시설")
    text_p = next((q for q in clones[1:] if rb._top_text(q).strip() and not list(q.iter(f"{{{HP}}}tbl"))), None)
    if text_p is not None:
        rb._set_para(text_p, OTHER_TEXT)
    for q in clones:
        for tbl in q.iter(f"{{{HP}}}tbl"):
            cells = rb._cells(tbl)
            if (0, 0) in cells and "사진 현황" in rb._cell_text(cells[(0, 0)]):
                rb._set_lines(cells[(0, 0)], ["  ■ 기타시설 사진 현황:"])
                for (r, c), tc in cells.items():  # 사진 아래 설명 칸 "-", 사진 없던 칸("해당없음")은 비움
                    if r > 0 and next(tc.iter(f"{{{HP}}}pic"), None) is None:
                        rb._set_lines(tc, ["" if "해당없음" in rb._cell_text(tc) else "-"])
    last = block[-1]
    for q in clones:
        last.addnext(q)
        last = q
    rb._set_para(tops[i8], "8) 외관조사 결과의 분석")
    for tbl in root.iter(f"{{{HP}}}tbl"):  # 결과의 분석 표(조사항목 | 조사결과)
        cells = rb._cells(tbl)
        if re.sub(r"\s", "", rb._cell_text(cells.get((0, 0), tbl))) != "조사항목":
            continue
        for (r, c), tc in cells.items():
            if c == 0 and re.sub(r"\s", "", rb._cell_text(tc)) == "공중이이용하는부위":
                rb._set_lines(tc, ["공중이 이용하는 부위 및 부대시설"])
        if not any("기타" in rb._cell_text(tc) for (r, c), tc in cells.items() if c == 0):
            rb._add_row(tbl)
            cells = rb._cells(tbl)
            last_r = int(tbl.get("rowCnt")) - 1
            rb._set_lines(cells[(last_r, 0)], ["기타시설"])
            rb._set_lines(cells[(last_r, 1)], [f"ㆍ{OTHER_TEXT}"])
    return 1


def _blank_other_pics(root, key: str) -> int:
    """7) 기타시설 사진 표의 그림을 흰 그림으로(공중이용 사진 복제본이 남지 않게)."""
    n = 0
    for tbl in root.iter(f"{{{HP}}}tbl"):
        cells = rb._cells(tbl)
        if (0, 0) in cells and "기타시설 사진 현황" in rb._cell_text(cells[(0, 0)]):
            for _, pic in rb._pic_slots(tbl):
                img = next(pic.iter(f"{{{rb.CORE}}}img"), None)
                if img is not None:
                    img.set("binaryItemIDRef", key)
                    n += 1
    return n


def make_from(src: Path, dest: Path) -> dict:
    """광숭초 보고서(src) → 원본 템플릿(dest). 고친 곳 수를 돌려줌."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buf, "JPEG")
    key = "sitokmaster_blank"
    out = {"text": 0, "13": 0, "pics": 0}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        secs = rb._sections(zin)
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in secs:
                root = etree.fromstring(data)
                out["text"] += _fix_texts(root)
                if info.filename == secs[2]:
                    out["13"] += _restructure_13(root)
                    out["pics"] += _blank_other_pics(root, key)
                for el in list(root.iter(f"{{{HP}}}linesegarray")):
                    el.getparent().remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename in ("Preview/PrvImage.png",):
                continue
            elif info.filename == "Contents/content.hpf":
                data = data.decode("utf-8").replace(
                    "</opf:manifest>", f'<opf:item id="{key}" href="BinData/{key}.jpg" media-type="image/jpg" isEmbeded="1"/></opf:manifest>').encode("utf-8")
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
        zout.writestr(f"BinData/{key}.jpg", buf.getvalue(), compress_type=zipfile.ZIP_STORED)
    return out
