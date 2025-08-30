#!/usr/bin/env python3
"""
Event Proxy - Automatic event emission based on method naming conventions.
Wraps any object and emits events when specific methods are called.
"""

import asyncio
from typing import Any, Dict, Optional, Tuple
from functools import wraps

from .stream import EventTopic

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)


class AutoEventProxy:
    """
    Automatically emits events based on method naming conventions.
    
    This proxy wraps any object and intercepts method calls,
    emitting events when methods match predefined patterns.
    """
    
    # Method name/prefix -> (event_type, topic) mapping
    EVENT_RULES = {
        # Message operations
        'send_message': ('message.created', EventTopic.MESSAGES),
        'update_message': ('message.updated', EventTopic.MESSAGES),
        'edit_message': ('message.edited', EventTopic.MESSAGES),
        'delete_message': ('message.deleted', EventTopic.MESSAGES),
        
        # Channel operations
        'create_channel': ('channel.created', EventTopic.CHANNELS),
        'create_or_get_dm_channel': ('channel.dm_created', EventTopic.CHANNELS),
        'update_channel': ('channel.updated', EventTopic.CHANNELS),
        'archive_channel': ('channel.archived', EventTopic.CHANNELS),
        'delete_channel': ('channel.deleted', EventTopic.CHANNELS),
        
        # Member operations
        'join_channel': ('member.joined', EventTopic.MEMBERS),
        'leave_channel': ('member.left', EventTopic.MEMBERS),
        'add_channel_member': ('member.added', EventTopic.MEMBERS),
        'remove_channel_member': ('member.removed', EventTopic.MEMBERS),
        'update_member': ('member.updated', EventTopic.MEMBERS),
        
        # Agent operations
        'register_agent': ('agent.registered', EventTopic.AGENTS),
        'update_agent': ('agent.updated', EventTopic.AGENTS),
        'update_agent_status': ('agent.status_changed', EventTopic.AGENTS),
        'delete_agent': ('agent.deleted', EventTopic.AGENTS),
        
        # Note operations (from notes manager)
        'write_note': ('note.created', EventTopic.NOTES),
        'create_note': ('note.created', EventTopic.NOTES),
        'update_note': ('note.updated', EventTopic.NOTES),
        'delete_note': ('note.deleted', EventTopic.NOTES),
        'tag_note': ('note.tagged', EventTopic.NOTES),
        
        # Project operations
        'register_project': ('project.registered', EventTopic.SYSTEM),
        'add_project_link': ('project.linked', EventTopic.SYSTEM),
        'remove_project_link': ('project.unlinked', EventTopic.SYSTEM),
        
        # DM permission operations
        'set_dm_permission': ('dm.permission_set', EventTopic.SYSTEM),
        'update_dm_policy': ('dm.policy_updated', EventTopic.SYSTEM),
        'remove_dm_permission': ('dm.permission_removed', EventTopic.SYSTEM),
        
        # Session operations
        'register_session': ('session.created', EventTopic.SYSTEM),
        'update_session': ('session.updated', EventTopic.SYSTEM),
        
        # Tool call tracking
        'record_tool_call': ('tool.called', EventTopic.SYSTEM),
        
        # Generic patterns (checked if no exact match)
        'create_': ('entity.created', EventTopic.SYSTEM),
        'update_': ('entity.updated', EventTopic.SYSTEM),
        'delete_': ('entity.deleted', EventTopic.SYSTEM),
        'archive_': ('entity.archived', EventTopic.SYSTEM),
        'register_': ('entity.registered', EventTopic.SYSTEM),
        'add_': ('entity.added', EventTopic.SYSTEM),
        'remove_': ('entity.removed', EventTopic.SYSTEM),
    }
    
    def __init__(self, target: Any, event_stream: Any, context: Optional[Dict] = None):
        """
        Initialize the event proxy.
        
        Args:
            target: The object to wrap
            event_stream: SimpleEventStream instance for emitting events
            context: Optional context to include with all events
        """
        self._target = target
        self._events = event_stream
        self._context = context or {}
        self._logger = get_logger('AutoEventProxy', component='streaming')
        
    def __getattr__(self, name: str) -> Any:
        """
        Intercept attribute access and wrap methods with event emission.
        
        Args:
            name: Attribute name
            
        Returns:
            Wrapped method or original attribute
        """
        attr = getattr(self._target, name)
        
        # Only wrap async methods
        if asyncio.iscoroutinefunction(attr):
            # Check for exact match first
            if name in self.EVENT_RULES:
                event_type, topic = self.EVENT_RULES[name]
                return self._wrap_with_event(attr, name, event_type, topic)
            
            # Check for prefix patterns
            for prefix, (event_type, topic) in self.EVENT_RULES.items():
                if prefix.endswith('_') and name.startswith(prefix):
                    # Use more specific event type based on method name
                    specific_event = event_type.replace('entity', name.split('_')[0])
                    return self._wrap_with_event(attr, name, specific_event, topic)
                    
        return attr
    
    def _wrap_with_event(self, method: Any, method_name: str, 
                         event_type: str, topic: EventTopic) -> Any:
        """
        Wrap a method to emit events after successful execution.
        
        Args:
            method: The method to wrap
            method_name: Name of the method
            event_type: Type of event to emit
            topic: Event topic
            
        Returns:
            Wrapped method
        """
        @wraps(method)
        async def wrapper(*args, **kwargs):
            # Call original method
            result = await method(*args, **kwargs)
            
            # Emit event on success
            try:
                # Build payload from result and kwargs
                payload = self._build_payload(method_name, result, kwargs)
                
                # Add context
                metadata = {**self._context}
                
                # Extract common metadata from kwargs
                if 'agent_name' in kwargs:
                    metadata['agent_name'] = kwargs['agent_name']
                if 'agent_project_id' in kwargs:
                    metadata['agent_project_id'] = kwargs['agent_project_id']
                if 'channel_id' in kwargs:
                    metadata['channel_id'] = kwargs['channel_id']
                if 'project_id' in kwargs:
                    metadata['project_id'] = kwargs['project_id']
                    
                # Emit the event
                await self._events.emit(
                    topic=topic,
                    event_type=event_type,
                    payload=payload,
                    **metadata
                )
                
                self._logger.debug(f"Emitted {event_type} for {method_name}")
                
            except Exception as e:
                # Don't fail the operation if event emission fails
                self._logger.error(f"Failed to emit event for {method_name}: {e}")
                
            return result
            
        return wrapper
    
    def _build_payload(self, method_name: str, result: Any, 
                       kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build event payload from method result and arguments.
        
        Args:
            method_name: Name of the method
            result: Method return value
            kwargs: Method keyword arguments
            
        Returns:
            Event payload dictionary
        """
        payload = {}
        
        # Add result based on method pattern
        if method_name.startswith('send_message'):
            payload['message_id'] = result
        elif method_name.startswith('create_'):
            payload['created_id'] = result
        elif method_name.startswith('delete_'):
            payload['deleted'] = result
        elif result is not None:
            payload['result'] = result
            
        # Add relevant kwargs to payload
        # Filter out sensitive or large data
        skip_keys = {'password', 'secret', 'token', 'key', 'content'}
        for key, value in kwargs.items():
            if key not in skip_keys and not key.startswith('_'):
                # Limit size of included values
                if isinstance(value, str) and len(value) > 1000:
                    payload[key] = value[:1000] + '...'
                elif isinstance(value, (str, int, float, bool, type(None))):
                    payload[key] = value
                elif isinstance(value, (list, tuple)) and len(value) <= 10:
                    payload[key] = value
                elif isinstance(value, dict) and len(value) <= 20:
                    payload[key] = value
                    
        # Include content for messages (but limited)
        if 'content' in kwargs and method_name.startswith('send_message'):
            content = kwargs['content']
            payload['content'] = content[:500] if len(content) > 500 else content
            payload['content_length'] = len(content)
            
        return payload
    
    def __repr__(self) -> str:
        """String representation"""
        return f"AutoEventProxy({self._target})"
    
    # Pass through special methods to the target
    def __aenter__(self):
        """Support async context manager if target supports it"""
        return self._target.__aenter__()
    
    def __aexit__(self, *args):
        """Support async context manager if target supports it"""
        return self._target.__aexit__(*args)


def with_events(event_stream: Any, context: Optional[Dict] = None):
    """
    Decorator to wrap a class instance with automatic event emission.
    
    Usage:
        event_stream = SimpleEventStream()
        
        @with_events(event_stream)
        db = MessageStore(...)
        
    Args:
        event_stream: SimpleEventStream instance
        context: Optional context for all events
        
    Returns:
        Wrapped instance
    """
    def wrapper(instance: Any) -> AutoEventProxy:
        return AutoEventProxy(instance, event_stream, context)
    return wrapper