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

__all__ = [
    'AgentManager',
    'DMPolicy',
    'Discoverability', 
    'DMPermission',
    'AgentInfo'
]