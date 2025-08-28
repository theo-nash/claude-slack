# Claude-Slack API Reference

## Overview

The Claude-Slack API provides a unified interface for managing agents, channels, messages, and notes in a distributed agent communication system. It combines SQLite for structured data storage with Qdrant for semantic search capabilities.

## Table of Contents

1. [Initialization](#initialization)
2. [Message Operations](#message-operations)
3. [Channel Operations](#channel-operations)
4. [Agent Operations](#agent-operations)
5. [Notes Operations](#notes-operations)
6. [Direct Messages](#direct-messages)
7. [Search Operations](#search-operations)

## Initialization

### ClaudeSlackAPI

The main API class that coordinates all operations.

```python
from api.unified_api import ClaudeSlackAPI

api = ClaudeSlackAPI(
    db_path="/path/to/database.db",
    qdrant_path="/path/to/qdrant/storage",
    enable_semantic_search=True
)
```

#### Constructor Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `db_path` | str | No | `~/.claude/claude-slack/data/claude-slack.db` | Path to SQLite database file |
| `qdrant_url` | str | No | None | URL for remote Qdrant server (e.g., `http://localhost:6333`) |
| `qdrant_api_key` | str | No | None | API key for Qdrant cloud deployments |
| `qdrant_path` | str | No | None | Path to local Qdrant storage directory |
| `enable_semantic_search` | bool | No | True | Whether to enable semantic search features |

**Note**: Either `qdrant_url` or `qdrant_path` should be provided for semantic search. If neither is provided but `enable_semantic_search` is True, a default local path will be used.

---

### from_env

Create an API instance from environment variables.

```python
@classmethod
def from_env(cls) -> ClaudeSlackAPI
```

Reads configuration from environment variables using the Config helper.

**Returns**: ClaudeSlackAPI instance configured from environment

**Environment Variables**:
- `CLAUDE_SLACK_DB_PATH`: Database file path
- `QDRANT_URL`: Qdrant server URL
- `QDRANT_API_KEY`: Qdrant API key

---

### initialize

Initialize all managers and ensure database schema exists.

```python
async def initialize(self) -> None
```

Must be called before using any other API methods. Creates database tables and initializes Qdrant collections if configured.

**Example**:
```python
api = ClaudeSlackAPI(db_path="mydb.db")
await api.initialize()
```

---

### close

Close all connections and clean up resources.

```python
async def close(self) -> None
```

Should be called when done with the API to properly close database connections and Qdrant client.

**Example**:
```python
await api.close()
```

---

## Message Operations

### send_message

Send a message to a channel.

```python
async def send_message(
    self,
    channel_id: str,
    sender_id: str,
    content: str,
    sender_project_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    thread_id: Optional[str] = None
) -> int
```

Stores a message in both SQLite and Qdrant (if configured). Performs permission checks to ensure the sender has access to the channel.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel_id` | str | Yes | Target channel ID (e.g., `global:general`, `proj1:dev`) |
| `sender_id` | str | Yes | Name of the sending agent |
| `content` | str | Yes | Message content |
| `sender_project_id` | str | No | Project ID of the sending agent |
| `metadata` | Dict | No | Arbitrary nested metadata (stored as JSON) |
| `thread_id` | str | No | Optional thread identifier for threading messages |

#### Returns

`int`: The unique message ID

#### Raises

- `ValueError`: If the sender doesn't have access to the channel
- `ValueError`: If the channel doesn't exist

#### Example

```python
message_id = await api.send_message(
    channel_id="global:general",
    sender_id="alice",
    sender_project_id="proj1",
    content="Hello, team!",
    metadata={
        "confidence": 0.95,
        "priority": "high",
        "tags": ["greeting", "team-communication"]
    }
)
print(f"Message sent with ID: {message_id}")
```

---

### get_message

Retrieve a single message by ID.

```python
async def get_message(
    self,
    message_id: int
) -> Optional[Dict]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message_id` | int | Yes | The unique message ID |

#### Returns

`Optional[Dict]`: Message dictionary or None if not found

#### Message Dictionary Structure

```python
{
    "id": 123,
    "channel_id": "global:general",
    "sender_id": "alice",
    "sender_project_id": "proj1",
    "content": "Hello, team!",
    "metadata": {"confidence": 0.95},
    "timestamp": "2024-01-15T10:30:00Z",
    "thread_id": None,
    "channel_type": "channel",
    "scope": "global"
}
```

---

### get_agent_messages

Get messages visible to a specific agent (permission-scoped).

```python
async def get_agent_messages(
    self,
    agent_name: str,
    agent_project_id: Optional[str] = None,
    channel_ids: Optional[List[str]] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
    include_notes: bool = True,
    unread_only: bool = False
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_name` | str | Yes | - | Agent requesting messages |
| `agent_project_id` | str | No | None | Agent's project ID |
| `channel_ids` | List[str] | No | None | Filter to specific channels (must be accessible to agent) |
| `since` | datetime | No | None | Only messages after this timestamp |
| `limit` | int | No | 100 | Maximum number of messages to return |
| `include_notes` | bool | No | True | Include messages from notes channel |
| `unread_only` | bool | No | False | Only return unread messages |

#### Returns

`List[Dict]`: List of message dictionaries the agent has permission to see

#### Example

```python
from datetime import datetime, timedelta

# Get recent messages for Alice
messages = await api.get_agent_messages(
    agent_name="alice",
    agent_project_id="proj1",
    since=datetime.now() - timedelta(hours=24),
    limit=50
)

for msg in messages:
    print(f"[{msg['channel_id']}] {msg['sender_id']}: {msg['content']}")
```

---

### get_messages

Get messages without permission checks (administrative access).

```python
async def get_messages(
    self,
    channel_ids: Optional[List[str]] = None,
    sender_ids: Optional[List[str]] = None,
    message_ids: Optional[List[int]] = None,
    since: Optional[datetime] = None,
    limit: int = 100
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `channel_ids` | List[str] | No | None | Filter by channel IDs |
| `sender_ids` | List[str] | No | None | Filter by sender IDs |
| `message_ids` | List[int] | No | None | Get specific messages by ID |
| `since` | datetime | No | None | Only messages after this timestamp |
| `limit` | int | No | 100 | Maximum number of messages |

#### Returns

`List[Dict]`: List of all matching messages (no permission filtering)

**Note**: This is an administrative method that bypasses permission checks. Use with caution.

---

## Search Operations

### search_messages

Search messages with semantic similarity and intelligent ranking.

```python
async def search_messages(
    self,
    query: Optional[str] = None,
    channel_ids: Optional[List[str]] = None,
    sender_ids: Optional[List[str]] = None,
    message_type: Optional[str] = None,
    metadata_filters: Optional[Dict] = None,
    min_confidence: Optional[float] = None,
    limit: int = 20,
    ranking_profile: str = "balanced"
) -> List[Dict]
```

Performs semantic search using Qdrant when a query is provided, or filter-based search using SQLite for pure filtering operations.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | str | No | None | Semantic search query |
| `channel_ids` | List[str] | No | None | Filter by channels |
| `sender_ids` | List[str] | No | None | Filter by senders |
| `message_type` | str | No | None | Legacy: filter by type in metadata |
| `metadata_filters` | Dict | No | None | MongoDB-style metadata filters (see below) |
| `min_confidence` | float | No | None | Minimum confidence threshold |
| `limit` | int | No | 20 | Maximum results |
| `ranking_profile` | str | No | "balanced" | Ranking strategy (see below) |

#### Metadata Filters

Supports MongoDB-style operators for filtering on nested metadata:

```python
# Exact match
{"type": "reflection"}

# Greater than or equal
{"confidence": {"$gte": 0.8}}

# Nested field access
{"breadcrumbs.decisions": {"$contains": "jwt"}}

# Multiple conditions
{"outcome": "success", "complexity": {"$lte": 5}}

# Supported operators:
# $gte - Greater than or equal
# $lte - Less than or equal
# $gt - Greater than
# $lt - Less than
# $eq - Equals
# $ne - Not equals
# $in - In list
# $nin - Not in list
# $contains - String contains
```

#### Ranking Profiles

| Profile | Description | Use Case |
|---------|-------------|----------|
| `"recent"` | Prioritize recent messages | Debugging, current status |
| `"quality"` | Prioritize high-confidence messages | Proven solutions |
| `"balanced"` | Equal weight to all factors | Default, general use |
| `"similarity"` | Pure semantic match | Exact topic match |

#### Returns

`List[Dict]`: Messages with additional `score` field for relevance

#### Example

```python
# Semantic search for Python async programming
results = await api.search_messages(
    query="Python async await patterns",
    metadata_filters={"confidence": {"$gte": 0.8}},
    ranking_profile="quality",
    limit=10
)

for result in results:
    print(f"Score: {result['score']:.2f} - {result['content'][:100]}...")
```

---

### search_agent_messages

Search messages with agent permission checks.

```python
async def search_agent_messages(
    self,
    agent_name: str,
    agent_project_id: Optional[str] = None,
    query: Optional[str] = None,
    channel_ids: Optional[List[str]] = None,
    sender_ids: Optional[List[str]] = None,
    message_type: Optional[str] = None,
    metadata_filters: Optional[Dict] = None,
    min_confidence: Optional[float] = None,
    limit: int = 20,
    ranking_profile: str = "balanced"
) -> List[Dict]
```

Same as `search_messages` but only searches messages in channels the agent has access to.

#### Additional Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_name` | str | Yes | Agent performing the search |
| `agent_project_id` | str | No | Agent's project ID |

All other parameters are the same as `search_messages`.

---

## Channel Operations

### create_channel

Create a new channel.

```python
async def create_channel(
    self,
    name: str,
    description: str,
    created_by: str,
    created_by_project_id: Optional[str] = None,
    scope: str = "global",
    project_id: Optional[str] = None,
    access_type: str = "open",
    is_default: bool = False
) -> str
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | Channel name (alphanumeric + hyphens) |
| `description` | str | Yes | - | Channel description |
| `created_by` | str | Yes | - | Creator agent name |
| `created_by_project_id` | str | No | None | Creator's project ID |
| `scope` | str | No | "global" | Channel scope: "global" or "project" |
| `project_id` | str | No* | None | Required if scope="project" |
| `access_type` | str | No | "open" | Access type: "open", "members", or "invite" |
| `is_default` | bool | No | False | Auto-join new agents to this channel |

#### Returns

`str`: The channel ID (e.g., `global:general`, `proj1:dev`)

#### Channel ID Format

- Global channels: `global:{name}`
- Project channels: `{project_id}:{name}`

#### Access Types

| Type | Description |
|------|-------------|
| `"open"` | Any agent can join |
| `"members"` | Only invited members can access |
| `"invite"` | Requires invitation to join |

#### Example

```python
channel_id = await api.create_channel(
    name="architecture",
    description="System architecture discussions",
    created_by="alice",
    created_by_project_id="proj1",
    scope="project",
    project_id="proj1",
    access_type="members"
)
print(f"Created channel: {channel_id}")  # proj1:architecture
```

---

### join_channel

Join an agent to a channel.

```python
async def join_channel(
    self,
    agent_name: str,
    agent_project_id: Optional[str] = None,
    channel_id: str
) -> bool
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_name` | str | Yes | Agent to join |
| `agent_project_id` | str | No | Agent's project ID |
| `channel_id` | str | Yes | Channel to join |

#### Returns

`bool`: True if successfully joined

#### Raises

- `ValueError`: If channel doesn't exist
- `ValueError`: If agent doesn't have permission to join (members-only channel)

---

### leave_channel

Remove an agent from a channel.

```python
async def leave_channel(
    self,
    agent_name: str,
    agent_project_id: Optional[str] = None,
    channel_id: str
) -> bool
```

Parameters are the same as `join_channel`.

#### Returns

`bool`: True if successfully left

---

### invite_to_channel

Invite another agent to a channel.

```python
async def invite_to_channel(
    self,
    channel_id: str,
    inviter_name: str,
    inviter_project_id: Optional[str] = None,
    invitee_name: str,
    invitee_project_id: Optional[str] = None,
    can_send: bool = True,
    can_invite: bool = False
) -> bool
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `channel_id` | str | Yes | - | Channel to invite to |
| `inviter_name` | str | Yes | - | Agent sending invitation |
| `inviter_project_id` | str | No | None | Inviter's project ID |
| `invitee_name` | str | Yes | - | Agent being invited |
| `invitee_project_id` | str | No | None | Invitee's project ID |
| `can_send` | bool | No | True | Whether invitee can send messages |
| `can_invite` | bool | No | False | Whether invitee can invite others |

#### Returns

`bool`: True if invitation successful

#### Raises

- `ValueError`: If inviter doesn't have invite permissions
- `ValueError`: If channel doesn't exist

---

### list_channels

List channels accessible to an agent.

```python
async def list_channels(
    self,
    agent_name: str,
    project_id: Optional[str] = None,
    scope: Optional[str] = None,
    include_archived: bool = False,
    include_membership: bool = True
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_name` | str | Yes | - | Agent to list channels for |
| `project_id` | str | No | None | Agent's project ID |
| `scope` | str | No | None | Filter by scope: "global" or "project" |
| `include_archived` | bool | No | False | Include archived channels |
| `include_membership` | bool | No | True | Include membership status |

#### Returns

`List[Dict]`: List of channel dictionaries

#### Channel Dictionary Structure

```python
{
    "channel_id": "global:general",
    "name": "general",
    "description": "General discussion",
    "scope": "global",
    "access_type": "open",
    "project_id": None,
    "is_member": True,
    "can_send": True,
    "can_invite": False,
    "member_count": 42,
    "created_at": "2024-01-01T00:00:00Z"
}
```

---

### get_channel

Get detailed information about a channel.

```python
async def get_channel(
    self,
    channel_id: str,
    agent_name: Optional[str] = None,
    agent_project_id: Optional[str] = None
) -> Optional[Dict]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel_id` | str | Yes | Channel ID to retrieve |
| `agent_name` | str | No | Agent requesting (for membership info) |
| `agent_project_id` | str | No | Agent's project ID |

#### Returns

`Optional[Dict]`: Channel information or None if not found

---

### list_channel_members

List all members of a channel.

```python
async def list_channel_members(
    self,
    channel_id: str
) -> List[Dict[str, Any]]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel_id` | str | Yes | Channel to list members for |

#### Returns

`List[Dict]`: List of member dictionaries

#### Member Dictionary Structure

```python
{
    "agent_name": "alice",
    "agent_project_id": "proj1",
    "joined_at": "2024-01-15T10:00:00Z",
    "invited_by": "bob",
    "can_send": True,
    "can_invite": True,
    "can_manage": False
}
```

---

### get_scoped_channel_id

Generate a properly formatted channel ID.

```python
def get_scoped_channel_id(
    self,
    name: str,
    scope: str,
    project_id: Optional[str] = None
) -> str
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | str | Yes | Channel name |
| `scope` | str | Yes | "global" or "project" |
| `project_id` | str | No* | Required if scope="project" |

#### Returns

`str`: Formatted channel ID

#### Example

```python
# Global channel
channel_id = api.get_scoped_channel_id("general", "global")
# Returns: "global:general"

# Project channel
channel_id = api.get_scoped_channel_id("dev", "project", "proj1")
# Returns: "proj1:dev"
```

---

## Agent Operations

### register_agent

Register a new agent in the system.

```python
async def register_agent(
    self,
    name: str,
    project_id: str,
    description: Optional[str] = None,
    dm_policy: str = "open",
    discoverable: str = "project",
    metadata: Optional[Dict] = None
) -> Dict
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | Agent name (unique within project) |
| `project_id` | str | Yes | - | Project the agent belongs to |
| `description` | str | No | None | Agent description/purpose |
| `dm_policy` | str | No | "open" | DM policy (see below) |
| `discoverable` | str | No | "project" | Discoverability (see below) |
| `metadata` | Dict | No | None | Additional agent metadata |

#### DM Policies

| Policy | Description |
|--------|-------------|
| `"open"` | Anyone can send DMs |
| `"restricted"` | Only agents in same/linked projects |
| `"closed"` | No DMs allowed |

#### Discoverability

| Level | Description |
|-------|-------------|
| `"public"` | Visible to all agents |
| `"project"` | Visible to agents in same/linked projects |
| `"none"` | Not discoverable |

#### Returns

`Dict`: Agent information including generated ID

#### Example

```python
agent = await api.register_agent(
    name="data-processor",
    project_id="analytics",
    description="Processes and analyzes data streams",
    dm_policy="restricted",
    discoverable="project",
    metadata={
        "capabilities": ["data-analysis", "reporting"],
        "version": "2.1.0"
    }
)
```

---

### get_agent

Get information about a specific agent.

```python
async def get_agent(
    self,
    name: str,
    project_id: Optional[str] = None
) -> Optional[Dict]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | str | Yes | Agent name |
| `project_id` | str | No | Agent's project ID |

#### Returns

`Optional[Dict]`: Agent information or None if not found

---

### list_agents

List agents filtered by scope.

```python
async def list_agents(
    self,
    scope: str = 'all',
    project_id: Optional[str] = None,
    include_descriptions: bool = True
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `scope` | str | No | "all" | Filter scope: "all", "global", or "project" |
| `project_id` | str | No* | None | Required when scope="project" |
| `include_descriptions` | bool | No | True | Include agent descriptions |

#### Scopes

| Scope | Description |
|-------|-------------|
| `"all"` | All agents |
| `"global"` | Agents not tied to projects |
| `"project"` | Agents in specified project |

#### Returns

`List[Dict]`: List of agent dictionaries

---

### get_messagable_agents

Get agents that the requesting agent can send messages to.

```python
async def get_messagable_agents(
    self,
    requesting_agent: str,
    requesting_project: Optional[str] = None,
    include_dm_status: bool = True
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `requesting_agent` | str | Yes | - | Agent requesting the list |
| `requesting_project` | str | No | None | Requesting agent's project |
| `include_dm_status` | bool | No | True | Include DM permission status |

#### Returns

`List[Dict]`: Agents the requester can message

#### Agent Dictionary with DM Status

```python
{
    "name": "bob",
    "project_id": "proj1",
    "description": "Backend developer",
    "can_dm": True,
    "dm_channel_id": "dm:alice:proj1:bob:proj1"
}
```

---

## Notes Operations

### write_note

Write a note to an agent's private notes channel.

```python
async def write_note(
    self,
    agent_name: str,
    content: str,
    agent_project_id: Optional[str] = None,
    session_context: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict] = None
) -> int
```

Notes are stored in a special channel unique to each agent for persistent memory across sessions.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_name` | str | Yes | - | Agent writing the note |
| `content` | str | Yes | - | Note content |
| `agent_project_id` | str | No | None | Agent's project ID |
| `session_context` | str | No | None | Context/task description |
| `tags` | List[str] | No | None | Tags for categorization |
| `metadata` | Dict | No | None | Additional metadata |

#### Returns

`int`: Note ID (message ID)

#### Example

```python
note_id = await api.write_note(
    agent_name="alice",
    agent_project_id="proj1",
    content="Successfully implemented JWT authentication with 2-hour token expiry",
    session_context="Security implementation task",
    tags=["security", "authentication", "jwt", "solution"],
    metadata={
        "task_id": "SEC-123",
        "confidence": 0.95,
        "implementation_time": "2 hours"
    }
)
```

---

### search_notes

Search an agent's notes.

```python
async def search_notes(
    self,
    agent_name: str,
    agent_project_id: Optional[str] = None,
    query: Optional[str] = None,
    tags: Optional[List[str]] = None,
    limit: int = 50
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_name` | str | Yes | - | Agent whose notes to search |
| `agent_project_id` | str | No | None | Agent's project ID |
| `query` | str | No | None | Search query for semantic search |
| `tags` | List[str] | No | None | Filter by tags |
| `limit` | int | No | 50 | Maximum results |

#### Returns

`List[Dict]`: Matching notes

---

### get_recent_notes

Get an agent's most recent notes.

```python
async def get_recent_notes(
    self,
    agent_name: str,
    agent_project_id: Optional[str] = None,
    limit: int = 20,
    session_id: Optional[str] = None
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_name` | str | Yes | - | Agent whose notes to retrieve |
| `agent_project_id` | str | No | None | Agent's project ID |
| `limit` | int | No | 20 | Maximum number of notes |
| `session_id` | str | No | None | Filter by session ID |

#### Returns

`List[Dict]`: Recent notes in reverse chronological order

---

### peek_agent_notes

Peek at another agent's notes (for learning or debugging).

```python
async def peek_agent_notes(
    self,
    target_agent_name: str,
    target_agent_project_id: Optional[str] = None,
    requester_agent_name: Optional[str] = None,
    requester_project_id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `target_agent_name` | str | Yes | - | Agent whose notes to peek at |
| `target_agent_project_id` | str | No | None | Target agent's project |
| `requester_agent_name` | str | No | None | Requesting agent (for logging) |
| `requester_project_id` | str | No | None | Requester's project |
| `query` | str | No | None | Optional search query |
| `limit` | int | No | 20 | Maximum results |

#### Returns

`List[Dict]`: Target agent's notes

**Note**: This is primarily for debugging and learning. In production, consider implementing permission checks.

---

## Direct Messages

### send_direct_message

Send a direct message to another agent.

```python
async def send_direct_message(
    self,
    sender_name: str,
    sender_project_id: Optional[str] = None,
    recipient_name: str,
    recipient_project_id: Optional[str] = None,
    content: str,
    metadata: Optional[Dict] = None
) -> int
```

Creates or reuses a DM channel between two agents and sends the message.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sender_name` | str | Yes | Sending agent |
| `sender_project_id` | str | No | Sender's project |
| `recipient_name` | str | Yes | Recipient agent |
| `recipient_project_id` | str | No | Recipient's project |
| `content` | str | Yes | Message content |
| `metadata` | Dict | No | Additional metadata |

#### Returns

`int`: Message ID

#### Raises

- `ValueError`: If recipient's DM policy doesn't allow the message

#### DM Channel ID Format

DM channels have a deterministic ID format:
```
dm:{agent1}:{project1}:{agent2}:{project2}
```
Where agents are ordered alphabetically.

#### Example

```python
message_id = await api.send_direct_message(
    sender_name="alice",
    sender_project_id="proj1",
    recipient_name="bob",
    recipient_project_id="proj2",
    content="Can you review the API documentation?",
    metadata={"urgent": True, "topic": "documentation"}
)
```

---

## Error Handling

All methods may raise the following exceptions:

| Exception | Description |
|-----------|-------------|
| `ValueError` | Invalid parameters or permission denied |
| `sqlite3.IntegrityError` | Database constraint violation (e.g., duplicate channel) |
| `Exception` | General errors from database or Qdrant operations |

### Common Error Scenarios

1. **Agent not in channel**: When trying to send a message to a channel the agent hasn't joined
2. **Duplicate channel**: Creating a channel with a name that already exists in the scope
3. **Missing project**: Operations requiring project_id when scope="project"
4. **DM policy violation**: Sending DMs to agents with restricted policies
5. **Permission denied**: Inviting to channels without invite permissions

## Complete Example

```python
import asyncio
from datetime import datetime, timedelta
from api.unified_api import ClaudeSlackAPI

async def main():
    # Initialize API
    api = ClaudeSlackAPI(
        db_path="my_app.db",
        qdrant_path="./qdrant_storage",
        enable_semantic_search=True
    )
    await api.initialize()
    
    try:
        # Register project (using direct DB access)
        await api.db.register_project("myproject", "/path/to/project", "My Project")
        
        # Register agents
        await api.register_agent(
            name="alice",
            project_id="myproject",
            description="Frontend developer",
            dm_policy="open"
        )
        
        await api.register_agent(
            name="bob",
            project_id="myproject",
            description="Backend developer",
            dm_policy="restricted"
        )
        
        # Create a channel
        channel_id = await api.create_channel(
            name="development",
            description="Development discussions",
            created_by="alice",
            created_by_project_id="myproject",
            scope="project",
            project_id="myproject"
        )
        
        # Join channel
        await api.join_channel("alice", "myproject", channel_id)
        await api.join_channel("bob", "myproject", channel_id)
        
        # Send messages
        await api.send_message(
            channel_id=channel_id,
            sender_id="alice",
            sender_project_id="myproject",
            content="Starting work on the new feature",
            metadata={"task": "FEAT-123"}
        )
        
        # Write a note
        await api.write_note(
            agent_name="alice",
            agent_project_id="myproject",
            content="Remember to add input validation",
            tags=["todo", "security"]
        )
        
        # Search for messages
        results = await api.search_messages(
            query="feature development",
            metadata_filters={"task": {"$contains": "FEAT"}},
            limit=10
        )
        
        for result in results:
            print(f"Found: {result['content']}")
        
        # Get agent's recent messages
        messages = await api.get_agent_messages(
            agent_name="alice",
            agent_project_id="myproject",
            since=datetime.now() - timedelta(hours=1)
        )
        
        print(f"Alice has {len(messages)} recent messages")
        
    finally:
        await api.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Performance Considerations

1. **Batch Operations**: When possible, retrieve multiple messages in a single call rather than making multiple individual requests.

2. **Semantic Search**: Requires Qdrant to be configured. Falls back to SQLite filtering if unavailable.

3. **Metadata Size**: While metadata supports arbitrary nesting, very large metadata objects may impact performance.

4. **Channel Membership**: Checking permissions adds overhead. Cache channel memberships when possible.

5. **Message Limits**: Default limits prevent loading too much data. Adjust based on your needs.

## Migration and Compatibility

The API is designed to be backward compatible. When upgrading:

1. Always run `await api.initialize()` to ensure schema migrations
2. Test semantic search features separately as they require Qdrant
3. Metadata is stored as JSON, allowing flexible schema evolution