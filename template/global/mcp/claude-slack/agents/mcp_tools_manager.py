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

try:
    from frontmatter.parser import FrontmatterParser
except ImportError:
    # If parser not available, we'll need to handle it
    FrontmatterParser = None

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
                'mcp__claude-slack__join_channel',           # Replaces subscribe_to_channel
                'mcp__claude-slack__leave_channel',          # Replaces unsubscribe_from_channel
                'mcp__claude-slack__invite_to_channel',      # New unified API
                'mcp__claude-slack__list_my_channels',       # Replaces get_my_subscriptions
                'mcp__claude-slack__search_messages',
                'mcp__claude-slack__get_current_project',
                'mcp__claude-slack__list_projects',
                'mcp__claude-slack__list_agents',
                'mcp__claude-slack__create_channel',
                'mcp__claude-slack__get_linked_projects',
                'mcp__claude-slack__list_channel_members',
                # Agent Notes Tools
                'mcp__claude-slack__write_note',
                'mcp__claude-slack__search_my_notes',
                'mcp__claude-slack__get_recent_notes',
                'mcp__claude-slack__peek_agent_notes'
            ]
        
        return slack_tools
    
    @staticmethod
    def get_agent_id_instruction(agent_name: str) -> str:
        """
        Get the agent ID instruction text for an agent.
        
        Args:
            agent_name: Name of the agent (file stem)
            
        Returns:
            The instruction text to append to agent file
        """
        return f"""

## Claude-Slack Integration

When using any claude-slack MCP tools (tools starting with `mcp__claude-slack__`), you MUST provide your agent_id.
Your agent_id is: {agent_name}

Always use this exact agent_id when calling claude-slack tools that require an agent_id parameter."""
    
    @staticmethod
    def ensure_agent_has_id_instruction(agent_file_path: str, agent_name: str = None) -> bool:
        """
        Ensure an agent file has the agent_id instruction at the end.
        
        Args:
            agent_file_path: Path to the agent .md file
            agent_name: Optional agent name from frontmatter. If not provided, will parse it.
            
        Returns:
            True if instruction was added, False if already present or error
        """
        logger = MCPToolsManager._get_logger()
        
        agent_path = Path(agent_file_path)
        if not agent_path.exists():
            return False
        
        try:
            # Get agent name from frontmatter if not provided
            if not agent_name:
                if FrontmatterParser:
                    agent_data = FrontmatterParser.parse_file(str(agent_path))
                    agent_name = agent_data.get('name', agent_path.stem)
                else:
                    agent_name = agent_path.stem
            
            with open(agent_path, 'r') as f:
                content = f.read()
            
            # Check if agent_id instruction already exists
            agent_id_marker = f"Your agent_id is: {agent_name}"
            if agent_id_marker in content:
                return False
            
            # Add agent_id instruction at the end
            agent_id_instruction = MCPToolsManager.get_agent_id_instruction(agent_name)
            new_content = content.rstrip() + agent_id_instruction
            
            with open(agent_path, 'w') as f:
                f.write(new_content)
            
            logger.info(f"Added agent_id instruction to {agent_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding agent_id instruction to {agent_name}: {e}")
            return False
    
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
        
        # Get MCP tools list
        slack_tools = MCPToolsManager.get_default_mcp_tools(config_manager)
        
        try:
            # Use parser if available, otherwise fall back to simple parsing
            if FrontmatterParser:
                # Parse the agent file using FrontmatterParser
                agent_data = FrontmatterParser.parse_file(str(agent_path))
                
                # Get agent name from frontmatter
                agent_name = agent_data.get('name', agent_path.stem)
                
                # Check if there was an error parsing
                if 'error' in agent_data:
                    logger.debug(f"Error parsing {agent_name}: {agent_data['error']}")
                    return False
                
                # Get the parsed tools
                existing_tools = agent_data.get('tools', 'All')
                
                # If tools is 'All' or '*', agent already has full access
                if existing_tools == 'All':
                    logger.debug(f"Agent {agent_name} already has full tool access")
                    # Still check if agent_id instruction needs to be added
                    return MCPToolsManager.ensure_agent_has_id_instruction(str(agent_path), agent_name)
                
                # Ensure existing_tools is a list
                if not isinstance(existing_tools, list):
                    existing_tools = []
                
                # Check if slack tools already present
                missing_tools = [tool for tool in slack_tools if tool not in existing_tools]
                
                if not missing_tools:
                    logger.debug(f"Agent {agent_name} already has all MCP tools")
                    # Still check if agent_id instruction needs to be added
                    return MCPToolsManager.ensure_agent_has_id_instruction(str(agent_path), agent_name)
                
                # Need to update the file - read original content
                with open(agent_path, 'r') as f:
                    content = f.read()
                
                lines = content.split('\n')
                
                # Find frontmatter boundaries
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
                for i in range(1, end_index):
                    if lines[i].startswith('tools:'):
                        tools_line_index = i
                        break
                
                # Add missing tools
                all_tools = existing_tools + missing_tools
                
                # Format tools line as comma-separated list (Anthropic standard format)
                tools_line = f"tools: {', '.join(all_tools)}"
                
                # Find where to insert (replace existing tools section)
                if tools_line_index != -1:
                    # Find end of tools section (handle multi-line format if present)
                    tools_end = tools_line_index + 1
                    while tools_end < end_index:
                        if lines[tools_end].startswith('  - ') or (lines[tools_end].strip() == '' and tools_end + 1 < end_index and lines[tools_end + 1].startswith('  - ')):
                            tools_end += 1
                        else:
                            break
                    
                    # Replace the tools section with single line
                    lines = lines[:tools_line_index] + [tools_line] + lines[tools_end:]
                else:
                    # Add tools before the closing ---
                    lines = lines[:end_index] + [tools_line] + lines[end_index:]
                
                # Write back
                new_content = '\n'.join(lines)
                
                # Check if agent_id instruction already exists
                agent_id_marker = f"Your agent_id is: {agent_name}"
                if agent_id_marker not in new_content:
                    # Add agent_id instruction at the end
                    agent_id_instruction = MCPToolsManager.get_agent_id_instruction(agent_name)
                    new_content = new_content.rstrip() + agent_id_instruction
                    logger.info(f"Added agent_id instruction to {agent_name}")
                
                with open(agent_path, 'w') as f:
                    f.write(new_content)
                
                logger.info(f"Added {len(missing_tools)} MCP tools to agent {agent_name}")
                return True
                
            else:
                # Fallback to original implementation if parser not available
                logger.warning("FrontmatterParser not available, using fallback parsing")
                # ... original implementation would go here ...
                # For now, just return False
                return False
            
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