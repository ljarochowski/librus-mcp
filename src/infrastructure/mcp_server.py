"""MCP Server - infrastructure layer"""
import asyncio
import json
from pathlib import Path
from typing import List

from mcp.server import Server
from mcp.types import Tool, TextContent

from ..adapters import FileStorageAdapter, YamlConfigAdapter, PlaywrightBrowserAdapter
from ..application import (
    ScrapeChildUseCase,
    LoginChildUseCase,
    GetGradesSummaryUseCase,
    GetCalendarEventsUseCase,
    AnalyzeGradesUseCase
)


class LibrusMcpServer:
    """MCP Server for Librus scraping"""
    
    def __init__(self, config_path: Path):
        # Initialize adapters
        self.config = YamlConfigAdapter(config_path)
        self.storage = FileStorageAdapter(self.config.data_dir)
        self.browser = PlaywrightBrowserAdapter(
            self.storage,
            page_timeout=self.config.get_page_timeout()
        )
        
        # Initialize use cases
        self.scrape_child = ScrapeChildUseCase(self.browser, self.storage, self.config)
        self.login_child = LoginChildUseCase(self.browser, self.config)
        self.get_grades = GetGradesSummaryUseCase(self.storage, self.config)
        self.get_calendar = GetCalendarEventsUseCase(self.storage, self.config)
        self.analyze_grades = AnalyzeGradesUseCase(self.storage, self.config)
        
        # MCP server
        self.server = Server("librus-mcp")
        self._register_handlers()
    
    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return self._get_tools()
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[TextContent]:
            return await self._handle_tool(name, arguments)
    
    def _get_tools(self) -> List[Tool]:
        return [
            Tool(
                name="scrape_librus",
                description="Scrape Librus data for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"},
                        "force_full": {"type": "boolean", "default": False}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="manual_login",
                description="Trigger login for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_grades_summary",
                description="Get grades summary for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_calendar_events",
                description="Get upcoming calendar events",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_homework_summary",
                description="Get homework assignments for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_messages_summary",
                description="Get messages for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_remarks_summary",
                description="Get teacher remarks for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_memory",
                description="Get stored memory and trends for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="analyze_grade_trends",
                description="Analyze grade trends, averages, and at-risk subjects",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="list_children",
                description="List all configured children",
                inputSchema={"type": "object", "properties": {}}
            ),
        ]
    
    async def _handle_tool(self, name: str, arguments: dict) -> List[TextContent]:
        if name == "scrape_librus":
            result = await self.scrape_child.execute(
                arguments["child_name"],
                arguments.get("force_full", False)
            )
            if result.get("status") == "session_expired":
                return [TextContent(type="text", text=f"❌ Session expired for {result['child_name']}. Use manual_login.")]
            return [TextContent(type="text", text=f"✅ Scraped {result.get('stats', {})} for {result['child_name']}")]
        
        elif name == "manual_login":
            result = await self.login_child.execute(arguments["child_name"])
            if result["status"] == "success":
                return [TextContent(type="text", text=result["message"])]
            return [TextContent(type="text", text=f"❌ {result['message']}")]
        
        elif name == "get_grades_summary":
            result = self.get_grades.execute(arguments["child_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_calendar_events":
            result = self.get_calendar.execute(arguments["child_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_homework_summary":
            result = self._get_data_summary(arguments["child_name"], "homework")
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_messages_summary":
            result = self._get_data_summary(arguments["child_name"], "messages")
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_remarks_summary":
            result = self._get_data_summary(arguments["child_name"], "remarks")
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_memory":
            child = self.config.get_child(arguments["child_name"])
            if not child:
                return [TextContent(type="text", text=f"Child not found: {arguments['child_name']}")]
            memory = self.storage.load_memory(child.name)
            return [TextContent(type="text", text=json.dumps(memory, ensure_ascii=False, indent=2))]
        
        elif name == "analyze_grade_trends":
            result = self.analyze_grades.execute(arguments["child_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "list_children":
            children = self.config.get_children()
            lines = ["📚 Configured children:\n"]
            for child in children:
                state = self.storage.load_state(child.name)
                last_scan = state.get("last_scrape_iso", "Never")
                aliases = f" (aliases: {', '.join(child.aliases)})" if child.aliases else ""
                lines.append(f"- **{child.name}**{aliases}\n  Last scan: {last_scan}")
            return [TextContent(type="text", text="\n".join(lines))]
        
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    def _get_data_summary(self, child_name: str, data_type: str) -> dict:
        """Generic helper to get data summaries"""
        child = self.config.get_child(child_name)
        if not child:
            return {"error": f"Child not found: {child_name}"}
        
        data = self.storage.get_recent_data(child.name, months=2)
        if not data:
            return {"error": f"No data found for {child.name}"}
        
        items = []
        for month_data in data.values():
            raw = month_data.get('data', {}).get('rawData', {})
            items.extend(raw.get(data_type, []))
        
        return {"total": len(items), "items": items[-20:]}
    
    async def run(self):
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    server = LibrusMcpServer(config_path)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
