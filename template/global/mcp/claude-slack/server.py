#!/usr/bin/env python3
"""
Claude-Slack MCP Server (Cleaned Version with MCPToolOrchestrator)
Channel-based messaging system for Claude Code agents with project isolation
"""

import os
import sys
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from api.unified_api import ClaudeSlackAPI

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.environment_config import env_config
from utils.tool_orchestrator import MCPToolOrchestrator, ProjectContext
from utils.performance import timing_decorator, Timer, get_performance_summary
from sessions.manager import SessionManager

# Initialize server
app = Server("claude-slack")

# Configuration - Use environment-aware paths
CLAUDE_DIR = str(env_config.global_claude_dir)
DB_PATH = str(env_config.db_path)

# Global managers (only what server.py directly uses)
session_manager = None  # For session context resolution
tool_orchestrator = None  # For all tool execution
api = None

# Set up logging - use new centralized logging system
try:
    from log_manager.manager import get_logger
    logger = get_logger('server')
    
    # Helper functions for structured logging  
    def log_json_data(logger, message, data, level=logging.DEBUG):
        """Log data as JSON for structured logging"""
        logger.log(level, f"{message}: {json.dumps(data, default=str)}")
    
    def log_db_result(logger, operation, success, data=None):
        """Log database operation results"""
        level = logging.DEBUG if success else logging.WARNING
        status = "Success" if success else "Failed"
        msg = f"DB {operation}: {status}"
        if data:
            log_json_data(logger, msg, data, level)
        else:
            logger.log(level, msg)
except ImportError:
    # Fallback logging if centralized system not available
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    def log_json_data(l, m, d, level=logging.DEBUG): pass
    def log_db_result(l, o, s, d=None): pass
    


async def initialize():
    """Initialize the server and database"""
    global api, session_manager, tool_orchestrator
    
    # Ensure data directory exists
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)
    
    # Initialize the api
    api = ClaudeSlackAPI(db_path = DB_PATH, qdrant_url=os.getenv('QDRANT_URL', 'http://localhost:6333'))
    await api.initialize()
    
    # Initialize session manager (needed for session context resolution)
    session_manager = SessionManager(api)
    
    # Initialize tool orchestrator (handles all tool execution)
    tool_orchestrator = MCPToolOrchestrator(api)
    
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
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
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
                "required": ["agent_id", "channel_id", "description"]
            }
        ),
        types.Tool(
            name="list_channels",
            description="List all channels you could join (shows which ones you're already a member of)",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
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
                "required": ["agent_id"]
            }
        ),
        
        # Message Operations
        types.Tool(
            name="send_channel_message",
            description="Send a message to a channel (only agents who are members of this channel will receive it)",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Channel name where to send message (must be a member first)"
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
                "required": ["agent_id", "channel_id", "content"]
            }
        ),
        types.Tool(
            name="send_direct_message",
            description="Send a private message to another agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "recipient_id": {
                        "type": "string",
                        "description": "Target agent's name (e.g. 'backend-engineer', 'frontend-dev', 'assistant')"
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
                "required": ["agent_id", "recipient_id", "content"]
            }
        ),
        types.Tool(
            name="get_messages",
            description="Check for new messages from your channels and DMs, or get specific messages by ID. TIP: Call this at the start of each session to catch up on context",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "message_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional list of specific message IDs to retrieve"
                    },
                    "since": {
                        "type": "string",
                        "description": "ISO timestamp to get messages since (ignored if message_ids provided)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages (ignored if message_ids provided)",
                        "default": 100
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only return unread messages (ignored if message_ids provided)",
                        "default": False
                    }
                },
                "required": ["agent_id"]
            }
        ),
        
        # Subscription Management (v3: maps to join/leave)
        types.Tool(
            name="join_channel",
            description="Join a channel and receive messages from the specified channel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Channel name to join (e.g. 'general', 'backend', 'dev')"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Where to look for channel: 'global' for system-wide, 'project' for current project only (defaults to project)",
                        "enum": ["global", "project"]
                    }
                },
                "required": ["agent_id", "channel_id"]
            }
        ),
        types.Tool(
            name="leave_channel",
            description="Leave a channel.  You will no longer recieve messages from this channel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Channel to leave"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Channel scope: 'global' or 'project'",
                        "enum": ["global", "project"]
                    }
                },
                "required": ["agent_id", "channel_id"]
            }
        ),
        types.Tool(
            name="list_my_channels",
            description="List only the channels you've already joined (your active subscriptions)",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                        }
                    },
                "required": ["agent_id"]
            }
        ),
        types.Tool(
            name="list_channel_members",
            description="List all members of a specific channel, including their permissions and join information",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Channel name (without # prefix)"
                    },
                    "scope": {
                        "type": "string",
                        "description": "Channel scope: 'global' or 'project' (defaults to project)",
                        "enum": ["global", "project"]
                    }
                },
                "required": ["agent_id", "channel_id"]
            }
        ),
        
        # Search Operations
        types.Tool(
            name="search_messages",
            description="Search messages across channels and DMs",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
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
                "required": ["agent_id", "query"]
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
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
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
                "required": ["agent_id"]
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
        # Agent Notes Tools
        types.Tool(
            name="write_note",
            description="Save a note for your future self - findings, solutions, gotchas, etc. TIP: Write notes after completing tasks so you remember next time",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Note content"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags (e.g., ['learned', 'solution', 'debug'])"
                    },
                    "session_context": {
                        "type": "string",
                        "description": "Optional session context or task description"
                    }
                },
                "required": ["agent_id", "content"]
            }
        ),
        types.Tool(
            name="search_my_notes",
            description="Search your own notes by content or tags",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query for content"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 50
                    }
                },
                "required": ["agent_id"]
            }
        ),
        types.Tool(
            name="get_recent_notes",
            description="Get your most recent notes",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of notes to retrieve",
                        "default": 20
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Filter by specific session ID"
                    }
                },
                "required": ["agent_id"]
            }
        ),
        types.Tool(
            name="peek_agent_notes",
            description="Peek at another agent's notes (for learning or debugging)",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Your unique agent identifier (REQUIRED)"
                    },
                    "target_agent": {
                        "type": "string",
                        "description": "Name of the agent whose notes to peek at"
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 20
                    }
                },
                "required": ["agent_id", "target_agent"]
            }
        ),
        
        # Performance Diagnostics
        types.Tool(
            name="get_performance_stats",
            description="Get performance statistics for debugging slow tool calls",
            inputSchema={
                "type": "object",
                "properties": {
                    "component": {
                        "type": "string",
                        "description": "Filter by component (server/orchestrator/database)",
                        "enum": ["all", "server", "orchestrator", "database"]
                    },
                    "reset": {
                        "type": "boolean",
                        "description": "Reset statistics after retrieving",
                        "default": False
                    }
                },
                "required": []
            }
        ),
    ]

# Keep the validate_agent_and_provide_help function for backward compatibility
async def validate_agent_and_provide_help(agent_id: Optional[str], project_id: Optional[str]) -> Tuple[bool, str, Optional[str]]:
    """
    Validate that an agent_id exists and provide helpful error messages.
    This is kept for backward compatibility but is now handled by orchestrator.
    """
    if not agent_id:
        error_msg = """Missing agent_id parameter. Please provide your agent identifier.

Example: If your agent frontmatter has 'name: alice', use:
{
  "agent_id": "alice",
  ...
}"""
        return False, error_msg, None
    
    # The orchestrator handles actual validation
    return True, "", agent_id

@app.call_tool()
@timing_decorator('server')
async def call_tool(name: str, arguments: Dict[str, Any]) -> list[types.TextContent]:
    """
    Handle tool calls using MCPToolOrchestrator.
    
    This function:
    1. Ensures the system is initialized
    2. Resolves session context for project information
    3. Delegates to MCPToolOrchestrator for execution
    4. Returns formatted response to MCP client
    """
    
    logger.debug(f"Tool {name} called with args: {arguments}")
    
    # Ensure system is initialized
    with Timer('initialization_check', 'server'):
        if not tool_orchestrator:
            await initialize()
    
    # Get current project context from session by matching tool call
    # The PreToolUse hook records the full MCP tool name, so we need to prepend it
    with Timer('session_resolution', 'server'):
        full_tool_name = f"mcp__claude-slack__{name}"
        session_id = await session_manager.match_tool_call_session(full_tool_name, arguments)
        logger.debug(f"Session ID resolved: {session_id}")
    
    # Get session context if available
    with Timer('context_retrieval', 'server'):
        ctx = await session_manager.get_session_context(session_id) if session_id else None
    
    # Create ProjectContext for orchestrator
    context = None
    if ctx:
        logger.debug(f"Session context resolved: project_id: {ctx.project_id}, "
                    f"project_path: {ctx.project_path}, project_name: {ctx.project_name}, "
                    f"transcript_path: {ctx.transcript_path}")
        
        context = ProjectContext(
            project_id=ctx.project_id,
            project_path=ctx.project_path,
            project_name=ctx.project_name,
            transcript_path=ctx.transcript_path
        )
    
    # Handle performance diagnostics tool directly
    if name == "get_performance_stats":
        from utils.performance import PERF_ENABLED
        
        if not PERF_ENABLED:
            return [types.TextContent(
                type="text", 
                text="Performance monitoring is disabled.\n\n"
                     "To enable, set environment variable: CLAUDE_SLACK_PERF=1\n"
                     "Then restart the MCP server."
            )]
        
        component_filter = arguments.get('component', 'all')
        reset = arguments.get('reset', False)
        
        summary = get_performance_summary()
        
        # Filter by component if requested
        if component_filter != 'all':
            summary = {k: v for k, v in summary.items() if k == component_filter}
        
        # Format the output
        output = ["=== Performance Statistics ===\n"]
        for comp, stats in summary.items():
            output.append(f"\n{comp.upper()}:")
            output.append(f"  Total calls: {stats['total_calls']}")
            output.append(f"  Avg duration: {stats['avg_duration_ms']}ms")
            output.append(f"  Min/Max: {stats['min_duration_ms']}ms / {stats['max_duration_ms']}ms")
            output.append(f"  Slow calls (>100ms): {stats['slow_calls']}")
            
            if stats['by_function']:
                output.append("  By function:")
                for func, fstats in stats['by_function'].items():
                    output.append(f"    {func}: {fstats['calls']} calls, avg {fstats['avg_ms']}ms")
        
        if reset:
            from utils.performance import reset_performance_data
            reset_performance_data()
            output.append("\n[Performance data reset]")
        
        return [types.TextContent(type="text", text="\n".join(output))]
    
    # Execute tool using orchestrator
    try:
        with Timer(f'tool_execution_{name}', 'server'):
            result = await tool_orchestrator.execute_tool(name, arguments, context)
        
        # Format response based on result
        if result['success']:
            return [types.TextContent(
                type="text",
                text=result['content']
            )]
        else:
            # Error response
            return [types.TextContent(
                type="text",
                text=result.get('error', 'Unknown error occurred')
            )]
    
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=f"Internal error: {str(e)}"
        )]

async def main():
    """Main entry point for the MCP server"""
    logger.info("Starting Claude-Slack MCP server")
    
    try:
        await initialize()
        
        # Clean up old sessions periodically
        await session_manager.cleanup_old_sessions()
        
        logger.info("MCP server initialized successfully")
        
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP server running on stdio transport")
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    except KeyboardInterrupt:
        logger.info("MCP server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in MCP server: {e}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    try:
        logger.info("Starting MCP server from main")
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Server error: {e}")
        sys.exit(1)