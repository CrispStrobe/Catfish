# core/file_index.py

"""File indexing and CAF format handling."""
import os
import time
import struct
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import stat

from core.data_structures import FileEntry
from utils.file_utils import calculate_file_hash

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
        self.root_path = root_path.resolve()
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

    def find_potential_duplicates(self, file_path: Path) -> List[FileEntry]:
        """Finds potential duplicates of a given file in the index."""
        try:
            stat_info = file_path.stat()
            file_size = stat_info.st_size
            
            if file_size not in self.size_index:
                return []
            
            if self.use_hash:
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash: return []
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
    def load_from_caf(cls, caf_path: Path, use_hash: bool, hash_algo: str) -> Optional['FileIndex']:
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
                index = cls(Path(device), use_hash, hash_algo)
                
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
                        
                        # For legacy CAF files without size info, try to get actual size if file exists
                        actual_size = size
                        if version <= 6 and size == 0 and path.exists():
                            try:
                                actual_size = path.stat().st_size
                            except OSError:
                                actual_size = 0
                        
                        entry_hash = ""
                        if use_hash and path.exists():
                            # Hashes are not stored in CAF, must be calculated on demand
                            entry_hash = calculate_file_hash(path, hash_algo)
                        
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