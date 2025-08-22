# Agent Notes System Guide

## Overview

The Agent Notes system provides a persistent knowledge base for each agent, allowing them to:
- **Persist learnings** across sessions
- **Build contextual memory** about projects and patterns
- **Share knowledge** with other agents (discoverable but not strictly private)
- **Support collective intelligence** through META agent aggregation

## Architecture

### Auto-Provisioning

When an agent is registered, the system automatically creates a private notes channel:

```
global:agent-notes:{agent_name}     # For global agents
proj_{id}:agent-notes:{agent_name}  # For project agents
```

This happens transparently through the DatabaseManager during agent registration.

### Database Schema

Notes are stored as messages with special attributes:

```sql
-- Channels table includes notes channels
channel_type TEXT DEFAULT 'standard',  -- 'standard' or 'agent-notes'
owner_agent_name TEXT,                 -- Owning agent
owner_agent_project_id TEXT            -- Agent's project

-- Messages table includes note metadata
tags TEXT,                             -- JSON array of tags
session_id TEXT                        -- Session context
```

### Privacy Model

Notes follow a **"discoverable-by-owner"** model:
- Each agent has full access to their own notes
- Other agents can "peek" at notes for learning
- META agents can aggregate across all notes
- Not strictly private, enabling collective intelligence

## MCP Tools

### Writing Notes

```python
# Basic note
write_note(
    agent_id="backend-engineer",
    content="Discovered that caching reduces API response time by 50%"
)

# Note with tags for categorization
write_note(
    agent_id="backend-engineer",
    content="Database indexing pattern: compound indexes on (user_id, timestamp)",
    tags=["performance", "database", "pattern"]
)

# Note with session context
write_note(
    agent_id="backend-engineer",
    content="User reported slow queries, fixed with index optimization",
    session_context="Debug session for ticket #1234",
    tags=["debug", "solution", "database"]
)
```

### Searching Notes

```python
# Search by content
results = search_my_notes(
    agent_id="backend-engineer",
    query="caching"
)

# Search by tags
results = search_my_notes(
    agent_id="backend-engineer",
    tags=["performance", "learned"]
)

# Combine query and tags
results = search_my_notes(
    agent_id="backend-engineer",
    query="API",
    tags=["pattern"]
)
```

### Retrieving Recent Notes

```python
# Get recent notes
notes = get_recent_notes(
    agent_id="backend-engineer",
    limit=10
)

# Get notes from specific session
notes = get_recent_notes(
    agent_id="backend-engineer",
    session_id="debug-session-123"
)
```

### Learning from Other Agents

```python
# Peek at another agent's notes
notes = peek_agent_notes(
    agent_id="frontend-engineer",
    target_agent="backend-engineer",
    query="API optimization"
)
```

## Use Cases

### 1. Debugging Patterns

Agent discovers and documents a debugging pattern:

```python
write_note(
    agent_id="debugger",
    content="Pattern: Memory leaks often occur in event listeners not being cleaned up. Check for missing removeEventListener calls.",
    tags=["pattern", "memory", "debugging"]
)
```

### 2. Performance Optimizations

Agent records performance improvements:

```python
write_note(
    agent_id="performance-optimizer",
    content="Implemented lazy loading for images. Page load time improved from 3.2s to 1.1s. Key: Intersection Observer API.",
    tags=["performance", "optimization", "metrics"]
)
```

### 3. Architecture Decisions

Agent documents architectural insights:

```python
write_note(
    agent_id="architect",
    content="Chose event-driven architecture for notification system. Pros: Decoupled, scalable. Cons: Complexity in debugging.",
    tags=["architecture", "decision", "tradeoffs"]
)
```

### 4. Learning from Failures

Agent records lessons from failures:

```python
write_note(
    agent_id="backend-engineer",
    content="Migration failed due to missing foreign key constraints. Lesson: Always verify referential integrity before migrations.",
    tags=["learned", "failure", "database", "migration"]
)
```

## META Agent Integration

The infrastructure supports future META agents that can:

### Aggregate Learnings

```python
# META agent searches across all agents' notes
all_performance_insights = []
for agent in list_agents():
    insights = peek_agent_notes(
        agent_id="meta-agent",
        target_agent=agent["name"],
        query="performance optimization"
    )
    all_performance_insights.extend(insights)

# Synthesize and broadcast findings
synthesized = analyze_patterns(all_performance_insights)
send_channel_message(
    agent_id="meta-agent",
    channel="best-practices",
    content=f"Performance patterns across all agents: {synthesized}"
)
```

### Pattern Detection

```python
# META agent identifies recurring issues
all_debug_notes = search_all_notes(tags=["debug", "solution"])
patterns = identify_recurring_patterns(all_debug_notes)

for pattern in patterns:
    write_note(
        agent_id="meta-agent",
        content=f"Recurring pattern detected: {pattern}",
        tags=["pattern", "aggregated", "insight"]
    )
```

### Knowledge Distribution

```python
# META agent shares collective insights
best_practices = compile_best_practices()
for practice in best_practices:
    send_channel_message(
        agent_id="meta-agent",
        channel="announcements",
        content=f"Best practice from collective learning: {practice}"
    )
```

## Implementation Details

### Database Initialization Pattern

The system uses a clean decorator pattern for ensuring database initialization:

```python
from db.initialization import DatabaseInitializer, ensure_db_initialized

class NotesManager(DatabaseInitializer):
    @ensure_db_initialized
    async def write_note(self, ...):
        # Database guaranteed to be initialized
        pass
```

### Token-Efficient Formatting

Notes are formatted for minimal token usage while preserving full context:

```
=== My Notes ===

[global/note #performance, #learned] "Cache improves response by 50%" (2h ago)
[project/note #debug, #solution] "Fixed memory leak in event handlers" (1d ago)
```

### Auto-Provisioning Flow

1. Agent registers via any path (MCP tool, session hook, etc.)
2. DatabaseManager.register_agent() is called
3. Auto-provisions notes channel if doesn't exist
4. Agent can immediately start writing notes

## Best Practices

### Tagging Strategy

Use consistent tags for better searchability:
- **Category**: `#performance`, `#security`, `#architecture`
- **Type**: `#pattern`, `#solution`, `#learned`, `#failure`
- **Component**: `#api`, `#database`, `#frontend`, `#backend`
- **Action**: `#debug`, `#optimize`, `#refactor`

### Content Guidelines

1. **Be Specific**: Include concrete details, metrics, and examples
2. **Add Context**: Include why something worked or failed
3. **Document Patterns**: Record recurring solutions and anti-patterns
4. **Include Tradeoffs**: Note pros/cons of decisions
5. **Link Resources**: Reference relevant files, commits, or documentation

### Session Context

Use session context to group related notes:

```python
session_id = f"feature-{ticket_id}"

# All notes for this feature implementation
write_note(..., session_id=session_id)
write_note(..., session_id=session_id)

# Later, retrieve all notes from that session
notes = get_recent_notes(session_id=session_id)
```

## Summary

The Agent Notes system provides:
- **Persistent memory** for agents across sessions
- **Knowledge sharing** between agents
- **Foundation for collective intelligence** via META agents
- **Auto-provisioning** for zero-configuration usage
- **Token-efficient** formatting for AI consumption
- **Flexible tagging** and search capabilities

This infrastructure enables agents to learn, remember, and share knowledge effectively, building towards a system where collective intelligence emerges from individual agent experiences.