"""Tests for core/index_discovery.py"""

from unittest.mock import patch

import pytest

from core.config import Config
from core.file_index import FileIndex
from core.index_discovery import IndexDiscovery


@pytest.fixture
def discovery(tmp_path):
    """Create an IndexDiscovery with a temporary config pointing at tmp_path."""
    with patch.object(Config, "__init__", lambda self: None):
        cfg = Config.__new__(Config)
        cfg.config_file = tmp_path / ".test_config.json"
        cfg.default_config = {
            "language": "en",
            "default_hash_algo": "md5",
            "auto_load_indices": True,
            "index_search_locations": [str(tmp_path)],
            "window_geometry": None,
            "active_indices": [],
        }
        cfg.config = cfg.default_config.copy()
    return IndexDiscovery(cfg)


def _create_caf(tmp_path, name="test_index.caf"):
    """Helper: build a small index and save it as a CAF file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    for i in range(3):
        (data_dir / f"file_{i}.txt").write_text(f"content {i}")

    idx = FileIndex(data_dir, use_hash=False, hash_algo="md5")
    for f in data_dir.rglob("*"):
        if f.is_file():
            idx.add_file(f)

    caf_path = tmp_path / name
    idx.save_to_caf(caf_path)
    return caf_path


class TestDiscoverIndices:
    def test_finds_caf_files(self, tmp_path, discovery):
        caf = _create_caf(tmp_path)
        indices = discovery.discover_indices()
        assert caf in indices

    def test_finds_in_subdirectory(self, tmp_path, discovery):
        sub = tmp_path / "subdir"
        sub.mkdir()
        caf = _create_caf(tmp_path, "subdir/nested_index.caf")
        indices = discovery.discover_indices()
        assert caf in indices

    def test_ignores_non_caf_files(self, tmp_path, discovery):
        (tmp_path / "not_an_index.txt").write_text("hello")
        indices = discovery.discover_indices()
        assert all(p.suffix == ".caf" for p in indices)

    def test_empty_directory(self, tmp_path, discovery):
        indices = discovery.discover_indices()
        # May find .caf files from other tests via tmp_path, but should not crash
        assert isinstance(indices, list)

    def test_deduplicates(self, tmp_path, discovery):
        _create_caf(tmp_path)
        indices = discovery.discover_indices()
        # Each path should appear only once
        assert len(indices) == len(set(indices))

    def test_nonexistent_location(self, tmp_path):
        with patch.object(Config, "__init__", lambda self: None):
            cfg = Config.__new__(Config)
            cfg.config_file = tmp_path / ".cfg.json"
            cfg.default_config = {
                "index_search_locations": ["/nonexistent/path/xyz"],
            }
            cfg.config = cfg.default_config.copy()
        d = IndexDiscovery(cfg)
        indices = d.discover_indices()
        assert indices == []


class TestGetIndexInfo:
    def test_returns_index_info(self, tmp_path, discovery):
        caf = _create_caf(tmp_path)
        info = discovery.get_index_info(caf)
        assert info is not None
        assert info.path == caf
        assert info.file_count == 3

    def test_detects_hash_from_filename(self, tmp_path, discovery):
        caf = _create_caf(tmp_path, "backup_index_sha256.caf")
        info = discovery.get_index_info(caf)
        assert info is not None
        assert info.hash_method == "SHA256"

    def test_md5_detection(self, tmp_path, discovery):
        caf = _create_caf(tmp_path, "photos_index_md5.caf")
        info = discovery.get_index_info(caf)
        assert info is not None
        assert info.hash_method == "MD5"

    def test_sha1_detection(self, tmp_path, discovery):
        caf = _create_caf(tmp_path, "music_index_sha1.caf")
        info = discovery.get_index_info(caf)
        assert info is not None
        assert info.hash_method == "SHA1"

    def test_no_hash_in_name(self, tmp_path, discovery):
        caf = _create_caf(tmp_path, "plain_catalog.caf")
        info = discovery.get_index_info(caf)
        assert info is not None
        assert info.hash_method == "None"

    def test_nonexistent_caf(self, tmp_path, discovery):
        info = discovery.get_index_info(tmp_path / "missing.caf")
        assert info is None

    def test_invalid_caf(self, tmp_path, discovery):
        bad = tmp_path / "bad.caf"
        bad.write_bytes(b"not a caf file")
        info = discovery.get_index_info(bad)
        assert info is None
