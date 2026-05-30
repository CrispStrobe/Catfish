"""Tests for core/config.py"""

import json
from unittest.mock import patch

import pytest

from core.config import Config


@pytest.fixture
def config_file(tmp_path):
    """Provide a temporary config file path."""
    return tmp_path / ".test_config.json"


@pytest.fixture
def config(config_file):
    """Create a Config instance with a temporary config file."""
    with patch.object(Config, "__init__", lambda self: None):
        cfg = Config.__new__(Config)
        cfg.config_file = config_file
        cfg.default_config = {
            "language": "en",
            "default_hash_algo": "md5",
            "auto_load_indices": True,
            "index_search_locations": [],
            "window_geometry": None,
            "active_indices": [],
        }
        cfg.config = cfg.default_config.copy()
    return cfg


class TestConfig:
    def test_get_default(self, config):
        assert config.get("language") == "en"

    def test_get_missing_key(self, config):
        assert config.get("nonexistent", "fallback") == "fallback"

    def test_set_and_get(self, config):
        config.set("language", "de")
        assert config.get("language") == "de"

    def test_save_and_load(self, config):
        config.set("language", "de")
        config.save_config()

        assert config.config_file.exists()

        # Load it back
        data = json.loads(config.config_file.read_text())
        assert data["language"] == "de"

    def test_index_active_default_true(self, config):
        # When no active_indices key, default is True
        config.config.pop("active_indices", None)
        assert config.is_index_active("/some/path.caf") is True

    def test_set_index_active(self, config):
        config.set_index_active("/test.caf", True)
        assert config.is_index_active("/test.caf") is True

        config.set_index_active("/test.caf", False)
        assert config.is_index_active("/test.caf") is False

    def test_get_active_indices(self, config):
        config.set_index_active("/a.caf", True)
        config.set_index_active("/b.caf", True)
        active = config.get_active_indices()
        assert "/a.caf" in active
        assert "/b.caf" in active

    def test_load_corrupt_config(self, config):
        config.config_file.write_text("not json!")
        loaded = config.load_config()
        assert loaded == config.default_config
