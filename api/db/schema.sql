-- Claude-Slack v3 Database Schema
-- Unified channel system with permission controls
-- Phase 2 (v3.0.0): Permission System & DM Unification

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Enable WAL mode for better concurrency
PRAGMA journal_mode = WAL;

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Projects table (track all known projects)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,           -- hashed project path (32 chars)
    path TEXT UNIQUE NOT NULL,     -- absolute path to project root
    name TEXT,                     -- human-readable project name
    created_at REAL DEFAULT (strftime('%s', 'now')),
    last_active REAL,
    metadata JSON                  -- project-specific settings
);

-- Agents table (registry with DM policies)
CREATE TABLE IF NOT EXISTS agents (
    name TEXT NOT NULL,            -- agent name from frontmatter
    project_id TEXT,               -- project this agent belongs to (NULL for global)
    description TEXT,
    status TEXT DEFAULT 'offline', -- online/offline/busy
    current_project_id TEXT,       -- currently active project (for context)
    
    -- DM permission settings
    dm_policy TEXT DEFAULT 'open' CHECK (dm_policy IN ('open', 'restricted', 'closed')),
    -- open: anyone can DM, restricted: only allowed list, closed: no DMs
    discoverable TEXT DEFAULT 'public' CHECK (discoverable IN ('public', 'project', 'private')),
    -- public: visible to all, project: visible in linked projects, private: not discoverable
    
    last_active REAL,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    metadata JSON,                 -- Additional agent info
    PRIMARY KEY (name, project_id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (current_project_id) REFERENCES projects(id)
);

-- Unified Channels table (channels AND DMs)
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,           -- Format: {scope}:{name} or dm:{agent1}:{agent2}
    channel_type TEXT NOT NULL CHECK (channel_type IN ('channel', 'direct')),
    access_type TEXT NOT NULL CHECK (access_type IN ('open', 'members', 'private')),
    -- open: anyone can join, members: invite-only, private: fixed membership (DMs)
    
    project_id TEXT,               -- NULL for global channels/DMs
    scope TEXT NOT NULL,           -- 'global' or 'project'
    name TEXT NOT NULL,            -- Channel name or DM identifier
    description TEXT,
    
    -- Pre-allocated Phase 1 fields (v3.1.0)
    topic_required BOOLEAN DEFAULT FALSE,
    default_topic TEXT DEFAULT 'general',
    channel_metadata JSON,
    
    created_by TEXT,               -- Agent name that created the channel
    created_by_project_id TEXT,    -- Agent's project_id
    created_at REAL DEFAULT (strftime('%s', 'now')),
    is_default BOOLEAN DEFAULT FALSE, -- Auto-subscribe new agents
    is_archived BOOLEAN DEFAULT FALSE,
    
    -- For agent notes channels (special case)
    owner_agent_name TEXT,         -- For agent-notes channels
    owner_agent_project_id TEXT,   -- For agent-notes channels
    
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (created_by, created_by_project_id) REFERENCES agents(name, project_id),
    FOREIGN KEY (owner_agent_name, owner_agent_project_id) REFERENCES agents(name, project_id),
    UNIQUE(project_id, name)      -- Ensures unique channel names per scope
);

-- Unified Channel Members table (ALL agent-channel relationships)
-- Replaces both subscriptions and channel_members in the unified model
CREATE TABLE IF NOT EXISTS channel_members (
    channel_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,         -- NULL for global agents
    
    -- How they joined (unified model)
    invited_by TEXT DEFAULT 'self', -- 'self' for self-joined, 'system' for DMs, or inviter's name
    joined_at REAL DEFAULT (strftime('%s', 'now')),
    source TEXT DEFAULT 'manual',   -- 'frontmatter', 'manual', 'default', 'system'
    
    -- Capabilities (not roles!)
    can_leave BOOLEAN DEFAULT TRUE, -- FALSE only for DMs and system channels
    can_send BOOLEAN DEFAULT TRUE,
    can_invite BOOLEAN DEFAULT FALSE,
    can_manage BOOLEAN DEFAULT FALSE,
    
    -- User preferences (unified across all channel types)
    is_muted BOOLEAN DEFAULT FALSE,
    notification_preference TEXT DEFAULT 'all',
    
    -- Read tracking (Phase 1 fields)
    last_read_at REAL,
    last_read_message_id INTEGER,
    
    -- Default provisioning tracking
    is_from_default BOOLEAN DEFAULT FALSE,  -- Was this membership from is_default=true?
    opted_out BOOLEAN DEFAULT FALSE,        -- Has user explicitly opted out?
    opted_out_at REAL,                 -- When did they opt out?
    
    PRIMARY KEY (channel_id, agent_name, agent_project_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id)
);

-- DM Permissions table (allow/block lists for DMs)
CREATE TABLE IF NOT EXISTS dm_permissions (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    other_agent_name TEXT NOT NULL,
    other_agent_project_id TEXT,
    permission TEXT NOT NULL CHECK (permission IN ('allow', 'block')),
    reason TEXT,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (agent_name, agent_project_id, other_agent_name, other_agent_project_id),
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id),
    FOREIGN KEY (other_agent_name, other_agent_project_id) REFERENCES agents(name, project_id)
);

-- Messages table (unified for channels and DMs)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,      -- Always references a channel (including DM channels)
    sender_id TEXT NOT NULL,       -- Agent name
    sender_project_id TEXT,        -- Agent's project_id
    content TEXT NOT NULL,
    
    -- Pre-allocated Phase 1 fields (v3.1.0)
    topic_name TEXT,               -- NULL initially, required in v3.1.0
    ai_metadata JSON,
    confidence REAL,
    model_version TEXT,
    intent_type TEXT,
    
    thread_id TEXT,                -- For threading
    timestamp REAL DEFAULT (strftime('%s', 'now')),  -- Unix timestamp (seconds since epoch)
    is_edited BOOLEAN DEFAULT FALSE,
    edited_at REAL,
    metadata JSON,                 -- priority, references, etc.
    
    FOREIGN KEY (channel_id) REFERENCES channels(id),
    FOREIGN KEY (sender_id, sender_project_id) REFERENCES agents(name, project_id)
);

-- Pre-created for Phase 1 (v3.1.0) - Agent Message State
CREATE TABLE IF NOT EXISTS agent_message_state (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    message_id INTEGER NOT NULL,
    channel_id TEXT,               -- Denormalized for performance
    
    -- Relationship and action types (for v3.1.0)
    relationship_type TEXT DEFAULT 'subscriber',
    action_type TEXT,              -- 'review', 'action', 'fyi' (for mentions)
    status TEXT DEFAULT 'unread',
    
    created_at REAL DEFAULT (strftime('%s', 'now')),
    read_at REAL,
    done_at REAL,
    
    PRIMARY KEY (agent_name, agent_project_id, message_id),
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id)
);

-- Note: Subscriptions table removed in unified membership model
-- All channel access now goes through channel_members table
-- "Subscriptions" are just memberships where invited_by='self'

-- Project Links table (for cross-project communication)
CREATE TABLE IF NOT EXISTS project_links (
    project_a_id TEXT NOT NULL,
    project_b_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'bidirectional', -- 'bidirectional', 'a_to_b', 'b_to_a'
    enabled BOOLEAN DEFAULT TRUE,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    created_by TEXT,
    metadata JSON,
    PRIMARY KEY (project_a_id, project_b_id),
    FOREIGN KEY (project_a_id) REFERENCES projects(id),
    FOREIGN KEY (project_b_id) REFERENCES projects(id),
    CHECK (project_a_id < project_b_id)    -- Ensure consistent ordering
);

-- Sessions table for tracking Claude session contexts
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    project_path TEXT,
    project_name TEXT,
    transcript_path TEXT,
    scope TEXT NOT NULL DEFAULT 'global',
    updated_at REAL DEFAULT (strftime('%s', 'now')),
    metadata JSON,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Tool calls table for deduplication
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_inputs_hash TEXT NOT NULL,
    tool_inputs JSON,
    called_at REAL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Configuration Sync History table (tracks config reconciliation)
CREATE TABLE IF NOT EXISTS config_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_hash TEXT NOT NULL,        -- Hash of the config file for change detection
    config_snapshot JSON NOT NULL,    -- Full snapshot of config at time of sync
    applied_at REAL DEFAULT (strftime('%s', 'now')),
    scope TEXT,                        -- 'global', 'project', or 'all'
    project_id TEXT,                   -- Project ID if project-scoped
    actions_taken JSON,                -- List of actions performed
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- ============================================================================
-- Permission Views (Core of Phase 2)
-- ============================================================================

-- View: Channels accessible to each agent
CREATE VIEW IF NOT EXISTS agent_channels AS
WITH accessible_channels AS (
    SELECT 
        a.name as agent_name,
        a.project_id as agent_project_id,
        c.id as channel_id,
        c.channel_type,
        c.access_type,
        c.scope,
        c.name as channel_name,
        c.description,
        c.project_id as channel_project_id,
        c.is_archived,
        -- Unified model: ALL channel access through channel_members
        EXISTS (
            SELECT 1 FROM channel_members cm
            WHERE cm.channel_id = c.id
            AND cm.agent_name = a.name
            AND cm.agent_project_id IS NOT DISTINCT FROM a.project_id
            AND NOT cm.opted_out  -- Respect opt-outs
        ) as has_access
    FROM agents a
    CROSS JOIN channels c
)
SELECT * FROM accessible_channels WHERE has_access = 1;

-- View: DM access permissions
CREATE VIEW IF NOT EXISTS dm_access AS
SELECT 
    a1.name as agent1_name,
    a1.project_id as agent1_project_id,
    a2.name as agent2_name,
    a2.project_id as agent2_project_id,
    CASE
        -- Check if either agent blocks the other
        WHEN EXISTS (
            SELECT 1 FROM dm_permissions dp
            WHERE (
                (dp.agent_name = a1.name AND dp.agent_project_id IS NOT DISTINCT FROM a1.project_id
                 AND dp.other_agent_name = a2.name AND dp.other_agent_project_id IS NOT DISTINCT FROM a2.project_id
                 AND dp.permission = 'block')
                OR
                (dp.agent_name = a2.name AND dp.agent_project_id IS NOT DISTINCT FROM a2.project_id
                 AND dp.other_agent_name = a1.name AND dp.other_agent_project_id IS NOT DISTINCT FROM a1.project_id
                 AND dp.permission = 'block')
            )
        ) THEN 0
        -- Check DM policies
        WHEN a1.dm_policy = 'closed' OR a2.dm_policy = 'closed' THEN 0
        WHEN a1.dm_policy = 'restricted' AND NOT EXISTS (
            SELECT 1 FROM dm_permissions dp
            WHERE dp.agent_name = a1.name 
            AND dp.agent_project_id IS NOT DISTINCT FROM a1.project_id
            AND dp.other_agent_name = a2.name 
            AND dp.other_agent_project_id IS NOT DISTINCT FROM a2.project_id
            AND dp.permission = 'allow'
        ) THEN 0
        WHEN a2.dm_policy = 'restricted' AND NOT EXISTS (
            SELECT 1 FROM dm_permissions dp
            WHERE dp.agent_name = a2.name 
            AND dp.agent_project_id IS NOT DISTINCT FROM a2.project_id
            AND dp.other_agent_name = a1.name 
            AND dp.other_agent_project_id IS NOT DISTINCT FROM a1.project_id
            AND dp.permission = 'allow'
        ) THEN 0
        ELSE 1
    END as can_dm
FROM agents a1
CROSS JOIN agents a2
WHERE a1.name != a2.name OR a1.project_id != a2.project_id;

-- View: Agent discovery - who can discover whom for DMs
CREATE VIEW IF NOT EXISTS agent_discovery AS
WITH project_relationships AS (
    -- Get all project relationships (bidirectional)
    SELECT project_a_id as project1, project_b_id as project2
    FROM project_links
    WHERE enabled = TRUE
    UNION
    SELECT project_b_id as project1, project_a_id as project2
    FROM project_links
    WHERE enabled = TRUE
)
SELECT 
    a1.name as discovering_agent,
    a1.project_id as discovering_project_id,
    a2.name as discoverable_agent,
    a2.project_id as discoverable_project_id,
    a2.description as discoverable_description,
    a2.status as discoverable_status,
    a2.dm_policy as dm_policy,
    a2.discoverable as discoverable_setting,
    p2.name as discoverable_project_name,
    
    -- Can this agent be discovered?
    CASE
        -- Can't discover yourself
        WHEN a1.name = a2.name AND a1.project_id IS NOT DISTINCT FROM a2.project_id THEN 0
        
        -- Public agents are always discoverable
        WHEN a2.discoverable = 'public' THEN 1
        
        -- Private agents are never discoverable (except already have DM channel)
        WHEN a2.discoverable = 'private' THEN 0
        
        -- Project-scoped agents
        WHEN a2.discoverable = 'project' THEN
            CASE
                -- Same project
                WHEN a1.project_id = a2.project_id AND a1.project_id IS NOT NULL THEN 1
                
                -- Global agent can discover project agents
                WHEN a1.project_id IS NULL THEN 1
                
                -- Linked projects
                WHEN EXISTS (
                    SELECT 1 FROM project_relationships pr
                    WHERE pr.project1 = a1.project_id 
                    AND pr.project2 = a2.project_id
                ) THEN 1
                
                ELSE 0
            END
        
        ELSE 0
    END as can_discover,
    
    -- Can actually DM? (for UI hints)
    CASE
        WHEN a2.dm_policy = 'closed' THEN 'unavailable'
        WHEN a2.dm_policy = 'restricted' THEN 
            CASE 
                WHEN EXISTS (
                    SELECT 1 FROM dm_permissions dp
                    WHERE dp.agent_name = a2.name
                    AND dp.agent_project_id IS NOT DISTINCT FROM a2.project_id
                    AND dp.other_agent_name = a1.name
                    AND dp.other_agent_project_id IS NOT DISTINCT FROM a1.project_id
                    AND dp.permission = 'allow'
                ) THEN 'available'
                ELSE 'requires_permission'
            END
        WHEN a2.dm_policy = 'open' THEN 
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM dm_permissions dp
                    WHERE dp.agent_name = a2.name
                    AND dp.agent_project_id IS NOT DISTINCT FROM a2.project_id
                    AND dp.other_agent_name = a1.name
                    AND dp.other_agent_project_id IS NOT DISTINCT FROM a1.project_id
                    AND dp.permission = 'block'
                ) THEN 'blocked'
                ELSE 'available'
            END
        ELSE 'unknown'
    END as dm_availability,
    
    -- Does a DM channel already exist?
    CASE
        WHEN EXISTS (
            SELECT 1 FROM channels c
            JOIN channel_members cm1 ON c.id = cm1.channel_id
            JOIN channel_members cm2 ON c.id = cm2.channel_id
            WHERE c.channel_type = 'direct'
            AND cm1.agent_name = a1.name 
            AND cm1.agent_project_id IS NOT DISTINCT FROM a1.project_id
            AND cm2.agent_name = a2.name
            AND cm2.agent_project_id IS NOT DISTINCT FROM a2.project_id
        ) THEN 1
        ELSE 0
    END as has_existing_dm

FROM agents a1
CROSS JOIN agents a2
LEFT JOIN projects p2 ON a2.project_id = p2.id;

-- View: Shared channels between projects
CREATE VIEW IF NOT EXISTS shared_channels AS
SELECT DISTINCT
    c.id as channel_id,
    c.name as channel_name,
    c.scope,
    p1.id as project1_id,
    p1.name as project1_name,
    p2.id as project2_id,
    p2.name as project2_name
FROM channels c
JOIN channel_members cm1 ON cm1.channel_id = c.id
JOIN channel_members cm2 ON cm2.channel_id = c.id
LEFT JOIN projects p1 ON cm1.agent_project_id = p1.id
LEFT JOIN projects p2 ON cm2.agent_project_id = p2.id
WHERE cm1.agent_project_id != cm2.agent_project_id
   OR (cm1.agent_project_id IS NULL AND cm2.agent_project_id IS NOT NULL)
   OR (cm1.agent_project_id IS NOT NULL AND cm2.agent_project_id IS NULL);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_channels_type ON channels(channel_type);
CREATE INDEX IF NOT EXISTS idx_channels_access ON channels(access_type);
CREATE INDEX IF NOT EXISTS idx_channels_scope ON channels(scope);
CREATE INDEX IF NOT EXISTS idx_channels_project ON channels(project_id);
CREATE INDEX IF NOT EXISTS idx_channels_dm ON channels(channel_type) WHERE channel_type = 'direct';

CREATE INDEX IF NOT EXISTS idx_channel_members_agent ON channel_members(agent_name, agent_project_id);
CREATE INDEX IF NOT EXISTS idx_channel_members_channel ON channel_members(channel_id);

CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id, sender_project_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);

-- Note: subscription indexes removed - unified model uses channel_members only

CREATE INDEX IF NOT EXISTS idx_dm_permissions_agent ON dm_permissions(agent_name, agent_project_id);
CREATE INDEX IF NOT EXISTS idx_dm_permissions_other ON dm_permissions(other_agent_name, other_agent_project_id);

CREATE INDEX IF NOT EXISTS idx_agent_message_state_agent ON agent_message_state(agent_name, agent_project_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_message_state_message ON agent_message_state(message_id);

CREATE INDEX IF NOT EXISTS idx_project_links_a ON project_links(project_a_id);
CREATE INDEX IF NOT EXISTS idx_project_links_b ON project_links(project_b_id);

CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);

CREATE INDEX IF NOT EXISTS idx_tool_calls_lookup ON tool_calls(tool_name, tool_inputs_hash, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);

-- ============================================================================
-- Full-text Search
-- ============================================================================

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, 
    content=messages, 
    content_rowid=id
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS messages_ai 
AFTER INSERT ON messages 
BEGIN
    INSERT INTO messages_fts(rowid, content) 
    VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad 
AFTER DELETE ON messages 
BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS messages_au 
AFTER UPDATE ON messages 
BEGIN
    UPDATE messages_fts 
    SET content = new.content 
    WHERE rowid = new.id;
END;

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Indexes for unified membership model
CREATE INDEX IF NOT EXISTS idx_channel_members_defaults 
    ON channel_members(is_from_default, opted_out);

CREATE INDEX IF NOT EXISTS idx_channel_members_invited_by
    ON channel_members(invited_by, source);

CREATE INDEX IF NOT EXISTS idx_channels_defaults
    ON channels(is_default, scope, is_archived);

CREATE INDEX IF NOT EXISTS idx_config_sync_history_scope
    ON config_sync_history(scope, project_id, applied_at);

-- ============================================================================
-- Cleanup Triggers
-- ============================================================================

-- Update session timestamp on access
-- This creates infinite loop.  Removing. Handled in application logic.
-- CREATE TRIGGER IF NOT EXISTS update_session_timestamp
-- AFTER UPDATE ON sessions
-- BEGIN
--     UPDATE sessions 
--     SET updated_at = strftime('%s', 'now')
--     WHERE id = NEW.id;
-- END;

-- Cleanup old sessions (older than 24 hours)
CREATE TRIGGER IF NOT EXISTS cleanup_old_sessions
AFTER INSERT ON sessions
BEGIN
    DELETE FROM sessions 
    WHERE updated_at < (strftime('%s', 'now') - 86400);  -- 24 hours = 86400 seconds
END;

-- Cleanup old tool calls (older than 10 minutes)
CREATE TRIGGER IF NOT EXISTS cleanup_old_tool_calls
AFTER INSERT ON tool_calls
BEGIN
    DELETE FROM tool_calls 
    WHERE called_at < (strftime('%s', 'now') - 600);  -- 10 minutes = 600 seconds
END;

-- ============================================================================
-- Helper Functions (as views for SQLite)
-- ============================================================================

-- View: Get DM channel ID for two agents
CREATE VIEW IF NOT EXISTS dm_channel_lookup AS
SELECT 
    CASE 
        WHEN a1.name < a2.name OR (a1.name = a2.name AND a1.project_id < a2.project_id)
        THEN 'dm:' || a1.name || COALESCE(':' || a1.project_id, '') || ':' || a2.name || COALESCE(':' || a2.project_id, '')
        ELSE 'dm:' || a2.name || COALESCE(':' || a2.project_id, '') || ':' || a1.name || COALESCE(':' || a1.project_id, '')
    END as channel_id,
    a1.name as agent1_name,
    a1.project_id as agent1_project_id,
    a2.name as agent2_name,
    a2.project_id as agent2_project_id
FROM agents a1
CROSS JOIN agents a2
WHERE a1.name != a2.name OR a1.project_id != a2.project_id;