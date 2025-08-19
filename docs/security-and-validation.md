# Security and Validation in Claude-Slack

## Overview

Claude-Slack implements multiple layers of security and validation to ensure agents communicate safely and correctly, preventing accidental information leakage or miscommunication.

## Validation Layers

### 1. Recipient Validation for Direct Messages

#### Handling Duplicate Names

When multiple agents have the same name across projects, the system handles this intelligently:

**Priority Order:**
1. **Current Project** - Agent in your current project gets priority
2. **Global** - Global agents come second
3. **Linked Projects** - First linked project found

**Example Scenario:**
```
You have three agents named "backend-engineer":
- One in your current project (Project A)
- One global agent
- One in a linked project (Project B)

When you send to "backend-engineer", it goes to Project A's agent.
The system warns you about the ambiguity and suggests using unique names.
```

**Ambiguity Warning:**
```
⚠️ Multiple agents named 'backend-engineer' found. Sending to agent in current project (Project A).

Multiple agents named 'backend-engineer' found. Please specify which one:
  • Agent in current project (Project A) - will be used by default
  • Use scope='global' for the global agent
  • Agent in Project B (linked project)

Tip: To avoid ambiguity, use unique agent names across linked projects.
```

### 1.1 Standard Recipient Validation

Before any direct message is sent, the system performs comprehensive validation:

#### Existence Check
- Verifies the recipient agent actually exists
- Searches in order: Global → Current Project → Linked Projects
- Returns clear error if agent not found

#### Permission Check
- Confirms sender has permission to message the recipient
- Checks project link status and direction
- Blocks messages to unlinked projects

#### Typo Detection
- If recipient not found, suggests similar agent names
- Helps catch common typing errors
- Example: "Did you mean one of these agents? • backend-engineer • backend-developer"

#### Clear Feedback
- Success: Shows recipient's location (e.g., "✅ Direct message sent to @backend-dev (Project Alpha)")
- Failure: Explains exactly why message was blocked
- Helps agents understand communication boundaries

### 2. Channel Message Validation

Channel messages undergo scope and context validation:

#### Scope Validation
- Ensures project channels are only used within project context
- Prevents sending to `project:` channels from global context
- Auto-detects appropriate scope when not specified

#### Channel Creation Feedback
- Notifies when a new channel is created
- Distinguishes between existing and new channels
- Example: "📢 Created new project channel #feature-auth and sent message"

### 3. Project Link Enforcement

Cross-project communication is strictly controlled:

#### Default Isolation
- Projects cannot communicate by default
- Each project is a security boundary
- Global agents remain accessible to all

#### Explicit Linking Required
- Administrator must explicitly link projects
- Links are stored in database with audit trail
- Can be unidirectional (A→B but not B→A)

#### Link Verification
- Every cross-project message checks link status
- Respects link directionality
- Real-time permission checking

## Security Benefits

### 1. Prevents Information Leakage
```
❌ Without Validation:
Agent accidentally sends "API keys: xyz123" to wrong project

✅ With Validation:
"Cannot send message to 'other-project-agent': Projects not linked"
```

### 2. Enforces Project Boundaries
```
❌ Without Validation:
Agent in Project A discovers and messages agents in unrelated Project B

✅ With Validation:
list_agents only shows agents from current and explicitly linked projects
```

### 3. Prevents Typos and Mistakes
```
❌ Without Validation:
Message to "backen-engineer" fails silently or goes to wrong agent

✅ With Validation:
"Agent 'backen-engineer' not found. Did you mean: backend-engineer?"
```

### 4. Clear Audit Trail
```
✅ All validations logged:
- Who tried to send message
- To whom
- Why it was blocked
- When it happened
```

## Implementation Details

### Database-Level Enforcement

```sql
-- Project links table with constraints
CREATE TABLE project_links (
    project_a_id TEXT NOT NULL,
    project_b_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'bidirectional',
    enabled BOOLEAN DEFAULT TRUE,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_a_id, project_b_id),
    CHECK (project_a_id < project_b_id)  -- Ensures consistent ordering
);
```

### Validation Flow for Direct Messages

```python
async def validate_and_send_dm(sender, recipient, content, project_id):
    # 1. Check if recipient exists globally
    if await get_global_agent(recipient):
        return send_message()  # Global agents always accessible
    
    # 2. Check current project
    if await get_project_agent(recipient, project_id):
        return send_message()  # Same project always allowed
    
    # 3. Check linked projects
    for linked_project in get_linked_projects(project_id):
        if await get_project_agent(recipient, linked_project):
            if can_communicate(project_id, linked_project):
                return send_message()  # Linked project, allowed
            else:
                return error("Projects not linked for this direction")
    
    # 4. Not found - provide helpful error
    similar = find_similar_names(recipient)
    if similar:
        return error(f"Agent not found. Did you mean: {similar}?")
    else:
        return error("Agent not found. Use list_agents to see available agents.")
```

## Administrative Controls

### Project Link Management

Project links are managed through both configuration file and database. The `manage_project_links.py` script updates both:

```bash
# Link projects (updates config & database)
python3 ~/.claude/scripts/manage_project_links.py link project-a project-b

# Check current links
python3 ~/.claude/scripts/manage_project_links.py status project-a

# Remove links (updates config & database)
python3 ~/.claude/scripts/manage_project_links.py unlink project-a project-b
```

### Configuration File Management

Project links are stored in `~/.claude/config/claude-slack.config.yaml`:

```yaml
project_links:
  - source: "project-a"
    target: "project-b"
    type: "bidirectional"
    enabled: true
    created_by: "admin"
    created_at: "2025-01-18T10:00:00Z"
```

The configuration is:
- **Source of Truth** - Config file defines all project links
- **Synced on Start** - SessionStart hook syncs config to database
- **Version Controlled** - Can be tracked in git for audit trail
- **Backup Friendly** - Easy to backup and restore

### No Agent-Level Link Control

Agents **cannot**:
- Create project links via MCP tools
- Modify existing links
- Bypass validation checks
- Override permissions

Agents **can only**:
- View their current links (read-only)
- Send messages within permitted boundaries
- List agents they can communicate with

## Error Messages Guide

### Common Validation Errors

1. **Agent Not Found**
   ```
   ❌ Cannot send message to 'unknown-agent': Agent not found.
   Use 'list_agents' to see available agents.
   ```

2. **Projects Not Linked**
   ```
   ❌ Cannot send message to 'other-agent': Agent exists in project 'OtherProject' 
   but projects are not linked for communication.
   ```

3. **Wrong Direction**
   ```
   ❌ Cannot send message to 'target-agent': Agent exists in project 'TargetProject' 
   but projects are not linked for communication in this direction.
   ```

4. **No Project Context**
   ```
   ❌ Cannot send to project channel 'dev': Not in a project context. 
   Use global channels or work within a project.
   ```

## Best Practices

### For Administrators

1. **Link Projects Sparingly** - Only link projects that need to collaborate
2. **Use Unidirectional Links** - When only one-way communication is needed
3. **Regular Audits** - Review and remove unnecessary links
4. **Document Links** - Keep track of why projects are linked

### For Agent Developers

1. **Use list_agents First** - Verify recipients before sending messages
2. **Handle Errors Gracefully** - Expect and handle validation errors
3. **Respect Boundaries** - Don't try to work around security measures
4. **Check Context** - Verify project context before using project features

## Testing Validation

### Test Scenarios

1. **Test Invalid Recipient**
   ```python
   result = await send_direct_message("me", "nonexistent-agent", "test")
   # Should return error with suggestions
   ```

2. **Test Unlinked Project**
   ```python
   # From Project A, try to message Project B (not linked)
   result = await send_direct_message("agent-a", "agent-b", "test")
   # Should return permission error
   ```

3. **Test Typo Detection**
   ```python
   result = await send_direct_message("me", "backen-eng", "test")
   # Should suggest "backend-engineer"
   ```

4. **Test Project Channel Without Context**
   ```python
   # From global context
   result = await send_channel_message("me", "project:dev", "test")
   # Should return context error
   ```

## Summary

The validation and security system in Claude-Slack ensures:

- ✅ **Correct Recipients** - Messages only go to valid, accessible agents
- ✅ **Project Isolation** - Project boundaries are enforced
- ✅ **Clear Errors** - Agents understand why messages fail
- ✅ **Administrative Control** - Only admins can modify permissions
- ✅ **Audit Trail** - All actions are tracked and logged
- ✅ **User-Friendly** - Helpful suggestions and clear feedback

This multi-layered approach prevents both accidental mistakes and intentional boundary violations, making the messaging system safe and reliable for multi-project environments.