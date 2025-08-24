#!/usr/bin/env python3
"""
Database Manager for Claude-Slack
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

class DatabaseManager:
    """Manages SQLite database operations for claude-slack v3 with unified channels"""
    
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
                            discoverable: str = 'public',
                            status: str = 'offline',
                            current_project_id: Optional[str] = None,
                            metadata: Optional[Dict] = None):
        """
        Register an agent with DM policies and initial settings.
        
        Args:
            name: Agent name
            project_id: Project the agent belongs to
            description: Agent description
            dm_policy: DM policy ('open', 'restricted', 'closed')
            discoverable: Discoverability ('public', 'project', 'private')
            status: Initial status ('online', 'offline', 'busy')
            current_project_id: Currently active project
            metadata: Additional agent metadata as dict
        """
        metadata_str = json.dumps(metadata) if metadata else None
        
        await conn.execute("""
            INSERT OR REPLACE INTO agents 
            (name, project_id, description, dm_policy, discoverable, 
             status, current_project_id, metadata, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (name, project_id, description, dm_policy, discoverable,
              status, current_project_id, metadata_str))
    
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
                                invited_by: str = 'self',
                                source: str = 'manual',
                                can_leave: bool = True,
                                can_send: bool = True,
                                can_invite: bool = False,
                                can_manage: bool = False,
                                is_from_default: bool = False):
        """
        Add a member to any channel (unified membership model).
        
        Args:
            channel_id: Channel to add member to
            agent_name: Agent to add
            agent_project_id: Agent's project ID
            invited_by: 'self' for self-joined, 'system' for defaults, or inviter's name
            source: How membership was created ('manual', 'frontmatter', 'default', 'system')
            can_leave: Whether member can leave (false for DMs)
            can_send: Whether member can send messages
            can_invite: Whether member can invite others (true for open channels)
            can_manage: Whether member can manage channel settings
            is_from_default: Whether this was from is_default=true
        """
        await conn.execute("""
            INSERT OR REPLACE INTO channel_members 
            (channel_id, agent_name, agent_project_id, invited_by, source,
             can_leave, can_send, can_invite, can_manage, is_from_default, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (channel_id, agent_name, agent_project_id, invited_by, source,
              can_leave, can_send, can_invite, can_manage, is_from_default))
    
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
            SELECT agent_name, agent_project_id, invited_by, source,
                   can_leave, can_send, can_invite, can_manage, 
                   joined_at, is_from_default, is_muted
            FROM channel_members
            WHERE channel_id = ?
            ORDER BY joined_at
        """, (channel_id,))
        
        rows = await cursor.fetchall()
        return [
            {
                'agent_name': row[0],
                'agent_project_id': row[1],
                'invited_by': row[2],
                'source': row[3],
                'can_leave': bool(row[4]),
                'can_send': bool(row[5]),
                'can_invite': bool(row[6]),
                'can_manage': bool(row[7]),
                'joined_at': row[8],
                'is_from_default': bool(row[9]),
                'is_muted': bool(row[10])
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
    
    @with_connection(writer=True)
    async def remove_dm_permission(self, conn,
                                  agent_name: str,
                                  agent_project_id: Optional[str],
                                  other_agent_name: str,
                                  other_agent_project_id: Optional[str]):
        """Remove a DM permission between two agents"""
        await conn.execute("""
            DELETE FROM dm_permissions
            WHERE agent_name = ? 
              AND agent_project_id IS NOT DISTINCT FROM ?
              AND other_agent_name = ?
              AND other_agent_project_id IS NOT DISTINCT FROM ?
        """, (agent_name, agent_project_id, other_agent_name, other_agent_project_id))
    
    @with_connection(writer=True)
    async def update_agent(self, conn,
                         agent_name: str,
                         agent_project_id: Optional[str],
                         **fields):
        """Update agent fields"""
        allowed_fields = {
            'description', 'status', 'current_project_id',
            'dm_policy', 'discoverable', 'metadata'
        }
        
        update_fields = []
        values = []
        
        for field, value in fields.items():
            if field in allowed_fields:
                if field == 'metadata' and not isinstance(value, str):
                    value = json.dumps(value)
                update_fields.append(f"{field} = ?")
                values.append(value)
        
        if not update_fields:
            return
        
        values.extend([agent_name, agent_project_id])
        
        await conn.execute(f"""
            UPDATE agents
            SET {', '.join(update_fields)},
                last_active = CURRENT_TIMESTAMP
            WHERE name = ? AND project_id IS NOT DISTINCT FROM ?
        """, values)
    
    @with_connection(writer=False)
    async def get_dm_permission_stats(self, conn,
                                     agent_name: str,
                                     agent_project_id: Optional[str]) -> Dict[str, int]:
        """Get DM permission statistics for an agent"""
        cursor = await conn.execute("""
            SELECT 
                SUM(CASE WHEN permission = 'block' THEN 1 ELSE 0 END) as blocked_count,
                SUM(CASE WHEN permission = 'allow' THEN 1 ELSE 0 END) as allowed_count
            FROM dm_permissions
            WHERE agent_name = ?
              AND agent_project_id IS NOT DISTINCT FROM ?
        """, (agent_name, agent_project_id))
        row = await cursor.fetchone()
        blocked_count = row[0] or 0 if row else 0
        allowed_count = row[1] or 0 if row else 0
        
        # Get agents that blocked this agent
        cursor = await conn.execute("""
            SELECT COUNT(*)
            FROM dm_permissions
            WHERE other_agent_name = ?
              AND other_agent_project_id IS NOT DISTINCT FROM ?
              AND permission = 'block'
        """, (agent_name, agent_project_id))
        blocked_by_count = (await cursor.fetchone())[0] or 0
        
        return {
            'agents_blocked': blocked_count,
            'agents_allowed': allowed_count,
            'blocked_by_others': blocked_by_count
        }
    
    # ============================================================================
    # Unified Membership Management (replaces subscription/membership split)
    # ============================================================================
    
    @with_connection(writer=False)
    async def is_channel_member(self, conn,
                               channel_id: str,
                               agent_name: str,
                               agent_project_id: Optional[str] = None) -> bool:
        """Check if an agent is a member of a channel"""
        cursor = await conn.execute("""
            SELECT 1 FROM channel_members
            WHERE channel_id = ? AND agent_name = ?
              AND agent_project_id IS NOT DISTINCT FROM ?
        """, (channel_id, agent_name, agent_project_id))
        return await cursor.fetchone() is not None
    
    @with_connection(writer=False)
    async def get_default_channels(self, conn, 
                                  scope: str = 'all',
                                  project_id: Optional[str] = None) -> List[Dict]:
        """Get all channels marked as is_default=true"""
        query = "SELECT * FROM channels WHERE is_default = 1"
        params = []
        
        if scope == 'global':
            query += " AND scope = 'global'"
        elif scope == 'project' and project_id:
            query += " AND scope = 'project' AND project_id = ?"
            params.append(project_id)
        # scope == 'all' returns everything
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    @with_connection(writer=False)
    async def get_channels_by_scope(self, conn, scope: str = 'all', 
                                   project_id: Optional[str] = None,
                                   is_default: Optional[bool] = None) -> List[Dict]:
        """Get channels filtered by scope and optionally by is_default flag"""
        query = "SELECT * FROM channels WHERE is_archived = 0"
        params = []
        
        if is_default is not None:
            query += " AND is_default = ?"
            params.append(1 if is_default else 0)
        
        if scope == 'global':
            query += " AND scope = 'global'"
        elif scope == 'project' and project_id:
            query += " AND scope = 'project' AND project_id = ?"
            params.append(project_id)
        # scope == 'all' returns everything
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    @with_connection(writer=False)
    async def get_agents_by_scope(self, conn, scope: str = 'all',
                                 project_id: Optional[str] = None) -> List[Dict]:
        """Get agents filtered by scope"""
        if scope == 'global':
            query = "SELECT * FROM agents WHERE project_id IS NULL"
            params = []
        elif scope == 'project' and project_id:
            query = "SELECT * FROM agents WHERE project_id = ?"
            params = [project_id]
        else:  # 'all'
            query = "SELECT * FROM agents"
            params = []
            if project_id:
                query += " WHERE project_id = ? OR project_id IS NULL"
                params = [project_id]
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    @with_connection(writer=True)
    async def track_config_sync(self, conn, config_hash: str, config_snapshot: str,
                               scope: str, project_id: Optional[str],
                               actions_taken: str, success: bool,
                               error_message: Optional[str] = None):
        """Track configuration sync in history table"""
        await conn.execute("""
            INSERT INTO config_sync_history
            (config_hash, config_snapshot, scope, project_id, 
             actions_taken, success, error_message, applied_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (config_hash, config_snapshot, scope, project_id,
              actions_taken, success, error_message))
    
    @with_connection(writer=False)
    async def get_last_sync_hash(self, conn) -> Optional[str]:
        """Get the hash of the last successful sync"""
        cursor = await conn.execute("""
            SELECT config_hash
            FROM config_sync_history
            WHERE success = 1
            ORDER BY applied_at DESC
            LIMIT 1
        """)
        row = await cursor.fetchone()
        return row[0] if row else None
    
    @with_connection(writer=True) 
    async def subscribe_to_channel(self, conn,
                                  agent_name: str,
                                  agent_project_id: Optional[str],
                                  channel_id: str,
                                  source: str = 'manual'):
        """Subscribe to a channel (unified model: self-joined membership)"""
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
        
        # In unified model, subscription is just membership with invited_by='self'
        await self.add_channel_member(
            conn,
            channel_id=channel_id,
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            invited_by='self',
            source=source,
            can_leave=True,
            can_send=True,
            can_invite=True,  # Open channels allow invites
            can_manage=False
        )
    
    @with_connection(writer=True)
    async def unsubscribe_from_channel(self, conn,
                                      agent_name: str,
                                      agent_project_id: Optional[str],
                                      channel_id: str):
        """Unsubscribe from a channel (unified model: remove membership)"""
        await self.remove_channel_member(
            conn,
            channel_id=channel_id,
            agent_name=agent_name,
            agent_project_id=agent_project_id
        )
    
    # ============================================================================
    # Agent Discovery
    # ============================================================================
    
    @with_connection(writer=False)
    async def get_discoverable_agents(self, conn,
                                     agent_name: str,
                                     agent_project_id: Optional[str] = None,
                                     include_unavailable: bool = False) -> List[Dict]:
        """
        Get all agents discoverable by a given agent using the agent_discovery view.
        
        Args:
            agent_name: Agent doing the discovery
            agent_project_id: Agent's project ID
            include_unavailable: Include agents with closed DM policy
            
        Returns:
            List of discoverable agents with their DM availability
        """
        query = """
            SELECT 
                discoverable_agent as name,
                discoverable_project_id as project_id,
                discoverable_project_name as project_name,
                discoverable_description as description,
                discoverable_status as status,
                discoverable_setting,
                dm_policy,
                dm_availability,
                has_existing_dm
            FROM agent_discovery
            WHERE discovering_agent = ?
              AND discovering_project_id IS NOT DISTINCT FROM ?
              AND can_discover = 1
        """
        
        params = [agent_name, agent_project_id]
        
        if not include_unavailable:
            query += " AND dm_availability != 'unavailable'"
        
        query += """
            ORDER BY 
                -- Existing DMs first
                has_existing_dm DESC,
                -- Then by availability
                CASE dm_availability
                    WHEN 'available' THEN 1
                    WHEN 'requires_permission' THEN 2
                    WHEN 'blocked' THEN 3
                    WHEN 'unavailable' THEN 4
                END,
                -- Then by name
                name
        """
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'name': row[0],
                'project_id': row[1],
                'project_name': row[2],
                'description': row[3],
                'status': row[4],
                'discoverable': row[5],
                'dm_policy': row[6],
                'dm_availability': row[7],
                'has_existing_dm': bool(row[8]),
                'can_dm': row[7] in ['available', 'requires_permission']
            }
            for row in rows
        ]
    
    @with_connection(writer=False)
    async def check_can_discover_agent(self, conn,
                                      discovering_agent: str,
                                      discovering_project_id: Optional[str],
                                      target_agent: str,
                                      target_project_id: Optional[str]) -> bool:
        """
        Check if one agent can discover another using the agent_discovery view.
        
        Args:
            discovering_agent: Agent trying to discover
            discovering_project_id: Discovering agent's project
            target_agent: Agent to be discovered
            target_project_id: Target agent's project
            
        Returns:
            True if target agent is discoverable by discovering agent
        """
        cursor = await conn.execute("""
            SELECT can_discover
            FROM agent_discovery
            WHERE discovering_agent = ?
              AND discovering_project_id IS NOT DISTINCT FROM ?
              AND discoverable_agent = ?
              AND discoverable_project_id IS NOT DISTINCT FROM ?
        """, (discovering_agent, discovering_project_id, 
              target_agent, target_project_id))
        
        row = await cursor.fetchone()
        return bool(row[0]) if row else False
    
    # ============================================================================
    # Mention Validation
    # ============================================================================
    
    @with_connection(writer=False)
    async def check_agent_can_access_channel(self, conn,
                                            agent_name: str,
                                            agent_project_id: Optional[str],
                                            channel_id: str) -> bool:
        """
        Check if an agent can access a specific channel.
        Used for @mention validation - ensures mentioned agent can see the message.
        
        Simply checks if the agent appears in agent_channels view for this channel.
        """
        cursor = await conn.execute("""
            SELECT 1
            FROM agent_channels
            WHERE agent_name = ?
            AND agent_project_id IS NOT DISTINCT FROM ?
            AND channel_id = ?
        """, (agent_name, agent_project_id, channel_id))
        
        result = await cursor.fetchone()
        return result is not None
    
    @with_connection(writer=False)
    async def validate_mentions_batch(self, conn,
                                     channel_id: str,
                                     mentions: List[Dict[str, Optional[str]]]) -> Dict[str, List]:
        """
        Validate multiple @mentions for a channel.
        
        Args:
            channel_id: The channel where the message will be posted
            mentions: List of dicts with 'name' and 'project_id' keys
        
        Returns:
            Dict with:
            - 'valid': List of agents who can access the channel
            - 'invalid': List of agents who cannot access the channel  
            - 'unknown': List of agents who don't exist
        """
        if not mentions:
            return {'valid': [], 'invalid': [], 'unknown': []}
        
        result = {'valid': [], 'invalid': [], 'unknown': []}
        
        # Check each mention
        for mention in mentions:
            agent_name = mention.get('name')
            agent_project_id = mention.get('project_id')
            
            # Check if agent exists
            cursor = await conn.execute("""
                SELECT 1 FROM agents
                WHERE name = ? AND project_id IS NOT DISTINCT FROM ?
            """, (agent_name, agent_project_id))
            
            exists = await cursor.fetchone()
            if not exists:
                result['unknown'].append(mention)
                continue
            
            # Check if agent can access the channel
            cursor = await conn.execute("""
                SELECT 1 FROM agent_channels
                WHERE agent_name = ?
                AND agent_project_id IS NOT DISTINCT FROM ?
                AND channel_id = ?
            """, (agent_name, agent_project_id, channel_id))
            
            can_access = await cursor.fetchone()
            if can_access:
                result['valid'].append(mention)
            else:
                result['invalid'].append(mention)
        
        return result
    
    # ============================================================================
    # Session Management
    # ============================================================================
    
    @with_connection(writer=True)
    async def register_session(self, conn,
                              session_id: str,
                              project_id: Optional[str] = None,
                              project_path: Optional[str] = None,
                              project_name: Optional[str] = None,
                              transcript_path: Optional[str] = None,
                              scope: str = 'global',
                              metadata: Optional[Dict] = None) -> str:
        """
        Register or update a Claude session.
        
        Args:
            session_id: Unique session identifier
            project_id: Associated project ID
            project_path: Path to project (if applicable)
            project_name: Human-readable project name
            transcript_path: Path to transcript file
            scope: 'global' or 'project'
            metadata: Additional session metadata
        
        Returns:
            session_id
        """
        metadata_str = json.dumps(metadata) if metadata else None
        
        await conn.execute("""
            INSERT OR REPLACE INTO sessions 
            (id, project_id, project_path, project_name, transcript_path, 
             scope, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (session_id, project_id, project_path, project_name, 
              transcript_path, scope, metadata_str))
        
        self.logger.info(f"Registered session: {session_id} (scope={scope})")
        return session_id
    
    @with_connection(writer=True)
    async def update_session(self, conn,
                           session_id: str,
                           **fields) -> bool:
        """
        Update session fields.
        
        Args:
            session_id: Session ID to update
            **fields: Fields to update (project_id, project_path, project_name,
                     transcript_path, scope, metadata)
        
        Returns:
            True if updated, False if session not found
        """
        allowed_fields = {
            'project_id', 'project_path', 'project_name',
            'transcript_path', 'scope', 'metadata'
        }
        
        update_fields = []
        values = []
        
        for field, value in fields.items():
            if field in allowed_fields:
                if field == 'metadata' and not isinstance(value, str):
                    value = json.dumps(value)
                update_fields.append(f"{field} = ?")
                values.append(value)
        
        if not update_fields:
            return False
        
        # Add session_id for WHERE clause
        values.append(session_id)
        
        result = await conn.execute(f"""
            UPDATE sessions
            SET {', '.join(update_fields)},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, values)
        
        return result.rowcount > 0
    
    @with_connection(writer=False)
    async def get_session(self, conn, session_id: str) -> Optional[Dict]:
        """
        Get session information.
        
        Args:
            session_id: Session ID
        
        Returns:
            Session dictionary or None if not found
        """
        cursor = await conn.execute("""
            SELECT id, project_id, project_path, project_name, 
                   transcript_path, scope, updated_at, metadata
            FROM sessions
            WHERE id = ?
        """, (session_id,))
        
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'project_id': row[1],
                'project_path': row[2],
                'project_name': row[3],
                'transcript_path': row[4],
                'scope': row[5],
                'updated_at': row[6],
                'metadata': json.loads(row[7]) if row[7] else {}
            }
        return None
    
    @with_connection(writer=False)
    async def get_active_sessions(self, conn,
                                 project_id: Optional[str] = None,
                                 hours: int = 24) -> List[Dict]:
        """
        Get recently active sessions.
        
        Args:
            project_id: Optional filter by project
            hours: Number of hours to look back (default 24)
        
        Returns:
            List of active session dictionaries
        """
        query = """
            SELECT id, project_id, project_path, project_name,
                   transcript_path, scope, updated_at, metadata
            FROM sessions
            WHERE updated_at > datetime('now', ? || ' hours')
        """
        params = [-hours]
        
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)
        
        query += " ORDER BY updated_at DESC"
        
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        
        return [
            {
                'id': row[0],
                'project_id': row[1],
                'project_path': row[2],
                'project_name': row[3],
                'transcript_path': row[4],
                'scope': row[5],
                'updated_at': row[6],
                'metadata': json.loads(row[7]) if row[7] else {}
            }
            for row in rows
        ]
    
    @with_connection(writer=True)
    async def cleanup_old_sessions(self, conn, hours: int = 24) -> int:
        """
        Clean up sessions older than specified hours.
        
        Args:
            hours: Number of hours after which to clean up sessions
        
        Returns:
            Number of sessions deleted
        """
        result = await conn.execute("""
            DELETE FROM sessions
            WHERE updated_at < datetime('now', ? || ' hours')
        """, (-hours,))
        
        deleted_count = result.rowcount
        if deleted_count > 0:
            self.logger.info(f"Cleaned up {deleted_count} old sessions")
        
        return deleted_count
    
    # ============================================================================
    # Tool Call Deduplication
    # ============================================================================
    
    @with_connection(writer=True)
    async def record_tool_call(self, conn,
                              session_id: str,
                              tool_name: str,
                              tool_inputs: Dict,
                              dedup_window_minutes: int = 10) -> bool:
        """
        Record a tool call for deduplication.
        
        Args:
            session_id: Session ID
            tool_name: Name of the tool called
            tool_inputs: Tool input parameters
            dedup_window_minutes: Minutes to look back for duplicates
        
        Returns:
            True if this is a new tool call, False if duplicate detected
        """
        # Generate hash of tool inputs for comparison
        inputs_str = json.dumps(tool_inputs, sort_keys=True)
        inputs_hash = hashlib.sha256(inputs_str.encode()).hexdigest()
        
        # Check for recent duplicate
        cursor = await conn.execute("""
            SELECT id FROM tool_calls
            WHERE session_id = ?
              AND tool_name = ?
              AND tool_inputs_hash = ?
              AND called_at > datetime('now', ? || ' minutes')
        """, (session_id, tool_name, inputs_hash, -dedup_window_minutes))
        
        if await cursor.fetchone():
            self.logger.debug(f"Duplicate tool call detected: {tool_name} in session {session_id}")
            return False
        
        # Record new tool call
        await conn.execute("""
            INSERT INTO tool_calls 
            (session_id, tool_name, tool_inputs_hash, tool_inputs, called_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (session_id, tool_name, inputs_hash, inputs_str))
        
        return True
    
    @with_connection(writer=False)
    async def get_recent_tool_calls(self, conn,
                                   session_id: str,
                                   minutes: int = 10) -> List[Dict]:
        """
        Get recent tool calls for a session.
        
        Args:
            session_id: Session ID
            minutes: Number of minutes to look back
        
        Returns:
            List of recent tool calls
        """
        cursor = await conn.execute("""
            SELECT id, tool_name, tool_inputs, called_at
            FROM tool_calls
            WHERE session_id = ?
              AND called_at > datetime('now', ? || ' minutes')
            ORDER BY called_at DESC
        """, (session_id, -minutes))
        
        rows = await cursor.fetchall()
        return [
            {
                'id': row[0],
                'tool_name': row[1],
                'tool_inputs': json.loads(row[2]),
                'called_at': row[3]
            }
            for row in rows
        ]
    
    @with_connection(writer=True)
    async def cleanup_old_tool_calls(self, conn, minutes: int = 10) -> int:
        """
        Clean up tool calls older than specified minutes.
        
        Args:
            minutes: Number of minutes after which to clean up tool calls
        
        Returns:
            Number of tool calls deleted
        """
        result = await conn.execute("""
            DELETE FROM tool_calls
            WHERE called_at < datetime('now', ? || ' minutes')
        """, (-minutes,))
        
        deleted_count = result.rowcount
        if deleted_count > 0:
            self.logger.debug(f"Cleaned up {deleted_count} old tool calls")
        
        return deleted_count
    
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
    
    # ============================================================================
    # Message CRUD Operations
    # ============================================================================
    
    @with_connection(writer=False)
    async def get_message(self, conn,
                         message_id: int,
                         agent_name: Optional[str] = None,
                         agent_project_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get a specific message by ID.
        
        Args:
            message_id: The message ID
            agent_name: Optional agent requesting (for permission check)
            agent_project_id: Optional agent's project ID
        
        Returns:
            Message dict or None if not found/not accessible
        """
        if agent_name:
            # Check permissions using agent_channels view
            cursor = await conn.execute("""
                SELECT m.id, m.channel_id, m.sender_id, m.sender_project_id,
                       m.content, m.timestamp, m.thread_id, m.metadata,
                       m.topic_name, m.ai_metadata, m.confidence, m.model_version,
                       m.intent_type, m.is_edited, m.edited_at,
                       c.channel_type, c.access_type, c.scope, c.name as channel_name
                FROM messages m
                INNER JOIN channels c ON m.channel_id = c.id
                INNER JOIN agent_channels ac ON m.channel_id = ac.channel_id
                WHERE m.id = ?
                  AND ac.agent_name = ?
                  AND ac.agent_project_id IS NOT DISTINCT FROM ?
            """, (message_id, agent_name, agent_project_id))
        else:
            # No permission check - return any message
            cursor = await conn.execute("""
                SELECT m.id, m.channel_id, m.sender_id, m.sender_project_id,
                       m.content, m.timestamp, m.thread_id, m.metadata,
                       m.topic_name, m.ai_metadata, m.confidence, m.model_version,
                       m.intent_type, m.is_edited, m.edited_at,
                       c.channel_type, c.access_type, c.scope, c.name as channel_name
                FROM messages m
                INNER JOIN channels c ON m.channel_id = c.id
                WHERE m.id = ?
            """, (message_id,))
        
        row = await cursor.fetchone()
        if not row:
            return None
        
        return {
            'id': row[0],
            'channel_id': row[1],
            'sender_id': row[2],
            'sender_project_id': row[3],
            'content': row[4],
            'timestamp': row[5],
            'thread_id': row[6],
            'metadata': row[7],
            'topic_name': row[8],
            'ai_metadata': row[9],
            'confidence': row[10],
            'model_version': row[11],
            'intent_type': row[12],
            'is_edited': row[13],
            'edited_at': row[14],
            'channel_type': row[15],
            'access_type': row[16],
            'scope': row[17],
            'channel_name': row[18]
        }
    
    @with_connection(writer=True)
    async def update_message(self, conn,
                           message_id: int,
                           content: str,
                           agent_name: str,
                           agent_project_id: Optional[str] = None) -> bool:
        """
        Update a message's content.
        
        Args:
            message_id: The message ID to update
            content: New content
            agent_name: Agent requesting the update
            agent_project_id: Agent's project ID
        
        Returns:
            True if updated, False if not found or not authorized
        """
        # Verify the agent is the sender
        cursor = await conn.execute("""
            SELECT sender_id, sender_project_id
            FROM messages
            WHERE id = ?
        """, (message_id,))
        
        row = await cursor.fetchone()
        if not row:
            return False
        
        sender_id, sender_project_id = row
        if sender_id != agent_name or sender_project_id != agent_project_id:
            return False  # Not authorized to edit
        
        # Update the message
        await conn.execute("""
            UPDATE messages
            SET content = ?,
                is_edited = TRUE,
                edited_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (content, message_id))
        
        return True
    
    @with_connection(writer=True)
    async def delete_message(self, conn,
                           message_id: int,
                           agent_name: str,
                           agent_project_id: Optional[str] = None) -> bool:
        """
        Delete a message (soft delete by default).
        
        Args:
            message_id: The message ID to delete
            agent_name: Agent requesting deletion
            agent_project_id: Agent's project ID
        
        Returns:
            True if deleted, False if not found or not authorized
        """
        # Verify the agent is the sender or has admin rights
        cursor = await conn.execute("""
            SELECT m.sender_id, m.sender_project_id, m.channel_id,
                   cm.role
            FROM messages m
            LEFT JOIN channel_members cm ON 
                m.channel_id = cm.channel_id
                AND cm.agent_name = ?
                AND cm.agent_project_id IS NOT DISTINCT FROM ?
            WHERE m.id = ?
        """, (agent_name, agent_project_id, message_id))
        
        row = await cursor.fetchone()
        if not row:
            return False
        
        sender_id, sender_project_id, channel_id, member_role = row
        
        # Check authorization: sender or channel admin
        is_sender = (sender_id == agent_name and sender_project_id == agent_project_id)
        is_admin = member_role in ('owner', 'admin')
        
        if not (is_sender or is_admin):
            return False
        
        # Perform soft delete by updating content
        await conn.execute("""
            UPDATE messages
            SET content = '[Message deleted]',
                is_edited = TRUE,
                edited_at = CURRENT_TIMESTAMP,
                metadata = json_set(
                    COALESCE(metadata, '{}'),
                    '$.deleted', true,
                    '$.deleted_by', ?,
                    '$.deleted_at', datetime('now')
                )
            WHERE id = ?
        """, (agent_name, message_id))
        
        return True