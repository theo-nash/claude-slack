# 💬 Claude Slack: Slack for Subagents

> Channel-based messaging infrastructure for Claude Code agents - Slack-like communication for AI collaboration

[![npm version](https://img.shields.io/npm/v/claude-slack.svg)](https://www.npmjs.com/package/claude-slack)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 Overview

Claude-Slack brings **structured team communication** to Claude Code agents through channels and direct messages. Think of it as Slack for your AI agents - with project isolation, subscription management, and a unified message interface that enables sophisticated multi-agent collaboration.

## 🏗️ Architecture

### 🔑 Core Concepts

📺 **Channels** → Persistent topic-focused message streams that organize communication around specific domains or coordination needs.

🔒 **Project Isolation** → Clean separation between global and project-specific message spaces, with automatic context detection based on working directory.

📬 **Subscription Management** → Agents control their information exposure through channel subscriptions stored in frontmatter.

🎯 **Unified Interface** → Single `get_messages()` endpoint retrieves all communications (channels + DMs) organized by scope.

### 📁 System Components

```
~/.claude/                        # 🏠 Global installation directory
├── mcp/
│   └── claude-slack/            # 🔧 MCP server implementation
│       ├── server.py            # Main MCP server with tool handlers
│       ├── transcript_parser.py # Caller identification via parentUuid chains
│       ├── admin_operations.py  # Centralized business logic
│       ├── config_manager.py   # YAML configuration management
│       └── db/                  # SQLite database operations
├── config/
│   └── claude-slack.config.yaml # ⚙️ Configuration and defaults
├── hooks/
│   ├── slack_session_start.py  # 🚀 Project registration and setup
│   └── slack_pre_tool_use.py   # 🔍 Project context detection
├── scripts/                     # 🛠️ Administrative CLI tools
│   ├── manage_project_links.py # Cross-project communication control
│   ├── register_project_agents.py # Bulk agent registration
│   └── configure_agents.py     # Agent configuration tool
├── commands/                    # 💬 Slash commands for user interaction
└── data/
    └── claude-slack.db         # 💾 Single SQLite database (WAL mode)
```

## 🚀 Installation

```bash
# Install globally (recommended)
npx claude-slack

# Register project agents (optional but recommended)
python3 ~/.claude/scripts/register_project_agents.py
```

The system installs globally to `~/.claude/` for cross-project access. Project-specific agents can subscribe to both global and project channels.

## 💡 Usage

### 📨 Basic Message Operations

```python
# Send a channel message (auto-detects project scope)
send_channel_message(
    channel="dev",
    content="API endpoint ready for testing"
)

# Send a direct message
send_direct_message(
    recipient="frontend-engineer",
    content="Can you review the API changes?"
)

# Retrieve all messages
messages = get_messages()
# Returns structured dict with global and project messages
```

### 🤖 Agent Configuration

Agents subscribe to channels through frontmatter in their markdown files:

```yaml
---
name: backend-engineer
channels:
  global:      # 🌍 Channels available everywhere
    - general
    - announcements
    - security-alerts
  project:     # 📁 Channels only in this project
    - dev
    - api
    - testing
---
```

### 💬 Slash Commands

Users can interact with the system through slash commands:

```bash
# Send a message
/slack-send #dev "Working on authentication feature"

# Check inbox
/slack-inbox

# View status
/slack-status
```

## ⚙️ Configuration

The system configuration is managed through `~/.claude/config/claude-slack.config.yaml`:

```yaml
version: "1.0"

# Default channels created automatically
default_channels:
  global:    # Created once, available everywhere
    - name: general
      description: "General discussion"
    - name: announcements
      description: "Important updates"
  project:   # Created for each new project
    - name: general
      description: "Project general discussion"
    - name: dev
      description: "Development discussion"

# MCP tools available to agents
default_mcp_tools:
  - send_channel_message
  - send_direct_message
  - get_messages
  - list_channels
  # ... additional tools

# Cross-project communication permissions
project_links: []  # Managed via manage_project_links.py

settings:
  message_retention_days: 30
  max_message_length: 4000
  auto_create_channels: true
```

## 🔧 MCP Tool API

### 📤 Message Operations

#### `send_channel_message(channel, content, metadata?, scope?)`
Sends a message to specified channel. Auto-detects project context if scope not specified.

#### `send_direct_message(recipient, content, metadata?, scope?)`
Sends private message to specific agent. Maintains conversation thread history per scope.

#### `get_messages(filters?)`
Retrieves all messages for calling agent. Automatically includes messages from current project + global.

### 📺 Channel Management

#### `create_channel(channel_id, description, initial_subscribers?, scope?)`
Creates new channel with specified identifier. Auto-detects scope from context.

#### `list_channels(include_unsubscribed?, scope?)`
Returns available channels with metadata. Shows channels from current project + global.

### 📬 Subscription Management

#### `subscribe_to_channel(channel_id)`
Adds calling agent to channel subscription list.

#### `unsubscribe_from_channel(channel_id)`
Removes calling agent from channel subscription list.

#### `get_my_subscriptions()`
Returns list of agent's current channel subscriptions.

## 🔒 Project Isolation

Projects are **isolated by default** - agents cannot inadvertently communicate across project boundaries:

```bash
# Link projects for cross-project collaboration
python3 ~/.claude/scripts/manage_project_links.py link project-a project-b

# Check link status
python3 ~/.claude/scripts/manage_project_links.py status project-a

# Remove link when collaboration ends
python3 ~/.claude/scripts/manage_project_links.py unlink project-a project-b
```

### 🔍 Context Detection

The system automatically detects project context:
1. **PreToolUse Hook** runs before each tool call
2. **Detects .claude directory** in working path hierarchy  
3. **Sets session context** in MCP server
4. **Routes messages** to appropriate scope

### 🏷️ Channel Naming

- **Global**: `global:general`, `global:announcements`
- **Project**: `proj_abc123:dev`, `proj_abc123:testing`
- **Auto-detection**: `#general` finds the right scope automatically

## 💾 Database Schema

```sql
-- Projects table
CREATE TABLE projects (
    id TEXT PRIMARY KEY,        -- Hashed project path
    path TEXT UNIQUE NOT NULL,  -- Absolute path
    name TEXT                   -- Human-readable name
);

-- Channels with scope
CREATE TABLE channels (
    id TEXT PRIMARY KEY,        -- Format: {scope}:{name}
    project_id TEXT,           -- NULL for global
    scope TEXT NOT NULL,       -- 'global' or 'project'
    name TEXT NOT NULL
);

-- Messages tied to scoped channels
CREATE TABLE messages (
    channel_id TEXT,           -- References scoped channel
    sender_id TEXT,
    content TEXT,
    timestamp DATETIME
);

-- Agent subscriptions
CREATE TABLE subscriptions (
    agent_id TEXT,
    channel_id TEXT,
    project_id TEXT            -- NULL for global subscriptions
);
```

## 🔍 Transcript Parser

The system includes a **robust transcript parser** that identifies callers by following `parentUuid` chains:

```python
from transcript_parser import TranscriptParser

# Initialize parser
parser = TranscriptParser(transcript_path)

# Get caller information
caller = parser.get_caller_info(tool_name="send_channel_message")
# Returns: CallerInfo(agent="task-executor", is_subagent=True, ...)

# Handles nested subagent calls
# main → task-executor → memory-manager → tool call
# Correctly identifies memory-manager as the caller
```

## 👨‍💻 Development

### 🧪 Running Tests

```bash
npm test
```

### 🛠️ Administrative Scripts

- **`manage_project_links.py`** - Control cross-project communication
- **`register_project_agents.py`** - Bulk register agents in a project
- **`configure_agents.py`** - Add MCP tools to existing agents

### 📐 Architecture Principles

1. **Separation of Concerns**: AdminOperations handles business logic, ConfigManager handles YAML, DatabaseManager handles SQLite
2. **Single Source of Truth**: Configuration drives behavior, database reflects configuration
3. **No Duplication**: Each component has one clear responsibility
4. **Project Isolation**: Projects isolated by default, require explicit linking

## 📚 Documentation

- **[Architecture Guide](docs/architecture-guide.md)** - System design and component relationships
- **[Configuration Guide](docs/configuration-guide.md)** - Detailed configuration options
- **[Security & Validation](docs/security-and-validation.md)** - Security considerations
- **[Quick Reference](docs/quick-reference.md)** - Command cheat sheet

## 📦 Publishing

This package is automatically published to npm when a new release is created on GitHub.

### 🚀 Release Process

1. **Create a new release** using GitHub Actions:
   ```bash
   # Via GitHub UI: Actions → Create Release → Run workflow
   # Enter version number (e.g., 1.0.1)
   ```

2. **Automatic publishing**:
   - ✅ Tests run automatically
   - ✅ Version is updated in package.json
   - ✅ Git tag is created
   - ✅ Package is published to npm with provenance
   - ✅ GitHub release is created with changelog

### 🔧 Manual Publishing

If needed, you can publish manually:
```bash
npm version patch  # or minor/major
npm publish
git push --tags
```

### 🔑 NPM Token Setup

Add your npm token as a GitHub secret:
1. Get token from npm: `npm token create`
2. Add to GitHub: Settings → Secrets → Actions → New repository secret
3. Name: `NPM_TOKEN`

## 🤝 Contributing

Priority improvements needed:
- [ ] 🔍 Message search and filtering
- [ ] 📁 Channel archival
- [ ] 🧵 Message threading
- [ ] 🎨 Rich message formatting
- [ ] 📦 Bulk message operations

## 📄 License

MIT - See [LICENSE](LICENSE)

## 👤 Author

**Theo Nash**

## 🙏 Credits

Built as foundational messaging infrastructure for Claude Code multi-agent systems.

---

<p align="center">
  <strong>🚀 Transform your Claude Code agents into a coordinated team!</strong>
</p>