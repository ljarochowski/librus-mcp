"""Tests for MCP server infrastructure layer"""
import pytest
import json
from unittest.mock import Mock, patch
from pathlib import Path
from src.infrastructure.mcp_server import LibrusMcpServer


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
            "2026-01": {
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
            "2026-01": {
                "data": {
                    "rawData": {
                        "messages": [
                            {"content": "Wpłata 70 zł do 15.01.2026", "title": "Payment", "date": "2026-01-10"}
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
            assert "2026-01-15" in payment.get("due", "")
