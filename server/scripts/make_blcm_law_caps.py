"""건축물관리점검 해당없음 근거 — 법령 조문 캡처(빨간 네모) 만들기(2026-10-30 사용자 "해당없음 근거 법령 캡처 및 관리대장 캡처 후 표기").

server/blcm/applicability.py 해당없음 사유에 나오는 조문(건축법·시행령·설비규칙 …)마다 국가법령정보센터 현행 조문 화면을 찍어
저장소 _건축물관리점검/_법령캡처/{이름}.jpg + index.json({"건축법 시행령 제27조제1항": {file, title, url, made}})으로 둠.
항이 있으면 그 항(다음 항 앞까지)에, 없으면 조문 전체에 빨간 네모. [① 서류검토 확정] 때 server/blcm/evidence.py가 이 그림을 그 항목 현황사진으로 넣음.

쓰는 법: python -I server/scripts/make_blcm_law_caps.py [--only "건축법 시행령 제27조제1항"]   (조문 하나에 화면 한 번, 사이 2초 — 법이 바뀌면 다시)
law.go.kr 조문 화면은 본문을 iframe(lsSideInfoP.do)으로 불러서 iframe 주소를 바로 열어 찍음(핵심기술 46절)."""
from __future__ import annotations

import datetime
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from core.db import DATA_DIR  # noqa: E402

OUT = DATA_DIR / "_건축물관리점검" / "_법령캡처"
CITE = re.compile(r"((?:건축법|건축물의 설비기준 등에 관한 규칙|건축물의 피난·방화구조 등의 기준에 관한 규칙|녹색건축물 조성 지원법)(?: 시행령| 시행규칙)?)\s*(제\d+조(?:의\d+)?)(제\d+항)?")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

MARK_JS = """(hang) => {
  const ps = [...document.querySelectorAll('p')].filter(p => p.textContent.trim());
  const start = ps.findIndex(p => /^\\s*제\\d+조/.test(p.textContent.trim()));
  if (start < 0) return null;
  let a = start, b = ps.length;
  for (let i = start + 1; i < ps.length; i++) { const t = ps[i].textContent.trim(); if (/^\\[(전문개정|본조신설|제목개정)/.test(t) || /^제\\d+조/.test(t)) { b = i; break; } }
  if (hang) {
    const C = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮", n = C.indexOf(hang), next = C[n + 1];
    const has = (p, c) => p.textContent.trim().startsWith(c) || (p === ps[start] && p.textContent.includes(c));
    const s0 = ps.slice(start, b).findIndex(p => has(p, hang));
    if (s0 >= 0) { const e0 = ps.slice(start + s0 + 1, b).findIndex(p => p.textContent.trim().startsWith(next)); a = start + s0; if (e0 >= 0) b = start + s0 + 1 + e0; }
  }
  const rs = ps.slice(a, b).map(p => p.getBoundingClientRect());
  const top = Math.min(...rs.map(r => r.top)) + scrollY, bottom = Math.max(...rs.map(r => r.bottom)) + scrollY;
  const left = Math.min(...rs.map(r => r.left)), right = Math.max(...rs.map(r => r.right));
  const box = document.createElement('div');
  Object.assign(box.style, {position: 'absolute', left: (left - 6) + 'px', top: (top - 4) + 'px', width: (right - left + 12) + 'px', height: (bottom - top + 5) + 'px',
    border: '3px solid #e00', borderRadius: '4px', pointerEvents: 'none', zIndex: 9999});
  document.body.appendChild(box);
  const head = [...document.querySelectorAll('h2, .cont_top, #conTop, .tit, div')].find(e => /\\[시행 /.test(e.textContent) && e.textContent.length < 400);
  const all = ps.slice(start, ps.length).map(p => p.getBoundingClientRect());
  const t0 = head ? head.getBoundingClientRect().top + scrollY : top - 40;
  const artEnd = Math.max(...ps.slice(start, ps.findIndex((p, i) => i > start && /^제\\d+조/.test(p.textContent.trim())) > 0 ? ps.findIndex((p, i) => i > start && /^제\\d+조/.test(p.textContent.trim())) : ps.length).map(p => p.getBoundingClientRect().bottom)) + scrollY;
  const title = (ps[start].textContent.match(/제\\d+조(의\\d+)?\\(([^)]*)\\)/) || [])[2] || '';
  return {x: 0, y: Math.max(0, Math.min(t0, top) - 10), width: document.documentElement.clientWidth, height: Math.min(Math.max(artEnd, bottom) - Math.min(t0, top) + 24, 2600), title};
}"""


def cites() -> list[tuple[str, str, str]]:
    src = (ROOT / "server/blcm/applicability.py").read_text(encoding="utf-8")
    return sorted({(m[1], m[2], m[3] or "") for m in CITE.finditer(src)})


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from playwright.sync_api import sync_playwright

    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    OUT.mkdir(parents=True, exist_ok=True)
    idx_f = OUT / "index.json"
    idx = json.loads(idx_f.read_text(encoding="utf-8")) if idx_f.exists() else {}
    todo = [c for c in cites() if not only or f"{c[0]} {c[1]}{c[2]}" == only]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1000, "height": 1400}, device_scale_factor=1.5)
        for law, jo, hang in todo:
            key = f"{law} {jo}{hang}"
            outer = "https://www.law.go.kr/" + quote(f"법령/{law.replace(' ', '')}/{jo}")
            pg.goto(outer, wait_until="networkidle", timeout=60000)
            fr = next((f for f in pg.frames if "lsSideInfoP" in f.url), None)
            if fr is None:
                print("본문 iframe 없음", key)
                continue
            frame_url = fr.url
            pg.goto(frame_url, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(500)
            h = CIRCLED[int(hang[1:-1]) - 1] if hang else ""
            clip = pg.evaluate(MARK_JS, h)
            if not clip:
                print("조문 못 찾음", key)
                continue
            title = clip.pop("title")
            name = re.sub(r"\s", "", key) + ".jpg"
            pg.screenshot(path=str(OUT / name), clip=clip, type="jpeg", quality=85, full_page=True)
            idx[key] = {"file": name, "title": title, "url": outer, "made": datetime.date.today().isoformat()}
            print("✓", key, title, round(clip["height"]))
            time.sleep(2)
        b.close()
    idx_f.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    print("index", len(idx))


if __name__ == "__main__":
    main()
