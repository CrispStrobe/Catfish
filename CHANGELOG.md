# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-30

### Added
- `pyproject.toml` for modern Python packaging (replaces `setup.py` as the authoritative config)
- 132 unit and integration tests covering core/, utils/, CLI, index discovery, and scan operations
- GitHub Actions CI workflow: lint (ruff + bandit) + test matrix (3 OSes x 3 Python versions)
- GitHub Actions release workflow: test + build cross-platform binaries + create GitHub Release
- MIT `LICENSE` file
- `CHANGELOG.md`
- `interactive` CLI command documented in readme
- CI/Release status badges in readme

### Fixed
- All 942 lint issues (ruff) across the entire codebase
- Bare `except` clauses replaced with specific exception types throughout
- Duplicate dictionary keys in i18n translations (`total_size`, `index_info`)
- Lambda closure bug in `ui/dialogs.py` (undefined variable `e` in error handler)
- Missing exception chaining (`raise ... from e`) in 5 locations
- Deprecated `locale.getdefaultlocale()` replaced with `locale.getlocale()`
- `format_size()` loop starting at redundant `'B'` unit
- `get_platform_info` imported from wrong module in `duplicate_results.py`
- `dt` variable shadowing `datetime` import in `build_optimized_indices`
- Releases page link in readme pointing to a Google search instead of GitHub
- Diagnostic `print()` calls in `file_index.py` polluting stdout (moved to stderr), which broke JSON CLI output
- `build_binaries.py` hardcoded version `1.0.0` and stale app name; now reads version from `__init__.py` and uses `CatfishSearch`
- `find_all_duplicates_bulk` redundantly re-scanned the filesystem instead of using the already-populated `source_index.size_index`

### Removed
- ~800 lines of dead/legacy code:
  - `load_from_caf_old`, `_ensure_indexes_built`, `_ensure_indexes_built_really`
  - `_find_name_duplicates_optimized`, `_read_caf_string_fast` (duplicate of `_read_string`)
  - `perform_search_old`, `search_files_in_index_with_progress`
  - `find_duplicates_with_locations_legacy`, `get_index_info_old`, `_read_caf_string` (on IndexDiscovery)
  - `clear_duplicate_form`, `add_dup_dest_folder`, `remove_dup_dest_folder`, `clear_dup_dest_folders`
  - Duplicate `_find_hash_duplicates_optimized` method
  - `find_potential_duplicates_optimized` (merged into `find_potential_duplicates`)
  - `build_destination_index_selective` (consolidated into `build_destination_index`)
  - Dead `hasattr(self, "raw_elm")` branches and `_get_or_build_dir_map`
  - Unused `get_display_path` function
- Redundant `setup.py` configuration (reduced to minimal shim)
- Duplicate `run_scan_with_progress_enhanced` (now alias of `run_scan_with_progress`)

### Changed
- Minimum Python version bumped from 3.8 to 3.9
- Package name changed from `file-search` to `catfish-search`
- Version bumped from 1.0.0 to 1.1.0
- `scan_operations.py` reduced from 228 to 76 lines by reusing `search_logic.build_destination_index`
- `build_binaries.py` app name changed to `CatfishSearch`, macOS bundle identifier fixed

## [1.0.0] - 2025

### Added
- Initial release with GUI and CLI interfaces
- CAF file format support (Cathy-compatible)
- File indexing with MD5, SHA1, SHA256 hashing
- Duplicate detection by hash or name+size
- Binary search indices for fast prefix/suffix queries
- Offline index browsing
- English and German translations
- Cross-platform support (Windows, macOS, Linux)
- Interactive REPL shell for repeated searches
- Deletion script generation (.bat/.sh)
