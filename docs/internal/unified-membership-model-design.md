# Unified Membership Model Design Document

## Executive Summary

This document outlines a fundamental architectural change to the Claude-Slack v3 system: **eliminating the separate `subscriptions` table and unifying all channel access through a single `channel_members` table**. This change removes artificial complexity, reduces code by ~50%, and provides a cleaner, more maintainable architecture.

**Key Change**: "Subscriptions" become just memberships with `invited_by='self'`.

## Current State (Problem)

The v3 system currently maintains two separate concepts and tables:

1. **Subscriptions** (`subscriptions` table)
   - For "open" channels only
   - Voluntary opt-in/opt-out
   - Lightweight relationship
   - Synced from frontmatter

2. **Memberships** (`channel_members` table)
   - For "members" and "private" channels
   - Invitation-based with roles
   - Heavier relationship with permissions
   - Managed through API calls

This dual-table approach creates:
- **Conceptual confusion**: Two ways to relate agents to channels
- **Code duplication**: Separate managers, methods, and logic paths
- **Missing functionality**: The `get_subscriptions()` method is called but never implemented
- **Maintenance burden**: Two tables to migrate, index, and query
- **Inconsistent features**: Read status, muting only work for some channel types

## Proposed Solution

### Core Insight

**"Subscription" is just membership where you joined yourself.** Both subscriptions and memberships represent the same relationship: an agent's participation in a channel. The only difference is how they joined.

### Unified Model

```sql
-- Single table for ALL agent-channel relationships
CREATE TABLE channel_members (
    -- Identity
    channel_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,         -- Agent's project context
    
    -- How they joined
    invited_by TEXT DEFAULT 'self', -- 'self' or inviter's agent name
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'manual',   -- 'frontmatter', 'manual', 'default', 'system'
    
    -- Capabilities (not roles!)
    can_leave BOOLEAN DEFAULT TRUE, -- FALSE only for DMs
    can_send BOOLEAN DEFAULT TRUE,
    can_invite BOOLEAN DEFAULT FALSE,
    can_manage BOOLEAN DEFAULT FALSE,
    
    -- User preferences
    is_muted BOOLEAN DEFAULT FALSE,
    notification_preference TEXT DEFAULT 'all',
    
    -- Read tracking (future)
    last_read_at TIMESTAMP,
    last_read_message_id INTEGER,
    
    -- Default provisioning
    is_from_default BOOLEAN DEFAULT FALSE,
    opted_out BOOLEAN DEFAULT FALSE,
    opted_out_at TIMESTAMP,
    
    PRIMARY KEY (channel_id, agent_name, agent_project_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id)
);
```

### Access Control Model

Channel access is determined by two factors:

1. **Channel properties** (scope and access_type)
2. **Agent properties** (project membership)

| Channel Type | Scope | Who Can Join | How to Join | Can Leave |
|-------------|-------|--------------|-------------|-----------|
| Open | Global | Anyone | Self-service | Yes |
| Open | Project | Project members only | Self-service | Yes |
| Members | Global | Invited only | Invitation | Yes |
| Members | Project | Invited project members | Invitation | Yes |
| Private/DM | Either | Fixed participants | System | No |

### Simplified API

```python
# OLD: 6+ methods
async def subscribe_to_channel(...)
async def unsubscribe_from_channel(...)
async def add_channel_member(...)
async def remove_channel_member(...)
async def get_subscriptions(...)
async def get_members(...)

# NEW: 3 methods
async def join_channel(agent, channel)      # Self-service (open channels)
async def invite_to_channel(agent, channel, inviter)  # Invitation (members channels)
async def leave_channel(agent, channel)     # Leave any channel (if allowed)
```

## Implementation Impact

### 1. Database Changes

**Delete:**
- `subscriptions` table
- All subscription-related indexes
- Subscription-specific views

**Modify:**
- `channel_members` table: Add `source`, `invited_by`, `is_muted` columns
- `agent_channels` view: Simplify to only check `channel_members`

**Migration:**
```sql
-- One-time migration
INSERT INTO channel_members (
    channel_id, agent_name, agent_project_id,
    invited_by, source, is_muted, joined_at,
    is_from_default, opted_out, opted_out_at
)
SELECT 
    channel_id, agent_name, agent_project_id,
    'self', source, is_muted, subscribed_at,
    is_from_default, opted_out, opted_out_at
FROM subscriptions;

DROP TABLE subscriptions;
```

### 2. Code Changes

**Delete entirely:**
- `/subscriptions/` directory (400+ lines)
- `SubscriptionManager` class
- Legacy subscription methods

**Simplify:**
- `DatabaseManager`: Remove subscription methods, unify under membership
- `ChannelManager`: Consolidate to 3 core methods
- `server.py`: Merge 6 MCP tools into 3

**Fix:**
- Implement missing `get_subscriptions()` as `get_memberships()` 
- Update all callers to use unified API

### 3. Frontmatter Integration

**Current format remains unchanged:**
```yaml
channels:
  global: [general, announcements]
  project: [dev, releases]
```

**But internally:**
- Syncs to `channel_members` with `invited_by='self'`
- No separate subscription logic needed

### 4. MCP Tools

**Deprecate:**
- `subscribe_to_channel`
- `unsubscribe_from_channel`
- `get_my_subscriptions`

**Introduce:**
- `join_channel` - Self-service joining (open channels)
- `leave_channel` - Leave any channel where `can_leave=true`
- `list_my_channels` - Single unified list

**Keep (with modifications):**
- `invite_to_channel` - For members channels
- `send_channel_message` - Works identically

## Benefits

### 1. Conceptual Simplicity
- **One concept**: Membership (not subscription vs membership)
- **One table**: `channel_members`
- **Clear semantics**: How you joined is just metadata

### 2. Code Reduction
- **~50% less code** to maintain
- **No duplicate logic** for subscriptions vs memberships
- **Single code path** for all channel operations

### 3. Feature Parity
- **All channels** get read tracking, muting, notifications
- **Consistent behavior** across all channel types
- **No special cases** in the code

### 4. Performance
- **Single table** to query for all channel access
- **Simpler joins** in SQL views
- **Better cache utilization**

### 5. Maintainability
- **One migration point** for schema changes
- **Unified testing** approach
- **Clear ownership** model

## Migration Strategy

### Phase 1: Add Compatibility Layer (1 day)
1. Add new columns to `channel_members`
2. Create compatibility views/methods
3. Implement missing `get_subscriptions()` method

### Phase 2: Data Migration (1 day)
1. Migrate all subscriptions to channel_members
2. Verify data integrity
3. Update all views

### Phase 3: Code Simplification (2 days)
1. Update DatabaseManager to unified model
2. Simplify ChannelManager
3. Update MCP tools in server.py
4. Remove SubscriptionManager

### Phase 4: Cleanup (1 day)
1. Drop subscriptions table
2. Remove deprecated code
3. Update documentation

## Risks and Mitigations

### Risk 1: Data Loss During Migration
**Mitigation**: 
- Full backup before migration
- Staged rollout with verification
- Reversible migration script

### Risk 2: Breaking Existing Integrations
**Mitigation**:
- Compatibility layer during transition
- Clear deprecation warnings
- Documentation of changes

### Risk 3: Performance Degradation
**Mitigation**:
- Add appropriate indexes
- Benchmark before/after
- Query optimization

## Success Criteria

1. **Zero data loss** during migration
2. **All tests pass** with new model
3. **Performance equal or better** than current
4. **50% code reduction** achieved
5. **No user-visible changes** (same MCP interface behavior)

## Timeline

- **Day 1**: Add compatibility layer, implement missing methods
- **Day 2**: Migrate data, update views
- **Day 3-4**: Refactor code to unified model
- **Day 5**: Cleanup and documentation

## Decision Points

### Why Not Keep Both Tables?

**Separation of concerns** sounds good in theory, but here it's artificial:
- Both represent agent-channel relationships
- Both need similar features (muting, read status)
- The distinction (how they joined) is just metadata

### Why Not Use Roles?

Initially considered `role='subscriber'` vs `role='member'`, but:
- Roles imply hierarchy (subscriber < member < admin)
- These are different entry methods, not permission levels
- Capabilities are more flexible than roles

### Why Break Backward Compatibility?

If we maintained compatibility:
- We'd keep unnecessary complexity
- The migration would be partial
- We couldn't achieve full simplification

Since this is v3 (major version), breaking changes are acceptable for significant improvements.

## Conclusion

The unified membership model eliminates artificial complexity while preserving all semantic distinctions through metadata (`invited_by`, `source`). This change will make the codebase significantly simpler, more maintainable, and more performant.

The key insight is that "subscription" vs "membership" was a false dichotomy. They're both just memberships - the only difference is whether you joined yourself or were invited. By encoding this as a simple field rather than separate tables and concepts, we achieve dramatic simplification without losing any functionality.

## Appendix: Sample Queries

### Get all channels for an agent (unified)
```sql
SELECT c.*, cm.invited_by, cm.can_leave, cm.is_muted
FROM channels c
JOIN channel_members cm ON c.id = cm.channel_id
WHERE cm.agent_name = ? AND cm.agent_project_id = ?
ORDER BY c.scope, c.name;
```

### Get "subscribed" channels (self-joined open channels)
```sql
SELECT c.*
FROM channels c
JOIN channel_members cm ON c.id = cm.channel_id
WHERE cm.agent_name = ?
  AND cm.invited_by = 'self'
  AND c.access_type = 'open';
```

### Check if agent can join a channel
```sql
SELECT CASE
    WHEN c.access_type != 'open' THEN FALSE
    WHEN c.scope = 'global' THEN TRUE
    WHEN c.scope = 'project' AND ? = c.project_id THEN TRUE
    ELSE FALSE
END as can_join
FROM channels c
WHERE c.id = ?;
```