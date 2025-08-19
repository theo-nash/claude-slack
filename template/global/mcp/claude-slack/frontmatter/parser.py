#!/usr/bin/env python3
"""
Frontmatter Parser for Claude-Slack
Parses agent markdown files to extract channel subscriptions and preferences
"""

import re
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class FrontmatterParser:
    """Parse and extract frontmatter from Claude agent files"""
    
    @staticmethod
    def parse_file(file_path: str) -> Dict[str, Any]:
        """
        Parse an agent file and extract frontmatter data
        
        Args:
            file_path: Path to the agent markdown file
            
        Returns:
            Dictionary containing parsed frontmatter data
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return FrontmatterParser.parse_content(content)
        except Exception as e:
            return {
                'error': f"Failed to parse file: {str(e)}",
                'name': Path(file_path).stem,
                'channels': ['general', 'announcements'],
                'direct_messages': True
            }
    
    @staticmethod
    def parse_content(content: str) -> Dict[str, Any]:
        """
        Parse content and extract frontmatter
        
        Args:
            content: File content as string
            
        Returns:
            Dictionary containing parsed frontmatter data
        """
        if not content.startswith('---'):
            return {
                'error': 'No frontmatter found',
                'channels': ['general', 'announcements'],
                'direct_messages': True
            }
        
        # Find the end of frontmatter
        lines = content.split('\n')
        end_index = -1
        
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_index = i
                break
        
        if end_index == -1:
            return {
                'error': 'Invalid frontmatter format',
                'channels': ['general', 'announcements'],
                'direct_messages': True
            }
        
        # Extract frontmatter lines
        frontmatter_lines = '\n'.join(lines[1:end_index])
        
        try:
            # Parse as YAML
            frontmatter = yaml.safe_load(frontmatter_lines) or {}
        except yaml.YAMLError as e:
            # Fallback to simple parsing
            frontmatter = FrontmatterParser._simple_parse(frontmatter_lines)
        
        # Extract and normalize data
        return FrontmatterParser._normalize_agent_data(frontmatter)
    
    @staticmethod
    def _simple_parse(text: str) -> Dict[str, Any]:
        """
        Simple fallback parser for frontmatter
        
        Args:
            text: Frontmatter text
            
        Returns:
            Parsed dictionary
        """
        result = {}
        current_key = None
        current_value = []
        
        for line in text.split('\n'):
            # Check if line is a key
            if ':' in line and not line.startswith(' '):
                if current_key:
                    result[current_key] = FrontmatterParser._parse_value(current_value)
                
                parts = line.split(':', 1)
                current_key = parts[0].strip()
                remainder = parts[1].strip() if len(parts) > 1 else ''
                
                if remainder:
                    # Single line value
                    result[current_key] = FrontmatterParser._parse_value([remainder])
                    current_key = None
                else:
                    current_value = []
            elif current_key and line.strip():
                # Multi-line value
                current_value.append(line)
        
        # Handle last key
        if current_key:
            result[current_key] = FrontmatterParser._parse_value(current_value)
        
        return result
    
    @staticmethod
    def _parse_value(lines: List[str]) -> Any:
        """Parse a value from lines"""
        if not lines:
            return None
        
        # Join lines
        text = '\n'.join(lines).strip()
        
        # Check for list format
        if any(line.strip().startswith('- ') for line in lines):
            # Parse as list
            items = []
            for line in lines:
                line = line.strip()
                if line.startswith('- '):
                    items.append(line[2:].strip())
            return items
        
        # Check for bracketed list [item1, item2]
        if text.startswith('[') and text.endswith(']'):
            try:
                # Remove brackets and split
                items = text[1:-1].split(',')
                return [item.strip() for item in items]
            except:
                pass
        
        # Return as string
        return text
    
    @staticmethod
    def _normalize_agent_data(frontmatter: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize and validate agent data from frontmatter
        Supports both old (flat) and new (scoped) channel formats
        
        Args:
            frontmatter: Raw frontmatter dictionary
            
        Returns:
            Normalized agent data with scoped channels
        """
        # Extract basic fields
        agent_data = {
            'name': frontmatter.get('name', 'unknown'),
            'description': frontmatter.get('description', ''),
            'tools': frontmatter.get('tools', 'All')
        }
        
        # Extract channels - support both old and new formats
        channels = frontmatter.get('channels', {'global': ['general', 'announcements'], 'project': []})
        
        if isinstance(channels, str):
            # String format: "[general, announcements]"
            if channels.startswith('[') and channels.endswith(']'):
                channel_list = [c.strip().lstrip('#') for c in channels[1:-1].split(',')]
            else:
                channel_list = [channels.lstrip('#').strip()]
            # Old format - treat as global channels
            agent_data['channels'] = {
                'global': channel_list,
                'project': []
            }
        elif isinstance(channels, list):
            # Old flat list format - treat as global channels
            agent_data['channels'] = {
                'global': [c.lstrip('#').strip() for c in channels],
                'project': []
            }
        elif isinstance(channels, dict):
            # New scoped format
            global_channels = channels.get('global', ['general', 'announcements'])
            project_channels = channels.get('project', [])
            
            # Ensure they're lists
            if isinstance(global_channels, str):
                global_channels = [global_channels]
            if isinstance(project_channels, str):
                project_channels = [project_channels]
            
            # Clean channel names
            agent_data['channels'] = {
                'global': [c.lstrip('#').strip() for c in global_channels] if isinstance(global_channels, list) else [],
                'project': [c.lstrip('#').strip() for c in project_channels] if isinstance(project_channels, list) else []
            }
        else:
            # Default channels
            agent_data['channels'] = {
                'global': ['general', 'announcements'],
                'project': []
            }
        
        # Extract direct messages preference
        dm_pref = frontmatter.get('direct_messages', 'enabled')
        agent_data['direct_messages'] = dm_pref != 'disabled'
        
        # Extract message preferences
        msg_prefs = frontmatter.get('message_preferences', {})
        if isinstance(msg_prefs, dict):
            # Support scoped auto-subscribe patterns
            auto_patterns = msg_prefs.get('auto_subscribe_patterns', [])
            if isinstance(auto_patterns, dict):
                agent_data['auto_subscribe_patterns'] = auto_patterns
            elif isinstance(auto_patterns, list):
                # Old format - treat as global
                agent_data['auto_subscribe_patterns'] = {
                    'global': auto_patterns,
                    'project': []
                }
            else:
                agent_data['auto_subscribe_patterns'] = {'global': [], 'project': []}
            
            agent_data['muted_channels'] = msg_prefs.get('muted_channels', [])
            agent_data['dm_scope_preference'] = msg_prefs.get('dm_scope_preference', 'project')
        else:
            agent_data['auto_subscribe_patterns'] = {'global': [], 'project': []}
            agent_data['muted_channels'] = []
            agent_data['dm_scope_preference'] = 'project'
        
        return agent_data
    
    @staticmethod
    def get_agent_channels(agent_name: str, claude_dir: str = '.claude') -> Dict[str, List[str]]:
        """
        Get scoped channels for a specific agent
        
        Args:
            agent_name: Name of the agent
            claude_dir: Path to .claude directory
            
        Returns:
            Dictionary with 'global' and 'project' channel lists
        """
        agent_file = Path(claude_dir) / 'agents' / f'{agent_name}.md'
        
        if not agent_file.exists():
            return {
                'global': ['general', 'announcements'],
                'project': []
            }
        
        agent_data = FrontmatterParser.parse_file(str(agent_file))
        channels = agent_data.get('channels', {})
        
        # Ensure it's the scoped format
        if isinstance(channels, dict):
            return channels
        elif isinstance(channels, list):
            # Old format - convert to scoped
            return {
                'global': channels,
                'project': []
            }
        else:
            return {
                'global': ['general', 'announcements'],
                'project': []
            }
    
    @staticmethod
    def get_all_agents(claude_dir: str = '.claude') -> List[Dict[str, Any]]:
        """
        Get all agents and their configurations
        
        Args:
            claude_dir: Path to .claude directory
            
        Returns:
            List of agent configurations
        """
        agents_dir = Path(claude_dir) / 'agents'
        
        if not agents_dir.exists():
            return []
        
        agents = []
        for agent_file in agents_dir.glob('*.md'):
            if agent_file.stem.startswith('_'):
                continue
            
            agent_data = FrontmatterParser.parse_file(str(agent_file))
            agent_data['file'] = agent_file.stem
            agents.append(agent_data)
        
        return agents


if __name__ == '__main__':
    # Test the parser
    import sys
    
    if len(sys.argv) > 1:
        # Parse a specific file
        file_path = sys.argv[1]
        result = FrontmatterParser.parse_file(file_path)
        print(json.dumps(result, indent=2))
    else:
        # Parse all agents
        agents = FrontmatterParser.get_all_agents()
        for agent in agents:
            print(f"\nAgent: {agent['name']}")
            print(f"  Channels: {', '.join(agent['channels'])}")
            print(f"  Direct Messages: {'Enabled' if agent['direct_messages'] else 'Disabled'}")