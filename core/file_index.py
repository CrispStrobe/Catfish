# core/file_index.py

"""File indexing and CAF format handling."""

import stat
import struct
import sys
import time
from collections import defaultdict
from datetime import datetime as dt
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional

from core.data_structures import DuplicateMatch, FileEntry
from utils.file_utils import calculate_file_hash, format_size, path_is_native_and_exists


class FileIndex:
    """
    Manages file metadata with O(1) duplicate lookups and O(log N) search indices.
    """

    ulMagicBase = 500410407
    ulModus = 1000000000
    saveVersion = 8

    def __init__(self, root_path: Path, use_hash: bool = False, hash_algo: str = "md5"):
        self.root_path = root_path
        self.use_hash = use_hash
        self.hash_algo = hash_algo

        # O(1) Lookup for Duplicates: {size_bytes: [entries]}
        self.size_index: dict[int, list[FileEntry]] = defaultdict(list)
        self.hash_index: dict[tuple[int, str], list[FileEntry]] = defaultdict(list)

        # O(N) Linear Scan List (Fastest iteration)
        self.all_files: list[FileEntry] = []

        # O(log N) Binary Search Indices
        self.is_optimized = False
        self.prefix_index: list[tuple[str, FileEntry]] = []  # Sorted by name
        self.suffix_index: list[tuple[str, FileEntry]] = []  # Sorted by reversed name

        self.total_files = 0

    def add_file(self, file_path: Path) -> bool:
        """Adds a file to the in-memory index."""
        try:
            stat_info = file_path.stat()
            if not stat.S_ISREG(stat_info.st_mode):
                return False

            file_size = stat_info.st_size
            mtime = int(stat_info.st_mtime)

            file_hash = ""
            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash:
                    return False

            entry = FileEntry(file_path, file_size, mtime, file_hash)

            # Add to all structures
            self.size_index[file_size].append(entry)
            self.all_files.append(entry)
            if self.use_hash:
                self.hash_index[(file_size, file_hash)].append(entry)

            self.total_files += 1
            return True
        except OSError:
            return False

    def build_optimized_indices(self):
        """
        Builds O(log N) search structures. Call this once after loading.
        """
        if not self.all_files:
            return

        print(
            f"[INDEX] Optimization: Sorting {len(self.all_files)} items for Binary Search...",
            end="",
            flush=True,
            file=sys.stderr,
        )
        t0 = time.time()

        # 1. Prefix Index: Sort by lowercase name for 'start*' queries
        # We store tuples (key, entry) to allow bisecting on the key
        self.prefix_index = sorted([(e.path.name.lower(), e) for e in self.all_files], key=lambda x: x[0])

        # 2. Suffix Index: Sort by REVERSED lowercase name for '*.ext' queries
        self.suffix_index = sorted([(e.path.name.lower()[::-1], e) for e in self.all_files], key=lambda x: x[0])

        self.is_optimized = True
        elapsed = time.time() - t0
        print(f" Done in {elapsed:.2f}s", file=sys.stderr)

    def _write_caf(self, caf_path, elm, info):
        with caf_path.open("wb") as buffer:
            buffer.write(struct.pack("<L", 3 * self.ulModus + self.ulMagicBase))
            buffer.write(struct.pack("<h", self.saveVersion))
            buffer.write(struct.pack("<L", int(time.time())))
            self._write_string(buffer, str(self.root_path))
            self._write_string(buffer, self.root_path.name)
            self._write_string(buffer, self.root_path.name)
            buffer.write(struct.pack("<L", 0))
            self._write_string(buffer, "Universal Search Index")
            buffer.write(struct.pack("<f", 0.0))
            buffer.write(struct.pack("<h", 0))
            buffer.write(struct.pack("<l", len(info)))
            for i, (_dir_id, fc, ts) in enumerate(info):
                if i == 0:
                    self._write_string(buffer, "")
                buffer.write(struct.pack("<l", fc))
                buffer.write(struct.pack("<d", ts))
            buffer.write(struct.pack("<l", len(elm)))
            for mtime, size, parent_id, name in elm:
                buffer.write(struct.pack("<L", mtime))
                buffer.write(struct.pack("<q", size))
                buffer.write(struct.pack("<L", parent_id))
                self._write_string(buffer, name)

    @classmethod
    def load_from_caf(cls, caf_path: Path, use_hash: bool, hash_algo: str) -> Optional["FileIndex"]:
        """Loads index from CAF file with optimized buffered reading."""
        if not caf_path.is_file():
            return None

        with caf_path.open("rb") as buffer:
            try:
                # Header Check
                magic = struct.unpack("<L", buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase):
                    return None
                version = int(magic / cls.ulModus)
                if version > 2:
                    version = struct.unpack("<h", buffer.read(2))[0]
                if version > cls.saveVersion:
                    return None

                # Header Skip
                buffer.read(4)
                device = cls._read_string(buffer) if version >= 2 else ""

                # Path Logic
                is_windows = "\\" in device or (len(device) > 1 and device[1] == ":")
                PathClass = PureWindowsPath if is_windows else PurePosixPath
                index = cls(PathClass(device), use_hash, hash_algo)

                # Metadata Skip
                cls._read_string(buffer)  # volume
                cls._read_string(buffer)  # alias
                buffer.read(4)  # serial
                cls._read_string(buffer) if version >= 4 else ""
                if version >= 1:
                    buffer.read(4)
                if version >= 6:
                    buffer.read(2)

                dir_count = struct.unpack("<l", buffer.read(4))[0]
                for i in range(dir_count):
                    if i == 0 or version <= 3:
                        cls._read_string(buffer)
                    if version >= 3:
                        buffer.read(12)

                # --- FAST BODY PARSING ---
                data = buffer.read()
                offset = 0
                max_offset = len(data)

                file_count = struct.unpack_from("<l", data, offset)[0]
                offset += 4

                raw_elm = []

                # Determine struct format
                if version <= 6:
                    fmt, step = "<LlH", 10
                elif version <= 7:
                    fmt, step = "<LqH", 14
                else:
                    fmt, step = "<LqL", 16

                # Vectorized loop
                for _ in range(file_count):
                    if offset + step > max_offset:
                        break
                    mtime, size, parent_id = struct.unpack_from(fmt, data, offset)
                    offset += step

                    end_pos = data.find(b"\x00", offset)
                    if end_pos == -1:
                        filename = ""
                    else:
                        filename = data[offset:end_pos].decode("latin-1", errors="replace")
                        offset = end_pos + 1

                    raw_elm.append((mtime, size, parent_id, filename))

                # Directory Reconstruction
                referenced_parent_ids = {pid for _, _, pid, _ in raw_elm}
                dir_path_map = {0: index.root_path}

                # 1. Build Dirs
                for i, (_mtime, size, pid, name) in enumerate(raw_elm):
                    is_dir = (version > 6 and size < 0) or (version <= 6 and (i + 1) in referenced_parent_ids)
                    if is_dir:
                        dir_id = -size if version > 6 else (i + 1)
                        if pid in dir_path_map and name:
                            dir_path_map[dir_id] = dir_path_map[pid] / name

                # 2. Add Files
                for i, (mtime, size, pid, name) in enumerate(raw_elm):
                    is_dir = (version > 6 and size < 0) or (version <= 6 and (i + 1) in referenced_parent_ids)
                    if not is_dir and pid in dir_path_map and name.strip():
                        path = dir_path_map[pid] / name
                        actual_size = max(size, 1) if version > 6 else (max(size, 1024) if size == 0 else size)

                        entry = FileEntry(path, actual_size, mtime, "")
                        index.size_index[actual_size].append(entry)
                        index.total_files += 1

                # Final Optimization Step
                index._flatten_index()
                index.build_optimized_indices()  # Build O(log N) structures

                return index

            except Exception as e:
                print(f"[CAF] Error: {e}", file=sys.stderr)
                return None

    def _flatten_index(self):
        """Populates the flat all_files list."""
        if not self.all_files and self.size_index:
            self.all_files = [entry for bucket in self.size_index.values() for entry in bucket]

    @classmethod
    def load_metadata_only(cls, caf_path: Path) -> Optional[dict]:
        """Fast metadata extraction without loading file entries."""
        if not caf_path.is_file():
            return None

        with caf_path.open("rb") as buffer:
            try:
                # Header validation
                magic = struct.unpack("<L", buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase):
                    return None
                version = int(magic / cls.ulModus)
                if version > 2:
                    version = struct.unpack("<h", buffer.read(2))[0]

                # Quick header parsing
                created_timestamp = struct.unpack("<L", buffer.read(4))[0]
                device = cls._read_string(buffer) if version >= 2 else ""
                volume = cls._read_string(buffer)
                cls._read_string(buffer)
                buffer.read(4)  # serial
                cls._read_string(buffer) if version >= 4 else ""
                freesize = struct.unpack("<f", buffer.read(4))[0] if version >= 1 else 0
                archive = struct.unpack("<h", buffer.read(2))[0] if version >= 6 else 0

                # Get file count from info block
                dir_count = struct.unpack("<l", buffer.read(4))[0]
                file_count = 0
                total_size = 0

                if dir_count > 0:
                    cls._read_string(buffer)  # Skip root dir name
                    file_count = struct.unpack("<l", buffer.read(4))[0]
                    total_size = int(struct.unpack("<d", buffer.read(8))[0])

                return {
                    "device": device,
                    "volume": volume,
                    "file_count": file_count,
                    "total_size": total_size,
                    "created_date": dt.fromtimestamp(created_timestamp),
                    "archive": archive,
                    "freesize": freesize,
                }

            except (struct.error, OSError, IndexError):
                return None

    @staticmethod
    def find_all_duplicates_bulk(
        source_index: "FileIndex", dest_index: "FileIndex", progress_callback=None, cancel_event=None
    ) -> list[DuplicateMatch]:
        """
        Bulk duplicate detection optimized for scanning operations.
        Uses source_index.size_index to skip sizes with no destination matches,
        avoiding a redundant filesystem rescan.
        """
        duplicates: list[DuplicateMatch] = []
        processed = 0
        total_files = source_index.total_files

        for size, source_entries in source_index.size_index.items():
            if cancel_event and cancel_event.is_set():
                break

            # Skip sizes with no destination matches
            if size not in dest_index.size_index:
                processed += len(source_entries)
                continue

            if progress_callback:
                progress_callback(
                    "Finding duplicates", f"Processing {len(source_entries)} files of size {format_size(size)}"
                )

            for entry in source_entries:
                if cancel_event and cancel_event.is_set():
                    break

                processed += 1
                if progress_callback and processed % 50 == 0:
                    progress_callback(
                        "Finding duplicates",
                        f"Checked {processed}/{total_files} files ({len(duplicates)} duplicates found)",
                    )

                matches = dest_index.find_potential_duplicates(entry.path)
                if matches:
                    duplicates.append(DuplicateMatch(source_file=entry.path, destinations=matches))

        return duplicates

    def find_potential_duplicates(self, file_path: Path) -> list[FileEntry]:
        """Finds potential duplicates of a given file in the index.

        Uses hash_index for pre-computed hashes (from add_file with use_hash=True),
        or calculates hashes on demand for indices loaded from CAF files.
        Falls back to name+size comparison when hashing is disabled.
        """
        try:
            stat_info = file_path.stat()
            file_size = stat_info.st_size

            if file_size not in self.size_index:
                return []

            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash:
                    return []

                # Try pre-computed hash index first (fast path)
                if self.hash_index:
                    return self.hash_index.get((file_size, file_hash), [])

                # Fall back to on-demand hash calculation (for CAF-loaded indices)
                matches = []
                for entry in self.size_index[file_size]:
                    if path_is_native_and_exists(entry.path):
                        candidate_hash = calculate_file_hash(Path(entry.path), self.hash_algo)
                        if candidate_hash == file_hash:
                            matches.append(FileEntry(entry.path, entry.size, entry.mtime, candidate_hash))
                return matches
            else:
                return [e for e in self.size_index[file_size] if e.path.name == file_path.name]
        except OSError:
            return []

    # --- CAF Serialization Methods ---

    def save_to_caf(self, caf_path: Path):
        """
        Saves the current in-memory index to a Cathy-compatible .caf file.
        """
        # 1. Prepare directory structure and metadata
        dir_id_map: dict[Path, int] = {self.root_path: 0}
        next_dir_id = 1

        all_entries: list[FileEntry] = [e for entries in self.size_index.values() for e in entries]

        # Discover all unique directories and assign IDs
        all_dirs = {entry.path.parent for entry in all_entries}
        for d in sorted(all_dirs, key=lambda p: len(p.parts)):
            if d not in dir_id_map:
                dir_id_map[d] = next_dir_id
                next_dir_id += 1

        # 2. Build the `elm` list (all files and directories)
        elm = []
        dir_stats = defaultdict(lambda: {"file_count": 0, "total_size": 0})

        # Add directories to elm list first
        for dir_path, dir_id in dir_id_map.items():
            if dir_id == 0:
                continue
            try:
                parent_id = dir_id_map[dir_path.parent]
                mtime = int(dir_path.stat().st_mtime)
                # Directories are stored with their negative ID as the size
                elm.append((mtime, -dir_id, parent_id, dir_path.name))
            except (OSError, KeyError):
                continue

        # Add files to elm list and update directory stats
        for entry in all_entries:
            try:
                parent_id = dir_id_map[entry.path.parent]
                elm.append((entry.mtime, entry.size, parent_id, entry.path.name))
                dir_stats[parent_id]["file_count"] += 1
                dir_stats[parent_id]["total_size"] += entry.size
            except KeyError:
                continue

        # 3. Build the `info` list (directory summaries)
        info = [(0, 0, 0)] * next_dir_id  # Pre-allocate list
        for dir_id, stats in dir_stats.items():
            info[dir_id] = (dir_id, stats["file_count"], stats["total_size"])

        # Set root directory info (aggregate all stats)
        total_file_count = sum(s["file_count"] for s in dir_stats.values())
        total_catalog_size = sum(s["total_size"] for s in dir_stats.values())
        info[0] = (0, total_file_count, total_catalog_size)

        # 4. Write the CAF file
        self._write_caf(caf_path, elm, info)

    # --- Private static I/O helpers ---
    @staticmethod
    def _read_string(buffer) -> str:
        chars = bytearray()
        while (char := buffer.read(1)) != b"\x00":
            if not char:
                break
            chars.extend(char)
        return chars.decode("latin-1", errors="replace")

    @staticmethod
    def _write_string(buffer, text: str):
        buffer.write(text.encode("latin-1", errors="replace"))
        buffer.write(b"\x00")
