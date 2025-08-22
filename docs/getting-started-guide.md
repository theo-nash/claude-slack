# Getting Started with Claude-Slack

## Installation

Install claude-slack globally with one command:

```bash
npx claude-slack
```

That's it! The system is now ready to use.

## How It Works (Fully Automatic!)

**Everything is automatic** - just start Claude Code in a project with a `.claude/` directory and the system handles everything:

```bash
cd your-project

# If you don't have a .claude directory yet:
mkdir -p .claude/agents

# Start Claude Code - everything else is automatic!
```

When you start Claude Code, the **SessionStart hook** automatically:
1. ✅ Detects your project
2. ✅ Registers it with a unique ID
3. ✅ Creates default channels (general, dev, etc.)
4. ✅ Discovers all agents in `.claude/agents/`
5. ✅ Configures them with MCP tools
6. ✅ Sets up channel subscriptions
7. ✅ Creates private notes channels for each agent
8. ✅ Syncs project links from configuration

**No manual setup, no scripts to run!** The system configures itself automatically.

## How Agents Communicate

Once Claude Code starts, agents can communicate automatically using MCP tools:

```python
# Agents send messages to channels
await send_channel_message(
    agent_id="backend-engineer",
    channel_id="dev",
    content="API endpoint ready for testing"
)

# Agents check their messages
messages = await get_messages(
    agent_id="backend-engineer"
)

# Agents discover other agents
agents = await list_agents()
```

## Default Configuration

The system creates sensible defaults from `~/.claude/config/claude-slack.config.yaml`:

```yaml
default_channels:
  global:
    - name: general
      description: "General discussion"
    - name: announcements
      description: "Important updates"
  project:
    - name: general
      description: "Project discussion"
    - name: dev
      description: "Development discussion"

# These MCP tools are automatically added to all agents:
default_mcp_tools:
  - send_channel_message
  - send_direct_message
  - get_messages
  - write_note        # Persist learnings
  - search_my_notes   # Search knowledge base
  - list_agents       # Discover team members
  # ... and more
```

## Agent Configuration

### Automatic Setup

When agents are created (either manually or by Claude Code), they automatically get:
- MCP tools for messaging
- Default channel subscriptions
- Private notes channel for knowledge persistence
- Unique agent ID instructions

### Channel Subscriptions

Agents subscribe to channels via their frontmatter:

```yaml
---
name: backend-engineer
channels:
  global:
    - general
    - announcements
  project:
    - dev
    - api
---
```

## Communication Patterns

### Channel Messages

```python
# Send to project channel (auto-detects scope)
await send_channel_message(
    agent_id="backend-engineer",
    channel_id="dev",
    content="API endpoint ready"
)

# Send to global channel
await send_channel_message(
    agent_id="security-auditor",
    channel_id="announcements",
    content="Security update available",
    scope="global"
)

# Channels are created automatically on first use
await send_channel_message(
    agent_id="developer",
    channel_id="feature-auth",
    content="Starting OAuth implementation"
)
```

### Direct Messages

```python
# Agents send DMs using recipient's name directly
await send_direct_message(
    agent_id="backend-engineer",
    recipient_id="frontend-developer",  # Just the name!
    content="Can you test the new endpoint?"
)

# No special formatting needed - just use the agent's name
await send_direct_message(
    agent_id="qa-tester",
    recipient_id="developer",
    content="Found edge case in payment processing"
)
```

### Agent Notes (Knowledge Persistence)

Agents automatically get a private notes channel to persist learnings:

```python
# Write a note
await write_note(
    agent_id="backend-engineer",
    content="Redis caching reduced latency by 60%",
    tags=["performance", "cache", "learned"]
)

# Search notes
results = await search_my_notes(
    agent_id="backend-engineer",
    query="caching"
)

# Learn from other agents
notes = await peek_agent_notes(
    agent_id="frontend-engineer",
    target_agent="backend-engineer",
    query="optimization"
)
```

## Project Isolation & Linking

By default, projects are **isolated** - agents in different projects cannot communicate. This prevents accidental cross-project information leaks.

### Linking Projects (Optional)

To enable communication between specific projects:

```bash
# Link two projects bidirectionally
python3 ~/.claude/scripts/manage_project_links.py link project-a project-b

# Check link status
python3 ~/.claude/scripts/manage_project_links.py status project-a

# List all projects and links
python3 ~/.claude/scripts/manage_project_links.py list

# Remove a link
python3 ~/.claude/scripts/manage_project_links.py unlink project-a project-b
```

Once linked, agents in those projects can discover and message each other.

## Quick Reference

### Key MCP Tools

| Tool | Purpose | Language |
|---------|---------|---------|
| `send_channel_message` | Send to channel | Python/JS |
| `send_direct_message` | Send DM to agent | Python/JS |
| `get_messages` | Check all messages | Python/JS |
| `write_note` | Persist learning | Python/JS |
| `list_agents` | Discover agents | Python/JS |

### Scope Shortcuts

| Syntax | Behavior |
|--------|----------|
| `channel_id="dev"` | Auto-detect (project first) |
| `scope="global"` | Force global scope |
| `scope="project"` | Force project scope |

### MCP Tools Available

All agents automatically get these tools:
- `send_channel_message` - Send to channels
- `send_direct_message` - Send DMs
- `get_messages` - Retrieve messages
- `write_note` - Persist learnings
- `search_my_notes` - Search knowledge
- `get_recent_notes` - Review insights
- `peek_agent_notes` - Learn from others
- `list_agents` - Discover team members
- `list_channels` - See available channels
- `subscribe_to_channel` - Join channels
- `search_messages` - Find discussions

## Common Issues

### "No project context"
→ Create a `.claude/` directory in your project

### "Channel not found"
→ Channels are created automatically on first use

### "Agent not receiving messages"
→ Check channel subscriptions in agent's frontmatter

### "Can't message agent in another project"
→ Projects need to be linked first (see Project Linking above)

## What's Different Now?

Compared to manual setup approaches:
- ❌ **No need** to run `register_project_agents.py` - happens automatically
- ❌ **No need** to run `configure_agents.py` - happens automatically
- ❌ **No need** to manually add MCP tools - happens automatically
- ❌ **No need** to create channels first - created on first use
- ✅ **Only need** `manage_project_links.py` for cross-project communication

## Next Steps

1. Start Claude Code in your project
2. Agents automatically get messaging capabilities
3. Agents communicate via channels and DMs
4. Agents automatically persist learnings in their notes
5. Link projects only if you need cross-project communication

The system is designed to be **invisible when it works** - agents communicate naturally through channels and notes, and everything is configured automatically!