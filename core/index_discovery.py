# core/index_discovery.py

"""Index discovery and management."""
import struct
from pathlib import Path, PureWindowsPath, PurePosixPath
from typing import List, Optional
from datetime import datetime as dt

from core.data_structures import IndexInfo
from core.config import Config

class IndexDiscovery:
    """Discovers and manages index files."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def discover_indices(self) -> List[Path]:
        """Discover all .caf index files in configured locations."""
        indices = []
        search_locations = self.config.get('index_search_locations', [])
        
        for location_str in search_locations:
            try:
                location = Path(location_str)
                if location.exists() and location.is_dir():
                    # Find all .caf files
                    for caf_file in location.glob('*.caf'):
                        if caf_file.is_file():
                            indices.append(caf_file)
                    # Also search one level deep
                    for subdir in location.iterdir():
                        if subdir.is_dir():
                            for caf_file in subdir.glob('*.caf'):
                                if caf_file.is_file():
                                    indices.append(caf_file)
            except Exception:
                continue
        
        return list(set(indices))  # Remove duplicates
    
    def get_index_info(self, caf_path: Path) -> Optional[IndexInfo]:
        """Extract information about an index file by parsing the CAF header."""
        try:
            with caf_path.open('rb') as f:
                # --- Header Parsing ---
                magic = struct.unpack('<L', f.read(4))[0]
                if not (magic > 0 and magic % 1000000000 == 500410407):
                    return None
                
                version = struct.unpack('<h', f.read(2))[0]
                created_timestamp = struct.unpack('<L', f.read(4))[0]
                root_path_str = self._read_caf_string(f)
                
                # Skip remaining header fields to get to the info block
                self._read_caf_string(f)  # volume
                self._read_caf_string(f)  # alias
                f.read(4)  # serial
                self._read_caf_string(f)  # comment
                f.read(4)  # freesize
                f.read(2)  # archive

                # --- Info Block Parsing ---
                dir_count = struct.unpack('<l', f.read(4))[0]
                if dir_count > 0:
                    self._read_caf_string(f)  # Skip root dir name (it's empty)
                    file_count = struct.unpack('<l', f.read(4))[0]
                    total_size = int(struct.unpack('<d', f.read(8))[0])
                else:
                    file_count = 0
                    total_size = 0

                # Platform-independent path handling
                is_windows_path = '\\' in root_path_str or (len(root_path_str) > 1 and root_path_str[1] == ':')
                PathClass = PureWindowsPath if is_windows_path else PurePosixPath
                root_path = PathClass(root_path_str) if root_path_str else caf_path.parent

                # Determine hash method from filename
                name = caf_path.stem.lower()
                if '_sha256' in name:
                    hash_method = 'SHA256'
                elif '_sha1' in name:
                    hash_method = 'SHA1'
                elif '_md5' in name or 'index' in name:
                    hash_method = 'MD5'
                else:
                    hash_method = 'None'
                
                return IndexInfo(
                    path=caf_path,
                    root_path=root_path,
                    file_count=file_count,
                    total_size=total_size,
                    created_date=dt.fromtimestamp(created_timestamp),
                    hash_method=hash_method
                )
        except (struct.error, OSError, IndexError):
            return None
    
    def _read_caf_string(self, buffer) -> str:
        """Read null-terminated string from CAF file, decoded as latin-1 for compatibility."""
        chars = bytearray()
        while (char := buffer.read(1)) != b'\x00':
            if not char:
                break
            chars.extend(char)
        return chars.decode('latin-1', errors='replace')