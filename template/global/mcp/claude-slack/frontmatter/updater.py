#!/usr/bin/env python3
"""
Frontmatter Updater for Claude-Slack
Updates agent markdown files to add/remove channel subscriptions with scope support
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any


class FrontmatterUpdater:
    """Updates agent frontmatter for scoped channel subscriptions"""
    
    @staticmethod
    async def add_channel_subscription(
        agent_name: str,
        channel_name: str, 
        scope: str,
        claude_dir: str = "~/.claude"
    ) -> bool:
        """
        Add a channel subscription to an agent's frontmatter
        
        Args:
            agent_name: Name of the agent
            channel_name: Channel to subscribe to (without #)
            scope: 'global' or 'project'
            claude_dir: Base directory (could be project or global)
            
        Returns:
            True if successful, False otherwise
        """
        agent_file = FrontmatterUpdater._find_agent_file(agent_name, claude_dir)
        if not agent_file:
            return False
        
        try:
            # Read file content
            with open(agent_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter and content
            fm_data, body = FrontmatterUpdater._parse_file(content)
            
            # Ensure channels structure exists
            if 'channels' not in fm_data:
                fm_data['channels'] = {'global': [], 'project': []}
            elif isinstance(fm_data['channels'], list):
                # Migrate old format
                fm_data['channels'] = {
                    'global': fm_data['channels'],
                    'project': []
                }
            elif not isinstance(fm_data['channels'], dict):
                fm_data['channels'] = {'global': [], 'project': []}
            
            # Ensure scope exists
            if scope not in fm_data['channels']:
                fm_data['channels'][scope] = []
            
            # Add channel if not already subscribed
            channel_name = channel_name.lstrip('#').strip()
            if channel_name not in fm_data['channels'][scope]:
                fm_data['channels'][scope].append(channel_name)
            else:
                return True  # Already subscribed
            
            # Write back to file
            updated_content = FrontmatterUpdater._format_file(fm_data, body)
            with open(agent_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            return True
            
        except Exception as e:
            print(f"Error updating frontmatter: {e}")
            return False
    
    @staticmethod
    async def remove_channel_subscription(
        agent_name: str,
        channel_name: str,
        scope: str,
        claude_dir: str = "~/.claude"
    ) -> bool:
        """
        Remove a channel subscription from an agent's frontmatter
        
        Args:
            agent_name: Name of the agent
            channel_name: Channel to unsubscribe from (without #)
            scope: 'global' or 'project'
            claude_dir: Base directory
            
        Returns:
            True if successful, False otherwise
        """
        agent_file = FrontmatterUpdater._find_agent_file(agent_name, claude_dir)
        if not agent_file:
            return False
        
        try:
            # Read file content
            with open(agent_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter and content
            fm_data, body = FrontmatterUpdater._parse_file(content)
            
            # Check if channels exist
            if 'channels' not in fm_data:
                return True  # Not subscribed
            
            if isinstance(fm_data['channels'], dict) and scope in fm_data['channels']:
                channel_name = channel_name.lstrip('#').strip()
                if channel_name in fm_data['channels'][scope]:
                    fm_data['channels'][scope].remove(channel_name)
                else:
                    return True  # Already unsubscribed
            elif isinstance(fm_data['channels'], list):
                # Old format
                channel_name = channel_name.lstrip('#').strip()
                if channel_name in fm_data['channels']:
                    fm_data['channels'].remove(channel_name)
            else:
                return True  # Not subscribed
            
            # Write back to file
            updated_content = FrontmatterUpdater._format_file(fm_data, body)
            with open(agent_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            return True
            
        except Exception as e:
            print(f"Error updating frontmatter: {e}")
            return False
    
    @staticmethod
    async def bulk_update_subscriptions(
        agent_name: str,
        subscribe_to: Dict[str, List[str]],
        unsubscribe_from: Dict[str, List[str]],
        claude_dir: str = "~/.claude"
    ) -> bool:
        """
        Bulk update channel subscriptions
        
        Args:
            agent_name: Name of the agent
            subscribe_to: Dict with 'global' and 'project' channel lists to subscribe
            unsubscribe_from: Dict with 'global' and 'project' channel lists to unsubscribe
            claude_dir: Base directory
            
        Returns:
            True if successful, False otherwise
        """
        agent_file = FrontmatterUpdater._find_agent_file(agent_name, claude_dir)
        if not agent_file:
            return False
        
        try:
            # Read file content
            with open(agent_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter and content
            fm_data, body = FrontmatterUpdater._parse_file(content)
            
            # Ensure channels structure exists
            if 'channels' not in fm_data:
                fm_data['channels'] = {'global': [], 'project': []}
            elif isinstance(fm_data['channels'], list):
                # Migrate old format
                fm_data['channels'] = {
                    'global': fm_data['channels'],
                    'project': []
                }
            
            # Process subscriptions
            for scope in ['global', 'project']:
                if scope not in fm_data['channels']:
                    fm_data['channels'][scope] = []
                
                # Add new subscriptions
                if scope in subscribe_to:
                    for channel in subscribe_to[scope]:
                        channel = channel.lstrip('#').strip()
                        if channel not in fm_data['channels'][scope]:
                            fm_data['channels'][scope].append(channel)
                
                # Remove unsubscriptions
                if scope in unsubscribe_from:
                    for channel in unsubscribe_from[scope]:
                        channel = channel.lstrip('#').strip()
                        if channel in fm_data['channels'][scope]:
                            fm_data['channels'][scope].remove(channel)
            
            # Write back to file
            updated_content = FrontmatterUpdater._format_file(fm_data, body)
            with open(agent_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            return True
            
        except Exception as e:
            print(f"Error updating frontmatter: {e}")
            return False
    
    @staticmethod
    def _find_agent_file(agent_name: str, claude_dir: str) -> Optional[str]:
        """
        Find the agent file in the directory
        
        Args:
            agent_name: Name of the agent
            claude_dir: Base directory to search
            
        Returns:
            Path to agent file or None if not found
        """
        # Expand user path
        claude_dir = os.path.expanduser(claude_dir)
        
        # Check in agents directory
        agents_dir = os.path.join(claude_dir, 'agents')
        if os.path.exists(agents_dir):
            agent_file = os.path.join(agents_dir, f'{agent_name}.md')
            if os.path.exists(agent_file):
                return agent_file
        
        # Check in .claude/agents if claude_dir is a project
        dot_claude = os.path.join(claude_dir, '.claude', 'agents')
        if os.path.exists(dot_claude):
            agent_file = os.path.join(dot_claude, f'{agent_name}.md')
            if os.path.exists(agent_file):
                return agent_file
        
        return None
    
    @staticmethod
    def _parse_file(content: str) -> tuple[Dict[str, Any], str]:
        """
        Parse markdown file into frontmatter and body
        
        Args:
            content: File content
            
        Returns:
            Tuple of (frontmatter_dict, body_content)
        """
        if not content.startswith('---'):
            return {}, content
        
        # Find the end of frontmatter
        lines = content.split('\n')
        end_index = -1
        
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_index = i
                break
        
        if end_index == -1:
            return {}, content
        
        # Extract frontmatter and body
        frontmatter_lines = '\n'.join(lines[1:end_index])
        body_lines = '\n'.join(lines[end_index + 1:])
        
        try:
            frontmatter = yaml.safe_load(frontmatter_lines) or {}
        except yaml.YAMLError:
            frontmatter = {}
        
        return frontmatter, body_lines
    
    @staticmethod
    def _format_file(frontmatter: Dict[str, Any], body: str) -> str:
        """
        Format frontmatter and body back into markdown file
        
        Args:
            frontmatter: Frontmatter dictionary
            body: Body content
            
        Returns:
            Formatted file content
        """
        # Format frontmatter as YAML with proper indentation for nested structures
        yaml_str = yaml.dump(
            frontmatter, 
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2
        )
        
        # Combine with body
        return f"---\n{yaml_str}---\n{body}"
    
    @staticmethod
    async def migrate_to_scoped_format(
        agent_name: str,
        claude_dir: str = "~/.claude"
    ) -> bool:
        """
        Migrate an agent from flat channel list to scoped format
        
        Args:
            agent_name: Name of the agent
            claude_dir: Base directory
            
        Returns:
            True if migrated or already in new format, False on error
        """
        agent_file = FrontmatterUpdater._find_agent_file(agent_name, claude_dir)
        if not agent_file:
            return False
        
        try:
            # Read file content
            with open(agent_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter and content
            fm_data, body = FrontmatterUpdater._parse_file(content)
            
            # Check if already migrated
            if 'channels' in fm_data and isinstance(fm_data['channels'], dict):
                return True  # Already in new format
            
            # Migrate if needed
            if 'channels' in fm_data and isinstance(fm_data['channels'], list):
                old_channels = fm_data['channels']
                fm_data['channels'] = {
                    'global': old_channels,
                    'project': []
                }
                
                # Write back to file
                updated_content = FrontmatterUpdater._format_file(fm_data, body)
                with open(agent_file, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
            
            return True
            
        except Exception as e:
            print(f"Error migrating frontmatter: {e}")
            return False