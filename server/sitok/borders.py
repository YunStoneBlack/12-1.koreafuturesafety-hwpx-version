"""표 칸 테두리 모양(header.xml borderFill) 고치기(2026-10-15 민재형 검토 "가운데 줄이 진함 — 3개동 4개동 늘어날 때도 가운데 줄은 진해지면 안 되게").

양식 표의 데이터 줄 하나는 보통 "위 = 머리줄 밑 이중선, 아래 = 표 끝 굵은 선" 모양이라, 그 줄을 동·층 수만큼 복사하면 복사본끼리 맞닿는 곳마다
이중선 + 굵은 선이 겹쳐 진한 줄이 생김. 줄을 복사한 곳(report_build._dup_rows·_add_row·_fill_rows)이 맞닿는 선만 그 칸의 얇은 선(칸 네 변 중 가장 가는
실선 굵기)으로 바꾼 모양을 여기서 받아 씀 — 같은 정의가 header.xml에 이미 있으면 그 번호, 없으면 새 번호로 더하고 파일 쓸 때 header.xml에 붙임.

쓰는 법: 파일 쓰는 쪽이 `with report_build.using_borders(Borders(header_xml)) as b:` 안에서 표를 채우고, header.xml 쓸 때 `b.result(xml)`.
합본(precision_merge)은 다른 동 파일의 칸 번호를 정의 기준으로 이 파일 번호로 바꿈(adopt) — 동마다 더한 번호가 서로 다를 수 있음.
"""
from __future__ import annotations

import re

_BF = re.compile(r'<hh:borderFill id="(\d+)"[\s\S]*?</hh:borderFill>')
_SIDE = re.compile(r'<hh:(left|right|top|bottom)Border type="(\w+)" width="([\d.]+) mm"')


def _norm(block: str) -> str:
    """번호를 뺀 정의(같은 모양 찾기용)."""
    return re.sub(r'^<hh:borderFill id="\d+"', "<hh:borderFill", block)


def defs(xml: str) -> dict[str, str]:
    """header.xml → {번호: 번호 뺀 정의}."""
    return {m[1]: _norm(m.group(0)) for m in _BF.finditer(xml)}


class Borders:
    def __init__(self, xml: str):
        self.xml = xml
        self.by_id = defs(xml)
        self.by_def = {}
        for i, d in self.by_id.items():
            self.by_def.setdefault(d, i)
        self.next = max([int(i) for i in self.by_id] or [0]) + 1
        self.added: list[str] = []

    def adopt(self, d: str) -> str:
        """정의 d(번호 뺀 것)의 번호 — 없으면 새로 더함."""
        if d in self.by_def:
            return self.by_def[d]
        new = str(self.next)
        self.next += 1
        self.by_id[new] = d
        self.by_def[d] = new
        self.added.append(d.replace("<hh:borderFill", f'<hh:borderFill id="{new}"', 1))
        return new

    def thin(self, bid: str | None, top: bool, bottom: bool) -> str | None:
        """bid 모양에서 위(top)·아래(bottom) 선이 굵거나 이중선이면 그 칸의 가장 가는 실선으로 바꾼 모양의 번호(바꿀 게 없으면 bid 그대로)."""
        d = self.by_id.get(str(bid)) if bid is not None else None
        if d is None or not (top or bottom):
            return bid
        sides = {m[1]: (m[2], float(m[3])) for m in _SIDE.finditer(d)}
        solid = [w for t, w in sides.values() if t == "SOLID"]
        if not solid:
            return bid
        w = min(solid)

        def thick(side: str) -> bool:
            t, x = sides.get(side, ("NONE", 0.0))
            return t not in ("SOLID", "NONE") or (t == "SOLID" and x > w)

        new = d
        for side, want in (("top", top), ("bottom", bottom)):
            if want and thick(side):
                new = re.sub(rf'<hh:{side}Border type="\w+" width="[\d.]+ mm"', f'<hh:{side}Border type="SOLID" width="{w:g} mm"', new, count=1)
        return bid if new == d else self.adopt(new)

    def result(self, xml: str) -> str:
        """header.xml(다른 고침이 들어간 것도 됨)에 더한 모양을 붙임."""
        if not self.added:
            return xml
        xml = xml.replace("</hh:borderFills>", "".join(self.added) + "</hh:borderFills>", 1)
        return re.sub(r'(<hh:borderFills itemCnt=")(\d+)(")', lambda m: f"{m[1]}{int(m[2]) + len(self.added)}{m[3]}", xml, count=1)
