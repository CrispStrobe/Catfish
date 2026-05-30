"""Tests for core/file_index.py"""

from core.file_index import FileIndex


class TestFileIndexAddFile:
    def test_add_regular_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")

        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        assert idx.add_file(f) is True
        assert idx.total_files == 1
        assert len(idx.all_files) == 1

    def test_add_file_with_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")

        idx = FileIndex(tmp_path, use_hash=True, hash_algo="md5")
        assert idx.add_file(f) is True
        assert idx.total_files == 1
        # Hash should be populated
        assert idx.all_files[0].hash != ""

    def test_add_directory_returns_false(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()

        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        assert idx.add_file(d) is False
        assert idx.total_files == 0

    def test_add_nonexistent_returns_false(self, tmp_path):
        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        assert idx.add_file(tmp_path / "nope.txt") is False

    def test_size_index_populated(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        size = f.stat().st_size

        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        idx.add_file(f)

        assert size in idx.size_index
        assert len(idx.size_index[size]) == 1

    def test_hash_index_populated(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")

        idx = FileIndex(tmp_path, use_hash=True, hash_algo="md5")
        idx.add_file(f)

        assert len(idx.hash_index) == 1


class TestBuildOptimizedIndices:
    def test_builds_prefix_and_suffix(self, tmp_path):
        for name in ["alpha.txt", "beta.txt", "gamma.log"]:
            (tmp_path / name).write_text("content")

        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        for f in tmp_path.iterdir():
            idx.add_file(f)

        idx.build_optimized_indices()

        assert idx.is_optimized is True
        assert len(idx.prefix_index) == 3
        assert len(idx.suffix_index) == 3

    def test_empty_index_optimization(self, tmp_path):
        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        idx.build_optimized_indices()
        assert idx.is_optimized is False


class TestCAFRoundTrip:
    def test_save_and_load(self, tmp_tree):
        """Save index to CAF, load it back, verify contents."""
        idx = FileIndex(tmp_tree, use_hash=False, hash_algo="md5")

        # Add all files
        for f in tmp_tree.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        assert idx.total_files == 4

        # Save
        caf_path = tmp_tree / "test_index.caf"
        idx.save_to_caf(caf_path)
        assert caf_path.exists()

        # Load
        loaded = FileIndex.load_from_caf(caf_path, use_hash=False, hash_algo="md5")
        assert loaded is not None
        assert loaded.total_files == 4

    def test_load_nonexistent(self, tmp_path):
        result = FileIndex.load_from_caf(tmp_path / "missing.caf", False, "md5")
        assert result is None

    def test_load_invalid_file(self, tmp_path):
        bad = tmp_path / "bad.caf"
        bad.write_bytes(b"this is not a CAF file")
        result = FileIndex.load_from_caf(bad, False, "md5")
        assert result is None


class TestLoadMetadataOnly:
    def test_metadata_extraction(self, tmp_tree):
        idx = FileIndex(tmp_tree, use_hash=False, hash_algo="md5")
        for f in tmp_tree.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        caf_path = tmp_tree / "meta_test.caf"
        idx.save_to_caf(caf_path)

        meta = FileIndex.load_metadata_only(caf_path)
        assert meta is not None
        assert "device" in meta
        assert "file_count" in meta
        assert meta["file_count"] == 4


class TestFindPotentialDuplicates:
    def test_find_by_name_and_size(self, source_and_dest):
        src, dst = source_and_dest

        # Build destination index
        idx = FileIndex(dst, use_hash=False, hash_algo="md5")
        for f in dst.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        # Check for duplicates of source files
        matches = idx.find_potential_duplicates(src / "shared.txt")
        assert len(matches) == 1
        assert matches[0].path.name == "shared.txt"

    def test_no_duplicate_for_unique(self, source_and_dest):
        src, dst = source_and_dest

        idx = FileIndex(dst, use_hash=False, hash_algo="md5")
        for f in dst.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        matches = idx.find_potential_duplicates(src / "unique.txt")
        assert len(matches) == 0

    def test_find_by_hash(self, source_and_dest):
        src, dst = source_and_dest

        idx = FileIndex(dst, use_hash=True, hash_algo="md5")
        for f in dst.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        matches = idx.find_potential_duplicates(src / "shared.txt")
        assert len(matches) == 1


class TestFlattenIndex:
    def test_flatten(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")

        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        idx.add_file(f)

        # Clear all_files and rebuild
        idx.all_files = []
        idx._flatten_index()
        assert len(idx.all_files) == 1
