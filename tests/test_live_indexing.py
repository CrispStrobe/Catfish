"""Live integration tests that exercise real file I/O operations.

These tests create real file trees, index them, save/load CAF files,
search across indices, and detect duplicates end-to-end.
"""

import pytest

from core.data_structures import ScanConfig, SearchCriteria
from core.file_index import FileIndex
from core.search_logic import (
    build_destination_index,
    find_duplicates_with_locations,
    search_files_in_index,
)

pytestmark = pytest.mark.live


class TestLiveIndexing:
    """End-to-end indexing workflow tests."""

    def _create_file_tree(self, root, files):
        """Helper: create files from a dict {relative_path: content}."""
        for rel_path, content in files.items():
            f = root / rel_path
            f.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                f.write_text(content)
            else:
                f.write_bytes(content)

    def test_index_scan_and_save(self, tmp_path):
        """Create files, build index, save to CAF, verify."""
        self._create_file_tree(
            tmp_path,
            {
                "readme.txt": "This is a readme",
                "data/report.csv": "a,b,c\n1,2,3\n",
                "data/archive/old.log": "old log data " * 100,
                "images/photo.jpg": b"\xff\xd8\xff" + b"\x00" * 1000,
            },
        )

        idx = FileIndex(tmp_path, use_hash=True, hash_algo="md5")
        for f in tmp_path.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        assert idx.total_files == 4
        assert len(idx.all_files) == 4

        # Verify size index
        for entry in idx.all_files:
            assert entry.size > 0
            assert entry.hash != ""  # hash was computed
            assert entry.size in idx.size_index

        # Save and reload
        caf = tmp_path / "test.caf"
        idx.save_to_caf(caf)
        assert caf.exists()
        assert caf.stat().st_size > 0

        loaded = FileIndex.load_from_caf(caf, use_hash=False, hash_algo="md5")
        assert loaded is not None
        assert loaded.total_files == 4

    def test_search_across_index(self, tmp_path):
        """Build index, search by various criteria."""
        self._create_file_tree(
            tmp_path,
            {
                "doc.txt": "small text",
                "photo.jpg": b"x" * 5000,
                "video.mp4": b"x" * 50000,
                "notes.TXT": "mixed case extension",
                "sub/deep.txt": "nested file",
            },
        )

        idx = FileIndex(tmp_path, use_hash=False, hash_algo="md5")
        for f in tmp_path.rglob("*"):
            if f.is_file():
                idx.add_file(f)
        idx.build_optimized_indices()

        # Search by extension
        results = search_files_in_index(idx, SearchCriteria(name_pattern="*.txt"))
        names = {r.path.name for r in results}
        assert "doc.txt" in names
        assert "notes.TXT" in names
        assert "deep.txt" in names
        assert "photo.jpg" not in names

        # Search by size
        results = search_files_in_index(idx, SearchCriteria(size_min=10000))
        assert len(results) == 1
        assert results[0].path.name == "video.mp4"

        # Search by prefix
        results = search_files_in_index(idx, SearchCriteria(name_pattern="doc*"))
        assert len(results) == 1

        # Search all files
        results = search_files_in_index(idx, SearchCriteria())
        assert len(results) == 5


class TestLiveDuplicateDetection:
    """End-to-end duplicate detection tests."""

    def test_find_name_size_duplicates(self, tmp_path):
        """Detect duplicates by name+size."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        # Create identical files
        content = "duplicate content here"
        (src / "shared.txt").write_text(content)
        (dst / "shared.txt").write_text(content)

        # Create unique files
        (src / "only_source.txt").write_text("unique to source")
        (dst / "only_dest.txt").write_text("unique to dest")

        config = ScanConfig(
            source_path=src,
            dest_paths=[dst],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        dest_index = build_destination_index(config)
        assert dest_index is not None
        assert dest_index.total_files == 2

        duplicates = find_duplicates_with_locations(src, dest_index)
        assert len(duplicates) == 1
        assert duplicates[0].source_file.name == "shared.txt"
        assert duplicates[0].destinations[0].path.name == "shared.txt"

    def test_find_hash_duplicates(self, tmp_path):
        """Detect duplicates by hash (same content, different names)."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        content = "identical bytes"
        (src / "original.txt").write_text(content)
        (dst / "original.txt").write_text(content)  # Same name+size

        config = ScanConfig(
            source_path=src,
            dest_paths=[dst],
            use_hash=True,
            hash_algo="sha256",
            reuse_indices=False,
            recreate_indices=False,
        )

        dest_index = build_destination_index(config)
        duplicates = find_duplicates_with_locations(src, dest_index)
        assert len(duplicates) == 1

    def test_no_false_positives(self, tmp_path):
        """Same filename but different content should not match by hash."""
        src = tmp_path / "source"
        dst = tmp_path / "dest"
        src.mkdir()
        dst.mkdir()

        (src / "data.bin").write_bytes(b"content_a_xxx")
        (dst / "data.bin").write_bytes(b"content_b_yyy")

        config = ScanConfig(
            source_path=src,
            dest_paths=[dst],
            use_hash=True,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        dest_index = build_destination_index(config)
        duplicates = find_duplicates_with_locations(src, dest_index)
        assert len(duplicates) == 0

    def test_multiple_destinations(self, tmp_path):
        """Scan source against multiple destinations."""
        src = tmp_path / "source"
        dst1 = tmp_path / "dest1"
        dst2 = tmp_path / "dest2"
        src.mkdir()
        dst1.mkdir()
        dst2.mkdir()

        content = "shared content"
        (src / "file.txt").write_text(content)
        (dst1 / "file.txt").write_text(content)
        (dst2 / "file.txt").write_text(content)
        (dst2 / "extra.txt").write_text("only in dest2")

        config = ScanConfig(
            source_path=src,
            dest_paths=[dst1, dst2],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        dest_index = build_destination_index(config)
        assert dest_index.total_files == 3

        duplicates = find_duplicates_with_locations(src, dest_index)
        assert len(duplicates) == 1
        assert len(duplicates[0].destinations) == 2


class TestLiveCAFPersistence:
    """Test CAF file persistence with reuse."""

    def test_caf_reuse_workflow(self, tmp_path):
        """Build index, save CAF, then reuse it in a search."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        for i in range(20):
            (data_dir / f"file_{i:03d}.txt").write_text(f"content {i}" * 10)

        # Build and save
        idx = FileIndex(data_dir, use_hash=False, hash_algo="md5")
        for f in data_dir.rglob("*"):
            if f.is_file():
                idx.add_file(f)

        caf_path = tmp_path / "data_index.caf"
        idx.save_to_caf(caf_path)

        # Load and search
        loaded = FileIndex.load_from_caf(caf_path, use_hash=False, hash_algo="md5")
        assert loaded is not None
        assert loaded.total_files == 20
        assert loaded.is_optimized is True  # auto-built during load

        results = search_files_in_index(loaded, SearchCriteria(name_pattern="file_01*"))
        names = {r.path.name for r in results}
        assert "file_010.txt" in names
        assert "file_019.txt" in names
