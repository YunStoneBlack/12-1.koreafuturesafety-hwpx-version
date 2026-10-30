"""건축물관리점검 부적합 견본 후보 모으기(2026-10-30 사용자 "부적합 견본 사진 — 회사 보고서에서 찾아 대조표 → 형·민재형 확인").

회사 제출 보고서(드롭박스 4.보고서/4. 건축물관리법, "보고서" 폴더의 1MB 넘는 PDF)를 훑어, 항목마다 현황사진 설명에 부적합 낱말(균열·누수·적치물·불량 …,
건수형은 변경 유형 이름 — 실외기·간이 시설물 …)이 있는 사진을 후보로: 저장소 _건축물관리점검/_참고사진/후보/{code}_{해시}.jpg + candidates.json
{code: [{file, caption, from, score: {칸 key: 점수}}]}. 칸(items.bad_types) 점수 = 칸 이름 낱말이 설명에 있으면 +2, 부적합 낱말이 있으면 +1.
고르기는 화면(보고서 자동화 › 건축물관리점검 › 🖼 부적합 견본 고르기)에서 — 점수 3 이상인 첫 후보는 '검토 전'으로 미리 넣어 둠(bad.json, 이미 있는 칸은 그대로).

쓰는 법: python -I server/scripts/scan_blcm_bad_samples.py <드롭박스 4. 건축물관리법 폴더>   (읽기만, 6개 동시)"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
DEFECT = re.compile(r"균열|누수|백화|백태|박리|박락|탈락|부식|파손|훼손|적치|불량|미흡|오염|들뜸|처짐|막힘|노후|미설치|미작동|닫힘\s*불량|손상|기울|침하|유실|낙석|미비|망실|고사|무단|불법|변경됨|감소|설치됨")
OK_WORDS = re.compile(r"없음|양호|이상\s*없|정상|유지\s*전경|^전경$")
TOK_SKIP = {"기타", "여부", "상태", "성능", "유지", "및", "등", "의", "작동", "설치", "확인"}


def _load_m():
    spec = importlib.util.spec_from_file_location("mbs", HERE.with_name("make_blcm_samples.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tokens(label: str) -> list[str]:
    words = [w for w in re.split(r"[\s—·,()/「」\[\]]+", label) if w and w not in TOK_SKIP]
    out = []
    for w in words:
        w = re.sub(r"(의|을|를|에서|으로|로)$", "", w)
        if len(w) >= 2 or w in ("보",):
            out.append(w)
    return out


SYN = {"훼손": "훼손|고사|불량|손상|파손", "간이": "간이|가설", "시설물": "시설물|시설|창고|컨테이너|천막", "쓰레기": "쓰레기|분리수거|재활용",
       "분리시설": "분리|수거|재활용", "적치물": "적치", "슬래브": "슬래브|슬라브", "작동불량": "작동\\s*불량|불량|미작동"}
NEUTRAL = re.compile(r"여부|측정|현황도|배치도|확인\)?$")  # 점검 사진(부적합이 아님일 수 있음) — 미리 넣기에서 뺌


def _has(caption: str, t: str) -> bool:
    if t == "보":
        return bool(re.search(r"(^|[\s(·,])보(\s|$|\s*(미장)?(균열|누수|처짐|백화|박리|철근|부식))", caption))
    return bool(re.search(SYN.get(t, re.escape(t)), caption))


def score(caption: str, label: str, count_kind: bool) -> int:
    """3 = 미리 넣어도 됨(칸 이름 낱말이 모두 있고 — 점수형은 부적합 낱말도, 점검 사진 같은 말은 없음), 2 = 낱말 일부, 1 = 부적합 낱말만, 0 = 없음."""
    toks = tokens(label)
    allhit = bool(toks) and all(_has(caption, t) for t in toks)
    anyhit = any(_has(caption, t) for t in toks)
    defect = bool(DEFECT.search(caption))
    if allhit and (count_kind or defect) and not NEUTRAL.search(caption) and "보행거리" not in label:  # 보행거리는 사진으로 부적합을 못 보임
        return 3
    return 2 if anyhit else 1 if defect else 0


def one(args: tuple[str, str]) -> tuple[str, list]:
    pdf, outdir = args
    import pymupdf

    sys.path.insert(0, str(ROOT))
    from server.blcm import items as I

    M = _load_m()
    by_name = {M.sq(it["name"]): it["code"] for it in I.items()}
    rows = []
    try:
        doc = pymupdf.open(pdf)
        pages = M.item_pages(doc)
    except Exception as err:  # noqa: BLE001
        return pdf, [{"_err": str(err)}]
    name = Path(pdf).parent.parent.name
    for rcode, pns in pages.items():
        try:
            got = M.read_item(doc, pns)
        except Exception:  # noqa: BLE001
            continue
        nm = M.sq(got["name"])
        code = by_name.get(nm) or next((c for n, c in by_name.items() if nm and (nm in n or n in nm)), None)
        it = I.by_code().get(code or "")
        if it is None:
            continue
        types = I.bad_types(it)
        for ph in got["photos"]:
            cap = (ph.get("caption") or "").strip()
            if not cap or OK_WORDS.search(cap):
                continue
            sc = {t["key"]: score(cap, t["label"], it["kind"] == "count") for t in types if t["label"] != "기타"}
            if not (DEFECT.search(cap) or any(v >= 3 for v in sc.values())):
                continue
            h = hashlib.sha1(f"{pdf}|{ph['page']}|{tuple(round(x) for x in ph['rect'])}".encode()).hexdigest()[:10]
            fn = f"{code}_{h}.jpg"
            f = Path(outdir) / fn
            if not f.exists():
                f.write_bytes(doc[ph["page"]].get_pixmap(clip=ph["rect"], dpi=110).tobytes("jpg", jpg_quality=82))
            rows.append({"code": code, "file": fn, "caption": cap, "from": name, "score": {k: v for k, v in sc.items() if v}})
    return pdf, rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    from core.db import DATA_DIR

    ref = DATA_DIR / "_건축물관리점검" / "_참고사진"
    out = ref / "후보"
    out.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "--rescore":  # 모은 후보로 점수·미리 넣기만 다시(그림은 그대로)
        from server.blcm import items as I

        cand = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
        for code, rows in cand.items():
            it = I.by_code()[code]
            for r in rows:
                r["score"] = {k: v for k, v in ((t["key"], score(r["caption"], t["label"], it["kind"] == "count")) for t in I.bad_types(it) if t["label"] != "기타") if v}
        return _finish(ref, out, cand)
    base = Path(sys.argv[1])
    pdfs = sorted(str(p) for p in base.rglob("*.pdf") if "보고서" in str(p.parent) and p.stat().st_size > 1_000_000)
    cand: dict[str, list] = {}
    seen: set[tuple] = set()
    with ProcessPoolExecutor(max_workers=6) as ex:
        for pdf, rows in ex.map(one, [(p, str(out)) for p in pdfs]):
            n = 0
            for r in rows:
                if "_err" in r:
                    continue
                k = (r["code"], r["caption"], r["from"])
                if k in seen:  # 같은 보고서 다른 판(초안·최종)의 같은 사진
                    continue
                seen.add(k)
                cand.setdefault(r["code"], []).append(r)
                n += 1
            print(Path(pdf).parent.parent.name[:30], "후보", n, rows[0].get("_err", "") if rows and "_err" in rows[0] else "")
    _finish(ref, out, cand)


def _finish(ref: Path, out: Path, cand: dict) -> None:
    for v in cand.values():
        v.sort(key=lambda r: -max(r["score"].values(), default=0))
    (out / "candidates.json").write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
    # 점수 3 첫 후보 → '검토 전' 견본 — 사람이 고른 칸(ok)은 그대로, 예전 자동 칸은 다시
    bad_f = ref / "bad.json"
    bad = json.loads(bad_f.read_text(encoding="utf-8")) if bad_f.exists() else {}
    for code in list(bad):
        bad[code] = {k: v for k, v in bad[code].items() if v and v[0].get("ok")}
    added = 0
    for code, rows in cand.items():
        for r in rows:
            for key, sc in r["score"].items():
                if sc >= 3 and not (bad.get(code) or {}).get(key):
                    bad.setdefault(code, {})[key] = [{"file": f"후보/{r['file']}", "caption": r["caption"], "from": r["from"], "ok": False}]
                    added += 1
    bad = {c: v for c, v in bad.items() if v}
    bad_f.write_text(json.dumps(bad, ensure_ascii=False, indent=1), encoding="utf-8")
    print("항목", len(cand), "후보", sum(len(v) for v in cand.values()), "미리 넣은 칸(검토 전)", added)


if __name__ == "__main__":
    main()
