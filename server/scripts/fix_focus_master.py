"""정기안전점검 원본(회사 원본)의 결과표 "라. 참고사항"을 민재형이 고친 양식(줄마다 [항목 | 내용] 두 칸)으로 바꾼다(2026-10-30).

- 사용: python -m server.scripts.fix_focus_master <민재형이 고친 한글.hwpx> [--master 정기|정밀]
- 고친 파일의 결과표에서 "라. 참고사항" 아래 줄들(항목 칸 span3 + 내용 칸 span6 × 3줄)을 통째로 가져와 원본의 옛 한 칸(○ 세 줄) 줄 자리에 넣는다.
  고친 파일은 한글이 모양 번호를 다시 매겨서 번호가 우리 원본과 다름 → 줄이 쓰는 문단 모양·테두리 정의를 원본 header.xml 끝에 새 번호로 더하고 줄 안 번호도 바꿈.
- 원본은 같은 폴더 _지난원본에 시각을 붙여 먼저 백업. 이미 두 칸 양식이면 아무것도 안 함.
- 채우는 쪽: report_build가 "중점 점검부위" 줄의 내용 칸(오른쪽)에 차기 점검 부위를 넣음.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import re
import shutil
import sys
import zipfile

from lxml import etree

from server.sitok import master
from server.sitok import report_build as rb

HP = rb.HP
HH = "http://www.hancom.co.kr/hwpml/2011/head"


def _result_table(root):
    for t in root.iter(f"{{{HP}}}tbl"):
        txt = re.sub(r"\s", "", "".join(t.itertext()))
        if "참고사항" in txt and "책임" in txt and "일반현황" in txt:
            return t
    return None


def _label_row(tbl) -> int | None:
    for i, tr in enumerate(tbl.findall(f"{{{HP}}}tr")):
        if re.sub(r"\s", "", "".join(tr.itertext())).startswith("라.참고사항"):
            return i
    return None


def _defs(header_root, tag: str) -> dict:
    return {el.get("id"): el for el in header_root.iter(f"{{{HH}}}{tag}")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixed", help="민재형이 고친 한글(.hwpx)")
    ap.add_argument("--master", default="정기")
    a = ap.parse_args()
    mpath = master.master_path(a.master)
    with zipfile.ZipFile(a.fixed) as z:
        up_items = {i.filename: z.read(i.filename) for i in z.infolist()}
    with zipfile.ZipFile(mpath) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    sec = next(n for n in sorted(up_items) if re.fullmatch(r"Contents/section\d+\.xml", n) and _result_table(etree.fromstring(up_items[n])) is not None)
    up_root = etree.fromstring(up_items[sec])
    up_tbl = _result_table(up_root)
    up_rows = up_tbl.findall(f"{{{HP}}}tr")
    k = _label_row(up_tbl)
    new_rows = up_rows[k + 1:]
    if not new_rows or any(len(r.findall(f"{{{HP}}}tc")) != 2 for r in new_rows):
        print("고친 파일 참고사항 아래가 두 칸 줄이 아닙니다 — 양식을 확인하세요.")
        return 1

    name = next(i.filename for i, _ in items if i.filename == sec)
    root = etree.fromstring(next(d for i, d in items if i.filename == name))
    tbl = _result_table(root)
    rows = tbl.findall(f"{{{HP}}}tr")
    j = _label_row(tbl)
    old = rows[j + 1:]
    if all(len(r.findall(f"{{{HP}}}tc")) == 2 for r in old) and old:
        print("원본이 이미 두 칸 양식입니다 — 바꾸지 않았습니다.")
        return 0

    # 모양 정의 이식 — 새 줄이 쓰는 문단 모양·테두리(+ 그 안에서 가리키는 테두리)를 원본 header.xml 끝에 새 번호로
    up_h, our_h = etree.fromstring(up_items["Contents/header.xml"]), etree.fromstring(next(d for i, d in items if i.filename == "Contents/header.xml"))
    up_para, up_bf = _defs(up_h, "paraPr"), _defs(up_h, "borderFill")
    our_para_parent = next(our_h.iter(f"{{{HH}}}paraProperties"))
    our_bf_parent = next(our_h.iter(f"{{{HH}}}borderFills"))
    next_id = {"paraPr": max(int(x.get("id")) for x in our_para_parent) + 1, "borderFill": max(int(x.get("id")) for x in our_bf_parent) + 1}
    mapped: dict[tuple[str, str], str] = {}

    def port(kind: str, old_id: str) -> str:
        key = (kind, old_id)
        if key in mapped:
            return mapped[key]
        src = (up_para if kind == "paraPr" else up_bf)[old_id]
        el = copy.deepcopy(src)
        nid = str(next_id[kind])
        next_id[kind] += 1
        mapped[key] = nid
        el.set("id", nid)
        for sub in el.iter(f"{{{HH}}}border"):  # 문단 모양 안 테두리 번호
            if sub.get("borderFillIDRef") and kind == "paraPr":
                sub.set("borderFillIDRef", port("borderFill", sub.get("borderFillIDRef")))
        (our_para_parent if kind == "paraPr" else our_bf_parent).append(el)
        return nid

    ported = []
    for tr in new_rows:
        tr = copy.deepcopy(tr)
        for el in tr.iter():
            if el.get("paraPrIDRef") is not None:
                el.set("paraPrIDRef", port("paraPr", el.get("paraPrIDRef")))
            if el.get("borderFillIDRef") is not None and el.tag == f"{{{HP}}}tc":
                el.set("borderFillIDRef", port("borderFill", el.get("borderFillIDRef")))
        for seg in list(tr.iter(f"{{{HP}}}linesegarray")):  # 줄 배치는 한글이 다시 계산
            seg.getparent().remove(seg)
        ported.append(tr)
    our_para_parent.set("itemCnt", str(len(our_para_parent)))
    our_bf_parent.set("itemCnt", str(len(our_bf_parent)))

    old_h = sum(int(r.find(f"{{{HP}}}tc/{{{HP}}}cellSz").get("height") or 0) for r in old)
    new_h = sum(int(r.find(f"{{{HP}}}tc/{{{HP}}}cellSz").get("height") or 0) for r in ported)
    for r in old:
        tbl.remove(r)
    for n, tr in enumerate(ported):
        for tc in tr.findall(f"{{{HP}}}tc"):
            tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(j + 1 + n))
        tbl.append(tr)
    tbl.set("rowCnt", str(j + 1 + len(ported)))
    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None:
        sz.set("height", str(int(sz.get("height") or 0) + new_h - old_h))

    backup_dir = mpath.parent / "_지난원본"
    backup_dir.mkdir(exist_ok=True)
    shutil.copy2(mpath, backup_dir / f"{mpath.stem}_{datetime.datetime.now():%Y%m%d_%H%M%S}{mpath.suffix}")
    tmp = mpath.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w") as zo:
        for info, d in items:
            if info.filename == name:
                d = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename == "Contents/header.xml":
                d = etree.tostring(our_h, xml_declaration=True, encoding="UTF-8", standalone=True)
            zo.writestr(info, d)
    tmp.replace(mpath)
    print(f"원본 바꿈: {mpath.name} — 참고사항 {len(old)}줄(한 칸) → {len(ported)}줄(항목|내용 두 칸), 문단 모양 {sum(1 for k in mapped if k[0]=='paraPr')}개·테두리 {sum(1 for k in mapped if k[0]=='borderFill')}개 이식")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
