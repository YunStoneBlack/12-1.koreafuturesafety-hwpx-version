"""건축물관리점검 최종 보고서(2026-10-29 3단계) — 우리 앞부분(표지·책등·제출문·등록증·참여기술자 명단·목차) + 생애이력시스템 본문 PDF + 부록(계약서·점검교육 이수증).

앞부분 원본 = 회사 "표지 및 내용.hwp"(사용자 10/29, 우리프라자 최종본 156쪽과 같은 짜임)를 한글로 hwpx로 바꿔 둔 TEMPLATE(9쪽):
  1 표지(건물명·주소·사진·연월) 2 책등(건물명·연월) 3 제출문(○○ 시설담당 귀하·과업명·연월) 4 안전진단기관 등록증 5 참여기술자 명단 6 목차
  7 부록 간지 8 부록.1(계약서) 간지 9 부록.2(점검교육 수료증) 간지.
목차 쪽 번호는 본문 PDF(사이트 [점검보고서 출력])에서 찾음 — 사이트 쪽 번호("- 1 -")가 그대로 보고서 쪽 번호.
채운 hwpx → 한글 PDF(hwp_queue) → pymupdf로 앞 6쪽 + 본문 + 간지·계약서·간지·이수증."""
from __future__ import annotations

import copy
import datetime
import io
import re
import zipfile
from pathlib import Path

import pymupdf
from lxml import etree

from core.db import DATA_DIR
from server.sitok import report_build as rb
from server.sitok.report_build import HP, T

TEMPLATE = DATA_DIR / "_건축물관리점검" / "_회사템플릿" / "표지.hwpx"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
COVER_IMAGE = "image1"  # 표지 사진(틀 42520×29099)
DEFAULT_ROLES = ("과업 책임기술자", "현장조사 및 보고서 작성")

# 목차 줄 → 본문 PDF에서 찾을 것(띄어쓰기 없앤 글). 대항목 다섯은 정기점검표 쪽(첫 소항목 상세 "구분점검내용" 앞)에서 차례대로.
TOC_KEYS = (("report", "건축물 점검 보고서"), ("law", "2.1 법규유지"), ("func", "2.2 기능유지"), ("energy", "2.3 에너지"), ("struct", "2.4 구조안전"),
            ("fire", "2.5 화재안전"), ("other", "2.6 그 밖의 항목"), ("opinion", "2.7 주요 개선"), ("detail", "3. 점검 세부"))
BIG_FIND = (("law", "법규유지"), ("func", "기능유지"), ("energy", "에너지및친환경"), ("struct", "구조안전"), ("fire", "화재안전"))


HH = "http://www.hancom.co.kr/hwpml/2011/head"
ROW_STEP = 2340  # 명단 표 아래 빈 문단 한 줄 높이(글자 1800 + 줄 간격) — 줄을 더하면 그만큼 빈 문단을 빼서 회사 상자가 다음 쪽으로 안 밀리게
BODY_EM = 31  # 제출문 본문 한 줄 글자 폭(원본 87.3 = 3줄, 안산 원시동 … 99.95 = 4줄)
NAME_EM = 13.0  # 표지 이름 상자 한 줄에 25pt로 들어가는 글자 폭(한글 1, 띄어쓰기·영문·숫자 0.55) — 넘으면 글자를 줄임


def _clone_pr(hd, tag: str, base_id: str, change) -> str:
    """header.xml의 charPr·borderFill 하나를 본떠 고친 새 항목 id(같은 것이 이미 있으면 그 id)."""
    items = list(hd.iter(f"{{{HH}}}{tag}"))
    base = next(x for x in items if x.get("id") == base_id)
    new = copy.deepcopy(base)
    change(new)
    key = etree.tostring(new).replace(f'id="{base_id}"'.encode(), b"")
    for x in items:
        if etree.tostring(x).replace(f'id="{x.get("id")}"'.encode(), b"") == key:
            return x.get("id")
    nid = str(max(int(x.get("id")) for x in items) + 1)
    new.set("id", nid)
    items[-1].addnext(new)
    box = new.getparent()
    box.set("itemCnt", str(len(box)))
    return nid


def _em(s: str) -> float:
    return sum(1.0 if "가" <= ch <= "힣" or ord(ch) > 0x3000 else 0.55 for ch in s)


def _fit_cover_name(hd, p, name: str) -> None:
    """표지 이름이 상자 한 줄을 넘으면 글자 크기를 줄인 모양으로(두 줄이 되면 표지가 한 쪽을 넘침 — 10/29 시험)."""
    w = _em(name)
    run = p.find(f"{{{HP}}}run")
    if run is None or w <= NAME_EM:
        return
    base = next((c for c in hd.iter(f"{{{HH}}}charPr") if c.get("id") == run.get("charPrIDRef")), None)
    if base is None:
        return
    h = max(1300, int(int(base.get("height")) * NAME_EM / w) // 50 * 50)
    run.set("charPrIDRef", _clone_pr(hd, "charPr", base.get("id"), lambda c: c.set("height", str(h))))


def _bottom(hd, bf_id: str, width: str) -> str:
    def change(b):
        el = b.find(f"{{{HH}}}bottomBorder")
        el.set("type", "SOLID")
        el.set("width", width)
    return _clone_pr(hd, "borderFill", bf_id, change)


def _sq(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def toc_pages(pdf_bytes: bytes) -> dict[str, int]:
    """본문 PDF(생애이력시스템 출력) → 목차 쪽 번호 {report: 1, law: 3, …, detail: 18}. 못 찾은 것은 빠짐."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    texts = [_sq(p.get_text()) for p in doc]
    doc.close()
    out = {"report": 1}
    detail = next((i for i, t in enumerate(texts) if "구분점검내용" in t and "점검대항목" in t), None)
    if detail is not None:
        out["detail"] = detail + 1
    other = next((i for i, t in enumerate(texts) if "그밖의항목에대한이행여부" in t and "확인대상" in t), None)
    if other is not None:
        out["other"] = other + 1
    opinion = next((i for i, t in enumerate(texts) if "주요개선방안에대한의견" in t), None)
    if opinion is not None:
        out["opinion"] = opinion + 1
    end = min(x for x in (detail, other, opinion, len(texts)) if x is not None)
    start = 1  # 첫 쪽(보고서·총괄표)은 대항목 이름이 다 있어서 뺌
    body = [t.split("개선방안에대한의견(필요한경우작성)", 1)[-1] for t in texts]  # 쪽 머리(점검 대·중·소 항목 …) 뒤 글만
    for key, word in BIG_FIND:
        hit = next((i for i in range(start, end) if word in body[i]), None)
        if hit is not None:
            out[key] = hit + 1
            start = hit
    return out


def report_month(contract: dict | None) -> tuple[int, int]:
    """보고 연월 — 정한 값(report_ym "2026-08") > 점검기간 끝 > 오늘."""
    c = contract or {}
    for v in (c.get("report_ym"), c.get("end")):
        m = re.match(r"(\d{4})\D?(\d{1,2})", str(v or ""))
        if m and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
    t = datetime.date.today()
    return t.year, t.month


def task_title(name: str, contract: dict | None) -> str:
    return ((contract or {}).get("title") or "").strip() or f"{name} 건축물관리법 정기안전점검 용역"


def _paras(root) -> list:
    return list(root.iter(f"{{{HP}}}p"))


def _text(p) -> str:
    return "".join("".join(t.itertext()) for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p)


def _find(root, pred) -> list:
    return [p for p in _paras(root) if pred(_text(p))]


def _set_t(t, text: str) -> None:
    for ch in list(t):
        t.remove(ch)
    t.text = text


def _drop_lineseg(p) -> None:
    for el in list(p.iter(f"{{{HP}}}linesegarray")):
        el.getparent().remove(el)


def _people_rows(root, hd, people: list[dict], field: str) -> None:
    """참여기술자 명단 표 — 머리줄 + 사람마다 한 줄(분야 칸은 첫 줄에 묶음). 원본은 2줄(책임·현장조사), 첫 줄 위는 겹선·끝줄 아래는 굵은 선(0.4mm).
    줄을 더하면 표 아래 빈 문단을 그 높이만큼 빼고(회사 상자가 다음 쪽으로 밀림 — 10/29 시험), 4명부터는 줄 높이를 줄여 한 쪽에."""
    host = next(iter(_find(root, lambda s: s.strip() == "자격 및 등급")), None)
    if host is None or not people:
        return
    tbl = next(host.iterancestors(f"{{{HP}}}tbl"))
    rows = tbl.findall(f"{{{HP}}}tr")
    if len(rows) < 3:
        return
    n = len(people)
    first_bf = [tc.get("borderFillIDRef") for tc in rows[1].findall(f"{{{HP}}}tc")]  # 분야 칸 + 5칸
    model_bf = [tc.get("borderFillIDRef") for tc in rows[2].findall(f"{{{HP}}}tc")]  # 5칸(끝줄 — 아래 굵은 선)
    row_h = int(rows[2].findall(f"{{{HP}}}tc")[0].find(f"{{{HP}}}cellSz").get("height") or 9260)
    model = rows[2]
    while len(tbl.findall(f"{{{HP}}}tr")) - 1 < n:  # 줄 더하기(두 번째 사람 줄을 본뜸)
        tbl.findall(f"{{{HP}}}tr")[-1].addnext(copy.deepcopy(model))
    for extra in tbl.findall(f"{{{HP}}}tr")[1 + n:]:  # 사람이 적으면 줄 빼기
        tbl.remove(extra)
    trs = tbl.findall(f"{{{HP}}}tr")
    new_h = row_h if n <= 3 else max(5200, 3 * row_h // n)
    for r, tr in enumerate(trs):
        for tc in tr.findall(f"{{{HP}}}tc"):
            tc.find(f"{{{HP}}}cellAddr").set("rowAddr", str(r))
    tbl.set("rowCnt", str(len(trs)))
    for cz in tbl.iter(f"{{{HP}}}cellzone"):  # 칸 묶음 테두리(1~2줄, 아래 0.4mm)도 새 끝줄까지 — 안 늘리면 2번째 사람 아래 굵은 선(10/29 사용자 짚음)
        if int(cz.get("endRowAddr") or 0) >= len(rows) - 1:
            cz.set("endRowAddr", str(len(trs) - 1))
    span_tc = trs[1].findall(f"{{{HP}}}tc")[0]
    span_tc.find(f"{{{HP}}}cellSpan").set("rowSpan", str(n))
    span_tc.find(f"{{{HP}}}cellSz").set("height", str(new_h * n))
    rb._set_para(next(span_tc.iter(f"{{{HP}}}p")), field or "건축", in_table=True)
    for r, (tr, person) in enumerate(zip(trs[1:], people)):
        tcs = tr.findall(f"{{{HP}}}tc")
        cells = tcs[1:] if r == 0 else tcs
        bfs = first_bf[1:] if r == 0 else model_bf
        last = r == n - 1
        vals = [person.get("role") or (DEFAULT_ROLES[min(r, 1)]), person.get("name") or "", person.get("position") or "",
                person.get("grade") or "", person.get("note") or "-"]
        for tc, v, bf in zip(cells, vals, bfs):
            tc.set("borderFillIDRef", _bottom(hd, bf, "0.4 mm" if last else "0.12 mm"))  # 끝줄만 아래 굵은 선
            tc.find(f"{{{HP}}}cellSz").set("height", str(new_h))
            ps = [p for p in tc.iter(f"{{{HP}}}p") if next(p.iterancestors(f"{{{HP}}}tc"), None) is tc]
            if ps:
                rb._set_para(ps[0], v, in_table=True)
                for p in ps[1:]:
                    p.getparent().remove(p)
    sz = tbl.find(f"{{{HP}}}sz")  # 표 높이 = 머리줄 + 줄 높이 합(한글이 열 때 다시 잼 — 대략 맞춰 둠)
    head_h = int(trs[0].findall(f"{{{HP}}}tc")[0].find(f"{{{HP}}}cellSz").get("height") or 0)
    grow = new_h * n - row_h * 2
    if sz is not None:
        sz.set("height", str(head_h + new_h * n))
    top = next(tbl.iterancestors(f"{{{HP}}}p"))
    while next(top.iterancestors(f"{{{HP}}}p"), None) is not None:
        top = next(top.iterancestors(f"{{{HP}}}p"))
    empties = []
    nxt = top.getnext()
    while nxt is not None and nxt.tag == f"{{{HP}}}p" and not _text(nxt).strip() and not list(nxt.iter(f"{{{HP}}}tbl")) and not list(nxt.iter(f"{{{HP}}}pic")):
        empties.append(nxt)
        nxt = nxt.getnext()
    if grow > 0:
        for p in empties[:min(len(empties), -(-grow // ROW_STEP))]:
            p.getparent().remove(p)
    elif grow < 0 and empties:
        for _ in range((-grow) // ROW_STEP):
            empties[-1].addnext(copy.deepcopy(empties[-1]))


def _toc(root, pages: dict[str, int]) -> None:
    for key, head in TOC_KEYS:
        n = pages.get(key)
        p = next(iter(_find(root, lambda s, h=head: _sq(s).startswith(_sq(h)) and "..." in s)), None)
        if p is None:
            continue
        ts = [t for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p]
        last = next((t for t in reversed(ts) if "." in "".join(t.itertext())), None)
        if last is None:
            continue
        s = "".join(last.itertext())
        _set_t(last, re.sub(r"(\.{3,})\s*\d*\s*$", lambda m: m.group(1) + (f"{n:03d}" if n else ""), s))
        _drop_lineseg(p)


def fill(name: str, address: str, contract: dict | None, people: list[dict], pages: dict[str, int],
         cover: bytes | None = None, tpl: Path = TEMPLATE) -> tuple[bytes, list[str]]:
    """원본 hwpx 채우기 → (hwpx 바이트, 알림)."""
    notes: list[str] = []
    y, m = report_month(contract)
    title = task_title(name, contract)
    zin = zipfile.ZipFile(tpl)
    root = etree.fromstring(zin.read("Contents/section0.xml"))
    hd = etree.fromstring(zin.read("Contents/header.xml"))

    def one(pred, text, in_table=True):
        hit = _find(root, pred)
        if hit:
            rb._set_para(hit[0], text, in_table=in_table)
        return bool(hit)

    # 1쪽 표지·머리
    one(lambda s: re.fullmatch(r"KFSC\d{4}", s.strip()) is not None, f"KFSC{y}")
    cover_name = _find(root, lambda s: s.strip() == "건축물 관리법 정기안전점검")
    if cover_name:
        prev = cover_name[0].getprevious()
        if prev is not None and prev.tag == f"{{{HP}}}p":
            rb._set_para(prev, name, in_table=True)
            _fit_cover_name(hd, prev, name)
    one(lambda s: re.fullmatch(r"\[.*\]", s.strip()) is not None, f"[{address}]" if address else "")
    one(lambda s: re.fullmatch(r"\d{4}\.\s*\d{1,2}\.", s.strip()) is not None, f"{y}. {m:02d}.", in_table=False)
    # 2쪽 책등 — 건물명 칸(︻ 앞), 연도 네 글자·"."·월이 한 문단씩
    brk = _find(root, lambda s: s.strip() == "︻")
    if brk:
        prev = brk[0].getprevious()
        if prev is not None and prev.tag == f"{{{HP}}}p":
            rb._set_para(prev, name, in_table=True)
        allp = _paras(root)  # 연도·월 문단은 다른 칸에 있을 수 있어 문서 차례로
        at = allp.index(brk[0])
        digits = [p for p in allp[at + 1:at + 16] if re.fullmatch(r"\d{1,2}|\.", _text(p).strip() or "x")]
        vals = [*str(y), ".", f"{m:02d}"]
        if len(digits) >= 6:
            for p, v in zip(digits[:6], vals):
                rb._set_para(p, v, in_table=True)
    # 3쪽 제출문
    to = _find(root, lambda s: "시설담당 귀하" in s)
    if to:
        ts = [t for t in to[0].iter(T)]
        if len(ts) >= 2:
            new = f"{name} 시설담당 귀하"
            dash = "".join(ts[0].itertext())
            n_dash = max(0, len(dash) - 2 * (len(new) - len("".join(ts[1].itertext()))))
            _set_t(ts[0], "-" * n_dash)
            _set_t(ts[1], new)
            _drop_lineseg(to[0])
    body = _find(root, lambda s: "계약 체결한" in s)
    if body:
        t = next(body[0].iter(T))
        s = "".join(t.itertext())
        new = re.sub(r"“[^”]*”", f"“{title}”", s, count=1)
        _set_t(t, new)
        from server.sitok import layout_fix
        layout_fix.apply_greeting(root, name)  # "귀 사와 계약 체결한" — 건물 이름에 맞게(학교 → 귀교, 시청 → 귀청, 그 밖은 귀사, 10/30)
        _drop_lineseg(body[0])
        # 본문 줄 수가 바뀌면 아래 빈 줄로 맞춤 — 날짜·회사·대표 줄이 그대로 있어야 도장(쪽에 고정)과 겹침이 원본처럼(10/29 시험: 긴 이름은 4줄)
        diff = -(-int(_em(new)) // BODY_EM) - -(-int(_em(s)) // BODY_EM)
        gap = []
        nxt = body[0].getnext()
        while nxt is not None and nxt.tag == f"{{{HP}}}p" and not _text(nxt).strip():
            gap.append(nxt)
            nxt = nxt.getnext()
        if diff > 0:
            for q in gap[:min(diff, len(gap) - 1)]:
                q.getparent().remove(q)
        elif diff < 0 and gap:
            for _ in range(-diff):
                gap[-1].addnext(copy.deepcopy(gap[-1]))
    one(lambda s: re.fullmatch(r"\d{4}년\s*\d{1,2}월", s.strip()) is not None, f"{y}년  {m:02d}월")
    # 5쪽 명단
    head = _find(root, lambda s: s.strip() == "과업명")
    if head:
        tc = next(head[0].iterancestors(f"{{{HP}}}tc"))
        nxt_tc = tc.getnext()
        if nxt_tc is not None:
            rb._set_para(next(nxt_tc.iter(f"{{{HP}}}p")), title, in_table=True)
    _people_rows(root, hd, people, (contract or {}).get("field") or "건축")
    # 6쪽 목차 — 제목을 늘 새 쪽에서(명단이 1명이면 표가 짧아져 앞 쪽으로 딸려 올라감 — 10/29 시험)
    for q in _find(root, lambda s: _sq(s) == "목차"):
        q.set("pageBreak", "1")
    _toc(root, pages)
    miss = [h for k, h in TOC_KEYS if k not in pages]
    if miss:
        notes.append("목차 쪽 번호를 본문 PDF에서 못 찾았습니다: " + ", ".join(miss))

    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    cover_bytes = None
    if cover:
        pic = next((p for p in root.iter(f"{{{HP}}}pic") if (p.find(f".//{{{HC}}}img") is not None
                                                            and p.find(f".//{{{HC}}}img").get("binaryItemIDRef") == COVER_IMAGE)), None)
        if pic is not None:
            cur = pic.find(f"{{{HP}}}curSz")
            w, h = int(cur.get("width")), int(cur.get("height"))
            tmp = io.BytesIO(cover)
            cover_bytes = rb._cropped(tmp, w, h, dpi=200)
            from server.sitok.wall_build import _size_pic
            _size_pic(pic, w, h, cover_bytes)
            xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    else:
        notes.append("표지 사진이 없어 원본 사진(우리프라자) 그대로입니다 — [📷 표지 사진]을 올리세요")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                data = xml
            elif info.filename == "Contents/header.xml":
                data = etree.tostring(hd, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif cover_bytes is not None and info.filename == f"BinData/{COVER_IMAGE}.jpg":
                data = cover_bytes
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)
    zin.close()
    return out.getvalue(), notes


def _page_index(doc, word: str, start: int = 0) -> int | None:
    return next((i for i in range(start, doc.page_count) if word in _sq(doc[i].get_text())), None)


def _add_file(out, data: bytes, name: str) -> int:
    """계약서·이수증 — PDF는 쪽 그대로, 그림은 A4 한 쪽에 비율 그대로. 넣은 쪽 수."""
    if data[:4] == b"%PDF":
        src = pymupdf.open(stream=data, filetype="pdf")
        n = src.page_count
        out.insert_pdf(src)
        src.close()
        return n
    page = out.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=data, keep_proportion=True)
    return 1


def assemble(front_pdf: bytes, site_pdf: bytes, contract_doc: tuple[bytes, str] | None, edu: list[tuple[bytes, str]]) -> tuple[bytes, dict, list[str]]:
    """앞 6쪽 + 본문 + 부록 간지 + 부록.1 간지 + 계약서 + 부록.2 간지 + 이수증 → (PDF, 쪽 수 정보, 알림)."""
    notes: list[str] = []
    front = pymupdf.open(stream=front_pdf, filetype="pdf")
    a1 = _page_index(front, "부록.1")
    a2 = _page_index(front, "부록.2", (a1 or 0) + 1)
    a0 = next((i for i in range((a1 or front.page_count) - 1, -1, -1) if "▣" in front[i].get_text()), None)
    if a1 is None or a2 is None or a0 is None:
        raise ValueError("표지 원본에서 부록 간지 쪽을 찾지 못했습니다(부록·부록.1·부록.2)")
    site = pymupdf.open(stream=site_pdf, filetype="pdf")
    out = pymupdf.open()
    out.insert_pdf(front, from_page=0, to_page=a0 - 1)
    n_front = out.page_count
    out.insert_pdf(site)
    n_site = site.page_count
    out.insert_pdf(front, from_page=a0, to_page=a0)
    out.insert_pdf(front, from_page=a1, to_page=a1)
    n_contract = 0
    if contract_doc:
        n_contract = _add_file(out, *contract_doc)
    else:
        notes.append("계약서가 없어 부록.1 간지만 들어갔습니다")
    out.insert_pdf(front, from_page=a2, to_page=a2)
    for data, name in edu:
        _add_file(out, data, name)
    if not edu:
        notes.append("점검교육 이수증이 없어 부록.2 간지만 들어갔습니다")
    info = {"pages": out.page_count, "front": n_front, "site": n_site, "contract": n_contract, "edu": len(edu)}
    data = out.tobytes(garbage=3, deflate=True)
    for d in (front, site, out):
        d.close()
    return data, info, notes
