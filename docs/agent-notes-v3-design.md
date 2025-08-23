# Agent Notes in V3 Architecture

## Overview
Agent notes are private messages an agent leaves for themselves for future context recall. In the v3 unified channel system, these are implemented as private single-member channels.

## Design Approach

### Channel Structure
- **Channel Type**: `channel` (not `direct`)
- **Access Type**: `private` (fixed membership)
- **Channel ID**: `notes:{agent_name}:{agent_project_id|global}`
- **Name**: `notes-{agent_name}`
- **Description**: "Private notes for {agent_name}"
- **Membership**: Only the agent themselves

### Key Properties
1. **Private by design**: Access type `private` ensures no one else can join
2. **Single member**: Only the agent is a member
3. **Auto-provisioned**: Created automatically when agent first writes a note
4. **Searchable**: Agent can search their own notes
5. **Session-aware**: Notes can be tagged with session IDs
6. **Metadata-rich**: Support for tags, context, and other metadata

## Implementation in DatabaseManagerV3

```python
@with_connection(writer=True)
async def ensure_notes_channel(self, conn,
                              agent_name: str,
                              agent_project_id: Optional[str]) -> str:
    """Ensure a notes channel exists for an agent"""
    # Generate channel ID
    if agent_project_id:
        channel_id = f"notes:{agent_name}:{agent_project_id}"
        scope = 'project'
    else:
        channel_id = f"notes:{agent_name}:global"
        scope = 'global'
    
    # Check if exists
    cursor = await conn.execute(
        "SELECT id FROM channels WHERE id = ?", (channel_id,)
    )
    if await cursor.fetchone():
        return channel_id
    
    # Create the notes channel
    await conn.execute("""
        INSERT INTO channels (
            id, channel_type, access_type, scope, name, 
            project_id, description, created_at
        ) VALUES (?, 'channel', 'private', ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        channel_id, scope, f"notes-{agent_name}",
        agent_project_id if scope == 'project' else None,
        f"Private notes for {agent_name}"
    ))
    
    # Add the agent as the sole member
    await conn.execute("""
        INSERT INTO channel_members (
            channel_id, agent_name, agent_project_id, 
            role, can_send, joined_at
        ) VALUES (?, ?, ?, 'owner', TRUE, CURRENT_TIMESTAMP)
    """, (channel_id, agent_name, agent_project_id))
    
    # Auto-subscribe the agent
    await conn.execute("""
        INSERT INTO subscriptions (
            agent_name, agent_project_id, channel_id, subscribed_at
        ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (agent_name, agent_project_id, channel_id))
    
    return channel_id

@with_connection(writer=True)
async def write_note(self, conn,
                    agent_name: str,
                    agent_project_id: Optional[str],
                    content: str,
                    topic: str = "general",
                    tags: List[str] = None,
                    session_id: Optional[str] = None,
                    metadata: Optional[Dict] = None) -> int:
    """Write a note to agent's private notes channel"""
    
    # Ensure notes channel exists
    channel_id = await self.ensure_notes_channel(
        conn, agent_name, agent_project_id
    )
    
    # Prepare metadata
    note_metadata = {
        "type": "note",
        "tags": tags or [],
        "session_id": session_id,
        **(metadata or {})
    }
    
    # Insert the note as a message
    cursor = await conn.execute("""
        INSERT INTO messages (
            channel_id, topic_name, sender_id, sender_project_id,
            content, metadata, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id
    """, (
        channel_id, topic, agent_name, agent_project_id,
        content, json.dumps(note_metadata)
    ))
    
    row = await cursor.fetchone()
    return row[0] if row else None
```

## Advantages of This Approach

1. **Unified System**: Notes use the same channel/message infrastructure
2. **Permission Consistency**: Access controlled by standard channel membership
3. **Topics Support**: Notes can be organized by topics (e.g., "debugging", "learned", "todo")
4. **Standard Queries**: Can use existing message search/filter functionality
5. **Future-proof**: Easy to extend (e.g., shared notes channels for teams)

## Migration from V2

For existing notes in the old system:
1. Create private notes channels for each agent with notes
2. Migrate messages to the new structure
3. Preserve timestamps, tags, and metadata
4. Map old session IDs to new format

## Usage Examples

### Writing a Note
```python
# Agent writes a note to remember something
note_id = await db.write_note(
    agent_name="alice",
    agent_project_id=None,
    content="Remember: The authentication bug was caused by race condition in token refresh",
    topic="debugging",
    tags=["auth", "bug-fix", "race-condition"],
    session_id=current_session,
    metadata={
        "related_pr": "PR-123",
        "severity": "high"
    }
)
```

### Searching Notes
```python
# Search notes by content and tags
notes = await db.search_agent_notes(
    agent_name="alice",
    agent_project_id=None,
    query="authentication",
    tags=["bug-fix"],
    limit=10
)
```

### Getting Recent Notes
```python
# Get recent notes from current session
recent = await db.get_recent_notes(
    agent_name="alice",
    agent_project_id=None,
    session_id=current_session,
    limit=5
)
```

## Alternative Approaches Considered

### Option 2: Notes as DM to Self
- Create a DM channel where both participants are the same agent
- Pros: Reuses DM infrastructure
- Cons: Conceptually weird, may break DM assumptions

### Option 3: Separate Notes Table
- Keep notes in a dedicated table outside the channel system
- Pros: Simple, independent
- Cons: Duplicates functionality, inconsistent with unified approach

### Option 4: Special Channel Type
- Create a new channel_type = 'notes'
- Pros: Explicit type
- Cons: Adds complexity, needs special handling

## Recommendation

Use **Option 1: Private Single-Member Channels** because:
- It's the most consistent with our unified channel architecture
- Reuses all existing infrastructure (permissions, messages, search)
- Natural extension of the channel concept
- Easy to understand and maintain
- Allows future extension (e.g., team notes channels)