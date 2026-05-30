"""Tests for utils/platform_utils.py"""

import platform
from pathlib import Path

from utils.platform_utils import (
    FileOperationError,
    calculate_window_geometry,
    get_platform_info,
    make_script_executable,
)


class TestGetPlatformInfo:
    def test_returns_dict(self):
        info = get_platform_info()
        assert isinstance(info, dict)
        assert "name" in info
        assert "script_ext" in info
        assert "delete_cmd" in info
        assert "path_quote" in info
        assert "script_header" in info

    def test_script_ext(self):
        info = get_platform_info()
        if platform.system() == "Windows":
            assert info["script_ext"] == ".bat"
        else:
            assert info["script_ext"] == ".sh"

    def test_path_quote(self):
        info = get_platform_info()
        quoted = info["path_quote"](Path("/some/path"))
        assert isinstance(quoted, str)
        assert "path" in quoted


class TestCalculateWindowGeometry:
    def test_geometry_format(self):
        geom = calculate_window_geometry(1920, 1080)
        # Format should be WxH+X+Y
        assert "x" in geom
        assert "+" in geom

    def test_small_screen(self):
        geom = calculate_window_geometry(800, 600)
        # Should still produce valid geometry
        parts = geom.split("+")
        assert len(parts) == 3

    def test_large_screen(self):
        geom = calculate_window_geometry(3840, 2160)
        w, rest = geom.split("x")
        rest.split("+")[0]
        # Width capped at 1400
        assert int(w) <= 1400


class TestMakeScriptExecutable:
    def test_makes_executable(self, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text("#!/bin/bash\necho hello")

        if platform.system() != "Windows":
            make_script_executable(script)
            import stat

            mode = script.stat().st_mode
            assert mode & stat.S_IEXEC


class TestFileOperationError:
    def test_is_exception(self):
        err = FileOperationError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"
