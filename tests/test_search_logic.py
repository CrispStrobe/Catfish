"""Tests for core/search_logic.py"""

from core.data_structures import SearchCriteria
from core.file_index import FileIndex
from core.search_logic import _safe_compile_pattern, search_files_in_index


class TestSafeCompilePattern:
    def test_empty_pattern(self):
        p = _safe_compile_pattern("")
        assert p.search("anything") is not None

    def test_regex_pattern(self):
        p = _safe_compile_pattern(r"IMG_\d+\.jpg")
        assert p.search("IMG_123.jpg") is not None
        assert p.search("photo.png") is None

    def test_glob_pattern(self):
        p = _safe_compile_pattern("*.txt")
        assert p.search("file.txt") is not None

    def test_fallback_to_fnmatch(self):
        # Invalid regex patterns fall back to fnmatch.translate, which handles almost anything
        p = _safe_compile_pattern("[invalid")
        # fnmatch treats it as a glob, so it should still compile
        assert p is not None


class TestSearchFilesInIndex:
    def _build_index(self, tmp_path):
        """Helper to build a small in-memory index."""
        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")

        files = [
            ("photo.jpg", b"x" * 1000),
            ("document.txt", b"hello world\n"),
            ("report.pdf", b"x" * 5000),
            ("image.PNG", b"x" * 2000),
        ]
        for name, content in files:
            f = tmp_path / name
            f.write_bytes(content)
            idx.add_file(f)

        idx.build_optimized_indices()
        return idx

    def test_search_by_name_contains(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria(name_pattern="*photo*")
        results = search_files_in_index(idx, criteria)
        assert len(results) == 1
        assert results[0].path.name == "photo.jpg"

    def test_search_by_extension_endswith(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria(name_pattern="*.txt")
        results = search_files_in_index(idx, criteria)
        assert len(results) == 1
        assert results[0].path.name == "document.txt"

    def test_search_by_prefix_startswith(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria(name_pattern="report*")
        results = search_files_in_index(idx, criteria)
        assert len(results) == 1

    def test_search_by_size_min(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria(size_min=2000)
        results = search_files_in_index(idx, criteria)
        # report.pdf (5000) and image.PNG (2000)
        assert len(results) == 2

    def test_search_by_size_range(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria(size_min=999, size_max=2001)
        results = search_files_in_index(idx, criteria)
        names = {r.path.name for r in results}
        assert "photo.jpg" in names
        assert "image.PNG" in names

    def test_search_no_criteria(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria()
        results = search_files_in_index(idx, criteria)
        assert len(results) == 4

    def test_search_multiple_extensions(self, tmp_path):
        idx = self._build_index(tmp_path)
        # Use glob patterns that the search logic supports
        jpg_results = search_files_in_index(idx, SearchCriteria(name_pattern="*.jpg"))
        png_results = search_files_in_index(idx, SearchCriteria(name_pattern="*.png"))
        # Case-insensitive: photo.jpg and image.PNG
        combined = {r.path.name for r in jpg_results} | {r.path.name for r in png_results}
        assert "photo.jpg" in combined
        assert "image.PNG" in combined

    def test_search_case_insensitive(self, tmp_path):
        idx = self._build_index(tmp_path)
        criteria = SearchCriteria(name_pattern="*.png")
        results = search_files_in_index(idx, criteria)
        assert len(results) == 1
        assert results[0].path.name == "image.PNG"

    def test_search_with_progress_callback(self, tmp_path):
        idx = self._build_index(tmp_path)
        calls = []

        def cb(current, total, speed):
            calls.append((current, total))

        criteria = SearchCriteria(name_pattern="*")
        search_files_in_index(idx, criteria, progress_callback=cb)
        # Progress may or may not fire depending on batch size
        # Just verify it doesn't crash

    def test_empty_index(self, tmp_path):
        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        idx.build_optimized_indices()
        criteria = SearchCriteria(name_pattern="*")
        results = search_files_in_index(idx, criteria)
        assert results == []
