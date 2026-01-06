"""Configuration loader and manager"""
import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    """Configuration manager - loads and provides access to config values"""
    
    _instance = None
    _config: Dict[str, Any] = {}
    _test_overrides: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """Load configuration from YAML file"""
        config_file = Path(__file__).parent.parent / "config.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        with open(config_file, 'r') as f:
            self._config = yaml.safe_load(f)
    
    def set_test_override(self, key: str, value: Any):
        """Set test override for a config value"""
        self._test_overrides[key] = value
    
    def clear_test_overrides(self):
        """Clear all test overrides"""
        self._test_overrides = {}
    
    @property
    def data_dir(self) -> Path:
        """Get data directory path"""
        if 'data_dir' in self._test_overrides:
            return self._test_overrides['data_dir']
        
        dir_name = self._config['storage']['data_dir']
        path = Path.home() / dir_name
        path.mkdir(exist_ok=True)
        return path
    
    @property
    def login_timeout_ms(self) -> int:
        return self._config['browser']['login_timeout_ms']
    
    @property
    def page_timeout_ms(self) -> int:
        return self._config['browser']['page_timeout_ms']
    
    @property
    def max_messages(self) -> int:
        return self._config['scraping']['max_messages']
    
    @property
    def max_announcements(self) -> int:
        return self._config['scraping']['max_announcements']
    
    @property
    def fetch_delay_ms(self) -> int:
        return self._config['scraping']['fetch_delay_ms']
    
    @property
    def calendar_months_ahead(self) -> int:
        return self._config['scraping']['calendar_months_ahead']
    
    @property
    def colors_enabled(self) -> bool:
        return self._config['console']['colors_enabled']


class Colors:
    """Console color codes"""
    
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    
    @classmethod
    def disable(cls):
        """Disable all colors"""
        cls.HEADER = ''
        cls.BLUE = ''
        cls.CYAN = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.RED = ''
        cls.ENDC = ''
        cls.BOLD = ''


# Initialize colors based on config
config = Config()
if not config.colors_enabled:
    Colors.disable()
