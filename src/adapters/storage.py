"""File storage adapter"""
import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from ..ports import IStoragePort
from ..domain.models import ScrapeResult


class FileStorageAdapter(IStoragePort):
    """File-based storage implementation"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def get_child_dir(self, child_name: str) -> Path:
        safe_name = child_name.lower().replace(" ", "-")
        child_dir = self.base_dir / safe_name
        child_dir.mkdir(parents=True, exist_ok=True)
        return child_dir
    
    def get_context_dir(self, child_name: str) -> Path:
        context_dir = self.get_child_dir(child_name) / "browser_context"
        context_dir.mkdir(exist_ok=True)
        return context_dir
    
    def load_state(self, child_name: str) -> Dict:
        state_file = self.get_child_dir(child_name) / "state.json"
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"child_name": child_name, "last_scrape_iso": None}
    
    def save_state(self, child_name: str, state: Dict) -> None:
        state_file = self.get_child_dir(child_name) / "state.json"
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def save_result(self, child_name: str, result: ScrapeResult) -> None:
        # Save as markdown
        md_file = self.get_child_dir(child_name) / "latest.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(self._result_to_markdown(result))
        
        # Save monthly pickle
        now = result.timestamp
        self._save_monthly(child_name, now.year, now.month, result)
    
    def _result_to_markdown(self, result: ScrapeResult) -> str:
        lines = [f"# Librus Data - {result.child_name}"]
        lines.append(f"**Scraped:** {result.timestamp.isoformat()}\n")
        
        if result.grades:
            lines.append(f"## Grades ({len(result.grades)})")
            for g in result.grades:
                lines.append(f"- {g.subject}: {g.grade} ({g.category}) - {g.date}")
        
        if result.homework:
            lines.append(f"\n## Homework ({len(result.homework)})")
            for h in result.homework:
                lines.append(f"- {h.subject}: {h.title} (due: {h.date_due})")
        
        return "\n".join(lines)
    
    def _save_monthly(self, child_name: str, year: int, month: int, result: ScrapeResult) -> None:
        monthly_file = self.get_child_dir(child_name) / f"{year}-{month:02d}.pkl"
        data = {
            'timestamp': result.timestamp.isoformat(),
            'data': {
                'rawData': {
                    'grades': [vars(g) for g in result.grades],
                    'homework': [vars(h) for h in result.homework],
                    'calendar': [vars(c) for c in result.calendar],
                    'messages': [vars(m) for m in result.messages],
                    'remarks': [vars(r) for r in result.remarks],
                }
            }
        }
        
        # Merge with existing if present
        if monthly_file.exists():
            with open(monthly_file, 'rb') as f:
                existing = pickle.load(f)
            data = self._merge_monthly_data(existing, data)
        
        with open(monthly_file, 'wb') as f:
            pickle.dump(data, f)
    
    def _merge_monthly_data(self, existing: Dict, new: Dict) -> Dict:
        """Merge new data with existing, avoiding duplicates"""
        for key in ['grades', 'messages', 'calendar', 'homework', 'remarks']:
            existing_items = existing.get('data', {}).get('rawData', {}).get(key, [])
            new_items = new.get('data', {}).get('rawData', {}).get(key, [])
            
            existing_sigs = {self._item_signature(key, item) for item in existing_items}
            
            for item in new_items:
                if self._item_signature(key, item) not in existing_sigs:
                    existing_items.append(item)
            
            if 'data' not in existing:
                existing['data'] = {'rawData': {}}
            existing['data']['rawData'][key] = existing_items
        
        existing['timestamp'] = new['timestamp']
        return existing
    
    def _item_signature(self, key: str, item: Dict) -> str:
        if key == 'grades':
            return f"{item.get('subject')}_{item.get('grade')}_{item.get('date')}_{item.get('category')}"
        elif key == 'messages':
            return f"{item.get('date')}_{item.get('sender')}_{item.get('subject')}"
        elif key == 'calendar':
            return f"{item.get('date')}_{item.get('title')}"
        elif key == 'homework':
            return f"{item.get('subject')}_{item.get('title')}_{item.get('date_due')}"
        return str(item)
    
    def load_memory(self, child_name: str) -> Dict:
        memory_file = self.get_child_dir(child_name) / "memory.json"
        if memory_file.exists():
            with open(memory_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"child_name": child_name, "grade_history": {}, "issues": [], "action_items": []}
    
    def save_memory(self, child_name: str, memory: Dict) -> None:
        memory_file = self.get_child_dir(child_name) / "memory.json"
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
    
    def get_recent_data(self, child_name: str, months: int = 2) -> Dict:
        now = datetime.now()
        data = {}
        
        for i in range(months):
            year = now.year
            month = now.month - i
            if month <= 0:
                month += 12
                year -= 1
            
            monthly_file = self.get_child_dir(child_name) / f"{year}-{month:02d}.pkl"
            if monthly_file.exists():
                with open(monthly_file, 'rb') as f:
                    data[f"{year}-{month:02d}"] = pickle.load(f)
        
        return data
