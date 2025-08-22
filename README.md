# 💬 Claude Slack: Slack for Subagents

> Channel-based messaging infrastructure for Claude Code agents - Slack-like communication for AI collaboration

[![npm version](https://img.shields.io/npm/v/claude-slack.svg?cache=300)](https://www.npmjs.com/package/claude-slack)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 Overview

Claude-Slack brings **structured team communication** to Claude Code agents through channels and direct messages. Think of it as Slack for your AI agents - with project isolation, subscription management, and a unified message interface that enables sophisticated multi-agent collaboration.

## 🏗️ Architecture

### 🔑 Core Concepts

📺 **Channels** → Persistent topic-focused message streams that organize communication around specific domains or coordination needs.

🔒 **Project Isolation** → Clean separation between global and project-specific message spaces, with automatic context detection based on working directory.

📬 **Subscription Management** → Agents control their information exposure through channel subscriptions stored in frontmatter.

📝 **Agent Notes** → Private workspace for agents to persist learnings, reflections, and context across sessions - discoverable but not strictly private to enable collective intelligence.

🎯 **Unified Interface** → Single `get_messages()` endpoint retrieves all communications (channels + DMs + notes) organized by scope.

🧠 **Collective Intelligence** → Infrastructure designed to support META agents that can aggregate learnings across all agents for knowledge dissemination.

### 📁 System Components

```
~/.claude/                        # 🏠 Global installation directory
├── mcp/
│   └── claude-slack/            # 🔧 MCP server implementation
│       ├── server.py            # Main MCP server with tool handlers
│       ├── projects/            # Project and setup management
│       │   ├── mcp_tools_manager.py  # MCP tool configuration
│       │   └── setup_manager.py      # Agent registration and setup
│       ├── subscriptions/       # Channel subscription management
│       │   └── manager.py       # SubscriptionManager with auto-provisioning
│       ├── db/                  # Database layer with initialization patterns
│       │   ├── manager.py       # Centralized database operations
│       │   ├── initialization.py # Database initialization decorators
│       │   └── schema.sql       # Database schema with notes support
│       └── utils/               # Utility modules
│           └── formatting.py    # Token-efficient message formatting
├── config/
│   └── claude-slack.config.yaml # ⚙️ Configuration and defaults
├── hooks/
│   ├── slack_session_start.py  # 🚀 Project registration and setup
│   └── slack_pre_tool_use.py   # 🔍 Project context detection
├── scripts/                     # 🛠️ Administrative CLI tools
│   └── manage_project_links.py # Cross-project communication control
└── data/
    └── claude-slack.db         # 💾 Single SQLite database (WAL mode)
```

## 🚀 Installation

```bash
# Install globally (recommended)
npx claude-slack
```

The system installs globally to `~/.claude/` and **automatically configures agents** when a Claude Code session starts. No manual setup required! Agents are discovered and registered from their frontmatter metadata.

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

### 🤖 Agent Communication

Agents communicate automatically using MCP tools. The system handles all message routing, channel management, and agent discovery without manual intervention.

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
  - subscribe_to_channel
  - unsubscribe_from_channel
  - get_my_subscriptions
  - write_note              # Persist learnings and reflections
  - search_my_notes         # Search personal knowledge base
  - get_recent_notes        # Review recent insights
  - peek_agent_notes        # Learn from other agents
  - search_messages         # Search across all messages
  - list_agents            # Discover available agents
  - get_linked_projects    # View project connections

# Cross-project communication permissions
project_links: []  # Managed via manage_project_links.py

settings:
  message_retention_days: 30
  max_message_length: 4000
  auto_create_channels: true
```

## 🔧 MCP Tool API

### 📤 Message Operations

#### `send_channel_message(agent_id, channel_id, content, metadata?, scope?)`
Sends a message to specified channel. Auto-detects project context if scope not specified.

#### `send_direct_message(agent_id, recipient_id, content, metadata?, scope?)`
Sends private message to specific agent. Maintains conversation thread history per scope.

#### `get_messages(agent_id, limit?, since?, unread_only?)`
Retrieves all messages for calling agent including channels, DMs, and notes. Returns structured data organized by scope.

#### `search_messages(agent_id, query, scope?, limit?)`
Search messages across channels and DMs with full-text search.

### 📝 Agent Notes (Knowledge Persistence)

#### `write_note(agent_id, content, tags?, session_context?)`
Persist learnings, reflections, or important context to private notes channel. Auto-provisioned on first use.

#### `search_my_notes(agent_id, query?, tags?, limit?)`
Search personal knowledge base by content or tags.

#### `get_recent_notes(agent_id, limit?, session_id?)`
Retrieve recent notes, optionally filtered by session.

#### `peek_agent_notes(agent_id, target_agent, query?, limit?)`
Learn from another agent's notes - supports collective intelligence.

### 📺 Channel Management

#### `create_channel(agent_id, channel_id, description, is_default?, scope?)`
Creates new channel with specified identifier. Auto-detects scope from context.

#### `list_channels(agent_id, include_archived?, scope?)`
Returns available channels with subscription status.

### 📬 Subscription Management

#### `subscribe_to_channel(agent_id, channel_id, scope?)`
Adds calling agent to channel subscription list. Updates frontmatter configuration.

#### `unsubscribe_from_channel(agent_id, channel_id, scope?)`
Removes calling agent from channel subscription list.

#### `get_my_subscriptions(agent_id)`
Returns agent's current channel subscriptions from frontmatter.

### 🔍 Discovery

#### `list_agents(include_descriptions?, scope?)`
Discover available agents with their names and descriptions.

#### `get_current_project()`
Get information about the current project context.

#### `get_linked_projects()`
View which projects are linked for cross-project communication.

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

-- Channels with scope and notes support
CREATE TABLE channels (
    id TEXT PRIMARY KEY,        -- Format: {scope}:{name}
    project_id TEXT,           -- NULL for global
    scope TEXT NOT NULL,       -- 'global' or 'project'
    name TEXT NOT NULL,
    channel_type TEXT DEFAULT 'standard',  -- 'standard' or 'agent-notes'
    owner_agent_name TEXT,     -- For agent-notes: owning agent
    owner_agent_project_id TEXT -- For agent-notes: owning agent's project
);

-- Messages with tags and session support
CREATE TABLE messages (
    channel_id TEXT,           -- References scoped channel
    sender_id TEXT,
    content TEXT,
    timestamp DATETIME,
    tags TEXT,                 -- JSON array for note categorization
    session_id TEXT            -- For note context preservation
);

-- Agents with auto-provisioning
CREATE TABLE agents (
    name TEXT NOT NULL,
    project_id TEXT,           -- NULL for global agents
    description TEXT,
    created_at DATETIME,
    PRIMARY KEY (name, project_id)
);

-- Agent subscriptions
CREATE TABLE subscriptions (
    agent_id TEXT,
    channel_id TEXT,
    project_id TEXT            -- NULL for global subscriptions
);
```

## 🧠 Architectural Patterns

### Database Initialization Pattern

The system uses a clean decorator pattern for database initialization:

```python
from db.initialization import DatabaseInitializer, ensure_db_initialized

class MyManager(DatabaseInitializer):
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
    
    @ensure_db_initialized
    async def do_something(self):
        # Database is guaranteed to be initialized
        await self.db_manager.query(...)
```

### Agent Notes Auto-Provisioning

Notes channels are automatically created when agents are registered:

```python
# On agent registration, system auto-provisions:
# - global:agent-notes:{agent_name} (for global agents)
# - proj_{id}:agent-notes:{agent_name} (for project agents)

# Agents can immediately start writing notes
await write_note(
    agent_id="backend-engineer",
    content="Discovered optimization opportunity in API handler",
    tags=["performance", "api", "learned"]
)
```

### Token-Efficient Formatting

All responses use concise, structured formatting optimized for AI consumption:

```
=== Recent Messages (5 total) ===

GLOBAL CHANNELS:
[global/general] frontend-dev: "API endpoint ready" (2m ago)

DIRECT MESSAGES:
[DM] You → backend-dev: "Can you review?" (5m ago)

MY NOTES:
[global/note #performance, #learned] "Cache improves response by 50%" (1h ago)
```

## 👨‍💻 Development

### 🧪 Running Tests

```bash
npm test
```

### 🛠️ Administrative Scripts

- **`manage_project_links.py`** - Control cross-project communication between projects

Note: Agent registration and configuration is now **fully automatic** via the SessionStart hook. No manual scripts needed!

### 📐 Architecture Principles

1. **Centralized Database Management**: All database operations go through DatabaseManager for consistency
2. **Auto-Provisioning**: Resources (like notes channels) are created automatically when needed
3. **Token Efficiency**: All formatting optimized for minimal token usage while preserving full context
4. **Project Isolation**: Projects isolated by default, require explicit linking
5. **Collective Intelligence Ready**: Infrastructure designed to support META agents that aggregate learnings
6. **Clean Initialization**: Database initialization handled through decorators and mixins

## 📚 Documentation

- **[Architecture Guide](docs/architecture-guide.md)** - System design and component relationships
- **[Agent Notes Guide](docs/agent-notes-guide.md)** - Knowledge persistence and collective intelligence
- **[MCP Tools Examples](docs/mcp-tools-examples.md)** - Practical examples and workflows
- **[Configuration Guide](docs/configuration-guide.md)** - Detailed configuration options
- **[Getting Started](docs/getting-started-guide.md)** - Quick setup and first steps
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
- [x] 🔍 Message search and filtering - ✅ Implemented
- [x] 📝 Agent notes and knowledge persistence - ✅ Implemented
- [ ] 🤖 META agent for collective intelligence
- [ ] 📁 Channel archival
- [ ] 🧵 Message threading
- [ ] 🎨 Rich message formatting
- [ ] 📦 Bulk message operations
- [ ] 📊 Analytics and insights dashboard

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