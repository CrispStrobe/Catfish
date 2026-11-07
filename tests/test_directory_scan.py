"""Real filesystem and failure-path tests for the shared single-pass scanner."""

import hashlib
import os
from pathlib import Path
from threading import Event

import pytest

from core.data_structures import ScanConfig
from core.file_index import FileIndex
from core.search_logic import build_destination_index
from utils.file_utils import calculate_file_hash


def test_keeps_hidden_unicode_zero_and_directory_metadata(tmp_path):
    (tmp_path / "parent" / "child").mkdir(parents=True)
    (tmp_path / "empty-folder").mkdir()
    files = {".hidden": b"hidden", "snow-雪.txt": b"snow", "zero.bin": b"", "parent/child/deep.txt": b"deep"}
    for name, content in files.items():
        file = tmp_path / name
        file.write_bytes(content)
        os.utime(file, (1730000000, 1730000000))

    index = FileIndex.scan_directory(tmp_path)
    assert index.is_complete
    assert index.total_files == 4
    assert {e.path.relative_to(tmp_path).as_posix(): (e.size, e.mtime) for e in index.all_files} == {
        name: (len(content), 1730000000) for name, content in files.items()
    }
    assert set(index.directory_mtimes) == {
        tmp_path,
        tmp_path / "parent",
        tmp_path / "parent/child",
        tmp_path / "empty-folder",
    }


def test_scanner_reuses_direntry_metadata_without_restatting_files(tmp_path, monkeypatch):
    file = tmp_path / "example.txt"
    file.write_bytes(b"metadata")
    original = Path.stat

    def forbid_redundant_file_stat(path, *args, **kwargs):
        if path == file:
            raise AssertionError("The scan must reuse DirEntry metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", forbid_redundant_file_stat)
    index = FileIndex.scan_directory(tmp_path)
    assert index.is_complete
    assert [(e.path, e.size) for e in index.all_files] == [(file, 8)]


def test_preserves_file_link_following_but_does_not_descend_directory_links(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "outside.txt"
    target.write_bytes(b"external target")
    (root / "sub").mkdir()
    (root / "sub" / "inside.txt").write_bytes(b"inside")
    try:
        (root / "file-link.txt").symlink_to(target)
        (root / "directory-link").symlink_to(root / "sub", target_is_directory=True)
        (root / "sub" / "cycle").symlink_to(root, target_is_directory=True)
        selected_root = tmp_path / "selected-root-link"
        selected_root.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"This platform cannot create test symlinks: {error}")

    for selected in (root, selected_root):
        index = FileIndex.scan_directory(selected, use_hash=True, hash_algo="sha256")
        assert index.is_complete
        rows = {e.path.relative_to(selected).as_posix(): e for e in index.all_files}
        assert set(rows) == {"file-link.txt", "sub/inside.txt"}
        assert rows["file-link.txt"].size == len(b"external target")
        assert rows["file-link.txt"].hash == hashlib.sha256(b"external target").hexdigest()
        assert set(index.directory_mtimes) == {selected, selected / "sub"}


def test_unreadable_directory_retains_healthy_siblings_and_explicit_error(tmp_path, monkeypatch):
    denied = tmp_path / "denied"
    denied.mkdir()
    (denied / "hidden.txt").write_text("not read")
    (tmp_path / "good.txt").write_text("good")
    original = os.scandir

    def scandir(path):
        if Path(path) == denied:
            raise PermissionError("simulated denial")
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    index = FileIndex.scan_directory(tmp_path)
    assert not index.is_complete
    assert not index.cancelled
    assert [e.path.name for e in index.all_files] == ["good.txt"]
    assert index.scan_error_count == 1
    assert index.scan_errors[0].path == denied
    assert "simulated denial" in index.scan_errors[0].message


def test_partial_scan_never_overwrites_reusable_catalog(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    root.mkdir()
    (root / "good.txt").write_text("good")
    (root / "denied").mkdir()
    catalog = tmp_path / "root_index.caf"
    catalog.write_bytes(b"previous catalog")
    original = os.scandir

    def scandir(path):
        if Path(path) == root / "denied":
            raise PermissionError("simulated denial")
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    index = build_destination_index(ScanConfig(root, [root], False, "md5", True, True))
    assert not index.is_complete
    assert index.total_files == 1
    assert catalog.read_bytes() == b"previous catalog"
    assert "Results are incomplete" in capsys.readouterr().err


def test_cancel_before_scanning_does_not_touch_the_root(tmp_path, monkeypatch):
    cancel = Event()
    cancel.set()
    original = Path.stat

    def unexpected(path, *args, **kwargs):
        if path == tmp_path:
            raise AssertionError("Cancelled scan must not read metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", unexpected)
    index = FileIndex.scan_directory(tmp_path, cancel_event=cancel)
    assert index.cancelled
    assert not index.is_complete
    assert index.total_files == 0


def test_cancel_mid_scan_keeps_only_completed_entries(tmp_path):
    for i in range(25):
        (tmp_path / f"{i}.txt").write_text(str(i))
    cancel = Event()

    def progress(count, path):
        if count == 1:
            cancel.set()

    index = FileIndex.scan_directory(tmp_path, cancel_event=cancel, progress_callback=progress, progress_interval=0)
    assert index.cancelled
    assert index.total_files == 1
    assert len(index.all_files) == 1
    assert sum(map(len, index.size_index.values())) == 1


@pytest.mark.parametrize("algorithm", ["md5", "sha1", "sha256"])
def test_chunked_hash_reads_every_byte_and_handles_empty_files(tmp_path, algorithm):
    content = b"different bytes\x00\xff" * 140000
    file = tmp_path / "data.bin"
    file.write_bytes(content)
    assert calculate_file_hash(file, algorithm) == hashlib.new(algorithm, content).hexdigest()
    empty = tmp_path / "empty"
    empty.touch()
    assert calculate_file_hash(empty, algorithm) == hashlib.new(algorithm, b"").hexdigest()


def test_cancel_during_hash_never_indexes_a_partial_digest(tmp_path, monkeypatch):
    (tmp_path / "large.bin").write_bytes(b"x" * (3 * 1024 * 1024))
    cancel = Event()
    original = hashlib.new

    class CancellingHash:
        def __init__(self):
            self.hash = original("sha256")

        def update(self, chunk):
            self.hash.update(chunk)
            cancel.set()

        def hexdigest(self):
            return self.hash.hexdigest()

    monkeypatch.setattr(hashlib, "new", lambda _: CancellingHash())
    index = FileIndex.scan_directory(tmp_path, True, "sha256", cancel_event=cancel)
    assert index.cancelled
    assert index.total_files == 0
    assert not index.hash_index
    assert not index.scan_errors


def test_failed_hash_is_reported_and_not_mistaken_for_zero_byte_data(tmp_path, monkeypatch):
    (tmp_path / "unreadable.bin").write_text("unreadable")
    monkeypatch.setattr("core.file_index.calculate_file_hash", lambda *args, **kwargs: "")
    index = FileIndex.scan_directory(tmp_path, True, "sha256")
    assert not index.is_complete
    assert index.scan_error_count == 1
    assert index.total_files == 0


def test_search_index_is_invalidated_when_a_file_is_added(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    index = FileIndex.scan_directory(tmp_path)
    index.build_optimized_indices()
    assert index.is_optimized
    (tmp_path / "b.txt").write_text("bb")
    index.add_file(tmp_path / "b.txt")
    assert not index.is_optimized
    index.build_optimized_indices()
    assert [name for name, _ in index.prefix_index] == ["a.txt", "b.txt"]
