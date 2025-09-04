"""
Unified Claude-Slack API that integrates all existing managers.
This is the main entry point for all claude-slack operations.
"""

import os
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path

from .db.message_store import MessageStore
from .channels.manager import ChannelManager
from .notes.manager import NotesManager
from .config import Config
from .models import DMPolicy, Discoverability, DMPermission, AgentInfo
from .events import SimpleEventStream, AutoEventProxy


class ClaudeSlackAPI:
    """
    Unified API that brings together all claude-slack managers.
    
    This class provides a single interface for:
    - Database operations (with Qdrant for semantic search)
    - Channel management
    - Agent management
    - Notes management
    - Configuration management
    """
    
    def __init__(self, 
                 db_path: Optional[str] = None,
                 qdrant_url: Optional[str] = None,
                 qdrant_api_key: Optional[str] = None,
                 qdrant_path: Optional[str] = None,
                 enable_semantic_search: bool = True):
        """
        Initialize the unified API with all managers.
        
        Args:
            db_path: Path to SQLite database (defaults to ~/.claude/claude-slack/data/claude-slack.db)
            qdrant_url: Optional Qdrant server URL for cloud/docker deployments
            qdrant_api_key: Optional API key for Qdrant cloud
            qdrant_path: Optional path to local Qdrant storage
            enable_semantic_search: Whether to enable semantic search features
        """
        # Default database path
        if db_path is None:
            config_dir = os.environ.get('CLAUDE_CONFIG_DIR')
            if config_dir:
                config_dir = Path(config_dir).expanduser().resolve()
            else:
                config_dir = Path.home() / '.claude'
                
            claude_slack_dir = os.environ.get('CLAUDE_SLACK_DIR')
            if claude_slack_dir:
                claude_slack_dir = Path(claude_slack_dir)
            else:
                claude_slack_dir = config_dir / 'claude-slack'
                
            db_path = claude_slack_dir / 'data' / 'claude-slack.db'
        
        self.db_path = db_path
        
        # Build Qdrant config if semantic search is enabled
        qdrant_config = None
        if enable_semantic_search and (qdrant_url or qdrant_path):
            qdrant_config = {
                'qdrant_url': qdrant_url,
                'qdrant_api_key': qdrant_api_key,
                'qdrant_path': qdrant_path
            }
            # Remove None values
            qdrant_config = {k: v for k, v in qdrant_config.items() if v is not None}
        elif enable_semantic_search:
            # Use default local path
            qdrant_config = {
                'qdrant_path': os.path.join(os.path.dirname(db_path), 'qdrant')
            }
        
        # Initialize event streaming first
        self.events = SimpleEventStream()
        
        # Initialize MessageStore as the primary database abstraction
        db = MessageStore(db_path, qdrant_config)
        
        # Wrap database with auto-event proxy for automatic event emission
        self.db = AutoEventProxy(db, self.events)
        
        # Initialize other managers with the proxied database
        self.channels = ChannelManager(self.db)
        self.notes = NotesManager(self.db)  # Now uses MessageStore
        
    @classmethod
    def from_env(cls):
        """
        Create API instance from environment variables.
        
        Uses Config helper to read environment variables.
        """
        config = Config.from_env()
        return cls(
            db_path=config.get('db_path'),
            qdrant_url=config.get('qdrant_url'),
            qdrant_api_key=config.get('qdrant_api_key')
        )
    
    async def initialize(self):
        """
        Initialize all managers and ensure database schema exists.
        """
        await self.db.initialize()
        await self.events.start()
    
    async def close(self):
        """Close all connections."""
        await self.events.stop()
        await self.db.close()
    
    # ============================================================================
    # Message Operations (Core API)
    # ============================================================================
    
    async def send_message(self,
                          channel_id: str,
                          sender_id: str,
                          content: str,
                          sender_project_id: Optional[str] = None,
                          metadata: Optional[Dict] = None,
                          thread_id: Optional[str] = None) -> int:
        """
        Send a message to a channel.
        
        This is the primary method for storing messages and handles:
        - SQLite storage
        - Qdrant vector storage (if enabled)
        - Permission checks
        - Metadata validation
        
        Args:
            channel_id: Target channel
            sender_id: Sender agent name
            content: Message content
            sender_project_id: Sender's project ID
            metadata: Optional nested metadata (stored as-is!)
            thread_id: Optional thread ID
            
        Returns:
            Message ID
        """
        # Normalize channel ID
        channel_id = self.channels.normalize_channel_id(
            channel_id,
            project_id=sender_project_id
        )
        
        # Prepare the message
        prepared = await self.channels.prepare_message(
            channel_id=channel_id,
            sender_name=sender_id,
            sender_project_id=sender_project_id,
            content=content,
            metadata=metadata
        )
        
        return await self.db.send_message(**prepared)
    
    async def search_messages(self,
                             query: Optional[str] = None,
                             project_ids: Optional[List[str]] = None,
                             channel_ids: Optional[List[str]] = None,
                             sender_ids: Optional[List[str]] = None,
                             message_type: Optional[str] = None,
                             metadata_filters: Optional[Dict] = None,
                             min_confidence: Optional[float] = None,
                             since: Optional[Union[datetime, str]] = None,
                             until: Optional[Union[datetime, str]] = None,
                             limit: int = 20,
                             ranking_profile: str = "balanced") -> List[Dict]:
        """
        Search messages with semantic similarity and intelligent ranking.
        
        Supports arbitrary nested metadata filtering with MongoDB-style operators!
        
        Args:
            query: Semantic search query
            project_ids: Project scope filter:
                - None: Search entire database (all projects + global)
                - []: No results (empty search)
                - ["global"]: Search only global channels
                - ["project-1"]: Search only project-1 channels  
                - ["global", "project-1"]: Search global + project-1 channels
            channel_ids: Filter by channels
            sender_ids: Filter by senders
            message_type: Filter by message type from metadata (legacy, use metadata_filters)
            metadata_filters: Arbitrary nested metadata filters with MongoDB-style operators
                Examples:
                    {"type": "reflection"}
                    {"confidence": {"$gte": 0.8}}
                    {"breadcrumbs.decisions": {"$contains": "jwt"}}
                    {"breadcrumbs.metrics.test_coverage": {"$gte": 0.9}}
                    {"outcome": "success", "complexity": {"$lte": 5}}
            min_confidence: Minimum confidence threshold
            since: Only return messages after this timestamp (datetime or ISO string)
            until: Only return messages before this timestamp (datetime or ISO string)
            limit: Maximum results
            ranking_profile: Scoring profile for semantic search results:
                - 'recent': Prioritize recent messages (good for debugging, current status)
                - 'quality': Prioritize high-confidence messages (good for proven solutions)
                - 'balanced': Equal weight to all factors (default)
                - 'similarity': Pure semantic match (good for exact topic match)
                Or pass a custom RankingProfile instance
            
        Returns:
            List of messages with search scores
        """
        # Handle legacy message_type parameter
        if message_type and not metadata_filters:
            metadata_filters = {"type": message_type}
        elif message_type and metadata_filters and "type" not in metadata_filters:
            metadata_filters["type"] = message_type
        
        # Parse date strings if needed
        if since and isinstance(since, str):
            since = datetime.fromisoformat(since)
        if until and isinstance(until, str):
            until = datetime.fromisoformat(until)
        
        # Use MessageStore's unified search
        return await self.db.search_messages(
            query=query,
            project_ids=project_ids,
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            metadata_filters=metadata_filters,
            min_confidence=min_confidence,
            since=since,
            until=until,
            limit=limit,
            ranking_profile=ranking_profile
        )
    
    async def search_agent_messages(self,
                                   agent_name: str,
                                   agent_project_id: Optional[str] = None,
                                   query: Optional[str] = None,
                                   channel_ids: Optional[List[str]] = None,
                                   sender_ids: Optional[List[str]] = None,
                                   message_type: Optional[str] = None,
                                   metadata_filters: Optional[Dict] = None,
                                   min_confidence: Optional[float] = None,
                                   since: Optional[Union[datetime, str]] = None,
                                   until: Optional[Union[datetime, str]] = None,
                                   limit: int = 20,
                                   ranking_profile: str = "balanced") -> List[Dict]:
        """
        Search messages with agent permission checks.
        
        Only searches messages in channels the agent has access to.
        Supports both semantic search (with query) and filter-based search.
        
        Args:
            agent_name: Agent performing the search (for permissions)
            agent_project_id: Agent's project ID
            query: Semantic search query (optional)
            channel_ids: Filter by specific channels (will be intersected with accessible channels)
            sender_ids: Filter by senders
            message_type: Filter by message type from metadata (legacy, use metadata_filters)
            metadata_filters: Arbitrary nested metadata filters with MongoDB-style operators
            min_confidence: Minimum confidence threshold
            since: Only return messages after this timestamp (datetime or ISO string)
            until: Only return messages before this timestamp (datetime or ISO string)
            limit: Maximum results
            ranking_profile: Scoring profile for semantic search results:
                - 'recent': Prioritize recent messages (good for debugging, current status)
                - 'quality': Prioritize high-confidence messages (good for proven solutions)
                - 'balanced': Equal weight to all factors (default)
                - 'similarity': Pure semantic match (good for exact topic match)
                Or pass a custom RankingProfile instance
            
        Returns:
            List of messages the agent has permission to see, with search scores if semantic
        """
        # Handle legacy message_type parameter
        if message_type and not metadata_filters:
            metadata_filters = {"type": message_type}
        elif message_type and metadata_filters and "type" not in metadata_filters:
            metadata_filters["type"] = message_type
        
        # Parse date strings if needed
        if since and isinstance(since, str):
            since = datetime.fromisoformat(since)
        if until and isinstance(until, str):
            until = datetime.fromisoformat(until)
        
        # Use MessageStore's agent-scoped search
        return await self.db.search_agent_messages(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            query=query,
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            metadata_filters=metadata_filters,
            min_confidence=min_confidence,
            since=since,
            until=until,
            limit=limit,
            ranking_profile=ranking_profile
        )
    
    async def get_message(self, message_id: int) -> Optional[Dict]:
        """Get a single message by ID."""
        return await self.db.get_message(message_id)
    
    async def get_agent_messages(self,
                                agent_name: str,
                                agent_project_id: Optional[str] = None,
                                channel_id: Optional[str] = None,
                                limit: int = 100,
                                since: Optional[str] = None) -> List[Dict]:
        """
        Get messages visible to a specific agent (with permission checks).
        
        This method enforces permissions - only returns messages from
        channels the agent has access to.
        
        Args:
            agent_name: Agent requesting messages
            agent_project_id: Agent's project ID
            channel_id: Optional filter by specific channel
            limit: Maximum messages
            since: ISO timestamp to get messages after
            
        Returns:
            List of message dictionaries visible to the agent
        """
        # Convert since string to datetime if provided
        since_dt = None
        if since:
            from datetime import datetime
            since_dt = datetime.fromisoformat(since)
        
        return await self.db.get_agent_messages(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            channel_id=channel_id,
            limit=limit,
            since=since_dt
        )
    
    async def get_messages(self,
                          channel_ids: Optional[List[str]] = None,
                          sender_ids: Optional[List[str]] = None,
                          message_ids: Optional[List[int]] = None,
                          limit: int = 100,
                          since: Optional[str] = None) -> List[Dict]:
        """
        Get messages without permission checks (administrative access).
        
        This method bypasses agent permissions for system operations.
        Use with caution - no permission enforcement.
        
        Args:
            channel_ids: Optional list of channel IDs to filter
            sender_ids: Optional list of sender IDs to filter  
            message_ids: Optional list of specific message IDs
            limit: Maximum messages
            since: ISO timestamp to get messages after
            
        Returns:
            List of message dictionaries (no permission filtering)
        """
        # Convert since string to datetime if provided
        since_dt = None
        if since:
            from datetime import datetime
            since_dt = datetime.fromisoformat(since)
        
        return await self.db.get_messages(
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            message_ids=message_ids,
            limit=limit,
            since=since_dt
        )
    
    # ============================================================================
    # Channel Operations
    # ============================================================================
    
    async def create_channel(self,
                           name: str,
                           scope: str = 'global',
                           access_type: str = 'open',
                           project_id: Optional[str] = None,
                           description: Optional[str] = None,
                           created_by: Optional[str] = None,
                           created_by_project_id: Optional[str] = None,
                           is_default: bool = False) -> str:
        """
        Create a new channel.
        
        Args:
            name: Channel name
            scope: 'global' or 'project'
            access_type: 'open', 'members', or 'private'
            project_id: Project ID for project channels
            description: Channel description
            created_by: Creator agent name
            created_by_project_id: Creator's project ID
            is_default: Auto-subscribe new agents
            
        Returns:
            Channel ID
        """
        name_validation, msg = self.channels.validate_channel_name(name)
        
        if not name_validation:
            raise ValueError(msg)
        
        if scope == 'project' and not project_id:
            raise ValueError('Project ID required for project channels')
        
        # Strip project_id if global scope
        if scope == 'global':
            project_id = None
            
        if not description:
            description = f"{scope.title()} {name} channel"
            
        channel_id = self.channels.get_scoped_channel_id(name, scope, project_id)
        
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
        
        return created_id
    
    async def join_channel(self,
                          agent_name: str,
                          agent_project_id: Optional[str],
                          channel_id: str) -> bool:
        """
        Join a channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel_id: Channel to join
            
        Returns:
            True if successfully joined
        """
        # Debug logging
        self.logger.debug(f"join_channel called with channel_id='{channel_id}', agent_project_id='{agent_project_id}'")
        
        # Normalize channel ID (use agent's project as context)
        normalized_id = self.channels.normalize_channel_id(
            channel_id,
            project_id=agent_project_id
        )
        self.logger.debug(f"After normalization: '{normalized_id}'")
        channel_id = normalized_id
          
        # Get channel info
        channel = await self.db.get_channel(channel_id)
        self.logger.debug(f"get_channel returned: {channel}")
        
        # Check if channel exists
        if not channel:
            self.logger.warning(f"Channel not found: {channel_id}")
            return False
        
        # Verify eligibility
        access = await self.channels.determine_channel_eligibility(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            channel=channel
            )
        
        if not access['can_join']:
            return False
        
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
        
        return True
    
    async def leave_channel(self,
                           agent_name: str,
                           agent_project_id: Optional[str],
                           channel_id: str) -> bool:
        """
        Leave a channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            channel_id: Channel to leave
            
        Returns:
            True if successfully left
        """
        
        # Normalize channel ID
        channel_id = self.channels.normalize_channel_id(
            channel_id,
            project_id=agent_project_id
        )
            
        # Get channel info
        channel = await self.db.get_channel(channel_id)
        
        # Verify eligibility
        valid, reason = await self.channels.validate_channel_access(
            channel_id=channel_id,
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            required_permission='can_leave'
            )
        
        if not valid:
            return False
        
        # Remove membership
        await self.db.remove_channel_member(
            channel_id=channel_id,
            agent_name=agent_name,
            agent_project_id=agent_project_id
        )
        
        return True
    
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
            inviter_name: Agent doing the inviting (must be a member with can_invite)
            inviter_project_id: Inviter's project ID
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If invitation is invalid
        """
        
        # Normalize channel ID
        channel_id = self.channels.normalize_channel_id(
            channel_id,
            project_id=inviter_project_id
        )
            
        # Validate the invitation
        is_valid, error = await self.channels.validate_invitation(
            channel_id=channel_id,
            inviter_name=inviter_name,
            inviter_project_id=inviter_project_id,
            invitee_name=invitee_name,
            invitee_project_id=invitee_project_id
        )
        
        if not is_valid:
            raise ValueError(error)
        
        # Add invitee as member
        await self.db.add_channel_member(
            channel_id=channel_id,
            agent_name=invitee_name,
            agent_project_id=invitee_project_id,
            invited_by=inviter_name,
            source='manual',
            can_leave=True,
            can_send=True,
            can_invite=False,  # New members can't invite by default in members-only channels
            can_manage=False
        )
        
        return True
    
    async def list_channels(self,
                          agent_name: Optional[str] = None,
                          project_id: Optional[str] = None,
                          scope_filter: str = 'all',
                          include_archived: bool = False,
                          is_default: bool = None) -> List[Dict]:
        """
        List available channels with optional permission information (if agent_name provided).
        
        Args:
            agent_name: Agent to check membership for (exclude for all channels)
            agent_project_id: Agent's project ID
            scope_filter: 'all', 'global', or 'project'
            include_archived: Include archived channels
            
        Returns:
            List of channel dictionaries
        """
        result = []
        
        all_channels = await self.db.get_channels_by_scope(scope=scope_filter, project_id=project_id, is_default=is_default)
        
        # Add agent access detail, if provided
        if agent_name:
            for channel in all_channels:
                agent_access = await self.channels.determine_channel_eligibility(agent_name, project_id, channel)
                result.append(channel | agent_access)
        else:
            result = all_channels
            
        return result
    
    async def get_channel(self, 
                         channel_id: str,
                         agent_name: Optional[str] = None,
                         agent_project_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get detailed information about a channel.
        
        Args:
            channel_id: Channel ID to retrieve
            agent_name: Optional agent requesting (for access info)
            agent_project_id: Optional agent's project ID
            
        Returns:
            Channel dictionary with all metadata, or None if not found.
            If agent_name provided, includes access information.
        """
        
        # Normalize channel ID
        channel_id = self.channels.normalize_channel_id(
            channel_id,
            project_id=agent_project_id
        )
        
        channel = await self.db.get_channel(channel_id)
        
        if not channel:
            return None
        
        # If agent specified, add their access/eligibility info
        if agent_name:
            eligibility = await self.channels.determine_channel_eligibility(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                channel=channel
            )
            channel.update(eligibility)
            
            # Also check if they have special permissions
            if eligibility['is_member']:
                members = await self.db.get_channel_members(channel_id)
                for member in members:
                    if (member['agent_name'] == agent_name and 
                        member.get('agent_project_id') == agent_project_id):
                        channel['member_permissions'] = {
                            'can_send': member.get('can_send', False),
                            'can_invite': member.get('can_invite', False),
                            'can_manage': member.get('can_manage', False),
                            'can_leave': member.get('can_leave', True),
                            'joined_at': member.get('joined_at'),
                            'invited_by': member.get('invited_by')
                        }
                        break
        
        return channel
    
    async def list_channel_members(self, channel_id: str) -> List[Dict[str, Any]]:
        """
        Get all members of a channel.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            List of member dictionaries
        """
        return await self.db.get_channel_members(channel_id)

    def get_scoped_channel_id(self, name: str, scope: str, project_id: Optional[str] = None) -> str:
        """
        Generate the full channel ID with scope prefix.
        
        Helper method to construct channel IDs consistently.
        
        Args:
            name: Channel name without prefix
            scope: 'global' or 'project'
            project_id: Project ID for project channels
            
        Returns:
            Full channel ID (e.g., "global:general" or "proj_abc123:dev")
        """
        return self.channels.get_scoped_channel_id(name, scope, project_id)
    
    # ============================================================================
    # Agent Operations
    # ============================================================================
    
    async def register_agent(self,
                            name: str,
                            project_id: Optional[str] = None,
                            description: Optional[str] = None,
                            dm_policy: str = 'open',
                            discoverable: str = 'public',
                            status: str = 'online',
                            metadata: Optional[Dict] = None,
                            auto_join_defaults: bool = True) -> int:
        """
        Register an agent.
        
        Args:
            name: Agent name
            project_id: Agent's project ID
            description: Agent description
            dm_policy: DM policy ('open', 'restricted', 'closed')
            discoverable: Discoverability ('public', 'project', 'private')
            status: Agent status
            metadata: Optional metadata
            auto_join_defaults: Auto-join default channels after registration
            
        Returns:
            Number of default channels joined (0 if auto_join_defaults is False)
        """
        # Validate DM policy
        if dm_policy not in [p.value for p in DMPolicy]:
            raise ValueError("Invalid DM policy")
        
        # Validate discoverability
        if discoverable not in [d.value for d in Discoverability]:
            raise ValueError("Invalid discoverability")
        
        # Register the agent in the database with all fields
        await self.db.register_agent(
            name=name,
            project_id=project_id,
            description=description,
            dm_policy=dm_policy,
            discoverable=discoverable,
            status=status,
            metadata=metadata
        )
        
        # Auto-join default channels if requested
        if auto_join_defaults:
            return await self.apply_default_channels(name, project_id)
        
        return 0
    
    async def get_messagable_agents(self,
                                    agent_name: str,
                                    agent_project_id: Optional[str],
                                    ) -> List[AgentInfo]:
        """
        List agents that an agent can message.
        
        Args:
            agent_name: Agent requesting the list
            agent_project_id: Agent's project ID
        
        Returns:
            List of AgentInfo objects for messageable agents
        """        
        # Delegate to DatabaseManagerV3's get_discoverable_agents
        agents = await self.db.get_discoverable_agents(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
        )
        
        return [
            AgentInfo(
                    name=agent['name'],
                    project_id=agent['project_id'],
                    description=agent.get('description'),
                    status=agent.get('status', 'offline'),
                    dm_policy=agent.get('dm_policy', 'open'),
                    discoverable=agent.get('discoverable', 'public'),
                    project_name=agent.get('project_name'),
                    dm_availability=agent.get('dm_availability'),
                    has_existing_dm=agent.get('has_existing_dm', False)
                )
                for agent in agents
            ]
        
    
    async def list_agents(self,
                         scope: str = 'all',
                         project_id: Optional[str] = None,
                         include_descriptions: bool = True) -> List[Dict]:
        """
        List agents filtered by scope.
        
        Args:
            scope: 'all', 'global', or 'project'
            project_id: Required when scope='project'
            include_descriptions: Include agent descriptions
            
        Returns:
            List of agent dictionaries
        """
        # Validate scope
        if scope not in ['all', 'global', 'project']:
            raise ValueError("scope must be 'all', 'global', or 'project'")
        
        # Check project_id requirement
        if scope == 'project' and not project_id:
            raise ValueError("project_id is required when scope='project'")
        
        # Get agents by scope
        agents = await self.db.get_agents_by_scope(
            scope=scope,
            project_id=project_id
        )
        
        # Remove descriptions if not wanted
        if not include_descriptions:
            for agent in agents:
                agent.pop('description', None)
        
        return agents
    
    # ============================================================================
    # Notes Operations
    # ============================================================================
    
    async def write_note(self,
                        agent_name: str,
                        content: str,
                        agent_project_id: Optional[str] = None,
                        session_context: Optional[str] = None,
                        tags: Optional[List[str]] = None,
                        metadata: Optional[Dict] = None) -> int:
        """
        Write a note to agent's private notes channel.
        
        This is a convenience method that ensures the notes channel exists
        and properly formats the note metadata.
        
        Args:
            agent_name: Agent name
            content: Note content
            agent_project_id: Optional agent's project ID
            session_context: Optional session context or description
            tags: Optional tags for categorization
            metadata: Additional metadata to store with the note
            
        Returns:
            Message ID of the created note
        """
        return await self.notes.write_note(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            content=content,
            session_context=session_context,
            tags=tags,
            metadata=metadata
        )
    
    async def search_agent_notes(self,
                                agent_name: str,
                                agent_project_id: Optional[str] = None,
                                query: Optional[str] = None,
                                tags: Optional[List[str]] = None,
                                since: Optional[Union[datetime, str]] = None,
                                until: Optional[Union[datetime, str]] = None,
                                limit: int = 50) -> List[Dict]:
        """
        Search agent's notes with optional semantic search.
        
        If a query is provided and Qdrant is available, this will use
        semantic search to find relevant notes. Otherwise, it performs
        a filter-based search.
        
        Args:
            agent_name: Agent name
            agent_project_id: Optional agent's project ID
            query: Optional search query (triggers semantic search if available)
            tags: Optional tags to filter by
            since: Only return notes after this timestamp (datetime or ISO string)
            until: Only return notes before this timestamp (datetime or ISO string)
            limit: Maximum results
            
        Returns:
            List of note dictionaries with content, tags, timestamp, and search scores
        """
        return await self.notes.search_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            query=query,
            tags=tags,
            since=since,
            until=until,
            limit=limit
        )
    
    async def search_notes(self,
                          query: Optional[str] = None,
                          project_ids: Optional[List[str]] = None,
                          agent_names: Optional[List[str]] = None,
                          channel_ids: Optional[List[str]] = None,
                          tags: Optional[List[str]] = None,
                          metadata_filters: Optional[Dict] = None,
                          min_confidence: Optional[float] = None,
                          limit: int = 50,
                          ranking_profile: str = "balanced") -> List[Dict]:
        """
        Search all notes with semantic similarity and intelligent ranking.
        
        This is the general administrative search for notes, similar to search_messages.
        Supports arbitrary nested metadata filtering with MongoDB-style operators!
        
        Args:
            query: Semantic search query
            project_ids: Project scope filter:
                - None: Search entire database (all projects + global)
                - []: No results (empty search)
                - ["global"]: Search only global channels
                - ["project-1"]: Search only project-1 channels
                - ["global", "project-1"]: Search global + project-1 channels
            agent_names: Filter by specific agents' notes
            channel_ids: Filter by specific notes channels
            tags: Filter by tags (uses $all operator internally)
            metadata_filters: Arbitrary nested metadata filters with MongoDB-style operators
                Examples:
                    {"session_id": "abc-123"}
                    {"confidence": {"$gte": 0.8}}
                    {"breadcrumbs.decisions": {"$contains": "jwt"}}
                    {"breadcrumbs.metrics.test_coverage": {"$gte": 0.9}}
                    {"tags": {"$contains": "solution"}}
                    {"$or": [{"tags": {"$contains": "bug"}}, {"tags": {"$contains": "issue"}}]}
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            ranking_profile: Scoring profile for semantic search results
            
        Returns:
            List of notes with search scores
        """
        # Build channel filter if agent_names provided
        if agent_names and not channel_ids:
            channel_ids = []
            for agent in agent_names:
                # Notes channels follow the pattern: notes-{agent_name}
                channel_ids.append(f"notes-{agent}")
        
        # Handle tags filter - convert to metadata filter
        if tags:
            tag_filter = {"tags": {"$all": tags}}
            if metadata_filters:
                # Combine with existing filters using $and
                metadata_filters = {
                    "$and": [metadata_filters, tag_filter]
                }
            else:
                metadata_filters = tag_filter
        
        # Add type filter to only get notes
        type_filter = {"type": "note"}
        if metadata_filters:
            metadata_filters = {
                "$and": [metadata_filters, type_filter]
            }
        else:
            metadata_filters = type_filter
        
        # Use the message search infrastructure since notes are stored as messages
        return await self.db.search_messages(
            query=query,
            project_ids=project_ids,
            channel_ids=channel_ids,
            sender_ids=agent_names,  # For notes, sender = agent
            metadata_filters=metadata_filters,
            min_confidence=min_confidence,
            since=since,
            until=until,
            limit=limit,
            ranking_profile=ranking_profile
        )
    
    async def get_recent_notes(self,
                              agent_name: str,
                              agent_project_id: Optional[str] = None,
                              limit: int = 20,
                              session_id: Optional[str] = None) -> List[Dict]:
        """
        Get recent notes for an agent.
        
        Args:
            agent_name: Agent name
            agent_project_id: Optional agent's project ID
            limit: Maximum notes to return
            session_id: Optional filter by session context
            
        Returns:
            List of recent notes ordered by timestamp
        """
        return await self.notes.get_recent_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            limit=limit,
            session_id=session_id
        )
    
    async def peek_agent_notes(self,
                              target_agent_name: str,
                              target_agent_project_id: Optional[str] = None,
                              requester_agent_name: str = None,
                              requester_project_id: Optional[str] = None,
                              query: Optional[str] = None,
                              limit: int = 20) -> List[Dict]:
        """
        Peek at another agent's notes (for debugging or administrative purposes).
        
        Note: This bypasses privacy and should only be used for:
        - System administrators
        - Debugging with permission
        - Cross-agent learning scenarios
        
        Args:
            target_agent_name: Agent whose notes to peek at
            target_agent_project_id: Target agent's project ID
            requester_agent_name: Agent making the request (for audit)
            requester_project_id: Requester's project ID
            query: Optional search query
            limit: Maximum number of notes
            
        Returns:
            List of notes from target agent
        """
        return await self.notes.peek_agent_notes(
            target_agent_name=target_agent_name,
            target_project_id=target_agent_project_id,
            requester_name=requester_agent_name,
            requester_project_id=requester_project_id,
            query=query,
            limit=limit
        )
    
    # ============================================================================
    # Direct Message Operations
    # ============================================================================
    
    async def send_direct_message(self,
                                 sender_name: str,
                                 recipient_name: str,
                                 content: str,
                                 sender_project_id: Optional[str] = None,
                                 recipient_project_id: Optional[str] = None,
                                 metadata: Optional[Dict] = None) -> int:
        """
        Send a direct message to another agent.
        
        Args:
            sender_name: Sender agent name
            recipient_name: Recipient agent name
            content: Message content
            sender_project_id: Optional sender's project ID
            recipient_project_id: Optional recipient's project ID
            metadata: Optional metadata
            
        Returns:
            Message ID
        """
        
        # Create or get DM channel
        channel_id = await self.db.create_or_get_dm_channel(
            sender_name, sender_project_id,
            recipient_name, recipient_project_id
        )
        
        # Send message
        return await self.send_message(
            channel_id=channel_id,
            sender_id=sender_name,
            sender_project_id=sender_project_id,
            content=content,
            metadata=metadata
        )
    
    # ============================================================================
    # Default Channels & Auto-join
    # ============================================================================
    
    async def apply_default_channels(self, 
                                    agent_name: str,
                                    agent_project_id: Optional[str] = None) -> int:
        """
        Auto-join agent to all default channels they can access.
        
        Args:
            agent_name: Agent to join to default channels
            agent_project_id: Agent's project ID
            
        Returns:
            Number of channels joined
        """
        # Get all default channels
        channels = await self.list_channels(
            agent_name=agent_name,
            project_id=agent_project_id,
            is_default=True
        )
        
        joined = 0
        for channel in channels:
            # Check if agent can join and is not already a member
            if channel.get('can_join', False) and not channel.get('is_member', False):
                try:
                    success = await self.join_channel(
                        agent_name=agent_name,
                        agent_project_id=agent_project_id,
                        channel_id=channel['id']
                    )
                    if success:
                        joined += 1
                except Exception as e:
                    # Log but don't fail if one channel fails
                    print(f"Failed to join {channel['id']}: {e}")
        
        return joined
    
    # ============================================================================
    # Event Streaming API
    # ============================================================================
    
    async def subscribe_events(
        self,
        client_id: str,
        topics: Optional[List[str]] = None,
        replay_recent: bool = True
    ):
        """
        Subscribe to event stream.
        
        Args:
            client_id: Unique client identifier
            topics: List of topics to subscribe to (None = all)
            replay_recent: Whether to replay recent events on connect
            
        Yields:
            Event objects as they occur
        """
        async for event in self.events.subscribe(client_id, topics, replay_recent):
            yield event
    
    async def subscribe_sse(
        self,
        client_id: str,
        topics: Optional[List[str]] = None,
        last_event_id: Optional[str] = None
    ):
        """
        Subscribe to events with SSE formatting.
        
        Args:
            client_id: Unique client identifier  
            topics: List of topics to subscribe to
            last_event_id: Last event ID for reconnection
            
        Yields:
            SSE-formatted strings ready for streaming
        """
        async for sse_data in self.events.subscribe_sse(client_id, topics, last_event_id):
            yield sse_data
    
    async def unsubscribe_events(self, client_id: str):
        """
        Unsubscribe a client from events.
        
        Args:
            client_id: Client to unsubscribe
        """
        await self.events.unsubscribe(client_id)
    
    def get_event_stats(self) -> Dict[str, Any]:
        """
        Get event streaming statistics.
        
        Returns:
            Dictionary with streaming stats
        """
        return self.events.get_stats()
    
    # ============================================================================
    # Magic Method: Pass-through to MessageStore
    # ============================================================================
    
    def __getattr__(self, name):
        """
        Proxy missing methods to the MessageStore.
        
        This creates a clean delegation chain:
        ClaudeSlackAPI -> MessageStore -> SQLiteStore
        
        The MessageStore has its own __getattr__ that forwards to SQLiteStore,
        so we only need to check self.db here.
        
        Examples of proxied methods:
            api.add_channel_member(...)      # API -> MessageStore -> SQLiteStore
            api.is_channel_member(...)       # API -> MessageStore -> SQLiteStore
            api.create_or_get_dm_channel(...) # API -> MessageStore -> SQLiteStore
            api.register_project(...)        # API -> MessageStore -> SQLiteStore
            api.record_tool_call(...)        # API -> MessageStore -> SQLiteStore
        """
        # Check if MessageStore has the requested method (or can proxy it)
        if hasattr(self.db, name):
            return getattr(self.db, name)
        
        # If not found, raise AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")