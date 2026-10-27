"""내진성능평가 본문 원본(우리 1~2장) 다듬기 — 민재형이 호원초 1~2장을 손으로 고친 것(10/26)을 틀에 옮김.
다시 돌려도 같음(이미 고친 곳은 건너뜀) — 형이 원본을 새로 올리면 한 번 더 돌리면 됨.

    python -m server.scripts.fix_seismic_master          # 고치고 옛 원본은 _지난원본/에 보관
    python -m server.scripts.fix_seismic_master --dry    # 무엇을 고칠지만
    python -m server.scripts.fix_seismic_master --out X  # 원본은 두고 고친 것을 X로(시험)
    python -m server.scripts.fix_seismic_master --mm 12  # ⑤ 용지 여백 12mm + 한 쪽짜리 표·그림 줄이기(아래)

① 요약문·2.2.4 자동 번호 — 문단마다 번호 정의가 따로(모두 1부터)라 "가."만 다섯 번·"(1)"이 두 번 나오던 것 → 시작값으로 이어지게
   (나~마, (2), 나~라, 2.2.4 (2) 조사결과)
② 목차 줄 간격 200 → 190%, "목 차" 160 → 150%
③ 결과표 "라." 표·선형해석결과 층강도비(X·Y)·층간변위(X·Y) 표 줄 높이(민재형 값 — 작은 글이 빽빽하던 것)
④ 쪽 끝을 채워 다음 내용을 새 쪽으로 밀던 빈 줄 → 지우고 새 쪽에서 시작할 제목에 쪽 나눔(내용 길이가 바뀌어도 안 흐트러짐),
   쪽 나눔 빈 줄이 제목과 표 사이에 있던 곳((3) 철근 배근 조사 결과)은 제목에, 표 제목과 표 사이 빈 줄
⑤ (--mm 12) 용지 여백 위·머리말·꼬리말·아래 12mm(민재형 10/27 — 머리말이 본문에 붙어 보여서, 좌우 15·제본 그대로) — 본문 높이 74553 → 70580이라
   한 쪽에 맞춘 표·그림이 넘쳐 둘로 나뉘던 곳(10/27 밤 시험 호원초 66 → 80쪽)을 그만큼 줄임: 등록증·위치도/전경·종합의견 둘·결함조사 분석 표·
   1.2 건물규모(전경 틀)·평면도 틀(한 쪽 두 장)·성적서 틀·2.3 균열 분석 표·2.4.2 마감재 사진 틀·체크리스트 표지 빈 줄. 여백이 이미 12mm면 건너뜀.
   사진·그림 틀은 만들 때 그 틀 크기로 넣으니(seismic_fill _pad_photo·_put_full) 틀만 줄이면 됨.
표지~목차 앞 쪽 나눔은 그대로(서버 PDF에서 맞게 나뉨)."""
import argparse
import copy
import datetime
import re
import shutil
import sys
from pathlib import Path

import server.settings  # noqa: F401  # DATA_DIR 등 설정
from server.sitok import master
from server.sitok import report_build as rb
from server.sitok.seismic_fill import _empty_para, _scale_pic
from server.sitok.wall_build import HP, Hwpx

HH = "http://www.hancom.co.kr/hwpml/2011/head"

# ① 번호 문단 글 → 그 수준 시작값
NUMBER_START = {"현장시험": 2, "장비조사결과": 3, "비구조조사결과": 4, "지반조사결과": 5, "내진성능평가적용": 2,
                "재료강도의결정": 2, "평가방법적용기준": 3, "내진성능평가결과": 4, "조사결과": 2}
# ③ (표 첫 글, 줄×칸, 몇 번째) → (전 줄 높이, 민재형 줄 높이)
ROW_HEIGHTS = {
    ("라.내진성능평가방법및판정결과", ("19", "16"), 0): (
        [2765, 3945, 2980, 2765, 3945, 2980, 2475, 2765, 2765, 2475, 3346, 3346, 3346, 3346, 3346, 3346, 2475, 3343, 3634],
        [3238, 4621, 3490, 3238, 4621, 3490, 2898, 3238, 3238, 3329, 3919, 3919, 3919, 3919, 3919, 3919, 2898, 3915, 4255]),
    ("층모멘트골조", ("8", "18"), 0): ([1500, 2632] + [1566] * 6, [2632, 3764] + [2698] * 6),
    ("층모멘트골조", ("8", "18"), 1): ([1500, 2632] + [1566] * 6, [2632, 3764] + [2698] * 6),
    ("하중조합층층높이", ("7", "8"), 0): ([1897, 3048] + [1660] * 5, [2746, 3897] + [2509] * 5),
    ("하중조합층층높이", ("7", "8"), 1): ([1705, 3048] + [1565] * 5, [2554, 3897] + [2414] * 5),
}


def _t(el) -> str:
    return re.sub(r"\s", "", "".join(x.text or "" for x in el.iter(f"{{{HP}}}t")))


class Fix:
    def __init__(self, doc: Hwpx):
        self.doc, self.root, self.head = doc, doc.root, doc.header
        self.log: list[str] = []
        self.pp = {p.get("id"): p for p in self.head.iter(f"{{{HH}}}paraPr")}
        self.num = {n.get("id"): n for n in self.head.iter(f"{{{HH}}}numbering")}

    def tops(self) -> list:
        return [p for p in self.root if p.tag == f"{{{HP}}}p"]

    def heading(self, p):
        h = self.pp[p.get("paraPrIDRef")].find(f"{{{HH}}}heading")
        return h if h is not None and h.get("type") == "NUMBER" else None

    # ---- 찾기 ----
    def find(self, text: str, *, last=False, prefix=False, numbered=False, after=None):
        hits = [p for p in self.tops() if (_t(p).startswith(text) if prefix else _t(p) == text) and (not numbered or self.heading(p) is not None)]
        if after is not None:
            hits = [p for p in hits if self.tops().index(p) > self.tops().index(after)]
        if not hits:
            raise SystemExit(f"못 찾음: {text}")
        return hits[-1] if last else hits[0]

    # ---- ① 번호 ----
    def numbers(self):
        start = self.tops().index(self.find("a.내진성능평가결과요약", last=True))
        for p in self.tops()[start:]:
            h = self.heading(p)
            want = NUMBER_START.get(_t(p)) if h is not None else None
            if want is None:
                continue
            users = [x for x in self.tops() if (g := self.heading(x)) is not None and g.get("idRef") == h.get("idRef")]
            if len(users) != 1:
                raise SystemExit(f"번호 정의 {h.get('idRef')}를 여러 문단이 씀 — 손으로 확인: {_t(p)}")
            level = str(int(h.get("level")) + 1)
            ph = next(x for x in self.num[h.get("idRef")].findall(f"{{{HH}}}paraHead") if x.get("level") == level)
            if ph.get("start") != str(want):
                ph.set("start", str(want))
                self.log.append(f"번호 {_t(p)} → {want}번째부터")

    # ---- ② 목차 줄 간격 ----
    def _pp_with_line(self, pid: str, value: int) -> str:
        src = self.pp[pid]
        if int(src.find(f"{{{HH}}}lineSpacing").get("value")) == value:
            return pid
        key = (pid, value)
        cache = getattr(self, "_clones", {})
        self._clones = cache
        if key not in cache:
            new = copy.deepcopy(src)
            nid = str(max(int(i) for i in self.pp) + 1)
            new.set("id", nid)
            new.find(f"{{{HH}}}lineSpacing").set("value", str(value))
            parent = src.getparent()
            parent.append(new)
            parent.set("itemCnt", str(len(parent.findall(f"{{{HH}}}paraPr"))))
            self.pp[nid] = new
            cache[key] = nid
        return cache[key]

    def toc(self):
        tops = self.tops()
        i0 = tops.index(self.find("목차"))
        i1 = tops.index(self.find("a.내진성능평가결과요약", last=True))
        n = 0
        for k, p in enumerate(tops[i0:i1]):
            ls = self.pp[p.get("paraPrIDRef")].find(f"{{{HH}}}lineSpacing")
            if ls.get("type") != "PERCENT":
                continue
            v = int(ls.get("value"))
            want = 150 if k < 2 and v == 160 else 190 if v == 200 else v  # "목 차"와 그 뒤 빈 줄 150, 목차 줄 190
            if want != v:
                p.set("paraPrIDRef", self._pp_with_line(p.get("paraPrIDRef"), want))
                n += 1
        if n:
            self.log.append(f"목차 줄 간격 {n}줄")

    # ---- ③ 줄 높이 ----
    def rows(self):
        for (head, rc, nth), (old, new) in ROW_HEIGHTS.items():
            tbls = [t for t in self.root.iter(f"{{{HP}}}tbl") if (t.get("rowCnt"), t.get("colCnt")) == rc and _t(t).startswith(head)]
            if len(tbls) <= nth:
                raise SystemExit(f"표 못 찾음: {head} {nth}")
            t = tbls[nth]
            cells = [tc for tc in t.iter(f"{{{HP}}}tc") if next(tc.iterancestors(f"{{{HP}}}tbl")) is t]
            now = {}
            for tc in cells:
                if tc.find(f"{{{HP}}}cellSpan").get("rowSpan") == "1":
                    now[int(tc.find(f"{{{HP}}}cellAddr").get("rowAddr"))] = int(tc.find(f"{{{HP}}}cellSz").get("height"))
            cur = [now.get(r) for r in range(len(old))]
            if cur == new:
                continue
            if cur != old:
                raise SystemExit(f"{head} {nth} 줄 높이가 예상과 다름 — 손으로 확인: {cur}")
            for tc in cells:
                r = int(tc.find(f"{{{HP}}}cellAddr").get("rowAddr"))
                rs = int(tc.find(f"{{{HP}}}cellSpan").get("rowSpan"))
                tc.find(f"{{{HP}}}cellSz").set("height", str(sum(new[r:r + rs])))
            t.find(f"{{{HP}}}sz").set("height", str(sum(new)))
            self.log.append(f"줄 높이 {head} {nth + 1}번째")

    # ---- ④ 빈 줄·쪽 나눔 ----
    def _blanks(self, p, step):
        out, q = [], (p.getprevious() if step < 0 else p.getnext())
        while q is not None and q.tag == f"{{{HP}}}p" and _empty_para(q):
            out.append(q)
            q = q.getprevious() if step < 0 else q.getnext()
        return out

    def act(self, p, before=False, after=False, pb=False, keep=0, unpb=False):
        """before/after = 앞/뒤 빈 줄 지움(keep = 앞 빈 줄 몇 개 남김), pb = 늘 새 쪽, unpb = 늘 새 쪽을 풂(이어 붙임 — 제목만 쪽 끝에 걸리면 만들 때 pagecheck.push_lonely가 넘김)."""
        name = _t(p)[:20]
        gone = 0
        if before:
            for q in self._blanks(p, -1)[keep:]:
                q.getparent().remove(q)
                gone += 1
        if after:
            for q in self._blanks(p, 1):
                q.getparent().remove(q)
                gone += 1
        if pb and p.get("pageBreak") != "1":
            p.set("pageBreak", "1")
            self.log.append(f"쪽 나눔 {name}")
        if unpb and p.get("pageBreak") == "1":
            p.set("pageBreak", "0")
            self.log.append(f"쪽 나눔 풂 {name}")
        if gone:
            self.log.append(f"빈 줄 {gone}개 지움 {name}")

    def blanks(self):
        """늘 새 쪽 = 민재형이 정한 곳만(10/27 사용자 목록 — 제1장·(6) 평면도·1.3·1.4·2.1·2.2·【부재단면치수조사결과】·2.2.2·[철근배근 조사결과]·2.2.3·2.2.4·2.3·
        2.2.4 (2) 조사결과·【금회 균열 및 기타 결함현황 조사 결과표】·2.4·2.4.2·2.4.3·[조적벽 상태 평가를 위한 예시]·[조적벽 치수 및 상태조사 결과표]·2.5, (6) 평면도·2.2.3은 만들 때 seismic_fill).
        나머지는 이어 붙임 — 앞 내용이 짧으면 다음 내용이 당겨 올라옴, 제목·표 이름만 쪽 끝에 걸리면 만들 때 그것만 다음 쪽(pagecheck.push_lonely)."""
        f, a = self.find, self.act
        a(f("a.내진성능평가결과요약", last=True), before=True, pb=True)
        a(f("요약문"), before=True, pb=True)
        a(f("장비조사결과", numbered=True), before=True, pb=True)  # 빈 줄만 지우면 제목만 앞 쪽 끝에 남음(원래도 새 쪽 첫머리)
        a(f("내진성능평가적용", numbered=True), pb=True)
        a(f("평가방법적용기준", numbered=True), pb=True)
        a(f("b.기존학교시설내진성능평가및보강체크리스트", last=True), before=True, pb=True)  # 뒤 빈 줄은 체크리스트 표지 세로 자리라 둠
        a(f("검토항목검토내용보고서페이지적합여부A.기본정보", prefix=True), before=True, pb=True)
        a(f("검토항목검토내용보고서페이지적합여부E.모델링공통사항", prefix=True), before=True, pb=True)
        a(f("제1장건물개요1.1일반사항", prefix=True), before=True)
        a(f("1.3내진등급및성능목표", last=True), before=True, pb=True)
        a(f("1.4구조변경이력사항", last=True), before=True, pb=True)
        cover2 = f("제2장현장조사2.1현장조사개요", prefix=True)
        body2 = cover2.getnext()
        while body2 is not None and _empty_para(body2):
            body2 = body2.getnext()
        a(body2, before=True, pb=True)
        a(f("2.1.3세부사항", last=True), before=True, unpb=True)  # 목록 밖 — 이어 붙임(10/27)
        a(f("2.2철근콘크리트조사", last=True), before=True, pb=True)
        a(f("【부재단면조사수량】"), before=True)
        a(f("【부재단면치수조사결과】"), before=True, after=True, pb=True)  # 무조건 새 쪽(10/27 사용자 "부재단면·철근배근·조적 결과표는 새 페이지부터 [고정]")
        a(f("2.2.2철근배근", last=True), before=True, pb=True)
        a(f("(3)철근배근조사결과"), pb=True)  # 철근배근 조사결과 — 제목·표가 새 쪽(고정)
        a(f("【철근배근조사결과】"), before=True, after=True)
        a(f("2.2.3콘크리트압축강도", last=True), before=True)
        a(f("2.2.4재료강도의결정", last=True), before=True, pb=True)
        a(f("압축강도시험성적서", numbered=True), before=True, unpb=True)  # 목록 밖(10/27)
        a(f("조사결과", numbered=True), before=True, pb=True)  # 2.2.4 (2) 조사결과 늘 새 쪽(10/27 사용자 "조사결과도 다음 페이지로" — 성적서 아래 남은 두 줄에 걸리던 것)
        a(f("2.3외관조사", last=True), before=True, pb=True)
        a(f("【금회균열및기타결함현황조사결과표】"), before=True, pb=True)  # 늘 새 쪽(10/27 사용자 목록)
        a(f("2.4마감재및조적조조사", last=True), before=True, pb=True)  # 결함 표가 한 표가 되면 2.4가 바로 뒤에 붙어 중량물 사진 표가 쪽 끝에서 넘침
        a(f("(2)조사내용", after=f("2.4.1중량물", last=True)), after=True)
        a(f("2.4.2마감재", last=True), before=True, pb=True)
        a(f("2.4.3조적조", last=True), before=True, pb=True)  # 늘 새 쪽(10/27 사용자 "위 내용이 짧아도 다음 페이지부터" — 제목만 쪽 끝에 걸리던 것)
        a(f("【조적벽상태평가를위한예시】"), before=True, pb=True)  # 표 제목만 쪽 끝에 걸리던 것 — 늘 새 쪽(10/27)
        a(f("조적벽의치수및상태조사에서순수조적두께는", prefix=True), before=True, unpb=True)  # 목록 밖(10/27) — 결과표 제목이 늘 새 쪽
        a(f("[조적벽치수및상태조사결과표]"), before=True, after=True, pb=True)  # 조적벽 결과표 새 쪽(고정)
        a(f("2.5지반및기초", last=True), before=True, pb=True)  # 늘 새 쪽(10/27) — 앞 빈 줄 2개도 지움(쪽 나눔 앞 빈 줄은 앞 쪽에서 넘쳐 빈 쪽)
        a(f("지반조사현황(BH-1)", prefix=True), before=True, unpb=True)  # 2.5 안 — 목록 밖(10/27)
        a(f("지반조사현황(BH-2)", prefix=True), before=True, unpb=True)
        a(f("BH-1지반조사결과"), before=True, unpb=True)
        a(f("BH-2지반조사결과"), before=True, unpb=True)

    # ---- ⑤ 여백 12mm + 한 쪽짜리 표·그림 줄이기 ----
    def _tbl(self, head: str, rc=None, nth: int = 0, height: int | None = None):
        """표 첫 글(앞부분)·줄×칸·몇 번째로 바깥 표 찾기 — height를 주면 지금 높이가 그것인지 확인(다른 원본이면 멈춤)."""
        hits = [t for t in self.root.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None
                and _t(t).startswith(head) and (rc is None or (t.get("rowCnt"), t.get("colCnt")) == rc)]
        if height is not None:
            same = [t for t in hits if int(t.find(f"{{{HP}}}sz").get("height")) == height]
            if not same:
                raise SystemExit(f"{head} {rc} 표 중 높이 {height}인 것이 없음(있는 높이 {[t.find(f'{{{HP}}}sz').get('height') for t in hits]}) — 원본이 달라졌으면 손으로 확인")
            hits = same
        if len(hits) <= nth:
            raise SystemExit(f"표 못 찾음: {head} {rc} {nth}")
        return hits[nth]

    def _shrink_row(self, t, r: int, delta: int, what: str, table_too: bool = True) -> None:
        """r번째 줄 높이를 delta만큼(줄에 걸친 칸은 함께), 표 높이도."""
        for tc in t.iter(f"{{{HP}}}tc"):
            if next(tc.iterancestors(f"{{{HP}}}tbl")) is not t:
                continue
            r0, rs = int(tc.find(f"{{{HP}}}cellAddr").get("rowAddr")), int(tc.find(f"{{{HP}}}cellSpan").get("rowSpan"))
            if r0 <= r < r0 + rs:
                sz = tc.find(f"{{{HP}}}cellSz")
                sz.set("height", str(int(sz.get("height")) - delta))
        if table_too:
            sz = t.find(f"{{{HP}}}sz")
            sz.set("height", str(int(sz.get("height")) - delta))
        self.log.append(f"⑤ {what} 줄 {r + 1} −{delta}")

    def _shrink_pics(self, t, delta: int, what: str, table_too: bool = True) -> None:
        """표 안 그림(사진·도면 틀) 높이를 delta만큼 같은 비율로(폭도) — 칸보다 큰 그림이 칸을 키우던 곳은 줄 높이를 두어도 칸이 줄어듦. 표 높이도."""
        pics = list(t.iter(f"{{{HP}}}pic"))
        for pic in pics:
            h = int(pic.find(f"{{{HP}}}curSz").get("height"))
            _scale_pic(pic, (h - delta) / h)
        if table_too:
            sz = t.find(f"{{{HP}}}sz")
            sz.set("height", str(int(sz.get("height")) - delta))
        self.log.append(f"⑤ {what} 그림 {len(pics)}개 −{delta}")

    def _top_of(self, el):
        """표(또는 그 안 요소)의 바깥 문단."""
        while not (el.tag == f"{{{HP}}}p" and el.getparent() is self.root):
            el = el.getparent()
        return el

    def margins(self, mm: float) -> bool:
        """용지 여백 위·머리말·꼬리말·아래 = mm(좌우·제본 그대로). 이미 그 값이면 False(⑤ 전체 건너뜀)."""
        v = str(round(mm * 7200 / 25.4))
        m = next(self.root.iter(f"{{{HP}}}pagePr")).find(f"{{{HP}}}margin")
        if all(m.get(k) == v for k in ("top", "header", "footer", "bottom")):
            return False
        self.log.append(f"⑤ 용지 여백 위·머리말·꼬리말·아래 {mm:g}mm({v}) ← " + "/".join(m.get(k) for k in ("top", "header", "footer", "bottom")))
        for k in ("top", "header", "footer", "bottom"):
            m.set(k, v)
        return True

    def shrink12(self) -> None:
        """여백 12mm(본문 70580)에서 넘치던 한 쪽짜리 표·그림 — 10/27 밤 시험(호원초·삼숭초 12mm본을 기준본과 쪽마다 견줌: 넘친 만큼 + 10pt 안팎, 100 = 1pt).
        줄이는 양은 원본 틀(여백 10·8·6·10) 기준이라 표 높이를 확인하고 다르면 멈춤."""
        f, row, pics = self._tbl, self._shrink_row, self._shrink_pics
        t = f("l", ("5", "5"), 0, 63049)  # 등록증: 제목 + 표 727pt > 706
        row(t, 2, 3500, "등록증", table_too=False)
        pics(t, 3500, "등록증")
        p0, p1 = self.find("시설물위치도및전경사진"), self.find("참여기술자명단", last=True)
        tops = self.tops()
        between = [t for p in tops[tops.index(p0):tops.index(p1)] for t in p.iter(f"{{{HP}}}tbl") if rb._pic_slots(t)]
        if [(t.get("rowCnt"), t.get("colCnt")) for t in between] != [("2", "3"), ("2", "1")]:
            raise SystemExit("위치도·전경 표 모양이 예상과 다름 — 손으로 확인")
        row(between[0], 0, 1500, "위치도", table_too=False)  # 위치도 + 전경 722pt > 706
        pics(between[0], 1500, "위치도")
        pics(between[1], 1500, "전경(사진이 칸보다 커 칸을 키움)")
        row(f("책임기술자종합의견", ("4", "3"), 0, 70055), 2, 2000, "종합의견(표지 뒤)")  # 695pt — 글이 길어지면 바로 넘침
        row(f("책임기술자종합의견", ("4", "5"), 0, 69027), 2, 3000, "요약문 종합의견")  # 704pt
        row(f("구분내용분석결과", ("2", "2"), 0, 44475), 1, 2500, "요약문 가. 결함조사 분석")  # (1) 현장시험 쪽 708pt
        row(f("구분내용분석결과", ("2", "2"), 0, 22740), 1, 2300, "2.3 (2) 균열 분석")  # 713pt — 마지막 작은 표가 혼자 다음 쪽
        row(f("(1)건물명", ("9", "6"), 0, 25491), 6, 5000, "1.1 일반사항 (7) 재료강도(두 줄 글에 96pt)")  # 1.1 + 1.2 쪽 752pt > 706 — 글이 길면 칸이 알아서 늘어남
        pics(f("(1)층수", ("8", "4"), 0, 34935), 2500, "1.2 건물규모 전경 틀")
        plans = [t for t in self.root.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None and (t.get("rowCnt"), t.get("colCnt")) == ("3", "4")
                 and rb._pic_slots(t) and _t(rb._cells(t).get((2, 0), t)).endswith("평면도")]
        if len(plans) < 2:
            raise SystemExit("평면도 틀을 못 찾음")
        for t in plans:
            pics(t, 1000, "평면도 틀(한 쪽 두 장 709pt)")
        first, last = (self._top_of(plans[0]), self._top_of(plans[-1]))  # 평면도 칸 사이 빈 줄(견본 쪽 나눔용 2개씩) — 12mm에선 다음 쪽 머리에 남아 한 쪽 한 장이 됨
        q, gone = first.getnext(), 0
        while q is not None and q is not last:
            nxt = q.getnext()
            if q.tag == f"{{{HP}}}p" and _empty_para(q):
                q.getparent().remove(q)
                gone += 1
            q = nxt
        if gone:
            self.log.append(f"⑤ 평면도 칸 사이 빈 줄 {gone}개 지움")
        certs = [t for t in self.root.iter(f"{{{HP}}}tbl") if next(t.iterancestors(f"{{{HP}}}tbl"), None) is None and (t.get("rowCnt"), t.get("colCnt")) == ("1", "1")
                 and t.find(f"{{{HP}}}sz").get("height") == "68645" and rb._pic_slots(t)]
        if len(certs) != 2:
            raise SystemExit(f"성적서 틀 2개가 아님: {len(certs)}")
        for t in certs:
            row(t, 0, 1500, "성적서 틀(제목 + 틀 704pt)")
        pics(f("조사내용건물외부마감재", None, 0, 22120), 2300, "2.4.2 마감재 사진 틀")  # 2.4.2 쪽 721pt
        # 체크리스트 표지(709pt): 소재지와 날짜 사이 빈 줄 5개 중 2개 지움
        p = self._top_of(f("책임자소속", ("1", "8"), 0))
        date = p.getprevious()
        while date is not None and not _t(date):  # 빈 줄 4개·도장 그림 문단을 거슬러 날짜 줄까지
            date = date.getprevious()
        if date is None or not re.match(r"^\d{4}년\d{1,2}월일?$", _t(date)):
            raise SystemExit(f"체크리스트 표지 날짜 줄을 못 찾음: {_t(date)[:20] if date is not None else None}")
        blanks = self._blanks(date, -1)
        if len(blanks) < 4:
            raise SystemExit(f"체크리스트 표지 날짜 앞 빈 줄이 {len(blanks)}개뿐")
        for b in blanks[:2]:
            b.getparent().remove(b)
        self.log.append("⑤ 체크리스트 표지 날짜 앞 빈 줄 2개 지움")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--src")
    ap.add_argument("--mm", type=float, help="⑤ 용지 여백 위·머리말·꼬리말·아래(mm) + 한 쪽짜리 표·그림 줄이기(12)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    src = Path(a.src) if a.src else master.master_path("성능평가본문")
    fx = Fix(Hwpx(src))
    fx.numbers()
    fx.toc()
    fx.rows()
    fx.blanks()
    if a.mm and fx.margins(a.mm):
        fx.shrink12()
    for line in fx.log:
        print(" ·", line)
    if not fx.log:
        print("고칠 곳 없음(이미 고침)")
        return
    if a.dry:
        return
    if a.out:
        fx.doc.save(Path(a.out), drop_unused=False)
        print("저장:", a.out)
        return
    old = master.master_dir() / "_지난원본" / f"{src.stem}_{datetime.datetime.fromtimestamp(src.stat().st_mtime):%Y%m%d_%H%M%S}.hwpx"
    old.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, old)
    fx.doc.save(src, drop_unused=False)
    print("원본 고침:", src, "| 옛것:", old)


if __name__ == "__main__":
    main()
