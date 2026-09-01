"""한글 자모 분해 기반 검색 매칭.

일반 부분일치(LIKE %keyword%)만 쓰면 IME로 조합 중인 미완성 글자(예: "기ㅊ" —
"초"의 자음만 입력되고 모음은 아직 안 눌린 상태)는 어떤 결과와도 일치하지 않아
깜빡이는 것처럼 보인다("기차"/"기초"가 있어도 "기ㅊ"로는 둘 다 안 잡힘).

이 모듈은 검색어와 대상 문자열을 전부 자모(초성/중성/종성) 단위까지 풀어서
비교한다. 그러면 "기ㅊ"는 자모열 "ㄱㅣㅊ"가 되고, "기차"(ㄱㅣㅊㅏ)·"기초"
(ㄱㅣㅊㅗ) 둘 다 그 자모열로 시작하므로 둘 다 걸린다. 이후 "기차"까지 완성되면
자모열이 "ㄱㅣㅊㅏ"가 되어 "기초"(ㄱㅣㅊㅗ)는 더 이상 안 걸린다 — 실제 사이트
검색창에서 기대하는 동작과 동일하다.
"""

from __future__ import annotations

_CHOSEONG = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]
_JUNGSEONG = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
]
# 인덱스 0은 "받침 없음"을 뜻하므로 빈 문자열.
_JONGSEONG = [
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]

_SYLLABLE_COUNT = len(_CHOSEONG) * len(_JUNGSEONG) * len(_JONGSEONG)  # 11172


def decompose(text: str) -> str:
    """완성형 한글 음절을 자모(초성/중성/종성)로 풀어 이어붙인다.

    이미 낱자(호환 자모, 예: 조합 중인 단독 "ㅊ")이거나 한글이 아닌 문자는
    그대로 둔다 — 그래야 미완성 조합 상태의 검색어도 같은 방식으로 비교할 수 있다.
    """
    result: list[str] = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < _SYLLABLE_COUNT:
            cho, rem = divmod(code, len(_JUNGSEONG) * len(_JONGSEONG))
            jung, jong = divmod(rem, len(_JONGSEONG))
            result.append(_CHOSEONG[cho])
            result.append(_JUNGSEONG[jung])
            if jong:
                result.append(_JONGSEONG[jong])
        else:
            result.append(ch)
    return "".join(result)


def matches(query: str, candidate: str) -> bool:
    """자모 단위로 풀어서 candidate 안에 query가 부분 문자열로 있는지 본다."""
    query = query.strip()
    if not query:
        return True
    return decompose(query) in decompose(candidate)
