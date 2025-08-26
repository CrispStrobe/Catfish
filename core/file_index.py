# core/file_index.py

"""File indexing and CAF format handling."""
import os
import time
import struct
from pathlib import Path, PureWindowsPath, PurePosixPath
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import stat
from datetime import datetime as dt

from core.data_structures import FileEntry, DuplicateMatch
from utils.file_utils import calculate_file_hash, path_is_native_and_exists, format_size

class FileIndex:
    """
    Manages file metadata for fast lookups and handles reading/writing 
    the .caf index file format for persistence and compatibility.
    """
    # CAF format constants for compatibility
    ulMagicBase = 500410407
    ulModus = 1000000000
    saveVersion = 8
    delim = b'\x00'

    def __init__(self, root_path: Path, use_hash: bool = False, hash_algo: str = 'md5'):
        self.root_path = root_path
        self.use_hash = use_hash
        self.hash_algo = hash_algo
        
        # In-memory dictionaries for fast duplicate lookups
        self.size_index: Dict[int, List[FileEntry]] = defaultdict(list)
        self.hash_index: Dict[Tuple[int, str], List[FileEntry]] = defaultdict(list)
        self.total_files = 0

    def add_file(self, file_path: Path) -> bool:
        """Adds a file to the in-memory index."""
        try:
            stat_info = file_path.stat()
            if not stat.S_ISREG(stat_info.st_mode):  # Skip non-regular files
                return False
            
            file_size = stat_info.st_size
            mtime = int(stat_info.st_mtime)
            
            file_hash = ""
            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash: 
                    return False # Skip files that couldn't be read

            entry = FileEntry(file_path, file_size, mtime, file_hash)
            self.size_index[file_size].append(entry)
            
            if self.use_hash:
                self.hash_index[(file_size, file_hash)].append(entry)
            
            self.total_files += 1
            return True
        except OSError:
            return False
        
    @classmethod
    def load_from_caf(cls, caf_path: Path, use_hash: bool, hash_algo: str) -> Optional['FileIndex']:
        """
        Loads an index from a .caf file with proper CAF format handling.
        """
        print(f"[CAF] Loading CAF file: {caf_path}")
        
        if not caf_path.is_file(): 
            print(f"[CAF] File not found: {caf_path}")
            return None
        
        with caf_path.open('rb') as buffer:
            try:
                # Header validation
                magic = struct.unpack('<L', buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase): 
                    print(f"[CAF] Invalid magic number: {magic}")
                    return None
                version = int(magic / cls.ulModus)
                if version > 2: 
                    version = struct.unpack('<h', buffer.read(2))[0]
                if version > cls.saveVersion: 
                    print(f"[CAF] Unsupported version: {version}")
                    return None

                print(f"[CAF] CAF version: {version}")

                # Header parsing
                buffer.read(4) # Skip date
                device = cls._read_string(buffer) if version >= 2 else ""
                
                print(f"[CAF] Device path: {device}")
                
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

                # Parse info block to get directory information
                dir_count = struct.unpack('<l', buffer.read(4))[0]
                print(f"[CAF] Directory count: {dir_count}")
                
                # Read directory info to understand file counts per directory
                dir_info = []
                for i in range(dir_count):
                    if i == 0 or version <= 3: 
                        cls._read_string(buffer)  # directory name (empty for root)
                    if version >= 3: 
                        file_count = struct.unpack('<l', buffer.read(4))[0]
                        total_size = struct.unpack('<d', buffer.read(8))[0]
                        dir_info.append((file_count, total_size))
                    else:
                        dir_info.append((0, 0))

                # Read element data
                file_count = struct.unpack('<l', buffer.read(4))[0]
                print(f"[CAF] Total elements (files + dirs): {file_count}")
                
                raw_elm = []
                for _ in range(file_count):
                    mtime = struct.unpack('<L', buffer.read(4))[0]
                    
                    # Handle different size formats by version
                    if version <= 6:
                        # v6 uses a 4-byte signed integer for size/directory_id
                        size = struct.unpack('<l', buffer.read(4))[0]

                    else:
                        # v7/v8 use an 8-byte signed integer
                        size = struct.unpack('<q', buffer.read(8))[0]
                    
                    # Handle parent ID format by version  
                    if version > 7:
                        parent_id = struct.unpack('<L', buffer.read(4))[0]
                    else:
                        parent_id = struct.unpack('<H', buffer.read(2))[0]
                    
                    filename = cls._read_string(buffer)
                    raw_elm.append((mtime, size, parent_id, filename))

                print(f"[CAF] Read {len(raw_elm)} elements from CAF")

                print("[CAF] Pre-calculating parent directory IDs for legacy CAF...")
                referenced_parent_ids = {parent_id for _, _, parent_id, _ in raw_elm}
                print(f"[CAF] Found {len(referenced_parent_ids)} unique directories")

                # Build directory structure properly
                dir_path_map = {0: index.root_path}
                
                if version <= 6:
                    print(f"[CAF] Processing legacy CAF v{version} with optimized algorithm")
                    
                    # First, build the directory tree.
                    # We loop until no new directories can be added in a full pass.
                    while True:
                        dirs_created_this_pass = 0
                        for i, (mtime, size, parent_id, name) in enumerate(raw_elm):
                            element_id = i + 1  # Elements are 1-indexed in CAF
                            
                            # An element is a directory if its ID is in our set
                            if element_id in referenced_parent_ids:
                                # If we haven't processed this directory yet, but its parent exists...
                                if element_id not in dir_path_map and parent_id in dir_path_map:
                                    dir_path_map[element_id] = dir_path_map[parent_id] / name.strip()
                                    dirs_created_this_pass += 1
                        
                        if dirs_created_this_pass == 0:
                            break # Exit loop when the tree is fully built

                    print(f"[CAF] Created {len(dir_path_map) - 1} directory paths for legacy CAF")
                    
                    # Now, add the files in a separate loop.
                    files_added = 0
                    for i, (mtime, size, parent_id, name) in enumerate(raw_elm):
                        element_id = i + 1
                        
                        # An element is a file if it's NOT a directory
                        if element_id not in referenced_parent_ids:
                            if parent_id in dir_path_map and name.strip():
                                path = dir_path_map[parent_id] / name.strip()
                                entry = FileEntry(path, size, mtime, "")
                                index.size_index[size].append(entry)
                                files_added += 1
                    
                    index.total_files = files_added
                    print(f"[CAF] Added {files_added} files to index")


                else:
                    # Modern CAF: directories have negative size
                    dirs_created = 0
                    for _, size, parent_id, name in raw_elm:
                        if size < 0:  # Directory
                            dir_id = -size
                            if parent_id in dir_path_map and name:
                                dir_path_map[dir_id] = dir_path_map[parent_id] / name
                                dirs_created += 1
                    
                    print(f"[CAF] Created {dirs_created} directory paths for modern CAF")

                # Add files to index
                files_added = 0
                size_buckets_created = 0
                
                for i, (mtime, size, parent_id, name) in enumerate(raw_elm):
                    element_id = i + 1
                    
                    # Skip if this is a directory (for modern CAF) or referenced as parent (for legacy)
                    if version > 6 and size < 0:
                        continue  # Directory in modern CAF
                    if version <= 6 and element_id in referenced_parent_ids:
                        continue  # Directory in legacy CAF
                    
                    # This is a file - find its parent directory
                    file_parent_id = parent_id
                    if file_parent_id in dir_path_map and name.strip():  # Valid parent and non-empty name
                        path = dir_path_map[file_parent_id] / name
                        
                        # For legacy CAF, we don't have file sizes, use a reasonable default
                        if version <= 6:
                            actual_size = 1024  # Default size for legacy files
                        else:
                            actual_size = max(size, 1)  # Use actual size, minimum 1
                        
                        entry = FileEntry(path, actual_size, mtime, "")
                        
                        if actual_size not in index.size_index:
                            size_buckets_created += 1
                        index.size_index[actual_size].append(entry)
                        
                        files_added += 1
                        index.total_files += 1
                        
                        # Log first few files for debugging
                        if files_added <= 5:
                            print(f"[CAF] File {files_added}: {name} in {dir_path_map.get(file_parent_id, 'UNKNOWN')} ({actual_size} bytes)")

                print(f"[CAF] Added {files_added} files to index")
                print(f"[CAF] Created {size_buckets_created} size buckets")
                print(f"[CAF] Final total_files: {index.total_files}")
                
                # Verify the index has content
                if index.total_files == 0:
                    print(f"[CAF] WARNING: No files were indexed from {caf_path}")
                
                return index
                
            except Exception as e:
                print(f"[CAF] Error loading CAF file {caf_path}: {e}")
                import traceback
                traceback.print_exc()
                return None

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
        """
        Optimized duplicate detection that only calculates hashes when needed.
        Much faster than building full hash index during CAF load.
        """
        try:
            stat_info = file_path.stat()
            file_size = stat_info.st_size
        except OSError:
            return []
        
        if self.use_hash:
            return self._find_hash_duplicates_optimized(file_path, file_size)
        else:
            return self._find_name_duplicates_optimized(file_path, file_size)
   
    def _find_hash_duplicates_optimized(self, file_path: Path, file_size: int) -> List[FileEntry]:
        """Hash-based duplicate detection with on-demand hash calculation."""
        
        # Step 1: Quick size pre-filtering using raw elm data (very fast)
        size_candidates = []
        if hasattr(self, 'raw_elm'):
            # Use raw data for initial size filtering
            dir_path_map = self._get_or_build_dir_map()
            for mtime, size, parent_id, filename in self.raw_elm:
                if size == file_size and size >= 0 and parent_id in dir_path_map:
                    candidate_path = dir_path_map[parent_id] / filename
                    size_candidates.append((candidate_path, mtime, size))
        else:
            # Fall back to existing size_index if available
            self._ensure_indexes_built()
            size_candidates = [(entry.path, entry.mtime, entry.size) for entry in self.size_index.get(file_size, [])]
        
        if not size_candidates:
            return []
        
        # Step 2: Calculate hash for source file only once
        source_hash = calculate_file_hash(file_path, self.hash_algo)
        if not source_hash:
            return []
        
        # Step 3: Calculate hashes only for size-matched candidates
        matches = []
        for candidate_path, mtime, size in size_candidates:
            # Skip if file doesn't exist on current OS
            if not path_is_native_and_exists(candidate_path):
                # Create entry without hash for cross-platform compatibility
                matches.append(FileEntry(candidate_path, size, mtime, ""))
                continue
                
            # Calculate hash only for existing, size-matched files
            candidate_hash = calculate_file_hash(Path(candidate_path), self.hash_algo)
            if candidate_hash and candidate_hash == source_hash:
                matches.append(FileEntry(candidate_path, size, mtime, candidate_hash))
        
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

    def _write_caf(self, caf_path: Path, elm: List, info: List):
        """Private helper to write the prepared data to a binary .caf file."""
        with caf_path.open('wb') as buffer:
            # Header
            buffer.write(struct.pack('<L', 3 * self.ulModus + self.ulMagicBase))
            buffer.write(struct.pack('<h', self.saveVersion))
            buffer.write(struct.pack('<L', int(time.time())))
            self._write_string(buffer, str(self.root_path))
            self._write_string(buffer, self.root_path.name or str(self.root_path))
            self._write_string(buffer, self.root_path.name or str(self.root_path))
            buffer.write(struct.pack('<L', 0)) # Serial number

            # Comment with hash info
            comment = f"Universal Search Index (hash: {self.hash_algo if self.use_hash else 'none'})"
            self._write_string(buffer, comment)
            
            buffer.write(struct.pack('<f', 0.0)) # Free size
            buffer.write(struct.pack('<h', 0))   # Archive flag

            # Directory Info block
            buffer.write(struct.pack('<l', len(info)))
            for i, (dir_id, file_count, total_size) in enumerate(info):
                if i == 0: self._write_string(buffer, "")
                buffer.write(struct.pack('<l', file_count))
                buffer.write(struct.pack('<d', total_size))

            # Element (file/dir) block
            buffer.write(struct.pack('<l', len(elm)))
            for mtime, size, parent_id, name in elm:
                buffer.write(struct.pack('<L', mtime))
                buffer.write(struct.pack('<q', size))
                buffer.write(struct.pack('<L', parent_id))
                self._write_string(buffer, name)

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