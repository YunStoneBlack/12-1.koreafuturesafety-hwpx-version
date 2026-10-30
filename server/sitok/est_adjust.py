"""착수계 붙임 — 낙찰가 적용 내역서 만들기(2026-10-30 사용자 "현재 내역서를 수기로 수정해 올림 → 낙찰가 적용 전 내역서를 첨부하면 계약금액에 맞게
노임단가를 조정해 맞춘 내역서를 착수계에 첨부, 내려받기·미리보기(내역서만 따로)").

흐름: 올린 설계(낙찰가 적용 전) 엑셀 → LibreOffice 파이썬으로 기술자 노임단가를 계약금액이 딱 나오게(server/sitok/est_adjust_lo.py — 바꾼 칸에 딸린 칸만 다시 계산)
→ 원본 xlsx의 바뀐 칸만 고쳐 "낙찰가적용 내역서.xlsx"(서식·다른 칸 그대로, xls면 LibreOffice로 저장한 것) → 고른 시트로 PDF → 착수계 붙임 "산출내역서" 칸.
계약 폴더/낙찰가적용/: 적용전.xlsx(올린 것) · 낙찰가적용 내역서.xlsx · 낙찰가적용 내역서.pdf · meta.json."""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from core.db import DATA_DIR
from server.contract_docs import to_pdf

LO_SCRIPT = Path(__file__).with_name("est_adjust_lo.py")
PROFILE = DATA_DIR / "_시스템" / "libreoffice_uno"
DIR = "낙찰가적용"
OUT_NAME = "낙찰가적용 내역서"
_LOCK = threading.Lock()
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def lo_python() -> str:
    exe = Path(to_pdf.soffice_path()).with_name("python.exe")
    if not exe.exists():
        raise RuntimeError("LibreOffice 파이썬이 없어 내역서를 맞출 수 없습니다 — LibreOffice를 다시 설치하세요.")
    return str(exe)


def run_lo(job: dict, timeout: int = 300) -> dict:
    """LibreOffice 파이썬으로 est_adjust_lo.py 한 번(한 번에 하나)."""
    with _LOCK, tempfile.TemporaryDirectory() as tmp:
        jf = Path(tmp) / "job.json"
        jf.write_text(json.dumps({**job, "profile": str(PROFILE)}, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "SOFFICE_PATH": to_pdf.soffice_path()}
        subprocess.run([lo_python(), str(LO_SCRIPT), str(jf)], capture_output=True, timeout=timeout, env=env,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = jf.with_suffix(".out.json")
        if not out.exists():
            raise RuntimeError("내역서 계산이 끝나지 않았습니다(LibreOffice) — 다시 해 보세요.")
        return json.loads(out.read_text(encoding="utf-8"))


# ---------- 원본 xlsx의 바뀐 칸만 고치기 ----------
def _sheet_parts(z: zipfile.ZipFile) -> dict[str, str]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for s in wb.find("m:sheets", NS):
        t = rels[s.get("{%s}id" % NS["r"])]
        out[s.get("name")] = t.lstrip("/") if t.lstrip("/").startswith("xl/") else "xl/" + t.lstrip("/")
    return out


def _excel_formula(lo: str) -> str:
    """LibreOffice 수식 → 엑셀(<f> 글): 앞 = 빼고, 따옴표 밖 ; → , , $시트.$A$1 → 시트!$A$1."""
    s, out, q = lo.lstrip("="), [], False
    for ch in s:
        if ch == '"':
            q = not q
        out.append("," if ch == ";" and not q else ch)
    s = "".join(out)
    return re.sub(r"\$?('?[^'.!(),;=+\-*/&\s]+'?)\.(\$?[A-Z]+\$?\d+)", lambda m: f"{m.group(1)}!{m.group(2)}", s)


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _new_formula(ch: dict, f_text: str | None, res: dict) -> str | None:
    """바꾼 수식(엑셀 글) — 원래 엑셀 수식을 바탕으로(절사 자리·한글 금액), 노임단가는 =원래×p%."""
    rate = next((r for r in res.get("rates") or [] if r["sheet"] == ch["sheet"] and r["cell"] == ch["cell"]), None)
    if rate is not None:
        return f"{rate['before']:g}*{rate['pct']}%" if rate.get("formula") else None
    rnd = next((r for r in res.get("rounding") or [] if r["sheet"] == ch["sheet"] and r["cell"] == ch["cell"]), None)
    if rnd is not None and f_text:
        d = re.search(r"[;,]\s*(-?\d+)\)$", rnd["after"]).group(1)
        return re.sub(r",\s*-?\d+\)$", f",{d})", f_text)
    txt = next((t for t in res.get("texts") or [] if t["sheet"] == ch["sheet"] and t["cell"] == ch["cell"]), None)
    if txt is not None and f_text:
        lit = re.search(r'"([^"]*)"', txt["after"].split("CONCATENATE(", 1)[-1]).group(1) if "CONCATENATE(" in txt["after"] else None
        m = re.search(r'TEXT\((\$?[A-Z]+\$?\d+),"\[DBNum4\][^"]*"\)', f_text)
        if m and lit is not None:
            return f_text.replace(m.group(0), f'"{lit}"')
    return _excel_formula(ch["formula"]) if ch.get("formula") else None


def patch_xlsx(src: Path, dst: Path, res: dict) -> int:
    """원본 xlsx에서 바뀐 칸(값·수식)만 고쳐 dst — 나머지 XML은 한 글자도 안 바꿈. calcChain은 빼서 엑셀이 새로 만들게. → 고친 칸 수."""
    by_sheet: dict[str, list] = {}
    for ch in res.get("changed") or []:
        by_sheet.setdefault(ch["sheet"], []).append(ch)
    n = 0
    with zipfile.ZipFile(src) as zin:
        parts = _sheet_parts(zin)
        new: dict[str, bytes] = {}
        for sheet, chs in by_sheet.items():
            part = parts.get(sheet)
            if part is None:
                continue
            xml = zin.read(part).decode("utf-8")
            p = (re.search(r"<(\w+:)?worksheet\b", xml) or [None, None])[1] or ""  # 칸 태그 접두사(<x:c …> — 엑셀 밖에서 만든 파일, 10/30 내진 견본)
            for ch in chs:
                pat = re.compile(rf'<{p}c\b(?=[^>]*\br\s*=\s*"{ch["cell"]}")([^>]*?)(/>|>(.*?)</{p}c>)', re.S)
                m = pat.search(xml)
                if m is None:
                    continue
                attrs, inner = m.group(1).rstrip("/"), m.group(3) or ""
                fm = re.search(rf"<{p}f\b[^>]*/>|<{p}f\b[^>]*>.*?</{p}f>", inner, re.S)
                f_el = fm.group(0) if fm else ""
                f_text = html.unescape(re.sub(rf"^<{p}f\b[^>]*>|</{p}f>$", "", f_el)) if f_el and not f_el.endswith("/>") else None
                nf = _new_formula(ch, f_text, res) if ch.get("formula") else None
                if nf is not None:
                    f_attrs = re.match(rf"<{p}f\b([^>]*?)/?>", f_el).group(1) if f_el else ""
                    if "ref=" not in f_attrs:  # 공유 수식의 딸린 칸이면 따로 떼어 냄
                        f_attrs = re.sub(r'\s(t="shared"|si="\d+")', "", f_attrs)
                    f_el = f"<{p}f{f_attrs}>{html.escape(nf, quote=False)}</{p}f>"
                attrs = re.sub(r'\st\s*=\s*"[^"]*"', "", attrs)
                if ch["kind"] == "str":
                    attrs += ' t="str"'
                    v = f"<{p}v>{html.escape(str(ch['value'] or ''), quote=False)}</{p}v>"
                else:
                    v = f"<{p}v>{_num(ch['value'] or 0)}</{p}v>"
                xml = xml[:m.start()] + f"<{p}c{attrs}>{f_el}{v}</{p}c>" + xml[m.end():]
                n += 1
            new[part] = xml.encode("utf-8")
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "xl/calcChain.xml":
                    continue
                data = new.get(item.filename) or zin.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    data = re.sub(rb'<Override[^>]*PartName\s*=\s*"/xl/calcChain\.xml"[^>]*/>', b"", data)
                elif item.filename == "xl/_rels/workbook.xml.rels":
                    data = re.sub(rb'<Relationship[^>]*Target\s*=\s*"[^"]*calcChain\.xml"[^>]*/>', b"", data)
                zout.writestr(item, data)
    return n


# ---------- 계약 폴더 ----------
def base(folder: Path) -> Path:
    return folder / DIR


def meta(folder: Path) -> dict | None:
    f = base(folder) / "meta.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_meta(folder: Path, m: dict) -> None:
    (base(folder) / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def make(folder: Path, data: bytes, filename: str, target: int, by: str) -> dict:
    """설계 내역서 → 낙찰가 적용 내역서(xlsx·PDF). 실패하면 ValueError(화면에 그대로)."""
    ext = Path(filename).suffix.lower()
    if ext not in (".xlsx", ".xlsm", ".xls"):
        raise ValueError("엑셀(xlsx·xls) 내역서만 맞출 수 있습니다.")
    if not target:
        raise ValueError("계약금액이 비었습니다 — 계약 창에서 계약금액을 넣어 주세요.")
    d = base(folder)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    src = d / f"적용전{ext}"
    src.write_bytes(data)
    is_zip = zipfile.is_zipfile(src)
    xlsx = d / f"{OUT_NAME}.xlsx"
    res = run_lo({"mode": "adjust", "src": str(src), "target": int(target), "xlsx": None if is_zip and ext != ".xls" else str(xlsx)})
    if not res.get("ok"):
        shutil.rmtree(d, ignore_errors=True)
        raise ValueError(res.get("error") or "내역서를 맞추지 못했습니다.")
    if is_zip and ext != ".xls":
        res["patched"] = patch_xlsx(src, xlsx, res)
    sheets = [s["name"] for s in res["sheets"] if s["default"]]
    m = {k: v for k, v in res.items() if k != "changed"} | {"changed": len(res.get("changed") or []), "filename": filename, "by": by,
                                                             "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "chosen": sheets, "src": src.name}
    _save_meta(folder, m)
    return export(folder, sheets)


def export(folder: Path, sheets: list[str]) -> dict:
    """고른 시트로 PDF 다시(조정한 xlsx — 저장된 계산값 그대로)."""
    m = meta(folder)
    if m is None:
        raise ValueError("먼저 내역서를 맞춰 주세요.")
    names = {s["name"] for s in m.get("sheets") or []}
    sheets = [s for s in sheets if s in names]
    if not sheets:
        raise ValueError("PDF에 넣을 시트를 하나 이상 고르세요.")
    d = base(folder)
    pdf = d / f"{OUT_NAME}.pdf"
    res = run_lo({"mode": "pdf", "src": str(d / f"{OUT_NAME}.xlsx"), "pdf": str(pdf), "sheets": sheets, "kind": m.get("kind")})
    if not res.get("ok") or not pdf.exists():
        raise ValueError(res.get("error") or "PDF를 만들지 못했습니다.")
    import pymupdf

    with pymupdf.open(pdf) as doc:
        pages = doc.page_count
    m.update(chosen=sheets, pages=pages, pdf_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    _save_meta(folder, m)
    return m
