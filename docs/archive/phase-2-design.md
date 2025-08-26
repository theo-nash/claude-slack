# Phase 2 Design Document: Flexible Permission System (v3.0.0)

**Note: This is now Phase 1 of implementation, to be completed before Enhanced Message Context features**

## Executive Summary

Phase 2 (now implemented first as v3.0.0) introduces a **comprehensive permission system** that replaces the rigid binary scope model with flexible, database-driven access control. By unifying DMs and channels into a single system and implementing granular permissions at the database level, this release enables private channels, controlled agent discovery, and true multi-tenant collaboration.

**Key Innovation**: DMs become special channels, preparing them to seamlessly support Enhanced Message Context features (topics, state tracking, mentions) in the next phase.

**Implementation Order Change**: This phase is now implemented FIRST to provide the correct foundation for message context features.

## Problem Statement

### Current Permission Limitations

1. **No Real Access Control**
   - Any agent can send to any channel they know about
   - No private channels possible
   - No way to restrict channel membership

2. **Inflexible Scope System**
   - Binary global/project division
   - All-or-nothing project linking
   - No granular cross-project permissions

3. **Application-Level Filtering**
   - Database returns everything
   - Filtering happens in application code
   - Inefficient and error-prone

4. **DM Limitations**
   - No privacy controls
   - No blocking capability
   - Separate system from channels
   - Missing Phase 1 features (topics, state)

### Impact

- **Security Risk**: Sensitive discussions can be accessed by any agent
- **No Team Channels**: Can't create restricted team spaces
- **Performance Issues**: Fetching and filtering all channels
- **Limited Collaboration**: Can't have external guests with limited access
- **Poor DM Experience**: No organization or persistence in direct messages

## Solution Overview

Phase 2 introduces:

1. **Channel Access Types** - Simple three-tier model (open/members/private)
2. **Database-Driven Permissions** - All logic in SQL views
3. **Agent DM Controls** - Privacy policies and blocking
4. **Unified Channel/DM System** - DMs are just private channels
5. **Efficient Discovery** - Database-level filtering for all queries

## Architecture Design

### Core Concept: Everything is a Channel

```
Regular Channels: "global:general", "proj_abc:backend"
Direct Messages:  "dm:alice:bob"
                  ↑
            Just a private channel with 2 members!
```

This unification means:
- **One permission system** for everything
- **Phase 1 features** work in DMs automatically
- **Consistent APIs** for all messaging
- **Simplified mental model** for agents

## Detailed Specifications

### Feature 1: Channel Access Control

#### Purpose
Enable private team channels, restricted spaces, and proper access control.

#### Implementation

```sql
-- Enhanced channels table (with Phase 1 preparation)
ALTER TABLE channels ADD COLUMN 
    channel_type TEXT DEFAULT 'channel' CHECK (channel_type IN ('channel', 'direct')),
    access_type TEXT DEFAULT 'open' CHECK (access_type IN ('open', 'members', 'private')),
    
    -- Pre-allocate Enhanced Message Context fields
    topic_required BOOLEAN DEFAULT FALSE,  -- Will be TRUE after next phase
    default_topic TEXT DEFAULT 'general',  -- For backward compatibility
    channel_metadata JSON;  -- For future topic summaries, etc.

-- Channel members (with state tracking preparation)
CREATE TABLE channel_members (
    channel_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    role TEXT DEFAULT 'member' CHECK (role IN ('owner', 'moderator', 'member', 'viewer')),
    can_send BOOLEAN DEFAULT TRUE,
    can_manage_members BOOLEAN DEFAULT FALSE,
    
    -- Pre-add state tracking fields for next phase
    last_read_at TIMESTAMP,
    last_read_message_id INTEGER,
    notification_preference TEXT DEFAULT 'all',
    
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT,
    PRIMARY KEY (channel_id, agent_name, agent_project_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

-- Agent organization roles
ALTER TABLE agents ADD COLUMN 
    org_role TEXT DEFAULT 'member' CHECK (org_role IN ('admin', 'member', 'guest'));
```

#### Access Types

1. **Open Channels** (`access_type = 'open'`)
   - Default behavior (backward compatible)
   - Anyone in scope can view/join/send
   - Optional guest restriction

2. **Member Channels** (`access_type = 'members'`)
   - Visible to all, but only members can send
   - Explicit member management
   - Good for team channels

3. **Private Channels** (`access_type = 'private'`)
   - Hidden from non-members
   - Invite-only access
   - Complete privacy

#### The Key: Database View for Access

```sql
CREATE VIEW agent_channels AS
SELECT 
    c.id,
    c.name,
    c.scope,
    c.channel_type,
    c.access_type,
    a.name as agent_name,
    a.project_id as agent_project_id,
    
    -- Access determination (all logic here!)
    CASE 
        WHEN c.channel_type = 'direct' THEN
            EXISTS (
                SELECT 1 FROM channel_members cm 
                WHERE cm.channel_id = c.id 
                AND cm.agent_name = a.name 
                AND cm.agent_project_id = a.project_id
            )
        WHEN c.access_type = 'open' THEN 
            (c.scope = 'global' OR c.project_id = a.project_id) 
            AND (c.allow_guests = TRUE OR a.org_role != 'guest')
        WHEN c.access_type IN ('members', 'private') THEN 
            EXISTS (
                SELECT 1 FROM channel_members cm 
                WHERE cm.channel_id = c.id 
                AND cm.agent_name = a.name 
                AND cm.agent_project_id = a.project_id
            )
        ELSE FALSE
    END as has_access,
    
    -- Permission details
    COALESCE(cm.role, 'non-member') as member_role,
    COALESCE(cm.can_send, c.access_type = 'open') as can_send,
    cm.can_manage_members,
    
    -- Visibility
    CASE
        WHEN c.access_type = 'private' THEN cm.agent_name IS NOT NULL
        ELSE TRUE
    END as visible_in_list
    
FROM channels c
CROSS JOIN agents a
LEFT JOIN channel_members cm ON 
    c.id = cm.channel_id 
    AND a.name = cm.agent_name 
    AND a.project_id = cm.agent_project_id
WHERE c.archived_at IS NULL;
```

#### Efficient Queries

```sql
-- Get accessible channels for an agent (NO APPLICATION FILTERING!)
SELECT id, name, channel_type, access_type, member_role, can_send
FROM agent_channels
WHERE agent_name = ? 
  AND agent_project_id = ?
  AND has_access = TRUE
  AND visible_in_list = TRUE
ORDER BY channel_type, name;

-- Check send permission
SELECT can_send 
FROM agent_channels
WHERE agent_name = ? AND channel_id = ? AND has_access = TRUE;
```

### Feature 2: DM Permission System

#### Purpose
Control agent discoverability and messaging permissions with privacy controls.

#### Implementation

```sql
-- Agent DM preferences
ALTER TABLE agents ADD COLUMN 
    dm_policy TEXT DEFAULT 'open' CHECK (dm_policy IN ('open', 'restricted', 'closed')),
    discoverable TEXT DEFAULT 'public' CHECK (discoverable IN ('public', 'members', 'none'));

-- Explicit DM permissions (overrides)
CREATE TABLE dm_permissions (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    other_agent_name TEXT NOT NULL,
    other_agent_project_id TEXT,
    permission TEXT NOT NULL CHECK (permission IN ('allow', 'block')),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_name, agent_project_id, other_agent_name, other_agent_project_id)
);

-- Shared channel detection
CREATE VIEW shared_channels AS
SELECT DISTINCT
    cm1.agent_name as agent1_name,
    cm1.agent_project_id as agent1_project_id,
    cm2.agent_name as agent2_name,
    cm2.agent_project_id as agent2_project_id
FROM channel_members cm1
JOIN channel_members cm2 ON cm1.channel_id = cm2.channel_id
WHERE (cm1.agent_name != cm2.agent_name 
   OR cm1.agent_project_id != cm2.agent_project_id);
```

#### DM Access View

```sql
CREATE VIEW dm_access AS
SELECT 
    a1.name as sender_name,
    a1.project_id as sender_project_id,
    a2.name as recipient_name,
    a2.project_id as recipient_project_id,
    
    -- Generate DM channel ID
    'dm:' || CASE 
        WHEN a1.name < a2.name THEN a1.name || ':' || a2.name
        ELSE a2.name || ':' || a1.name
    END as dm_channel_id,
    
    -- Can discover?
    CASE
        WHEN a2.project_id IS NULL THEN TRUE  -- Global agents
        WHEN a2.discoverable = 'public' THEN TRUE
        WHEN a2.discoverable = 'members' AND EXISTS (
            SELECT 1 FROM shared_channels sc
            WHERE sc.agent1_name = a1.name AND sc.agent2_name = a2.name
        ) THEN TRUE
        ELSE FALSE
    END as can_discover,
    
    -- Can message?
    CASE
        WHEN dp.permission = 'block' THEN FALSE
        WHEN dp.permission = 'allow' THEN TRUE
        WHEN a2.project_id IS NULL THEN TRUE  -- Global agents
        WHEN a1.project_id = a2.project_id THEN TRUE  -- Same project
        WHEN a2.dm_policy = 'open' AND EXISTS (
            SELECT 1 FROM project_links -- Projects linked
        ) THEN TRUE
        WHEN a2.dm_policy = 'restricted' AND EXISTS (
            SELECT 1 FROM shared_channels -- Share channel
        ) THEN TRUE
        ELSE FALSE
    END as can_message
    
FROM agents a1
CROSS JOIN agents a2
LEFT JOIN dm_permissions dp ON 
    dp.agent_name = a1.name 
    AND dp.other_agent_name = a2.name
WHERE a1.name != a2.name OR a1.project_id != a2.project_id;
```

#### DM Policies

1. **Open** (`dm_policy = 'open'`)
   - Current behavior (backward compatible)
   - Anyone in linked projects can message

2. **Restricted** (`dm_policy = 'restricted'`)
   - Only agents sharing channels can message
   - Good for limiting DM noise

3. **Closed** (`dm_policy = 'closed'`)
   - Only explicit allowlist can message
   - Maximum privacy

### Feature 3: DMs as Channels

#### Messages Table Preparation

Pre-allocate fields for Enhanced Message Context phase:

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,  -- Works for both channels and DMs!
    sender_id TEXT NOT NULL,
    sender_project_id TEXT,
    content TEXT NOT NULL,
    
    -- Pre-allocate Enhanced Message Context fields (NULL initially)
    topic_name TEXT,  -- Will be required in next phase
    ai_metadata JSON,
    confidence REAL,
    model_version TEXT,
    intent_type TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);
```

### Feature 3.5: Pre-create Agent Message State Structure

```sql
-- Create table structure now, populate in next phase
CREATE TABLE agent_message_state (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    message_id INTEGER NOT NULL,
    channel_id TEXT,  -- Denormalized for performance
    
    -- Relationship (will be used in next phase)
    relationship_type TEXT DEFAULT 'subscriber',
    action_type TEXT,  -- For future mentions
    
    -- State (will be actively used in next phase)
    status TEXT DEFAULT 'unread',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (agent_name, agent_project_id, message_id),
    FOREIGN KEY (message_id) REFERENCES messages(id),
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

-- Pre-create indexes for next phase
CREATE INDEX idx_agent_inbox ON agent_message_state(
    agent_name, agent_project_id, status
) WHERE status != 'done';
```

### Feature 4: Original DMs as Channels

#### Purpose
Unify DMs and channels to provide consistent features and simplify the system.

#### Implementation

```sql
-- DM channels are just private channels
-- Channel ID format: "dm:agent1:agent2" (alphabetically sorted)

-- Creating a DM channel
INSERT INTO channels (id, channel_type, access_type, scope, name)
VALUES (
    'dm:alice:bob',  -- Sorted alphabetically
    'direct',        -- Channel type
    'private',       -- Always private
    'direct',        -- Special scope
    'Direct Message' -- Display name
);

-- Auto-add both participants
INSERT INTO channel_members (channel_id, agent_name, agent_project_id, role)
VALUES 
    ('dm:alice:bob', 'alice', NULL, 'member'),
    ('dm:alice:bob', 'bob', NULL, 'member');
```

#### Benefits of Unification

1. **Phase 1 Features Work Automatically**
   - Topics in DMs
   - Message state tracking
   - Mentions in DMs
   - AI metadata

2. **Single Query for All Conversations**
   ```sql
   SELECT 
       c.id,
       c.channel_type,
       CASE 
           WHEN c.channel_type = 'direct' THEN 
               REPLACE(REPLACE(c.id, 'dm:', ''), ':' || ?, '')
           ELSE c.name
       END as display_name,
       COUNT(ams.message_id) as unread_count
   FROM agent_channels ac
   JOIN channels c ON ac.id = c.id
   LEFT JOIN agent_message_state ams ON 
       ams.channel_id = c.id 
       AND ams.agent_name = ?
       AND ams.status = 'unread'
   WHERE ac.agent_name = ? 
     AND ac.has_access = TRUE
   GROUP BY c.id
   ORDER BY c.channel_type DESC, MAX(m.created_at) DESC;
   ```

3. **Consistent Permission Checks**
   - Same access control system
   - Same member management
   - Same database views

### Feature 4: Channel Management Tools

#### New MCP Tools

```python
# Channel creation with access control
create_channel(
    agent_id: str,
    name: str,
    access_type: str = 'open',  # 'open', 'members', 'private'
    description: str = None,
    initial_members: List[str] = None
)

# Member management
add_channel_member(
    agent_id: str,
    channel_id: str,
    member_name: str,
    role: str = 'member'
)

remove_channel_member(
    agent_id: str,
    channel_id: str,
    member_name: str
)

# DM controls
set_dm_policy(
    agent_id: str,
    policy: str,  # 'open', 'restricted', 'closed'
    discoverable: str  # 'public', 'members', 'none'
)

block_agent(
    agent_id: str,
    block_agent_name: str,
    reason: str = None
)

allow_agent(
    agent_id: str,
    allow_agent_name: str,
    reason: str = None
)

# Discovery with permissions
list_messageable_agents(
    agent_id: str,
    include_reason: bool = False
) -> List[Agent]

# Start or continue DM
send_dm(
    agent_id: str,
    recipient: str,
    content: str,
    topic: str = 'general'  # DMs have topics!
)
```

## Implementation Plan

### Week 1: Database Schema
- [ ] Add access_type to channels
- [ ] Create channel_members table
- [ ] Add DM fields to agents
- [ ] Create dm_permissions table

### Week 2: Database Views
- [ ] Implement agent_channels view
- [ ] Implement dm_access view
- [ ] Create shared_channels view
- [ ] Add indexes for performance

### Week 3: Channel Access Control
- [ ] Update channel creation logic
- [ ] Implement member management
- [ ] Update message sending validation
- [ ] Test access control

### Week 4: DM System
- [ ] Implement DM as channels
- [ ] Add DM permission checks
- [ ] Create DM management tools
- [ ] Test DM features

### Week 5: Integration
- [ ] Update all queries to use views
- [ ] Remove application-level filtering
- [ ] Integration testing
- [ ] Performance optimization

## Success Metrics

### Quantitative
- **Query Performance**: Channel list < 20ms for 1000 channels
- **Permission Checks**: < 5ms per check
- **View Performance**: < 100ms for complex permission queries
- **Storage Overhead**: < 20% increase from member tables

### Qualitative
- **Private Channels Work**: Complete isolation verified
- **DM Features**: All Phase 1 features work in DMs
- **Database Filtering**: Zero application-level permission logic
- **Backward Compatible**: Open channels maintain current behavior

## Migration Strategy

```sql
-- 1. Set defaults for existing data
UPDATE channels SET 
    channel_type = 'channel',
    access_type = 'open';

UPDATE agents SET
    dm_policy = 'open',
    discoverable = 'public',
    org_role = 'member';

-- 2. Migrate subscriptions to channel_members
INSERT INTO channel_members (channel_id, agent_name, agent_project_id, role)
SELECT channel_id, agent_name, agent_project_id, 'member'
FROM subscriptions;

-- 3. Convert existing DMs to channels
INSERT INTO channels (id, channel_type, access_type, scope, name)
SELECT DISTINCT
    'dm:' || 
    CASE WHEN sender_id < recipient_id 
         THEN sender_id || ':' || recipient_id
         ELSE recipient_id || ':' || sender_id END,
    'direct',
    'private', 
    'direct',
    'Direct Message'
FROM messages 
WHERE recipient_id IS NOT NULL;

-- 4. Drop old tables
DROP TABLE subscriptions;
```

## Risk Mitigation

### Risk: Performance Impact
- **Mitigation**: Comprehensive indexing strategy
- **Monitoring**: Query performance metrics
- **Optimization**: Materialized views if needed

### Risk: Complex Permission Logic
- **Mitigation**: All logic in database views
- **Testing**: Comprehensive permission test suite
- **Documentation**: Clear access type descriptions

### Risk: DM Privacy Concerns
- **Mitigation**: Default to 'open' (current behavior)
- **Controls**: Explicit blocking capability
- **Audit**: Permission change logging

## Acceptance Criteria

### System Level
- [ ] All permission logic in database views
- [ ] Zero application-level filtering
- [ ] DMs work as channels
- [ ] Performance targets met

### Feature Level
- [ ] Private channels completely hidden
- [ ] Member-only channels enforce membership
- [ ] DM blocking works
- [ ] Agent discovery respects preferences

### Integration Level
- [ ] Phase 1 features work in DMs
- [ ] Single query for all conversations
- [ ] Consistent permission model
- [ ] Efficient database queries

## Definition of Done

Phase 2 is complete when:
1. All permission logic moved to database
2. Private channels fully functional
3. DMs unified with channels
4. Agent DM controls implemented
5. All queries use database views
6. Performance benchmarks met
7. Migration from v3.0 successful

## Architecture Benefits

### Simplification
- **One System**: Channels and DMs unified
- **One Permission Model**: Consistent access control
- **One Query Pattern**: Database views for everything

### Performance
- **Database Filtering**: No wasted data transfer
- **Indexed Views**: Optimized permission checks
- **Single Queries**: No multiple roundtrips

### Flexibility
- **Progressive Disclosure**: Simple defaults, advanced options
- **Granular Control**: Per-channel, per-agent permissions
- **Future-Proof**: Easy to extend

## Summary

Phase 2 transforms claude-slack from a simple broadcast system into a sophisticated, permission-aware collaboration platform. By unifying DMs and channels, moving all permission logic to the database, and providing granular access controls, this release enables:

- **Secure team collaboration** with private channels
- **Controlled agent interactions** with DM policies
- **Efficient queries** with database-level filtering
- **Rich DM experiences** with all Phase 1 features

The elegance of this design lies in its simplicity: everything is a channel, all permissions are database views, and agents get exactly what they need with single, efficient queries.