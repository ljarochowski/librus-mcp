"""Domain models - core business entities"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


# Value Objects

class GradeValue:
    """Value object for grade with numeric conversion"""
    
    def __init__(self, value: str):
        self._value = (value or "").strip()
    
    @property
    def raw(self) -> str:
        return self._value
    
    @property
    def numeric(self) -> Optional[float]:
        g = self._value
        if g.isdigit():
            return float(g)
        if g.endswith('+'):
            base = g[:-1]
            if base.isdigit():
                return float(base) + 0.5
        if g.endswith('-'):
            base = g[:-1]
            if base.isdigit():
                return float(base) - 0.25
        return None
    
    def __str__(self) -> str:
        return self._value
    
    def __eq__(self, other) -> bool:
        if isinstance(other, GradeValue):
            return self._value == other._value
        return self._value == other


class SubjectName:
    """Value object for subject name with normalization"""
    
    def __init__(self, name: str):
        self._name = name.strip()
    
    @property
    def raw(self) -> str:
        return self._name
    
    @property
    def normalized(self) -> str:
        return self._name.lower().replace(" ", "_")
    
    def __str__(self) -> str:
        return self._name
    
    def __eq__(self, other) -> bool:
        if isinstance(other, SubjectName):
            return self.normalized == other.normalized
        return self.normalized == str(other).lower().replace(" ", "_")
    
    def __hash__(self) -> int:
        return hash(self.normalized)


# Entities

@dataclass
class Grade:
    subject: str
    grade: str
    date: Optional[str]
    category: str
    weight: str = ""
    teacher: str = ""
    comment: str = ""
    
    @property
    def is_semester_grade(self) -> bool:
        """Check if this grade is a semester/final grade"""
        category = (self.category or '').lower()
        return any(x in category for x in ['śródroczn', 'roczn', 'końcow', 'przewidywan'])
    
    @property
    def numeric_value(self) -> Optional[float]:
        return GradeValue(self.grade).numeric
    
    @property
    def subject_name(self) -> SubjectName:
        return SubjectName(self.subject)


@dataclass
class Homework:
    subject: str
    title: str
    date_added: str
    date_due: str
    teacher: str = ""
    category: str = ""
    
    @property
    def is_overdue(self) -> bool:
        if not self.date_due:
            return False
        try:
            due = datetime.strptime(self.date_due, '%Y-%m-%d')
            return due < datetime.now()
        except:
            return False
    
    @property
    def days_until_due(self) -> Optional[int]:
        if not self.date_due:
            return None
        try:
            due = datetime.strptime(self.date_due, '%Y-%m-%d')
            return (due - datetime.now()).days
        except:
            return None


@dataclass
class CalendarEvent:
    date: str
    title: str
    category: str = ""
    
    @property
    def is_upcoming(self) -> bool:
        try:
            event_date = datetime.strptime(self.date, '%Y-%m-%d')
            return event_date >= datetime.now()
        except:
            return False
    
    @property
    def is_test(self) -> bool:
        keywords = ['sprawdzian', 'kartkówka', 'test', 'klasówka']
        return any(kw in self.title.lower() for kw in keywords)


@dataclass
class Message:
    date: str
    sender: str
    subject: str
    content: str
    is_new: bool = False
    
    @property
    def requires_response(self) -> bool:
        keywords = ['proszę o odpowiedź', 'proszę potwierdzić', 'proszę o kontakt']
        text = (self.subject + self.content).lower()
        return any(kw in text for kw in keywords)


@dataclass
class Remark:
    date: str
    teacher: str
    content: str
    is_positive: bool = False


@dataclass
class Child:
    name: str
    aliases: List[str] = field(default_factory=list)
    username: Optional[str] = None
    password: Optional[str] = None
    
    def matches_name(self, query: str) -> bool:
        query_lower = query.lower()
        if self.name.lower() == query_lower:
            return True
        return any(alias.lower() == query_lower for alias in self.aliases)
    
    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)


@dataclass
class ScrapeResult:
    child_name: str
    timestamp: datetime
    grades: List[Grade] = field(default_factory=list)
    homework: List[Homework] = field(default_factory=list)
    calendar: List[CalendarEvent] = field(default_factory=list)
    messages: List[Message] = field(default_factory=list)
    remarks: List[Remark] = field(default_factory=list)
    descriptive_grade: Optional[str] = None
    
    @property
    def stats(self) -> dict:
        return {
            'grades': len(self.grades),
            'homework': len(self.homework),
            'calendar': len(self.calendar),
            'messages': len(self.messages),
            'remarks': len(self.remarks)
        }
    
    @property
    def has_urgent_items(self) -> bool:
        """Check if there are items requiring immediate attention"""
        overdue_hw = any(h.is_overdue for h in self.homework)
        unread_msgs = any(m.is_new for m in self.messages)
        upcoming_tests = any(e.is_test and e.is_upcoming for e in self.calendar)
        return overdue_hw or unread_msgs or upcoming_tests
