"""
Claude-Slack Infrastructure API
Simplified infrastructure for AI agent knowledge management with Qdrant.
"""

from .unified_api import ClaudeSlackAPI
from .models import AgentInfo, DMPolicy, Discoverability
from .exceptions import StorageError, QueryError, ValidationError
from .config import Config
from .ranking import RankingProfile, RankingProfiles

__version__ = "4.1.0"

__all__ = [
    "ClaudeSlackAPI",
    "AgentInfo",
    "DMPolicy",
    "Discoverability",
    "StorageError",
    "QueryError",
    "ValidationError",
    "Config",
    "RankingProfile",
    "RankingProfiles"
]