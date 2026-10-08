"""완수계 붙임 5번 "검사 및 납품조서"(2026-10-08 형·사용자) — 발주처 한글 양식(가로 1장)을 그대로 채워 hwpx로, 한글로 PDF(hwp_queue).

양식: data/templates/검사납품조서_양식.hwpx (받은 hwp를 한글에서 HWPX로 저장한 것, 원본은 검사납품조서_원본.hwp — git 제외)
- 위: 용역명·계약번호·납품기한(= 준공일, 완수계와 같은 값)·납품장소(발주처)·납품일자(= 만든 날/발송일). 주소·상호·대표자는 양식 그대로,
  도장은 "넣기/빼기"를 따름.
- 표: 붙임 완수내역서 PDF의 값 그대로 — "원래 서류와 1원도 안 틀리게"(사용자). 계약 = "산출근거(계약서)" 장, 준공 = "(완수시)" 장의 횟수,
  산출내역서 표의 계약금액·완수금액(용역비 = 공급가액, 부가세, 합계 = 계). 소계 = 공급가액 + 부가세(내역서 "산출금액 총계").
  단가 = 계약 공급가액 ÷ 계약 횟수(1원 반올림). 증감은 준공 − 계약(같으면 공란), 증감 수량은 계 줄에만(형). 내역서에 없으면 계에서 역산.
- 아래(검사대장·검사일자·검사관·출납관…)는 발주처가 쓰는 칸이라 공란 — 검사일자·납품일자의 연도만 만든 해(사용자).
"""
from __future__ import annotations

import datetime
import re
import zipfile
from pathlib import Path

import pymupdf
from lxml import etree

from core.db import BASE_DIR

TEMPLATE = BASE_DIR / "data" / "templates" / "검사납품조서_양식.hwpx"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
KEYS = ("qty", "supply", "vat", "total", "done_qty", "done_supply", "done_vat", "done_total")
_NUM = re.compile(r"-?\d{1,3}(?:,\d{3})+")
_QTY = re.compile(r"기술지도\s*횟수\s*([\d,]+)\s*회")


# ---------- 완수내역서 PDF 읽기 ----------
def _int(s: str) -> int:
    return int(s.replace(",", ""))


def read_done_list(paths: list[Path]) -> dict | None:
    """완수내역서 PDF(들) → 표 값. 하나도 못 읽으면 None. 못 읽은 칸은 None(normalize가 채움)."""
    pages: list[str] = []
    for p in paths:
        try:
            with pymupdf.open(p) as doc:
                pages += [pg.get_text() for pg in doc]
        except Exception:  # noqa: BLE001 — 깨진 파일은 건너뜀
            continue
    out: dict = {k: None for k in KEYS}
    # 산출내역서 표: 용역비(계약·완수) → 부가세(계약·완수) → 합계(계약·완수). 공급가 + 부가세 ≈ 합계(단수조정 10원 안쪽)로 맞는 6개를 찾는다
    for text in pages:
        if "완수금액" not in text or "계약금액" not in text:
            continue
        nums = [_int(n) for n in _NUM.findall(text)]
        for i in range(len(nums) - 5):
            s, ds, v, dv, t, dt = nums[i:i + 6]
            if abs(s + v - t) <= 10 and abs(ds + dv - dt) <= 10 and v * 9 < s < v * 11:
                out.update(supply=s, done_supply=ds, vat=v, done_vat=dv, total=t, done_total=dt)
                break
        if out["supply"] is not None:
            break
    # 횟수: "<산출근거>(계약서)" 장 / "(완수시)" 장
    for text in pages:
        m = _QTY.search(text)
        if not m:
            continue
        key = "done_qty" if "완수시" in text else "qty"
        if out[key] is None:
            out[key] = _int(m.group(1))
    if all(v is None for v in out.values()):
        return None
    return out


# ---------- 값 맞추기 ----------
def _round(x: float) -> int:
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def normalize(ins: dict | None) -> dict:
    """빈 칸 채우기 — 계만 있으면 역산(공급가 = 계 ÷ 1.1, 부가세 = 계 − 공급가), 준공이 통째로 비면 계약과 같게(형: 기본은 계약 = 준공)."""
    d = {k: (None if (ins or {}).get(k) in (None, "") else int((ins or {})[k])) for k in KEYS}
    for pre in ("", "done_"):
        s, v, t = d[pre + "supply"], d[pre + "vat"], d[pre + "total"]
        if s is None and t is not None:
            s = _round(t / 1.1)
            v = t - s if v is None else v
        if s is not None and v is None:
            v = s // 10
        if t is None and s is not None:
            t = s + v
        d[pre + "supply"], d[pre + "vat"], d[pre + "total"] = s, v, t
    if all(d["done_" + k] is None for k in ("qty", "supply", "vat", "total")):
        for k in ("qty", "supply", "vat", "total"):
            d["done_" + k] = d[k]
    if d["done_qty"] is None:
        d["done_qty"] = d["qty"]
    return d


def unit_price(d: dict) -> int | None:
    return _round(d["supply"] / d["qty"]) if d.get("supply") is not None and d.get("qty") else None


def missing(d: dict) -> list[str]:
    names = {"qty": "계약 횟수", "supply": "계약 공급가액", "total": "계약 금액(계)", "done_qty": "준공 횟수", "done_total": "준공 금액(계)"}
    return [label for k, label in names.items() if d.get(k) is None]


# ---------- 한글 양식 채우기 ----------
def _fmt(n: int | None, unit: str = "") -> str:
    return "" if n is None else f"{n:,}{unit}"


def _diff(a: int | None, b: int | None, unit: str = "") -> str:
    if a is None or b is None or a == b:
        return ""
    return f"{b - a:,}{unit}"


def _set(tc, text: str) -> None:
    """칸 글자 바꾸기 — 첫 문단의 첫 글자 모양으로 새로 쓰고, 줄 배치 캐시(linesegarray)는 지워 한글이 다시 잡게. 수식 칸도 글자로."""
    p = tc.find(".//hp:subList/hp:p", NS)
    run = p.find("hp:run", NS)
    char = run.get("charPrIDRef") if run is not None else "0"
    for el in p.findall("hp:run", NS) + p.findall("hp:linesegarray", NS):
        p.remove(el)
    new = etree.SubElement(p, f"{{{HP}}}run", charPrIDRef=char)
    if text:
        etree.SubElement(new, f"{{{HP}}}t").text = text


def _cells(tbl) -> dict[tuple[int, int], object]:
    out = {}
    for tc in tbl.iter(f"{{{HP}}}tc"):
        a = tc.find("hp:cellAddr", NS)
        out[(int(a.get("rowAddr")), int(a.get("colAddr")))] = tc
    return out


def _ymd(d: datetime.date | None) -> str:
    return f"{d.year}년 {d.month:02d}  월  {d.day:02d}   일" if d else "      년     월     일"


def build(out: Path, *, title: str, contract_no: str, client: str, due: datetime.date | None, made: datetime.date,
          seal: bool, ins: dict, template: Path = TEMPLATE) -> None:
    d = normalize(ins)
    with zipfile.ZipFile(template) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]
    sec_name = "Contents/section0.xml"
    xml = dict((i.filename, b) for i, b in items)[sec_name]
    root = etree.fromstring(xml)
    tbls = root.findall(".//hp:tbl", NS)
    if len(tbls) != 4:
        raise RuntimeError(f"검사 및 납품조서 양식 모양이 바뀌었습니다(표 {len(tbls)}개) — 양식을 확인하세요.")
    head, table, foot = _cells(tbls[1]), _cells(tbls[2]), _cells(tbls[3])

    _set(head[(0, 0)], f"용역명 :{title}")
    _set(head[(0, 3)], f"납품일자 : {_ymd(made)}")
    _set(head[(1, 0)], f"계약번호 : {contract_no}")
    _set(head[(2, 0)], f"납품기한 : {_ymd(due)}")
    _set(head[(3, 0)], f"납품장소 : {client}")
    if not seal:  # 도장 그림을 빼면 칸 가운데로 내려가므로 위에 붙여 원래 자리 그대로
        for pic in head[(3, 3)].findall(".//hp:pic", NS):
            pic.getparent().remove(pic)
        head[(3, 3)].find("hp:subList", NS).set("vertAlign", "TOP")

    sub, dsub = (None if d["supply"] is None else d["supply"] + d["vat"]), (None if d["done_supply"] is None else d["done_supply"] + d["done_vat"])
    rows = {  # 줄: (계약 금액, 준공 금액)
        2: (d["supply"], d["done_supply"]), 3: (d["vat"], d["done_vat"]), 4: (sub, dsub), 5: (d["total"], d["done_total"]),
    }
    _set(table[(2, 0)], title)
    _set(table[(2, 3)], _fmt(unit_price(d)))
    for r, (a, b) in rows.items():
        _set(table[(r, 5)], _fmt(a))
        _set(table[(r, 7)], _fmt(b))
        _set(table[(r, 9)], _diff(a, b))
    for r in (2, 5):  # 수량은 품명 줄·계 줄
        _set(table[(r, 4)], _fmt(d["qty"], "회"))
        _set(table[(r, 6)], _fmt(d["done_qty"], "회"))
    _set(table[(2, 8)], "")
    _set(table[(5, 8)], _diff(d["qty"], d["done_qty"], "회"))  # 증감 수량은 계 줄에만(형)

    _set(foot[(1, 1)], f"검사일자 : {made.year} 년   월    일")
    _set(foot[(1, 3)], f"납품일자 : {made.year} 년    월    일")

    # 줄 배치 캐시는 문서 전체에서 지운다 — 한글 밖에서 글자를 바꾼 문단이 캐시와 안 맞으면 보안 설정에 따라 "변조 가능성"으로 막음
    # (core/report_builder_hwpx._strip_line_seg_arrays와 같은 이유). 미리보기 글자는 실제 내용으로, 미리보기 그림은 지움(같은 파일 설명 참고)
    for el in list(root.iter(f"{{{HP}}}linesegarray")):
        el.getparent().remove(el)
    plain = "\r\n".join("".join(t.text or "" for t in p.iter(f"{{{HP}}}t")) for p in root.iter(f"{{{HP}}}p"))
    parts = {sec_name: etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
             "Preview/PrvText.txt": plain.encode("utf-8")}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as zout:
        for info, data in items:
            if info.filename == "Preview/PrvImage.png":
                continue
            zout.writestr(info, parts.get(info.filename, data), compress_type=info.compress_type)
    tmp.replace(out)
