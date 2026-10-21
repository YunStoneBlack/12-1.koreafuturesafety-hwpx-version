"""철근탐사기 화면 캡처 읽기(2026-10-21 사용자·민재형 — 내진성능평가 철근탐사 3단계) — 탐사기 프로그램 "파형 그래프" 한 장에서
철근 개수(점 개수)·간격·피복을 읽어 철근배근 표 조사값으로.

화면 모양(형이 보낸 캡처): 위 가로줄 숫자 = 간격(mm, 맨 앞 값은 스캔 시작~첫 철근), 점(빨강 = 불합격, 초록 = 합격) = 철근, 점 아래 숫자 = 피복(mm).
값 규칙(사용자 10/21 "이렇게 해줘"): 간격 = 철근 사이 간격들의 평균(맨 앞·맨 뒤 끝 거리 뺌, 162·156 → @159), 피복 = 점마다 값의 평균 반올림(56·55·56 → 56).
읽기: 숫자는 AI(그림 한 장, 약 10원), 점 개수는 색으로 셈(꽉 찬 작은 빨강·초록 원, 오른쪽 위 범례 점 뺌) → 둘이 다르면 경고.
"""
from __future__ import annotations

import io
import json
from collections import deque

PROMPT = """아래 그림은 철근탐사기(RC 레이더) 프로그램의 "파형 그래프" 화면 캡처입니다.
- 철근 = 그래프 아래쪽의 작은 빨강(불합격)·초록(합격) 동그라미 점. 오른쪽 위 범례(합격·불합격) 점은 빼세요.
- 위쪽 가로선 위 숫자들 = 간격(mm), 왼쪽부터. 맨 앞(스캔 시작 ~ 첫 철근)이나 맨 뒤(마지막 철근 ~ 끝) 거리도 숫자로 있을 수 있습니다.
- 점 바로 아래(또는 옆) 숫자 = 그 철근의 피복(mm).
JSON만: {"dots": 3, "spacings_all": [25, 162, 156], "bar_spacings": [162, 156], "covers": [56, 55, 56], "unsure": false}
bar_spacings = 이웃한 두 철근(점) 사이 간격만(맨 앞·맨 뒤 끝 거리 빼고). 숫자가 흐려 확실하지 않으면 unsure: true."""


def color_dots(data: bytes) -> list[dict]:
    """빨강·초록 꽉 찬 작은 원 [{x, y, color}] — 손으로 그린 선·글자는 크기·채움 비율로 빼고, 오른쪽 위 범례(가로 88%↑·세로 25%↓)는 뺌."""
    import numpy as np
    from PIL import Image

    im = np.array(Image.open(io.BytesIO(data)).convert("RGB")).astype(int)
    H, W, _ = im.shape
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    masks = {"red": (r > 190) & (g < 70) & (b < 70), "green": (g > 170) & (r < 90) & (b < 90)}
    out = []
    for color, m in masks.items():
        seen = np.zeros_like(m, bool)
        for y0, x0 in zip(*np.nonzero(m)):
            if seen[y0, x0]:
                continue
            q = deque([(y0, x0)])
            seen[y0, x0] = True
            pts = []
            while q:
                y, x = q.popleft()
                pts.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and m[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
            a = np.array(pts)
            h, w = int(np.ptp(a[:, 0])) + 1, int(np.ptp(a[:, 1])) + 1
            side = max(h, w)
            if not (6 <= side <= max(24, W // 40)) or not (0.7 < w / h < 1.4) or len(pts) < 0.6 * w * h:
                continue
            cx, cy = float(a[:, 1].mean()), float(a[:, 0].mean())
            if cx > W * 0.88 and cy < H * 0.25:  # 범례
                continue
            out.append({"x": round(cx), "y": round(cy), "color": color, "size": side})
    return sorted(out, key=lambda d: d["x"])


def values(bar_spacings: list, covers: list) -> dict:
    """표에 넣을 값 — 간격 = 철근 사이 간격 평균(반올림), 피복 = 평균 반올림."""
    sp = [float(v) for v in bar_spacings if isinstance(v, (int, float)) and v > 0]
    cv = [float(v) for v in covers if isinstance(v, (int, float)) and v > 0]
    return {"spacing": round(sum(sp) / len(sp)) if sp else None, "cover": round(sum(cv) / len(cv)) if cv else None}


def read(company_id: int, data: bytes) -> dict:
    """캡처 한 장 → {count, spacing, cover, spacings, covers, dots_color, warn: [..]}."""
    from server.sitok import vision

    got = vision.ask_json(company_id, [data], PROMPT, max_tokens=4000, side=1568, effort="low")
    if isinstance(got, list):
        got = got[0] if got else {}
    dots = color_dots(data)
    bar = [v for v in (got.get("bar_spacings") or []) if isinstance(v, (int, float))]
    covers = [v for v in (got.get("covers") or []) if isinstance(v, (int, float))]
    n_ai = int(got.get("dots") or 0)
    v = values(bar, covers)
    warn = []
    if dots and n_ai and len(dots) != n_ai:
        warn.append(f"점 개수가 다릅니다 — 색으로 센 {len(dots)}개, AI {n_ai}개")
    if n_ai and bar and len(bar) != n_ai - 1:
        warn.append(f"철근 사이 간격 {len(bar)}개 ≠ 점 {n_ai}개 − 1")
    if got.get("unsure"):
        warn.append("숫자가 흐려 AI가 확실하지 않다고 함")
    # 개수: 색으로 센 것과 AI가 다르면 "철근 사이 간격 수 + 1"과 맞는 쪽(캡처에 손으로 그린 빨간 표시가 점에 붙으면 색 세기가 모자람, 10/21 형 캡처)
    expect = len(bar) + 1 if bar else None
    count = len(dots) or n_ai or None
    if dots and n_ai and len(dots) != n_ai and expect in (len(dots), n_ai):
        count = expect
    return {"count": count, "spacing": v["spacing"], "cover": v["cover"], "spacings": got.get("spacings_all") or bar,
            "bar_spacings": bar, "covers": covers, "dots_color": len(dots), "dots_ai": n_ai, "warn": warn}


def _selfcheck() -> None:
    assert values([162, 156], [56, 55, 56]) == {"spacing": 159, "cover": 56}
    assert values([], [40]) == {"spacing": None, "cover": 40}


if __name__ == "__main__":
    import sys

    _selfcheck()
    if len(sys.argv) > 1:
        print(json.dumps(color_dots(open(sys.argv[1], "rb").read()), ensure_ascii=False))
    print("ok")
