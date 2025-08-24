"""
Agent management module for Claude-Slack v3
"""

from .manager_v3 import (
    AgentManagerV3,
    DMPolicy,
    Discoverability,
    DMPermission,
    AgentInfo
)

__all__ = [
    'AgentManagerV3',
    'DMPolicy',
    'Discoverability', 
    'DMPermission',
    'AgentInfo'
]