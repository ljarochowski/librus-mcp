# Librus MCP Server

MCP (Model Context Protocol) server for scraping Polish school system data from Librus Synergia.

## Features

- **Auto-login** - Saves browser session, no manual login after first setup
- **Full data scraping** - Messages (with pagination), announcements, grades, calendar events
- **Delta mode** - Only fetch new data since last scrape
- **Multi-child support** - Manage multiple children with aliases
- **Memory tracking** - Track grade history and trends
- **Headless mode** - Runs in background after initial setup
- **Colored console output** - Easy to read progress indicators

## Installation

```bash
# Clone repository
git clone https://github.com/yourusername/librus-mcp.git
cd librus-mcp

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install webkit

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your settings and Librus credentials
```

## Configuration

Create `config.yaml` based on the example:

```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your settings and credentials
```

Example configuration:

```yaml
# Browser settings
browser:
  login_timeout_ms: 120000
  page_timeout_ms: 30000

# Scraping limits
scraping:
  max_messages: 200
  max_announcements: 150

# Children credentials
children:
  - name: "Jakub"
    aliases: ["Kuba"]
    login: "your_librus_login"
    password: "your_librus_password"
```

**Security:** `config.yaml` contains credentials and is excluded from git. Scraped data is stored in `~/.librus_scraper/` (outside the repository).

## Usage

### As MCP Server

Add to your MCP client configuration (e.g., Claude Desktop `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "librus": {
      "command": "python",
      "args": ["/absolute/path/to/librus-mcp/server.py"]
    }
  }
}
```

### Direct Usage (Console)

```bash
# Activate virtual environment
source venv/bin/activate

# Run scraper directly
python3 -c "
import asyncio
from server import scrape_librus

async def main():
    result = await scrape_librus('Jakub', force_full=True)
    print(f'Scraped: {result[\"stats\"]}')

asyncio.run(main())
"
```

### Available MCP Tools

1. **scrape_librus** - Scrape Librus data for a child
   - `child_name` (required): Child name or alias
   - `force_full` (optional): Force full scan instead of delta

2. **get_memory** - Get stored memory and trends
   - `child_name` (required): Child name or alias

3. **save_analysis** - Save insight or note to memory
   - `child_name` (required): Child name or alias
   - `analysis_type` (required): "issue", "action_item", or "parent_note"
   - `content` (required): Note content

4. **list_children** - List all configured children with last scan dates

## Project Structure

```
librus-mcp/
├── server.py                  # Main MCP server
├── src/
│   ├── config.py              # Configuration and constants
│   ├── credentials.py         # Credentials management
│   ├── storage.py             # File storage operations
│   ├── scraper.py             # Scraping orchestration
│   ├── scraper_js.py          # JavaScript scraping code
│   └── memory.py              # Memory and trends tracking
├── tests/
│   ├── test_credentials.py    # Credentials tests
│   └── test_storage.py        # Storage tests
├── credentials.json.example   # Example credentials file
├── requirements.txt           # Python dependencies
├── pyproject.toml            # Pytest configuration
├── LICENSE                    # MIT License
└── README.md                  # This file
```

## Data Storage

All data is stored in `~/.librus_scraper/<child-name>/`:

- `browser_context/cookies.json` - Browser session (auto-login)
- `state.json` - Scraping state (last scan date, etc.)
- `memory.json` - Trends, notes, grade history
- `latest.md` - Latest scraped data in Markdown format

## Development

```bash
# Run tests
pytest tests/ -v

# Run specific test file
pytest tests/test_credentials.py -v

# Check code with type hints
mypy src/ server.py
```

## Security Notes

- **Never commit `credentials.json`** - It contains login credentials
- **Never commit `~/.librus_scraper/`** - It contains personal data
- All sensitive data is stored outside the repository
- `.gitignore` is configured to prevent accidental commits
- Browser sessions are encrypted by Playwright

## How It Works

1. **First Run**: Opens browser, you log in manually, session is saved
2. **Subsequent Runs**: Uses saved session, runs headless (no GUI)
3. **Scraping**: JavaScript code runs in browser context to extract data
4. **Delta Mode**: Only fetches new data since last scrape (configurable)
5. **Storage**: Saves data as Markdown and JSON for easy access

## Troubleshooting

### "No credentials found"
- Make sure `credentials.json` exists and is properly formatted
- Check that child name matches exactly (case-insensitive)

### "Login failed"
- Verify credentials are correct in `credentials.json`
- Try deleting `~/.librus_scraper/<child-name>/browser_context/` and run again
- Check if Librus website is accessible

### "No data scraped"
- Check if there's actually data in Librus (log in manually to verify)
- Try with `force_full=True` to do a complete rescan
- Check console output for specific errors

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest tests/ -v`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Disclaimer

This tool is for personal use only. Ensure you comply with Librus terms of service and applicable data protection laws (GDPR, etc.). The authors are not responsible for any misuse of this software.

## Support

For issues, questions, or contributions, please open an issue on GitHub.
