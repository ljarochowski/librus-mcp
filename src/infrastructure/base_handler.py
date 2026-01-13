"""Base MCP handler to eliminate infrastructure duplication"""
from typing import Dict, Any, List
from mcp.types import TextContent
import json


class BaseMcpHandler:
    """Base class for MCP tool handlers - eliminates massive duplication"""
    
    def __init__(self, use_case_class, *args, **kwargs):
        self.use_case = use_case_class(*args, **kwargs)
    
    def handle_tool(self, tool_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Generic MCP tool handler pattern"""
        try:
            result = self.use_case.execute(**arguments)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except Exception as e:
            error_result = {"error": f"Error in {tool_name}: {str(e)}"}
            return [TextContent(type="text", text=json.dumps(error_result, ensure_ascii=False, indent=2))]


class AsyncMcpHandler(BaseMcpHandler):
    """Async version of MCP handler"""
    
    async def handle_tool(self, tool_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Generic async MCP tool handler pattern"""
        try:
            result = await self.use_case.execute(**arguments)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except Exception as e:
            error_result = {"error": f"Error in {tool_name}: {str(e)}"}
            return [TextContent(type="text", text=json.dumps(error_result, ensure_ascii=False, indent=2))]
