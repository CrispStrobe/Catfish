# main.py

#!/usr/bin/env python3
"""
Universal File Search and Index Tool - Entry Point

A comprehensive file indexing and search tool with duplicate detection capabilities.
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime as dt

from core.config import Config
from core.index_discovery import IndexDiscovery
from core.search_logic import search_files_in_index
from core.data_structures import SearchCriteria
from core.file_index import FileIndex
from utils.i18n import translator as t
from utils.file_utils import format_size, parse_size, parse_date
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

  CLI Text Search:
    python %(prog)s --cli --search "\\.jpg$" --size-min 1MB --date-min 2024-01-01

  CLI JSON Output for scripting:
    python %(prog)s --cli --search "report" --output json
"""
    )

    # --- MODIFIED: Expanded CLI arguments ---
    cli_group = parser.add_argument_group('CLI Mode Options')
    cli_group.add_argument('--cli', action='store_true',
                           help='Use command-line interface instead of GUI')
    cli_group.add_argument('--lang', choices=['en', 'de'],
                           help='Set interface language for CLI output')
    cli_group.add_argument('--search', type=str,
                           help='Search pattern (regex) for filenames')
    cli_group.add_argument('--size-min', type=str,
                           help='Minimum file size (e.g., "500KB", "2MB")')
    cli_group.add_argument('--size-max', type=str,
                           help='Maximum file size')
    cli_group.add_argument('--date-min', type=str,
                           help='Minimum modification date (e.g., "YYYY-MM-DD", "yesterday")')
    cli_group.add_argument('--date-max', type=str,
                           help='Maximum modification date')
    cli_group.add_argument('--output', choices=['text', 'json'], default='text',
                           help='Set the output format for search results (default: text)')

    args = parser.parse_args()

    if args.lang:
        t.set_language(args.lang)

    if args.cli:
        run_cli_mode(args)
        return

    try:
        app = UniversalSearchApp()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
    except Exception as e:
        print(f"Application error: {e}")

def run_cli_mode(args):
    """Run CLI mode with full search and output functionality."""
    config = Config()
    discovery = IndexDiscovery(config)

    # Use only active indices, just like the GUI
    all_indices = discovery.discover_indices()
    active_indices = [path for path in all_indices if config.is_index_active(str(path))]

    if not active_indices:
        print("No active index files found. Please create or activate indices using GUI mode.", file=sys.stderr)
        sys.exit(1)

    # --- criteria parsing with error handling ---
    try:
        size_min = parse_size(args.size_min) if args.size_min else None
        size_max = parse_size(args.size_max) if args.size_max else None
        date_min = parse_date(args.date_min) if args.date_min else None
        date_max = parse_date(args.date_max) if args.date_max else None
    except ValueError as e:
        print(f"Error: Invalid argument. {e}", file=sys.stderr)
        sys.exit(1)

    criteria = SearchCriteria(
        name_pattern=args.search,
        size_min=size_min,
        size_max=size_max,
        date_min=date_min,
        date_max=date_max
    )

    all_results = []
    for caf_path in active_indices:
        # NOTE: we for now determine hash algo from filename, but we should change that to e.g. use comment field instead
        name = caf_path.stem.lower()
        hash_algo = 'sha256' if '_sha256' in name else 'sha1' if '_sha1' in name else 'md5'
        
        file_index = FileIndex.load_from_caf(caf_path, use_hash=True, hash_algo=hash_algo)
        if file_index:
            results = search_files_in_index(file_index, criteria)
            # Add the source index name to each result
            for res in results:
                all_results.append({'result': res, 'index_name': caf_path.name})

    # --- ADDED: Formatted output logic ---
    if args.output == 'json':
        json_results = [
            {
                "path": str(item['result'].path),
                "size": item['result'].size,
                "modified_iso": dt.fromtimestamp(item['result'].mtime).isoformat(),
                "modified_unix": item['result'].mtime,
                "source_index": item['index_name']
            }
            for item in all_results
        ]
        print(json.dumps(json_results, indent=2))
    else: # Default to text output
        if not all_results:
            print("No matching files found.")
            return
            
        for item in all_results:
            result = item['result']
            print(f"[{item['index_name']}] {result.path} ({format_size(result.size)})")
        print(f"\nFound {len(all_results)} matching files across {len(active_indices)} active indices.")

if __name__ == "__main__":
    main()