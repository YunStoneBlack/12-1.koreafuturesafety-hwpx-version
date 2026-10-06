"""착수계·완수계 붙임 파일(2026-10-06 사용자·형: 산출내역서·완수내역서·기술지도보고서·기술지도 완료증명서는 우리가 쓰는 게 아니라
받아 오는 파일 — 담당자가 올리면 갑지 붙임 순서에 맞춰 합본 PDF 하나로).

- 칸(slot)마다 여러 파일, 올린 순서대로. 올릴 때 바로 PDF로 바꿔 둔다(만들기가 빠르고, 못 바꾸는 파일은 올릴 때 바로 알림):
  PDF 그대로 · 그림은 A4 한 장에 맞춰 · 엑셀·워드 등은 LibreOffice · 한글(hwp·hwpx)은 이 PC 한글(작업 프로그램, hwp_queue).
- 자리: 현장 폴더 착수계·완수계\\붙임\\<칸 이름>\\01_원래이름.pdf
- 엑셀에는 안 넣는다(우리가 채운 시트만). 합본 PDF에서 시트 페이지 사이에 끼운다 — 시트 하나 = PDF 한 장(양식 인쇄 범위가 한 장씩).
"""
from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from server.contract_docs import hwp_queue, to_pdf

# 칸: (kind, 칸 키, 이름, 끼울 자리 = 이 시트 번호(0부터) 뒤). 갑지 붙임 순서 그대로.
SLOTS = {
    "start": [("calc", "산출내역서", 1)],  # 1. 착수계 → 2. 산출내역서 → 3. 현장대리인계
    "done": [("done_list", "완수내역서", 3), ("report", "기술지도보고서", 3), ("finish_cert", "기술지도 완료증명서", 3)],  # 3. 청구서 뒤
}
OFFICE_EXTS = (".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".pptx", ".ppt", ".odt", ".ods", ".rtf")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp")
A4 = (595, 842)  # pt
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def slot_label(kind: str, slot: str) -> str:
    for key, label, _ in SLOTS[kind]:
        if key == slot:
            return label
    raise KeyError(slot)


def slot_dir(out_dir: Path, kind: str, slot: str) -> Path:
    return out_dir / "붙임" / slot_label(kind, slot)


def list_files(out_dir: Path, kind: str, slot: str) -> list[Path]:
    d = slot_dir(out_dir, kind, slot)
    return sorted(d.glob("*.pdf")) if d.exists() else []


def file_info(path: Path) -> dict:
    try:
        with pymupdf.open(path) as doc:
            pages = doc.page_count
    except Exception:  # noqa: BLE001
        pages = 0
    return {"name": path.name, "title": path.stem.split("_", 1)[-1], "pages": pages}


def to_pdf_bytes(data: bytes, filename: str) -> bytes:
    """올린 파일 → PDF 바이트. 못 바꾸면 ValueError(화면에 그대로 보임)."""
    ext = Path(filename).suffix.lower()
    if data[:4] == b"%PDF" or ext == ".pdf":
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.page_count == 0:
                raise ValueError("빈 PDF입니다.")
        return data
    if ext in IMAGE_EXTS:
        return _image_pdf(data)
    if ext in OFFICE_EXTS:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"doc{ext}"
            src.write_bytes(data)
            return to_pdf.office_to_pdf(src, Path(tmp) / "out.pdf").read_bytes()
    if ext in hwp_queue.HWP_EXTS:
        return hwp_queue.convert_via_worker(data, ext)
    raise ValueError("PDF·그림·엑셀·워드·한글 파일만 올릴 수 있습니다.")


def _image_pdf(data: bytes) -> bytes:
    """그림 한 장 → A4 한 장(여백 20pt, 비율 유지, 가로가 길면 가로 A4)."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ValueError("그림 파일을 읽지 못했습니다.") from e
    img.thumbnail((2400, 2400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    w, h = A4 if img.height >= img.width else (A4[1], A4[0])
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    page.insert_image(pymupdf.Rect(20, 20, w - 20, h - 20), stream=buf.getvalue(), keep_proportion=True)
    out = doc.tobytes()
    doc.close()
    return out


def add_file(out_dir: Path, kind: str, slot: str, data: bytes, filename: str) -> Path:
    pdf = to_pdf_bytes(data, filename)
    d = slot_dir(out_dir, kind, slot)
    d.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name[:2]) for p in d.glob("*.pdf") if p.name[:2].isdigit()]
    title = _BAD.sub("_", Path(filename).stem).strip(" .")[:60] or "파일"
    dest = d / f"{(max(nums) + 1 if nums else 1):02d}_{title}.pdf"
    dest.write_bytes(pdf)
    return dest


def remove_file(out_dir: Path, kind: str, slot: str, name: str) -> None:
    d = slot_dir(out_dir, kind, slot)
    target = d / Path(name).name  # 경로 밖으로 못 나가게 이름만
    target.unlink(missing_ok=True)
    try:
        d.rmdir()  # 비면 칸 폴더도
    except OSError:
        pass


def merge(sheet_pdf: Path, out_dir: Path, kind: str, sheet_count: int, dest: Path) -> list[str]:
    """시트 PDF에 붙임 파일을 끼워 합본 PDF(dest). 경고(빠진 칸·시트 장수가 안 맞음)를 돌려준다."""
    warnings: list[str] = []
    base = pymupdf.open(sheet_pdf)
    aligned = base.page_count == sheet_count
    if not aligned:
        warnings.append(f"시트 PDF가 {base.page_count}장이라(시트 {sheet_count}장) 붙임 파일을 맨 뒤에 붙였습니다 — 순서를 확인하세요.")
    out = pymupdf.open()
    by_pos: dict[int, list[Path]] = {}
    for key, label, after in SLOTS[kind]:
        files = list_files(out_dir, kind, key)
        if not files:
            warnings.append(f"{label} — 올린 파일이 없어 빼고 합쳤습니다.")
        by_pos.setdefault(after if aligned else base.page_count - 1, []).extend(files)
    for i in range(base.page_count):
        out.insert_pdf(base, from_page=i, to_page=i)
        for f in by_pos.get(i, []):
            with pymupdf.open(f) as add:
                out.insert_pdf(add)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.pdf")
    out.save(tmp, garbage=3, deflate=True)
    out.close()
    base.close()
    tmp.replace(dest)
    return warnings
