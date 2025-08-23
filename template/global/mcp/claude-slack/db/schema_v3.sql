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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
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
    
    last_active TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

-- Channel Members table (explicit membership for members/private channels)
CREATE TABLE IF NOT EXISTS channel_members (
    channel_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,         -- NULL for global agents
    
    -- Permissions within the channel
    role TEXT DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    can_send BOOLEAN DEFAULT TRUE,
    can_manage_members BOOLEAN DEFAULT FALSE,
    
    -- Pre-allocated Phase 1 fields (v3.1.0)
    last_read_at TIMESTAMP,
    last_read_message_id INTEGER,
    notification_preference TEXT DEFAULT 'all',
    
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT,                 -- Agent who added this member
    added_by_project_id TEXT,
    
    PRIMARY KEY (channel_id, agent_name, agent_project_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id),
    FOREIGN KEY (added_by, added_by_project_id) REFERENCES agents(name, project_id)
);

-- DM Permissions table (allow/block lists for DMs)
CREATE TABLE IF NOT EXISTS dm_permissions (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    other_agent_name TEXT NOT NULL,
    other_agent_project_id TEXT,
    permission TEXT NOT NULL CHECK (permission IN ('allow', 'block')),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_edited BOOLEAN DEFAULT FALSE,
    edited_at TIMESTAMP,
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
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    done_at TIMESTAMP,
    
    PRIMARY KEY (agent_name, agent_project_id, message_id),
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id)
);

-- Subscriptions table (for open channels only)
CREATE TABLE IF NOT EXISTS subscriptions (
    agent_name TEXT NOT NULL,
    agent_project_id TEXT,
    channel_id TEXT NOT NULL,
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'frontmatter', -- 'frontmatter', 'manual', 'auto_pattern'
    is_muted BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (agent_name, agent_project_id, channel_id),
    FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

-- Project Links table (for cross-project communication)
CREATE TABLE IF NOT EXISTS project_links (
    project_a_id TEXT NOT NULL,
    project_b_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'bidirectional', -- 'bidirectional', 'a_to_b', 'b_to_a'
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
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
        CASE
            -- Open channels: accessible if subscribed
            WHEN c.access_type = 'open' THEN 
                EXISTS (
                    SELECT 1 FROM subscriptions s 
                    WHERE s.channel_id = c.id 
                    AND s.agent_name = a.name 
                    AND s.agent_project_id IS NOT DISTINCT FROM a.project_id
                )
            -- Members/Private channels: accessible if in channel_members
            WHEN c.access_type IN ('members', 'private') THEN
                EXISTS (
                    SELECT 1 FROM channel_members cm
                    WHERE cm.channel_id = c.id
                    AND cm.agent_name = a.name
                    AND cm.agent_project_id IS NOT DISTINCT FROM a.project_id
                )
            ELSE 0
        END as has_access
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

CREATE INDEX IF NOT EXISTS idx_subscriptions_agent ON subscriptions(agent_name, agent_project_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_channel ON subscriptions(channel_id);

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
-- Cleanup Triggers
-- ============================================================================

-- Update session timestamp on access
CREATE TRIGGER IF NOT EXISTS update_session_timestamp
AFTER UPDATE ON sessions
BEGIN
    UPDATE sessions 
    SET updated_at = datetime('now')
    WHERE id = NEW.id;
END;

-- Cleanup old sessions (older than 24 hours)
CREATE TRIGGER IF NOT EXISTS cleanup_old_sessions
AFTER INSERT ON sessions
BEGIN
    DELETE FROM sessions 
    WHERE updated_at < datetime('now', '-24 hours');
END;

-- Cleanup old tool calls (older than 10 minutes)
CREATE TRIGGER IF NOT EXISTS cleanup_old_tool_calls
AFTER INSERT ON tool_calls
BEGIN
    DELETE FROM tool_calls 
    WHERE called_at < datetime('now', '-10 minutes');
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