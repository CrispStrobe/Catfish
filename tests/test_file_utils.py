"""Tests for utils/file_utils.py"""

import hashlib
from datetime import datetime

import pytest

from utils.file_utils import (
    calculate_file_hash,
    filter_overlapping_paths,
    format_size,
    get_caf_path,
    is_subdirectory,
    parse_date,
    parse_size,
    path_is_native_and_exists,
)

# --- format_size ---


class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(512) == "512 B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert format_size(1024**2) == "1.0 MB"

    def test_gigabytes(self):
        assert format_size(1024**3) == "1.0 GB"

    def test_terabytes(self):
        assert format_size(1024**4) == "1.0 TB"


# --- parse_size ---


class TestParseSize:
    def test_bytes(self):
        assert parse_size("100B") == 100
        assert parse_size("100") == 100

    def test_kilobytes(self):
        assert parse_size("1KB") == 1024
        assert parse_size("2kb") == 2048

    def test_megabytes(self):
        assert parse_size("5MB") == 5 * 1024**2

    def test_gigabytes(self):
        assert parse_size("1GB") == 1024**3

    def test_fractional(self):
        assert parse_size("1.5MB") == int(1.5 * 1024**2)

    def test_with_spaces(self):
        assert parse_size("  10 MB  ") == 10 * 1024**2

    def test_empty_or_any(self):
        assert parse_size("") == 0
        assert parse_size("any") == 0

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_size("not_a_size")

    def test_shorthand_units(self):
        # Single-letter units like "K", "M" should also work
        assert parse_size("1K") == 1024
        assert parse_size("2M") == 2 * 1024**2


# --- parse_date ---


class TestParseDate:
    def test_iso_format(self):
        result = parse_date("2024-06-15")
        assert result == datetime(2024, 6, 15)

    def test_european_format(self):
        result = parse_date("15.06.2024")
        assert result == datetime(2024, 6, 15)

    def test_today(self):
        result = parse_date("today")
        now = datetime.now()
        assert result.year == now.year
        assert result.month == now.month
        assert result.day == now.day

    def test_yesterday(self):
        result = parse_date("yesterday")
        assert result is not None

    def test_german_relative(self):
        assert parse_date("heute") is not None
        assert parse_date("gestern") is not None

    def test_empty_returns_none(self):
        assert parse_date("") is None
        assert parse_date("any") is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_date("not_a_date")


# --- calculate_file_hash ---


class TestCalculateFileHash:
    def test_md5(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        expected = hashlib.md5(b"hello").hexdigest()
        assert calculate_file_hash(f, "md5") == expected

    def test_sha256(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert calculate_file_hash(f, "sha256") == expected

    def test_nonexistent_file(self, tmp_path):
        result = calculate_file_hash(tmp_path / "no_such_file", "md5")
        assert result == ""


# --- path_is_native_and_exists ---


class TestPathIsNativeAndExists:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "exists.txt"
        f.write_text("ok")
        assert path_is_native_and_exists(f) is True

    def test_nonexistent(self, tmp_path):
        assert path_is_native_and_exists(tmp_path / "nope") is False


# --- is_subdirectory ---


class TestIsSubdirectory:
    def test_child(self, tmp_path):
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert is_subdirectory(child, tmp_path) is True

    def test_not_child(self, tmp_path):
        other = tmp_path.parent / "other"
        assert is_subdirectory(other, tmp_path) is False


# --- filter_overlapping_paths ---


class TestFilterOverlappingPaths:
    def test_removes_child(self, tmp_path):
        parent = tmp_path / "a"
        child = parent / "b"
        parent.mkdir()
        child.mkdir()

        result = filter_overlapping_paths([parent, child])
        assert result == [parent]

    def test_keeps_siblings(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()

        result = filter_overlapping_paths([a, b])
        assert set(result) == {a, b}


# --- get_caf_path ---


class TestGetCafPath:
    def test_md5_default(self, tmp_path):
        p = tmp_path / "mydir"
        p.mkdir()
        caf = get_caf_path(p, "md5")
        assert caf.name == "mydir_index.caf"

    def test_sha256(self, tmp_path):
        p = tmp_path / "mydir"
        p.mkdir()
        caf = get_caf_path(p, "sha256")
        assert caf.name == "mydir_index_sha256.caf"
