#!/usr/bin/env python3
"""
Database Manager v3 for Claude-Slack
Handles unified channel system with permission controls
Phase 2 (v3.0.0) Implementation
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
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)

class DatabaseManagerV3:
    """Manages SQLite database operations for claude-slack v3 with unified channels"""
    
    def __init__(self, db_path: str):
        """
        Initialize database manager
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.logger = get_logger('DatabaseManagerV3', component='manager')
    
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
                    os.path.dirname(__file__), 'schema_v3.sql'
                )
                with open(schema_path, 'r') as f:
                    schema = f.read()
                    await conn.executescript(schema)
    
    async def close(self):
        """Close database connection (no-op with connection pooling)"""
        pass
    
    # ============================================================================
    # Project Management
    # ============================================================================
    
    @with_connection(writer=True)
    async def register_project(self, conn, project_id: str, project_path: str, project_name: str):
        """Register a project in the database"""
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
    
    # ============================================================================
    # Agent Management
    # ============================================================================
    
    @with_connection(writer=True)
    async def register_agent(self, conn, name: str, project_id: Optional[str] = None,
                            description: Optional[str] = None,
                            dm_policy: str = 'open',
                            discoverable: str = 'public'):
        """Register an agent with DM policies"""
        await conn.execute("""
            INSERT OR REPLACE INTO agents 
            (name, project_id, description, dm_policy, discoverable, last_active)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (name, project_id, description, dm_policy, discoverable))
    
    @with_connection(writer=False)
    async def get_agent(self, conn, name: str, project_id: Optional[str] = None) -> Optional[Dict]:
        """Get agent information"""
        cursor = await conn.execute("""
            SELECT name, project_id, description, status, dm_policy, discoverable,
                   current_project_id, last_active, created_at, metadata
            FROM agents WHERE name = ? AND project_id IS NOT DISTINCT FROM ?
        """, (name, project_id))
        
        row = await cursor.fetchone()
        if row:
            return {
                'name': row[0],
                'project_id': row[1],
                'description': row[2],
                'status': row[3],
                'dm_policy': row[4],
                'discoverable': row[5],
                'current_project_id': row[6],
                'last_active': row[7],
                'created_at': row[8],
                'metadata': json.loads(row[9]) if row[9] else {}
            }
        return None
    
    # ============================================================================
    # Unified Channel Management
    # ============================================================================
    
    def get_dm_channel_id(self, agent1_name: str, agent1_project_id: Optional[str],
                         agent2_name: str, agent2_project_id: Optional[str]) -> str:
        """Generate consistent DM channel ID"""
        # Sort agents to ensure consistent channel ID regardless of order
        agent1_key = f"{agent1_name}:{agent1_project_id or ''}"
        agent2_key = f"{agent2_name}:{agent2_project_id or ''}"
        
        if agent1_key < agent2_key:
            return f"dm:{agent1_key}:{agent2_key}"
        else:
            return f"dm:{agent2_key}:{agent1_key}"
    
    @with_connection(writer=True)
    async def create_channel(self, conn, 
                           channel_id: str,
                           channel_type: str,
                           access_type: str,
                           scope: str,
                           name: str,
                           project_id: Optional[str] = None,
                           description: Optional[str] = None,
                           created_by: Optional[str] = None,
                           created_by_project_id: Optional[str] = None,
                           is_default: bool = False) -> str:
        """
        Create a new channel (regular or DM)
        
        Args:
            channel_id: Unique channel identifier
            channel_type: 'channel' or 'direct'
            access_type: 'open', 'members', or 'private'
            scope: 'global' or 'project'
            name: Channel name or DM identifier
            project_id: Project ID for project-scoped channels
            description: Channel description
            created_by: Agent who created the channel
            created_by_project_id: Creator's project ID
            is_default: Whether to auto-subscribe new agents
        
        Returns:
            channel_id
        """
        try:
            await conn.execute("""
                INSERT INTO channels 
                (id, channel_type, access_type, scope, name, project_id, 
                 description, created_by, created_by_project_id, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (channel_id, channel_type, access_type, scope, name, project_id,
                  description, created_by, created_by_project_id, is_default))
            
            self.logger.info(f"Created {channel_type} channel: {channel_id} "
                           f"(access_type={access_type}, scope={scope})")
            return channel_id
        except sqlite3.IntegrityError:
            # Channel already exists
            self.logger.debug(f"Channel already exists: {channel_id}")
            return channel_id
    
    @with_connection(writer=True)
    async def create_or_get_dm_channel(self, conn,
                                      agent1_name: str, agent1_project_id: Optional[str],
                                      agent2_name: str, agent2_project_id: Optional[str]) -> str:
        """
        Create or get a DM channel between two agents
        
        Returns:
            channel_id of the DM channel
        """
        # Check if agents can DM each other
        can_dm = await self.check_dm_permission(
            agent1_name, agent1_project_id,
            agent2_name, agent2_project_id
        )
        
        if not can_dm:
            raise ValueError(f"DM not allowed between {agent1_name} and {agent2_name}")
        
        # Generate consistent channel ID
        channel_id = self.get_dm_channel_id(
            agent1_name, agent1_project_id,
            agent2_name, agent2_project_id
        )
        
        # Check if channel exists
        cursor = await conn.execute(
            "SELECT id FROM channels WHERE id = ?", (channel_id,)
        )
        existing = await cursor.fetchone()
        
        if not existing:
            # Determine scope (global if either agent is global)
            scope = 'global' if (agent1_project_id is None or agent2_project_id is None) else 'project'
            
            # Create the DM channel
            await conn.execute("""
                INSERT INTO channels 
                (id, channel_type, access_type, scope, name, created_at)
                VALUES (?, 'direct', 'private', ?, ?, CURRENT_TIMESTAMP)
            """, (channel_id, scope, channel_id))
            
            # Add both agents as members
            await conn.execute("""
                INSERT INTO channel_members 
                (channel_id, agent_name, agent_project_id, role, can_send)
                VALUES (?, ?, ?, 'member', TRUE)
            """, (channel_id, agent1_name, agent1_project_id))
            
            await conn.execute("""
                INSERT INTO channel_members 
                (channel_id, agent_name, agent_project_id, role, can_send)
                VALUES (?, ?, ?, 'member', TRUE)
            """, (channel_id, agent2_name, agent2_project_id))
            
            self.logger.info(f"Created DM channel: {channel_id}")
        
        return channel_id
    
    @with_connection(writer=False)
    async def check_dm_permission(self, conn,
                                 agent1_name: str, agent1_project_id: Optional[str],
                                 agent2_name: str, agent2_project_id: Optional[str]) -> bool:
        """Check if two agents can DM each other based on policies"""
        # Use the dm_access view
        cursor = await conn.execute("""
            SELECT can_dm FROM dm_access
            WHERE agent1_name = ? AND agent1_project_id IS NOT DISTINCT FROM ?
              AND agent2_name = ? AND agent2_project_id IS NOT DISTINCT FROM ?
        """, (agent1_name, agent1_project_id, agent2_name, agent2_project_id))
        
        row = await cursor.fetchone()
        return bool(row[0]) if row else False
    
    @with_connection(writer=True)
    async def add_channel_member(self, conn,
                                channel_id: str,
                                agent_name: str,
                                agent_project_id: Optional[str] = None,
                                role: str = 'member',
                                can_send: bool = True,
                                can_manage_members: bool = False,
                                added_by: Optional[str] = None,
                                added_by_project_id: Optional[str] = None):
        """Add a member to a members/private channel"""
        await conn.execute("""
            INSERT OR REPLACE INTO channel_members 
            (channel_id, agent_name, agent_project_id, role, can_send, can_manage_members,
             added_by, added_by_project_id, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (channel_id, agent_name, agent_project_id, role, can_send, can_manage_members,
              added_by, added_by_project_id))
    
    @with_connection(writer=True)
    async def remove_channel_member(self, conn,
                                   channel_id: str,
                                   agent_name: str,
                                   agent_project_id: Optional[str] = None):
        """Remove a member from a channel"""
        await conn.execute("""
            DELETE FROM channel_members
            WHERE channel_id = ? AND agent_name = ? 
              AND agent_project_id IS NOT DISTINCT FROM ?
        """, (channel_id, agent_name, agent_project_id))
    
    @with_connection(writer=False)
    async def get_channel_members(self, conn, channel_id: str) -> List[Dict]:
        """
        Get all members of a channel.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            List of member dictionaries
        """
        cursor = await conn.execute("""
            SELECT agent_name, agent_project_id, role, can_send, 
                   can_manage_members, joined_at, added_by, added_by_project_id
            FROM channel_members
            WHERE channel_id = ?
            ORDER BY role DESC, joined_at
        """, (channel_id,))
        
        rows = await cursor.fetchall()
        return [
            {
                'agent_name': row[0],
                'agent_project_id': row[1],
                'role': row[2],
                'can_send': bool(row[3]),
                'can_manage_members': bool(row[4]),
                'joined_at': row[5],
                'added_by': row[6],
                'added_by_project_id': row[7]
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def get_channel(self, conn, channel_id: str) -> Optional[Dict]:
        """
        Get channel information by ID.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            Dictionary with channel information or None if not found
        """
        cursor = await conn.execute("""
            SELECT id, channel_type, access_type, scope, name, project_id,
                   description, created_by, created_by_project_id, created_at,
                   is_default, is_archived, topic_required, default_topic,
                   channel_metadata, owner_agent_name, owner_agent_project_id
            FROM channels 
            WHERE id = ?
        """, (channel_id,))
        
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'channel_type': row[1],
                'access_type': row[2],
                'scope': row[3],
                'name': row[4],
                'project_id': row[5],
                'description': row[6],
                'created_by': row[7],
                'created_by_project_id': row[8],
                'created_at': row[9],
                'is_default': row[10],
                'is_archived': row[11],
                'topic_required': row[12],
                'default_topic': row[13],
                'channel_metadata': json.loads(row[14]) if row[14] else None,
                'owner_agent_name': row[15],
                'owner_agent_project_id': row[16]
            }
        return None
    
    @with_connection(writer=False)
    async def get_agent_channels(self, conn,
                                agent_name: str,
                                agent_project_id: Optional[str] = None,
                                include_archived: bool = False) -> List[Dict]:
        """Get all channels accessible to an agent using the permission view"""
        query = """
            SELECT channel_id, channel_type, access_type, scope, 
                   channel_name, description, channel_project_id
            FROM agent_channels
            WHERE agent_name = ? AND agent_project_id IS NOT DISTINCT FROM ?
        """
        
        if not include_archived:
            query += " AND is_archived = FALSE"
        
        cursor = await conn.execute(query, (agent_name, agent_project_id))
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'channel_type': row[1],
                'access_type': row[2],
                'scope': row[3],
                'name': row[4],
                'description': row[5],
                'project_id': row[6]
            }
            for row in rows
        ]
    
    # ============================================================================
    # Message Management
    # ============================================================================
    
    @with_connection(writer=True)
    async def send_message(self, conn,
                         channel_id: str,
                         sender_id: str,
                         sender_project_id: Optional[str],
                         content: str,
                         metadata: Optional[Dict] = None,
                         thread_id: Optional[str] = None) -> int:
        """
        Send a message to a channel (unified for regular channels and DMs)
        
        Returns:
            Message ID
        """
        # Verify sender has access to the channel
        cursor = await conn.execute("""
            SELECT 1 FROM agent_channels
            WHERE channel_id = ? AND agent_name = ? 
              AND agent_project_id IS NOT DISTINCT FROM ?
        """, (channel_id, sender_id, sender_project_id))
        
        if not await cursor.fetchone():
            raise ValueError(f"Agent {sender_id} does not have access to channel {channel_id}")
        
        # Insert the message
        cursor = await conn.execute("""
            INSERT INTO messages 
            (channel_id, sender_id, sender_project_id, content, metadata, thread_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (channel_id, sender_id, sender_project_id, content,
              json.dumps(metadata) if metadata else None, thread_id))
        
        message_id = cursor.lastrowid
        
        self.logger.info(f"Message {message_id} sent to channel {channel_id} by {sender_id}")
        return message_id
    
    @with_connection(writer=False)
    async def get_messages(self, conn,
                         agent_name: str,
                         agent_project_id: Optional[str] = None,
                         channel_id: Optional[str] = None,
                         limit: int = 100,
                         since: Optional[datetime] = None) -> List[Dict]:
        """
        Get messages for an agent (only from accessible channels)
        
        Args:
            agent_name: Agent requesting messages
            agent_project_id: Agent's project ID
            channel_id: Optional specific channel
            limit: Maximum number of messages
            since: Only messages after this timestamp
        
        Returns:
            List of messages
        """
        # Build query using agent_channels view for permission checking
        query = """
            SELECT m.id, m.channel_id, m.sender_id, m.sender_project_id,
                   m.content, m.timestamp, m.thread_id, m.metadata,
                   ac.channel_name, ac.channel_type, ac.scope
            FROM messages m
            INNER JOIN agent_channels ac ON m.channel_id = ac.channel_id
            WHERE ac.agent_name = ? AND ac.agent_project_id IS NOT DISTINCT FROM ?
        """
        params = [agent_name, agent_project_id]
        
        if channel_id:
            query += " AND m.channel_id = ?"
            params.append(channel_id)
        
        if since:
            query += " AND m.timestamp > ?"
            params.append(since.isoformat())
        
        query += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'channel_id': row[1],
                'sender_id': row[2],
                'sender_project_id': row[3],
                'content': row[4],
                'timestamp': row[5],
                'thread_id': row[6],
                'metadata': json.loads(row[7]) if row[7] else {},
                'channel_name': row[8],
                'channel_type': row[9],
                'scope': row[10]
            }
            for row in rows
        ]
    
    # ============================================================================
    # DM Permission Management
    # ============================================================================
    
    @with_connection(writer=True)
    async def set_dm_permission(self, conn,
                               agent_name: str,
                               agent_project_id: Optional[str],
                               other_agent_name: str,
                               other_agent_project_id: Optional[str],
                               permission: str,
                               reason: Optional[str] = None):
        """Set DM permission (allow/block) between two agents"""
        await conn.execute("""
            INSERT OR REPLACE INTO dm_permissions
            (agent_name, agent_project_id, other_agent_name, other_agent_project_id,
             permission, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (agent_name, agent_project_id, other_agent_name, other_agent_project_id,
              permission, reason))
    
    @with_connection(writer=True)
    async def update_dm_policy(self, conn,
                             agent_name: str,
                             agent_project_id: Optional[str],
                             dm_policy: str):
        """Update an agent's DM policy (open/restricted/closed)"""
        await conn.execute("""
            UPDATE agents 
            SET dm_policy = ?
            WHERE name = ? AND project_id IS NOT DISTINCT FROM ?
        """, (dm_policy, agent_name, agent_project_id))
    
    # ============================================================================
    # Subscription Management (for open channels)
    # ============================================================================
    
    @with_connection(writer=True)
    async def subscribe_to_channel(self, conn,
                                  agent_name: str,
                                  agent_project_id: Optional[str],
                                  channel_id: str):
        """Subscribe an agent to an open channel"""
        # Check if channel is open
        cursor = await conn.execute(
            "SELECT access_type FROM channels WHERE id = ?", (channel_id,)
        )
        row = await cursor.fetchone()
        
        if not row:
            raise ValueError(f"Channel {channel_id} not found")
        
        if row[0] != 'open':
            raise ValueError(f"Channel {channel_id} is not open for subscriptions. "
                           f"Use add_channel_member for {row[0]} channels.")
        
        await conn.execute("""
            INSERT OR REPLACE INTO subscriptions
            (agent_name, agent_project_id, channel_id, subscribed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (agent_name, agent_project_id, channel_id))
    
    @with_connection(writer=True)
    async def unsubscribe_from_channel(self, conn,
                                      agent_name: str,
                                      agent_project_id: Optional[str],
                                      channel_id: str):
        """Unsubscribe an agent from a channel"""
        await conn.execute("""
            DELETE FROM subscriptions
            WHERE agent_name = ? AND agent_project_id IS NOT DISTINCT FROM ?
              AND channel_id = ?
        """, (agent_name, agent_project_id, channel_id))
    
    # ============================================================================
    # Search and Query
    # ============================================================================
    
    @with_connection(writer=False)
    async def search_messages(self, conn,
                            agent_name: str,
                            agent_project_id: Optional[str],
                            query: str,
                            limit: int = 50) -> List[Dict]:
        """Search messages in accessible channels using FTS"""
        cursor = await conn.execute("""
            SELECT m.id, m.channel_id, m.sender_id, m.content, m.timestamp,
                   ac.channel_name, ac.channel_type
            FROM messages m
            INNER JOIN messages_fts fts ON m.id = fts.rowid
            INNER JOIN agent_channels ac ON m.channel_id = ac.channel_id
            WHERE fts.content MATCH ?
              AND ac.agent_name = ? 
              AND ac.agent_project_id IS NOT DISTINCT FROM ?
            ORDER BY m.timestamp DESC
            LIMIT ?
        """, (query, agent_name, agent_project_id, limit))
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'channel_id': row[1],
                'sender_id': row[2],
                'content': row[3],
                'timestamp': row[4],
                'channel_name': row[5],
                'channel_type': row[6]
            }
            for row in rows
        ]