#!/usr/bin/env python3
"""
Universal File Search and Index Tool - Entry Point

A comprehensive file indexing and search tool with duplicate detection capabilities.
"""

import argparse
import sys
from pathlib import Path

from core.config import Config
from core.index_discovery import IndexDiscovery
from core.search_logic import search_files_in_index
from core.data_structures import SearchCriteria
from core.file_index import FileIndex
from utils.i18n import translator as t
from utils.file_utils import format_size
from ui.main_window import UniversalSearchApp

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
        run_cli_mode(args)
        return

    # GUI mode (default)
    try:
        app = UniversalSearchApp()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
    except Exception as e:
        print(f"Application error: {e}")

def run_cli_mode(args):
    """Run CLI mode with basic functionality."""
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

if __name__ == "__main__":
    main()