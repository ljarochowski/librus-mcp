"""Domain services - business logic that doesn't belong to a single entity"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from ..models import Grade, Homework, CalendarEvent, ScrapeResult


class GradeAnalyzer:
    """Analyzes grades and calculates trends"""
    
    def calculate_average(self, grades: List[Grade], subject: Optional[str] = None) -> Optional[float]:
        """Calculate average for grades, optionally filtered by subject"""
        filtered = [g for g in grades if not g.is_semester_grade]
        if subject:
            filtered = [g for g in filtered if g.subject == subject]
        
        numeric = [g.numeric_value for g in filtered if g.numeric_value is not None]
        if not numeric:
            return None
        return round(sum(numeric) / len(numeric), 2)
    
    def get_trend(self, grades: List[Grade], subject: str) -> str:
        """Calculate trend for a subject: IMPROVING, DECLINING, or STABLE"""
        subject_grades = [g for g in grades if g.subject == subject and not g.is_semester_grade]
        subject_grades = sorted(subject_grades, key=lambda g: g.date or '')
        
        if len(subject_grades) < 3:
            return "INSUFFICIENT_DATA"
        
        recent = subject_grades[-3:]
        early = subject_grades[:3]
        
        recent_avg = self._avg([g.numeric_value for g in recent if g.numeric_value])
        early_avg = self._avg([g.numeric_value for g in early if g.numeric_value])
        
        if recent_avg is None or early_avg is None:
            return "INSUFFICIENT_DATA"
        
        diff = recent_avg - early_avg
        if diff > 0.3:
            return "IMPROVING"
        elif diff < -0.3:
            return "DECLINING"
        return "STABLE"
    
    def get_subjects_at_risk(self, grades: List[Grade], threshold: float = 2.5) -> List[str]:
        """Get subjects with average below threshold"""
        subjects = set(g.subject for g in grades if not g.is_semester_grade)
        at_risk = []
        
        for subject in subjects:
            avg = self.calculate_average(grades, subject)
            if avg and avg < threshold:
                at_risk.append(subject)
        
        return at_risk
    
    def _avg(self, values: List[float]) -> Optional[float]:
        if not values:
            return None
        return sum(values) / len(values)


class HomeworkTracker:
    """Tracks homework status and deadlines"""
    
    def get_overdue(self, homework: List[Homework]) -> List[Homework]:
        """Get overdue homework"""
        return [h for h in homework if h.is_overdue]
    
    def get_due_soon(self, homework: List[Homework], days: int = 3) -> List[Homework]:
        """Get homework due within N days"""
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        
        due_soon = []
        for h in homework:
            if not h.date_due:
                continue
            try:
                due = datetime.strptime(h.date_due, '%Y-%m-%d')
                if now <= due <= cutoff:
                    due_soon.append(h)
            except:
                pass
        
        return sorted(due_soon, key=lambda h: h.date_due)


class CalendarAnalyzer:
    """Analyzes calendar for upcoming events"""
    
    def get_upcoming_tests(self, events: List[CalendarEvent], days: int = 14) -> List[CalendarEvent]:
        """Get upcoming tests/exams"""
        test_keywords = ['sprawdzian', 'kartkówka', 'test', 'klasówka', 'egzamin']
        upcoming = self._get_upcoming(events, days)
        
        return [e for e in upcoming 
                if any(kw in e.title.lower() for kw in test_keywords)]
    
    def get_upcoming(self, events: List[CalendarEvent], days: int = 14) -> List[CalendarEvent]:
        """Get all upcoming events"""
        return self._get_upcoming(events, days)
    
    def _get_upcoming(self, events: List[CalendarEvent], days: int) -> List[CalendarEvent]:
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        
        upcoming = []
        for e in events:
            try:
                event_date = datetime.strptime(e.date, '%Y-%m-%d')
                if now <= event_date <= cutoff:
                    upcoming.append(e)
            except:
                pass
        
        return sorted(upcoming, key=lambda e: e.date)


class ChildReportGenerator:
    """Generates reports for a child"""
    
    def __init__(self):
        self.grade_analyzer = GradeAnalyzer()
        self.homework_tracker = HomeworkTracker()
        self.calendar_analyzer = CalendarAnalyzer()
    
    def generate_summary(self, result: ScrapeResult) -> Dict:
        """Generate comprehensive summary from scrape result"""
        return {
            "child_name": result.child_name,
            "timestamp": result.timestamp.isoformat(),
            "grades": {
                "total": len(result.grades),
                "average": self.grade_analyzer.calculate_average(result.grades),
                "at_risk_subjects": self.grade_analyzer.get_subjects_at_risk(result.grades),
            },
            "homework": {
                "total": len(result.homework),
                "overdue": len(self.homework_tracker.get_overdue(result.homework)),
                "due_soon": len(self.homework_tracker.get_due_soon(result.homework)),
            },
            "calendar": {
                "upcoming_tests": len(self.calendar_analyzer.get_upcoming_tests(result.calendar)),
                "upcoming_events": len(self.calendar_analyzer.get_upcoming(result.calendar)),
            },
            "messages": {
                "total": len(result.messages),
                "unread": len([m for m in result.messages if m.is_new]),
            },
            "remarks": {
                "total": len(result.remarks),
                "positive": len([r for r in result.remarks if r.is_positive]),
                "negative": len([r for r in result.remarks if not r.is_positive]),
            }
        }
