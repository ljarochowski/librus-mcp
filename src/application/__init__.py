"""Application layer - use cases / orchestration"""
from datetime import datetime
from typing import Dict, Optional

from ..ports import IBrowserPort, IStoragePort, IConfigPort
from ..domain.models import ScrapeResult


class ScrapeChildUseCase:
    """Use case: Scrape data for a child"""
    
    def __init__(self, browser: IBrowserPort, storage: IStoragePort, config: IConfigPort):
        self.browser = browser
        self.storage = storage
        self.config = config
    
    async def execute(self, child_name: str, force_full: bool = False) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"status": "error", "message": f"Child not found: {child_name}"}
        
        # Check session
        if not await self.browser.is_session_valid(child):
            return {
                "status": "session_expired",
                "child_name": child.name,
                "message": "Session expired. Use manual_login to refresh."
            }
        
        # Get last scrape date
        state = self.storage.load_state(child.name)
        last_scrape = None if force_full else state.get("last_scrape_iso")
        
        # Scrape
        result = await self.browser.scrape(child, last_scrape)
        
        # Save result
        self.storage.save_result(child.name, result)
        
        # Update state
        state["last_scrape_iso"] = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        self.storage.save_state(child.name, state)
        
        # Update memory
        self._update_memory(child.name, result)
        
        return {
            "status": "success",
            "child_name": child.name,
            "stats": result.stats,
            "mode": "full" if force_full or not last_scrape else f"delta since {last_scrape}"
        }
    
    def _update_memory(self, child_name: str, result: ScrapeResult) -> None:
        memory = self.storage.load_memory(child_name)
        grade_history = memory.setdefault("grade_history", {})
        
        for grade in result.grades:
            if grade.subject not in grade_history:
                grade_history[grade.subject] = []
            
            entry = {
                "grade": grade.grade,
                "date": grade.date,
                "category": grade.category,
                "weight": grade.weight
            }
            
            if entry not in grade_history[grade.subject]:
                grade_history[grade.subject].append(entry)
        
        memory["last_updated"] = datetime.now().isoformat()
        self.storage.save_memory(child_name, memory)


class LoginChildUseCase:
    """Use case: Login for a child"""
    
    def __init__(self, browser: IBrowserPort, config: IConfigPort):
        self.browser = browser
        self.config = config
    
    async def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"status": "error", "message": f"Child not found: {child_name}"}
        
        if not child.username or not child.password:
            return {
                "status": "error",
                "message": f"No credentials configured for {child.name} in config.yaml"
            }
        
        success = await self.browser.login(child)
        
        if success:
            return {"status": "success", "message": f"Login successful for {child.name}"}
        else:
            return {"status": "error", "message": f"Login failed for {child.name}"}


class GetGradesSummaryUseCase:
    """Use case: Get grades summary for a child"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        all_grades = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            all_grades.extend(raw.get('grades', []))
        
        # Separate current vs semester grades
        current = []
        semester = {}
        
        for g in all_grades:
            cat = g.get('category', '').lower()
            subj = g.get('subject', 'Unknown')
            
            if any(x in cat for x in ['śródroczn', 'roczn', 'końcow', 'przewidywan']):
                if subj not in semester:
                    semester[subj] = []
                semester[subj].append(g)
            else:
                current.append(g)
        
        # Group by subject
        by_subject = {}
        for g in current:
            subj = g.get('subject', 'Unknown')
            if subj not in by_subject:
                by_subject[subj] = []
            by_subject[subj].append(g)
        
        return {
            "total_current_grades": len(current),
            "recent_grades": current[-10:],
            "semester_grades": semester,
            "by_subject": by_subject
        }


class GetCalendarEventsUseCase:
    """Use case: Get upcoming calendar events"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str, days_ahead: int = 14) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        from datetime import timedelta
        now = datetime.now()
        cutoff = now + timedelta(days=days_ahead)
        
        all_events = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            all_events.extend(raw.get('calendar', []))
        
        upcoming = []
        for e in all_events:
            try:
                event_date = datetime.strptime(e.get('date', ''), '%Y-%m-%d')
                if now <= event_date <= cutoff:
                    upcoming.append(e)
            except:
                pass
        
        return {
            "total_events": len(all_events),
            "upcoming": sorted(upcoming, key=lambda x: x.get('date', ''))
        }
