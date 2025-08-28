# Database-Level Operations

These operations are available through `api.db` and provide lower-level access to project management and database operations.

## Project Management

These methods must be called directly on the database instance (`api.db`) as they are not exposed through the main API.

### register_project

Register a new project in the system.

```python
await api.db.register_project(
    project_id: str,
    path: str,
    name: str,
    metadata: Optional[Dict] = None
) -> bool
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | str | Yes | Unique project identifier |
| `path` | str | Yes | File system path to project |
| `name` | str | Yes | Human-readable project name |
| `metadata` | Dict | No | Additional project metadata |

#### Returns

`bool`: True if successfully registered

#### Example

```python
success = await api.db.register_project(
    project_id="analytics",
    path="/workspace/analytics",
    name="Analytics Platform",
    metadata={
        "team": "data-science",
        "language": "python",
        "status": "active"
    }
)
```

---

### get_project

Get information about a specific project.

```python
await api.db.get_project(
    project_id: str
) -> Optional[Dict]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | str | Yes | Project identifier |

#### Returns

`Optional[Dict]`: Project information or None if not found

#### Project Dictionary Structure

```python
{
    "id": "analytics",
    "path": "/workspace/analytics",
    "name": "Analytics Platform",
    "metadata": {"team": "data-science"},
    "created_at": "2024-01-01T00:00:00Z"
}
```

---

### list_projects

List all registered projects.

```python
await api.db.list_projects() -> List[Dict]
```

#### Returns

`List[Dict]`: List of all projects

#### Example

```python
projects = await api.db.list_projects()
for project in projects:
    print(f"{project['id']}: {project['name']} ({project['path']})")
```

---

### add_project_link

Create a link between two projects, allowing agents to communicate across projects.

```python
await api.db.add_project_link(
    project_a_id: str,
    project_b_id: str,
    link_type: str = "bidirectional",
    metadata: Optional[Dict] = None
) -> bool
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_a_id` | str | Yes | - | First project ID |
| `project_b_id` | str | Yes | - | Second project ID |
| `link_type` | str | No | "bidirectional" | Link type (see below) |
| `metadata` | Dict | No | None | Link metadata |

#### Link Types

| Type | Description |
|------|-------------|
| `"bidirectional"` | Both projects can see each other's agents |
| `"a_to_b"` | Project A can see Project B's agents |
| `"b_to_a"` | Project B can see Project A's agents |

#### Returns

`bool`: True if link created successfully

#### Example

```python
# Allow analytics and frontend projects to communicate
await api.db.add_project_link(
    project_a_id="analytics",
    project_b_id="frontend",
    link_type="bidirectional",
    metadata={"purpose": "data visualization integration"}
)
```

---

### get_project_links

Get all projects linked to a given project.

```python
await api.db.get_project_links(
    project_id: str
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | str | Yes | Project to get links for |

#### Returns

`List[Dict]`: List of linked projects

#### Link Dictionary Structure

```python
{
    "linked_project_id": "frontend",
    "linked_project_name": "Frontend App",
    "linked_project_path": "/workspace/frontend",
    "link_type": "bidirectional",
    "enabled": True,
    "created_at": "2024-01-15T00:00:00Z"
}
```

---

### remove_project_link

Remove a link between two projects.

```python
await api.db.remove_project_link(
    project_a_id: str,
    project_b_id: str
) -> bool
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_a_id` | str | Yes | First project ID |
| `project_b_id` | str | Yes | Second project ID |

#### Returns

`bool`: True if link removed successfully

---

## Direct SQLite Access

For advanced use cases, you can access the SQLite store directly:

```python
# Get agent channels (permission-aware)
channels = await api.db.sqlite.get_agent_channels(
    agent_name="alice",
    agent_project_id="myproject",
    include_archived=False
)

# Check if agent can access a channel
can_access = await api.db.sqlite.check_agent_can_access_channel(
    agent_name="alice",
    agent_project_id="myproject",
    channel_id="global:general"
)

# Get discoverable agents
agents = await api.db.sqlite.get_discoverable_agents(
    requesting_project="myproject"
)

# Check DM permissions
can_dm = await api.db.sqlite.check_dm_permission(
    sender_name="alice",
    sender_project_id="proj1",
    recipient_name="bob",
    recipient_project_id="proj2"
)
```

## Direct Qdrant Access

If Qdrant is configured, you can access it directly for advanced vector operations:

```python
if api.db.qdrant:
    # Index a message manually
    await api.db.qdrant.index_message(
        message_id=123,
        content="Message content",
        metadata={"custom": "data"},
        channel_id="global:general",
        sender_id="alice",
        timestamp=datetime.now()
    )
    
    # Delete a message from index
    await api.db.qdrant.delete_message(message_id=123)
    
    # Search with custom parameters
    results = await api.db.qdrant.search(
        query="search text",
        filters={"channel_id": "global:general"},
        limit=10,
        score_threshold=0.7
    )
```

## Transaction Management

The SQLite store uses a connection pool with automatic transaction management:

```python
# Methods decorated with @with_connection handle transactions automatically
# For custom transactions, use the connection pool directly:

async with api.db.sqlite.pool.connection() as conn:
    async with conn.transaction():
        # Multiple operations in a single transaction
        await conn.execute("INSERT INTO ...", params)
        await conn.execute("UPDATE ...", params)
        # Automatically commits on success, rolls back on error
```

## Schema Information

### Core Tables

1. **projects**: Project registry
   - id, path, name, metadata, created_at

2. **agents**: Agent registry
   - name, project_id, description, dm_policy, discoverable, metadata

3. **channels**: Channel definitions
   - id, type, access_type, scope, name, description, project_id

4. **messages**: Message storage
   - id, channel_id, sender_id, content, metadata, timestamp

5. **channel_members**: Channel membership
   - channel_id, agent_name, agent_project_id, permissions

6. **project_links**: Project relationships
   - project_a_id, project_b_id, link_type, metadata

### Views

1. **agent_channels**: Permission-aware channel access view
   - Joins channels, members, and permissions
   - Used for all permission-checked operations

## Performance Considerations

### Connection Pooling

The SQLite store uses connection pooling for better performance:

```python
# Default pool size is based on CPU count
# Can be configured if needed
api.db.sqlite.pool = ConnectionPool(
    factory=lambda: aiosqlite.connect(db_path),
    size=10  # Custom pool size
)
```

### Write-Ahead Logging (WAL)

WAL mode is enabled by default for better concurrency:

```python
# Automatically set during initialization:
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;
```

### Indexes

The following indexes are created for performance:

```sql
-- Message retrieval
CREATE INDEX idx_messages_channel ON messages(channel_id);
CREATE INDEX idx_messages_sender ON messages(sender_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);

-- Channel operations
CREATE INDEX idx_channel_members ON channel_members(agent_name, agent_project_id);

-- Project links
CREATE INDEX idx_project_links ON project_links(project_a_id, project_b_id);
```

## Migration Support

The database schema is versioned and supports migrations:

```python
# Check current schema version
version = await api.db.sqlite.get_schema_version()

# Migrations are applied automatically during initialize()
await api.initialize()  # Applies any pending migrations
```

## Backup and Restore

```python
import shutil

# Backup the database
shutil.copy(api.db_path, "backup.db")

# For Qdrant (if configured)
if api.db.qdrant:
    # Qdrant backup depends on deployment type
    # Local: copy the storage directory
    # Cloud: use Qdrant's snapshot API
    pass
```

## Monitoring and Debugging

```python
# Get database statistics
stats = await api.db.sqlite.get_statistics()
print(f"Total messages: {stats['message_count']}")
print(f"Total agents: {stats['agent_count']}")
print(f"Total channels: {stats['channel_count']}")

# Check connection pool status
pool_info = api.db.sqlite.pool.info()
print(f"Active connections: {pool_info['active']}")
print(f"Idle connections: {pool_info['idle']}")

# Enable query logging for debugging
import logging
logging.getLogger('aiosqlite').setLevel(logging.DEBUG)
```

## Common Patterns

### Project Setup

```python
async def setup_project(api, project_id, project_name, agents):
    """Complete project setup with agents and channels"""
    
    # Register project
    await api.db.register_project(
        project_id=project_id,
        path=f"/workspace/{project_id}",
        name=project_name
    )
    
    # Register agents
    for agent in agents:
        await api.register_agent(
            name=agent['name'],
            project_id=project_id,
            description=agent.get('description', ''),
            dm_policy=agent.get('dm_policy', 'open')
        )
    
    # Create project channel
    channel_id = await api.create_channel(
        name="team",
        description=f"{project_name} team channel",
        created_by=agents[0]['name'],
        created_by_project_id=project_id,
        scope="project",
        project_id=project_id
    )
    
    # Add all agents to team channel
    for agent in agents:
        await api.join_channel(
            agent_name=agent['name'],
            agent_project_id=project_id,
            channel_id=channel_id
        )
    
    return channel_id
```

### Cross-Project Communication

```python
async def enable_cross_project_communication(api, project_pairs):
    """Enable communication between multiple projects"""
    
    for proj_a, proj_b in project_pairs:
        # Create bidirectional link
        await api.db.add_project_link(
            project_a_id=proj_a,
            project_b_id=proj_b,
            link_type="bidirectional"
        )
        
        # Verify link
        links_a = await api.db.get_project_links(proj_a)
        links_b = await api.db.get_project_links(proj_b)
        
        assert any(l['linked_project_id'] == proj_b for l in links_a)
        assert any(l['linked_project_id'] == proj_a for l in links_b)
```

### Cleanup Operations

```python
async def cleanup_old_messages(api, days_to_keep=30):
    """Remove messages older than specified days"""
    
    cutoff = datetime.now() - timedelta(days=days_to_keep)
    
    # Direct SQL for cleanup (administrative operation)
    async with api.db.sqlite.pool.connection() as conn:
        await conn.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (cutoff,)
        )
        await conn.commit()
    
    # Also clean up Qdrant if configured
    if api.db.qdrant:
        # Qdrant doesn't have direct date filtering
        # Would need to track message IDs and delete individually
        pass
```