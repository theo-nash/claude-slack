"""
Frontmatter module for Claude-Slack
Handles parsing and updating agent frontmatter for channel subscriptions
"""

from .parser import FrontmatterParser
from .updater import FrontmatterUpdater

__all__ = ['FrontmatterParser', 'FrontmatterUpdater']