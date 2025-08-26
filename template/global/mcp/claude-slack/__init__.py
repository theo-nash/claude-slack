"""
Claude-Slack MCP Server Package
Channel-based messaging system for Claude Code agents with project isolation

Version 3.0 Features:
- Unified membership model (no separate subscriptions)
- MCPToolOrchestrator for clean tool handling
- Project-based isolation
- Agent notes system
- Simplified architecture
"""

__version__ = "3.0.0"
__author__ = "Claude-Slack Contributors"

# Note: Due to the package name containing a hyphen, this package is primarily
# designed to be run as a standalone MCP server via server.py, not imported as a library.
# 
# To run the server:
#   python server.py
#
# The submodules can be imported individually when needed:
#   from db.manager import DatabaseManager
#   from mcp.tool_orchestrator import MCPToolOrchestrator
#   etc.