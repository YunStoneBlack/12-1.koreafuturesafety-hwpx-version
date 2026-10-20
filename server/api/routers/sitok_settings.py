"""시특법 설정(2026-10-10 3단계, sitok-settings.html) — 보고서 앞부분·부록에 자동으로 들어가는 회사·기술자 서류와 사용 장비.

- `GET    /sitok/settings` — 전부(회사 서류·기술자·장비).
- `POST|DELETE /sitok/settings/company/{kind}` — 회사 서류 그림(안전진단전문기관 등록증, 유효기간 칸).
- `PATCH  /sitok/settings/persons/{id}` — 기술자 시특법 칸(분야·결과표 기술등급). 기술자 추가·이름·직위·등급은 서류 자동화와 같은
  `/contract-docs/persons`(같은 사람을 산안법 착수계와 같이 씀).
- `POST|DELETE /sitok/settings/persons/{id}/docs/{kind}` — 기술자 시특법 서류(정밀안전진단 교육 수료증·책임기술자 자격, 유효기간 칸).
- `POST /sitok/settings/equipment`, `PATCH|DELETE /sitok/settings/equipment/{id}`, `POST .../{id}/photo`, `GET .../photo/{n}` — 사용 장비(1.6 표).
- `POST /sitok/settings/prices`, `PATCH|DELETE /sitok/settings/prices/{id}` — 개략공사비 보수 단가표(10/11, 처음 열 때 기본값 채움).
- `POST /sitok/settings/vocab`, `DELETE /sitok/settings/vocab/{id}` — 결함 부재·결함유형 회사 목록(10/12, 처음 열 때 server/sitok/kinds.py 기본값).
- `GET /sitok/settings/master/file`, `POST /sitok/settings/master` — 회사 원본 템플릿 받기·고친 한글 올리기(10/12, server/sitok/master.py).
- `GET /sitok/settings/corrections`, `DELETE .../corrections/{id}`, `GET .../corrections/{id}/photo` — 사진 분류 교정 기록(10/12, server/sitok/learn.py).
서류 그림·유효기간 저장은 서류 자동화(contract_library)와 같은 표(SubmitDoc)·같은 함수 — 종류 이름만 시특법 것(SITOK_*).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models_web import SitokEquipment, SitokUnitPrice, SitokVocab, TechPerson, User
from core.stored_path import to_full, to_stored
from server.api import storage
from server.api.deps import get_current_user, get_db
from server.api.routers import contract_library as lib
from server.api.routers.sitok import ROOT
from server.contract_docs import files
from server.sitok import kinds, master

router = APIRouter(prefix="/sitok/settings", tags=["sitok"])
# 서류 종류 — SubmitDoc.kind(서류 자동화의 build.COMPANY_DOCS·PERSON_DOCS와 이름이 겹치지 않게 sitok_ 붙임)
SITOK_COMPANY_DOCS = [("sitok_reg", "안전진단전문기관 등록증")]
SITOK_PERSON_DOCS = [("sitok_edu", "정밀안전진단 교육 수료증"), ("sitok_license", "책임기술자 자격"),
                     ("sitok_sign", "서명·도장(관급 보안각서)")]  # 10/12 서류 자동화 관급 착수계 — 사람 보안각서 "(서명)" 위
COMPANY_LABELS = dict(SITOK_COMPANY_DOCS)
PERSON_LABELS = dict(SITOK_PERSON_DOCS)
EQUIP_DIR = ROOT / "장비"


def _person_out(db: Session, p: TechPerson) -> dict:
    docs = lib.person_docs(db, p.id)
    return {"id": p.id, "name": p.name, "position": p.position, "grade": p.grade, "qualification": p.qualification, "active": p.active,
            "sitok_field": p.sitok_field, "sitok_grade": p.sitok_grade,
            "docs": [lib.doc_out(docs.get(k), k, label) for k, label in SITOK_PERSON_DOCS]}


def _equip_out(e: SitokEquipment) -> dict:
    return {"id": e.id, "grp": e.grp, "name": e.name, "model": e.model, "purpose": e.purpose, "active": e.active, "sort": e.sort,
            "photos": len(e.photos or []), "ts": abs(hash(tuple(e.photos or []))) % 100000}


def equipment(db: Session, company_id: int) -> list[SitokEquipment]:
    return db.query(SitokEquipment).filter(SitokEquipment.company_id == company_id).order_by(SitokEquipment.sort, SitokEquipment.id).all()


# 보수 단가 기본값(10/11 민재형: 조달청 표준시장단가·시중노임단가 등으로 알아서) — 공법 이름은 조치 필요사항 문구(sitok_defects.default_action)와 같게.
# 표준시장단가 = 국토교통부·한국건설기술연구원 "2025년 상반기 건설공사 표준시장단가"(재료비 제외 단가). 표준시장단가에 없는 균열 주입·표면처리는
# 시중 견적 하한(검색, 확인 필요). 설정 탭에서 고침.
DEFAULT_PRICES = [
    ("표면처리", "㎡", 50000, "검색 참고값 — 시중 견적 5만~15만 원의 하한", "확인 필요(표준시장단가에 없음) — 0.3mm 미만 균열은 길이×0.25 ㎡로 환산(형 10/14·15)"),
    ("에폭시주입보수", "m", 100000, "검색 참고값 — 시중 견적 m당 10만~30만 원의 하한", "확인 필요(표준시장단가에 없음) — 0.3mm 이상 균열은 길이(m) 그대로(10/15)"),
    ("탄성실링 보수", "m", 4431, "표준시장단가 2025 상반기 EF700.00100 실링마감(V컷팅·프라이머·백업재·실링재 주입)", "재료비 별도"),
    ("마감재 재시공", "㎡", 6396, "표준시장단가 2025 상반기 NC102.20000 수성페인트 롤러칠 벽체 1회 3,198원 × 2회", "재료비 별도"),
    ("표면정리 후 재도장", "㎡", 10124, "표준시장단가 2025 상반기 NA012.10000 녹막이 1회 3,988원 + NB112.20000 유성 롤러 철재 3,068원 × 2회", "재료비 별도"),
    ("단면복구", "㎡", 15384, "표준시장단가 2025 상반기 HG022.01000 폴리머 시멘트 모르타르 1종(3층) — 근사", "재료비 별도·근사"),
    ("방수 보수", "㎡", 6602, "표준시장단가 2025 상반기 HC001.10000 도막방수 바닥 3,844원 + HC003.10000 마감도료 2,758원", "재료비 별도"),
    ("주의관찰", "식", 0, "-", "공사비 없음"),
]


def prices(db: Session, company_id: int) -> list[SitokUnitPrice]:
    rows = db.query(SitokUnitPrice).filter(SitokUnitPrice.company_id == company_id).order_by(SitokUnitPrice.sort, SitokUnitPrice.id).all()
    if not rows:  # 처음 — 기본값 채움
        for i, (m, u, pr, src, note) in enumerate(DEFAULT_PRICES, 1):
            db.add(SitokUnitPrice(company_id=company_id, method=m, unit=u, price=pr, source=src, note=note, sort=i))
        db.commit()
        rows = db.query(SitokUnitPrice).filter(SitokUnitPrice.company_id == company_id).order_by(SitokUnitPrice.sort, SitokUnitPrice.id).all()
    return rows


def _price_out(p: SitokUnitPrice) -> dict:
    return {"id": p.id, "method": p.method, "unit": p.unit, "price": p.price, "source": p.source, "note": p.note}


def vocab_rows(db: Session, company_id: int, report_id: int | None = None, fam: str = "") -> list[SitokVocab]:
    """결함 부재·결함유형 목록 — 회사 것(처음이면 기본값 채움) + report_id가 있으면 그 회차에만 추가한 것(뒤에).
    fam = 목록 묶음(kinds.FAMILIES — "" 건축물, "wall" 옹벽: SitokVocab.kind가 wall_member·wall_dtype, 10/20). 줄마다 base_kind = 앞말 뗀 member/dtype."""
    defaults = kinds.FAMILIES[fam]
    want = {kinds.vocab_kind(fam, k): k for k in defaults}
    q = db.query(SitokVocab).filter(SitokVocab.company_id == company_id, SitokVocab.report_id.is_(None), SitokVocab.kind.in_(list(want)))
    rows = q.all()
    have = {r.kind for r in rows}
    if have != set(want):  # 처음(또는 한 종류를 다 지운 뒤) — 기본값
        for vk, kind in want.items():
            if vk not in have:
                db.add_all(SitokVocab(company_id=company_id, kind=vk, name=n, sort=i) for i, n in enumerate(defaults[kind], 1))
        db.commit()
        rows = q.all()
    rows.sort(key=lambda r: (r.sort, r.id))
    if report_id:
        rows += sorted(db.query(SitokVocab).filter(SitokVocab.company_id == company_id, SitokVocab.report_id == report_id, SitokVocab.kind.in_(list(want))).all(),
                       key=lambda r: (r.sort, r.id))
    for r in rows:  # 화면·검사는 member/dtype 이름으로(저장 칸 kind는 그대로)
        r.base_kind = want[r.kind]
    return rows


def vocab_out(rows: list[SitokVocab]) -> dict:
    return {kind: [{"id": r.id, "name": r.name, "scope": "report" if r.report_id else "company"} for r in rows if r.base_kind == kind] for kind in kinds.DEFAULTS}


def vocab_names(db: Session, company_id: int, report_id: int | None = None, fam: str = "") -> dict[str, list[str]]:
    rows = vocab_rows(db, company_id, report_id, fam)
    return {kind: [r.name for r in rows if r.base_kind == kind] for kind in kinds.DEFAULTS}


def add_vocab(db: Session, company_id: int, kind: str, name: str, report_id: int | None = None, fam: str = "") -> None:
    """목록에 하나 더(이미 있으면 그대로). 회사 목록에 넣으면 그 회차에만 넣었던 같은 이름은 지움."""
    name = " ".join((name or "").split())
    if kind not in kinds.DEFAULTS or not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "추가할 이름을 넣어 주세요.")
    if len(name) > 20:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이름은 20자 안으로 — 표 칸이 좁습니다.")
    vk = kinds.vocab_kind(fam, kind)
    rows = [r for r in vocab_rows(db, company_id, report_id, fam) if r.base_kind == kind]
    if any(r.name == name and (r.report_id is None or report_id) for r in rows):
        return
    if report_id is None:
        db.query(SitokVocab).filter(SitokVocab.company_id == company_id, SitokVocab.kind == vk, SitokVocab.name == name,
                                    SitokVocab.report_id.isnot(None)).delete(synchronize_session=False)
    db.add(SitokVocab(company_id=company_id, report_id=report_id, kind=vk, name=name, sort=max((r.sort for r in rows), default=0) + 1))
    db.commit()


@router.get("")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = lib.company_docs(db, user.company_id)
    return {
        "company_docs": [lib.doc_out(docs.get(k), k, label) for k, label in SITOK_COMPANY_DOCS],
        "persons": [_person_out(db, p) for p in lib.persons(db, user.company_id)],
        "equipment": [_equip_out(e) for e in equipment(db, user.company_id)],
        "prices": [_price_out(p) for p in prices(db, user.company_id)],
        "vocab": vocab_out(vocab_rows(db, user.company_id)),
        "vocab_wall": vocab_out(vocab_rows(db, user.company_id, fam="wall")),  # 옹벽 목록(10/20)
        "master": master.info_all(),
    }


def _master_kind(kind: str) -> str:
    if kind not in master.FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "원본 종류는 정기·정밀본문·정밀부록입니다.")
    return kind


@router.get("/master/file")
def master_file(kind: str = "정기", user: User = Depends(get_current_user)):
    p = master.master_path(_master_kind(kind))
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "원본 템플릿이 아직 없습니다.")
    return FileResponse(p, media_type="application/octet-stream", filename=p.name)


@router.post("/master")
def upload_master(file: UploadFile = File(...), kind: str = Form("정기"), user: User = Depends(get_current_user)):
    """형이 한글에서 고친 원본 올리기(kind = 정기 / 정밀본문 / 정밀부록) — hwp는 작업 프로그램이 hwpx로. 결과표를 못 읽거나 프로그램이 채우는 자리가 없으면
    안 받음(옛 원본은 보관)."""
    import tempfile

    from server.contract_docs import hwp_queue
    from server.sitok import report_build as rb

    kind = _master_kind(kind)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".hwp", ".hwpx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "한글 파일(.hwp·.hwpx)을 올려 주세요.")
    data = file.file.read()
    if ext == ".hwp":
        try:
            data = hwp_queue.convert_via_worker(data, ".hwp", to="hwpx", wait=170)
        except RuntimeError as err:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "원본.hwpx"
        tmp.write_bytes(data)
        try:
            if kind == "정기":
                rb.read_old(tmp)
            missing = master.check(tmp, kind)
        except Exception as err:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"원본으로 쓸 수 없습니다: {str(err).splitlines()[0][:150]}") from err
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "프로그램이 채우는 자리가 없어 안 바꿨습니다: " + ", ".join(missing))
    master.install(data, kind=kind)
    return master.info_all()


class VocabIn(BaseModel):
    kind: str
    name: str
    fam: str = ""  # "" 건축물 / "wall" 옹벽 목록


def _fam(fam: str) -> str:
    if fam not in kinds.FAMILIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "목록 묶음이 맞지 않습니다.")
    return fam


@router.post("/vocab")
def post_vocab(body: VocabIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fam = _fam(body.fam)
    add_vocab(db, user.company_id, body.kind, body.name, fam=fam)
    return vocab_out(vocab_rows(db, user.company_id, fam=fam))


@router.delete("/vocab/{vocab_id}")
def delete_vocab(vocab_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회사 목록에서 빼기 — 이미 그 이름으로 적은 결함은 그대로(새로 고를 때만 안 보임)."""
    v = db.get(SitokVocab, vocab_id)
    if v is None or v.company_id != user.company_id or v.report_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "목록 항목을 찾을 수 없습니다.")
    fam = "wall" if v.kind.startswith("wall_") else ""
    if sum(1 for r in vocab_rows(db, user.company_id, fam=fam) if r.kind == v.kind) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "마지막 하나는 지울 수 없습니다.")
    db.delete(v)
    db.commit()
    return vocab_out(vocab_rows(db, user.company_id, fam=fam))


# ---------- 사진 분류 교정 기록(10/12 — server/sitok/learn.py) ----------

@router.get("/corrections")
def get_corrections(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """(AI 추천 → 점검자 값) 묶음별 — 다음 사진 분석 때 AI에게 같이 보여 주는 회사 판단 기준."""
    from server.sitok import learn

    return {"groups": learn.groups(db, user.company_id)}


def _correction(db: Session, user: User, cid: int):
    from core.models_web import SitokCorrection

    c = db.get(SitokCorrection, cid)
    if c is None or c.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "교정 기록을 찾을 수 없습니다.")
    return c


@router.delete("/corrections/{cid}")
def delete_correction(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """잘못 쌓인 기록 지우기(점검자 실수 등) — 결함 자체는 그대로, 그 결함의 AI 추천 기록도 지워 다시 안 쌓이게."""
    from core.models_web import SitokDefect
    from server.sitok import learn

    c = _correction(db, user, cid)
    d = db.get(SitokDefect, c.defect_id) if c.defect_id else None
    if d is not None:
        d.ai_guess = None
    if c.thumb:
        Path(c.thumb).unlink(missing_ok=True)
    db.delete(c)
    db.commit()
    return {"groups": learn.groups(db, user.company_id)}


@router.get("/corrections/{cid}/photo")
def correction_photo(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _correction(db, user, cid)
    if not c.thumb or not Path(c.thumb).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(c.thumb, media_type="image/jpeg")


class PriceIn(BaseModel):
    method: str | None = None
    unit: str | None = None
    price: int | None = None
    source: str | None = None
    note: str | None = None


def _require_price(db: Session, user: User, price_id: int) -> SitokUnitPrice:
    p = db.get(SitokUnitPrice, price_id)
    if p is None or p.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "단가를 찾을 수 없습니다.")
    return p


@router.post("/prices")
def add_price(body: PriceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    last = max((p.sort for p in prices(db, user.company_id)), default=0)
    p = SitokUnitPrice(company_id=user.company_id, sort=last + 1, **{k: (v.strip() if isinstance(v, str) else v)
                                                                      for k, v in body.model_dump(exclude_unset=True).items()})
    db.add(p)
    db.commit()
    return _price_out(p)


@router.patch("/prices/{price_id}")
def update_price(price_id: int, body: PriceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _require_price(db, user, price_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return _price_out(p)


@router.delete("/prices/{price_id}")
def delete_price(price_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_require_price(db, user, price_id))
    db.commit()
    return {"ok": True}


@router.post("/company/{kind}")
def upload_company_doc(kind: str, file: UploadFile = File(...), issued_on: str = Form(""), valid_until: str = Form(""),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if kind not in COMPANY_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    return lib._upload_dated(db, user, file, kind, COMPANY_LABELS[kind], files.company_doc_path(COMPANY_LABELS[kind]),
                             lib.company_docs(db, user.company_id).get(kind), None, issued_on, valid_until)


@router.delete("/company/{kind}")
def delete_company_doc(kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if kind not in COMPANY_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    lib._drop_doc(db, lib.company_docs(db, user.company_id).get(kind))
    return {"ok": True}


class PersonSitokIn(BaseModel):
    sitok_field: str | None = None
    sitok_grade: str | None = None


@router.patch("/persons/{person_id}")
def update_person(person_id: int, body: PersonSitokIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = lib._require_person(db, user, person_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, (v or "").strip())
    db.commit()
    return _person_out(db, p)


@router.post("/persons/{person_id}/docs/{kind}")
def upload_person_doc(person_id: int, kind: str, file: UploadFile = File(...), issued_on: str = Form(""), valid_until: str = Form(""),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = lib._require_person(db, user, person_id)
    if kind not in PERSON_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    lib._upload_dated(db, user, file, kind, PERSON_LABELS[kind], files.person_doc_path(p.id, p.name, PERSON_LABELS[kind]),
                      lib.person_docs(db, p.id).get(kind), p.id, issued_on, "")
    row = lib.person_docs(db, p.id).get(kind)
    if row is not None and kind in lib.VALID_RULES:
        # 수료증은 유효기간이 적혀 있지 않음 — AI가 교육기간 끝을 유효기간으로 읽어도 버리고 항상 수료일 + 5년
        row.valid_until = lib.default_valid_until(kind, row.issued_on) if row.issued_on else None
        db.commit()
    return _person_out(db, p)


@router.delete("/persons/{person_id}/docs/{kind}")
def delete_person_doc(person_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = lib._require_person(db, user, person_id)
    if kind not in PERSON_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 서류 종류입니다.")
    lib._drop_doc(db, lib.person_docs(db, p.id).get(kind))
    return _person_out(db, p)


class EquipIn(BaseModel):
    grp: str | None = None
    name: str | None = None
    model: str | None = None
    purpose: str | None = None
    sort: int | None = None
    active: bool | None = None


def _require_equip(db: Session, user: User, equip_id: int) -> SitokEquipment:
    e = db.get(SitokEquipment, equip_id)
    if e is None or e.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "장비를 찾을 수 없습니다.")
    return e


@router.post("/equipment")
def add_equipment(body: EquipIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    last = max((e.sort for e in equipment(db, user.company_id)), default=0)
    e = SitokEquipment(company_id=user.company_id, sort=last + 1)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v.strip() if isinstance(v, str) else v)
    db.add(e)
    db.commit()
    return _equip_out(e)


@router.patch("/equipment/{equip_id}")
def update_equipment(equip_id: int, body: EquipIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require_equip(db, user, equip_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return _equip_out(e)


@router.delete("/equipment/{equip_id}")
def delete_equipment(equip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require_equip(db, user, equip_id)
    for p in e.photos or []:
        Path(to_full(p)).unlink(missing_ok=True)
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.post("/equipment/{equip_id}/photo")
def upload_equipment_photo(equip_id: int, file: UploadFile = File(...), replace: bool = Form(True),
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """장비 사진 — replace면 있던 사진을 지우고 이 한 장으로, 아니면 덧붙임(표 칸엔 1~2장)."""
    e = _require_equip(db, user, equip_id)
    jpeg = files.to_jpeg(file.file.read(), file.filename or "")
    old = list(e.photos or [])
    if replace:
        for p in old:
            Path(to_full(p)).unlink(missing_ok=True)
        old = []
    dest = EQUIP_DIR / f"{storage._clean(e.name)[:20] or '장비'}_{e.id}_{len(old) + 1}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(jpeg)
    e.photos = old + [to_stored(str(dest))]
    db.commit()
    return _equip_out(e)


@router.get("/equipment/{equip_id}/photo/{n}")
def equipment_photo(equip_id: int, n: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _require_equip(db, user, equip_id)
    photos = e.photos or []
    if not 0 <= n < len(photos) or not Path(to_full(photos[n])).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사진이 없습니다.")
    return FileResponse(to_full(photos[n]), media_type="image/jpeg")
