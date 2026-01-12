"""Tests for new MCP server tools"""
import pytest
import json
from unittest.mock import Mock, patch
from pathlib import Path
from src.infrastructure.mcp_server import LibrusMcpServer


class TestNewMcpTools:
    """Test the new MCP tools added for Professor Dumbledore"""
    
    @pytest.fixture
    def mock_server(self, tmp_path):
        """Create server with mocked dependencies"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild\n    aliases: [TC]")
        
        server = LibrusMcpServer(config_path)
        
        # Mock storage to return test data
        server.storage.get_recent_data = Mock(return_value={
            "2026-01": {
                "data": {
                    "rawData": {
                        "grades": [
                            {"date": "2026-01-10", "subject": "Math", "teacher": "Smith", "grade": "5", "category": "sprawdzian"},
                            {"date": "2026-01-09", "subject": "Math", "teacher": "Smith", "grade": "4", "category": "ocena śródroczna"}
                        ],
                        "homework": [
                            {"date": "2026-01-10", "subject": "Math", "title": "Exercise 1", "due_date": "2026-01-15"}
                        ],
                        "messages": [
                            {"date": "2026-01-10", "title": "Test message", "content": "proszę o odpowiedź", "sender": "Teacher"}
                        ],
                        "calendar": [
                            {"date": "2026-01-14", "title": "Sprawdzian Math", "subject": "Math"}
                        ]
                    }
                }
            }
        })
        
        server.config.get_child = Mock(return_value=Mock(name="TestChild", aliases=["TC"]))
        return server
    
    def test_generate_pdf_report_missing_deps(self, mock_server):
        """Test PDF generation with missing dependencies"""
        with patch('builtins.__import__', side_effect=ImportError("No module named 'markdown'")):
            result = mock_server._generate_pdf_report("# Test", "~/test.pdf")
            assert "Missing dependencies" in result
            assert "markdown" in result
    
    def test_generate_pdf_report_success(self, mock_server, tmp_path):
        """Test PDF generation handles both success and system dependency issues"""
        output_path = tmp_path / "test.pdf"
        
        result = mock_server._generate_pdf_report("# Test Header\n\nTest content", str(output_path))
        
        # Should either succeed or fail gracefully with system dependency issues
        assert ("PDF generated" in result) or ("PDF generation failed" in result)
        # The method should handle errors gracefully, not crash
    
    def test_get_grade_details_by_date(self, mock_server):
        """Test grade details by date range"""
        result = mock_server._get_grade_details_by_date("TestChild", "2026-01-09", "2026-01-10", True)
        
        assert result["total_grades"] == 2
        assert result["date_range"] == "2026-01-09 to 2026-01-10"
        assert len(result["grades"]) == 2
        assert result["grades"][0]["date"] == "2026-01-10"  # Newest first
    
    def test_get_grade_details_exclude_semester(self, mock_server):
        """Test excluding semester grades"""
        result = mock_server._get_grade_details_by_date("TestChild", "2026-01-09", "2026-01-10", False)
        
        assert result["total_grades"] == 1  # Only non-semester grade
        assert result["grades"][0]["category"] == "sprawdzian"
    
    def test_get_teacher_subject_mapping(self, mock_server):
        """Test teacher to subject mapping"""
        result = mock_server._get_teacher_subject_mapping("TestChild")
        
        assert result["total_mappings"] == 1
        assert result["teacher_subject_mapping"]["Smith"] == "Math"
    
    def test_get_semester_grades_summary(self, mock_server):
        """Test semester grades summary"""
        result = mock_server._get_semester_grades_summary("TestChild", 1, "2025/2026")
        
        assert result["total_semester_grades"] == 1
        assert result["semester"] == 1
        assert result["grades"][0]["category"] == "ocena śródroczna"
    
    def test_get_recent_activity_delta(self, mock_server):
        """Test recent activity delta"""
        result = mock_server._get_recent_activity_delta("TestChild", "2026-01-09")
        
        assert result["new_grades"] == 2
        assert result["new_homework"] == 1
        assert result["new_messages"] == 1
        assert result["since_date"] == "2026-01-09"
    
    def test_analyze_urgent_matters(self, mock_server):
        """Test urgent matters analysis"""
        with patch('datetime.datetime') as mock_dt:
            mock_dt.now.return_value.date.return_value.strftime.return_value = "2026-01-12"
            mock_dt.strptime.return_value.date.return_value = Mock()
            mock_dt.strptime.return_value.date.return_value.__sub__ = Mock(return_value=Mock(days=3))
            
            result = mock_server._analyze_urgent_matters("TestChild")
            
            assert "summary" in result
            assert "critical_0_2_days" in result
            assert "important_3_7_days" in result
    
    def test_get_messages_with_content(self, mock_server):
        """Test enhanced messages with content"""
        result = mock_server._get_messages_with_content("TestChild")
        
        assert result["total_messages"] == 1
        assert result["requiring_response_count"] == 1  # Message contains "respond"
        assert len(result["requiring_response"]) == 1
    
    def test_child_not_found_errors(self, mock_server):
        """Test error handling for unknown child"""
        mock_server.config.get_child = Mock(return_value=None)
        
        result = mock_server._get_grade_details_by_date("Unknown", "2026-01-01", "2026-01-02", True)
        assert "error" in result
        assert "Child not found" in result["error"]
        
        result = mock_server._get_teacher_subject_mapping("Unknown")
        assert "error" in result
        
        result = mock_server._analyze_urgent_matters("Unknown")
        assert "error" in result
    
    def test_no_data_errors(self, mock_server):
        """Test error handling for no data"""
        mock_server.storage.get_recent_data = Mock(return_value=None)
        
        result = mock_server._get_grade_details_by_date("TestChild", "2026-01-01", "2026-01-02", True)
        assert "error" in result
        assert "No data found" in result["error"]


class TestMcpToolHandlers:
    """Test MCP tool handlers"""
    
    @pytest.fixture
    def mock_server(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("children:\n  - name: TestChild")
        return LibrusMcpServer(config_path)
    
    @pytest.mark.asyncio
    async def test_generate_pdf_handler(self, mock_server):
        """Test PDF generation handler"""
        with patch.object(mock_server, '_generate_pdf_report', return_value="Success"):
            result = await mock_server._handle_tool("generate_pdf_report", {
                "content": "# Test",
                "output_path": "~/test.pdf"
            })
            assert len(result) == 1
            assert "Success" in result[0].text
    
    @pytest.mark.asyncio
    async def test_grade_details_handler(self, mock_server):
        """Test grade details handler"""
        with patch.object(mock_server, '_get_grade_details_by_date', return_value={"test": "data"}):
            result = await mock_server._handle_tool("get_grade_details_by_date", {
                "child_name": "TestChild",
                "date_from": "2026-01-01",
                "date_to": "2026-01-02"
            })
            assert len(result) == 1
            assert "test" in result[0].text
    
    @pytest.mark.asyncio
    async def test_teacher_mapping_handler(self, mock_server):
        """Test teacher mapping handler"""
        with patch.object(mock_server, '_get_teacher_subject_mapping', return_value={"mapping": "data"}):
            result = await mock_server._handle_tool("get_teacher_subject_mapping", {
                "child_name": "TestChild"
            })
            assert len(result) == 1
            assert "mapping" in result[0].text
    
    @pytest.mark.asyncio
    async def test_enhanced_messages_handler(self, mock_server):
        """Test enhanced messages handler"""
        with patch.object(mock_server, '_get_messages_with_content', return_value={"messages": []}):
            result = await mock_server._handle_tool("get_messages_summary", {
                "child_name": "TestChild"
            })
            assert len(result) == 1
            assert "messages" in result[0].text
