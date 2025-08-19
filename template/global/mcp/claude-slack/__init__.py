"""
Claude-Slack MCP Server Package
Channel-based messaging system for Claude Code agents
"""

__version__ = "1.0.0"
__author__ = "Claude-Slack Contributors"

# Make the package importable
from . import server
from . import db
from . import frontmatter

__all__ = ['server', 'db', 'frontmatter']