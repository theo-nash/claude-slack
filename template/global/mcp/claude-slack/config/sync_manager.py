#!/usr/bin/env python3
"""
Configuration Sync Manager for Claude-Slack V3

Unified configuration synchronization and project setup.
Replaces ProjectSetupManager with reconciliation pattern and unified membership model.
"""

import os
import sys
import json
import hashlib
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config.reconciliation import (
    ReconciliationPlan, 
    CreateChannelAction, 
    RegisterAgentAction, 
    AddMembershipAction,
    ActionResult
)
from agents.discovery import AgentDiscoveryService, DiscoveredAgent
from sessions.manager import SessionManager
from config.config_manager import get_config_manager
from frontmatter.parser import FrontmatterParser

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)


class ConfigSyncManager:
    """
    Unified configuration synchronization and project setup.
    Replaces ProjectSetupManager with reconciliation pattern.
    """
    
    def __init__(self, api):
        """
        Initialize ConfigSyncManager with required components.
        
        Args:
            api: ClaudeSlackAPI instance
        """
        
        self.logger = get_logger('ConfigSyncManager', component='manager')
        
        self.api = api
        
        # Initialize managers
        self.session_manager = SessionManager(api)
        
        # Initialize services
        self.discovery = AgentDiscoveryService()
        self.config = get_config_manager()
        
        # Ensure config exists
        self.config.ensure_config_exists()
    
    async def initialize_session(self, session_id: str, cwd: str, 
                                transcript_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Initialize a new session with project detection and full reconciliation.
        
        This is the main entry point from the session hook.
        
        Args:
            session_id: Claude session ID
            cwd: Current working directory
            transcript_path: Optional path to session transcript
            
        Returns:
            Dictionary with initialization results
        """
        results = {
            'session_registered': False,
            'project_id': None,
            'reconciliation': None,
            'errors': []
        }
        
        self.logger.info(f"Initializing session: {session_id}")
        
        try:
            # Find project path
            project_path = os.environ.get('CLAUDE_PROJECT_DIR', cwd)
            if not project_path:
                project_path = cwd
            
            # Derive project name from path
            project_name = os.path.basename(project_path) if project_path else None
            
            # Register session (this also registers the project)
            if self.session_manager:
                success = await self.session_manager.register_session(
                    session_id=session_id,
                    project_path=project_path,
                    project_name=project_name,
                    transcript_path=transcript_path
                )
                results['session_registered'] = success
                
                if success:
                    # Get project ID
                    project_id = self.session_manager.generate_project_id(project_path)
                    results['project_id'] = project_id
                    
                    # Run full reconciliation
                    reconciliation_results = await self.reconcile_all(
                        scope='all',
                        project_id=project_id,
                        project_path=project_path
                    )
                    results['reconciliation'] = reconciliation_results
                else:
                    self.logger.warning("Failed to register session")
                    results['errors'].append("Session registration failed")
            
        except Exception as e:
            self.logger.error(f"Error initializing session: {e}")
            results['errors'].append(str(e))
        
        return results
    
    async def reconcile_all(self, scope: str = 'all', 
                           project_id: Optional[str] = None,
                           project_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Reconcile configuration with database state.
        
        Executes in phases to ensure proper dependencies:
        1. Infrastructure (channels) - planned and executed
        2. Agents - planned and executed  
        3. Access (memberships) - planned and executed
        
        Args:
            scope: 'global', 'project', or 'all'
            project_id: Project ID for project scope
            project_path: Project path for agent discovery
            
        Returns:
            Dictionary with reconciliation results
        """
        self.logger.info(f"Starting reconciliation: scope={scope}, project_id={project_id}")
        
        # Load configuration
        config = self.config.load_config()
        
        # Track overall results
        all_results = []
        total_executed = 0
        total_failed = 0
        phase_summaries = {}
        
        # Phase 1: Infrastructure (channels)
        self.logger.info("Phase 1: Planning and executing infrastructure")
        infra_plan = ReconciliationPlan()
        await self._plan_channels(infra_plan, config, scope, project_id)
        
        if infra_plan.get_total_actions() > 0:
            infra_results = await infra_plan.execute(self.api)
            all_results.extend(infra_results.get('results', []))
            total_executed += infra_results.get('executed', 0)
            total_failed += infra_results.get('failed', 0)
            phase_summaries.update(infra_results.get('phase_summary', {}))
        
        # Phase 2: Agents
        self.logger.info("Phase 2: Planning and executing agent registration")
        agents_plan = ReconciliationPlan()
        if project_path or scope in ['global', 'all']:
            await self._plan_agents(agents_plan, scope, project_id, project_path)
        
        if agents_plan.get_total_actions() > 0:
            agents_results = await agents_plan.execute(self.api)
            all_results.extend(agents_results.get('results', []))
            total_executed += agents_results.get('executed', 0)
            total_failed += agents_results.get('failed', 0)
            phase_summaries.update(agents_results.get('phase_summary', {}))
        
        # Phase 3: Access (default memberships and explicit subscriptions)
        self.logger.info("Phase 3: Planning and executing access control")
        access_plan = ReconciliationPlan()
        await self._plan_default_access(access_plan, scope, project_id)
        await self._plan_explicit_subscriptions(access_plan, scope, project_id)
        
        if access_plan.get_total_actions() > 0:
            access_results = await access_plan.execute(self.api)
            all_results.extend(access_results.get('results', []))
            total_executed += access_results.get('executed', 0)
            total_failed += access_results.get('failed', 0)
            phase_summaries.update(access_results.get('phase_summary', {}))
        
        # Compile overall results
        execution_results = {
            'total_actions': len(all_results),
            'executed': total_executed,
            'failed': total_failed,
            'success': total_failed == 0,
            'results': all_results,
            'phase_summary': phase_summaries
        }
        
        self.logger.info(f"Reconciliation complete: {total_executed} executed, {total_failed} failed")
        
        # Track in history
        await self._track_sync_history(config, scope, project_id, execution_results)
        
        return execution_results
    
    async def reconcile_config(self, force: bool = False) -> Dict[str, Any]:
        """
        Reconcile configuration changes.
        
        Args:
            force: Force reconciliation even if config hasn't changed
            
        Returns:
            Dictionary with reconciliation results
        """
        config = self.config.load_config()
        config_hash = self._hash_config(config)
        
        # Check if config has changed
        if not force:
            last_sync = await self._get_last_sync_hash()
            if last_sync == config_hash:
                self.logger.info("Configuration unchanged, skipping reconciliation")
                return {'changed': False, 'actions': []}
        
        # Run reconciliation for all scopes
        return await self.reconcile_all(scope='all')
    
    async def _plan_channels(self, plan: ReconciliationPlan, config: Dict[str, Any],
                            scope: str, project_id: Optional[str] = None):
        """
        Plan channel creation based on configuration.
        
        Args:
            plan: ReconciliationPlan to add actions to
            config: Configuration dictionary
            scope: 'global', 'project', or 'all'
            project_id: Project ID for project channels
        """
        default_channels = config.get('default_channels', {})
        
        # Process global channels
        if scope in ['global', 'all']:
            for channel_config in default_channels.get('global', []):
                channel_id = f"global:{channel_config['name']}"
                
                # Check if channel exists
                existing = await self.api.get_channel(channel_id)
                if not existing:
                    action = CreateChannelAction(
                        channel_id=channel_id,
                        channel_type='channel',
                        access_type=channel_config.get('access_type', 'open'),
                        scope='global',
                        name=channel_config['name'],
                        description=channel_config.get('description'),
                        is_default=channel_config.get('is_default', False)
                    )
                    plan.add_action(action)
        
        # Process project channels
        if scope in ['project', 'all'] and project_id:
            for channel_config in default_channels.get('project', []):
                # Generate project-scoped channel ID
                project_id_short = project_id[:8] if len(project_id) > 8 else project_id
                channel_id = f"proj_{project_id_short}:{channel_config['name']}"
                
                # Check if channel exists
                existing = await self.api.get_channel(channel_id)
                if not existing:
                    action = CreateChannelAction(
                        channel_id=channel_id,
                        channel_type='channel',
                        access_type=channel_config.get('access_type', 'open'),
                        scope='project',
                        name=channel_config['name'],
                        project_id=project_id,
                        description=channel_config.get('description'),
                        is_default=channel_config.get('is_default', False)
                    )
                    plan.add_action(action)
    
    async def _plan_agents(self, plan: ReconciliationPlan, scope: str,
                          project_id: Optional[str] = None,
                          project_path: Optional[str] = None):
        """
        Plan agent registration based on discovery.
        
        Args:
            plan: ReconciliationPlan to add actions to
            scope: 'global', 'project', or 'all'
            project_id: Project ID for project agents
            project_path: Path to project for discovery
        """
        discovered_agents = []
        
        # Discover global agents
        if scope in ['global', 'all']:
            global_agents = await self.discovery.discover_global_agents()
            discovered_agents.extend(global_agents)
        
        # Discover project agents
        if scope in ['project', 'all'] and project_path:
            project_agents = await self.discovery.discover_project_agents(project_path)
            discovered_agents.extend(project_agents)
        
        # Plan registration for each discovered agent
        for agent in discovered_agents:
            # Determine project_id based on agent scope
            agent_project_id = project_id if agent.scope == 'project' else None
            
            # Check if agent already registered
            existing = await self.api.get_agent(agent.name, agent_project_id)
            if not existing:
                # Extract dm_whitelist from metadata if present
                metadata = {}
                if agent.metadata and 'dm_whitelist' in agent.metadata:
                    metadata['dm_whitelist'] = agent.metadata['dm_whitelist']
                
                action = RegisterAgentAction(
                    name=agent.name,
                    project_id=agent_project_id,
                    description=agent.description,
                    dm_policy=agent.dm_policy,
                    discoverable=agent.discoverable,
                    metadata=metadata
                )
                plan.add_action(action)
        
        # Always register the 'assistant' agent for projects
        if scope in ['project', 'all'] and project_id:
            assistant_exists = await self.api.get_agent('assistant', project_id)
            if not assistant_exists:
                action = RegisterAgentAction(
                    name='assistant',
                    project_id=project_id,
                    description='Main assistant agent for the project'
                )
                plan.add_action(action)
    
    async def _plan_default_access(self, plan: ReconciliationPlan, scope: str,
                                  project_id: Optional[str] = None):
        """
        Plan default memberships based on is_default channels.
        
        Uses the unified membership model - all access goes through channel_members.
        
        Args:
            plan: ReconciliationPlan to add actions to
            scope: 'global', 'project', or 'all'
            project_id: Project ID for eligibility check
        """
        # Get all channels with is_default=true
        default_channels = await self._get_default_channels(scope, project_id)
        
        # Get all eligible agents
        agents = await self._get_agents_for_scope(scope, project_id)
        
        for channel in default_channels:
            for agent in agents:
                # Check eligibility
                if not self._is_eligible_for_default(agent, channel, project_id):
                    continue
                
                # Check for exclusions in frontmatter
                if await self._check_agent_exclusions(
                    agent['name'], 
                    agent.get('project_id'),
                    channel['name']
                ):
                    self.logger.debug(f"Agent {agent['name']} excluded from {channel['name']}")
                    continue
                
                # Check if already a member
                is_member = await self.api.is_channel_member(
                    channel['id'],
                    agent['name'],
                    agent.get('project_id')
                )
                if is_member:
                    continue
                
                # Determine invited_by based on access_type
                # For open channels, agent joins themselves
                # For members channels with is_default, system adds them
                invited_by = 'self' if channel['access_type'] == 'open' else 'system'
                
                # Determine capabilities based on channel type
                can_leave = True  # All default memberships can be left
                can_invite = (channel['access_type'] == 'open')  # Only open channels allow invites
                
                # Add membership action
                action = AddMembershipAction(
                    channel_id=channel['id'],
                    agent_name=agent['name'],
                    agent_project_id=agent.get('project_id'),
                    invited_by=invited_by,
                    source='default',
                    is_from_default=True,
                    can_leave=can_leave,
                    can_invite=can_invite
                )
                plan.add_action(action)
    
    async def _plan_explicit_subscriptions(self, plan: ReconciliationPlan, scope: str,
                                          project_id: Optional[str] = None):
        """
        Plan explicit channel subscriptions from agent frontmatter.
        
        Agents can explicitly subscribe to channels in their frontmatter:
        channels:
          global:
            - general
            - security
          project:
            - dev
        
        Args:
            plan: ReconciliationPlan to add actions to
            scope: 'global', 'project', or 'all'
            project_id: Project ID for project scope
        """
        # Get all agents for the scope
        agents = await self._get_agents_for_scope(scope, project_id)
        
        for agent in agents:
            # Get agent's frontmatter
            agent_file = await self._get_agent_file_path(
                agent['name'], 
                agent.get('project_id')
            )
            
            if not agent_file or not os.path.exists(agent_file):
                continue
                
            try:
                # Parse frontmatter
                from frontmatter.parser import FrontmatterParser
                agent_data = FrontmatterParser.parse_file(agent_file)
                channels_config = agent_data.get('channels', {})
                
                # Process global channel subscriptions
                if scope in ['global', 'all']:
                    global_channels = channels_config.get('global', [])
                    for channel_name in global_channels:
                        await self._plan_subscription_for_channel(
                            plan, agent, channel_name, 'global', None
                        )
                
                # Process project channel subscriptions
                if scope in ['project', 'all'] and project_id:
                    project_channels = channels_config.get('project', [])
                    for channel_name in project_channels:
                        await self._plan_subscription_for_channel(
                            plan, agent, channel_name, 'project', project_id
                        )
                        
            except Exception as e:
                self.logger.warning(f"Failed to process explicit subscriptions for {agent['name']}: {e}")
    
    async def _plan_subscription_for_channel(self, plan: ReconciliationPlan, 
                                            agent: Dict, channel_name: str, 
                                            scope: str, project_id: Optional[str]):
        """
        Plan a subscription for a specific channel.
        
        Args:
            plan: ReconciliationPlan to add actions to
            agent: Agent dictionary
            channel_name: Name of the channel to subscribe to
            scope: 'global' or 'project'
            project_id: Project ID for project channels
        """
        # Determine channel ID
        if scope == 'global':
            channel_id = f"global:{channel_name}"
        else:
            project_id_short = project_id[:8] if len(project_id) > 8 else project_id
            channel_id = f"proj_{project_id_short}:{channel_name}"
        
        # Check if channel exists
        channel = await self.api.get_channel(channel_id)
        if not channel:
            self.logger.debug(f"Channel {channel_id} does not exist, skipping subscription")
            return
        
        # Check if already a member
        is_member = await self.api.is_channel_member(
            channel_id,
            agent['name'],
            agent.get('project_id')
        )
        if is_member:
            return
        
        # Determine access based on channel type
        if channel['access_type'] == 'open':
            # Open channels - agent can join themselves
            invited_by = 'self'
            can_leave = True
            can_invite = True
        elif channel['access_type'] == 'members':
            # Members-only channels - need to check if agent can join
            # For explicit subscriptions, we'll allow it with system invitation
            invited_by = 'system'
            can_leave = True
            can_invite = False
        else:
            # Private or other restricted channels - skip
            self.logger.debug(f"Cannot add {agent['name']} to {channel_id} (access_type: {channel['access_type']})")
            return
        
        # Add membership action
        action = AddMembershipAction(
            channel_id=channel_id,
            agent_name=agent['name'],
            agent_project_id=agent.get('project_id'),
            invited_by=invited_by,
            source='explicit',
            is_from_default=False,
            can_leave=can_leave,
            can_invite=can_invite
        )
        plan.add_action(action)
    
    async def _get_default_channels(self, scope: str, project_id: Optional[str] = None) -> List[Dict]:
        """
        Get all channels where is_default=true for the given scope.
        """
        return await self.api.list_channels(
            scope_filter=scope,
            project_id=project_id,
            is_default=True
        )
    
    async def _get_agents_for_scope(self, scope: str, project_id: Optional[str] = None) -> List[Dict]:
        """
        Get all agents eligible for the given scope.
        """
        return await self.api.list_agents(
            scope=scope,
            project_id=project_id
        )
    
    def _is_eligible_for_default(self, agent: Dict, channel: Dict, 
                                project_id: Optional[str] = None) -> bool:
        """
        Check if an agent is eligible for default access to a channel.
        """
        # Global channels: all agents eligible
        if channel['scope'] == 'global':
            return True
        
        # Project channels: only same-project agents
        if channel['scope'] == 'project':
            agent_project = agent.get('project_id')
            channel_project = channel.get('project_id', project_id)
            return agent_project == channel_project
        
        return False
    
    async def _check_agent_exclusions(self, agent_name: str,
                                     agent_project_id: Optional[str],
                                     channel_name: str) -> bool:
        """
        Check if agent has excluded this channel in frontmatter.
        
        Returns:
            True if excluded, False otherwise
        """
        # Get agent file path
        agent_file = await self._get_agent_file_path(agent_name, agent_project_id)
        if not agent_file or not os.path.exists(agent_file):
            return False
        
        try:
            # Parse frontmatter
            agent_data = FrontmatterParser.parse_file(agent_file)
            
            # Check exclusion list (under channels)
            channels = agent_data.get('channels', {})
            exclusions = channels.get('exclude', [])
            if channel_name in exclusions:
                return True
            
            # Check never_default flag (at top level due to parser behavior)
            if agent_data.get('never_default', False):
                return True
                
        except Exception as e:
            self.logger.warning(f"Failed to check exclusions for {agent_name}: {e}")
        
        return False
    
    async def _get_agent_file_path(self, agent_name: str, 
                                   agent_project_id: Optional[str]) -> Optional[str]:
        """Get the path to an agent's markdown file."""
        if agent_project_id:
            # Project agent - get project path from session manager
            project_context = await self.session_manager.get_project_context(agent_project_id)
            if project_context and project_context.project_path:
                project_path = project_context.project_path
            else:
                # Fall back to querying database directly
                project = await self.api.get_project(agent_project_id)
                if project and project.get('path'):
                    project_path = project['path']
                else:
                    # Last resort - use environment or current directory
                    project_path = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())
            return os.path.join(project_path, '.claude', 'agents', f'{agent_name}.md')
        else:
            # Global agent
            claude_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
            return os.path.join(claude_dir, 'agents', f'{agent_name}.md')
    
    async def _track_sync_history(self, config: Dict, scope: str,
                                 project_id: Optional[str],
                                 execution_results: Dict):
        """
        Track configuration sync in history table.
        """
        try:
            config_hash = self._hash_config(config)
            config_snapshot = json.dumps(config)
            actions_taken = json.dumps([
                {
                    'type': r.action_type,
                    'target': r.target,
                    'success': r.success,
                    'message': r.message,
                    'error': r.error
                }
                for r in execution_results.get('results', [])
            ])
            
            await self.api.track_config_sync(
                config_hash=config_hash,
                config_snapshot=config_snapshot,
                scope=scope,
                project_id=project_id,
                actions_taken=actions_taken,
                success=execution_results.get('success', False),
                error_message=None  # No error message if successful
            )
            
        except Exception as e:
            self.logger.error(f"Failed to track sync history: {e}")
    
    async def _get_last_sync_hash(self) -> Optional[str]:
        """Get the hash of the last successful sync."""
        return await self.api.get_last_sync_hash()
    
    def _hash_config(self, config: Dict) -> str:
        """Generate a hash of the configuration for change detection."""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    async def register_discovered_agent(self, agent: DiscoveredAgent) -> bool:
        """
        Register a single discovered agent.
        
        This is useful for on-demand agent registration.
        
        Args:
            agent: DiscoveredAgent object
            
        Returns:
            True if successful
        """
        try:
            # Create a plan with just this agent
            plan = ReconciliationPlan()
            
            # Extract dm_whitelist from metadata if present
            metadata = {}
            if agent.metadata and 'dm_whitelist' in agent.metadata:
                metadata['dm_whitelist'] = agent.metadata['dm_whitelist']
            
            # Add registration action
            action = RegisterAgentAction(
                name=agent.name,
                project_id=agent.project_id if agent.scope == 'project' else None,
                description=agent.description,
                dm_policy=agent.dm_policy,
                discoverable=agent.discoverable,
                metadata=metadata
            )
            plan.add_action(action)
            
            # Apply default memberships for this agent
            await self._plan_default_access_for_agent(plan, agent)
            
            # Execute the plan
            results = await plan.execute(self.api)
            
            return results.get('success', False)
            
        except Exception as e:
            self.logger.error(f"Failed to register agent {agent.name}: {e}")
            return False
    
    async def _plan_default_access_for_agent(self, plan: ReconciliationPlan,
                                            agent: DiscoveredAgent):
        """
        Plan default memberships for a specific agent.
        """
        # Determine scope and project_id
        project_id = None
        if agent.scope == 'project':
            # Get project_id from environment or current context
            project_path = os.path.dirname(os.path.dirname(agent.source_path))
            project_id = await self.session_manager.generate_project_id(project_path)
        
        # Get default channels for agent's scope
        default_channels = await self._get_default_channels(agent.scope, project_id)
        
        for channel in default_channels:
            # Check eligibility
            agent_dict = {
                'name': agent.name,
                'project_id': project_id if agent.scope == 'project' else None
            }
            
            if not self._is_eligible_for_default(agent_dict, channel, project_id):
                continue
            
            # Check exclusions
            if channel['name'] in agent.get_exclusions():
                continue
            
            if agent.excludes_all_defaults():
                continue
            
            # Determine membership parameters
            invited_by = 'self' if channel['access_type'] == 'open' else 'system'
            can_invite = (channel['access_type'] == 'open')
            
            # Add membership action
            action = AddMembershipAction(
                channel_id=channel['id'],
                agent_name=agent.name,
                agent_project_id=project_id if agent.scope == 'project' else None,
                invited_by=invited_by,
                source='default',
                is_from_default=True,
                can_leave=True,
                can_invite=can_invite
            )
            plan.add_action(action)