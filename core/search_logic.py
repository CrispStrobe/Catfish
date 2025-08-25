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

def build_destination_index_selective(config: ScanConfig, progress_callback=None, cancel_event=None) -> Optional[FileIndex]:
    """Build destination index with selective recreation of specific indices."""
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    
    if progress_callback:
        progress_callback(t.get('building_index'), f"Processing {len(filtered_paths)} destination folders")
    
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
                progress_callback(f"Creating new index for {dest_path.name}", t.get('scanning_files'))
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