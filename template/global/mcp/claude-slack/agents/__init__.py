"""
Agent management module for Claude-Slack
"""

from .manager import (
    AgentManager,
    DMPolicy,
    Discoverability,
    DMPermission,
    AgentInfo
)

from .mcp_tools_manager import MCPToolsManager

__all__ = [
    'AgentManager',
    'DMPolicy',
    'Discoverability', 
    'DMPermission',
    'AgentInfo',
    'MCPToolsManager'
]