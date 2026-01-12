"""Ports - abstract interfaces for external dependencies"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pathlib import Path

from ..domain.models import Child, ScrapeResult


class IBrowserPort(ABC):
    """Port for browser automation"""
    
    @abstractmethod
    async def login(self, child: Child) -> bool:
        """Perform login for a child. Returns True if successful."""
        pass
    
    @abstractmethod
    async def is_session_valid(self, child: Child) -> bool:
        """Check if saved session is still valid."""
        pass
    
    @abstractmethod
    async def scrape(self, child: Child, last_scrape: Optional[str]) -> ScrapeResult:
        """Scrape data for a child."""
        pass


class IStoragePort(ABC):
    """Port for data persistence"""
    
    @abstractmethod
    def get_child_dir(self, child_name: str) -> Path:
        """Get storage directory for a child."""
        pass
    
    @abstractmethod
    def load_state(self, child_name: str) -> Dict:
        """Load scraping state."""
        pass
    
    @abstractmethod
    def save_state(self, child_name: str, state: Dict) -> None:
        """Save scraping state."""
        pass
    
    @abstractmethod
    def save_result(self, child_name: str, result: ScrapeResult) -> None:
        """Save scrape result."""
        pass
    
    @abstractmethod
    def load_memory(self, child_name: str) -> Dict:
        """Load memory/trends."""
        pass
    
    @abstractmethod
    def save_memory(self, child_name: str, memory: Dict) -> None:
        """Save memory/trends."""
        pass
    
    @abstractmethod
    def get_recent_data(self, child_name: str, months: int) -> Dict:
        """Get recent months data."""
        pass


class IConfigPort(ABC):
    """Port for configuration"""
    
    @abstractmethod
    def get_children(self) -> List[Child]:
        """Get all configured children."""
        pass
    
    @abstractmethod
    def get_child(self, name: str) -> Optional[Child]:
        """Get child by name or alias."""
        pass
    
    @abstractmethod
    def get_browser_timeout(self) -> int:
        """Get browser timeout in ms."""
        pass
    
    @abstractmethod
    def get_page_timeout(self) -> int:
        """Get page timeout in ms."""
        pass
