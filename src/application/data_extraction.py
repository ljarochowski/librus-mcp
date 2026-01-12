"""Data extraction service - converts raw data to domain objects"""
from typing import Dict, List
from ..domain.models import Grade, Homework, Message, CalendarEvent


class DataExtractionService:
    """Application service for converting raw data to domain objects"""
    
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
    
    def convert_raw_to_homework(self, raw_data: Dict) -> List[Homework]:
        """Convert raw data to Homework domain objects"""
        all_homework = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for h in raw.get('homework', []):
                all_homework.append(Homework(
                    subject=h.get('subject', ''),
                    title=h.get('title', ''),
                    date_added=h.get('date_added') or h.get('date', ''),
                    date_due=h.get('date_due', ''),
                    teacher=h.get('teacher', ''),
                    category=h.get('category', '')
                ))
        return all_homework
    
    def convert_raw_to_messages(self, raw_data: Dict) -> List[Message]:
        """Convert raw data to Message domain objects"""
        all_messages = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for m in raw.get('messages', []):
                all_messages.append(Message(
                    date=m.get('date', ''),
                    sender=m.get('sender', ''),
                    subject=m.get('title', ''),
                    content=m.get('content', ''),
                    is_new=m.get('is_new', False)
                ))
        return all_messages
    
    def convert_raw_to_calendar(self, raw_data: Dict) -> List[CalendarEvent]:
        """Convert raw data to CalendarEvent domain objects"""
        all_calendar = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for e in raw.get('calendar', []):
                all_calendar.append(CalendarEvent(
                    date=e.get('date', ''),
                    title=e.get('title', ''),
                    category=e.get('category', '')
                ))
        return all_calendar
    
    def extract_raw_grades_from_data(self, raw_data: Dict) -> List[Dict]:
        """Extract raw grades from data structure"""
        all_grades = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            all_grades.extend(raw.get('grades', []))
        return all_grades
    
    def extract_data_by_type(self, raw_data: Dict, data_type: str) -> List[Dict]:
        """Extract specific data type from raw data"""
        items = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            items.extend(raw.get(data_type, []))
        return items
    
    def extract_all_messages_from_data(self, raw_data: Dict) -> List[Dict]:
        """Extract all messages from raw data"""
        return self.extract_data_by_type(raw_data, 'messages')
    
    def extract_grades_for_teacher_mapping(self, raw_data: Dict) -> List[Dict]:
        """Extract grades for teacher mapping"""
        return self.extract_raw_grades_from_data(raw_data)
    
    def extract_calendar_events_from_data(self, raw_data: Dict) -> List[CalendarEvent]:
        """Extract and convert calendar events from raw data"""
        all_events = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            for e in raw.get('calendar', []):
                all_events.append(CalendarEvent(
                    date=e.get('date', ''),
                    title=e.get('title', ''),
                    category=e.get('category', '')
                ))
        return all_events
