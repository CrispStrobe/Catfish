"""Independent CAF records distinguish modern zero bytes from legacy unknowns."""
import struct

import pytest

from core.file_index import FileIndex


@pytest.mark.parametrize("version,zero_size", [(6, 1024), (7, 0), (8, 0)])
def test_zero_size_record_by_format_version(tmp_path, version, zero_size):
    header = struct.pack("<IhI", 3 * FileIndex.ulModus + FileIndex.ulMagicBase, version, 1700000000)
    header += b"/fixture\0fixture\0fixture\0" + struct.pack("<I", 0)
    header += b"test\0" + struct.pack("<fh", 0.0, 0)
    info = struct.pack("<i", 1) + b"\0" + struct.pack("<id", 2, 1.0)
    fmt = "<IiH" if version <= 6 else "<IqH" if version == 7 else "<IqI"
    records = struct.pack("<i", 2)
    records += struct.pack(fmt, 1700000000, 0, 0) + b"empty\0"
    records += struct.pack(fmt, 1700000000, 1, 0) + b"one\0"
    path = tmp_path / "fixture.caf"
    path.write_bytes(header + info + records)
    loaded = FileIndex.load_from_caf(path, False, "md5")
    assert loaded is not None
    assert {entry.path.name: entry.size for entry in loaded.all_files} == {"empty": zero_size, "one": 1}
