#!/usr/bin/env python3
"""
Librus MCP Server - scrape Polish school system (Librus Synergia) data via MCP protocol
"""

import asyncio
from datetime import datetime
from typing import Dict

from playwright.async_api import async_playwright
from mcp.server import Server
from mcp.types import Tool, TextContent

from src.config import config, Colors
from src.credentials import resolve_child_name, list_children
from src.storage import (
    get_context_dir, load_state, save_state, save_scrape_result,
    load_memory, save_memory
)
from src.scraper import scrape_librus_data
from src.memory import update_memory, format_memory


# ============================================================================
# BROWSER CONTEXT
# ============================================================================

async def get_browser_context(child_name: str, browser):
    """
    Get or create browser context with auto-login.
    
    Tries to use saved cookies, but if login fails, opens browser for manual login.
    """
    context_dir = get_context_dir(child_name)
    state = load_state(child_name)
    cookies_file = context_dir / "cookies.json"
    
    # Try with cookies if they exist
    if cookies_file.exists():
        print(f"{Colors.CYAN}[{child_name}] Trying auto-login with saved session{Colors.ENDC}")
        context = await browser.new_context(storage_state=str(cookies_file))
        page = await context.new_page()
        
        try:
            # Test if cookies are still valid
            await page.goto('https://synergia.librus.pl/rodzic/index', timeout=config.page_timeout_ms)
            
            # Check if we're actually logged in (not redirected to login page)
            current_url = page.url
            if '/loguj' in current_url or '/login' in current_url:
                print(f"{Colors.YELLOW}Session expired, need to log in again{Colors.ENDC}")
                await context.close()
                # Delete invalid cookies
                cookies_file.unlink()
            else:
                print(f"{Colors.GREEN}Auto-login successful{Colors.ENDC}")
                return context
                
        except Exception as e:
            print(f"{Colors.YELLOW}Auto-login failed: {e}{Colors.ENDC}")
            await context.close()
            cookies_file.unlink()
    
    # Manual login required
    print(f"{Colors.YELLOW}[{child_name}] Manual login required{Colors.ENDC}")
    
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        await page.goto('https://portal.librus.pl/rodzina/synergia/loguj')
        print(f"{Colors.YELLOW}Please log in manually in the browser window...{Colors.ENDC}")
        
        print(f"{Colors.YELLOW}Waiting for login for {child_name}...{Colors.ENDC}")
        await page.wait_for_url(lambda url: '/rodzic' in url, timeout=config.login_timeout_ms)
        print(f"{Colors.GREEN}Logged in!{Colors.ENDC}")
        
        await context.storage_state(path=str(cookies_file))
        print(f"{Colors.GREEN}Session saved{Colors.ENDC}")
        
        state["setup_completed"] = True
        save_state(child_name, state)
        
    except Exception as e:
        print(f"{Colors.RED}Login failed: {e}{Colors.ENDC}")
        await context.close()
        raise
    
    return context


# ============================================================================
# MAIN SCRAPING FUNCTION
# ============================================================================

async def scrape_librus(child_name: str, force_full: bool = False) -> Dict:
    """
    Scrape Librus data for a child.
    
    Args:
        child_name: Child name or alias
        force_full: If True, scrape all data. If False, only new data since last scrape.
        
    Returns:
        Dict with markdown, stats, mode, and child_name
    """
    state = load_state(child_name)
    last_scrape = state.get("last_scrape_iso")
    is_first = last_scrape is None or force_full
    
    mode = "FULL" if is_first else f"DELTA since {last_scrape}"
    
    print(f"\n{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{child_name} - {mode}{Colors.ENDC}")
    print(f"{Colors.BOLD}{'='*60}{Colors.ENDC}\n")
    
    # Use headless mode if cookies exist
    context_dir = get_context_dir(child_name)
    cookies_file = context_dir / "cookies.json"
    headless = cookies_file.exists()
    
    async with async_playwright() as p:
        print(f"{Colors.BLUE}Launching browser...{Colors.ENDC}")
        browser = await p.webkit.launch(headless=headless)
        context = await get_browser_context(child_name, browser)
        page = await context.new_page()
        
        print(f"{Colors.BLUE}Navigating to Librus...{Colors.ENDC}")
        await page.goto('https://synergia.librus.pl/rodzic/index', timeout=config.page_timeout_ms)
        print(f"{Colors.GREEN}Page loaded{Colors.ENDC}")
        
        print(f"{Colors.BLUE}Running scraper...{Colors.ENDC}")
        result = await scrape_librus_data(page, last_scrape, is_first)
        print(f"{Colors.GREEN}Scraping complete{Colors.ENDC}")
        
        # Update state
        now = datetime.now()
        state["last_scrape_iso"] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_state(child_name, state)
        
        # Save results
        save_scrape_result(child_name, result["markdown"])
        await update_memory(child_name, result.get("rawData", {}))
        
        await context.close()
        await browser.close()
        
        return {
            "markdown": result["markdown"],
            "stats": result["stats"],
            "mode": mode,
            "child_name": resolve_child_name(child_name)
        }


# ============================================================================
# MCP SERVER
# ============================================================================

async def list_tools() -> list[Tool]:
    """List available MCP tools"""
    return [
        Tool(
            name="scrape_librus",
            description="Scrape Librus data for a child. Returns messages, announcements, grades, and calendar events.",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias (e.g., 'Jakub' or 'Kuba')"
                    },
                    "force_full": {
                        "type": "boolean",
                        "description": "Force full scan instead of delta (default: false)",
                        "default": False
                    }
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
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    }
                },
                "required": ["child_name"]
            }
        ),
        Tool(
            name="get_analysis_summary",
            description="Get agent's previous analysis summary for a child",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    }
                },
                "required": ["child_name"]
            }
        ),
        Tool(
            name="save_analysis_summary", 
            description="Save agent's analysis summary for a child",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    },
                    "summary_text": {
                        "type": "string",
                        "description": "Analysis summary (JSON or text)"
                    }
                },
                "required": ["child_name", "summary_text"]
            }
        ),
        Tool(
            name="get_recent_data",
            description="Get recent months data for analysis",
            inputSchema={
                "type": "object", 
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    },
                    "months_back": {
                        "type": "integer",
                        "description": "Number of months to look back (default: 2)",
                        "default": 2
                    }
                },
                "required": ["child_name"]
            }
        ),
        Tool(
            name="mark_task_done",
            description="Mark a task as completed by parent",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    },
                    "task_id": {
                        "type": "string", 
                        "description": "Task identifier"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional completion notes"
                    }
                },
                "required": ["child_name", "task_id"]
            }
        ),
        Tool(
            name="get_pending_tasks",
            description="Get pending tasks for a child",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    }
                },
                "required": ["child_name"]
            }
        ),
        Tool(
            name="save_analysis",
            description="Save an insight or note to child's memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Child name or alias"
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["issue", "action_item", "parent_note"],
                        "description": "Type of analysis to save"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the note or analysis"
                    }
                },
                "required": ["child_name", "analysis_type", "content"]
            }
        ),
        Tool(
            name="list_children",
            description="List all configured children with their last scan dates",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle MCP tool calls"""
    
    if name == "get_analysis_summary":
        child_name = arguments["child_name"]
        try:
            summary = storage.load_analysis_summary(child_name)
            if summary:
                return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
            else:
                return [TextContent(type="text", text=f"No analysis summary found for {child_name}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading analysis summary: {str(e)}")]
    
    elif name == "save_analysis_summary":
        child_name = arguments["child_name"]
        summary_text = arguments["summary_text"]
        try:
            # Parse the summary text as JSON or create structured summary
            try:
                summary = json.loads(summary_text)
            except json.JSONDecodeError:
                # If not JSON, create structured summary
                summary = {
                    "timestamp": datetime.now().isoformat(),
                    "analysis": summary_text,
                    "key_points": [],
                    "action_items": [],
                    "concerns": []
                }
            
            storage.save_analysis_summary(child_name, summary)
            return [TextContent(type="text", text=f"Analysis summary saved for {child_name}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error saving analysis summary: {str(e)}")]
    
    elif name == "get_recent_data":
        child_name = arguments["child_name"]
        months_back = arguments.get("months_back", 2)
        try:
            data = storage.get_recent_months_data(child_name, months_back)
            if data:
                # Convert to JSON for agent consumption
                return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]
            else:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading recent data: {str(e)}")]
    
    elif name == "mark_task_done":
        child_name = arguments["child_name"]
        task_id = arguments["task_id"]
        notes = arguments.get("notes", "")
        try:
            tasks = storage.load_tasks(child_name) or {"completed": [], "pending": []}
            
            # Add to completed with timestamp
            completed_task = {
                "task_id": task_id,
                "completed_at": datetime.now().isoformat(),
                "notes": notes
            }
            tasks["completed"].append(completed_task)
            
            # Remove from pending if exists
            tasks["pending"] = [t for t in tasks.get("pending", []) if t.get("id") != task_id]
            
            storage.save_tasks(child_name, tasks)
            return [TextContent(type="text", text=f"Task {task_id} marked as completed for {child_name}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error marking task done: {str(e)}")]
    
    elif name == "get_pending_tasks":
        child_name = arguments["child_name"]
        try:
            tasks = storage.load_tasks(child_name)
            if tasks and tasks.get("pending"):
                return [TextContent(type="text", text=json.dumps(tasks["pending"], ensure_ascii=False, indent=2))]
            else:
                return [TextContent(type="text", text=f"No pending tasks for {child_name}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading tasks: {str(e)}")]
    
    elif name == "scrape_librus":
        child_name = arguments["child_name"]
        force_full = arguments.get("force_full", False)
        
        result = await scrape_librus(child_name, force_full)
        
        return [TextContent(
            type="text",
            text=f"✅ Scraped {result['stats']} for {result['child_name']}\n\n{result['markdown'][:1000]}..."
        )]
    
    elif name == "get_memory":
        child_name = arguments["child_name"]
        memory = load_memory(child_name)
        formatted = format_memory(memory)
        
        return [TextContent(
            type="text",
            text=formatted
        )]
    
    elif name == "save_analysis":
        child_name = arguments["child_name"]
        analysis_type = arguments["analysis_type"]
        content = arguments["content"]
        
        memory = load_memory(child_name)
        
        entry = {
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if analysis_type == "issue":
            memory.setdefault("issues", []).append(entry)
        elif analysis_type == "action_item":
            memory.setdefault("action_items", []).append(entry)
        elif analysis_type == "parent_note":
            memory.setdefault("parent_notes", []).append(entry)
        
        save_memory(child_name, memory)
        
        return [TextContent(
            type="text",
            text=f"✅ Saved {analysis_type} for {resolve_child_name(child_name)}"
        )]
    
    elif name == "list_children":
        children = list_children()
        result = "📚 Configured children:\n\n"
        
        for child in children:
            name = child["name"]
            aliases = child.get("aliases", [])
            state = load_state(name)
            last_scan = state.get("last_scrape_iso", "Never")
            
            result += f"- **{name}**"
            if aliases:
                result += f" (aliases: {', '.join(aliases)})"
            result += f"\n  Last scan: {last_scan}\n"
        
        return [TextContent(type="text", text=result)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run MCP server"""
    server = Server("librus-mcp")
    
    @server.list_tools()
    async def handle_list_tools():
        return await list_tools()
    
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        return await call_tool(name, arguments)
    
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
