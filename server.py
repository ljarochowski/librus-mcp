#!/usr/bin/env python3
"""
Librus MCP Server - scrape Polish school system (Librus Synergia) data via MCP protocol
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict

from playwright.async_api import async_playwright
from mcp.server import Server
from mcp.types import Tool, TextContent

from src.config import config, Colors
from src.credentials import resolve_child_name, list_children
from src.storage import (
    get_context_dir, load_state, save_state, save_scrape_result,
    load_memory, save_memory, save_monthly_data, load_monthly_data,
    get_recent_months_data, save_analysis_summary, load_analysis_summary,
    save_tasks, load_tasks
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
            # Test if cookies are still valid - fail fast
            await page.goto('https://synergia.librus.pl/rodzic/index', timeout=3000, wait_until='domcontentloaded')
            
            # Check if we're actually logged in (not redirected to login page)
            current_url = page.url
            if '/loguj' in current_url or '/login' in current_url:
                print(f"{Colors.YELLOW}Session expired{Colors.ENDC}")
                await page.close()
                await context.close()
                cookies_file.unlink()
                return None
            else:
                print(f"{Colors.GREEN}Auto-login successful{Colors.ENDC}")
                await page.close()
                return context
                
        except Exception as e:
            print(f"{Colors.YELLOW}Auto-login failed: {e}{Colors.ENDC}")
            await page.close()
            await context.close()
            cookies_file.unlink()
            return None
    
    # No valid session - return None (don't auto-open browser)
    return None


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
    try:
        state = load_state(child_name)
        last_scrape_raw = state.get("last_scrape_iso")
        is_first = last_scrape_raw is None or force_full
        
        # For DELTA mode: go back to 23:59:59 of the day before last scrape
        # This ensures we capture all data from the day of last scrape
        last_scrape = None
        if not is_first and last_scrape_raw:
            last_dt = datetime.strptime(last_scrape_raw, "%Y-%m-%d %H:%M:%S")
            # Go back to previous day at 23:59:59
            delta_start = (last_dt.date() - timedelta(days=1))
            last_scrape = f"{delta_start} 23:59:59"
        
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
            
            if context is None:
                await browser.close()
                print(f"\n{Colors.BOLD}{Colors.RED}Session expired for {child_name}{Colors.ENDC}")
                print(f"{Colors.YELLOW}Use manual_login tool to refresh login session.{Colors.ENDC}\n")
                
                return {
                    "status": "session_expired",
                    "child_name": child_name,
                    "message": f"Session expired. Manual login required.",
                    "mode": "full" if force_full else "delta",
                    "stats": {}
                }
            
            page = await context.new_page()
            
            print(f"{Colors.BLUE}Navigating to Librus...{Colors.ENDC}")
            await page.goto('https://synergia.librus.pl/przegladaj_oceny/uczen', timeout=config.page_timeout_ms, wait_until='networkidle')
            print(f"{Colors.GREEN}Page loaded{Colors.ENDC}")
            
            print(f"{Colors.BLUE}Running scraper...{Colors.ENDC}")
            try:
                result = await scrape_librus_data(page, last_scrape, is_first)
            except Exception as e:
                # Check if it's a session expired error
                if "SESSION_EXPIRED" in str(e):
                    await context.close()
                    await browser.close()
                    print(f"\n{Colors.BOLD}{Colors.RED}Session expired for {child_name} (detected during scraping){Colors.ENDC}")
                    print(f"{Colors.YELLOW}Use manual_login tool to refresh login session.{Colors.ENDC}\n")
                    
                    return {
                        "status": "session_expired",
                        "child_name": child_name,
                        "message": f"Session expired during scraping. Manual login required.",
                        "mode": "full" if force_full else "delta",
                        "stats": {}
                    }
                else:
                    raise
            
            print(f"{Colors.GREEN}Scraping complete{Colors.ENDC}")
            
            # Update state
            now = datetime.now()
            state["last_scrape_iso"] = now.strftime("%Y-%m-%d %H:%M:%S")
            save_state(child_name, state)
            
            # Save data in monthly pickle format
            save_monthly_data(child_name, now.year, now.month, {
                "timestamp": now.isoformat(),
                "data": result,
                "mode": "delta" if not force_full else "full"
            })
            
            # Save results (backward compatibility)
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
            
    except Exception as e:
        print(f"\n{Colors.BOLD}{Colors.RED}Error: {str(e)}{Colors.ENDC}\n")
        raise e


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
            name="get_homework_summary",
            description="Get homework assignments and deadlines for a child",
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
            name="get_remarks_summary", 
            description="Get teacher remarks and notes for a child",
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
            name="get_messages_summary",
            description="Get messages from teachers for a child", 
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
            name="analyze_grade_trends",
            description="Analyze grade trends and calculate averages for a child",
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
            name="generate_pdf_report",
            description="Generate PDF report from markdown content and save to file",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Markdown content to convert to PDF"
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Path where to save PDF file",
                        "default": "~/Desktop/family_report.pdf"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="generate_family_report",
            description="Generate comprehensive family report with all children",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["weekly", "monthly"],
                        "description": "Type of report to generate",
                        "default": "weekly"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_grades_summary",
            description="Get grades summary for a child (recent grades, averages, trends)",
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
            name="get_homework_summary",
            description="Get homework assignments and deadlines for a child",
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
            name="get_remarks_summary",
            description="Get teacher remarks and notes for a child",
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
            name="get_messages_summary",
            description="Get messages from teachers for a child",
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
            name="get_calendar_events",
            description="Get upcoming calendar events for a child",
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
            name="manual_login",
            description="Trigger manual login for a child when auto-login fails",
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
    
    elif name == "analyze_grade_trends":
        child_name = arguments["child_name"]
        try:
            data = get_recent_months_data(child_name, 2)
            if not data:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
            
            # Extract grades from recent data
            all_grades = []
            for month_data in data.values():
                if 'data' in month_data and 'rawData' in month_data['data']:
                    grades = month_data['data']['rawData'].get('grades', [])
                    all_grades.extend(grades)
            
            # Analyze trends by subject
            subjects = {}
            for grade in all_grades:
                subject = grade.get('subject', 'Unknown')
                if subject not in subjects:
                    subjects[subject] = []
                
                # Convert grade to numeric (handle Polish grading system)
                grade_str = grade.get('grade', '')
                numeric_grade = None
                if grade_str.isdigit():
                    numeric_grade = int(grade_str)
                elif '+' in grade_str:
                    base = grade_str.replace('+', '')
                    if base.isdigit():
                        numeric_grade = int(base) + 0.5
                elif '-' in grade_str:
                    base = grade_str.replace('-', '')
                    if base.isdigit():
                        numeric_grade = int(base) - 0.5
                
                if numeric_grade:
                    subjects[subject].append({
                        'grade': numeric_grade,
                        'original': grade_str,
                        'date': grade.get('date', ''),
                        'category': grade.get('category', ''),
                        'weight': grade.get('weight', '')
                    })
            
            # Calculate trends and averages
            analysis = {}
            for subject, grades in subjects.items():
                if len(grades) < 2:
                    continue
                    
                # Sort by date (if available)
                sorted_grades = sorted(grades, key=lambda x: x['date'] or '1900-01-01')
                
                # Calculate average
                avg = sum(g['grade'] for g in grades) / len(grades)
                
                # Calculate trend (last 3 vs first 3 grades)
                recent = sorted_grades[-3:] if len(sorted_grades) >= 3 else sorted_grades
                early = sorted_grades[:3] if len(sorted_grades) >= 3 else sorted_grades
                
                recent_avg = sum(g['grade'] for g in recent) / len(recent)
                early_avg = sum(g['grade'] for g in early) / len(early)
                trend = recent_avg - early_avg
                
                # Determine trend direction
                if trend > 0.3:
                    trend_desc = "IMPROVING"
                elif trend < -0.3:
                    trend_desc = "DECLINING"
                else:
                    trend_desc = "STABLE"
                
                analysis[subject] = {
                    "total_grades": len(grades),
                    "average": round(avg, 2),
                    "trend_value": round(trend, 2),
                    "trend_direction": trend_desc,
                    "recent_grades": [g['original'] for g in sorted_grades[-5:]],
                    "grade_sequence": " → ".join([g['original'] for g in sorted_grades])
                }
            
            return [TextContent(type="text", text=json.dumps(analysis, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error analyzing trends: {str(e)}")]
    
    elif name == "generate_pdf_report":
        content = arguments.get("content", "")
        output_path = arguments.get("output_path", "~/Desktop/family_report.pdf")
        
        # Expand ~ to home directory
        from pathlib import Path
        output_path = str(Path(output_path).expanduser())
        
        if not content:
            return [TextContent(type="text", text="Error: No content provided for PDF generation")]
        
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
            from reportlab.lib.colors import HexColor
            import re
            
            # Register Polish font - use UTF-8 encoding
            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            
            font_name = 'Helvetica'
            font_bold = 'Helvetica-Bold'
            
            # Try to use system fonts that support Polish
            try:
                # Try Times New Roman (usually has Polish support)
                pdfmetrics.registerFont(TTFont('TimesNewRoman', '/System/Library/Fonts/Supplemental/Times New Roman.ttf'))
                pdfmetrics.registerFont(TTFont('TimesNewRoman-Bold', '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'))
                font_name = 'TimesNewRoman'
                font_bold = 'TimesNewRoman-Bold'
            except:
                try:
                    # Try Verdana
                    pdfmetrics.registerFont(TTFont('Verdana', '/System/Library/Fonts/Supplemental/Verdana.ttf'))
                    pdfmetrics.registerFont(TTFont('Verdana-Bold', '/System/Library/Fonts/Supplemental/Verdana Bold.ttf'))
                    font_name = 'Verdana'
                    font_bold = 'Verdana-Bold'
                except:
                    # Last resort - use Helvetica but ensure UTF-8
                    pass
            
            # Create PDF with margins
            doc = SimpleDocTemplate(
                output_path, 
                pagesize=A4,
                leftMargin=0.75*inch,
                rightMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
            story = []
            
            # Custom styles with Polish font
            title_style = ParagraphStyle(
                'CustomTitle',
                fontName=font_bold,
                fontSize=18,
                leading=22,
                spaceAfter=24,
                textColor=HexColor('#2C3E50'),
                alignment=TA_CENTER
            )
            
            heading1_style = ParagraphStyle(
                'CustomHeading1',
                fontName=font_bold,
                fontSize=14,
                leading=18,
                spaceAfter=12,
                spaceBefore=16,
                textColor=HexColor('#34495E')
            )
            
            heading2_style = ParagraphStyle(
                'CustomHeading2',
                fontName=font_bold,
                fontSize=12,
                leading=16,
                spaceAfter=10,
                spaceBefore=12,
                textColor=HexColor('#7F8C8D')
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                fontName=font_name,
                fontSize=10,
                leading=13,
                spaceAfter=4,
                alignment=TA_JUSTIFY
            )
            
            bullet_style = ParagraphStyle(
                'CustomBullet',
                fontName=font_name,
                fontSize=10,
                leading=13,
                spaceAfter=3,
                leftIndent=20,
                bulletIndent=10
            )
            
            # Parse markdown content
            lines = content.split('\n')
            skip_next_space = False
            
            for line in lines:
                line = line.strip()
                
                # Skip empty lines after headers
                if not line:
                    if not skip_next_space:
                        story.append(Spacer(1, 0.08*inch))
                    skip_next_space = False
                    continue
                
                # Escape HTML special chars but preserve our tags
                line = line.replace('&', '&amp;').replace('<br>', '<br/>')
                
                # Convert markdown formatting
                # Bold: **text** -> <b>text</b>
                line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
                # Italic: *text* -> <i>text</i>
                line = re.sub(r'\*([^*]+?)\*', r'<i>\1</i>', line)
                
                # Headers
                if line.startswith('# '):
                    text = line[2:]
                    story.append(Paragraph(text, title_style))
                    skip_next_space = True
                elif line.startswith('## '):
                    text = line[3:]
                    story.append(Paragraph(text, heading1_style))
                    skip_next_space = True
                elif line.startswith('### '):
                    text = line[4:]
                    story.append(Paragraph(text, heading2_style))
                    skip_next_space = True
                # Lists
                elif line.startswith('- ') or line.startswith('* '):
                    text = line[2:]
                    story.append(Paragraph(f'• {text}', bullet_style))
                # Horizontal rule
                elif line.startswith('---'):
                    story.append(Spacer(1, 0.15*inch))
                # Normal text
                else:
                    story.append(Paragraph(line, normal_style))
            
            # Add Dumbledore's signature at the end (right-aligned)
            try:
                from reportlab.platypus import Image as RLImage, Table
                from reportlab.lib.enums import TA_RIGHT
                import os
                sig_path = os.path.join(os.path.dirname(__file__), 'assets', 'dumbledore_signature.png')
                if os.path.exists(sig_path):
                    story.append(Spacer(1, 0.3*inch))
                    sig = RLImage(sig_path, width=2*inch, height=1*inch, hAlign='RIGHT')
                    # Create a table to right-align the signature
                    sig_table = Table([[sig]], colWidths=[doc.width])
                    sig_table.setStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT')])
                    story.append(sig_table)
            except Exception as e:
                # If signature fails, just skip it
                pass
            
            doc.build(story)
            
            return [TextContent(type="text", text=f"PDF report generated successfully: {output_path}")]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Error generating PDF: {str(e)}")]
    
    elif name == "generate_family_report":
        report_type = arguments.get("report_type", "weekly")
        try:
            # Get all children
            children = list_children()
            
            report_date = datetime.now().strftime("%d.%m.%Y")
            
            report = f"# RAPORT RODZINNY - {report_date}\n\n"
            
            urgent_items = []
            weekly_items = []
            payments_items = []
            shopping_items = []
            
            for child in children:
                child_name = child['name']
                try:
                    # Get data for each child
                    homework_data = get_recent_months_data(child_name, 2)
                    
                    # Extract homework
                    all_homework = []
                    for month_data in homework_data.values() if homework_data else []:
                        if 'data' in month_data and 'homework' in month_data['data']:
                            all_homework.extend(month_data['data']['homework'])
                    
                    # Check for urgent homework (tomorrow)
                    tomorrow = datetime.now() + timedelta(days=1)
                    
                    for hw in all_homework:
                        due_date_str = hw.get('dateDue', '')
                        if due_date_str:
                            try:
                                due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                                if due_date.date() == tomorrow.date():
                                    urgent_items.append(f"**[{child_name.upper()}]** - ZADANIE JUTRO! {hw.get('subject', 'Unknown')} - {hw.get('title', 'sprawdź czy zrobione!')}")
                            except:
                                pass
                    
                    report += f"## {child_name.upper()}\n\n"
                    report += f"### PILNE ACTION POINTS\n"
                    
                    # Add homework analysis
                    urgent_hw = [hw for hw in all_homework if hw.get('dateDue') == tomorrow.strftime('%Y-%m-%d')]
                    if urgent_hw:
                        for hw in urgent_hw:
                            report += f"- ZADANIE JUTRO: {hw.get('subject')} - {hw.get('title')}\n"
                    else:
                        report += "- Brak pilnych zadań na jutro\n"
                    
                    report += f"\n### OSTATNIE OCENY\n"
                    report += "*(Analiza trendów dostępna przez analyze_grade_trends)*\n\n"
                    
                    report += f"### NADCHODZĄCE WYDARZENIA\n"
                    report += "*(Sprawdziany i wydarzenia na 14 dni)*\n\n"
                    
                    report += "---\n\n"
                    
                except Exception as e:
                    report += f"## {child_name.upper()} - Błąd pobierania danych: {str(e)}\n\n"
            
            # Add family summary
            report += "## WSPÓLNE DLA WSZYSTKICH\n\n"
            
            if urgent_items:
                report += "### PILNE NA DZIŚ/JUTRO\n"
                for item in urgent_items:
                    report += f"- {item}\n"
                report += "\n"
            
            report += "### PŁATNOŚCI DO SPRAWDZENIA\n"
            report += "- Obiady szkolne\n"
            report += "- Składki klasowe\n"
            report += "- Wycieczki\n\n"
            
            report += "### ZAKUPY WEEKEND\n"
            report += "- Materiały szkolne\n"
            report += "- Stroje na wydarzenia\n\n"
            
            report += "### PODSUMOWANIE NA LODÓWKĘ\n"
            if urgent_items:
                report += "**PILNE:**\n"
                for item in urgent_items[:3]:  # Max 3 items for fridge
                    report += f"• {item.replace('**', '').replace('[', '').replace(']', '')}\n"
            else:
                report += "• Wszystko pod kontrolą!\n"
            
            return [TextContent(type="text", text=report)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error generating family report: {str(e)}")]
    
    elif name == "get_homework_summary":
        child_name = arguments["child_name"]
        try:
            data = get_recent_months_data(child_name, 2)
            if not data:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
            
            # Extract homework from recent data
            all_homework = []
            for month_data in data.values():
                if 'data' in month_data and 'homework' in month_data['data']:
                    homework = month_data['data']['homework']
                    all_homework.extend(homework)
            
            # Sort by due date and categorize (14 days ahead)
            now = datetime.now()
            tomorrow = now + timedelta(days=1)
            this_week = now + timedelta(days=7)
            two_weeks = now + timedelta(days=14)
            
            urgent = []  # Due today/tomorrow
            upcoming_week = []  # Due this week
            upcoming_two_weeks = []  # Due within 14 days
            overdue = []
            
            for hw in all_homework:
                due_date_str = hw.get('dateDue', '')
                if due_date_str:
                    try:
                        due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                        if due_date < now:
                            overdue.append(hw)
                        elif due_date <= tomorrow:
                            urgent.append(hw)
                        elif due_date <= this_week:
                            upcoming_week.append(hw)
                        elif due_date <= two_weeks:
                            upcoming_two_weeks.append(hw)
                    except:
                        upcoming_week.append(hw)  # If can't parse, include in upcoming
            
            summary = {
                "total_homework": len(all_homework),
                "overdue": overdue,
                "urgent_today_tomorrow": urgent,
                "upcoming_this_week": upcoming_week,
                "upcoming_14_days": upcoming_two_weeks
            }
            
            return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting homework: {str(e)}")]
    
    elif name == "get_remarks_summary":
        child_name = arguments["child_name"]
        try:
            data = get_recent_months_data(child_name, 2)
            if not data:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
            
            # Extract remarks from recent data
            all_remarks = []
            for month_data in data.values():
                if 'data' in month_data and 'rawData' in month_data['data']:
                    remarks = month_data['data']['rawData'].get('remarks', [])
                    all_remarks.extend(remarks)
            
            # Categorize remarks
            positive = []
            negative = []
            neutral = []
            
            for remark in all_remarks:
                content = remark.get('content', '').lower()
                if any(word in content for word in ['dobr', 'świetn', 'wzorn', 'aktywn', 'pomoc']):
                    positive.append(remark)
                elif any(word in content for word in ['brak', 'nie', 'źle', 'słab', 'problem']):
                    negative.append(remark)
                else:
                    neutral.append(remark)
            
            summary = {
                "total_remarks": len(all_remarks),
                "recent_remarks": all_remarks[-5:] if all_remarks else [],  # Last 5
                "positive": positive,
                "negative": negative,
                "neutral": neutral
            }
            
            return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting remarks: {str(e)}")]
    
    elif name == "get_messages_summary":
        child_name = arguments["child_name"]
        try:
            data = get_recent_months_data(child_name, 2)
            if not data:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
            
            # Extract messages from recent data
            all_messages = []
            for month_data in data.values():
                if 'data' in month_data and 'rawData' in month_data['data']:
                    messages = month_data['data']['rawData'].get('messages', [])
                    all_messages.extend(messages)
            
            # Sort by date and get recent ones
            recent_messages = sorted(all_messages, key=lambda x: x.get('date', ''), reverse=True)[:15]
            
            # Check for unread or requiring response
            unread = [msg for msg in recent_messages if msg.get('isNew', False)]
            
            # Detect messages requiring response (keywords in content)
            requiring_response = []
            response_keywords = [
                'proszę o odpowiedź', 'proszę potwierdzić', 'czy może', 'czy mogłaby', 'czy mógłby',
                'proszę o informację', 'proszę o kontakt', 'proszę o zgłoszenie', 'proszę o przesłanie',
                'czy zgadza się', 'czy wyrażają państwo zgodę', 'proszę o podpisanie',
                'termin', 'deadline', 'do kiedy', 'najpóźniej', 'wymagana odpowiedź'
            ]
            
            for msg in recent_messages:
                content = msg.get('content', '').lower()
                if any(keyword in content for keyword in response_keywords):
                    requiring_response.append(msg)
            
            # Also check subject for response indicators
            for msg in recent_messages:
                subject = msg.get('subject', '').lower()
                if any(word in subject for word in ['zgoda', 'potwierdzenie', 'odpowiedź', 'prośba']):
                    if msg not in requiring_response:
                        requiring_response.append(msg)
            
            summary = {
                "total_messages": len(all_messages),
                "recent_messages": recent_messages,
                "unread_count": len(unread),
                "unread_messages": unread,
                "requiring_response_count": len(requiring_response),
                "requiring_response": requiring_response
            }
            
            return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting messages: {str(e)}")]
    
    elif name == "get_grades_summary":
        child_name = arguments["child_name"]
        try:
            data = get_recent_months_data(child_name, 2)
            if not data:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
            
            # Extract grades from recent data
            all_grades = []
            for month_data in data.values():
                if 'data' in month_data and 'rawData' in month_data['data']:
                    grades = month_data['data']['rawData'].get('grades', [])
                    all_grades.extend(grades)
            
            # Create summary
            summary = {
                "total_grades": len(all_grades),
                "recent_grades": all_grades[-10:] if all_grades else [],  # Last 10 grades
                "subjects": {}
            }
            
            # Group by subject
            for grade in all_grades:
                subject = grade.get('subject', 'Unknown')
                if subject not in summary["subjects"]:
                    summary["subjects"][subject] = []
                summary["subjects"][subject].append(grade)
            
            return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting grades: {str(e)}")]
    
    elif name == "get_calendar_events":
        child_name = arguments["child_name"]
        try:
            data = get_recent_months_data(child_name, 2)
            if not data:
                return [TextContent(type="text", text=f"No recent data found for {child_name}")]
            
            # Extract calendar events
            all_events = []
            for month_data in data.values():
                if 'data' in month_data and 'rawData' in month_data['data']:
                    events = month_data['data']['rawData'].get('calendar', [])
                    all_events.extend(events)
            
            # Sort by date and get upcoming events (14 days ahead)
            now = datetime.now()
            two_weeks = now + timedelta(days=14)
            upcoming_events = []
            
            for event in all_events:
                event_date_str = event.get('date', '')
                if event_date_str:
                    try:
                        # Parse date and check if within 14 days
                        event_date = datetime.strptime(event_date_str, '%Y-%m-%d')
                        if now <= event_date <= two_weeks:
                            upcoming_events.append(event)
                    except:
                        # If date parsing fails, include anyway
                        upcoming_events.append(event)
            
            summary = {
                "total_events": len(all_events),
                "upcoming_14_days": sorted(upcoming_events, key=lambda x: x.get('date', ''))
            }
            
            return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting calendar: {str(e)}")]
    
    elif name == "manual_login":
        child_name = arguments["child_name"]
        try:
            # Remove old cookies to force manual login
            context_dir = get_context_dir(child_name)
            cookies_file = context_dir / "cookies.json"
            if cookies_file.exists():
                cookies_file.unlink()
            
            # Show clear message about which child is being logged in
            print(f"\n{Colors.BOLD}{Colors.YELLOW}=== MANUAL LOGIN FOR {child_name.upper()} ==={Colors.ENDC}")
            print(f"{Colors.YELLOW}Opening browser for {child_name} login only.{Colors.ENDC}")
            print(f"{Colors.YELLOW}Please log in as parent for {child_name} and close browser when done.{Colors.ENDC}\n")
            
            # Do a minimal login-only scrape
            async with async_playwright() as p:
                browser = await p.webkit.launch(headless=False)
                
                context = await browser.new_context()
                page = await context.new_page()
                
                await page.goto('https://portal.librus.pl/rodzina/synergia/loguj')
                print(f"{Colors.YELLOW}Waiting for login for {child_name}...{Colors.ENDC}")
                
                # Wait for successful login
                await page.wait_for_url(lambda url: '/rodzic' in url, timeout=300000)  # 5 min timeout
                print(f"{Colors.GREEN}Login successful for {child_name}!{Colors.ENDC}")
                
                # Save cookies
                await context.storage_state(path=str(cookies_file))
                
                await context.close()
                await browser.close()
            
            return [TextContent(type="text", text=f"Manual login completed for {child_name}. Session saved. You can now scrape data.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Manual login failed for {child_name}: {str(e)}")]
    
    elif name == "scrape_librus":
        child_name = arguments["child_name"]
        force_full = arguments.get("force_full", False)
        
        result = await scrape_librus(child_name, force_full)
        
        if result.get("status") == "session_expired":
            return [TextContent(
                type="text",
                text=f"❌ Session expired for {result['child_name']}. Use manual_login tool to refresh."
            )]
        
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
