"""Integration tests for MCP server"""
import pytest
import asyncio
from pathlib import Path
from datetime import datetime
import pickle

from src.infrastructure.mcp_server import LibrusMcpServer


@pytest.fixture
def config_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""
browser:
  login_timeout_ms: 120000
  page_timeout_ms: 30000
storage:
  data_dir: ".test_data"
children:
  - name: "TestChild"
    aliases: ["TC"]
    username: "testuser"
    password: "testpass"
  - name: "NoCredsChild"
    aliases: []
""")
    return config


@pytest.fixture
def server(config_file, tmp_path):
    # Patch data_dir to use tmp_path
    server = LibrusMcpServer(config_file)
    server.storage.base_dir = tmp_path / "data"
    server.storage.base_dir.mkdir(parents=True, exist_ok=True)
    return server


@pytest.fixture
def server_with_data(server):
    """Server with sample data"""
    now = datetime.now()
    child_dir = server.storage.get_child_dir("TestChild")
    
    data = {
        'timestamp': now.isoformat(),
        'data': {
            'rawData': {
                'grades': [
                    {'subject': 'Math', 'grade': '5', 'date': '2024-01-01', 'category': 'test', 'weight': '1'},
                    {'subject': 'Math', 'grade': '3', 'date': '2024-01-02', 'category': 'test', 'weight': '1'},
                    {'subject': 'Physics', 'grade': '2', 'date': '2024-01-01', 'category': 'test', 'weight': '1'},
                ],
                'calendar': [
                    {'date': '2099-01-15', 'title': 'Sprawdzian', 'category': ''},
                ],
                'homework': [
                    {'subject': 'Math', 'title': 'Task', 'date_added': '2024-01-01', 'date_due': '2024-01-10'},
                ],
                'messages': [
                    {'date': '2024-01-01', 'sender': 'Teacher', 'subject': 'Info', 'content': 'Hello', 'is_new': True},
                ],
                'remarks': [
                    {'date': '2024-01-01', 'teacher': 'Teacher', 'content': 'Good work'},
                ],
            }
        }
    }
    
    pkl_file = child_dir / f"{now.year}-{now.month:02d}.pkl"
    with open(pkl_file, 'wb') as f:
        pickle.dump(data, f)
    
    return server


class TestMcpServerTools:
    @pytest.mark.asyncio
    async def test_list_children(self, server):
        result = await server._handle_tool('list_children', {})
        text = result[0].text
        
        assert "TestChild" in text
        assert "NoCredsChild" in text
        assert "TC" in text  # alias
    
    @pytest.mark.asyncio
    async def test_get_grades_summary_no_data(self, server):
        result = await server._handle_tool('get_grades_summary', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "error" in text or "No data" in text
    
    @pytest.mark.asyncio
    async def test_get_grades_summary_with_data(self, server_with_data):
        result = await server_with_data._handle_tool('get_grades_summary', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "Math" in text
        assert "Physics" in text
    
    @pytest.mark.asyncio
    async def test_get_grades_summary_unknown_child(self, server):
        result = await server._handle_tool('get_grades_summary', {'child_name': 'Unknown'})
        text = result[0].text
        
        assert "not found" in text.lower() or "error" in text.lower()
    
    @pytest.mark.asyncio
    async def test_get_calendar_events(self, server_with_data):
        result = await server_with_data._handle_tool('get_calendar_events', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "total_events" in text
        # Future events (2099) are in upcoming
    
    @pytest.mark.asyncio
    async def test_get_homework_summary(self, server_with_data):
        result = await server_with_data._handle_tool('get_homework_summary', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "Math" in text or "Task" in text
    
    @pytest.mark.asyncio
    async def test_get_messages_summary(self, server_with_data):
        result = await server_with_data._handle_tool('get_messages_summary', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "Teacher" in text or "Info" in text
    
    @pytest.mark.asyncio
    async def test_get_remarks_summary(self, server_with_data):
        result = await server_with_data._handle_tool('get_remarks_summary', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "Good work" in text or "Teacher" in text
    
    @pytest.mark.asyncio
    async def test_get_memory_empty(self, server):
        result = await server._handle_tool('get_memory', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "TestChild" in text
    
    @pytest.mark.asyncio
    async def test_get_memory_unknown_child(self, server):
        result = await server._handle_tool('get_memory', {'child_name': 'Unknown'})
        text = result[0].text
        
        assert "not found" in text.lower()
    
    @pytest.mark.asyncio
    async def test_analyze_grade_trends(self, server_with_data):
        result = await server_with_data._handle_tool('analyze_grade_trends', {'child_name': 'TestChild'})
        text = result[0].text
        
        assert "Math" in text
        assert "average" in text.lower()
    
    @pytest.mark.asyncio
    async def test_unknown_tool(self, server):
        result = await server._handle_tool('nonexistent_tool', {})
        text = result[0].text
        
        assert "Unknown tool" in text
    
    @pytest.mark.asyncio
    async def test_alias_resolution(self, server_with_data):
        result = await server_with_data._handle_tool('get_grades_summary', {'child_name': 'TC'})
        text = result[0].text
        
        assert "Math" in text  # data exists, alias resolved


class TestMcpServerInitialization:
    def test_server_initializes(self, config_file):
        server = LibrusMcpServer(config_file)
        
        assert server.config is not None
        assert server.storage is not None
        assert server.browser is not None
    
    def test_server_has_use_cases(self, config_file):
        server = LibrusMcpServer(config_file)
        
        assert server.scrape_child is not None
        assert server.login_child is not None
        assert server.get_grades is not None
        assert server.get_calendar is not None
        assert server.analyze_grades is not None
    
    def test_tools_list(self, server):
        tools = server._get_tools()
        
        tool_names = [t.name for t in tools]
        assert "scrape_librus" in tool_names
        assert "manual_login" in tool_names
        assert "get_grades_summary" in tool_names
        assert "list_children" in tool_names
        assert "analyze_grade_trends" in tool_names
