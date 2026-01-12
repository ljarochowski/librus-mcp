"""Unit tests for domain services - edge cases and error handling"""
import pytest
from datetime import datetime, date, timedelta
from src.domain.services import GradeAnalyzer, HomeworkTracker, CalendarAnalyzer, GradeTrend
from src.domain.models import Grade, Homework, CalendarEvent, GradeValue, SubjectName

# Relative dates for non-flaky tests
TODAY = date.today().strftime("%Y-%m-%d")
YESTERDAY = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
TOMORROW = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
FUTURE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
PAST = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")


class TestGradeAnalyzerEdgeCases:
    """Unit tests for GradeAnalyzer with edge cases"""
    
    def test_calculate_average_with_malformed_grades(self):
        """Test average calculation with malformed grade data"""
        analyzer = GradeAnalyzer()
        
        # Malformed grades that should be handled gracefully
        malformed_grades = [
            Grade(subject="Math", grade=None, category="sprawdzian", date=TODAY),  # None grade
            Grade(subject="", grade="invalid", category="", date=TODAY),  # Invalid grade
            Grade(subject="Math", grade="", category="test", date=TODAY),  # Empty grade
            Grade(subject="Math", grade="∞", category="test", date=TODAY),  # Unicode
            Grade(subject="Math", grade="5+", category="test", date=TODAY),  # Valid grade
        ]
        
        # Should not crash, should handle invalid grades gracefully
        result = analyzer.calculate_average(malformed_grades)
        assert isinstance(result, (float, type(None)))
        if result is not None:
            assert 0 <= result <= 6
    
    def test_calculate_average_by_subject_with_empty_subjects(self):
        """Test subject averages with empty/None subject names"""
        analyzer = GradeAnalyzer()
        
        grades = [
            Grade(subject="", grade="5", category="test", date=TODAY),
            Grade(subject=None, grade="4", category="test", date=TODAY),
            Grade(subject="   ", grade="3", category="test", date=TODAY),
            Grade(subject="Math", grade="6", category="test", date=TODAY),
        ]
        
        result = analyzer.calculate_average_by_subject(grades)
        
        # Should handle empty subjects gracefully
        assert isinstance(result, dict)
        assert "Math" in result
        assert result["Math"] == 6.0
        
        # Empty subjects should be handled (grouped or ignored)
        for subject, avg in result.items():
            assert isinstance(subject, str)
            assert isinstance(avg, float)
            assert 0 <= avg <= 6
    
    def test_get_trend_with_insufficient_data(self):
        """Test trend calculation with edge cases"""
        analyzer = GradeAnalyzer()
        
        # Empty list
        assert analyzer.get_trend([], "Math") == GradeTrend.INSUFFICIENT_DATA
        
        # Single grade
        single_grade = [Grade(subject="Math", grade="5", category="test", date=TODAY)]
        assert analyzer.get_trend(single_grade, "Math") == GradeTrend.INSUFFICIENT_DATA
        
        # All same grades
        same_grades = [
            Grade(subject="Math", grade="5", category="test", date=TODAY),
            Grade(subject="Math", grade="5", category="test", date=TODAY),
            Grade(subject="Math", grade="5", category="test", date=TODAY),
        ]
        assert analyzer.get_trend(same_grades, "Math") == GradeTrend.STABLE
    
    def test_get_subjects_at_risk_with_extreme_values(self):
        """Test at-risk detection with extreme grade values"""
        analyzer = GradeAnalyzer()
        
        grades = [
            # Subject with mix of extreme values
            Grade(subject="Chaos", grade="1", category="test", date=TODAY),
            Grade(subject="Chaos", grade="6", category="test", date=TODAY),
            Grade(subject="Chaos", grade="1", category="test", date=TODAY),
            # Subject with only failing grades
            Grade(subject="Failing", grade="1", category="test", date=TODAY),
            Grade(subject="Failing", grade="2", category="test", date=TODAY),
            # Subject with only perfect grades
            Grade(subject="Perfect", grade="6", category="test", date=TODAY),
            Grade(subject="Perfect", grade="6", category="test", date=TODAY),
        ]
        
        at_risk = analyzer.get_subjects_at_risk(grades)
        
        # Should identify failing subjects
        assert "Failing" in at_risk
        assert "Perfect" not in at_risk
        
        # Should handle mixed subjects appropriately
        assert isinstance(at_risk, list)
        for subject in at_risk:
            assert isinstance(subject, str)


class TestHomeworkTrackerEdgeCases:
    """Unit tests for HomeworkTracker with edge cases"""
    
    def test_get_overdue_with_malformed_dates(self):
        """Test overdue detection with malformed dates"""
        tracker = HomeworkTracker()
        
        malformed_homework = [
            Homework(subject="Math", title="Valid", date_added=TODAY, date_due=TODAY),
            Homework(subject="Math", title="None date", date_added=TODAY, date_due=""),
            Homework(subject="Math", title="Future", date_added=TODAY, date_due=FUTURE),
            Homework(subject="Math", title="Past", date_added=TODAY, date_due=PAST),
        ]
        
        # Should not crash with malformed dates
        overdue = tracker.get_overdue(malformed_homework)
        assert isinstance(overdue, list)
        
        # Should include past dates, exclude None/future
        titles = [hw.title for hw in overdue]
        assert "Past" in titles
        assert "None date" not in titles
        assert "Future" not in titles
    
    def test_get_due_soon_with_edge_dates(self):
        """Test due soon detection with edge case dates"""
        tracker = HomeworkTracker()
        
        today = date.today()
        
        homework = [
            Homework(subject="Math", title="Today", date_added=TODAY, date_due=TODAY),
            Homework(subject="Math", title="Tomorrow", date_added=TODAY, date_due=TOMORROW),
            Homework(subject="Math", title="Way future", date_added=TODAY, date_due=FUTURE),
        ]
        
        due_soon = tracker.get_due_soon(homework, days=7)
        
        # Should include today and tomorrow, exclude way future
        titles = [hw.title for hw in due_soon]
        assert "Today" in titles
        assert "Tomorrow" in titles
        assert "Way future" not in titles


class TestCalendarAnalyzerEdgeCases:
    """Unit tests for CalendarAnalyzer with edge cases"""
    
    def test_get_upcoming_tests_with_malformed_events(self):
        """Test test detection with malformed calendar events"""
        analyzer = CalendarAnalyzer()
        
        malformed_events = [
            CalendarEvent(title="", date=TODAY),  # Empty title
            CalendarEvent(title="Sprawdzian Math", date=TODAY),  # Valid
            CalendarEvent(title="SPRAWDZIAN Physics", date=TODAY),  # Uppercase
            CalendarEvent(title="sprawdzian chemistry", date=TODAY),  # Lowercase
            CalendarEvent(title="Test with sprawdzian word", date=TODAY),  # Contains word
            CalendarEvent(title="Regular lesson", date=TODAY),  # Not a test
        ]
        
        tests = analyzer.get_upcoming_tests(malformed_events)
        
        # Should handle malformed data gracefully
        assert isinstance(tests, list)
        
        # Should detect tests regardless of case
        test_titles = [event.title for event in tests if event.title]
        assert any("sprawdzian" in title.lower() for title in test_titles)
        
        # Should exclude None/empty titles and dates
        for event in tests:
            assert event.title is not None
            assert event.date is not None
    
    def test_get_upcoming_with_extreme_date_ranges(self):
        """Test upcoming events with extreme date ranges"""
        analyzer = CalendarAnalyzer()
        
        today = date.today()
        events = [
            CalendarEvent(title="Ancient", date=date(1900, 1, 1)),
            CalendarEvent(title="Yesterday", date=date(today.year, today.month, today.day - 1) if today.day > 1 else date(today.year, today.month - 1, 28)),
            CalendarEvent(title="Today", date=today),
            CalendarEvent(title="Future", date=date(2099, 12, 31)),
        ]
        
        # Test different day ranges
        for days in [0, 1, 7, 30, 365, 10000]:
            upcoming = analyzer.get_upcoming(events, days=days)
            
            # Should not crash with extreme ranges
            assert isinstance(upcoming, list)
            
            # Should respect date filtering
            for event in upcoming:
                assert event.date >= today
                if days < 10000:  # Reasonable range
                    days_diff = (event.date - today).days
                    assert days_diff <= days


class TestGradeValueEdgeCases:
    """Unit tests for GradeValue with edge cases"""
    
    def test_numeric_with_extreme_inputs(self):
        """Test numeric conversion with extreme inputs"""
        test_cases = [
            # Valid cases
            ("5", 5.0),
            ("6-", 5.75),
            ("4+", 4.5),
            # Edge cases
            ("", None),
            (None, None),
            ("invalid", None),
            ("∞", None),
            ("NaN", None),
            ("1.5", None),  # Decimal not supported
            ("0", None),  # Below range
            ("7", None),  # Above range
            ("5++", None),  # Multiple modifiers
            ("--4", None),  # Invalid format
        ]
        
        for input_val, expected in test_cases:
            grade = GradeValue(input_val)
            result = grade.numeric
            assert result == expected, f"Input {input_val} should give {expected}, got {result}"
    
    def test_equality_with_different_types(self):
        """Test equality comparison with different input types"""
        grade1 = GradeValue("5")
        grade2 = GradeValue("5")
        grade3 = GradeValue("4")
        grade_none = GradeValue(None)
        
        # Same values should be equal
        assert grade1 == grade2
        
        # Different values should not be equal
        assert grade1 != grade3
        
        # None handling
        assert grade_none == GradeValue(None)
        assert grade_none != grade1
        
        # Type safety - should not equal strings or numbers
        assert not (grade1 == "5")
        assert not (grade1 == 5)
        assert not (grade1 == None)


class TestSubjectNameEdgeCases:
    """Unit tests for SubjectName with edge cases"""
    
    def test_normalization_with_extreme_inputs(self):
        """Test subject name normalization with extreme inputs"""
        test_cases = [
            # Normal cases
            ("Matematyka", "matematyka"),
            ("FIZYKA", "fizyka"),
            ("język angielski", "język_angielski"),
            # Edge cases
            ("", ""),
            (None, ""),
            ("   ", ""),
            ("  matematyka  ", "matematyka"),
            ("JĘZYK   POLSKI", "język_polski"),
            # Unicode and special chars
            ("Maﬀhematyka", "maﬀhematyka"),  # Ligatures
            ("Język🔥Polski", "język🔥polski"),  # Emoji
            ("Wychowanie fizyczne", "wychowanie_fizyczne"),
        ]
        
        for input_val, expected in test_cases:
            subject = SubjectName(input_val)
            assert subject.normalized == expected, f"Input '{input_val}' should normalize to '{expected}', got '{subject.normalized}'"
    
    def test_hash_consistency(self):
        """Test that equal subjects have same hash"""
        subject1 = SubjectName("matematyka")
        subject2 = SubjectName("MATEMATYKA")
        subject3 = SubjectName("Fizyka")
        
        # Equal subjects should have same hash
        assert hash(subject1) == hash(subject2)
        assert subject1 == subject2
        
        # Different subjects should have different hash (usually)
        assert hash(subject1) != hash(subject3)
        assert subject1 != subject3
        
        # Should be usable in sets/dicts
        subject_set = {subject1, subject2, subject3}
        assert len(subject_set) == 2  # subject1 and subject2 are same
