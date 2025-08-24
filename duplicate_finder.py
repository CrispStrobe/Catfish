#!/usr/bin/env python3
"""
Enhanced Duplicate File Finder and Batch Generator

Combines performance optimizations with detailed duplicate location tracking.
Inspired by the Cathy disk cataloging approach for efficient indexing.

Features:
- Lazy hashing for performance
- Detailed duplicate location tracking
- Hierarchical file organization
- Progress indicators
- Multiple hash algorithms
"""

import os
import sys
import argparse
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, NamedTuple
from tqdm import tqdm

# --- Data Structures ---

class FileEntry(NamedTuple):
    """Represents a single file with its metadata"""
    path: Path
    size: int
    hash: str = ""

class DuplicateMatch(NamedTuple):
    """Represents a duplicate match with source and all destination locations"""
    source_file: Path
    destinations: List[FileEntry]

# --- Core Logic ---

def calculate_file_hash(file_path: Path, hash_algo: str) -> str:
    """Calculate the hash of a file using the specified algorithm."""
    hash_obj = hashlib.new(hash_algo)
    try:
        with file_path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except OSError as e:
        print(f"\nWarning: Could not read file {file_path}: {e}", file=sys.stderr)
        return ""

class FileIndex:
    """
    Efficient file index inspired by Cathy's hierarchical approach.
    Uses size-based bucketing with lazy hash calculation.
    """
    
    def __init__(self, use_hash: bool = False, hash_algo: str = 'md5'):
        self.use_hash = use_hash
        self.hash_algo = hash_algo
        # Primary index: size -> list of files with that size
        self.size_index: Dict[int, List[FileEntry]] = defaultdict(list)
        # Hash index: (size, hash) -> list of files (only populated when needed)
        self.hash_index: Dict[Tuple[int, str], List[FileEntry]] = defaultdict(list)
        self.total_files = 0
        
    def add_file(self, file_path: Path) -> bool:
        """Add a file to the index. Returns True if successful."""
        try:
            file_size = file_path.stat().st_size
            
            if self.use_hash:
                # Calculate hash immediately for hash-based indexing
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash:
                    return False
                entry = FileEntry(file_path, file_size, file_hash)
                self.hash_index[(file_size, file_hash)].append(entry)
            else:
                # For filename-based, we'll use filename as "hash"
                entry = FileEntry(file_path, file_size, file_path.name)
                
            self.size_index[file_size].append(entry)
            self.total_files += 1
            return True
            
        except OSError as e:
            print(f"\nWarning: Could not process file {file_path}: {e}", file=sys.stderr)
            return False
    
    def find_potential_duplicates(self, file_path: Path) -> List[FileEntry]:
        """Find all files that could be duplicates of the given file."""
        try:
            file_size = file_path.stat().st_size
            
            # First check: do we have any files of this size?
            if file_size not in self.size_index:
                return []
            
            if self.use_hash:
                # Hash-based comparison
                file_hash = calculate_file_hash(file_path, self.hash_algo)
                if not file_hash:
                    return []
                return self.hash_index.get((file_size, file_hash), [])
            else:
                # Filename-based comparison
                potential_matches = []
                for entry in self.size_index[file_size]:
                    if entry.hash == file_path.name:  # hash field contains filename
                        potential_matches.append(entry)
                return potential_matches
                
        except OSError as e:
            print(f"\nWarning: Could not process file {file_path}: {e}", file=sys.stderr)
            return []

def build_destination_index(dest_paths: List[Path], use_hash: bool, hash_algo: str) -> FileIndex:
    """
    Build a comprehensive index of all files in destination folders.
    Uses Cathy-inspired hierarchical indexing with lazy evaluation.
    """
    print("Building destination file index...")
    index = FileIndex(use_hash, hash_algo)
    
    # Collect all files from all destination paths
    all_dest_files = []
    for path in dest_paths:
        if path.is_dir():
            all_dest_files.extend(p for p in path.rglob('*') if p.is_file())
        else:
            print(f"\nWarning: Destination path is not a directory: {path}", file=sys.stderr)
    
    # Add files to index with progress bar
    successful_adds = 0
    for file_path in tqdm(all_dest_files, desc="Indexing destination files"):
        if index.add_file(file_path):
            successful_adds += 1
    
    print(f"\nIndexed {successful_adds} files from {len(all_dest_files)} total files")
    return index

def find_duplicates_with_locations(
    source_path: Path, 
    dest_index: FileIndex
) -> List[DuplicateMatch]:
    """
    Find files in the source folder that exist in destinations, 
    with complete location tracking.
    """
    print("Scanning source folder for duplicates...")
    duplicates = []
    
    source_files = [p for p in source_path.rglob('*') if p.is_file()]
    
    for file_path in tqdm(source_files, desc="Checking source files"):
        potential_matches = dest_index.find_potential_duplicates(file_path)
        
        if potential_matches:
            duplicate_match = DuplicateMatch(
                source_file=file_path,
                destinations=potential_matches
            )
            duplicates.append(duplicate_match)
    
    print(f"\nFound {len(duplicates)} files in source with duplicates in destinations")
    return duplicates

# --- Batch File Generation ---

def escape_batch_path(path: Path) -> str:
    """Escape a file path for use in Windows batch files by quoting it."""
    return f'"{path}"'

def generate_enhanced_batch_file(duplicates: List[DuplicateMatch], output_file: str, method: str):
    """Generate a Windows batch file with detailed duplicate location information."""
    if not duplicates:
        print("No duplicates found - no batch file will be generated.")
        return

    print(f"Generating enhanced batch file: {output_file}")
    try:
        with open(output_file, 'w', encoding='utf-8-sig') as f:
            f.write("@echo off\n")
            f.write("chcp 65001 > nul\n\n")
            f.write("REM Enhanced batch file to delete duplicate files from source folder.\n")
            f.write(f"REM Comparison method: {method}\n")
            f.write("REM This file shows exactly WHERE each duplicate was found.\n")
            f.write("REM WARNING: This will permanently delete the files listed below!\n\n")
            f.write("echo ######################################################################\n")
            f.write("echo # WARNING: This script will PERMANENTLY DELETE the files listed.    #\n")
            f.write("echo # Each file shows ALL locations where duplicates were found.         #\n")
            f.write("echo # Review the commands below before proceeding.                       #\n")
            f.write("echo ######################################################################\n\n")
            f.write("echo Press Ctrl+C to cancel, or any key to begin deletion...\n")
            f.write("pause > nul\n\n")

            total_destinations = 0
            for duplicate in duplicates:
                f.write(f"REM Deleting source file: {duplicate.source_file}\n")
                f.write(f"REM Found {len(duplicate.destinations)} duplicate(s) at:\n")
                
                for dest_entry in duplicate.destinations:
                    f.write(f"REM   -> {dest_entry.path} ({dest_entry.size:,} bytes)\n")
                    total_destinations += 1
                
                f.write(f"del {escape_batch_path(duplicate.source_file)}\n\n")

            f.write(f"echo Deletion process completed for {len(duplicates)} source files.\n")
            f.write(f"echo Total duplicate locations found: {total_destinations}\n")
            f.write("pause\n")

        print(f"✅ Enhanced batch file '{output_file}' created successfully.")
        print(f"📊 Summary: {len(duplicates)} source files have duplicates in {total_destinations} destination locations")
        print("🚨 IMPORTANT: Review the batch file carefully before running it!")
    except IOError as e:
        print(f"\nError: Could not create batch file: {e}", file=sys.stderr)

def generate_duplicate_report(duplicates: List[DuplicateMatch], output_file: str):
    """Generate a detailed text report of all duplicates found."""
    if not duplicates:
        print("No duplicates found - no report will be generated.")
        return
    
    report_file = output_file.replace('.bat', '_report.txt')
    print(f"Generating duplicate report: {report_file}")
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("DUPLICATE FILES REPORT\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Total source files with duplicates: {len(duplicates)}\n")
            f.write(f"Total destination locations: {sum(len(d.destinations) for d in duplicates)}\n\n")
            
            for i, duplicate in enumerate(duplicates, 1):
                f.write(f"{i}. SOURCE: {duplicate.source_file}\n")
                f.write(f"   Size: {duplicate.source_file.stat().st_size:,} bytes\n")
                f.write(f"   Found in {len(duplicate.destinations)} location(s):\n")
                
                for j, dest_entry in enumerate(duplicate.destinations, 1):
                    f.write(f"   {j}. {dest_entry.path}\n")
                
                f.write("\n")
        
        print(f"✅ Duplicate report saved to: {report_file}")
    except IOError as e:
        print(f"\nError: Could not create report file: {e}", file=sys.stderr)

# --- Main Execution ---

def main():
    """Main function with enhanced argument parsing and workflow coordination."""
    parser = argparse.ArgumentParser(
        description="Enhanced duplicate file finder with detailed location tracking.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic filename+size comparison (fastest)
  python %(prog)s "C:\\Downloads" "D:\\Photos" "D:\\Documents"

  # MD5 hash comparison (more accurate, shows renamed duplicates)  
  python %(prog)s "C:\\Downloads" "D:\\Archive" --hash md5

  # SHA256 comparison (most secure) with custom output
  python %(prog)s "C:\\Source" "D:\\Backup1" "E:\\Backup2" --hash sha256 -o "cleanup.bat"

  # Generate both batch file and detailed report
  python %(prog)s "C:\\Downloads" "D:\\Archive" --hash md5 --report
"""
    )

    parser.add_argument('source_folder', type=Path,
                        help='Source folder to scan for duplicates.')
    parser.add_argument('dest_folders', type=Path, nargs='+',
                        help='One or more destination folders to compare against.')
    parser.add_argument('--hash', choices=['md5', 'sha1', 'sha256'], default=None,
                        help='Use file hash for comparison (more accurate, slower).')
    parser.add_argument('--output', '-o', default='delete_duplicates.bat',
                        help='Output batch file name (default: delete_duplicates.bat)')
    parser.add_argument('--report', action='store_true',
                        help='Generate detailed text report in addition to batch file')

    args = parser.parse_args()

    # --- Path Validation ---
    if not args.source_folder.is_dir():
        print(f"Error: Source folder does not exist or is not a directory: {args.source_folder}", file=sys.stderr)
        sys.exit(1)

    valid_dest_folders = [p for p in args.dest_folders if p.is_dir()]
    if not valid_dest_folders:
        print("Error: None of the provided destination paths are valid directories.", file=sys.stderr)
        sys.exit(1)

    invalid_dest_folders = [p for p in args.dest_folders if not p.is_dir()]
    if invalid_dest_folders:
        print(f"Warning: Ignoring invalid destination paths: {', '.join(map(str, invalid_dest_folders))}")

    # --- Execution ---
    use_hash = bool(args.hash)
    method = f"{args.hash.upper()} hash + size" if use_hash else "filename + size"
    
    print("ENHANCED DUPLICATE FINDER")
    print("=" * 50)
    print(f"Source: {args.source_folder}")
    print(f"Destinations: {', '.join(map(str, valid_dest_folders))}")
    print(f"Method: {method}")
    print(f"Batch file: {args.output}")
    if args.report:
        print(f"Report file: {args.output.replace('.bat', '_report.txt')}")
    print()

    # Build destination index
    dest_index = build_destination_index(valid_dest_folders, use_hash, args.hash or 'md5')
    
    # Find duplicates with full location tracking
    duplicates = find_duplicates_with_locations(args.source_folder, dest_index)
    
    # Generate outputs
    generate_enhanced_batch_file(duplicates, args.output, method)
    
    if args.report:
        generate_duplicate_report(duplicates, args.output)

    print(f"\n🎯 Process completed successfully!")
    print(f"📁 Found {len(duplicates)} source files with duplicates")
    
    if duplicates:
        total_size = sum(d.source_file.stat().st_size for d in duplicates)
        print(f"💾 Total size of duplicates: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")

if __name__ == "__main__":
    main()