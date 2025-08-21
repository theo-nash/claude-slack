#!/usr/bin/env python3
"""
MCP Tools Manager for Claude-Slack

Ensures agents have the necessary MCP tools in their frontmatter.
This is used during project setup to add claude-slack MCP tools to agents.
"""

import os
from pathlib import Path
from typing import List, Optional

try:
    from log_manager import get_logger
except ImportError:
    # Fallback to standard logging if new logging system not available
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)

class MCPToolsManager:
    """Manages MCP tool additions to agent frontmatter"""
    
    # Class-level logger
    _logger = None
    
    @classmethod
    def _get_logger(cls):
        """Get or create the logger for this manager"""
        if cls._logger is None:
            cls._logger = get_logger('MCPToolsManager', component='manager')
        return cls._logger
    
    @staticmethod
    def get_default_mcp_tools(config_manager=None) -> List[str]:
        """
        Get the list of default MCP tools from config or use hardcoded defaults.
        
        Args:
            config_manager: Optional config manager instance
            
        Returns:
            List of MCP tool names with full prefix
        """
        slack_tools = []
        
        # Try to get from config
        if config_manager:
            try:
                config = config_manager.load_config()
                # Get tool names from config and add prefix
                tool_names = config.get('default_mcp_tools', [])
                slack_tools = [f'mcp__claude-slack__{tool}' for tool in tool_names]
            except Exception:
                pass
        
        # Fallback to hardcoded list if config unavailable
        if not slack_tools:
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
                'mcp__claude-slack__get_linked_projects',
                # Agent Notes Tools
                'mcp__claude-slack__write_note',
                'mcp__claude-slack__search_my_notes',
                'mcp__claude-slack__get_recent_notes',
                'mcp__claude-slack__peek_agent_notes'
            ]
        
        return slack_tools
    
    @staticmethod
    def ensure_agent_has_mcp_tools(agent_file_path: str, config_manager=None) -> bool:
        """
        Ensure an agent has access to claude-slack MCP tools.
        
        This adds the MCP tools to the agent's frontmatter if they don't already have them
        and don't have 'All' tools access.
        
        Args:
            agent_file_path: Path to the agent .md file
            config_manager: Optional config manager for getting tool list
            
        Returns:
            True if tools were added, False if already present or agent not found
        """
        logger = MCPToolsManager._get_logger()
        
        agent_path = Path(agent_file_path)
        if not agent_path.exists():
            logger.debug(f"Agent file not found: {agent_file_path}")
            return False
        
        agent_name = agent_path.stem
        
        # Get MCP tools list
        slack_tools = MCPToolsManager.get_default_mcp_tools(config_manager)
        
        try:
            with open(agent_path, 'r') as f:
                content = f.read()
            
            if not content.startswith('---'):
                logger.debug(f"No frontmatter in {agent_name}")
                return False
            
            # Find frontmatter boundaries
            lines = content.split('\n')
            end_index = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end_index = i
                    break
            
            if end_index == -1:
                logger.debug(f"Invalid frontmatter in {agent_name}")
                return False
            
            # Find tools line
            tools_line_index = -1
            tools_value = None
            for i in range(1, end_index):
                if lines[i].startswith('tools:'):
                    tools_line_index = i
                    tools_value = lines[i].split(':', 1)[1].strip()
                    break
            
            # If no tools or "All"/"*", agent already has access
            if tools_line_index == -1 or tools_value in ['All', 'all', '"All"', "'All'", '*', '"*"', "'*'"]:
                logger.debug(f"Agent {agent_name} already has full tool access")
                return False
            
            # Parse existing tools
            existing_tools = []
            if tools_value:
                if tools_value.startswith('[') and tools_value.endswith(']'):
                    # List format: tools: [tool1, tool2]
                    tools_str = tools_value[1:-1]
                    existing_tools = [t.strip().strip('"').strip("'") for t in tools_str.split(',') if t.strip()]
                elif tools_value.startswith('-'):
                    # Multi-line format already, parse following lines
                    existing_tools = []
                    for j in range(tools_line_index + 1, end_index):
                        if lines[j].strip().startswith('- '):
                            tool = lines[j].strip()[2:].strip()
                            existing_tools.append(tool)
                        elif lines[j].strip() and not lines[j].startswith(' '):
                            break
                else:
                    # Single tool or comma-separated
                    existing_tools = [t.strip() for t in tools_value.split(',') if t.strip()]
            
            # Check if slack tools already present
            missing_tools = [tool for tool in slack_tools if tool not in existing_tools]
            
            if not missing_tools:
                logger.debug(f"Agent {agent_name} already has all MCP tools")
                return False
            
            # Add missing tools
            all_tools = existing_tools + missing_tools
            
            # Format tools line - always use multi-line for clarity
            tools_lines = ['tools:']
            for tool in all_tools:
                tools_lines.append(f'  - {tool}')
            
            # Find where to insert (replace existing tools section)
            if tools_line_index != -1:
                # Find end of tools section
                tools_end = tools_line_index + 1
                while tools_end < end_index:
                    if lines[tools_end].startswith('  - ') or (lines[tools_end].strip() == '' and tools_end + 1 < end_index and lines[tools_end + 1].startswith('  - ')):
                        tools_end += 1
                    else:
                        break
                
                # Replace the tools section
                lines = lines[:tools_line_index] + tools_lines + lines[tools_end:]
            else:
                # Add tools before the closing ---
                lines = lines[:end_index] + tools_lines + lines[end_index:]
            
            # Write back
            new_content = '\n'.join(lines)
            with open(agent_path, 'w') as f:
                f.write(new_content)
            
            logger.info(f"Added {len(missing_tools)} MCP tools to agent {agent_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating agent {agent_name} with MCP tools: {e}")
            return False
    
    @staticmethod
    async def ensure_all_agents_have_mcp_tools(claude_dir: str, config_manager=None) -> int:
        """
        Ensure all agents in a directory have MCP tools.
        
        Args:
            claude_dir: Path to .claude directory
            config_manager: Optional config manager
            
        Returns:
            Number of agents updated
        """
        logger = MCPToolsManager._get_logger()
        agents_dir = Path(claude_dir) / 'agents'
        
        if not agents_dir.exists():
            logger.debug(f"No agents directory at: {agents_dir}")
            return 0
        
        updated_count = 0
        for agent_file in agents_dir.glob('*.md'):
            if MCPToolsManager.ensure_agent_has_mcp_tools(str(agent_file), config_manager):
                updated_count += 1
        
        if updated_count > 0:
            logger.info(f"Updated {updated_count} agents with MCP tools")
        
        return updated_count