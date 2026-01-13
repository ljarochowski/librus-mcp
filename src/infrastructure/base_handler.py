"""Base MCP handler to eliminate infrastructure duplication"""
from typing import Dict, Any, List
from mcp.types import TextContent
import json


class BaseMcpHandler:
    """Base class for MCP tool handlers - eliminates massive duplication"""
    
    def __init__(self, use_case_class, *args, **kwargs):
        self.use_case = use_case_class(*args, **kwargs)
    
    def _format_response(self, result: Dict, tool_name: str) -> List[TextContent]:
        """Format response as JSON TextContent"""
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    def _handle_error(self, error: Exception, tool_name: str) -> List[TextContent]:
        """Handle and format error response"""
        error_result = {"error": f"Error in {tool_name}: {str(error)}"}
        return self._format_response(error_result, tool_name)
    
    def _execute_and_handle(self, tool_name: str, arguments: Dict[str, Any], execute_func) -> List[TextContent]:
        """Common execution pattern for sync and async handlers"""
        try:
            result = execute_func(**arguments)
            return self._format_response(result, tool_name)
        except Exception as e:
            return self._handle_error(e, tool_name)
    
    def handle_tool(self, tool_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Generic MCP tool handler pattern"""
        return self._execute_and_handle(tool_name, arguments, self.use_case.execute)


class AsyncMcpHandler(BaseMcpHandler):
    """Async version of MCP handler"""
    
    async def handle_tool(self, tool_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Generic async MCP tool handler pattern"""
        async def async_execute(**args):
            return await self.use_case.execute(**args)
        return self._execute_and_handle(tool_name, arguments, async_execute)
