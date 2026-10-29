"""내진성능평가 — 입력이 없어 못 채운 곳은 빈칸 + 노란 바탕(2026-10-26 사용자·형 "견본 값을 두면 통일감이 없음 — 다 지우고 노란색으로 바뀌어야 한다는 표시").

- 외주 몫(외주 한글이 없을 때 — 결과표 나~마·(2) 내진성능평가 적용~확인서·체크리스트)과 2.5 지반 및 기초(지반조사보고서가 없을 때)는
  견본(삼숭초) 값이 그대로 남았음 → 만들기 시작할 때 그 구간 칸·문단 글을 기억해 두고(snapshot), 다 채운 뒤 우리 프로그램이 손대지 않은 견본 값만 비우고 노랗게.
  "손댐" = report_build._set_lines로 쓴 칸(written) 또는 글이 바뀐 칸(견본 이름·날짜 바꾸기 등).
- 값 칸 가리기: 회색 이름칸은 안 건드림. 이름칸이 회색인 표(결과표·일반사항·층강도비 등)는 흰 칸 글을 모두, 이름칸도 흰 표(체크리스트)는 값처럼 생긴 글
  (숫자·유/무·○·■□·적용/미적용…)만, "건물명: 값"처럼 한 칸에 이름과 값이면 콜론 뒤만. "A."·"1."·"a."·"가." 같은 번호 붙은 이름은 그대로.
- 문단: 숫자가 든 견본 문장은 "(…을 올리면 채워집니다)" 노란 글로. 그림(모델링·지반 사진): 연한 노란 빈칸 그림으로.
- 우리 몫의 빈칸(사진 없음·부재 단면/철근/조적 표 빈 줄·2.2.4·요약 표)은 각 채우는 곳에서 paint().
"""
from __future__ import annotations

import re

from server.sitok import report_build as rb
from server.sitok import seismic_vendor as SV

HP = rb.HP
YELLOW = "#FFF2A8"  # 연한 노랑(인쇄해도 글이 보임) — 우리가 넣을 값인데 입력·서류가 없음
VENDOR = "#D4E8FF"  # 연한 하늘색 — 외주 결과물(결과표 나~마·(2)~체크리스트·구조해석 문단)로 채워질 값(10/29 사용자 "색을 구분")
LEGEND = "색 구분 — 노랑: 우리가 넣을 값(현장조사 입력·서류가 없음) · 하늘색: 외주 결과물을 받으면 채워질 값"
LABEL = re.compile(r"^\s*(\(?[0-9]{1,2}[).](?![0-9])|[A-Za-z][.)](?![0-9])|[가-하][.)]|[①-⑳]|[■□▣◆◇※]\s*[가-힣A-Za-z])")  # 번호·기호 붙은 이름("1. 일반사항" — "0.0023"은 아님)
PAIR = re.compile(r"^(\s*[^:：\d]{1,24}[:：])\s*\S")  # "용도: 교육연구시설"처럼 이름과 값이 한 칸
VALUE_WORDS = {"유", "무", "○", "◎", "●", "×", "O", "X", "만족", "불만족", "적합", "부적합", "적용", "미적용", "비적용", "해당없음", "있음", "없음",
               "정형", "비정형", "특등급", "1등급", "2등급", "LS", "CP", "IO", "Ⅰ", "Ⅱ", "I", "II", "S1", "S2", "S3", "S4", "S5", "S6", "-",
               "인명보호", "붕괴방지", "기능수행", "즉시거주", "선형해석법", "비선형해석법", "등가정적해석법", "모드해석법", "선형동적해석법",
               "교육연구시설", "철근콘크리트구조", "철근콘크리트조", "독립기초", "매트기초", "줄기초", "말뚝기초", "양호", "보통", "불량"}
SAMPLE = "삼숭"


def _txt(el) -> str:
    return "".join(t.text or "" for t in el.iter(rb.T))


def paint(tc, color: str = YELLOW) -> None:
    """칸 바탕을 노랗게(외주 몫은 color=VENDOR 하늘색, 테두리 그대로) — report_build.using_borders 안에서만(밖이면 그대로)."""
    b = getattr(rb._TL, "borders", None)
    if b is None or tc is None:
        return
    nid = b.fill(tc.get("borderFillIDRef"), color)
    if nid:
        tc.set("borderFillIDRef", nid)


def paint_empty(t, start: int) -> None:
    """표 t의 start줄부터 글 없는 칸을 노랗게(입력이 없어 비운 줄 — 2.2.1·2.2.2·2.4.3)."""
    if t is None:
        return
    for (r, _c), tc in rb._cells(t).items():
        if r >= start and not _txt(tc).strip():
            paint(tc)


def mark_text(p, color: str = YELLOW) -> None:
    """문단 글에 노란 형광펜(외주 몫은 하늘색, 글자 모양 shadeColor) — 테두리 도구 안에서만."""
    b = getattr(rb._TL, "borders", None)
    if b is None:
        return
    for run in p.iter(f"{{{HP}}}run"):
        cid = run.get("charPrIDRef")
        new = b._char_variant(cid, lambda d: re.sub(r'shadeColor="[^"]*"', f'shadeColor="{color}"', d, count=1) if "shadeColor=" in d
                              else d.replace("<hh:charPr ", f'<hh:charPr shadeColor="{color}" ', 1))
        if new:
            run.set("charPrIDRef", new)


def _gray(tc) -> bool:
    b = getattr(rb._TL, "borders", None)
    d = b.by_id.get(str(tc.get("borderFillIDRef"))) if b is not None else None
    m = re.search(r'faceColor="([^"]+)"', d or "")
    return bool(m) and m[1].lower() not in ("none", "#ffffff", YELLOW.lower(), VENDOR.lower())


def value_like(text: str) -> bool:
    t = re.sub(r"\s", "", text)
    if not t or LABEL.match(text):
        return False
    return bool(re.search(r"\d", t)) or t in VALUE_WORDS or "■" in t or "□" in t or SAMPLE in t or t.strip("()") in VALUE_WORDS


def _clear_keep_label(tc) -> bool:
    """칸 글·수식 지우기 — "이름: 값" 모양이면 콜론까지 남김. 지웠으면 True."""
    text = _txt(tc)
    for eq in list(tc.iter(f"{{{HP}}}equation")):  # 수식(Sds·Fa 등 — 글자가 아니라 hp:t에 안 보임)
        eq.getparent().remove(eq)
    m = PAIR.match(text)
    rb._set_lines(tc, [m[1]] if m else [""])
    return True


class Todo:
    """만들기 시작 때(외주 몫·지반 구간을 정한 뒤, 채우기 전) 만들고 → 채우기가 끝나면 finish(warn) — 테두리 도구(borders_for) 안에서."""

    def __init__(self, doc, vendor: bool, ground: bool):
        self.doc, self.cells, self.paras, self.pics, self.oles = doc, {}, {}, [], []
        tops = SV.tops_of(doc.root)
        areas = []
        if vendor:
            for key in SV.RESULT_KEYS:
                p, _ = SV.result_para(tops, key)
                if p is not None:
                    areas.append([p])
            fr = SV.front_range(tops)
            if fr:
                areas.append(tops[fr[0] + 1:fr[1]])  # 머리 문단 "(2) 내진성능평가 적용"은 빼고
        if ground:
            starts = [i for i, p in enumerate(tops) if re.sub(r"\s", "", rb._top_text(p)).startswith("2.5지반및기초") and next(p.iter(f"{{{HP}}}tbl"), None) is None]
            if starts:
                a = starts[-1]
                end = next((j for j in range(a + 1, len(tops)) if re.match(r"^제\s*3\s*장", rb._top_text(tops[j]).strip())), len(tops))
                areas.append(tops[a + 1:end])
        self.kind: dict = {}  # 칸·문단·그림 → "vendor"(외주 몫, 하늘색) | "ground"(지반 — 우리 서류, 노랑)
        for k, paras in enumerate(areas):
            in_ground = ground and k == len(areas) - 1
            kind = "ground" if in_ground else "vendor"
            for p in paras:
                tbls = [t for t in p.iter(f"{{{HP}}}tbl")]
                if not tbls:
                    t = _txt(p)
                    body = re.sub(r"^\s*(\(?[0-9]{1,2}[).]|[가-하][.)]|[①-⑳·•ㆍ-])\s*", "", t)  # 앞 번호·글머리 떼고
                    if re.search(r"\d", body) and len(body.strip()) > 12:
                        self.paras[p] = t
                        self.kind[id(p)] = kind
                for t in tbls:
                    if next(t.iterancestors(f"{{{HP}}}tbl"), None) is not None:
                        continue
                    for tc in rb._cells(t).values():
                        self.cells[tc] = (t, _txt(tc) + ("[수식]" if next(tc.iter(f"{{{HP}}}equation"), None) is not None else ""))
                        self.kind[id(tc)] = kind
                    if in_ground or "모델링" in re.sub(r"\s", "", _txt(t))[:40]:
                        self.pics += [(t, pic) for pic in t.iter(f"{{{HP}}}pic")]
                        self.oles += [(t, ole) for ole in t.iter(f"{{{HP}}}ole")]
                        for x in list(t.iter(f"{{{HP}}}pic")) + list(t.iter(f"{{{HP}}}ole")):
                            self.kind[id(x)] = kind
        self.on = bool(areas)
        if self.on:
            rb._TL.written = set()  # report_build._set_lines가 쓴 칸을 담음

    def stop(self) -> None:
        rb._TL.written = None

    def finish(self, rdir, warn: list) -> int:
        """손대지 않은 견본 값 → 빈칸 + 노랑. 고친 칸·문단 수."""
        if not self.on:
            return 0
        written = getattr(rb._TL, "written", None) or set()
        self.stop()
        gray_rows: dict = {}
        for tc, (t, _) in self.cells.items():
            if _gray(tc):
                gray_rows.setdefault(id(t), set()).add(tc.find(f"{{{HP}}}cellAddr").get("rowAddr"))
        n = 0
        for tc, (t, before) in self.cells.items():
            now = _txt(tc) + ("[수식]" if next(tc.iter(f"{{{HP}}}equation"), None) is not None else "")
            if tc in written or now != before or not before.strip() or _gray(tc) or self.doc.root not in tc.iterancestors():
                continue
            labeled = len(gray_rows.get(id(t), ())) >= 2  # 이름칸이 회색인 표 — 흰 칸은 모두 값
            head = re.match(r"^\s*[가-하]\.\s*\S", before)  # 결과표 "나. 구조물의 정보" 같은 마디 머리
            if (labeled and not head and not LABEL.match(before)) or value_like(before) or "[수식]" in before or PAIR.match(before):
                _clear_keep_label(tc)
                paint(tc, self._color(tc))
                n += 1
        for p, before in self.paras.items():
            if _txt(p) != before or self.doc.root not in p.iterancestors():
                continue
            ts = list(p.iter(rb.T))
            if not ts:
                continue
            vendor = self.kind.get(id(p)) == "vendor"
            ts[0].text = "(외주 결과물을 받으면 채워집니다)" if vendor else "(지반조사보고서를 올리면 채워집니다)"
            for x in ts[1:]:
                x.text = ""
            mark_text(p, VENDOR if vendor else YELLOW)
            n += 1
        for t, ole in self.oles:  # 견본 지반 위치도(OLE) — 지우고 그 칸 노랑
            if ole.getparent() is not None and self.doc.root in ole.iterancestors():
                tc = next(ole.iterancestors(f"{{{HP}}}tc"), None)
                kind = self.kind.get(id(ole))
                ole.getparent().remove(ole)
                paint(tc, VENDOR if kind == "vendor" else YELLOW)
                n += 1
        if self.pics:
            from server.sitok import seismic_fill

            for t, pic in self.pics:
                if pic.getparent() is not None and self.doc.root in pic.iterancestors():  # 사진 여러 장 표(지반 조사 현황)는 사진 칸 여백도(10/27)
                    blank = seismic_fill.blank_png(rdir, vendor=self.kind.get(id(pic)) == "vendor")  # 모델링 그림(외주) = 하늘색 빈칸
                    seismic_fill._put(self.doc, pic, blank, crop=False, pad=len(rb._pic_slots(t)) >= 2)
                    n += 1
        if n and LEGEND not in warn:
            warn.append(LEGEND)
        return n

    def _color(self, tc) -> str:
        return VENDOR if self.kind.get(id(tc)) == "vendor" else YELLOW
