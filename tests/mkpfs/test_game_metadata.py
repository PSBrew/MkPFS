from __future__ import annotations

import json
from pathlib import Path

from mkpfs import consts
from mkpfs.exfat_writer import write_exfat_image
from mkpfs.game_metadata import detect_region_from_content_id, read_game_metadata
from mkpfs.pfs import build_pfs_stream_single_file

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfeA\xe2&\xb3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_game_source(root: Path) -> Path:
    source = root / "game"
    sce_sys = source / "sce_sys"
    sce_sys.mkdir(parents=True)
    (sce_sys / "param.json").write_text(
        json.dumps(
            {
                "contentId": "UP9000-PPSA99999_00-ABCDEFGHIJKLMNOP",
                "titleId": "PPSA99999",
                "contentVersion": "01.234",
                "localizedParameters": {"en-US": {"titleName": "Spectrum Test Game"}},
            }
        ),
        encoding="utf-8",
    )
    (sce_sys / "icon0.png").write_bytes(_PNG_BYTES)
    (source / "fakelib").mkdir()
    (source / "fakelib" / "libSceAmpr.sprx").write_bytes(b"apr-emu")
    (source / "eboot.bin").write_bytes(b"BOOT")
    return source


def test_reads_game_metadata_from_exfat_image(tmp_path: Path) -> None:
    source = _make_game_source(tmp_path)
    image = tmp_path / "game.exfat"
    write_exfat_image(source, image)

    metadata = read_game_metadata(image)

    assert metadata.error == ""
    assert metadata.package_type == "EXFAT"
    assert metadata.game_title == "Spectrum Test Game"
    assert metadata.title_id == "PPSA99999"
    assert metadata.content_id == "UP9000-PPSA99999_00-ABCDEFGHIJKLMNOP"
    assert metadata.version == "01.234"
    assert metadata.region == "USA"
    assert metadata.has_apr_emu is True
    assert metadata.icon_bytes == _PNG_BYTES
    assert metadata.size_display.endswith(("KB", "MB"))


def test_reads_game_metadata_from_wrapped_ffpfsc_image(tmp_path: Path) -> None:
    source = _make_game_source(tmp_path)
    exfat_image = tmp_path / "inner.exfat"
    output = tmp_path / "wrapped.ffpfsc"
    write_exfat_image(source, exfat_image)
    build_pfs_stream_single_file(
        source_file=exfat_image,
        output_path=output,
        block_size=65536,
        pfs_version=consts.PFS_VERSION_PS5,
        case_insensitive=True,
        zlib_level=7,
        threshold_gain=0,
        min_file_gain=0,
        min_compress_size=0,
        cpu_count=1,
        compress=True,
    )

    metadata = read_game_metadata(output)

    assert metadata.error == ""
    assert metadata.package_type.startswith("FFPFSC")
    assert metadata.game_title == "Spectrum Test Game"
    assert metadata.title_id == "PPSA99999"
    assert metadata.content_id == "UP9000-PPSA99999_00-ABCDEFGHIJKLMNOP"
    assert metadata.has_apr_emu is True
    assert metadata.icon_bytes == _PNG_BYTES


def test_unknown_file_uses_safe_fallbacks(tmp_path: Path) -> None:
    path = tmp_path / "Random.PPSA12345.bin"
    path.write_bytes(b"not a package")

    metadata = read_game_metadata(path)

    assert metadata.title_id == "PPSA12345"
    assert metadata.content_id == "PPSA12345"
    assert metadata.package_type == "BIN"
    assert metadata.size_display == "13 B"


def test_reads_ffpkg_title_and_apr_emu_from_header_regions(tmp_path: Path) -> None:
    path = tmp_path / "game.ffpkg"
    data = bytearray(0x39000)
    data[0xFFEC : 0xFFF0] = b"\x19\x01\x54\x19"
    name = b"PPSA54321.complete"
    data[0x38000 : 0x38008] = b"\x01\x00\x00\x00\x20\x00\x01" + bytes([len(name)])
    data[0x38008 : 0x38008 + len(name)] = name
    data[0x20000 : 0x20000 + len(b"fakelib/libSceAmpr.sprx")] = b"fakelib/libSceAmpr.sprx"
    path.write_bytes(data)

    metadata = read_game_metadata(path)

    assert metadata.error == ""
    assert metadata.package_type == "FFPKG"
    assert metadata.title_id == "PPSA54321"
    assert metadata.content_id == "PPSA54321"
    assert metadata.has_apr_emu is True


def test_detects_region_from_content_id_prefix() -> None:
    assert detect_region_from_content_id("UP9000-PPSA00000_00-ABCDE") == "USA"
    assert detect_region_from_content_id("EP9000-PPSA00000_00-ABCDE") == "EUR"
    assert detect_region_from_content_id("-") == ""
