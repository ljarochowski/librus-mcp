"""Data extraction service - converts raw data to domain objects"""
from typing import Dict, List, Callable, TypeVar
from ..domain.models import Grade, Homework, Message, CalendarEvent

T = TypeVar('T')

class DataExtractionService:
    """Application service for converting raw data to domain objects"""
    
    def _extract_from_raw_data(self, raw_data: Dict, data_type: str, converter: Callable[[Dict], T]) -> List[T]:
        """Generic extraction pattern - eliminates all duplication"""
        result = []
        for month_data in raw_data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            result.extend(converter(item) for item in raw.get(data_type, []))
        return result
    
    def convert_raw_to_grades(self, raw_data: Dict) -> List[Grade]:
        return self._extract_from_raw_data(raw_data, 'grades', lambda g: Grade(
            subject=g.get('subject', ''), grade=g.get('grade', ''), date=g.get('date'),
            category=g.get('category', ''), weight=g.get('weight', ''), 
            teacher=g.get('teacher', ''), comment=g.get('comment', '')
        ))
    
    def convert_raw_to_homework(self, raw_data: Dict) -> List[Homework]:
        return self._extract_from_raw_data(raw_data, 'homework', lambda h: Homework(
            subject=h.get('subject', ''), title=h.get('title', ''),
            date_added=h.get('date_added') or h.get('date', ''), date_due=h.get('date_due', ''),
            teacher=h.get('teacher', ''), category=h.get('category', '')
        ))
    
    def convert_raw_to_messages(self, raw_data: Dict) -> List[Message]:
        return self._extract_from_raw_data(raw_data, 'messages', lambda m: Message(
            date=m.get('date', ''), sender=m.get('sender', ''), subject=m.get('title', ''),
            content=m.get('content', ''), is_new=m.get('is_new', False)
        ))
    
    def convert_raw_to_calendar(self, raw_data: Dict) -> List[CalendarEvent]:
        return self._extract_from_raw_data(raw_data, 'calendar', lambda e: CalendarEvent(
            date=e.get('date', ''), title=e.get('title', ''), category=e.get('category', '')
        ))
    
    def extract_raw_grades_from_data(self, raw_data: Dict) -> List[Dict]:
        return self._extract_from_raw_data(raw_data, 'grades', lambda x: x)
    
    def extract_data_by_type(self, raw_data: Dict, data_type: str) -> List[Dict]:
        return self._extract_from_raw_data(raw_data, data_type, lambda x: x)
    
    def extract_all_messages_from_data(self, raw_data: Dict) -> List[Dict]:
        return self.extract_data_by_type(raw_data, 'messages')
    
    def extract_grades_for_teacher_mapping(self, raw_data: Dict) -> List[Dict]:
        return self.extract_raw_grades_from_data(raw_data)
    
    def extract_calendar_events_from_data(self, raw_data: Dict) -> List[CalendarEvent]:
        return self.convert_raw_to_calendar(raw_data)
