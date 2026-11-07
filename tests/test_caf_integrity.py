"""CAF compatibility, topology and failure safety without a live UI."""

import io
import os
import shutil
import struct
from pathlib import PurePosixPath, PureWindowsPath
from threading import Event

import pytest

from core.data_structures import FileEntry
from core.file_index import FileIndex


def _independent_caf(version, entries, device="/offline/archive"):
    """Build fixture bytes independently of the production CAF writer."""
    data = io.BytesIO()
    data.write(struct.pack("<LhL", 3500410407, version, 1730000000))
    data.write(device.encode("latin-1") + b"\0Volume\0Alias\0")
    data.write(struct.pack("<L", 0))
    data.write(b"Fixture\0")
    data.write(struct.pack("<fh", 0, 0))
    data.write(struct.pack("<l", 1))
    data.write(b"\0")
    data.write(struct.pack("<ld", 0, 0))
    data.write(struct.pack("<l", len(entries)))
    fmt = "<LlH" if version <= 6 else ("<LqH" if version == 7 else "<LqL")
    for mtime, size, parent, name in entries:
        data.write(struct.pack(fmt, mtime, size, parent))
        data.write(name.encode("latin-1") + b"\0")
    return data.getvalue()


def _index_with_entry(root, name="good.txt", size=0, mtime=1730000000):
    index = FileIndex(root)
    entry = FileEntry(root / name, size, mtime, "")
    index.size_index[size].append(entry)
    index.all_files.append(entry)
    index.total_files = 1
    return index


def _rows(index):
    return {e.path.relative_to(index.root_path).as_posix(): (e.size, e.mtime) for e in index.all_files}


def test_deep_ancestors_empty_folders_zero_and_latin1_roundtrip_offline(tmp_path):
    root = tmp_path / "source"
    (root / "first" / "second").mkdir(parents=True)
    (root / "empty" / "also-empty").mkdir(parents=True)
    for name, content in {"first/second/café.txt": b"accent", ".hidden": b"", "space name.txt": b"space"}.items():
        (root / name).write_bytes(content)
        os.utime(root / name, (1730000000, 1730000000))
    for directory in (root / "first", root / "first/second", root / "empty", root / "empty/also-empty"):
        os.utime(directory, (1730000001, 1730000001))
    index = FileIndex.scan_directory(root, True, "sha256")
    expected = _rows(index)
    directory_mtimes = {
        p.relative_to(root).as_posix(): mtime for p, mtime in index.directory_mtimes.items() if p != root
    }
    catalog = tmp_path / "saved.caf"
    index.save_to_caf(catalog)
    shutil.rmtree(root)

    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert loaded is not None
    assert _rows(loaded) == expected
    assert {
        p.relative_to(loaded.root_path).as_posix(): m
        for p, m in loaded.directory_mtimes.items()
        if p != loaded.root_path
    } == directory_mtimes
    assert all(not e.hash for e in loaded.all_files)  # CAF has no hash field.
    saved_again = tmp_path / "saved-again.caf"
    loaded.save_to_caf(saved_again)
    reloaded = FileIndex.load_from_caf(saved_again, False, "md5")
    assert _rows(reloaded) == expected
    assert reloaded.directory_mtimes == loaded.directory_mtimes


def test_add_file_callers_also_keep_all_ancestors(tmp_path):
    root = tmp_path / "root"
    (root / "a" / "b" / "c").mkdir(parents=True)
    file = root / "a/b/c/deep.txt"
    file.write_bytes(b"deep")
    index = FileIndex(root)
    index.add_file(file)
    catalog = tmp_path / "deep.caf"
    index.save_to_caf(catalog)
    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert _rows(loaded) == _rows(index)
    assert {p.relative_to(loaded.root_path).as_posix() for p in loaded.directory_mtimes} == {".", "a", "a/b", "a/b/c"}


@pytest.mark.parametrize("version", [7, 8])
def test_independent_modern_zero_bytes_and_forward_directory_references(tmp_path, version):
    catalog = tmp_path / "modern.caf"
    catalog.write_bytes(_independent_caf(version, [(11, -2, 1, "child"), (12, 0, 2, "zero"), (13, -1, 0, "parent")]))
    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert loaded is not None
    assert _rows(loaded) == {"parent/child/zero": (0, 12)}
    assert loaded.directory_mtimes[loaded.root_path / "parent/child"] == 11


def test_legacy_v6_keeps_its_unknown_zero_size_convention(tmp_path):
    catalog = tmp_path / "legacy.caf"
    catalog.write_bytes(_independent_caf(6, [(11, 0, 0, "parent"), (12, 0, 1, "unknown")]))
    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert loaded is not None
    assert _rows(loaded) == {"parent/unknown": (1024, 12)}


def test_whitespace_only_caf_filename_is_retained(tmp_path):
    catalog = tmp_path / "spaces.caf"
    catalog.write_bytes(_independent_caf(8, [(12, 0, 0, " ")]))
    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert _rows(loaded) == {" ": (0, 12)}


def test_foreign_windows_paths_can_be_saved_again_without_disk_access(tmp_path):
    catalog = tmp_path / "windows.caf"
    catalog.write_bytes(_independent_caf(8, [(11, -1, 0, "café"), (12, 0, 1, "zero")], r"Z:\offline"))
    loaded = FileIndex.load_from_caf(catalog, False, "md5")
    assert isinstance(loaded.root_path, PureWindowsPath)
    copy = tmp_path / "windows-copy.caf"
    loaded.save_to_caf(copy)
    assert _rows(FileIndex.load_from_caf(copy, False, "md5")) == _rows(loaded)


@pytest.mark.parametrize("name", ["snow-雪.txt", "bad\x00name", "back\\slash.txt", "C:escape.txt"])
def test_unsupported_names_reject_without_replacing_existing_catalog(tmp_path, name):
    catalog = tmp_path / "old.caf"
    catalog.write_bytes(b"previous good catalog")
    index = _index_with_entry(PurePosixPath(tmp_path.as_posix()), name)
    with pytest.raises(ValueError):
        index.save_to_caf(catalog)
    assert catalog.read_bytes() == b"previous good catalog"
    assert not list(tmp_path.glob(".old.caf.*.tmp"))


def test_unsupported_root_path_rejects_before_replacement(tmp_path):
    catalog = tmp_path / "old.caf"
    catalog.write_bytes(b"previous")
    index = _index_with_entry(tmp_path / "雪")
    with pytest.raises(ValueError, match="Latin-1"):
        index.save_to_caf(catalog)
    assert catalog.read_bytes() == b"previous"


@pytest.mark.parametrize("size,mtime", [(-1, 1), (2**63, 1), (0, -1), (0, 2**32)])
def test_unrepresentable_metadata_never_replaces_catalog(tmp_path, size, mtime):
    catalog = tmp_path / "old.caf"
    catalog.write_bytes(b"previous")
    index = _index_with_entry(tmp_path, size=size, mtime=mtime)
    with pytest.raises(ValueError):
        index.save_to_caf(catalog)
    assert catalog.read_bytes() == b"previous"


def test_outside_root_path_is_not_silently_dropped(tmp_path):
    index = _index_with_entry(tmp_path / "root", "../outside")
    with pytest.raises(ValueError):
        index.save_to_caf(tmp_path / "outside.caf")
    assert not (tmp_path / "outside.caf").exists()


@pytest.mark.parametrize("names", [("a", "a"), ("a", "a/b"), ("a/b", "a")])
def test_writer_rejects_duplicate_paths_and_file_folder_collisions_before_replacement(tmp_path, names):
    catalog = tmp_path / "previous.caf"
    catalog.write_bytes(b"previous")
    index = FileIndex(tmp_path)
    for name in names:
        entry = FileEntry(tmp_path / name, 1, 1730000000, "")
        index.size_index[1].append(entry)
        index.all_files.append(entry)
        index.total_files += 1
    with pytest.raises(ValueError, match=r"Duplicate|both a file and a folder"):
        index.save_to_caf(catalog)
    assert catalog.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".previous.caf.*.tmp"))


@pytest.mark.parametrize("failure", ["write", "replace", "cancel"])
def test_atomic_save_preserves_previous_catalog_and_cleans_temp_on_failure(tmp_path, monkeypatch, failure):
    catalog = tmp_path / "old.caf"
    catalog.write_bytes(b"previous good catalog")
    index = _index_with_entry(tmp_path)
    cancel = Event()
    original = index._write_caf_stream

    def fail_during_write(buffer, elements, info, event):
        original(buffer, elements, info, event)
        if failure == "write":
            raise OSError("simulated write failure")
        if failure == "cancel":
            cancel.set()

    def fail_replace(*args):
        raise PermissionError("simulated replacement failure")

    monkeypatch.setattr(index, "_write_caf_stream", fail_during_write)
    if failure == "replace":
        monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        index.save_to_caf(catalog, cancel_event=cancel)
    assert catalog.read_bytes() == b"previous good catalog"
    assert not list(tmp_path.glob(".old.caf.*.tmp"))


def test_incomplete_scan_cannot_be_saved_as_complete_catalog(tmp_path):
    index = _index_with_entry(tmp_path)
    index._record_scan_error(tmp_path / "denied", "permission denied")
    with pytest.raises(ValueError, match="incomplete"):
        index.save_to_caf(tmp_path / "bad.caf")
    assert not (tmp_path / "bad.caf").exists()


@pytest.mark.parametrize("remove", [1, 5, 20, 40])
def test_truncated_catalog_never_returns_a_successful_partial_index(tmp_path, remove):
    catalog = tmp_path / "truncated.caf"
    data = _independent_caf(8, [(11, 10, 0, "first"), (12, 20, 0, "second")])
    catalog.write_bytes(data[:-remove])
    assert FileIndex.load_from_caf(catalog, False, "md5") is None


@pytest.mark.parametrize(
    "entries",
    [
        [(11, 10, 99, "orphan")],
        [(11, -1, 2, "a"), (12, -2, 1, "b")],
        [(11, -1, 0, "a"), (12, -1, 0, "b")],
        [(11, 0, 0, "../escape")],
        [(11, 0, 0, "C:escape")],
        [(11, 1, 0, "same"), (12, 2, 0, "same")],
        [(11, -1, 0, "same"), (12, -2, 0, "same")],
        [(11, -1, 0, "a"), (12, 1, 0, "a"), (13, 1, 1, "b")],
        [(12, 1, 0, "a"), (13, 1, 1, "b"), (11, -1, 0, "a")],
    ],
)
def test_invalid_parent_or_path_rejects_the_whole_catalog(tmp_path, entries):
    catalog = tmp_path / "invalid.caf"
    catalog.write_bytes(_independent_caf(8, entries))
    assert FileIndex.load_from_caf(catalog, False, "md5") is None


def test_loading_for_a_merge_can_skip_the_redundant_sorts(tmp_path):
    catalog = tmp_path / "good.caf"
    catalog.write_bytes(_independent_caf(8, [(11, 0, 0, "zero")]))
    index = FileIndex.load_from_caf(catalog, False, "md5", build_search_indices=False)
    assert not index.is_optimized
    assert index.total_files == 1
    index.build_optimized_indices()
    assert index.is_optimized
