"""내진성능평가 민간 계약서 양식 만들기(2026-10-28 사용자 "서류 자동화 시특법이랑 동일하게 내진성능평가 — 양식 똑같이").

시특법 민간 계약서 양식(data/templates/시특법_민간계약서_양식.hwpx)을 그대로 복사하고, 본문에서 시설물안전법 조항·안전점검 지침·FMS 등재처럼
시특법에만 맞는 문장만 내진성능평가에 맞게 바꿔 data/templates/내진_민간계약서_양식.hwpx로 둠(자리표시 {종류}·{관리주체} 등은 그대로 — 종류 = "내진성능평가").
형이 한글에서 고쳐 서류 자동화 › 내진성능평가 화면 [고친 양식 올리기]로 바꾸면 그 양식을 씀(이 스크립트는 처음 한 번 — 이미 있으면 --force일 때만 덮음).

    python -m server.scripts.make_seismic_civil_template [--force]
"""
from __future__ import annotations

import io
import sys
import zipfile

from lxml import etree

from server.sitok import civil
from server.sitok import report_build as rb

HP, T = rb.HP, rb.T

# (문단 자기 글에 든 말, 바꿀 문단 글) — 문단마다 정확히 한 번 맞아야 함
RULES = [
    ("안전점검 계약조건 1부", "붙임서류 : 1. 내진성능평가 용역 계약조건 1부 "),
    ("시설물의 안전점검 표준계약조건", "내진성능평가 용역 표준계약조건"),
    ("제6조 및 제7조에 따라 관리주체인", " 관리주체인 {관리주체}(이하 “갑”이라 한다)과 {종류}의 실시자인 (주)한국미래안전(이하 “을”이라 한다)은 "
                                     "「지진·화산재해대책법」 제16조의2에 따른 기존 시설물의 {종류}에 관하여 다음과 같이 계약을 체결한다."),
    ("제2조(진단․점검의 범위)", "제2조(평가의 범위) {종류}의 범위는 다음과 같다."),
    ("국토교통부장관이 고시한", "제4조(계약금액의 산정 및 변경) ① 계약금액의 산정은 관계법령에서 정한 {종류} 대가기준에 의한다."),
    ("제5조(대가의 지급 등)", "제5조(대가의 지급 등) {종류}대가 및 선금의 지급은 “을”의 {종류} 결과보고서 제출 완료 후 30일 이내에 지급하여야 한다."),
    ("안전점검 지침에 의거", "  ② “을”은 관계법령과 기존 시설물(건축물) 내진성능 평가요령 등 관련 기준에 의거 {종류}을 성실하게 실시하여야 한다."),
    ("실시한 안전점검 결과를 기초로", "  ③ “을”은 {종류}을 실시함에 있어 “갑”이 보유한 설계도서·구조계산서와 이전 안전점검·진단 결과를 기초로 수행하여야 하며, "
                                 "“갑”은 주요결함사항 및 보수․보강·증축 내용 등에 대하여 “을”에게 미리 통보하여야 한다."),
    ("진단수행 중 발생한 안전사고", "  ④ “을”은 {종류} 수행 중 발생한 안전사고에 대해 책임을 지며, 안전사고를 미연에 방지하도록 하여야 한다."),
    ("FMS(시설물정보관리종합시스템)", "  ➄ “을”은 {종류} 수행 후 결과보고서를 계약기간내에 “갑”에게 제출하여야 한다."),
    ("특별법 제11조제1항에 따라", "제7조(실시결과의 통보) ① “을”은 계약기간이 종료한 경우에는 지체없이 “갑”에게 {종류} 실시결과를 통보하여야 한다."),
    ("시행령 제12조에 따른 중대한 결함", "  ② “을”은 계약기간 중에도 구조안전에 영향을 주는 중대한 결함이 있을 경우에는 서면으로 “갑”에게 통보하여야 한다."),
    ("특별법 제10조에 따라", "제8조(설계도서 등의 열람교부 등) ① “을”은 {종류}을 수행함에 있어서 필요한 경우에는 “갑”에게 해당 시설물의 설계․시공 및 감리와 관련된 "
                         "서류의 열람이나 그 사본의 교부를 요청할 수 있으며 이 경우 “갑”은 이에 응하여야 한다."),
    ("“을”의 정상적인 진단이 곤란할 때", "  3. “갑”이 제10조의 의무를 기피하여 “을”의 정상적인 평가가 곤란할 때"),
]


def own_text(p) -> str:
    return "".join(rb._full(t) for t in p.iter(T) if next(t.iterancestors(f"{{{HP}}}p"), None) is p)


def make(src: bytes) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(src))
    roots = {}
    hits = {k: 0 for k, _ in RULES}
    for n in rb._sections(zin):
        root = etree.fromstring(zin.read(n))
        for p in list(root.iter(f"{{{HP}}}p")):
            t = own_text(p)
            for key, new in RULES:
                if key in t:
                    rb._set_para(p, new, in_table=True)
                    hits[key] += 1
                    break
        roots[n] = root
    bad = {k: v for k, v in hits.items() if v != 1}
    if bad:
        raise ValueError(f"양식에서 바꿀 문단을 못 찾았거나 둘 이상: {bad}")
    return civil._write(zin, roots)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    dst = civil.template_path(civil.SEISMIC)
    if dst.exists() and "--force" not in sys.argv:
        print("이미 있음(덮으려면 --force):", dst)
        return
    data = make(civil.template_path().read_bytes())
    missing = civil.check(data)
    if missing:
        raise SystemExit(f"자리표시 빠짐: {missing}")
    dst.write_bytes(data)
    print("만듦:", dst, len(data))


if __name__ == "__main__":
    main()
