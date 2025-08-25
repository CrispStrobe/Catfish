# utils/file_utils.py

"""File operation utilities."""
import hashlib
import re
import sys
import datetime
import platform
from pathlib import Path, PureWindowsPath
from datetime import datetime as dt
from typing import Optional, List
from utils.platform_utils import get_platform_info

def path_is_native_and_exists(path_obj: Path) -> bool:
    """
    Checks if a Path/PurePath object is compatible with the native OS and exists on disk.
    """
    is_windows_path_type = isinstance(path_obj, PureWindowsPath)
    is_on_windows_os = platform.system() == 'Windows'
    
    path_is_native = (is_windows_path_type and is_on_windows_os) or \
                   (not is_windows_path_type and not is_on_windows_os)

    if not path_is_native:
        return False
    
    try:
        # Convert to a concrete Path object for the filesystem check
        return Path(path_obj).exists()
    except (TypeError, OSError):
        # Errors can occur if the path string is invalid on the current OS
        return False

def format_size(size_bytes: int) -> str:
    """Formats bytes into a human-readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def calculate_file_hash(file_path: Path, hash_algo: str) -> str:
    """Calculates the hash of a file."""
    hash_obj = hashlib.new(hash_algo)
    try:
        with file_path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except OSError as e:
        print(f"Warning: Could not read file {file_path}: {e}", file=sys.stderr)
        return ""

def parse_size(size_str: str) -> int:
    """Parse size string like '5MB', '2.5GB' to bytes."""
    if not size_str or size_str.lower() == 'any':
        return 0
    
    size_str = size_str.strip().upper()
    match = re.match(r'^([\d.]+)\s*([KMGT]?B?)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    
    number = float(match.group(1))
    unit = match.group(2) or 'B'
    
    if len(unit) == 1 and unit in "KMGT":
        unit += 'B'
    
    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    return int(number * multipliers.get(unit, 1))
    
def parse_date(date_str: str) -> Optional[dt]:
    """Parse date string in various formats."""
    if not date_str or date_str.lower() in ['any', '']:
        return None
    
    # Handle relative dates in multiple languages
    date_str_lower = date_str.lower()
    now = dt.now()
    
    relative_dates = {
        'today': now.replace(hour=0, minute=0, second=0, microsecond=0),
        'heute': now.replace(hour=0, minute=0, second=0, microsecond=0),
        'yesterday': (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        'gestern': (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
    }
    
    if date_str_lower in relative_dates:
        return relative_dates[date_str_lower]
    
    # Try various date formats
    formats = [
        '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y',
        '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S',
    ]
    
    for fmt in formats:
        try:
            return dt.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Invalid date format: {date_str}")

def is_subdirectory(child: Path, parent: Path) -> bool:
    """Checks if one path is a subdirectory of another."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False

def filter_overlapping_paths(paths: List[Path]) -> List[Path]:
    """Removes paths that are subdirectories of others in the list."""
    sorted_paths = sorted(paths, key=lambda p: len(str(p)))
    unique_paths = []
    for path in sorted_paths:
        if not any(is_subdirectory(path, existing) for existing in unique_paths):
            unique_paths.append(path)
    return unique_paths

def get_caf_path(dest_path: Path, hash_algo: str) -> Path:
    """Generates a consistent CAF file path based on hash algorithm."""
    suffix = f"_{hash_algo}" if hash_algo != 'md5' else ""
    return dest_path.parent / f"{dest_path.name}_index{suffix}.caf"

def get_default_script_name() -> str:
    """Generates a default script name with a timestamp."""
    from datetime import datetime as dt
    platform_info = get_platform_info()
    return f'delete_duplicates_{dt.now().strftime("%Y%m%d_%H%M%S")}{platform_info["script_ext"]}'

def escape_script_path(path: Path) -> str:
    """Escapes a file path for use in a shell/batch script."""
    return get_platform_info()['path_quote'](path)

def get_display_path(file_path: Path) -> str:
    """Get a user-friendly display path, showing relative to home if possible."""
    try:
        # Use str() for comparison to handle PurePath objects correctly
        home_path_str = str(Path.home())
        file_path_str = str(file_path)
        if file_path_str.startswith(home_path_str):
            # Recreate path object to use relative_to
            return "~/" + str(Path(file_path).relative_to(Path.home()))
        return file_path_str
    except (ValueError, OSError):
        return str(file_path)