"""Abstract interfaces for SOLID compliance"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
from pathlib import Path


class ICredentialsProvider(ABC):
    """Interface for credentials management"""
    
    @abstractmethod
    def get_child_credentials(self, child_name: str) -> Dict:
        """Get credentials for a child"""
        pass
    
    @abstractmethod
    def resolve_child_name(self, name: str) -> str:
        """Resolve alias to canonical name"""
        pass
    
    @abstractmethod
    def list_children(self) -> list:
        """List all configured children"""
        pass


class IStorageProvider(ABC):
    """Interface for data storage"""
    
    @abstractmethod
    def get_child_dir(self, child_name: str) -> Path:
        """Get storage directory for a child"""
        pass
    
    @abstractmethod
    def load_state(self, child_name: str) -> Dict:
        """Load scraping state"""
        pass
    
    @abstractmethod
    def save_state(self, child_name: str, state: Dict):
        """Save scraping state"""
        pass
    
    @abstractmethod
    def save_scrape_result(self, child_name: str, markdown: str):
        """Save scraped data"""
        pass
    
    @abstractmethod
    def load_memory(self, child_name: str) -> Dict:
        """Load memory/trends"""
        pass
    
    @abstractmethod
    def save_memory(self, child_name: str, memory: Dict):
        """Save memory/trends"""
        pass


class IScraper(ABC):
    """Interface for scraping logic"""
    
    @abstractmethod
    async def scrape(self, page, last_scrape: Optional[str], is_first: bool) -> Dict:
        """Scrape data from Librus"""
        pass


class IMemoryManager(ABC):
    """Interface for memory management"""
    
    @abstractmethod
    async def update_memory(self, child_name: str, raw_data: Dict):
        """Update memory with new data"""
        pass
    
    @abstractmethod
    def format_memory(self, memory: Dict) -> str:
        """Format memory as readable text"""
        pass
