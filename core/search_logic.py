# core/search_logic.py

"""Core search and duplicate detection logic."""
import os
import re
from pathlib import Path
from typing import List, Optional
from threading import Event
from collections import defaultdict
from datetime import datetime as dt
from utils.i18n import translator as t

from core.data_structures import (
    SearchCriteria, SearchResult, DuplicateMatch, 
    FileEntry, ScanConfig
)
from core.file_index import FileIndex
from utils.file_utils import filter_overlapping_paths, get_caf_path

def search_files_in_index_with_raw_elm(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Optimized search using raw elm data without building full indexes"""
    results = []
    
    # Compile regex pattern if provided
    name_regex = None
    if criteria.name_pattern:
        try:
            name_regex = re.compile(criteria.name_pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(t.get('invalid_regex', e))
    
    # Get or build directory map once
    dir_path_map = file_index._get_or_build_dir_map()
    
    # Search through raw elm data directly
    for mtime, size, parent_id, filename in file_index.raw_elm:
        # Skip directories (negative size)
        if size < 0:
            continue
        
        # Size filtering (most efficient first)
        if criteria.size_min is not None and size < criteria.size_min:
            continue
        if criteria.size_max is not None and size > criteria.size_max:
            continue
        
        # Name filtering
        if name_regex and not name_regex.search(filename):
            continue
        
        # Check if parent directory exists in map
        if parent_id not in dir_path_map:
            continue
            
        # Build full path
        path = dir_path_map[parent_id] / filename
        
        # Date filtering
        if criteria.date_min or criteria.date_max:
            file_mtime = dt.fromtimestamp(mtime)
            
            if criteria.date_min and file_mtime < criteria.date_min:
                continue
            if criteria.date_max and file_mtime > criteria.date_max:
                continue
        
        # File passed all criteria
        results.append(SearchResult(
            path=path,
            size=size,
            mtime=mtime,
            hash=""  # Hash not stored in CAF, would need calculation
        ))
    
    return results

def search_files_in_index(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Search for files in index based on criteria with verbose logging"""
    print(f"[SEARCH] Starting search with criteria: name_pattern={criteria.name_pattern}, "
          f"size_min={criteria.size_min}, size_max={criteria.size_max}, "
          f"date_min={criteria.date_min}, date_max={criteria.date_max}")
    
    results = []
    
    # Compile regex pattern if provided
    name_regex = None
    if criteria.name_pattern:
        try:
            name_regex = re.compile(criteria.name_pattern, re.IGNORECASE)
            print(f"[SEARCH] Compiled regex pattern: {criteria.name_pattern}")
        except re.error as e:
            print(f"[SEARCH] Regex error: {e}")
            raise ValueError(t.get('invalid_regex', e))
    
    print(f"[SEARCH] Index has {len(file_index.size_index)} size buckets")
    print(f"[SEARCH] Total files in index: {file_index.total_files}")
    
    total_entries_examined = 0
    size_buckets_examined = 0
    
    # Search through all files in index
    for size, entries in file_index.size_index.items():
        size_buckets_examined += 1
        
        # Size filtering
        if criteria.size_min is not None and size < criteria.size_min:
            continue
        if criteria.size_max is not None and size > criteria.size_max:
            continue
        
        print(f"[SEARCH] Examining size bucket {size} with {len(entries)} entries")
        
        for entry in entries:
            total_entries_examined += 1
            
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
            result = SearchResult(
                path=entry.path,
                size=entry.size,
                mtime=entry.mtime,
                hash=entry.hash
            )
            results.append(result)
            
            if len(results) <= 10:  # Log first 10 matches
                print(f"[SEARCH] Match found: {entry.path.name} (size: {entry.size})")
    
    print(f"[SEARCH] Examined {size_buckets_examined} size buckets, {total_entries_examined} total entries")
    print(f"[SEARCH] Found {len(results)} matching files")
    return results

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
        
        # Check if this specific path needs recreation
        force_recreate = (hasattr(config, 'selective_recreation_paths') and 
                         dest_path in config.selective_recreation_paths)
        
        # Try to load existing index (unless forced recreation)
        if config.reuse_indices and not force_recreate and caf_path.exists():
            if progress_callback: 
                progress_callback(f"Loading index for {dest_path.name}", "Please wait...")
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        
        # Build new index if needed
        if not dest_index:
            if progress_callback:
                progress_callback(f"Creating new index for {dest_path.name}", t_get('scanning_files'))

            dest_index = FileIndex(dest_path, config.use_hash, config.hash_algo)
            
            for root, _, files in os.walk(dest_path):
                if cancel_event and cancel_event.is_set(): 
                    break
                root_path = Path(root)
                for j, filename in enumerate(files):
                    if cancel_event and cancel_event.is_set(): 
                        break
                    if progress_callback and j % 200 == 0:
                        progress_callback(f"Indexing {dest_path.name}", f"File: {filename}")
                    dest_index.add_file(root_path / filename)
            
            if cancel_event and cancel_event.is_set(): 
                break

            # Save the newly created index
            if config.reuse_indices:
                if progress_callback: 
                    progress_callback(f"Saving index for {dest_path.name}", f"Path: {caf_path.name}")
                dest_index.save_to_caf(caf_path)
        
        if not dest_index: 
            continue

        # Merge into combined index
        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files
        
    return combined_index

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

def search_files_in_index_optimized(file_index: FileIndex, criteria: SearchCriteria) -> List[SearchResult]:
    """Optimized search for files in index based on criteria."""
    results = []
    
    # Compile regex pattern if provided
    name_regex = None
    if criteria.name_pattern:
        try:
            name_regex = re.compile(criteria.name_pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
    
    # Pre-filter size buckets to avoid unnecessary iterations
    relevant_size_buckets = []
    for size in file_index.size_index.keys():
        if criteria.size_min is not None and size < criteria.size_min:
            continue
        if criteria.size_max is not None and size > criteria.size_max:
            continue
        relevant_size_buckets.append(size)
    
    # Search through relevant size buckets only
    for size in relevant_size_buckets:
        entries = file_index.size_index[size]
        
        for entry in entries:
            # Name filtering (most selective first)
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

def find_duplicates_with_locations(source_path: Path, dest_index: FileIndex, 
                                 progress_callback=None, cancel_event=None) -> List[DuplicateMatch]:
    """Find duplicates with optimized bulk processing"""
    
    # Create a temporary source index for bulk processing
    source_index = FileIndex(source_path, dest_index.use_hash, dest_index.hash_algo)
    
    if progress_callback:
        progress_callback(t.get('finding_duplicates'), f"Indexing source directory: {source_path.name}")
    
    # Quick indexing of source files
    file_count = 0
    for root, _, files in os.walk(source_path):
        if cancel_event and cancel_event.is_set():
            return []
        root_path = Path(root)
        for filename in files:
            if cancel_event and cancel_event.is_set():
                return []
            file_count += 1
            if progress_callback and file_count % 500 == 0:
                progress_callback("Indexing source", f"Processed {file_count} source files")
            source_index.add_file(root_path / filename)
    
    if progress_callback:
        progress_callback(t.get('finding_duplicates'), f"Comparing against destination indices...")
    
    # Use the optimized bulk duplicate detection
    return FileIndex.find_all_duplicates_bulk(source_index, dest_index, progress_callback, cancel_event)

# ADD this alternative function for when you want to use the original approach:
def find_duplicates_with_locations_legacy(source_path: Path, dest_index: FileIndex, 
                                        progress_callback=None, cancel_event=None) -> List[DuplicateMatch]:
    """Original find duplicates implementation (kept for compatibility)"""
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