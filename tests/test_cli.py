"""Tests for CLI entry points in main.py"""

import subprocess
import sys


class TestCLIHelp:
    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "search" in result.stdout
        assert "find-dupes" in result.stdout

    def test_search_help(self):
        result = subprocess.run(
            [sys.executable, "main.py", "search", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "pattern" in result.stdout

    def test_find_dupes_help(self):
        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "source" in result.stdout
