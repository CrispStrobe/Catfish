#!/usr/bin/env python3
"""
Enhanced Duplicate File Finder with Full Interactive GUI

Features:
- Complete GUI workflow with path selection and configuration.
- Interactive duplicate management with regex filtering.
- Smart folder overlap detection to prevent redundant scanning.
- Progress tracking and cancellation support for long operations.
- Caching of file indexes in `.caf` format for much faster subsequent scans.
- Full command-line interface for scripting and automation.
"""

import os
import sys
import platform
import argparse
import hashlib
import time
import struct
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, NamedTuple, Optional
from tqdm import tqdm
from threading import Thread, Event
import queue
import stat
import subprocess
import datetime
from datetime import datetime as dt

# --- Data Structures ---

class FileEntry(NamedTuple):
    """Represents a single file with its essential metadata."""
    path: Path
    size: int
    mtime: int
    hash: str = ""

class DuplicateMatch(NamedTuple):
    """Represents a source file and a list of its found duplicates."""
    source_file: Path
    destinations: List[FileEntry]

class SearchCriteria(NamedTuple):
    """Holds the criteria for searching within file indexes."""
    name_pattern: Optional[str] = None
    size_min: Optional[int] = None
    size_max: Optional[int] = None
    date_min: Optional[dt] = None
    date_max: Optional[dt] = None

class SearchResult(NamedTuple):
    """A single file search result"""
    path: Path
    size: int
    mtime: int
    hash: str = ""

class ScanConfig(NamedTuple):
    """Configuration for a duplicate scanning operation."""
    source_path: Path
    dest_paths: List[Path]
    use_hash: bool
    hash_algo: str
    reuse_indices: bool
    recreate_indices: bool

# --- Utility Functions ---

def format_size(size_bytes: int) -> str:
    """Formats bytes into a human-readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def get_platform_info() -> Dict:
    """Gets platform-specific commands and formatting."""
    system = platform.system().lower()
    if system == 'windows':
        return {
            'name': 'Windows', 'script_ext': '.bat', 'delete_cmd': 'del',
            'path_quote': lambda p: f'"{p}"',
            'script_header': '@echo off\nchcp 65001 > nul\n\n',
            'pause_cmd': 'pause', 'echo_cmd': 'echo'
        }
    else:  # Unix-like (Linux, macOS)
        return {
            'name': 'Unix-like', 'script_ext': '.sh', 'delete_cmd': 'rm -f',
            'path_quote': lambda p: f"'{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'",
            'script_header': '#!/bin/bash\n\n',
            'pause_cmd': 'read -p "Press any key to continue..."', 'echo_cmd': 'echo'
        }

def make_script_executable(script_path: Path):
    """Makes a script executable on Unix-like systems."""
    if platform.system().lower() != 'windows':
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

def is_subdirectory(child: Path, parent: Path) -> bool:
    """Checks if one path is a subdirectory of another."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False

def filter_overlapping_paths(paths: List[Path]) -> List[Path]:
    """Removes paths that are subdirectories of others in the list."""
    sorted_paths = sorted(paths, key=lambda p: len(str(p)))
    unique_paths = []
    for path in sorted_paths:
        if not any(is_subdirectory(path, existing) for existing in unique_paths):
            unique_paths.append(path)
    return unique_paths

def calculate_file_hash(file_path: Path, hash_algo: str) -> str:
    """Calculates the hash of a file."""
    hash_obj = hashlib.new(hash_algo)
    try:
        with file_path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except OSError as e:
        print(f"Warning: Could not read file {file_path}: {e}", file=sys.stderr)
        return ""

def get_screen_geometry() -> Tuple[int, int]:
    """Gets primary screen dimensions."""
    root = tk.Tk()
    root.withdraw()
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.destroy()
    return width, height

def calculate_window_geometry(screen_width: int, screen_height: int) -> str:
    """Calculates a responsive and centered window geometry string."""
    width = max(800, min(1400, int(screen_width * 0.8)))
    height = max(600, min(1000, int(screen_height * 0.8)))
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    return f"{width}x{height}+{x}+{y}"

def get_default_script_name() -> str:
    """Generates a default script name with a timestamp."""
    platform_info = get_platform_info()
    return f'delete_duplicates_{dt.now().strftime("%Y%m%d_%H%M%S")}{platform_info["script_ext"]}'

def escape_script_path(path: Path) -> str:
    """Escapes a file path for use in a shell/batch script."""
    return get_platform_info()['path_quote'](path)

def open_file_or_folder(path: Path, open_folder: bool = False):
    """Opens a file or its containing folder using the OS default."""
    try:
        target = path.parent if open_folder else path
        if not target.exists():
            messagebox.showerror("Error", f"Path does not exist:\n{target}")
            return
        system = platform.system().lower()
        if system == 'windows':
            os.startfile(target)
        elif system == 'darwin':
            subprocess.run(['open', str(target)], check=False)
        else: # Linux
            subprocess.run(['xdg-open', str(target)], check=False)
    except Exception as e:
        messagebox.showerror("Error", f"Could not open path:\n{e}")

def get_caf_path(dest_path: Path, hash_algo: str) -> Path:
    """Generates a consistent CAF file path based on hash algorithm."""
    suffix = f"_{hash_algo}" if hash_algo != 'md5' else ""
    return dest_path.parent / f"{dest_path.name}_index{suffix}.caf"

# --- Core File Indexing Classes ---

class CafFileIndex:
    """Handles the reading and writing of the proprietary .caf index file format."""
    ulMagicBase = 500410407
    ulModus = 1000000000
    saveVersion = 8
    sVersion = 8

    def __init__(self, root_path: Path):
        self.root_path = root_path.resolve()
        self.device = str(self.root_path)
        self.elm: List[Tuple] = []
        self.info: List[Tuple] = []
        self.dir_id_map: Dict[Path, int] = {self.root_path: 0}
        self.dir_path_map: Dict[int, Path] = {0: self.root_path}
        self.next_dir_id = 1

    def _get_dir_id(self, dir_path: Path) -> int:
        """Gets or creates a unique integer ID for a directory path."""
        dir_path = dir_path.resolve()
        if dir_path in self.dir_id_map:
            return self.dir_id_map[dir_path]
        dir_id = self.next_dir_id
        self.next_dir_id += 1
        self.dir_id_map[dir_path] = dir_id
        self.dir_path_map[dir_id] = dir_id
        return dir_id

    def _build_directory_structure(self, all_files: List[Path]):
        """Populates directory maps from a list of all file paths before saving."""
        directories = {p.parent for p in all_files}
        for dir_path in sorted(directories, key=lambda p: len(p.parts)):
            if dir_path != self.root_path:
                self._get_dir_id(dir_path)

    @staticmethod
    def _read_string(buffer) -> str:
        chars = bytearray()
        while (char := buffer.read(1)) != b'\x00':
            if not char: break
            chars.extend(char)
        return chars.decode('utf-8', errors='replace')

    @classmethod
    def load(cls, caf_path: Path) -> Optional['CafFileIndex']:
        """Loads and parses a .caf file from disk."""
        if not caf_path.exists(): return None
        try:
            with caf_path.open('rb') as buffer:
                magic = struct.unpack('<L', buffer.read(4))[0]
                if not (magic > 0 and magic % cls.ulModus == cls.ulMagicBase):
                    return None
                
                version = struct.unpack('<h', buffer.read(2))[0]
                if version > cls.sVersion: return None

                date = struct.unpack('<L', buffer.read(4))[0]
                device = cls._read_string(buffer) if version >= 2 else ""
                index = cls(Path(device))
                index.date = date
                index.volume = cls._read_string(buffer)
                index.alias = cls._read_string(buffer)
                buffer.read(4)  # Skip serial
                index.comment = cls._read_string(buffer) if version >= 4 else ""

                dir_count = struct.unpack('<l', buffer.read(4))[0]
                for i in range(dir_count):
                    cls._read_string(buffer) # Directory name, not used in this simplified loader
                    if version >= 3:
                        buffer.read(12) # Skip file_count and total_size

                file_count = struct.unpack('<l', buffer.read(4))[0]
                for _ in range(file_count):
                    mtime = struct.unpack('<L', buffer.read(4))[0]
                    size = struct.unpack('<q', buffer.read(8))[0] if version > 6 else 0
                    parent_id = struct.unpack('<L' if version > 7 else '<H', buffer.read(4 if version > 7 else 2))[0]
                    filename = cls._read_string(buffer)
                    
                    file_hash = "" # Hashes are parsed separately if they exist
                    index.elm.append((mtime, size, parent_id, filename, file_hash))
                
                # Simple hash parsing from comments
                if "HASH:" in index.comment:
                    hash_map = {}
                    for line in index.comment.split('\n'):
                        if line.startswith("HASH:"):
                            try:
                                _, fname, fhash = line.split(':', 2)
                                hash_map[fname] = fhash
                            except ValueError:
                                continue
                    
                    # Update elm with parsed hashes
                    for i, entry in enumerate(index.elm):
                        if entry[3] in hash_map:
                            index.elm[i] = entry[:4] + (hash_map[entry[3]],)
                return index
        except Exception as e:
            print(f"Error loading CAF file {caf_path}: {e}", file=sys.stderr)
            return None
        
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
        This method orchestrates the entire process of building the required
        CAF data structures from the current index state.
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
            comment = f"DuplicateFinder Index (hash: {self.hash_algo if self.use_hash else 'none'})"
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
                if version > 2: version = struct.unpack('<h', buffer.read(2))[0]
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
                    size = struct.unpack('<q', buffer.read(8))[0] if version > 6 else 0
                    parent_id = struct.unpack('<L' if version > 7 else '<H', buffer.read(4 if version > 7 else 2))[0]
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
                        if path.exists():
                            # We can trust mtime/size from cache, no need to stat() again
                            entry_hash = ""
                            if use_hash:
                                # Hashes are not stored in CAF, must be calculated on demand
                                entry_hash = calculate_file_hash(path, hash_algo)
                            
                            entry = FileEntry(path, size, mtime, entry_hash)
                            index.size_index[size].append(entry)
                            if use_hash and entry_hash:
                                index.hash_index[(size, entry_hash)].append(entry)
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

# --- File Search GUI ---

class FileSearchGUI:
    """GUI for searching files in existing indices"""
    
    def __init__(self, indices_paths: List[Path]):
        self.indices_paths = indices_paths
        self.search_results = []
        
        self.root = tk.Tk()
        self.root.title("File Search")
        
        # Responsive geometry
        screen_width, screen_height = get_screen_geometry()
        geometry = calculate_window_geometry(screen_width, screen_height)
        self.root.geometry(geometry)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the search interface"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Search criteria frame
        criteria_frame = ttk.LabelFrame(main_frame, text="Search Criteria", padding=10)
        criteria_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Name pattern
        name_frame = ttk.Frame(criteria_frame)
        name_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(name_frame, text="Name (regex):", width=12).pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.name_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(name_frame, text="Examples: *.jpg, IMG_\\d+, (?i)vacation").pack(side=tk.RIGHT, foreground='gray')
        
        # Size range  
        size_frame = ttk.Frame(criteria_frame)
        size_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(size_frame, text="Size range:", width=12).pack(side=tk.LEFT)
        
        size_inner = ttk.Frame(size_frame)
        size_inner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.size_min_var = tk.StringVar()
        ttk.Entry(size_inner, textvariable=self.size_min_var, width=15).pack(side=tk.LEFT)
        ttk.Label(size_inner, text=" to ").pack(side=tk.LEFT)
        self.size_max_var = tk.StringVar()
        ttk.Entry(size_inner, textvariable=self.size_max_var, width=15).pack(side=tk.LEFT)
        ttk.Label(size_inner, text=" (e.g., 1MB, 500KB)").pack(side=tk.LEFT, padx=(5, 0), foreground='gray')
        
        # Date range
        date_frame = ttk.Frame(criteria_frame)
        date_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(date_frame, text="Date range:", width=12).pack(side=tk.LEFT)
        
        date_inner = ttk.Frame(date_frame)
        date_inner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.date_min_var = tk.StringVar()
        ttk.Entry(date_inner, textvariable=self.date_min_var, width=15).pack(side=tk.LEFT)
        ttk.Label(date_inner, text=" to ").pack(side=tk.LEFT)
        self.date_max_var = tk.StringVar()
        ttk.Entry(date_inner, textvariable=self.date_max_var, width=15).pack(side=tk.LEFT)
        ttk.Label(date_inner, text=" (YYYY-MM-DD or 'today', 'yesterday')").pack(side=tk.LEFT, padx=(5, 0), foreground='gray')
        
        # Search button
        search_btn_frame = ttk.Frame(criteria_frame)
        search_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(search_btn_frame, text="Search Files", command=self.perform_search).pack(side=tk.LEFT)
        ttk.Button(search_btn_frame, text="Clear", command=self.clear_criteria).pack(side=tk.LEFT, padx=(10, 0))
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Search Results", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Results tree with scrollbars
        tree_frame = ttk.Frame(results_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Size', 'Modified', 'Path')
        self.results_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.results_tree.heading('#0', text='Filename')
        self.results_tree.heading('Size', text='Size')
        self.results_tree.heading('Modified', text='Modified')  
        self.results_tree.heading('Path', text='Full Path')
        
        # Responsive column widths
        screen_width, _ = get_screen_geometry()
        if screen_width < 1200:
            self.results_tree.column('#0', width=200, minwidth=150)
            self.results_tree.column('Size', width=80, minwidth=60)
            self.results_tree.column('Modified', width=120, minwidth=100)
            self.results_tree.column('Path', width=300, minwidth=250)
        else:
            self.results_tree.column('#0', width=250, minwidth=200)
            self.results_tree.column('Size', width=100, minwidth=80)
            self.results_tree.column('Modified', width=150, minwidth=120)
            self.results_tree.column('Path', width=400, minwidth=300)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.results_tree.bind('<Double-Button-1>', self.on_double_click)
        self.results_tree.bind('<Button-3>', self.on_right_click)  # Right-click context menu
        self.results_tree.bind('<Return>', self.on_enter_key)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X)
        
        ttk.Button(action_frame, text="Open File", command=self.open_selected_file).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Open Folder", command=self.open_selected_folder).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text="Copy Path", command=self.copy_selected_path).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text="Export Results", command=self.export_results).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text="Close", command=self.root.quit).pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set(f"Ready to search {len(self.indices_paths)} indexed locations")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
    def clear_criteria(self):
        """Clear all search criteria"""
        self.name_var.set("")
        self.size_min_var.set("")
        self.size_max_var.set("")
        self.date_min_var.set("")
        self.date_max_var.set("")
        
    def perform_search(self):
        """Execute the file search using indices with correct hash algorithms."""
        try:
            criteria = self.parse_criteria()
            self.results_tree.delete(*self.results_tree.get_children())
            self.search_results.clear()
            
            self.status_var.set("Searching...")
            self.root.update_idletasks()
            
            total_results = 0
            for caf_path in self.indices_paths:
                if caf_path.exists():
                    # Infer hash algorithm from filename for correct loading
                    name = caf_path.stem
                    use_hash = True
                    if name.endswith("_sha256"):
                        hash_algo = "sha256"
                    elif name.endswith("_sha1"):
                        hash_algo = "sha1"
                    else:
                        hash_algo = "md5"

                    file_index = FileIndex.load_from_caf(caf_path, use_hash, hash_algo)
                    
                    if file_index:
                        results = search_files_in_index(file_index, criteria)
                        total_results += len(results)
                        for result in results:
                            self.add_result_to_tree(result)
            
            self.status_var.set(f"Found {total_results} files matching criteria")
            
        except Exception as e:
            messagebox.showerror("Search Error", f"Search failed:\n{str(e)}")
            self.status_var.set("Search failed")
    
    def parse_criteria(self) -> SearchCriteria:
        """Parse user input into SearchCriteria"""
        # Name pattern
        name_pattern = self.name_var.get().strip()
        if not name_pattern:
            name_pattern = None
        
        # Size range
        size_min = None
        size_max = None
        try:
            if self.size_min_var.get().strip():
                size_min = parse_size(self.size_min_var.get().strip())
            if self.size_max_var.get().strip():
                size_max = parse_size(self.size_max_var.get().strip())
        except ValueError as e:
            raise ValueError(f"Invalid size format: {e}")
        
        # Date range
        date_min = None
        date_max = None
        try:
            if self.date_min_var.get().strip():
                date_min = parse_date(self.date_min_var.get().strip())
            if self.date_max_var.get().strip():
                date_max = parse_date(self.date_max_var.get().strip())
        except ValueError as e:
            raise ValueError(f"Invalid date format: {e}")
        
        return SearchCriteria(
            name_pattern=name_pattern,
            size_min=size_min,
            size_max=size_max,
            date_min=date_min,
            date_max=date_max
        )
    
    def add_result_to_tree(self, result: SearchResult):
        """Add a search result to the tree view"""
        self.search_results.append(result)
        
        # Format data for display
        filename = result.path.name
        size_str = format_size(result.size)
        modified_str = datetime.datetime.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M')
        path_str = str(result.path)
        
        # Insert into tree
        self.results_tree.insert('', 'end',
                                text=filename,
                                values=(size_str, modified_str, path_str),
                                tags=(len(self.search_results) - 1,))
    
    def get_selected_result(self) -> Optional[SearchResult]:
        """Get the currently selected search result"""
        selection = self.results_tree.selection()
        if not selection:
            return None
            
        item = selection[0]
        tags = self.results_tree.item(item, 'tags')
        if tags:
            try:
                result_index = int(tags[0])
                return self.search_results[result_index]
            except (ValueError, IndexError):
                return None
        return None
    
    def on_double_click(self, event):
        """Handle double-click on result"""
        self.open_selected_file()
    
    def on_right_click(self, event):
        """Handle right-click context menu"""
        # Simple context menu
        result = self.get_selected_result()
        if result:
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Open File", command=self.open_selected_file)
            menu.add_command(label="Open Folder", command=self.open_selected_folder)
            menu.add_command(label="Copy Path", command=self.copy_selected_path)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
    
    def on_enter_key(self, event):
        """Handle Enter key press"""
        self.open_selected_file()
    
    def open_selected_file(self):
        """Open the selected file"""
        result = self.get_selected_result()
        if result and result.path.exists():
            open_file_or_folder(result.path, open_folder=False)
        elif result:
            messagebox.showerror("File Not Found", f"File no longer exists:\n{result.path}")
    
    def open_selected_folder(self):
        """Open the folder containing the selected file"""
        result = self.get_selected_result()
        if result and result.path.exists():
            open_file_or_folder(result.path, open_folder=True)
        elif result:
            messagebox.showerror("File Not Found", f"File no longer exists:\n{result.path}")
    
    def copy_selected_path(self):
        """Copy selected file path to clipboard"""
        result = self.get_selected_result()
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(result.path))
            self.status_var.set(f"Copied path: {result.path.name}")
            self.root.after(2000, lambda: self.status_var.set(f"Found {len(self.search_results)} files"))
    
    def export_results(self):
        """Export search results to CSV"""
        if not self.search_results:
            messagebox.showwarning("No Results", "No search results to export.")
            return
            
        filename = filedialog.asksaveasfilename(
            title="Export Search Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("Filename,Size,Size (bytes),Modified,Full Path\n")
                    for result in self.search_results:
                        filename_clean = result.path.name.replace('"', '""')
                        path_clean = str(result.path).replace('"', '""')
                        size_str = format_size(result.size)
                        modified_str = datetime.datetime.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        f.write(f'"{filename_clean}","{size_str}",{result.size},"{modified_str}","{path_clean}"\n')
                
                messagebox.showinfo("Export Complete", f"Results exported to:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export results:\n{e}")
    
    def run(self):
        """Run the search GUI"""
        self.root.mainloop()

# --- Setup GUI ---

class SetupGUI:
    """Initial setup GUI for path selection and configuration"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Duplicate Finder - Setup")
        
        # Calculate responsive geometry
        screen_width, screen_height = get_screen_geometry()
        if screen_width < 1200:
            geometry = f"{min(800, screen_width-100)}x{min(600, screen_height-100)}"
        else:
            geometry = "900x700"
        
        # Center window
        self.root.geometry(geometry)
        self.root.resizable(True, True)
        
        self.config = None
        self.source_path = None
        self.dest_paths = []
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the configuration UI"""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Duplicate File Finder", 
                               font=('TkDefaultFont', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Source folder selection
        source_frame = ttk.LabelFrame(main_frame, text="Source Folder", padding=10)
        source_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.source_var = tk.StringVar()
        source_entry = ttk.Entry(source_frame, textvariable=self.source_var, width=50)
        source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(source_frame, text="Browse...", 
                  command=self.select_source_folder).pack(side=tk.RIGHT, padx=(10, 0))
        
        # Destination folders selection
        dest_frame = ttk.LabelFrame(main_frame, text="Destination Folders", padding=10)
        dest_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Destination list with scrollbar
        list_frame = ttk.Frame(dest_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.dest_listbox = tk.Listbox(list_frame, height=6)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.dest_listbox.yview)
        self.dest_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.dest_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Destination buttons
        dest_buttons = ttk.Frame(dest_frame)
        dest_buttons.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(dest_buttons, text="Add Folder", 
                  command=self.add_dest_folder).pack(side=tk.LEFT)
        ttk.Button(dest_buttons, text="Remove Selected", 
                  command=self.remove_dest_folder).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(dest_buttons, text="Clear All", 
                  command=self.clear_dest_folders).pack(side=tk.LEFT, padx=(10, 0))
        
        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Hash options
        hash_frame = ttk.Frame(options_frame)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.use_hash_var = tk.BooleanVar()
        hash_check = ttk.Checkbutton(hash_frame, text="Use file hashes for comparison", 
                                    variable=self.use_hash_var, command=self.on_hash_toggle)
        hash_check.pack(side=tk.LEFT)
        
        self.hash_algo_var = tk.StringVar(value="md5")
        hash_combo = ttk.Combobox(hash_frame, textvariable=self.hash_algo_var, 
                                 values=["md5", "sha1", "sha256"], width=10, state="disabled")
        hash_combo.pack(side=tk.LEFT, padx=(10, 0))
        self.hash_combo = hash_combo
        
        # Index options
        index_frame = ttk.Frame(options_frame)
        index_frame.pack(fill=tk.X)
        
        self.reuse_indices_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(index_frame, text="Reuse existing indices", 
                       variable=self.reuse_indices_var).pack(side=tk.LEFT)
        
        self.recreate_indices_var = tk.BooleanVar()
        ttk.Checkbutton(index_frame, text="Force recreation of indices", 
                       variable=self.recreate_indices_var).pack(side=tk.LEFT, padx=(20, 0))
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        ttk.Button(button_frame, text="Start Scan",
                   command=self.start_scan).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Search Files",
                   command=self.search_files).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(button_frame, text="Cancel",
                   command=self.root.quit).pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar(value="Select source and destination folders to begin")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(15, 0))
        
    def on_hash_toggle(self):
        """Enable/disable hash algorithm selection"""
        if self.use_hash_var.get():
            self.hash_combo.config(state="readonly")
        else:
            self.hash_combo.config(state="disabled")
    
    def select_source_folder(self):
        """Select source folder"""
        folder = filedialog.askdirectory(title="Select Source Folder")
        if folder:
            self.source_var.set(folder)
            self.source_path = Path(folder)
            self.update_status()
    
    def add_dest_folder(self):
        """Add destination folder"""
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            folder_path = Path(folder)
            if folder_path not in self.dest_paths:
                self.dest_paths.append(folder_path)
                self.dest_listbox.insert(tk.END, str(folder_path))
                self.update_status()
            else:
                messagebox.showwarning("Duplicate", "This folder is already in the list.")
    
    def remove_dest_folder(self):
        """Remove selected destination folder"""
        selection = self.dest_listbox.curselection()
        if selection:
            index = selection[0]
            self.dest_listbox.delete(index)
            del self.dest_paths[index]
            self.update_status()
    
    def clear_dest_folders(self):
        """Clear all destination folders"""
        self.dest_listbox.delete(0, tk.END)
        self.dest_paths.clear()
        self.update_status()
    
    def update_status(self):
        """Update status message"""
        if not self.source_path:
            self.status_var.set("Please select a source folder")
        elif not self.dest_paths:
            self.status_var.set("Please add at least one destination folder")
        else:
            self.status_var.set(f"Ready to scan: 1 source, {len(self.dest_paths)} destination(s)")
    
    def search_files(self):
        """Launch file search functionality"""
        if not self.dest_paths:
            messagebox.showerror("Error", "Please add at least one destination folder to search in.")
            return
        
        # Check for existing indices
        hash_algo = self.hash_algo_var.get()
        available_indices = []
        
        for dest_path in self.dest_paths:
            if not dest_path.exists():
                continue
                
            caf_path = get_caf_path(dest_path, hash_algo)
            if caf_path.exists():
                available_indices.append(caf_path)
        
        if not available_indices:
            result = messagebox.askyesno("No Indices Found", 
                                       "No existing indices found. Would you like to create indices first?")
            if result:
                self.start_scan()
                return
            else:
                return
        
        # Launch file search GUI
        self.root.withdraw()  # Hide setup window
        search_gui = FileSearchGUI(available_indices)
        search_gui.run()
        search_gui.root.destroy()
        self.root.deiconify()  # Show setup window again
    
    def start_scan(self):
        """Start the duplicate scan"""
        if not self.source_path:
            messagebox.showerror("Error", "Please select a source folder.")
            return
        
        if not self.dest_paths:
            messagebox.showerror("Error", "Please add at least one destination folder.")
            return
        
        # Validate paths
        if not self.source_path.exists():
            messagebox.showerror("Error", f"Source folder does not exist: {self.source_path}")
            return
        
        invalid_paths = [p for p in self.dest_paths if not p.exists()]
        if invalid_paths:
            messagebox.showerror("Error", f"Invalid destination folders:\n" + 
                               "\n".join(str(p) for p in invalid_paths))
            return
        
        # Create configuration
        self.config = ScanConfig(
            source_path=self.source_path,
            dest_paths=self.dest_paths,
            use_hash=self.use_hash_var.get(),
            hash_algo=self.hash_algo_var.get(),
            reuse_indices=self.reuse_indices_var.get(),
            recreate_indices=self.recreate_indices_var.get()
        )
        
        self.root.quit()
    
    def run(self) -> Optional[ScanConfig]:
        """Run the setup GUI"""
        self.root.mainloop()
        self.root.destroy()
        return self.config

# --- Progress GUI ---

class ProgressGUI:
    """Progress window for scanning operations"""
    
    def __init__(self, parent=None):
        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title("Scanning for Duplicates")
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        self.cancelled = Event()
        self.setup_ui()
        
    def setup_ui(self):
        """Setup progress UI"""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Current operation
        self.operation_var = tk.StringVar(value="Initializing...")
        ttk.Label(main_frame, textvariable=self.operation_var, 
                 font=('TkDefaultFont', 10, 'bold')).pack(pady=(0, 10))
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        self.progress.start()
        
        # Details
        self.details_var = tk.StringVar(value="")
        details_label = ttk.Label(main_frame, textvariable=self.details_var)
        details_label.pack(pady=(0, 20))
        
        # Cancel button
        ttk.Button(main_frame, text="Cancel", 
                  command=self.cancel).pack()
        
    def update_operation(self, text):
        """Update current operation text"""
        self.operation_var.set(text)
        self.root.update_idletasks()
    
    def update_details(self, text):
        """Update details text"""
        self.details_var.set(text)
        self.root.update_idletasks()
    
    def cancel(self):
        """Cancel the operation"""
        self.cancelled.set()
        self.root.quit()

# --- Results GUI ---

class DuplicateFinderGUI:
    """Interactive GUI for reviewing and selectively deleting duplicates"""
    
    def __init__(self, duplicates: List[DuplicateMatch], method: str):
        self.duplicates = duplicates
        self.method = method
        self.selected_for_deletion = set()
        self.action = None # Used to signal back to the main loop
        
        self.root = tk.Tk()
        self.root.title("Duplicate File Manager")
        
        # Responsive geometry
        screen_width, screen_height = get_screen_geometry()
        geometry = calculate_window_geometry(screen_width, screen_height)
        self.root.geometry(geometry)
        
        self.setup_ui()
        self.populate_tree()
        
    def setup_ui(self):
        """Setup the GUI components with responsive design"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text="Information", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        total_size_bytes = sum(d.source_file.stat().st_size for d in self.duplicates if d.source_file.exists())
        info_text = f"Method: {self.method} | Found {len(self.duplicates)} files with duplicates | Total Size: {format_size(total_size_bytes)}"
        ttk.Label(info_frame, text=info_text).pack(anchor=tk.W)
        
        # Filter frame
        filter_frame = ttk.LabelFrame(main_frame, text="Filter", padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        filter_inner = ttk.Frame(filter_frame)
        filter_inner.pack(fill=tk.X)
        
        ttk.Label(filter_inner, text="Regex filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_inner, textvariable=self.filter_var)
        self.filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self.filter_entry.bind('<KeyRelease>', self.on_filter_change)
        
        ttk.Button(filter_inner, text="Select All Filtered", command=self.select_all_filtered).pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(filter_inner, text="Deselect All", command=self.deselect_all).pack(side=tk.RIGHT, padx=(0, 5))
        
        # Tree frame
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Size', 'Path')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.tree.heading('#0', text='File')
        self.tree.heading('Size', text='Size')
        self.tree.heading('Path', text='Path')
        
        screen_width, _ = get_screen_geometry()
        if screen_width < 1200:
            self.tree.column('#0', width=200, minwidth=150)
            self.tree.column('Size', width=100, minwidth=80)
            self.tree.column('Path', width=400, minwidth=300)
        else:
            self.tree.column('#0', width=300, minwidth=200)
            self.tree.column('Size', width=120, minwidth=100)
            self.tree.column('Path', width=500, minwidth=400)
        
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<space>', self.on_space_key)
        self.tree.bind('<Control-c>', self.copy_path_to_clipboard)
        self.tree.bind('<Double-Button-1>', self.copy_path_to_clipboard)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        platform_info = get_platform_info()
        
        # --- FIX: Added "Delete Selected Files" button ---
        ttk.Button(action_frame, text="Delete Selected Files", command=self.delete_selected_files).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=f"Generate {platform_info['name']} Script...", command=self.generate_batch).pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Button(action_frame, text="New Scan", command=self.new_scan).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(action_frame, text="Exit", command=self.root.quit).pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Use checkboxes or spacebar to select files for deletion")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))

    def generate_batch(self):
        """Generate a script file to delete the selected items."""
        if not self.selected_for_deletion:
            messagebox.showwarning("No Selection", "No files are selected to include in the script.")
            return
            
        platform_info = get_platform_info()
        default_name = get_default_script_name()
        
        file_types = [
            (f"{platform_info['name']} scripts", f"*{platform_info['script_ext']}"),
            ("All files", "*.*")
        ]
        
        # --- FIX: Changed `initialvalue` to `initialfile` ---
        filename = filedialog.asksaveasfilename(
            title=f"Save {platform_info['name']} Deletion Script",
            defaultextension=platform_info['script_ext'],
            filetypes=file_types,
            initialfile=default_name # This was the parameter with the typo
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(platform_info['script_header'])
                    comment = "REM" if platform_info['name'] == 'Windows' else "#"
                    f.write(f"{comment} Deletion script generated by Duplicate Finder on {dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    
                    for item in self.selected_for_deletion:
                        file_path = Path(self.tree.item(item, 'values')[1])
                        quoted_path = escape_script_path(file_path)
                        f.write(f"{platform_info['delete_cmd']} {quoted_path}\n")
                    
                    f.write(f"\n{platform_info['echo_cmd']} \"Script finished.\"\n{platform_info['pause_cmd']}\n")
                
                make_script_executable(Path(filename))
                
                # --- FIX: Added confirmation message ---
                messagebox.showinfo("Script Generated", f"Deletion script was successfully saved to:\n{filename}")

            except OSError as e:
                messagebox.showerror("Error", f"Failed to create script file:\n{e}")

    # direct deletion from the GUI
    def delete_selected_files(self):
        """Deletes the selected files directly after user confirmation."""
        if not self.selected_for_deletion:
            messagebox.showwarning("No Selection", "No files are selected for deletion.")
            return

        count = len(self.selected_for_deletion)
        try:
            total_size = sum(Path(self.tree.item(item, 'values')[1]).stat().st_size for item in self.selected_for_deletion)
        except (OSError, IndexError):
            messagebox.showerror("Error", "Could not calculate size of selected files. Some may no longer exist.")
            return

        # Safety confirmation dialog
        if not messagebox.askyesno("Confirm Permanent Deletion",
                                   f"Are you sure you want to permanently delete {count} files ({format_size(total_size)})?\n\n"
                                   "This action CANNOT be undone."):
            return

        deleted_count = 0
        failed_deletions = []
        
        # Iterate over a copy because we're modifying the set and tree
        for item in list(self.selected_for_deletion):
            file_path_str = self.tree.item(item, 'values')[1]
            file_path = Path(file_path_str)
            try:
                file_path.unlink()
                deleted_count += 1
                self.tree.delete(item)
                self.selected_for_deletion.remove(item)
            except OSError as e:
                failed_deletions.append(f"{file_path.name}: {e}")
        
        # Final report message
        message = f"Successfully deleted {deleted_count} of {count} selected files."
        if failed_deletions:
            message += f"\n\nFailed to delete {len(failed_deletions)} files:\n"
            message += "\n".join(failed_deletions[:5]) # Show first 5 errors
            if len(failed_deletions) > 5:
                message += f"\n... and {len(failed_deletions) - 5} more."
                
        messagebox.showinfo("Deletion Complete", message)
        self.update_status()
        
    def populate_tree(self):
        """Populate the tree view with duplicates"""
        for i, duplicate in enumerate(self.duplicates):
            source_size = duplicate.source_file.stat().st_size
            source_id = self.tree.insert('', 'end', 
                                       text=f"☐ {duplicate.source_file.name}",
                                       values=(f"{source_size:,} bytes", str(duplicate.source_file)),
                                       tags=('source', f'dup_{i}'))
            
            for dest in duplicate.destinations:
                self.tree.insert(source_id, 'end',
                               text=f"→ {dest.path.name}",
                               values=(f"{dest.size:,} bytes", str(dest.path)),
                               tags=('destination',))
    
    def on_filter_change(self, event):
        """Handle filter text changes"""
        filter_text = self.filter_var.get()
        if not filter_text:
            for item in self.tree.get_children():
                self.show_item(item)
            return
        
        try:
            pattern = re.compile(filter_text, re.IGNORECASE)
            for item in self.tree.get_children():
                source_path = self.tree.item(item, 'values')[1]
                if pattern.search(source_path):
                    self.show_item(item)
                else:
                    self.hide_item(item)
        except re.error:
            pass
    
    def show_item(self, item):
        """Show a tree item"""
        self.tree.move(item, '', tk.END)
    
    def hide_item(self, item):
        """Hide a tree item by moving it to a hidden parent"""
        if not hasattr(self, '_hidden_parent'):
            self._hidden_parent = self.tree.insert('', 0, text='', tags=('hidden',))
            self.tree.item(self._hidden_parent, open=False)
        self.tree.move(item, self._hidden_parent, tk.END)
    
    def copy_path_to_clipboard(self, event):
        """Copy selected file path to clipboard"""
        item = self.tree.focus()
        if item:
            path_value = self.tree.item(item, 'values')
            if path_value and len(path_value) > 1:
                self.root.clipboard_clear()
                self.root.clipboard_append(path_value[1])  # Path is the second column
                self.status_var.set(f"Copied path to clipboard: {Path(path_value[1]).name}")
                # Reset status after 2 seconds
                self.root.after(2000, lambda: self.update_status())
    
    def on_tree_click(self, event):
        """Handle tree item clicks for selection"""
        item = self.tree.identify_row(event.y)
        if item and 'source' in self.tree.item(item, 'tags'):
            self.toggle_selection(item)
    
    def on_space_key(self, event):
        """Handle space key for selection"""
        item = self.tree.focus()
        if item and 'source' in self.tree.item(item, 'tags'):
            self.toggle_selection(item)
    
    def toggle_selection(self, item):
        """Toggle selection state of an item"""
        current_text = self.tree.item(item, 'text')
        if item in self.selected_for_deletion:
            self.selected_for_deletion.remove(item)
            new_text = current_text.replace('☑', '☐')
        else:
            self.selected_for_deletion.add(item)
            new_text = current_text.replace('☐', '☑')
        
        self.tree.item(item, text=new_text)
        self.update_status()
    
    def select_all_filtered(self):
        """Select all visible (filtered) items"""
        for item in self.tree.get_children():
            if ('source' in self.tree.item(item, 'tags') and 
                item not in self.selected_for_deletion):
                self.toggle_selection(item)
    
    def deselect_all(self):
        """Deselect all items"""
        for item in list(self.selected_for_deletion):
            self.toggle_selection(item)
    
    def update_status(self):
        """Update status bar with selection count"""
        count = len(self.selected_for_deletion)
        if count > 0:
            total_size = sum(Path(self.tree.item(item, 'values')[1]).stat().st_size 
                           for item in self.selected_for_deletion)
            self.status_var.set(f"Selected: {count} files ({total_size/1024/1024:.1f} MB)")
        else:
            self.status_var.set("No files selected")
    
    def launch_file_search(self):
        """Launch file search, finding all available indices for current directories."""
        dest_folders = set()
        # Get the parent directories of all located duplicate files
        for duplicate in self.duplicates:
            for dest_entry in duplicate.destinations:
                # We need the original root directory that was indexed
                # This is tricky. A simple approach is to find any index
                # inside the parent of the destination folder.
                dest_folders.add(dest_entry.path.parent)

        # Find all possible index files in the relevant directories
        available_indices = set()
        for folder in dest_folders:
            # Search in the parent directory of the folder containing the file
            if folder.parent.exists():
                for index_file in folder.parent.glob(f"{folder.name}_index*.caf"):
                    available_indices.add(index_file)

        if not available_indices:
            messagebox.showinfo("No Indices", "No search indices found for the directories in this scan.")
            return

        self.root.withdraw()
        search_gui = FileSearchGUI(list(available_indices))
        search_gui.run()
        search_gui.root.destroy()
        self.root.deiconify()
    
    def new_scan(self):
        """Flags that a new scan should be started."""
        self.action = 'new_scan' # Set a flag for the main loop
        self.root.quit()
    
    def run(self):
        """Run the results GUI"""
        self.root.mainloop()

# --- Core Logic Functions ---

def build_destination_index(config: ScanConfig, progress_callback=None, cancel_event=None) -> Optional[FileIndex]:
    """Builds a combined file index for all destination paths, using caching."""
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    
    if progress_callback:
        progress_callback("Building destination file index...", f"Processing {len(filtered_paths)} destination folders")
        
    # The combined_index doesn't have a single root, so we provide a dummy path.
    dummy_root = Path('.') 
    combined_index = FileIndex(dummy_root, config.use_hash, config.hash_algo)
    
    for i, dest_path in enumerate(filtered_paths):
        if cancel_event and cancel_event.is_set(): break
        if not dest_path.is_dir(): continue

        caf_path = get_caf_path(dest_path, config.hash_algo)
        dest_index = None

        if progress_callback:
            progress_callback(f"Processing folder {i+1}/{len(filtered_paths)}", f"Folder: {dest_path.name}")
        
        # Try to load existing index
        if config.reuse_indices and not config.recreate_indices and caf_path.exists():
            if progress_callback: progress_callback(f"Loading index for {dest_path.name}", "Please wait...")
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        
        # Build new index if needed
        if not dest_index:
            if progress_callback: progress_callback(f"Creating new index for {dest_path.name}", "Scanning files...")
            dest_index = FileIndex(dest_path, config.use_hash, config.hash_algo)
            
            # Use os.walk for efficiency
            for root, _, files in os.walk(dest_path):
                if cancel_event and cancel_event.is_set(): break
                root_path = Path(root)
                for j, filename in enumerate(files):
                    if cancel_event and cancel_event.is_set(): break
                    if progress_callback and j % 200 == 0:
                        progress_callback(f"Indexing {dest_path.name}", f"File: {filename}")
                    dest_index.add_file(root_path / filename)
            if cancel_event and cancel_event.is_set(): break

            # Save the newly created index
            if config.reuse_indices:
                if progress_callback: progress_callback(f"Saving index for {dest_path.name}", f"Path: {caf_path.name}")
                dest_index.save_to_caf(caf_path)
        
        if not dest_index: continue

        # Merge this destination's index into the combined one
        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files
        
    return combined_index

def find_duplicates_with_locations(source_path: Path, dest_index: FileIndex, 
                                 progress_callback=None, cancel_event=None) -> List[DuplicateMatch]:
    """Find duplicates with progress reporting"""
    duplicates = []
    source_files = [p for p in source_path.rglob('*') if p.is_file()]
    
    if progress_callback:
        progress_callback("Scanning source folder for duplicates", 
                         f"Checking {len(source_files)} files")
    
    for i, file_path in enumerate(source_files):
        if cancel_event and cancel_event.is_set():
            break
            
        if progress_callback and i % 50 == 0:
            progress_callback("Scanning for duplicates", 
                            f"Checked {i}/{len(source_files)} files")
        
        potential_matches = dest_index.find_potential_duplicates(file_path)
        
        if potential_matches:
            duplicates.append(DuplicateMatch(
                source_file=file_path,
                destinations=potential_matches
            ))
    
    return duplicates

def run_scan_with_progress(config: ScanConfig) -> List[DuplicateMatch]:
    """Run the complete scan with progress window - THREAD SAFE VERSION"""
    progress_gui = ProgressGUI()
    duplicates = []
    
    # Thread-safe communication queue
    progress_queue = queue.Queue()
    
    def update_progress_from_queue():
        """Safely updates GUI from main thread by checking the queue"""
        try:
            while True:
                message_type, operation, details = progress_queue.get_nowait()
                if message_type == "progress":
                    progress_gui.update_operation(operation)
                    progress_gui.update_details(details)
                elif message_type == "error":
                    messagebox.showerror("Error", f"Scan failed:\n{details}")
                elif message_type == "complete":
                    progress_gui.root.quit()
                    return  # Don't reschedule
        except queue.Empty:
            pass  # No new messages
        
        # Reschedule this check if thread is still running
        if scan_thread_obj.is_alive():
            progress_gui.root.after(100, update_progress_from_queue)
    
    def progress_callback(operation, details):
        """Thread-safe progress callback - puts messages in queue"""
        progress_queue.put(("progress", operation, details))
    
    def scan_thread():
        nonlocal duplicates
        try:
            # Build destination index
            dest_index = build_destination_index(config, progress_callback, progress_gui.cancelled)
            
            if not progress_gui.cancelled.is_set():
                # Find duplicates
                duplicates = find_duplicates_with_locations(config.source_path, dest_index, 
                                                          progress_callback, progress_gui.cancelled)
            
        except Exception as e:
            # Queue error message for safe display in main thread
            progress_queue.put(("error", "Error", str(e)))
        finally:
            # Signal completion to main thread
            progress_queue.put(("complete", "", ""))
    
    # Start scan in background thread
    scan_thread_obj = Thread(target=scan_thread)
    scan_thread_obj.daemon = True
    scan_thread_obj.start()
    
    # Start queue polling from main thread
    progress_gui.root.after(100, update_progress_from_queue)
    
    # Run progress GUI
    progress_gui.root.mainloop()
    progress_gui.root.destroy()
    
    # Wait for thread to complete
    scan_thread_obj.join(timeout=1.0)
    
    return duplicates if not progress_gui.cancelled.is_set() else []

def parse_size(size_str: str) -> int:
    """Parse size string like '5MB', '2.5GB' to bytes"""
    if not size_str or size_str.lower() == 'any':
        return 0
    
    size_str = size_str.strip().upper()
    
    # Corrected regex pattern
    match = re.match(r'^([\d.]+)\s*([KMGT]?B?)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    
    number = float(match.group(1))
    unit_str = match.group(2)
    
    # Handle single-letter units (K, M, G, T)
    if len(unit_str) == 1 and unit_str in "KMGT":
        unit = unit_str + 'B'
    elif not unit_str:
        unit = 'B'
    else:
        unit = unit_str

    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024**2,
        'GB': 1024**3,
        'TB': 1024**4
    }
    
    return int(number * multipliers.get(unit, 1))

def parse_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse date string in various formats"""
    if not date_str or date_str.lower() in ['any', '']:
        return None
    
    # Try common date formats
    formats = [
        '%Y-%m-%d',           # 2024-01-15
        '%d.%m.%Y',           # 15.01.2024
        '%d/%m/%Y',           # 15/01/2024
        '%m/%d/%Y',           # 01/15/2024
        '%Y-%m-%d %H:%M',     # 2024-01-15 14:30
        '%Y-%m-%d %H:%M:%S',  # 2024-01-15 14:30:45
    ]
    
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try relative dates
    date_str_lower = date_str.lower()
    now = datetime.datetime.now()
    
    if date_str_lower == 'today':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str_lower == 'yesterday':
        return (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str_lower == 'last week':
        return now - datetime.timedelta(days=7)
    elif date_str_lower == 'last month':
        return now - datetime.timedelta(days=30)
    
    raise ValueError(f"Invalid date format: {date_str}")

# --- File Search Functions ---

def search_files_in_index(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Search for files in index based on criteria"""
    results = []
    
    # Compile regex pattern if provided
    name_regex = None
    if criteria.name_pattern:
        try:
            name_regex = re.compile(criteria.name_pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
    
    # Search through all files in index
    for size, entries in file_index.size_index.items():
        # Size filtering
        if criteria.size_min is not None and size < criteria.size_min:
            continue
        if criteria.size_max is not None and size > criteria.size_max:
            continue
        
        for entry in entries:
            # Name filtering
            if name_regex and not name_regex.search(entry.path.name):
                continue
            
            # Date filtering
            if criteria.date_min or criteria.date_max:
                file_mtime = datetime.datetime.fromtimestamp(entry.mtime)
                
                if criteria.date_min and file_mtime < criteria.date_min:
                    continue
                if criteria.date_max and file_mtime > criteria.date_max:
                    continue
            
            # File passed all criteria
            results.append(SearchResult(
                path=entry.path,
                size=entry.size,
                mtime=entry.mtime,
                hash=entry.hash
            ))
    
    return results

def main_gui():
    """Main GUI workflow loop."""
    while True:
        # Setup phase
        setup = SetupGUI()
        config = setup.run()
        
        if not config:
            break  # User cancelled from setup

        # Scan phase
        method = f"{config.hash_algo.upper()} hash + size" if config.use_hash else "filename + size"
        if config.reuse_indices:
            method += " (with CAF indices)"
        
        duplicates = run_scan_with_progress(config)
        
        if not duplicates:
            if messagebox.askyesno("No Duplicates Found", "No duplicate files were found.\n\nWould you like to start a new scan?"):
                continue
            else:
                break
        
        # Results phase
        results_gui = DuplicateFinderGUI(duplicates, method)
        results_gui.action = None  # Initialize action flag
        results_gui.run()
        results_gui.root.destroy()
        
        if results_gui.action != 'new_scan':
            break # Exit loop if user didn't choose "New Scan"

def main():
    """Main entry point for both GUI and CLI modes."""
    parser = argparse.ArgumentParser(
        description="Enhanced duplicate file finder with GUI and CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  GUI Mode:
    python %(prog)s --gui

  CLI Mode:
    python %(prog)s "C:/ToScan" "D:/Archive" --hash sha1 --reuse-indices
    python %(prog)s ./source ./backup1 ./backup2 --output del_dupes.bat
"""
    )

    parser.add_argument('--gui', action='store_true',
                        help='Launch interactive GUI mode')
    parser.add_argument('source_folder', type=Path, nargs='?',
                        help='Source folder to scan for duplicates (CLI mode)')
    parser.add_argument('dest_folders', type=Path, nargs='*',
                        help='Destination folders to compare against (CLI mode)')
    parser.add_argument('--hash', choices=['md5', 'sha1', 'sha256'], default=None,
                        help='Use file hash for comparison (slower but more accurate)')
    parser.add_argument('--reuse-indices', action='store_true',
                        help='Save and reuse .caf index files for faster subsequent scans')
    parser.add_argument('--recreate-indices', action='store_true',
                        help='Force recreation of all index files')
    parser.add_argument('--output', type=Path,
                        help='Output path for the deletion script file')

    args = parser.parse_args()

    if args.gui:
        main_gui()
        return

    # --- CLI Implementation ---
    if not args.source_folder or not args.dest_folders:
        parser.error("Source and at least one destination folder are required for CLI mode.")

    if not args.source_folder.is_dir():
        print(f"Error: Source folder not found: {args.source_folder}")
        sys.exit(1)

    for path in args.dest_folders:
        if not path.is_dir():
            print(f"Error: Destination folder not found: {path}")
            sys.exit(1)

    config = ScanConfig(
        source_path=args.source_folder.resolve(),
        dest_paths=[p.resolve() for p in args.dest_folders],
        use_hash=bool(args.hash),
        hash_algo=args.hash or 'md5',
        reuse_indices=args.reuse_indices,
        recreate_indices=args.recreate_indices
    )
    
    print("Building destination index...")
    dest_index = build_destination_index(config)
    if not dest_index:
        print("Error: Failed to build destination index. Aborting.", file=sys.stderr)
        sys.exit(1)
    print(f"Destination index built with {dest_index.total_files} files.")

    print("\nScanning for duplicates...")
    duplicates = find_duplicates_with_locations(config.source_path, dest_index)

    if not duplicates:
        print("\n✅ No duplicate files found.")
        return

    total_size = sum(d.source_file.stat().st_size for d in duplicates)
    print(f"\nFound {len(duplicates)} duplicate files, totalling {format_size(total_size)}.")
    
    output_path = args.output or Path(get_default_script_name())
    try:
        platform_info = get_platform_info()
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(platform_info['script_header'])
            comment = "REM" if platform_info['name'] == 'Windows' else "#"
            f.write(f"{comment} Deletion script generated by Duplicate Finder on {dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{comment} This script will delete {len(duplicates)} source files found in other locations.\n\n")

            for match in duplicates:
                quoted_path = escape_script_path(match.source_file)
                f.write(f"{platform_info['delete_cmd']} {quoted_path}\n")
            
            f.write(f"\n{platform_info['echo_cmd']} \"Script finished. {len(duplicates)} files were targeted for deletion.\"\n")
            f.write(f"{platform_info['pause_cmd']}\n")
        
        make_script_executable(output_path)
        print(f"\n📝 Deletion script saved to: {output_path.resolve()}")
        print("    Please REVIEW THE SCRIPT carefully before executing it.")

    except Exception as e:
        print(f"\nError: Could not write deletion script: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()