"""Tests for domain services"""
import pytest
from src.domain.models import Grade, Homework, CalendarEvent, ScrapeResult, Message, Remark
from src.domain.services import GradeAnalyzer, HomeworkTracker, CalendarAnalyzer
from datetime import datetime, timedelta


class TestGradeAnalyzer:
    def setup_method(self):
        self.analyzer = GradeAnalyzer()
    
    def test_calculate_average(self):
        grades = [
            Grade("Math", "5", "2024-01-01", "test"),
            Grade("Math", "4", "2024-01-02", "test"),
            Grade("Math", "3", "2024-01-03", "test"),
        ]
        assert self.analyzer.calculate_average(grades) == 4.0
    
    def test_calculate_average_by_subject(self):
        grades = [
            Grade("Math", "5", "2024-01-01", "test"),
            Grade("Physics", "3", "2024-01-02", "test"),
        ]
        assert self.analyzer.calculate_average(grades, "Math") == 5.0
    
    def test_calculate_average_excludes_semester(self):
        grades = [
            Grade("Math", "5", "2024-01-01", "test"),
            Grade("Math", "2", None, "ocena śródroczna"),
        ]
        assert self.analyzer.calculate_average(grades) == 5.0
    
    def test_calculate_average_empty(self):
        assert self.analyzer.calculate_average([]) is None
    
    def test_calculate_average_no_numeric(self):
        grades = [Grade("Math", "nb", "2024-01-01", "test")]
        assert self.analyzer.calculate_average(grades) is None
    
    def test_get_trend_improving(self):
        grades = [
            Grade("Math", "2", "2024-01-01", "t"),
            Grade("Math", "2", "2024-01-02", "t"),
            Grade("Math", "2", "2024-01-03", "t"),
            Grade("Math", "5", "2024-01-04", "t"),
            Grade("Math", "5", "2024-01-05", "t"),
            Grade("Math", "5", "2024-01-06", "t"),
        ]
        assert self.analyzer.get_trend(grades, "Math") == "IMPROVING"
    
    def test_get_trend_declining(self):
        grades = [
            Grade("Math", "5", "2024-01-01", "t"),
            Grade("Math", "5", "2024-01-02", "t"),
            Grade("Math", "5", "2024-01-03", "t"),
            Grade("Math", "2", "2024-01-04", "t"),
            Grade("Math", "2", "2024-01-05", "t"),
            Grade("Math", "2", "2024-01-06", "t"),
        ]
        assert self.analyzer.get_trend(grades, "Math") == "DECLINING"
    
    def test_get_trend_stable(self):
        grades = [
            Grade("Math", "4", "2024-01-01", "t"),
            Grade("Math", "4", "2024-01-02", "t"),
            Grade("Math", "4", "2024-01-03", "t"),
            Grade("Math", "4", "2024-01-04", "t"),
            Grade("Math", "4", "2024-01-05", "t"),
            Grade("Math", "4", "2024-01-06", "t"),
        ]
        assert self.analyzer.get_trend(grades, "Math") == "STABLE"
    
    def test_get_trend_insufficient_data(self):
        grades = [Grade("Math", "5", "2024-01-01", "t")]
        assert self.analyzer.get_trend(grades, "Math") == "INSUFFICIENT_DATA"
    
    def test_get_subjects_at_risk(self):
        grades = [
            Grade("Math", "2", "2024-01-01", "t"),
            Grade("Math", "2", "2024-01-02", "t"),
            Grade("Physics", "5", "2024-01-01", "t"),
        ]
        at_risk = self.analyzer.get_subjects_at_risk(grades, threshold=2.5)
        assert "Math" in at_risk
        assert "Physics" not in at_risk
    
    def test_get_subjects_at_risk_empty(self):
        assert self.analyzer.get_subjects_at_risk([]) == []


class TestHomeworkTracker:
    def setup_method(self):
        self.tracker = HomeworkTracker()
    
    def test_get_overdue(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        homework = [
            Homework("Math", "Old", "", yesterday),
            Homework("Math", "New", "", tomorrow),
        ]
        overdue = self.tracker.get_overdue(homework)
        assert len(overdue) == 1
        assert overdue[0].title == "Old"
    
    def test_get_due_soon(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        homework = [
            Homework("Math", "Soon", "", tomorrow),
            Homework("Math", "Later", "", next_week),
        ]
        due_soon = self.tracker.get_due_soon(homework, days=3)
        assert len(due_soon) == 1
        assert due_soon[0].title == "Soon"


class TestCalendarAnalyzer:
    def setup_method(self):
        self.analyzer = CalendarAnalyzer()
    
    def test_get_upcoming_tests(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        events = [
            CalendarEvent(tomorrow, "Sprawdzian z matematyki"),
            CalendarEvent(tomorrow, "Wycieczka szkolna"),
        ]
        tests = self.analyzer.get_upcoming_tests(events)
        assert len(tests) == 1
        assert "Sprawdzian" in tests[0].title
    
    def test_get_upcoming(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        events = [
            CalendarEvent(tomorrow, "Future"),
            CalendarEvent(yesterday, "Past"),
        ]
        upcoming = self.analyzer.get_upcoming(events)
        assert len(upcoming) == 1
        assert upcoming[0].title == "Future"


class TestChildReportGenerator:
    def test_generate_summary(self):
        from src.domain.services import ChildReportGenerator
        
        generator = ChildReportGenerator()
        result = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
            grades=[
                Grade("Math", "5", "2024-01-01", "test"),
                Grade("Math", "4", "2024-01-02", "test"),
            ],
            homework=[],
            calendar=[],
            messages=[Message("2024-01-01", "T", "S", "C", is_new=True)],
            remarks=[Remark("2024-01-01", "T", "Good job", is_positive=True)],
        )
        
        summary = generator.generate_summary(result)
        
        assert summary["child_name"] == "Test"
        assert summary["grades"]["total"] == 2
        assert summary["grades"]["average"] == 4.5
        assert summary["messages"]["unread"] == 1
        assert summary["remarks"]["positive"] == 1
