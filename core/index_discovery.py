# core/index_discovery.py

"""Index discovery and management."""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional

from core.config import Config
from core.data_structures import IndexInfo


class IndexDiscovery:
    """Discovers and manages index files."""

    def __init__(self, config: Config):
        self.config = config

    def discover_indices(self) -> list[Path]:
        """Discover all .caf index files in configured locations."""
        indices = []
        search_locations = self.config.get("index_search_locations", [])

        for location_str in search_locations:
            try:
                location = Path(location_str)
                if location.exists() and location.is_dir():
                    # Find all .caf files
                    for caf_file in location.glob("*.caf"):
                        if caf_file.is_file():
                            indices.append(caf_file)
                    # Also search one level deep
                    for subdir in location.iterdir():
                        if subdir.is_dir():
                            for caf_file in subdir.glob("*.caf"):
                                if caf_file.is_file():
                                    indices.append(caf_file)
            except Exception:
                continue

        return list(set(indices))  # Remove duplicates

    def get_index_info(self, caf_path: Path) -> Optional[IndexInfo]:
        """Extract information about an index file using fast metadata loading."""
        from core.file_index import FileIndex

        metadata = FileIndex.load_metadata_only(caf_path)
        if not metadata:
            return None

        # Platform-independent path handling
        device = metadata["device"]
        is_windows_path = "\\" in device or (len(device) > 1 and device[1] == ":")
        PathClass = PureWindowsPath if is_windows_path else PurePosixPath
        root_path = PathClass(device) if device else caf_path.parent

        # Determine hash method from filename
        name = caf_path.stem.lower()
        if "_sha256" in name:
            hash_method = "SHA256"
        elif "_sha1" in name:
            hash_method = "SHA1"
        elif "_md5" in name or "index" in name:
            hash_method = "MD5"
        else:
            hash_method = "None"

        return IndexInfo(
            path=caf_path,
            root_path=root_path,
            file_count=metadata["file_count"],
            total_size=metadata["total_size"],
            created_date=metadata["created_date"],
            hash_method=hash_method,
        )
