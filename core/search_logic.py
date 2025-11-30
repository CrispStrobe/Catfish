# core/search_logic.py

"""Core search and duplicate detection logic."""
import os
import re
import fnmatch
import sys
from pathlib import Path
from typing import List, Optional
from datetime import datetime as dt
from utils.i18n import translator as t

from core.data_structures import (
    SearchCriteria, SearchResult, DuplicateMatch, 
    FileEntry, ScanConfig
)
from core.file_index import FileIndex
from utils.file_utils import filter_overlapping_paths, get_caf_path

def _safe_compile_pattern(pattern: str) -> re.Pattern:
    """
    Compiles a search pattern into a regex object with robust fallback and logging.
    Optimizes simple globs (e.g. *text*) to simple regexes.
    """
    # Debug log to trace what's happening
    print(f"[DEBUG] Processing pattern: '{pattern}'", file=sys.stderr)

    if not pattern:
        return re.compile("", re.IGNORECASE)

    # --- Optimization for common simple Globs ---
    # Check if we have simple start/end wildcards without internal wildcards
    # This avoids fnmatch's complex output for simple "contains" queries
    
    # Strip wildcards for analysis
    clean_pattern = pattern
    start_star = pattern.startswith("*")
    end_star = pattern.endswith("*")
    
    if start_star:
        clean_pattern = clean_pattern[1:]
    if end_star:
        clean_pattern = clean_pattern[:-1]
        
    # Check for internal wildcards in the remaining text
    has_internal_wildcards = "*" in clean_pattern or "?" in clean_pattern

    if not has_internal_wildcards and clean_pattern:
        # Case 1: *text* -> Contains text (standard search)
        if start_star and end_star:
            regex_str = re.escape(clean_pattern)
            print(f"[DEBUG] Optimized Glob: '*{clean_pattern}*' -> Regex substring search '{regex_str}'", file=sys.stderr)
            return re.compile(regex_str, re.IGNORECASE)
        
        # Case 2: *text -> Ends with text
        elif start_star:
            regex_str = re.escape(clean_pattern) + r"$"
            print(f"[DEBUG] Optimized Glob: '*{clean_pattern}' -> Regex ends-with '{regex_str}'", file=sys.stderr)
            return re.compile(regex_str, re.IGNORECASE)
            
        # Case 3: text* -> Starts with text
        elif end_star:
            regex_str = r"^" + re.escape(clean_pattern)
            print(f"[DEBUG] Optimized Glob: '{clean_pattern}*' -> Regex starts-with '{regex_str}'", file=sys.stderr)
            return re.compile(regex_str, re.IGNORECASE)

    # --- Fallback to fnmatch for complex Globs ---
    if pattern.startswith("*") or pattern.startswith("?"):
        print("[DEBUG] Complex wildcard detected. Using fnmatch conversion.", file=sys.stderr)
        try:
            regex_from_glob = fnmatch.translate(pattern)
            print(f"[DEBUG] fnmatch converted '{pattern}' to regex '{regex_from_glob}'", file=sys.stderr)
            return re.compile(regex_from_glob, re.IGNORECASE)
        except Exception as e:
            print(f"[DEBUG] Glob conversion failed: {e}", file=sys.stderr)
            pass

    # --- Standard Regex Compilation ---
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        print(f"[DEBUG] Regex compile failed ('{e}'). Falling back to strict Glob.", file=sys.stderr)
        try:
            regex_from_glob = fnmatch.translate(pattern)
            return re.compile(regex_from_glob, re.IGNORECASE)
        except Exception as e2:
            print(f"[DEBUG] Fatal: Glob fallback also failed: {e2}", file=sys.stderr)
            raise ValueError(f"Invalid search pattern '{pattern}': {e}")

def search_files_in_index(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Search for files in index based on criteria with verbose logging."""
    print(f"[SEARCH] Criteria: pattern='{criteria.name_pattern}', "
          f"size_min={criteria.size_min}, size_max={criteria.size_max}", file=sys.stderr)
    
    results = []
    
    # Compile regex pattern safely
    name_regex = None
    if criteria.name_pattern:
        try:
            name_regex = _safe_compile_pattern(criteria.name_pattern)
            print(f"[SEARCH] Pattern compiled successfully.", file=sys.stderr)
        except ValueError as e:
            print(f"[SEARCH] Error compiling pattern: {e}", file=sys.stderr)
            raise e
    
    print(f"[SEARCH] Scanning {file_index.total_files} files...", file=sys.stderr)
    
    total_entries_examined = 0
    debug_files_printed = 0
    
    # Search through all files in index
    for size, entries in file_index.size_index.items():
        # Size filtering
        if criteria.size_min is not None and size < criteria.size_min:
            continue
        if criteria.size_max is not None and size > criteria.size_max:
            continue
        
        for entry in entries:
            total_entries_examined += 1
            filename = entry.path.name
            
            # --- DEBUG: Print first 5 files seen to verify data integrity ---
            if debug_files_printed < 5:
                match_status = "MATCH" if (not name_regex or name_regex.search(filename)) else "NO MATCH"
                print(f"[DEBUG-SCAN] Checking: '{filename}' -> {match_status}", file=sys.stderr)
                debug_files_printed += 1
            # ----------------------------------------------------------------
            
            # Name filtering
            if name_regex and not name_regex.search(filename):
                continue
            
            # Date filtering
            if criteria.date_min or criteria.date_max:
                file_mtime = dt.fromtimestamp(entry.mtime)
                
                if criteria.date_min and file_mtime < criteria.date_min:
                    continue
                if criteria.date_max and file_mtime > criteria.date_max:
                    continue
            
            # File passed all criteria
            result = SearchResult(
                path=entry.path,
                size=entry.size,
                mtime=entry.mtime,
                hash=entry.hash
            )
            results.append(result)
            
            if len(results) >= 1000: # Limit result count for CLI safety
                print(f"[SEARCH] Hit limit of 1000 results. Stopping.", file=sys.stderr)
                break
        
        if len(results) >= 1000:
            break
    
    print(f"[SEARCH] Examined {total_entries_examined} entries.", file=sys.stderr)
    print(f"[SEARCH] Found {len(results)} matching files.", file=sys.stderr)
    return results

# ... (Include other functions like search_files_in_index_with_raw_elm, 
#      search_files_in_index_optimized, build_destination_index, etc. 
#      Make sure to update them to use _safe_compile_pattern if needed) ...

def search_files_in_index_with_raw_elm(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Optimized search using raw elm data without building full indexes."""
    results = []
    
    name_regex = None
    if criteria.name_pattern:
        name_regex = _safe_compile_pattern(criteria.name_pattern)
    
    dir_path_map = file_index._get_or_build_dir_map()
    
    for mtime, size, parent_id, filename in file_index.raw_elm:
        if size < 0: continue
        
        if criteria.size_min is not None and size < criteria.size_min: continue
        if criteria.size_max is not None and size > criteria.size_max: continue
        
        if name_regex and not name_regex.search(filename):
            continue
        
        if parent_id not in dir_path_map: continue
        path = dir_path_map[parent_id] / filename
        
        if criteria.date_min or criteria.date_max:
            file_mtime = dt.fromtimestamp(mtime)
            if criteria.date_min and file_mtime < criteria.date_min: continue
            if criteria.date_max and file_mtime > criteria.date_max: continue
        
        results.append(SearchResult(path=path, size=size, mtime=mtime, hash=""))
    
    return results

def search_files_in_index_optimized(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Optimized search for files in index based on criteria."""
    results = []
    
    name_regex = None
    if criteria.name_pattern:
        name_regex = _safe_compile_pattern(criteria.name_pattern)
    
    relevant_size_buckets = []
    for size in file_index.size_index.keys():
        if criteria.size_min is not None and size < criteria.size_min: continue
        if criteria.size_max is not None and size > criteria.size_max: continue
        relevant_size_buckets.append(size)
    
    for size in relevant_size_buckets:
        entries = file_index.size_index[size]
        for entry in entries:
            if name_regex and not name_regex.search(entry.path.name): continue
            
            if criteria.date_min or criteria.date_max:
                file_mtime = dt.fromtimestamp(entry.mtime)
                if criteria.date_min and file_mtime < criteria.date_min: continue
                if criteria.date_max and file_mtime > criteria.date_max: continue
            
            results.append(SearchResult(
                path=entry.path, size=entry.size, mtime=entry.mtime, hash=entry.hash
            ))
    return results

# (Keep build_destination_index and find_duplicates_with_locations as they were in previous steps, 
# ensuring they are present in the final file)

def build_destination_index(config: ScanConfig, progress_callback=None, cancel_event=None) -> Optional[FileIndex]:
    """Builds a combined file index for all destination paths."""
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    dummy_root = Path('.') 
    combined_index = FileIndex(dummy_root, config.use_hash, config.hash_algo)
    
    for i, dest_path in enumerate(filtered_paths):
        if cancel_event and cancel_event.is_set(): break
        if not dest_path.is_dir(): continue

        caf_path = get_caf_path(dest_path, config.hash_algo)
        dest_index = None

        if progress_callback: progress_callback(f"Processing folder {i+1}/{len(filtered_paths)}", f"Folder: {dest_path.name}")
        
        if config.reuse_indices and not config.recreate_indices and caf_path.exists():
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        
        if not dest_index:
            dest_index = FileIndex(dest_path, config.use_hash, config.hash_algo)
            for root, _, files in os.walk(dest_path):
                if cancel_event and cancel_event.is_set(): break
                root_path = Path(root)
                for j, filename in enumerate(files):
                    if cancel_event and cancel_event.is_set(): break
                    dest_index.add_file(root_path / filename)
            if cancel_event and cancel_event.is_set(): break

            if config.reuse_indices: dest_index.save_to_caf(caf_path)
        
        if not dest_index: continue

        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files
        
    return combined_index

def find_duplicates_with_locations(source_path: Path, dest_index: FileIndex, 
                                 progress_callback=None, cancel_event=None) -> List[DuplicateMatch]:
    """Find duplicates with optimized bulk processing"""
    source_index = FileIndex(source_path, dest_index.use_hash, dest_index.hash_algo)
    
    if progress_callback:
        progress_callback(t.get('finding_duplicates'), f"Indexing source directory: {source_path.name}")
    
    for root, _, files in os.walk(source_path):
        if cancel_event and cancel_event.is_set(): return []
        root_path = Path(root)
        for filename in files:
            if cancel_event and cancel_event.is_set(): return []
            source_index.add_file(root_path / filename)
    
    if progress_callback:
        progress_callback(t.get('finding_duplicates'), f"Comparing against destination indices...")
    
    return FileIndex.find_all_duplicates_bulk(source_index, dest_index, progress_callback, cancel_event)

def build_destination_index_selective(config: ScanConfig, progress_callback=None, cancel_event=None, translator_get_func=None) -> Optional[FileIndex]:
    """Build destination index with selective recreation of specific indices."""
    t_get = translator_get_func or t.get
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    
    if progress_callback:
        progress_callback(t_get('building_index'), f"Processing {len(filtered_paths)} destination folders")
    
    dummy_root = Path('.') 
    combined_index = FileIndex(dummy_root, config.use_hash, config.hash_algo)
    
    for i, dest_path in enumerate(filtered_paths):
        if cancel_event and cancel_event.is_set(): 
            break
        if not dest_path.is_dir(): 
            continue

        caf_path = get_caf_path(dest_path, config.hash_algo)
        dest_index = None

        if progress_callback:
            progress_callback(f"Processing folder {i+1}/{len(filtered_paths)}", f"Folder: {dest_path.name}")
        
        force_recreate = (hasattr(config, 'selective_recreation_paths') and 
                         dest_path in config.selective_recreation_paths)
        
        if config.reuse_indices and not force_recreate and caf_path.exists():
            if progress_callback: 
                progress_callback(f"Loading index for {dest_path.name}", "Please wait...")
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        
        if not dest_index:
            if progress_callback:
                progress_callback(f"Creating new index for {dest_path.name}", t_get('scanning_files'))

            dest_index = FileIndex(dest_path, config.use_hash, config.hash_algo)
            
            for root, _, files in os.walk(dest_path):
                if cancel_event and cancel_event.is_set(): break
                root_path = Path(root)
                for j, filename in enumerate(files):
                    if cancel_event and cancel_event.is_set(): break
                    if progress_callback and j % 200 == 0:
                        progress_callback(f"Indexing {dest_path.name}", f"File: {filename}")
                    dest_index.add_file(root_path / filename)
            
            if cancel_event and cancel_event.is_set(): break

            if config.reuse_indices:
                if progress_callback: 
                    progress_callback(f"Saving index for {dest_path.name}", f"Path: {caf_path.name}")
                dest_index.save_to_caf(caf_path)
        
        if not dest_index: continue

        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files
        
    return combined_index