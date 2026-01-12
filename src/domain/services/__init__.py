"""Domain services - business logic that doesn't belong to a single entity"""
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import re
from ..models import Grade, Homework, CalendarEvent, ScrapeResult, Message


# Grade trend constants
class GradeTrend:
    IMPROVING = "IMPROVING"
    DECLINING = "DECLINING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GradeHistoryService:
    """Manages grade history and deduplication"""
    
    def update_grade_history(self, existing_history: Dict, new_grades: List[Grade]) -> Dict:
        """Update grade history with new grades, avoiding duplicates"""
        grade_history = existing_history.copy()
        
        for grade in new_grades:
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
        
        return grade_history


class SessionService:
    """Handles session validation logic"""
    
    def should_scrape(self, is_session_valid: bool, force_full: bool) -> Dict:
        """Determine if scraping should proceed"""
        if not is_session_valid:
            return {
                "should_proceed": False,
                "reason": "session_expired",
                "message": "Session expired. Use manual_login to refresh."
            }
        return {"should_proceed": True}


class ScrapeResultService:
    """Handles scrape result formatting and mode determination"""
    
    def determine_scrape_mode(self, force_full: bool, last_scrape: str) -> str:
        """Determine scrape mode description"""
        if force_full or not last_scrape:
            return "full"
        return f"delta since {last_scrape}"


class GradeDataService:
    """Handles grade data processing and analysis - PURE DOMAIN"""
    
    def __init__(self):
        self.analyzer = GradeAnalyzer()
    
    def analyze_grades_by_subject(self, grades: List[Grade]) -> Dict:
        """Analyze grades grouped by subject"""
        subjects = set(g.subject for g in grades if not g.is_semester_grade)
        analysis = {}
        
        for subject in subjects:
            avg = self.analyzer.calculate_average(grades, subject)
            trend = self.analyzer.get_trend(grades, subject)
            subject_grades = [g for g in grades if g.subject == subject and not g.is_semester_grade]
            
            analysis[subject] = {
                "average": avg,
                "trend": trend,
                "count": len(subject_grades),
                "recent": [g.grade for g in sorted(subject_grades, key=lambda x: x.date or '')[-5:]]
            }
        
        return analysis
    
    def separate_current_and_semester_grades(self, grades: List[Grade]) -> Dict:
        """Separate current grades from semester grades"""
        current = []
        semester = {}
        
        for g in grades:
            if g.is_semester_grade:
                if g.subject not in semester:
                    semester[g.subject] = []
                semester[g.subject].append(g)
            else:
                current.append(g)
        
        # Group current grades by subject
        by_subject = {}
        for g in current:
            if g.subject not in by_subject:
                by_subject[g.subject] = []
            by_subject[g.subject].append(g)
        
        return {
            "current": current,
            "semester": semester,
            "by_subject": by_subject
        }
    
    def filter_grades_by_date(self, grades: List[Grade], date_from: str, date_to: str, include_semester: bool) -> List[Grade]:
        """Filter grades by date range"""
        filtered = []
        
        for grade in grades:
            if date_from <= (grade.date or '') <= date_to:
                if include_semester or not grade.is_semester_grade:
                    filtered.append(grade)
        
        return sorted(filtered, key=lambda x: x.date or '', reverse=True)


class TeacherMappingService:
    """Handles teacher to subject mapping - PURE DOMAIN"""
    
    def build_teacher_subject_mapping(self, grades: List[Grade]) -> Dict:
        """Build mapping of teachers to subjects from grade data"""
        teacher_subject = {}
        
        for grade in grades:
            if grade.teacher and grade.subject:
                teacher_subject[grade.teacher.strip()] = grade.subject.strip()
        
        return teacher_subject


class UrgentMattersService:
    """Analyzes urgent matters like payments and deadlines - PURE DOMAIN"""
    
    def analyze_urgent_matters(self, homework: List[Homework], messages: List[Message], calendar: List[CalendarEvent]) -> Dict:
        """Analyze urgent matters from structured data"""
        from datetime import datetime, timedelta
        import re
        
        today = datetime.now().date()
        critical_0_2_days = []
        important_3_7_days = []
        upcoming_8_14_days = []
        
        # Process homework deadlines
        self._process_homework_deadlines(homework, today, critical_0_2_days, important_3_7_days, upcoming_8_14_days)
        
        # Process payment messages
        self._process_payment_messages(messages, today, critical_0_2_days, important_3_7_days, upcoming_8_14_days)
        
        # Process upcoming tests
        self._process_upcoming_tests(calendar, today, critical_0_2_days, important_3_7_days, upcoming_8_14_days)
        
        return {
            "critical_0_2_days": critical_0_2_days,
            "important_3_7_days": important_3_7_days,
            "upcoming_8_14_days": upcoming_8_14_days,
            "total_urgent": len(critical_0_2_days) + len(important_3_7_days) + len(upcoming_8_14_days)
        }
    
    def _process_homework_deadlines(self, homework: List[Homework], today, critical, important, upcoming):
        """Process homework deadlines"""
        for hw in homework:
            if hw.date_due:
                try:
                    due_date = datetime.strptime(hw.date_due, '%Y-%m-%d').date()
                    days_until = (due_date - today).days
                    
                    item = {
                        "type": "homework",
                        "title": hw.title or 'Zadanie domowe',
                        "subject": hw.subject or '',
                        "due": hw.date_due,
                        "days_until": days_until
                    }
                    
                    self._categorize_by_urgency(item, days_until, critical, important, upcoming)
                except:
                    pass
    
    def _process_payment_messages(self, messages: List[Message], today, critical, important, upcoming):
        """Process payment messages for deadlines"""
        for msg in messages:
            content = (msg.content + ' ' + msg.subject).lower()
            
            if any(keyword in content for keyword in ['płatność', 'wpłata', 'opłata', 'składka', 'payment']):
                date_patterns = [
                    r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})',
                    r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})'
                ]
                amount_patterns = [
                    r'(\d+)[,.](\d{2})\s*z[łl]',
                    r'(\d+)\s*z[łl]'
                ]
                
                found_date = None
                found_amount = None
                
                for pattern in date_patterns:
                    match = re.search(pattern, content)
                    if match:
                        try:
                            if len(match.group(1)) == 4:
                                found_date = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                            else:
                                found_date = f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
                            break
                        except:
                            pass
                
                for pattern in amount_patterns:
                    match = re.search(pattern, content)
                    if match:
                        if len(match.groups()) == 2:
                            found_amount = f"{match.group(1)}.{match.group(2)} zł"
                        else:
                            found_amount = f"{match.group(1)} zł"
                        break
                
                if found_date:
                    try:
                        due_date = datetime.strptime(found_date, '%Y-%m-%d').date()
                        days_until = (due_date - today).days
                        
                        item = {
                            "type": "payment",
                            "amount": found_amount or "Nieznana kwota",
                            "due": found_date,
                            "title": msg.subject or 'Płatność',
                            "sender": msg.sender or '',
                            "days_until": days_until
                        }
                        
                        self._categorize_by_urgency(item, days_until, critical, important, upcoming)
                    except:
                        pass
    
    def _process_upcoming_tests(self, calendar: List[CalendarEvent], today, critical, important, upcoming):
        """Process upcoming tests from calendar"""
        for event in calendar:
            if event.is_test:
                try:
                    event_date = datetime.strptime(event.date, '%Y-%m-%d').date()
                    days_until = (event_date - today).days
                    
                    item = {
                        "type": "test",
                        "title": event.title,
                        "date": event.date,
                        "days_until": days_until
                    }
                    
                    self._categorize_by_urgency(item, days_until, critical, important, upcoming)
                except:
                    pass
    
    def _categorize_by_urgency(self, item: Dict, days_until: int, critical: List, important: List, upcoming: List):
        """Categorize item by urgency"""
        if 0 <= days_until <= 2:
            critical.append(item)
        elif 3 <= days_until <= 7:
            important.append(item)
        elif 8 <= days_until <= 14:
            upcoming.append(item)


class ActivityDeltaService:
    """Handles activity delta analysis - PURE DOMAIN"""
    
    def get_activity_since_date(self, grades: List[Grade], homework: List[Homework], messages: List[Message], calendar: List[CalendarEvent], since_date: str) -> Dict:
        """Get activity since specific date from structured data"""
        from datetime import datetime, timedelta
        
        new_grades = [g for g in grades if (g.date or '') >= since_date]
        new_homework = [h for h in homework if (h.date_added or '') >= since_date]
        new_messages = [m for m in messages if (m.date or '') >= since_date]
        
        # Upcoming tests (next 7 days)
        today = datetime.now().date()
        week_ahead = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        
        upcoming_tests = [
            e for e in calendar 
            if since_date <= (e.date or '') <= week_ahead 
            and e.is_test
        ]
        
        return {
            "new_grades": new_grades,
            "new_homework": new_homework,
            "new_messages": new_messages,
            "upcoming_tests": upcoming_tests
        }


class MessageAnalysisService:
    """Handles message content analysis - PURE DOMAIN"""
    
    def analyze_messages(self, messages: List[Message]) -> Dict:
        """Analyze messages for content and response requirements"""
        # Sort by date (newest first)
        sorted_messages = sorted(messages, key=lambda x: x.date or '', reverse=True)
        
        # Find messages requiring response
        requiring_response = [m for m in sorted_messages if m.requires_response]
        
        return {
            "enhanced_messages": [{"sender": m.sender, "subject": m.subject, "date": m.date, "content": m.content} for m in sorted_messages],
            "requiring_response": [{"sender": m.sender, "title": m.subject, "date": m.date} for m in requiring_response]
        }


class CalendarDataService:
    """Handles calendar data processing - PURE DOMAIN"""
    
    def __init__(self):
        self.calendar_analyzer = CalendarAnalyzer()
    
    def analyze_calendar_events(self, events: List, days_ahead: int) -> Dict:
        """Analyze calendar events for upcoming items"""
        upcoming = self.calendar_analyzer.get_upcoming(events, days_ahead)
        tests = self.calendar_analyzer.get_upcoming_tests(events, days_ahead)
        
        return {
            "total_events": len(events),
            "upcoming": [{"date": e.date, "title": e.title} for e in upcoming],
            "upcoming_tests": [{"date": e.date, "title": e.title} for e in tests]
        }


class ResponseFormattingService:
    """Handles response formatting and data presentation"""
    
    def format_semester_grades_response(self, deduplicated_grades: List[Grade], child_name: str, semester: int, year: str) -> Dict:
        """Format semester grades for response"""
        grades_dict = []
        for grade in deduplicated_grades:
            grades_dict.append({
                "subject": grade.subject,
                "grade": grade.grade,
                "date": grade.date,
                "category": grade.category,
                "weight": grade.weight,
                "teacher": grade.teacher,
                "comment": grade.comment
            })
        
        grades_dict.sort(key=lambda x: x['subject'])
        unique_subjects = len(set(g.subject for g in deduplicated_grades))
        
        return {
            "child_name": child_name,
            "semester": semester,
            "year": year,
            "total_semester_grades": len(grades_dict),
            "unique_subjects": unique_subjects,
            "grades": grades_dict
        }
    
    def format_children_list(self, children: List, storage) -> str:
        """Format children list for display"""
        lines = ["📚 Configured children:\n"]
        for child in children:
            state = storage.load_state(child.name)
            last_scan = state.get("last_scrape_iso", "Never")
            aliases = f" (aliases: {', '.join(child.aliases)})" if child.aliases else ""
            lines.append(f"- **{child.name}**{aliases}\n  Last scan: {last_scan}")
        return "\n".join(lines)


class GradeAnalyzer:
    """Analyzes grades and calculates trends"""
    
    def _avg(self, values: List[float]) -> Optional[float]:
        """Calculate average of numeric values"""
        if not values:
            return None
        return sum(values) / len(values)
    
    def calculate_average(self, grades: List[Grade], subject: Optional[str] = None) -> Optional[float]:
        """Calculate average for grades, optionally filtered by subject"""
        filtered = [g for g in grades if not g.is_semester_grade]
        if subject:
            filtered = [g for g in filtered if g.subject == subject]
        
        numeric = [g.numeric_value for g in filtered if g.numeric_value is not None]
        if not numeric:
            return None
        return round(sum(numeric) / len(numeric), 2)
    
    def calculate_average_by_subject(self, grades: List[Grade]) -> Dict[str, float]:
        """Calculate average for each subject"""
        subjects = set(g.subject for g in grades if not g.is_semester_grade and g.subject and g.subject.strip())
        result = {}
        for subject in subjects:
            avg = self.calculate_average(grades, subject)
            if avg is not None:
                result[subject] = avg
        return result
    
    def get_trend(self, grades: List[Grade], subject: str) -> str:
        """Calculate trend for a subject: IMPROVING, DECLINING, or STABLE"""
        subject_grades = [g for g in grades if g.subject == subject and not g.is_semester_grade]
        subject_grades = sorted(subject_grades, key=lambda g: g.date or '')
        
        if len(subject_grades) < 3:
            return GradeTrend.INSUFFICIENT_DATA
        
        recent = subject_grades[-3:]
        early = subject_grades[:3]
        
        recent_avg = self._avg([g.numeric_value for g in recent if g.numeric_value])
        early_avg = self._avg([g.numeric_value for g in early if g.numeric_value])
        
        if recent_avg is None or early_avg is None:
            return GradeTrend.INSUFFICIENT_DATA
        
        diff = recent_avg - early_avg
        if diff > 0.3:
            return GradeTrend.IMPROVING
        elif diff < -0.3:
            return GradeTrend.DECLINING
        return GradeTrend.STABLE
    
    def get_subjects_at_risk(self, grades: List[Grade], threshold: float = 2.5) -> List[str]:
        """Get subjects with average below threshold"""
        subjects = set(g.subject for g in grades if not g.is_semester_grade)
        at_risk = []
        
        for subject in subjects:
            subject_grades = [g for g in grades if g.subject == subject and not g.is_semester_grade]
            avg = self.calculate_average(subject_grades)
            if avg and avg < threshold:
                at_risk.append(subject)
        
        return at_risk
    
    def filter_semester_grades(self, grades: List[Grade]) -> List[Grade]:
        """Filter grades to only semester/final grades"""
        return [g for g in grades if g.is_semester_grade]
    
    def deduplicate_semester_grades(self, grades: List[Grade]) -> List[Grade]:
        """Remove duplicate semester grades using business logic"""
        # Build teacher-subject mapping from ALL grades (not just semester)
        teacher_subject = {}
        for grade in grades:
            teacher = (grade.teacher or '').strip()
            subject = (grade.subject or '').strip()
            if teacher and subject:
                teacher_subject[teacher] = subject
        
        # Filter to only semester grades
        semester_grades = self.filter_semester_grades(grades)
        
        # Enrich semester grades with mapped subjects
        enriched_grades = []
        for grade in semester_grades:
            subject = (grade.subject or '').strip()
            teacher = (grade.teacher or '').strip()
            
            # Map subject if missing
            if not subject and teacher in teacher_subject:
                subject = teacher_subject[teacher]
            
            if not subject:
                subject = 'Unknown'
            
            # Create enriched grade
            enriched_grade = Grade(
                subject=subject,
                grade=grade.grade,
                date=grade.date,
                category=grade.category,
                weight=grade.weight,
                teacher=grade.teacher,
                comment=grade.comment
            )
            enriched_grades.append(enriched_grade)
        
        # Now deduplicate using enriched subjects
        seen_grades = set()
        deduplicated = []
        
        for grade in enriched_grades:
            # Normalize category for deduplication
            category = (grade.category or '').lower()
            category_type = 'predicted' if 'przewidywan' in category else 'final'
            
            # Create unique key using enriched subject
            grade_value = (grade.grade or '').strip()
            dedup_key = (grade.subject, grade_value, category_type)
            
            if dedup_key not in seen_grades:
                seen_grades.add(dedup_key)
                deduplicated.append(grade)
        
        return deduplicated


class HomeworkTracker:
    """Tracks homework status and deadlines"""
    
    def get_overdue(self, homework: List[Homework]) -> List[Homework]:
        """Get overdue homework"""
        return [h for h in homework if h.is_overdue]
    
    def get_due_soon(self, homework: List[Homework], days: int = 3) -> List[Homework]:
        """Get homework due within N days"""
        now = datetime.now().date()
        cutoff = now + timedelta(days=days)
        
        due_soon = []
        for h in homework:
            if not h.date_due:
                continue
            try:
                due = datetime.strptime(h.date_due, '%Y-%m-%d').date()
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
        now = datetime.now().date()
        cutoff = now + timedelta(days=days)
        
        upcoming = []
        for e in events:
            try:
                event_date = datetime.strptime(e.date, '%Y-%m-%d').date()
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
