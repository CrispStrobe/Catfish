"""Tests for core/scan_operations.py"""

from core.data_structures import ScanConfig
from core.scan_operations import build_destination_index_selective


class TestBuildDestinationIndexSelective:
    def _make_tree(self, root, files):
        root.mkdir(exist_ok=True)
        for name, content in files.items():
            f = root / name
            f.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                f.write_text(content)
            else:
                f.write_bytes(content)

    def test_builds_index_from_single_dest(self, tmp_path):
        dst = tmp_path / "dest"
        self._make_tree(dst, {"a.txt": "hello", "b.txt": "world"})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[dst],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        index = build_destination_index_selective(config)
        assert index is not None
        assert index.total_files == 2

    def test_builds_index_from_multiple_dests(self, tmp_path):
        dst1 = tmp_path / "dest1"
        dst2 = tmp_path / "dest2"
        self._make_tree(dst1, {"a.txt": "aaa"})
        self._make_tree(dst2, {"b.txt": "bbb", "c.txt": "ccc"})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[dst1, dst2],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        index = build_destination_index_selective(config)
        assert index is not None
        assert index.total_files == 3

    def test_saves_and_reuses_caf(self, tmp_path):
        dst = tmp_path / "dest"
        self._make_tree(dst, {"file.txt": "content"})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[dst],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=True,
            recreate_indices=False,
        )

        # First call: creates CAF
        index1 = build_destination_index_selective(config)
        assert index1 is not None
        assert index1.total_files == 1

        # CAF should exist now
        from utils.file_utils import get_caf_path

        caf = get_caf_path(dst, "md5")
        assert caf.exists()

        # Second call: should reuse CAF
        index2 = build_destination_index_selective(config)
        assert index2 is not None
        assert index2.total_files == 1

    def test_with_hash_enabled(self, tmp_path):
        dst = tmp_path / "dest"
        self._make_tree(dst, {"data.bin": b"\x00" * 100})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[dst],
            use_hash=True,
            hash_algo="sha256",
            reuse_indices=False,
            recreate_indices=False,
        )

        index = build_destination_index_selective(config)
        assert index is not None
        assert index.total_files == 1

    def test_skips_nonexistent_dest(self, tmp_path):
        real_dst = tmp_path / "real"
        self._make_tree(real_dst, {"a.txt": "aaa"})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[real_dst, tmp_path / "nonexistent"],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        index = build_destination_index_selective(config)
        assert index is not None
        assert index.total_files == 1

    def test_progress_callback_invoked(self, tmp_path):
        dst = tmp_path / "dest"
        self._make_tree(dst, {"a.txt": "hello"})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[dst],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        calls = []

        def cb(operation, details):
            calls.append((operation, details))

        build_destination_index_selective(config, progress_callback=cb)
        assert len(calls) > 0

    def test_cancel_event_stops_scan(self, tmp_path):
        from threading import Event

        dst = tmp_path / "dest"
        self._make_tree(dst, {f"file_{i}.txt": f"content {i}" for i in range(20)})

        config = ScanConfig(
            source_path=tmp_path,
            dest_paths=[dst],
            use_hash=False,
            hash_algo="md5",
            reuse_indices=False,
            recreate_indices=False,
        )

        cancel = Event()
        cancel.set()  # Cancel immediately

        index = build_destination_index_selective(config, cancel_event=cancel)
        # Should return early with 0 files since cancel was set before scanning
        assert index is not None
        assert index.total_files == 0
