# Librus MCP Server

MCP (Model Context Protocol) server for scraping Polish school system data from Librus Synergia.

## Project Structure

```
src/
├── domain/           # Business logic and data models
│   ├── models/       # Child, Grade, Homework, CalendarEvent, etc.
│   └── services/     # GradeAnalyzer, HomeworkTracker, CalendarAnalyzer
├── ports/            # Interface definitions
├── adapters/         # External service implementations
│   ├── browser.py    # Web scraping with Playwright
│   ├── storage.py    # File-based data storage
│   └── config.py     # YAML configuration
├── application/      # Use cases and workflows
└── infrastructure/   # MCP server setup
```

## Features

- **Automated login** - Store credentials per child for hands-free operation
- **Complete data extraction** - Grades, homework, calendar, messages, remarks
- **Incremental updates** - Only fetch new data since last scrape
- **Multi-child support** - Manage multiple children with aliases
- **Grade analysis** - Calculate trends, averages, identify at-risk subjects
- **PDF reports** - Generate formatted letters with Dumbledore signature

## Installation

```bash
git clone https://github.com/yourusername/librus-mcp.git
cd librus-mcp

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
playwright install webkit

cp config.yaml.example config.yaml
# Edit config.yaml with your children
```

## Configuration

Edit `config.yaml`:

```yaml
children:
  - name: "Child1"
    aliases: ["Nickname"]
    # Optional: for automated login
    username: "librus_login"
    password: "librus_password"
```

`config.yaml` is gitignored - credentials stay local.

## Usage

### With Kiro CLI (Professor Dumbledore Agent)

The repo includes a "Professor Dumbledore" agent that writes warm, insightful letters to parents about their children's school progress.

```bash
# Copy agent config
mkdir -p ~/.kiro/agents
cp dumbledore-agent.json ~/.kiro/agents/

# Edit paths in the config, then:
kiro-cli --agent dumbledore
```

See `agent/` folder for:
- `dumbledore_prompt.md` - Agent system prompt
- `character.md` - Dumbledore's character profile
- `dumbledore-agent.json` - Kiro CLI agent config

### As MCP Server

Add to your MCP client config:

```json
{
  "mcpServers": {
    "librus": {
      "command": "python3",
      "args": ["/path/to/librus-mcp/server.py"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `scrape_librus` | Scrape data for a child |
| `manual_login` | Trigger login (uses config credentials) |
| `get_grades_summary` | Get grades with semester breakdown |
| `get_grade_details_by_date` | Get detailed grades for specific date range |
| `get_teacher_subject_mapping` | Get teacher to subject mapping |
| `get_semester_grades_summary` | Get semester/final grades only |
| `get_calendar_events` | Get upcoming events and tests |
| `get_homework_summary` | Get homework assignments |
| `get_messages_summary` | Get messages from teachers (enhanced with full content) |
| `get_remarks_summary` | Get teacher remarks |
| `get_recent_activity_delta` | Get summary of changes since date |
| `analyze_grade_trends` | Analyze trends, averages, at-risk subjects |
| `analyze_urgent_matters` | AI-powered urgency analysis |
| `generate_pdf_report` | Generate PDF with Dumbledore signature |
| `list_children` | List configured children |

## Testing

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=term-missing
```

Current: **96 tests, 73% coverage**

## Data Storage

All data stored in `~/.librus_scraper/<child>/`:
- `browser_context/cookies.json` - Session
- `state.json` - Last scrape timestamp
- `memory.json` - Grade history, trends
- `YYYY-MM.pkl` - Monthly data snapshots

## License

MIT
