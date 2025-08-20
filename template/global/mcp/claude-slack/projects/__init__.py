"""
Projects Package - Project setup and management for Claude-Slack

This package contains managers for project initialization and setup.
"""

from .setup_manager import ProjectSetupManager
from .mcp_tools_manager import MCPToolsManager

__all__ = ['ProjectSetupManager', 'MCPToolsManager']