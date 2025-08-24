#!/usr/bin/env python3
"""
Agent Discovery Service for Claude-Slack V3

Service for discovering agents from various sources (filesystem).
Separate from registration/management logic - pure discovery only.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from frontmatter.parser import FrontmatterParser
from projects.mcp_tools_manager import MCPToolsManager

try:
    from log_manager import get_logger
except ImportError:
    def get_logger(name, component=None):
        return logging.getLogger(name)


@dataclass
class DiscoveredAgent:
    """Represents a discovered agent before registration"""
    name: str
    description: str
    scope: str  # 'global' or 'project'
    source_path: str  # Where we found it (.claude directory)
    file_path: str  # Full path to the .md file
    channels: Dict[str, List[str]] = field(default_factory=dict)  # Includes 'global', 'project', 'exclude' keys
    tools: List[str] = field(default_factory=list)
    dm_policy: str = 'open'  # DM policy setting
    discoverable: str = 'public'  # Discoverability setting
    metadata: Dict[str, Any] = field(default_factory=dict)  # Full frontmatter data
    
    def get_exclusions(self) -> List[str]:
        """Get list of excluded channel names"""
        return self.channels.get('exclude', [])
    
    def excludes_all_defaults(self) -> bool:
        """Check if agent opts out of all defaults"""
        return self.channels.get('never_default', False)
    
    def get_global_channels(self) -> List[str]:
        """Get list of explicit global channel subscriptions"""
        return self.channels.get('global', [])
    
    def get_project_channels(self) -> List[str]:
        """Get list of explicit project channel subscriptions"""
        return self.channels.get('project', [])


@dataclass
class DiscoveryResult:
    """Result of agent discovery operation"""
    global_agents: List[DiscoveredAgent] = field(default_factory=list)
    project_agents: Dict[str, List[DiscoveredAgent]] = field(default_factory=dict)  # project_id -> agents
    errors: List[Dict[str, str]] = field(default_factory=list)  # List of errors encountered
    
    @property
    def total_agents(self) -> int:
        """Total number of agents discovered"""
        total = len(self.global_agents)
        for agents in self.project_agents.values():
            total += len(agents)
        return total
    
    def get_all_agents(self) -> List[DiscoveredAgent]:
        """Get all agents as a flat list"""
        all_agents = list(self.global_agents)
        for agents in self.project_agents.values():
            all_agents.extend(agents)
        return all_agents


class AgentDiscoveryService:
    """
    Service for discovering agents from various sources.
    Separate from registration/management logic - this is pure discovery.
    """
    
    def __init__(self):
        """Initialize the discovery service"""
        self.logger = get_logger('AgentDiscoveryService', component='discovery')
    
    async def discover_project_agents(self, project_path: str) -> List[DiscoveredAgent]:
        """
        Discover agents in a specific project.
        
        Args:
            project_path: Path to the project directory
            
        Returns:
            List of discovered agents
        """
        agents = []
        claude_dir = Path(project_path) / '.claude'
        
        if not claude_dir.exists():
            self.logger.debug(f"No .claude directory in project: {project_path}")
            return agents
        
        agents_dir = claude_dir / 'agents'
        if not agents_dir.exists():
            self.logger.debug(f"No agents directory in: {claude_dir}")
            return agents
        
        self.logger.info(f"Discovering agents in: {agents_dir}")
        
        for agent_file in agents_dir.glob('*.md'):
            if agent_file.stem.startswith('_'):
                # Skip files starting with underscore (templates, examples, etc.)
                continue
            
            try:
                # Ensure agent has MCP tools before parsing
                MCPToolsManager.ensure_agent_has_mcp_tools(str(agent_file))
                
                agent = self._parse_agent_file(
                    file_path=str(agent_file),
                    scope='project',
                    source_path=str(claude_dir)
                )
                if agent:
                    agents.append(agent)
                    self.logger.debug(f"Discovered project agent: {agent.name}")
            except Exception as e:
                self.logger.error(f"Failed to parse agent file {agent_file}: {e}")
        
        self.logger.info(f"Discovered {len(agents)} agents in project {project_path}")
        return agents
    
    async def discover_global_agents(self) -> List[DiscoveredAgent]:
        """
        Discover agents in the global Claude directory.
        
        Returns:
            List of discovered global agents
        """
        agents = []
        
        # Get global Claude directory
        claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
        claude_dir = Path(claude_config_dir)
        
        if not claude_dir.exists():
            self.logger.debug(f"No global Claude directory at: {claude_dir}")
            return agents
        
        agents_dir = claude_dir / 'agents'
        if not agents_dir.exists():
            self.logger.debug(f"No global agents directory at: {agents_dir}")
            return agents
        
        self.logger.info(f"Discovering global agents in: {agents_dir}")
        
        for agent_file in agents_dir.glob('*.md'):
            if agent_file.stem.startswith('_'):
                # Skip files starting with underscore
                continue
            
            try:
                # Ensure agent has MCP tools before parsing
                MCPToolsManager.ensure_agent_has_mcp_tools(str(agent_file))
                
                agent = self._parse_agent_file(
                    file_path=str(agent_file),
                    scope='global',
                    source_path=str(claude_dir)
                )
                if agent:
                    agents.append(agent)
                    self.logger.debug(f"Discovered global agent: {agent.name}")
            except Exception as e:
                self.logger.error(f"Failed to parse agent file {agent_file}: {e}")
        
        self.logger.info(f"Discovered {len(agents)} global agents")
        return agents
    
    async def discover_all_agents(self, project_paths: Optional[List[str]] = None) -> DiscoveryResult:
        """
        Discover all agents from all sources.
        
        Args:
            project_paths: Optional list of project paths to search
            
        Returns:
            DiscoveryResult with all discovered agents
        """
        result = DiscoveryResult()
        
        # Discover global agents
        try:
            result.global_agents = await self.discover_global_agents()
        except Exception as e:
            self.logger.error(f"Error discovering global agents: {e}")
            result.errors.append({
                'source': 'global',
                'error': str(e)
            })
        
        # Discover project agents if paths provided
        if project_paths:
            for project_path in project_paths:
                try:
                    agents = await self.discover_project_agents(project_path)
                    if agents:
                        # Generate a simple project ID from path
                        project_id = self._generate_project_id(project_path)
                        result.project_agents[project_id] = agents
                except Exception as e:
                    self.logger.error(f"Error discovering agents in {project_path}: {e}")
                    result.errors.append({
                        'source': project_path,
                        'error': str(e)
                    })
        
        self.logger.info(f"Discovery complete: {result.total_agents} agents found")
        return result
    
    async def discover_single_agent(self, agent_file_path: str) -> Optional[DiscoveredAgent]:
        """
        Discover a single agent from a specific file.
        
        Args:
            agent_file_path: Path to the agent's .md file
            
        Returns:
            DiscoveredAgent or None if not found/invalid
        """
        agent_path = Path(agent_file_path)
        
        if not agent_path.exists():
            self.logger.warning(f"Agent file not found: {agent_file_path}")
            return None
        
        # Determine scope based on path
        if '.claude' in str(agent_path):
            # Extract the .claude directory
            claude_dir = agent_path
            while claude_dir.name != '.claude' and claude_dir.parent != claude_dir:
                claude_dir = claude_dir.parent
            
            # Check if it's in home directory (global) or project
            home_dir = Path.home()
            if str(claude_dir.parent).startswith(str(home_dir / '.claude')):
                scope = 'global'
            else:
                scope = 'project'
            
            source_path = str(claude_dir)
        else:
            # Assume global if not in a .claude directory
            scope = 'global'
            source_path = str(agent_path.parent)
        
        return self._parse_agent_file(
            file_path=str(agent_path),
            scope=scope,
            source_path=source_path
        )
    
    def _parse_agent_file(self, file_path: str, scope: str, source_path: str) -> Optional[DiscoveredAgent]:
        """
        Parse an agent file and extract all metadata.
        
        Args:
            file_path: Path to the agent .md file
            scope: 'global' or 'project'
            source_path: Path to the source directory (.claude)
            
        Returns:
            DiscoveredAgent or None if parsing fails
        """
        try:
            # Use FrontmatterParser to parse the file
            agent_data = FrontmatterParser.parse_file(file_path)
            
            if 'error' in agent_data:
                self.logger.warning(f"Error parsing {file_path}: {agent_data['error']}")
                # Still try to extract what we can
            
            # Extract agent name (from frontmatter or filename)
            name = agent_data.get('name')
            if not name:
                name = Path(file_path).stem
                self.logger.debug(f"Using filename as agent name: {name}")
            
            # Extract channels configuration
            channels = agent_data.get('channels', {})
            if not isinstance(channels, dict):
                # Old format - convert to new
                if isinstance(channels, list):
                    channels = {
                        'global': channels,
                        'project': [],
                        'exclude': [],
                        'never_default': False
                    }
                else:
                    channels = {
                        'global': [],
                        'project': [],
                        'exclude': [],
                        'never_default': False
                    }
            
            # Ensure all keys exist
            channels.setdefault('global', [])
            channels.setdefault('project', [])
            channels.setdefault('exclude', [])
            channels.setdefault('never_default', False)
            
            # Extract tools
            tools = agent_data.get('tools', [])
            if isinstance(tools, str):
                if tools.lower() in ['all', '*']:
                    tools = ['*']
                else:
                    tools = [tools]
            elif not isinstance(tools, list):
                tools = []
            
            # Extract DM settings
            dm_policy = agent_data.get('dm_policy', 'open')
            if dm_policy not in ['open', 'restricted', 'closed']:
                dm_policy = 'open'
            
            discoverable = agent_data.get('discoverable', 'public')
            if discoverable not in ['public', 'project', 'private']:
                discoverable = 'public'
            
            # Create the DiscoveredAgent
            return DiscoveredAgent(
                name=name,
                description=agent_data.get('description', ''),
                scope=scope,
                source_path=source_path,
                file_path=file_path,
                channels=channels,
                tools=tools,
                dm_policy=dm_policy,
                discoverable=discoverable,
                metadata=agent_data  # Store full frontmatter for reference
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse agent file {file_path}: {e}")
            return None
    
    def _generate_project_id(self, project_path: str) -> str:
        """
        Generate a simple project ID from a path.
        
        Args:
            project_path: Path to the project
            
        Returns:
            Project ID (hash of the path)
        """
        import hashlib
        return hashlib.md5(project_path.encode()).hexdigest()[:8]


# Example usage
if __name__ == '__main__':
    import asyncio
    
    async def main():
        discovery = AgentDiscoveryService()
        
        # Test global agent discovery
        global_agents = await discovery.discover_global_agents()
        print(f"Found {len(global_agents)} global agents")
        for agent in global_agents:
            print(f"  - {agent.name}: {agent.description}")
            print(f"    Channels: {agent.get_global_channels()}")
            print(f"    Exclusions: {agent.get_exclusions()}")
        
        # Test project agent discovery if a path is provided
        if len(sys.argv) > 1:
            project_path = sys.argv[1]
            project_agents = await discovery.discover_project_agents(project_path)
            print(f"\nFound {len(project_agents)} project agents in {project_path}")
            for agent in project_agents:
                print(f"  - {agent.name}: {agent.description}")
                print(f"    Channels: {agent.get_project_channels()}")
                print(f"    DM Policy: {agent.dm_policy}")
    
    asyncio.run(main())