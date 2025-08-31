"""
Event System for Claude-Slack API
Provides real-time event streaming with in-memory pub/sub.
"""

from .stream import (
    SimpleEventStream,
    EventTopic,
    Event
)

from .proxy import (
    AutoEventProxy,
    with_events
)

__all__ = [
    # Stream components
    'SimpleEventStream',
    'EventTopic', 
    'Event',
    
    # Proxy components
    'AutoEventProxy',
    'with_events'
]