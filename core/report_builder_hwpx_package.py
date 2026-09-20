"""저장이 끝난 hwpx 패키지에서 우리가 넣은 이미지의 등록 방식을 실제 한글이 저장하는 관례로 맞춘다.

python-hwpx의 `add_image()`는 한글 정품 파일과 다르게 이미지를 등록한다 — JPG를 `image/jpeg`로
선언하고, ID를 `BIN0001` 식으로 짓고, 정품 파일엔 없는 헤더 `<hh:binDataList>`에 새 이미지만
적어 넣는다. 한글 2020은 이걸 관대하게 봐주지만 2018/2024에서는 우리가 넣은 사진·서명·도장만
"빈 그림틀"로 나오는 현상이 실사용에서 확인됐다(2026-09). 이 PC에 있던 정품 hwpx 4개(한글
빌드 10.x/11.x/12.x)는 전부 JPG=`image/jpg`, PNG=`image/png`, ID=`image1`·`image2`…, 헤더에
`binDataList` 없음으로 동일해서, 저장 직후 그 방식으로 되돌린다.
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

_MANIFEST_PATH = "Contents/content.hpf"
_HEADER_PATH = "Contents/header.xml"
_SECTION_NAME = re.compile(r"Contents/section\d+\.xml")
_MANIFEST_ITEM = re.compile(r"<opf:item\b[^>]*/>")
_BIN_DATA_LIST = re.compile(r"<hh:binDataList\b[^>]*?(?:/>|>.*?</hh:binDataList>)", re.S)


def normalize_image_packaging(hwpx_path: str | Path) -> int:
    """`hwpx_path` 파일을 제자리에서 고치고, 이름을 바꾼 이미지 개수를 돌려준다."""
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as zin:
        infos = zin.infolist()
        data = {info.filename: zin.read(info.filename) for info in infos}

    manifest = data[_MANIFEST_PATH].decode("utf-8")

    used_numbers = {int(n) for n in re.findall(r'\bid="image(\d+)"', manifest)}
    for name in data:
        stem = re.fullmatch(r"BinData/image(\d+)\.\w+", name)
        if stem:
            used_numbers.add(int(stem.group(1)))
    next_number = max(used_numbers, default=0) + 1

    renames: dict[str, tuple[str, str, str]] = {}
    for tag in _MANIFEST_ITEM.findall(manifest):
        item_id = re.search(r'\bid="(BIN\d+)"', tag)
        href = re.search(r'\bhref="(BinData/[^"]+)"', tag)
        if not item_id or not href:
            continue
        new_id = f"image{next_number}"
        next_number += 1
        new_href = f"BinData/{new_id}{Path(href.group(1)).suffix}"
        renames[item_id.group(1)] = (new_id, href.group(1), new_href)

    for old_id, (new_id, old_href, new_href) in renames.items():
        manifest = manifest.replace(f'id="{old_id}"', f'id="{new_id}"').replace(f'href="{old_href}"', f'href="{new_href}"')
    manifest = manifest.replace('media-type="image/jpeg"', 'media-type="image/jpg"')
    data[_MANIFEST_PATH] = manifest.encode("utf-8")

    header = data[_HEADER_PATH].decode("utf-8")
    data[_HEADER_PATH] = _BIN_DATA_LIST.sub("", header).encode("utf-8")

    for name in data:
        if _SECTION_NAME.fullmatch(name):
            section = data[name].decode("utf-8")
            for old_id, (new_id, _old_href, _new_href) in renames.items():
                section = section.replace(f'binaryItemIDRef="{old_id}"', f'binaryItemIDRef="{new_id}"')
            data[name] = section.encode("utf-8")

    renamed_entries = {old_href: new_href for _new_id, old_href, new_href in renames.values()}
    tmp_path = hwpx_path.with_name(hwpx_path.name + ".tmp")
    with zipfile.ZipFile(tmp_path, "w") as zout:
        for info in infos:
            out_info = zipfile.ZipInfo(renamed_entries.get(info.filename, info.filename), date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            zout.writestr(out_info, data[info.filename])
    os.replace(tmp_path, hwpx_path)
    return len(renames)
