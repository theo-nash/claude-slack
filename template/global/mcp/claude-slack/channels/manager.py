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
            # Use project_id as-is (it's already like "proj_test1")
            return f"{project_id}:{name}"
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
        List all channels the agent is currently a member of.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            include_archived: Include archived channels
            
        Returns:
            List of channel dictionaries (channels agent is member of)
        """
        if not self.db:
            return []
        
        try:
            # Use DatabaseManagerV3 to get agent's channels (where they're a member)
            channels = await self.db.get_agent_channels(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                include_archived=include_archived
            )
            return channels
            
        except Exception as e:
            self.logger.error(f"Error listing channels: {e}")
            return []
    
    @ensure_db_initialized
    async def list_available_channels(self,
                                     agent_name: str,
                                     agent_project_id: Optional[str] = None,
                                     scope_filter: str = 'all',
                                     include_archived: bool = False) -> List[Dict[str, Any]]:
        """
        List all channels available/discoverable to an agent (including ones they could join).
        
        This includes:
        - Channels they're already members of
        - Open channels they could join (respecting scope access)
        - Members/private channels they can see but can't self-join
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            scope_filter: 'all', 'global', or 'project'
            include_archived: Include archived channels
            
        Returns:
            List of channel dictionaries with membership status
        """
        if not self.db:
            return []
        
        try:
            result = []
            
            # Get all channels from database
            all_channels = await self.db.get_channels_by_scope(
                scope='all',
                project_id=None
            )
            
            # Get channels agent is already member of
            member_channels = await self.db.get_agent_channels(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                include_archived=True  # Get all to check membership
            )
            member_channel_ids = {ch['id'] for ch in member_channels}
            
            for channel in all_channels:
                # Skip archived if not requested
                if channel.get('is_archived') and not include_archived:
                    continue
                
                # Apply scope filter
                if scope_filter != 'all':
                    if channel['scope'] != scope_filter:
                        continue
                
                # Determine visibility and access
                is_member = channel['id'] in member_channel_ids
                can_see = False
                can_join = False
                access_reason = ""
                
                # Determine if agent can see this channel
                if is_member:
                    can_see = True
                    access_reason = "member"
                elif channel['scope'] == 'global':
                    can_see = True
                    can_join = (channel['access_type'] == 'open')
                    access_reason = "global channel"
                elif channel['scope'] == 'project':
                    # Same project
                    if agent_project_id == channel['project_id']:
                        can_see = True
                        can_join = (channel['access_type'] == 'open')
                        access_reason = "same project"
                    # Linked projects
                    elif agent_project_id and await self.db.check_projects_linked(
                        agent_project_id, channel['project_id']
                    ):
                        can_see = True
                        can_join = (channel['access_type'] == 'open')
                        access_reason = "linked project"
                    # Global agent
                    elif agent_project_id is None:
                        can_see = True
                        can_join = (channel['access_type'] == 'open')
                        access_reason = "global agent access"
                
                # Add to result if visible
                if can_see:
                    result.append({
                        'id': channel['id'],
                        'channel_type': channel.get('channel_type', 'channel'),
                        'access_type': channel.get('access_type', 'open'),
                        'scope': channel['scope'],
                        'name': channel['name'],
                        'description': channel.get('description'),
                        'project_id': channel.get('project_id'),
                        'is_default': channel.get('is_default', False),
                        'is_archived': channel.get('is_archived', False),
                        'is_member': is_member,
                        'can_join': can_join and not is_member,
                        'access_reason': access_reason
                    })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error listing available channels: {e}")
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
        Enforces scope restrictions: agents can only self-join channels 
        they have natural access to (same project, linked projects, or global).
        
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
            # Get channel info to verify it's open and check scope
            channel = await self.db.get_channel(channel_id)
            if not channel:
                self.logger.error(f"Channel {channel_id} not found")
                return False
            
            # Check 1: Channel must be open for self-service joining
            if channel['access_type'] != 'open':
                self.logger.error(f"Channel {channel_id} is not open for self-service joining (type={channel['access_type']})")
                return False
            
            # Check 2: Scope eligibility - critical for project isolation
            if channel['scope'] == 'project':
                channel_project_id = channel['project_id']
                
                # Allow if same project
                if agent_project_id == channel_project_id:
                    pass  # Same project - allowed
                # Allow if projects are linked
                elif agent_project_id and await self.db.check_projects_linked(agent_project_id, channel_project_id):
                    self.logger.info(f"Allowing cross-project join: projects {agent_project_id} and {channel_project_id} are linked")
                # Allow if agent is global (no project_id)
                elif agent_project_id is None:
                    self.logger.info(f"Allowing global agent to join project channel {channel_id}")
                else:
                    self.logger.error(
                        f"Agent from project {agent_project_id} cannot self-join "
                        f"channel {channel_id} from project {channel_project_id}. "
                        f"Projects are not linked. Cross-project access requires invitation."
                    )
                    return False
            # Global channels: any agent can self-join (no check needed)
            
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
        Invite an agent to a members-only channel.
        
        Open channels don't need invitations - agents can self-join.
        Private channels (DMs) have fixed membership.
        
        Args:
            channel_id: Target channel (must be members-only)
            invitee_name: Agent to invite
            invitee_project_id: Invitee's project ID
            inviter_name: Agent doing the inviting (must be a member)
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
            
            # Only allow invitations to members-only channels
            if channel['access_type'] == 'open':
                self.logger.error(
                    f"Cannot invite to open channel {channel_id}. "
                    f"Open channels allow self-service joining via join_channel."
                )
                return False
            
            if channel['access_type'] == 'private':
                self.logger.error("Cannot invite to private channels (DMs have fixed membership)")
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
    
    @ensure_db_initialized
    async def send_message(self,
                          channel_id: str,
                          sender_name: str,
                          sender_project_id: Optional[str],
                          content: str,
                          metadata: Optional[Dict] = None,
                          thread_id: Optional[str] = None) -> int:
        """
        Send a message to a channel with validation.
        
        Raises:
            ValueError: If validation fails
            
        Returns:
            Message ID
        """
        # Validate content
        if not content or not content.strip():
            raise ValueError("Cannot send empty message")
        
        # Get member record with permissions in one query
        members = await self.db.get_channel_members(channel_id)
        sender_member = next(
            (m for m in members
             if m['agent_name'] == sender_name
             and m['agent_project_id'] == sender_project_id),
            None
        )
        
        if not sender_member:
            raise ValueError(f"Agent {sender_name} is not a member of channel {channel_id}")
        
        if not sender_member.get('can_send', True):
            raise ValueError(f"Agent {sender_name} does not have send permission")
        
        # Validate mentions (warning only)
        mentions = await self._validate_mentions(channel_id, content)
        if mentions and metadata is not None:
            metadata['mentions'] = mentions
        elif mentions and metadata is None:
            metadata = {'mentions': mentions}
        
        # Send via database (will do its own permission check as safety net)
        try:
            message_id = await self.db.send_message(
                channel_id=channel_id,
                sender_id=sender_name,
                sender_project_id=sender_project_id,
                content=content,
                metadata=metadata,
                thread_id=thread_id
            )
            self.logger.info(f"Message {message_id} sent to {channel_id} by {sender_name}")
            return message_id
        except ValueError as e:
            # Database-level permission check failed
            self.logger.error(f"Database rejected message: {e}")
            raise
    
    async def _validate_mentions(self, channel_id: str, content: str) -> List[str]:
        """
        Validate @mentions in message content.
        
        Handles various mention formats:
        - Simple: @alice
        - Hyphenated: @backend-engineer
        - Project-scoped: @alice:proj_123
        
        Args:
            channel_id: Channel the message is being sent to
            content: Message content
            
        Returns:
            List of valid mentioned agent names
        """
        import re
        # Pattern matches: @word, @hyphen-word, @word:project
        mentions = re.findall(r'@([\w-]+(?::[\w-]+)?)', content)
        if not mentions:
            return []
        
        # Get channel members to validate mentions
        members = await self.db.get_channel_members(channel_id)
        
        # Build lookup sets for validation
        member_names = {m['agent_name'] for m in members}
        # Also track project-scoped names
        member_full_ids = {
            f"{m['agent_name']}:{m['agent_project_id']}" if m['agent_project_id'] else m['agent_name']
            for m in members
        }
        
        valid_mentions = []
        for mentioned in mentions:
            # Check if it's a simple name or project-scoped
            if ':' in mentioned:
                # Project-scoped mention (e.g., @alice:proj_123)
                if mentioned in member_full_ids:
                    valid_mentions.append(mentioned)
                else:
                    self.logger.warning(f"Mentioned agent @{mentioned} is not in channel {channel_id}")
            else:
                # Simple mention (e.g., @alice or @backend-engineer)
                if mentioned in member_names:
                    valid_mentions.append(mentioned)
                else:
                    self.logger.warning(f"Mentioned agent @{mentioned} is not in channel {channel_id}")
        
        return valid_mentions
    
    @ensure_db_initialized
    async def send_direct_message(self,
                                 sender_name: str,
                                 sender_project_id: Optional[str],
                                 recipient_name: str,
                                 recipient_project_id: Optional[str],
                                 content: str,
                                 metadata: Optional[Dict] = None) -> int:
        """
        Send a direct message to another agent (creates DM channel if needed).
        
        This is a convenience method that handles DM channel creation/retrieval
        and sends the message in one operation.
        
        Args:
            sender_name: Agent sending the message
            sender_project_id: Sender's project ID
            recipient_name: Agent receiving the message
            recipient_project_id: Recipient's project ID
            content: Message content
            metadata: Optional metadata
            
        Returns:
            Message ID
            
        Raises:
            ValueError: If DM is not allowed between agents or validation fails
        """
        # Get or create DM channel
        try:
            dm_channel_id = await self.db.create_or_get_dm_channel(
                sender_name, sender_project_id,
                recipient_name, recipient_project_id
            )
        except ValueError as e:
            # DM not allowed between these agents
            self.logger.error(f"Cannot create DM channel: {e}")
            raise
        
        # Use the unified send_message method
        return await self.send_message(
            channel_id=dm_channel_id,
            sender_name=sender_name,
            sender_project_id=sender_project_id,
            content=content,
            metadata=metadata
        )
    
    @ensure_db_initialized
    async def get_channel_messages(self,
                                  channel_id: str,
                                  requester_name: str,
                                  requester_project_id: Optional[str],
                                  limit: int = 100,
                                  since: Optional[str] = None) -> List[Dict]:
        """
        Get messages from a channel (with permission check).
        
        Args:
            channel_id: Channel to get messages from
            requester_name: Agent requesting messages
            requester_project_id: Requester's project ID
            limit: Maximum number of messages to return
            since: Optional timestamp to get messages since
            
        Returns:
            List of message dictionaries
            
        Raises:
            ValueError: If requester is not a member
        """
        # Verify requester is a member
        is_member = await self.db.is_channel_member(
            channel_id, requester_name, requester_project_id
        )
        if not is_member:
            raise ValueError(f"Agent {requester_name} is not a member of {channel_id}")
        
        # Get messages from database
        # Note: get_messages expects different parameters, using get_channel_messages instead
        messages = await self.db.get_messages(
            agent_name=requester_name,
            agent_project_id=requester_project_id,
            channel_id=channel_id,
            limit=limit,
            since=since
        )
        
        self.logger.debug(f"Retrieved {len(messages)} messages from {channel_id}")
        return messages
    
    @ensure_db_initialized
    async def send_to_channel(self,
                            channel_name: str,
                            scope: str,
                            sender_name: str,
                            sender_project_id: Optional[str],
                            content: str,
                            metadata: Optional[Dict] = None,
                            project_id: Optional[str] = None) -> int:
        """
        Send message to a named channel (resolves channel_id).
        
        This is a convenience method that constructs the channel_id
        from the channel name and scope.
        
        Args:
            channel_name: Channel name (without scope prefix)
            scope: 'global' or 'project'
            sender_name: Agent sending the message
            sender_project_id: Sender's project ID
            content: Message content
            metadata: Optional metadata
            project_id: Project ID for project-scoped channels (defaults to sender's)
            
        Returns:
            Message ID
            
        Raises:
            ValueError: If validation fails or channel doesn't exist
        """
        # For project scope, use provided project_id or sender's project
        if scope == 'project':
            project_id = project_id or sender_project_id
            if not project_id:
                raise ValueError("Project ID required for project-scoped channels")
        else:
            project_id = None
        
        # Build channel ID
        channel_id = self.get_scoped_channel_id(channel_name, scope, project_id)
        
        # Send the message
        return await self.send_message(
            channel_id=channel_id,
            sender_name=sender_name,
            sender_project_id=sender_project_id,
            content=content,
            metadata=metadata
        )