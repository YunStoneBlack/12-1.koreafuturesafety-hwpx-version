"""K2B 검색 결과에서 웹 현장과 같은 현장 고르기(2026-10-08 — 사용자: 이름이 같은데 못 찾거나 다른 현장을 고름).

원인(실측): K2B 결과 표(Nexacro 그리드)는 **화면에 보이는 5~8줄만** 그려 둔다. 예전엔 화면에 그려진 글자만 찾아 마우스로 눌러서
- 찾는 현장이 아래쪽이면 "못 찾음"(한탄강 보름리권역 — '한탄강' 17건),
- 표 가장자리에 반쯤 걸친 줄을 누르면 선택이 안 되고 K2B 기본(맨 윗줄, 다른 현장)이 그대로 → 엉뚱한 현장의 새 차수 1(TICN 차양대 — '00부대' 46건).
그래서 화면 대신 **화면 뒤 검색 결과 데이터(DS_EBP0110_R2 — 검색된 줄 전부)**를 읽어 고르고, 데이터의 줄 위치(rowposition)를 옮겨 선택한다
(옮기면 K2B가 아래 칸·상세보기를 그 현장으로 바꿈 — 실측). 고른 뒤 선택된 현장 데이터(DS_EBP0110_R3)로 맞는지 확인.

고르기(점수): 사업장관리번호·개시번호 같음(가장 확실) > 이름 같음(띄어쓰기 무시) > 공사금액 같음 > 주소 > 공사 기간.
이름이 조금 달라도 번호·금액이나 주소+기간이 맞으면 같은 현장으로 본다(사용자 (가) — 자동화 우선, 결과에 K2B 쪽 이름을 남김).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 데이터 칸: ENTRPS_NM = 현장명(BPLC_NM은 시공사 이름), CSTRN_AMT 공사금액, CSTRN_BGNG_YMD/END_YMD 공사 기간(YYYYMMDD), CONST_ADDR 소재지,
# BPLC_MNG_NO 사업장관리번호, BPLC_STRT_NO 사업장개시번호(웹 현장 정보의 "사업장관리번호(사업장개시번호)")
COLS = ["ENTRPS_NM", "CSTRN_AMT", "CSTRN_BGNG_YMD", "CSTRN_END_YMD", "CONST_ADDR", "BPLC_MNG_NO", "BPLC_STRT_NO", "BPLC_NM"]
LIST_DS, PICKED_DS = "DS_EBP0110_R2", "DS_EBP0110_R3"

# 검색 결과 화면(폼)과 데이터 찾기 — Nexacro 앱 객체 아래 gv_WorkFrame에서 DS_EBP0110_R2를 가진 폼
HELPERS_JS = r"""() => {
  const kids = (o) => (o && o.all) ? Object.keys(o.all).map(k => o.all[k]).filter(x => x && typeof x === 'object') : [];
  window.__k2bForm = function () {
    const app = window.application || (window.nexacro && nexacro._application);
    const wf = app && app.gv_WorkFrame;
    if (!wf) return null;
    for (const k of Object.keys(wf)) for (const g of kids(wf[k])) if (kids(g).some(x => x.id === '%LIST%')) return g;
    return null;
  };
  window.__k2bDs = function (id) { const f = __k2bForm(); return f ? (kids(f).find(x => x.id === id) || null) : null; };
  window.__k2bRows = function (id, cols) {
    const d = __k2bDs(id); if (!d) return null;
    const out = []; for (let r = 0; r < d.getRowCount(); r++) out.push(cols.map(c => d.getColumn(r, c)));
    return out;
  };
  return !!__k2bForm();
}""".replace("%LIST%", LIST_DS)


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _plain(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _addr(s) -> str:
    """주소 비교용 — 띄어쓰기·괄호 없애고 '경기도'→'경기' 같은 시도 줄임."""
    s = _plain(s).replace("(", "").replace(")", "")
    for long, short in (("경기도", "경기"), ("강원도", "강원"), ("강원특별자치도", "강원"), ("충청북도", "충북"), ("충청남도", "충남"),
                        ("전라북도", "전북"), ("전북특별자치도", "전북"), ("전라남도", "전남"), ("경상북도", "경북"), ("경상남도", "경남"),
                        ("서울특별시", "서울"), ("인천광역시", "인천")):
        s = s.replace(long, short)
    return s


@dataclass
class SiteKey:
    """웹 현장 쪽 비교 값(K2BSubmission에서)."""
    name: str
    address: str = ""
    amount: int | None = None
    start: str = ""  # YYYYMMDD
    end: str = ""
    mgmt_no: str = ""   # 숫자만
    start_no: str = ""


@dataclass
class Pick:
    index: int
    score: int
    reasons: list[str]
    row: dict


def score_row(key: SiteKey, row: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    if key.mgmt_no and _digits(row["BPLC_MNG_NO"]) == key.mgmt_no and (not key.start_no or _digits(row["BPLC_STRT_NO"]) == key.start_no):
        s += 200
        why.append("사업장 번호")
    if _plain(row["ENTRPS_NM"]) == _plain(key.name):
        s += 100
        why.append("이름")
    if key.amount and _digits(row["CSTRN_AMT"]) == str(key.amount):
        s += 60
        why.append("공사금액")
    a, b = _addr(key.address), _addr(row["CONST_ADDR"])
    if a and b and (a[:12] in b or b[:12] in a):
        s += 25
        why.append("주소")
    if key.start and key.end and _digits(row["CSTRN_BGNG_YMD"]) == key.start and _digits(row["CSTRN_END_YMD"]) == key.end:
        s += 25
        why.append("공사 기간")
    return s, why


def acceptable(score: int) -> bool:
    """이름만(100) · 번호(200) · 금액(60) · 주소+기간(50) 중 하나는 있어야 같은 현장으로 봄."""
    return score >= 50


def rank(key: SiteKey, rows: list[list]) -> list[Pick]:
    picks = []
    for i, vals in enumerate(rows):
        row = dict(zip(COLS, vals))
        s, why = score_row(key, row)
        if acceptable(s):
            picks.append(Pick(i, s, why, row))
    return sorted(picks, key=lambda p: -p.score)


def queries(name: str) -> list[str]:
    """검색어 — 전체 이름 → 괄호 뺀 이름 → 앞 두 낱말 → 첫 낱말(K2B 검색은 부분 일치지만 띄어쓰기가 다르면 0건이라 점점 짧게)."""
    words = name.split()
    out = [name, re.sub(r"\s*\([^)]*\)\s*$", "", name).strip(), " ".join(words[:2]), words[0] if words else name]
    seen, uniq = set(), []
    for q in out:
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq
