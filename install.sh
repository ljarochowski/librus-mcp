#!/bin/bash
set -e

echo "🧙 Professor Dumbledore - Librus MCP Server Setup"
echo "================================================="
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check dependencies
echo "Checking dependencies..."
command -v python3 >/dev/null || { echo "❌ python3 required"; exit 1; }
command -v pip3 >/dev/null || { echo "❌ pip3 required"; exit 1; }
echo "✓ Python found"

# Create venv if needed
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
fi
source "$SCRIPT_DIR/venv/bin/activate"

# Install dependencies
echo "Installing dependencies..."
pip install -q -r "$SCRIPT_DIR/requirements.txt"
playwright install webkit >/dev/null 2>&1 || echo "⚠ Run 'playwright install webkit' manually if needed"
echo "✓ Dependencies installed"
echo

# Config setup
CONFIG_FILE="$SCRIPT_DIR/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    echo "⚠ config.yaml already exists. Skipping config creation."
    echo "  Edit manually if needed: $CONFIG_FILE"
else
    echo "📝 Let's configure your children..."
    echo
    
    echo "children:" > "$CONFIG_FILE"
    
    while true; do
        read -p "Child's name (or 'done' to finish): " name
        [ "$name" = "done" ] && break
        [ -z "$name" ] && continue
        
        read -p "  Aliases (comma-separated, or empty): " aliases
        read -p "  Librus username (or empty for manual login): " username
        
        echo "  - name: \"$name\"" >> "$CONFIG_FILE"
        if [ -n "$aliases" ]; then
            echo "    aliases: [$(echo "$aliases" | sed 's/,/", "/g' | sed 's/^/"/;s/$/"/')]" >> "$CONFIG_FILE"
        fi
        if [ -n "$username" ]; then
            read -s -p "  Librus password: " password
            echo
            echo "    username: \"$username\"" >> "$CONFIG_FILE"
            echo "    password: \"$password\"" >> "$CONFIG_FILE"
        fi
        echo
    done
    echo "✓ Config saved to $CONFIG_FILE"
fi
echo

# Kiro agent setup
read -p "Install Kiro CLI agent? (y/n): " install_agent
if [ "$install_agent" = "y" ]; then
    KIRO_DIR="$HOME/.kiro/agents"
    mkdir -p "$KIRO_DIR"
    
    AGENT_FILE="$KIRO_DIR/professor-dumbledore.json"
    if [ -f "$AGENT_FILE" ]; then
        echo "⚠ Agent already exists at $AGENT_FILE"
        read -p "  Overwrite? (y/n): " overwrite
        [ "$overwrite" != "y" ] && install_agent="n"
    fi
    
    if [ "$install_agent" = "y" ]; then
        # Context directory
        read -p "Context directory (default: ~/.context/dumbledore): " context_dir
        context_dir="${context_dir:-$HOME/.context/dumbledore}"
        context_dir="${context_dir/#\~/$HOME}"
        mkdir -p "$context_dir"
        
        # Copy character.md if not exists
        if [ ! -f "$context_dir/character.md" ]; then
            cp "$SCRIPT_DIR/agent/character.md" "$context_dir/"
            echo "✓ Character profile copied to $context_dir/character.md"
            echo "  (Customize it with your children's names and details)"
        fi
        
        # Create agent config
        cat > "$AGENT_FILE" << EOF
{
  "name": "professor-dumbledore",
  "description": "Professor Dumbledore writes warm, insightful letters to Polish parents about their children's school progress",
  "prompt": "file://$SCRIPT_DIR/agent/dumbledore_prompt.md",
  "mcpServers": {
    "librus": {
      "command": "$SCRIPT_DIR/venv/bin/python3",
      "args": ["$SCRIPT_DIR/server.py"]
    }
  },
  "tools": ["read", "@librus"],
  "allowedTools": ["read", "@librus"],
  "resources": [
    "file://$context_dir/**/*.md",
    "file://$HOME/.librus_scraper/**/*.md",
    "file://$HOME/.librus_scraper/**/*.json"
  ],
  "model": "claude-sonnet-4-5"
}
EOF
        echo "✓ Agent installed: $AGENT_FILE"
    fi
fi
echo

echo "🎉 Setup complete!"
echo
echo "Usage:"
echo "  • MCP Server: python3 $SCRIPT_DIR/server.py"
[ "$install_agent" = "y" ] && echo "  • Kiro Agent: kiro-cli --agent professor-dumbledore"
echo
