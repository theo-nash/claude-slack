-- Claude-Slack Database Schema
-- SQLite database for channel-based messaging system with project isolation

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Enable WAL mode for better concurrency
PRAGMA journal_mode = WAL;

-- Projects table (track all known projects)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,           -- hashed project path (32 chars)
    path TEXT UNIQUE NOT NULL,     -- absolute path to project root
    name TEXT,                     -- human-readable project name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    metadata JSON                  -- project-specific settings
);

-- Agents table (registry, not subscriptions)
CREATE TABLE IF NOT EXISTS agents (
    name TEXT NOT NULL,            -- agent name from frontmatter
    project_id TEXT,               -- project this agent belongs to (NULL for global)
    description TEXT,
    status TEXT DEFAULT 'offline', -- online/offline/busy
    current_project_id TEXT,       -- currently active project (for context)
    last_active TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,                 -- Additional agent info
    PRIMARY KEY (name, project_id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (current_project_id) REFERENCES projects(id)
);

-- Channels table (with project scoping)
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,           -- Format: {scope}:{name} (e.g., "global:general" or "proj_abc123:dev")
    project_id TEXT,               -- NULL for global channels
    scope TEXT NOT NULL,           -- 'global' or 'project'
    name TEXT NOT NULL,            -- Channel name without prefix (e.g., "general", "dev")
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_default BOOLEAN DEFAULT FALSE, -- Auto-subscribe new agents
    is_archived BOOLEAN DEFAULT FALSE,
    metadata JSON,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (created_by) REFERENCES agents(name),
    UNIQUE(project_id, name)      -- Ensures unique channel names per scope
);

-- Messages table (with project scoping)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,               -- NULL for global messages
    channel_id TEXT,               -- NULL for DMs
    sender_id TEXT NOT NULL,
    recipient_id TEXT,             -- For DMs only
    content TEXT NOT NULL,
    scope TEXT,                    -- 'global' or 'project'
    thread_id TEXT,                -- For threading
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_edited BOOLEAN DEFAULT FALSE,
    edited_at TIMESTAMP,
    metadata JSON,                 -- priority, tags, references, etc.
    FOREIGN KEY (channel_id) REFERENCES channels(id),
    FOREIGN KEY (sender_id) REFERENCES agents(name),
    FOREIGN KEY (recipient_id) REFERENCES agents(name),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Read receipts table
CREATE TABLE IF NOT EXISTS read_receipts (
    agent_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, message_id),
    FOREIGN KEY (agent_id) REFERENCES agents(name),
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_scope ON messages(scope, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_channels_project ON channels(project_id);
CREATE INDEX IF NOT EXISTS idx_channels_scope ON channels(scope);
CREATE INDEX IF NOT EXISTS idx_read_receipts_agent ON read_receipts(agent_id);

-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, 
    content=messages, 
    content_rowid=id
);

-- Triggers to keep FTS in sync with messages table
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

-- Thread management view (helpful for querying threads)
CREATE VIEW IF NOT EXISTS thread_summary AS
SELECT 
    thread_id,
    COUNT(*) as message_count,
    MIN(timestamp) as started_at,
    MAX(timestamp) as last_message_at,
    GROUP_CONCAT(DISTINCT sender_id) as participants
FROM messages
WHERE thread_id IS NOT NULL
GROUP BY thread_id;

-- Unread messages view (per agent)
CREATE VIEW IF NOT EXISTS unread_messages AS
SELECT 
    m.*,
    c.name as channel_name
FROM messages m
LEFT JOIN channels c ON m.channel_id = c.id
WHERE m.id NOT IN (
    SELECT message_id FROM read_receipts
);

-- Agent activity view
CREATE VIEW IF NOT EXISTS agent_activity AS
SELECT 
    a.name as agent_name,
    a.project_id,
    a.description,
    a.status,
    COUNT(DISTINCT m.id) as total_messages_sent,
    COUNT(DISTINCT m.channel_id) as channels_used,
    MAX(m.timestamp) as last_message_at
FROM agents a
LEFT JOIN messages m ON a.name = m.sender_id
GROUP BY a.name, a.project_id;

-- Project Links table (for cross-project communication permissions)
CREATE TABLE IF NOT EXISTS project_links (
    project_a_id TEXT NOT NULL,
    project_b_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'bidirectional', -- 'bidirectional', 'a_to_b', 'b_to_a'
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    metadata JSON,                         -- Additional link configuration
    PRIMARY KEY (project_a_id, project_b_id),
    FOREIGN KEY (project_a_id) REFERENCES projects(id),
    FOREIGN KEY (project_b_id) REFERENCES projects(id),
    CHECK (project_a_id < project_b_id)    -- Ensure consistent ordering
);

-- Index for fast project link lookups
CREATE INDEX IF NOT EXISTS idx_project_links_a ON project_links(project_a_id);
CREATE INDEX IF NOT EXISTS idx_project_links_b ON project_links(project_b_id);

-- Sessions table for tracking Claude session contexts
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,              -- session_id from Claude
    project_id TEXT,                  -- References projects.id (NULL for global)
    project_path TEXT,                -- Absolute path to project
    project_name TEXT,                -- Human-readable project name  
    transcript_path TEXT,             -- Path to transcript
    scope TEXT NOT NULL DEFAULT 'global', -- 'global' or 'project'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,                    -- Additional session data if needed
    
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Index for fast session lookups
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

-- Index for project-specific sessions
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);

-- Trigger to update timestamp on session access
CREATE TRIGGER IF NOT EXISTS update_session_timestamp
AFTER UPDATE ON sessions
BEGIN
    UPDATE sessions 
    SET updated_at = datetime('now')
    WHERE id = NEW.id;
END;

-- Automatic cleanup of old sessions (older than 24 hours)
CREATE TRIGGER IF NOT EXISTS cleanup_old_sessions
AFTER INSERT ON sessions
BEGIN
    DELETE FROM sessions 
    WHERE updated_at < datetime('now', '-24 hours');
END;