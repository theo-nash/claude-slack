#!/usr/bin/env python3
"""
Project Setup Manager for Claude-Slack

Orchestrates project initialization and setup using other managers.
This manager handles the complete workflow of setting up a new project,
including creating channels, registering agents, and applying subscriptions.

This is the high-level orchestrator that uses:
- SessionManager for project registration
- ChannelManager for channel creation  
- SubscriptionManager for agent subscriptions
"""

import os
import sys
import json
import hashlib
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from sessions.manager import SessionManager
    from channels.manager import ChannelManager
    from subscriptions.manager import SubscriptionManager
    from frontmatter.parser import FrontmatterParser
    from db.manager import DatabaseManager
    from db.initialization import DatabaseInitializer, ensure_db_initialized
except ImportError as e:
    print(f"Import error in ProjectSetupManager: {e}", file=sys.stderr)
    SessionManager = None
    ChannelManager = None
    SubscriptionManager = None
    FrontmatterParser = None
    DatabaseManager = None
    DatabaseInitializer = None
    ensure_db_initialized = None

try:
    from log_manager import get_logger
except ImportError:
    # Fallback to standard logging if new logging system not available
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)
    
try:
    from config_manager import get_config_manager
except ImportError:
    get_config_manager = None

try:
    from projects.mcp_tools_manager import MCPToolsManager
except ImportError:
    MCPToolsManager = None


class ProjectSetupManager(DatabaseInitializer if DatabaseInitializer else object):
    """
    Orchestrates project setup and initialization.
    
    This manager coordinates the setup of new projects, handling:
    - Default channel creation
    - Agent discovery and registration
    - Default subscription application
    - Project linking
    """
    
    def __init__(self, db_path: str):
        """
        Initialize ProjectSetupManager with required managers.
        
        Args:
            db_path: Path to SQLite database
        """
        # Initialize parent class if it exists
        if DatabaseInitializer:
            super().__init__()
        
        self.db_path = db_path
        self.logger = get_logger('ProjectSetupManager', component='manager')
        
        # Initialize component managers
        self.db_manager = DatabaseManager(db_path) if DatabaseManager else None
        self.session_manager = SessionManager(db_path) if SessionManager else None
        self.channel_manager = ChannelManager(db_path) if ChannelManager else None
        self.subscription_manager = SubscriptionManager(db_path) if SubscriptionManager else None
        
        # Load configuration
        self.config = self._load_config()
    
    def _add_agent_id_instructions(self, agent_file_path: str, agent_name: str) -> bool:
        """
        Add agent_id instructions to an agent's .md file if not already present.
        This helps subagents quickly identify themselves when calling claude-slack MCP tools.
        
        Args:
            agent_file_path: Path to the agent's .md file
            agent_name: The agent's name (to be used as agent_id)
            
        Returns:
            True if instructions were added or already present, False on error
        """
        try:
            # Read the existing file content
            with open(agent_file_path, 'r') as f:
                content = f.read()
            
            # Check if agent_id instructions already exist
            agent_id_marker = "## Claude-Slack Agent ID"
            if agent_id_marker in content:
                self.logger.debug(f"Agent ID instructions already present in {agent_file_path}")
                return True
            
            # Prepare the agent_id section
            agent_id_section = f"""

## Claude-Slack Agent ID

When using claude-slack MCP tools, always use the following agent_id:
```
agent_id: {agent_name}
```

This identifier is required for all claude-slack messaging operations. Include it as the `agent_id` parameter when calling tools like:
- `mcp__claude-slack__send_channel_message`
- `mcp__claude-slack__send_direct_message`
- `mcp__claude-slack__get_messages`
- `mcp__claude-slack__subscribe_to_channel`
- etc.

Example usage:
```javascript
await mcp__claude-slack__send_channel_message({{
    agent_id: "{agent_name}",
    channel_id: "general",
    content: "Hello from {agent_name}!"
}})
```
"""
            
            # Append the section to the file
            with open(agent_file_path, 'a') as f:
                f.write(agent_id_section)
            
            self.logger.info(f"Added agent_id instructions to {agent_file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add agent_id instructions to {agent_file_path}: {e}")
            return False
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from ConfigManager or use defaults"""
        config = {
            'default_channels': {
                'global': [
                    {'name': 'general', 'description': 'General discussion'},
                    {'name': 'announcements', 'description': 'System announcements'}
                ],
                'project': [
                    {'name': 'general', 'description': 'General project discussion'},
                    {'name': 'dev', 'description': 'Development discussion'}
                ]
            },
            'settings': {
                'default_agent_subscriptions': {
                    'global': ['general', 'announcements'],
                    'project': ['general', 'dev']
                },
                'auto_create_channels': True,
                'auto_link_projects': True,
                'message_retention_days': 30,
                'max_message_length': 4000
            },
            'project_links': []
        }
        
        if get_config_manager:
            try:
                config_manager = get_config_manager()
                loaded_config = config_manager.load_config()
                
                # Properly merge configuration
                if 'default_channels' in loaded_config:
                    config['default_channels'] = loaded_config['default_channels']
                
                if 'settings' in loaded_config:
                    config['settings'].update(loaded_config['settings'])
                
                if 'project_links' in loaded_config:
                    config['project_links'] = loaded_config['project_links']
                    
            except Exception as e:
                self.logger.warning(f"Failed to load config: {e}")
        
        return config
    
    async def setup_new_project(self, project_path: str,
                                project_id: str,
                               project_name: Optional[str] = None,
                               session_id: Optional[str] = None,
                               create_channels: bool = True,
                               register_agents: bool = True) -> Dict[str, Any]:
        """
        Complete setup workflow for a new project.
        
        This orchestrates the entire project setup:
        1. Create default channels with ChannelManager
        2. Discover and register agents
        3. Apply default subscriptions with SubscriptionManager
        4. Set up project links if configured
        
        Args:
            project_path: Absolute path to project
            project_name: Human-readable project name
            session_id: Optional session ID to associate
            create_channels: Whether to create default channels
            register_agents: Whether to discover and register agents
            
        Returns:
            Dictionary with setup results
        """
        results = {
            'channels_created': [],
            'agents_registered': [],
            'errors': []
        }
        
        self.logger.info(f"Setting up new project: {project_path}")
        
        try:               
            # Step 1: Create default channels
            if create_channels and self.channel_manager:                
                # Create project channels
                try:
                    project_channels = await self.channel_manager.apply_default_channels(
                        scope='project',
                        project_id=project_id,
                        created_by='system'
                    )
                    results['channels_created'] = project_channels
                    self.logger.debug(f"Created {len(project_channels)} default project channels")
                except Exception as e:
                    self.logger.warning(f"Failed to create project channels: {e}")
                            
            # Step 2: Discover and register agents
            if register_agents:
                project_agents = await self.discover_project_agents(project_path, project_id)
                
                #Register agents and setup subscription sync/defaults
                registered_agents = await self.setup_agents(
                    agents=project_agents,
                    scope="project",
                    project_id=project_id,
                    base_path=project_path
                )
                
                #Always register the default assistant with default subscriptions
                try:
                    success = await self.register_agent("assistant", project_id, "Main/default assistant agent for the project")
                    registered_agents.append("assistant")
                    
                    if success:
                        self.logger.debug(f"Successfully registered assistant agent for project {project_id}")
                    else:
                        self.logger.warning(f"Failed to register assistant agent for project {project_id}")
                except Exception as e:
                    self.logger.warning(f"Failed to register assistant agent: {e}")
                
                await self.subscription_manager.apply_default_subscriptions("assistant", project_id)
                
                results['agents_registered'] = registered_agents
            
            # Step 3: Set up project links if configured
            if self.config.get('auto_link_projects'):
                await self.setup_project_links(project_id, project_path)
            
            self.logger.info(f"Project setup complete: {project_name}")
            
        except Exception as e:
            self.logger.error(f"Error setting up project: {e}")
            results['errors'].append(f"Setup error: {e}")
        
        return results
    
    async def discover_project_agents(self, project_path: str, project_id: str) -> List[Dict[str, str]]:
        """
        Discover and register agents in a project.
        Registers them with the claude-code system.
        Syncs subscriptions from frontmatter.
        Applied default subscriptions if none present in frontmatter.
        
        Uses FrontmatterParser.get_all_agents() to discover and parse all agents.
        
        Args:
            project_path: Path to project directory
            project_id: Project ID
            
        Returns:
            List of agent configurations
        """        
        if not FrontmatterParser:
            self.logger.warning("FrontmatterParser not available")
            return []
        
        # Use FrontmatterParser to discover all agents
        claude_dir = Path(project_path) / '.claude'
        if not claude_dir.exists():
            self.logger.debug(f"No .claude directory in project: {project_path}")
            return []
        
        self.logger.info(f"Discovering agents using FrontmatterParser in: {claude_dir}")
        
        # Get all agents with their parsed metadata
        discovered_agents = FrontmatterParser.get_all_agents(str(claude_dir))
        
        self.logger.info(f"Discovered {len(discovered_agents)} agents in project {project_path}")
        
        return discovered_agents
    
    async def discover_global_agents(self) -> List[Dict[str, str]]:
        """
        Discover and register agents in the global Claude directory.
        
        Uses FrontmatterParser.get_all_agents() to discover and parse all agents.
        
        Returns:
            List of global agent configurations
        """
        if not FrontmatterParser:
            self.logger.warning("FrontmatterParser not available for global agent discovery")
            return []
        
        # Get global Claude directory
        claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
        
        self.logger.info(f"Discovering global agents using FrontmatterParser in: {claude_config_dir}")
        
        # Get all agents with their parsed metadata
        discovered_agents = FrontmatterParser.get_all_agents(claude_config_dir)
        
        self.logger.info(f"Discovered {len(discovered_agents)} global agents in {claude_config_dir}")
        
        return discovered_agents
            
    async def setup_agents(self, agents: List[Dict[str,str]], scope: str, project_id: Optional[str], base_path: str):
        """
        Sets up a group of agents with proper registration and default subscriptions
        """
        successful_agents = []
        
        for agent_data in agents:
            agent_name = agent_data.get('name', agent_data.get('file', 'unknown'))
            claude_dir = Path(base_path) / '.claude' if '.claude' not in base_path else Path(base_path)
            agent_file_path = claude_dir / 'agents' / f'{agent_data.get('file', agent_name)}.md'
            agent_project_id = project_id if scope == "project" else None
            
            try:
                # Log parsed metadata
                channels = agent_data.get('channels', {})
                self.logger.debug(f"Setting up {scope} agent {agent_name}: "
                                f"global_channels={channels.get('global', [])}, "
                                f"project_channels={channels.get('project', [])}, "
                                f"tools={agent_data.get('tools', 'unknown')}")
                
                # Ensure agent has MCP tools  
                if MCPToolsManager:
                    config_mgr = get_config_manager() if get_config_manager else None
                    tools_added = MCPToolsManager.ensure_agent_has_mcp_tools(str(agent_file_path), config_mgr)
                    if tools_added:
                        self.logger.info(f"Added MCP tools to {scope} agent: {agent_name}")
                
                # Add agent_id instructions to the agent file
                self._add_agent_id_instructions(str(agent_file_path), agent_name)
                
                # Register agent with proper description handling
                # Handle empty string descriptions (use fallback if empty or missing)
                description = agent_data.get('description', '')
                self.logger.debug(f"Agent {agent_name} - Raw description from data: '{description}'")
                if not description:
                    description = f'Agent {agent_name}'
                    self.logger.debug(f"Agent {agent_name} - Using fallback: '{description}'")
                else:
                    self.logger.debug(f"Agent {agent_name} - Using provided: '{description}'")
                
                success = await self.register_agent(
                    agent_name=agent_name,
                    project_id=agent_project_id,
                    description=description,
                    status='online'
                )
                
                if success:
                    successful_agents.append(agent_name)
                    self.logger.debug(f"Registered {scope} agent: {agent_name}")
                
                # Sync subscriptions from frontmatter
                await self.subscription_manager.sync_from_frontmatter(
                    agent_name=agent_name,
                    agent_project_id=agent_project_id,
                    agent_file_path=str(agent_file_path)
                )
                
                # Apply default subscriptions if needed
                await self.subscription_manager.apply_default_subscriptions(
                    agent_name=agent_name,
                    agent_project_id=agent_project_id,
                    force=False
                )
                    
            except Exception as e:
                self.logger.warning(f"Failed to register agent {agent_name}: {e}")
        
        return successful_agents
    
    @ensure_db_initialized
    async def register_agent(self, agent_name: str, project_id: str, description: str, status: str = 'online') -> bool:
        """
        Registers an agent in the database using DatabaseManager.
        This ensures the agent gets their notes channel auto-provisioned.
        """
        if not self.db_manager:
            self.logger.error("DatabaseManager not available")
            return False
        
        try:
            # Debug log what we're about to pass
            self.logger.debug(f"Calling DatabaseManager.register_agent with: agent_name='{agent_name}', description='{description}', project_id='{project_id}'")
            
            # Use DatabaseManager's register_agent which auto-provisions notes channel
            await self.db_manager.register_agent(
                agent_name=agent_name,
                description=description,
                project_id=project_id
            )
            
            # Update status if needed (register_agent sets it to 'online' by default)
            if status != 'online':
                await self.db_manager.update_agent_status(
                    agent_name=agent_name,
                    status=status,
                    project_id=project_id
                )
            
            self.logger.debug(f"Registered agent: {agent_name} (project_id: {project_id}) with notes channel")
            return True
                
        except Exception as e:
            self.logger.error(f"Error registering agent: {e}")
            return False
    
    async def setup_project_links(self, project_id: str, project_path: str) -> bool:
        """
        Set up project links based on configuration.
        
        Args:
            project_id: Project ID
            project_path: Project path
        Returns:
            True if successful
        """
        # This would handle project linking logic
        # For now, just log
        # TODO: Implement this logic
        self.logger.info(f"Would set up project links for: {project_id}")
        return True
    
    async def setup_global_environment(self, create_channels: bool = True, register_agents: bool = True) -> Dict[str, Any]:
        """
        Set up the global Claude environment.
        
        This ensures global channels exist and the assistant agent is registered.
        
        Returns:
            Dictionary with setup results
        """
        results = {
            'channels_created': [],
            'agents_registered': [],
            'errors': []
        }
        
        self.logger.info("Setting up global environment")
        
        try:
            if create_channels and self.channel_manager:
                # Create global channels
                try:
                    global_channels = await self.channel_manager.apply_default_channels(
                        scope='global',
                        created_by='system'
                    )
                    results['channels_created'] = global_channels
                    self.logger.debug(f"Created {len(global_channels)} default global channels")
                except Exception as e:
                    self.logger.warning(f"Failed to create global channels: {e}")
                
            if register_agents:
                global_agents = await self.discover_global_agents()

                #Register agents and setup subscription sync/defaults
                # Get global Claude directory
                claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
                registered_agents = await self.setup_agents(
                    agents=global_agents,
                    scope="global",
                    project_id=None,
                    base_path=claude_config_dir
                )
                results['agents_registered'] = registered_agents
                
            self.logger.info("Global environment setup complete")
            
        except Exception as e:
            self.logger.error(f"Error setting up global environment: {e}")
            results['errors'].append(f"Global setup error: {e}")
        
        return results
    
    @ensure_db_initialized
    async def initialize_session(self, session_id: str, cwd: str, 
                                transcript_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Initialize a new session with proper project detection and setup.
        
        This is the main entry point for session initialization, typically
        called from the SessionStart hook.
        
        Args:
            session_id: Claude session ID
            cwd: Current working directory
            transcript_path: Path to session transcript
            
        Returns:
            Dictionary with initialization results
        """
        results = {
            'session_registered': False,
            'project_id': None,
            'project_setup_performed': {},
            'global_setup_performed': {},
            'errors': []
        }
        
        self.logger.info(f"Initializing session: {session_id}")
        
        try:
            # Find project root from cwd or environment
            project_path = os.environ.get('CLAUDE_PROJECT_DIR')
            if not project_path and cwd:
                # Use cwd as project path if CLAUDE_PROJECT_DIR not set
                # This assumes we're in a project directory
                project_path = cwd
                self.logger.debug(f"Using cwd as project path: {project_path}")
            elif project_path:
                self.logger.debug(f"Using CLAUDE_PROJECT_DIR: {project_path}")
            
            project_name = os.path.basename(project_path)
            
            if self.session_manager:
                # Register project
                project_id = await self.session_manager.register_project(project_path, project_name)
                self.logger.info(f"Registered project: {project_name} with project_id: {project_id}")
                results['project_id'] = project_id
                
                # Register session
                success = await self.session_manager.register_session(
                    session_id=session_id,
                    project_path=project_path,
                    project_name=project_name,
                    transcript_path=transcript_path
                )
                if success:
                    self.logger.info(f"Registered project with session: {session_id}")
                results['session_registered'] = success
                
                # Set up the project
                project_setup_results = await self.setup_new_project(
                        project_path=project_path,
                        project_id=project_id,
                        project_name=project_name,
                        session_id=session_id,
                        create_channels=True,
                        register_agents=True
                    )                
                    
                results['project_setup_performed'] = project_setup_results
                
                # Set up the global environment
                global_setup_results = await self.setup_global_environment()
                results['global_setup_performed'] = global_setup_results
            else:
                self.logger.warn("SessionManager is not configured.  Cannot proceed with session setup.")
            
            self.logger.info(f"Session initialization complete")
            
        except Exception as e:
            self.logger.error(f"Error initializing session: {e}")
            results['errors'].append(f"Initialization error: {e}")
        
        return results