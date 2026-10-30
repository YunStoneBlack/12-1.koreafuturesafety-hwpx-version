"""건축물관리점검 — 소항목마다 법령상 적용대상인지(2026-10-30 사용자 "법령에 해당없음이면 해당없음", "규칙은 추천으로 가자").

근거는 server/blcm/na_rules_draft.json(국가법령정보센터 원문·시행일, 217차)과 회사 결정 15개(검토 페이지 추천안 그대로, 10만 민재형 지시):
 1 신설·강화된 규제는 허가 당시, 없어지거나 풀린 규제는 현행 기준 · 2 허가일이 기준일 뒤 3개월 안이면 "확인 필요"(법은 허가 신청일) ·
 3 의무가 없어도 설치돼 있으면 점검 · 4 구조·용도변경이 없으면 해당없음 · 5 범죄예방 2014.11.29~2015.3.31 허가분 해당없음 ·
 6 범죄예방 대상 용도가 일부 층에만 있으면 "확인 필요" · 7 세대수는 단지 기준 · 8 3.1.11 = 사용승인도면 대비 변경 점검(늘 적용) ·
 9 법상 내진 대상이 아니어도 대장 "적용"이면 적용 · 10 실내건축 = 사용승인일 → 대장 용도, 입주 업종은 안 봄(10/30 민재형 — 담당자 통화) ·
 11 공공 의무 대상인데 인증 없음 = 적용(의견) ·
 12 저수조 청소 주기(판정 쪽) · 13 대지안의 공지 공백기(1999.2.8~2006.5.8) 허가분 해당없음 · 14 조경 면제 대상이면 조경면적이 있어도 해당없음 ·
 15 현장 체크는 옹벽·석축 / 사면·절개지 따로.

판정 = {"state", "why", "reason", "asks"}:
  state apply(적용 — 점검·사진) · na(해당없음 — reason = 비고에 넣을 사유) · ask(현장·면담·서류 답이 있어야 — asks = 물을 것) · check(대장 값이 모자라거나 경계 — 사람 확인).
점검 목록(plan): 반드시 찍을 사진 / 있으면 찍을 사진(현장에 있는지 물음) / 면담으로 확인 / 서류로 확인 / 해당없음(안 찍어도 됨) / 확인 필요."""
from __future__ import annotations

import datetime
import re

from server.blcm import items as I

# 현장·면담·서류로 받는 답(job.contract["facts"] = {key: "있음"|"없음"}) — kind: site 현장에서 봄(있으면 찍기) · talk 관리자 면담 · land 토지이용계획확인원
FACTS = {
    "retaining": ("site", "옹벽·석축이 있나요?"),
    "slope": ("site", "사면·절개지가 있나요?"),
    "fence": ("site", "담장이 있나요?"),
    "roof_garden": ("site", "옥상조경(옥상 화단·식재)이 있나요?"),
    "piloti_parking": ("site", "1층 필로티 주차장이 있나요?"),
    "ac": ("site", "냉방설비(냉방기·실외기·냉동기)가 있나요?"),
    "heat": ("site", "난방설비(보일러·히트펌프·지역난방)가 있나요?"),
    "vent": ("site", "기계환기설비·환기구가 있나요?"),
    "lightning": ("site", "피뢰설비(피뢰침)가 있나요?"),
    "broadcast": ("site", "방송수신설비(공동시청 안테나·위성·유선)가 있나요?"),
    "elevator": ("site", "승강기가 있나요?"),
    "roof_plaza": ("site", "옥상광장(옥상 출입·난간)이 있나요?"),
    "store24": ("talk", "24시간 영업하는 편의점(일용품 소매점)이 있나요?"),
    "unauth_change": ("talk", "사용승인 뒤 증축·구조변경·용도변경(무단 포함)이 있었나요?"),
    "multi_use": ("talk", "다중이용업소(노래방·PC방·학원 등 다중이용업)가 있나요?"),
    "certs": ("talk", "받은 건축물 인증(녹색·에너지효율·제로에너지·지능형)이 있나요?"),
    "public_owner": ("talk", "공공기관·지자체·교육청 소유·관리 건물인가요?"),
    "fire_district": ("land", "토지이용계획확인원에 방화지구가 있나요?"),
    "street_height": ("land", "토지이용계획확인원에 가로구역별 최고높이 지정이 있나요?"),
    "district_plan": ("land", "토지이용계획확인원에 지구단위계획구역이 있나요?"),
}


def _d(s) -> datetime.date | None:
    if isinstance(s, datetime.date):
        return s
    m = re.search(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", str(s or ""))
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


D = lambda y, m, d: datetime.date(y, m, d)  # noqa: E731


def _near(permit: datetime.date | None, day: datetime.date) -> bool:
    """결정 2 — 허가일이 기준일 뒤 3개월 안(법은 허가 '신청일' 기준이라 경계면 확인 필요)."""
    return bool(permit) and day <= permit < day + datetime.timedelta(days=92)


def _floor_no(f: str) -> int | None:
    f = (f or "").replace(" ", "")
    m = re.match(r"지(?:하)?(\d+)", f)
    if m:
        return -int(m.group(1))
    m = re.match(r"(?:지상)?(\d+)층", f)
    return int(m.group(1)) if m else None


class Bldg:
    """판정에 쓰는 건축물 값(대장 개요 + 층별) — 숫자·날짜를 고르게."""

    def __init__(self, b: dict, floors: list | None = None):
        self.b = b or {}
        self.floors = floors if floors is not None else (self.b.get("floors") or [])
        self.permit = _d(self.b.get("permit_date"))
        self.approval = _d(self.b.get("approval_date"))
        n = lambda k: float(self.b.get(k)) if isinstance(self.b.get(k), (int, float)) else None  # noqa: E731
        self.site_area, self.total, self.height = n("site_area"), n("total_area"), n("height")
        self.above, self.below = int(self.b.get("above") or 0), int(self.b.get("below") or 0)
        self.zone = str(self.b.get("zone") or "") + " " + str(self.b.get("district") or "") + " " + str(self.b.get("area_zone") or "")
        self.use = str(self.b.get("use") or "")
        self.structure = str(self.b.get("structure") or "")
        self.addr = str(self.b.get("lot_address") or self.b.get("address") or "")
        hh = re.findall(r"(\d+)\s*(호|가구|세대)", str(self.b.get("households") or ""))
        self.hh = {k: int(v) for v, k in hh}
        self.uses_all = " ".join([self.use] + [str(x.get("use") or "") for x in self.floors])

    def has(self, pat: str) -> bool:
        return bool(re.search(pat, self.uses_all))

    def main_has(self, pat: str) -> bool:
        return bool(re.search(pat, self.use))

    def area_of(self, pat: str) -> float:
        return sum(float(x.get("area") or 0) for x in self.floors if re.search(pat, str(x.get("use") or "")))

    def high_floors_use(self, pat: str, from_floor: int) -> list[str]:
        return [x.get("floor") for x in self.floors if (_floor_no(x.get("floor")) or 0) >= from_floor and re.search(pat, str(x.get("use") or ""))]

    def apartment(self) -> bool:
        return self.has(r"아파트|공동주택")

    def households(self) -> int:
        return self.hh.get("세대", 0)


def R(state: str, why: str, reason: str = "", asks: list | None = None) -> dict:
    return {"state": state, "why": why, "reason": reason, "asks": asks or []}


APPLY = lambda why="": R("apply", why or "적용대상")  # noqa: E731


def _fact(facts: dict, key: str) -> str:
    v = (facts or {}).get(key) or ""
    return v if v in ("있음", "없음") else ""


def _presence(facts: dict, key: str, na_reason: str, why_yes: str = "있음 — 점검") -> dict:
    v = _fact(facts, key)
    if v == "있음":
        return APPLY(why_yes)
    if v == "없음":
        return R("na", "현장에 없음", na_reason)
    return R("ask", FACTS[key][1], asks=[key])


def _ymd(d: datetime.date | None) -> str:
    return f"{d:%Y.%m.%d}" if d else "-"


HOUSE = r"아파트|연립|다세대|다가구|단독주택|공동주택"  # 주택법 주택(분양법 적용 제외)
SALE_OUT = r"지식산업센터|관광숙박|노인복지|노인요양|양로"  # 분양법 제3조 제2항 적용 제외(주택 말고)
CRIME_USES = r"오피스텔|다중생활시설|고시원|문화\s*및\s*집회|교육연구|노유자|수련|일용품|소매점|편의점|아파트|다가구|다세대|연립"


def _crime_base(x: Bldg) -> dict | None:
    """범죄예방(3.1.12~3.1.20) 공통 — 결정 5: 2015.4.1 전 허가는 해당없음(법 시행 2014.11.29 + 기준 고시 2015.4.1), 경계 확인."""
    if not x.permit:
        return R("check", "대장 허가일이 없음 — 허가일로 범죄예방 적용 여부를 가름")
    if x.permit < D(2015, 4, 1):
        return R("na", "허가일 2015.4.1 전",
                 f"본 건축물의 허가일({_ymd(x.permit)})이 범죄예방 건축기준[건축법 제53조의2 시행 2014.11.29, 기준 고시 제정 2015.4.1] 이전으로 적용대상에 해당되지 않음.")
    if _near(x.permit, D(2015, 4, 1)):
        return R("check", "허가일이 기준 고시 제정(2015.4.1) 직후 — 허가 신청일 확인")
    return None


def evaluate(code: str, x: Bldg, facts: dict) -> dict:  # noqa: C901 — 항목마다 법령 규칙(한 곳에 모음)
    f = facts or {}
    # ---------- 3.1 대지·높이·범죄예방 ----------
    if code == "3.1.1":
        if x.site_area is not None and x.site_area < 200:
            return R("na", "대지 200㎡ 미만", f"본 건축물의 대지면적({x.site_area:g}㎡)이 200㎡ 미만으로 건축법 제42조에 따른 조경 의무 대상이 아님.")
        if re.search(r"녹지지역", x.zone):
            return R("na", "녹지지역", "본 건축물은 녹지지역에 있어 건축법 시행령 제27조제1항에 따라 조경 의무 대상이 아님.")
        if re.search(r"자연환경보전|농림지역|관리지역", x.zone) and _fact(f, "district_plan") != "있음":
            return R("na", "자연환경보전·농림·관리지역", "본 건축물은 자연환경보전·농림·관리지역(지구단위계획구역 아님)에 있어 건축법 시행령 제27조제1항에 따라 조경 의무 대상이 아님.")
        if x.main_has(r"^축사|^공장") or re.search(r"가설", str(x.b.get("register_type") or "")):
            return R("na", "공장·축사·가설", "본 건축물은 건축법 시행령 제27조제1항 조경 면제 대상(공장·축사·가설건축물 등)에 해당되어 적용대상이 아님.")
        return APPLY()
    if code == "3.1.2":
        base = evaluate("3.1.1", x, f)
        if base["state"] == "na":
            return R("na", "대지 조경 대상 아님", base["reason"].replace("조경 의무", "조경(옥상조경 포함) 의무"))
        return _presence(f, "roof_garden", "본 건축물은 옥상조경이 설치되어 있지 않아 해당없음(옥상조경은 설치 의무가 아니며 설치 시 조경면적으로 산정하는 기준임).")
    if code == "3.1.3":
        if float(x.b.get("open_space_area") or 0) > 0:
            return APPLY("대장에 공개공지 면적")
        if not re.search(r"일반주거|준주거|상업|준공업", x.zone):
            return R("na", "대상 지역 아님", f"본 건축물은 {x.zone.strip() or '해당 용도지역'}으로 건축법 시행령 제27조의2제1항의 공개공지 확보 대상 지역(일반주거·준주거·상업·준공업지역)이 아님.")
        if x.total is not None and x.total < 5000:
            return R("na", "연면적 5천㎡ 미만", f"본 건축물은 연면적 {x.total:,.1f}㎡로 건축법 시행령 제27조의2제1항의 공개공지 확보 대상(해당 용도 바닥면적 합계 5,000㎡ 이상)에 해당되지 않음.")
        big = x.area_of(r"문화\s*및\s*집회|종교|판매|운수|업무|숙박")
        if x.floors and big < 5000:
            return R("na", "대상 용도 5천㎡ 미만", f"본 건축물의 공개공지 대상 용도(문화·집회, 종교, 판매, 운수, 업무, 숙박) 바닥면적 합계({big:,.1f}㎡)가 5,000㎡ 미만으로 적용대상이 아님.")
        return APPLY()
    if code in ("3.1.4", "3.1.5"):
        myeon = bool(re.search(r"\S+면(\s|$)", x.addr)) and bool(re.search(r"자연환경보전|농림지역|관리지역", x.zone))
        if myeon and _fact(f, "district_plan") == "없음":
            return R("na", "면 지역", "본 건축물은 도시지역·지구단위계획구역 밖의 면 지역에 있어 건축법 제3조제2항에 따라 해당 조문이 적용되지 않음.")
        if myeon:
            return R("ask", FACTS["district_plan"][1], asks=["district_plan"])
        return APPLY()
    if code in ("3.1.6", "3.1.7", "3.1.11"):  # 결정 8 — 3.1.11은 사용승인도면 대비 높이·외형 변경 점검
        return APPLY()
    if code == "3.1.8":
        if x.permit and D(1999, 2, 8) <= x.permit <= D(2006, 5, 8):  # 결정 13
            return R("na", "대지안의 공지 조문 없던 기간 허가",
                     f"본 건축물의 허가일({_ymd(x.permit)})은 대지 안의 공지 규정이 없던 기간(1999.2.8~2006.5.8)으로 적용대상에 해당되지 않음.")
        return APPLY()
    if code == "3.1.9":  # 결정 1 — 도로사선 폐지(2015.5.18, 완화)는 현행 기준: 가로구역 높이 지정이 있을 때만
        v = _fact(f, "street_height")
        if v == "있음":
            return APPLY("가로구역 높이 지정")
        if v == "없음":
            return R("na", "가로구역 높이 지정 없음", "본 건축물의 대지는 건축법 제60조에 따른 가로구역별 최고높이 지정 지역이 아니어서 해당없음(토지이용계획확인원).")
        return R("ask", FACTS["street_height"][1], asks=["street_height"])
    if code == "3.1.10":
        apt = x.apartment()
        if re.search(r"일반상업|중심상업", x.zone) and not re.search(r"전용주거|일반주거", x.zone):
            return R("na", "상업지역", f"본 건축물은 {x.zone.strip()}에 있어 건축법 제61조 일조 등의 확보를 위한 높이 제한 대상이 아님.")
        if not re.search(r"전용주거|일반주거", x.zone) and not apt:
            return R("na", "주거지역·공동주택 아님",
                     f"본 건축물은 {x.zone.strip() or '전용·일반주거지역 밖'}의 {x.use or '비주거 용도'}로 건축법 제61조 일조 등의 확보를 위한 높이 제한 대상(전용·일반주거지역 건축물, 공동주택)이 아님.")
        return APPLY()
    if code in ("3.1.12", "3.1.13", "3.1.14", "3.1.15"):
        b = _crime_base(x)
        if b:
            return b
        old = x.permit < D(2019, 7, 1)
        target = CRIME_USES if not old else r"오피스텔|다중생활시설|고시원|문화\s*및\s*집회|교육연구|노유자|수련|일용품|소매점|편의점"
        if old and x.apartment() and x.households() >= 500:
            return APPLY("500세대 이상 아파트")
        if x.main_has(target):
            return APPLY("범죄예방 대상 용도")
        if x.has(target):  # 결정 6 — 일부 층에만
            return R("check", "범죄예방 대상 용도가 일부 층에만 — 대상 여부 확인")
        return R("na", "범죄예방 대상 용도 없음",
                 f"본 건축물의 용도({x.use})는 건축법 시행령 제63조의7에 따른 범죄예방 기준 적용 대상 건축물에 해당되지 않음.")
    if code in ("3.1.16", "3.1.17", "3.1.18", "3.1.19", "3.1.20"):
        b = _crime_base(x)
        if b:
            return b
        if code == "3.1.16":
            need = 100 if x.permit >= D(2019, 7, 1) else 500
            if x.apartment() and x.households() >= need:
                return APPLY(f"{need}세대 이상 아파트")
            return R("na", "대상 아파트 아님", f"본 건축물은 {need}세대 이상 아파트가 아니어서 범죄예방 건축기준 세부기준(100세대 이상 아파트) 대상이 아님.")
        if code == "3.1.17":
            house = x.permit >= D(2019, 7, 1) and (x.has(r"다가구|다세대|연립") or (x.apartment() and x.households() < 100))
            if house or x.has(r"오피스텔"):
                return APPLY("다가구·다세대·연립·소규모 아파트·오피스텔")
            return R("na", "대상 주택·오피스텔 없음", "본 건축물에는 다가구·다세대·연립주택, 100세대 미만 아파트, 오피스텔이 없어 해당 세부기준 대상이 아님.")
        if code == "3.1.18":
            if re.search(r"문화\s*및\s*집회|노유자|수련", x.uses_all) or re.search(r"교육연구(?!.*(연구소|도서관))", x.uses_all):
                return APPLY("문화·집회·교육연구·노유자·수련시설")
            return R("na", "대상 용도 없음", "본 건축물에는 문화 및 집회·교육연구·노유자·수련시설이 없어 해당 세부기준 대상이 아님.")
        if code == "3.1.19":
            if not x.has(r"소매점|편의점|일용품"):
                return R("na", "일용품 소매점 없음", "본 건축물에는 일용품 소매점이 없어 해당 세부기준(24시간 일용품 소매점) 대상이 아님.")
            return _presence(f, "store24", "본 건축물의 소매점은 24시간 영업이 아니어서 해당 세부기준 대상이 아님.", "24시간 소매점 — 점검")
        if code == "3.1.20":
            if x.has(r"다중생활시설|고시원"):
                return APPLY("다중생활시설")
            return R("na", "다중생활시설 없음", "본 건축물에는 다중생활시설이 없어 해당 세부기준 대상이 아님.")
    # ---------- 3.2 설비 ----------
    if code in ("3.2.1", "3.2.2", "3.2.8"):
        return APPLY()
    if code == "3.2.3":
        return _presence(f, "ac", "본 건축물에는 냉방설비가 설치되어 있지 않아 해당없음.") if _fact(f, "ac") == "없음" else APPLY("냉방설비 — 없으면 [없음]")
    if code == "3.2.4":
        return _presence(f, "heat", "본 건축물에는 난방설비가 설치되어 있지 않아 해당없음.") if _fact(f, "heat") == "없음" else APPLY("난방설비 — 없으면 [없음]")
    if code == "3.2.5":
        hh_need = 30 if (x.permit and x.permit >= D(2020, 10, 10)) else 100
        if x.apartment() and x.households() >= hh_need:
            return APPLY(f"공동주택 {hh_need}세대 이상")
        return _presence(f, "vent", "본 건축물은 환기설비 설치 의무 대상(공동주택·다중이용시설)이 아니고 기계환기설비·환기구가 없어 해당없음.")
    if code == "3.2.6":
        if x.height is not None and x.height >= 20:
            return APPLY(f"높이 {x.height:g}m(20m 이상)")
        return _presence(f, "lightning", f"본 건축물은 높이 {x.height or 0:g}m로 건축물의 설비기준 등에 관한 규칙 제20조 피뢰설비 설치 대상(20m 이상)이 아니고 피뢰설비가 없어 해당없음.")
    if code == "3.2.7":
        big = x.area_of(r"업무|숙박")
        if x.permit and x.permit >= D(2009, 7, 16) and (x.apartment() or big >= 5000):
            return APPLY("방송 공동수신설비 설치 의무")
        return _presence(f, "broadcast", "본 건축물은 방송 공동수신설비 설치 의무 대상이 아니고 방송수신설비가 없어 해당없음.")
    if code == "3.2.9":
        if x.above >= 6 and (x.total or 0) >= 2000:
            return APPLY("6층 이상·2천㎡ 이상")
        return _presence(f, "elevator", f"본 건축물은 지상 {x.above}층으로 건축법 제64조 승강기 설치 대상(6층 이상·연면적 2,000㎡ 이상)이 아니고 승강기가 없어 해당없음.")
    # ---------- 3.3 에너지 ----------
    if code == "3.3.1":
        return APPLY()
    if code == "3.3.2":  # 결정 11
        if _fact(f, "certs") == "있음":
            return APPLY("받은 인증 있음")
        if _fact(f, "public_owner") == "있음":
            return APPLY("공공 소유 — 인증 의무(없으면 개선 의견)")
        if _fact(f, "certs") == "없음" and _fact(f, "public_owner") == "없음":
            return R("na", "민간·받은 인증 없음",
                     "본 건축물은 민간 건축물로 녹색건축물 조성 지원법에 따른 인증 의무 대상이 아니며 받은 인증(녹색·에너지효율·제로에너지·지능형)이 없어 해당없음.")
        return R("ask", "받은 인증·공공 소유 여부", asks=[k for k in ("certs", "public_owner") if not _fact(f, k)])
    # ---------- 3.4 구조 ----------
    if code == "3.4.1":
        a, b = _fact(f, "retaining"), _fact(f, "slope")
        if "있음" in (a, b):
            return APPLY("옹벽·석축 또는 사면 있음")
        if a == "없음" and b == "없음":
            return R("na", "옹벽·석축·사면 없음", "본 건축물은 옹벽 및 사면이 없는 것으로 조사되어 해당없음.")
        return R("ask", "옹벽·석축 / 사면·절개지", asks=[k for k in ("retaining", "slope") if not _fact(f, k)])
    if code == "3.4.2":
        return _presence(f, "fence", "본 건축물은 담장이 없는 건축물로 조사되어 해당없음.")
    if code in ("3.4.3", "3.4.4", "3.4.5", "3.4.6", "3.4.7"):
        return APPLY()
    if code == "3.4.8":  # 결정 4
        ch = [c for c in x.b.get("changes") or [] if re.search(r"증축|개축|대수선|용도변경|구조변경|철거", str(c.get("text") or ""))]
        if ch or _fact(f, "unauth_change") == "있음":
            return APPLY("변동사항·현장 변경 있음")
        if _fact(f, "unauth_change") == "없음":
            return R("na", "구조·용도변경 없음", "건축물대장 변동사항 및 현장 조사 결과 사용승인 이후 구조변경 및 용도변경이 없어 해당없음.")
        return R("ask", FACTS["unauth_change"][1], asks=["unauth_change"])
    if code == "3.4.9":  # 결정 9 + 허가 당시 내진 의무 기준
        if re.search(r"적용", str(x.b.get("seismic_design") or "")) and "미" not in str(x.b.get("seismic_design") or ""):
            return APPLY("대장 내진설계 적용")
        if not x.permit:
            return R("check", "대장 허가일이 없음 — 허가 당시 내진설계 대상 확인")
        p, t, h = x.permit, x.total or 0, x.height or 0
        need = ((p >= D(2017, 12, 1)) or (p >= D(2017, 2, 4) and (x.above >= 2 or t >= 500)) or (p >= D(2015, 9, 22) and (x.above >= 3 or t >= 500))
                or (p >= D(2009, 7, 16) and (x.above >= 3 or t >= 1000 or h >= 13)) or (p >= D(2005, 7, 18) and (x.above >= 3 or t >= 1000))
                or (p >= D(1996, 1, 6) and (x.above >= 6 or t >= 10000)) or (p >= D(1992, 6, 1) and (x.above >= 6 or t >= 100000))
                or (p >= D(1988, 8, 25) and x.above >= 6))
        if need:
            return APPLY("허가 당시 내진설계 대상")
        if x.has(r"의료|병원|교육연구|학교|방송|통신"):
            return R("check", "중요도가 높은 용도 — 층수·면적 미달이어도 내진 대상일 수 있음")
        return R("na", "허가 당시 내진설계 대상 아님",
                 f"본 건축물의 허가일({_ymd(p)}) 당시 건축법 시행령 제32조의 내진설계 대상(층수·연면적 기준)에 해당되지 않아 해당없음.")
    # ---------- 3.5 화재 ----------
    if code == "3.5.1":
        if x.above <= 1 and x.below == 0 and (x.total or 0) <= 200 and not x.has(r"문화|종교|판매|위락|장례|학교"):
            return R("na", "피난층만·200㎡ 이하", "본 건축물은 피난층 외의 층이 없고 연면적 200㎡ 이하로 건축법 시행령 제34조 직통계단 등 설치 대상이 아님.")
        return APPLY()
    if code == "3.5.2":
        hi = x.high_floors_use(r"공연장|종교집회장|인터넷컴퓨터게임|문화\s*및\s*집회(?!.*(전시장|동.식물원))|종교시설|판매시설|주점|장례", 5)
        if hi or x.above >= 11:
            return APPLY(f"5층 이상 대상 용도({', '.join(hi)})" if hi else "11층 이상")
        return _presence(f, "roof_plaza", "본 건축물은 5층 이상인 층이 건축법 시행령 제40조제2항 용도가 아니어서 옥상광장 설치 대상이 아니며 옥상광장이 없어 해당없음.",
                         "의무 아니나 옥상광장 있음 — 점검")
    if code == "3.5.3":
        if x.above >= 30 or (x.height or 0) >= 120:
            return APPLY("고층건축물")
        return R("na", "고층건축물 아님", f"해당 건축물은 지하 {x.below}층, 지상 {x.above}층, 높이 {x.height or 0:g}m로 고층건축물에 해당하지 않아 건축법 제50조의2에 의한 피난안전구역 적용대상이 아님.")
    if code == "3.5.4":
        if (x.total or 0) <= 1000:
            return R("na", "연면적 1천㎡ 이하", f"본 건축물은 연면적 {x.total or 0:,.1f}㎡로 건축법 시행령 제46조 방화구획 대상(1,000㎡ 초과)이 아님.")
        if re.search(r"목구조|목조", x.structure):
            return R("na", "주요구조부 내화·불연 아님", "본 건축물은 주요구조부가 내화구조 또는 불연재료가 아니어서 건축법 시행령 제46조 방화구획 대상이 아님.")
        return APPLY()
    if code == "3.5.5":
        inner = x.has(r"다가구|다세대|공동주택|아파트|의원|공연장|학원|독서실|당구장|다중생활|공장|창고|위험물|자동차|문화|종교|판매|운수|의료|학교|교육연구|노유자|수련|오피스텔|숙박|위락|장례") \
            or sum(float(y.get("area") or 0) for y in x.floors if (_floor_no(y.get("floor")) or 0) >= 5) >= 500 or _fact(f, "multi_use") == "있음"
        if inner:
            return APPLY("내부 마감재 대상")
        if _fact(f, "multi_use") == "":
            return R("ask", FACTS["multi_use"][1], asks=["multi_use"])
        return R("na", "마감재 대상 아님", "본 건축물은 건축법 시행령 제61조 내부·외벽 마감재 기준 적용 대상에 해당되지 않음.")
    if code == "3.5.6":
        return APPLY("거실 반자 높이(배연창·배연설비는 대상일 때만)")
    if code == "3.5.7":
        if x.above < 3 and x.below == 0 and (x.total or 0) < 1000:
            return R("na", "내화구조 대상 아님", f"본 건축물은 지상 {x.above}층·지하층 없음·연면적 {x.total or 0:,.1f}㎡로 건축법 시행령 제56조 내화구조 대상이 아님.")
        return APPLY()
    if code == "3.5.8":
        v = _fact(f, "fire_district")
        if v == "있음":
            return APPLY("방화지구")
        if x.permit and x.permit >= D(2021, 6, 23):
            return APPLY("2021.6.23 이후 허가 — 외벽 창호 방화성능 기준")
        if v == "없음":
            return R("na", "방화지구 아님", f"본 건축물의 대지는 방화지구가 아니며(토지이용계획확인원) 허가일({_ymd(x.permit)})이 외벽 창호 방화성능 기준 시행(2021.6.23) 이전으로 해당없음.")
        return R("ask", FACTS["fire_district"][1], asks=["fire_district"])
    if code == "3.5.9":  # 결정 10(10/30 민재형 — 실내건축 담당자 통화): ① 사용승인일 ② 건물 용도(대장), 입주 업종은 안 봄
        if not x.approval:
            return R("check", "대장 사용승인일이 없음 — 사용승인일로 실내건축 적용 여부를 가름")
        if x.approval < D(2014, 11, 29):
            return R("na", "사용승인일 2014.11.29 전",
                     f"본 건축물의 사용승인일({_ymd(x.approval)})이 실내건축 기준[건축법 제52조의2·같은 법 시행령 제61조의2, 2014.11.29 시행] 이전으로 해당없음.")
        big = x.area_of(r"문화\s*및\s*집회|종교|판매|운수|종합병원|관광숙박")
        if x.above >= 16 or big >= 5000:
            return APPLY("다중이용 건축물")
        # 분양 건축물(분양법 제3조·시행령 제2조) — 사용승인 전 분양 여부·분양 부분 면적은 대장에 없어 짐작(민재형 10/30 "짐작으로 두고, 평가 뒤 문제 되면 수정"),
        # 적용 제외(제3조 제2항 — 주택법 주택·지식산업센터·관광숙박·노인복지시설)는 법대로 뺌
        rooms = x.hh.get("호", 0)
        if not x.main_has(SALE_OUT):
            if x.has(r"오피스텔") and (rooms >= 30 or not rooms):
                return APPLY("분양 건축물 용도(오피스텔 30실 이상)")
            lodge = x.area_of(r"생활숙박")
            if x.has(r"생활숙박") and (rooms >= 30 or not rooms or (x.total and lodge * 3 >= x.total)):
                return APPLY("분양 건축물 용도(생활숙박시설 30실 이상·영업장 연면적 1/3 이상)")
            if x.has(HOUSE):
                other = sum(float(y.get("area") or 0) for y in x.floors if y.get("use") and not re.search(HOUSE, str(y.get("use"))))
                if other >= 3000:
                    return APPLY("분양 건축물(주택과 함께 지은 건축물 — 주택 외 용도 3천㎡ 이상)")
            elif rooms >= 2 and (x.total or 0) >= 3000:
                return APPLY("분양 건축물(집합건축물·연면적 3천㎡ 이상)")
        if x.has(r"휴게음식점|제과점"):
            return APPLY("휴게음식점·제과점 용도(칸막이로 가로 구획한 곳이 대상)")
        return R("na", "실내건축 대상 용도 아님",
                 f"본 건축물은 다중이용 건축물이 아니며 건축물 용도({x.use or '-'})가 건축법 시행령 제61조의2 적용대상(다중이용 건축물·분양 건축물·휴게음식점·제과점)이 아니어서 해당없음.")
    if code == "3.5.10":
        if x.below == 0:
            return R("na", "지하층 없음", "본 건축물은 지하층이 없어 해당없음.")
        return APPLY()
    return APPLY()


def plan(b: dict, facts: dict, results: dict, floors: list | None = None) -> dict:
    """건 하나의 점검 목록 — 항목마다 판정 + 갈래(must 반드시 찍을 사진 · present 있으면 찍을 사진 · talk 면담 · land 서류 · na 해당없음 · check 확인 필요),
    물을 것(questions — 답과 영향 항목)."""
    x = Bldg(b, floors)
    out, asked = {}, {}
    for it in I.items():
        code = it["code"]
        r = evaluate(code, x, facts)
        places = I.ITEM_PLACES.get(code, ["out"])
        if r["state"] == "apply":
            cat = "must" if places != ["doc"] else "talk" if code == "3.4.6" else "doc"
        elif r["state"] == "ask":
            kinds = {FACTS[k][0] for k in r["asks"]}
            cat = "talk" if "talk" in kinds else "present" if "site" in kinds else "land"  # 면담이 섞이면 면담 쪽
        else:
            cat = r["state"]
        res = (results or {}).get(code) or {}
        out[code] = {**r, "cat": cat, "photos": len(res.get("photos") or []), "marked_na": bool(res.get("na")),
                     "touched": bool(res.get("judge") or res.get("ratings") or res.get("photos") or res.get("na") or res.get("cert"))}
        for k in r["asks"]:
            asked.setdefault(k, []).append(code)
    qs = [{"key": k, "kind": FACTS[k][0], "label": FACTS[k][1], "answer": _fact(facts, k), "items": asked.get(k, [])}
          for k in FACTS if k in asked or _fact(facts, k)]
    count = {c: sum(1 for v in out.values() if v["cat"] == c) for c in ("must", "present", "talk", "doc", "land", "na", "check")}
    return {"items": out, "questions": qs, "count": count}
