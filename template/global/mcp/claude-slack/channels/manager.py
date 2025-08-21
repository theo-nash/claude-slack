#!/usr/bin/env python3
"""
Channel Manager for Claude-Slack

Manages channels as entities without knowledge of subscriptions.

Responsibilities:
- Create, read, update, delete channels
- Manage channel metadata (name, description, scope)
- Apply default channels from configuration
- Validate channel names and IDs
- NO knowledge of subscriptions or who is subscribed
"""

import os
import sys
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from db.db_helpers import aconnect
except ImportError as e:
    print(f"Import error in ChannelManager: {e}", file=sys.stderr)
    aconnect = None

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

@dataclass
class Channel:
    """Data class representing a channel"""
    id: str  # Full channel ID (e.g., "global:general" or "proj_abc123:dev")
    name: str  # Channel name without prefix (e.g., "general", "dev")
    scope: str  # 'global' or 'project'
    project_id: Optional[str]  # Project ID for project channels
    description: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    is_default: bool = False
    is_archived: bool = False
    metadata: Optional[Dict[str, Any]] = None


class ChannelManager:
    """
    Manages channels as standalone entities.
    
    This manager handles all channel CRUD operations without any knowledge
    of subscriptions. It purely manages channels as resources.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize ChannelManager.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.logger = get_logger('ChannelManager', component='manager')
    
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
            # Fallback to global if no project context
            return f"global:{name}"
    
    @staticmethod
    def parse_channel_id(channel_id: str) -> tuple[str, str, Optional[str]]:
        """
        Parse a full channel ID into its components.
        
        Args:
            channel_id: Full channel ID (e.g., "global:general" or "proj_abc123:dev")
            
        Returns:
            Tuple of (scope, name, project_id_short)
        """
        if channel_id.startswith('global:'):
            return 'global', channel_id[7:], None
        elif channel_id.startswith('proj_'):
            parts = channel_id.split(':', 1)
            if len(parts) == 2:
                project_part = parts[0][5:]  # Remove 'proj_' prefix
                return 'project', parts[1], project_part
        
        # Default fallback
        return 'global', channel_id, None
    
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
    
    async def create_channel(self, name: str, scope: str, 
                           project_id: Optional[str] = None,
                           description: Optional[str] = None,
                           created_by: Optional[str] = None,
                           is_default: bool = False) -> Optional[str]:
        """
        Create a new channel.
        
        Args:
            name: Channel name (without prefix)
            scope: 'global' or 'project'
            project_id: Project ID for project channels
            description: Channel description
            created_by: Agent or user who created the channel
            is_default: Whether this is a default channel
            
        Returns:
            Channel ID if created successfully, None otherwise
        """
        if not aconnect:
            self.logger.error("Database connection not available")
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
        if scope == 'global' and project_id:
            project_id = None
        
        channel_id = self.get_scoped_channel_id(name, scope, project_id)
        
        # Check if channel already exists
        if await self.channel_exists(channel_id):
            return channel_id
        
        if not description:
            description = f"{scope.title()} {name} channel"
        
        self.logger.info(f"Creating channel: {channel_id}")
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                await conn.execute("""
                    INSERT INTO channels 
                    (id, project_id, scope, name, description, created_by, 
                     created_at, is_default, is_archived)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, 0)
                """, (channel_id, project_id, scope, name, description, 
                     created_by, is_default))
                
                self.logger.info(f"Channel created successfully: {channel_id}")
                return channel_id
                
        except Exception as e:
            self.logger.error(f"Error creating channel: {e}")
            return None
    
    async def get_channel(self, channel_id: str) -> Optional[Channel]:
        """
        Get a channel by ID.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            Channel object or None if not found
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return None
        
        try:
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT id, name, scope, project_id, description, 
                           created_by, created_at, is_default, is_archived, metadata
                    FROM channels 
                    WHERE id = ?
                """, (channel_id,))
                
                row = await cursor.fetchone()
                if row:
                    return Channel(
                        id=row[0],
                        name=row[1],
                        scope=row[2],
                        project_id=row[3],
                        description=row[4],
                        created_by=row[5],
                        created_at=datetime.fromisoformat(row[6]) if row[6] else datetime.now(),
                        is_default=bool(row[7]),
                        is_archived=bool(row[8]),
                        metadata=json.loads(row[9]) if row[9] else None
                    )
                    
        except Exception as e:
            self.logger.error(f"Error getting channel: {e}")
        
        return None
    
    async def channel_exists(self, channel_id: str) -> bool:
        """
        Check if a channel exists.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            True if channel exists, False otherwise
        """
        channel = await self.get_channel(channel_id)
        return channel is not None
    
    async def list_channels(self, scope: Optional[str] = None, 
                           project_id: Optional[str] = None,
                           include_archived: bool = False) -> List[Channel]:
        """
        List channels with optional filtering.
        
        Args:
            scope: Filter by scope ('global' or 'project')
            project_id: Filter by project ID
            include_archived: Include archived channels
            
        Returns:
            List of Channel objects
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return []
        
        channels = []
        
        try:
            # Build query based on filters
            query = "SELECT id, name, scope, project_id, description, created_by, created_at, is_default, is_archived, metadata FROM channels WHERE 1=1"
            params = []
            
            if scope:
                query += " AND scope = ?"
                params.append(scope)
            
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            
            if not include_archived:
                query += " AND is_archived = 0"
            
            query += " ORDER BY scope, name"
            
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute(query, params)
                
                async for row in cursor:
                    channels.append(Channel(
                        id=row[0],
                        name=row[1],
                        scope=row[2],
                        project_id=row[3],
                        description=row[4],
                        created_by=row[5],
                        created_at=datetime.fromisoformat(row[6]) if row[6] else datetime.now(),
                        is_default=bool(row[7]),
                        is_archived=bool(row[8]),
                        metadata=json.loads(row[9]) if row[9] else None
                    ))
            
            self.logger.debug(f"Listed {len(channels)} channels")
            
        except Exception as e:
            self.logger.error(f"Error listing channels: {e}")
        
        return channels
    
    async def update_channel(self, channel_id: str, 
                           description: Optional[str] = None,
                           is_archived: Optional[bool] = None) -> bool:
        """
        Update a channel's metadata.
        
        Args:
            channel_id: Full channel ID
            description: New description
            is_archived: Archive status
            
        Returns:
            True if updated successfully
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        updates = []
        params = []
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if is_archived is not None:
            updates.append("is_archived = ?")
            params.append(int(is_archived))
        
        if not updates:
            self.logger.warning("No updates provided")
            return False
        
        params.append(channel_id)
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                cursor = await conn.execute(
                    f"UPDATE channels SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                
                success = cursor.rowcount > 0
                if success:
                    self.logger.info(f"Updated channel: {channel_id}")
                else:
                    self.logger.warning(f"No channel found to update: {channel_id}")
                
                return success
                
        except Exception as e:
            self.logger.error(f"Error updating channel: {e}")
            return False
    
    async def delete_channel(self, channel_id: str) -> bool:
        """
        Delete a channel.
        
        Note: This will fail if there are foreign key constraints (e.g., messages in the channel).
        Consider archiving instead of deleting.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            True if deleted successfully
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                cursor = await conn.execute(
                    "DELETE FROM channels WHERE id = ?",
                    (channel_id,)
                )
                
                success = cursor.rowcount > 0
                if success:
                    self.logger.info(f"Deleted channel: {channel_id}")
                else:
                    self.logger.warning(f"No channel found to delete: {channel_id}")
                
                return success
                
        except Exception as e:
            self.logger.error(f"Error deleting channel: {e}")
            return False
    
    async def archive_channel(self, channel_id: str) -> bool:
        """
        Archive a channel (soft delete).
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            True if archived successfully
        """
        return await self.update_channel(channel_id, is_archived=True)
    
    async def unarchive_channel(self, channel_id: str) -> bool:
        """
        Unarchive a channel.
        
        Args:
            channel_id: Full channel ID
            
        Returns:
            True if unarchived successfully
        """
        return await self.update_channel(channel_id, is_archived=False)
    
    async def apply_default_channels(self, scope: str, 
                                    project_id: Optional[str] = None,
                                    created_by: Optional[str] = None) -> List[str]:
        """
        Create default channels from configuration.
        
        Args:
            scope: 'global' or 'project'
            project_id: Project ID for project channels
            created_by: Who is creating these channels
            
        Returns:
            List of channel IDs that were created
        """
        created_channels = []
        
        self.logger.info(f"Creating default {scope} channels")
        
        # Get default channels from config
        default_channels = []
        
        if get_config_manager:
            try:
                config_manager = get_config_manager()
                channels_config = config_manager.get_default_channels()
                
                if scope == 'project':
                    default_channels = channels_config.get('project', [])
                else:
                    default_channels = channels_config.get('global', [])

            except Exception as e:
                self.logger.warning(f"Failed to get default channels from config: {e}")
        
        # Use hardcoded defaults if config unavailable
        if not default_channels:
            if scope == 'project':
                default_channels = [
                    {'name': 'general', 'description': 'General project discussion'},
                    {'name': 'dev', 'description': 'Development discussion'}
                ]
            else:
                default_channels = [
                    {'name': 'general', 'description': 'General discussion'},
                    {'name': 'announcements', 'description': 'System announcements'}
                ]
        
        # Create the channels
        for channel_config in default_channels:
            name = channel_config.get('name')
            description = channel_config.get('description', f'{scope.title()} {name} channel')
            is_default = channel_config.get('is_default', True)
            
            # Check if channel already exists
            channel_id = self.get_scoped_channel_id(name, scope, project_id)
            if await self.channel_exists(channel_id):
                self.logger.debug(f"Channel already exists: {channel_id}")
                continue
            
            # Create the channel
            created_id = await self.create_channel(
                name=name,
                scope=scope,
                project_id=project_id,
                description=description,
                created_by=created_by,
                is_default=is_default
            )
            
            if created_id:
                created_channels.append(created_id)
                self.logger.debug(f"Created default channel: {created_id}")
        
        self.logger.info(f"Created {len(created_channels)} default {scope} channels")
        
        return created_channels
    
    async def get_or_create_channel(self, name: str, scope: str,
                                  project_id: Optional[str] = None,
                                  description: Optional[str] = None) -> str:
        """
        Get a channel if it exists, or create it if it doesn't.
        
        Args:
            name: Channel name
            scope: 'global' or 'project'
            project_id: Project ID for project channels
            description: Channel description for creation
            
        Returns:
            Channel ID
        """
        channel_id = self.get_scoped_channel_id(name, scope, project_id)
        
        # Check if channel exists
        if await self.channel_exists(channel_id):
            return channel_id
        
        # Create the channel
        created_id = await self.create_channel(
            name=name,
            scope=scope,
            project_id=project_id,
            description=description
        )
        
        return created_id or channel_id