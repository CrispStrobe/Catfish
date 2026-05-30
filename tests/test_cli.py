"""Tests for CLI entry points in main.py"""

import json
import subprocess
import sys


def _parse_json_stdout(stdout: str):
    """Parse JSON from CLI stdout. Diagnostic prints now go to stderr, so stdout should be clean."""
    return json.loads(stdout)


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

    def test_interactive_help(self):
        result = subprocess.run(
            [sys.executable, "main.py", "interactive", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestCLIDupes:
    def test_find_dupes_text_output(self, tmp_path):
        """End-to-end: find duplicates via CLI with text output."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        content = "duplicate content here"
        (src / "shared.txt").write_text(content)
        (dst / "shared.txt").write_text(content)
        (src / "unique.txt").write_text("only in source")

        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", str(src), str(dst)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "shared.txt" in result.stdout

    def test_find_dupes_json_output(self, tmp_path):
        """End-to-end: find duplicates via CLI with JSON output."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        content = "identical bytes"
        (src / "data.bin").write_bytes(content.encode())
        (dst / "data.bin").write_bytes(content.encode())

        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", str(src), str(dst), "--output", "json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = _parse_json_stdout(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert "data.bin" in data[0]["source_file"]["path"]

    def test_find_dupes_with_hash(self, tmp_path):
        """End-to-end: find duplicates via CLI with hash verification."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        (src / "file.txt").write_text("same")
        (dst / "file.txt").write_text("same")

        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", str(src), str(dst), "--hash", "md5", "--output", "json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = _parse_json_stdout(result.stdout)
        assert len(data) == 1

    def test_find_dupes_no_duplicates(self, tmp_path):
        """End-to-end: no duplicates found."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        (src / "a.txt").write_text("aaa")
        (dst / "b.txt").write_text("bbb")

        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", str(src), str(dst)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No duplicate" in result.stdout

    def test_find_dupes_invalid_source(self, tmp_path):
        """End-to-end: error on invalid source path."""
        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", str(tmp_path / "nonexistent"), str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_find_dupes_multiple_destinations(self, tmp_path):
        """End-to-end: scan source against multiple destinations."""
        src = tmp_path / "source"
        dst1 = tmp_path / "dest1"
        dst2 = tmp_path / "dest2"
        src.mkdir()
        dst1.mkdir()
        dst2.mkdir()

        content = "shared"
        (src / "file.txt").write_text(content)
        (dst1 / "file.txt").write_text(content)
        (dst2 / "file.txt").write_text(content)

        result = subprocess.run(
            [sys.executable, "main.py", "find-dupes", str(src), str(dst1), str(dst2), "--output", "json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = _parse_json_stdout(result.stdout)
        assert len(data) == 1
        assert len(data[0]["duplicates_found"]) == 2
