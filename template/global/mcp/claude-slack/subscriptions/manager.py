#!/usr/bin/env python3
"""
Centralized Subscription Manager for Claude-Slack

Handles all subscription operations with proper composite key support for the database schema.
The database uses composite foreign keys: (agent_name, agent_project_id) -> agents(name, project_id)

This manager provides:
- Unified interface for all subscription operations
- Proper handling of composite keys for referential integrity
- Context-aware operations using SessionContextManager
- Atomic updates to both database and frontmatter
- Simple caching for performance
"""

import os
import sys
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Add parent directories to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from db.db_helpers import aconnect
    from frontmatter.updater import FrontmatterUpdater
    from frontmatter.parser import FrontmatterParser
except ImportError as e:
    print(f"Import error in SubscriptionManager: {e}", file=sys.stderr)
    # Create fallback imports to avoid crashes
    aconnect = None
    FrontmatterUpdater = None
    FrontmatterParser = None

try:
    from config_manager import get_config_manager
except ImportError:
    get_config_manager = None

try:
    from log_manager import get_logger
except ImportError:
    # Fallback to standard logging if new logging system not available
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)

class SubscriptionManager:
    """
    Centralized manager for all subscription operations.
    
    Handles the complexity of composite foreign keys and provides a clean interface
    for subscription management across both database and frontmatter persistence.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize subscription manager.
        
        Args:
            db_path: Path to SQLite database
            session_manager: SessionManager instance for context detection
        """
        self.db_path = db_path
        self.logger = get_logger('SubscriptionManager', component='manager')
        
        # Simple in-memory cache with TTL
        self._cache = {}
        self._cache_times = {}
        self._cache_ttl = 60  # 60 seconds
    
    def _cache_key(self, agent_name: str, agent_project_id: Optional[str]) -> str:
        """Generate cache key for agent subscriptions"""
        return f"{agent_name}:{agent_project_id or 'global'}"
    
    def _get_cached_subscriptions(self, agent_name: str, agent_project_id: Optional[str]) -> Optional[Dict[str, List[str]]]:
        """Get cached subscriptions if still valid"""
        cache_key = self._cache_key(agent_name, agent_project_id)
        if cache_key in self._cache:
            if time.time() - self._cache_times.get(cache_key, 0) < self._cache_ttl:
                self.logger.debug(f"Cache hit for {cache_key}")
                return self._cache[cache_key]
        return None
    
    def _cache_subscriptions(self, agent_name: str, agent_project_id: Optional[str], subscriptions: Dict[str, List[str]]):
        """Cache subscriptions for the agent"""
        cache_key = self._cache_key(agent_name, agent_project_id)
        self._cache[cache_key] = subscriptions
        self._cache_times[cache_key] = time.time()
        self.logger.debug(f"Cached subscriptions for {cache_key}")
    
    def _invalidate_cache(self, agent_name: str, agent_project_id: Optional[str]):
        """Invalidate cached subscriptions for the agent"""
        cache_key = self._cache_key(agent_name, agent_project_id)
        if cache_key in self._cache:
            del self._cache[cache_key]
            del self._cache_times[cache_key]
            self.logger.debug(f"Invalidated cache for {cache_key}")
    
    def _get_scoped_channel_id(self, channel_name: str, scope: str, project_id: Optional[str] = None) -> str:
        """
        Get the full channel ID with scope prefix.
        
        Args:
            channel_name: Channel name without prefix
            scope: 'global' or 'project'
            project_id: Project ID for project channels
            
        Returns:
            Full channel ID (e.g., "global:general" or "proj_abc123:dev")
        """
        if scope == 'global':
            return f"global:{channel_name}"
        else:
            if project_id:
                project_id_short = project_id[:8]
                return f"proj_{project_id_short}:{channel_name}"
            else:
                # Fallback to global if no project context
                return f"global:{channel_name}"
    
    async def ensure_agent_registered(self, agent_name: str, agent_project_id: Optional[str]) -> bool:
        """
        Ensure agent is registered in the database.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global)
            
        Returns:
            True if agent was registered or already exists
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                await conn.execute("""
                    INSERT OR IGNORE INTO agents (name, project_id, description, status, last_active)
                    VALUES (?, ?, ?, 'online', datetime('now'))
                """, (agent_name, agent_project_id, f"Agent {agent_name}"))
                
                # Update last_active if agent already exists
                await conn.execute("""
                    UPDATE agents 
                    SET last_active = datetime('now'), status = 'online'
                    WHERE name = ? AND project_id IS ?
                """, (agent_name, agent_project_id))
                
                self.logger.debug(f"Ensured agent registration: {agent_name} (project_id: {agent_project_id})")
                return True
                
        except Exception as e:
            self.logger.error(f"Error ensuring agent registration: {e}")
            return False
    
    async def ensure_channel_exists(self, channel_id: str, scope: str, channel_name: str, project_id: Optional[str] = None) -> bool:
        """
        Ensure channel exists in the database.
        
        Args:
            channel_id: Full channel ID
            scope: 'global' or 'project'
            channel_name: Channel name without prefix
            project_id: Project ID for project channels
            
        Returns:
            True if channel exists or was created
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                await conn.execute("""
                    INSERT OR IGNORE INTO channels (id, project_id, scope, name, description, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (channel_id, project_id, scope, channel_name, f"{scope.title()} {channel_name} channel"))
                
                self.logger.debug(f"Ensured channel exists: {channel_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error ensuring channel exists: {e}")
            return False
    
    async def subscribe(self, agent_name: str, agent_project_id: Optional[str], 
                       channel_name: str, scope: str, source: str = 'manual', agent_project_dir = None) -> bool:
        """
        Subscribe an agent to a channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            channel_name: Channel name without prefix
            scope: 'global' or 'project'
            source: Source of subscription ('manual', 'frontmatter', 'auto_pattern')
            
        Returns:
            True if subscription was successful
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        # Determine project ID for channel scoping
        channel_project_id = agent_project_id if scope == 'project' else None
        channel_id = self._get_scoped_channel_id(channel_name, scope, channel_project_id)
        
        self.logger.info(f"Subscribing {agent_name} (project: {agent_project_id}) to {channel_id}")
        
        try:
            # Ensure agent is registered
            await self.ensure_agent_registered(agent_name, agent_project_id)
            
            # Ensure channel exists
            await self.ensure_channel_exists(channel_id, scope, channel_name, channel_project_id)
            
            # Add subscription
            async with aconnect(self.db_path, writer=True) as conn:
                cursor = await conn.execute("""
                    INSERT OR REPLACE INTO subscriptions 
                    (agent_name, agent_project_id, channel_id, source, subscribed_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (agent_name, agent_project_id, channel_id, source))
                
                success = cursor.rowcount > 0
                if success:
                    self.logger.info(f"Successfully subscribed {agent_name} to {channel_id}")
                    # Invalidate cache
                    self._invalidate_cache(agent_name, agent_project_id)
                else:
                    self.logger.warning(f"No rows affected for subscription: {agent_name} -> {channel_id}")
            
            # Update frontmatter
            if agent_name != "assistant" and agent_project_dir:
                try:
                    await FrontmatterUpdater.add_channel_subscription(agent_name, channel_id, scope, agent_project_dir)
                    self.logger.debug(f"Updated frontmatter for {agent_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to update frontmatter: {e}")
            
            return success
                
        except Exception as e:
            self.logger.error(f"Error subscribing {agent_name} to {channel_id}: {e}")
            return False
    
    async def unsubscribe(self, agent_name: str, agent_project_id: Optional[str],
                         channel_name: str, scope: str, agent_project_dir = None) -> bool:
        """
        Unsubscribe an agent from a channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            channel_name: Channel name without prefix
            scope: 'global' or 'project'
            
        Returns:
            True if unsubscription was successful
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        # Determine project ID for channel scoping
        channel_project_id = agent_project_id if scope == 'project' else None
        channel_id = self._get_scoped_channel_id(channel_name, scope, channel_project_id)
        
        self.logger.info(f"Unsubscribing {agent_name} (project: {agent_project_id}) from {channel_id}")
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                cursor = await conn.execute("""
                    DELETE FROM subscriptions 
                    WHERE agent_name = ? AND agent_project_id IS ? AND channel_id = ?
                """, (agent_name, agent_project_id, channel_id))
                
                success = cursor.rowcount > 0
                if success:
                    self.logger.info(f"Successfully unsubscribed {agent_name} from {channel_id}")
                    # Invalidate cache
                    self._invalidate_cache(agent_name, agent_project_id)
                else:
                    self.logger.warning(f"No subscription found to remove: {agent_name} -> {channel_id}")
                
            # Update frontmatter
            if agent_name != "assistant" and agent_project_dir:
                try:
                    await FrontmatterUpdater.remove_channel_subscription(agent_name, channel_id, scope, agent_project_dir)
                    self.logger.debug(f"Remoed frontmatter for {agent_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to remove frontmatter: {e}")
            
            return success
                
        except Exception as e:
            self.logger.error(f"Error unsubscribing {agent_name} from {channel_id}: {e}")
            return False
    
    async def get_subscriptions(self, agent_name: str, agent_project_id: Optional[str]) -> Dict[str, List[str]]:
        """
        Get all subscriptions for an agent.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            
        Returns:
            Dictionary with 'global' and 'project' channel lists
        """
        # Check cache first
        cached = self._get_cached_subscriptions(agent_name, agent_project_id)
        if cached is not None:
            return cached
        
        if not aconnect:
            self.logger.error("Database connection not available")
            return {'global': [], 'project': []}
        
        subscriptions = {'global': [], 'project': []}
        
        try:
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT c.scope, c.name
                    FROM subscriptions s
                    JOIN channels c ON s.channel_id = c.id
                    WHERE s.agent_name = ? AND s.agent_project_id IS ?
                    AND s.is_muted = 0
                    ORDER BY c.scope, c.name
                """, (agent_name, agent_project_id))
                
                async for row in cursor:
                    scope, channel_name = row
                    if scope in subscriptions:
                        subscriptions[scope].append(channel_name)
                
                self.logger.debug(f"Retrieved subscriptions for {agent_name}: {subscriptions}")
                
                # Cache the result
                self._cache_subscriptions(agent_name, agent_project_id, subscriptions)
                
                return subscriptions
                
        except Exception as e:
            self.logger.error(f"Error getting subscriptions for {agent_name}: {e}")
            return {'global': [], 'project': []}
    
    async def is_subscribed(self, agent_name: str, agent_project_id: Optional[str], 
                           channel_name: str, scope: str) -> bool:
        """
        Check if an agent is subscribed to a specific channel.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            channel_name: Channel name without prefix
            scope: 'global' or 'project'
            
        Returns:
            True if agent is subscribed to the channel
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        # Determine project ID for channel scoping
        channel_project_id = agent_project_id if scope == 'project' else None
        channel_id = self._get_scoped_channel_id(channel_name, scope, channel_project_id)
        
        try:
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT 1 FROM subscriptions 
                    WHERE agent_name = ? AND agent_project_id IS ? AND channel_id = ?
                    AND is_muted = 0
                """, (agent_name, agent_project_id, channel_id))
                
                result = await cursor.fetchone()
                is_subscribed = result is not None
                
                self.logger.debug(f"Subscription check: {agent_name} -> {channel_id}: {is_subscribed}")
                return is_subscribed
                
        except Exception as e:
            self.logger.error(f"Error checking subscription: {e}")
            return False
    
    async def bulk_subscribe(self, agent_name: str, agent_project_id: Optional[str],
                            channels: List[str], scope: str, source: str = 'bulk') -> int:
        """
        Subscribe an agent to multiple channels at once.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            channels: List of channel names without prefix
            scope: 'global' or 'project'
            source: Source of subscriptions
            
        Returns:
            Number of channels successfully subscribed to
        """
        self.logger.info(f"Bulk subscribing {agent_name} to {len(channels)} {scope} channels")
        
        success_count = 0
        for channel_name in channels:
            if await self.subscribe(agent_name, agent_project_id, channel_name, scope, source):
                success_count += 1
        
        self.logger.info(f"Bulk subscription complete: {success_count}/{len(channels)} successful")
        return success_count
    
    async def clear_subscriptions(self, agent_name: str, agent_project_id: Optional[str], scope: Optional[str] = None) -> int:
        """
        Clear all subscriptions for an agent.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            scope: Optional scope filter ('global' or 'project')
            
        Returns:
            Number of subscriptions removed
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return 0
        
        self.logger.info(f"Clearing subscriptions for {agent_name} (project: {agent_project_id}, scope: {scope})")
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                if scope:
                    # Clear subscriptions for specific scope
                    cursor = await conn.execute("""
                        DELETE FROM subscriptions 
                        WHERE agent_name = ? AND agent_project_id IS ?
                        AND channel_id IN (
                            SELECT id FROM channels WHERE scope = ?
                        )
                    """, (agent_name, agent_project_id, scope))
                else:
                    # Clear all subscriptions
                    cursor = await conn.execute("""
                        DELETE FROM subscriptions 
                        WHERE agent_name = ? AND agent_project_id IS ?
                    """, (agent_name, agent_project_id))
                
                removed_count = cursor.rowcount
                self.logger.info(f"Cleared {removed_count} subscriptions for {agent_name}")
                
                # Invalidate cache
                self._invalidate_cache(agent_name, agent_project_id)
                
                return removed_count
                
        except Exception as e:
            self.logger.error(f"Error clearing subscriptions: {e}")
            return 0
    
    async def sync_from_frontmatter(self, agent_name: str, agent_project_id: Optional[str], 
                                   agent_file_path: str) -> bool:
        """
        Sync agent subscriptions from frontmatter file to database.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            agent_file_path: Path to agent markdown file
            
        Returns:
            True if sync was successful
        """
        if not FrontmatterParser:
            self.logger.error("FrontmatterParser not available")
            return False
        
        self.logger.info(f"Syncing subscriptions from frontmatter: {agent_file_path}")
        
        try:
            # Parse frontmatter
            agent_data = FrontmatterParser.parse_file(agent_file_path)
            channels = agent_data.get('channels', {'global': [], 'project': []})
            
            # Ensure it's in scoped format
            if isinstance(channels, list):
                channels = {'global': channels, 'project': []}
            elif not isinstance(channels, dict):
                channels = {'global': ['general', 'announcements'], 'project': []}
            
            # Clear existing subscriptions and replace with frontmatter data
            await self.clear_subscriptions(agent_name, agent_project_id)
            
            # Subscribe to global channels
            global_count = await self.bulk_subscribe(
                agent_name, agent_project_id, 
                channels.get('global', []), 'global', 'frontmatter'
            )
            
            # Subscribe to project channels (only if agent has project context)
            project_count = 0
            if agent_project_id and channels.get('project'):
                project_count = await self.bulk_subscribe(
                    agent_name, agent_project_id,
                    channels.get('project', []), 'project', 'frontmatter'
                )
            
            self.logger.info(f"Frontmatter sync complete: {global_count} global, {project_count} project subscriptions")
            return True
            
        except Exception as e:
            self.logger.error(f"Error syncing from frontmatter: {e}")
            return False
    
    async def get_channel_subscribers(self, channel_id: str) -> List[Tuple[str, Optional[str]]]:
        """
        Get all subscribers for a channel.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            List of (agent_name, agent_project_id) tuples
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return []
        
        try:
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT agent_name, agent_project_id
                    FROM subscriptions 
                    WHERE channel_id = ? AND is_muted = 0
                    ORDER BY agent_name
                """, (channel_id,))
                
                subscribers = []
                async for row in cursor:
                    subscribers.append((row[0], row[1]))
                
                self.logger.debug(f"Found {len(subscribers)} subscribers for {channel_id}")
                return subscribers
                
        except Exception as e:
            self.logger.error(f"Error getting channel subscribers: {e}")
            return []
    
    async def apply_default_subscriptions(self, agent_name: str, agent_project_id: Optional[str], 
                                         force: bool = False) -> Dict[str, List[str]]:
        """
        Apply default channel subscriptions from configuration.
        
        This method reads the default subscriptions from the config file and applies them
        to the specified agent. It's useful for initializing new agents or resetting
        an agent's subscriptions to defaults.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID (None for global agents)
            force: If True, overwrites existing subscriptions. If False, only adds missing defaults.
            
        Returns:
            Dictionary with 'global' and 'project' lists of applied subscriptions
        """
        applied = {'global': [], 'project': []}
        
        self.logger.info(f"Applying default subscriptions for {agent_name} (project: {agent_project_id})")
        
        # Get default subscriptions from config
        default_subs = None
        
        # Try to get from ConfigManager first
        if get_config_manager:
            try:
                config_manager = get_config_manager()
                settings = config_manager.get_settings()
                
                # Get default agent subscriptions from settings
                default_subs = settings.get('default_agent_subscriptions', None)
                if default_subs:
                    self.logger.debug("Using default subscriptions from config")
                    
            except Exception as e:
                self.logger.warning(f"Failed to get defaults from ConfigManager: {e}")
        
        # Use hardcoded defaults if config unavailable
        if not default_subs:
            default_subs = {
                'global': ['general', 'announcements'],
                'project': ['general', 'dev'] if agent_project_id else []
            }
            self.logger.debug("Using hardcoded default subscriptions")
        
        # Get current subscriptions if not forcing
        current_subs = {'global': [], 'project': []}
        if not force:
            current_subs = await self.get_subscriptions(agent_name, agent_project_id)
            self.logger.debug(f"Current subscriptions: {current_subs}")
        
        # Apply global defaults
        for channel in default_subs.get('global', []):
            if force or channel not in current_subs.get('global', []):
                success = await self.subscribe(agent_name, agent_project_id, channel, 'global', 'default')
                if success:
                    applied['global'].append(channel)
                    self.logger.debug(f"Applied default global subscription: {channel}")
        
        # Apply project defaults (only if agent has project context)
        if agent_project_id:
            for channel in default_subs.get('project', []):
                if force or channel not in current_subs.get('project', []):
                    success = await self.subscribe(agent_name, agent_project_id, channel, 'project', 'default')
                    if success:
                        applied['project'].append(channel)
                        self.logger.debug(f"Applied default project subscription: {channel}")
        
        self.logger.info(f"Applied default subscriptions: {len(applied['global'])} global, {len(applied['project'])} project")
        
        return applied