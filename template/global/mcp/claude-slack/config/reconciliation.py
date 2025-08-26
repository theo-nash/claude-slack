#!/usr/bin/env python3
"""
Reconciliation Plan and Actions for Claude-Slack V3

Provides a phased execution plan for configuration reconciliation.
Actions are grouped into phases to ensure safe execution order.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from log_manager import get_logger
except ImportError:
    def get_logger(name, component=None):
        return logging.getLogger(name)


class ActionPhase(Enum):
    """Execution phases for reconciliation"""
    INFRASTRUCTURE = 'infrastructure'  # Channels, projects, links
    AGENTS = 'agents'                  # Agent registration
    ACCESS = 'access'                  # Memberships (unified model)


class ActionStatus(Enum):
    """Status of an action"""
    PENDING = 'pending'
    EXECUTING = 'executing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass
class ActionResult:
    """Result of executing an action"""
    success: bool
    action_type: str
    target: str
    message: Optional[str] = None
    error: Optional[str] = None
    changes: Dict[str, Any] = field(default_factory=dict)


class Action(ABC):
    """Base class for reconciliation actions"""
    
    def __init__(self, phase: ActionPhase):
        self.phase = phase
        self.status = ActionStatus.PENDING
        self.result: Optional[ActionResult] = None
        self.logger = get_logger(self.__class__.__name__, component='reconciliation')
    
    @abstractmethod
    async def execute(self, db_manager) -> ActionResult:
        """Execute the action using the provided database manager"""
        pass
    
    @abstractmethod
    def describe(self) -> str:
        """Human-readable description of the action"""
        pass
    
    @abstractmethod
    def is_idempotent(self) -> bool:
        """Whether this action can be safely retried"""
        pass


class CreateChannelAction(Action):
    """Action to create a channel"""
    
    def __init__(self, channel_id: str, channel_type: str, access_type: str, 
                 scope: str, name: str, project_id: Optional[str] = None,
                 description: Optional[str] = None, is_default: bool = False):
        super().__init__(ActionPhase.INFRASTRUCTURE)
        self.channel_id = channel_id
        self.channel_type = channel_type
        self.access_type = access_type
        self.scope = scope
        self.name = name
        self.project_id = project_id
        self.description = description
        self.is_default = is_default
    
    async def execute(self, db_manager) -> ActionResult:
        """Create the channel"""
        try:
            # Check if channel already exists
            existing = await db_manager.get_channel(self.channel_id)
            if existing:
                self.logger.debug(f"Channel already exists: {self.channel_id}")
                return ActionResult(
                    success=True,
                    action_type='create_channel',
                    target=self.channel_id,
                    message='Channel already exists'
                )
            
            # Create the channel
            created_id = await db_manager.create_channel(
                channel_id=self.channel_id,
                channel_type=self.channel_type,
                access_type=self.access_type,
                scope=self.scope,
                name=self.name,
                project_id=self.project_id,
                description=self.description,
                created_by='system',
                is_default=self.is_default
            )
            
            return ActionResult(
                success=True,
                action_type='create_channel',
                target=self.channel_id,
                message=f'Created channel: {self.channel_id}',
                changes={'created': True, 'is_default': self.is_default}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to create channel {self.channel_id}: {e}")
            return ActionResult(
                success=False,
                action_type='create_channel',
                target=self.channel_id,
                error=str(e)
            )
    
    def describe(self) -> str:
        return f"Create channel '{self.name}' ({self.access_type}) in {self.scope} scope"
    
    def is_idempotent(self) -> bool:
        return True


class RegisterAgentAction(Action):
    """Action to register an agent"""
    
    def __init__(self, name: str, project_id: Optional[str] = None,
                 description: Optional[str] = None, dm_policy: str = 'open',
                 discoverable: str = 'public', metadata: Optional[Dict] = None,
                 create_notes_channel: bool = True):
        super().__init__(ActionPhase.AGENTS)
        self.name = name
        self.project_id = project_id
        self.description = description
        self.dm_policy = dm_policy
        self.discoverable = discoverable
        self.metadata = metadata or {}
        self.create_notes_channel = create_notes_channel
    
    async def execute(self, db_manager) -> ActionResult:
        """Register the agent and create notes channel"""
        try:
            # Check if agent already exists
            existing = await db_manager.get_agent(self.name, self.project_id)
            if existing:
                self.logger.debug(f"Agent already exists: {self.name}")
                return ActionResult(
                    success=True,
                    action_type='register_agent',
                    target=self.name,
                    message='Agent already registered'
                )
            
            # Register the agent
            await db_manager.register_agent(
                name=self.name,
                project_id=self.project_id,
                description=self.description,
                dm_policy=self.dm_policy,
                discoverable=self.discoverable,
                metadata=self.metadata
            )
            
            # Set up DM whitelist if policy is restricted
            if self.dm_policy == 'restricted' and self.metadata.get('dm_whitelist'):
                whitelist = self.metadata['dm_whitelist']
                for allowed_agent in whitelist:
                    # Parse agent name which might include project scope
                    if ':' in allowed_agent:
                        other_name, other_project = allowed_agent.split(':', 1)
                    else:
                        other_name = allowed_agent
                        other_project = None
                    
                    try:
                        await db_manager.set_dm_permission(
                            agent_name=self.name,
                            agent_project_id=self.project_id,
                            other_agent_name=other_name,
                            other_agent_project_id=other_project,
                            permission='allow',
                            reason='Whitelist from agent configuration'
                        )
                        self.logger.debug(f"Added DM whitelist entry: {self.name} allows {other_name}")
                    except Exception as e:
                        self.logger.warning(f"Failed to add DM whitelist entry for {other_name}: {e}")
            
            # Create notes channel if requested
            notes_channel_created = False
            if self.create_notes_channel:
                try:
                    # Import here to avoid circular dependency
                    from notes.manager import NotesManager
                    notes_mgr = NotesManager(db_manager.db_path)
                    notes_channel_id = await notes_mgr.ensure_notes_channel(
                        agent_name=self.name,
                        agent_project_id=self.project_id
                    )
                    notes_channel_created = True
                    self.logger.debug(f"Created notes channel for {self.name}: {notes_channel_id}")
                except Exception as e:
                    self.logger.warning(f"Failed to create notes channel for {self.name}: {e}")
            
            return ActionResult(
                success=True,
                action_type='register_agent',
                target=self.name,
                message=f'Registered agent: {self.name}' + 
                        (' with notes channel' if notes_channel_created else ''),
                changes={'registered': True, 'project_id': self.project_id,
                        'notes_channel': notes_channel_created}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to register agent {self.name}: {e}")
            return ActionResult(
                success=False,
                action_type='register_agent',
                target=self.name,
                error=str(e)
            )
    
    def describe(self) -> str:
        scope = 'project' if self.project_id else 'global'
        return f"Register {scope} agent '{self.name}'"
    
    def is_idempotent(self) -> bool:
        return True


class AddMembershipAction(Action):
    """Action to add channel membership (unified model)"""
    
    def __init__(self, channel_id: str, agent_name: str, 
                 agent_project_id: Optional[str] = None,
                 invited_by: str = 'self', source: str = 'default',
                 is_from_default: bool = False, can_leave: bool = True,
                 can_invite: bool = False):
        super().__init__(ActionPhase.ACCESS)
        self.channel_id = channel_id
        self.agent_name = agent_name
        self.agent_project_id = agent_project_id
        self.invited_by = invited_by
        self.source = source
        self.is_from_default = is_from_default
        self.can_leave = can_leave
        self.can_invite = can_invite
    
    async def execute(self, db_manager) -> ActionResult:
        """Add the membership"""
        try:
            # Check if membership already exists
            existing = await db_manager.is_channel_member(
                self.channel_id, self.agent_name, self.agent_project_id
            )
            if existing:
                self.logger.debug(f"Membership already exists: {self.agent_name} in {self.channel_id}")
                return ActionResult(
                    success=True,
                    action_type='add_membership',
                    target=f"{self.agent_name}:{self.channel_id}",
                    message='Membership already exists'
                )
            
            # Add the membership (unified model)
            await db_manager.add_channel_member(
                channel_id=self.channel_id,
                agent_name=self.agent_name,
                agent_project_id=self.agent_project_id,
                invited_by=self.invited_by,
                source=self.source,
                is_from_default=self.is_from_default,
                can_leave=self.can_leave,
                can_invite=self.can_invite
            )
            
            return ActionResult(
                success=True,
                action_type='add_membership',
                target=f"{self.agent_name}:{self.channel_id}",
                message=f'Added {self.agent_name} to {self.channel_id}',
                changes={
                    'invited_by': self.invited_by,
                    'is_from_default': self.is_from_default
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to add membership for {self.agent_name} to {self.channel_id}: {e}")
            return ActionResult(
                success=False,
                action_type='add_membership',
                target=f"{self.agent_name}:{self.channel_id}",
                error=str(e)
            )
    
    def describe(self) -> str:
        return f"Add {self.agent_name} to channel {self.channel_id}"
    
    def is_idempotent(self) -> bool:
        return True


class RemoveMembershipAction(Action):
    """Action to remove channel membership"""
    
    def __init__(self, channel_id: str, agent_name: str,
                 agent_project_id: Optional[str] = None):
        super().__init__(ActionPhase.ACCESS)
        self.channel_id = channel_id
        self.agent_name = agent_name
        self.agent_project_id = agent_project_id
    
    async def execute(self, db_manager) -> ActionResult:
        """Remove the membership"""
        try:
            await db_manager.remove_channel_member(
                channel_id=self.channel_id,
                agent_name=self.agent_name,
                agent_project_id=self.agent_project_id
            )
            
            return ActionResult(
                success=True,
                action_type='remove_membership',
                target=f"{self.agent_name}:{self.channel_id}",
                message=f'Removed {self.agent_name} from {self.channel_id}'
            )
            
        except Exception as e:
            self.logger.error(f"Failed to remove membership for {self.agent_name} from {self.channel_id}: {e}")
            return ActionResult(
                success=False,
                action_type='remove_membership',
                target=f"{self.agent_name}:{self.channel_id}",
                error=str(e)
            )
    
    def describe(self) -> str:
        return f"Remove {self.agent_name} from channel {self.channel_id}"
    
    def is_idempotent(self) -> bool:
        return True


class ReconciliationPlan:
    """
    Execution plan with dependency ordering.
    Actions are grouped into phases for safe execution.
    """
    
    def __init__(self):
        self.phases: Dict[ActionPhase, List[Action]] = {
            ActionPhase.INFRASTRUCTURE: [],
            ActionPhase.AGENTS: [],
            ActionPhase.ACCESS: []
        }
        self.logger = get_logger('ReconciliationPlan', component='reconciliation')
        self.results: List[ActionResult] = []
    
    def add_action(self, action: Action):
        """Add an action to the appropriate phase"""
        self.phases[action.phase].append(action)
        self.logger.debug(f"Added {action.__class__.__name__} to {action.phase.value} phase")
    
    def get_total_actions(self) -> int:
        """Get total number of actions in the plan"""
        return sum(len(actions) for actions in self.phases.values())
    
    def describe(self) -> Dict[str, List[str]]:
        """Get human-readable descriptions of all actions"""
        descriptions = {}
        for phase, actions in self.phases.items():
            descriptions[phase.value] = [action.describe() for action in actions]
        return descriptions
    
    async def execute(self, db_manager) -> Dict[str, Any]:
        """
        Execute the plan in phases.
        
        Args:
            db_manager: DatabaseManager instance
            
        Returns:
            Dictionary with execution results
        """
        self.results = []
        total_actions = self.get_total_actions()
        executed = 0
        failed = 0
        skipped = 0
        
        self.logger.info(f"Executing reconciliation plan with {total_actions} actions")
        
        # Execute phases in order
        for phase in [ActionPhase.INFRASTRUCTURE, ActionPhase.AGENTS, ActionPhase.ACCESS]:
            phase_actions = self.phases[phase]
            if not phase_actions:
                continue
            
            self.logger.info(f"Executing {phase.value} phase with {len(phase_actions)} actions")
            
            for action in phase_actions:
                try:
                    action.status = ActionStatus.EXECUTING
                    result = await action.execute(db_manager)
                    action.result = result
                    self.results.append(result)
                    
                    if result.success:
                        action.status = ActionStatus.COMPLETED
                        executed += 1
                        if result.message:
                            self.logger.debug(result.message)
                    else:
                        action.status = ActionStatus.FAILED
                        failed += 1
                        self.logger.error(f"Action failed: {result.error}")
                        
                        # Stop execution on critical failures
                        if phase == ActionPhase.INFRASTRUCTURE:
                            self.logger.error("Infrastructure phase failed, stopping execution")
                            break
                            
                except Exception as e:
                    self.logger.error(f"Unexpected error executing action: {e}")
                    action.status = ActionStatus.FAILED
                    failed += 1
                    result = ActionResult(
                        success=False,
                        action_type=action.__class__.__name__,
                        target='unknown',
                        error=str(e)
                    )
                    self.results.append(result)
        
        # Calculate summary
        summary = {
            'total_actions': total_actions,
            'executed': executed,
            'failed': failed,
            'skipped': total_actions - executed - failed,
            'success': failed == 0,
            'results': self.results,
            'phase_summary': {
                phase.value: {
                    'total': len(actions),
                    'completed': sum(1 for a in actions if a.status == ActionStatus.COMPLETED),
                    'failed': sum(1 for a in actions if a.status == ActionStatus.FAILED)
                }
                for phase, actions in self.phases.items()
            }
        }
        
        self.logger.info(f"Plan execution complete: {executed} executed, {failed} failed")
        return summary
    
    async def rollback(self):
        """
        Rollback executed actions (if possible).
        Note: Not all actions are reversible.
        """
        self.logger.warning("Rollback requested - some actions may not be reversible")
        # TODO: Implement rollback logic for reversible actions
        pass