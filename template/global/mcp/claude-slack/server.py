#!/usr/bin/env python3
"""
Claude-Slack MCP Server
Channel-based messaging system for Claude Code agents with project isolation
"""

import os
import sys
import json
import sqlite3
import hashlib
import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from frontmatter import FrontmatterParser, FrontmatterUpdater
from db.manager import DatabaseManager
from admin_operations import AdminOperations
from transcript_parser import TranscriptParser

# Initialize server
app = Server("claude-slack")

# Configuration - ALWAYS use global paths
CLAUDE_DIR = os.path.expanduser("~/.claude")
DB_PATH = os.path.expanduser("~/.claude/data/claude-slack.db")

# Global managers
db_manager = None
admin_ops = None


class SessionContextManager:
    """
    Manages session contexts for project isolation using SQLite database.
    
    The PreToolUse hook writes session context to the database, and we read it here.
    Falls back to file-based storage if database is unavailable.
    """
    
    def __init__(self):
        self.db_path = Path(os.path.expanduser("~/.claude/data/claude-slack.db"))
        self.sessions_dir = Path(os.path.expanduser("~/.claude/data/claude-slack-sessions"))
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.cache = {}  # In-memory cache for performance
        self.cache_ttl = 60  # Cache for 60 seconds
        self.cache_times = {}
        self.current_session = None  # Track the most recent session
    
    async def get_context_for_session(self, session_id: str) -> Optional[dict]:
        """
        Get project context for a specific session from database.
        Falls back to file if database is unavailable.
        
        Args:
            session_id: Session ID to get context for
            
        Returns:
            Dict with project_id, project_path, project_name, transcript_path, scope or None
        """
        if not session_id:
            return None
        
        # Check cache first
        import time
        if session_id in self.cache:
            if time.time() - self.cache_times.get(session_id, 0) < self.cache_ttl:
                return self.cache[session_id]
        
        # Try database first
        try:
            async with aiosqlite.connect(str(self.db_path)) as db:
                async with db.execute("""
                    SELECT project_id, project_path, project_name, transcript_path, scope
                    FROM sessions 
                    WHERE id = ?
                """, (session_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                if row:
                    context = {
                        'project_id': row[0],
                        'project_path': row[1],
                        'project_name': row[2],
                        'transcript_path': row[3],
                        'scope': row[4]
                    }
                    # Update cache
                    self.cache[session_id] = context
                    self.cache_times[session_id] = time.time()
                    self.current_session = session_id
                    return context
        except Exception:
            # Database error, try file fallback
            pass
        
        # Fall back to file
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            try:
                with open(session_file, 'r') as f:
                    context = json.load(f)
                    # Update cache
                    self.cache[session_id] = context
                    self.cache_times[session_id] = time.time()
                    self.current_session = session_id
                    return context
            except Exception:
                pass
        
        # No context found, return global context
        return {
            'project_id': None,
            'project_path': None,
            'project_name': None,
            'transcript_path': None,
            'scope': 'global'
        }
    
    async def get_current_context(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get the current session's project context.
        This tries to use the most recent session ID from tool calls.
        
        Returns: (project_id, project_path, project_name, transcript_path)
        """
        # Try to get context from the most recent session
        if self.current_session:
            ctx = await self.get_context_for_session(self.current_session)
            if ctx:
                return ctx.get('project_id'), ctx.get('project_path'), ctx.get('project_name'), ctx.get('transcript_path')
        
        # Fall back to checking for any recent sessions in database
        try:
            async with aiosqlite.connect(str(self.db_path)) as db:
                async with db.execute("""
                    SELECT id FROM sessions 
                    WHERE updated_at > datetime('now', '-5 minutes')
                    ORDER BY updated_at DESC
                    LIMIT 1
                """) as cursor:
                    row = await cursor.fetchone()
                    
                if row:
                    session_id = row[0]
                    ctx = await self.get_context_for_session(session_id)
                    if ctx:
                        return ctx.get('project_id'), ctx.get('project_path'), ctx.get('project_name'), ctx.get('transcript_path')
        except Exception:
            pass
        
        return None, None, None, None
    
    def cleanup_old_sessions(self):
        """Remove old session files (database has automatic cleanup trigger)"""
        import time
        current_time = time.time()
        max_age_seconds = 24 * 3600  # 24 hours
        
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                if current_time - session_file.stat().st_mtime > max_age_seconds:
                    session_file.unlink()
            except Exception:
                pass


# Global session manager
session_manager = SessionContextManager()


async def initialize():
    """Initialize the server and database"""
    global db_manager, admin_ops
    
    # Ensure data directory exists
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)
    
    db_manager = DatabaseManager(DB_PATH)
    await db_manager.initialize()
    
    # Initialize admin operations
    admin_ops = AdminOperations(DB_PATH)
    
    # Create default global channels using AdminOperations
    success, msg = await admin_ops.create_default_channels()
    if not success:
        print(f"Warning: Failed to create default channels: {msg}", file=sys.stderr)


# create_default_channels function removed - now handled by AdminOperations


async def ensure_project_registered(project_id: str, project_path: str, project_name: str):
    """Ensure project is registered in database and create default channels"""
    global admin_ops
    
    # Use AdminOperations to register project and create channels
    success, msg = await admin_ops.register_project(project_path, project_name)
    if not success:
        print(f"Warning: Failed to register project: {msg}", file=sys.stderr)


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """List available messaging tools"""
    return [
        # Channel Operations
        types.Tool(
            name="create_channel",
            description="Create a new channel for topic-based discussions",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel name (without #)",
                        "pattern": "^[a-z0-9-]+$"
                    },
                    "description": {
                        "type": "string",
                        "description": "Channel description"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Channel scope: 'global' or 'project' (default: auto-detect)",
                        "enum": ["global", "project"]
                    },
                    "is_default": {
                        "type": "boolean",
                        "description": "Auto-subscribe new agents to this channel",
                        "default": False
                    }
                },
                "required": ["channel_id", "description"]
            }
        ),
        types.Tool(
            name="list_channels",
            description="List all available channels with subscription status",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": "Filter by scope: 'all', 'global', or 'project'",
                        "enum": ["all", "global", "project"],
                        "default": "all"
                    },
                    "include_archived": {
                        "type": "boolean",
                        "description": "Include archived channels",
                        "default": False
                    }
                },
                "required": ["agent_name"]
            }
        ),
        
        # Message Operations
        types.Tool(
            name="send_channel_message",
            description="Send a message to a channel (only subscribed agents will receive it)",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Target channel (without #)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Explicit scope: 'global' or 'project' (auto-detect if not provided)",
                        "enum": ["global", "project"]
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata (priority, tags, etc.)"
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Optional thread ID to reply to"
                    }
                },
                "required": ["agent_name", "channel_id", "content"]
            }
        ),
        types.Tool(
            name="send_direct_message",
            description="Send a private message to another agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipient_id": {
                        "type": "string",
                        "description": "Target agent's name (just the name, e.g., 'backend-engineer' or 'security-auditor')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Message scope: 'global' or 'project' (auto-detect if not provided)",
                        "enum": ["global", "project"]
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata (links to documents, etc.)"
                    }
                },
                "required": ["sender_id", "recipient_id", "content"]
            }
        ),
        types.Tool(
            name="get_messages",
            description="Get messages for an agent (channels + DMs) with scoped structure.  Use PROACTIVELY at the start of a new task or session to get proper context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "since": {
                        "type": "string",
                        "description": "ISO timestamp to get messages since"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages",
                        "default": 100
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only return unread messages",
                        "default": False
                    }
                },
                "required": ["agent_name"]
            }
        ),
        
        # Subscription Management
        types.Tool(
            name="subscribe_to_channel",
            description="Subscribe agent to a channel (updates frontmatter)",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel to subscribe to"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Channel scope: 'global' or 'project'",
                        "enum": ["global", "project"]
                    }
                },
                "required": ["agent_name", "channel_id"]
            }
        ),
        types.Tool(
            name="unsubscribe_from_channel",
            description="Unsubscribe agent from a channel (updates frontmatter)",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Channel to unsubscribe from"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Channel scope: 'global' or 'project'",
                        "enum": ["global", "project"]
                    }
                },
                "required": ["agent_name", "channel_id"]
            }
        ),
        types.Tool(
            name="get_my_subscriptions",
            description="Get an agent's channel subscriptions from frontmatter",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Agent name"
                    }
                },
                "required": ["agent_name"]
            }
        ),
        
        # Search Operations
        types.Tool(
            name="search_messages",
            description="Search messages across channels and DMs",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Search scope: 'all', 'global', or 'project'",
                        "enum": ["all", "global", "project"],
                        "default": "all"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 50
                    }
                },
                "required": ["query", "agent_name"]
            }
        ),
        
        # Project Operations
        types.Tool(
            name="get_current_project",
            description="Get information about the current project context",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="list_projects",
            description="List all known projects",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        # Agent Discovery
        types.Tool(
            name="list_agents",
            description="List all agents available for communication with their names and descriptions (respects project links)",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": "Filter agents by scope: 'all', 'global', 'project' (linked projects only), or 'current' (current project only)",
                        "enum": ["all", "global", "project", "current"],
                        "default": "all"
                    },
                    "include_descriptions": {
                        "type": "boolean",
                        "description": "Include agent descriptions",
                        "default": True
                    }
                },
                "required": []
            }
        ),
        
        # Project Link Status (read-only)
        types.Tool(
            name="get_linked_projects",
            description="View which projects are linked to the current project (read-only)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]

def get_scoped_channel_id(channel_name: str, scope: str, project_id: Optional[str] = None) -> str:
    """
    Get the full channel ID with scope prefix
    """
    if scope == 'global':
        return f"global:{channel_name}"
    else:
        if project_id:
            return f"proj_{project_id}:{channel_name}"
        else:
            # Fallback to global if no project context
            return f"global:{channel_name}"


async def get_agent_subscriptions(agent_name: str) -> Dict[str, List[str]]:
    """
    Get agent's channel subscriptions from frontmatter
    Returns dict with 'global' and 'project' channel lists
    """
    # Try project-local agent file first
    project_id, project_path, _ = await session_manager.get_current_context()
    
    # Check project agent file if in project context
    if project_path:
        project_claude = os.path.join(project_path, '.claude')
        agent_data = await FrontmatterParser.parse_agent_file(
            agent_name, project_claude
        )
        if agent_data:
            return agent_data.get('channels', {'global': [], 'project': []})
    
    # Fall back to global agent file
    agent_data = await FrontmatterParser.parse_agent_file(
        agent_name, CLAUDE_DIR
    )
    
    if agent_data:
        channels = agent_data.get('channels', {'global': [], 'project': []})
        # Handle old format (flat list)
        if isinstance(channels, list):
            return {
                'global': channels,
                'project': []
            }
        return channels
    
    # Default subscriptions if no agent file
    return {
        'global': ['general', 'announcements'],
        'project': []
    }


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls"""
    
    # Ensure database is initialized
    if not db_manager:
        await initialize()
    
    # Get session context from database (written by PreToolUse hook)
    # The hook detects the session_id and cwd, then writes the context
    # We read it here when needed for project-aware operations
    
    # Get current project context from session
    project_id, project_path, project_name, transcript_path = await session_manager.get_current_context()
    
    # Determine caller
    # Use TranscriptParser to get caller info for the specific tool being called
    if transcript_path and os.path.exists(transcript_path):
        parser = TranscriptParser(transcript_path)
        caller_info = parser.get_caller_info(tool_name=name)  # Pass the actual tool name
        caller = {
            "agent": caller_info.agent,
            "is_subagent": caller_info.is_subagent,
            "confidence": caller_info.confidence
        }
    else:
        caller = {"agent": "unknown", "is_subagent": False, "confidence": "LOW"}
    
    # Handle get_current_project
    if name == "get_current_project":
        
        if project_id:
            result = {
                "project_id": project_id,
                "project_name": project_name,
                "project_path": project_path
            }
        else:
            result = {
                "project_id": None,
                "project_name": "Global Context",
                "project_path": None
            }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    # Handle get_messages with scoped structure
    if name == "get_messages":
        agent_name = caller.get('agent', 'unknown')
        since = arguments.get("since")
        limit = arguments.get("limit", 100)
        unread_only = arguments.get("unread_only", False)
        
        # If we have a project context, ensure it's registered
        if project_id and project_path:
            await ensure_project_registered(project_id, project_path, project_name)
        
        # Get agent's subscriptions
        subscriptions = await get_agent_subscriptions(agent_name)
        
        # Build response structure
        response = {
            "global_messages": {
                "direct_messages": [],
                "channel_messages": {}
            },
            "project_messages": None
        }
        
        # Get global messages
        for channel in subscriptions['global']:
            channel_id = f"global:{channel}"
            messages = await db_manager.get_channel_messages(
                channel_id, since=since, limit=limit//4  # Divide limit
            )
            if messages:
                response["global_messages"]["channel_messages"][channel] = messages
        
        # Get global DMs
        global_dms = await db_manager.get_direct_messages(
            agent_name, scope='global', since=since, limit=limit//4
        )
        response["global_messages"]["direct_messages"] = global_dms
        
        # Get project messages if in project context
        if project_id:
            response["project_messages"] = {
                "project_id": project_id,
                "project_name": project_name,
                "direct_messages": [],
                "channel_messages": {}
            }
            
            # Get project channel messages
            for channel in subscriptions['project']:
                channel_id = f"proj_{project_id}:{channel}"
                messages = await db_manager.get_channel_messages(
                    channel_id, since=since, limit=limit//4
                )
                if messages:
                    response["project_messages"]["channel_messages"][channel] = messages
            
            # Get project DMs
            project_dms = await db_manager.get_direct_messages(
                agent_name, scope='project', project_id=project_id,
                since=since, limit=limit//4
            )
            response["project_messages"]["direct_messages"] = project_dms
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2)
        )]
    
    # Handle send_channel_message
    if name == "send_channel_message":
        agent_name = caller.get('agent', 'unknown')
        channel_name = arguments["channel_id"].lstrip('#')
        content = arguments["content"]
        scope = arguments.get("scope")
        metadata = arguments.get("metadata", {})
        thread_id = arguments.get("thread_id")
        
        # Determine scope
        if not scope:
            # If channel name has explicit scope prefix, use it
            if channel_name.startswith('global:'):
                scope = 'global'
                channel_name = channel_name.replace('global:', '')
            elif channel_name.startswith('project:'):
                scope = 'project'
                channel_name = channel_name.replace('project:', '')
            else:
                # Auto-detect: project scope if in project, else global
                scope = 'project' if project_id else 'global'
        
        # VALIDATION: Verify the channel is appropriate for the scope
        if scope == 'project' and not project_id:
            return [types.TextContent(
                type="text",
                text=f"❌ Cannot send to project channel '{channel_name}': Not in a project context. Use global channels or work within a project."
            )]
        
        # Get full channel ID
        channel_id = get_scoped_channel_id(channel_name, scope, project_id)
        
        # Check if channel exists (will be created if not, but we can note it)
        existing_channel = await db_manager.get_channel(channel_id)
        
        # Register the sender agent if needed
        await db_manager.register_agent(agent_name, project_id=project_id)
        
        # Send message (will create channel if it doesn't exist)
        message_id = await db_manager.send_channel_message(
            channel_id=channel_id,
            sender_id=agent_name,
            content=content,
            metadata=metadata,
            thread_id=thread_id
        )
        
        # Provide feedback about channel creation
        if not existing_channel:
            return [types.TextContent(
                type="text",
                text=f"📢 Created new {scope} channel #{channel_name} and sent message (ID: {message_id})"
            )]
        else:
            return [types.TextContent(
                type="text",
                text=f"📨 Message sent to {scope} channel #{channel_name} (ID: {message_id})"
            )]
    
    # Handle send_direct_message
    elif name == "send_direct_message":
        agent_name = caller.get('agent', 'unknown')
        recipient_id = arguments["recipient_id"]
        content = arguments["content"]
        scope = arguments.get("scope")
        metadata = arguments.get("metadata", {})
                
        # Determine scope if not provided
        if not scope:
            scope = "project" if project_id else "global"
        
        # VALIDATION: Find and verify the recipient exists and is accessible
        # Also handle duplicate names across projects
        all_matching_agents = []
        
        # Step 1: Check if recipient is a global agent
        global_recipient = await db_manager.get_agent(recipient_id, project_id=None)
        if global_recipient:
            all_matching_agents.append({
                'project_id': None,
                'project_name': 'Global',
                'scope': 'global',
                'accessible': True
            })
        
        # Step 2: Check current project (if we're in one)
        if project_id:
            project_recipient = await db_manager.get_agent(recipient_id, project_id)
            if project_recipient:
                all_matching_agents.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'scope': 'current_project',
                    'accessible': True
                })
            
            # Step 3: Check linked projects
            linked_projects = await db_manager.get_linked_projects(project_id)
            for linked_proj_id in linked_projects:
                linked_recipient = await db_manager.get_agent(recipient_id, linked_proj_id)
                if linked_recipient:
                    # Verify communication is allowed in the right direction
                    can_communicate = await db_manager.can_projects_communicate(
                        project_id, linked_proj_id
                    )
                    linked_proj = await db_manager.get_project(linked_proj_id)
                    all_matching_agents.append({
                        'project_id': linked_proj_id,
                        'project_name': linked_proj['name'] if linked_proj else "Unknown Project",
                        'scope': 'linked_project',
                        'accessible': can_communicate
                    })
        
        # Analyze results
        accessible_agents = [a for a in all_matching_agents if a['accessible']]
        inaccessible_agents = [a for a in all_matching_agents if not a['accessible']]
        
        # Handle different scenarios
        if len(accessible_agents) == 0:
            # No accessible agents found
            if len(inaccessible_agents) > 0:
                # Agent exists but not accessible
                blocked_projects = [a['project_name'] for a in inaccessible_agents]
                return [types.TextContent(
                    type="text",
                    text=f"❌ Cannot send message to '{recipient_id}': Agent exists in {', '.join(blocked_projects)} but projects are not linked for communication."
                )]
            else:
                # Agent doesn't exist at all - provide suggestions
                available_agents = await db_manager.get_agents_by_scope(
                    all_projects=True, 
                    current_project_id=project_id
                )
                agent_names = [a['name'] for a in available_agents]
                
                error_msg = f"❌ Cannot send message to '{recipient_id}': Agent not found.\n"
                
                # Check if there's a similar name (typo detection)
                similar_names = [name for name in agent_names if name.lower().startswith(recipient_id[:3].lower())]
                if similar_names:
                    error_msg += f"\nDid you mean one of these agents?\n"
                    for name in similar_names[:5]:
                        error_msg += f"  • {name}\n"
                else:
                    error_msg += f"\nUse 'list_agents' to see available agents."
                
                return [types.TextContent(
                    type="text",
                    text=error_msg
                )]
        
        elif len(accessible_agents) == 1:
            # Exactly one accessible agent - perfect!
            recipient_found = True
            recipient_project_id = accessible_agents[0]['project_id']
            recipient_project_name = accessible_agents[0]['project_name']
        
        else:
            # Multiple accessible agents with same name - ambiguous!
            error_msg = f"⚠️ Multiple agents named '{recipient_id}' found. Please specify which one:\n\n"
            
            # Show all accessible options
            for agent in accessible_agents:
                if agent['scope'] == 'global':
                    error_msg += f"  • Use scope='global' for the global agent\n"
                elif agent['scope'] == 'current_project':
                    error_msg += f"  • Agent in current project ({agent['project_name']}) - will be used by default\n"
                else:
                    error_msg += f"  • Agent in {agent['project_name']} (linked project)\n"
            
            error_msg += f"\nTip: To avoid ambiguity, use unique agent names across linked projects."
            
            # For now, use priority: current project > global > first linked
            # But warn the user about the ambiguity
            if any(a['scope'] == 'current_project' for a in accessible_agents):
                selected = next(a for a in accessible_agents if a['scope'] == 'current_project')
                recipient_found = True
                recipient_project_id = selected['project_id']
                recipient_project_name = selected['project_name']
                
                return [types.TextContent(
                    type="text",
                    text=f"⚠️ Multiple agents named '{recipient_id}' found. Sending to agent in current project ({recipient_project_name}). {error_msg}"
                )]
            elif any(a['scope'] == 'global' for a in accessible_agents):
                selected = next(a for a in accessible_agents if a['scope'] == 'global')
                recipient_found = True
                recipient_project_id = selected['project_id']
                recipient_project_name = selected['project_name']
                
                return [types.TextContent(
                    type="text",
                    text=f"⚠️ Multiple agents named '{recipient_id}' found. Sending to global agent. {error_msg}"
                )]
            else:
                # Multiple linked projects have the same agent name
                selected = accessible_agents[0]
                recipient_found = True
                recipient_project_id = selected['project_id']
                recipient_project_name = selected['project_name']
                
                return [types.TextContent(
                    type="text",
                    text=f"⚠️ Multiple agents named '{recipient_id}' found in linked projects. Sending to agent in {recipient_project_name}. {error_msg}"
                )]
        
        # Register the sender if needed (for message tracking)
        await db_manager.register_agent(sender_id, project_id=project_id)
        
        # Step 5: Send the direct message with validated recipient
        message_id = await db_manager.send_message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            project_id=project_id if scope == "project" else None,
            scope=scope,
            metadata=metadata
        )
        
        # Provide clear confirmation with recipient location
        confirmation = f"✅ Direct message sent to @{recipient_id}"
        if recipient_project_name:
            confirmation += f" ({recipient_project_name})"
        confirmation += f" - Message ID: {message_id}"
        
        return [types.TextContent(
            type="text",
            text=confirmation
        )]
    
    # Handle list_agents
    elif name == "list_agents":
        scope_filter = arguments.get("scope", "all")
        include_descriptions = arguments.get("include_descriptions", True)
        
        # Query agents from database based on scope
        agents = []
        
        if scope_filter in ["all", "global"]:
            # Get global agents (project_id IS NULL)
            global_agents = await db_manager.get_agents_by_scope(None)
            for agent in global_agents:
                agents.append({
                    "name": agent["name"],
                    "description": agent.get("description", "No description") if include_descriptions else None,
                    "scope": "global",
                    "project": None
                })
        
        if scope_filter in ["all", "project", "current"]:
            if scope_filter == "current" and not project_id:
                # No current project context
                pass
            else:
                # Get project agents - either current project or linked projects
                project_filter = project_id if scope_filter == "current" else None
                # Pass current_project_id to respect project links
                project_agents = await db_manager.get_agents_by_scope(
                    project_filter, 
                    all_projects=(scope_filter == "project"),
                    current_project_id=project_id
                )
                
                for agent in project_agents:
                    # Get project name for the agent
                    agent_project_name = project_name if agent.get("project_id") == project_id else agent.get("project_name", "Unknown Project")
                    agents.append({
                        "name": agent["name"],
                        "description": agent.get("description", "No description") if include_descriptions else None,
                        "scope": "project",
                        "project": agent_project_name
                    })
        
        # Format output
        if not agents:
            result_text = "No agents found for the specified scope."
        else:
            result_lines = [f"Found {len(agents)} agent(s):"]
            result_lines.append("")
            
            # Group by scope for better readability
            global_agents = [a for a in agents if a["scope"] == "global"]
            project_agents = [a for a in agents if a["scope"] == "project"]
            
            if global_agents:
                result_lines.append("🌍 Global Agents:")
                for agent in global_agents:
                    if include_descriptions:
                        result_lines.append(f"  • {agent['name']}: {agent['description']}")
                    else:
                        result_lines.append(f"  • {agent['name']}")
            
            if project_agents:
                if global_agents:
                    result_lines.append("")
                
                # Group by project
                projects = {}
                for agent in project_agents:
                    proj = agent['project'] or 'Unknown'
                    if proj not in projects:
                        projects[proj] = []
                    projects[proj].append(agent)
                
                for proj_name, proj_agents in projects.items():
                    result_lines.append(f"📁 Project: {proj_name}")
                    for agent in proj_agents:
                        if include_descriptions:
                            result_lines.append(f"  • {agent['name']}: {agent['description']}")
                        else:
                            result_lines.append(f"  • {agent['name']}")
            
            result_text = "\n".join(result_lines)
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle get_linked_projects
    elif name == "get_linked_projects":        
        if not project_id:
            return [types.TextContent(
                type="text",
                text="No project context. You're in global scope - project links don't apply here."
            )]
        
        # Get linked projects
        linked_project_ids = await db_manager.get_linked_projects(project_id)
        
        if not linked_project_ids:
            result_text = f"Project '{project_name}' has no linked projects.\n"
            result_text += "Cross-project communication is restricted to this project only."
        else:
            # Get project details
            linked_projects = []
            for linked_id in linked_project_ids:
                proj_info = await db_manager.get_project(linked_id)
                if proj_info:
                    linked_projects.append(proj_info['name'])
            
            result_text = f"Project '{project_name}' is linked to {len(linked_projects)} project(s):\n"
            for proj_name in linked_projects:
                result_text += f"  • {proj_name}\n"
            result_text += "\nAgents in these projects can discover and communicate with each other."
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle list_channels
    elif name == "list_channels":
        agent_name = agent_name = arguments.get("agent_name", caller.get('agent', 'unknown'))
        scope_filter = arguments.get("scope", "all")
        include_archived = arguments.get("include_archived", False)
        
        # Get agent's subscriptions to show subscription status
        subscriptions = await get_agent_subscriptions(agent_name)
        all_subscribed = subscriptions.get('global', []) + subscriptions.get('project', [])
        
        # Get channels based on scope
        channels = []
        
        if scope_filter in ["all", "global"]:
            # Get global channels
            global_channels = await db_manager.get_channels_by_scope('global')
            for channel in global_channels:
                if not include_archived and channel.get('is_archived'):
                    continue
                channel_name = channel['name']
                is_subscribed = channel_name in subscriptions.get('global', [])
                channels.append({
                    'scope': 'global',
                    'name': channel_name,
                    'id': channel['id'],
                    'description': channel.get('description', ''),
                    'subscribed': is_subscribed,
                    'is_default': channel.get('is_default', False)
                })
        
        if scope_filter in ["all", "project"] and project_id:
            # Get project channels
            project_channels = await db_manager.get_channels_by_scope('project', project_id)
            for channel in project_channels:
                if not include_archived and channel.get('is_archived'):
                    continue
                channel_name = channel['name']
                is_subscribed = channel_name in subscriptions.get('project', [])
                channels.append({
                    'scope': 'project',
                    'name': channel_name,
                    'id': channel['id'],
                    'description': channel.get('description', ''),
                    'subscribed': is_subscribed,
                    'is_default': channel.get('is_default', False),
                    'project_name': project_name
                })
        
        # Format output
        if not channels:
            result_text = "No channels found"
            if not project_id and scope_filter == "project":
                result_text += " (not in a project context)"
        else:
            result_text = f"Available Channels ({len(channels)} total):\n\n"
            
            # Group by scope
            global_chs = [c for c in channels if c['scope'] == 'global']
            project_chs = [c for c in channels if c['scope'] == 'project']
            
            if global_chs:
                result_text += "GLOBAL CHANNELS:\n"
                for ch in global_chs:
                    sub_marker = "✓" if ch['subscribed'] else " "
                    default_marker = "*" if ch['is_default'] else ""
                    result_text += f"  [{sub_marker}] #{ch['name']}{default_marker} - {ch['description']}\n"
            
            if project_chs:
                result_text += f"\nPROJECT CHANNELS ({project_name}):\n"
                for ch in project_chs:
                    sub_marker = "✓" if ch['subscribed'] else " "
                    default_marker = "*" if ch['is_default'] else ""
                    result_text += f"  [{sub_marker}] #{ch['name']}{default_marker} - {ch['description']}\n"
            
            result_text += "\n[✓] = Subscribed | * = Default channel"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle subscribe_to_channel
    elif name == "subscribe_to_channel":
        agent_name = arguments.get("agent_name", caller.get('agent', 'unknown'))
        channel_id = arguments.get("channel_id")
        scope = arguments.get("scope")
        
        # Auto-detect scope if not provided
        if not scope:
            if project_id:
                # Check if channel exists in project scope first
                project_channel_id = f"proj_{project_id}:{channel_id}"
                if await db_manager.channel_exists(project_channel_id):
                    scope = 'project'
                else:
                    scope = 'global'
            else:
                scope = 'global'
        
        # Update agent's frontmatter
        # Determine which directory to use (project or global)
        claude_dir = str(project_path) if project_path else CLAUDE_DIR
        
        # Add channel to appropriate scope using static method
        success = await FrontmatterUpdater.add_channel_subscription(
            agent_name, channel_id, scope, claude_dir
        )
        
        if success:
            result_text = f"✅ Subscribed to #{channel_id} ({scope} scope)"
            
            # Also register the subscription in database for quick lookup
            full_channel_id = get_scoped_channel_id(channel_id, scope, project_id)
            await db_manager.add_subscription(agent_name, full_channel_id)
        else:
            result_text = f"Failed to subscribe to #{channel_id} - may already be subscribed"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle unsubscribe_from_channel
    elif name == "unsubscribe_from_channel":
        agent_name = arguments.get("agent_name", caller.get('agent', 'unknown'))
        channel_id = arguments.get("channel_id")
        scope = arguments.get("scope")
        
        # Auto-detect scope if not provided
        if not scope:
            # Check current subscriptions to find which scope the channel is in
            subscriptions = await get_agent_subscriptions(agent_name)
            if channel_id in subscriptions.get('global', []):
                scope = 'global'
            elif channel_id in subscriptions.get('project', []):
                scope = 'project'
            else:
                return [types.TextContent(
                    type="text",
                    text=f"Not subscribed to #{channel_id} in any scope"
                )]
        
        # Update agent's frontmatter
        # Determine which directory to use (project or global)
        claude_dir = str(project_path) if project_path else CLAUDE_DIR
        
        # Remove channel from appropriate scope using static method
        success = await FrontmatterUpdater.remove_channel_subscription(
            agent_name, channel_id, scope, claude_dir
        )
        
        if success:
            result_text = f"✅ Unsubscribed from #{channel_id} ({scope} scope)"
            
            # Also remove from database
            full_channel_id = get_scoped_channel_id(channel_id, scope, project_id)
            await db_manager.remove_subscription(agent_name, full_channel_id)
        else:
            result_text = f"Failed to unsubscribe from #{channel_id}"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle get_my_subscriptions
    elif name == "get_my_subscriptions":
        agent_name = arguments.get("agent_name", caller.get('agent', 'unknown'))
        
        # Get subscriptions from frontmatter
        subscriptions = await get_agent_subscriptions(agent_name)
        
        result_text = f"Channel Subscriptions for {agent_name}:\n\n"
        
        # Global subscriptions
        global_subs = subscriptions.get('global', [])
        if global_subs:
            result_text += "GLOBAL CHANNELS:\n"
            for channel in global_subs:
                result_text += f"  • #{channel}\n"
        else:
            result_text += "GLOBAL CHANNELS: (none)\n"
        
        # Project subscriptions
        project_subs = subscriptions.get('project', [])
        if project_subs:
            if project_name:
                result_text += f"\nPROJECT CHANNELS ({project_name}):\n"
            else:
                result_text += "\nPROJECT CHANNELS:\n"
            for channel in project_subs:
                result_text += f"  • #{channel}\n"
        else:
            result_text += "\nPROJECT CHANNELS: (none)\n"
        
        # Add subscription statistics
        total = len(global_subs) + len(project_subs)
        result_text += f"\nTotal subscriptions: {total}"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle search_messages
    elif name == "search_messages":
        agent_name = arguments.get("agent_name", caller.get('agent', 'unknown'))
        query = arguments.get("query")
        scope_filter = arguments.get("scope", "all")
        limit = arguments.get("limit", 50)
        
        # Build search parameters based on scope
        search_params = {
            'query': query,
            'limit': limit
        }
        
        if scope_filter == "global":
            search_params['scope'] = 'global'
        elif scope_filter == "project" and project_id:
            search_params['scope'] = 'project'
            search_params['project_id'] = project_id
        # else: search all scopes
        
        # Get agent's accessible channels
        subscriptions = await get_agent_subscriptions(agent_name)
        accessible_channels = []
        
        if scope_filter in ["all", "global"]:
            for ch in subscriptions.get('global', []):
                accessible_channels.append(f"global:{ch}")
        
        if scope_filter in ["all", "project"] and project_id:
            for ch in subscriptions.get('project', []):
                accessible_channels.append(f"proj_{project_id}:{ch}")
        
        # Search messages
        results = await db_manager.search_messages(
            query=query,
            channels=accessible_channels,
            include_dms=True,
            agent_name=agent_name,
            limit=limit
        )
        
        if not results:
            result_text = f"No messages found matching '{query}'"
        else:
            result_text = f"Search Results for '{query}' ({len(results)} found):\n\n"
            
            for msg in results:
                # Format each message
                timestamp = msg.get('timestamp', 'unknown time')
                sender = msg.get('sender_id', 'unknown')
                content = msg.get('content', '')
                channel = msg.get('channel_id', 'direct')
                
                # Truncate long content
                if len(content) > 100:
                    content = content[:97] + "..."
                
                # Determine location
                if channel.startswith('global:'):
                    location = f"#{channel.split(':', 1)[1]} (global)"
                elif channel.startswith('proj_'):
                    location = f"#{channel.split(':', 1)[1]} (project)"
                else:
                    location = "DM"
                
                result_text += f"[{timestamp}] {sender} in {location}:\n"
                result_text += f"  {content}\n\n"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle create_channel
    elif name == "create_channel":
        channel_name = arguments.get("channel_id")  # Note: parameter is channel_id but it's the name
        description = arguments.get("description")
        scope = arguments.get("scope")
        is_default = arguments.get("is_default", False)
        
        # Auto-detect scope if not provided
        if not scope:
            scope = 'project' if project_id else 'global'
        
        # Validate we're in project context if creating project channel
        if scope == 'project' and not project_id:
            return [types.TextContent(
                type="text",
                text="Cannot create project channel - not in a project context"
            )]
        
        # Create the channel
        full_channel_id = get_scoped_channel_id(channel_name, scope, project_id)
        
        # Check if channel already exists
        if await db_manager.channel_exists(full_channel_id):
            return [types.TextContent(
                type="text",
                text=f"Channel #{channel_name} already exists in {scope} scope"
            )]
        
        # Create channel
        success = await db_manager.create_channel(
            channel_id=full_channel_id,
            project_id=project_id if scope == 'project' else None,
            scope=scope,
            name=channel_name,
            description=description,
            created_by=caller.get('agent', 'unknown'),
            is_default=is_default
        )
        
        if success:
            result_text = f"✅ Created channel #{channel_name} ({scope} scope)\n"
            result_text += f"Description: {description}\n"
            if is_default:
                result_text += "This is a default channel - new agents will auto-subscribe"
        else:
            result_text = f"Failed to create channel #{channel_name}"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle list_projects
    elif name == "list_projects":
        # Get all projects from database
        projects = await db_manager.list_all_projects()
        
        if not projects:
            result_text = "No projects registered yet"
        else:
            result_text = f"Registered Projects ({len(projects)} total):\n\n"
            
            # Group by activity
            active_projects = []
            inactive_projects = []
            
            for proj in projects:
                # Check if this is the current project
                is_current = proj['id'] == project_id if project_id else False
                
                # Check last activity
                last_active = proj.get('last_active')
                if last_active:
                    # Parse timestamp and check if active in last 7 days
                    from datetime import datetime, timedelta
                    try:
                        last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                        is_active = (datetime.now() - last_active_dt).days < 7
                    except:
                        is_active = False
                else:
                    is_active = False
                
                proj_info = {
                    'name': proj['name'],
                    'id': proj['id'],
                    'path': proj['path'],
                    'is_current': is_current,
                    'last_active': last_active
                }
                
                if is_active or is_current:
                    active_projects.append(proj_info)
                else:
                    inactive_projects.append(proj_info)
            
            # Display active projects
            if active_projects:
                result_text += "ACTIVE PROJECTS:\n"
                for proj in active_projects:
                    current_marker = " ← current" if proj['is_current'] else ""
                    result_text += f"  • {proj['name']}{current_marker}\n"
                    result_text += f"    Path: {proj['path']}\n"
                    result_text += f"    ID: {proj['id'][:8]}...\n"
            
            # Display inactive projects
            if inactive_projects:
                result_text += "\nINACTIVE PROJECTS:\n"
                for proj in inactive_projects[:5]:  # Limit to 5 to avoid clutter
                    result_text += f"  • {proj['name']}\n"
                if len(inactive_projects) > 5:
                    result_text += f"  ... and {len(inactive_projects) - 5} more\n"
        
        # Add project linking information if in project context
        if project_id:
            linked = await db_manager.get_linked_projects(project_id)
            if linked:
                result_text += f"\n{project_name} is linked to {len(linked)} project(s)"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    # Handle other tools...
    # (Additional tool handlers would go here)
    
    return [types.TextContent(
        type="text",
        text=f"Tool {name} not yet implemented"
    )]

# Note: get_caller_from_transcript function has been replaced by TranscriptParser class

async def main():
    """Main entry point for the MCP server"""
    await initialize()
    
    # Clean up old session files periodically
    session_manager.cleanup_old_sessions()
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Server error: {e}")
        sys.exit(1)