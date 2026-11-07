#!/usr/bin/env python3
"""Benchmark actual Catfish APIs against a complete independent file manifest.

Run each checkout in a separate process, on the same unchanged fixture, while
other compilers and benchmarks are idle. The baseline Create Index workflow is
an exact headless emulation of its two walks; the updated workflow calls the
production core.catalog_creation.create_catalog function. No GUI rendering or
hashing is included. See docs/scan-performance.md for commands and limits.
"""

import argparse
import contextlib
import gc
import hashlib
import io
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def digest(records):
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--revision", required=True, help="Recorded source revision; hashes also pin actual files")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--verify-only", action="store_true", help="Validate every workflow once without timing")
    args = parser.parse_args()
    root = args.root.resolve()
    source = args.source.resolve()
    output = args.output.resolve()
    if args.samples < 1:
        parser.error("At least one measured sample is required")
    if root == output or root in output.parents:
        parser.error("Keep benchmark output and temporary catalogs outside the input fixture")
    if not root.is_dir():
        parser.error("Fixture root is not a directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    oracle = json.loads(args.manifest.read_text(encoding="utf-8"))
    if "microseconds" not in oracle.get("mtimeUnit", ""):
        parser.error("The manifest must record microsecond mtimes; see tools/create_scan_fixture.py")
    expected = sorted([path, size, mtime // 1_000_000] for path, size, mtime in oracle["records"])
    expected_directories = sorted([path or ".", mtime // 1_000_000] for path, mtime in oracle.get("directories", []))
    expected_digest = digest(expected)

    sys.path.insert(0, str(source))
    from core.data_structures import ScanConfig
    from core.file_index import FileIndex
    from core.search_logic import build_destination_index

    updated_workflow = (source / "core/catalog_creation.py").is_file()
    if updated_workflow:
        from core.catalog_creation import create_catalog

    config = ScanConfig(root, [root], False, "md5", False, False)

    def production_scan():
        return build_destination_index(config)

    def dialog_scan():
        if updated_workflow:
            return FileIndex.scan_directory(root, False, "md5")
        index = FileIndex(root, False, "md5")
        total = sum(1 for path in root.rglob("*") if path.is_file())
        for path in root.rglob("*"):
            if path.is_file():
                index.add_file(path)
        if total != index.total_files:
            raise RuntimeError("The baseline GUI count and indexed count differ")
        return index

    def verify(index, *, allow_invalid=False, validate_directories=True):
        if index is None:
            rows = []
        else:
            rows = sorted(
                [entry.path.relative_to(root).as_posix(), entry.size, entry.mtime] for entry in index.all_files
            )
        actual_digest = digest(rows)
        valid = rows == expected
        result = {
            "files": len(rows),
            "logical_bytes": sum(row[1] for row in rows),
            "path_size_mtime_seconds_sha256": actual_digest,
            "matches_every_expected_file": valid,
        }
        if not valid and not allow_invalid:
            raise RuntimeError(f"Full file oracle mismatch: {result}")
        if index is not None and hasattr(index, "directory_mtimes") and validate_directories:
            directories = sorted(
                [path.relative_to(root).as_posix(), mtime] for path, mtime in index.directory_mtimes.items()
            )
            result["folders_excluding_root"] = len(directories) - 1
            result["matches_every_expected_directory"] = directories == expected_directories
            if directories != expected_directories and not allow_invalid:
                raise RuntimeError("The directory path/mtime oracle differs")
        if index is not None and hasattr(index, "is_complete") and not index.is_complete:
            raise RuntimeError("Production scanner returned an incomplete scan")
        return result

    def measure(function, verify_function):
        # Imports, validation, GC, output rendering, and process startup are not
        # timed. A warmup precedes each measured mode; the OS cache stays warm.
        with contextlib.redirect_stderr(io.StringIO()):
            value = function()
            validation = verify_function(value)
            del value
            if args.verify_only:
                return {"verification": validation}
            samples = []
            for _ in range(args.samples):
                gc.collect()
                started = time.perf_counter_ns()
                value = function()
                elapsed = time.perf_counter_ns() - started
                validation = verify_function(value)
                samples.append(elapsed / 1_000_000)
                del value
        median = statistics.median(samples)
        return {
            "samples_ms": samples,
            "median_ms": median,
            "min_ms": min(samples),
            "max_ms": max(samples),
            "files_per_second": len(expected) * 1000 / median
            if validation.get("matches_every_expected_file")
            else None,
            "verification": validation,
        }

    source_files = ["core/file_index.py", "core/search_logic.py", "utils/file_utils.py", "ui/dialogs.py"]
    if updated_workflow:
        source_files.append("core/catalog_creation.py")
    result = {
        "repository": "https://github.com/CrispStrobe/Catfish",
        "revision": args.revision,
        "source_sha256": {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in source_files},
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": sys.version,
        "platform": platform.platform(),
        "logical_cpu_count": os.cpu_count(),
        "fixture": {
            "root": str(root),
            "files": len(expected),
            "folders_excluding_root": oracle["foldersExcludingRoot"],
            "logical_bytes": sum(row[1] for row in expected),
            "path_size_mtime_seconds_sha256": expected_digest,
            "original_microsecond_oracle_sha256": oracle["filesSizeMtimeDigest"],
        },
        "protocol": {
            "warmups_per_mode": 1,
            "measured_samples_per_mode": 0 if args.verify_only else args.samples,
            "cache": "warm; no cache flushing",
            "hashing": False,
            "progress_callbacks": False,
            "excluded": "process startup, imports, GC between runs, full oracle verification, GUI rendering",
            "stderr": "captured in memory equally for both revisions",
            "mtime_comparison": "integer seconds; this is Catfish's metadata and CAF precision",
            "create_index_workflow": "production headless function"
            if updated_workflow
            else "baseline GUI two-pass emulation",
        },
        "variants": {},
    }
    with tempfile.TemporaryDirectory(prefix="catfish-bench-", dir=output.parent) as temporary:
        catalog = Path(temporary) / "saved.caf"

        def dialog_scan_and_save():
            if updated_workflow:
                return create_catalog(root, catalog, False, "md5")
            index = dialog_scan()
            index.save_to_caf(catalog)
            return index

        for name, function in [
            ("production_build_destination_index_with_search_sorts", production_scan),
            ("create_index_metadata_only", dialog_scan),
            ("create_index_metadata_and_save", dialog_scan_and_save),
        ]:
            result["variants"][name] = measure(function, verify)
            print(f"Verified {name}")

        saved_index = dialog_scan()

        def save_only():
            saved_index.save_to_caf(catalog)

        result["variants"]["caf_save_only"] = measure(save_only, lambda _: {"catalog_bytes": catalog.stat().st_size})
        result["variants"]["caf_load_with_search_sorts"] = measure(
            lambda: FileIndex.load_from_caf(catalog, False, "md5"),
            # The baseline catalog has a known missing-ancestor bug; record its
            # actual result without treating that invalid reload as a speed win.
            lambda index: verify(index, allow_invalid=True, validate_directories=False),
        )
        with contextlib.redirect_stderr(io.StringIO()):
            loaded = FileIndex.load_from_caf(catalog, False, "md5")
        if updated_workflow:
            if loaded is None:
                raise RuntimeError("Updated catalog did not load")
            # CAF has no root-folder mtime, so verify descendant folder metadata.
            actual_dirs = sorted(
                [path.relative_to(root).as_posix(), mtime]
                for path, mtime in loaded.directory_mtimes.items()
                if path != loaded.root_path
            )
            if actual_dirs != [row for row in expected_directories if row[0] != "."]:
                raise RuntimeError("Saved catalog lost descendant directory metadata")
            if not result["variants"]["caf_load_with_search_sorts"]["verification"]["matches_every_expected_file"]:
                raise RuntimeError("Updated catalog did not preserve every file")
        result["catalog_roundtrip"] = {
            "catalog_bytes": catalog.stat().st_size,
            "loaded_files": None if loaded is None else loaded.total_files,
            "loaded_folders_excluding_root": len(loaded.directory_mtimes) - 1
            if loaded is not None and hasattr(loaded, "directory_mtimes")
            else None,
            "valid": result["variants"]["caf_load_with_search_sorts"]["verification"]["matches_every_expected_file"],
            "hashes_persisted": False,
        }
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "catalog_roundtrip": result["catalog_roundtrip"]}, indent=2))


if __name__ == "__main__":
    main()
