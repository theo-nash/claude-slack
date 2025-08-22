#!/usr/bin/env python3
"""
Database Manager for Claude-Slack
Handles all database operations with project isolation support
"""

import os
import sys
import sqlite3
import aiosqlite
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from .db_helpers import with_connection, aconnect

# Add parent directory to path to import config_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config_manager import ConfigManager
except ImportError:
    ConfigManager = None

try:
    from log_manager import get_logger
except ImportError:
    # Fallback to standard logging if new logging system not available
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)

class DatabaseManager:
    """Manages SQLite database operations for claude-slack with project isolation"""
    
    def __init__(self, db_path: str):
        """
        Initialize database manager
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.logger = get_logger('DatabaseManager', component='manager')
    
    
    async def initialize(self):
        """Initialize database and ensure schema exists"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Check if database exists
        is_new = not os.path.exists(self.db_path)
        
        if is_new:
            # Create schema using a temporary connection
            async with aconnect(self.db_path, writer=True) as conn:
                # Create schema
                schema_path = os.path.join(
                    os.path.dirname(__file__), 'schema.sql'
                )
                with open(schema_path, 'r') as f:
                    schema = f.read()
                    await conn.executescript(schema)
    
    
    async def close(self):
        """Close database connection (no-op with connection pooling)"""
        pass
    
    
    # Project Management
    
    @with_connection(writer=True)
    async def register_project(self, conn, project_id: str, project_path: str, project_name: str):
        """
        Register a project in the database
        
        Args:
            project_id: Unique project identifier (hash of path)
            project_path: Absolute path to project
            project_name: Human-readable project name
        """
        await conn.execute("""
            INSERT OR REPLACE INTO projects (id, path, name, last_active)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (project_id, project_path, project_name))
    
    @with_connection(writer=False)
    async def get_project(self, conn, project_id: str) -> Optional[Dict]:
        """Get project information"""
        cursor = await conn.execute("""
            SELECT id, path, name, created_at, last_active, metadata
            FROM projects WHERE id = ?
        """, (project_id,))
        
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'path': row[1],
                'name': row[2],
                'created_at': row[3],
                'last_active': row[4],
                'metadata': json.loads(row[5]) if row[5] else {}
            }
        return None
    
    @with_connection(writer=True)
    async def link_projects(self, conn, project_a_id: str, project_b_id: str, 
                           link_type: str = "bidirectional", created_by: str = None) -> bool:
        """
        Create a link between two projects to allow cross-project communication.
        
        Args:
            project_a_id: First project ID
            project_b_id: Second project ID  
            link_type: 'bidirectional', 'a_to_b', or 'b_to_a'
            created_by: Agent or user who created the link
            
        Returns:
            True if link created successfully
        """
        # Ensure consistent ordering
        if project_a_id > project_b_id:
            project_a_id, project_b_id = project_b_id, project_a_id
            # Reverse link type if needed
            if link_type == "a_to_b":
                link_type = "b_to_a"
            elif link_type == "b_to_a":
                link_type = "a_to_b"
        
        try:
            await conn.execute("""
                INSERT OR REPLACE INTO project_links 
                (project_a_id, project_b_id, link_type, created_by, enabled)
                VALUES (?, ?, ?, ?, TRUE)
            """, (project_a_id, project_b_id, link_type, created_by))
            return True
        except Exception:
            return False
    
    @with_connection(writer=True)
    async def unlink_projects(self, conn, project_a_id: str, project_b_id: str) -> bool:
        """Remove link between two projects"""
        # Ensure consistent ordering
        if project_a_id > project_b_id:
            project_a_id, project_b_id = project_b_id, project_a_id
        
        await conn.execute("""
            DELETE FROM project_links 
            WHERE project_a_id = ? AND project_b_id = ?
        """, (project_a_id, project_b_id))
        return True
    
    @with_connection(writer=False)
    async def get_linked_projects(self, conn, project_id: str) -> List[str]:
        """
        Get all projects linked to the given project.
        Checks config file first, then falls back to database.
        
        Returns:
            List of project IDs that this project can communicate with
        """
        # Try to get from config first
        if ConfigManager is not None:
            try:
                config_manager = ConfigManager()
                return config_manager.get_linked_projects(project_id)
            except Exception:
                pass  # Fall back to database
        
        # Fall back to database
        cursor = await conn.execute("""
            SELECT 
                CASE 
                    WHEN project_a_id = ? THEN project_b_id
                    ELSE project_a_id
                END as linked_project_id,
                link_type
            FROM project_links
            WHERE (project_a_id = ? OR project_b_id = ?)
                AND enabled = TRUE
                AND (
                    link_type = 'bidirectional'
                    OR (project_a_id = ? AND link_type = 'a_to_b')
                    OR (project_b_id = ? AND link_type = 'b_to_a')
                )
        """, (project_id, project_id, project_id, project_id, project_id))
        
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
    
    @with_connection(writer=False)
    async def can_projects_communicate(self, conn, project_a_id: str, project_b_id: str) -> bool:
        """
        Check if two projects are allowed to communicate.
        Checks config file first, then falls back to database.
        """
        if project_a_id == project_b_id:
            return True  # Same project can always communicate
        
        # Try to check from config first
        if ConfigManager is not None:
            try:
                config_manager = ConfigManager()
                return config_manager.can_projects_communicate(project_a_id, project_b_id)
            except Exception:
                pass  # Fall back to database
        
        # Fall back to database
        # Ensure consistent ordering
        orig_a, orig_b = project_a_id, project_b_id
        if project_a_id > project_b_id:
            project_a_id, project_b_id = project_b_id, project_a_id
        
        cursor = await conn.execute("""
            SELECT link_type FROM project_links
            WHERE project_a_id = ? AND project_b_id = ? AND enabled = TRUE
        """, (project_a_id, project_b_id))
        
        row = await cursor.fetchone()
        if not row:
            return False
        
        link_type = row[0]
        if link_type == "bidirectional":
            return True
        elif link_type == "a_to_b":
            return orig_a == project_a_id  # Original A can talk to B
        elif link_type == "b_to_a":
            return orig_b == project_a_id  # Original B can talk to A
        
        return False
    
    @with_connection(writer=False)
    async def list_projects(self, conn) -> List[Dict]:
        """List all known projects"""
        cursor = await conn.execute("""
            SELECT id, path, name, created_at, last_active
            FROM projects
            ORDER BY last_active DESC
        """)
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'path': row[1],
                'name': row[2],
                'created_at': row[3],
                'last_active': row[4]
            }
            for row in rows
        ]
    
    # Channel Management
    
    
    @with_connection(writer=True)
    async def create_channel_if_not_exists(
        self, 
        conn,
        channel_id: str,
        name: str,
        description: str,
        scope: str,
        project_id: Optional[str] = None,
        is_default: bool = False
    ):
        """Create a channel if it doesn't exist"""
        try:
            await conn.execute("""
                INSERT INTO channels (id, project_id, scope, name, description, 
                                    created_by, created_by_project_id, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (channel_id, project_id, scope, name, description, 
                  'system', None,  # System-created channels don't have a specific creator
                  is_default))
        except sqlite3.IntegrityError:
            # Channel already exists
            pass
    
    
    @with_connection(writer=False)
    async def get_channel(self, conn, channel_id: str) -> Optional[Dict]:
        """Get channel information"""
        cursor = await conn.execute("""
            SELECT id, project_id, scope, name, description, created_at, is_default, is_archived
            FROM channels WHERE id = ?
        """, (channel_id,))
        
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'project_id': row[1],
                'scope': row[2],
                'name': row[3],
                'description': row[4],
                'created_at': row[5],
                'is_default': row[6],
                'is_archived': row[7]
            }
        return None
    
    @with_connection(writer=False)
    async def list_channels(
        self, 
        conn,
        scope: str = 'all',
        project_id: Optional[str] = None,
        include_archived: bool = False
    ) -> List[Dict]:
        """
        List channels based on scope
        
        Args:
            scope: 'all', 'global', or 'project'
            project_id: Project ID for project scope
            include_archived: Include archived channels
        """
        query = "SELECT id, project_id, scope, name, description, is_default FROM channels WHERE 1=1"
        params = []
        
        if not include_archived:
            query += " AND is_archived = 0"
        
        if scope == 'global':
            query += " AND scope = 'global'"
        elif scope == 'project' and project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        elif scope == 'all' and project_id:
            query += " AND (scope = 'global' OR project_id = ?)"
            params.append(project_id)
        
        query += " ORDER BY scope, name"
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'project_id': row[1],
                'scope': row[2],
                'name': row[3],
                'description': row[4],
                'is_default': row[5]
            }
            for row in rows
        ]
    
    # Agent Management
    
    @with_connection(writer=False)
    async def validate_agent_for_scope(self, conn, agent_name: str, scope: str, project_id: Optional[str] = None) -> bool:
        """Validate that an agent exists with the correct project context for the given scope"""
        if scope == "global":
            # For global scope, agent must exist with project_id=NULL
            agent = await self.get_agent(agent_name, project_id=None)
        else:  # project scope
            # For project scope, agent must exist with matching project_id
            agent = await self.get_agent(agent_name, project_id=project_id)
        
        return agent is not None
    
    @with_connection(writer=True)
    async def register_agent(self, conn, agent_name: str, description: str = "", project_id: Optional[str] = None):
        """Register or update an agent and auto-provision notes channel"""
        # Debug logging
        self.logger.debug(f"register_agent called with: agent_name='{agent_name}', description='{description}', project_id='{project_id}'")
        
        # Register the agent
        final_desc = description or f"Agent: {agent_name}"
        self.logger.debug(f"Using final description: '{final_desc}'")
        
        await conn.execute("""
            INSERT OR REPLACE INTO agents (name, description, project_id, last_active, status)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'online')
        """, (agent_name, final_desc, project_id))
        
        # Auto-provision agent notes channel
        await self._provision_agent_notes_channel(conn, agent_name, project_id)
    
    @with_connection(writer=True)
    async def update_agent_status(self, conn, agent_name: str, status: str, project_id: Optional[str] = None):
        """Update agent status"""
        await conn.execute("""
            UPDATE agents SET status = ?, last_active = CURRENT_TIMESTAMP
            WHERE name = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))
        """, (status, agent_name, project_id, project_id))
    
    @with_connection(writer=False)
    async def agent_exists(self, conn, agent_name: str, project_id: Optional[str] = None) -> bool:
        """Check if an agent exists in the database"""
        cursor = await conn.execute("""
            SELECT COUNT(*) FROM agents 
            WHERE name = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))
        """, (agent_name, project_id, project_id))
        
        row = await cursor.fetchone()
        return row[0] > 0 if row else False
    
    @with_connection(writer=False)
    async def get_agent(self, conn, agent_name: str, project_id: Optional[str] = None) -> Optional[Dict]:
        """Get agent information"""
        cursor = await conn.execute("""
            SELECT name, description, project_id, status, current_project_id, last_active
            FROM agents WHERE name = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))
        """, (agent_name, project_id, project_id))
        
        row = await cursor.fetchone()
        if row:
            return {
                'name': row[0],
                'description': row[1],
                'project_id': row[2],
                'status': row[3],
                'current_project_id': row[4],
                'last_active': row[5]
            }
        return None
    
    @with_connection(writer=False)
    async def get_agents_by_scope(self, conn, project_id: Optional[str] = None, all_projects: bool = False, 
                                  current_project_id: Optional[str] = None) -> List[Dict]:
        """
        Get agents filtered by scope, respecting project link permissions.
        
        Args:
            project_id: If None, get global agents. If specified, get agents for that project.
            all_projects: If True and project_id is None, get agents from linked projects only
            current_project_id: The current project context (for filtering linked projects)
        
        Returns:
            List of agent dictionaries with name, description, project_id
        """
        if project_id:
            # Get agents for specific project
            cursor = await conn.execute("""
                SELECT a.name, a.description, a.project_id, p.name as project_name
                FROM agents a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE a.project_id = ?
                ORDER BY a.name
            """, (project_id,))
        elif all_projects:
            # Get agents from linked projects only (not all projects)
            if current_project_id:
                # Get linked project IDs
                linked_projects = await self.get_linked_projects(current_project_id)
                # Include current project
                linked_projects.append(current_project_id)
                
                if linked_projects:
                    placeholders = ','.join('?' * len(linked_projects))
                    cursor = await conn.execute(f"""
                        SELECT a.name, a.description, a.project_id, p.name as project_name
                        FROM agents a
                        LEFT JOIN projects p ON a.project_id = p.id
                        WHERE a.project_id IN ({placeholders})
                        ORDER BY p.name, a.name
                    """, linked_projects)
                else:
                    # No linked projects, only show current project agents
                    cursor = await conn.execute("""
                        SELECT a.name, a.description, a.project_id, p.name as project_name
                        FROM agents a
                        LEFT JOIN projects p ON a.project_id = p.id
                        WHERE a.project_id = ?
                        ORDER BY a.name
                    """, (current_project_id,))
            else:
                # No current project context, don't show any project agents
                return []
        else:
            # Get global agents only
            cursor = await conn.execute("""
                SELECT name, description, project_id, NULL as project_name
                FROM agents
                WHERE project_id IS NULL
                ORDER BY name
            """)
        
        rows = await cursor.fetchall()
        agents = []
        for row in rows:
            agents.append({
                'name': row[0],
                'description': row[1] or f"Agent: {row[0]}",
                'project_id': row[2],
                'project_name': row[3]
            })
        
        return agents
    
    # Message Operations
    
    @with_connection(writer=True)
    async def send_channel_message(
        self,
        conn,
        channel_id: str,
        sender_id: str,
        content: str,
        sender_project_id: Optional[str] = None,  # Agent's actual project_id
        metadata: Optional[Dict] = None,
        thread_id: Optional[str] = None
    ) -> int:
        """
        Send a message to a channel (creates channel if it doesn't exist)
        
        Returns:
            Message ID
        """
        # Parse channel_id to determine scope and project
        if channel_id.startswith('global:'):
            scope = 'global'
            project_id = None
            channel_name = channel_id.replace('global:', '')
        elif channel_id.startswith('proj_'):
            scope = 'project'
            # Extract project_id from channel_id (e.g., proj_abc123:general)
            parts = channel_id.split(':')
            if len(parts) >= 2:
                project_prefix = parts[0].replace('proj_', '')[:8]
                channel_name = parts[1] if len(parts) > 1 else 'general'
                # Need to look up full project_id from prefix
                cursor = await conn.execute(
                    "SELECT id FROM projects WHERE id LIKE ? LIMIT 1",
                    (f"{project_prefix}%",)
                )
                row = await cursor.fetchone()
                project_id = row[0] if row else None
            else:
                project_id = None
                channel_name = 'general'
        else:
            # Default to global scope
            scope = 'global'
            project_id = None
            channel_name = channel_id
            channel_id = f'global:{channel_id}'
        
        # Ensure channel exists - need to call the method with conn
        try:
            await conn.execute("""
                INSERT INTO channels (id, project_id, scope, name, description, 
                                    created_by, created_by_project_id, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (channel_id, project_id, scope, channel_name, f"Channel: {channel_name}", 
                  'system', None, False))
        except sqlite3.IntegrityError:
            # Channel already exists
            pass
        
        # Send the message - validate sender exists with exact sender_id + sender_project_id combination
        # sender_project_id can be None for global agents
        
        # Verify the agent exists with this exact combination
        agent = await self.get_agent(sender_id, project_id=sender_project_id)
        if not agent:
            if sender_project_id is None:
                raise ValueError(f"Global agent '{sender_id}' not found")
            else:
                raise ValueError(f"Agent '{sender_id}' with project_id '{sender_project_id}' not found")
        
        # For project channels, verify access permissions
        if scope == 'project':
            # Global agents (sender_project_id=None) can post to any project channel
            # Project agents can only post to their own project's channels
            if sender_project_id is not None and sender_project_id != project_id:
                raise ValueError(f"Agent '{sender_id}' from project '{sender_project_id}' cannot post to channels in project '{project_id}'")
        
        metadata_json = json.dumps(metadata) if metadata else None
        
        cursor = await conn.execute("""
            INSERT INTO messages (
                project_id, channel_id, 
                sender_id, sender_project_id,
                recipient_id, recipient_project_id,
                content, scope, thread_id, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id, channel_id, 
            sender_id, sender_project_id,  # Use the actual sender's project_id, not the channel's
            None, None,
            content, scope, thread_id, metadata_json
        ))
        
        return cursor.lastrowid
    
    @with_connection(writer=True)
    async def send_message(
        self,
        conn,
        sender_id: str,
        content: str,
        channel_id: Optional[str] = None,
        recipient_id: Optional[str] = None,
        project_id: Optional[str] = None,
        scope: Optional[str] = None,
        metadata: Optional[Dict] = None,
        thread_id: Optional[str] = None
    ) -> int:
        """
        Send a message to a channel or as a DM
        
        Returns:
            Message ID
        """
        # Validate sender exists with correct project context
        agent = await self.get_agent(sender_id, project_id=project_id)
        if not agent:
            raise ValueError(f"Agent '{sender_id}' not found in {'project ' + project_id if project_id else 'global'} context")
        
        metadata_json = json.dumps(metadata) if metadata else None
        
        cursor = await conn.execute("""
            INSERT INTO messages (
                project_id, channel_id, 
                sender_id, sender_project_id,
                recipient_id, recipient_project_id,
                content, scope, thread_id, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id, channel_id, 
            sender_id, project_id,  # sender's project_id is the current project
            recipient_id, project_id if recipient_id else None,  # recipient's project_id (same project for DMs)
            content, scope, thread_id, metadata_json
        ))
        
        return cursor.lastrowid
    
    @with_connection(writer=False)
    async def get_channel_messages(
        self,
        conn,
        channel_id: str,
        since: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get messages from a channel"""
        query = """
            SELECT m.id, m.sender_id, m.content, m.timestamp, m.thread_id, m.metadata,
                   COALESCE(a.name, m.sender_id) as sender_name
            FROM messages m
            LEFT JOIN agents a ON m.sender_id = a.name AND m.sender_project_id = a.project_id
            WHERE m.channel_id = ?
        """
        params = [channel_id]
        
        if since:
            query += " AND m.timestamp > ?"
            params.append(since)
        else:
            # Default to last 7 days
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            query += " AND m.timestamp > ?"
            params.append(week_ago)
        
        query += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'sender_id': row[1],
                'content': row[2],
                'timestamp': row[3],
                'thread_id': row[4],
                'metadata': json.loads(row[5]) if row[5] else {},
                'sender_name': row[6]
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def get_direct_messages(
        self,
        conn,
        agent_id: str,
        scope: str = 'all',
        project_id: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get direct messages for an agent"""
        query = """
            SELECT m.id, m.sender_id, m.recipient_id, m.content, m.timestamp, 
                   m.scope, m.metadata, COALESCE(a.name, m.sender_id) as sender_name
            FROM messages m
            LEFT JOIN agents a ON m.sender_id = a.name AND m.sender_project_id = a.project_id
            WHERE m.channel_id IS NULL
            AND (m.recipient_id = ? OR m.sender_id = ?)
        """
        params = [agent_id, agent_id]
        
        if scope == 'global':
            query += " AND m.scope = 'global'"
        elif scope == 'project' and project_id:
            query += " AND m.project_id = ?"
            params.append(project_id)
        
        if since:
            query += " AND m.timestamp > ?"
            params.append(since)
        else:
            # Default to last 7 days
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            query += " AND m.timestamp > ?"
            params.append(week_ago)
        
        query += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'sender_id': row[1],
                'recipient_id': row[2],
                'content': row[3],
                'timestamp': row[4],
                'scope': row[5],
                'metadata': json.loads(row[6]) if row[6] else {},
                'sender_name': row[7],
                'is_sent': row[1] == agent_id
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def search_messages(
        self,
        conn,
        query: str,
        agent_id: str,
        scope: str = 'all',
        project_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search messages using full-text search"""
        # This would use the FTS5 virtual table
        # For now, simple LIKE search
        search_query = """
            SELECT m.id, m.channel_id, m.sender_id, m.content, m.timestamp,
                   c.name as channel_name, COALESCE(a.name, m.sender_id) as sender_name
            FROM messages m
            LEFT JOIN channels c ON m.channel_id = c.id
            LEFT JOIN agents a ON m.sender_id = a.name AND m.sender_project_id = a.project_id
            WHERE m.content LIKE ?
        """
        params = [f'%{query}%']
        
        if scope == 'global':
            search_query += " AND m.scope = 'global'"
        elif scope == 'project' and project_id:
            search_query += " AND m.project_id = ?"
            params.append(project_id)
        
        search_query += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = await conn.execute(search_query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'channel_id': row[1],
                'sender_id': row[2],
                'content': row[3],
                'timestamp': row[4],
                'channel_name': row[5],
                'sender_name': row[6]
            }
            for row in rows
        ]
    
    # Read Receipt Management
    
    @with_connection(writer=True)
    async def mark_messages_read(self, conn, agent_id: str, message_ids: List[int]):
        """Mark messages as read"""
        for msg_id in message_ids:
            try:
                await conn.execute("""
                    INSERT INTO read_receipts (agent_id, message_id)
                    VALUES (?, ?)
                """, (agent_id, msg_id))
            except sqlite3.IntegrityError:
                # Already marked as read
                pass
    
    @with_connection(writer=False)
    async def get_unread_count(self, conn, agent_id: str) -> int:
        """Get count of unread messages for an agent"""
        cursor = await conn.execute("""
            SELECT COUNT(*) FROM messages m
            WHERE m.id NOT IN (
                SELECT message_id FROM read_receipts WHERE agent_id = ?
            )
            AND (
                m.recipient_id = ?
                OR m.channel_id IN (
                    -- This would need to check agent's subscriptions
                    SELECT id FROM channels WHERE scope = 'global'
                )
            )
        """, (agent_id, agent_id))
        
        row = await cursor.fetchone()
        return row[0] if row else 0
    
    # Thread Management
    
    @with_connection(writer=False)
    async def get_thread_messages(self, conn, thread_id: str) -> List[Dict]:
        """Get all messages in a thread"""
        cursor = await conn.execute("""
            SELECT m.id, m.sender_id, m.content, m.timestamp, m.metadata,
                   COALESCE(a.name, m.sender_id) as sender_name
            FROM messages m
            LEFT JOIN agents a ON m.sender_id = a.name AND m.sender_project_id = a.project_id
            WHERE m.thread_id = ?
            ORDER BY m.timestamp ASC
        """, (thread_id,))
        
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'sender_id': row[1],
                'content': row[2],
                'timestamp': row[3],
                'metadata': json.loads(row[4]) if row[4] else {},
                'sender_name': row[5]
            }
            for row in rows
        ]
    
    # Additional methods for channel management
    @with_connection(writer=False)
    async def get_channels_by_scope(self, conn, scope: str, project_id: Optional[str] = None) -> List[Dict]:
        """Get all channels for a given scope"""
        if scope == 'global':
            cursor = await conn.execute("""
                SELECT id, name, description, is_default, is_archived, created_at
                FROM channels
                WHERE scope = 'global'
                ORDER BY name
            """)
        elif scope == 'project' and project_id:
            cursor = await conn.execute("""
                SELECT id, name, description, is_default, is_archived, created_at
                FROM channels
                WHERE scope = 'project' AND project_id = ?
                ORDER BY name
            """, (project_id,))
        else:
            return []
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'is_default': row[3],
                'is_archived': row[4],
                'created_at': row[5]
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def channel_exists(self, conn, channel_id: str) -> bool:
        """Check if a channel exists"""
        cursor = await conn.execute(
            "SELECT 1 FROM channels WHERE id = ?",
            (channel_id,)
        )
        row = await cursor.fetchone()
        return row is not None
    
    @with_connection(writer=True)
    async def create_channel(self, conn, channel_id: str, project_id: Optional[str], 
                            scope: str, name: str, description: str,
                            created_by: str, created_by_project_id: Optional[str] = None, 
                            is_default: bool = False) -> bool:
        """Create a new channel"""
        try:
            await conn.execute("""
                INSERT INTO channels (id, project_id, scope, name, description, 
                                    created_by, created_by_project_id, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (channel_id, project_id, scope, name, description, created_by, created_by_project_id, is_default))
            return True
        except Exception as e:
            # Channel might already exist or other error
            return False
    
    @with_connection(writer=True)
    async def add_subscription(self, conn, agent_name: str, channel_id: str, 
                              agent_project_id: Optional[str] = None,
                              source: str = 'manual') -> bool:
        """Add a subscription to the database"""
        try:
            # Ensure channel exists
            cursor = await conn.execute(
                "SELECT 1 FROM channels WHERE id = ?", (channel_id,)
            )
            channel_exists = await cursor.fetchone()
            if not channel_exists:
                return False
            
            # Add subscription
            await conn.execute("""
                INSERT OR REPLACE INTO subscriptions 
                (agent_name, agent_project_id, channel_id, source, subscribed_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (agent_name, agent_project_id, channel_id, source))
            
            return True
        except Exception as e:
            print(f"Error adding subscription: {e}")
            return False
    
    @with_connection(writer=True)
    async def remove_subscription(self, conn, agent_name: str, channel_id: str,
                                  agent_project_id: Optional[str] = None) -> bool:
        """Remove a subscription from the database"""
        try:
            await conn.execute("""
                DELETE FROM subscriptions 
                WHERE agent_name = ? AND agent_project_id IS ? AND channel_id = ?
            """, (agent_name, agent_project_id, channel_id))
            
            return True
        except Exception as e:
            print(f"Error removing subscription: {e}")
            return False
    
    @with_connection(writer=False)
    async def list_all_projects(self, conn) -> List[Dict]:
        """List all registered projects"""
        cursor = await conn.execute("""
            SELECT id, path, name, created_at, last_active, metadata
            FROM projects
            ORDER BY last_active DESC NULLS LAST, name
        """)
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'path': row[1],
                'name': row[2],
                'created_at': row[3],
                'last_active': row[4],
                'metadata': json.loads(row[5]) if row[5] else {}
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def list_all_agents(self, conn) -> List[Dict]:
        """List all registered agents"""
        cursor = await conn.execute("""
            SELECT name, description, status, current_project_id,
                   last_active, created_at, project_id
            FROM agents
            ORDER BY name
        """)
        
        rows = await cursor.fetchall()
        return [
            {
                'name': row[0],
                'description': row[1],
                'status': row[2],
                'current_project_id': row[3],
                'last_active': row[4],
                'created_at': row[5],
                'project_id': row[6]
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def list_all_channels(self, conn) -> List[Dict]:
        """List all channels across all scopes"""
        cursor = await conn.execute("""
            SELECT c.id, c.project_id, c.scope, c.name, c.description,
                   c.created_by, c.created_at, c.is_default, c.is_archived,
                   p.name as project_name
            FROM channels c
            LEFT JOIN projects p ON c.project_id = p.id
            ORDER BY c.scope, c.name
        """)
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'project_id': row[1],
                'scope': row[2],
                'name': row[3],
                'description': row[4],
                'created_by': row[5],
                'created_at': row[6],
                'is_default': row[7],
                'is_archived': row[8],
                'project_name': row[9]
            }
            for row in rows
        ]
    
    # Agent Notes Channel Management
    
    def _get_agent_notes_channel_id(self, agent_name: str, project_id: Optional[str] = None) -> str:
        """Generate the channel ID for an agent's notes channel"""
        if project_id:
            return f"agent-notes:{agent_name}:proj_{project_id[:8]}"
        return f"agent-notes:{agent_name}:global"
    
    async def _provision_agent_notes_channel(self, conn, agent_name: str, project_id: Optional[str] = None):
        """Auto-provision a notes channel for an agent"""
        channel_id = self._get_agent_notes_channel_id(agent_name, project_id)
        channel_name = f"agent-notes-{agent_name}"
        
        # Check if channel already exists
        cursor = await conn.execute("""
            SELECT id FROM channels WHERE id = ?
        """, (channel_id,))
        
        if await cursor.fetchone():
            return  # Channel already exists
        
        # Create the notes channel
        scope = 'project' if project_id else 'global'
        await conn.execute("""
            INSERT INTO channels (
                id, project_id, scope, name, description, 
                created_by, created_by_project_id, channel_type,
                owner_agent_name, owner_agent_project_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            channel_id, project_id, scope, channel_name,
            f"Private notes for {agent_name}",
            agent_name, project_id, 'agent-notes',
            agent_name, project_id
        ))
        
        # Auto-subscribe the agent to their notes channel
        await conn.execute("""
            INSERT OR IGNORE INTO subscriptions (
                agent_name, agent_project_id, channel_id, source
            )
            VALUES (?, ?, ?, 'auto_notes')
        """, (agent_name, project_id, channel_id))
    
    @with_connection(writer=True)
    async def write_note(self, conn, agent_name: str, agent_project_id: Optional[str], 
                         content: str, tags: List[str] = None, session_id: Optional[str] = None,
                         metadata: Optional[Dict] = None):
        """Write a note to an agent's notes channel"""
        channel_id = self._get_agent_notes_channel_id(agent_name, agent_project_id)
        scope = 'project' if agent_project_id else 'global'
        
        # Ensure notes channel exists
        await self._provision_agent_notes_channel(conn, agent_name, agent_project_id)
        
        # Insert the note
        cursor = await conn.execute("""
            INSERT INTO messages (
                channel_id, sender_id, sender_project_id, content, 
                scope, tags, session_id, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (
            channel_id, agent_name, agent_project_id, content,
            scope, json.dumps(tags) if tags else None, session_id,
            json.dumps(metadata) if metadata else None
        ))
        
        row = await cursor.fetchone()
        return row[0] if row else None
    
    @with_connection(writer=False)
    async def search_notes(self, conn, agent_name: str, agent_project_id: Optional[str],
                           query: Optional[str] = None, tags: Optional[List[str]] = None,
                           since: Optional[datetime] = None, limit: int = 50) -> List[Dict]:
        """Search an agent's own notes"""
        channel_id = self._get_agent_notes_channel_id(agent_name, agent_project_id)
        
        # Build query
        sql_parts = ["SELECT id, content, tags, timestamp, session_id, metadata FROM messages WHERE channel_id = ?"]
        params = [channel_id]
        
        if query:
            sql_parts.append("AND content LIKE ?")
            params.append(f"%{query}%")
        
        if tags:
            # Search for any of the provided tags
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            sql_parts.append(f"AND ({' OR '.join(tag_conditions)})")
        
        if since:
            sql_parts.append("AND timestamp >= ?")
            params.append(since.isoformat())
        
        sql_parts.append("ORDER BY timestamp DESC LIMIT ?")
        params.append(limit)
        
        cursor = await conn.execute(" ".join(sql_parts), params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'content': row[1],
                'tags': json.loads(row[2]) if row[2] else [],
                'timestamp': row[3],
                'session_id': row[4],
                'metadata': json.loads(row[5]) if row[5] else {}
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def get_recent_notes(self, conn, agent_name: str, agent_project_id: Optional[str],
                               limit: int = 20, session_id: Optional[str] = None) -> List[Dict]:
        """Get recent notes for an agent"""
        channel_id = self._get_agent_notes_channel_id(agent_name, agent_project_id)
        
        if session_id:
            # Get notes from a specific session
            cursor = await conn.execute("""
                SELECT id, content, tags, timestamp, session_id, metadata
                FROM messages
                WHERE channel_id = ? AND session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (channel_id, session_id, limit))
        else:
            # Get most recent notes
            cursor = await conn.execute("""
                SELECT id, content, tags, timestamp, session_id, metadata
                FROM messages
                WHERE channel_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (channel_id, limit))
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'content': row[1],
                'tags': json.loads(row[2]) if row[2] else [],
                'timestamp': row[3],
                'session_id': row[4],
                'metadata': json.loads(row[5]) if row[5] else {}
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def peek_agent_notes(self, conn, target_agent_name: str, target_project_id: Optional[str],
                               query: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Peek at another agent's notes (for META agents or debugging)"""
        channel_id = self._get_agent_notes_channel_id(target_agent_name, target_project_id)
        
        if query:
            cursor = await conn.execute("""
                SELECT id, content, tags, timestamp, session_id, metadata
                FROM messages
                WHERE channel_id = ? AND content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (channel_id, f"%{query}%", limit))
        else:
            cursor = await conn.execute("""
                SELECT id, content, tags, timestamp, session_id, metadata
                FROM messages
                WHERE channel_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (channel_id, limit))
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'content': row[1],
                'tags': json.loads(row[2]) if row[2] else [],
                'timestamp': row[3],
                'session_id': row[4],
                'metadata': json.loads(row[5]) if row[5] else {},
                'agent': target_agent_name  # Include whose notes these are
            }
            for row in rows
        ]