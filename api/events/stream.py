#!/usr/bin/env python3
"""
Simple Event Stream Manager
A lightweight, in-memory pub/sub system for real-time events.
No database, no polling - just fast event routing.
"""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, AsyncGenerator
from collections import deque, defaultdict
from enum import Enum

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)


class EventTopic(str, Enum):
    """Event topics for filtering"""
    ALL = "*"  # Special topic for all events
    MESSAGES = "messages"
    CHANNELS = "channels"
    MEMBERS = "members"
    AGENTS = "agents"
    NOTES = "notes"
    SYSTEM = "system"


@dataclass
class Event:
    """Structured event format for consistency"""
    id: str
    timestamp: float
    topic: str
    type: str  # e.g., "message.created", "channel.updated"
    payload: Dict[str, Any]
    
    # Optional metadata
    agent_name: Optional[str] = None
    agent_project_id: Optional[str] = None
    channel_id: Optional[str] = None
    project_id: Optional[str] = None
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event"""
        data = asdict(self)
        return (
            f"id: {self.id}\n"
            f"event: {self.type}\n"
            f"data: {json.dumps(data)}\n\n"
        )


class SimpleEventStream:
    """
    Simple in-memory event streaming with:
    - Ring buffer for recent events
    - Topic-based routing
    - Automatic cleanup
    - Backpressure handling
    - SSE formatting
    """
    
    def __init__(
        self,
        buffer_size: int = 10000,
        buffer_ttl_seconds: int = 60,
        max_queue_size: int = 1000
    ):
        """
        Initialize the event stream.
        
        Args:
            buffer_size: Max events to keep in memory
            buffer_ttl_seconds: How long to keep events in buffer
            max_queue_size: Max events per subscriber queue (backpressure)
        """
        self.logger = get_logger('SimpleEventStream', component='streaming')
        
        # Configuration
        self.buffer_size = buffer_size
        self.buffer_ttl = buffer_ttl_seconds
        self.max_queue_size = max_queue_size
        
        # Event buffer (ring buffer with TTL)
        self.event_buffer = deque(maxlen=buffer_size)
        
        # Subscriber management
        # Structure: {client_id: {topic: queue}}
        self.subscribers: Dict[str, Dict[str, asyncio.Queue]] = {}
        
        # Track subscriptions for cleanup
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)  # client_id -> topics
        
        # Statistics
        self.event_counter = 0
        self.dropped_events = 0
        
        # Lifecycle
        self._running = False
        self._cleanup_task = None
        
    async def start(self):
        """Start the event stream manager"""
        if self._running:
            return
            
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("Simple event stream started")
        
    async def stop(self):
        """Stop the event stream manager"""
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        # Clean up all subscribers
        for client_id in list(self.subscribers.keys()):
            await self.unsubscribe(client_id)
            
        self.logger.info("Simple event stream stopped")
        
    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: Dict[str, Any],
        **metadata
    ) -> str:
        """
        Emit an event to subscribers.
        
        Args:
            topic: Event topic (e.g., "messages", "channels")
            event_type: Event type (e.g., "message.created")
            payload: Event data
            **metadata: Optional metadata (agent_name, channel_id, etc.)
            
        Returns:
            Event ID
        """
        # Create structured event
        event = Event(
            id=f"evt_{self.event_counter}_{int(time.time() * 1000000)}",
            timestamp=time.time(),
            topic=topic,
            type=event_type,
            payload=payload,
            **{k: v for k, v in metadata.items() if k in Event.__dataclass_fields__}
        )
        self.event_counter += 1
        
        # Add to buffer for replay
        self.event_buffer.append(event)
        
        # Route to subscribers
        await self._route_event(event)
        
        return event.id
        
    async def _route_event(self, event: Event):
        """Route event to appropriate subscribers"""
        for client_id, client_topics in self.subscribers.items():
            # Check if client subscribes to this topic or ALL
            for topic in [event.topic, EventTopic.ALL]:
                if topic in client_topics:
                    queue = client_topics[topic]
                    try:
                        # Non-blocking put with backpressure handling
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        # Queue is full - drop oldest event and add new one
                        try:
                            queue.get_nowait()  # Drop oldest
                            queue.put_nowait(event)  # Add new
                            self.dropped_events += 1
                            self.logger.warning(
                                f"Queue full for {client_id}/{topic}, dropped oldest event"
                            )
                        except:
                            pass
                    break  # Don't send same event twice to same client
                    
    async def subscribe(
        self,
        client_id: str,
        topics: Optional[List[str]] = None,
        replay_recent: bool = True
    ) -> AsyncGenerator[Event, None]:
        """
        Subscribe to event stream.
        
        Args:
            client_id: Unique client identifier
            topics: List of topics to subscribe to (None = ALL)
            replay_recent: Whether to replay recent events on connect
            
        Yields:
            Events as they occur
        """
        # Default to ALL topics if none specified
        if not topics:
            topics = [EventTopic.ALL]
            
        # Create queues for each topic
        if client_id not in self.subscribers:
            self.subscribers[client_id] = {}
            
        for topic in topics:
            if topic not in self.subscribers[client_id]:
                queue = asyncio.Queue(maxsize=self.max_queue_size)
                self.subscribers[client_id][topic] = queue
                self.subscriptions[client_id].add(topic)
                
                # Replay recent events for this topic
                if replay_recent:
                    await self._replay_recent(queue, topic)
                    
        try:
            # Merge events from all topic queues
            while self._running:
                # Get events from any queue that has them
                for topic, queue in self.subscribers.get(client_id, {}).items():
                    try:
                        event = queue.get_nowait()
                        yield event
                    except asyncio.QueueEmpty:
                        continue
                        
                # Small delay to prevent busy loop
                await asyncio.sleep(0.01)
                
        finally:
            # Auto-cleanup on disconnect
            await self.unsubscribe(client_id)
            
    async def subscribe_sse(
        self,
        client_id: str,
        topics: Optional[List[str]] = None,
        last_event_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Subscribe with SSE formatting.
        
        Yields:
            SSE-formatted strings
        """
        # Send initial connection event
        yield (
            f"event: connected\n"
            f"data: {json.dumps({'client_id': client_id, 'topics': topics or ['*']})}\n\n"
        )
        
        # Replay missed events if reconnecting
        if last_event_id:
            await self._replay_since(client_id, last_event_id, topics)
            
        # Stream events as SSE
        async for event in self.subscribe(client_id, topics, replay_recent=not last_event_id):
            yield event.to_sse()
            
            # Periodic heartbeat
            if self.event_counter % 100 == 0:
                yield ":heartbeat\n\n"
                
    async def unsubscribe(self, client_id: str):
        """
        Unsubscribe client and clean up resources.
        
        Args:
            client_id: Client to unsubscribe
        """
        if client_id in self.subscribers:
            # Close all queues for this client
            for queue in self.subscribers[client_id].values():
                # Signal end of stream
                try:
                    queue.put_nowait(None)
                except:
                    pass
                    
            del self.subscribers[client_id]
            del self.subscriptions[client_id]
            self.logger.debug(f"Unsubscribed {client_id}")
            
    async def _replay_recent(self, queue: asyncio.Queue, topic: str):
        """Replay recent events for a topic to a new subscriber"""
        now = time.time()
        cutoff = now - self.buffer_ttl
        
        for event in self.event_buffer:
            # Skip expired events
            if event.timestamp < cutoff:
                continue
                
            # Match topic
            if topic == EventTopic.ALL or event.topic == topic:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    break  # Stop replay if queue is full
                    
    async def _replay_since(self, client_id: str, last_event_id: str, topics: Optional[List[str]]):
        """Replay events since a specific event ID"""
        # Parse timestamp from event ID
        try:
            parts = last_event_id.split('_')
            if len(parts) >= 3:
                last_timestamp = int(parts[2]) / 1000000
                
                # Find events after this timestamp
                for event in self.event_buffer:
                    if event.timestamp > last_timestamp:
                        # Check topic match
                        if not topics or EventTopic.ALL in topics or event.topic in topics:
                            # Add to appropriate queue
                            for topic in [event.topic, EventTopic.ALL]:
                                if topic in self.subscribers.get(client_id, {}):
                                    queue = self.subscribers[client_id][topic]
                                    try:
                                        queue.put_nowait(event)
                                    except asyncio.QueueFull:
                                        pass
                                    break
        except:
            pass  # Invalid event ID format
            
    async def _cleanup_loop(self):
        """Periodic cleanup of expired events"""
        while self._running:
            try:
                await asyncio.sleep(60)
                
                # Remove expired events from buffer
                now = time.time()
                cutoff = now - self.buffer_ttl
                
                while self.event_buffer and self.event_buffer[0].timestamp < cutoff:
                    self.event_buffer.popleft()
                    
                # Log statistics
                self.logger.info(
                    f"Stats: {len(self.subscribers)} subscribers, "
                    f"{len(self.event_buffer)} buffered events, "
                    f"{self.dropped_events} dropped"
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
                
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            'running': self._running,
            'subscribers': len(self.subscribers),
            'subscriptions': sum(len(topics) for topics in self.subscriptions.values()),
            'buffered_events': len(self.event_buffer),
            'total_events': self.event_counter,
            'dropped_events': self.dropped_events,
            'buffer_size': self.buffer_size,
            'buffer_ttl': self.buffer_ttl,
            'max_queue_size': self.max_queue_size
        }
        
    # Convenience methods for common event types
    
    async def emit_message(self, message_id: int, channel_id: str, 
                           sender_id: str, content: str, **kwargs):
        """Emit a message event"""
        return await self.emit(
            topic=EventTopic.MESSAGES,
            event_type="message.created",
            payload={
                'message_id': message_id,
                'channel_id': channel_id,
                'sender_id': sender_id,
                'content': content,
                **kwargs
            },
            channel_id=channel_id,
            agent_name=sender_id
        )
        
    async def emit_channel(self, channel_id: str, event_type: str, **payload):
        """Emit a channel event"""
        return await self.emit(
            topic=EventTopic.CHANNELS,
            event_type=f"channel.{event_type}",
            payload={'channel_id': channel_id, **payload},
            channel_id=channel_id
        )
        
    async def emit_member(self, channel_id: str, agent_name: str, 
                         event_type: str, **payload):
        """Emit a member event"""
        return await self.emit(
            topic=EventTopic.MEMBERS,
            event_type=f"member.{event_type}",
            payload={
                'channel_id': channel_id,
                'agent_name': agent_name,
                **payload
            },
            channel_id=channel_id,
            agent_name=agent_name
        )