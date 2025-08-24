#!/usr/bin/env python3
"""
Agent Manager v3 for Claude-Slack
Manages agent policies, DM permissions, and discovery
Phase 2 (v3.0.0) Implementation

This manager handles agent-specific operations that don't belong in ChannelManager:
- DM policies and permissions
- Agent discovery and visibility
- Agent relationships and blocking
"""

import os
import sys
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from db.manager_v3 import DatabaseManagerV3
    from db.initialization import DatabaseInitializer, ensure_db_initialized
except ImportError as e:
    print(f"Import error in AgentManagerV3: {e}", file=sys.stderr)
    DatabaseManagerV3 = None
    DatabaseInitializer = object  # Fallback to object if not available
    ensure_db_initialized = lambda f: f  # No-op decorator

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)


class DMPolicy(Enum):
    """DM policy options for agents"""
    OPEN = 'open'           # Accept DMs from anyone
    RESTRICTED = 'restricted'  # Only from allowlist
    CLOSED = 'closed'       # No DMs allowed


class Discoverability(Enum):
    """Agent discoverability settings"""
    PUBLIC = 'public'       # Visible to all
    PROJECT = 'project'     # Visible in linked projects
    PRIVATE = 'private'     # Not discoverable


class DMPermission(Enum):
    """DM permission types"""
    ALLOW = 'allow'
    BLOCK = 'block'


@dataclass
class AgentInfo:
    """Agent information"""
    name: str
    project_id: Optional[str]
    description: Optional[str]
    status: str
    dm_policy: str
    discoverable: str
    project_name: Optional[str] = None
    dm_availability: Optional[str] = None
    has_existing_dm: bool = False


class AgentManagerV3(DatabaseInitializer):
    """
    Manages agent policies, DM permissions, and discovery.
    
    This manager provides agent-specific operations, delegating
    all database operations to DatabaseManagerV3.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize AgentManagerV3.
        
        Args:
            db_path: Path to SQLite database
        """
        # Initialize parent class (DatabaseInitializer)
        super().__init__()
        
        self.db_path = db_path
        self.logger = get_logger('AgentManagerV3', component='manager')
        
        if DatabaseManagerV3:
            self.db = DatabaseManagerV3(db_path)
            self.db_manager = self.db  # Required for DatabaseInitializer mixin
        else:
            self.db = None
            self.db_manager = None
            self.logger.error("DatabaseManagerV3 not available")
    
    # ============================================================================
    # Agent Registration and Management
    # ============================================================================
    
    @ensure_db_initialized
    async def agent_exists(self,
                         name: str,
                         project_id: Optional[str] = None) -> bool:
        """
        Check if an agent exists.
        
        Args:
            name: Agent name
            project_id: Project ID
        
        Returns:
            True if agent exists, False otherwise
        """
        if not self.db:
            return False
        
        try:
            agent = await self.db.get_agent(name, project_id)
            return agent is not None
        except Exception as e:
            self.logger.error(f"Error checking if agent exists: {e}")
            return False
    
    @ensure_db_initialized
    async def register_agent(self,
                           name: str,
                           project_id: Optional[str] = None,
                           description: Optional[str] = None,
                           dm_policy: str = 'open',
                           discoverable: str = 'public',
                           status: str = 'online',
                           metadata: Optional[Dict] = None) -> bool:
        """
        Register a new agent or update an existing one.
        
        This is the primary method for agent initialization. It handles:
        - Validation of policy settings
        - Agent registration in database
        - Initial configuration
        - Default channel subscriptions (if needed)
        
        Args:
            name: Agent name (required)
            project_id: Project ID (None for global agents)
            description: Agent description
            dm_policy: DM policy ('open', 'restricted', 'closed')
            discoverable: Discoverability setting ('public', 'project', 'private')
            status: Initial status ('online', 'offline', 'busy')
            metadata: Additional agent metadata
        
        Returns:
            True if registration successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            # Validate DM policy
            if dm_policy not in [p.value for p in DMPolicy]:
                self.logger.error(f"Invalid DM policy: {dm_policy}")
                return False
            
            # Validate discoverability
            if discoverable not in [d.value for d in Discoverability]:
                self.logger.error(f"Invalid discoverability: {discoverable}")
                return False
            
            # Register the agent in the database with all fields
            await self.db.register_agent(
                name=name,
                project_id=project_id,
                description=description,
                dm_policy=dm_policy,
                discoverable=discoverable,
                status=status,
                metadata=metadata
            )
            
            self.logger.info(
                f"Registered agent {name} "
                f"(project={project_id}, dm_policy={dm_policy}, "
                f"discoverable={discoverable}, status={status})"
            )
            
            # Note: Default channel subscriptions should be handled by 
            # SubscriptionManagerV3, not here. This maintains separation
            # of concerns.
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error registering agent {name}: {e}")
            return False
    
    @ensure_db_initialized
    async def deactivate_agent(self,
                             name: str,
                             project_id: Optional[str] = None) -> bool:
        """
        Deactivate an agent (set status to offline).
        
        Note: This doesn't delete the agent, just marks it as offline.
        To fully remove an agent would require cleaning up all their
        messages, channel memberships, etc.
        
        Args:
            name: Agent name
            project_id: Project ID
        
        Returns:
            True if deactivated successfully
        """
        if not self.db:
            return False
        
        try:
            await self.db.update_agent(
                agent_name=name,
                agent_project_id=project_id,
                status='offline'
            )
            
            self.logger.info(f"Deactivated agent {name} (project={project_id})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error deactivating agent {name}: {e}")
            return False
    
    # ============================================================================
    # DM Policy Management
    # ============================================================================
    
    @ensure_db_initialized
    async def set_dm_policy(self,
                          agent_name: str,
                          agent_project_id: Optional[str],
                          policy: str,
                          discoverable: Optional[str] = None) -> bool:
        """
        Set an agent's DM policy and optionally discoverability.
        
        Args:
            agent_name: Agent to update
            agent_project_id: Agent's project ID
            policy: DM policy ('open', 'restricted', 'closed')
            discoverable: Optional discoverability ('public', 'project', 'private')
        
        Returns:
            True if updated successfully
        """
        if not self.db:
            return False
        
        try:
            # Validate policy
            if policy not in [p.value for p in DMPolicy]:
                self.logger.error(f"Invalid DM policy: {policy}")
                return False
            
            # Update DM policy using DatabaseManagerV3
            await self.db.update_dm_policy(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                dm_policy=policy
            )
            
            # Update discoverability if provided
            if discoverable:
                if discoverable not in [d.value for d in Discoverability]:
                    self.logger.error(f"Invalid discoverability: {discoverable}")
                    return False
                
                # Update discoverability using update_agent
                await self.db.update_agent(
                    agent_name=agent_name,
                    agent_project_id=agent_project_id,
                    discoverable=discoverable
                )
            
            self.logger.info(
                f"Updated DM policy for {agent_name}: "
                f"policy={policy}, discoverable={discoverable}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting DM policy: {e}")
            return False
    
    @ensure_db_initialized
    async def block_agent(self,
                        agent_name: str,
                        agent_project_id: Optional[str],
                        target_agent: str,
                        target_project_id: Optional[str],
                        reason: Optional[str] = None) -> bool:
        """
        Block another agent from sending DMs.
        
        Args:
            agent_name: Agent performing the block
            agent_project_id: Agent's project ID
            target_agent: Agent to block
            target_project_id: Target agent's project ID
            reason: Optional reason for blocking
        
        Returns:
            True if blocked successfully
        """
        if not self.db:
            return False
        
        try:
            await self.db.set_dm_permission(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                other_agent_name=target_agent,
                other_agent_project_id=target_project_id,
                permission=DMPermission.BLOCK.value,
                reason=reason
            )
            
            self.logger.info(
                f"{agent_name} blocked {target_agent} "
                f"(reason: {reason or 'not specified'})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error blocking agent: {e}")
            return False
    
    @ensure_db_initialized
    async def allow_agent(self,
                        agent_name: str,
                        agent_project_id: Optional[str],
                        target_agent: str,
                        target_project_id: Optional[str],
                        reason: Optional[str] = None) -> bool:
        """
        Allow another agent to send DMs (for restricted policy).
        
        Args:
            agent_name: Agent granting permission
            agent_project_id: Agent's project ID
            target_agent: Agent to allow
            target_project_id: Target agent's project ID
            reason: Optional reason for allowing
        
        Returns:
            True if allowed successfully
        """
        if not self.db:
            return False
        
        try:
            await self.db.set_dm_permission(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                other_agent_name=target_agent,
                other_agent_project_id=target_project_id,
                permission=DMPermission.ALLOW.value,
                reason=reason
            )
            
            self.logger.info(
                f"{agent_name} allowed {target_agent} "
                f"(reason: {reason or 'not specified'})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error allowing agent: {e}")
            return False
    
    @ensure_db_initialized
    async def unblock_agent(self,
                          agent_name: str,
                          agent_project_id: Optional[str],
                          target_agent: str,
                          target_project_id: Optional[str]) -> bool:
        """
        Remove a DM permission (unblock/unallow).
        
        Args:
            agent_name: Agent removing permission
            agent_project_id: Agent's project ID
            target_agent: Target agent
            target_project_id: Target agent's project ID
        
        Returns:
            True if removed successfully
        """
        if not self.db:
            return False
        
        try:
            await self.db.remove_dm_permission(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                other_agent_name=target_agent,
                other_agent_project_id=target_project_id
            )
            
            self.logger.info(f"{agent_name} removed DM permission for {target_agent}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error removing DM permission: {e}")
            return False
    
    # ============================================================================
    # Agent Discovery
    # ============================================================================
    
    @ensure_db_initialized
    async def list_messageable_agents(self,
                                     agent_name: str,
                                     agent_project_id: Optional[str],
                                     include_blocked: bool = False) -> List[AgentInfo]:
        """
        List agents that the current agent can message.
        
        Args:
            agent_name: Agent requesting the list
            agent_project_id: Agent's project ID
            include_blocked: Include blocked agents in results
        
        Returns:
            List of AgentInfo objects for messageable agents
        """
        if not self.db:
            return []
        
        try:
            # Delegate to DatabaseManagerV3's get_discoverable_agents
            agents = await self.db.get_discoverable_agents(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                include_unavailable=include_blocked
            )
            
            return [
                AgentInfo(
                        name=agent['name'],
                        project_id=agent['project_id'],
                        description=agent.get('description'),
                        status=agent.get('status', 'offline'),
                        dm_policy=agent.get('dm_policy', 'open'),
                        discoverable=agent.get('discoverable', 'public'),
                        project_name=agent.get('project_name'),
                        dm_availability=agent.get('dm_availability'),
                        has_existing_dm=agent.get('has_existing_dm', False)
                    )
                    for agent in agents
                ]
        
        except Exception as e:
            self.logger.error(f"Error listing messageable agents: {e}")
            return []
    
    @ensure_db_initialized
    async def get_discoverable_agents(self,
                                     agent_name: str,
                                     agent_project_id: Optional[str],
                                     filter_by_dm_available: bool = False) -> List[AgentInfo]:
        """
        Get all discoverable agents.
        
        Args:
            agent_name: Agent requesting discovery
            agent_project_id: Agent's project ID
            filter_by_dm_available: Only show agents available for DM
        
        Returns:
            List of discoverable agents
        """
        if not self.db:
            return []
        
        try:
            agents = await self.db.get_discoverable_agents(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                include_unavailable=not filter_by_dm_available
            )
            
            return [
                    AgentInfo(
                        name=agent['name'],
                        project_id=agent['project_id'],
                        description=agent.get('description'),
                        status=agent.get('status', 'offline'),
                        dm_policy=agent.get('dm_policy', 'open'),
                        discoverable=agent.get('discoverable', 'public'),
                        project_name=agent.get('project_name'),
                        dm_availability=agent.get('dm_availability'),
                        has_existing_dm=agent.get('has_existing_dm', False)
                    )
                    for agent in agents
                ]
        
        except Exception as e:
            self.logger.error(f"Error getting discoverable agents: {e}")
            return []
    
    @ensure_db_initialized
    async def can_dm_agent(self,
                         agent_name: str,
                         agent_project_id: Optional[str],
                         target_agent: str,
                         target_project_id: Optional[str]) -> Tuple[bool, str]:
        """
        Check if one agent can DM another.
        
        Args:
            agent_name: Agent wanting to send DM
            agent_project_id: Agent's project ID
            target_agent: Target agent
            target_project_id: Target agent's project ID
        
        Returns:
            Tuple of (can_dm: bool, reason: str)
        """
        if not self.db:
            return False, "Database not available"
        
        try:
            # Use DatabaseManagerV3's check_dm_permission
            can_dm = await self.db.check_dm_permission(
                agent1_name=agent_name,
                agent1_project_id=agent_project_id,
                agent2_name=target_agent,
                agent2_project_id=target_project_id
            )
            
            if can_dm:
                return True, "DM allowed"
            
            # Use DatabaseManagerV3's check_can_discover_agent for detailed reason
            can_discover = await self.db.check_can_discover_agent(
                discovering_agent=agent_name,
                discovering_project_id=agent_project_id,
                target_agent=target_agent,
                target_project_id=target_project_id
            )
            
            if not can_discover.get('can_discover'):
                return False, "Agent not discoverable"
            
            # Check dm_availability for specific reason
            dm_availability = can_discover.get('dm_availability', 'unknown')
            if dm_availability == 'blocked':
                return False, "You are blocked by this agent"
            elif dm_availability == 'unavailable':
                return False, "Agent has closed DMs"
            elif dm_availability == 'requires_permission':
                return False, "Agent requires permission for DMs"
            else:
                return False, "Cannot send DM for unknown reason"
        
        except Exception as e:
            self.logger.error(f"Error checking DM permission: {e}")
            return False, f"Error: {str(e)}"
    
    # ============================================================================
    # Agent DM Channel Management
    # ============================================================================
    
    @ensure_db_initialized
    async def get_agent_dm_channels(self,
                                   agent_name: str,
                                   agent_project_id: Optional[str]) -> List[Dict[str, Any]]:
        """
        Get all DM channels for an agent.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
        
        Returns:
            List of DM channel information
        """
        if not self.db:
            return []
        
        try:
            channels = await self.db.get_agent_channels(
                agent_name=agent_name,
                agent_project_id=agent_project_id
            )
            
            # Filter for direct channels
            dm_channels = [c for c in channels if c.get('channel_type') == 'direct']
                
            # Extract the other participant from each DM
            result = []
            for channel in dm_channels:
                # Parse DM channel ID to get participants
                channel_id = channel['id']
                if channel_id.startswith('dm:'):
                    parts = channel_id[3:].split(':')
                    
                    # Find the other participant
                    other_agent = None
                    other_project = None
                    
                    if len(parts) == 2:
                        # Format: dm:agent1:agent2
                        other_agent = parts[1] if parts[0] == agent_name else parts[0]
                    elif len(parts) == 4:
                        # Format: dm:agent1:proj1:agent2:proj2
                        if parts[0] == agent_name:
                            other_agent = parts[2]
                            other_project = parts[3] if parts[3] else None
                        else:
                            other_agent = parts[0]
                            other_project = parts[1] if parts[1] else None
                    
                    result.append({
                        'channel_id': channel_id,
                        'other_agent': other_agent,
                        'other_project_id': other_project,
                        'created_at': channel.get('created_at'),
                        'last_message': channel.get('last_message')
                    })
            
            return result
        
        except Exception as e:
            self.logger.error(f"Error getting agent DM channels: {e}")
            return []
    
    # ============================================================================
    # Agent Settings Management
    # ============================================================================
    
    @ensure_db_initialized
    async def get_agent_settings(self,
                                agent_name: str,
                                agent_project_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Get an agent's current settings.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
        
        Returns:
            Dict with agent settings or None if not found
        """
        if not self.db:
            return None
        
        try:
            agent = await self.db.get_agent(agent_name, agent_project_id)
            
            if not agent:
                return None
            
            return {
                'name': agent['name'],
                'project_id': agent['project_id'],
                'description': agent.get('description'),
                'status': agent.get('status', 'offline'),
                'dm_policy': agent.get('dm_policy', 'open'),
                'discoverable': agent.get('discoverable', 'public'),
                'current_project_id': agent.get('current_project_id'),
                'metadata': agent.get('metadata')
            }
        
        except Exception as e:
            self.logger.error(f"Error getting agent settings: {e}")
            return None
    
    @ensure_db_initialized
    async def update_agent_settings(self,
                                   agent_name: str,
                                   agent_project_id: Optional[str],
                                   **settings) -> bool:
        """
        Update various agent settings.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
            **settings: Settings to update (description, status, metadata, etc.)
        
        Returns:
            True if updated successfully
        """
        if not self.db:
            return False
        
        try:
            # Use the new update_agent method
            await self.db.update_agent(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                **settings
            )
                
            self.logger.info(f"Updated settings for {agent_name}: {settings}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating agent settings: {e}")
            return False
    
    # ============================================================================
    # Agent DM Statistics
    # ============================================================================
    
    @ensure_db_initialized
    async def get_dm_statistics(self,
                               agent_name: str,
                               agent_project_id: Optional[str]) -> Dict[str, Any]:
        """
        Get DM statistics for an agent.
        
        This is business logic that aggregates data from multiple sources.
        It's appropriate to have here as it provides a higher-level view.
        
        Args:
            agent_name: Agent name
            agent_project_id: Agent's project ID
        
        Returns:
            Dict with DM statistics
        """
        if not self.db:
            return {}
        
        try:
            # Get DM channels using DatabaseManagerV3
            channels = await self.db.get_agent_channels(
                agent_name=agent_name,
                agent_project_id=agent_project_id
            )
            
            # Filter for DM channels
            dm_channels = [c for c in channels if c.get('channel_type') == 'direct']
            
            # Get permission statistics from DatabaseManagerV3
            stats = await self.db.get_dm_permission_stats(
                agent_name=agent_name,
                agent_project_id=agent_project_id
            )
            
            return {
                'dm_channels': len(dm_channels),
                'agents_blocked': stats['agents_blocked'],
                'agents_allowed': stats['agents_allowed'],
                'blocked_by_others': stats['blocked_by_others']
            }
                
        except Exception as e:
            self.logger.error(f"Error getting DM statistics: {e}")
            return {}