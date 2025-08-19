#!/usr/bin/env python3
"""
admin_operations.py - Centralized business logic for Claude-Slack administration

This module contains all administrative operations for the Claude-Slack system.
It coordinates between the ConfigManager (YAML) and DatabaseManager (SQLite)
to ensure consistency and provide a single source of truth for all operations.

All scripts, hooks, and server components should use this module instead of
directly manipulating config or database.
"""

import os
import sys
import sqlite3
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from db.manager import DatabaseManager


class AdminOperations:
    """Centralized business logic for all administrative operations"""
    
    def __init__(self, db_path: Optional[str] = None, config_path: Optional[str] = None):
        """
        Initialize admin operations
        
        Args:
            db_path: Path to database (defaults to ~/.claude/data/claude-slack.db)
            config_path: Path to config file (defaults to ~/.claude/config/claude-slack.config.yaml)
        """
        # Initialize config manager
        self.config_mgr = ConfigManager(config_path)
        
        # Database path
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = Path.home() / '.claude' / 'data' / 'claude-slack.db'
        
        # Will be initialized when needed
        self.db_mgr = None
        self._db_initialized = False
    
    async def _ensure_db(self):
        """Ensure database manager is initialized"""
        if not self._db_initialized:
            self.db_mgr = DatabaseManager(str(self.db_path))
            await self.db_mgr.initialize()
            self._db_initialized = True
    
    def _get_project_id(self, project_path: str) -> str:
        """Generate consistent project ID from path"""
        return hashlib.sha256(project_path.encode()).hexdigest()[:32]
    
    # ==================== PROJECT OPERATIONS ====================
    
    async def register_project(self, project_path: str, project_name: Optional[str] = None) -> Tuple[bool, str]:
        """
        Register a project and create default channels
        
        Args:
            project_path: Absolute path to project
            project_name: Optional project name (defaults to directory name)
            
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_db()
        
        try:
            # Generate project ID
            project_id = self._get_project_id(project_path)
            if not project_name:
                project_name = os.path.basename(project_path)
            
            # Register in database
            await self.db_mgr.register_project(project_id, project_path, project_name)
            
            # Create default channels from config
            success, msg = await self.create_default_channels(project_id=project_id)
            if not success:
                return False, f"Project registered but channel creation failed: {msg}"
            
            return True, f"Project '{project_name}' registered successfully"
            
        except Exception as e:
            return False, f"Failed to register project: {str(e)}"
    
    async def create_default_channels(self, project_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Create default channels from configuration
        
        Args:
            project_id: If provided, create project channels. Otherwise create global channels.
            
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_db()
        
        try:
            config = self.config_mgr.load_config()
            
            if project_id:
                # Create project channels
                channels = config.get('default_channels', {}).get('project', [])
                project_id_short = project_id[:8]
                created = 0
                
                for channel in channels:
                    channel_id = f"proj_{project_id_short}:{channel['name']}"
                    await self.db_mgr.create_channel_if_not_exists(
                        channel_id=channel_id,
                        name=channel['name'],
                        description=channel.get('description', f"Project {channel['name']} channel"),
                        scope='project',
                        project_id=project_id,
                        is_default=True
                    )
                    created += 1
                
                return True, f"Created {created} project channels"
            
            else:
                # Create global channels
                channels = config.get('default_channels', {}).get('global', [])
                created = 0
                
                for channel in channels:
                    channel_id = f"global:{channel['name']}"
                    await self.db_mgr.create_channel_if_not_exists(
                        channel_id=channel_id,
                        name=channel['name'],
                        description=channel.get('description', f"Global {channel['name']} channel"),
                        scope='global',
                        project_id=None,
                        is_default=True
                    )
                    created += 1
                
                return True, f"Created {created} global channels"
                
        except Exception as e:
            return False, f"Failed to create channels: {str(e)}"
    
    # ==================== PROJECT LINK OPERATIONS ====================
    
    async def link_projects(
        self, 
        source: str, 
        target: str, 
        link_type: str = 'bidirectional',
        created_by: str = 'admin'
    ) -> Tuple[bool, str]:
        """
        Link two projects for cross-project communication
        
        Args:
            source: Source project name or ID
            target: Target project name or ID
            link_type: 'bidirectional', 'a_to_b', or 'b_to_a'
            created_by: Who is creating the link
            
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_db()
        
        try:
            # Validate projects exist
            source_project = await self._get_project_by_name_or_id(source)
            target_project = await self._get_project_by_name_or_id(target)
            
            if not source_project:
                return False, f"Project '{source}' not found"
            if not target_project:
                return False, f"Project '{target}' not found"
            
            source_id, source_name = source_project[0], source_project[1]
            target_id, target_name = target_project[0], target_project[1]
            
            if source_id == target_id:
                return False, "Cannot link a project to itself"
            
            # Update configuration
            config = self.config_mgr.load_config()
            project_links = config.get('project_links', [])
            
            # Check if link already exists
            for link in project_links:
                if (link.get('source') in [source_id, source_name] and 
                    link.get('target') in [target_id, target_name]) or \
                   (link.get('source') in [target_id, target_name] and 
                    link.get('target') in [source_id, source_name]):
                    # Update existing link
                    link['type'] = link_type
                    link['enabled'] = True
                    link['updated_at'] = datetime.now().isoformat()
                    link['updated_by'] = created_by
                    break
            else:
                # Add new link
                project_links.append({
                    'source': source_id,
                    'target': target_id,
                    'type': link_type,
                    'enabled': True,
                    'created_by': created_by,
                    'created_at': datetime.now().isoformat()
                })
            
            config['project_links'] = project_links
            if not self.config_mgr.save_config(config):
                return False, "Failed to update configuration"
            
            # Update database
            success = await self.db_mgr.link_projects(source_id, target_id, link_type, created_by)
            if not success:
                return False, "Failed to update database"
            
            # Format success message
            if link_type == 'bidirectional':
                msg = f"Linked projects (bidirectional): {source_name} ↔️ {target_name}"
            elif link_type == 'a_to_b':
                msg = f"Linked projects (one-way): {source_name} → {target_name}"
            else:
                msg = f"Linked projects (one-way): {target_name} → {source_name}"
            
            return True, msg
            
        except Exception as e:
            return False, f"Failed to link projects: {str(e)}"
    
    async def unlink_projects(self, source: str, target: str) -> Tuple[bool, str]:
        """
        Remove link between two projects
        
        Args:
            source: Source project name or ID
            target: Target project name or ID
            
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_db()
        
        try:
            # Validate projects exist
            source_project = await self._get_project_by_name_or_id(source)
            target_project = await self._get_project_by_name_or_id(target)
            
            if not source_project:
                return False, f"Project '{source}' not found"
            if not target_project:
                return False, f"Project '{target}' not found"
            
            source_id, source_name = source_project[0], source_project[1]
            target_id, target_name = target_project[0], target_project[1]
            
            # Update configuration
            config = self.config_mgr.load_config()
            project_links = config.get('project_links', [])
            
            # Remove link
            new_links = [
                link for link in project_links
                if not (
                    (link.get('source') in [source_id, source_name] and 
                     link.get('target') in [target_id, target_name]) or
                    (link.get('source') in [target_id, target_name] and 
                     link.get('target') in [source_id, source_name])
                )
            ]
            
            if len(new_links) == len(project_links):
                return False, "No link found between these projects"
            
            config['project_links'] = new_links
            if not self.config_mgr.save_config(config):
                return False, "Failed to update configuration"
            
            # Update database
            success = await self.db_mgr.unlink_projects(source_id, target_id)
            if not success:
                return False, "Failed to update database"
            
            return True, f"Unlinked projects: {source_name} ✂️ {target_name}"
            
        except Exception as e:
            return False, f"Failed to unlink projects: {str(e)}"
    
    async def sync_project_links_from_config(self) -> Tuple[bool, str]:
        """
        Sync project links from configuration to database
        
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_db()
        
        try:
            config = self.config_mgr.load_config()
            project_links = config.get('project_links', [])
            
            # Clear existing links in database
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM project_links")
            
            # Add links from config
            synced = 0
            for link in project_links:
                if not link.get('enabled', True):
                    continue
                
                source = link.get('source')
                target = link.get('target')
                link_type = link.get('type', 'bidirectional')
                created_by = link.get('created_by', 'config')
                
                # Ensure consistent ordering
                if source > target:
                    source, target = target, source
                    if link_type == "a_to_b":
                        link_type = "b_to_a"
                    elif link_type == "b_to_a":
                        link_type = "a_to_b"
                
                conn.execute("""
                    INSERT INTO project_links 
                    (project_a_id, project_b_id, link_type, created_by, enabled)
                    VALUES (?, ?, ?, ?, 1)
                """, (source, target, link_type, created_by))
                synced += 1
            
            conn.commit()
            conn.close()
            
            return True, f"Synced {synced} project links from configuration"
            
        except Exception as e:
            return False, f"Failed to sync project links: {str(e)}"
    
    # ==================== AGENT OPERATIONS ====================
    
    async def register_agent(
        self,
        agent_name: str,
        description: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Register an agent in the database
        
        Args:
            agent_name: Name of the agent
            description: Agent description
            project_id: Project ID (None for global agents)
            
        Returns:
            Tuple of (success, message)
        """
        await self._ensure_db()
        
        try:
            await self.db_mgr.register_agent(agent_name, description, project_id)
            
            scope = "project" if project_id else "global"
            return True, f"Registered {scope} agent: {agent_name}"
            
        except Exception as e:
            return False, f"Failed to register agent: {str(e)}"
    
    def configure_agent_file(
        self,
        agent_file: Path,
        add_tools: bool = True,
        add_subscriptions: bool = True
    ) -> Tuple[bool, str]:
        """
        Configure an agent file with MCP tools and channel subscriptions
        
        Args:
            agent_file: Path to agent markdown file
            add_tools: Whether to add MCP tools
            add_subscriptions: Whether to add channel subscriptions
            
        Returns:
            Tuple of (success, message)
        """
        try:
            if not agent_file.exists():
                return False, f"Agent file not found: {agent_file}"
            
            with open(agent_file, 'r') as f:
                content = f.read()
            
            if not content.startswith('---'):
                return False, "Agent file has no frontmatter"
            
            lines = content.split('\n')
            updates_made = []
            
            # Find frontmatter boundaries
            end_index = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end_index = i
                    break
            
            if end_index == -1:
                return False, "Invalid frontmatter format"
            
            # Add MCP tools if requested
            if add_tools:
                tools_added = self._add_mcp_tools_to_lines(lines, end_index)
                if tools_added:
                    updates_made.append("MCP tools")
            
            # Add channel subscriptions if requested
            if add_subscriptions:
                subs_added = self._add_subscriptions_to_lines(lines, end_index)
                if subs_added:
                    updates_made.append("channel subscriptions")
            
            if updates_made:
                # Write updated content
                with open(agent_file, 'w') as f:
                    f.write('\n'.join(lines))
                return True, f"Added {', '.join(updates_made)} to {agent_file.stem}"
            else:
                return True, f"Agent {agent_file.stem} already configured"
                
        except Exception as e:
            return False, f"Failed to configure agent: {str(e)}"
    
    def _add_mcp_tools_to_lines(self, lines: List[str], end_index: int) -> bool:
        """Add MCP tools to agent frontmatter lines"""
        # Get MCP tools from config
        config = self.config_mgr.load_config()
        tool_names = config.get('default_mcp_tools', [])
        
        # Add prefix to tool names
        if tool_names:
            slack_tools = [f'mcp__claude-slack__{tool}' for tool in tool_names]
        else:
            # Fallback to hardcoded list if config doesn't have them
            slack_tools = [
                'mcp__claude-slack__send_channel_message',
                'mcp__claude-slack__send_direct_message',
                'mcp__claude-slack__get_messages',
                'mcp__claude-slack__list_channels',
                'mcp__claude-slack__subscribe_to_channel',
                'mcp__claude-slack__unsubscribe_from_channel',
                'mcp__claude-slack__get_my_subscriptions',
                'mcp__claude-slack__search_messages',
                'mcp__claude-slack__get_current_project',
                'mcp__claude-slack__list_projects',
                'mcp__claude-slack__list_agents',
                'mcp__claude-slack__create_channel',
                'mcp__claude-slack__get_linked_projects'
            ]
        
        # Find tools line
        tools_line = -1
        for i in range(1, end_index):
            if lines[i].startswith('tools:'):
                tools_line = i
                tools_value = lines[i].split(':', 1)[1].strip()
                
                # Check if already has all tools access
                if tools_value in ['All', 'all', '"All"', "'All'", '*', '"*"', "'*'"]:
                    return False
                
                # Parse existing tools
                if tools_value.startswith('[') and tools_value.endswith(']'):
                    existing_tools = [t.strip().strip('"\'') for t in tools_value[1:-1].split(',')]
                else:
                    existing_tools = []
                
                # Check if already has slack tools
                if any(tool in existing_tools for tool in slack_tools):
                    return False
                
                # Add slack tools
                all_tools = existing_tools + slack_tools
                
                # Format tools line
                if len(all_tools) > 3:
                    # Multi-line format
                    tool_lines = ['tools:']
                    for tool in all_tools:
                        tool_lines.append(f'  - {tool}')
                    lines[tools_line:tools_line+1] = tool_lines
                else:
                    # Single line format
                    lines[tools_line] = f'tools: [{", ".join(all_tools)}]'
                
                return True
        
        # No tools line found, add one
        tool_lines = ['tools:']
        for tool in slack_tools:
            tool_lines.append(f'  - {tool}')
        
        # Insert before closing ---
        for line in reversed(tool_lines):
            lines.insert(end_index, line)
        
        return True
    
    def _add_subscriptions_to_lines(self, lines: List[str], end_index: int) -> bool:
        """Add channel subscriptions to agent frontmatter lines"""
        # Get default subscriptions from config
        config = self.config_mgr.load_config()
        default_subs = config.get('settings', {}).get('default_agent_subscriptions', {
            'global': ['general', 'announcements'],
            'project': ['general', 'dev']
        })
        
        # Check if channels already exist
        for i in range(1, end_index):
            if lines[i].startswith('channels:'):
                return False  # Already has channels
        
        # Add channel subscriptions
        channel_lines = ['channels:']
        
        if default_subs.get('global'):
            channel_lines.append('  global:')
            for channel in default_subs['global']:
                channel_lines.append(f'    - {channel}')
        
        if default_subs.get('project'):
            channel_lines.append('  project:')
            for channel in default_subs['project']:
                channel_lines.append(f'    - {channel}')
        
        # Insert before closing ---
        for line in reversed(channel_lines):
            lines.insert(end_index, line)
        
        return True
    
    # ==================== UTILITY OPERATIONS ====================
    
    async def _get_project_by_name_or_id(self, identifier: str) -> Optional[Tuple[str, str, str]]:
        """Get project by name or ID"""
        await self._ensure_db()
        
        # Try direct database query
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("""
            SELECT id, name, path
            FROM projects
            WHERE name = ? OR id = ? OR path = ?
        """, (identifier, identifier, identifier))
        
        result = cursor.fetchone()
        conn.close()
        
        return result
    
    async def list_all_projects(self) -> List[Dict]:
        """List all registered projects"""
        await self._ensure_db()
        return await self.db_mgr.list_projects()
    
    async def list_all_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents"""
        await self._ensure_db()
        return await self.db_mgr.list_all_agents()
    
    async def list_all_channels(self) -> List[Dict[str, Any]]:
        """List all channels"""
        await self._ensure_db()
        return await self.db_mgr.list_all_channels()
    
    async def get_project_links(self, project_id: str) -> List[str]:
        """Get all projects linked to a specific project"""
        await self._ensure_db()
        return await self.db_mgr.get_linked_projects(project_id)
    
    async def validate_configuration(self) -> Tuple[bool, List[str]]:
        """
        Validate the configuration file
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        return self.config_mgr.validate_config()
    
    # ==================== SYNCHRONOUS WRAPPERS ====================
    
    def sync_register_project(self, project_path: str, project_name: Optional[str] = None) -> Tuple[bool, str]:
        """Synchronous wrapper for register_project"""
        return asyncio.run(self.register_project(project_path, project_name))
    
    def sync_link_projects(self, source: str, target: str, link_type: str = 'bidirectional') -> Tuple[bool, str]:
        """Synchronous wrapper for link_projects"""
        return asyncio.run(self.link_projects(source, target, link_type))
    
    def sync_unlink_projects(self, source: str, target: str) -> Tuple[bool, str]:
        """Synchronous wrapper for unlink_projects"""
        return asyncio.run(self.unlink_projects(source, target))
    
    def sync_create_default_channels(self, project_id: Optional[str] = None) -> Tuple[bool, str]:
        """Synchronous wrapper for create_default_channels"""
        return asyncio.run(self.create_default_channels(project_id))
    
    def sync_register_agent(self, agent_name: str, description: Optional[str] = None, 
                           project_id: Optional[str] = None) -> Tuple[bool, str]:
        """Synchronous wrapper for register_agent"""
        return asyncio.run(self.register_agent(agent_name, description, project_id))
    
    def sync_sync_project_links(self) -> Tuple[bool, str]:
        """Synchronous wrapper for sync_project_links_from_config"""
        return asyncio.run(self.sync_project_links_from_config())


# Convenience function for scripts
def get_admin_ops(db_path: Optional[str] = None, config_path: Optional[str] = None) -> AdminOperations:
    """Get an AdminOperations instance"""
    return AdminOperations(db_path, config_path)