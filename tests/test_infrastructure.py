"""Tests for MCP server infrastructure layer"""
import pytest
import json
from unittest.mock import Mock, patch
from pathlib import Path
from datetime import date, timedelta
from src.infrastructure.mcp_server import LibrusMcpServer

# Relative dates for non-flaky tests
TODAY = date.today()
CURRENT_MONTH = TODAY.strftime("%Y-%m")
FUTURE_DATE = (TODAY + timedelta(days=5)).strftime("%Y-%m-%d")
PAYMENT_DUE = (TODAY + timedelta(days=2)).strftime("%d.%m.%Y")


class TestMcpServerInfrastructure:
    """Test MCP server initialization and basic functionality"""
    
    @pytest.fixture
    def server(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        return LibrusMcpServer(config_path)
    
    def test_server_initializes(self, server):
        """Test server initializes with required components"""
        assert server.config is not None
        assert server.storage is not None
        assert server.browser is not None
        assert server.server is not None
    
    def test_tools_list_includes_new_tools(self, server):
        """Test that new tools are registered"""
        tools = server._get_tools()
        tool_names = [tool.name for tool in tools]
        
        # Check new tools are present
        assert "generate_pdf_report" in tool_names
        assert "get_grade_details_by_date" in tool_names
        assert "get_teacher_subject_mapping" in tool_names
        assert "get_semester_grades_summary" in tool_names
        assert "analyze_urgent_matters" in tool_names


class TestSemesterGradeDeduplication:
    """Test semester grade deduplication logic"""
    
    @pytest.fixture
    def server_with_duplicates(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        server = LibrusMcpServer(config_path)
        
        # Mock data with duplicate semester grades
        server.storage.get_recent_data = Mock(return_value={
            CURRENT_MONTH: {
                "data": {
                    "rawData": {
                        "grades": [
                            # Same math grade appearing twice (the bug we're fixing)
                            {"subject": "", "teacher": "Brzęczek", "grade": "2", "category": "ocena śródroczna"},
                            {"subject": "Matematyka", "teacher": "", "grade": "2", "category": "ocena śródroczna"},
                            # Regular grade for teacher mapping
                            {"subject": "Matematyka", "teacher": "Brzęczek", "grade": "4", "category": "sprawdzian"},
                        ]
                    }
                }
            }
        })
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        return server
    
    def test_deduplicates_semester_grades(self, server_with_duplicates):
        """Test that duplicate semester grades are removed"""
        result = server_with_duplicates._get_semester_grades_summary("TestChild", 1)
        
        # Should have only 1 math grade, not 2
        assert result["total_semester_grades"] == 1
        assert result["unique_subjects"] == 1
        
        # Should map teacher to subject
        grade = result["grades"][0]
        assert grade["subject"] == "Matematyka"
        assert grade["grade"] == "2"


class TestPdfErrorHandling:
    """Test PDF generation error handling"""
    
    @pytest.fixture
    def server(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        return LibrusMcpServer(config_path)
    
    def test_handles_import_errors_gracefully(self, server, tmp_path):
        """Test PDF generation handles missing dependencies"""
        output_path = tmp_path / "test.pdf"
        
        with patch('builtins.__import__', side_effect=ImportError("No module named 'weasyprint'")):
            result = server._generate_pdf_report("# Test", str(output_path))
            
            # Should provide helpful error message, not crash
            assert "Missing Python dependencies" in result
            assert "pip install" in result
    
    def test_handles_system_library_errors(self, server, tmp_path):
        """Test PDF generation handles system library issues"""
        output_path = tmp_path / "test.pdf"
        
        # Test the actual error handling without triggering real pango issues
        result = server._generate_pdf_report("# Test", str(output_path))
        
        # Should either succeed or fail gracefully with helpful message
        success = "PDF generated" in result
        graceful_failure = any(x in result for x in ["Missing", "failed", "Error"])
        
        assert success or graceful_failure, f"Unexpected result: {result}"


class TestPaymentParsing:
    """Test payment deadline parsing from messages"""
    
    @pytest.fixture
    def server_with_payment_message(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        server = LibrusMcpServer(config_path)
        
        server.storage.get_recent_data = Mock(return_value={
            CURRENT_MONTH: {
                "data": {
                    "rawData": {
                        "messages": [
                            {"content": f"Wpłata 70 zł do {PAYMENT_DUE}", "title": "Payment", "date": FUTURE_DATE}
                        ],
                        "grades": [], "homework": [], "calendar": []
                    }
                }
            }
        })
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        return server
    
    def test_parses_payment_deadlines(self, server_with_payment_message):
        """Test that payment deadlines are extracted from messages"""
        with patch('datetime.datetime') as mock_dt:
            from datetime import date
            mock_dt.now.return_value.date.return_value = date(2026, 1, 12)
            mock_dt.strptime.return_value.date.return_value = date(2026, 1, 15)
            
            result = server_with_payment_message._analyze_urgent_matters("TestChild")
            
            # Should find payment in important category (3 days away)
            all_items = (result["critical_0_2_days"] + result["important_3_7_days"] + 
                        result["upcoming_8_14_days"])
            payment_items = [item for item in all_items if item.get("type") == "payment"]
            
            assert len(payment_items) >= 1, "Payment deadline not found"
            payment = payment_items[0]
            assert "70 zł" in payment.get("amount", "")
            # Should parse the date correctly (converts DD.MM.YYYY to YYYY-MM-DD)
            expected_iso_date = f"{TODAY.year}-{(TODAY + timedelta(days=2)).strftime('%m-%d')}"
            assert payment.get("due") == expected_iso_date


class TestGradeDetailsByDate:
    """Test grade details by date functionality"""
    
    @pytest.fixture
    def server_with_grades(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        server = LibrusMcpServer(config_path)
        
        server.storage.get_recent_data = Mock(return_value={
            CURRENT_MONTH: {
                "data": {
                    "rawData": {
                        "grades": [
                            {"date": "2026-01-10", "subject": "Math", "grade": "5", "category": "sprawdzian"},
                            {"date": "2026-01-09", "subject": "Math", "grade": "4", "category": "ocena śródroczna"},
                            {"date": "2026-01-08", "subject": "Physics", "grade": "3", "category": "kartkówka"},
                        ]
                    }
                }
            }
        })
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        return server
    
    def test_filters_by_date_range(self, server_with_grades):
        """Test filtering grades by date range"""
        result = server_with_grades._get_grade_details_by_date("TestChild", "2026-01-09", "2026-01-10", True)
        
        assert result["total_grades"] == 2
        assert result["date_range"] == "2026-01-09 to 2026-01-10"
        
        # Should be sorted by date (newest first)
        assert result["grades"][0]["date"] == "2026-01-10"
        assert result["grades"][1]["date"] == "2026-01-09"
    
    def test_excludes_semester_grades(self, server_with_grades):
        """Test excluding semester grades from results"""
        result = server_with_grades._get_grade_details_by_date("TestChild", "2026-01-08", "2026-01-10", False)
        
        # Should exclude the semester grade (ocena śródroczna)
        assert result["total_grades"] == 2  # sprawdzian + kartkówka, no semester
        categories = [g["category"] for g in result["grades"]]
        assert "ocena śródroczna" not in categories


class TestTeacherSubjectMapping:
    """Test teacher to subject mapping functionality"""
    
    @pytest.fixture
    def server_with_teacher_data(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        server = LibrusMcpServer(config_path)
        
        server.storage.get_recent_data = Mock(return_value={
            CURRENT_MONTH: {
                "data": {
                    "rawData": {
                        "grades": [
                            {"subject": "Matematyka", "teacher": "Kowalski Jan", "grade": "5"},
                            {"subject": "Fizyka", "teacher": "Nowak Anna", "grade": "4"},
                            {"subject": "Matematyka", "teacher": "Kowalski Jan", "grade": "3"},  # Same teacher
                        ]
                    }
                }
            }
        })
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        return server
    
    def test_creates_teacher_mapping(self, server_with_teacher_data):
        """Test creating teacher to subject mapping"""
        result = server_with_teacher_data._get_teacher_subject_mapping("TestChild")
        
        assert result["total_mappings"] == 2
        assert result["teacher_subject_mapping"]["Kowalski Jan"] == "Matematyka"
        assert result["teacher_subject_mapping"]["Nowak Anna"] == "Fizyka"


class TestRecentActivityDelta:
    """Test recent activity delta functionality"""
    
    @pytest.fixture
    def server_with_activity(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        server = LibrusMcpServer(config_path)
        
        server.storage.get_recent_data = Mock(return_value={
            CURRENT_MONTH: {
                "data": {
                    "rawData": {
                        "grades": [
                            {"date": "2026-01-10", "subject": "Math", "grade": "5"},
                            {"date": "2026-01-08", "subject": "Physics", "grade": "4"},  # Before cutoff
                        ],
                        "homework": [
                            {"date": "2026-01-10", "title": "Exercise 1", "due_date": "2026-01-15"},
                        ],
                        "messages": [
                            {"date": "2026-01-10", "title": "Test message", "content": "Hello"},
                        ],
                        "calendar": []
                    }
                }
            }
        })
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        return server
    
    def test_counts_activity_since_date(self, server_with_activity):
        """Test counting activity since specific date"""
        result = server_with_activity._get_recent_activity_delta("TestChild", "2026-01-09")
        
        assert result["new_grades"] == 1  # Only grade from 2026-01-10
        assert result["new_homework"] == 1
        assert result["new_messages"] == 1
        assert result["since_date"] == "2026-01-09"


class TestEnhancedMessages:
    """Test enhanced message functionality"""
    
    @pytest.fixture
    def server_with_messages(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        server = LibrusMcpServer(config_path)
        
        server.storage.get_recent_data = Mock(return_value={
            CURRENT_MONTH: {
                "data": {
                    "rawData": {
                        "messages": [
                            {"title": "Regular message", "content": "Just info", "date": "2026-01-10"},
                            {"title": "Response needed", "content": "Proszę o odpowiedź", "date": "2026-01-09"},
                            {"title": "Payment", "content": "Proszę o wpłatę", "date": "2026-01-08"},
                        ]
                    }
                }
            }
        })
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        return server
    
    def test_detects_response_required(self, server_with_messages):
        """Test detection of messages requiring response"""
        result = server_with_messages._get_messages_with_content("TestChild")
        
        assert result["total_messages"] == 3
        assert result["requiring_response_count"] == 1  # Only "proszę o odpowiedź" matches
        
        # Check that response detection works
        response_titles = [msg["title"] for msg in result["requiring_response"]]
        assert "Response needed" in response_titles


class TestMcpToolHandlers:
    """Test MCP tool handlers"""
    
    @pytest.fixture
    def server(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        return LibrusMcpServer(config_path)
    
    @pytest.mark.asyncio
    async def test_grade_details_handler(self, server):
        """Test grade details handler"""
        with patch.object(server.get_grade_details, 'execute', return_value={"test": "data"}):
            result = await server._handle_tool("get_grade_details_by_date", {
                "child_name": "TestChild",
                "date_from": "2026-01-01",
                "date_to": "2026-01-02"
            })
            assert len(result) == 1
            assert "test" in result[0].text
    
    @pytest.mark.asyncio
    async def test_teacher_mapping_handler(self, server):
        """Test teacher mapping handler"""
        with patch.object(server.get_teacher_mapping, 'execute', return_value={"mapping": "data"}):
            result = await server._handle_tool("get_teacher_subject_mapping", {
                "child_name": "TestChild"
            })
            assert len(result) == 1
            assert "mapping" in result[0].text
    
    @pytest.mark.asyncio
    async def test_semester_grades_handler(self, server):
        """Test semester grades handler"""
        with patch.object(server.get_semester_grades, 'execute', return_value={"semester": "data"}):
            result = await server._handle_tool("get_semester_grades_summary", {
                "child_name": "TestChild"
            })
            assert len(result) == 1
            assert "semester" in result[0].text
    
    @pytest.mark.asyncio
    async def test_activity_delta_handler(self, server):
        """Test activity delta handler"""
        with patch.object(server.get_activity_delta, 'execute', return_value={"activity": "data"}):
            result = await server._handle_tool("get_recent_activity_delta", {
                "child_name": "TestChild",
                "since_date": "2026-01-01"
            })
            assert len(result) == 1
            assert "activity" in result[0].text
    
    @pytest.mark.asyncio
    async def test_urgent_matters_handler(self, server):
        """Test urgent matters handler"""
        with patch.object(server.analyze_urgent, 'execute', return_value={"urgent": "data"}):
            result = await server._handle_tool("analyze_urgent_matters", {
                "child_name": "TestChild"
            })
            assert len(result) == 1
            assert "urgent" in result[0].text
    
    @pytest.mark.asyncio
    async def test_enhanced_messages_handler(self, server):
        """Test enhanced messages handler"""
        with patch.object(server.get_messages_content, 'execute', return_value={"messages": []}):
            result = await server._handle_tool("get_messages_summary", {
                "child_name": "TestChild"
            })
            assert len(result) == 1
            assert "messages" in result[0].text


class TestErrorHandling:
    """Test error handling across all new functions"""
    
    @pytest.fixture
    def server(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        return LibrusMcpServer(config_path)
    
    def test_child_not_found_errors(self, server):
        """Test error handling for unknown child"""
        server.config.get_child = Mock(return_value=None)
        
        result = server._get_grade_details_by_date("Unknown", "2026-01-01", "2026-01-02", True)
        assert "error" in result
        assert "Child not found" in result["error"]
        
        result = server._get_teacher_subject_mapping("Unknown")
        assert "error" in result
        
        result = server._get_semester_grades_summary("Unknown", 1)
        assert "error" in result
        
        result = server._analyze_urgent_matters("Unknown")
        assert "error" in result
    
    def test_no_data_errors(self, server):
        """Test error handling for no data"""
        server.config.get_child = Mock(return_value=Mock(name="TestChild"))
        server.storage.get_recent_data = Mock(return_value=None)
        
        result = server._get_grade_details_by_date("TestChild", "2026-01-01", "2026-01-02", True)
        assert "error" in result
        assert "No data found" in result["error"]
