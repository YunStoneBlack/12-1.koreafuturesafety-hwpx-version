"""낙찰가 적용 내역서 — LibreOffice 파이썬(uno)으로 도는 쪽(2026-10-30 사용자 "낙찰가 적용 전 내역서를 첨부하면 계약금액에 맞게 노임단가를 조정한 내역서를 착수계에").

server/sitok/est_adjust.py가 LibreOffice의 python.exe로 이 파일을 돌림: python.exe est_adjust_lo.py <일.json> → 같은 이름 .out.json.
- 엑셀 파일을 LibreOffice로 열되 **다시 계산은 바꾼 칸에 딸린 칸만**(doc.calculate) — 전체 다시 계산(calculateAll)은 LibreOffice와 엑셀 함수 차이로
  산출근거 인원수부터 달라짐(10/30 시특법 견본: 12.3인 → 14.1인). 저장된 엑셀 계산값 위에서 노임단가 쪽만 다시 셈.
- 양식 두 가지(회사가 받는 관급 내역서):
  sitok  = 시특법 정기·정밀 대가(시트 "내역서" + "노임단가표") — 노임단가표 엔지니어링 기술자 단가 중 내역서가 쓰는 칸을 같은 비율로(=원래×p%),
           용역비 = 내역서 "용역비" 줄 M칸, 끝자리가 안 맞으면 "공급가액"·"용역비" 줄 ROUNDDOWN 자리를 -2·-1·0으로(형 견본처럼).
  seismic = 교육청 내진성능평가(시트 "1. 내진성능 평가 용역비 산출내역서" ● 고급기술자 노임단가 + 총괄표 합계) — 단가를 원 단위로(안 되면 비율),
           끝자리가 안 맞으면 시설별 총계·M61 ROUND 자리를.
- 한글 금액(TEXT …[DBNum4]) 칸은 LibreOffice가 모르는 서식이라 "#FMT"가 됨 → 엑셀 규칙대로(일십·일백·일천) 글로 바꿔 넣음.
- 결과: 바뀐 칸 [sheet, cell, kind(num|str), value, formula?] — 원본 엑셀은 est_adjust.py가 이 칸만 고침(서식 그대로).
- mode pdf: 고친 엑셀을 열어(저장된 계산값 그대로) 고른 시트의 쪽만 PDF(시트마다 쪽 수를 세어 PageRange)."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue

SOFFICE = os.environ.get("SOFFICE_PATH") or r"C:\Program Files\LibreOffice\program\soffice.exe"
DIG = "영일이삼사오육칠팔구"


def hangul(n: int) -> str:
    """엑셀 TEXT(n,"[DBNum4]G/표준")와 같게 — 59822700 → 오천구백팔십이만이천칠백, 1100 → 일천일백."""
    n = int(n)
    if n == 0:
        return "영"
    out, g = [], 0
    while n:
        n, part = divmod(n, 10000)
        if part:
            s = str(part)
            out.append("".join(DIG[int(c)] + ("", "십", "백", "천")[len(s) - 1 - i] for i, c in enumerate(s) if c != "0") + ("", "만", "억", "조")[g])
        g += 1
    return "".join(reversed(out))


def pv(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def col_name(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class Book:
    def __init__(self, doc):
        self.doc = doc
        self.sheets = doc.Sheets

    def names(self):
        return list(self.sheets.ElementNames)

    def cell(self, sheet, addr):
        return self.sheets.getByName(sheet).getCellRangeByName(addr)

    def used(self, sheet):
        sh = self.sheets.getByName(sheet)
        cur = sh.createCursor()
        cur.gotoEndOfUsedArea(False)
        return sh, cur.RangeAddress.EndRow, cur.RangeAddress.EndColumn

    def grid(self, sheet):
        """(값 배열, 수식 배열) — 쓰인 범위 전체."""
        sh, r, c = self.used(sheet)
        rng = sh.getCellRangeByPosition(0, 0, c, r)
        return rng.getDataArray(), rng.getFormulaArray()

    def find(self, sheet, pat, cols=None):
        """글 칸 찾기 → [(row, col, text)]."""
        vals, _ = self.grid(sheet)
        rx = re.compile(pat)
        out = []
        for r, row in enumerate(vals):
            for c, v in enumerate(row):
                if (cols is None or c in cols) and isinstance(v, str) and rx.search(re.sub(r"\s", "", v)):
                    out.append((r, c, v))
        return out


def set_round(book, sheet, addr, digits):
    """그 칸 수식 바깥 ROUND/ROUNDDOWN의 자리 수를 digits로 — 바뀌면 (전, 후) 수식."""
    c = book.cell(sheet, addr)
    f = c.getFormula()
    m = re.match(r"^=(ROUND|ROUNDDOWN|ROUNDUP)\((.*)[;,]\s*(-?\d+)\)$", f)
    if not m or int(m.group(3)) == digits:
        return None
    nf = f"={m.group(1)}({m.group(2)};{digits})"
    c.setFormula(nf)
    return f, nf


def detect(book):
    names = book.names()
    if "내역서" in names and any("노임단가" in n for n in names):
        lab = next(n for n in names if "노임단가" in n)
        tot = book.find("내역서", r"^\d*\.?용역비$", cols=range(0, 3))
        sup = book.find("내역서", r"^\d*\.?공급가액$", cols=range(0, 3))
        if tot:
            _, f = book.grid("내역서")
            refs = set()
            for row in f:
                for x in row:
                    for m in re.finditer(re.escape(lab) + r"'?\.\$?([A-Z]+)\$?(\d+)", x or ""):
                        refs.add(f"{m.group(1)}{m.group(2)}")
            vals, forms = book.grid(lab)
            rates = []
            for r, row in enumerate(vals):
                name = re.sub(r"\s", "", str(row[1] if len(row) > 1 else ""))
                for c in range(2, len(row)):
                    addr = f"{col_name(c)}{r + 1}"
                    if "기술자" in name and addr in refs and isinstance(row[c], float) and row[c] > 0:
                        rates.append({"sheet": lab, "cell": addr, "label": name, "before": row[c], "formula_before": forms[r][c]})
            if rates:
                tr = tot[0][0] + 1
                return {"kind": "sitok", "total": ("내역서", f"M{tr}"), "rates": rates,
                        "rounding": [("내역서", f"M{sup[0][0] + 1}")] * bool(sup) + [("내역서", f"M{tr}")]}
    s1 = next((n for n in names if re.match(r"^1\.\s*내진성능\s*평가", n)), None)
    if s1 and "총괄표" in names:
        rates = []
        vals, forms = book.grid(s1)
        for r, row in enumerate(vals):
            for c, v in enumerate(row):
                if isinstance(v, str) and "기술자노임단가" in re.sub(r"\s", "", v):
                    for c2 in range(c + 1, len(row)):
                        if isinstance(row[c2], float) and row[c2] > 10000 and not str(forms[r][c2]).startswith("="):
                            rates.append({"sheet": s1, "cell": f"{col_name(c2)}{r + 1}", "label": re.sub(r"[●\s]", "", v), "before": row[c2], "formula_before": forms[r][c2]})
                            break
        tot = book.find("총괄표", r"합계", cols=range(0, 3))
        if rates and tot:
            tr = tot[0][0] + 1
            _, f1 = book.grid(s1)
            rnd = [(s1, f"{col_name(c)}{r + 1}") for r, row in enumerate(f1) for c, x in enumerate(row)
                   if re.match(r"^=ROUND\(IFERROR\(ROUND\(", x or "")]  # 시설별 총계(AF7 …)
            m61 = book.find(s1, r"^\(D\)총계$")
            if m61:
                rr = m61[0][0] + 1
                rnd.append((s1, next((f"{col_name(c)}{rr}" for c, x in enumerate(f1[rr - 1]) if re.match(r"^=ROUND\(", x or "")), f"M{rr}")))
            return {"kind": "seismic", "total": ("총괄표", f"E{tr}"), "rates": rates, "rounding": rnd}
    return None


def run(job: dict) -> dict:
    prof = Path(job["profile"])
    prof.mkdir(parents=True, exist_ok=True)
    pipe = f"est{os.getpid()}_{int(time.time())}"
    proc = subprocess.Popen([SOFFICE, f"-env:UserInstallation={prof.as_uri()}", "--headless", "--norestore", "--nologo", "--nodefault",
                             f"--accept=pipe,name={pipe};urp;StarOffice.ComponentContext"], creationflags=0x08000000)
    desktop = None
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        ctx = None
        for _ in range(150):
            try:
                ctx = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.2)
        if ctx is None:
            return {"ok": False, "error": "LibreOffice를 띄우지 못했습니다."}
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(job["src"]), "_blank", 0, (pv("Hidden", True), pv("UpdateDocMode", 0)))
        if doc is None:
            return {"ok": False, "error": "엑셀 파일을 열지 못했습니다."}
        try:
            return pdf_only(Book(doc), job) if job.get("mode") == "pdf" else adjust(Book(doc), job)
        finally:
            doc.close(True)
    finally:
        try:
            if desktop is not None:
                desktop.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def adjust(book: Book, job: dict) -> dict:
    spec = detect(book)
    if spec is None:
        return {"ok": False, "error": "이 내역서 양식은 아직 모릅니다 — 시특법 대가(내역서·노임단가표) 또는 교육청 내진성능평가 양식만 맞출 수 있습니다."}
    target = int(job["target"])
    ts, ta = spec["total"]
    tc = book.cell(ts, ta)
    before_total = tc.getValue()
    names = book.names()
    snap = {n: book.grid(n) for n in names}  # 바뀐 칸 찾기용(값·수식)
    rates = spec["rates"]

    def total_at(x, mode):
        for r in rates:
            c = book.cell(r["sheet"], r["cell"])
            c.setValue(round(r["before"] * x / 100000, 5) if mode == "pct" else x)
        book.doc.calculate()
        return round(tc.getValue())

    def first_at_least(lo, hi, mode, t):
        while lo < hi:
            mid = (lo + hi) // 2
            if total_at(mid, mode) >= t:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def search(mode):
        """계약금액이 딱 나오는 값 중 가장 큰 것(단가를 덜 깎음) — 없으면 None."""
        lo, hi = (1, 150000) if mode == "pct" else (1, int(rates[0]["before"] * 1.5))
        if total_at(hi, mode) < target:
            return None
        x = first_at_least(lo, hi, mode, target)
        if total_at(x, mode) != target:
            return None
        return first_at_least(x, hi + 1, mode, target + 1) - 1

    rounding = []
    found = mode = None
    for digits in (None, -2, -1, 0):
        if digits is not None:  # 끝자리가 안 맞으면 절사 자리를 줄임(형 견본: 만원·천원 → 백원)
            for s, a in spec["rounding"]:
                got = set_round(book, s, a, digits)
                if got:
                    rounding.append({"sheet": s, "cell": a, "before": got[0], "after": got[1]})
            if not rounding:
                break
        modes = ["won", "pct"] if len(rates) == 1 and spec["kind"] == "seismic" else ["pct"]
        for md in modes:
            k = search(md)
            if k is not None:
                found, mode = k, md
                break
        if found is not None:
            break
    if found is None:
        for r in rates:
            book.cell(r["sheet"], r["cell"]).setValue(r["before"])
        book.doc.calculate()
        return {"ok": False, "error": f"노임단가를 바꿔도 계약금액 {target:,}원에 딱 맞지 않습니다(설계 {round(before_total):,}원) — 내역서를 확인해 주세요."}
    # 확정 — 비율이면 "=원래×p%"(형 견본처럼), 원이면 그 값
    for r in rates:
        c = book.cell(r["sheet"], r["cell"])
        if mode == "pct":
            pct = f"{found / 1000:.3f}".rstrip("0").rstrip(".")
            c.setFormula(f"={r['before']:g}*{pct}%")
            r.update(after=round(r["before"] * found / 100000, 5), formula=f"={r['before']:g}*{pct}%", pct=pct)
        else:
            c.setValue(found)
            r.update(after=float(found), formula=None, pct=f"{found / r['before'] * 100:.3f}")
    book.doc.calculate()
    after_total = round(tc.getValue())
    # 한글 금액(DBNum4) — LibreOffice가 모르는 서식 → 글로
    texts = []
    for n in names:
        vals, forms = book.grid(n)
        for ri, row in enumerate(forms):
            for ci, f in enumerate(row):
                if "DBNum" in (f or "") and isinstance(vals[ri][ci], str):
                    m = re.search(r'TEXT\((\$?[A-Z]+\$?\d+);"\[DBNum4\][^"]*"\)', f)
                    if not m:
                        continue
                    ref = m.group(1).replace("$", "")
                    num = book.cell(n, ref).getValue()
                    nf = f.replace(m.group(0), f'"{hangul(round(num))}"')
                    book.cell(n, f"{col_name(ci)}{ri + 1}").setFormula(nf)
                    texts.append({"sheet": n, "cell": f"{col_name(ci)}{ri + 1}", "before": f, "after": nf})
    book.doc.calculate()
    # 바뀐 칸(값·수식)
    changed = []
    for n in names:
        v0, f0 = snap[n]
        v1, f1 = book.grid(n)
        for ri in range(max(len(v0), len(v1))):
            r0 = v0[ri] if ri < len(v0) else ()
            r1 = v1[ri] if ri < len(v1) else ()
            for ci in range(max(len(r0), len(r1))):
                a = r0[ci] if ci < len(r0) else None
                b = r1[ci] if ci < len(r1) else None
                fa = f0[ri][ci] if ri < len(f0) and ci < len(f0[ri]) else ""
                fb = f1[ri][ci] if ri < len(f1) and ci < len(f1[ri]) else ""
                if a != b or fa != fb:
                    changed.append({"sheet": n, "cell": f"{col_name(ci)}{ri + 1}", "kind": "num" if isinstance(b, float) else "str",
                                    "value": b, "formula": fb if fb.startswith("=") and fb != fa else None, "was_formula": fa.startswith("=")})
    if job.get("xlsx"):  # 원본이 xlsx가 아니면(xls) LibreOffice로 저장한 것을 받기 파일로
        book.doc.storeToURL(uno.systemPathToFileUrl(job["xlsx"]), (pv("FilterName", "Calc MS Excel 2007 XML"),))
    return {"ok": True, "kind": spec["kind"], "before": round(before_total), "after": after_total, "target": target, "mode": mode,
            "rates": [{k: r[k] for k in ("sheet", "cell", "label", "before", "after", "formula", "pct", "formula_before")} for r in rates],
            "rounding": rounding, "texts": texts, "changed": changed, "sheets": sheet_list(book, spec["kind"])}


SEISMIC_DEFAULT = ("총괄표", "여비", "차량운행", "인쇄비", "선택집계")  # + "1. 내진성능 평가 …" — 일위대가·자재단가 같은 공사 내역(100쪽 넘음)은 기본에서 뺌


def sheet_list(book: Book, kind: str) -> list[dict]:
    """PDF에 넣을 시트 고르기 — [{name, hidden, default}]. 시특법 = 보이는 시트 전부(엑셀 인쇄와 같음), 내진 = 총괄표·산출내역서·직접경비·선택집계."""
    out = []
    for n in book.names():
        hidden = not book.sheets.getByName(n).IsVisible
        if kind == "seismic":
            d = not hidden and (n in SEISMIC_DEFAULT or bool(re.match(r"^1\.\s*내진성능\s*평가", n)))
        else:
            d = not hidden
        out.append({"name": n, "hidden": hidden, "default": d})
    return out


def export_pdf(book: Book, pdf: str, sheets: list) -> int:
    """고른 시트만 PDF — LibreOffice는 숨긴 시트도 내보내고 빈 인쇄 범위도 빈 쪽(머리글 그림)으로 내서, 시트마다 쪽 수(getRendererCount — 합 = 전체 PDF 쪽 수)를
    세어 고른 시트의 쪽 번호만(PageRange) 내보냄."""
    keep = set(sheets)
    start, ranges = 1, []
    for n in book.names():
        c = book.doc.getRendererCount(book.sheets.getByName(n), (pv("IsPrinter", True),))
        if n in keep and c:
            ranges.append(f"{start}-{start + c - 1}")
        start += c
    if not ranges:
        raise ValueError("고른 시트에 인쇄할 쪽이 없습니다.")
    fd = uno.Any("[]com.sun.star.beans.PropertyValue", (pv("PageRange", ",".join(ranges)),))
    book.doc.storeToURL(uno.systemPathToFileUrl(pdf), (pv("FilterName", "calc_pdf_Export"), pv("FilterData", fd)))
    return start - 1


def pdf_only(book: Book, job: dict) -> dict:
    export_pdf(book, job["pdf"], job.get("sheets") or [s["name"] for s in sheet_list(book, job.get("kind") or "") if s["default"]])
    return {"ok": True}


if __name__ == "__main__":
    jf = Path(sys.argv[1])
    job = json.loads(jf.read_text(encoding="utf-8"))
    try:
        out = run(job)
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}
    jf.with_suffix(".out.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
