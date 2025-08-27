#!/usr/bin/env python3
"""
Improved Channel Manager - Pure Business Logic
This manager focuses ONLY on channel-specific business logic,
delegating all storage operations to MessageStore.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import re


class ChannelType(Enum):
    """Channel types in the unified system"""
    CHANNEL = 'channel'
    DIRECT = 'direct'


class AccessType(Enum):
    """Channel access types"""
    OPEN = 'open'        # Anyone can subscribe
    MEMBERS = 'members'  # Invite-only
    PRIVATE = 'private'  # Fixed membership (DMs)


class ChannelManager:
    """
    Pure business logic for channels.
    No direct database access - all storage through MessageStore.
    """
    
    def __init__(self, message_store):
        """
        Initialize with MessageStore for all storage operations.
        
        Args:
            message_store: MessageStore instance for storage operations
        """
        self.store = message_store
    
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
            return f"{project_id}:{name}"
        else:
            return f"global:{name}"
    
    @staticmethod
    def validate_channel_name(name: str) -> tuple[bool, Optional[str]]:
        """
        Validate a channel name.
        
        Args:
            name: Channel name to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not name:
            return False, "Channel name cannot be empty"
        
        if len(name) > 80:
            return False, "Channel name cannot exceed 80 characters"
        
        # Channel names should be lowercase alphanumeric with hyphens
        pattern = r'^[a-z0-9-]+$'
        if not re.match(pattern, name):
            return False, "Channel name must contain only lowercase letters, numbers, and hyphens"
        
        if name.startswith('-') or name.endswith('-'):
            return False, "Channel name cannot start or end with a hyphen"
        
        if '--' in name:
            return False, "Channel name cannot contain consecutive hyphens"
        
        return True, None
    
    @staticmethod
    def extract_mentions(content: str) -> List[Dict[str, Optional[str]]]:
        """
        Extract @mentions from message content.
        
        Handles various mention formats:
        - Simple: @alice
        - Hyphenated: @backend-engineer
        - Project-scoped: @alice:proj_123
        
        Args:
            content: Message content
            
        Returns:
            List of mention dictionaries with 'name' and 'project_id' keys
        """
        # Pattern matches: @word, @hyphen-word, @word:project
        pattern = r'@([\w-]+)(?::([\w-]+))?'
        matches = re.findall(pattern, content)
        
        mentions = []
        for match in matches:
            name = match[0]
            project_id = match[1] if len(match) > 1 and match[1] else None
            mentions.append({
                'name': name,
                'project_id': project_id,
                'raw': f"@{name}:{project_id}" if project_id else f"@{name}"
            })
        
        return mentions
    
    async def validate_mentions_for_channel(self, 
                                           channel_id: str,
                                           mentions: List[Dict]) -> Dict[str, List]:
        """
        Validate that mentioned agents are in the channel.
        
        Args:
            channel_id: Channel ID
            mentions: List of mention dicts from extract_mentions
            
        Returns:
            Dict with 'valid' and 'invalid' mention lists
        """
        # Get channel members from storage
        members = await self.store.sqlite.get_channel_members(channel_id)
        
        # Build lookup sets
        member_lookup = set()
        for m in members:
            # Add simple name
            member_lookup.add(m['agent_name'])
            # Add project-scoped name if applicable
            if m.get('agent_project_id'):
                member_lookup.add(f"{m['agent_name']}:{m['agent_project_id']}")
        
        valid = []
        invalid = []
        
        for mention in mentions:
            lookup_key = mention['raw'].lstrip('@')
            if lookup_key in member_lookup:
                valid.append(mention)
            else:
                invalid.append(mention)
        
        return {'valid': valid, 'invalid': invalid}
    
    async def validate_channel_access(self,
                                     channel_id: str,
                                     agent_name: str,
                                     agent_project_id: Optional[str],
                                     required_permission: str = 'can_send') -> tuple[bool, Optional[str]]:
        """
        Validate agent's access to a channel.
        
        Args:
            channel_id: Channel to check
            agent_name: Agent name
            agent_project_id: Agent's project ID
            required_permission: Permission to check ('can_send', 'can_invite', 'can_manage')
            
        Returns:
            Tuple of (has_access, error_message)
        """
        # Get member info
        members = await self.store.sqlite.get_channel_members(channel_id)
        
        member = next(
            (m for m in members
             if m['agent_name'] == agent_name
             and m.get('agent_project_id') == agent_project_id),
            None
        )
        
        if not member:
            return False, f"Agent {agent_name} is not a member of channel {channel_id}"
        
        if not member.get(required_permission, False):
            return False, f"Agent {agent_name} does not have {required_permission} permission"
        
        return True, None
    
    async def prepare_message(self,
                            channel_id: str,
                            sender_name: str,
                            sender_project_id: Optional[str],
                            content: str,
                            metadata: Optional[Dict] = None) -> Dict:
        """
        Prepare a message with validation and enrichment.
        
        This method handles all business logic for message preparation:
        - Content validation
        - Permission checking
        - Mention extraction and validation
        - Metadata enrichment
        
        Args:
            channel_id: Target channel
            sender_name: Sender agent name
            sender_project_id: Sender's project ID
            content: Message content
            metadata: Optional metadata
            
        Returns:
            Prepared message dict with enriched metadata
            
        Raises:
            ValueError: If validation fails
        """
        # Validate content
        if not content or not content.strip():
            raise ValueError("Message content cannot be empty")
        
        if len(content) > 150000:
            raise ValueError("Message content exceeds maximum length")
        
        # Check permissions
        has_access, error = await self.validate_channel_access(
            channel_id, sender_name, sender_project_id, 'can_send'
        )
        if not has_access:
            raise ValueError(error)
        
        # Extract and validate mentions
        mentions = self.extract_mentions(content)
        if mentions:
            validation = await self.validate_mentions_for_channel(channel_id, mentions)
            
            # Enrich metadata with mentions
            if metadata is None:
                metadata = {}
            
            metadata['mentions'] = {
                'valid': validation['valid'],
                'invalid': validation['invalid'],
                'total': len(mentions)
            }
            
            # Log warnings for invalid mentions
            for invalid in validation['invalid']:
                print(f"Warning: {invalid['raw']} is not in channel {channel_id}")
        
        return {
            'channel_id': channel_id,
            'sender_id': sender_name,
            'sender_project_id': sender_project_id,
            'content': content,
            'metadata': metadata
        }
    
    async def validate_invitation(self,
                                 channel_id: str,
                                 inviter_name: str,
                                 inviter_project_id: Optional[str],
                                 invitee_name: str,
                                 invitee_project_id: Optional[str]) -> tuple[bool, Optional[str]]:
        """
        Validate an invitation to a channel.
        
        Checks:
        - Channel type supports invitations (members-only)
        - Inviter has permission to invite
        - Invitee is not already a member
        - Invitee agent exists
        
        Args:
            channel_id: Target channel
            inviter_name: Agent doing the inviting
            inviter_project_id: Inviter's project ID
            invitee_name: Agent being invited
            invitee_project_id: Invitee's project ID
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Get channel info
        channel = await self.store.get_channel(channel_id)
        if not channel:
            return False, f"Channel {channel_id} not found"
        
        # Check channel type supports invitations
        if channel['access_type'] == 'open':
            return False, "Cannot invite to open channels - they allow self-service joining via join_channel"
        
        if channel['access_type'] == 'private':
            return False, "Cannot invite to private channels (DMs have fixed membership)"
        
        # Only members-only channels support invitations
        if channel['access_type'] != 'members':
            return False, f"Channel type '{channel['access_type']}' does not support invitations"
        
        # Check inviter has permission
        has_permission, error = await self.validate_channel_access(
            channel_id=channel_id,
            agent_name=inviter_name,
            agent_project_id=inviter_project_id,
            required_permission='can_invite'
        )
        
        if not has_permission:
            return False, error
        
        # Check invitee is not already a member
        is_member = await self.store.sqlite.is_channel_member(
            channel_id, invitee_name, invitee_project_id
        )
        
        if is_member:
            return False, f"{invitee_name} is already a member of {channel_id}"
        
        # Check invitee agent exists
        invitee = await self.store.get_agent(invitee_name, invitee_project_id)
        if not invitee:
            return False, f"Agent {invitee_name} not found"
        
        return True, None
    
    async def determine_channel_eligibility(self,
                                          agent_name: str,
                                          agent_project_id: Optional[str],
                                          channel: Dict) -> Dict[str, Any]:
        """
        Determine an agent's eligibility for a channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel: Channel information dict
            
        Returns:
            Dict with eligibility information:
            - can_see: Whether agent can see the channel exists
            - can_join: Whether agent can self-join
            - is_member: Whether agent is already a member
            - reason: Explanation of eligibility
        """
        # Check membership
        is_member = await self.store.sqlite.is_channel_member(
            channel['id'], agent_name, agent_project_id
        )
        
        if is_member:
            return {
                'can_see': True,
                'can_join': False,
                'is_member': True,
                'reason': 'already_member'
            }
        
        # Global channels - everyone can see
        if channel['scope'] == 'global':
            return {
                'can_see': True,
                'can_join': channel['access_type'] == 'open',
                'is_member': False,
                'reason': 'global_channel'
            }
        
        # Project channels - check project relationship
        if channel['scope'] == 'project':
            channel_project = channel.get('project_id')
            
            # Same project
            if agent_project_id == channel_project:
                return {
                    'can_see': True,
                    'can_join': channel['access_type'] == 'open',
                    'is_member': False,
                    'reason': 'same_project'
                }
            
            # Global agents can see all project channels
            if agent_project_id is None:
                return {
                    'can_see': True,
                    'can_join': channel['access_type'] == 'open',
                    'is_member': False,
                    'reason': 'global_agent'
                }
            
            # Check if projects are linked
            if agent_project_id and channel_project:
                linked = await self.store.sqlite.check_projects_linked(
                    agent_project_id, channel_project
                )
                if linked:
                    return {
                        'can_see': True,
                        'can_join': channel['access_type'] == 'open',
                        'is_member': False,
                        'reason': 'linked_projects'
                    }
            
            # Different, unlinked project
            return {
                'can_see': False,
                'can_join': False,
                'is_member': False,
                'reason': 'different_project'
            }
        
        # Unknown channel type
        return {
            'can_see': False,
            'can_join': False,
            'is_member': False,
            'reason': 'unknown_channel_type'
        }