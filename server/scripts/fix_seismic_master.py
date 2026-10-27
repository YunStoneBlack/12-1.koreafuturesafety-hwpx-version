"""내진성능평가 본문 원본(우리 1~2장) 다듬기 — 민재형이 호원초 1~2장을 손으로 고친 것(10/26)을 틀에 옮김.
다시 돌려도 같음(이미 고친 곳은 건너뜀) — 형이 원본을 새로 올리면 한 번 더 돌리면 됨.

    python -m server.scripts.fix_seismic_master          # 고치고 옛 원본은 _지난원본/에 보관
    python -m server.scripts.fix_seismic_master --dry    # 무엇을 고칠지만
    python -m server.scripts.fix_seismic_master --out X  # 원본은 두고 고친 것을 X로(시험)

① 요약문·2.2.4 자동 번호 — 문단마다 번호 정의가 따로(모두 1부터)라 "가."만 다섯 번·"(1)"이 두 번 나오던 것 → 시작값으로 이어지게
   (나~마, (2), 나~라, 2.2.4 (2) 조사결과)
② 목차 줄 간격 200 → 190%, "목 차" 160 → 150%
③ 결과표 "라." 표·선형해석결과 층강도비(X·Y)·층간변위(X·Y) 표 줄 높이(민재형 값 — 작은 글이 빽빽하던 것)
④ 쪽 끝을 채워 다음 내용을 새 쪽으로 밀던 빈 줄 → 지우고 새 쪽에서 시작할 제목에 쪽 나눔(내용 길이가 바뀌어도 안 흐트러짐),
   쪽 나눔 빈 줄이 제목과 표 사이에 있던 곳((3) 철근 배근 조사 결과)은 제목에, 표 제목과 표 사이 빈 줄
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
from server.sitok.seismic_fill import _empty_para
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
        【금회 균열 및 기타 결함현황 조사 결과표】·2.4·2.4.2·2.4.3·[조적벽 상태 평가를 위한 예시]·[조적벽 치수 및 상태조사 결과표]·2.5, (6) 평면도·2.2.3은 만들 때 seismic_fill).
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
        a(f("조사결과", numbered=True), before=True, unpb=True)  # 목록 밖(10/27)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--src")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(a.src) if a.src else master.master_path("성능평가본문")
    fx = Fix(Hwpx(src))
    fx.numbers()
    fx.toc()
    fx.rows()
    fx.blanks()
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
