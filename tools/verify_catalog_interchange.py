#!/usr/bin/env python3
"""Opt-in file metadata interchange check against the real Rust crispcat CLI.

Run from a Catfish checkout after building CrispSorter's catalog harness:
  python tools/verify_catalog_interchange.py --rust-cli /path/to/crispcat

Only a fresh temporary fixture is changed. No user catalog or source folder is
read. CAF contains no content hashes; the Rust file index does not retain empty
directories, so those are verified separately through Catfish's offline round trip.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.file_index import FileIndex


def require_equal(actual, expected, description):
    if actual != expected:
        raise RuntimeError(f"{description}: expected {expected!r}, got {actual!r}")


def run_rust(executable, *arguments):
    process = subprocess.run(
        [str(executable), "--format", "json", *map(str, arguments)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [json.loads(line) for line in process.stdout.splitlines() if line.strip()]


def catfish_rows(index):
    if index is None:
        raise RuntimeError("Catfish rejected a generated catalog")
    rows = {str(entry.path.relative_to(index.root_path)): [entry.size, entry.mtime] for entry in index.all_files}
    require_equal(len(rows), len(index.all_files), "unique Catfish paths")
    return rows


def rust_rows(executable, catalog, root, count):
    entries = run_rust(executable, "browse", catalog, "--limit", count + 1)
    rows = {str(Path(entry["path"]).relative_to(root)): [entry["size"], entry["mtime_unix"]] for entry in entries}
    require_equal(len(rows), len(entries), "unique Rust paths")
    require_equal(len(entries), count, "Rust entry count")
    return rows


def verify(executable):
    with tempfile.TemporaryDirectory(prefix="catfish-interchange-") as temporary:
        work = Path(temporary)
        root = work / "source"
        root.mkdir()
        contents = {
            "empty.bin": b"",
            ".hidden": b"hidden",
            "no-files/parent/leaf/Ümläut.txt": b"Latin-1 names",
            "no-files/parent/leaf/same.txt": b"first",
            "another/leaf/same.txt": b"second",
            "spaces/file with spaces": b"spaces",
        }
        # Windows does not support a whitespace-only filename.
        if os.name != "nt":
            contents[" "] = b""
        expected = {}
        for number, (relative, content) in enumerate(contents.items()):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            timestamp = 1_700_000_000 + number
            os.utime(path, (timestamp, timestamp))
            expected[str(Path(relative))] = [len(content), timestamp]
        (root / "empty-folder/empty-child").mkdir(parents=True)
        for directory in [root, *(path for path in root.rglob("*") if path.is_dir())]:
            os.utime(directory, (1_700_000_100, 1_700_000_100))

        rust_catalog = work / "rust.caf"
        scan = run_rust(executable, "scan", root, "--out", rust_catalog)[0]
        require_equal(scan["complete"], True, "complete Rust scan")
        require_equal(scan["files"], len(expected), "Rust scan count")
        require_equal(catfish_rows(FileIndex.load_from_caf(rust_catalog, False, "md5")), expected, "Rust to Catfish")

        index = FileIndex.scan_directory(root)
        require_equal(index.is_complete, True, "complete Catfish scan")
        require_equal(catfish_rows(index), expected, "Catfish live metadata")
        catfish_catalog = work / "catfish.caf"
        index.save_to_caf(catfish_catalog)
        require_equal(rust_rows(executable, catfish_catalog, root, len(expected)), expected, "Catfish to Rust")
        info = run_rust(executable, "info", catfish_catalog)[0]
        require_equal(info["file_count"], len(expected), "CAF header file count")
        require_equal(info["total_size_bytes"], sum(row[0] for row in expected.values()), "CAF header byte total")

        # Move only our generated fixture out of the original location. Reuse
        # must succeed without stat calls against the old source root.
        root.rename(work / "offline-source")
        loaded = FileIndex.load_from_caf(catfish_catalog, False, "md5")
        require_equal(catfish_rows(loaded), expected, "offline Catfish load")
        expected_directories = {
            str(path.relative_to(index.root_path)): timestamp
            for path, timestamp in index.directory_mtimes.items()
            if path != index.root_path
        }
        actual_directories = {
            str(path.relative_to(loaded.root_path)): timestamp
            for path, timestamp in loaded.directory_mtimes.items()
            if path != loaded.root_path
        }
        require_equal(actual_directories, expected_directories, "saved directory metadata and empty folders")
        reused_catalog = work / "offline-copy.caf"
        loaded.save_to_caf(reused_catalog)
        reused = FileIndex.load_from_caf(reused_catalog, False, "md5")
        require_equal(catfish_rows(reused), expected, "offline re-save")
        require_equal(reused.directory_mtimes, loaded.directory_mtimes, "offline folder metadata")
        require_equal(rust_rows(executable, reused_catalog, root, len(expected)), expected, "offline re-save to Rust")
        return {
            "passed": True,
            "files": len(expected),
            "bytes": sum(row[0] for row in expected.values()),
            "descendant_directories": len(expected_directories),
            "checks": [
                "Rust scan/export to Catfish load",
                "Catfish scan/export to Rust browse and header",
                "identical full relative paths, byte sizes and second mtimes",
                "hidden, Latin-1, zero-byte and repeated leaf names",
                "Catfish empty folders and directory mtimes",
                "offline load and re-save readable by both implementations",
            ],
            "whitespace_only_filename": os.name != "nt",
            "scope": "Native paths; classic CAF file metadata, without hash persistence or Rust empty-folder retention",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rust-cli", type=Path, required=True, help="Built real crispcat CLI executable")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence file")
    arguments = parser.parse_args()
    result = verify(arguments.rust_cli.resolve(strict=True))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
