# utils/platform_utils.py

"""Platform-specific utilities."""
import os
import platform
import subprocess
import stat
from pathlib import Path, PureWindowsPath
from typing import Dict, Tuple
import tkinter as tk

class FileOperationError(Exception):
    """Custom exception for file operation errors."""
    pass

def get_platform_info() -> Dict:
    """Gets platform-specific commands and formatting."""
    system = platform.system().lower()
    if system == 'windows':
        return {
            'name': 'Windows', 'script_ext': '.bat', 'delete_cmd': 'del',
            'path_quote': lambda p: f'"{p}"',
            'script_header': '@echo off\nchcp 65001 > nul\n\n',
            'pause_cmd': 'pause', 'echo_cmd': 'echo'
        }
    else:  # Unix-like (Linux, macOS)
        return {
            'name': 'Unix-like', 'script_ext': '.sh', 'delete_cmd': 'rm -f',
            'path_quote': lambda p: f"'{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'",
            'script_header': '#!/bin/bash\n\n',
            'pause_cmd': 'read -p "Press any key to continue..."', 'echo_cmd': 'echo'
        }

def get_screen_geometry() -> Tuple[int, int]:
    """Gets primary screen dimensions."""
    root = tk.Tk()
    root.withdraw()
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.destroy()
    return width, height

def calculate_window_geometry(screen_width: int, screen_height: int) -> str:
    """Calculates a responsive and centered window geometry string."""
    width = max(900, min(1400, int(screen_width * 0.85)))
    height = max(700, min(1000, int(screen_height * 0.85)))
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    return f"{width}x{height}+{x}+{y}"

def open_file_or_folder(path: Path, open_folder: bool = False):
    """Opens a file or its containing folder using the OS default.
    
    Args:
        path: Path to open (can be a PurePath for cross-platform safety)
        open_folder: If True, open containing folder instead of file
        
    Raises:
        FileOperationError: If the operation fails
        FileNotFoundError: If the path doesn't exist or is for a different OS
    """
    # Check if path is compatible with current OS before trying to access filesystem
    is_windows_path_type = isinstance(path, PureWindowsPath)
    is_on_windows_os = platform.system() == 'Windows'
    if not ((is_windows_path_type and is_on_windows_os) or \
           (not is_windows_path_type and not is_on_windows_os)):
        raise FileNotFoundError(f"Path is not on the current operating system: {path}")

    # Convert to a concrete Path object for filesystem operations
    concrete_path = Path(path)
    target = concrete_path.parent if open_folder else concrete_path
    
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")
    
    try:
        system = platform.system().lower()
        if system == 'windows':
            os.startfile(target)
        elif system == 'darwin':
            subprocess.run(['open', str(target)], check=True)
        else: # Linux
            subprocess.run(['xdg-open', str(target)], check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise FileOperationError(f"Could not open path {target}: {e}")

def make_script_executable(script_path: Path):
    """Makes a script executable on Unix-like systems."""
    if platform.system().lower() != 'windows':
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
