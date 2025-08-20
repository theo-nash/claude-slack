# Session Management

## Overview

The SessionManager is the foundational component of Claude-Slack that manages session contexts and project detection. It provides critical context information that all other components depend on, but has no knowledge of channels, subscriptions, or messaging.

## Core Responsibilities

1. **Session Registration**: Track Claude sessions and their associated project contexts
2. **Context Retrieval**: Provide project information for the current session
3. **Project Management**: Register and track projects in the database
4. **Tool Call Tracking**: Match tool calls to their originating sessions
5. **Lifecycle Management**: Clean up old sessions and maintain cache

## Architecture

### Data Models

#### SessionContext
```python
@dataclass
class SessionContext:
    session_id: str
    project_id: Optional[str]
    project_path: Optional[str]
    project_name: Optional[str]
    transcript_path: Optional[str]
    scope: str  # 'global' or 'project'
    updated_at: datetime
    metadata: Optional[Dict[str, Any]]
```

#### ProjectContext
```python
@dataclass
class ProjectContext:
    project_id: str
    project_path: str
    project_name: str
    scope: str = 'project'
```

### Key Design Principles

1. **Single Responsibility**: Only manages session and project context
2. **No Dependencies**: Doesn't know about channels or subscriptions
3. **Foundation Layer**: Other managers depend on this, not vice versa
4. **Caching**: Simple TTL-based cache for performance
5. **Backwards Compatible**: Maintains compatibility with existing code

## API Reference

### Core Methods

#### `register_session(session_id, project_path=None, project_name=None, transcript_path=None)`
Register a new session or update an existing one.

#### `get_session_context(session_id) -> SessionContext`
Get complete context for a specific session.

#### `get_current_session_context() -> SessionContext`
Get context for the current/most recent session.

#### `register_project(project_path, project_name=None) -> project_id`
Register a project in the database.

#### `get_project_context(project_id) -> ProjectContext`
Get project information by ID.

### Tool Call Tracking

#### `record_tool_call(session_id, tool_name, tool_inputs)`
Record a tool call for later session matching.

#### `match_tool_call_session(tool_name, tool_inputs) -> session_id`
Find which session made a specific tool call.

### Utility Methods

#### `generate_project_id(project_path) -> project_id`
Generate consistent project ID from path (static method).

#### `cleanup_old_sessions(max_age_hours=24) -> count`
Remove old sessions from database.

#### `get_current_context(tool_name=None, tool_inputs=None)`
Backwards compatibility method returning tuple of (project_id, project_path, project_name, transcript_path).

## Usage Examples

### Basic Session Registration
```python
session_manager = SessionManager(db_path)

# Register a global session
await session_manager.register_session(
    session_id="abc123",
    transcript_path="/path/to/transcript"
)

# Register a project session
await session_manager.register_session(
    session_id="xyz789",
    project_path="/home/user/my-project",
    project_name="My Project",
    transcript_path="/path/to/transcript"
)
```

### Getting Current Context
```python
# Get full context object
context = await session_manager.get_current_session_context()
if context:
    print(f"Project: {context.project_name}")
    print(f"Scope: {context.scope}")

# Backwards compatible tuple
project_id, project_path, project_name, transcript_path = \
    await session_manager.get_current_context()
```

### Tool Call Tracking
```python
# Record a tool call
await session_manager.record_tool_call(
    session_id="abc123",
    tool_name="send_message",
    tool_inputs={"channel": "general", "text": "Hello"}
)

# Later, match the tool call to find the session
session_id = await session_manager.match_tool_call_session(
    tool_name="send_message",
    tool_inputs={"channel": "general", "text": "Hello"}
)
```

## Integration with Other Managers

The SessionManager provides context to other managers without depending on them:

```python
# ChannelManager uses SessionManager for project context
session_manager = SessionManager(db_path)
channel_manager = ChannelManager(db_path, session_manager)

# Get project context for channel operations
context = await session_manager.get_current_session_context()
if context and context.project_id:
    await channel_manager.create_channel("dev", "project", context.project_id)
```

## Database Schema

The SessionManager works with these tables:

```sql
-- Sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    project_path TEXT,
    project_name TEXT,
    transcript_path TEXT,
    scope TEXT NOT NULL DEFAULT 'global',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Projects table
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    metadata JSON
);

-- Tool calls table
CREATE TABLE tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_inputs_hash TEXT NOT NULL,
    tool_inputs JSON,
    called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

## Benefits

1. **Clear Separation**: Pure session management, no mixed concerns
2. **Foundation Layer**: Provides context for all other operations
3. **Performance**: Built-in caching reduces database queries
4. **Reliability**: Fallback mechanisms for finding current session
5. **Maintainability**: Simple, focused API that's easy to test