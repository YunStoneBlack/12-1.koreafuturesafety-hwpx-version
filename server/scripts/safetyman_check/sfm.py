"""SafetyMan .sfm(MFC CArchive) 읽기·쓰기 — 다산 파일로 구조를 맞춤(2026-10-15).

머리: ver(d) 이름 주소 준공년 월(i) 용도 이미지 구조형식 / 지상 지하(i) / 대지 건축 연면적 건폐 용적(d) / ?(i)
     소유주 연락처 관리주체 연락처(s) / 평가종류(i, 0 정밀점검) / 기관 연락처 일시(s) / 기울기 부동침하 ?(i, 0=a…) / 변위 메모(s) / 12개 실수(뜻 모름)
층 개수(i), 층마다: 시작 끝 대표 구조형식(i) + 66바이트(뜻 모름 — 재료 등) + 부재 7칸 × [강도(줄 수 + 줄(측정1·2·3·설계(d) 손상(i)))]
  + 7칸 × [탄산화(줄 수 + 줄(깊이1·2·3·피복 d))] + 80바이트 + 7칸 × 균열·박리·박락(있음 i + A~E i + 면적20%미만·이상 i)
  + 7칸 × 누수·철근노출(있음 i + A~E i) + 48바이트.
"""
from __future__ import annotations

import struct

ITEMS8 = ("crack", "scaling", "spalling")
ITEMS6 = ("leak", "rebar")


class R:
    def __init__(self, b: bytes):
        self.b, self.p = b, 0

    def d(self):
        v = struct.unpack_from("<d", self.b, self.p)[0]
        self.p += 8
        return v

    def i(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def s(self):
        n = self.b[self.p]
        self.p += 1
        if n == 0xFF:
            n = struct.unpack_from("<H", self.b, self.p)[0]
            self.p += 2
        v = self.b[self.p:self.p + n].decode("cp949")
        self.p += n
        return v

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v


class W:
    def __init__(self):
        self.out = bytearray()

    def d(self, v):
        self.out += struct.pack("<d", float(v))

    def i(self, v):
        self.out += struct.pack("<i", int(v))

    def s(self, v):
        e = v.encode("cp949")
        if len(e) < 0xFF:
            self.out.append(len(e))
        else:
            self.out.append(0xFF)
            self.out += struct.pack("<H", len(e))
        self.out += e

    def raw(self, v):
        self.out += v


HEAD = [("ver", "d"), ("name", "s"), ("addr", "s"), ("year", "s"), ("month", "i"), ("use", "s"), ("img", "s"), ("struct", "s"),
        ("above", "i"), ("below", "i"), ("land", "d"), ("bldg_area", "d"), ("total_area", "d"), ("coverage", "d"), ("far", "d"), ("x1", "i"),
        ("owner", "s"), ("owner_tel", "s"), ("manager", "s"), ("manager_tel", "s"), ("kind", "i"), ("org", "s"), ("org_tel", "s"), ("when", "s"),
        ("tilt", "i"), ("settle", "i"), ("x2", "i"), ("deform_note", "s")]


def read(b: bytes) -> dict:
    r = R(b)
    h = {k: getattr(r, t)() for k, t in HEAD}
    h["dbl12"] = [r.d() for _ in range(12)]
    floors = []
    for _ in range(r.i()):
        f = {"start": r.i(), "end": r.i(), "rep": r.i(), "type": r.i(), "mid": r.raw(66)}
        f["strength"] = [[(r.d(), r.d(), r.d(), r.d(), r.i()) for _ in range(r.i())] for _ in range(7)]
        f["carb"] = [[(r.d(), r.d(), r.d(), r.d()) for _ in range(r.i())] for _ in range(7)]  # 줄 = 깊이1·2·3·피복(cm) — 화면 저장 비교로 확인(10/15)
        f["gap80"] = r.raw(80)
        for it in ITEMS8:
            f[it] = [([r.i() for _ in range(7)] if r.i() else None) for _ in range(7)]
        for it in ITEMS6:
            f[it] = [([r.i() for _ in range(5)] if r.i() else None) for _ in range(7)]
        f["tail48"] = r.raw(48)
        floors.append(f)
    h["floors"] = floors
    h["rest"] = r.raw(len(b) - r.p)
    return h


def write(h: dict) -> bytes:
    w = W()
    for k, t in HEAD:
        getattr(w, t)(h[k])
    for v in h["dbl12"]:
        w.d(v)
    w.i(len(h["floors"]))
    for f in h["floors"]:
        for k in ("start", "end", "rep", "type"):
            w.i(f[k])
        w.raw(f["mid"])
        for rows in f["strength"]:
            w.i(len(rows))
            for a, b2, c, d, e in rows:
                w.d(a); w.d(b2); w.d(c); w.d(d); w.i(e)
        for rows in f["carb"]:
            w.i(len(rows))
            for a, b2, c, d in rows:
                w.d(a); w.d(b2); w.d(c); w.d(d)
        w.raw(f["gap80"])
        for it in ITEMS8 + ITEMS6:
            for rec in f[it]:
                if rec is None:
                    w.i(0)
                else:
                    w.i(1)
                    for v in rec:
                        w.i(v)
        w.raw(f["tail48"])
    w.raw(h["rest"])
    return bytes(w.out)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    b = open(sys.argv[1], "rb").read()
    h = read(b)
    print({k: h[k] for k, _ in HEAD if k not in ("img",)})
    print("dbl12", h["dbl12"], "floors", len(h["floors"]), "rest", len(h["rest"]), h["rest"][:40].hex(" "))
    for f in h["floors"]:
        print("층", f["start"], f["end"], f["rep"], f["type"], "mid", f["mid"].hex() if any(f["mid"]) else "0", "gap80", "0" if not any(f["gap80"]) else f["gap80"].hex(), "tail48", "0" if not any(f["tail48"]) else f["tail48"].hex())
        print("   강도", [[(round(a, 1), round(d, 1), e) for a, _, _, d, e in rows] for rows in f["strength"]])
        print("   탄산화", [[(round(a, 3), round(d, 2)) for a, _, _, d in rows] for rows in f["carb"]])
        for it in ITEMS8 + ITEMS6:
            print("  ", it, f[it])
    print("round trip 같음:", write(h) == b)
