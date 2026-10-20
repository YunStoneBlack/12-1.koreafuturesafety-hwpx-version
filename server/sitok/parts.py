"""시특법 공중이용·기타시설(2026-10-12 사용자) — 현장 화면 [공중이용]·[기타시설] 탭 사진 → 보고서 1.3 6)·7) 사진 표(각 4칸)·AI 판단.

- 공중이용(6) 공중이 이용하는 부위 및 부대시설): 기준표 4항목(추락방지시설·도로포장·도로부 신축이음부·환기구 등의 덮개) — 항목마다 사진 한 장
  또는 해당없음. 보고서 표 = 항목마다 한 칸(설명 = 항목 이름, 없으면 사진 칸 "해당없음"). 예전 원본의 6칸 고정(옹벽·비탈면·난간…)은 잘못된 방식(사용자).
- 기타시설(7) 기타시설): 마감재 2장·부착물 등 2장(윗줄 마감재·아랫줄 부착물), 한 장만 찍으면 빈 칸은 사진·설명 모두 "-".
- AI 판단(evaluate): 사진을 보고 조사항목(표 6.7·6.8·6.9)·상태평가기준(표 6.44~6.47, a~e)으로 항목별 등급·한 줄 → AI 초안이 이 판단으로
  6)·7) 본문과 결과표 "공중이 이용하는 부위" 칸을 씀(server/sitok/ai_draft.py).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PUBLIC = [("fall", "추락방지시설"), ("road", "도로포장"), ("joint", "도로부 신축이음부"), ("vent", "환기구 등의 덮개")]
OTHER = [("finish", "마감재"), ("attach", "부착물 등")]
OTHER_SLOTS = 2  # 마감재·부착물 등 각 2장

# [표 6.7] 공중이 이용하는 부위 조사항목 + [표 6.44~6.47] 상태평가기준(사용자 10/12 제공)
PUBLIC_CRITERIA = {
    "fall": ("부재 상태 및 내구성 — 규격(지지구조 철물·연결재 등의 규격), 접합 및 고정상태, 탈락 및 파손 유무, 부식유무 / 변위·변형 — 처짐 및 변형유무",
             {"a": "손상 및 결함 등이 없는 최상의 상태",
              "b": "추락방지시설에 경미한 결함 및 파손이 발생하였으나, 기능에는 문제가 없으며 결함의 진행 여부를 지속적으로 관찰하고 보수 여부를 결정해야 하는 상태",
              "c": "추락방지시설에 결함 및 파손으로 인하여 기능에 일부 문제가 발생하여 간단한 보수가 필요한 상태",
              "d": "고정부 및 연결부 파손 등으로 인해 추락방지시설의 전도 및 이탈이 발생할 수 있어 즉각적인 보수·보강이 필요한 상태",
              "e": "추락방지시설의 전반적 기능저하로 사용자의 안전에 위험이 있어 즉각 사용을 금지해야 하는 상태"}),
    "road": ("포장상태 및 내구성 — 아스팔트 상태(균열·함몰·단차 및 요철·블리딩·마모), 콘크리트 상태(균열·마모·박리·파손), "
             "신축이음 전후·구조물 경계부(단차·파손), 곡선부·중차량 통행차로(마모·바퀴자국), 배수구 주변(물고임)",
             {"a": "포장상태가 최상으로 차량의 주행에 문제가 없는 상태",
              "b": "포장의 결함 및 파손이 미미하게 발생된 상태로 차량주행에 문제는 없으나 결함의 진행 여부를 지속적으로 관찰하고 보수 여부를 결정하여야 하는 상태",
              "c": "포장 결함 및 파손이 차량에 직접적인 파손을 유발할 정도는 아니나 차량 운전자에게 불쾌감을 유발할 수 있어 간단한 보수가 필요한 상태",
              "d": "깊이 8cm 이상의 포트홀에 의해 차량에 심각한 손상이 발생할 수 있어 즉각적인 보수가 필요한 상태, 또는 배수불량으로 주행차로 상시 물고임으로 "
                   "통행차량의 안전성 저하가 우려되는 상태",
              "e": "도로포장 결함 및 파손 정도가 심각하고 차량주행이 불가하여 차량통행 제한 및 사용금지가 필요한 상태"}),
    "joint": ("본체 설치상태 및 부재 내구성 — 설치 및 관리상태(충격음·본체유동 및 파손·누수·유간부족 및 과다·유간 오물퇴적), 고무재(고무판 마모·강판노출 및 부식), "
              "강재(강재 연결부 이완 및 파손) / 후타재 설치상태 및 부재 내구성(단차(본체·교면포장·접속슬래브)·균열 및 파손)",
              {"a": "신축이음부에 손상이 없는 상태",
               "b": "신축이음 본체의 토사 및 이물질 퇴적, 고무판 노후, 후타재의 미세균열이 발생된 상태로 기능발휘에는 지장이 없으며 결함의 진행 여부를 지속적으로 "
                    "관찰하고 보수 여부를 결정하여야 하는 상태",
               "c": "신축이음 본체의 유간사이 이물질로 기능불량, 고무판 마모, 국부적인 부식 등의 열화가 발생한 상태 또는 후타재의 균열이 50cm 이하의 간격으로 "
                    "발생하거나, 국부적인 박리·박락·파손이 발생하여 간단한 보수가 필요한 상태",
               "d": "신축유간 밀착으로 인한 거동불량 또는 신축유간이 넓어 차량통행에 지장을 초래할 수 있어 교체가 필요한 상태, 또는 신축이음의 파손 상태가 심각하여 "
                    "차량통행 시 충격이 발생하는 등 긴급한 보수·보강이 필요한 상태",
               "e": "신축이음부 본체 탈락으로 차량주행 시 파손을 유발하거나, 주행 중 사고의 원인이 될 수 있는 상태"}),
    "vent": ("부재 상태 및 내구성 — 규격(지지구조 및 연결재 등의 규격), 접합 및 고정상태, 탈락 및 파손 유무, 부식 유무, 걸침턱 및 추락방지시설(상태 및 유무) / "
             "변위·변형 — 환기구 덮개 등의 처짐 및 변형 유무",
             {"a": "환기구 등의 덮개가 최상의 상태",
              "b": "덮개 등(지지구조 철물, 연결재, 걸침턱 등)에 결함 및 파손 등이 발생하였으나 기능 발휘에는 지장이 없고 기능성에 문제가 없는 상태, "
                   "또는 기능성에 문제가 없어 결함 및 파손에 대해 지속적 관찰이 필요한 상태",
              "c": "덮개 등(지지구조 철물, 연결재, 걸침턱 등)에 결함 및 파손 등으로 기능에 일부 문제가 발생하여 보수가 필요한 상태",
              "d": "덮개 등(지지구조 철물, 연결재, 걸침턱 등)에 결함 및 파손 등으로 기능이 상실되어 국부적인 교체 및 보강이 필요한 상태",
              "e": "결함 및 파손 정도가 심각하거나 덮개 등이 탈락된 상태"}),
}
# [표 6.8] 마감재·[표 6.9] 부착물 등 조사항목 + 기타시설 정의(사용자 10/12 제공)
OTHER_DEFINITION = ("기타시설은 구조적 내력을 부담하지 않는 비구조 요소로서, 외부 환경으로부터 사용자를 보호하거나 건축물의 외관을 장식하기 위하여 설치하는 "
                    "외장재·내장재·천장재 등의 마감재와 난간대·광고판·광고탑·첨탑·커튼월·점검용 통로(캣워크 등)·대형조명 등과 같은 부착물 등을 말한다.")
OTHER_CRITERIA = {
    "finish": "부재상태 및 내구성 — 균열발생 상태(균열 폭 및 면적률, 발생 형태), 붙임모르타르 상태(들뜸·박락·노후정도), 연결철물 시공 상태(지지구조 철물 및 "
              "연결재 노후상태 등), 균열방지 조치 상태(하중분산(조적턱·앵글선반 등)·신축줄눈) / 변위·변형 — 기울기 및 배부름(면외방향 기울기 및 배부름 발생 유무)",
    "attach": "정착부 — 앵커·브라켓 정착부(정착부 콘크리트의 균열·박락 여부, 앵커 시공상태·풀림 및 빠짐·부식 여부), 용접 정착부(용접 면적 적정성·균열·부식 등 손상), "
              "매립 정착부(정착 철물 매립 깊이·철물 여장(노출) 길이) / 연결부 — 볼트 연결부(볼트 풀림 및 빠짐·부재 변형·부식, 볼트 규격·설치 간격), "
              "용접 연결부(용접 면적 적정성·균열) / 보강부 — 와이어 로프(손상·부식·변형·고정클립 수량 및 상태) / 변위·변형 — 기울기 및 배부름",
}
GRADE_WORD = {"a": "최상", "b": "양호(경미한 결함·관찰)", "c": "보통(간단한 보수 필요)", "d": "미흡(즉각 보수·보강)", "e": "불량(사용금지)"}


def empty() -> dict:
    return {"public": {}, "other": {k: [] for k, _ in OTHER}, "grades": {}}


def norm(parts: dict | None) -> dict:
    p = parts or {}
    out = empty()
    out["public"] = {k: dict(v) for k, v in (p.get("public") or {}).items() if k in dict(PUBLIC)}
    for k, _ in OTHER:
        out["other"][k] = [x for x in ((p.get("other") or {}).get(k) or [])][:OTHER_SLOTS]
    keys = dict(PUBLIC) | dict(OTHER)
    out["grades"] = {k: g for k, g in (p.get("grades") or {}).items() if k in keys and g in ("a", "b", "c", "d", "e")}  # 정밀 3.2.7~8 등급(10/13)
    return out


def build_input(parts: dict | None, base: Path) -> dict:
    """보고서 만들 때 — {"public": [(이름, 사진 경로 | None)], "other": [(설명, 사진 경로 | None) × 4](윗줄 마감재 2, 아랫줄 부착물 2)}.
    아무것도 안 찍었으면 None(그 표는 원본 그대로 두지 않고 — report_build가 "해당없음"·"-"로)."""
    p = norm(parts)
    pub = []
    for k, name in PUBLIC:
        it = p["public"].get(k) or {}
        f = base / (it.get("file") or it.get("prev")) if (it.get("file") or it.get("prev")) else None  # 이번 사진, 없으면 전회차(옹벽 가져오기, 10/21)
        pub.append((name, str(f) if f and f.exists() else None))
    other = []
    for k, name in OTHER:
        files = [base / x for x in p["other"][k] if (base / x).exists()]
        for i in range(OTHER_SLOTS):
            other.append((name, str(files[i])) if i < len(files) else ("-", None))
    return {"public": pub, "other": other}


def recorded(parts: dict | None) -> bool:
    """현장 화면에서 하나라도 찍었거나 해당없음을 골랐는지."""
    p = norm(parts)
    return any(v.get("file") or v.get("none") or v.get("prev") for v in p["public"].values()) or any(p["other"][k] for k, _ in OTHER)


def photo_list(parts: dict | None, base: Path) -> list[tuple[str, str, str, Path]]:
    """AI 판단용 [(public|other, 키, 이름, 사진 경로)] — 있는 사진만."""
    p = norm(parts)
    out = []
    for k, name in PUBLIC:
        f = (p["public"].get(k) or {}).get("file") or (p["public"].get(k) or {}).get("prev")
        if f and (base / f).exists():
            out.append(("public", k, name, base / f))
    for k, name in OTHER:
        for i, f in enumerate(p["other"][k], 1):
            if (base / f).exists():
                out.append(("other", k, f"{name} {i}", base / f))
    return out


def rows(parts: dict | None, judged: dict) -> list[dict]:
    """AI 초안 창에 보일 항목별 판단 [{group, key, name, grade, note}] — 공중이용 해당없음은 grade "해당없음"."""
    p = norm(parts)
    out = []
    for k, name in PUBLIC:
        it = p["public"].get(k) or {}
        j = (judged.get("public") or {}).get(k) or {}
        if it.get("none"):
            out.append({"group": "public", "key": k, "name": name, "grade": "해당없음", "note": ""})
        elif it.get("file"):
            out.append({"group": "public", "key": k, "name": name, "grade": j.get("grade", ""), "note": j.get("note", "")})
    for k, name in OTHER:
        j = (judged.get("other") or {}).get(k) or {}
        if p["other"][k]:
            out.append({"group": "other", "key": k, "name": name, "grade": j.get("grade", ""), "note": j.get("note", "")})
    return out


PROMPT = """당신은 시설물 정기안전점검(시설물안전법) 책임기술자입니다. 아래 사진은 이번 회차 현장에서 찍은 "공중이 이용하는 부위"와 "기타시설" 사진입니다.
사진에 보이는 것만으로 항목마다 상태를 판단하세요(보이지 않는 것을 지어내지 말 것 — 사진으로 판단이 어려우면 그렇게 적기).

[시설물] {facility}
[사진 차례]
{order}

[공중이 이용하는 부위 — 항목별 조사항목과 상태평가기준(a~e)]
{public}

[기타시설 — 정의] {definition}
[기타시설 — 조사항목]
{other}

[이번 회차 결함 조사에서 공중이용·기타로 분류된 결함(참고)]
{defects}

아래 JSON 객체 하나로만 답하세요(설명 없이). 사진이 없는 항목은 넣지 마세요:
{{"public": [{{"key": "fall|road|joint|vent", "grade": "a~e", "note": "보고서 문장에 쓸 한 줄 — 무엇이 어떤 상태인지 구체적으로(예: 외부 난간 지주 하부 일부 도장 박리·경미한 부식, 고정상태 양호)"}}],
 "other": [{{"key": "finish|attach", "grade": "a~e", "note": "한 줄(예: 외벽 치장벽돌 마감 일부 줄눈 탈락, 들뜸·배부름 없음)"}}]}}"""


def evaluate(company_id: int, facility: str, photos: list[tuple[str, str, str, Path]], defects_text: str) -> dict:
    """photos = [(구분 public|other, 키, 이름, 사진 경로)] → {"public": {키: {grade, note}}, "other": {키: {grade, note}}}."""
    from server.sitok import vision

    imgs, order = [], []
    for i, (grp, key, name, path) in enumerate(photos, 1):
        imgs.append(_small(path))
        order.append(f"{i}번 사진 = {'공중이용' if grp == 'public' else '기타시설'} · {name}({key})")
    pub = "\n".join(f"- {name}({k}): 조사항목 {PUBLIC_CRITERIA[k][0]}\n  상태평가기준: " + " / ".join(f"{g} {d}" for g, d in PUBLIC_CRITERIA[k][1].items())
                    for k, name in PUBLIC)
    oth = "\n".join(f"- {name}({k}): {OTHER_CRITERIA[k]}" for k, name in OTHER)
    prompt = PROMPT.format(facility=facility, order="\n".join(order), public=pub, definition=OTHER_DEFINITION, other=oth,
                           defects=defects_text or "(없음)")
    text = vision.ask(company_id, imgs, prompt, max_tokens=4000)
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("AI 답에서 JSON을 찾지 못했습니다.")
    data = json.loads(m.group(0))
    out: dict = {"public": {}, "other": {}}
    for grp, keys in (("public", dict(PUBLIC)), ("other", dict(OTHER))):
        for x in data.get(grp) or []:
            k = str(x.get("key") or "")
            g = str(x.get("grade") or "").strip().lower()[:1]
            if k in keys:
                out[grp][k] = {"grade": g if g in "abcde" and g else "", "note": str(x.get("note") or "").strip()}
    return out


def _small(path: Path, side: int = 1280) -> bytes:
    import io

    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def facts(parts: dict | None, judged: dict) -> str:
    """AI 초안 본문 프롬프트에 줄 사실 — 항목마다 해당없음/사진 없음/판단."""
    p = norm(parts)
    lines = ["[공중이 이용하는 부위 — 현장 사진 판단(이 내용으로 sections.public·결과표 public을 쓸 것, 해당없음 항목은 '해당없음')]"]
    for k, name in PUBLIC:
        it = p["public"].get(k) or {}
        j = (judged.get("public") or {}).get(k)
        if it.get("none"):
            lines.append(f"- {name}: 해당없음(이 시설물에 없음)")
        elif j:
            lines.append(f"- {name}: {j['grade']}({GRADE_WORD.get(j['grade'], '')}) — {j['note']}")
        else:
            lines.append(f"- {name}: 사진 없음(판단 안 함)")
    lines.append("[기타시설 — 현장 사진 판단(이 내용으로 sections.other를 쓸 것)]")
    for k, name in OTHER:
        j = (judged.get("other") or {}).get(k)
        lines.append(f"- {name}: {j['grade']}({GRADE_WORD.get(j['grade'], '')}) — {j['note']}" if j else f"- {name}: 사진 없음")
    return "\n".join(lines)
