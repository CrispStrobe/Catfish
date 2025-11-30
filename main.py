#!/usr/bin/env python3
"""
Universal File Search and Index Tool - Entry Point

A comprehensive file indexing and search tool with duplicate detection capabilities,
supporting both a full GUI and a powerful command-line interface.
"""

import argparse
import sys
import json
import cmd
import shlex
import time
from pathlib import Path
from datetime import datetime as dt

# Import all required components from your project structure
from core.config import Config
from core.index_discovery import IndexDiscovery
from core.search_logic import search_files_in_index, build_destination_index, find_duplicates_with_locations
from core.data_structures import SearchCriteria, ScanConfig
from core.file_index import FileIndex
from utils.i18n import translator as t
from utils.file_utils import format_size, parse_size, parse_date
from ui.main_window import UniversalSearchApp

# --- Custom Parser to prevent REPL crashes ---
class SilentArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Instead of exiting, raise an error we can catch
        raise ValueError(message)

class SearchShell(cmd.Cmd):
    """Interactive command shell for performing multiple searches without reloading indices."""
    intro = 'Welcome to the Universal Search Shell.\nType "help" or "?" to list commands.\nType "search <pattern>" to find files (e.g., search *.jpg --size-min 5MB).'
    prompt = '(search) '

    def __init__(self, active_indices):
        super().__init__()
        self.active_indices = active_indices
        self.loaded_indices = []
        self._load_indices()

    def _load_indices(self):
        print(f"Loading {len(self.active_indices)} indices...", file=sys.stderr)
        for caf_path in self.active_indices:
            print(f"Loading {caf_path.name}...", file=sys.stderr)
            name = caf_path.stem.lower()
            hash_algo = 'sha256' if '_sha256' in name else 'sha1' if '_sha1' in name else 'md5'
            idx = FileIndex.load_from_caf(caf_path, use_hash=True, hash_algo=hash_algo)
            if idx:
                self.loaded_indices.append((caf_path.name, idx))
        print(f"Loaded {len(self.loaded_indices)} indices. Ready to search.", file=sys.stderr)

    def do_search(self, arg):
        """
        Search files. 
        Usage: search <pattern> [options]
        
        Options:
          --size-min <size>   Minimum file size (e.g. 1MB, 500KB)
          --size-max <size>   Maximum file size
          --date-min <date>   Min modification date (YYYY-MM-DD)
          --date-max <date>   Max modification date
        
        Example: 
          search *report* --size-min 1MB --date-min 2023-01-01
        """
        # 1. Setup Parser (Safe Mode)
        parser = SilentArgumentParser(prog="search", description="Search files", add_help=False)
        parser.add_argument('pattern', type=str, nargs='?', help="Search pattern")
        parser.add_argument('--size-min', type=str)
        parser.add_argument('--size-max', type=str)
        parser.add_argument('--date-min', type=str)
        parser.add_argument('--date-max', type=str)
        parser.add_argument('--help', '-h', action='store_true')

        try:
            # Handle empty input
            if not arg:
                print("Error: Missing search pattern.")
                print(self.do_search.__doc__)
                return

            # Split args respecting quotes
            try:
                args_list = shlex.split(arg)
            except ValueError as e:
                print(f"Error parsing quotes: {e}")
                return

            parsed_args, unknown = parser.parse_known_args(args_list)

            # Handle Help
            if parsed_args.help:
                print(self.do_search.__doc__)
                return
            
            # Handle missing pattern after parsing
            if not parsed_args.pattern:
                print("Error: Pattern required.")
                return

            # 2. Build Criteria
            criteria = SearchCriteria(
                name_pattern=parsed_args.pattern,
                size_min=parse_size(parsed_args.size_min) if parsed_args.size_min else None,
                size_max=parse_size(parsed_args.size_max) if parsed_args.size_max else None,
                date_min=parse_date(parsed_args.date_min) if parsed_args.date_min else None,
                date_max=parse_date(parsed_args.date_max) if parsed_args.date_max else None
            )

            # 3. Run Search
            all_results = []
            
            def progress_printer(current, total, speed):
                # Update line in place
                if total > 0:
                    pct = int((current / total) * 100)
                    sys.stderr.write(f"\rScanning... {current}/{total} ({pct}%) @ {int(speed)} items/s")
                else:
                    sys.stderr.write(f"\rScanning... {current} @ {int(speed)} items/s")
                sys.stderr.flush()

            start_time = time.time()
            for name, idx in self.loaded_indices:
                results = search_files_in_index(idx, criteria, progress_callback=progress_printer)
                for res in results:
                    all_results.append((name, res))
            
            elapsed = time.time() - start_time
            sys.stderr.write(f"\rDone. Found {len(all_results)} files in {elapsed:.3f}s.                \n")

            # 4. Print Results
            if not all_results:
                print("No matches found.")
            else:
                # Limit output if too many results
                if len(all_results) > 1000:
                    print(f"Displaying first 20 of {len(all_results)} results:")
                    display_set = all_results[:20]
                else:
                    display_set = all_results

                for index_name, result in display_set:
                    modified_time = dt.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M')
                    print(f"{format_size(result.size):>10s} | {modified_time} | {result.path}")
                
                if len(all_results) > 1000:
                    print(f"... and {len(all_results)-20} more.")

        except ValueError as e:
            print(f"Input Error: {e}")
        except Exception as e:
            print(f"Unexpected Error: {e}")

    def do_exit(self, arg):
        """Exit the shell."""
        print("Goodbye.")
        return True
    
    def do_quit(self, arg):
        """Exit the shell."""
        return self.do_exit(arg)

def run_search_cli(args):
    """Handles the 'search' command in CLI mode."""
    print("--- Running in Search Mode ---", file=sys.stderr)
    config = Config()
    discovery = IndexDiscovery(config)
    indices = discovery.discover_indices()
    active_indices = [path for path in indices if config.is_index_active(str(path))]

    if not active_indices:
        print("Error: No active index files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Searching across {len(active_indices)} active index file(s)...", file=sys.stderr)

    try:
        criteria = SearchCriteria(
            name_pattern=args.pattern,
            size_min=parse_size(args.size_min) if args.size_min else None,
            size_max=parse_size(args.size_max) if args.size_max else None,
            date_min=parse_date(args.date_min) if args.date_min else None,
            date_max=parse_date(args.date_max) if args.date_max else None
        )
    except ValueError as e:
        print(f"Error: Invalid search criteria. {e}", file=sys.stderr)
        sys.exit(1)

    all_results = []
    
    # Callback to print progress to stderr with speed
    # FIX: Added 'speed' argument to match core logic call signature
    def progress_printer(current, total, speed):
        if total > 0:
            percent = int((current / total) * 100)
            sys.stderr.write(f"\r[SEARCH] Scanning... {current}/{total} ({percent}%) @ {int(speed)} items/s")
        else:
            sys.stderr.write(f"\r[SEARCH] Scanning... {current} @ {int(speed)} items/s")
        sys.stderr.flush()

    for caf_path in active_indices:
        print(f"\nLoading index: {caf_path.name}...", file=sys.stderr)
        name = caf_path.stem.lower()
        hash_algo = 'sha256' if '_sha256' in name else 'sha1' if '_sha1' in name else 'md5'
        
        file_index = FileIndex.load_from_caf(caf_path, use_hash=True, hash_algo=hash_algo)
        if file_index:
            results = search_files_in_index(file_index, criteria, progress_callback=progress_printer)
            sys.stderr.write("\n") # Newline
            
            for res in results:
                all_results.append({'result': res, 'index_name': caf_path.name})

    if args.output == 'json':
        json_results = [
            {
                "path": str(item['result'].path),
                "size_bytes": item['result'].size,
                "modified_iso": dt.fromtimestamp(item['result'].mtime).isoformat(),
                "modified_unix": item['result'].mtime,
                "source_index": item['index_name']
            }
            for item in all_results
        ]
        print(json.dumps(json_results, indent=2))
    else: # Text output
        if not all_results:
            print("No matching files found.")
            return
            
        for item in all_results:
            result = item['result']
            modified_time = dt.fromtimestamp(result.mtime).strftime('%Y-%m-%d %H:%M')
            print(f"{format_size(result.size):>10s} | {modified_time} | [{item['index_name']}] {result.path}")
        print(f"\nFound {len(all_results)} matching file(s).", file=sys.stderr)


def run_dupes_cli(args):
    """Handles the 'find-dupes' command in CLI mode."""
    print("--- Running in Duplicate Finder Mode ---", file=sys.stderr)
    
    if not args.source.is_dir():
        print(f"Error: Source path '{args.source}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)
    for dest in args.destinations:
        if not dest.is_dir():
            print(f"Error: Destination path '{dest}' is not a valid directory.", file=sys.stderr)
            sys.exit(1)

    config = ScanConfig(
        source_path=args.source,
        dest_paths=args.destinations,
        use_hash=bool(args.hash),
        hash_algo=args.hash if args.hash else 'md5',
        reuse_indices=args.reuse_indices,
        recreate_indices=args.recreate_indices
    )

    if args.output == 'text':
        print(f"Source: {config.source_path}", file=sys.stderr)
        print(f"Destinations: {[str(p) for p in config.dest_paths]}", file=sys.stderr)
        print(f"Comparison method: {'Hash (' + config.hash_algo + ')' if config.use_hash else 'Name + Size'}", file=sys.stderr)
    
    def cli_progress(operation, details):
        if args.output == 'text':
            if operation.startswith("Processing") or "Scanning" in operation:
                sys.stderr.write(f"\r-> {operation}: {details}")
                sys.stderr.flush()
            else:
                sys.stderr.write(f"\n-> {operation}: {details}")

    try:
        dest_index = build_destination_index(config, progress_callback=cli_progress)
        sys.stderr.write("\n")

        if not dest_index or dest_index.total_files == 0:
            print("\nError: Could not build a destination index or no files found in destination(s).", file=sys.stderr)
            sys.exit(1)

        duplicates = find_duplicates_with_locations(config.source_path, dest_index, progress_callback=cli_progress)
        sys.stderr.write("\n") 

        if args.output == 'json':
            results = []
            for match in duplicates:
                source_info = {
                    "path": str(match.source_file),
                    "size_bytes": match.source_file.stat().st_size,
                    "modified_iso": dt.fromtimestamp(match.source_file.stat().st_mtime).isoformat()
                }
                destination_info = [
                    {
                        "path": str(dest.path),
                        "size_bytes": dest.size,
                        "modified_iso": dt.fromtimestamp(dest.mtime).isoformat()
                    }
                    for dest in match.destinations
                ]
                results.append({
                    "source_file": source_info,
                    "duplicates_found": destination_info
                })
            print(json.dumps(results, indent=2))
        else: # Text output
            if not duplicates:
                print("\n--- No duplicate files found. ---")
                return
            
            print(f"\n--- Found {len(duplicates)} file(s) with duplicates: ---")
            for match in duplicates:
                print(f"\n[Source] {match.source_file}")
                for dest_entry in match.destinations:
                    print(f"  └─ Dupe: {dest_entry.path}")

    except Exception as e:
        print(f"\nAn error occurred during the scan: {e}", file=sys.stderr)
        sys.exit(1)


def run_interactive_cli():
    """Run interactive REPL mode."""
    print("--- Interactive Search Shell ---", file=sys.stderr)
    config = Config()
    discovery = IndexDiscovery(config)
    indices = discovery.discover_indices()
    active_indices = [path for path in indices if config.is_index_active(str(path))]
    
    if not active_indices:
        print("Error: No active index files found. Please create/activate indexes in GUI or Config.", file=sys.stderr)
        return

    try:
        shell = SearchShell(active_indices)
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nExiting shell.")

def run_cli(args):
    """Master CLI handler that dispatches to sub-commands."""
    if args.lang:
        t.set_language(args.lang)
    
    if args.command == 'search':
        run_search_cli(args)
    elif args.command == 'find-dupes':
        run_dupes_cli(args)
    elif args.command == 'interactive':
        run_interactive_cli()


def main():
    """Main entry point for GUI and CLI."""
    parser = argparse.ArgumentParser(
        description="Universal File Search and Index Tool.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Run without arguments to launch the GUI.
Use 'search', 'find-dupes', or 'interactive' for command-line operations.

Examples:
  python main.py interactive
    (Launches the fast interactive shell with pre-loaded indices)

  python main.py search "*.jpg" --size-min 1MB
    (Searches for JPG files over 1MB and prints to console)
"""
    )
    parser.add_argument('--lang', choices=['en', 'de'], help='Set language for CLI output')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands', required=False)

    # --- Search Command ---
    search_parser = subparsers.add_parser('search', help='Search for files in existing indexes')
    search_parser.add_argument('pattern', type=str, help='Search pattern (e.g., "*.txt", or a regex)')
    search_parser.add_argument('--size-min', type=str, help='Minimum file size (e.g., "500KB", "10MB")')
    search_parser.add_argument('--size-max', type=str, help='Maximum file size')
    search_parser.add_argument('--date-min', type=str, help='Minimum modification date (e.g., "2025-01-01")')
    search_parser.add_argument('--date-max', type=str, help='Maximum modification date')
    search_parser.add_argument('--output', choices=['text', 'json'], default='text', help='Output format')

    # --- Find Duplicates Command ---
    dupes_parser = subparsers.add_parser('find-dupes', help='Find duplicate files between a source and destination(s)')
    dupes_parser.add_argument('source', type=Path, help='The source folder to check for duplicates')
    dupes_parser.add_argument('destinations', type=Path, nargs='+', help='One or more destination folders to search within')
    dupes_parser.add_argument('--hash', choices=['md5', 'sha1', 'sha256'], help='Use a hash algorithm for accuracy (slower).')
    dupes_parser.add_argument('--reuse-indices', action='store_true', help='Use existing .caf indexes for destination folders.')
    dupes_parser.add_argument('--recreate-indices', action='store_true', help='Force recreation of all destination indexes.')
    dupes_parser.add_argument('--output', choices=['text', 'json'], default='text', help='Output format')
    
    # --- Interactive Command ---
    subparsers.add_parser('interactive', help='Launch interactive shell (REPL) for instant searching')

    args = parser.parse_args()

    if args.command:
        run_cli(args)
    else:
        try:
            app = UniversalSearchApp()
            app.run()
        except KeyboardInterrupt:
            print("\nApplication interrupted by user.")
        except Exception as e:
            print(f"Application error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()