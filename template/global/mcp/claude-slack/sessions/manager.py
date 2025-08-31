#!/usr/bin/env python3
"""
Session Manager for Claude-Slack

Manages Claude session contexts and project detection.
This is the foundation that provides context for all other operations.

Responsibilities:
- Track current session ID and associated project context
- Store and retrieve session data from database
- Provide context information (project_id, project_path, transcript_path)
- Handle session lifecycle and cleanup
- NO knowledge of channels, subscriptions, or messaging
"""

import os
import sys
import json
import time
import hashlib
from typing import Optional, Dict, Tuple, Any
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from log_manager import get_logger
except ImportError:
    # Fallback to standard logging if new logging system not available
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)


@dataclass
class SessionContext:
    """Data class representing a session's context"""
    session_id: str
    project_id: Optional[str]
    project_path: Optional[str]
    project_name: Optional[str]
    transcript_path: Optional[str]
    scope: str  # 'global' or 'project'
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ProjectContext:
    """Data class representing project information"""
    project_id: str
    project_path: str
    project_name: str
    scope: str = 'project'


class SessionManager:
    """
    Manages session contexts for Claude-Slack.
    
    This is the foundational manager that tracks session state and provides
    project context information to other components. It has no knowledge of
    channels, subscriptions, or messaging - it purely manages session context.
    """
    
    def __init__(self, api):
        """
        Initialize SessionManager.
        
        Args:
            api: ClaudeSlackAPI instance
        """
        
        self.api = api
        self.logger = get_logger('SessionManager', component='manager')
        
        # Simple in-memory cache for performance
        self._cache = {}
        self._cache_times = {}
        self._cache_ttl = 60  # 60 seconds
        
        # Track the most recently used session for fallback
        self._current_session_id = None
    
    def _cache_key(self, session_id: str) -> str:
        """Generate cache key for session"""
        return f"session:{session_id}"
    
    def _get_cached_context(self, session_id: str) -> Optional[SessionContext]:
        """Get cached session context if still valid"""
        cache_key = self._cache_key(session_id)
        if cache_key in self._cache:
            if time.time() - self._cache_times.get(cache_key, 0) < self._cache_ttl:
                self.logger.debug(f"Cache hit for session {session_id}")
                return self._cache[cache_key]
        return None
    
    def _cache_context(self, context: SessionContext):
        """Cache session context"""
        cache_key = self._cache_key(context.session_id)
        self._cache[cache_key] = context
        self._cache_times[cache_key] = time.time()
        self.logger.debug(f"Cached context for session {context.session_id}")
    
    def _invalidate_cache(self, session_id: str):
        """Invalidate cached session context"""
        cache_key = self._cache_key(session_id)
        if cache_key in self._cache:
            del self._cache[cache_key]
            del self._cache_times[cache_key]
            self.logger.debug(f"Invalidated cache for session {session_id}")
    
    @staticmethod
    def generate_project_id(project_path: str) -> str:
        """
        Generate consistent project ID from path.
        
        Args:
            project_path: Absolute path to project root
            
        Returns:
            32-character project ID
        """
        return hashlib.sha256(project_path.encode()).hexdigest()[:32]
    
    async def register_session(self, session_id: str, 
                              project_path: Optional[str] = None,
                              project_name: Optional[str] = None,
                              transcript_path: Optional[str] = None) -> bool:
        """
        Register a new session or update existing session.
        
        Args:
            session_id: Unique session identifier
            project_path: Path to project directory (None for global context)
            project_name: Human-readable project name
            transcript_path: Path to session transcript
            
        Returns:
            True if successful
        """        
        try:
            # Determine project context
            project_id = None
            scope = 'global'
            
            if project_path:
                scope = 'project'
                
                # Register the project first (or update last_active)
                project_id = await self.register_project(project_path, project_name)
            
            self.logger.info(f"Registering session {session_id} (scope: {scope})")
            
            # Use ClaudeSlackAPI to register session
            await self.api.register_session(
                session_id=session_id,
                project_id=project_id,
                project_path=project_path,
                project_name=project_name,
                transcript_path=transcript_path,
                scope=scope
            )
            
            # Update current session
            self._current_session_id = session_id
            
            # Invalidate cache for this session
            self._invalidate_cache(session_id)
            
            self.logger.info(f"Session {session_id} registered successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error registering session: {e}")
            return False
    
    async def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """
        Get context for a specific session.
        
        Args:
            session_id: Session ID to look up
            
        Returns:
            SessionContext object or None if not found
        """
        if not session_id:
            self.logger.debug("No session_id provided")
            return None
        
        # Check cache first
        cached = self._get_cached_context(session_id)
        if cached:
            return cached
        
        try:
            self.logger.debug(f"Looking up session {session_id} in database")
            
            # Use ClaudeSlackAPI to get session
            session_data = await self.api.get_session(session_id)
            
            if session_data:
                context = SessionContext(
                    session_id=session_id,
                    project_id=session_data['project_id'],
                    project_path=session_data['project_path'],
                    project_name=session_data['project_name'],
                    transcript_path=session_data['transcript_path'],
                    scope=session_data['scope'],
                    updated_at=datetime.fromisoformat(session_data['updated_at']) if session_data['updated_at'] else datetime.now(),
                    metadata=session_data['metadata']
                )
                
                # Update cache
                self._cache_context(context)
                
                # Update current session
                self._current_session_id = session_id
                
                self.logger.info(f"Found session context: scope={context.scope}, project={context.project_name}")
                return context
            else:
                self.logger.debug(f"No context found for session {session_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting session context: {e}")
            return None
    
    async def get_current_session_context(self) -> Optional[SessionContext]:
        """
        Get context for the current/most recent session.
        
        Returns:
            SessionContext object or None if no current session
        """
        if not self._current_session_id:
            # Try to find most recent session
            session_id = await self.get_most_recent_session_id()
            if session_id:
                self._current_session_id = session_id
        
        if self._current_session_id:
            return await self.get_session_context(self._current_session_id)
        
        return None
    
    async def get_most_recent_session_id(self) -> Optional[str]:
        """
        Get the most recently active session ID.
        
        Returns:
            Session ID or None if no recent sessions
        """        
        try:
            # Get active sessions from the last 5 minutes (0.083 hours)
            active_sessions = await self.api.get_active_sessions(hours=0.083)
            
            if active_sessions:
                session_id = active_sessions[0]['id']
                self.logger.debug(f"Found recent session: {session_id}")
                return session_id
                    
        except Exception as e:
            self.logger.error(f"Error getting recent session: {e}")
        
        return None
    
    async def get_project_context(self, project_id: str) -> Optional[ProjectContext]:
        """
        Get project information by ID.
        
        Args:
            project_id: Project ID to look up
            
        Returns:
            ProjectContext object or None if not found
        """        
        try:
            # Use ClaudeSlackAPI to get project
            project_data = await self.api.get_project(project_id)
            
            if project_data:
                return ProjectContext(
                    project_id=project_id,
                    project_path=project_data['path'],
                    project_name=project_data['name']
                )
                    
        except Exception as e:
            self.logger.error(f"Error getting project context: {e}")
        
        return None
    
    async def register_project(self, project_path: str, project_name: Optional[str] = None) -> str:
        """
        Register a project in the database.
        
        Args:
            project_path: Absolute path to project
            project_name: Human-readable project name
            
        Returns:
            Project ID
        """
        project_id = self.generate_project_id(project_path)
        
        if not project_name:
            project_name = os.path.basename(project_path)
                
        try:
            # Use ClaudeSlackAPI to register project
            await self.api.register_project(
                project_id=project_id,
                project_path=project_path,
                project_name=project_name
            )
            
            self.logger.info(f"Registered project: {project_name} ({project_id})")
                
        except Exception as e:
            self.logger.error(f"Error registering project: {e}")
        
        return project_id
    
    async def match_tool_call_session(self, tool_name: str, tool_inputs: Dict[str, Any]) -> Optional[str]:
        """
        Match a tool call to its session by looking up recent tool calls.
        
        This is used when we need to determine which session made a specific tool call.
        
        Args:
            tool_name: Name of the tool
            tool_inputs: Input parameters for the tool
            
        Returns:
            Session ID or None if no match found
        """
        
        try:
            # For matching, we need to iterate through recent sessions
            # and check their tool calls
            active_sessions = await self.api.get_active_sessions(hours=1)
            
            for session in active_sessions:
                session_id = session['id']
                recent_calls = await self.api.get_recent_tool_calls(
                    session_id=session_id,
                    minutes=10
                )
                
                for call in recent_calls:
                    if call['tool_name'] == tool_name:
                        # Check if inputs match
                        if call['tool_inputs'] == tool_inputs:
                            self.logger.debug(f"Matched tool call to session: {session_id}")
                            return session_id
                    
        except Exception as e:
            self.logger.error(f"Error matching tool call: {e}")
        
        return None
    
    async def record_tool_call(self, session_id: str, tool_name: str, tool_inputs: Dict[str, Any]) -> bool:
        """
        Record a tool call for session tracking.
        
        Args:
            session_id: Session making the tool call
            tool_name: Name of the tool
            tool_inputs: Input parameters for the tool
            
        Returns:
            True if recorded successfully (False if duplicate)
        """
        
        try:
            # Use ClaudeSlackAPI to record tool call with deduplication
            is_new = await self.api.record_tool_call(
                session_id=session_id,
                tool_name=tool_name,
                tool_inputs=tool_inputs,
                dedup_window_minutes=10
            )
            
            if is_new:
                self.logger.debug(f"Recorded tool call: {tool_name} for session {session_id}")
            else:
                self.logger.debug(f"Duplicate tool call skipped: {tool_name} for session {session_id}")
            
            return is_new
                
        except Exception as e:
            self.logger.error(f"Error recording tool call: {e}")
            return False
    
    async def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up old sessions from the database.
        
        Args:
            max_age_hours: Maximum age of sessions to keep
            
        Returns:
            Number of sessions cleaned up
        """
        
        try:
            # Use ClaudeSlackAPI to cleanup old sessions
            count = await self.api.cleanup_old_sessions(hours=max_age_hours)
            
            # Also cleanup old tool calls
            await self.api.cleanup_old_tool_calls(minutes=10)
            
            if count > 0:
                self.logger.info(f"Cleaned up {count} old sessions")
            
            return count
                
        except Exception as e:
            self.logger.error(f"Error cleaning up sessions: {e}")
            return 0
    
    # Convenience methods for backwards compatibility
    async def get_current_context(self, tool_name: str = None, 
                                 tool_inputs: dict = None) -> Tuple[Optional[str], Optional[str], 
                                                                   Optional[str], Optional[str]]:
        """
        Get the current session's project context.
        
        This method maintains backwards compatibility with existing code.
        
        Args:
            tool_name: Name of the current tool being called
            tool_inputs: Input parameters for the tool
            
        Returns:
            Tuple of (project_id, project_path, project_name, transcript_path)
        """
        session_id = None
        
        # Try to match by tool call if provided
        if tool_name and tool_inputs:
            session_id = await self.match_tool_call_session(tool_name, tool_inputs)
        
        # Fall back to current session
        if not session_id:
            session_id = self._current_session_id
        
        # Fall back to most recent session
        if not session_id:
            session_id = await self.get_most_recent_session_id()
        
        if session_id:
            context = await self.get_session_context(session_id)
            if context:
                return (context.project_id, context.project_path, 
                       context.project_name, context.transcript_path)
        
        self.logger.debug("No context found, returning None values")
        return None, None, None, None