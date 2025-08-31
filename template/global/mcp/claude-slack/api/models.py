"""
Data models for Claude-Slack API.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any, List
from datetime import datetime
from enum import Enum


@dataclass
class Message:
    """
    Message with natural nested metadata.
    
    Attributes:
        id: Unique message identifier
        channel_id: Channel where message was posted
        sender_id: Agent who sent the message
        content: Message text content
        metadata: Arbitrary nested JSON metadata
        confidence: Optional confidence score (0.0 to 1.0)
        timestamp: ISO format timestamp
        score: Search relevance score (set during search operations)
    """
    id: int
    channel_id: str
    sender_id: str
    content: str
    metadata: Dict[str, Any] = None
    confidence: Optional[float] = None
    timestamp: Optional[str] = None
    score: Optional[float] = None
    search_scores: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize defaults."""
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Export as dictionary."""
        return asdict(self)
    
    def get_nested(self, path: str, default=None) -> Any:
        """
        Get value from nested metadata using dot notation.
        
        Args:
            path: Dot-separated path (e.g., "breadcrumbs.task")
            default: Default value if path not found
            
        Returns:
            Value at path or default
        """
        keys = path.split('.')
        value = self.metadata
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        
        return value


@dataclass
class SearchResult:
    """
    Search result with scoring information.
    
    Attributes:
        message: The message object
        similarity_score: Vector similarity score (0.0 to 1.0)
        final_score: Combined score after ranking
        scores: Detailed scoring breakdown
    """
    message: Message
    similarity_score: float
    final_score: float
    scores: Optional[Dict[str, float]] = None
    
    def __post_init__(self):
        """Set message score."""
        self.message.score = self.final_score


@dataclass
class AggregationResult:
    """
    Aggregation result for grouped data.
    
    Attributes:
        value: The grouped value
        count: Number of items in group
        metrics: Additional computed metrics
    """
    value: Any
    count: int
    metrics: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize defaults."""
        if self.metrics is None:
            self.metrics = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Export as dictionary."""
        return {
            "value": self.value,
            "count": self.count,
            **self.metrics
        }
        
@dataclass
class AgentInfo:
    """Agent information"""
    name: str
    project_id: Optional[str]
    description: Optional[str]
    status: str
    dm_policy: str
    discoverable: str
    project_name: Optional[str] = None
    dm_availability: Optional[str] = None
    has_existing_dm: bool = False

class DMPolicy(Enum):
    """DM policy options for agents"""
    OPEN = 'open'           # Accept DMs from anyone
    RESTRICTED = 'restricted'  # Only from allowlist
    CLOSED = 'closed'       # No DMs allowed


class Discoverability(Enum):
    """Agent discoverability settings"""
    PUBLIC = 'public'       # Visible to all
    PROJECT = 'project'     # Visible in linked projects
    PRIVATE = 'private'     # Not discoverable


class DMPermission(Enum):
    """DM permission types"""
    ALLOW = 'allow'
    BLOCK = 'block'