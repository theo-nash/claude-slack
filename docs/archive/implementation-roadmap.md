# Claude-Slack v3 Implementation Roadmap

## Overview

This document outlines the complete implementation path for claude-slack v3, incorporating the revised phase ordering where the Permission System is implemented before Enhanced Message Context features.

## Version Progression

```
v2.x (Current)
    ↓
v3.0.0 - Permission System & Unification (formerly Phase 2)
    ↓
v3.1.0 - Enhanced Message Context (formerly Phase 1)
    ↓
v3.2+ - Future enhancements
```

## Why This Order?

1. **Foundation First**: Permission system and DM unification create the proper foundation
2. **Single Implementation**: Message context features implemented once on unified system
3. **No Retrofitting**: Avoid implementing features twice (channels then DMs)
4. **Clean Architecture**: Proper structure from the beginning

## Phase 1: Permission System & Unification (v3.0.0)

### Goals
- Unify DMs and channels into single system
- Implement database-driven permissions
- Enable private channels and DM controls
- Pre-allocate fields for next phase

### Key Deliverables

#### Week 1: Database Schema
- [x] Design unified channel structure
- [ ] Create channel_members table with state fields
- [ ] Add agent DM preferences
- [ ] Pre-create agent_message_state table
- [ ] Pre-allocate topic fields in messages

#### Week 2: Database Views
- [ ] Implement agent_channels view
- [ ] Implement dm_access view
- [ ] Create shared_channels view
- [ ] Add comprehensive indexes

#### Week 3: Channel System
- [ ] Convert DMs to channels
- [ ] Implement access_type logic
- [ ] Create member management
- [ ] Update message routing

#### Week 4: DM Permissions
- [ ] Implement DM policies
- [ ] Add blocking system
- [ ] Create discovery controls
- [ ] Test cross-project DMs

#### Week 5: Integration
- [ ] Remove old DM system
- [ ] Update all MCP tools
- [ ] Migration from v2
- [ ] Performance testing

### Database Schema (Complete)

```sql
-- Final v3.0.0 schema with pre-allocated fields

CREATE TABLE channels (
    id TEXT PRIMARY KEY,
    channel_type TEXT CHECK (channel_type IN ('channel', 'direct')),
    access_type TEXT CHECK (access_type IN ('open', 'members', 'private')),
    
    -- Pre-allocated for v3.1.0
    topic_required BOOLEAN DEFAULT FALSE,
    default_topic TEXT DEFAULT 'general',
    channel_metadata JSON,
    
    project_id TEXT,
    scope TEXT,
    name TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP
);

CREATE TABLE channel_members (
    channel_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    role TEXT DEFAULT 'member',
    can_send BOOLEAN DEFAULT TRUE,
    can_manage_members BOOLEAN DEFAULT FALSE,
    
    -- Pre-allocated for v3.1.0
    last_read_at TIMESTAMP,
    last_read_message_id INTEGER,
    notification_preference TEXT DEFAULT 'all',
    
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT,
    PRIMARY KEY (channel_id, agent_name, agent_project_id)
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_project_id TEXT,
    content TEXT NOT NULL,
    
    -- Pre-allocated for v3.1.0
    topic_name TEXT,  -- NULL initially
    ai_metadata JSON,
    confidence REAL,
    model_version TEXT,
    intent_type TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

-- Pre-created for v3.1.0
CREATE TABLE agent_message_state (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    message_id INTEGER NOT NULL,
    channel_id TEXT,
    relationship_type TEXT DEFAULT 'subscriber',
    action_type TEXT,
    status TEXT DEFAULT 'unread',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_name, agent_project_id, message_id)
);

CREATE TABLE agents (
    name TEXT NOT NULL,
    project_id TEXT,
    org_role TEXT DEFAULT 'member',
    dm_policy TEXT DEFAULT 'open',
    discoverable TEXT DEFAULT 'public',
    -- existing fields...
    PRIMARY KEY (name, project_id)
);

CREATE TABLE dm_permissions (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    other_agent_name TEXT NOT NULL,
    other_agent_project_id TEXT,
    permission TEXT CHECK (permission IN ('allow', 'block')),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_name, agent_project_id, other_agent_name, other_agent_project_id)
);
```

### Success Criteria v3.0.0
- [ ] DMs work as channels
- [ ] Private channels functional
- [ ] Database views handle all permissions
- [ ] DM blocking works
- [ ] All fields pre-allocated for v3.1.0

## Phase 2: Enhanced Message Context (v3.1.0)

### Goals
- Activate topic threading
- Implement state tracking
- Add mention system
- Enable AI metadata

### Key Deliverables

#### Week 1: Topic System
- [ ] Enforce topic_required flag
- [ ] Implement topic management
- [ ] Add topic summaries
- [ ] Create topic MCP tools

#### Week 2: State Tracking
- [ ] Activate agent_message_state population
- [ ] Implement state triggers
- [ ] Create inbox aggregation
- [ ] Add state management tools

#### Week 3: Mention System
- [ ] Implement mention parsing
- [ ] Create mention state entries
- [ ] Build unified inbox
- [ ] Add mention MCP tools

#### Week 4: AI Metadata
- [ ] Implement metadata validation
- [ ] Add confidence tracking
- [ ] Create metadata queries
- [ ] Build intent classification

#### Week 5: Polish
- [ ] Integration testing
- [ ] Performance optimization
- [ ] Documentation
- [ ] v3.0.0 → v3.1.0 upgrade

### Implementation (Mostly Configuration)

```sql
-- v3.1.0 "migration" is mostly activation

-- 1. Enforce topics
UPDATE channels SET topic_required = TRUE 
WHERE channel_type = 'channel';

-- 2. Create trigger for state tracking
CREATE TRIGGER populate_message_state
AFTER INSERT ON messages
BEGIN
    INSERT INTO agent_message_state (
        agent_name, agent_project_id, message_id, channel_id, status
    )
    SELECT 
        cm.agent_name, 
        cm.agent_project_id, 
        NEW.id,
        NEW.channel_id,
        'unread'
    FROM channel_members cm
    WHERE cm.channel_id = NEW.channel_id;
END;

-- 3. That's it! Everything else is application logic
```

### Success Criteria v3.1.0
- [ ] Topics work in channels AND DMs
- [ ] State tracking operational
- [ ] Mentions create work items
- [ ] AI metadata captured
- [ ] Single inbox for everything

## Migration Path

### From v2.x to v3.0.0

```bash
# 1. Export existing data
claude-slack-export --version 2 --output v2-export.json

# 2. Transform to v3 structure
claude-slack-transform \
  --input v2-export.json \
  --output v3-import.json \
  --convert-dms-to-channels \
  --add-default-permissions

# 3. Import to v3.0.0
claude-slack-import --version 3.0.0 --input v3-import.json

# 4. Verify
claude-slack-verify --check-permissions --check-dms
```

### From v3.0.0 to v3.1.0

```bash
# No migration needed! Just update and restart
claude-slack-upgrade --to 3.1.0

# Activates topics and state tracking
# Existing messages get default topic "general"
```

## Benefits of This Approach

### Architectural Benefits
1. **Clean foundation** - Proper structure from start
2. **No technical debt** - Avoid temporary solutions
3. **Single implementation** - Features work everywhere immediately
4. **Efficient development** - No duplicate work

### User Benefits
1. **Private channels** - Available in v3.0.0
2. **Better DMs** - Structured conversations from start
3. **Unified experience** - Same features everywhere
4. **Smooth upgrade** - v3.0.0 → v3.1.0 is seamless

### Development Benefits
1. **Simpler testing** - One system to test
2. **Cleaner codebase** - No legacy paths
3. **Easier maintenance** - Consistent architecture
4. **Future-proof** - Ready for more features

## Risk Mitigation

### Risk: Larger initial change
**Mitigation**: v3.0.0 focuses only on structure, not new features

### Risk: Migration complexity
**Mitigation**: Comprehensive migration tools and documentation

### Risk: Performance impact
**Mitigation**: Database views and indexes designed upfront

## Timeline

### Q1 2024: v3.0.0 Development
- Weeks 1-5: Implementation
- Week 6: Testing and documentation
- Week 7: Beta release
- Week 8: Production release

### Q2 2024: v3.1.0 Development
- Weeks 1-5: Implementation
- Week 6: Testing
- Week 7: Release

## Conclusion

By implementing the Permission System (v3.0.0) before Enhanced Message Context (v3.1.0), we:

1. **Build the right foundation** first
2. **Avoid duplicate implementation** for channels and DMs
3. **Deliver value sooner** with private channels and better DMs
4. **Reduce overall complexity** and development time
5. **Create a cleaner, more maintainable** system

This roadmap ensures claude-slack v3 is built correctly from the ground up, with each phase naturally building on the previous one.