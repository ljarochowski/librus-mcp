"""YAML config adapter"""
import yaml
from pathlib import Path
from typing import List, Optional

from ..ports import IConfigPort
from ..domain.models import Child


class YamlConfigAdapter(IConfigPort):
    """YAML-based configuration"""
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self._config = self._load()
    
    def _load(self) -> dict:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def get_children(self) -> List[Child]:
        children = []
        for c in self._config.get('children', []):
            children.append(Child(
                name=c['name'],
                aliases=c.get('aliases', []),
                username=c.get('username'),
                password=c.get('password')
            ))
        return children
    
    def get_child(self, name: str) -> Optional[Child]:
        name_lower = name.lower()
        for child in self.get_children():
            if child.matches_name(name_lower):
                return child
        return None
    
    def get_browser_timeout(self) -> int:
        return self._config.get('browser', {}).get('login_timeout_ms', 120000)
    
    def get_page_timeout(self) -> int:
        return self._config.get('browser', {}).get('page_timeout_ms', 30000)
    
    @property
    def data_dir(self) -> Path:
        dir_name = self._config.get('storage', {}).get('data_dir', '.librus_scraper')
        return Path.home() / dir_name
