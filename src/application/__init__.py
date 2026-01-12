"""Application layer - use cases / orchestration"""
from datetime import datetime
from typing import Dict, Optional

from ..ports import IBrowserPort, IStoragePort, IConfigPort
from ..domain.models import ScrapeResult
from ..domain.services import GradeAnalyzer, HomeworkTracker, CalendarAnalyzer, ChildReportGenerator


class ScrapeChildUseCase:
    """Use case: Scrape data for a child"""
    
    def __init__(self, browser: IBrowserPort, storage: IStoragePort, config: IConfigPort):
        self.browser = browser
        self.storage = storage
        self.config = config
        self.report_generator = ChildReportGenerator()
    
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
        
        # Update memory with analysis
        self._update_memory(child.name, result)
        
        return {
            "status": "success",
            "child_name": child.name,
            "stats": result.stats,
            "mode": "full" if force_full or not last_scrape else f"delta since {last_scrape}",
            "has_urgent": result.has_urgent_items
        }
    
    def _update_memory(self, child_name: str, result: ScrapeResult) -> None:
        memory = self.storage.load_memory(child_name)
        
        # Update grade history
        grade_history = memory.setdefault("grade_history", {})
        for grade in result.grades:
            subj = grade.subject
            if subj not in grade_history:
                grade_history[subj] = []
            
            entry = {
                "grade": grade.grade,
                "date": grade.date,
                "category": grade.category,
                "weight": grade.weight
            }
            if entry not in grade_history[subj]:
                grade_history[subj].append(entry)
        
        # Add summary from domain service
        memory["last_summary"] = self.report_generator.generate_summary(result)
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
        
        if not child.has_credentials:
            return {
                "status": "error",
                "message": f"No credentials configured for {child.name} in config.yaml"
            }
        
        success = await self.browser.login(child)
        
        if success:
            return {"status": "success", "message": f"Login successful for {child.name}"}
        else:
            return {"status": "error", "message": f"Login failed for {child.name}"}


class AnalyzeGradesUseCase:
    """Use case: Analyze grades for a child"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.analyzer = GradeAnalyzer()
    
    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Extract grades
        from ..domain.models import Grade
        all_grades = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for g in raw.get('grades', []):
                all_grades.append(Grade(
                    subject=g.get('subject', ''),
                    grade=g.get('grade', ''),
                    date=g.get('date'),
                    category=g.get('category', ''),
                    weight=g.get('weight', ''),
                    teacher=g.get('teacher', '')
                ))
        
        # Analyze by subject
        subjects = set(g.subject for g in all_grades if not g.is_semester_grade)
        analysis = {}
        
        for subject in subjects:
            avg = self.analyzer.calculate_average(all_grades, subject)
            trend = self.analyzer.get_trend(all_grades, subject)
            subject_grades = [g for g in all_grades if g.subject == subject and not g.is_semester_grade]
            
            analysis[subject] = {
                "average": avg,
                "trend": trend,
                "count": len(subject_grades),
                "recent": [g.grade for g in sorted(subject_grades, key=lambda x: x.date or '')[-5:]]
            }
        
        return {
            "total_grades": len(all_grades),
            "overall_average": self.analyzer.calculate_average(all_grades),
            "at_risk": self.analyzer.get_subjects_at_risk(all_grades),
            "by_subject": analysis
        }


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
        self.analyzer = CalendarAnalyzer()
    
    def execute(self, child_name: str, days_ahead: int = 14) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        from ..domain.models import CalendarEvent
        all_events = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for e in raw.get('calendar', []):
                all_events.append(CalendarEvent(
                    date=e.get('date', ''),
                    title=e.get('title', ''),
                    category=e.get('category', '')
                ))
        
        upcoming = self.analyzer.get_upcoming(all_events, days_ahead)
        tests = self.analyzer.get_upcoming_tests(all_events, days_ahead)
        
        return {
            "total_events": len(all_events),
            "upcoming": [{"date": e.date, "title": e.title} for e in upcoming],
            "upcoming_tests": [{"date": e.date, "title": e.title} for e in tests]
        }
