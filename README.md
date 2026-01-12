# Librus MCP Server

MCP (Model Context Protocol) server for scraping Polish school system data from Librus Synergia.

## Architecture

This project follows **Clean Architecture** (Ports & Adapters / DDD):

```
src/
├── domain/           # Core business logic (no external dependencies)
│   ├── models/       # Entities: Child, Grade, Homework, CalendarEvent, etc.
│   └── services/     # GradeAnalyzer, HomeworkTracker, CalendarAnalyzer
├── ports/            # Abstract interfaces
│   └── __init__.py   # IBrowserPort, IStoragePort, IConfigPort
├── adapters/         # Implementations
│   ├── browser.py    # PlaywrightBrowserAdapter
│   ├── storage.py    # FileStorageAdapter
│   └── config.py     # YamlConfigAdapter
├── application/      # Use cases
│   └── __init__.py   # ScrapeChild, LoginChild, AnalyzeGrades, etc.
└── infrastructure/   # MCP server wiring
    └── mcp_server.py # LibrusMcpServer
```

## Features

- **Automated login** - Configurable credentials per child
- **Full data scraping** - Grades, homework, calendar, messages, remarks
- **Delta mode** - Only fetch new data since last scrape
- **Multi-child support** - Manage multiple children with aliases
- **Grade analysis** - Trends, averages, at-risk subjects
- **Clean architecture** - Testable, maintainable, extensible

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
| `get_calendar_events` | Get upcoming events and tests |
| `get_homework_summary` | Get homework assignments |
| `get_messages_summary` | Get messages from teachers |
| `get_remarks_summary` | Get teacher remarks |
| `analyze_grade_trends` | Analyze trends, averages, at-risk subjects |
| `list_children` | List configured children |

## Testing

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=term-missing
```

Current: **81 tests, 71% coverage**

## Data Storage

All data stored in `~/.librus_scraper/<child>/`:
- `browser_context/cookies.json` - Session
- `state.json` - Last scrape timestamp
- `memory.json` - Grade history, trends
- `YYYY-MM.pkl` - Monthly data snapshots

## License

MIT
