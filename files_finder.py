#!/usr/bin/env python3
"""
Universal File Search and Index Tool - Complete Implementation

A comprehensive file indexing and search tool with duplicate detection capabilities.
Features:
- Auto-discovery of index files in current and home directories
- Multilingual support (English/German)
- Advanced file search with regex, size, and date filters
- Index catalog browsing and management
- Duplicate detection and handling
- Cross-platform compatibility
- Complete GUI with tabbed interface
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
import locale
import json

# --- Internationalization ---

class Translator:
    """Simple translation system for multilingual support."""
    
    def __init__(self):
        self.current_lang = 'en'
        self.translations = {
            'en': {
                # Main Interface
                'app_title': 'Universal File Search & Index Tool',
                'search_tab': 'Search Files',
                'manage_tab': 'Manage Indices',
                'duplicates_tab': 'Find Duplicates',
                'settings_tab': 'Settings',
                
                # Search Interface
                'search_criteria': 'Search Criteria',
                'name_pattern': 'Name (regex):',
                'name_examples': 'Examples: *.jpg, IMG_\\d+, (?i)vacation',
                'size_range': 'Size range:',
                'size_examples': ' (e.g., 1MB, 500KB)',
                'date_range': 'Date range:',
                'date_examples': ' (YYYY-MM-DD or \'today\', \'yesterday\')',
                'search_button': 'Search Files',
                'clear_button': 'Clear',
                'search_results': 'Search Results',
                'filename_col': 'Filename',
                'size_col': 'Size',
                'modified_col': 'Modified',
                'path_col': 'Full Path',
                'open_file': 'Open File',
                'open_folder': 'Open Folder',
                'copy_path': 'Copy Path',
                'export_results': 'Export Results',
                'close_button': 'Close',
                
                # Index Management
                'index_catalog': 'Index Catalog',
                'available_indices': 'Available Indices',
                'create_index': 'Create New Index',
                'refresh_indices': 'Refresh List',
                'delete_index': 'Delete Selected',
                'index_info': 'Index Information',
                'root_path': 'Root Path:',
                'file_count': 'Files:',
                'total_size': 'Total Size:',
                'created_date': 'Created:',
                'hash_method': 'Hash Method:',
                
                # Duplicate Detection
                'source_folder': 'Source Folder',
                'destination_folders': 'Destination Folders',
                'browse_button': 'Browse...',
                'add_folder': 'Add Folder',
                'remove_selected': 'Remove Selected',
                'clear_all': 'Clear All',
                'options': 'Options',
                'use_hash': 'Use file hashes for comparison',
                'reuse_indices': 'Reuse existing indices',
                'force_recreation': 'Force recreation of indices',
                'start_scan': 'Start Scan',
                'new_scan': 'New Scan',
                'exit_button': 'Exit',

                'method': 'Method',
                'found': 'Found',
                'files_with_duplicates': 'files with duplicates',
                'total_size': 'Total Size',
                
                # Results and Actions
                'duplicate_manager': 'Duplicate File Manager',
                'information': 'Information',
                'filter': 'Filter',
                'regex_filter': 'Regex filter:',
                'select_all_filtered': 'Select All Filtered',
                'deselect_all': 'Deselect All',
                'delete_selected': 'Delete Selected Files',
                'generate_script': 'Generate Script...',
                
                # Progress
                'initializing': 'Initializing...',
                'scanning_files': 'Scanning files...',
                'building_index': 'Building index...',
                'finding_duplicates': 'Finding duplicates...',
                'cancel_button': 'Cancel',
                
                # Messages
                'no_results': 'No search results to export.',
                'export_complete': 'Results exported to:\n{}',
                'export_error': 'Failed to export results:\n{}',
                'search_error': 'Search failed:\n{}',
                'no_duplicates': 'No duplicate files were found.\n\nWould you like to start a new scan?',
                'confirm_deletion': 'Are you sure you want to permanently delete {} files ({})?\n\nThis action CANNOT be undone.',
                'deletion_complete': 'Successfully deleted {} of {} selected files.',
                'script_generated': 'Deletion script was successfully saved to:\n{}',
                'ready_status': 'Ready to search {} indexed locations',
                'searching_status': 'Searching...',
                'found_status': 'Found {} files matching criteria',
                'selected_status': 'Selected: {} files ({:.1f} MB)',
                'no_selection_status': 'No files selected',
                'path_copied': 'Copied path to clipboard: {}',
                'select_source': 'Please select a source folder',
                'select_dest': 'Please add at least one destination folder',
                
                # Settings
                'language': 'Language:',
                'default_hash': 'Default Hash Algorithm:',
                'auto_load_indices': 'Auto-load indices on startup',
                'index_locations': 'Index Search Locations:',
                'add_location': 'Add Location',
                'remove_location': 'Remove Location',
                'apply_settings': 'Apply Settings',
                
                # Errors
                'error': 'Error',
                'file_not_found': 'File no longer exists:\n{}',
                'invalid_regex': 'Invalid regex pattern: {}',
                'invalid_size': 'Invalid size format: {}',
                'invalid_date': 'Invalid date format: {}',
                'scan_failed': 'Scan failed:\n{}',
                'no_indices': 'No search indices found.',
                'no_selection': 'No files are selected.',
                'duplicate_folder': 'This folder is already in the list.',
            },
            
            'de': {
                # Main Interface
                'app_title': 'Universelles Datei-Such- & Index-Tool',
                'search_tab': 'Dateien suchen',
                'manage_tab': 'Indices verwalten',
                'duplicates_tab': 'Duplikate finden',
                'settings_tab': 'Einstellungen',
                
                # Search Interface
                'search_criteria': 'Suchkriterien',
                'name_pattern': 'Name (regex):',
                'name_examples': 'Beispiele: *.jpg, IMG_\\d+, (?i)urlaub',
                'size_range': 'Größenbereich:',
                'size_examples': ' (z.B. 1MB, 500KB)',
                'date_range': 'Datumsbereich:',
                'date_examples': ' (JJJJ-MM-TT oder \'heute\', \'gestern\')',
                'search_button': 'Dateien suchen',
                'clear_button': 'Löschen',
                'search_results': 'Suchergebnisse',
                'filename_col': 'Dateiname',
                'size_col': 'Größe',
                'modified_col': 'Geändert',
                'path_col': 'Vollständiger Pfad',
                'open_file': 'Datei öffnen',
                'open_folder': 'Ordner öffnen',
                'copy_path': 'Pfad kopieren',
                'export_results': 'Ergebnisse exportieren',
                'close_button': 'Schließen',
                
                # Index Management
                'index_catalog': 'Index-Katalog',
                'available_indices': 'Verfügbare Indices',
                'create_index': 'Neuen Index erstellen',
                'refresh_indices': 'Liste aktualisieren',
                'delete_index': 'Ausgewählte löschen',
                'index_info': 'Index-Informationen',
                'root_path': 'Stammpfad:',
                'file_count': 'Dateien:',
                'total_size': 'Gesamtgröße:',
                'created_date': 'Erstellt:',
                'hash_method': 'Hash-Methode:',
                
                # Duplicate Detection
                'source_folder': 'Quellordner',
                'destination_folders': 'Zielordner',
                'browse_button': 'Durchsuchen...',
                'add_folder': 'Ordner hinzufügen',
                'remove_selected': 'Ausgewählte entfernen',
                'clear_all': 'Alle löschen',
                'options': 'Optionen',
                'use_hash': 'Dateihashes für Vergleich verwenden',
                'reuse_indices': 'Vorhandene Indices wiederverwenden',
                'force_recreation': 'Neuerststellung der Indices erzwingen',
                'start_scan': 'Scan starten',
                'new_scan': 'Neuer Scan',
                'exit_button': 'Beenden',

                'method': 'Methode',
                'found': 'Gefunden',
                'files_with_duplicates': 'Dateien mit Duplikaten',
                'total_size': 'Gesamtgröße',
                
                # Results and Actions
                'duplicate_manager': 'Duplikat-Dateiverwaltung',
                'information': 'Information',
                'filter': 'Filter',
                'regex_filter': 'Regex-Filter:',
                'select_all_filtered': 'Alle gefilterten auswählen',
                'deselect_all': 'Alle abwählen',
                'delete_selected': 'Ausgewählte Dateien löschen',
                'generate_script': 'Skript generieren...',
                
                # Progress
                'initializing': 'Initialisierung...',
                'scanning_files': 'Scanne Dateien...',
                'building_index': 'Erstelle Index...',
                'finding_duplicates': 'Suche Duplikate...',
                'cancel_button': 'Abbrechen',
                
                # Messages
                'no_results': 'Keine Suchergebnisse zum Exportieren.',
                'export_complete': 'Ergebnisse exportiert nach:\n{}',
                'export_error': 'Fehler beim Exportieren der Ergebnisse:\n{}',
                'search_error': 'Suche fehlgeschlagen:\n{}',
                'no_duplicates': 'Keine doppelten Dateien gefunden.\n\nMöchten Sie einen neuen Scan starten?',
                'confirm_deletion': 'Sind Sie sicher, dass Sie {} Dateien ({}) dauerhaft löschen möchten?\n\nDiese Aktion kann NICHT rückgängig gemacht werden.',
                'deletion_complete': 'Erfolgreich {} von {} ausgewählten Dateien gelöscht.',
                'script_generated': 'Löschskript wurde erfolgreich gespeichert unter:\n{}',
                'ready_status': 'Bereit zum Durchsuchen von {} indexierten Standorten',
                'searching_status': 'Suche läuft...',
                'found_status': '{} Dateien gefunden, die den Kriterien entsprechen',
                'selected_status': 'Ausgewählt: {} Dateien ({:.1f} MB)',
                'no_selection_status': 'Keine Dateien ausgewählt',
                'path_copied': 'Pfad in Zwischenablage kopiert: {}',
                'select_source': 'Bitte wählen Sie einen Quellordner',
                'select_dest': 'Bitte fügen Sie mindestens einen Zielordner hinzu',
                
                # Settings
                'language': 'Sprache:',
                'default_hash': 'Standard-Hash-Algorithmus:',
                'auto_load_indices': 'Indices beim Start automatisch laden',
                'index_locations': 'Index-Suchpfade:',
                'add_location': 'Pfad hinzufügen',
                'remove_location': 'Pfad entfernen',
                'apply_settings': 'Einstellungen anwenden',
                
                # Errors
                'error': 'Fehler',
                'file_not_found': 'Datei existiert nicht mehr:\n{}',
                'invalid_regex': 'Ungültiges Regex-Muster: {}',
                'invalid_size': 'Ungültiges Größenformat: {}',
                'invalid_date': 'Ungültiges Datumsformat: {}',
                'scan_failed': 'Scan fehlgeschlagen:\n{}',
                'no_indices': 'Keine Suchindices gefunden.',
                'no_selection': 'Keine Dateien ausgewählt.',
                'duplicate_folder': 'Dieser Ordner ist bereits in der Liste.',
            }
        }
        
        # Auto-detect system language
        try:
            system_lang = locale.getdefaultlocale()[0]
            if system_lang and system_lang.startswith('de'):
                self.current_lang = 'de'
        except:
            pass
    
    def set_language(self, lang_code: str):
        """Set the current language."""
        if lang_code in self.translations:
            self.current_lang = lang_code
    
    def get(self, key: str, *args) -> str:
        """Get translated string, with optional formatting."""
        text = self.translations[self.current_lang].get(key, key)
        if args:
            try:
                return text.format(*args)
            except:
                return text
        return text

# Global translator instance
t = Translator()

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

class IndexInfo(NamedTuple):
    """Information about an index file"""
    path: Path
    root_path: Path
    file_count: int
    total_size: int
    created_date: dt
    hash_method: str

class ScanConfig(NamedTuple):
    """Configuration for a duplicate scanning operation."""
    source_path: Path
    dest_paths: List[Path]
    use_hash: bool
    hash_algo: str
    reuse_indices: bool
    recreate_indices: bool

# --- Configuration Management ---

class Config:
    """Application configuration manager."""
    
    def __init__(self):
        self.config_file = Path.home() / '.universal_search_config.json'
        self.default_config = {
            'language': 'en',
            'default_hash_algo': 'md5',
            'auto_load_indices': True,
            'index_search_locations': [
                str(Path.cwd()),
                str(Path.home()),
                str(Path.home() / 'Desktop'),
                str(Path.home() / 'Documents')
            ],
            'window_geometry': None
        }
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge with defaults
                    config = self.default_config.copy()
                    config.update(loaded)
                    return config
            except Exception:
                pass
        return self.default_config.copy()
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get(self, key: str, default=None):
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """Set configuration value."""
        self.config[key] = value

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

def get_screen_geometry() -> Tuple[int, int]:
    """Gets primary screen dimensions."""
    root = tk.Tk()
    root.withdraw()
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.destroy()
    return width, height

def calculate_window_geometry(screen_width: int, screen_height: int) -> str:
    """Calculates a responsive and centered window geometry string."""
    width = max(900, min(1400, int(screen_width * 0.85)))
    height = max(700, min(1000, int(screen_height * 0.85)))
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    return f"{width}x{height}+{x}+{y}"

def open_file_or_folder(path: Path, open_folder: bool = False):
    """Opens a file or its containing folder using the OS default."""
    try:
        target = path.parent if open_folder else path
        if not target.exists():
            messagebox.showerror(t.get('error'), t.get('file_not_found', target))
            return
        system = platform.system().lower()
        if system == 'windows':
            os.startfile(target)
        elif system == 'darwin':
            subprocess.run(['open', str(target)], check=False)
        else: # Linux
            subprocess.run(['xdg-open', str(target)], check=False)
    except Exception as e:
        messagebox.showerror(t.get('error'), str(e))

def make_script_executable(script_path: Path):
    """Makes a script executable on Unix-like systems."""
    if platform.system().lower() != 'windows':
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

def get_caf_path(dest_path: Path, hash_algo: str) -> Path:
    """Generates a consistent CAF file path based on hash algorithm."""
    suffix = f"_{hash_algo}" if hash_algo != 'md5' else ""
    return dest_path.parent / f"{dest_path.name}_index{suffix}.caf"

def get_default_script_name() -> str:
    """Generates a default script name with a timestamp."""
    platform_info = get_platform_info()
    return f'delete_duplicates_{dt.now().strftime("%Y%m%d_%H%M%S")}{platform_info["script_ext"]}'

def escape_script_path(path: Path) -> str:
    """Escapes a file path for use in a shell/batch script."""
    return get_platform_info()['path_quote'](path)

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

# --- Core File Index Classes ---

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

# --- Index Discovery and Management ---

class IndexDiscovery:
    """Discovers and manages index files."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def discover_indices(self) -> List[Path]:
        """Discover all .caf index files in configured locations."""
        indices = []
        search_locations = self.config.get('index_search_locations', [])
        
        for location_str in search_locations:
            try:
                location = Path(location_str)
                if location.exists() and location.is_dir():
                    # Find all .caf files
                    for caf_file in location.glob('*.caf'):
                        if caf_file.is_file():
                            indices.append(caf_file)
                    # Also search one level deep
                    for subdir in location.iterdir():
                        if subdir.is_dir():
                            for caf_file in subdir.glob('*.caf'):
                                if caf_file.is_file():
                                    indices.append(caf_file)
            except Exception:
                continue
        
        return list(set(indices))  # Remove duplicates
    
    def get_index_info(self, caf_path: Path) -> Optional[IndexInfo]:
        """Extract information about an index file."""
        try:
            # Quick parsing of CAF header
            with caf_path.open('rb') as f:
                magic = struct.unpack('<L', f.read(4))[0]
                if not (magic > 0 and magic % 1000000000 == 500410407):
                    return None
                
                version = struct.unpack('<h', f.read(2))[0]
                created_timestamp = struct.unpack('<L', f.read(4))[0]
                
                # Read device (root path)
                root_path_str = self._read_caf_string(f)
                
                # Simplified approach for file count and size
                # In a full implementation, you'd parse the entire header properly
                file_count = 0
                total_size = caf_path.stat().st_size  # Use file size as approximation
                
                # Determine hash method from filename
                name = caf_path.stem.lower()
                if '_sha256' in name:
                    hash_method = 'SHA256'
                elif '_sha1' in name:
                    hash_method = 'SHA1'
                elif '_md5' in name or 'index' in name:
                    hash_method = 'MD5'
                else:
                    hash_method = 'None'
                
                return IndexInfo(
                    path=caf_path,
                    root_path=Path(root_path_str) if root_path_str else caf_path.parent,
                    file_count=file_count,
                    total_size=total_size,
                    created_date=dt.fromtimestamp(created_timestamp),
                    hash_method=hash_method
                )
        except Exception:
            return None
    
    def _read_caf_string(self, buffer) -> str:
        """Read null-terminated string from CAF file."""
        chars = bytearray()
        while (char := buffer.read(1)) != b'\x00':
            if not char:
                break
            chars.extend(char)
        return chars.decode('utf-8', errors='replace')

# --- Progress GUI ---

class ProgressWindow:
    """Progress window for long-running operations."""
    
    def __init__(self, parent=None, title="Progress"):
        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title(title)
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        self.cancelled = Event()
        self.setup_ui()
        
        # Center on parent
        if parent:
            self.root.transient(parent)
            self.root.grab_set()
    
    def setup_ui(self):
        """Setup progress UI"""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Current operation
        self.operation_var = tk.StringVar(value=t.get('initializing'))
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
        ttk.Button(main_frame, text=t.get('cancel_button'), 
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

# --- Duplicate Results GUI ---

class DuplicateResultsWindow:
    """Window for displaying and managing duplicate results."""
    
    def __init__(self, parent, duplicates: List[DuplicateMatch], method: str):
        self.parent = parent
        self.duplicates = duplicates
        self.method = method
        self.selected_for_deletion = set()
        self.action = None
        
        self.root = tk.Toplevel(parent.root)
        self.root.title(t.get('duplicate_manager'))
        
        # Responsive geometry
        screen_width, screen_height = get_screen_geometry()
        geometry = calculate_window_geometry(screen_width, screen_height)
        self.root.geometry(geometry)
        
        self.setup_ui()
        self.populate_tree()
        
        # Make modal
        self.root.transient(parent.root)
        self.root.grab_set()
    
    def setup_ui(self):
        """Setup the GUI components"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text=t.get('information'), padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        try:
            total_size_bytes = sum(d.source_file.stat().st_size for d in self.duplicates if d.source_file.exists())
        except:
            total_size_bytes = 0
            
        info_text = f"Method: {self.method} | Found {len(self.duplicates)} files with duplicates | Total Size: {format_size(total_size_bytes)}"
        ttk.Label(info_frame, text=info_text).pack(anchor=tk.W)
        
        # Filter frame
        filter_frame = ttk.LabelFrame(main_frame, text=t.get('filter'), padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        filter_inner = ttk.Frame(filter_frame)
        filter_inner.pack(fill=tk.X)
        
        ttk.Label(filter_inner, text=t.get('regex_filter')).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_inner, textvariable=self.filter_var)
        self.filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self.filter_entry.bind('<KeyRelease>', self.on_filter_change)
        
        ttk.Button(filter_inner, text=t.get('select_all_filtered'), command=self.select_all_filtered).pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(filter_inner, text=t.get('deselect_all'), command=self.deselect_all).pack(side=tk.RIGHT, padx=(0, 5))
        
        # Tree frame
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Size', 'Path')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.tree.heading('#0', text='File')
        self.tree.heading('Size', text='Size')
        self.tree.heading('Path', text='Path')
        
        # Column widths
        self.tree.column('#0', width=300, minwidth=200)
        self.tree.column('Size', width=120, minwidth=100)
        self.tree.column('Path', width=500, minwidth=400)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<space>', self.on_space_key)
        self.tree.bind('<Control-c>', self.copy_path_to_clipboard)
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text=t.get('delete_selected'), command=self.delete_selected_files).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=t.get('generate_script'), command=self.generate_script).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('new_scan'), command=self.new_scan).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('close_button'), command=self.close).pack(side=tk.RIGHT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set(t.get('no_selection_status'))
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def populate_tree(self):
        """Populate the tree view with duplicates"""
        for i, duplicate in enumerate(self.duplicates):
            try:
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
            except OSError:
                continue
    
    def on_filter_change(self, event):
        """Handle filter text changes"""
        filter_text = self.filter_var.get()
        if not filter_text:
            # Show all items
            for item in self.tree.get_children():
                self.tree.item(item, tags=self.tree.item(item, 'tags'))
            return
        
        try:
            pattern = re.compile(filter_text, re.IGNORECASE)
            for item in self.tree.get_children():
                source_path = self.tree.item(item, 'values')[1]
                if pattern.search(source_path):
                    # Keep visible
                    pass
                else:
                    # Hide by changing tags
                    current_tags = list(self.tree.item(item, 'tags'))
                    if 'hidden' not in current_tags:
                        current_tags.append('hidden')
                    self.tree.item(item, tags=tuple(current_tags))
        except re.error:
            pass
    
    def on_tree_click(self, event):
        """Handle tree item clicks for selection"""
        item = self.tree.identify_row(event.y)
        if item:
            tags = self.tree.item(item, 'tags')
            if 'source' in tags and 'hidden' not in tags:
                self.toggle_selection(item)
    
    def on_space_key(self, event):
        """Handle space key for selection"""
        item = self.tree.focus()
        if item:
            tags = self.tree.item(item, 'tags')
            if 'source' in tags and 'hidden' not in tags:
                self.toggle_selection(item)
    
    def on_double_click(self, event):
        """Handle double-click to open file"""
        item = self.tree.identify_row(event.y)
        if item and 'hidden' not in self.tree.item(item, 'tags'):
            path_str = self.tree.item(item, 'values')[1]
            path = Path(path_str)
            if path.exists():
                open_file_or_folder(path)
    
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
            tags = self.tree.item(item, 'tags')
            if 'source' in tags and 'hidden' not in tags and item not in self.selected_for_deletion:
                self.toggle_selection(item)
    
    def deselect_all(self):
        """Deselect all items"""
        for item in list(self.selected_for_deletion):
            self.toggle_selection(item)
    
    def update_status(self):
        """Update status bar with selection count"""
        count = len(self.selected_for_deletion)
        if count > 0:
            try:
                total_size = sum(Path(self.tree.item(item, 'values')[1]).stat().st_size 
                               for item in self.selected_for_deletion)
                self.status_var.set(f"Selected: {count} files ({total_size/1024/1024:.1f} MB)")
            except:
                self.status_var.set(f"Selected: {count} files")
        else:
            self.status_var.set(t.get('no_selection_status'))
    
    def delete_selected_files(self):
        """Delete selected files directly"""
        if not self.selected_for_deletion:
            messagebox.showwarning("Warning", t.get('no_selection'))
            return

        count = len(self.selected_for_deletion)
        try:
            total_size = sum(Path(self.tree.item(item, 'values')[1]).stat().st_size for item in self.selected_for_deletion)
        except (OSError, IndexError):
            messagebox.showerror("Error", "Could not calculate size of selected files.")
            return

        # Safety confirmation dialog
        if not messagebox.askyesno("Confirm Deletion",
                                   f"Are you sure you want to permanently delete {count} files ({format_size(total_size)})?\n\nThis action CANNOT be undone."):
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
    
    def generate_script(self):
        """Generate a script file to delete the selected items"""
        if not self.selected_for_deletion:
            messagebox.showwarning("Warning", t.get('no_selection'))
            return
            
        platform_info = get_platform_info()
        default_name = get_default_script_name()
        
        file_types = [
            (f"{platform_info['name']} scripts", f"*{platform_info['script_ext']}"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.asksaveasfilename(
            title=f"Save {platform_info['name']} Deletion Script",
            defaultextension=platform_info['script_ext'],
            filetypes=file_types,
            initialfile=default_name
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(platform_info['script_header'])
                    comment = "REM" if platform_info['name'] == 'Windows' else "#"
                    f.write(f"{comment} Deletion script generated on {dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    
                    for item in self.selected_for_deletion:
                        file_path = Path(self.tree.item(item, 'values')[1])
                        quoted_path = escape_script_path(file_path)
                        f.write(f"{platform_info['delete_cmd']} {quoted_path}\n")
                    
                    f.write(f"\n{platform_info['echo_cmd']} \"Script finished.\"\n{platform_info['pause_cmd']}\n")
                
                make_script_executable(Path(filename))
                messagebox.showinfo("Success", f"Deletion script was successfully saved to:\n{filename}")

            except OSError as e:
                messagebox.showerror("Error", str(e))
    
    def copy_path_to_clipboard(self, event):
        """Copy selected file path to clipboard"""
        item = self.tree.focus()
        if item:
            path_value = self.tree.item(item, 'values')
            if path_value and len(path_value) > 1:
                self.root.clipboard_clear()
                self.root.clipboard_append(path_value[1])
                self.status_var.set(f"Copied path to clipboard: {Path(path_value[1]).name}")
                self.root.after(2000, self.update_status)
    
    def new_scan(self):
        """Signal that a new scan should be started"""
        self.action = 'new_scan'
        self.close()
    
    def close(self):
        """Close the window"""
        self.root.destroy()

# --- Core Logic Functions ---

def build_destination_index(config: ScanConfig, progress_callback=None, cancel_event=None) -> Optional[FileIndex]:
    """Builds a combined file index for all destination paths, using caching."""
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    
    if progress_callback:
        progress_callback(t.get('building_index'), f"Processing {len(filtered_paths)} destination folders")
        
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
            if progress_callback: progress_callback(f"Creating new index for {dest_path.name}", t.get('scanning_files'))
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
        progress_callback(t.get('finding_duplicates'), 
                         f"Checking {len(source_files)} files")
    
    for i, file_path in enumerate(source_files):
        if cancel_event and cancel_event.is_set():
            break
            
        if progress_callback and i % 50 == 0:
            progress_callback(t.get('finding_duplicates'), 
                            f"Checked {i}/{len(source_files)} files")
        
        potential_matches = dest_index.find_potential_duplicates(file_path)
        
        if potential_matches:
            duplicates.append(DuplicateMatch(
                source_file=file_path,
                destinations=potential_matches
            ))
    
    return duplicates

def search_files_in_index(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Search for files in index based on criteria"""
    results = []
    
    # Compile regex pattern if provided
    name_regex = None
    if criteria.name_pattern:
        try:
            name_regex = re.compile(criteria.name_pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(t.get('invalid_regex', e))
    
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
                file_mtime = dt.fromtimestamp(entry.mtime)
                
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

def run_scan_with_progress(config: ScanConfig, parent) -> List[DuplicateMatch]:
    """Run the complete scan with progress window"""
    progress_window = ProgressWindow(parent, t.get('finding_duplicates'))
    duplicates = []
    
    # Thread-safe communication queue
    progress_queue = queue.Queue()
    
    def update_progress_from_queue():
        """Safely updates GUI from main thread by checking the queue"""
        try:
            while True:
                message_type, operation, details = progress_queue.get_nowait()
                if message_type == "progress":
                    progress_window.update_operation(operation)
                    progress_window.update_details(details)
                elif message_type == "error":
                    messagebox.showerror(t.get('error'), t.get('scan_failed', details))
                elif message_type == "complete":
                    progress_window.root.quit()
                    return
        except queue.Empty:
            pass
        
        # Reschedule this check if thread is still running
        if scan_thread_obj.is_alive():
            progress_window.root.after(100, update_progress_from_queue)
    
    def progress_callback(operation, details):
        """Thread-safe progress callback"""
        progress_queue.put(("progress", operation, details))
    
    def scan_thread():
        nonlocal duplicates
        try:
            # Build destination index
            dest_index = build_destination_index(config, progress_callback, progress_window.cancelled)
            
            if not progress_window.cancelled.is_set() and dest_index:
                # Find duplicates
                duplicates = find_duplicates_with_locations(config.source_path, dest_index, 
                                                          progress_callback, progress_window.cancelled)
            
        except Exception as e:
            progress_queue.put(("error", "Error", str(e)))
        finally:
            progress_queue.put(("complete", "", ""))
    
    # Start scan in background thread
    scan_thread_obj = Thread(target=scan_thread)
    scan_thread_obj.daemon = True
    scan_thread_obj.start()
    
    # Start queue polling from main thread
    progress_window.root.after(100, update_progress_from_queue)
    
    # Run progress GUI
    progress_window.root.mainloop()
    progress_window.root.destroy()
    
    # Wait for thread to complete
    scan_thread_obj.join(timeout=1.0)
    
    return duplicates if not progress_window.cancelled.is_set() else []

# --- Main Application GUI ---

class UniversalSearchApp:
    """Main application with tabbed interface."""
    
    def __init__(self):
        self.config = Config()
        
        # Apply language setting
        t.set_language(self.config.get('language', 'en'))
        
        self.root = tk.Tk()
        self.root.title(t.get('app_title'))
        
        # Set up geometry
        screen_width, screen_height = get_screen_geometry()
        saved_geometry = self.config.get('window_geometry')
        if saved_geometry:
            self.root.geometry(saved_geometry)
        else:
            geometry = calculate_window_geometry(screen_width, screen_height)
            self.root.geometry(geometry)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize components
        self.index_discovery = IndexDiscovery(self.config)
        self.available_indices = []
        self.search_results = []
        
        # Duplicate scan variables
        self.dup_source_path = None
        self.dup_dest_paths = []
        
        self.setup_ui()
        
        # Auto-load indices if enabled
        if self.config.get('auto_load_indices', True):
            self.refresh_indices()
    
    def setup_ui(self):
        """Setup the main tabbed interface."""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.search_frame = ttk.Frame(self.notebook)
        self.manage_frame = ttk.Frame(self.notebook)
        self.duplicates_frame = ttk.Frame(self.notebook)
        self.settings_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.search_frame, text=t.get('search_tab'))
        self.notebook.add(self.manage_frame, text=t.get('manage_tab'))
        self.notebook.add(self.duplicates_frame, text=t.get('duplicates_tab'))
        self.notebook.add(self.settings_frame, text=t.get('settings_tab'))
        
        # Setup individual tabs
        self.setup_search_tab()
        self.setup_manage_tab()
        self.setup_duplicates_tab()
        self.setup_settings_tab()
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.update_status()
    
    def setup_search_tab(self):
        """Setup the main search interface."""
        main_frame = ttk.Frame(self.search_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Search criteria frame
        criteria_frame = ttk.LabelFrame(main_frame, text=t.get('search_criteria'), padding=10)
        criteria_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Name pattern
        name_frame = ttk.Frame(criteria_frame)
        name_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(name_frame, text=t.get('name_pattern'), width=15).pack(side=tk.LEFT)
        self.search_name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.search_name_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(name_frame, text=t.get('name_examples'), foreground='gray').pack(side=tk.RIGHT)
        
        # Size range
        size_frame = ttk.Frame(criteria_frame)
        size_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(size_frame, text=t.get('size_range'), width=15).pack(side=tk.LEFT)
        
        size_inner = ttk.Frame(size_frame)
        size_inner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_size_min_var = tk.StringVar()
        ttk.Entry(size_inner, textvariable=self.search_size_min_var, width=15).pack(side=tk.LEFT)
        ttk.Label(size_inner, text=" - ").pack(side=tk.LEFT)
        self.search_size_max_var = tk.StringVar()
        ttk.Entry(size_inner, textvariable=self.search_size_max_var, width=15).pack(side=tk.LEFT)
        ttk.Label(size_inner, text=t.get('size_examples'), foreground='gray').pack(side=tk.LEFT, padx=(5, 0))
        
        # Date range
        date_frame = ttk.Frame(criteria_frame)
        date_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(date_frame, text=t.get('date_range'), width=15).pack(side=tk.LEFT)
        
        date_inner = ttk.Frame(date_frame)
        date_inner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_date_min_var = tk.StringVar()
        ttk.Entry(date_inner, textvariable=self.search_date_min_var, width=15).pack(side=tk.LEFT)
        ttk.Label(date_inner, text=" - ").pack(side=tk.LEFT)
        self.search_date_max_var = tk.StringVar()
        ttk.Entry(date_inner, textvariable=self.search_date_max_var, width=15).pack(side=tk.LEFT)
        ttk.Label(date_inner, text=t.get('date_examples'), foreground='gray').pack(side=tk.LEFT, padx=(5, 0))
        
        # Search buttons
        search_btn_frame = ttk.Frame(criteria_frame)
        search_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(search_btn_frame, text=t.get('search_button'), command=self.perform_search).pack(side=tk.LEFT)
        ttk.Button(search_btn_frame, text=t.get('clear_button'), command=self.clear_search_criteria).pack(side=tk.LEFT, padx=(10, 0))
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text=t.get('search_results'), padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Results tree
        tree_frame = ttk.Frame(results_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = (t.get('size_col'), t.get('modified_col'), t.get('path_col'))
        self.search_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.search_tree.heading('#0', text=t.get('filename_col'))
        self.search_tree.heading(t.get('size_col'), text=t.get('size_col'))
        self.search_tree.heading(t.get('modified_col'), text=t.get('modified_col'))
        self.search_tree.heading(t.get('path_col'), text=t.get('path_col'))
        
        # Column widths
        self.search_tree.column('#0', width=250, minwidth=200)
        self.search_tree.column(t.get('size_col'), width=100, minwidth=80)
        self.search_tree.column(t.get('modified_col'), width=150, minwidth=120)
        self.search_tree.column(t.get('path_col'), width=400, minwidth=300)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.search_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.search_tree.xview)
        self.search_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.search_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.search_tree.bind('<Double-Button-1>', self.on_search_double_click)
        self.search_tree.bind('<Button-3>', self.on_search_right_click)
        
        # Action buttons
        action_frame = ttk.Frame(results_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text=t.get('open_file'), command=self.open_search_file).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=t.get('open_folder'), command=self.open_search_folder).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('copy_path'), command=self.copy_search_path).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('export_results'), command=self.export_search_results).pack(side=tk.LEFT, padx=(10, 0))
    
    def setup_manage_tab(self):
        """Setup the index management interface."""
        main_frame = ttk.Frame(self.manage_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Index list frame
        list_frame = ttk.LabelFrame(main_frame, text=t.get('available_indices'), padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Index tree
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('Root Path', 'Files', 'Size', 'Created', 'Hash')
        self.index_tree = ttk.Treeview(tree_frame, columns=columns, show='tree headings')
        self.index_tree.heading('#0', text='Index File')
        for col in columns:
            self.index_tree.heading(col, text=col)
        
        # Column widths
        self.index_tree.column('#0', width=200, minwidth=150)
        self.index_tree.column('Root Path', width=300, minwidth=250)
        self.index_tree.column('Files', width=80, minwidth=60)
        self.index_tree.column('Size', width=100, minwidth=80)
        self.index_tree.column('Created', width=120, minwidth=100)
        self.index_tree.column('Hash', width=80, minwidth=60)
        
        # Scrollbars
        v_scrollbar2 = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.index_tree.yview)
        h_scrollbar2 = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.index_tree.xview)
        self.index_tree.configure(yscrollcommand=v_scrollbar2.set, xscrollcommand=h_scrollbar2.set)
        
        self.index_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar2.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.index_tree.bind('<<TreeviewSelect>>', self.on_index_select)
        self.index_tree.bind('<Double-Button-1>', self.on_index_double_click)
        
        # Action buttons
        action_frame = ttk.Frame(list_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text=t.get('create_index'), command=self.create_new_index).pack(side=tk.LEFT)
        ttk.Button(action_frame, text=t.get('refresh_indices'), command=self.refresh_indices).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(action_frame, text=t.get('delete_index'), command=self.delete_selected_index).pack(side=tk.LEFT, padx=(10, 0))
        
        # Index info frame
        info_frame = ttk.LabelFrame(main_frame, text=t.get('index_info'), padding=10)
        info_frame.pack(fill=tk.X)
        
        self.index_info_var = tk.StringVar()
        self.index_info_var.set("Select an index to view details")
        ttk.Label(info_frame, textvariable=self.index_info_var, justify=tk.LEFT).pack(anchor=tk.W, fill=tk.X)
    
    def setup_duplicates_tab(self):
        """Setup the duplicate detection interface."""
        main_frame = ttk.Frame(self.duplicates_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        ttk.Label(main_frame, text=t.get('duplicates_tab'), 
                 font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 20))
        
        # Source selection
        source_frame = ttk.LabelFrame(main_frame, text=t.get('source_folder'), padding=10)
        source_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.dup_source_var = tk.StringVar()
        source_entry = ttk.Entry(source_frame, textvariable=self.dup_source_var, width=50)
        source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(source_frame, text=t.get('browse_button'), 
                  command=self.select_duplicate_source).pack(side=tk.RIGHT, padx=(10, 0))
        
        # Destination selection
        dest_frame = ttk.LabelFrame(main_frame, text=t.get('destination_folders'), padding=10)
        dest_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Destination list with scrollbar
        list_frame = ttk.Frame(dest_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.dup_dest_listbox = tk.Listbox(list_frame, height=6)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.dup_dest_listbox.yview)
        self.dup_dest_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.dup_dest_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Destination buttons
        dest_buttons = ttk.Frame(dest_frame)
        dest_buttons.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(dest_buttons, text=t.get('add_folder'), 
                  command=self.add_dup_dest_folder).pack(side=tk.LEFT)
        ttk.Button(dest_buttons, text=t.get('remove_selected'), 
                  command=self.remove_dup_dest_folder).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(dest_buttons, text=t.get('clear_all'), 
                  command=self.clear_dup_dest_folders).pack(side=tk.LEFT, padx=(10, 0))
        
        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text=t.get('options'), padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Hash options
        hash_frame = ttk.Frame(options_frame)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.dup_use_hash_var = tk.BooleanVar(value=True)
        hash_check = ttk.Checkbutton(hash_frame, text=t.get('use_hash'), 
                                    variable=self.dup_use_hash_var, command=self.on_dup_hash_toggle)
        hash_check.pack(side=tk.LEFT)
        
        self.dup_hash_algo_var = tk.StringVar(value=self.config.get('default_hash_algo', 'md5'))
        self.dup_hash_combo = ttk.Combobox(hash_frame, textvariable=self.dup_hash_algo_var, 
                                          values=["md5", "sha1", "sha256"], width=10, state="readonly")
        self.dup_hash_combo.pack(side=tk.LEFT, padx=(10, 0))
        
        # Index options
        index_frame = ttk.Frame(options_frame)
        index_frame.pack(fill=tk.X)
        
        self.dup_reuse_indices_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(index_frame, text=t.get('reuse_indices'), 
                       variable=self.dup_reuse_indices_var).pack(side=tk.LEFT)
        
        self.dup_recreate_indices_var = tk.BooleanVar()
        ttk.Checkbutton(index_frame, text=t.get('force_recreation'), 
                       variable=self.dup_recreate_indices_var).pack(side=tk.LEFT, padx=(20, 0))
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        ttk.Button(button_frame, text=t.get('start_scan'),
                   command=self.start_duplicate_scan).pack(side=tk.LEFT)
        ttk.Button(button_frame, text=t.get('clear_button'),
                   command=self.clear_duplicate_form).pack(side=tk.LEFT, padx=(10, 0))
    
    def setup_settings_tab(self):
        """Setup the settings interface."""
        main_frame = ttk.Frame(self.settings_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Language settings
        lang_frame = ttk.LabelFrame(main_frame, text=t.get('language'), padding=10)
        lang_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.language_var = tk.StringVar(value=self.config.get('language', 'en'))
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.language_var, 
                                 values=['en', 'de'], width=10, state='readonly')
        lang_combo.pack(side=tk.LEFT)
        
        # Hash algorithm settings
        hash_frame = ttk.LabelFrame(main_frame, text=t.get('default_hash'), padding=10)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.hash_var = tk.StringVar(value=self.config.get('default_hash_algo', 'md5'))
        hash_combo = ttk.Combobox(hash_frame, textvariable=self.hash_var,
                                 values=['md5', 'sha1', 'sha256'], width=10, state='readonly')
        hash_combo.pack(side=tk.LEFT)
        
        # Auto-load indices
        self.auto_load_var = tk.BooleanVar(value=self.config.get('auto_load_indices', True))
        ttk.Checkbutton(main_frame, text=t.get('auto_load_indices'), 
                       variable=self.auto_load_var).pack(anchor=tk.W, pady=(0, 10))
        
        # Index search locations
        locations_frame = ttk.LabelFrame(main_frame, text=t.get('index_locations'), padding=10)
        locations_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Locations list
        list_frame_settings = ttk.Frame(locations_frame)
        list_frame_settings.pack(fill=tk.BOTH, expand=True)
        
        self.locations_listbox = tk.Listbox(list_frame_settings, height=6)
        scrollbar_settings = ttk.Scrollbar(list_frame_settings, orient=tk.VERTICAL, command=self.locations_listbox.yview)
        self.locations_listbox.configure(yscrollcommand=scrollbar_settings.set)
        
        self.locations_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_settings.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_locations_list()
        
        locations_buttons = ttk.Frame(locations_frame)
        locations_buttons.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(locations_buttons, text=t.get('add_location'), 
                  command=self.add_search_location).pack(side=tk.LEFT)
        ttk.Button(locations_buttons, text=t.get('remove_location'), 
                  command=self.remove_search_location).pack(side=tk.LEFT, padx=(10, 0))
        
        # Apply settings button
        ttk.Button(main_frame, text=t.get('apply_settings'), 
                  command=self.apply_settings).pack(pady=(20, 0))
    
    def refresh_indices(self):
        """Refresh the list of available indices."""
        self.available_indices = self.index_discovery.discover_indices()
        self.populate_index_tree()
        self.update_status()
    
    def populate_index_tree(self):
        """Populate the index management tree."""
        # Clear existing items
        for item in self.index_tree.get_children():
            self.index_tree.delete(item)
        
        for caf_path in self.available_indices:
            info = self.index_discovery.get_index_info(caf_path)
            if info:
                self.index_tree.insert('', 'end',
                                     text=caf_path.name,
                                     values=(
                                         str(info.root_path),
                                         f"{info.file_count:,}",
                                         format_size(info.total_size),
                                         info.created_date.strftime('%Y-%m-%d'),
                                         info.hash_method
                                     ),
                                     tags=(str(caf_path),))
    
    def refresh_locations_list(self):
        """Refresh the search locations list."""
        self.locations_listbox.delete(0, tk.END)
        for location in self.config.get('index_search_locations', []):
            self.locations_listbox.insert(tk.END, location)
    
    def perform_search(self):
        """Perform file search across all available indices."""
        try:
            criteria = self.parse_search_criteria()
            self.search_tree.delete(*self.search_tree.get_children())
            self.search_results.clear()
            
            self.status_var.set(t.get('searching_status'))
            self.root.update_idletasks()
            
            total_results = 0
            for caf_path in self.available_indices:
                if caf_path.exists():
                    # Load index and search
                    file_index = self.load_index_for_search(caf_path)
                    if file_index:
                        results = search_files_in_index(file_index, criteria)
                        total_results += len(results)
                        for result in results:
                            self.add_search_result_to_tree(result)
            
            self.status_var.set(t.get('found_status', total_results))
            
        except Exception as e:
            messagebox.showerror(t.get('error'), t.get('search_error', str(e)))
            self.status_var.set("Search failed")
    
    def parse_search_criteria(self) -> SearchCriteria:
        """Parse search criteria from UI."""
        # Name pattern
        name_pattern = self.search_name_var.get().strip()
        if not name_pattern:
            name_pattern = None
        
        # Size range  
        size_min = None
        size_max = None
        try:
            if self.search_size_min_var.get().strip():
                size_min = self.parse_size(self.search_size_min_var.get().strip())
            if self.search_size_max_var.get().strip():
                size_max = self.parse_size(self.search_size_max_var.get().strip())
        except ValueError as e:
            raise ValueError(t.get('invalid_size', e))
        
        # Date range
        date_min = None
        date_max = None
        try:
            if self.search_date_min_var.get().strip():
                date_min = self.parse_date(self.search_date_min_var.get().strip())
            if self.search_date_max_var.get().strip():
                date_max = self.parse_date(self.search_date_max_var.get().strip())
        except ValueError as e:
            raise ValueError(t.get('invalid_date', e))
        
        return SearchCriteria(
            name_pattern=name_pattern,
            size_min=size_min,
            size_max=size_max,
            date_min=date_min,
            date_max=date_max
        )
    
    def load_index_for_search(self, caf_path: Path):
        """Load an index file for searching."""
        # Determine hash algorithm from filename
        name = caf_path.stem.lower()
        use_hash = True
        if '_sha256' in name:
            hash_algo = 'sha256'
        elif '_sha1' in name:
            hash_algo = 'sha1'
        else:
            hash_algo = 'md5'
        
        return FileIndex.load_from_caf(caf_path, use_hash, hash_algo)
    
    def add_search_result_to_tree(self, result: SearchResult):
        """Add search result to tree."""
        self.search_results.append(result)
        filename = result.path.name
        size_str = format_size(result.size)
        modified_str = dt.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M')
        path_str = str(result.path)
        
        self.search_tree.insert('', 'end',
                              text=filename,
                              values=(size_str, modified_str, path_str),
                              tags=(len(self.search_results) - 1,))
    
    def clear_search_criteria(self):
        """Clear all search criteria."""
        self.search_name_var.set("")
        self.search_size_min_var.set("")
        self.search_size_max_var.set("")
        self.search_date_min_var.set("")
        self.search_date_max_var.set("")
    
    def get_selected_search_result(self) -> Optional[SearchResult]:
        """Get the currently selected search result"""
        selection = self.search_tree.selection()
        if not selection:
            return None
            
        item = selection[0]
        tags = self.search_tree.item(item, 'tags')
        if tags:
            try:
                result_index = int(tags[0])
                return self.search_results[result_index]
            except (ValueError, IndexError):
                return None
        return None
    
    def on_search_double_click(self, event):
        """Handle double-click on search result."""
        result = self.get_selected_search_result()
        if result and result.path.exists():
            open_file_or_folder(result.path, open_folder=False)
        elif result:
            messagebox.showerror(t.get('error'), t.get('file_not_found', result.path))
    
    def on_search_right_click(self, event):
        """Handle right-click on search result."""
        result = self.get_selected_search_result()
        if result:
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label=t.get('open_file'), command=self.open_search_file)
            menu.add_command(label=t.get('open_folder'), command=self.open_search_folder)
            menu.add_command(label=t.get('copy_path'), command=self.copy_search_path)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
    
    def open_search_file(self):
        """Open selected search result file."""
        result = self.get_selected_search_result()
        if result and result.path.exists():
            open_file_or_folder(result.path, open_folder=False)
        elif result:
            messagebox.showerror(t.get('error'), t.get('file_not_found', result.path))
    
    def open_search_folder(self):
        """Open folder containing selected search result."""
        result = self.get_selected_search_result()
        if result and result.path.exists():
            open_file_or_folder(result.path, open_folder=True)
        elif result:
            messagebox.showerror(t.get('error'), t.get('file_not_found', result.path))
    
    def copy_search_path(self):
        """Copy selected search result path to clipboard."""
        result = self.get_selected_search_result()
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(result.path))
            self.status_var.set(t.get('path_copied', result.path.name))
            self.root.after(2000, self.update_status)
    
    def export_search_results(self):
        """Export search results to CSV."""
        if not self.search_results:
            messagebox.showwarning("Warning", t.get('no_results'))
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
                        modified_str = dt.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        f.write(f'"{filename_clean}","{size_str}",{result.size},"{modified_str}","{path_clean}"\n')
                
                messagebox.showinfo("Success", t.get('export_complete', filename))
                
            except Exception as e:
                messagebox.showerror(t.get('error'), t.get('export_error', e))
    
    def on_index_select(self, event):
        """Handle index selection in management tab."""
        selection = self.index_tree.selection()
        if selection:
            item = selection[0]
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            caf_path = Path(caf_path_str)
            
            info = self.index_discovery.get_index_info(caf_path)
            if info:
                info_text = f"{t.get('root_path')} {info.root_path}\n"
                info_text += f"{t.get('file_count')} {info.file_count:,}\n"
                info_text += f"{t.get('total_size')} {format_size(info.total_size)}\n"
                info_text += f"{t.get('created_date')} {info.created_date.strftime('%Y-%m-%d %H:%M')}\n"
                info_text += f"{t.get('hash_method')} {info.hash_method}"
                self.index_info_var.set(info_text)
        else:
            self.index_info_var.set("Select an index to view details")
    
    def on_index_double_click(self, event):
        """Handle double-click on index - open in file manager."""
        selection = self.index_tree.selection()
        if selection:
            item = selection[0]
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            caf_path = Path(caf_path_str)
            open_file_or_folder(caf_path, open_folder=True)
    
    def create_new_index(self):
        """Create a new index file."""
        folder = filedialog.askdirectory(title="Select Folder to Index")
        if folder:
            # Show options dialog
            dialog = IndexCreationDialog(self.root, Path(folder), self.config)
            dialog.run()
            if dialog.result:
                # Refresh indices after creation
                self.refresh_indices()
    
    def delete_selected_index(self):
        """Delete selected index file."""
        selection = self.index_tree.selection()
        if selection:
            item = selection[0]
            caf_path_str = self.index_tree.item(item, 'tags')[0]
            
            if messagebox.askyesno("Confirm", f"Delete index file?\n{Path(caf_path_str).name}"):
                try:
                    Path(caf_path_str).unlink()
                    self.refresh_indices()
                    messagebox.showinfo("Success", "Index file deleted successfully.")
                except Exception as e:
                    messagebox.showerror(t.get('error'), str(e))
    
    # --- Duplicate Detection Methods ---
    
    def select_duplicate_source(self):
        """Select source folder for duplicate detection."""
        folder = filedialog.askdirectory(title=t.get('source_folder'))
        if folder:
            self.dup_source_var.set(folder)
            self.dup_source_path = Path(folder)
    
    def add_dup_dest_folder(self):
        """Add destination folder for duplicate detection."""
        folder = filedialog.askdirectory(title="Select Destination Folder")
        if folder:
            folder_path = Path(folder)
            if folder_path not in self.dup_dest_paths:
                self.dup_dest_paths.append(folder_path)
                self.dup_dest_listbox.insert(tk.END, str(folder_path))
            else:
                messagebox.showwarning("Warning", t.get('duplicate_folder'))
    
    def remove_dup_dest_folder(self):
        """Remove selected destination folder."""
        selection = self.dup_dest_listbox.curselection()
        if selection:
            index = selection[0]
            self.dup_dest_listbox.delete(index)
            del self.dup_dest_paths[index]
    
    def clear_dup_dest_folders(self):
        """Clear all destination folders."""
        self.dup_dest_listbox.delete(0, tk.END)
        self.dup_dest_paths.clear()
    
    def on_dup_hash_toggle(self):
        """Enable/disable hash algorithm selection for duplicates."""
        if self.dup_use_hash_var.get():
            self.dup_hash_combo.config(state="readonly")
        else:
            self.dup_hash_combo.config(state="disabled")
    
    def clear_duplicate_form(self):
        """Clear the duplicate detection form."""
        self.dup_source_var.set("")
        self.dup_source_path = None
        self.clear_dup_dest_folders()
    
    def start_duplicate_scan(self):
        """Start the duplicate scan process."""
        # Validate input
        if not self.dup_source_path:
            messagebox.showerror(t.get('error'), t.get('select_source'))
            return
        
        if not self.dup_dest_paths:
            messagebox.showerror(t.get('error'), t.get('select_dest'))
            return
        
        # Validate paths
        if not self.dup_source_path.exists():
            messagebox.showerror(t.get('error'), f"Source folder does not exist: {self.dup_source_path}")
            return
        
        invalid_paths = [p for p in self.dup_dest_paths if not p.exists()]
        if invalid_paths:
            messagebox.showerror(t.get('error'), f"Invalid destination folders:\n" + 
                               "\n".join(str(p) for p in invalid_paths))
            return
        
        # Create configuration
        config = ScanConfig(
            source_path=self.dup_source_path,
            dest_paths=self.dup_dest_paths,
            use_hash=self.dup_use_hash_var.get(),
            hash_algo=self.dup_hash_algo_var.get(),
            reuse_indices=self.dup_reuse_indices_var.get(),
            recreate_indices=self.dup_recreate_indices_var.get()
        )
        
        # Run scan
        duplicates = run_scan_with_progress(config, self.root)
        
        if not duplicates:
            if messagebox.askyesno(t.get('no_duplicates'), t.get('no_duplicates')):
                return  # Stay in duplicate tab for new scan
            else:
                return
        
        # Show results
        method = f"{config.hash_algo.upper()} hash + size" if config.use_hash else "filename + size"
        if config.reuse_indices:
            method += " (with CAF indices)"
        
        results_window = DuplicateResultsWindow(self, duplicates, method)
        results_window.root.wait_window()
        
        # Check if user wants new scan
        if hasattr(results_window, 'action') and results_window.action == 'new_scan':
            self.clear_duplicate_form()
    
    # --- Settings Methods ---
    
    def add_search_location(self):
        """Add new search location."""
        folder = filedialog.askdirectory(title=t.get('add_location'))
        if folder:
            locations = self.config.get('index_search_locations', [])
            if folder not in locations:
                locations.append(folder)
                self.config.set('index_search_locations', locations)
                self.refresh_locations_list()
    
    def remove_search_location(self):
        """Remove selected search location."""
        selection = self.locations_listbox.curselection()
        if selection:
            index = selection[0]
            locations = self.config.get('index_search_locations', [])
            if 0 <= index < len(locations):
                locations.pop(index)
                self.config.set('index_search_locations', locations)
                self.refresh_locations_list()
    
    def apply_settings(self):
        """Apply changed settings."""
        # Save language setting
        old_lang = self.config.get('language', 'en')
        new_lang = self.language_var.get()
        self.config.set('language', new_lang)
        
        # Save other settings
        self.config.set('default_hash_algo', self.hash_var.get())
        self.config.set('auto_load_indices', self.auto_load_var.get())
        
        # Save configuration
        self.config.save_config()
        
        # If language changed, show restart message
        if old_lang != new_lang:
            messagebox.showinfo("Language Changed", 
                              "Please restart the application to apply language changes.")
        else:
            messagebox.showinfo("Settings", "Settings applied successfully.")
        
        # Refresh indices if auto-load setting changed
        if self.config.get('auto_load_indices', True):
            self.refresh_indices()
    
    def update_status(self):
        """Update status bar."""
        count = len(self.available_indices)
        self.status_var.set(t.get('ready_status', count))
    
    def on_closing(self):
        """Handle application closing."""
        # Save window geometry
        self.config.set('window_geometry', self.root.geometry())
        self.config.save_config()
        self.root.destroy()
    
    def parse_size(self, size_str: str) -> int:
        """Parse size string like '5MB', '2.5GB' to bytes."""
        if not size_str or size_str.lower() == 'any':
            return 0
        
        size_str = size_str.strip().upper()
        match = re.match(r'^([\d.]+)\s*([KMGT]?B?)$', size_str)  # Fixed: added missing quote and $
        if not match:
            raise ValueError(f"Invalid size format: {size_str}")
        
        number = float(match.group(1))
        unit = match.group(2) or 'B'
        
        if len(unit) == 1 and unit in "KMGT":
            unit += 'B'
        
        multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
        return int(number * multipliers.get(unit, 1))
    
    def parse_date(self, date_str: str) -> Optional[dt]:
        """Parse date string in various formats."""
        if not date_str or date_str.lower() in ['any', '']:
            return None
        
        # Handle relative dates in multiple languages
        date_str_lower = date_str.lower()
        now = dt.now()
        
        relative_dates = {
            'today': now.replace(hour=0, minute=0, second=0, microsecond=0),
            'heute': now.replace(hour=0, minute=0, second=0, microsecond=0),
            'yesterday': (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
            'gestern': (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        }
        
        if date_str_lower in relative_dates:
            return relative_dates[date_str_lower]
        
        # Try various date formats
        formats = [
            '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y',
            '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S',
        ]
        
        for fmt in formats:
            try:
                return dt.strptime(date_str, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Invalid date format: {date_str}")
    
    def run(self):
        """Run the application."""
        self.root.mainloop()

# --- Index Creation Dialog ---

class IndexCreationDialog:
    """Dialog for creating new index files."""
    
    def __init__(self, parent, folder_path: Path, config: Config):
        self.parent = parent
        self.folder_path = folder_path
        self.config = config
        self.result = False
        
        self.root = tk.Toplevel(parent)
        self.root.title("Create New Index")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Make modal
        self.root.transient(parent)
        self.root.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Folder info
        ttk.Label(main_frame, text="Create index for:", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)
        ttk.Label(main_frame, text=str(self.folder_path), foreground='blue').pack(anchor=tk.W, pady=(0, 20))
        
        # Hash options
        hash_frame = ttk.LabelFrame(main_frame, text="Hash Algorithm", padding=10)
        hash_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.use_hash_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(hash_frame, text="Include file hashes", 
                       variable=self.use_hash_var, command=self.on_hash_toggle).pack(anchor=tk.W)
        
        self.hash_algo_var = tk.StringVar(value=self.config.get('default_hash_algo', 'md5'))
        self.hash_combo = ttk.Combobox(hash_frame, textvariable=self.hash_algo_var,
                                      values=['md5', 'sha1', 'sha256'], width=10, state='readonly')
        self.hash_combo.pack(anchor=tk.W, pady=(5, 0))
        
        # Output file
        output_frame = ttk.LabelFrame(main_frame, text="Output File", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.output_var = tk.StringVar()
        self.update_output_filename()
        
        ttk.Entry(output_frame, textvariable=self.output_var, width=50).pack(fill=tk.X)
        
        # Progress
        self.progress_var = tk.StringVar(value="Ready to create index")
        ttk.Label(main_frame, textvariable=self.progress_var).pack(anchor=tk.W, pady=(10, 0))
        
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(5, 20))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Create Index", command=self.create_index).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
    
    def on_hash_toggle(self):
        """Handle hash toggle."""
        if self.use_hash_var.get():
            self.hash_combo.config(state='readonly')
        else:
            self.hash_combo.config(state='disabled')
        self.update_output_filename()
    
    def update_output_filename(self):
        """Update output filename based on settings."""
        if self.use_hash_var.get():
            hash_suffix = f"_{self.hash_algo_var.get()}"
        else:
            hash_suffix = ""
        
        filename = f"{self.folder_path.name}_index{hash_suffix}.caf"
        output_path = self.folder_path.parent / filename
        self.output_var.set(str(output_path))
    
    def create_index(self):
        """Create the index file."""
        output_path = Path(self.output_var.get())
        
        # Check if file already exists
        if output_path.exists():
            if not messagebox.askyesno("File Exists", 
                                     f"Index file already exists:\n{output_path.name}\n\nOverwrite?"):
                return
        
        # Start creation in thread
        self.progress.start()
        self.progress_var.set("Creating index...")
        
        def create_thread():
            try:
                index = FileIndex(self.folder_path, self.use_hash_var.get(), self.hash_algo_var.get())
                
                # Count total files first
                total_files = sum(1 for _ in self.folder_path.rglob('*') if _.is_file())
                processed = 0
                
                # Add files to index
                for file_path in self.folder_path.rglob('*'):
                    if file_path.is_file():
                        index.add_file(file_path)
                        processed += 1
                        
                        if processed % 100 == 0:
                            self.root.after(0, lambda: self.progress_var.set(
                                f"Processing files... {processed}/{total_files}"))
                
                # Save index
                self.root.after(0, lambda: self.progress_var.set("Saving index file..."))
                index.save_to_caf(output_path)
                
                # Success
                self.root.after(0, self.creation_success)
                
            except Exception as e:
                self.root.after(0, lambda: self.creation_error(str(e)))
        
        thread = Thread(target=create_thread)
        thread.daemon = True
        thread.start()
    
    def creation_success(self):
        """Handle successful index creation."""
        self.progress.stop()
        self.progress_var.set("Index created successfully!")
        messagebox.showinfo("Success", f"Index file created:\n{self.output_var.get()}")
        self.result = True
        self.root.destroy()
    
    def creation_error(self, error_msg):
        """Handle index creation error."""
        self.progress.stop()
        self.progress_var.set("Creation failed")
        messagebox.showerror("Error", f"Failed to create index:\n{error_msg}")
    
    def cancel(self):
        """Cancel the dialog."""
        self.root.destroy()
    
    def run(self):
        """Run the dialog."""
        self.root.wait_window()

# --- Main Entry Point ---

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Universal File Search and Index Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
A comprehensive file indexing and search tool with duplicate detection.
Features auto-discovery of index files, multilingual support, and advanced search capabilities.

Examples:
  GUI Mode (default):
    python %(prog)s

  CLI Mode:
    python %(prog)s --cli --search "*.jpg" --size-min 1MB
"""
    )

    parser.add_argument('--cli', action='store_true',
                        help='Use command-line interface instead of GUI')
    parser.add_argument('--lang', choices=['en', 'de'], 
                        help='Set interface language')
    parser.add_argument('--search', type=str,
                        help='Search pattern (CLI mode)')
    parser.add_argument('--size-min', type=str,
                        help='Minimum file size (CLI mode)')
    parser.add_argument('--size-max', type=str,
                        help='Maximum file size (CLI mode)')

    args = parser.parse_args()

    # Set language if specified
    if args.lang:
        t.set_language(args.lang)

    if args.cli:
        # CLI mode implementation
        print("CLI mode - Basic search functionality")
        config = Config()
        
        # Discover indices
        discovery = IndexDiscovery(config)
        indices = discovery.discover_indices()
        
        if not indices:
            print("No index files found. Please create indices first using GUI mode.")
            return
        
        print(f"Found {len(indices)} index files:")
        for idx_path in indices:
            info = discovery.get_index_info(idx_path)
            if info:
                print(f"  {idx_path.name} -> {info.root_path} ({info.hash_method})")
        
        # Perform search if criteria provided
        if args.search:
            criteria = SearchCriteria(
                name_pattern=args.search,
                size_min=None,  # TODO: Parse size arguments
                size_max=None,
                date_min=None,
                date_max=None
            )
            
            total_results = 0
            for caf_path in indices:
                # Load and search index
                name = caf_path.stem.lower()
                use_hash = True
                if '_sha256' in name:
                    hash_algo = 'sha256'
                elif '_sha1' in name:
                    hash_algo = 'sha1'
                else:
                    hash_algo = 'md5'
                
                file_index = FileIndex.load_from_caf(caf_path, use_hash, hash_algo)
                if file_index:
                    results = search_files_in_index(file_index, criteria)
                    total_results += len(results)
                    
                    for result in results:
                        print(f"{result.path} ({format_size(result.size)})")
            
            print(f"\nFound {total_results} matching files.")
        
        return

    # GUI mode (default)
    try:
        app = UniversalSearchApp()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
    except Exception as e:
        print(f"Application error: {e}")

if __name__ == "__main__":
    main()