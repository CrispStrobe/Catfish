"""Shared test fixtures."""

import pytest


@pytest.fixture
def tmp_tree(tmp_path):
    """Create a temporary file tree for testing.

    Structure:
        root/
            file_a.txt  (13 bytes: "hello world\\n")
            file_b.jpg  (5 bytes:  "image")
            sub/
                file_c.txt  (13 bytes, same content as file_a.txt)
                deep/
                    file_d.log  (4 bytes: "data")
    """
    (tmp_path / "file_a.txt").write_text("hello world\n")
    (tmp_path / "file_b.jpg").write_bytes(b"image")

    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file_c.txt").write_text("hello world\n")

    deep = sub / "deep"
    deep.mkdir()
    (deep / "file_d.log").write_bytes(b"data")

    return tmp_path


@pytest.fixture
def source_and_dest(tmp_path):
    """Create source and destination directories with known duplicates.

    source/
        unique.txt    (6 bytes: "unique")
        shared.txt    (6 bytes: "shared")
    dest/
        shared.txt    (6 bytes: "shared")  -- duplicate
        other.bin     (3 bytes: "abc")
    """
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()
    dst.mkdir()

    (src / "unique.txt").write_text("unique")
    (src / "shared.txt").write_text("shared")
    (dst / "shared.txt").write_text("shared")
    (dst / "other.bin").write_bytes(b"abc")

    return src, dst
