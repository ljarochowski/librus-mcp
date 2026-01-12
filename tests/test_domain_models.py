"""Tests for domain models"""
import pytest
from src.domain.models import (
    Grade, GradeValue, SubjectName, Homework, CalendarEvent, 
    Message, Remark, Child, ScrapeResult
)
from datetime import datetime, timedelta


class TestGradeValue:
    def test_numeric_integer(self):
        assert GradeValue("5").numeric == 5.0
    
    def test_numeric_plus(self):
        assert GradeValue("4+").numeric == 4.5
    
    def test_numeric_minus(self):
        assert GradeValue("3-").numeric == 2.75
    
    def test_numeric_invalid(self):
        assert GradeValue("nb").numeric is None
    
    def test_equality(self):
        assert GradeValue("5") == GradeValue("5")
        assert GradeValue("5") == "5"


class TestSubjectName:
    def test_normalized(self):
        assert SubjectName("Język Polski").normalized == "język_polski"
    
    def test_equality(self):
        assert SubjectName("Matematyka") == SubjectName("matematyka")
        assert SubjectName("Język Polski") == "język_polski"
    
    def test_hash(self):
        s = {SubjectName("Math"), SubjectName("math")}
        assert len(s) == 1


class TestGrade:
    def test_is_semester_grade(self):
        g1 = Grade("Math", "5", "2024-01-01", "ocena śródroczna")
        g2 = Grade("Math", "5", "2024-01-01", "kartkówka")
        assert g1.is_semester_grade is True
        assert g2.is_semester_grade is False
    
    def test_numeric_value(self):
        g = Grade("Math", "4+", "2024-01-01", "test")
        assert g.numeric_value == 4.5


class TestHomework:
    def test_is_overdue(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        h1 = Homework("Math", "Task", "2024-01-01", yesterday)
        h2 = Homework("Math", "Task", "2024-01-01", tomorrow)
        
        assert h1.is_overdue is True
        assert h2.is_overdue is False
    
    def test_days_until_due(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        h = Homework("Math", "Task", "2024-01-01", tomorrow)
        assert h.days_until_due == 0 or h.days_until_due == 1


class TestCalendarEvent:
    def test_is_test(self):
        e1 = CalendarEvent("2024-01-01", "Sprawdzian z matematyki")
        e2 = CalendarEvent("2024-01-01", "Wycieczka")
        
        assert e1.is_test is True
        assert e2.is_test is False


class TestChild:
    def test_matches_name(self):
        c = Child("Jakub", aliases=["Kuba", "Kubuś"])
        
        assert c.matches_name("Jakub") is True
        assert c.matches_name("jakub") is True
        assert c.matches_name("Kuba") is True
        assert c.matches_name("Jan") is False
    
    def test_has_credentials(self):
        c1 = Child("Test", username="user", password="pass")
        c2 = Child("Test")
        
        assert c1.has_credentials is True
        assert c2.has_credentials is False


class TestScrapeResult:
    def test_stats(self):
        r = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
            grades=[Grade("M", "5", None, "t")],
            homework=[Homework("M", "T", "", "")],
        )
        assert r.stats == {'grades': 1, 'homework': 1, 'calendar': 0, 'messages': 0, 'remarks': 0}
    
    def test_has_urgent_items_overdue_homework(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        r = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
            homework=[Homework("M", "T", "", yesterday)],
        )
        assert r.has_urgent_items is True
    
    def test_has_urgent_items_unread_message(self):
        r = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
            messages=[Message("2024-01-01", "Teacher", "Subject", "Content", is_new=True)],
        )
        assert r.has_urgent_items is True
    
    def test_has_urgent_items_upcoming_test(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        r = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
            calendar=[CalendarEvent(tomorrow, "Sprawdzian z matematyki")],
        )
        assert r.has_urgent_items is True
    
    def test_has_urgent_items_false(self):
        r = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
        )
        assert r.has_urgent_items is False


class TestMessage:
    def test_requires_response(self):
        m1 = Message("2024-01-01", "Teacher", "Proszę o odpowiedź", "Content")
        m2 = Message("2024-01-01", "Teacher", "Info", "Content")
        
        assert m1.requires_response is True
        assert m2.requires_response is False
