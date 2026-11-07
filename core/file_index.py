# core/file_index.py

"""File indexing and CAF format handling."""

import os
import stat
import struct
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime as dt
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Optional

from core.data_structures import DuplicateMatch, FileEntry, ScanError
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
        self.directory_mtimes: dict[Path, int] = {}
        self.scan_errors: list[ScanError] = []
        self.scan_error_count = 0
        self.cancelled = False

    @property
    def is_complete(self) -> bool:
        return not self.cancelled and self.scan_error_count == 0

    def _record_scan_error(self, path: Path, error: object):
        self.scan_error_count += 1
        if len(self.scan_errors) < 1000:
            self.scan_errors.append(ScanError(path, str(error)))

    @classmethod
    def scan_directory(
        cls,
        root_path: Path,
        use_hash: bool = False,
        hash_algo: str = "md5",
        *,
        progress_callback: Optional[Callable[[int, Path], None]] = None,
        cancel_event=None,
        progress_interval: float = 0.1,
    ) -> "FileIndex":
        """Index a native folder in one metadata pass.

        Reuse DirEntry metadata instead of discarding it and calling Path.stat
        again. As with the original os.walk scanner, file links are followed,
        directory links are not descended, and a selected root may itself be a
        directory link. Hidden names are included. Failures and cancellation
        remain explicit so an incomplete scan cannot silently replace a catalog.
        """
        if progress_interval < 0:
            raise ValueError("The progress interval cannot be negative")
        root_path = Path(root_path)
        index = cls(root_path, use_hash, hash_algo)
        last_progress = 0.0

        def cancelled():
            if cancel_event is not None and cancel_event.is_set():
                index.cancelled = True
            return index.cancelled

        def progress(path, *, force=False):
            nonlocal last_progress
            if progress_callback is None:
                return
            now = time.monotonic()
            if force or now - last_progress >= progress_interval:
                last_progress = now
                progress_callback(index.total_files, path)

        if cancelled():
            return index
        progress(root_path, force=True)
        if cancelled():
            return index
        try:
            root_info = root_path.stat()
            if not stat.S_ISDIR(root_info.st_mode):
                raise NotADirectoryError(f"Not a directory: {root_path}")
            index.directory_mtimes[root_path] = int(root_info.st_mtime)
        except OSError as error:
            index._record_scan_error(root_path, error)
            return index

        pending = [root_path]
        while pending and not cancelled():
            directory = pending.pop()
            # Recheck queued folders before descent, just as os.walk does when
            # followlinks=False. The chosen root keeps its historical behavior.
            subdirectories = []
            try:
                if directory != root_path and directory.is_symlink():
                    index._record_scan_error(directory, "The folder became a symbolic link before it was scanned")
                    continue
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if cancelled():
                            break
                        path = directory / entry.name
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                info = entry.stat(follow_symlinks=False)
                                if not stat.S_ISDIR(info.st_mode):
                                    raise OSError("The folder changed while its metadata was read")
                                index.directory_mtimes[path] = int(info.st_mtime)
                                subdirectories.append(path)
                            else:
                                # File symlinks retain the original target-size
                                # and target-hash semantics. Special files and
                                # links to directories are never opened/read.
                                index.add_file(path, stat_info=entry.stat(), cancel_event=cancel_event)
                        except OSError as error:
                            index._record_scan_error(path, error)
                        progress(path)
            except OSError as error:
                index._record_scan_error(directory, error)
            # Preserve os.walk's depth-first directory order without recursion.
            pending.extend(reversed(subdirectories))
        cancelled()
        progress(root_path, force=True)
        cancelled()
        return index

    def add_file(self, file_path: Path, *, stat_info: Optional[os.stat_result] = None, cancel_event=None) -> bool:
        """Add a file, optionally using metadata already obtained by a scan."""
        try:
            if cancel_event is not None and cancel_event.is_set():
                self.cancelled = True
                return False
            if stat_info is None:
                stat_info = file_path.stat()
            if not stat.S_ISREG(stat_info.st_mode):
                return False

            file_size = stat_info.st_size
            mtime = int(stat_info.st_mtime)

            file_hash = ""
            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo, cancel_event=cancel_event)
                if not file_hash:
                    if cancel_event is not None and cancel_event.is_set():
                        self.cancelled = True
                    else:
                        self._record_scan_error(file_path, f"Could not calculate the {self.hash_algo} hash")
                    return False

            entry = FileEntry(file_path, file_size, mtime, file_hash)

            # Add to all structures
            self.size_index[file_size].append(entry)
            self.all_files.append(entry)
            if self.use_hash:
                self.hash_index[(file_size, file_hash)].append(entry)

            self.total_files += 1
            if self.is_optimized:
                self.is_optimized = False
                self.prefix_index = []
                self.suffix_index = []
            return True
        except OSError as error:
            self._record_scan_error(file_path, error)
            return False

    def build_optimized_indices(self):
        """
        Builds O(log N) search structures. Call this once after loading.
        """
        if self.is_optimized or not self.all_files:
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
        names = [(e.path.name.lower(), e) for e in self.all_files]
        self.prefix_index = sorted(names, key=lambda x: x[0])

        # 2. Suffix Index: Sort by REVERSED lowercase name for '*.ext' queries
        self.suffix_index = sorted([(name[::-1], entry) for name, entry in names], key=lambda x: x[0])

        self.is_optimized = True
        elapsed = time.time() - t0
        print(f" Done in {elapsed:.2f}s", file=sys.stderr)

    def _write_caf(self, caf_path, elm, info, cancel_event=None):
        """Write beside the destination and replace it only after a full flush."""
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{caf_path.name}.", suffix=".tmp", dir=caf_path.parent, delete=False
            ) as buffer:
                temporary_path = Path(buffer.name)
                self._write_caf_stream(buffer, elm, info, cancel_event)
                buffer.flush()
                os.fsync(buffer.fileno())
            self._check_save_cancelled(cancel_event)
            os.replace(temporary_path, caf_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _write_caf_stream(self, buffer, elm, info, cancel_event):
        self._check_save_cancelled(cancel_event)
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
            self._check_save_cancelled(cancel_event)
            if i == 0:
                self._write_string(buffer, "")
            buffer.write(struct.pack("<l", fc))
            buffer.write(struct.pack("<d", ts))
        buffer.write(struct.pack("<l", len(elm)))
        for mtime, size, parent_id, name in elm:
            self._check_save_cancelled(cancel_event)
            buffer.write(struct.pack("<LqL", mtime, size, parent_id))
            self._write_string(buffer, name)

    @classmethod
    def load_from_caf(
        cls, caf_path: Path, use_hash: bool, hash_algo: str, *, build_search_indices: bool = True
    ) -> Optional["FileIndex"]:
        """Load a complete CAF, including empty folders and zero-byte files.

        CAF stores Latin-1 names and integer-second mtimes, but no file hashes.
        The optional sort switch lets a caller merge multiple catalogs before
        constructing the combined search indexes once.
        """
        try:
            with caf_path.open("rb") as buffer:
                magic = struct.unpack("<L", buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase):
                    return None
                version = magic // cls.ulModus
                if version > 2:
                    version = struct.unpack("<h", buffer.read(2))[0]

                if not 0 <= version <= cls.saveVersion:
                    return None

                struct.unpack("<L", buffer.read(4))  # catalog creation time
                device = cls._read_string(buffer) if version >= 2 else ""
                is_windows = "\\" in device or (len(device) > 1 and device[1] == ":")
                path_class = PureWindowsPath if is_windows else PurePosixPath
                index = cls(path_class(device), use_hash, hash_algo)
                # The root folder's mtime is not represented in CAF.
                index.directory_mtimes[index.root_path] = 0

                cls._read_string(buffer)  # volume
                cls._read_string(buffer)  # alias
                struct.unpack("<L", buffer.read(4))  # serial
                if version >= 4:
                    cls._read_string(buffer)
                if version >= 1:
                    struct.unpack("<f", buffer.read(4))
                if version >= 6:
                    struct.unpack("<h", buffer.read(2))

                dir_count = struct.unpack("<l", buffer.read(4))[0]
                if dir_count < 0:
                    raise ValueError("Negative directory count")
                for i in range(dir_count):
                    if i == 0 or version <= 3:
                        cls._read_string(buffer)
                    if version >= 3:
                        struct.unpack("<ld", buffer.read(12))

                data = buffer.read()
                file_count = struct.unpack_from("<l", data, 0)[0]
                offset = 4
                if version <= 6:
                    entry_struct = struct.Struct("<LlH")
                elif version == 7:
                    entry_struct = struct.Struct("<LqH")
                else:
                    entry_struct = struct.Struct("<LqL")
                if file_count < 0 or file_count > (len(data) - offset) // (entry_struct.size + 1):
                    raise ValueError("Truncated or invalid CAF entry count")

                raw_entries = []
                for _ in range(file_count):
                    mtime, size, parent_id = entry_struct.unpack_from(data, offset)
                    offset += entry_struct.size
                    end = data.find(b"\x00", offset)
                    if end == -1:
                        raise ValueError("Unterminated CAF entry name")
                    name = data[offset:end].decode("latin-1")
                    cls._validate_caf_name(name)
                    raw_entries.append((mtime, size, parent_id, name))
                    offset = end + 1

                # Legacy CAF identifies folders by the entry IDs referenced as
                # parents. Modern versions encode a folder ID as a negative size.
                referenced_ids = {parent for _, _, parent, _ in raw_entries}
                directories = {}
                files = []
                for i, (mtime, size, parent, name) in enumerate(raw_entries):
                    is_directory = (size < 0) if version > 6 else (i + 1) in referenced_ids
                    if is_directory:
                        directory_id = -size if version > 6 else i + 1
                        if directory_id in directories:
                            raise ValueError("Duplicate CAF directory ID")
                        directories[directory_id] = (parent, name, mtime)
                    else:
                        # Keep the historical pre-v7 unknown-size convention.
                        actual_size = 1024 if version <= 6 and size == 0 else size
                        files.append((mtime, actual_size, parent, name))

                # Resolve parents in linear time, even for forward references.
                # A missing parent or cycle rejects the whole damaged catalog;
                # silently dropping orphan files would look like a complete scan.
                children = defaultdict(list)
                for directory_id, (parent, name, mtime) in directories.items():
                    if parent != 0 and parent not in directories:
                        raise ValueError("Unknown CAF parent directory")
                    children[parent].append((directory_id, name, mtime))
                dir_paths = {0: index.root_path}
                pending = [0]
                while pending:
                    parent_id = pending.pop()
                    for directory_id, name, mtime in children[parent_id]:
                        path = dir_paths[parent_id] / name
                        dir_paths[directory_id] = path
                        index.directory_mtimes[path] = mtime
                        pending.append(directory_id)
                if len(dir_paths) != len(directories) + 1:
                    raise ValueError("Cyclic CAF directory hierarchy")

                for mtime, size, parent, name in files:
                    if parent not in dir_paths:
                        raise ValueError("Unknown CAF file parent")
                    entry = FileEntry(dir_paths[parent] / name, size, mtime, "")
                    index.size_index[size].append(entry)
                    index.all_files.append(entry)
                index.total_files = len(index.all_files)
                if build_search_indices:
                    index.build_optimized_indices()
                return index
        except (OSError, ValueError, struct.error, OverflowError) as error:
            print(f"[CAF] Error: {error}", file=sys.stderr)
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
                if not 0 <= version <= cls.saveVersion:
                    return None

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

            except (struct.error, OSError, IndexError, ValueError, OverflowError):
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

    def save_to_caf(self, caf_path: Path, *, cancel_event=None):
        """Atomically save a complete index in the Cathy-compatible v8 format.

        The classic format cannot represent names outside Latin-1. Reject those
        names, unsafe paths, and out-of-range metadata rather than replacing
        characters or overwriting a previous good catalog with partial data.
        """
        self._check_save_cancelled(cancel_event)
        if self.cancelled:
            raise InterruptedError("Catalog creation cancelled")
        if self.scan_error_count:
            raise ValueError("Cannot save an incomplete scan; resolve its scan errors and try again")
        caf_path = Path(caf_path)
        self._validate_caf_text(str(self.root_path))
        self._validate_caf_text(self.root_path.name)

        all_entries = [entry for entries in self.size_index.values() for entry in entries]
        directories = {self.root_path}

        def include_directory(directory):
            relative = directory.relative_to(self.root_path)
            for component in relative.parts:
                self._validate_caf_name(component)
            while directory not in directories:
                directories.add(directory)
                directory = directory.parent

        # Retain empty folders and every ancestor, even when only a deep leaf
        # contains files. The original writer only kept the immediate parents.
        for directory in self.directory_mtimes:
            self._check_save_cancelled(cancel_event)
            include_directory(directory)
        for entry in all_entries:
            self._check_save_cancelled(cancel_event)
            relative = entry.path.relative_to(self.root_path)
            if not relative.parts:
                raise ValueError("A catalog file cannot be its own root folder")
            for component in relative.parts:
                self._validate_caf_name(component)
            if not 0 <= entry.size <= 0x7FFFFFFFFFFFFFFF:
                raise ValueError(f"CAF cannot represent this file size: {entry.path}")
            self._validate_caf_mtime(entry.mtime, entry.path)
            include_directory(entry.path.parent)

        # Sorting by depth makes parent IDs available before their children and
        # gives deterministic serialization without any second filesystem walk.
        ordered_dirs = sorted(directories - {self.root_path}, key=lambda path: (len(path.parts), str(path)))
        dir_id_map = {self.root_path: 0}
        dir_id_map.update((path, i) for i, path in enumerate(ordered_dirs, 1))
        if len(dir_id_map) > 0x7FFFFFFF or len(all_entries) + len(ordered_dirs) > 0x7FFFFFFF:
            raise ValueError("Too many entries for the CAF format")

        elements = []
        stats = [[0, 0] for _ in dir_id_map]
        for directory in ordered_dirs:
            self._check_save_cancelled(cancel_event)
            mtime = self.directory_mtimes.get(directory)
            if mtime is None:
                # Compatibility for callers that construct an index with
                # add_file(). Scans and loaded catalogs already have metadata.
                mtime = int(Path(directory).stat().st_mtime)
            self._validate_caf_mtime(mtime, directory)
            elements.append((mtime, -dir_id_map[directory], dir_id_map[directory.parent], directory.name))
        for entry in all_entries:
            self._check_save_cancelled(cancel_event)
            parent_id = dir_id_map[entry.path.parent]
            elements.append((entry.mtime, entry.size, parent_id, entry.path.name))
            stats[parent_id][0] += 1
            stats[parent_id][1] += entry.size
        info = [(directory_id, count, size) for directory_id, (count, size) in enumerate(stats)]
        info[0] = (0, len(all_entries), sum(entry.size for entry in all_entries))
        self._write_caf(caf_path, elements, info, cancel_event)

    @staticmethod
    def _check_save_cancelled(cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Catalog creation cancelled")

    @staticmethod
    def _validate_caf_mtime(mtime, path):
        if not isinstance(mtime, int) or not 0 <= mtime <= 0xFFFFFFFF:
            raise ValueError(f"CAF requires a timestamp from 1970 through 2106: {path}")

    @staticmethod
    def _validate_caf_text(text):
        if "\x00" in text:
            raise ValueError("CAF names and paths cannot contain a NUL character")
        try:
            text.encode("latin-1")
        except UnicodeEncodeError as error:
            raise ValueError(f"CAF supports Latin-1 names only; this name cannot be saved: {text!r}") from error

    @classmethod
    def _validate_caf_name(cls, name):
        cls._validate_caf_text(name)
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            raise ValueError(f"Invalid CAF path component: {name!r}")

    # --- Private static I/O helpers ---
    @staticmethod
    def _read_string(buffer) -> str:
        chars = bytearray()
        while (char := buffer.read(1)) != b"\x00":
            if not char:
                raise ValueError("Unterminated CAF string")
            chars.extend(char)
        return chars.decode("latin-1")

    @classmethod
    def _write_string(cls, buffer, text: str):
        cls._validate_caf_text(text)
        buffer.write(text.encode("latin-1"))
        buffer.write(b"\x00")
