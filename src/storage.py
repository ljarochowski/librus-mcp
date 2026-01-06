"""File storage management"""
import json
import pickle
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


def save_monthly_data(child_name: str, year: int, month: int, data: Dict) -> None:
    """Save data for specific month in pickle format"""
    child_dir = get_child_dir(child_name)
    monthly_file = child_dir / f"{year}-{month:02d}.pkl"
    with open(monthly_file, 'wb') as f:
        pickle.dump(data, f)


def load_monthly_data(child_name: str, year: int, month: int) -> Optional[Dict]:
    """Load data for specific month"""
    child_dir = get_child_dir(child_name)
    monthly_file = child_dir / f"{year}-{month:02d}.pkl"
    
    if not monthly_file.exists():
        return None
        
    with open(monthly_file, 'rb') as f:
        return pickle.load(f)


def get_recent_months_data(child_name: str, months_back: int = 2) -> Dict:
    """Get data from recent months (current + previous)"""
    now = datetime.now()
    data = {}
    
    for i in range(months_back):
        year = now.year
        month = now.month - i
        
        if month <= 0:
            month += 12
            year -= 1
            
        month_data = load_monthly_data(child_name, year, month)
        if month_data:
            data[f"{year}-{month:02d}"] = month_data
            
    return data


def save_analysis_summary(child_name: str, summary: Dict) -> None:
    """Save agent's analysis summary"""
    child_dir = get_child_dir(child_name)
    summary_file = child_dir / "summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def load_analysis_summary(child_name: str) -> Optional[Dict]:
    """Load agent's analysis summary"""
    child_dir = get_child_dir(child_name)
    summary_file = child_dir / "summary.json"
    
    if not summary_file.exists():
        return None
        
    with open(summary_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tasks(child_name: str, tasks: Dict) -> None:
    """Save parent tasks/checkoffs"""
    child_dir = get_child_dir(child_name)
    tasks_file = child_dir / "tasks.json"
    with open(tasks_file, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def load_tasks(child_name: str) -> Optional[Dict]:
    """Load parent tasks/checkoffs"""
    child_dir = get_child_dir(child_name)
    tasks_file = child_dir / "tasks.json"
    
    if not tasks_file.exists():
        return None
        
    with open(tasks_file, 'r', encoding='utf-8') as f:
        return json.load(f)
