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

from utils.formatting import format_messages_concise, format_channel_list
from log_manager import get_logger


@dataclass
class ProjectContext:
    """Project context from session"""
    project_id: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    transcript_path: Optional[str] = None


class MCPToolOrchestrator:
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
        "write_note", "search_my_notes", "get_recent_notes", "peek_agent_notes",
        "list_agents"  # Added list_agents
    }
    
    def __init__(self, api):
        """
        Initialize the orchestrator with all required managers.
        
        Args:
            db_path: Path to the SQLite database
        """
        
        self.logger = get_logger('MCPToolOrchestrator', component='manager')
        
        # Initialize only the managers we actually use
        self.api = api
            
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
        channel_id = await self.api.create_channel(
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
        await self.api.join_channel(
            agent['name'], agent['project_id'], channel_id
        )
        
        return self._success_response(
            f"Created {final_scope} channel '{channel_name}' ({channel_id})"
        )
    
    async def handle_list_channels(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """List available channels (discoverable, including joinable ones)"""
        scope_filter = args.get("scope", "all")
        
        channels = await self.api.list_channels(
            agent_name=agent['name'], 
            project_id=agent['project_id'],
            scope_filter=scope_filter,
            include_archived=include_archived
        )
                
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
        success = await self.api.join_channel(
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
        success = await self.api.leave_channel(
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
        success = await self.api.invite_to_channel(
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
        channels = await self.api.db.sqlite.get_agent_channels(
            agent_name=agent['name'], 
            project_id=agent['project_id']
        )
        
        # Filter for only m
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
        is_member = await self.api.db.sqlite.is_channel_member(
            channel_id, agent['name'], agent['project_id']
        )
        
        if not is_member:
            return self._error_response(
                f"You must join '{channel_name}' before sending messages"
            )
        
        # Send message
        message_id = await self.api.send_message(
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
                        
        # Send message
        message_id = await self.api.send_direct_message(
            sender_name=agent['name'],
            recipient_name=recipient['name'],
            sender_project_id=agent['project_id'],
            recipient_project_id=recipient['project_id']
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
        
        # Get all messages accessible to the agent
        messages = await self.api.get_agent_messages(
            agent_name=agent['name'],
            agent_project_id=agent['project_id'],
            limit=limit,
            since=since
        )
        
        if not messages:
            return self._success_response("No recent messages")
        
        # Group messages by channel type and scope
        channel_messages = {}
        dm_messages = []
        
        for msg in messages:
            if msg.get('channel_type') == 'dm':
                dm_messages.append(msg)
            else:
                channel_name = msg.get('channel_name', msg['channel_id'])
                if channel_name not in channel_messages:
                    channel_messages[channel_name] = []
                channel_messages[channel_name].append(msg)
        
        # Format response
        formatted = []
        
        if dm_messages:
            formatted.append(f"=== Direct Messages ({len(dm_messages)}) ===")
            for msg in dm_messages[:10]:  # Limit to 10 most recent
                formatted.append(
                    f"[{msg['timestamp'][:16]}] {msg['sender_id']}: {msg['content'][:100]}"
                )
        
        if channel_messages:
            formatted.append(f"\n=== Channel Messages ===")
            for channel_name, msgs in list(channel_messages.items())[:5]:  # Top 5 channels
                formatted.append(f"\n#{channel_name} ({len(msgs)} messages):")
                for msg in msgs[:5]:  # Top 5 messages per channel
                    formatted.append(
                        f"  [{msg['timestamp'][:16]}] {msg['sender_id']}: {msg['content'][:80]}"
                    )
        
        if not formatted:
            return self._success_response("No recent messages")
            
        return self._success_response('\n'.join(formatted))
    
    async def handle_search_messages(self, args: Dict, agent: Dict, context: ProjectContext) -> Dict:
        """Search messages across channels and DMs with semantic search (v4)"""
        query = args.get("query", "")
        scope = args.get("scope", "all")
        limit = args.get("limit", 50)
        
        # v4 semantic search parameters
        ranking_profile = args.get("ranking_profile", "balanced")  # recent, quality, balanced, similarity
        message_type = args.get("message_type")  # e.g., "reflection", "decision"
        min_confidence = args.get("min_confidence")
        
        if not query:
            return self._error_response("Search query is required")
        
        # Search messages accessible to the agent (v4 with semantic search)
        results = await self.api.search_agent_messages(
            agent_name=agent['name'],
            agent_project_id=agent['project_id'],
            query=query,
            limit=limit,
            # v4 parameters
            ranking_profile=ranking_profile,
            message_type=message_type,
            min_confidence=min_confidence
        )
        
        if not results:
            return self._success_response("No messages found")
        
        # Format results (enhanced for v4 with search scores)
        formatted = [f"Found {len(results)} messages matching '{query}':\n"]
        for msg in results:
            channel_name = msg.get('channel_name', msg['channel_id'])
            
            # Include search scores if present (v4 semantic search)
            score_info = ""
            if 'search_scores' in msg:
                scores = msg['search_scores']
                if 'final_score' in scores:
                    score_info = f" [Score: {scores['final_score']:.2f}]"
                elif 'similarity' in scores:
                    score_info = f" [Similarity: {scores['similarity']:.2f}]"
            
            formatted.append(
                f"[{msg['timestamp'][:16]}]{score_info} {msg['sender_id']} in #{channel_name}: "
                f"{msg['content'][:100]}{'...' if len(msg['content']) > 100 else ''}"
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
        projects = await self.api.db.list_projects()
        
        if not projects:
            return self._success_response("No projects registered")
        
        formatted = []
        for project in projects:
            formatted.append(
                f"- {project['name']} ({project['id'][:8]}): {project['path']}"
            )
        
        return self._success_response('\n'.join(formatted))
    
    async def handle_list_agents(self, args: Dict, agent: Dict, 
                                context: ProjectContext) -> Dict:
        """List discoverable agents"""
        scope = args.get("scope", "all")
        include_descriptions = args.get("include_descriptions", True)
        
        # Use the discovering agent's perspective
        agents = await self.api.get_messagable_agents(
            agent_name=agent['name'],
            agent_project_id=agent['project_id'],
        )
        
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
        
        links = await self.api.db.sqlite.get_project_links(context.project_id)
        
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
        metadata = args.get("metadata")
        
        if not content:
            return self._error_response("Note content is required")
        
        # Write note
        note_id = await self.api.write_note(
            agent_name=agent['name'],
            agent_project_id=agent['project_id'],
            content=content,
            tags=tags,
            metadata=metadata
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
        
        notes = await self.api.search_agent_notes(
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
        session_id = args.get("session_id")  # Not used by current implementation
        
        notes = await self.api.get_recent_notes(
            agent['name'],
            agent['project_id'],
            limit=limit
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
        notes = await self.api.peek_agent_notes(
            target_agent_name=target['name'],
            target_project_id=target['project_id'],
            requester_name=agent['name'],
            requester_project_id=agent['project_id'],
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
        agent = await self.api.get_agent(name, project_id)
        if agent:
            return {
                'name': agent['name'],
                'project_id': agent['project_id'],
                'description': agent.get('description')
            }
        
        # Try global agent if project agent not found
        if project_id:
            agent = await self.api.get_agent(name, None)
            if agent:
                return {
                    'name': agent['name'],
                    'project_id': None,
                    'description': agent.get('description')
                }
            
            # Try linked projects if we have a context
            if context and context.project_id:
                linked_projects = await self.api.db.sqlite.get_project_links(context.project_id)
                for link in linked_projects:
                    agent = await self.api.get_agent(name, link['project_id'])
                    if agent:
                        return {
                            'name': agent['name'],
                            'project_id': agent['project_id'],
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
        projects = await self.api.db.list_projects()
        
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