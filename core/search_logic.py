# core/search_logic.py

"""Core search and duplicate detection logic."""

import bisect
import fnmatch
import os
import re
import time
from datetime import datetime as dt
from pathlib import Path
from typing import Callable, Optional

from core.data_structures import DuplicateMatch, ScanConfig, SearchCriteria, SearchResult
from core.file_index import FileIndex
from utils.file_utils import filter_overlapping_paths, get_caf_path
from utils.i18n import translator as t


def _safe_compile_pattern(pattern: str) -> re.Pattern:
    """Compiles a search pattern into a regex object with robust fallback."""
    if not pattern:
        return re.compile("", re.IGNORECASE)
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        try:
            return re.compile(fnmatch.translate(pattern), re.IGNORECASE)
        except Exception as e:
            raise ValueError(f"Invalid search pattern: {e}") from e


def search_files_in_index(
    file_index: FileIndex,
    criteria: SearchCriteria,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> list[SearchResult]:
    """
    Search for files using Binary Search O(log N) where possible, or optimized Linear Scan O(N).
    """
    results = []

    # 1. Analyze Pattern
    name_regex = None
    simple_query = None
    query_type = None  # 'contains', 'startswith', 'endswith'

    if criteria.name_pattern:
        pat = criteria.name_pattern
        if "*" in pat or "?" in pat:
            is_start_star = pat.startswith("*")
            is_end_star = pat.endswith("*")
            clean_pat = pat.strip("*")

            # Only optimize if NO internal wildcards (e.g. "te*xt" -> use Regex)
            if "*" not in clean_pat and "?" not in clean_pat:
                simple_query = clean_pat.lower()
                if is_start_star and is_end_star:
                    query_type = "contains"
                elif is_start_star:
                    query_type = "endswith"
                elif is_end_star:
                    query_type = "startswith"

        # Exact match logic (no wildcards)
        elif pat:
            simple_query = pat.lower()
            # FIX: Default to 'contains' to match user expectations (grep/explorer behavior)
            # This uses Linear Scan O(N). User must type "pat*" to get Binary Search O(log N).
            query_type = "contains"

        if not simple_query:
            try:
                name_regex = _safe_compile_pattern(criteria.name_pattern)
            except ValueError:
                return []

    # 2. Strategy Selection
    # Use Binary Search O(log N) ONLY if explicit Start/End wildcard AND Optimized Index exists
    use_binary_search = (
        file_index.is_optimized
        and criteria.size_min is None
        and criteria.size_max is None
        and simple_query
        and query_type in ("startswith", "endswith")
    )

    start_time = time.time()

    # --- STRATEGY A: BINARY SEARCH (Instant) ---
    if use_binary_search:
        candidates = []

        if query_type == "startswith":
            data = file_index.prefix_index
            # FIX: Use 1-tuple for comparison to avoid TypeError with FileEntry objects
            # (str,) is strictly smaller than (str, object) if strings match, suitable for bisect_left
            idx = bisect.bisect_left(data, (simple_query,))

            while idx < len(data):
                name, entry = data[idx]
                if not name.startswith(simple_query):
                    break
                candidates.append(entry)
                idx += 1

        elif query_type == "endswith":
            data = file_index.suffix_index
            rev_query = simple_query[::-1]
            idx = bisect.bisect_left(data, (rev_query,))

            while idx < len(data):
                rev_name, entry = data[idx]
                if not rev_name.startswith(rev_query):
                    break
                candidates.append(entry)
                idx += 1

        # Filter candidates by Date
        for entry in candidates:
            if criteria.date_min or criteria.date_max:
                file_mtime = dt.fromtimestamp(entry.mtime)
                if criteria.date_min and file_mtime < criteria.date_min:
                    continue
                if criteria.date_max and file_mtime > criteria.date_max:
                    continue
            results.append(SearchResult(entry.path, entry.size, entry.mtime, entry.hash))

        if progress_callback:
            progress_callback(len(results), len(results), 0)
        return results

    # --- STRATEGY B: LINEAR SCAN (O(N)) ---
    # Used for 'contains', Regex, or when size filters present

    # Select Source: Flat list is faster than dict values
    if criteria.size_min is None and criteria.size_max is None:
        iterable_source = file_index.all_files
        total_items = len(file_index.all_files)
    else:
        # If size filtering, use size buckets (O(1) lookup)
        relevant_buckets = []
        total_items = 0
        for size in file_index.size_index:
            if criteria.size_min is not None and size < criteria.size_min:
                continue
            if criteria.size_max is not None and size > criteria.size_max:
                continue
            bucket = file_index.size_index[size]
            relevant_buckets.append(bucket)
            total_items += len(bucket)
        iterable_source = (entry for bucket in relevant_buckets for entry in bucket)

    processed_count = 0
    last_report = 0

    for entry in iterable_source:
        processed_count += 1

        # Benchmark / Progress (Every 20k to minimize IO overhead)
        if progress_callback and (processed_count - last_report >= 20000):
            elapsed = time.time() - start_time
            speed = processed_count / elapsed if elapsed > 0 else 0
            progress_callback(processed_count, total_items, speed)
            last_report = processed_count

        # Name Filtering
        if simple_query:
            name_lower = entry.path.name.lower()
            if query_type == "contains":
                # Python's 'in' operator is highly optimized in C
                if simple_query not in name_lower:
                    continue
            elif query_type == "endswith":
                if not name_lower.endswith(simple_query):
                    continue
            elif query_type == "startswith" and not name_lower.startswith(simple_query):
                continue
        elif name_regex:
            if not name_regex.search(entry.path.name):
                continue

        # Date Filtering
        if criteria.date_min or criteria.date_max:
            file_mtime = dt.fromtimestamp(entry.mtime)
            if criteria.date_min and file_mtime < criteria.date_min:
                continue
            if criteria.date_max and file_mtime > criteria.date_max:
                continue

        results.append(SearchResult(entry.path, entry.size, entry.mtime, entry.hash))

    return results


# ... (Previous helper functions build_destination_index, find_duplicates, etc. remain the same)
def build_destination_index(config: ScanConfig, progress_callback=None, cancel_event=None) -> Optional[FileIndex]:
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    dummy_root = Path(".")
    combined_index = FileIndex(dummy_root, config.use_hash, config.hash_algo)
    for i, dest_path in enumerate(filtered_paths):
        if cancel_event and cancel_event.is_set():
            break
        if not dest_path.is_dir():
            continue
        caf_path = get_caf_path(dest_path, config.hash_algo)
        dest_index = None
        if progress_callback:
            progress_callback(f"Processing folder {i + 1}/{len(filtered_paths)}", f"Folder: {dest_path.name}")
        if config.reuse_indices and not config.recreate_indices and caf_path.exists():
            if progress_callback:
                progress_callback(f"Loading index for {dest_path.name}", "Please wait...")
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        if not dest_index:
            if progress_callback:
                progress_callback(f"Creating new index for {dest_path.name}", t.get("scanning_files"))
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
            if config.reuse_indices:
                if progress_callback:
                    progress_callback(f"Saving index for {dest_path.name}", f"Path: {caf_path.name}")
                dest_index.save_to_caf(caf_path)
        if not dest_index:
            continue

        # Merge logic
        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
            combined_index.all_files.extend(entries)  # Populate flat list
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files

    combined_index.build_optimized_indices()  # Optimize the combined index
    return combined_index


def build_destination_index_selective(
    config: ScanConfig, progress_callback=None, cancel_event=None, translator_get_func=None
) -> Optional[FileIndex]:
    t_get = translator_get_func or t.get
    filtered_paths = filter_overlapping_paths(config.dest_paths)
    if progress_callback:
        progress_callback(t_get("building_index"), f"Processing {len(filtered_paths)} destination folders")
    dummy_root = Path(".")
    combined_index = FileIndex(dummy_root, config.use_hash, config.hash_algo)
    for i, dest_path in enumerate(filtered_paths):
        if cancel_event and cancel_event.is_set():
            break
        if not dest_path.is_dir():
            continue
        caf_path = get_caf_path(dest_path, config.hash_algo)
        dest_index = None
        if progress_callback:
            progress_callback(f"Processing folder {i + 1}/{len(filtered_paths)}", f"Folder: {dest_path.name}")
        force_recreate = (
            hasattr(config, "selective_recreation_paths") and dest_path in config.selective_recreation_paths
        )
        if config.reuse_indices and not force_recreate and caf_path.exists():
            if progress_callback:
                progress_callback(f"Loading index for {dest_path.name}", "Please wait...")
            dest_index = FileIndex.load_from_caf(caf_path, config.use_hash, config.hash_algo)
        if not dest_index:
            if progress_callback:
                progress_callback(f"Creating new index for {dest_path.name}", t_get("scanning_files"))
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
            if config.reuse_indices:
                if progress_callback:
                    progress_callback(f"Saving index for {dest_path.name}", f"Path: {caf_path.name}")
                dest_index.save_to_caf(caf_path)
        if not dest_index:
            continue
        for size, entries in dest_index.size_index.items():
            combined_index.size_index[size].extend(entries)
            combined_index.all_files.extend(entries)
        if config.use_hash:
            for key, entries in dest_index.hash_index.items():
                combined_index.hash_index[key].extend(entries)
        combined_index.total_files += dest_index.total_files
    combined_index.build_optimized_indices()
    return combined_index


def find_duplicates_with_locations(
    source_path: Path, dest_index: FileIndex, progress_callback=None, cancel_event=None
) -> list[DuplicateMatch]:
    source_index = FileIndex(source_path, dest_index.use_hash, dest_index.hash_algo)
    if progress_callback:
        progress_callback(t.get("finding_duplicates"), f"Indexing source directory: {source_path.name}")
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
    source_index._flatten_index()
    if progress_callback:
        progress_callback(t.get("finding_duplicates"), "Comparing against destination indices...")
    return FileIndex.find_all_duplicates_bulk(source_index, dest_index, progress_callback, cancel_event)


def find_duplicates_with_locations_legacy(
    source_path: Path, dest_index: FileIndex, progress_callback=None, cancel_event=None
) -> list[DuplicateMatch]:
    duplicates = []
    source_files = [p for p in source_path.rglob("*") if p.is_file()]
    if progress_callback:
        progress_callback(t.get("finding_duplicates"), f"Checking {len(source_files)} files")
    for i, file_path in enumerate(source_files):
        if cancel_event and cancel_event.is_set():
            break
        if progress_callback and i % 50 == 0:
            progress_callback(t.get("finding_duplicates"), f"Checked {i}/{len(source_files)} files")
        potential_matches = dest_index.find_potential_duplicates_optimized(file_path)
        if potential_matches:
            duplicates.append(DuplicateMatch(source_file=file_path, destinations=potential_matches))
    return duplicates
