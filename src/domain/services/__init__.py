"""Domain services - business logic that doesn't belong to a single entity"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from ..models import Grade, Homework, CalendarEvent, ScrapeResult


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
    """Handles grade data processing and analysis"""
    
    def __init__(self):
        self.analyzer = GradeAnalyzer()
    
    def convert_raw_to_grades(self, raw_data: Dict) -> List[Grade]:
        """Convert raw data to Grade domain objects"""
        all_grades = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for g in raw.get('grades', []):
                all_grades.append(Grade(
                    subject=g.get('subject', ''),
                    grade=g.get('grade', ''),
                    date=g.get('date'),
                    category=g.get('category', ''),
                    weight=g.get('weight', ''),
                    teacher=g.get('teacher', ''),
                    comment=g.get('comment', '')
                ))
        return all_grades
    
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
    
    def separate_current_and_semester_grades(self, raw_grades: List[Dict]) -> Dict:
        """Separate current grades from semester grades"""
        current = []
        semester = {}
        
        for g in raw_grades:
            cat = g.get('category', '').lower()
            subj = g.get('subject', 'Unknown')
            
            if any(x in cat for x in ['śródroczn', 'roczn', 'końcow', 'przewidywan']):
                if subj not in semester:
                    semester[subj] = []
                semester[subj].append(g)
            else:
                current.append(g)
        
        # Group current grades by subject
        by_subject = {}
        for g in current:
            subj = g.get('subject', 'Unknown')
            if subj not in by_subject:
                by_subject[subj] = []
            by_subject[subj].append(g)
        
        return {
            "current": current,
            "semester": semester,
            "by_subject": by_subject
        }
    
    def filter_grades_by_date(self, raw_grades: List[Dict], date_from: str, date_to: str, include_semester: bool) -> List[Dict]:
        """Filter grades by date range"""
        filtered = []
        
        for grade in raw_grades:
            grade_date = grade.get('date', '')
            if date_from <= grade_date <= date_to:
                category = grade.get('category', '').lower()
                is_semester = any(x in category for x in ['śródroczn', 'roczn', 'końcow', 'przewidywan'])
                
                if include_semester or not is_semester:
                    filtered.append(grade)
        
        return sorted(filtered, key=lambda x: x.get('date', ''), reverse=True)


class TeacherMappingService:
    """Handles teacher to subject mapping"""
    
    def build_teacher_subject_mapping(self, raw_data: Dict) -> Dict:
        """Build mapping of teachers to subjects"""
        teacher_subject = {}
        
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            grades = raw.get('grades', [])
            
            for grade in grades:
                teacher = grade.get('teacher', '').strip()
                subject = grade.get('subject', '').strip()
                if teacher and subject:
                    teacher_subject[teacher] = subject
        
        return teacher_subject


class UrgentMattersService:
    """Analyzes urgent matters like payments and deadlines"""
    
    def analyze_urgent_matters(self, raw_data: Dict) -> Dict:
        """Analyze urgent matters from raw data"""
        from datetime import datetime, timedelta
        import re
        
        today = datetime.now().date()
        critical_0_2_days = []
        important_3_7_days = []
        upcoming_8_14_days = []
        
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            
            # Process homework deadlines
            self._process_homework_deadlines(raw.get('homework', []), today, critical_0_2_days, important_3_7_days, upcoming_8_14_days)
            
            # Process payment messages
            self._process_payment_messages(raw.get('messages', []), today, critical_0_2_days, important_3_7_days, upcoming_8_14_days)
            
            # Process upcoming tests
            self._process_upcoming_tests(raw.get('calendar', []), today, critical_0_2_days, important_3_7_days, upcoming_8_14_days)
        
        return {
            "critical_0_2_days": critical_0_2_days,
            "important_3_7_days": important_3_7_days,
            "upcoming_8_14_days": upcoming_8_14_days,
            "total_urgent": len(critical_0_2_days) + len(important_3_7_days) + len(upcoming_8_14_days)
        }
    
    def _process_homework_deadlines(self, homework: List[Dict], today, critical, important, upcoming):
        """Process homework deadlines"""
        from datetime import datetime
        
        for hw in homework:
            due_date_str = hw.get('due_date', '')
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                    days_until = (due_date - today).days
                    
                    item = {
                        "type": "homework",
                        "title": hw.get('title', 'Zadanie domowe'),
                        "subject": hw.get('subject', ''),
                        "due": due_date_str,
                        "days_until": days_until
                    }
                    
                    self._categorize_by_urgency(item, days_until, critical, important, upcoming)
                except:
                    pass
    
    def _process_payment_messages(self, messages: List[Dict], today, critical, important, upcoming):
        """Process payment messages for deadlines"""
        import re
        from datetime import datetime
        
        for msg in messages:
            content = (msg.get('content', '') + ' ' + msg.get('title', '')).lower()
            
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
                            "title": msg.get('title', 'Płatność'),
                            "sender": msg.get('sender', ''),
                            "days_until": days_until
                        }
                        
                        self._categorize_by_urgency(item, days_until, critical, important, upcoming)
                    except:
                        pass
    
    def _process_upcoming_tests(self, calendar: List[Dict], today, critical, important, upcoming):
        """Process upcoming tests from calendar"""
        from datetime import datetime
        
        for event in calendar:
            event_date_str = event.get('date', '')
            if event_date_str and 'sprawdzian' in event.get('title', '').lower():
                try:
                    event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                    days_until = (event_date - today).days
                    
                    item = {
                        "type": "test",
                        "title": event.get('title', 'Sprawdzian'),
                        "date": event_date_str,
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
    """Handles activity delta analysis"""
    
    def get_activity_since_date(self, raw_data: Dict, since_date: str) -> Dict:
        """Get activity since specific date"""
        from datetime import datetime, timedelta
        
        new_grades = []
        new_homework = []
        new_messages = []
        upcoming_tests = []
        
        today = datetime.now().date()
        week_ahead = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            
            # Filter by date
            for grade in raw.get('grades', []):
                if grade.get('date', '') >= since_date:
                    new_grades.append(grade)
            
            for hw in raw.get('homework', []):
                if hw.get('date', '') >= since_date:
                    new_homework.append(hw)
            
            for msg in raw.get('messages', []):
                if msg.get('date', '') >= since_date:
                    new_messages.append(msg)
            
            for event in raw.get('calendar', []):
                event_date = event.get('date', '')
                if since_date <= event_date <= week_ahead and 'sprawdzian' in event.get('title', '').lower():
                    upcoming_tests.append(event)
        
        return {
            "new_grades": new_grades,
            "new_homework": new_homework,
            "new_messages": new_messages,
            "upcoming_tests": upcoming_tests
        }


class MessageAnalysisService:
    """Handles message content analysis"""
    
    def analyze_messages(self, raw_messages: List[Dict]) -> Dict:
        """Analyze messages for content and response requirements"""
        # Sort by date (newest first)
        messages = sorted(raw_messages, key=lambda x: x.get('date', ''), reverse=True)
        
        # Enhance with full content
        enhanced_messages = []
        for msg in messages:
            enhanced_msg = msg.copy()
            if not enhanced_msg.get('content') and enhanced_msg.get('title'):
                enhanced_msg['content'] = enhanced_msg['title']
            enhanced_messages.append(enhanced_msg)
        
        # Find messages requiring response
        requiring_response = []
        for msg in enhanced_messages:
            content = (msg.get('content', '') + ' ' + msg.get('title', '')).lower()
            if any(keyword in content for keyword in ['proszę o odpowiedź', 'odpowiedz', 'potwierdź', 'zgoda', 'płatność']):
                requiring_response.append(msg)
        
        return {
            "enhanced_messages": enhanced_messages,
            "requiring_response": requiring_response
        }


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
