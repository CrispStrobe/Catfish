# core/config.py

"""Configuration management."""
import json
from pathlib import Path
from typing import Set

class Config:
    """Application configuration manager."""
    
    def __init__(self):
        self.config_file = Path.home() / '.universal_search_config.json'
        self.default_config = {
            'language': 'en',
            'default_hash_algo': 'md5',
            'auto_load_indices': True,
            'index_search_locations': [
                str(Path.cwd()),
                str(Path.home()),
                str(Path.home() / 'Desktop'),
                str(Path.home() / 'Documents')
            ],
            'window_geometry': None,
            'active_indices': []
        }
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge with defaults
                    config = self.default_config.copy()
                    config.update(loaded)
                    return config
            except Exception:
                pass
        return self.default_config.copy()
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get(self, key: str, default=None):
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """Set configuration value."""
        self.config[key] = value

    def get_active_indices(self) -> Set[str]:
        """Get set of active index file paths."""
        return set(self.config.get('active_indices', []))

    def set_index_active(self, index_path: str, active: bool):
        """Set active state for an index."""
        active_indices = set(self.config.get('active_indices', []))
        if active:
            active_indices.add(index_path)
        else:
            active_indices.discard(index_path)
        self.config['active_indices'] = list(active_indices)

    def is_index_active(self, index_path: str) -> bool:
        """Check if index is active (default True for new indices)."""
        active_indices = self.config.get('active_indices', None)
        if active_indices is None:
            return True  # Default to active for new indices
        return index_path in active_indices