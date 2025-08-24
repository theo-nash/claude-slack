#!/usr/bin/env python3
"""
Channel Manager for Claude-Slack
Manages channels using DatabaseManager for all database operations
Phase 2 Implementation

This manager acts as a higher-level abstraction over DatabaseManager,
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
    from db.manager import DatabaseManager
    from db.initialization import DatabaseInitializer, ensure_db_initialized
except ImportError as e:
    print(f"Import error in ChannelManager: {e}", file=sys.stderr)
    DatabaseManager = None
    DatabaseInitializer = object  # Fallback to object if not available
    ensure_db_initialized = lambda f: f  # No-op decorator

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


class ChannelManager(DatabaseInitializer):
    """
    Manages channels using DatabaseManager.
    
    This manager provides channel-specific operations and business logic,
    delegating all database operations to DatabaseManager.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize ChannelManager.
        
        Args:
            db_path: Path to SQLite database
        """
        # Initialize parent class (DatabaseInitializer)
        super().__init__()
        
        self.db_path = db_path
        self.logger = get_logger('ChannelManager', component='manager')
        
        if DatabaseManager:
            self.db = DatabaseManager(db_path)
            self.db_manager = self.db  # Required for DatabaseInitializer mixin
        else:
            self.db = None
            self.db_manager = None
            self.logger.error("DatabaseManager not available")
    
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
    
    @ensure_db_initialized
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
                    invited_by='system',  # System adds creator
                    source='system',
                    can_leave=(access_type != 'private'),  # Can't leave private channels
                    can_send=True,
                    can_invite=(access_type == 'members'),  # Can invite in members channels
                    can_manage=True  # Creator can manage
                )
            
            return created_id
            
        except Exception as e:
            self.logger.error(f"Error creating channel: {e}")
            return None
    
    @ensure_db_initialized
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
    
    @ensure_db_initialized
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
    
    @ensure_db_initialized
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
    
    # Note: Old add_channel_member, remove_channel_member, subscribe_to_channel, 
    # and unsubscribe_from_channel methods removed in favor of unified API below
    
    @ensure_db_initialized
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
    
    @ensure_db_initialized
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
        if not self.db:
            return False
        
        try:
            return await self.db.is_channel_member(channel_id, agent_name, agent_project_id)
        except Exception as e:
            self.logger.error(f"Error checking membership: {e}")
            return False
    
    @ensure_db_initialized
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
    
    # ============================================================================
    # Unified Membership API (Phase 2)
    # ============================================================================
    
    @ensure_db_initialized
    async def join_channel(self,
                          agent_name: str,
                          agent_project_id: Optional[str],
                          channel_id: str) -> bool:
        """
        Join an open channel (self-service subscription).
        
        This is the unified API for subscribing to open channels.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel_id: Channel to join
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            # Get channel info to verify it's open
            channel = await self.db.get_channel(channel_id)
            if not channel:
                self.logger.error(f"Channel {channel_id} not found")
                return False
            
            if channel['access_type'] != 'open':
                self.logger.error(f"Channel {channel_id} is not open for self-service joining")
                return False
            
            # Add as member with invited_by='self'
            await self.db.add_channel_member(
                channel_id=channel_id,
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                invited_by='self',
                source='manual',
                can_leave=True,
                can_send=True,
                can_invite=True,  # Open channels allow invites
                can_manage=False
            )
            
            self.logger.info(f"Agent {agent_name} joined channel {channel_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error joining channel: {e}")
            return False
    
    @ensure_db_initialized
    async def invite_to_channel(self,
                              channel_id: str,
                              invitee_name: str,
                              invitee_project_id: Optional[str],
                              inviter_name: str,
                              inviter_project_id: Optional[str]) -> bool:
        """
        Invite an agent to a members channel.
        
        Args:
            channel_id: Target channel
            invitee_name: Agent to invite
            invitee_project_id: Invitee's project ID
            inviter_name: Agent doing the inviting
            inviter_project_id: Inviter's project ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            # Get channel info
            channel = await self.db.get_channel(channel_id)
            if not channel:
                self.logger.error(f"Channel {channel_id} not found")
                return False
            
            # Check if inviter can invite
            if channel['access_type'] == 'private':
                self.logger.error("Cannot invite to private channels")
                return False
            
            # For members channels, check if inviter has permission
            if channel['access_type'] == 'members':
                members = await self.db.get_channel_members(channel_id)
                inviter_member = None
                for member in members:
                    if (member['agent_name'] == inviter_name and
                        member['agent_project_id'] == inviter_project_id):
                        inviter_member = member
                        break
                
                if not inviter_member:
                    self.logger.error(f"{inviter_name} is not a member of {channel_id}")
                    return False
                
                if not inviter_member.get('can_invite', False):
                    self.logger.error(f"{inviter_name} cannot invite to {channel_id}")
                    return False
            
            # Add invitee as member
            await self.db.add_channel_member(
                channel_id=channel_id,
                agent_name=invitee_name,
                agent_project_id=invitee_project_id,
                invited_by=inviter_name,
                source='manual',
                can_leave=True,
                can_send=True,
                can_invite=(channel['access_type'] == 'open'),
                can_manage=False
            )
            
            self.logger.info(f"{inviter_name} invited {invitee_name} to {channel_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error inviting to channel: {e}")
            return False
    
    @ensure_db_initialized
    async def leave_channel(self,
                           agent_name: str,
                           agent_project_id: Optional[str],
                           channel_id: str) -> bool:
        """
        Leave a channel (unified for all channel types).
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel_id: Channel to leave
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            # Check if agent can leave
            members = await self.db.get_channel_members(channel_id)
            member = None
            for m in members:
                if (m['agent_name'] == agent_name and
                    m['agent_project_id'] == agent_project_id):
                    member = m
                    break
            
            if not member:
                self.logger.error(f"{agent_name} is not a member of {channel_id}")
                return False
            
            if not member.get('can_leave', True):
                self.logger.error(f"{agent_name} cannot leave {channel_id} (e.g., DM channel)")
                return False
            
            # Remove membership
            await self.db.remove_channel_member(
                channel_id=channel_id,
                agent_name=agent_name,
                agent_project_id=agent_project_id
            )
            
            self.logger.info(f"Agent {agent_name} left channel {channel_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error leaving channel: {e}")
            return False
    
    @ensure_db_initialized
    async def apply_default_channels(self,
                                    agent_name: str,
                                    agent_project_id: Optional[str] = None,
                                    exclusions: List[str] = None) -> int:
        """
        Apply default channel memberships for an agent.
        
        This method is called during agent registration to automatically
        add them to channels marked with is_default=true.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            exclusions: List of channel names to exclude
            
        Returns:
            Number of channels the agent was added to
        """
        if not self.db:
            return 0
        
        if exclusions is None:
            exclusions = []
        
        added_count = 0
        
        try:
            # Determine agent's scope
            agent_scope = 'project' if agent_project_id else 'global'
            
            # Get all default channels the agent is eligible for
            channels = await self.db.get_default_channels(
                scope='all',  # Get all, we'll filter
                project_id=agent_project_id
            )
            
            for channel in channels:
                # Skip excluded channels
                if channel['name'] in exclusions:
                    self.logger.debug(f"Skipping excluded channel: {channel['name']}")
                    continue
                
                # Check scope eligibility
                if channel['scope'] == 'project' and channel['project_id'] != agent_project_id:
                    continue  # Different project
                
                # Check if already a member
                is_member = await self.db.is_channel_member(
                    channel['id'],
                    agent_name,
                    agent_project_id
                )
                if is_member:
                    continue
                
                # Add to channel based on access type
                invited_by = 'self' if channel['access_type'] == 'open' else 'system'
                can_invite = (channel['access_type'] == 'open')
                
                await self.db.add_channel_member(
                    channel_id=channel['id'],
                    agent_name=agent_name,
                    agent_project_id=agent_project_id,
                    invited_by=invited_by,
                    source='default',
                    can_leave=True,
                    can_send=True,
                    can_invite=can_invite,
                    can_manage=False,
                    is_from_default=True
                )
                
                added_count += 1
                self.logger.info(f"Added {agent_name} to default channel: {channel['id']}")
            
            return added_count
            
        except Exception as e:
            self.logger.error(f"Error applying default channels: {e}")
            return added_count