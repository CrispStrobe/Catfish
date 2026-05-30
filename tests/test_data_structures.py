"""Tests for core/data_structures.py"""

from pathlib import Path

from core.data_structures import (
    DuplicateMatch,
    FileEntry,
    IndexInfo,
    ScanConfig,
    SearchCriteria,
    SearchResult,
)


class TestFileEntry:
    def test_creation(self):
        e = FileEntry(Path("/tmp/a.txt"), 100, 1700000000, "abc123")
        assert e.path == Path("/tmp/a.txt")
        assert e.size == 100
        assert e.mtime == 1700000000
        assert e.hash == "abc123"

    def test_default_hash(self):
        e = FileEntry(Path("/tmp/b.txt"), 50, 0)
        assert e.hash == ""


class TestSearchCriteria:
    def test_defaults(self):
        c = SearchCriteria()
        assert c.name_pattern is None
        assert c.size_min is None
        assert c.size_max is None
        assert c.date_min is None
        assert c.date_max is None

    def test_with_values(self):
        c = SearchCriteria(name_pattern="*.txt", size_min=100)
        assert c.name_pattern == "*.txt"
        assert c.size_min == 100


class TestSearchResult:
    def test_creation(self):
        r = SearchResult(Path("/a"), 10, 999)
        assert r.path == Path("/a")
        assert r.size == 10
        assert r.hash == ""


class TestScanConfig:
    def test_creation(self):
        cfg = ScanConfig(
            source_path=Path("/src"),
            dest_paths=[Path("/dst1"), Path("/dst2")],
            use_hash=True,
            hash_algo="sha256",
            reuse_indices=True,
            recreate_indices=False,
        )
        assert cfg.source_path == Path("/src")
        assert len(cfg.dest_paths) == 2
        assert cfg.hash_algo == "sha256"


class TestDuplicateMatch:
    def test_creation(self):
        entries = [FileEntry(Path("/d/dup.txt"), 100, 0)]
        m = DuplicateMatch(source_file=Path("/s/file.txt"), destinations=entries)
        assert m.source_file == Path("/s/file.txt")
        assert len(m.destinations) == 1


class TestIndexInfo:
    def test_creation(self):
        from datetime import datetime

        info = IndexInfo(
            path=Path("/idx.caf"),
            root_path=Path("/data"),
            file_count=42,
            total_size=1024,
            created_date=datetime(2024, 1, 1),
            hash_method="MD5",
        )
        assert info.file_count == 42
        assert info.hash_method == "MD5"
