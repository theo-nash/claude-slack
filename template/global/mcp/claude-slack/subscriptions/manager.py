#!/usr/bin/env python3
"""
SubscriptionManager: Simplified subscription management for open channels

In the v3 architecture, subscriptions are ONLY for open channels where agents
can voluntarily choose what to follow. For other channel types:
- Members channels: Membership determines access (no subscription needed)
- Private channels: Fixed membership (no subscription concept)
- DM channels: Participants only (no subscription concept)
- Notes channels: Single member (no subscription concept)

This manager handles:
1. Voluntary subscriptions to open channels
2. Frontmatter syncing for agent preferences
3. Default channel patterns for new agents
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Set
from pathlib import Path

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from db.manager import DatabaseManager
from channels.manager import ChannelManager
from db.initialization import DatabaseInitializer, ensure_db_initialized
from frontmatter.parser import FrontmatterParser
from frontmatter.updater import FrontmatterUpdater


class SubscriptionManager(DatabaseInitializer):
    """Manages voluntary subscriptions to open channels"""
    
    def __init__(self, db_path: str):
        """
        Initialize SubscriptionManager
        
        Args:
            db_path: Path to the database
        """
        # Initialize parent class (DatabaseInitializer)
        super().__init__()
        
        self.db_path = db_path
        self.db = DatabaseManager(db_path)
        self.db_manager = self.db  # Required for DatabaseInitializer mixin
        self.channel_manager = ChannelManager(db_path)
        self.logger = logging.getLogger(__name__)
    
    @ensure_db_initialized
    async def subscribe_to_channel(self,
                                  agent_name: str,
                                  agent_project_id: Optional[str],
                                  channel_id: str) -> bool:
        """
        Subscribe an agent to an open channel.
        
        This only works for open channels. For other channel types:
        - Members/private: Use ChannelManagerV3.add_member()
        - DM: Automatically handled when DM is created
        - Notes: Automatically handled when notes channel is created
        
        Args:
            agent_name: Agent to subscribe
            agent_project_id: Agent's project ID
            channel_id: Channel to subscribe to
            
        Returns:
            True if subscription successful, False otherwise
        """
        # Get channel info
        channel = await self.channel_manager.get_channel(channel_id)
        if not channel:
            self.logger.error(f"Channel {channel_id} does not exist")
            return False
        
        # Only allow subscriptions to open channels
        if channel.access_type != 'open':
            self.logger.error(
                f"Cannot subscribe to {channel.access_type} channel {channel_id}. "
                f"Use add_member() for members/private channels."
            )
            return False
        
        # Subscribe the agent
        try:
            await self.db.subscribe_to_channel(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                channel_id=channel_id
            )
            self.logger.info(f"Subscribed {agent_name} to {channel_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to subscribe {agent_name} to {channel_id}: {e}")
            return False
    
    @ensure_db_initialized
    async def unsubscribe_from_channel(self,
                                      agent_name: str,
                                      agent_project_id: Optional[str],
                                      channel_id: str) -> bool:
        """
        Unsubscribe an agent from an open channel.
        
        Args:
            agent_name: Agent to unsubscribe
            agent_project_id: Agent's project ID
            channel_id: Channel to unsubscribe from
            
        Returns:
            True if unsubscription successful, False otherwise
        """
        # Get channel info
        channel = await self.channel_manager.get_channel(channel_id)
        if not channel:
            self.logger.error(f"Channel {channel_id} does not exist")
            return False
        
        # Only allow unsubscribing from open channels
        if channel.access_type != 'open':
            self.logger.error(
                f"Cannot unsubscribe from {channel.access_type} channel {channel_id}. "
                f"Use remove_member() for members/private channels."
            )
            return False
        
        # Unsubscribe the agent
        try:
            await self.db.unsubscribe_from_channel(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                channel_id=channel_id
            )
            self.logger.info(f"Unsubscribed {agent_name} from {channel_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe {agent_name} from {channel_id}: {e}")
            return False
    
    @ensure_db_initialized
    async def get_agent_channels(self,
                                agent_name: str,
                                agent_project_id: Optional[str]) -> Dict[str, List[Dict]]:
        """
        Get all channels accessible to an agent.
        
        This includes:
        - Open channels they're subscribed to
        - Members/private channels they're members of
        - DM channels they're participants in
        - Their notes channel
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            
        Returns:
            Dict with 'subscribed', 'member', 'dm', and 'notes' lists
        """
        # Use the channel manager to get all accessible channels
        all_channels = await self.channel_manager.list_channels_for_agent(
            agent_name, agent_project_id
        )
        
        # Categorize channels
        result = {
            'subscribed': [],  # Open channels (voluntary)
            'member': [],      # Members/private channels (mandatory)
            'dm': [],          # Direct message channels
            'notes': []        # Notes channels
        }
        
        for channel in all_channels:
            channel_id = channel['id']
            
            # Categorize by channel type and access
            if channel_id.startswith('dm:'):
                result['dm'].append(channel)
            elif channel_id.startswith('notes:'):
                result['notes'].append(channel)
            elif channel.get('access_type') == 'open':
                result['subscribed'].append(channel)
            else:  # members or private
                result['member'].append(channel)
        
        return result
    
    @ensure_db_initialized
    async def get_subscribed_open_channels(self,
                                          agent_name: str,
                                          agent_project_id: Optional[str]) -> List[str]:
        """
        Get only the open channels an agent is subscribed to.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            
        Returns:
            List of channel IDs for open channels the agent is subscribed to
        """
        channels = await self.get_agent_channels(agent_name, agent_project_id)
        return [ch['id'] for ch in channels.get('subscribed', [])]
    
    @ensure_db_initialized
    async def apply_default_subscriptions(self,
                                         agent_name: str,
                                         agent_project_id: Optional[str],
                                         default_channels: Optional[List[str]] = None) -> List[str]:
        """
        Apply default subscriptions for a new agent.
        
        Only subscribes to open channels that exist.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            default_channels: List of channel IDs to subscribe to.
                            If None, uses standard defaults.
            
        Returns:
            List of channel IDs successfully subscribed to
        """
        if default_channels is None:
            # Standard defaults
            default_channels = []
            
            # Global defaults
            if agent_project_id is None:
                default_channels = [
                    'global:general',
                    'global:announcements',
                    'global:random'
                ]
            else:
                # Project agent defaults
                # Include both global and project channels
                default_channels = [
                    'global:announcements',
                    f'project:{agent_project_id}:general',
                    f'project:{agent_project_id}:dev'
                ]
        
        subscribed = []
        for channel_id in default_channels:
            # Check if channel exists and is open
            channel = await self.channel_manager.get_channel(channel_id)
            if channel and channel.access_type == 'open':
                success = await self.subscribe_to_channel(
                    agent_name, agent_project_id, channel_id
                )
                if success:
                    subscribed.append(channel_id)
                    self.logger.debug(f"Applied default subscription: {channel_id}")
            else:
                self.logger.debug(f"Skipping non-existent or non-open channel: {channel_id}")
        
        self.logger.info(f"Applied {len(subscribed)} default subscriptions for {agent_name}")
        return subscribed
    
    @ensure_db_initialized
    async def sync_from_frontmatter(self,
                                   agent_name: str,
                                   agent_project_id: Optional[str],
                                   agent_file_path: str) -> Dict[str, List[str]]:
        """
        Sync agent's subscriptions from their frontmatter file using FrontmatterParser.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            agent_file_path: Path to agent's markdown file
            
        Returns:
            Dict with 'added' and 'removed' channel lists
        """
        result = {'added': [], 'removed': []}
        
        if not os.path.exists(agent_file_path):
            self.logger.warning(f"Agent file not found: {agent_file_path}")
            return result
        
        try:
            # Parse frontmatter using FrontmatterParser
            agent_data = FrontmatterParser.parse_file(agent_file_path)
            channels_config = agent_data.get('channels', {})
                        
            # Build list of desired channel IDs
            desired_channels = set()
            
            # Add global channels
            for ch in channels_config.get('global', []):
                # Channel names from frontmatter don't have scope prefix
                desired_channels.add(f"global:{ch}")
            
            # Add project channels (only if agent has project context)
            if agent_project_id:
                for ch in channels_config.get('project', []):
                    # Add project scope
                    project_short = agent_project_id[:8] if len(agent_project_id) > 8 else agent_project_id
                    desired_channels.add(f"proj_{project_short}:{ch}")
            
            # Get current subscriptions (open channels only)
            current_channels = set(await self.get_subscribed_open_channels(
                agent_name, agent_project_id
            ))
            
            # Calculate changes
            to_add = desired_channels - current_channels
            to_remove = current_channels - desired_channels
            
            # Apply additions
            for channel_id in to_add:
                success = await self.subscribe_to_channel(
                    agent_name, agent_project_id, channel_id
                )
                if success:
                    result['added'].append(channel_id)
            
            # Apply removals  
            for channel_id in to_remove:
                success = await self.unsubscribe_from_channel(
                    agent_name, agent_project_id, channel_id
                )
                if success:
                    result['removed'].append(channel_id)
            
            self.logger.info(
                f"Frontmatter sync for {agent_name}: "
                f"added {len(result['added'])}, removed {len(result['removed'])} subscriptions"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to sync from frontmatter: {e}")
        
        return result
    
    @ensure_db_initialized
    async def update_frontmatter(self,
                                agent_name: str,
                                agent_project_id: Optional[str],
                                agent_project_dir: str) -> bool:
        """
        Update agent's frontmatter file with current subscriptions using FrontmatterUpdater.
        
        Only updates open channel subscriptions.
        Does NOT include members/private/dm channels (those are determined by membership).
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            agent_project_dir: Directory containing agent files (project or global)
            
        Returns:
            True if update successful
        """
        try:
            # Get current open channel subscriptions
            subscribed_channels = await self.get_subscribed_open_channels(
                agent_name, agent_project_id
            )
            
            # Organize by scope for FrontmatterUpdater
            channels_by_scope = {'global': [], 'project': []}
            
            for ch_id in subscribed_channels:
                if ch_id.startswith('global:'):
                    # Remove 'global:' prefix for cleaner frontmatter
                    channel_name = ch_id[7:]
                    channels_by_scope['global'].append(channel_name)
                elif ch_id.startswith('proj_'):
                    # Extract channel name from project channel ID
                    # Format: proj_{short_id}:{channel_name}
                    parts = ch_id.split(':', 1)
                    if len(parts) == 2:
                        channel_name = parts[1]
                        channels_by_scope['project'].append(channel_name)
            
            # Use FrontmatterUpdater to bulk update
            success = await FrontmatterUpdater.bulk_update_subscriptions(
                agent_name=agent_name,
                subscribe_to=channels_by_scope,  # Set exact subscriptions
                unsubscribe_from={'global': [], 'project': []},  # No removals in this mode
                claude_dir=agent_project_dir
            )
            
            if success:
                self.logger.info(
                    f"Updated frontmatter for {agent_name}: "
                    f"{len(channels_by_scope['global'])} global, "
                    f"{len(channels_by_scope['project'])} project channels"
                )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to update frontmatter: {e}")
            return False