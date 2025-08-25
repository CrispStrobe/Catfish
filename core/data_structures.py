"""Core data structures for the Universal Search Tool."""
from pathlib import Path
from typing import List, Optional, NamedTuple
from datetime import datetime as dt

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
