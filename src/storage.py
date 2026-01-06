"""File storage management"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from .config import config
from .credentials import resolve_child_name


def get_child_dir(child_name: str) -> Path:
    """Get storage directory for a child"""
    canonical_name = resolve_child_name(child_name)
    safe_name = canonical_name.lower().replace(" ", "-")
    child_dir = config.data_dir / safe_name
    child_dir.mkdir(parents=True, exist_ok=True)
    return child_dir


def get_context_dir(child_name: str) -> Path:
    """Get browser context directory for a child"""
    context_dir = get_child_dir(child_name) / "browser_context"
    context_dir.mkdir(exist_ok=True)
    return context_dir


def load_state(child_name: str) -> Dict:
    """Load scraping state for a child"""
    state_file = get_child_dir(child_name) / "state.json"
    if state_file.exists():
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return {
        "child_name": resolve_child_name(child_name),
        "last_scrape_iso": None,
        "setup_completed": False
    }


def save_state(child_name: str, state: Dict):
    """Save scraping state for a child"""
    state_file = get_child_dir(child_name) / "state.json"
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def save_scrape_result(child_name: str, markdown: str):
    """Save scraped data as markdown"""
    output_file = get_child_dir(child_name) / "latest.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown)


def load_memory(child_name: str) -> Dict:
    """Load memory/trends for a child"""
    memory_file = get_child_dir(child_name) / "memory.json"
    if memory_file.exists():
        with open(memory_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return {
        "child_name": resolve_child_name(child_name),
        "issues": [],
        "action_items": [],
        "parent_notes": [],
        "trends": {}
    }


def save_memory(child_name: str, memory: Dict):
    """Save memory/trends for a child"""
    memory_file = get_child_dir(child_name) / "memory.json"
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)


def get_last_scan_date(child_name: str) -> Optional[str]:
    """Get last scan date in ISO format"""
    state = load_state(child_name)
    return state.get("last_scrape_iso")
