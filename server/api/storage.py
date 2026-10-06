"""파일 저장소 규칙(2026-10-01 사용자) — 사진·PDF·한글·서명을 사람이 탐색기에서 바로 찾을 수 있게 현장·회차 폴더로.

저장소 = `.env.server`의 DATA_DIR(없으면 프로그램 폴더의 data). 옮길 때는 폴더를 통째로 복사하고 DATA_DIR 한 줄만 바꾼다
(DB에는 저장소 기준 상대경로만 들어감 — core/stored_path.py).

    저장소\\
     ├ 26-1)_테스트현장테스트보고서\\            현장 폴더 = 관리번호(줄임))_현장명(현장명만 30자까지, 못 쓰는 글자는 _)
     │  └ 05회차\\
     │     ├ 사진\\26-1)_테스트현장테스트보고서_05회차_전경사진1.jpg    칸 이름 = 보고서 화면 칸 이름 + 칸 번호
     │     ├ 26-1)_테스트현장테스트보고서_05회차.pdf / .hwpx
     │     └ 26-1)_테스트현장테스트보고서_05회차_현장책임자서명.png
     ├ _서명\\     요원 서명·결재 도장
     ├ _자료실\\   11번 배포 자료 그림
     └ _시스템\\   작은 사진·폰 미리보기·한글 중간 파일(지워도 다시 만들어짐)

이름은 사람이 보기 위한 것 — 안쪽 연결은 지금처럼 DB 번호. 현장명·관리번호·회차가 바뀌면 `relocate_site`/`relocate_report`가
폴더·파일 이름을 다시 맞추고 DB 경로를 고친다(예전 data\\photos\\report_N 구조에서 옮길 때도 같은 함수 — server/scripts/migrate_storage.py).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from core.db import DATA_DIR
from core.models_db import (
    CurrentProcessEntry, CurrentProcessPhoto, Finding, InspectionPhoto, Measurement, OverviewPhoto, PreviousFinding,
    ProcessHazardEntry, ProvidedMaterial, Report, SafetyEducation, Site,
)
from server.api.site_label import short_mgmt

NAME_MAX = 30  # 현장명(관리번호 빼고) 최대 글자 — 경로가 윈도우 한도(260자)를 넘지 않게
SYSTEM_DIR = DATA_DIR / "_시스템"
THUMB_DIR = SYSTEM_DIR / "thumbs"
PREVIEW_DIR = SYSTEM_DIR / "previews"
SIGNATURE_DIR = DATA_DIR / "_서명"
LIBRARY_DIR = DATA_DIR / "_자료실"
PHOTO_SUBDIR = "사진"
CONTRACT_SUBDIR = "착수계·완수계"  # 현장 폴더 안 착수계·완수계 서류(server/contract_docs/files.py)
# 예전 구조(2026-10-01 전) — 옮기기 전 파일도 계속 읽히고, 삭제할 때도 같이 정리한다
OLD_PHOTO_DIR = DATA_DIR / "photos"
OLD_REPORTS_DIR = DATA_DIR / "reports"
OLD_SIGNATURE_DIR = DATA_DIR / "signatures"

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# 사진 칸 → 파일 이름 속 칸 이름(보고서 화면 칸 이름 그대로). (표, 경로 칸, 이름 만들기)
PHOTO_KINDS = [
    (OverviewPhoto, "photo_path", lambda r: f"전경사진{r.slot}"),
    (InspectionPhoto, "photo_path", lambda r: f"점검사진{r.slot}"),
    (PreviousFinding, "photo_path", lambda r: f"이전지적사항{r.slot}"),
    (PreviousFinding, "completion_photo_path", lambda r: f"이전지적사항{r.slot}_이행완료"),
    (CurrentProcessPhoto, "photo_path", lambda r: f"현재진행공정사진{r.slot}"),
    (CurrentProcessEntry, "photo_path", lambda r: f"현재진행공정{r.slot}"),
    (Finding, "photo_path", lambda r: f"지적사항{r.slot}"),
    (ProcessHazardEntry, "photo_path", lambda r: f"향후진행공정{r.slot}"),
    (SafetyEducation, "photo_path", lambda r: "TBM교육"),
    (Measurement, "photo_path", lambda r: f"계측자료_{r.instrument_type}"),
    (ProvidedMaterial, "custom_photo_path", lambda r: f"제공자료{r.slot}"),
]


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", _BAD.sub("_", text or "")).strip()
    return text.rstrip(" .")  # 윈도우는 끝의 공백·점을 못 씀


def base_site_name(site: Site) -> str:
    name = _clean(_clean(site.name)[:NAME_MAX])
    mgmt = _clean(short_mgmt(site.management_no))
    return (f"{mgmt})_{name}" if mgmt else name) or f"현장{site.id}"


def site_folder_name(db: Session, site: Site) -> str:
    """현장 폴더 이름. 다른 현장과 같아지면(관리번호 없는 같은 이름 등) 번호가 큰 쪽에 _현장번호를 붙인다."""
    base = base_site_name(site)
    others = db.query(Site).filter(Site.company_id == site.company_id, Site.id < site.id).all()
    if any(base_site_name(o).casefold() == base.casefold() for o in others):
        return f"{base}_{site.id}"
    return base


def site_dir(db: Session, site: Site) -> Path:
    return DATA_DIR / site_folder_name(db, site)


def _visit_folder(db: Session, report: Report) -> str:
    """회차 폴더 이름 "05회차". 같은 현장에 같은 회차 보고서가 둘이면 번호가 큰 쪽에 _보고서번호."""
    name = f"{report.visit_no:02d}회차"
    dup = db.query(Report.id).filter(Report.site_id == report.site_id, Report.visit_no == report.visit_no,
                                     Report.id < report.id).first()
    return f"{name}_{report.id}" if dup else name


def report_dir(db: Session, report: Report) -> Path:
    site = report.site or db.get(Site, report.site_id)
    return site_dir(db, site) / _visit_folder(db, report)


def report_base(db: Session, report: Report) -> str:
    """파일 이름 앞부분 "26-1)_현장명_05회차"."""
    site = report.site or db.get(Site, report.site_id)
    return f"{site_folder_name(db, site)}_{_visit_folder(db, report)}"


def _report_photo_paths(db: Session, report_id: int) -> list[str]:
    return [getattr(row, field) for model, field, _ in PHOTO_KINDS
            for row in db.query(model).filter(model.report_id == report_id).all() if getattr(row, field)]


def photo_path(db: Session, report: Report, label: str, suffix: str, own: str = "") -> Path:
    """사진 칸 파일 경로(폴더는 만들어 둠). label = 칸 이름(예: "전경사진1"). own = 이 칸이 지금 쓰는 파일.
    같은 이름을 이 보고서의 다른 칸이 쓰고 있으면(이전지적사항은 이월 때문에 칸 번호가 바뀔 수 있음) _2, _3…을 붙여 덮어쓰지 않는다."""
    folder = report_dir(db, report) / PHOTO_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{report_base(db, report)}_{_clean(label)}"
    taken = [p for p in _report_photo_paths(db, report.id) if not (own and same_path(p, own))]
    dest, n = folder / f"{stem}{suffix.lower()}", 1
    while any(same_path(p, dest) for p in taken):
        n += 1
        dest = folder / f"{stem}_{n}{suffix.lower()}"
    return dest


def pdf_path(db: Session, report: Report) -> Path:
    folder = report_dir(db, report)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{report_base(db, report)}.pdf"


def hwpx_path(db: Session, report: Report) -> Path:
    """[한글 받기]용으로 만들어 두는 파일(DB에는 안 적음 — 받을 때마다 최신으로 다시 만듦)."""
    folder = report_dir(db, report)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{report_base(db, report)}.hwpx"


def notify_signature_path(db: Session, report: Report) -> Path:
    folder = report_dir(db, report)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{report_base(db, report)}_현장책임자서명.png"


def preview_dir(report_id: int) -> Path:
    """폰 미리보기 쪽 이미지 폴더(PDF가 바뀌면 다시 만듦)."""
    return PREVIEW_DIR / f"report_{report_id}"


# ---------- 지우기 ----------
def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def drop_old(old: str | None, new: str | Path) -> None:
    """사진을 바꿔 넣었을 때 예전 파일 지우기(확장자가 달라 이름이 다르거나 예전 구조에 있던 것). 같은 자리면 안 지움(방금 쓴 파일)."""
    if old and not same_path(old, new):
        Path(old).unlink(missing_ok=True)
        _remove_empty_parents(Path(old).parent)


def _remove_empty_parents(folder: Path) -> None:
    """빈 폴더를 저장소 바로 아래까지 거슬러 올라가며 지운다(옮기거나 지운 뒤 껍데기 정리)."""
    root = os.path.normcase(os.path.abspath(str(DATA_DIR)))
    folder = Path(os.path.abspath(str(folder)))
    while os.path.normcase(str(folder)).startswith(root + os.sep):
        try:
            folder.rmdir()  # 비어 있을 때만 지워짐
        except OSError:
            return
        folder = folder.parent


def report_file_targets(db: Session, report: Report) -> list[Path]:
    """보고서를 지울 때 같이 지울 파일·폴더 목록 — 회차 폴더(새 구조)·예전 사진 폴더·미리보기·예전 자리 PDF·서명·한글 파일.
    DB 행을 지우기 전에 모으고(이름 계산에 행이 필요), DB 삭제가 확정된 뒤 `delete_targets`로 지운다."""
    rid = report.id
    folders = [report_dir(db, report), OLD_PHOTO_DIR / f"report_{rid}"]
    # 다음 회차 이전지적사항이 이 보고서의 지적사항 사진을 같이 쓰고 있으면(이월 복사본) 그 파일은 남긴다
    shared = [pf.photo_path for pf in db.query(PreviousFinding).filter(PreviousFinding.report_id != rid).all() if pf.photo_path]
    if any(any(_inside(p, f) for f in folders) for p in shared):
        targets = [f for folder in folders if folder.exists() for f in folder.rglob("*")
                   if f.is_file() and not any(same_path(f, p) for p in shared)]
    else:
        targets = list(folders)
    targets += [preview_dir(rid), OLD_REPORTS_DIR / f"report_{rid}.hwpx"]
    for path in (report.pdf_path, report.notify_signature_path):
        if path:
            targets.append(Path(path))
            if path.lower().endswith(".pdf"):
                targets.append(Path(path).with_name(Path(path).stem + "_preview"))  # 예전 미리보기 자리
    return targets


def _inside(path: str | Path, folder: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(path))).startswith(os.path.normcase(os.path.abspath(str(folder))) + os.sep)


def delete_targets(targets: list[Path]) -> None:
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        _remove_empty_parents(target.parent)


# ---------- 이름 다시 맞추기(현장명·관리번호·회차 변경, 예전 구조에서 옮기기) ----------
def _owned_by(report: Report, path: str) -> bool:
    """이 보고서 소유 파일인지 — 예전 구조에서 다른 보고서 폴더(data/photos/report_다른번호)에 있으면 이월 복사본이라 손대지 않는다."""
    old_root = os.path.normcase(os.path.abspath(str(OLD_PHOTO_DIR)))
    full = os.path.normcase(os.path.abspath(path))
    if full.startswith(old_root + os.sep):
        return Path(full).parent.name == f"report_{report.id}"
    return True


def _plan_report(db: Session, report: Report) -> list[tuple[str, Path, list]]:
    """(지금 파일, 옮길 자리, [(DB 행, 칸)…]) 목록. 같은 보고서 안에서 이름이 겹치면 _2를 붙인다."""
    base = report_base(db, report)
    rdir = report_dir(db, report)
    plan: list[tuple[str, Path, list]] = []
    used: list[Path] = []

    def add(cur: str, dest: Path, refs: list) -> None:
        if any(same_path(c, cur) for c, _, _ in plan):  # 같은 파일을 두 번 옮기지 않게(예전 PDF 옆 한글 파일 = 예전 한글 받기 파일)
            return
        stem, suffix, n = dest.stem, dest.suffix, 1
        while any(same_path(u, dest) for u in used):
            n += 1
            dest = dest.with_name(f"{stem}_{n}{suffix}")
        used.append(dest)
        plan.append((cur, dest, refs))

    for model, field, label in PHOTO_KINDS:
        for row in db.query(model).filter(model.report_id == report.id).order_by(model.id).all():
            cur = getattr(row, field)
            if not cur or not Path(cur).exists() or not _owned_by(report, cur):
                continue
            if model is PreviousFinding and field == "photo_path" and \
                    db.query(Finding.id).filter(Finding.photo_path == cur).first():
                continue  # 이월 복사본 — 원본 지적사항 쪽에서 옮긴다
            refs = [(row, field)]
            if model is Finding:  # 다음 회차 이전지적사항에 복사된 같은 경로도 같이 고친다
                refs += [(pf, "photo_path") for pf in db.query(PreviousFinding).filter(PreviousFinding.report_id != report.id).all()
                         if pf.photo_path and same_path(pf.photo_path, cur)]
            add(cur, rdir / PHOTO_SUBDIR / f"{base}_{_clean(label(row))}{Path(cur).suffix.lower()}", refs)
    if report.pdf_path and Path(report.pdf_path).exists():
        add(report.pdf_path, rdir / f"{base}.pdf", [(report, "pdf_path")])
        sibling = Path(report.pdf_path).with_suffix(".hwpx")  # 한글 받기용(새 구조에서 이름이 바뀔 때)
        if sibling.exists():
            add(str(sibling), rdir / f"{base}.hwpx", [])
    old_prepared = OLD_REPORTS_DIR / f"report_{report.id}.hwpx"
    if old_prepared.exists():
        add(str(old_prepared), rdir / f"{base}.hwpx", [])
    if report.notify_signature_path and Path(report.notify_signature_path).exists():
        add(report.notify_signature_path, rdir / f"{base}_현장책임자서명{Path(report.notify_signature_path).suffix.lower()}",
            [(report, "notify_signature_path")])
    return [(cur, dest, refs) for cur, dest, refs in plan if not same_path(cur, dest)]


def relocate_report(db: Session, report: Report, dry: bool = False) -> list[tuple[str, str]]:
    """이 보고서 파일들을 규칙대로의 자리·이름으로 옮기고 DB 경로를 고친다(commit은 호출하는 쪽). 옮긴 (전, 후) 목록을 돌려준다.
    파일이 없는 경로는 그대로 둔다. 두 단계(임시 이름 → 새 이름)로 옮겨 서로 이름을 바꾸는 경우(칸 번호 교환)에도 덮어쓰지 않는다.
    같은 드라이브 안 이동이라 수정 시각이 그대로 — PDF 미리보기·작은 사진이 헛되이 다시 만들어지지 않는다."""
    plan = _plan_report(db, report)
    if dry or not plan:
        return [(cur, str(dest)) for cur, dest, _ in plan]
    staged, placed = [], []
    try:
        for cur, dest, refs in plan:
            tmp = Path(cur).with_name(Path(cur).name + ".moving")
            os.replace(cur, tmp)
            staged.append((cur, tmp, dest, refs))
        for cur, tmp, dest, refs in staged:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
            placed.append(cur)
    except OSError:  # 하나라도 실패하면(파일이 열려 있음 등) 전부 원래 자리로 — DB 경로는 아직 안 바꿨으므로 그대로 맞음
        for cur, tmp, dest, _ in staged:
            try:
                os.replace(dest if cur in placed else tmp, cur)
            except OSError:
                pass
        raise
    for cur, tmp, dest, refs in staged:
        for row, field in refs:
            setattr(row, field, str(dest))
    try:
        db.flush()  # DB에 바로 써 본다 — 실패하면(연결 끊김 등) 파일을 원래 자리로 되돌려 DB와 파일이 어긋나지 않게
    except Exception:
        db.rollback()
        for cur, tmp, dest, _ in staged:
            try:
                os.replace(dest, cur)
                _remove_empty_parents(dest.parent)
            except OSError:
                pass
        raise
    for cur, _, _, _ in staged:
        _remove_empty_parents(Path(cur).parent)
    if report.pdf_path:  # 예전 미리보기 자리(PDF 옆 _preview — 새 자리는 _시스템/previews)
        for cur, _, _, _ in staged:
            if cur.lower().endswith(".pdf"):
                shutil.rmtree(Path(cur).with_name(Path(cur).stem + "_preview"), ignore_errors=True)
                _remove_empty_parents(Path(cur).parent)
    return [(cur, str(dest)) for cur, _, dest, _ in staged]


def relocate_site(db: Session, site: Site, dry: bool = False) -> list[tuple[str, str]]:
    """현장의 보고서 전부. 한 보고서가 실패하면(파일이 열려 있음 등) 그 보고서만 예전 이름 그대로 두고 넘어간다 —
    relocate_report가 원래대로 되돌려 DB 경로와 파일은 맞고, 다음에 이름이 바뀌거나 옮기기를 다시 돌리면 맞춰진다."""
    moves: list[tuple[str, str]] = []
    for report in sorted(site.reports, key=lambda r: r.id):
        try:
            moves += relocate_report(db, report, dry)
        except OSError as err:
            print(f"[storage] 보고서 {report.id} 파일 이름 맞추기 실패(예전 이름 그대로 둠): {err}")
    return moves


def relocate_after_site_change(db: Session, site: Site, old_base: str) -> int:
    """현장명·관리번호를 바꾼 뒤 — 이 현장과, 예전·새 이름이 같아 번호가 붙거나 떨어질 수 있는 다른 현장까지 다시 맞춘다."""
    new_base = base_site_name(site)
    if new_base == old_base:
        return 0
    targets = [s for s in db.query(Site).filter(Site.company_id == site.company_id).all()
               if s.id == site.id or base_site_name(s).casefold() in (old_base.casefold(), new_base.casefold())]
    moved = sum(len(relocate_site(db, s)) for s in targets)
    db.commit()
    _move_contract_dir(db, site, old_base)
    return moved


def _move_contract_dir(db: Session, site: Site, old_base: str) -> None:
    """착수계·완수계 폴더(보고서 파일이 아니라 relocate_report가 안 옮김)를 새 현장 폴더로. 안의 파일 이름은 그대로 —
    받기는 "…_착수계.xlsx" 중 최근 것을 찾는다(contract_docs/files.find_out)."""
    new = site_dir(db, site) / CONTRACT_SUBDIR
    for old_name in (old_base, f"{old_base}_{site.id}"):
        old = DATA_DIR / old_name / CONTRACT_SUBDIR
        if old.exists() and old != new and not new.exists():
            try:
                new.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old), str(new))
                _remove_empty_parents(old.parent)
            except OSError as err:
                print(f"[storage] 착수계·완수계 폴더 옮기기 실패(예전 폴더에 둠): {err}")
            return
