"""Domain models - core business entities"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class GradeCategory(Enum):
    REGULAR = "regular"
    SEMESTER = "semester"
    PREDICTED = "predicted"
    FINAL = "final"


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
        cat = self.category.lower()
        return any(x in cat for x in ['śródroczn', 'roczn', 'końcow', 'przewidywan'])
    
    @property
    def numeric_value(self) -> Optional[float]:
        """Convert grade to numeric value for averaging"""
        g = self.grade.strip()
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


@dataclass
class Message:
    date: str
    sender: str
    subject: str
    content: str
    is_new: bool = False


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
