"""Application layer - use cases / orchestration"""
from datetime import datetime
from typing import Dict, Optional

from ..ports import IBrowserPort, IStoragePort, IConfigPort
from ..domain.models import ScrapeResult, Grade
from ..domain.services import (
    GradeAnalyzer, HomeworkTracker, CalendarAnalyzer, ChildReportGenerator, 
    GradeHistoryService, SessionService, ScrapeResultService, GradeDataService,
    TeacherMappingService, UrgentMattersService, ActivityDeltaService, MessageAnalysisService
)


class ScrapeChildUseCase:
    """Use case: Scrape data for a child"""
    
    def __init__(self, browser: IBrowserPort, storage: IStoragePort, config: IConfigPort):
        self.browser = browser
        self.storage = storage
        self.config = config
        self.report_generator = ChildReportGenerator()
        self.grade_history_service = GradeHistoryService()
        self.session_service = SessionService()
        self.scrape_result_service = ScrapeResultService()
    
    async def execute(self, child_name: str, force_full: bool = False) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"status": "error", "message": f"Child not found: {child_name}"}
        
        # Check session using domain service
        is_session_valid = await self.browser.is_session_valid(child)
        session_check = self.session_service.should_scrape(is_session_valid, force_full)
        
        if not session_check["should_proceed"]:
            return {
                "status": session_check["reason"],
                "child_name": child.name,
                "message": session_check["message"]
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
        
        # Determine mode using domain service
        mode = self.scrape_result_service.determine_scrape_mode(force_full, last_scrape)
        
        return {
            "status": "success",
            "child_name": child.name,
            "stats": result.stats,
            "mode": mode,
            "has_urgent": result.has_urgent_items
        }
    
    def _update_memory(self, child_name: str, result: ScrapeResult) -> None:
        memory = self.storage.load_memory(child_name)
        
        # Update grade history using domain service
        existing_history = memory.setdefault("grade_history", {})
        memory["grade_history"] = self.grade_history_service.update_grade_history(existing_history, result.grades)
        
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


class GetSemesterGradesSummaryUseCase:
    """Get semester grades summary with deduplication"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str, semester: int = 1, year: str = None) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=12)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Convert raw data to domain objects
        all_grades = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            grades_data = raw.get('grades', [])
            
            for grade_data in grades_data:
                grade = Grade(
                    subject=grade_data.get('subject', ''),
                    grade=grade_data.get('grade', ''),
                    date=grade_data.get('date'),
                    category=grade_data.get('category', ''),
                    weight=grade_data.get('weight', ''),
                    teacher=grade_data.get('teacher', ''),
                    comment=grade_data.get('comment', '')
                )
                all_grades.append(grade)
        
        # Use domain services for business logic
        analyzer = GradeAnalyzer()
        deduplicated_grades = analyzer.deduplicate_semester_grades(all_grades)
        
        # Convert back to response format
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
        
        grades_dict.sort(key=lambda x: x.get('subject', ''))
        unique_subjects = len(set(g.subject for g in deduplicated_grades))
        
        return {
            "child_name": child.name,
            "semester": semester,
            "year": year,
            "total_semester_grades": len(grades_dict),
            "unique_subjects": unique_subjects,
            "grades": grades_dict
        }

class GetGradeDetailsByDateUseCase:
    """Get detailed grades for specific date range"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str, date_from: str, date_to: str, include_semester: bool) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=6)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        grades = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            month_grades = raw.get('grades', [])
            
            for grade in month_grades:
                grade_date = grade.get('date', '')
                if date_from <= grade_date <= date_to:
                    # Filter semester grades if requested
                    category = grade.get('category', '').lower()
                    is_semester = any(x in category for x in ['śródroczn', 'roczn', 'końcow', 'przewidywan'])
                    
                    if include_semester or not is_semester:
                        grades.append(grade)
        
        # Sort by date (newest first)
        grades.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return {
            "date_range": f"{date_from} to {date_to}",
            "total_grades": len(grades),
            "include_semester_grades": include_semester,
            "grades": grades
        }


class GetTeacherSubjectMappingUseCase:
    """Get mapping of teachers to subjects"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=6)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        teacher_subject = {}
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            grades = raw.get('grades', [])
            
            for grade in grades:
                teacher = grade.get('teacher', '').strip()
                subject = grade.get('subject', '').strip()
                if teacher and subject:
                    teacher_subject[teacher] = subject
        
        return {
            "child_name": child.name,
            "teacher_subject_mapping": teacher_subject,
            "total_mappings": len(teacher_subject)
        }


class AnalyzeUrgentMattersUseCase:
    """Analyze and prioritize urgent matters"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=1)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        from datetime import datetime, timedelta
        today = datetime.now().date()
        
        critical_0_2_days = []
        important_3_7_days = []
        upcoming_8_14_days = []
        
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            
            # Check homework deadlines
            for hw in raw.get('homework', []):
                due_date_str = hw.get('due_date', '')
                if due_date_str:
                    try:
                        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                        days_until = (due_date - today).days
                        
                        item = {
                            "type": "homework",
                            "subject": hw.get('subject', ''),
                            "due": due_date_str,
                            "title": hw.get('title', ''),
                            "days_until": days_until
                        }
                        
                        if 0 <= days_until <= 2:
                            critical_0_2_days.append(item)
                        elif 3 <= days_until <= 7:
                            important_3_7_days.append(item)
                        elif 8 <= days_until <= 14:
                            upcoming_8_14_days.append(item)
                    except:
                        pass
            
            # Check messages for payment deadlines
            for msg in raw.get('messages', []):
                content = (msg.get('content', '') + ' ' + msg.get('title', '')).lower()
                
                if any(keyword in content for keyword in ['płatność', 'wpłata', 'opłata', 'składka', 'payment']):
                    import re
                    
                    # Look for dates and amounts
                    date_patterns = [
                        r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})',
                        r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',
                    ]
                    
                    amount_patterns = [
                        r'(\d+)\s*zł',
                        r'(\d+)\s*PLN',
                        r'(\d+)[,.](\d{2})\s*zł',
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
                                "amount": found_amount or "unknown",
                                "due": found_date,
                                "title": msg.get('title', ''),
                                "sender": msg.get('sender', ''),
                                "days_until": days_until
                            }
                            
                            if 0 <= days_until <= 2:
                                critical_0_2_days.append(item)
                            elif 3 <= days_until <= 7:
                                important_3_7_days.append(item)
                            elif 8 <= days_until <= 14:
                                upcoming_8_14_days.append(item)
                        except:
                            pass
            
            # Check upcoming tests
            for event in raw.get('calendar', []):
                event_date_str = event.get('date', '')
                if event_date_str and 'sprawdzian' in event.get('title', '').lower():
                    try:
                        event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                        days_until = (event_date - today).days
                        
                        item = {
                            "type": "test",
                            "subject": event.get('subject', ''),
                            "date": event_date_str,
                            "title": event.get('title', ''),
                            "days_until": days_until
                        }
                        
                        if 0 <= days_until <= 2:
                            critical_0_2_days.append(item)
                        elif 3 <= days_until <= 7:
                            important_3_7_days.append(item)
                        elif 8 <= days_until <= 14:
                            upcoming_8_14_days.append(item)
                    except:
                        pass
        
        return {
            "child_name": child.name,
            "analysis_date": today.strftime('%Y-%m-%d'),
            "critical_0_2_days": critical_0_2_days,
            "important_3_7_days": important_3_7_days,
            "upcoming_8_14_days": upcoming_8_14_days,
            "summary": {
                "critical_count": len(critical_0_2_days),
                "important_count": len(important_3_7_days),
                "upcoming_count": len(upcoming_8_14_days)
            }
        }

class GetRecentActivityDeltaUseCase:
    """Get summary of recent changes since date"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str, since_date: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        new_grades = []
        new_homework = []
        new_messages = []
        upcoming_tests = []
        
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            
            # New grades
            for grade in raw.get('grades', []):
                if grade.get('date', '') >= since_date:
                    new_grades.append(grade)
            
            # New homework
            for hw in raw.get('homework', []):
                if hw.get('date', '') >= since_date:
                    new_homework.append(hw)
            
            # New messages
            for msg in raw.get('messages', []):
                if msg.get('date', '') >= since_date:
                    new_messages.append(msg)
            
            # Upcoming tests (next 7 days)
            from datetime import datetime, timedelta
            today = datetime.now().date()
            week_ahead = (today + timedelta(days=7)).strftime('%Y-%m-%d')
            
            for event in raw.get('calendar', []):
                event_date = event.get('date', '')
                if since_date <= event_date <= week_ahead and 'sprawdzian' in event.get('title', '').lower():
                    upcoming_tests.append(event)
        
        return {
            "child_name": child.name,
            "since_date": since_date,
            "new_grades": len(new_grades),
            "new_homework": len(new_homework),
            "new_messages": len(new_messages),
            "upcoming_tests_this_week": len(upcoming_tests),
            "details": {
                "grades": new_grades[-10:],  # Last 10
                "homework": new_homework,
                "messages": new_messages[-5:],  # Last 5
                "tests": upcoming_tests
            }
        }

class GeneratePdfReportUseCase:
    """Generate PDF report from markdown content"""
    
    def execute(self, content: str, output_path: str) -> str:
        try:
            import markdown
            from weasyprint import HTML, CSS
            from pathlib import Path
            import os
            
            # Expand ~ in path
            output_path = os.path.expanduser(output_path)
            
            # Convert markdown to HTML
            html_content = markdown.markdown(content)
            
            # Add Dumbledore signature
            signature_path = Path(__file__).parent.parent.parent / "assets" / "dumbledore_signature.png"
            if signature_path.exists():
                html_content += f'<br><br><img src="{signature_path}" style="width: 200px; height: auto;">'
            
            # CSS for Polish fonts and styling
            css = CSS(string="""
                @page { margin: 2cm; }
                body { font-family: 'Times New Roman', serif; font-size: 12pt; line-height: 1.6; }
                h1, h2, h3 { color: #2c3e50; }
                strong { font-weight: bold; }
                em { font-style: italic; }
            """)
            
            # Generate PDF
            HTML(string=html_content).write_pdf(output_path, stylesheets=[css])
            
            return f"✅ PDF generated: {output_path}"
            
        except ImportError as e:
            missing_lib = str(e).split("'")[1] if "'" in str(e) else "unknown"
            return f"❌ Missing Python dependencies for PDF generation: {e}.\n\nInstall with: pip install markdown weasyprint"
        
        except Exception as e:
            error_msg = str(e)
            if "libpango" in error_msg or "pango" in error_msg:
                return f"""❌ PDF generation failed: Missing system libraries.

macOS: brew install pango
Ubuntu/Debian: sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
CentOS/RHEL: sudo yum install pango harfbuzz

For detailed installation instructions, see:
https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation

Error: {error_msg}"""
            else:
                return f"❌ PDF generation failed: {error_msg}"


class GetMessagesWithContentUseCase:
    """Get messages with full content and response detection"""
    
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
        
        messages = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            month_messages = raw.get('messages', [])
            messages.extend(month_messages)
        
        # Sort by date (newest first)
        messages.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Enhance with full content where available
        enhanced_messages = []
        for msg in messages:
            enhanced_msg = msg.copy()
            # If content is empty but we have title, use title as content
            if not enhanced_msg.get('content') and enhanced_msg.get('title'):
                enhanced_msg['content'] = enhanced_msg['title']
            enhanced_messages.append(enhanced_msg)
        
        # Check for messages requiring response
        requiring_response = []
        for msg in enhanced_messages:
            content = (msg.get('content', '') + ' ' + msg.get('title', '')).lower()
            if any(keyword in content for keyword in ['proszę o odpowiedź', 'odpowiedz', 'potwierdź', 'zgoda', 'płatność']):
                requiring_response.append(msg)
        
        return {
            "total_messages": len(enhanced_messages),
            "messages": enhanced_messages[:50],  # Last 50 messages
            "requiring_response_count": len(requiring_response),
            "requiring_response": requiring_response
        }


class GetDataSummaryUseCase:
    """Get generic data summary"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self, child_name: str, data_type: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        items = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            items.extend(raw.get(data_type, []))
        
        return {"total": len(items), "items": items[-20:]}


class ListChildrenUseCase:
    """List all configured children with their status"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
    
    def execute(self) -> str:
        children = self.config.get_children()
        lines = ["📚 Configured children:\n"]
        for child in children:
            state = self.storage.load_state(child.name)
            last_scan = state.get("last_scrape_iso", "Never")
            aliases = f" (aliases: {', '.join(child.aliases)})" if child.aliases else ""
            lines.append(f"- **{child.name}**{aliases}\n  Last scan: {last_scan}")
        return "\n".join(lines)
