# Claude-Slack Issues Found During Testing

## Date: 2025-08-21
## Context: Testing agent_id validation system after implementation

## ✅ RESOLVED ISSUES

### 1. ~~FOREIGN KEY Constraint Failures for Channel Messages~~ (FIXED)
**Severity**: High  
**Affected Components**: Channel messaging (both global and project scopes)

**Symptoms**:
- Attempting to send channel messages fails with "FOREIGN KEY constraint failed"
- Occurs for both `assistant` and `example-agent` 
- Affects both global and project-scoped channels

**Test Cases That Failed**:
```python
# Assistant trying to send to global channel
mcp__claude-slack__send_channel_message({
    agent_id: "assistant",
    channel_id: "general", 
    content: "Test message",
    scope: "global"
})
# Error: "Agent 'assistant' not found in global context"

# Assistant trying to send to project channel  
mcp__claude-slack__send_channel_message({
    agent_id: "assistant",
    channel_id: "general",
    content: "Test message", 
    scope: "project"
})
# Error: "FOREIGN KEY constraint failed"

# Example-agent trying to send to channels
# Both global and project channels failed with same FOREIGN KEY error
```

**Root Causes Found**:
1. **Channel ID Format Mismatch**: Project channels were using full UUID but database stored 8-char prefix
2. **Global Channel Access Restriction**: Project agents were incorrectly blocked from posting to global channels  
3. **Missing sender_project_id**: Messages weren't properly tracking sender's project context

**Fix Applied**:
- Updated `get_scoped_channel_id()` to use `project_id[:8]` 
- Modified `send_channel_message()` to accept any registered agent for global channels
- Added `sender_project_id` parameter to properly track message sender
- Fixed message retrieval to use truncated project_id

---

### 2. Empty Agent Listing
**Severity**: Medium  
**Affected Components**: Agent discovery/listing

**Symptoms**:
- `list_agents` tool returns "No agents found for the specified scope"
- Yet validation shows agents DO exist ("assistant" and "example-agent")
- Agents can send direct messages to each other

**Test Cases**:
```python
# Returns empty list
mcp__claude-slack__list_agents({
    scope: "all",
    include_descriptions: true
})
# Result: "No agents found for the specified scope"

# But validation shows agents exist
mcp__claude-slack__get_messages({
    agent_id: "non-existent"
})
# Error message shows: "Available agents: • assistant • example-agent"
```

**Possible Causes**:
- `get_agents_by_scope()` query may be incorrect
- Agent registration may not be setting required fields
- Scope filtering logic may be broken

---

## 🟡 Inconsistencies

### 3. Agent Scope Confusion
**Severity**: Medium  
**Affected Components**: Agent registration and validation

**Observations**:
- Assistant appears to be project-scoped (error: "not found in global context")
- But can receive direct messages from example-agent
- Channels show subscriptions but agents can't send to them

**Evidence**:
- Assistant successfully receives DMs
- Assistant shows subscribed to channels (✓ marks in channel list)
- But cannot send to those same channels

---

## 🟢 What's Working

### Successfully Tested:
1. ✅ Agent ID validation with helpful error messages
2. ✅ Direct messages between agents
3. ✅ Message retrieval with proper agent_id
4. ✅ Channel listing with subscription status
5. ✅ Project context detection
6. ✅ Schema validation for required agent_id parameter

---

## 📋 Recommended Fixes

### Priority 1: Fix Channel Messaging
1. Verify agents are properly registered in the `agents` table
2. Check channel_subscriptions table has proper entries
3. Review FOREIGN KEY constraints in schema
4. Ensure send_channel_message properly validates sender

### Priority 2: Fix Agent Listing  
1. Debug `get_agents_by_scope()` SQL query
2. Verify agent registration sets all required fields
3. Check if project_id relationships are correct

### Priority 3: Clarify Agent Scopes
1. Document whether agents can be both global and project-scoped
2. Fix scope validation logic for cross-scope operations
3. Ensure consistent scope handling across all operations

---

## 🔍 Debug Commands Needed

```sql
-- Check agents table
SELECT * FROM agents;

-- Check channel_subscriptions
SELECT * FROM channel_subscriptions;

-- Check channels
SELECT * FROM channels;

-- Check foreign key relationships
PRAGMA foreign_key_list(messages);
PRAGMA foreign_key_list(channel_subscriptions);
```

---

## 📝 Notes

The agent_id validation system itself is working perfectly. The issues appear to be related to:
1. Database constraints and relationships
2. Agent registration process
3. Scope handling logic

These issues existed before the agent_id changes and are not caused by them.