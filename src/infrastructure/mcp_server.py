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
    AnalyzeGradesUseCase,
    GetSemesterGradesSummaryUseCase,
    GetGradeDetailsByDateUseCase,
    GetTeacherSubjectMappingUseCase,
    AnalyzeUrgentMattersUseCase,
    GetRecentActivityDeltaUseCase,
    GeneratePdfReportUseCase,
    GetMessagesWithContentUseCase,
    GetDataSummaryUseCase,
    ListChildrenUseCase
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
        self.get_semester_grades = GetSemesterGradesSummaryUseCase(self.storage, self.config)
        self.get_grade_details = GetGradeDetailsByDateUseCase(self.storage, self.config)
        self.get_teacher_mapping = GetTeacherSubjectMappingUseCase(self.storage, self.config)
        self.analyze_urgent = AnalyzeUrgentMattersUseCase(self.storage, self.config)
        self.get_activity_delta = GetRecentActivityDeltaUseCase(self.storage, self.config)
        self.generate_pdf = GeneratePdfReportUseCase()
        self.get_messages_content = GetMessagesWithContentUseCase(self.storage, self.config)
        self.get_data_summary = GetDataSummaryUseCase(self.storage, self.config)
        self.list_children_uc = ListChildrenUseCase(self.storage, self.config)
        
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
            Tool(
                name="generate_pdf_report",
                description="Generate PDF report from markdown content with Dumbledore signature",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Markdown content to convert to PDF"},
                        "output_path": {"type": "string", "description": "Output path for PDF file"}
                    },
                    "required": ["content", "output_path"]
                }
            ),
            Tool(
                name="get_grade_details_by_date",
                description="Get detailed grades for specific date range",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"},
                        "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                        "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                        "include_semester_grades": {"type": "boolean", "default": True}
                    },
                    "required": ["child_name", "date_from", "date_to"]
                }
            ),
            Tool(
                name="get_teacher_subject_mapping",
                description="Get mapping of teachers to subjects for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_semester_grades_summary",
                description="Get semester/final grades summary",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"},
                        "semester": {"type": "integer", "description": "Semester number (1 or 2)", "default": 1},
                        "year": {"type": "string", "description": "School year (e.g., 2025/2026)"}
                    },
                    "required": ["child_name"]
                }
            ),
            Tool(
                name="get_recent_activity_delta",
                description="Get summary of recent changes since date",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"},
                        "since_date": {"type": "string", "description": "Date to check changes since (YYYY-MM-DD)"}
                    },
                    "required": ["child_name", "since_date"]
                }
            ),
            Tool(
                name="analyze_urgent_matters",
                description="Analyze and prioritize urgent matters for a child",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "child_name": {"type": "string", "description": "Child name or alias"}
                    },
                    "required": ["child_name"]
                }
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
            result = self._get_messages_with_content(arguments["child_name"])
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
            result = self.list_children_uc.execute()
            return [TextContent(type="text", text=result)]
        
        elif name == "generate_pdf_report":
            result = self._generate_pdf_report(arguments["content"], arguments["output_path"])
            return [TextContent(type="text", text=result)]
        
        elif name == "get_grade_details_by_date":
            result = self._get_grade_details_by_date(
                arguments["child_name"],
                arguments["date_from"],
                arguments["date_to"],
                arguments.get("include_semester_grades", True)
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_teacher_subject_mapping":
            result = self._get_teacher_subject_mapping(arguments["child_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_semester_grades_summary":
            result = self._get_semester_grades_summary(
                arguments["child_name"],
                arguments.get("semester", 1),
                arguments.get("year")
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "get_recent_activity_delta":
            result = self._get_recent_activity_delta(
                arguments["child_name"],
                arguments["since_date"]
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        elif name == "analyze_urgent_matters":
            result = self._analyze_urgent_matters(arguments["child_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    def _generate_pdf_report(self, content: str, output_path: str) -> str:
        """Generate PDF from markdown content"""
        return self.generate_pdf.execute(content, output_path)    
    def _get_grade_details_by_date(self, child_name: str, date_from: str, date_to: str, include_semester: bool) -> dict:
        """Get detailed grades for specific date range"""
        return self.get_grade_details.execute(child_name, date_from, date_to, include_semester)
    
    def _get_teacher_subject_mapping(self, child_name: str) -> dict:
        """Get mapping of teachers to subjects"""
        return self.get_teacher_mapping.execute(child_name)
    
    def _get_semester_grades_summary(self, child_name: str, semester: int, year: str = None) -> dict:
        """Get semester/final grades summary"""
        return self.get_semester_grades.execute(child_name, semester, year)
    
    def _get_recent_activity_delta(self, child_name: str, since_date: str) -> dict:
        """Get summary of recent changes since date"""
        return self.get_activity_delta.execute(child_name, since_date)
    
    def _analyze_urgent_matters(self, child_name: str) -> dict:
        """Analyze and prioritize urgent matters"""
        return self.analyze_urgent.execute(child_name)
    
    def _get_messages_with_content(self, child_name: str) -> dict:
        """Get messages with full content"""
        return self.get_messages_content.execute(child_name)
    
    def _get_data_summary(self, child_name: str, data_type: str) -> dict:
        """Generic helper to get data summaries"""
        return self.get_data_summary.execute(child_name, data_type)
    
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
