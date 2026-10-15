"""면적률 20% 이상 개수 0~10 × 부재 종류 × 균열폭 분포 두 가지 → SafetyMan 부재 점수 표."""
import json, os, sys, tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
WORK = Path(os.environ.get("SM_WORK") or (Path(tempfile.gettempdir()) / "safetyman_check"))  # 시험 파일·결과(저장소 밖)
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE))
import t_rule as R
W = {"W1": [7, 2, 1, 0, 0], "W2": [5, 1, 1, 2, 1]}
out = {}
for wname, w in W.items():
    for half in (0, 1):
        areas = [a for a in range(11) if a % 2 == half] + ([10] if half else [])
        floors = []
        for a in areas[:6]:
            floors.append({m: R.mem(w, a) for m in ("기둥", "내력벽", "큰보", "작은보", "슬래브")})
        R.SETS[f"{wname}_{half}"] = floors
        for r in R.run(f"{wname}_{half}"):
            out[(wname, r["member"], r["area_ge"])] = r["sm"]
rows = {}
for (wname, m, a), v in out.items():
    rows.setdefault((wname, m), {})[a] = v
for (wname, m), d in rows.items():
    print(wname, W[wname], m, " ".join(f"{a}:{d[a]:.0f}" if d[a] else f"{a}:-" for a in sorted(d)))
json.dump({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in out.items()}, open(WORK / "area_table.json", "w", encoding="utf-8"), ensure_ascii=False)
