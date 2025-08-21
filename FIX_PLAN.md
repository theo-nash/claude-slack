# Claude-Slack Fix Plan - Robust Solutions for Remaining Issues

## Current Status (2025-08-20)

### ✅ Working Features
- Project context detection via PreToolUse hook + session matching
- Agent attribution (after parser fix)
- Channel operations (list, subscribe, send messages)
- Basic messaging infrastructure

### ❌ Critical Issues Requiring Fixes

## Issue 1: send_direct_message - undefined sender_id

### Problem
- Line ~690-694 in server.py uses `sender_id` variable that's never defined
- The tool expects `sender_id` in arguments but handler doesn't retrieve it

### Root Cause
```python
# Current broken code around line 544:
elif name == "send_direct_message":
    recipient_id = arguments["recipient_id"]
    content = arguments["content"]
    # ... missing sender_id definition ...
    
    # Line 690: Uses undefined sender_id
    await db_manager.register_agent(sender_id, project_id=project_id)
    
    # Line 694: Uses undefined sender_id
    message_id = await db_manager.send_message(
        sender_id=sender_id,  # UNDEFINED!
        ...
    )
```

### Fix Required
```python
# Add after line 546:
sender_id = arguments.get("sender_id", arguments.get("agent_name"))
if not sender_id:
    return [types.TextContent(
        type="text", 
        text="❌ Error: sender_id or agent_name must be provided"
    )]
```

## Issue 2: Foreign Key Constraint Failures

### Problem
- Database has composite foreign keys: `(agent_name, project_id)`
- Messages table requires valid agent+project_id combinations
- Sending to project channel with global agent (or vice versa) fails

### Database Structure
```sql
-- Messages table foreign keys:
FOREIGN KEY (sender_id, sender_project_id) REFERENCES agents(name, project_id)

-- This means:
-- For global message: Need agent with (name, NULL)
-- For project message: Need agent with (name, project_id)
```

### Current Bad Behavior
1. `send_message` in db/manager.py auto-creates agents (line 564-567)
2. This creates duplicate/phantom agents with wrong project_id
3. Leads to "unknown", "main" agents polluting the database

### Fix Required
1. **Remove auto-creation of agents**
2. **Validate agent exists with correct project context**
3. **Return clear error if agent doesn't exist**

## Issue 3: Agent Auto-Creation (Anti-Pattern)

### Problem
- db/manager.py `send_message()` auto-creates agents on line 564-567
- db/manager.py `send_channel_message()` auto-creates agents on line 520-523
- This creates phantom agents ("unknown", "main") 

### Fix Required
Replace auto-creation with validation:

```python
# Instead of auto-creating (REMOVE THIS):
await conn.execute("""
    INSERT OR REPLACE INTO agents (name, description, project_id, last_active, status)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'online')
""", (sender_id, f"Agent: {sender_id}", project_id))

# Replace with validation (ADD THIS):
# Check if agent exists with correct project_id
agent = await self.get_agent(conn, sender_id, project_id)
if not agent:
    raise ValueError(f"Agent '{sender_id}' not found in {'project' if project_id else 'global'} context")
```

## Implementation Order

### Phase 1: Fix send_direct_message (Critical)
1. Add sender_id retrieval from arguments
2. Add validation that sender_id is provided
3. Test direct messaging works

### Phase 2: Remove Agent Auto-Creation (Critical)
1. Remove auto-creation from `send_message()` 
2. Remove auto-creation from `send_channel_message()`
3. Add proper validation instead
4. Return clear errors when agent doesn't exist

### Phase 3: Fix Agent Context Matching (Critical)
1. When sending messages, validate agent exists with correct project_id:
   - Global messages → agent with project_id=NULL
   - Project messages → agent with project_id=current_project
2. Add helper function: `validate_agent_for_scope(agent_name, scope, project_id)`
3. Use this validation before all message operations

### Phase 4: Clean Up Database (Important)
1. Remove phantom agents ("unknown", "main" without proper registration)
2. Ensure all agents have proper descriptions and project associations

## Testing Plan

### Test 1: Direct Messages
```python
# Should work with valid agents
send_direct_message(sender_id="assistant", recipient_id="example-agent", content="test")

# Should fail with clear error for non-existent agent
send_direct_message(sender_id="fake-agent", recipient_id="example-agent", content="test")
# Expected: "❌ Agent 'fake-agent' not found"
```

### Test 2: Channel Messages with Correct Context
```python
# Global channel with global agent - should work
send_channel_message(agent_name="assistant", channel_id="general", scope="global")

# Project channel with project agent - should work  
send_channel_message(agent_name="assistant", channel_id="dev", scope="project")

# Project channel with global-only agent - should fail
# Expected: "❌ Agent 'global-only-agent' not found in project context"
```

### Test 3: No More Phantom Agents
```python
# After fixes, sending with non-existent agent should NOT create it
# Database should stay clean with only registered agents
```

## Files to Modify

1. `/home/gbode/.claude/mcp/claude-slack/server.py`
   - Fix send_direct_message handler (add sender_id)
   - Add agent validation before sending

2. `/home/gbode/.claude/mcp/claude-slack/db/manager.py`
   - Remove auto-creation from send_message()
   - Remove auto-creation from send_channel_message()
   - Add validation methods

3. `/home/gbode/at/claude-slack/template/global/mcp/claude-slack/server.py`
   - Same fixes as above for template

4. `/home/gbode/at/claude-slack/template/global/mcp/claude-slack/db/manager.py`
   - Same fixes as above for template

## Success Criteria

1. ✅ No undefined variable errors
2. ✅ No foreign key constraint failures
3. ✅ No phantom agents created
4. ✅ Clear error messages when agent doesn't exist
5. ✅ Messages only sent from/to valid, registered agents
6. ✅ Proper project isolation maintained

## Notes

- The system should be explicit about agent existence
- Better to fail with clear error than create phantom data
- Agent registration should be intentional (via setup/registration process)
- This will make the system more predictable and maintainable