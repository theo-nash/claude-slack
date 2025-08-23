#!/usr/bin/env python3
"""
Channel Manager v3 for Claude-Slack
Manages channels using DatabaseManagerV3 for all database operations
Phase 2 (v3.0.0) Implementation

This manager acts as a higher-level abstraction over DatabaseManagerV3,
focusing on channel-specific business logic and validation.
"""

import os
import sys
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from db.manager_v3 import DatabaseManagerV3
except ImportError as e:
    print(f"Import error in ChannelManagerV3: {e}", file=sys.stderr)
    DatabaseManagerV3 = None

try:
    from config_manager import get_config_manager
except ImportError:
    get_config_manager = None

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)


class ChannelType(Enum):
    """Channel types in the unified system"""
    CHANNEL = 'channel'
    DIRECT = 'direct'


class AccessType(Enum):
    """Channel access types"""
    OPEN = 'open'        # Anyone can subscribe
    MEMBERS = 'members'  # Invite-only
    PRIVATE = 'private'  # Fixed membership (DMs)


@dataclass
class ChannelV3:
    """Data class representing a channel in v3"""
    id: str  # Full channel ID
    channel_type: ChannelType
    access_type: AccessType
    scope: str  # 'global' or 'project'
    name: str  # Channel name or DM identifier
    project_id: Optional[str]
    description: Optional[str]
    created_by: Optional[str]
    created_by_project_id: Optional[str]
    created_at: datetime
    is_default: bool = False
    is_archived: bool = False
    topic_required: bool = False  # Pre-allocated for Phase 1
    default_topic: str = 'general'  # Pre-allocated for Phase 1
    metadata: Optional[Dict[str, Any]] = None


class ChannelManagerV3:
    """
    Manages channels using DatabaseManagerV3.
    
    This manager provides channel-specific operations and business logic,
    delegating all database operations to DatabaseManagerV3.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize ChannelManagerV3.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.logger = get_logger('ChannelManagerV3', component='manager')
        
        if DatabaseManagerV3:
            self.db = DatabaseManagerV3(db_path)
        else:
            self.db = None
            self.logger.error("DatabaseManagerV3 not available")
    
    async def initialize(self):
        """Initialize the database if needed"""
        if self.db:
            await self.db.initialize()
    
    @staticmethod
    def get_scoped_channel_id(name: str, scope: str, project_id: Optional[str] = None) -> str:
        """
        Generate the full channel ID with scope prefix.
        
        Args:
            name: Channel name without prefix
            scope: 'global' or 'project'
            project_id: Project ID for project channels
            
        Returns:
            Full channel ID (e.g., "global:general" or "proj_abc123:dev")
        """
        if scope == 'global':
            return f"global:{name}"
        elif scope == 'project' and project_id:
            project_id_short = project_id[:8] if len(project_id) > 8 else project_id
            return f"proj_{project_id_short}:{name}"
        else:
            return f"global:{name}"
    
    @staticmethod
    def parse_channel_id(channel_id: str) -> Dict[str, Any]:
        """
        Parse a channel ID to determine its type and components.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            Dictionary with parsed components
        """
        if channel_id.startswith('dm:'):
            # DM channel
            parts = channel_id[3:].split(':')
            if len(parts) >= 4:
                return {
                    'type': 'direct',
                    'agent1_name': parts[0],
                    'agent1_project_id': parts[1] if parts[1] else None,
                    'agent2_name': parts[2],
                    'agent2_project_id': parts[3] if len(parts) > 3 and parts[3] else None
                }
        elif channel_id.startswith('global:'):
            # Global channel
            return {
                'type': 'channel',
                'scope': 'global',
                'name': channel_id[7:],
                'project_id': None
            }
        elif channel_id.startswith('proj_'):
            # Project channel
            parts = channel_id.split(':', 1)
            if len(parts) == 2:
                project_part = parts[0][5:]  # Remove 'proj_' prefix
                return {
                    'type': 'channel',
                    'scope': 'project',
                    'name': parts[1],
                    'project_id_short': project_part
                }
        
        # Unknown format
        return {'type': 'unknown', 'raw': channel_id}
    
    @staticmethod
    def validate_channel_name(name: str) -> bool:
        """
        Validate a channel name.
        
        Args:
            name: Channel name to validate
            
        Returns:
            True if valid, False otherwise
        """
        import re
        # Channel names should be lowercase alphanumeric with hyphens
        pattern = r'^[a-z0-9-]+$'
        return bool(re.match(pattern, name))
    
    async def create_channel(self, 
                           name: str,
                           scope: str,
                           access_type: str = 'open',
                           project_id: Optional[str] = None,
                           description: Optional[str] = None,
                           created_by: Optional[str] = None,
                           created_by_project_id: Optional[str] = None,
                           is_default: bool = False) -> Optional[str]:
        """
        Create a new channel.
        
        Args:
            name: Channel name (without prefix)
            scope: 'global' or 'project'
            access_type: 'open', 'members', or 'private'
            project_id: Project ID for project channels
            description: Channel description
            created_by: Agent who created the channel
            created_by_project_id: Creator's project ID
            is_default: Whether this is a default channel
            
        Returns:
            Channel ID if created successfully, None otherwise
        """
        if not self.db:
            self.logger.error("Database manager not available")
            return None
        
        # Validate channel name
        if not self.validate_channel_name(name):
            self.logger.error(f"Invalid channel name: {name}")
            return None
        
        # Validate scope and project_id combination
        if scope == 'project' and not project_id:
            self.logger.error("Project ID required for project channels")
            return None
        
        # Strip project_id if global scope
        if scope == 'global':
            project_id = None
        
        channel_id = self.get_scoped_channel_id(name, scope, project_id)
        
        if not description:
            description = f"{scope.title()} {name} channel"
        
        self.logger.info(f"Creating channel: {channel_id} (access_type={access_type})")
        
        try:
            # Use DatabaseManagerV3 to create the channel
            created_id = await self.db.create_channel(
                channel_id=channel_id,
                channel_type='channel',
                access_type=access_type,
                scope=scope,
                name=name,
                project_id=project_id,
                description=description,
                created_by=created_by,
                created_by_project_id=created_by_project_id,
                is_default=is_default
            )
            
            # If it's a members or private channel with a creator, add them as member
            # (DatabaseManagerV3 doesn't do this automatically for regular channels)
            if created_id and access_type in ['members', 'private'] and created_by:
                await self.db.add_channel_member(
                    channel_id=created_id,
                    agent_name=created_by,
                    agent_project_id=created_by_project_id,
                    role='owner',
                    can_send=True,
                    can_manage_members=True,
                    added_by=created_by,
                    added_by_project_id=created_by_project_id
                )
            
            return created_id
            
        except Exception as e:
            self.logger.error(f"Error creating channel: {e}")
            return None
    
    async def create_dm_channel(self,
                              agent1_name: str,
                              agent1_project_id: Optional[str],
                              agent2_name: str,
                              agent2_project_id: Optional[str]) -> Optional[str]:
        """
        Create a DM channel between two agents.
        
        Args:
            agent1_name: First agent name
            agent1_project_id: First agent's project ID
            agent2_name: Second agent name
            agent2_project_id: Second agent's project ID
            
        Returns:
            DM channel ID if created successfully, None otherwise
        """
        if not self.db:
            self.logger.error("Database manager not available")
            return None
        
        try:
            # Use DatabaseManagerV3 to create or get the DM channel
            dm_channel_id = await self.db.create_or_get_dm_channel(
                agent1_name, agent1_project_id,
                agent2_name, agent2_project_id
            )
            return dm_channel_id
            
        except ValueError as e:
            self.logger.error(f"Cannot create DM: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error creating DM channel: {e}")
            return None
    
    async def get_channel(self, channel_id: str) -> Optional[ChannelV3]:
        """
        Get a channel by ID.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            ChannelV3 object or None if not found
        """
        if not self.db:
            return None
        
        try:
            # Use DatabaseManagerV3 to get channel information
            channel_data = await self.db.get_channel(channel_id)
            
            if not channel_data:
                return None
            
            # Convert to ChannelV3 object
            return ChannelV3(
                id=channel_data['id'],
                channel_type=ChannelType(channel_data['channel_type']),
                access_type=AccessType(channel_data['access_type']),
                scope=channel_data['scope'],
                name=channel_data['name'],
                project_id=channel_data['project_id'],
                description=channel_data['description'],
                created_by=channel_data['created_by'],
                created_by_project_id=channel_data['created_by_project_id'],
                created_at=datetime.fromisoformat(channel_data['created_at']) if channel_data['created_at'] else datetime.now(),
                is_default=bool(channel_data['is_default']),
                is_archived=bool(channel_data['is_archived']),
                topic_required=bool(channel_data['topic_required']),
                default_topic=channel_data['default_topic'] or 'general',
                metadata=channel_data['channel_metadata']
            )
            
        except Exception as e:
            self.logger.error(f"Error getting channel: {e}")
            return None
    
    async def list_channels_for_agent(self,
                                     agent_name: str,
                                     agent_project_id: Optional[str] = None,
                                     include_archived: bool = False) -> List[Dict[str, Any]]:
        """
        List all channels accessible to an agent.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            include_archived: Include archived channels
            
        Returns:
            List of channel dictionaries
        """
        if not self.db:
            return []
        
        try:
            # Use DatabaseManagerV3 to get agent's channels
            channels = await self.db.get_agent_channels(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                include_archived=include_archived
            )
            return channels
            
        except Exception as e:
            self.logger.error(f"Error listing channels: {e}")
            return []
    
    async def add_channel_member(self,
                                channel_id: str,
                                agent_name: str,
                                agent_project_id: Optional[str] = None,
                                role: str = 'member',
                                can_send: bool = True,
                                can_manage_members: bool = False,
                                added_by: Optional[str] = None,
                                added_by_project_id: Optional[str] = None) -> bool:
        """
        Add a member to a channel.
        
        Args:
            channel_id: Channel ID
            agent_name: Agent to add
            agent_project_id: Agent's project ID
            role: Member role (owner/admin/member)
            can_send: Whether member can send messages
            can_manage_members: Whether member can manage other members
            added_by: Agent who added this member
            added_by_project_id: Adder's project ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            await self.db.add_channel_member(
                channel_id=channel_id,
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                role=role,
                can_send=can_send,
                can_manage_members=can_manage_members,
                added_by=added_by,
                added_by_project_id=added_by_project_id
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding channel member: {e}")
            return False
    
    async def remove_channel_member(self,
                                   channel_id: str,
                                   agent_name: str,
                                   agent_project_id: Optional[str] = None) -> bool:
        """
        Remove a member from a channel.
        
        Args:
            channel_id: Channel ID
            agent_name: Agent to remove
            agent_project_id: Agent's project ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            await self.db.remove_channel_member(
                channel_id=channel_id,
                agent_name=agent_name,
                agent_project_id=agent_project_id
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error removing channel member: {e}")
            return False
    
    async def subscribe_to_channel(self,
                                  agent_name: str,
                                  agent_project_id: Optional[str],
                                  channel_id: str) -> bool:
        """
        Subscribe an agent to an open channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel_id: Channel to subscribe to
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            await self.db.subscribe_to_channel(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                channel_id=channel_id
            )
            return True
            
        except ValueError as e:
            self.logger.error(f"Cannot subscribe: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error subscribing to channel: {e}")
            return False
    
    async def unsubscribe_from_channel(self,
                                      agent_name: str,
                                      agent_project_id: Optional[str],
                                      channel_id: str) -> bool:
        """
        Unsubscribe an agent from a channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel_id: Channel to unsubscribe from
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            await self.db.unsubscribe_from_channel(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                channel_id=channel_id
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from channel: {e}")
            return False
    
    async def get_channel_members(self, channel_id: str) -> List[Dict[str, Any]]:
        """
        Get all members of a channel.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            List of member dictionaries
        """
        if not self.db:
            return []
        
        try:
            members = await self.db.get_channel_members(channel_id)
            return members
            
        except Exception as e:
            self.logger.error(f"Error getting channel members: {e}")
            return []
    
    async def is_channel_member(self,
                               channel_id: str,
                               agent_name: str,
                               agent_project_id: Optional[str] = None) -> bool:
        """
        Check if an agent is a member of a channel.
        
        Args:
            channel_id: Channel ID
            agent_name: Agent name
            agent_project_id: Agent's project ID
            
        Returns:
            True if agent is a member, False otherwise
        """
        members = await self.get_channel_members(channel_id)
        for member in members:
            if (member['agent_name'] == agent_name and 
                member['agent_project_id'] == agent_project_id):
                return True
        return False
    
    async def send_message_to_channel(self,
                                     channel_id: str,
                                     sender_id: str,
                                     sender_project_id: Optional[str],
                                     content: str,
                                     metadata: Optional[Dict] = None,
                                     thread_id: Optional[str] = None) -> Optional[int]:
        """
        Send a message to a channel.
        
        Args:
            channel_id: Target channel
            sender_id: Sender agent name
            sender_project_id: Sender's project ID
            content: Message content
            metadata: Optional metadata
            thread_id: Optional thread ID
            
        Returns:
            Message ID if successful, None otherwise
        """
        if not self.db:
            return None
        
        try:
            message_id = await self.db.send_message(
                channel_id=channel_id,
                sender_id=sender_id,
                sender_project_id=sender_project_id,
                content=content,
                metadata=metadata,
                thread_id=thread_id
            )
            return message_id
            
        except ValueError as e:
            self.logger.error(f"Cannot send message: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return None