#!/usr/bin/env python3
"""Create a sparse metadata fixture and an independent complete scan oracle.

This helper does not import Catfish. The default fixture has 24,000 files,
460 descendant folders, and 359,116,800 logical bytes. It refuses to overwrite
an existing root or manifest. Use --oracle-only for an existing regular tree.
"""

import argparse
import hashlib
import json
import os
import platform
import stat
from pathlib import Path


def generate_oracle(root, output):
    records = []
    directories = []

    def fail(error):
        raise error

    for directory, names, filenames in os.walk(root, followlinks=False, onerror=fail):
        path = Path(directory)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Oracle requires real directories: {path}")
        relative = path.relative_to(root).as_posix()
        directories.append(["" if relative == "." else relative, info.st_mtime_ns // 1000])
        for name in names:
            if not stat.S_ISDIR((path / name).lstat().st_mode):
                raise ValueError(f"Oracle fixture must not contain directory links: {path / name}")
        for name in filenames:
            file = path / name
            info = file.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Oracle fixture must contain only regular files: {file}")
            records.append([file.relative_to(root).as_posix(), info.st_size, info.st_mtime_ns // 1000])
    records.sort()
    directories.sort()
    digest = hashlib.sha256(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    manifest = {
        "root": str(root),
        "files": len(records),
        "foldersExcludingRoot": len(directories) - 1,
        "logicalBytes": sum(row[1] for row in records),
        "mtimeUnit": "microseconds since Unix epoch; Python st_mtime_ns // 1000",
        "filesSizeMtimeDigest": digest,
        "records": records,
        "directories": directories,
        "createdBy": f"Python {platform.python_version()} os.walk + os.lstat; no Catfish imports",
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    return {key: value for key, value in manifest.items() if key not in ("records", "directories")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--oracle-only", action="store_true")
    parser.add_argument("--groups", type=int, default=40)
    parser.add_argument("--folders", type=int, default=10)
    parser.add_argument("--files", type=int, default=60)
    parser.add_argument("--empty", type=int, default=20)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.manifest.exists():
        parser.error("The manifest already exists; choose a new output path")
    if args.oracle_only:
        if not root.is_dir():
            parser.error("The root must be an existing directory with --oracle-only")
    else:
        if min(args.groups, args.folders, args.files, args.empty) < 0:
            parser.error("Fixture dimensions cannot be negative")
        root.mkdir(parents=True, exist_ok=False)
        sizes = [0, 64, 1024, 8192, 65536]
        extensions = ["txt", "jpg", "mp4", "bin", "pdf"]
        directories = [root]
        for group in range(args.groups):
            parent = root / f"group_{group:02d}"
            parent.mkdir()
            directories.append(parent)
            for folder in range(args.folders):
                directory = parent / f"folder_{folder:02d}"
                directory.mkdir()
                directories.append(directory)
                for number in range(args.files):
                    file = directory / f"file_{number:03d}.{extensions[number % len(extensions)]}"
                    with file.open("xb") as stream:
                        stream.truncate(sizes[number % len(sizes)])
                    os.utime(file, (1730000000 + number, 1730000000 + number))
        for number in range(args.empty):
            directory = root / f"empty_{number:02d}"
            directory.mkdir()
            directories.append(directory)
        for directory in directories:
            os.utime(directory, (1730000100, 1730000100))
    print(json.dumps(generate_oracle(root, args.manifest), indent=2))


if __name__ == "__main__":
    main()
