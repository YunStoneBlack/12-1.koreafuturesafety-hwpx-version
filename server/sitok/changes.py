"""건축물대장 변동사항 → 1.2.8 대상시설물 변경사항 실태조사 초안(2026-10-12 — 사용자: 건축물대장 변동사항을 보고 초안을 만들기로 했는데 빠져 있었음).

- 범위: 준공 이후 줄 전부(사용자 10/12 "전부"). 건물이 실제로 바뀐 게 아닌 줄(정기점검 기재·법령/규칙 개정 기재·소유자·지번 정리 등)은 뺌.
- 용도변경 → 3) 용도변경, 전유부·호실 분할·합병 → 3) 평면변경, 증축·대수선·구조변경 → 1) 바뀐 구조부재 + 3) 평면·입면·단면.
- 용도변경으로 활하중이 달라지면 2) 사용하중에도 "변경"(원칙인데 아무도 안 하고 있었음 — 사용자). 활하중 값은 AI가 아니라 아래 표 —
  AI는 변경 전·후 용도를 표의 어느 줄로 볼지만 고름. 한 항목에 변동이 여러 건이면 칸 안에서 줄을 나눔("\n").
- 결과는 sitok_report.survey["changes"]와 같은 모양 {항목 이름: {before, after, where, note}} — 점검자가 면담·변경사항 창에서 확인하고 저장.
"""
from __future__ import annotations

from pathlib import Path

# KDS 41 10 15 건축구조기준 설계하중 표 2.2-1 기본등분포활하중(kN/㎡) 중 자주 쓰는 줄 — 키: (용도, 값)
LIVE_LOADS = {
    "주거": ("주거(거실·공용실)", 2.0),
    "공동주택공용": ("공동주택 공용실", 5.0),
    "사무실": ("일반 사무실", 2.5),
    "특수사무실": ("특수용도사무실·문서보관실", 5.0),
    "교실": ("학교 교실", 3.0),
    "중량실험실": ("학교 중량물 실험실", 5.0),
    "병실": ("병원 병실", 2.0),
    "병원공용": ("병원 수술실·공용실", 3.0),
    "객실": ("숙박 객실", 2.0),
    "숙박공용": ("숙박 공용실", 5.0),
    "판매1층": ("상점·백화점 1층", 5.0),
    "판매2층": ("상점·백화점 2층 이상", 4.0),
    "창고형매장": ("창고형 매장", 6.0),
    "식당": ("식당", 5.0),
    "주방": ("영업용 주방", 7.0),
    "집회고정석": ("극장·집회장(고정석)", 4.0),
    "집회이동석": ("집회장(이동석)", 5.0),
    "연회장": ("연회장·무도장(유흥)", 5.0),
    "무대": ("무대", 7.0),
    "체육": ("체육관 바닥", 5.0),
    "열람실": ("도서관 열람실", 3.0),
    "서고": ("도서관 서고", 7.5),
    "주차승용": ("옥내 주차(승용차 전용)", 3.0),
    "창고경량": ("경량품 저장창고", 6.0),
    "창고중량": ("중량품 저장창고", 12.0),
    "공장경": ("경공업 공장", 6.0),
    "공장중": ("중공업 공장", 12.0),
    "기계실": ("기계실·전기실·공조실", 5.0),
}
KINDS = ("용도변경", "평면변경", "입면변경", "단면변경", "증축", "대수선", "구조변경", "기재")
MEMBERS = ("기둥", "보", "슬래브", "지붕", "계단")

PROMPT = """건축물대장의 "변동사항"(변동일 · 변동내용 및 원인) 부분입니다. 줄(변동일) 하나하나를 빠짐없이 읽어 JSON 배열 하나로만 답하세요(설명 없이). 날짜 순,
변동일 하나에 호실마다 서로 다른 변경이 섞여 있으면(예: 501호는 유흥주점→사무소, 401호는 사무소→안마시술소) 변경마다 하나씩(같은 날짜·문서번호로):
[{{"date": "2020.7.27", "doc": "문서번호(예: 건축과-31287, 없으면 \\"\\")", "kind": 아래 중 하나,
  "where": "위치 — 층·호를 짧게(예: 4층 401·403호, 1층 102호), 건물 전체면 \\"전체\\"",
  "before": "변경 전 — 보고서 표 칸이 좁으니 짧게(용도변경이면 세부 용도 이름만, 예: 사무소 / 유흥주점 / 일반음식점; 평면변경이면 예: 302·303호 2개 호실) — 없으면 \\"\\"",
  "after": "변경 후 — 같은 꼴(예: 안마시술소 / 303호로 합병)",
  "before_load": 용도변경일 때만 변경 전 용도에 맞는 활하중 표 키(아래), 아니면 null,
  "after_load": 용도변경일 때만 변경 후 용도의 활하중 표 키, 아니면 null,
  "members": 증축·대수선·구조변경이면 바뀐 구조부재 {members} 중(모르면 []), 아니면 [],
  "shapes": 증축·대수선이면 함께 바뀐 것 ["평면변경","입면변경","단면변경"] 중(층이 늘면 단면변경, 바닥 면적이 늘면 평면변경, 외관이면 입면변경), 아니면 [],
  "summary": "한 줄 요약"}}]
kind:
- "용도변경" — 용도가 바뀜(표시변경·기재변경이라도 용도가 바뀌었으면 용도변경)
- "평면변경" — 전유부·호실 분할·합병, 전유·공용 면적 변경처럼 칸막이·면적이 바뀜
- "증축" / "대수선" / "구조변경" / "입면변경"(외관·창호) / "단면변경"(층고·층)
- "기재" — 건물이 바뀐 게 아닌 기록: 정기점검 기재, 법령·규칙 개정에 따른 현황 기재, 소유자·주소·지번·도로명 정리, 대장 신규 작성·전환, 오기 정정 등
한 줄에 여러 호실이 같은 변경이면 한 건으로(where에 호실을 모아서). 지어내지 말 것.

[활하중 표 키 — 용도(kN/㎡)] (근린생활시설 사무소 = 사무실, 미용원·소매점 = 판매(층에 따라), 일반·휴게음식점 = 식당, 유흥주점·단란주점 = 연회장,
 안마시술소·노래연습장·인터넷게임시설 = 사무실 또는 집회이동석 중 사람이 모이는 정도로, 교회·종교집회장 = 집회고정석 또는 집회이동석)
{loads}

[건축물대장 글]
{text}"""


def register_text(pdf: Path) -> str:
    """건축물대장 PDF 글 — "변동사항" 쪽부터(앞 쪽 표제부는 짧게 남김). 글자가 없으면(스캔) 빈 글."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        text = "\n".join(p.get_text() for p in doc)
    i = text.find("변동사항")
    if i < 0:
        i = text.find("변동내용")
    return (text[max(0, i - 200):] if i >= 0 else text)[:30000] if text.strip() else ""


def register_images(pdf: Path, pages: int = 6) -> list[bytes]:
    import pymupdf

    with pymupdf.open(pdf) as doc:
        return [doc[i].get_pixmap(dpi=130).tobytes("jpg") for i in range(min(pages, doc.page_count))]


def read_events(pdf: Path, company_id: int) -> list[dict]:
    """건축물대장 변동사항 줄 → [{date, doc, kind, where, before, after, before_load, after_load, members, shapes, summary}]."""
    from server.sitok import vision

    text = register_text(pdf)
    imgs = [] if len(text) > 200 else register_images(pdf)
    if not text and not imgs:
        raise ValueError("건축물대장에서 글을 읽지 못했습니다.")
    loads = "\n".join(f"{k} — {v[0]} {v[1]:.1f}" for k, v in LIVE_LOADS.items())
    got = vision.ask_json(company_id, imgs, PROMPT.format(members=list(MEMBERS), loads=loads, text=text or "(글자 없음 — 그림을 보세요)"), max_tokens=16000)
    out = []
    for g in got if isinstance(got, list) else []:
        if not isinstance(g, dict):
            continue
        kind = str(g.get("kind") or "").strip()
        out.append({"date": str(g.get("date") or "").strip(), "doc": str(g.get("doc") or "").strip(),
                    "kind": kind if kind in KINDS else "기재", "where": str(g.get("where") or "").strip(),
                    "before": str(g.get("before") or "").strip(), "after": str(g.get("after") or "").strip(),
                    "before_load": g.get("before_load") if g.get("before_load") in LIVE_LOADS else None,
                    "after_load": g.get("after_load") if g.get("after_load") in LIVE_LOADS else None,
                    "members": [m for m in g.get("members") or [] if m in MEMBERS],
                    "shapes": [s for s in g.get("shapes") or [] if s in ("평면변경", "입면변경", "단면변경")],
                    "summary": str(g.get("summary") or "").strip()})
    return out


def _label(labels: list[str], word: str) -> str | None:
    words = (word, "슬라브") if word == "슬래브" else (word,)
    return next((lb for w in words for lb in labels if w in lb.replace(" ", "")), None)


def _load(key: str | None) -> tuple[str, float] | None:
    return LIVE_LOADS.get(key) if key else None


def draft(events: list[dict], labels: list[str]) -> tuple[dict, list[str]]:
    """변동 줄 → ({1.2.8 항목 이름: {before, after, where, note}}, 넣을 칸이 틀에 없어 못 넣은 것). labels = 틀의 1.2.8 항목 이름들."""
    rows: dict[str, list[tuple[str, str, str, str]]] = {}
    missing: list[str] = []

    def add(word: str, before: str, after: str, where: str, note: str) -> None:
        lb = _label(labels, word)
        if lb is None:
            missing.append(f"{word}: {after}")
            return
        rows.setdefault(lb, []).append((before or "-", after or "변경", where or "-", note or "-"))

    for e in events:
        note = " ".join(x for x in (e["date"], e["doc"]) if x)
        k = e["kind"]
        if k == "기재":
            continue
        if k == "용도변경":
            add("용도", e["before"], e["after"], e["where"], note)
            lb, la = _load(e["before_load"]), _load(e["after_load"])
            if lb and la and lb[1] != la[1]:
                add("사용하중", f"{e['before'] or lb[0]} {lb[1]:.1f}kN/㎡", f"{e['after'] or la[0]} {la[1]:.1f}kN/㎡({'증가' if la[1] > lb[1] else '감소'})",
                    e["where"], note)
        elif k == "평면변경":
            add("평면", e["before"], e["after"] or e["summary"], e["where"], note)
        elif k in ("입면변경", "단면변경"):
            add(k[:2], e["before"], e["after"] or e["summary"], e["where"], note)
        else:  # 증축·대수선·구조변경
            for m in e["members"]:
                add(m, e["before"], f"{k} — {e['summary'] or e['after']}", e["where"], note)
            for s in e["shapes"] or (["평면변경"] if k == "증축" else []):
                add(s[:2], e["before"], f"{k} — {e['summary'] or e['after']}", e["where"], note)
    out = {lb: {"before": "\n".join(r[0] for r in rs), "after": "\n".join(r[1] for r in rs),
                "where": "\n".join(r[2] for r in rs), "note": "\n".join(r[3] for r in rs)} for lb, rs in rows.items()}
    return out, missing
