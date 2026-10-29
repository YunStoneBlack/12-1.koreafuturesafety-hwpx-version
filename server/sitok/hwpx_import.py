"""다른 hwpx 파일의 구역을 이 파일로 가져올 때 서식 번호 맞추기(2026-10-29 — 옹벽·교량 섞인 묶음: 옹벽 원본에 교량 시설물편 장을 끼움).

두 원본은 짜임(공통편·시설물편 구역)이 같아도 한글이 저장할 때 header.xml 번호를 새로 매겨 글자 모양·문단 모양·테두리·스타일 번호가 거의 다 다름
(10/29 옹벽·교량 원본 글자 모양 350개 중 109개만 같음) → 구역 XML을 그대로 옮기면 엉뚱한 모양이 됨.
StyleMap: 가져올 쪽(src) header의 항목을 이 파일(dst) header에 맞춤 — 안쪽 참조(글자 모양 → 테두리·글꼴, 문단 모양 → 탭·번호 모양·테두리,
스타일 → 문단·글자 모양·다음 스타일, 번호 모양 → 글자 모양, 테두리 → 그림)를 먼저 dst 번호로 바꾼 뒤 내용이 같은 항목이 dst에 있으면 그 번호,
없으면 새 번호로 더함. 스타일은 이름이 같으면 dst 것(문단마다 문단·글자 모양 번호를 따로 가져서 모양은 그대로). 글꼴은 언어별 (이름, 종류)로.
remap_tree(구역 root): 구역 안 charPrIDRef·paraPrIDRef·borderFillIDRef·styleIDRef·outlineShapeIDRef·binaryItemIDRef를 바꿈."""
from __future__ import annotations

import copy

from lxml import etree

HH = "http://www.hancom.co.kr/hwpml/2011/head"
_GROUP = {"borderFill": "borderFills", "charPr": "charProperties", "tabPr": "tabProperties", "numbering": "numberings",
          "bullet": "bullets", "paraPr": "paraProperties", "style": "styles"}
_LANG = {"hangul": "HANGUL", "latin": "LATIN", "hanja": "HANJA", "japanese": "JAPANESE", "other": "OTHER", "symbol": "SYMBOL", "user": "USER"}
_TREE_REFS = {"charPrIDRef": "charPr", "paraPrIDRef": "paraPr", "borderFillIDRef": "borderFill", "styleIDRef": "style", "outlineShapeIDRef": "numbering"}


def _canon(el) -> bytes:
    """번호(id) 뺀 내용 — 같은 모양인지 비교용."""
    x = copy.deepcopy(el)
    x.attrib.pop("id", None)
    return etree.tostring(x)


class StyleMap:
    def __init__(self, dst_header, src_header, take_image):
        """take_image(src 그림 이름) → dst 그림 이름(dst 파일에 그림을 더하고 그 이름)."""
        self.dst, self.src, self.take_image = dst_header, src_header, take_image
        self.src_items = {cat: {e.get("id"): e for e in src_header.iter(f"{{{HH}}}{cat}")} for cat in _GROUP}
        self._index: dict[str, dict[bytes, str]] = {}
        self.memo: dict[str, dict[str, str]] = {cat: {} for cat in _GROUP}
        self.fonts: dict[tuple[str, str], str] = {}
        self.images: dict[str, str] = {}
        self.added: dict[str, int] = {cat: 0 for cat in _GROUP}  # 새로 더한 수(시험·알림용)

    # ---- dst 쪽
    def _group(self, cat: str):
        g = next(self.dst.iter(f"{{{HH}}}{_GROUP[cat]}"), None)
        if g is None:  # 묶음이 아예 없는 header(글머리표 0개 등) — refList 안에 만듦
            ref = next(self.dst.iter(f"{{{HH}}}refList"))
            g = etree.SubElement(ref, f"{{{HH}}}{_GROUP[cat]}")
            g.set("itemCnt", "0")
        return g

    def _idx(self, cat: str) -> dict[bytes, str]:
        if cat not in self._index:
            idx: dict[bytes, str] = {}
            for e in self._group(cat):
                idx.setdefault(_canon(e), e.get("id"))
            self._index[cat] = idx
        return self._index[cat]

    def _append(self, cat: str, el) -> str:
        g = self._group(cat)
        nid = str(max([int(x.get("id")) for x in g if (x.get("id") or "").isdigit()] or [-1 if cat in ("charPr", "paraPr", "style", "tabPr") else 0]) + 1)
        el.set("id", nid)
        g.append(el)
        g.set("itemCnt", str(len(g)))
        self._idx(cat)[_canon(el)] = nid
        self.added[cat] += 1
        return nid

    # ---- 글꼴·그림
    def _font(self, lang: str, fid: str) -> str:
        key = (lang, fid)
        if key in self.fonts:
            return self.fonts[key]
        sface = next((f for f in self.src.iter(f"{{{HH}}}fontface") if f.get("lang") == lang), None)
        dface = next((f for f in self.dst.iter(f"{{{HH}}}fontface") if f.get("lang") == lang), None)
        sfont = next((x for x in (sface if sface is not None else []) if x.get("id") == fid), None)
        if sfont is None or dface is None:
            self.fonts[key] = fid
            return fid
        hit = next((x.get("id") for x in dface if x.get("face") == sfont.get("face") and x.get("type") == sfont.get("type")), None)
        if hit is None:
            new = copy.deepcopy(sfont)
            hit = str(len(dface))
            new.set("id", hit)
            for img in new.iter():
                if img.get("binaryItemIDRef"):
                    img.set("binaryItemIDRef", self._image(img.get("binaryItemIDRef")))
            dface.append(new)
            dface.set("fontCnt", str(len(dface)))
        self.fonts[key] = hit
        return hit

    def _image(self, key: str) -> str:
        if key not in self.images:
            self.images[key] = self.take_image(key) or key
        return self.images[key]

    # ---- 항목 하나
    def map(self, cat: str, sid: str | None) -> str | None:
        if sid is None or cat not in _GROUP:
            return sid
        memo = self.memo[cat]
        if sid in memo:
            return memo[sid]
        src = self.src_items[cat].get(sid)
        if src is None:  # 없는 번호(4294967295 = 없음 등)는 그대로
            return sid
        if cat == "style":
            hit = next((e.get("id") for e in self._group("style") if e.get("name") == src.get("name") and e.get("type") == src.get("type")), None)
            if hit is not None:
                memo[sid] = hit
                return hit
        el = copy.deepcopy(src)
        self._inner(cat, el, sid)
        hit = self._idx(cat).get(_canon(el))
        if hit is None:
            hit = self._append(cat, el)
            if cat == "style" and el.get("nextStyleIDRef") == "__self__":
                el.set("nextStyleIDRef", hit)
        memo[sid] = hit
        return hit

    def _inner(self, cat: str, el, sid: str) -> None:
        """항목 안 참조를 dst 번호로."""
        if cat == "charPr":
            if el.get("borderFillIDRef"):
                el.set("borderFillIDRef", self.map("borderFill", el.get("borderFillIDRef")))
            fr = el.find(f"{{{HH}}}fontRef")
            if fr is not None:
                for a, lang in _LANG.items():
                    if fr.get(a) is not None:
                        fr.set(a, self._font(lang, fr.get(a)))
        elif cat == "paraPr":
            if el.get("tabPrIDRef") is not None:
                el.set("tabPrIDRef", self.map("tabPr", el.get("tabPrIDRef")))
            hd = el.find(f"{{{HH}}}heading")
            if hd is not None and (hd.get("idRef") or "0") != "0":
                kind = "bullet" if hd.get("type") == "BULLET" else "numbering"
                hd.set("idRef", self.map(kind, hd.get("idRef")))
            for b in el.iter(f"{{{HH}}}border"):
                if b.get("borderFillIDRef"):
                    b.set("borderFillIDRef", self.map("borderFill", b.get("borderFillIDRef")))
        elif cat == "style":
            el.set("paraPrIDRef", self.map("paraPr", el.get("paraPrIDRef")))
            el.set("charPrIDRef", self.map("charPr", el.get("charPrIDRef")))
            nxt = el.get("nextStyleIDRef")  # 다음 스타일은 이름으로만(서로 가리키면 끝없이 돌므로) — dst에 없으면 자기 자신
            nsrc = self.src_items["style"].get(nxt) if nxt is not None else None
            hit = next((e.get("id") for e in self._group("style") if nsrc is not None and nxt != sid
                        and e.get("name") == nsrc.get("name") and e.get("type") == nsrc.get("type")), None)
            if nxt is not None:
                el.set("nextStyleIDRef", hit if hit is not None else "__self__")
        elif cat in ("numbering", "bullet"):
            for x in el.iter():
                if x.get("charPrIDRef") is not None:
                    x.set("charPrIDRef", self.map("charPr", x.get("charPrIDRef")))
        for x in el.iter():  # 테두리 그림 무늬·그림 글머리표
            if x.get("binaryItemIDRef"):
                x.set("binaryItemIDRef", self._image(x.get("binaryItemIDRef")))

    # ---- 구역 하나
    def remap_tree(self, root) -> None:
        for x in root.iter():
            if not isinstance(x.tag, str):
                continue
            for a, cat in _TREE_REFS.items():
                v = x.get(a)
                if v is not None:
                    x.set(a, self.map(cat, v))
            v = x.get("binaryItemIDRef")
            if v:
                x.set("binaryItemIDRef", self._image(v))
