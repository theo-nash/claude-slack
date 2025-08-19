#!/bin/bash
# Integration test for Claude-Slack installation

set -e

echo "Claude-Slack Integration Test"
echo "=============================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Test directory (temporary)
TEST_DIR="/tmp/claude-slack-test-$$"
BACKUP_DIR="/tmp/claude-backup-$$"

# Cleanup function
cleanup() {
    echo -e "\nCleaning up test environment..."
    # Restore any backed up files
    if [ -d "$BACKUP_DIR" ]; then
        if [ -d "$BACKUP_DIR/.claude" ]; then
            cp -r "$BACKUP_DIR/.claude"/* ~/.claude/ 2>/dev/null || true
        fi
        rm -rf "$BACKUP_DIR"
    fi
    rm -rf "$TEST_DIR"
}

# Set trap for cleanup
trap cleanup EXIT

echo "1. Setting up test environment..."
mkdir -p "$TEST_DIR"

# Backup existing .claude directory if it exists
if [ -d ~/.claude ]; then
    echo "   Backing up existing ~/.claude directory..."
    mkdir -p "$BACKUP_DIR"
    cp -r ~/.claude "$BACKUP_DIR/.claude"
fi

echo -e "${GREEN}✓${NC} Test environment ready"

echo
echo "2. Testing global installation..."

# Run the installer in test mode
cd "$(dirname "$0")/.."
node bin/install.js --test 2>&1 | tee "$TEST_DIR/install.log"

# Check if installation succeeded
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Installation completed"
else
    echo -e "${RED}✗${NC} Installation failed"
    exit 1
fi

echo
echo "3. Verifying installed components..."

# Check global MCP server
if [ -f ~/.claude/mcp/claude-slack/server.py ]; then
    echo -e "${GREEN}✓${NC} MCP server installed"
else
    echo -e "${RED}✗${NC} MCP server not found"
    exit 1
fi

# Check database
if [ -f ~/.claude/data/claude-slack.db ]; then
    echo -e "${GREEN}✓${NC} Database created"
else
    echo -e "${RED}✗${NC} Database not found"
    exit 1
fi

# Check hooks
if [ -f ~/.claude/hooks/slack_pre_tool_use.py ]; then
    echo -e "${GREEN}✓${NC} PreToolUse hook installed"
else
    echo -e "${RED}✗${NC} PreToolUse hook not found"
    exit 1
fi

# Check commands
for cmd in slack-status slack-inbox slack-send; do
    if [ -f ~/.claude/commands/$cmd.md ]; then
        echo -e "${GREEN}✓${NC} Command $cmd installed"
    else
        echo -e "${RED}✗${NC} Command $cmd not found"
        exit 1
    fi
done

# Check Python virtual environment
if [ -d ~/.claude/mcp/claude-slack/venv ]; then
    echo -e "${GREEN}✓${NC} Python virtual environment created"
else
    echo -e "${RED}✗${NC} Python virtual environment not found"
    exit 1
fi

# Check MCP settings update
if grep -q "claude-slack" ~/.claude/mcp/settings.json 2>/dev/null; then
    echo -e "${GREEN}✓${NC} MCP settings updated"
else
    echo -e "${RED}✗${NC} MCP settings not updated"
    exit 1
fi

echo
echo "4. Testing Python components..."

# Test database manager
python3 -c "
import sys
sys.path.insert(0, '$HOME/.claude/mcp/claude-slack')
try:
    from db.manager import DatabaseManager
    print('✓ Database manager imports correctly')
except Exception as e:
    print(f'✗ Failed to import database manager: {e}')
    sys.exit(1)
"

# Test frontmatter parser
python3 -c "
import sys
sys.path.insert(0, '$HOME/.claude/mcp/claude-slack')
try:
    from frontmatter.parser import FrontmatterParser
    print('✓ Frontmatter parser imports correctly')
except Exception as e:
    print(f'✗ Failed to import frontmatter parser: {e}')
    sys.exit(1)
"

echo
echo "5. Testing database operations..."

# Test database initialization
python3 -c "
import sys
import asyncio
sys.path.insert(0, '$HOME/.claude/mcp/claude-slack')

async def test_db():
    from db.manager import DatabaseManager
    
    db = DatabaseManager('$HOME/.claude/data/claude-slack.db')
    await db.initialize()
    
    # Test creating a channel
    await db.create_channel('test-channel', 'global', 'Test channel')
    print('✓ Created test channel')
    
    # Test listing channels
    channels = await db.list_channels('global')
    if any(c['name'] == 'test-channel' for c in channels):
        print('✓ Channel listed correctly')
    else:
        print('✗ Channel not found in list')
        sys.exit(1)
    
    await db.close()

asyncio.run(test_db())
"

echo
echo "=============================="
echo -e "${GREEN}All integration tests passed!${NC}"
echo
echo "Claude-Slack has been successfully tested."
echo "The system is ready for use."