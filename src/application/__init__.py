"""Clean application layer - use cases with proper orchestration only"""
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
    """Use case: Scrape data for a child - CLEAN VERSION"""
    
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
        
        # Update memory using domain service
        self._update_memory(child.name, result)
        
        # Update state
        state["last_scrape_iso"] = result.timestamp.isoformat()
        self.storage.save_state(child.name, state)
        
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


class AnalyzeGradesUseCase:
    """Use case: Analyze grades and trends - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.grade_data_service = GradeDataService()

    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for all grade processing
        all_grades = self.grade_data_service.convert_raw_to_grades(data)
        analysis = self.grade_data_service.analyze_grades_by_subject(all_grades)
        
        return {
            "total_grades": len(all_grades),
            "overall_average": self.grade_data_service.analyzer.calculate_average(all_grades),
            "at_risk_subjects": self.grade_data_service.analyzer.get_subjects_at_risk(all_grades),
            "by_subject": analysis
        }


class GetGradesSummaryUseCase:
    """Use case: Get grades summary - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.grade_data_service = GradeDataService()

    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for grade separation
        all_grades = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            all_grades.extend(raw.get('grades', []))
        
        separated = self.grade_data_service.separate_current_and_semester_grades(all_grades)
        
        return {
            "total_current_grades": len(separated["current"]),
            "recent_grades": separated["current"][-10:],
            "semester_grades": separated["semester"],
            "subjects": separated["by_subject"]
        }


class GetSemesterGradesSummaryUseCase:
    """Use case: Get semester grades with deduplication - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.grade_data_service = GradeDataService()

    def execute(self, child_name: str, semester: int = 1, year: str = None) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=12)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for grade processing
        all_grades = self.grade_data_service.convert_raw_to_grades(data)
        deduplicated_grades = self.grade_data_service.analyzer.deduplicate_semester_grades(all_grades)
        
        # Convert to response format
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
    """Use case: Get grades by date range - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.grade_data_service = GradeDataService()
    
    def execute(self, child_name: str, date_from: str, date_to: str, include_semester: bool) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=6)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for filtering
        all_grades = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            all_grades.extend(raw.get('grades', []))
        
        filtered_grades = self.grade_data_service.filter_grades_by_date(all_grades, date_from, date_to, include_semester)
        
        return {
            "child_name": child.name,
            "date_from": date_from,
            "date_to": date_to,
            "include_semester": include_semester,
            "total_grades": len(filtered_grades),
            "grades": filtered_grades
        }


class GetTeacherSubjectMappingUseCase:
    """Use case: Get teacher to subject mapping - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.teacher_mapping_service = TeacherMappingService()

    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=6)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for mapping
        teacher_subject = self.teacher_mapping_service.build_teacher_subject_mapping(data)
        
        return {
            "child_name": child.name,
            "teacher_subject_mapping": teacher_subject,
            "total_mappings": len(teacher_subject)
        }


class AnalyzeUrgentMattersUseCase:
    """Use case: Analyze urgent matters - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.urgent_matters_service = UrgentMattersService()

    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=1)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for analysis
        analysis = self.urgent_matters_service.analyze_urgent_matters(data)
        
        return {
            "child_name": child.name,
            **analysis
        }


class GetRecentActivityDeltaUseCase:
    """Use case: Get recent activity delta - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.activity_delta_service = ActivityDeltaService()

    def execute(self, child_name: str, since_date: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Use domain service for activity analysis
        activity = self.activity_delta_service.get_activity_since_date(data, since_date)
        
        return {
            "child_name": child.name,
            "since_date": since_date,
            "new_grades": len(activity["new_grades"]),
            "new_homework": len(activity["new_homework"]),
            "new_messages": len(activity["new_messages"]),
            "upcoming_tests": len(activity["upcoming_tests"]),
            "details": activity
        }


class GetMessagesWithContentUseCase:
    """Use case: Get messages with content analysis - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.message_analysis_service = MessageAnalysisService()

    def execute(self, child_name: str) -> Dict:
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        # Collect all messages
        all_messages = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            all_messages.extend(raw.get('messages', []))
        
        # Use domain service for analysis
        analysis = self.message_analysis_service.analyze_messages(all_messages)
        
        return {
            "total_messages": len(analysis["enhanced_messages"]),
            "messages": analysis["enhanced_messages"][:50],
            "requiring_response_count": len(analysis["requiring_response"]),
            "requiring_response": analysis["requiring_response"]
        }


class LoginChildUseCase:
    """Use case: Login child - CLEAN VERSION"""
    
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


class GetCalendarEventsUseCase:
    """Use case: Get calendar events - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config
        self.calendar_analyzer = CalendarAnalyzer()

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
        
        upcoming = self.calendar_analyzer.get_upcoming(all_events, days_ahead)
        tests = self.calendar_analyzer.get_upcoming_tests(all_events, days_ahead)
        
        return {
            "total_events": len(all_events),
            "upcoming": [{"date": e.date, "title": e.title} for e in upcoming],
            "upcoming_tests": [{"date": e.date, "title": e.title} for e in tests]
        }


class GeneratePdfReportUseCase:
    """Use case: Generate PDF report - CLEAN VERSION"""
    
    def __init__(self, storage: IStoragePort, config: IConfigPort):
        self.storage = storage
        self.config = config

    def execute(self, content: str, output_path: str) -> str:
        """Generate PDF from markdown content"""
        try:
            from pathlib import Path
            import markdown
            from weasyprint import HTML, CSS
            
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

Error: {error_msg}"""
            return f"❌ PDF generation failed: {error_msg}"


class GetDataSummaryUseCase:
    """Use case: Get data summary - CLEAN VERSION"""
    
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
    """Use case: List children - CLEAN VERSION"""
    
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
