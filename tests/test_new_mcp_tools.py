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
        
        # Mock storage to return test data with DUPLICATES and edge cases
        server.storage.get_recent_data = Mock(return_value={
            "2026-01": {
                "data": {
                    "rawData": {
                        "grades": [
                            # DUPLICATE semester grades - same math grade appearing twice
                            {"date": "2026-01-09", "subject": "", "teacher": "Brzęczek Izabela", "grade": "2", "category": "ocena śródroczna"},
                            {"date": "", "subject": "Matematyka", "teacher": "", "grade": "2", "category": "ocena śródroczna"},
                            # Regular grade for mapping
                            {"date": "2026-01-08", "subject": "Matematyka", "teacher": "Brzęczek Izabela", "grade": "4", "category": "sprawdzian"},
                            # Another subject
                            {"date": "2026-01-10", "subject": "Fizyka", "teacher": "Kowalski Jan", "grade": "3", "category": "przewidywana śródroczna"},
                        ],
                        "homework": [
                            {"date": "2026-01-10", "subject": "Math", "title": "Exercise 1", "due_date": "2026-01-15"}
                        ],
                        "messages": [
                            # Payment deadline message
                            {"date": "2026-01-10", "title": "Płatność za spektakl", "content": "Proszę o wpłatę 70 zł do 15.01.2026", "sender": "Teacher"},
                            # Regular message
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
            assert "Missing Python dependencies" in result
            assert "markdown" in result
    
    def test_generate_pdf_report_pango_error(self, mock_server, tmp_path):
        """Test PDF generation with pango library error"""
        output_path = tmp_path / "test.pdf"
        
        # Simulate pango library error by patching the HTML class after import
        with patch('weasyprint.HTML') as mock_html:
            mock_html.side_effect = Exception("cannot load library 'libpango-1.0-0': dlopen failed")
            
            result = mock_server._generate_pdf_report("# Test", str(output_path))
            
            # Should provide helpful installation instructions
            assert "Missing system libraries" in result
            assert "brew install pango" in result  # macOS instructions
            assert "apt-get install" in result     # Ubuntu instructions
    
    def test_generate_pdf_report_import_error(self, mock_server, tmp_path):
        """Test PDF generation with missing Python dependencies"""
        output_path = tmp_path / "test.pdf"
        
        with patch('builtins.__import__', side_effect=ImportError("No module named 'weasyprint'")):
            result = mock_server._generate_pdf_report("# Test", str(output_path))
            
            # Should provide pip install instructions
            assert "Missing Python dependencies" in result
            assert "pip install markdown weasyprint" in result
    
    def test_get_grade_details_by_date(self, mock_server):
        """Test grade details by date range"""
        result = mock_server._get_grade_details_by_date("TestChild", "2026-01-09", "2026-01-10", True)
        
        assert result["total_grades"] == 2
        assert result["date_range"] == "2026-01-09 to 2026-01-10"
        assert len(result["grades"]) == 2
        assert result["grades"][0]["date"] == "2026-01-10"  # Newest first
    
    def test_get_grade_details_exclude_semester(self, mock_server):
        """Test excluding semester grades"""
        result = mock_server._get_grade_details_by_date("TestChild", "2026-01-08", "2026-01-10", False)
        
        assert result["total_grades"] == 1  # Only the sprawdzian grade (non-semester)
        assert result["grades"][0]["category"] == "sprawdzian"
    
    def test_get_teacher_subject_mapping(self, mock_server):
        """Test teacher to subject mapping"""
        result = mock_server._get_teacher_subject_mapping("TestChild")
        
        assert result["total_mappings"] == 2  # Brzęczek->Matematyka, Kowalski->Fizyka
        assert result["teacher_subject_mapping"]["Brzęczek Izabela"] == "Matematyka"
        assert result["teacher_subject_mapping"]["Kowalski Jan"] == "Fizyka"
    
    def test_get_semester_grades_summary(self, mock_server):
        """Test semester grades summary with deduplication"""
        result = mock_server._get_semester_grades_summary("TestChild", 1, "2025/2026")
        
        # Should deduplicate the duplicate math grade (2 entries → 1)
        assert result["total_semester_grades"] == 2  # Math + Physics, not 3
        assert result["unique_subjects"] == 2  # Math and Physics
        assert result["semester"] == 1
        
        # Check that math grade appears only once
        math_grades = [g for g in result["grades"] if g.get("subject") == "Matematyka"]
        assert len(math_grades) == 1
        assert math_grades[0]["grade"] == "2"
        
        # Check that teacher mapping worked (empty subject filled from teacher)
        subjects = [g.get("subject") for g in result["grades"]]
        assert "Matematyka" in subjects
        assert "Fizyka" in subjects
        assert "" not in subjects  # No empty subjects
    
    def test_get_semester_grades_deduplication_edge_cases(self, mock_server):
        """Test edge cases in semester grade deduplication"""
        # Add more complex duplicate scenario
        mock_server.storage.get_recent_data = Mock(return_value={
            "2026-01": {
                "data": {
                    "rawData": {
                        "grades": [
                            # Same grade, different categories (should keep both)
                            {"subject": "Math", "grade": "4", "category": "przewidywana śródroczna"},
                            {"subject": "Math", "grade": "4", "category": "ocena śródroczna"},
                            # Same grade, same category (should deduplicate)
                            {"subject": "Physics", "grade": "3", "category": "ocena śródroczna"},
                            {"subject": "Physics", "grade": "3", "category": "ocena śródroczna"},
                        ]
                    }
                }
            }
        })
        
        result = mock_server._get_semester_grades_summary("TestChild", 1)
        
        # Should keep 3 grades: Math predicted, Math final, Physics final (deduplicated)
        assert result["total_semester_grades"] == 3
        assert result["unique_subjects"] == 2  # Math and Physics
    
    def test_get_recent_activity_delta(self, mock_server):
        """Test recent activity delta"""
        result = mock_server._get_recent_activity_delta("TestChild", "2026-01-09")
        
        assert result["new_grades"] == 3  # 3 grades since 2026-01-09 (inclusive)
        assert result["new_homework"] == 1
        assert result["new_messages"] == 2  # 2 messages in test data
        assert result["since_date"] == "2026-01-09"
    
    def test_analyze_urgent_matters(self, mock_server):
        """Test urgent matters analysis including payment deadlines"""
        with patch('datetime.datetime') as mock_dt:
            mock_dt.now.return_value.date.return_value.strftime.return_value = "2026-01-12"
            
            # Mock date parsing for payment deadline (15.01.2026 = 3 days from 2026-01-12)
            from datetime import date
            mock_dt.strptime.return_value.date.return_value = date(2026, 1, 15)
            mock_dt.now.return_value.date.return_value = date(2026, 1, 12)
            
            result = mock_server._analyze_urgent_matters("TestChild")
            
            assert "summary" in result
            assert "critical_0_2_days" in result
            assert "important_3_7_days" in result
            
            # Should find payment deadline in important (3 days away)
            important_items = result["important_3_7_days"]
            payment_items = [item for item in important_items if item.get("type") == "payment"]
            assert len(payment_items) >= 1
            
            # Check payment details
            payment = payment_items[0]
            assert payment["amount"] == "70 zł"
            assert payment["due"] == "2026-01-15"
            assert payment["days_until"] == 3
    
    def test_analyze_urgent_matters_payment_parsing(self, mock_server):
        """Test payment deadline parsing from various message formats"""
        # Test different payment message formats
        test_messages = [
            {"content": "Wpłata 50 zł do 20.01.2026", "expected_amount": "50 zł", "expected_date": "2026-01-20"},
            {"content": "Opłata 75.50 zł termin 2026-01-25", "expected_amount": "75.50 zł", "expected_date": "2026-01-25"},
            {"content": "Składka 100 PLN deadline 30/01/2026", "expected_amount": "100 PLN", "expected_date": "2026-01-30"},
        ]
        
        for i, msg_test in enumerate(test_messages):
            mock_server.storage.get_recent_data = Mock(return_value={
                "2026-01": {
                    "data": {
                        "rawData": {
                            "messages": [
                                {"date": "2026-01-10", "title": "Payment", "content": msg_test["content"], "sender": "School"}
                            ],
                            "grades": [], "homework": [], "calendar": []
                        }
                    }
                }
            })
            
            with patch('datetime.datetime') as mock_dt:
                from datetime import date
                mock_dt.now.return_value.date.return_value = date(2026, 1, 12)
                mock_dt.strptime.return_value.date.return_value = date.fromisoformat(msg_test["expected_date"])
                
                result = mock_server._analyze_urgent_matters("TestChild")
                
                # Find payment in results
                all_items = (result["critical_0_2_days"] + result["important_3_7_days"] + 
                           result["upcoming_8_14_days"])
                payment_items = [item for item in all_items if item.get("type") == "payment"]
                
                assert len(payment_items) >= 1, f"Test {i}: No payment found for '{msg_test['content']}'"
                payment = payment_items[0]
                assert payment["amount"] == msg_test["expected_amount"], f"Test {i}: Wrong amount"
                assert payment["due"] == msg_test["expected_date"], f"Test {i}: Wrong date"
    
    def test_get_messages_with_content(self, mock_server):
        """Test enhanced messages with content"""
        result = mock_server._get_messages_with_content("TestChild")
        
        assert result["total_messages"] == 2  # 2 messages in test data
        assert result["requiring_response_count"] == 1  # Only one has "proszę o odpowiedź"
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
