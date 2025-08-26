"""
Projects Package - Project setup and management for Claude-Slack

This package contains managers for project initialization and setup.
Note: ProjectSetupManager is deprecated in v3 - use ConfigSyncManager instead.
"""

# Only import non-deprecated modules
from .mcp_tools_manager import MCPToolsManager

__all__ = ['MCPToolsManager']