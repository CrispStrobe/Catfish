# core/file_index.py

"""File indexing and CAF format handling."""
import struct
import time
from pathlib import Path, PureWindowsPath, PurePosixPath
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import stat
from datetime import datetime as dt

from core.data_structures import FileEntry, DuplicateMatch
from utils.file_utils import calculate_file_hash, path_is_native_and_exists, format_size

class FileIndex:
    """
    Manages file metadata with O(1) duplicate lookups and O(log N) search indices.
    """
    ulMagicBase = 500410407
    ulModus = 1000000000
    saveVersion = 8

    def __init__(self, root_path: Path, use_hash: bool = False, hash_algo: str = 'md5'):
        self.root_path = root_path
        self.use_hash = use_hash
        self.hash_algo = hash_algo
        
        # O(1) Lookup for Duplicates: {size_bytes: [entries]}
        self.size_index: Dict[int, List[FileEntry]] = defaultdict(list)
        self.hash_index: Dict[Tuple[int, str], List[FileEntry]] = defaultdict(list)
        
        # O(N) Linear Scan List (Fastest iteration)
        self.all_files: List[FileEntry] = []

        # O(log N) Binary Search Indices
        self.is_optimized = False
        self.prefix_index: List[Tuple[str, FileEntry]] = []  # Sorted by name
        self.suffix_index: List[Tuple[str, FileEntry]] = []  # Sorted by reversed name
        
        self.total_files = 0

    def add_file(self, file_path: Path) -> bool:
        """Adds a file to the in-memory index."""
        try:
            stat_info = file_path.stat()
            if not stat.S_ISREG(stat_info.st_mode): return False
            
            file_size = stat_info.st_size
            mtime = int(stat_info.st_mtime)
            
            file_hash = ""
            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash: return False

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
        if not self.all_files: return

        print(f"[INDEX] Optimization: Sorting {len(self.all_files)} items for Binary Search...", end='', flush=True)
        t0 = time.time()

        # 1. Prefix Index: Sort by lowercase name for 'start*' queries
        # We store tuples (key, entry) to allow bisecting on the key
        self.prefix_index = sorted(
            [(e.path.name.lower(), e) for e in self.all_files],
            key=lambda x: x[0]
        )

        # 2. Suffix Index: Sort by REVERSED lowercase name for '*.ext' queries
        self.suffix_index = sorted(
            [(e.path.name.lower()[::-1], e) for e in self.all_files],
            key=lambda x: x[0]
        )
        
        self.is_optimized = True
        dt = time.time() - t0
        print(f" Done in {dt:.2f}s")

    def _write_caf(self, caf_path, elm, info):
        with caf_path.open('wb') as buffer:
            buffer.write(struct.pack('<L', 3 * self.ulModus + self.ulMagicBase))
            buffer.write(struct.pack('<h', self.saveVersion))
            buffer.write(struct.pack('<L', int(time.time())))
            self._write_string(buffer, str(self.root_path))
            self._write_string(buffer, self.root_path.name)
            self._write_string(buffer, self.root_path.name)
            buffer.write(struct.pack('<L', 0))
            self._write_string(buffer, f"Universal Search Index")
            buffer.write(struct.pack('<f', 0.0))
            buffer.write(struct.pack('<h', 0))
            buffer.write(struct.pack('<l', len(info)))
            for i, (dir_id, fc, ts) in enumerate(info):
                if i == 0: self._write_string(buffer, "")
                buffer.write(struct.pack('<l', fc))
                buffer.write(struct.pack('<d', ts))
            buffer.write(struct.pack('<l', len(elm)))
            for mtime, size, parent_id, name in elm:
                buffer.write(struct.pack('<L', mtime))
                buffer.write(struct.pack('<q', size))
                buffer.write(struct.pack('<L', parent_id))
                self._write_string(buffer, name)
    
    @classmethod
    def load_from_caf(cls, caf_path: Path, use_hash: bool, hash_algo: str) -> Optional['FileIndex']:
        """Loads index from CAF file with optimized buffered reading."""
        if not caf_path.is_file(): return None
        
        with caf_path.open('rb') as buffer:
            try:
                # Header Check
                magic = struct.unpack('<L', buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase): return None
                version = int(magic / cls.ulModus)
                if version > 2: version = struct.unpack('<h', buffer.read(2))[0]
                if version > cls.saveVersion: return None

                # Header Skip
                buffer.read(4) 
                device = cls._read_string(buffer) if version >= 2 else ""
                
                # Path Logic
                is_windows = '\\' in device or (len(device) > 1 and device[1] == ':')
                PathClass = PureWindowsPath if is_windows else PurePosixPath
                index = cls(PathClass(device), use_hash, hash_algo)
                
                # Metadata Skip
                cls._read_string(buffer) # volume
                cls._read_string(buffer) # alias
                buffer.read(4) # serial
                cls._read_string(buffer) if version >= 4 else ""
                if version >= 1: buffer.read(4)
                if version >= 6: buffer.read(2)

                dir_count = struct.unpack('<l', buffer.read(4))[0]
                for i in range(dir_count):
                    if i == 0 or version <= 3: cls._read_string(buffer)
                    if version >= 3: buffer.read(12)

                # --- FAST BODY PARSING ---
                data = buffer.read()
                offset = 0
                max_offset = len(data)

                file_count = struct.unpack_from('<l', data, offset)[0]
                offset += 4
                
                raw_elm = []
                
                # Determine struct format
                if version <= 6: fmt, step = '<LlH', 10
                elif version <= 7: fmt, step = '<LqH', 14
                else: fmt, step = '<LqL', 16

                # Vectorized loop
                for _ in range(file_count):
                    if offset + step > max_offset: break
                    mtime, size, parent_id = struct.unpack_from(fmt, data, offset)
                    offset += step
                    
                    end_pos = data.find(b'\x00', offset)
                    if end_pos == -1: filename = ""
                    else:
                        filename = data[offset:end_pos].decode('latin-1', errors='replace')
                        offset = end_pos + 1
                    
                    raw_elm.append((mtime, size, parent_id, filename))

                # Directory Reconstruction
                referenced_parent_ids = {pid for _, _, pid, _ in raw_elm}
                dir_path_map = {0: index.root_path}
                
                # 1. Build Dirs
                for i, (mtime, size, pid, name) in enumerate(raw_elm):
                    is_dir = (version > 6 and size < 0) or (version <= 6 and (i+1) in referenced_parent_ids)
                    if is_dir:
                        dir_id = -size if version > 6 else (i+1)
                        if pid in dir_path_map and name:
                            dir_path_map[dir_id] = dir_path_map[pid] / name

                # 2. Add Files
                for i, (mtime, size, pid, name) in enumerate(raw_elm):
                    is_dir = (version > 6 and size < 0) or (version <= 6 and (i+1) in referenced_parent_ids)
                    if not is_dir and pid in dir_path_map and name.strip():
                        path = dir_path_map[pid] / name
                        actual_size = max(size, 1) if version > 6 else (max(size, 1024) if size == 0 else size)
                        
                        entry = FileEntry(path, actual_size, mtime, "")
                        index.size_index[actual_size].append(entry)
                        index.total_files += 1

                # Final Optimization Step
                index._flatten_index()
                index.build_optimized_indices() # Build O(log N) structures
                
                return index
                
            except Exception as e:
                print(f"[CAF] Error: {e}")
                return None

    def _flatten_index(self):
        """Populates the flat all_files list."""
        if not self.all_files and self.size_index:
            self.all_files = [entry for bucket in self.size_index.values() for entry in bucket]

    @staticmethod 
    def _read_caf_string_fast(buffer) -> str:
        """Fast string reading like original Cathy - latin-1 for speed."""
        chars = bytearray()
        while True:
            char = buffer.read(1)
            if not char or char == b'\x00':
                break
            chars.extend(char)
        return chars.decode('latin-1', errors='replace')

    def _ensure_indexes_built(self):
        """This method is no longer needed since we build indexes during load."""
        pass
    
    def _ensure_indexes_built_really(self):
        """Build search indexes on-demand, not during load."""
        # Check if we need to build indexes
        if not hasattr(self, '_indexes_built'):
            return  # For newly created indexes, no need to build from raw_elm
            
        if self._indexes_built:
            return  # Already built
            
        if not hasattr(self, 'raw_elm'):
            return  # No raw data to build from
            
        # Build directory path map first (like original)
        dir_path_map = {0: self.root_path}
        
        # First pass: build directory structure
        for mtime, size, parent_id, filename in self.raw_elm:
            if size < 0:  # Directory
                dir_id = -size
                if parent_id in dir_path_map:
                    dir_path_map[dir_id] = dir_path_map[parent_id] / filename
        
        # Second pass: build search indexes
        self.size_index.clear()
        self.hash_index.clear()
        
        for mtime, size, parent_id, filename in self.raw_elm:
            if size >= 0 and parent_id in dir_path_map:  # It's a file
                path = dir_path_map[parent_id] / filename
                
                # Get actual size for legacy CAF files
                actual_size = size
                if size == 0 and path_is_native_and_exists(path):
                    try:
                        actual_size = Path(path).stat().st_size
                    except OSError:
                        actual_size = 0
                
                # Calculate hash only if needed and file exists
                entry_hash = ""
                if self.use_hash and path_is_native_and_exists(path):
                    entry_hash = calculate_file_hash(Path(path), self.hash_algo)
                
                # Create entry and add to indexes
                entry = FileEntry(path, actual_size, mtime, entry_hash)
                self.size_index[actual_size].append(entry)
                
                if self.use_hash and entry_hash:
                    self.hash_index[(actual_size, entry_hash)].append(entry)
        
        self._indexes_built = True

    @classmethod
    def load_metadata_only(cls, caf_path: Path) -> Optional[Dict]:
        """Fast metadata extraction without loading file entries."""
        if not caf_path.is_file():
            return None
        
        with caf_path.open('rb') as buffer:
            try:
                # Header validation
                magic = struct.unpack('<L', buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase):
                    return None
                version = int(magic / cls.ulModus)
                if version > 2:
                    version = struct.unpack('<h', buffer.read(2))[0]
                
                # Quick header parsing
                created_timestamp = struct.unpack('<L', buffer.read(4))[0]
                device = cls._read_caf_string_fast(buffer) if version >= 2 else ""
                volume = cls._read_caf_string_fast(buffer)
                alias = cls._read_caf_string_fast(buffer)
                buffer.read(4)  # serial
                comment = cls._read_caf_string_fast(buffer) if version >= 4 else ""
                freesize = struct.unpack('<f', buffer.read(4))[0] if version >= 1 else 0
                archive = struct.unpack('<h', buffer.read(2))[0] if version >= 6 else 0
                
                # Get file count from info block
                dir_count = struct.unpack('<l', buffer.read(4))[0]
                file_count = 0
                total_size = 0
                
                if dir_count > 0:
                    cls._read_caf_string_fast(buffer)  # Skip root dir name
                    file_count = struct.unpack('<l', buffer.read(4))[0]
                    total_size = int(struct.unpack('<d', buffer.read(8))[0])
                
                return {
                    'device': device,
                    'volume': volume,
                    'file_count': file_count,
                    'total_size': total_size,
                    'created_date': dt.fromtimestamp(created_timestamp),
                    'archive': archive,
                    'freesize': freesize
                }
                
            except (struct.error, OSError, IndexError):
                return None
            
    def find_potential_duplicates_optimized(self, file_path: Path) -> List[FileEntry]:
        try:
            stat_info = file_path.stat()
            file_size = stat_info.st_size
        except OSError: return []
        
        # O(1) lookup in size_index
        if file_size not in self.size_index: return []
        
        if self.use_hash:
            return self._find_hash_duplicates_optimized(file_path, file_size)
        else:
            return [e for e in self.size_index[file_size] if e.path.name == file_path.name]

    def _find_hash_duplicates_optimized(self, file_path: Path, file_size: int) -> List[FileEntry]:
        # Pre-filter by size (O(1))
        candidates = self.size_index[file_size]
        if not candidates: return []
        
        source_hash = calculate_file_hash(file_path, self.hash_algo)
        if not source_hash: return []
        
        matches = []
        for entry in candidates:
            if path_is_native_and_exists(entry.path):
                # Calculate hash only on demand
                h = calculate_file_hash(Path(entry.path), self.hash_algo)
                if h == source_hash:
                    matches.append(FileEntry(entry.path, entry.size, entry.mtime, h))
        return matches
   
    def _find_hash_duplicates_optimized(self, file_path: Path, file_size: int) -> List[FileEntry]:
        """Hash-based duplicate detection with on-demand hash calculation."""
        
        # Step 1: Quick size pre-filtering (this part is correct)
        size_candidates = []
        if hasattr(self, 'raw_elm'):
            dir_path_map = self._get_or_build_dir_map()
            for mtime, size, parent_id, filename in self.raw_elm:
                if size == file_size and size >= 0 and parent_id in dir_path_map:
                    candidate_path = dir_path_map[parent_id] / filename
                    size_candidates.append((candidate_path, mtime, size))
        else:
            self._ensure_indexes_built()
            size_candidates = [(entry.path, entry.mtime, entry.size) for entry in self.size_index.get(file_size, [])]

        if not size_candidates:
            return []
        
        # Step 2: Calculate hash for the source file only once
        source_hash = calculate_file_hash(file_path, self.hash_algo)
        if not source_hash:
            return []
        
        # Step 3: Calculate hashes ONLY for candidates that exist locally
        matches = []
        for candidate_path, mtime, size in size_candidates:
            # FIX: Only proceed if the file exists on the current system
            if path_is_native_and_exists(candidate_path):
                # Calculate hash only for existing, size-matched files
                candidate_hash = calculate_file_hash(Path(candidate_path), self.hash_algo)
                if candidate_hash and candidate_hash == source_hash:
                    matches.append(FileEntry(candidate_path, size, mtime, candidate_hash))
            # If the file doesn't exist locally, we can't verify its hash, so it's NOT a match.
            
        return matches

    def _find_name_duplicates_optimized(self, file_path: Path, file_size: int) -> List[FileEntry]:
        """Name-based duplicate detection for when hashes are disabled."""
        matches = []
        
        if hasattr(self, 'raw_elm'):
            dir_path_map = self._get_or_build_dir_map()
            for mtime, size, parent_id, filename in self.raw_elm:
                if (size == file_size and size >= 0 and 
                    filename == file_path.name and parent_id in dir_path_map):
                    candidate_path = dir_path_map[parent_id] / filename
                    matches.append(FileEntry(candidate_path, size, mtime, ""))
        else:
            # Fall back to existing approach
            self._ensure_indexes_built()
            matches = [e for e in self.size_index.get(file_size, []) if e.path.name == file_path.name]
        
        return matches

    def _get_or_build_dir_map(self):
        """Build directory path map once and cache it."""
        if hasattr(self, '_dir_path_map'):
            return self._dir_path_map
        
        dir_path_map = {0: self.root_path}
        
        if hasattr(self, 'raw_elm'):
            # Build from raw elm data
            for mtime, size, parent_id, filename in self.raw_elm:
                if size < 0:  # Directory
                    dir_id = -size
                    if parent_id in dir_path_map:
                        dir_path_map[dir_id] = dir_path_map[parent_id] / filename
        
        self._dir_path_map = dir_path_map
        return dir_path_map
    
    @staticmethod
    def find_all_duplicates_bulk(source_index: 'FileIndex', dest_index: 'FileIndex', 
                        progress_callback=None, cancel_event=None) -> List[DuplicateMatch]:
        """
        Bulk duplicate detection optimized for scanning operations.
        Processes files in batches and calculates hashes strategically.
        """
        from collections import defaultdict
        
        duplicates = []
        
        # Get source files, grouped by size for efficiency
        source_files_by_size = defaultdict(list)
        
        if hasattr(source_index, 'raw_elm'):
            dir_map = source_index._get_or_build_dir_map()
            for mtime, size, parent_id, filename in source_index.raw_elm:
                if size >= 0 and parent_id in dir_map:  # Regular file
                    file_path = dir_map[parent_id] / filename
                    if path_is_native_and_exists(file_path):
                        source_files_by_size[size].append(Path(file_path))
        else:
            # Fall back to traditional approach
            for file_path in source_index.root_path.rglob('*'):
                if file_path.is_file():
                    try:
                        size = file_path.stat().st_size
                        source_files_by_size[size].append(file_path)
                    except OSError:
                        continue
        
        total_files = sum(len(files) for files in source_files_by_size.values())
        processed = 0
        
        # Process each size group
        for size, source_files in source_files_by_size.items():
            if cancel_event and cancel_event.is_set():
                break
                
            if progress_callback:
                progress_callback("Finding duplicates", f"Processing {len(source_files)} files of size {format_size(size)}")
            
            # Find potential destination matches by size first
            dest_candidates = []
            if hasattr(dest_index, 'raw_elm'):
                dest_dir_map = dest_index._get_or_build_dir_map()
                for mtime, dest_size, parent_id, filename in dest_index.raw_elm:
                    if dest_size == size and dest_size >= 0 and parent_id in dest_dir_map:
                        dest_path = dest_dir_map[parent_id] / filename
                        dest_candidates.append((dest_path, mtime, dest_size))
            else:
                dest_candidates = [(entry.path, entry.mtime, entry.size) for entry in dest_index.size_index.get(size, [])]
            
            if not dest_candidates:
                processed += len(source_files)
                continue
            
            # Now process source files of this size
            for source_file in source_files:
                if cancel_event and cancel_event.is_set():
                    break
                    
                processed += 1
                if progress_callback and processed % 50 == 0:
                    progress_callback("Finding duplicates", f"Checked {processed}/{total_files} files ({len(duplicates)} duplicates found)")
                
                # Use optimized duplicate detection
                matches = dest_index.find_potential_duplicates_optimized(source_file)
                
                if matches:
                    duplicates.append(DuplicateMatch(
                        source_file=source_file,
                        destinations=matches
                    ))
        
        return duplicates


    def find_potential_duplicates(self, file_path: Path) -> List[FileEntry]:
        """Finds potential duplicates of a given file in the index."""
        try:
            stat_info = file_path.stat()
            file_size = stat_info.st_size
            
            if file_size not in self.size_index:
                return []
            
            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash: 
                    return []
                return self.hash_index.get((file_size, file_hash), [])
            else:
                # Fallback to name comparison if not using hashes
                return [e for e in self.size_index[file_size] if e.path.name == file_path.name]
        except OSError:
            return []

    # --- CAF Serialization Methods ---

    def save_to_caf(self, caf_path: Path):
        """
        Saves the current in-memory index to a Cathy-compatible .caf file.
        """
        # 1. Prepare directory structure and metadata
        dir_id_map: Dict[Path, int] = {self.root_path: 0}
        next_dir_id = 1
        
        all_entries: List[FileEntry] = [e for entries in self.size_index.values() for e in entries]
        
        # Discover all unique directories and assign IDs
        all_dirs = {entry.path.parent for entry in all_entries}
        for d in sorted(all_dirs, key=lambda p: len(p.parts)):
            if d not in dir_id_map:
                dir_id_map[d] = next_dir_id
                next_dir_id += 1
        
        # 2. Build the `elm` list (all files and directories)
        elm = []
        dir_stats = defaultdict(lambda: {'file_count': 0, 'total_size': 0})

        # Add directories to elm list first
        for dir_path, dir_id in dir_id_map.items():
            if dir_id == 0: continue
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
                dir_stats[parent_id]['file_count'] += 1
                dir_stats[parent_id]['total_size'] += entry.size
            except KeyError:
                continue

        # 3. Build the `info` list (directory summaries)
        info = [(0, 0, 0)] * next_dir_id # Pre-allocate list
        for dir_id, stats in dir_stats.items():
            info[dir_id] = (dir_id, stats['file_count'], stats['total_size'])
        
        # Set root directory info (aggregate all stats)
        total_file_count = sum(s['file_count'] for s in dir_stats.values())
        total_catalog_size = sum(s['total_size'] for s in dir_stats.values())
        info[0] = (0, total_file_count, total_catalog_size)

        # 4. Write the CAF file
        self._write_caf(caf_path, elm, info)

    

    @classmethod
    def load_from_caf_old(cls, caf_path: Path, use_hash: bool, hash_algo: str) -> Optional['FileIndex']:
        """
        Loads an index from a .caf file, efficiently populating the in-memory
        dictionaries without re-scanning the disk.
        """
        if not caf_path.is_file(): return None
        
        with caf_path.open('rb') as buffer:
            try:
                # Header validation
                magic = struct.unpack('<L', buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase): return None
                version = int(magic / cls.ulModus)
                if version > 2: 
                    version = struct.unpack('<h', buffer.read(2))[0]
                if version > cls.saveVersion: return None

                # Header parsing
                buffer.read(4) # Skip date
                device = cls._read_string(buffer) if version >= 2 else ""
                
                # Platform-independent path handling
                is_windows_path = '\\' in device or (len(device) > 1 and device[1] == ':')
                PathClass = PureWindowsPath if is_windows_path else PurePosixPath
                index = cls(PathClass(device), use_hash, hash_algo)
                
                cls._read_string(buffer) # volume
                cls._read_string(buffer) # alias
                buffer.read(4) # serial
                comment = cls._read_string(buffer) if version >= 4 else ""
                if version >= 1: buffer.read(4) # freesize
                if version >= 6: buffer.read(2) # archive

                # Skip info block
                dir_count = struct.unpack('<l', buffer.read(4))[0]
                for i in range(dir_count):
                    if i == 0 or version <= 3: cls._read_string(buffer)
                    if version >= 3: buffer.read(12) # file_count, total_size

                # Rebuild directory structure from elm
                dir_path_map = {0: index.root_path}
                file_count = struct.unpack('<l', buffer.read(4))[0]
                raw_elm = []
                for _ in range(file_count):
                    mtime = struct.unpack('<L', buffer.read(4))[0]
                    
                    # Handle legacy CAF versions that don't store file sizes
                    if version <= 6:
                        size = 0  # Legacy versions don't have size information
                    else:
                        size = struct.unpack('<q', buffer.read(8))[0]
                    
                    # Handle different parent ID formats by version
                    if version > 7:
                        parent_id = struct.unpack('<L', buffer.read(4))[0]
                    else:
                        parent_id = struct.unpack('<H', buffer.read(2))[0]
                    
                    filename = cls._read_string(buffer)
                    raw_elm.append((mtime, size, parent_id, filename))

                # First pass: build directory path map
                for _, size, parent_id, name in raw_elm:
                    if size < 0: # It's a directory
                        dir_id = -size
                        if parent_id in dir_path_map:
                            dir_path_map[dir_id] = dir_path_map[parent_id] / name

                # Second pass: populate the index
                for mtime, size, parent_id, name in raw_elm:
                    if size >= 0 and parent_id in dir_path_map:
                        path = dir_path_map[parent_id] / name
                        path_exists = path_is_native_and_exists(path)
                        concrete_path = Path(path) if path_exists else None
                        
                        # For legacy CAF files without size info, try to get actual size if file exists
                        actual_size = size
                        if version <= 6 and size == 0 and path_exists:
                            try:
                                actual_size = concrete_path.stat().st_size
                            except OSError:
                                actual_size = 0
                        
                        entry_hash = ""
                        if use_hash and path_exists:
                            # Hashes are not stored in CAF, must be calculated on demand
                            entry_hash = calculate_file_hash(concrete_path, hash_algo)
                        
                        entry = FileEntry(path, actual_size, mtime, entry_hash)
                        index.size_index[actual_size].append(entry)
                        if use_hash and entry_hash:
                            index.hash_index[(actual_size, entry_hash)].append(entry)
                        index.total_files += 1

                return index
            except (struct.error, OSError, IndexError):
                return None
    
    # --- Private static I/O helpers ---
    @staticmethod 
    def _read_string(buffer) -> str:
        chars = bytearray()
        while (char := buffer.read(1)) != b'\x00':
            if not char: break
            chars.extend(char)
        return chars.decode('latin-1', errors='replace')
    @staticmethod
    def _write_string(buffer, text: str):
        buffer.write(text.encode('latin-1', errors='replace'))
        buffer.write(b'\x00')
    
    

    