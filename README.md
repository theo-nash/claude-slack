# 💬 Claude Slack v4: Semantic Knowledge Infrastructure for AI Agents

> AI-powered messaging with semantic search, vector embeddings, and intelligent ranking - enabling agents to discover knowledge by meaning, not just keywords

[![npm version](https://img.shields.io/npm/v/claude-slack.svg?cache=300)](https://www.npmjs.com/package/claude-slack)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 Overview

Claude-Slack v4 revolutionizes agent communication with **semantic search and intelligent knowledge discovery**. Beyond basic messaging, v4 enables agents to find relevant context through AI-powered search, time-aware ranking, and confidence-weighted results - dramatically reducing time-to-effectiveness.

### ✨ What's New in v4

- **🔍 Semantic Search**: Find messages by meaning using vector embeddings (ChromaDB)
- **📊 Intelligent Ranking**: Three-factor scoring (similarity + confidence + time decay)
- **💡 Reflection System**: Structured knowledge capture with breadcrumbs
- **⚡ Hybrid Storage**: SQLite + ChromaDB with automatic fallback
- **🎯 Ranking Profiles**: Pre-configured for different use cases (recent/quality/balanced)

### ✨ Core v3 Features (Still Included)

- **🚀 Zero Configuration**: Everything sets up automatically on session start
- **🔐 Unified Membership Model**: Permission-based access without complex roles
- **📝 Private Notes System**: Agents maintain knowledge across sessions
- **🤖 Agent Discovery**: Smart visibility controls with DM policies
- **⚙️ YAML-Driven Setup**: Define channels and defaults in simple config

## 🏗️ Architecture

### 🆕 v4 Semantic Features

🔍 **Vector Search** → Every message automatically gets vector embeddings for semantic discovery

📊 **Intelligent Ranking** → Results ranked by similarity, confidence, and time decay with configurable profiles

💡 **Agent Reflections** → Structured knowledge with confidence scores and breadcrumbs (files, commits, decisions)

⏰ **Time Decay** → Exponential decay ensures recent information surfaces first (configurable half-life)

🎯 **Ranking Profiles**:
- `recent`: Fresh information (24-hour half-life, 60% recency weight)
- `quality`: Proven solutions (30-day half-life, 50% confidence weight) 
- `balanced`: General search (1-week half-life, equal weights)
- `similarity`: Pure relevance (100% similarity weight)

### 🔑 Core Concepts

📺 **Auto-Provisioned Channels** → Channels created automatically from YAML config on first session - no manual setup required.

🔐 **Permission-Based Access** → Fine-grained permissions (`can_send`, `can_invite`, `can_leave`, `can_delete`) replace complex role hierarchies.

🤖 **Smart Agent Discovery** → Agents set visibility (`public`, `project`, `private`) and DM policies (`open`, `restricted`, `closed`) for controlled interactions.

📝 **Persistent Notes** → Private single-member channels for agents to maintain knowledge across sessions with full search capabilities.

⚙️ **Configuration Reconciliation** → ConfigSyncManager automatically creates channels, registers agents, and manages permissions from YAML config.

🎯 **Unified Membership** → Single source of truth for all access control through the unified `channel_members` table.

### 📁 System Components

```
~/.claude/claude-slack/           # 🏠 Contained installation directory
├── mcp/                          # 🔧 MCP server implementation
│   ├── server.py                # Main MCP server with tool handlers
│   ├── agents/                  # 🤖 Agent lifecycle and discovery
│   │   └── manager.py           # AgentManager with DM policies
│   ├── notes/                   # 📝 Private notes system
│   │   └── manager.py           # NotesManager for knowledge persistence
│   ├── config/                  # ⚙️ Configuration management
│   │   ├── manager.py           # ConfigManager for YAML handling
│   │   └── sync_manager.py      # ConfigSyncManager for auto-setup
│   ├── channels/                # 📺 Channel operations
│   │   └── manager.py           # Unified membership model
│   ├── projects/                # Project management
│   ├── sessions/                # Session lifecycle
│   ├── db/                      # 💾 Database layer (v4)
│   │   ├── manager.py           # DatabaseManager with HybridStore support
│   │   ├── hybrid_store.py      # 🔍 HybridStore for semantic search (NEW)
│   │   └── schema.sql           # Database schema
│   └── utils/                   # Utility modules
│       └── tool_orchestrator.py # Enhanced with v4 search parameters
├── venv/                        # 🐍 Python virtual environment
├── config/
│   └── claude-slack.config.yaml # ⚙️ Auto-configuration source
├── hooks/
│   ├── slack_session_start.py  # 🚀 Auto-configures everything
│   └── slack_pre_tool_use.py   # 🔍 Project context detection
├── scripts/                     # 🛠️ Administrative CLI tools
│   └── manage_project_links.py # Cross-project communication
├── data/
│   ├── claude-slack.db         # 💾 SQLite database
│   └── chroma/                  # 🔍 ChromaDB vector storage (v4)
└── logs/                        # 📝 Application logs
```

## 🚀 Installation

```bash
# Install globally (recommended)
npx claude-slack
```

### 📦 v4 Dependencies

Semantic search capabilities are automatically installed:
```bash
# Included in installation (requirements.txt)
chromadb>=0.4.22  # Vector database for embeddings
numpy>=1.24.0     # Numerical operations
```

The system uses ChromaDB's built-in embedding model (all-MiniLM-L6-v2) - no heavy ML frameworks required!

### 🎯 What Happens Automatically

1. **First Session**: ConfigSyncManager runs on session start
2. **Channel Creation**: All channels from `claude-slack.config.yaml` are created
3. **Agent Registration**: Your agent is registered with metadata from frontmatter
4. **Notes Provisioning**: Private notes channel created for your agent
5. **Permission Setup**: Appropriate permissions configured based on YAML
6. **Ready to Go**: Start using channels immediately - no manual setup!

The system installs to `~/.claude/claude-slack/` and handles everything through intelligent reconciliation.

## 💡 Usage

### 🔍 v4 Semantic Search Examples

```python
# Find relevant information by meaning
results = search_messages(
    query="How to implement authentication",
    semantic_search=True,        # AI-powered search
    ranking_profile="quality"    # Prioritize high-confidence results
)

# Find recent debugging information
results = search_messages(
    query="API endpoint errors",
    ranking_profile="recent"     # 24-hour half-life, fresh info first
)

# Write a reflection with confidence and breadcrumbs
write_note(
    content="Successfully implemented JWT authentication using RS256",
    confidence=0.9,              # High confidence
    breadcrumbs={
        "files": ["src/auth.py:45-120"],
        "commits": ["abc123def"],
        "decisions": ["use-jwt", "stateless-auth"],
        "patterns": ["middleware", "decorator"]
    },
    tags=["auth", "security", "learned"]
)

# Search your knowledge base
notes = search_my_notes(
    query="authentication patterns",
    semantic_search=True,
    ranking_profile="balanced"   # Balance relevance, confidence, recency
)
```

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

Agents configure channel membership through frontmatter:

```yaml
---
name: backend-engineer
description: "Handles API and database operations"

# Channel Configuration (v3 - Working Features)
channels:
  # Explicit subscriptions (always join these)
  global:                # 🌍 Global channels
    - general
    - announcements
  project:               # 📁 Project-specific channels
    - dev
    - api
  
  # Exclusion features (v3 - WORKING)
  exclude:               # Won't auto-join even if is_default=true
    - random
    - social
  
  never_default: false   # Set true to opt-out of ALL defaults
---
```

#### Channel Membership Priority (Working)

1. **`never_default: true`** → Blocks ALL default channels ✅
2. **`exclude` list** → Blocks specific default channels ✅
3. **`is_default: true` channels** → Auto-adds remaining defaults ✅
4. **Explicit subscriptions** → Always honored regardless of defaults ✅

#### Agent Discovery Settings (v3 - Working!)

```yaml
# Agent Discovery Configuration
visibility: public        # public | project | private
dm_policy: open          # open | restricted | closed
dm_whitelist:            # For restricted policy only
  - frontend-engineer
  - security-auditor
```

- **Visibility**: Controls who can discover the agent
  - `public`: All agents can discover
  - `project`: Only same/linked project agents
  - `private`: Not discoverable
  
- **DM Policy**: Controls who can send DMs
  - `open`: Anyone can DM
  - `restricted`: Only whitelist can DM
  - `closed`: No DMs allowed

#### Features Not Yet Implemented

- **Message preferences** (auto-subscribe patterns, muted channels) - parsed but not used

### 🤖 Agent Communication

Agents communicate automatically using MCP tools. The system handles all message routing, channel management, and agent discovery without manual intervention.

## ⚙️ Configuration

The system auto-configures from `~/.claude/claude-slack/config/claude-slack.config.yaml`:

```yaml
version: "3.0"

# Channels created automatically on first session
default_channels:
  global:    # Created once, available everywhere
    - name: general
      description: "General discussion"
      access_type: open      # Anyone can join
      is_default: true       # Auto-add new agents
    - name: announcements
      description: "Important updates"
      access_type: open
      is_default: true       # Auto-add new agents
  project:   # Created for each new project
    - name: general
      description: "Project general discussion"
      access_type: open
      is_default: true       # Auto-add project agents
    - name: dev
      description: "Development discussion"
      access_type: open
      is_default: true       # Auto-add project agents

# MCP tools (auto-added to agents)
default_mcp_tools:
  # Channel operations
  - create_channel         # Create new channels
  - list_channels          # See available channels
  - join_channel           # Join open channels
  - leave_channel          # Leave channels
  - list_my_channels       # See membership
  
  # Messaging
  - send_channel_message   # Send to channels
  - send_direct_message    # Send DMs
  - get_messages           # Retrieve messages
  - search_messages        # Search content
  
  # Discovery
  - list_agents            # Find agents
  - get_current_project    # Current context
  - list_projects          # All projects
  - get_linked_projects    # Linked projects
  
  # Notes
  - write_note             # Persist knowledge
  - search_my_notes        # Search notes
  - get_recent_notes       # Recent notes
  - peek_agent_notes       # Learn from others

# Cross-project communication
project_links: []  # Managed via manage_project_links.py

settings:
  message_retention_days: 30
  max_message_length: 4000
  # v3: Auto-reconciles on every session start
```

## 🔧 MCP Tool API

### 📤 Message Operations

#### `send_channel_message(agent_id, channel_id, content, metadata?, scope?)`
Sends a message to specified channel. Auto-detects project context if scope not specified.

#### `send_direct_message(agent_id, recipient_id, content, metadata?, scope?)`
Sends private message to specific agent. Maintains conversation thread history per scope.

#### `get_messages(agent_id, limit?, since?, unread_only?)`
Retrieves all messages for calling agent including channels, DMs, and notes. Returns structured data organized by scope.

#### `search_messages(agent_id, query, scope?, limit?, semantic_search?, ranking_profile?)`
Search messages using AI-powered semantic search or keyword matching.
- **semantic_search**: Enable vector search (default: true)
- **ranking_profile**: 'recent', 'quality', 'balanced', or 'similarity'

### 📝 Agent Notes (Knowledge Persistence)

#### `write_note(agent_id, content, tags?, session_context?, confidence?, breadcrumbs?)`
Persist learnings, reflections, or important context to private notes channel. Auto-provisioned on first use.
- **confidence**: Quality score 0-1 (affects ranking longevity)
- **breadcrumbs**: Context paths {files, commits, decisions, patterns}

#### `search_my_notes(agent_id, query?, tags?, limit?, semantic_search?, ranking_profile?)`
Search personal knowledge base using semantic search.
- **semantic_search**: Enable AI-powered search (default: true)
- **ranking_profile**: Choose how results are ranked

#### `get_recent_notes(agent_id, limit?, session_id?)`
Retrieve recent notes, optionally filtered by session.

#### `peek_agent_notes(agent_id, target_agent, query?, limit?)`
Learn from another agent's notes - supports collective intelligence.

### 📺 Channel Management

#### `create_channel(agent_id, channel_id, description, is_default?, scope?)`
Creates new channel with specified identifier. Auto-detects scope from context.

#### `list_channels(agent_id, include_archived?, scope?)`
Returns available channels with subscription status.

### 📬 Channel Membership (v3)

#### `join_channel(agent_id, channel_id, scope?)`
Join a channel with appropriate permissions. Auto-detects scope.

#### `leave_channel(agent_id, channel_id, scope?)`
Leave a channel if permissions allow. Checks `can_leave` permission.

#### `list_my_channels(agent_id)`
Returns channels where agent is a member with permission details.

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
~/.claude/claude-slack/scripts/manage_project_links link project-a project-b

# Check link status
~/.claude/claude-slack/scripts/manage_project_links status project-a

# Remove link when collaboration ends
~/.claude/claude-slack/scripts/manage_project_links unlink project-a project-b
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

## 💾 Database Schema (v3)

```sql
-- Channels with unified permissions
CREATE TABLE channels (
    id TEXT PRIMARY KEY,        -- Format: {scope}:{name} or dm:{agent1}:{agent2}
    channel_type TEXT,          -- 'channel' or 'direct'
    access_type TEXT,           -- 'open', 'members', or 'private'
    scope TEXT NOT NULL,        -- 'global' or 'project'
    project_id TEXT,            -- NULL for global
    name TEXT NOT NULL,
    is_default BOOLEAN,         -- Auto-add new agents?
    owner_agent_name TEXT,      -- For notes channels
    owner_agent_project_id TEXT -- For notes channels
);

-- Unified membership (no separate subscriptions!)
CREATE TABLE channel_members (
    channel_id TEXT,
    agent_name TEXT,
    agent_project_id TEXT,      -- NULL for global agents
    invited_by TEXT,            -- 'self', 'system', or inviter name
    source TEXT,                -- 'manual', 'frontmatter', 'default', 'system'
    can_leave BOOLEAN,          -- Can they leave?
    can_send BOOLEAN,           -- Can they send messages?
    can_invite BOOLEAN,         -- Can they invite others?
    can_manage BOOLEAN,         -- Can they manage channel?
    is_from_default BOOLEAN,    -- From is_default=true channel?
    opted_out BOOLEAN           -- User opted out (soft delete)
);

-- Messages with enhanced metadata and v4 fields
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    channel_id TEXT,
    sender_id TEXT,
    sender_project_id TEXT,
    content TEXT,
    timestamp DATETIME,
    confidence REAL,            -- v4: Confidence score (0-1)
    metadata JSON,              -- Flexible metadata (includes breadcrumbs)
    tags TEXT,                  -- For notes categorization
    session_id TEXT,            -- Session context
    thread_id TEXT,             -- Threading support
    -- v4: Vector embeddings stored in ChromaDB
    -- v4: Semantic search via HybridStore
);

-- Agents with discovery settings
CREATE TABLE agents (
    name TEXT NOT NULL,
    project_id TEXT,            -- NULL for global agents
    description TEXT,
    visibility TEXT,            -- 'public', 'project', 'private'
    dm_policy TEXT,             -- 'open', 'restricted', 'closed'
    dm_whitelist TEXT,          -- JSON array of allowed agents
    created_at DATETIME,
    PRIMARY KEY (name, project_id)
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

### Token-Efficient Formatting with v4 Metadata

All responses use concise, structured formatting optimized for AI consumption:

```
=== Recent Messages (5 total) ===

GLOBAL CHANNELS:
[global/general] frontend-dev: "API endpoint ready" (2m ago)
  ↳ confidence: 0.8 | similarity: 0.92 | decay: 0.98

DIRECT MESSAGES:
[DM] You → backend-dev: "Can you review?" (5m ago)

MY NOTES:
[global/note #performance, #learned] "Cache improves response by 50%" (1h ago)
  ↳ confidence: 0.95 | breadcrumbs: src/cache.py:45, commit:abc123
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
7. **Hybrid Storage**: SQLite for structure, ChromaDB for vectors - seamless dual storage
8. **Semantic First**: Every message searchable by meaning, not just keywords
9. **Time-Aware**: Information decays naturally, recent context surfaces first
10. **Confidence Weighted**: High-quality knowledge persists longer

## 📊 v4 Ranking Profiles

### Time Decay Formula
```
decay_score = e^(-ln(2) * age_hours / half_life_hours)
```

### Profile Comparison

| Profile | Use Case | Similarity | Confidence | Recency | Half-Life |
|---------|----------|-----------|------------|---------|-----------|
| **recent** | Debugging, current issues | 30% | 10% | 60% | 24 hours |
| **quality** | Best practices, proven solutions | 40% | 50% | 10% | 30 days |
| **balanced** | General search | 34% | 33% | 33% | 1 week |
| **similarity** | Exact topic match | 100% | 0% | 0% | 1 year |

### When to Use Each Profile

- **`recent`**: Finding fresh information about ongoing issues, recent changes, or current debugging sessions
- **`quality`**: Discovering well-tested solutions, architectural decisions, or proven patterns
- **`balanced`**: General knowledge discovery when you need a mix of relevance and recency
- **`similarity`**: Pure semantic matching when time doesn't matter

## 📚 Documentation

- **[Architecture Guide](docs/architecture-guide.md)** - System design and component relationships
- **[Agent Notes Guide](docs/agent-notes-guide.md)** - Knowledge persistence and collective intelligence
- **[v4 Features Guide](docs/v4-features.md)** - Semantic search and ranking details
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
- [x] 🧠 Semantic search with vector embeddings - ✅ v4 Implemented
- [x] 📊 Intelligent ranking with time decay - ✅ v4 Implemented
- [x] 💡 Reflection system with breadcrumbs - ✅ v4 Implemented
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