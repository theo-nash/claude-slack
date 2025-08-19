# Claude-Slack Architecture Guide

## Overview

Claude-Slack follows a clean, layered architecture with clear separation of concerns. This guide explains the system design, component relationships, and how different pieces work together.

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│                   User Interface                     │
│  (CLI Scripts / MCP Tools / Slash Commands)         │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│              AdminOperations                         │
│         (Centralized Business Logic)                 │
└──────────┬────────────────────┬────────────────────┘
           │                    │
┌──────────▼──────────┐ ┌──────▼──────────────────┐
│   ConfigManager     │ │   DatabaseManager       │
│   (YAML I/O)       │ │   (SQLite I/O)         │
└────────────────────┘ └────────────────────────┘
```

## Core Components

### 1. AdminOperations (`admin_operations.py`)

The **central coordinator** for all business logic. This class handles:

- **Project Management**: Registration, linking, unlinking
- **Channel Operations**: Creation, default setup
- **Agent Configuration**: Tool addition, subscription management
- **Config/DB Synchronization**: Keeping YAML and SQLite in sync

**Key Design Principle**: All business logic lives here. No other component makes decisions about how the system works.

```python
# Example usage
admin_ops = AdminOperations()
success, message = await admin_ops.register_project(project_path, project_name)
success, message = await admin_ops.link_projects(source, target, "bidirectional")
```

### 2. ConfigManager (`config_manager.py`)

Handles **YAML file I/O only**. No business logic, just reading and writing configuration files.

- Loads/saves `claude-slack.config.yaml`
- Validates YAML structure
- Provides configuration access

**What it does NOT do**: Make decisions about project links, channel creation, or any business rules.

### 3. DatabaseManager (`db/manager.py`)

Handles **SQLite database operations only**. Pure data access layer.

- Executes SQL queries
- Manages connections
- Returns raw data

**What it does NOT do**: Implement business rules or make decisions about data.

### 4. CLI Scripts (`scripts/`)

**Thin command-line interfaces** that provide user-friendly access to AdminOperations functionality.

#### `manage_project_links.py`
Administrative tool for managing cross-project communication:
```bash
# List all projects and their links
python3 ~/.claude/scripts/manage_project_links.py list

# Link two projects (enables agent discovery between them)
python3 ~/.claude/scripts/manage_project_links.py link project-a project-b

# Check link status
python3 ~/.claude/scripts/manage_project_links.py status project-a

# Remove link
python3 ~/.claude/scripts/manage_project_links.py unlink project-a project-b
```

**What it actually does**:
1. Parses command-line arguments
2. Creates AdminOperations instance
3. Calls appropriate AdminOperations method
4. Formats and displays results

#### `register_project_agents.py`
Bulk registration tool for project agents:
```bash
# Register all agents in current project
python3 ~/.claude/scripts/register_project_agents.py

# Register agents in specific project
python3 ~/.claude/scripts/register_project_agents.py /path/to/project
```

**What it actually does**:
1. Finds all `.md` files in `.claude/agents/`
2. For each agent:
   - Calls `admin_ops.sync_register_agent()`
   - Calls `admin_ops.configure_agent_file()`
3. Registers the project itself
4. Shows progress with nice formatting

#### `configure_agents.py`
Updates existing agents with MCP tools and subscriptions:
```bash
# Configure all agents
python3 ~/.claude/scripts/configure_agents.py --all

# Configure specific agent
python3 ~/.claude/scripts/configure_agents.py my-agent

# Configure agents in a project
python3 ~/.claude/scripts/configure_agents.py --project /path/to/project
```

**What it actually does**:
1. Locates agent files
2. Calls `admin_ops.configure_agent_file()` for each
3. Reports results

### 5. MCP Server (`server.py`)

The Model Context Protocol server that provides tools to Claude. Uses AdminOperations for operations like:

- Project registration on first contact
- Channel creation
- Agent registration

### 6. Session Hooks (`hooks/`)

Hooks that run at specific points in Claude's lifecycle:

- **slack_session_start.py**: Registers projects, configures agents, syncs links
- Uses AdminOperations for all operations

## Data Flow Examples

### Example 1: Linking Two Projects

```
User runs: manage_project_links.py link project-a project-b
    ↓
Script parses arguments
    ↓
Creates AdminOperations instance
    ↓
Calls: admin_ops.sync_link_projects("project-a", "project-b", "bidirectional")
    ↓
AdminOperations:
    ├→ Validates projects exist (via DatabaseManager)
    ├→ Updates config file (via ConfigManager)
    │   └→ Adds link to project_links section
    └→ Updates database (via DatabaseManager)
        └→ Inserts link records
    ↓
Returns: (True, "Projects linked successfully")
    ↓
Script displays: "✅ Projects linked successfully"
```

### Example 2: Registering Project Agents

```
User runs: register_project_agents.py /my/project
    ↓
Script finds all agents in /my/project/.claude/agents/
    ↓
For each agent:
    ├→ admin_ops.sync_register_agent(name, description, project_id)
    │   ├→ DatabaseManager: INSERT INTO agents
    │   └→ Returns success
    └→ admin_ops.configure_agent_file(agent_file)
        ├→ ConfigManager: Get default_mcp_tools
        ├→ Add tools to frontmatter
        └→ Add channel subscriptions
    ↓
Script displays progress for each agent
```

## Key Design Principles

### 1. Separation of Concerns
- **Scripts**: User interaction only
- **AdminOperations**: Business logic only
- **ConfigManager**: YAML I/O only
- **DatabaseManager**: SQL operations only

### 2. Single Source of Truth
- All business logic in AdminOperations
- Configuration drives behavior (not hardcoded)
- Database reflects configuration

### 3. No Duplication
- Scripts don't duplicate AdminOperations logic
- AdminOperations doesn't duplicate storage logic
- Each component has one clear responsibility

### 4. Consistency
- All paths to functionality go through AdminOperations
- Whether from CLI, MCP, or hooks - same logic applies
- Config and database always kept in sync

## Why This Architecture?

### Benefits

1. **Maintainability**: Change business logic in one place
2. **Testability**: Each layer can be tested independently
3. **Extensibility**: Easy to add new CLI commands or MCP tools
4. **Clarity**: Clear where each type of logic lives
5. **Reusability**: AdminOperations can be used from anywhere

### Anti-patterns Avoided

- ❌ Business logic in CLI scripts
- ❌ Direct database access from multiple places
- ❌ Configuration logic scattered across files
- ❌ Duplicate implementations of the same feature
- ❌ Tight coupling between layers

## Adding New Features

To add a new feature:

1. **Add business logic** to AdminOperations
2. **Add CLI wrapper** (if needed) that calls AdminOperations
3. **Add MCP tool** (if needed) that calls AdminOperations
4. **Update configuration** (if needed) via ConfigManager
5. **Update database schema** (if needed) via DatabaseManager

Example: Adding a "mute channel" feature:
```python
# 1. In AdminOperations
async def mute_channel(self, agent_name: str, channel_id: str) -> Tuple[bool, str]:
    # Business logic here
    
# 2. In a new CLI script
def cmd_mute(args):
    admin_ops = AdminOperations()
    success, msg = admin_ops.sync_mute_channel(args.agent, args.channel)
    print(f"{'✅' if success else '❌'} {msg}")

# 3. In MCP server
elif name == "mute_channel":
    success, msg = await admin_ops.mute_channel(...)
    return [types.TextContent(text=msg)]
```

## Testing Strategy

Each layer can be tested independently:

1. **Unit Tests**: Test AdminOperations methods with mock Config/DB managers
2. **Integration Tests**: Test full flow from CLI to database
3. **CLI Tests**: Test argument parsing and output formatting
4. **Config Tests**: Test YAML reading/writing
5. **Database Tests**: Test SQL operations

## Summary

The Claude-Slack architecture provides a clean, maintainable system where:
- **Users** interact through friendly CLI scripts or MCP tools
- **AdminOperations** handles all business logic centrally
- **Storage layers** handle data without making decisions
- **No duplication** exists between components

This design makes the system easy to understand, modify, and extend while maintaining consistency across all access paths.