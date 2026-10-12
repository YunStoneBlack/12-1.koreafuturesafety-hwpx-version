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

TITLE = "2026년 상반기 광숭초등학교 제3종시설물 정기안전점검 용역"  # 원본 용역명 — 만들 때 이 회차 용역명으로 통째로 바뀜
NAME = "광숭초등학교 교사동"  # 원본 시설물명(관리주체명은 "광숭초등학교")
TEXT_FIXES = [  # (틀린 글, 고친 글) — 광숭초 2026 상반기 보고서에서 찾은 것 + 이름 모양 맞추기(만들 때 빠짐없이 바뀌게)
    ("2024년 하반기 안산대학교 정기안전점검 용역", TITLE),
    ("2026년 광숭초등학교 상반기 제3종시설물 정기안전점검 용역", TITLE),  # 머리글 — 연도·반기 사이에 이름
    ("2026년도 상반기 제3종시설물 정기안전 점검 용역", TITLE),  # 부록 과업수행조직
    ("제2종에 해당하는 업무시설 및 근린생활시설", "제3종에 해당하는 교육연구시설"),
    ("해당없는 것을 확인되었다", "해당없는 것으로 확인되었다"),
    ("박리, 바락", "박리, 박락"),
    ("광숭초등학교정기안전점검 결과표", f"{NAME} 정기안전점검 결과표"),
]
NAME_ALONE = re.compile(r"^(\s*(?:제\s*1\s*장\.?\s*)?)교사동(\s*\d*\s*)$")  # 장 제목·목차 "제 1장. 교사동" → 시설물명 전체
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
            s = NAME_ALONE.sub(lambda m: f"{m[1]}{NAME}{m[2]}", s)
            if s != pc.text:
                pc.text = s
                n += 1
    for p in root.iter(f"{{{HP}}}p"):  # 머리글 용역명이 글자 모양별로 조각나 있으면(만들 때 통째 바꾸기가 안 걸림) 한 조각으로
        own = [t for t in p.iter(rb.T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p]
        if len(own) > 1 and " ".join("".join(rb._full(t) for t in own).split()) == TITLE:
            rb._set_para(p, TITLE, in_table=True)
            n += 1
    cells = rb._find_result_table([root])  # 결과표 용역명 칸 "…광숭초등학교 ⏎ 제3종시설물 정기안전점검용역" → 한 모양
    if cells is not None and (1, 1) in cells and rb._cell_text(cells[(1, 1)]).replace("\n", " ") != TITLE:
        rb._set_lines(cells[(1, 1)], [TITLE])
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


# ---------- 종별 손질(만들 때마다) ----------
DROP = {"2종": ("안전등급평가및결과", "치장벽돌"), "3종일반": ("치장벽돌",), "3종학교": ()}
HEAD = re.compile(r"^\s*1\.(\d+)\s+(.+?)\s*$")


def _tops(root) -> list:
    return [p for p in root if p.tag == f"{{{HP}}}p"]


def _appendix_start(tops) -> int:
    """시설물편 구역에서 부록 간지가 시작하는 문단 번호(없으면 끝)."""
    for i, p in enumerate(tops):
        if any("부록.1" in rb._cell_text(c).replace(" ", "") for t in p.iter(f"{{{HP}}}tbl") for c in rb._cells(t).values()):
            return i
    return len(tops)


def _renum(p, old: int, new: int, in_table: bool = False) -> None:
    """문단(또는 칸 안 문단)의 맨 앞 "1.old" → "1.new"(1.old.x도) — 글자 모양은 그대로, 그 조각만."""
    ts = [t for t in p.iter(rb.T) if (next(t.iterancestors(f"{{{HP}}}p"), None) is p if in_table
                                      else next(t.iterancestors(f"{{{HP}}}tbl"), None) is None)]
    for t in ts:
        for pc in rb._pieces(t):
            if re.search(rf"1\.{old}(?=[\s.]|$)", pc.text):
                pc.text = re.sub(rf"1\.{old}(?=[\s.]|$)", f"1.{new}", pc.text, count=1)
                return


PRIVATE_TERMS = [("학교별 3부", "1부"), ("총괄 보고서(인쇄물) : 3부", "총괄 보고서(인쇄물) : 1부"), ("계약일로부터 3일 이내", "계약일로부터 7일 이내")]


def _appendix_terms(root, school: bool, private: bool) -> None:
    """부록 과업지시서·과업수행계획서 문구(민재형 10/12): 민간 = 보고서 1부·착수계 7일 이내, 적용법규 "제3종시설물 안전등급 평가 매뉴얼"은 학교만."""
    if private:
        for t in root.iter(rb.T):
            for pc in rb._pieces(t):
                s = pc.text
                for o, nw in PRIVATE_TERMS:
                    s = s.replace(o, nw)
                if s != pc.text:
                    pc.text = s
    if not school:
        for p in _tops(root):
            t = rb._top_text(p)
            if re.match(r"^\s*라\.\s*제3종시설물\s*안전등급\s*평가\s*매뉴얼", t):
                nxt = p.getnext()
                root.remove(p)
                if nxt is not None and re.match(r"^\s*마\.\s*기타\s*관련법규", rb._top_text(nxt)):
                    _sub_once(nxt, r"마\.", "라.")
                break


def _sub_once(p, pat: str, repl: str) -> None:
    for t in p.iter(rb.T):
        for pc in rb._pieces(t):
            if re.search(pat, pc.text):
                pc.text = re.sub(pat, repl, pc.text, count=1)
                return


def prepare(src: Path, kind: str, dest: Path, private: bool = True) -> list[str]:
    """원본 → 이 시설물 종별의 틀(dest): 학교 전용 절 빼기(2종 = 1.5 18항목 안전등급 평가·1.7 치장벽돌, 3종 일반 = 1.7) → 시설물편 절 번호·
    목차·장 표지 소목차를 실제 절로 다시, 2종 표지·책등 "3종시설" → "2종시설", 부록 문구(민간 1부·7일, 평가 매뉴얼은 학교만). 안내를 돌려줌."""
    drop = DROP.get(kind, ())
    notes: list[str] = []
    with zipfile.ZipFile(src) as zin:
        secs = rb._sections(zin)
        roots = {n: etree.fromstring(zin.read(n)) for n in secs}
        for n in secs[2:]:
            _appendix_terms(roots[n], kind == "3종학교", private)
        body = roots[secs[2]]
        tops = _tops(body)
        stop = _appendix_start(tops)
        heads = [(i, int(m[1]), m[2]) for i, p in enumerate(tops[:stop]) if (m := HEAD.match(rb._top_text(p)))]
        keep, gone = [], []
        for k, (i, num, title) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else stop
            if any(d in re.sub(r"\s", "", title) for d in drop):
                for p in tops[i:end]:
                    p.getparent().remove(p)
                gone.append(num)
            else:
                keep.append((num, title, tops[i:end]))
        mapping = {old: new for new, (old, _, _) in enumerate(keep, 1)}
        for old, _, block in keep:
            if mapping[old] != old:
                for p in block:
                    if re.match(rf"^\s*1\.{old}(?=[\s.])", rb._top_text(p)):
                        _renum(p, old, mapping[old])
        final = [f"1.{mapping[old]} {title}" for old, title, _ in keep]
        # 장 표지 소목차(시설물편 첫 표의 "1.1 …" 칸들)
        first = next((t for p in _tops(body)[:3] for t in p.iter(f"{{{HP}}}tbl")), None)
        if first is not None:
            cells = rb._cells(first)
            col = next((c for (r, c), tc in sorted(cells.items()) if re.match(r"^1\.1\s", rb._cell_text(tc))), None)
            if col is not None:
                start = next(r for (r, c), tc in sorted(cells.items()) if c == col and re.match(r"^1\.1\s", rb._cell_text(tc)))
                slots = [cells[(r, c)] for (r, c) in sorted(cells) if c == col and r >= start]
                for k, tc in enumerate(slots):
                    lines = final[k:k + 1] if k < len(slots) - 1 else final[k:]
                    rb._set_lines(tc, lines or [""])
                if len(final) > len(slots):
                    notes.append("장 표지 소목차 칸이 모자라 마지막 칸에 두 줄로 넣었습니다")
        # 목차(첫 구역) — "Ⅱ. 시설물편" 뒤 "1.x 제목쪽" 줄
        front = roots[secs[0]]
        on = False
        for p in _tops(front):
            t = rb._top_text(p).strip()
            if t.startswith("Ⅱ"):
                on = True
                continue
            if on and t.startswith(("▣", "부록")):
                break
            m = re.match(r"^1\.(\d+)\s*(.+)$", t) if on else None
            if not m:
                continue
            old = int(m[1])
            if old in gone:
                p.getparent().remove(p)
            elif mapping.get(old, old) != old:
                _renum(p, old, mapping[old])
        if kind == "2종":  # 책등 "제 / 3종시설" 칸만(용역명 안 "제3종시설물"은 만들 때 용역명째 바뀜 — 여기서 바꾸면 머리글 용역명과 어긋남)
            for t in front.iter(rb.T):
                for pc in rb._pieces(t):
                    if re.fullmatch(r"\s*3종시설\s*", pc.text):
                        pc.text = pc.text.replace("3종시설", "2종시설")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename in roots:
                    data = etree.tostring(roots[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True)
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    return notes


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
