#!/usr/bin/env python3
"""
MCP Tool Orchestrator for Claude-Slack
Handles all MCP tool execution logic with common patterns and validation.
Separates MCP protocol handling from business logic.
"""

import os
import sys
import json
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from db.manager import DatabaseManager
from db.initialization import DatabaseInitializer, ensure_db_initialized
from channels.manager import ChannelManager
from notes.manager import NotesManager
from utils.formatting import format_messages_concise, format_channel_list
from log_manager import get_logger


@dataclass
class ProjectContext:
    """Project context from session"""
    project_id: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    transcript_path: Optional[str] = None


class MCPToolOrchestrator(DatabaseInitializer):
    """
    Orchestrates MCP tool execution with unified patterns.
    
    This class:
    - Handles all MCP tool execution logic
    - Provides common validation and error handling
    - Delegates to appropriate managers
    - Formats responses consistently
    """
    
    # Tools that require agent_id validation
    TOOLS_REQUIRING_AGENT = {
        "create_channel", "list_channels", "join_channel", "leave_channel",
        "invite_to_channel", "list_my_channels", "send_channel_message",
        "send_direct_message", "get_messages", "search_messages",
        "write_note", "search_my_notes", "get_recent_notes", "peek_agent_notes"
    }
    
    def __init__(self, db_path: str):
        """
        Initialize the orchestrator with all required managers.
        
        Args:
            db_path: Path to the SQLite database
        """
        super().__init__()
        
        self.db_path = db_path
        self.logger = get_logger('MCPToolOrchestrator', component='orchestrator')
        
        # Initialize only the managers we actually use
        self.db = DatabaseManager(db_path)
        self.db_manager = self.db  # Required for DatabaseInitializer mixin
        
        self.channels = ChannelManager(db_path)
        self.notes = NotesManager(db_path)
    
    @ensure_db_initialized
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any],
                          context: Optional[ProjectContext] = None) -> Dict[str, Any]:
        """
        Main entry point for tool execution.
        
        Args:
            tool_name: Name of the MCP tool to execute
            arguments: Tool arguments from MCP call
            context: Optional project context from session
            
        Returns:
            Dict with 'success' and 'content' or 'error' keys
        """
        try:           
            # Validate agent if required
            agent = None
            if tool_name in self.TOOLS_REQUIRING_AGENT:
                agent_id = arguments.get("agent_id")
                if not agent_id:
                    return self._error_response("Missing required parameter: agent_id")
                
                agent = await self._validate_and_get_agent(agent_id, context)
                if not agent:
                    return self._error_response(
                        f"Agent '{agent_id}' not found. Please check your agent_id in frontmatter."
                    )
            
            # Find and execute handler
            handler_name = f"handle_{tool_name}"
            handler = getattr(self, handler_name, None)
            
            if not handler:
                return self._error_response(f"Unknown tool: {tool_name}")
            
            # Execute the handler
            result = await handler(arguments, agent, context)
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return self._error_response(f"Internal error: {str(e)}")
    
    # ============================================================================
    # Channel Operations
    # ============================================================================
    
    async def handle_create_channel(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Create a new channel"""
        channel_name = args.get("channel_id", "").lstrip('#')
        description = args.get("description", "")
        scope = args.get("scope")
        is_default = args.get("is_default", False)
        
        if not channel_name:
            return self._error_response("Channel name is required")
        
        # Validate channel name format
        if not self._is_valid_channel_name(channel_name):
            return self._error_response(
                "Invalid channel name. Use lowercase letters, numbers, and hyphens only."
            )
        
        # Resolve scope
        final_scope = self._resolve_scope(scope, context)
        project_id = context.project_id if final_scope == 'project' else None
        
        # Create channel
        channel_id = await self.channels.create_channel(
            name=channel_name,
            scope=final_scope,
            project_id=project_id,
            description=description,
            created_by=agent['name'],
            created_by_project_id=agent['project_id'],
            is_default=is_default
        )
        
        if not channel_id:
            return self._error_response(f"Failed to create channel '{channel_name}'")
        
        # Auto-join creator to the channel
        await self.channels.join_channel(
            agent['name'], agent['project_id'], channel_id
        )
        
        return self._success_response(
            f"Created {final_scope} channel '{channel_name}' ({channel_id})"
        )
    
    async def handle_list_channels(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """List available channels (discoverable, including joinable ones)"""
        scope_filter = args.get("scope", "all")
        include_archived = args.get("include_archived", False)
        
        channels = await self.channels.list_available_channels(
            agent['name'], 
            agent['project_id'],
            scope_filter=scope_filter,
            include_archived=include_archived
        )
        
        # Filter by scope if requested
        if scope_filter != "all":
            channels = [c for c in channels if c['scope'] == scope_filter]
        
        # Format response
        if not channels:
            return self._success_response("No channels found")
        
        formatted = format_channel_list(channels, agent['name'])
        return self._success_response(formatted)
    
    async def handle_join_channel(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Join an open channel (replaces subscribe_to_channel)"""
        channel_name = args.get("channel_id", "").lstrip('#')
        scope = args.get("scope")
        
        if not channel_name:
            return self._error_response("Channel name is required")
        
        # Resolve channel ID
        channel_id = self._resolve_channel_id(channel_name, scope, context)
        
        # Join the channel
        success = await self.channels.join_channel(
            agent['name'], agent['project_id'], channel_id
        )
        
        if success:
            return self._success_response(f"Joined channel '{channel_name}'")
        else:
            return self._error_response(
                f"Failed to join '{channel_name}'. Channel may not exist or may require invitation."
            )
    
    async def handle_leave_channel(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Leave a channel (replaces unsubscribe_from_channel)"""
        channel_name = args.get("channel_id", "").lstrip('#')
        scope = args.get("scope")
        
        if not channel_name:
            return self._error_response("Channel name is required")
        
        # Resolve channel ID
        channel_id = self._resolve_channel_id(channel_name, scope, context)
        
        # Leave the channel
        success = await self.channels.leave_channel(
            agent['name'], agent['project_id'], channel_id
        )
        
        if success:
            return self._success_response(f"Left channel '{channel_name}'")
        else:
            return self._error_response(f"Failed to leave '{channel_name}'")
    
    async def handle_invite_to_channel(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Invite another agent to a members channel"""
        channel_name = args.get("channel_id", "").lstrip('#')
        invitee_name = args.get("invitee_id", "")
        scope = args.get("scope")
        
        if not channel_name or not invitee_name:
            return self._error_response("Channel name and invitee_id are required")
        
        # Resolve channel ID
        channel_id = self._resolve_channel_id(channel_name, scope, context)
        
        # Resolve invitee (could be in different project)
        invitee = await self._resolve_agent(invitee_name, context)
        if not invitee:
            return self._error_response(f"Agent '{invitee_name}' not found")
        
        # Perform invitation
        success = await self.channels.invite_to_channel(
            channel_id,
            invitee['name'],
            invitee['project_id'],
            agent['name'],  # inviter
            agent['project_id']
        )
        
        if success:
            return self._success_response(f"Invited {invitee_name} to '{channel_name}'")
        else:
            return self._error_response(
                f"Failed to invite. Check channel type and your permissions."
            )
    
    async def handle_list_my_channels(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """List agent's channels (replaces get_my_subscriptions)"""
        channels = await self.channels.list_channels_for_agent(
            agent['name'], 
            agent['project_id']
        )
        
        # Group by scope
        global_channels = [c['name'] for c in channels if c['scope'] == 'global']
        project_channels = [c['name'] for c in channels if c['scope'] == 'project']
        
        response = []
        if global_channels:
            response.append(f"Global channels: {', '.join(global_channels)}")
        if project_channels:
            response.append(f"Project channels: {', '.join(project_channels)}")
        if not response:
            response.append("No channel memberships")
        
        return self._success_response('\n'.join(response))
    
    # ============================================================================
    # Message Operations
    # ============================================================================
    
    async def handle_send_channel_message(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Send a message to a channel"""
        channel_name = args.get("channel_id", "").lstrip('#')
        content = args.get("content", "")
        scope = args.get("scope")
        metadata = args.get("metadata", {})
        thread_id = args.get("thread_id")
        
        if not channel_name or not content:
            return self._error_response("Channel name and content are required")
        
        # Resolve channel ID
        channel_id = self._resolve_channel_id(channel_name, scope, context)
        
        # Check if agent is member of channel
        is_member = await self.channels.is_channel_member(
            channel_id, agent['name'], agent['project_id']
        )
        
        if not is_member:
            return self._error_response(
                f"You must join '{channel_name}' before sending messages"
            )
        
        # Send message
        message_id = await self.db.send_message(
            channel_id=channel_id,
            sender_id=agent['name'],
            sender_project_id=agent['project_id'],
            content=content,
            metadata=metadata,
            thread_id=thread_id
        )
        
        if message_id:
            return self._success_response(f"Message sent to '{channel_name}' (ID: {message_id})")
        else:
            return self._error_response("Failed to send message")
    
    async def handle_send_direct_message(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Send a direct message to another agent"""
        recipient_name = args.get("recipient_id", "")
        content = args.get("content", "")
        scope = args.get("scope")
        metadata = args.get("metadata", {})
        
        if not recipient_name or not content:
            return self._error_response("Recipient and content are required")
        
        # Resolve recipient
        recipient = await self._resolve_agent(recipient_name, context)
        if not recipient:
            return self._error_response(f"Agent '{recipient_name}' not found")
        
        # Create or get DM channel
        dm_channel_id = await self.db.create_or_get_dm_channel(
            agent['name'], agent['project_id'],
            recipient['name'], recipient['project_id']
        )
        
        if not dm_channel_id:
            return self._error_response(
                f"Cannot create DM with {recipient_name}. Check their DM policy."
            )
        
        # Send message
        message_id = await self.db.send_message(
            channel_id=dm_channel_id,
            sender_id=agent['name'],
            sender_project_id=agent['project_id'],
            content=content,
            metadata=metadata
        )
        
        if message_id:
            return self._success_response(f"DM sent to {recipient_name}")
        else:
            return self._error_response("Failed to send DM")
    
    async def handle_get_messages(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Get messages for an agent"""
        since = args.get("since")
        limit = args.get("limit", 100)
        unread_only = args.get("unread_only", False)
        
        # Get agent's channels
        channels = await self.channels.list_channels_for_agent(
            agent['name'], agent['project_id']
        )
        
        # Build response structure
        response = {
            "global_messages": {
                "direct_messages": [],
                "channel_messages": {},
                "notes": []
            },
            "project_messages": None
        }
        
        # Get global channel messages
        global_channels = [c for c in channels if c['scope'] == 'global']
        for channel in global_channels:
            messages = await self.db.get_channel_messages(
                channel['id'], since=since, limit=limit // 5
            )
            if messages:
                response["global_messages"]["channel_messages"][channel['name']] = messages
        
        # Get global DMs
        global_dms = await self.db.get_direct_messages(
            agent['name'], scope='global', since=since, limit=limit // 5
        )
        response["global_messages"]["direct_messages"] = global_dms
        
        # Get agent's global notes
        global_notes = await self.notes.get_recent_notes(
            agent['name'], None, limit=limit // 5
        )
        if global_notes:
            response["global_messages"]["notes"] = global_notes
        
        # Get project messages if in project context
        if context.project_id:
            response["project_messages"] = {
                "project_id": context.project_id,
                "project_name": context.project_name,
                "direct_messages": [],
                "channel_messages": {},
                "notes": []
            }
            
            # Get project channel messages
            project_channels = [c for c in channels if c['scope'] == 'project']
            for channel in project_channels:
                messages = await self.db.get_channel_messages(
                    channel['id'], since=since, limit=limit // 5
                )
                if messages:
                    response["project_messages"]["channel_messages"][channel['name']] = messages
            
            # Get project DMs
            project_dms = await self.db.get_direct_messages(
                agent['name'], scope='project', project_id=context.project_id,
                since=since, limit=limit // 5
            )
            response["project_messages"]["direct_messages"] = project_dms
            
            # Get agent's project notes
            project_notes = await self.notes.get_recent_notes(
                agent['name'], context.project_id, limit=limit // 5
            )
            if project_notes:
                response["project_messages"]["notes"] = project_notes
        
        # Format response
        formatted = format_messages_concise(response, agent['name'])
        return self._success_response(formatted)
    
    async def handle_search_messages(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Search messages across channels and DMs"""
        query = args.get("query", "")
        scope = args.get("scope", "all")
        limit = args.get("limit", 50)
        
        if not query:
            return self._error_response("Search query is required")
        
        # Search based on scope
        results = await self.db.search_messages(
            query=query,
            agent_name=agent['name'],
            agent_project_id=agent['project_id'],
            scope=scope,
            limit=limit
        )
        
        if not results:
            return self._success_response("No messages found")
        
        # Format results
        formatted = []
        for msg in results:
            formatted.append(
                f"[{msg['timestamp']}] {msg['sender_id']} in {msg['channel_id']}: "
                f"{msg['content'][:100]}..."
            )
        
        return self._success_response('\n'.join(formatted))
    
    # ============================================================================
    # Project and Discovery Operations
    # ============================================================================
    
    async def handle_get_current_project(self, args: Dict, agent: Optional[Dict], 
                                        context: ProjectContext) -> Dict:
        """Get current project context"""
        if not context or not context.project_id:
            return self._success_response("No project context (global scope)")
        
        return self._success_response(
            f"project_id: {context.project_id}\n"
            f"project_name: {context.project_name}\n"
            f"project_path: {context.project_path}"
        )
    
    async def handle_list_projects(self, args: Dict, agent: Optional[Dict], 
                                  context: ProjectContext) -> Dict:
        """List all known projects"""
        projects = await self.db.list_projects()
        
        if not projects:
            return self._success_response("No projects registered")
        
        formatted = []
        for project in projects:
            formatted.append(
                f"- {project['name']} ({project['id'][:8]}): {project['path']}"
            )
        
        return self._success_response('\n'.join(formatted))
    
    async def handle_list_agents(self, args: Dict, agent: Optional[Dict], 
                                context: ProjectContext) -> Dict:
        """List discoverable agents"""
        scope = args.get("scope", "all")
        include_descriptions = args.get("include_descriptions", True)
        include_unavailable = args.get("include_unavailable", False)
        
        # Get discoverable agents using DatabaseManager
        if agent:
            # Use the discovering agent's perspective
            agents = await self.db.get_discoverable_agents(
                agent_name=agent['name'],
                agent_project_id=agent['project_id'],
                include_unavailable=include_unavailable
            )
        else:
            # No agent context - can't discover agents
            return self._success_response("Agent context required to discover other agents")
        
        if not agents:
            return self._success_response("No discoverable agents found")
        
        # Format response
        formatted = []
        for a in agents:
            name = a.get('discoverable_agent', a.get('name', 'unknown'))
            desc = a.get('discoverable_description', a.get('description', ''))
            status = a.get('discoverable_status', '')
            dm_policy = a.get('dm_policy', '')
            
            # Build agent info
            info = f"- {name}"
            if desc and include_descriptions:
                info += f": {desc}"
            if status and status != 'online':
                info += f" [{status}]"
            if dm_policy and dm_policy != 'open':
                info += f" (DM: {dm_policy})"
            
            formatted.append(info)
        
        return self._success_response('\n'.join(formatted))
    
    async def handle_get_linked_projects(self, args: Dict, agent: Optional[Dict], 
                                        context: ProjectContext) -> Dict:
        """Get linked projects for current project"""
        if not context or not context.project_id:
            return self._success_response("No project context")
        
        links = await self.db.get_project_links(context.project_id)
        
        if not links:
            return self._success_response("No linked projects")
        
        formatted = []
        for link in links:
            formatted.append(f"- {link['project_name']} ({link['project_id'][:8]})")
        
        return self._success_response('\n'.join(formatted))
    
    # ============================================================================
    # Notes Operations
    # ============================================================================
    
    async def handle_write_note(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Write a note to agent's private notes channel"""
        content = args.get("content", "")
        tags = args.get("tags", [])
        session_context = args.get("session_context")
        
        if not content:
            return self._error_response("Note content is required")
        
        # Write note
        note_id = await self.notes.write_note(
            agent['name'],
            agent['project_id'],
            content,
            tags=tags,
            session_id=session_context,  # Use session_id parameter
            metadata={"context": session_context} if session_context else None
        )
        
        if note_id:
            return self._success_response(f"Note saved (ID: {note_id})")
        else:
            return self._error_response("Failed to save note")
    
    async def handle_search_my_notes(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Search agent's own notes"""
        query = args.get("query")
        tags = args.get("tags", [])
        limit = args.get("limit", 50)
        
        notes = await self.notes.search_notes(
            agent['name'],
            agent['project_id'],
            query=query,
            tags=tags,
            limit=limit
        )
        
        if not notes:
            return self._success_response("No notes found")
        
        # Format notes
        formatted = []
        for note in notes:
            tags_str = f" [{', '.join(note['tags'])}]" if note.get('tags') else ""
            formatted.append(
                f"[{note['timestamp']}]{tags_str}: {note['content'][:100]}..."
            )
        
        return self._success_response('\n'.join(formatted))
    
    async def handle_get_recent_notes(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Get agent's recent notes"""
        limit = args.get("limit", 20)
        session_id = args.get("session_id")
        
        notes = await self.notes.get_recent_notes(
            agent['name'],
            agent['project_id'],
            limit=limit,
            session_id=session_id
        )
        
        if not notes:
            return self._success_response("No recent notes")
        
        # Format notes
        formatted = []
        for note in notes:
            formatted.append(f"[{note['timestamp']}]: {note['content']}")
        
        return self._success_response('\n'.join(formatted))
    
    async def handle_peek_agent_notes(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Peek at another agent's notes"""
        target_agent = args.get("target_agent", "")
        query = args.get("query")
        limit = args.get("limit", 20)
        
        if not target_agent:
            return self._error_response("Target agent is required")
        
        # Resolve target agent
        target = await self._resolve_agent(target_agent, context)
        if not target:
            return self._error_response(f"Agent '{target_agent}' not found")
        
        # Get notes (read-only peek)
        notes = await self.notes.peek_agent_notes(
            target['name'],
            target['project_id'],
            query=query,
            limit=limit
        )
        
        if not notes:
            return self._success_response(f"No notes found for {target_agent}")
        
        # Format notes
        formatted = [f"Notes from {target_agent}:"]
        for note in notes:
            formatted.append(f"[{note['timestamp']}]: {note['content'][:100]}...")
        
        return self._success_response('\n'.join(formatted))
    
    # ============================================================================
    # Helper Methods
    # ============================================================================
    
    async def _validate_and_get_agent(self, agent_id: str, 
                                     context: Optional[ProjectContext]) -> Optional[Dict]:
        """
        Validate agent exists and return agent data.
        
        Args:
            agent_id: Agent identifier from MCP tool
            context: Project context for scoping
            
        Returns:
            Agent dict with 'name' and 'project_id', or None if not found
        """
        # Parse agent_id (could be "name" or "name@project")
        if '@' in agent_id:
            name, project_hint = agent_id.split('@', 1)
        else:
            name = agent_id
            project_hint = None
        
        # Determine project_id
        if project_hint:
            # Explicit project specified
            project_id = await self._resolve_project_id(project_hint)
        else:
            # Use context project if available
            project_id = context.project_id if context else None
        
        # Check if agent exists
        agent = await self.db.get_agent(name, project_id)
        if agent:
            return {
                'name': agent['name'],
                'project_id': agent['project_id'],
                'description': agent.get('description')
            }
        
        # Try global agent if project agent not found
        if project_id:
            agent = await self.db.get_agent(name, None)
            if agent:
                return {
                    'name': agent['name'],
                    'project_id': None,
                    'description': agent.get('description')
                }
        
        return None
    
    async def _resolve_agent(self, agent_name: str, 
                            context: Optional[ProjectContext]) -> Optional[Dict]:
        """
        Resolve an agent name to full agent info.
        Similar to _validate_and_get_agent but for target agents.
        """
        return await self._validate_and_get_agent(agent_name, context)
    
    async def _resolve_project_id(self, project_hint: str) -> Optional[str]:
        """
        Resolve a project hint (name or partial ID) to full project ID.
        """
        # Could be project name or ID prefix
        projects = await self.db.list_projects()
        
        for project in projects:
            if (project['name'] == project_hint or 
                project['id'].startswith(project_hint)):
                return project['id']
        
        return None
    
    def _resolve_scope(self, requested_scope: Optional[str], 
                      context: Optional[ProjectContext]) -> str:
        """
        Resolve scope based on request and context.
        
        Args:
            requested_scope: Explicitly requested scope ('global' or 'project')
            context: Current project context
            
        Returns:
            'global' or 'project'
        """
        if requested_scope:
            return requested_scope
        
        # Default to project scope if in project context
        if context and context.project_id:
            return 'project'
        
        return 'global'
    
    def _resolve_channel_id(self, channel_name: str, scope: Optional[str],
                           context: Optional[ProjectContext]) -> str:
        """
        Resolve a channel name to full channel ID.
        
        Args:
            channel_name: Channel name (may include scope prefix)
            scope: Optional explicit scope
            context: Project context
            
        Returns:
            Full channel ID (e.g., "global:general" or "proj_abc123:dev")
        """
        # Check for explicit scope prefix
        if ':' in channel_name:
            return channel_name  # Already has scope prefix
        
        # Determine scope
        final_scope = self._resolve_scope(scope, context)
        
        if final_scope == 'global':
            return f"global:{channel_name}"
        else:
            # Project scope
            if context and context.project_id:
                project_id_short = context.project_id[:8]
                return f"proj_{project_id_short}:{channel_name}"
            else:
                # Fallback to global if no project context
                return f"global:{channel_name}"
    
    def _is_valid_channel_name(self, name: str) -> bool:
        """
        Validate channel name format.
        Must be lowercase alphanumeric with hyphens.
        """
        import re
        pattern = r'^[a-z0-9-]+$'
        return bool(re.match(pattern, name))
    
    def _success_response(self, content: str) -> Dict[str, Any]:
        """Create a success response"""
        return {
            'success': True,
            'content': content
        }
    
    def _error_response(self, error: str) -> Dict[str, Any]:
        """Create an error response"""
        return {
            'success': False,
            'error': error
        }