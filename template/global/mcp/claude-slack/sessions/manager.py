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
    from db.db_helpers import aconnect
except ImportError as e:
    print(f"Import error in SessionManager: {e}", file=sys.stderr)
    aconnect = None

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
    
    def __init__(self, db_path: str):
        """
        Initialize SessionManager.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
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
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        try:
            # Determine project context
            project_id = None
            scope = 'global'
            
            if project_path:
                project_id = self.generate_project_id(project_path)
                scope = 'project'
                if not project_name:
                    project_name = os.path.basename(project_path)
            
            self.logger.info(f"Registering session {session_id} (scope: {scope})")
            
            async with aconnect(self.db_path, writer=True) as conn:
                # Register or update session
                await conn.execute("""
                    INSERT OR REPLACE INTO sessions 
                    (id, project_id, project_path, project_name, transcript_path, scope, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (session_id, project_id, project_path, project_name, transcript_path, scope))
                
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
        
        if not aconnect:
            self.logger.error("Database connection not available")
            return None
        
        try:
            self.logger.debug(f"Looking up session {session_id} in database")
            
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT project_id, project_path, project_name, transcript_path, 
                           scope, updated_at, metadata
                    FROM sessions 
                    WHERE id = ?
                """, (session_id,))
                
                row = await cursor.fetchone()
                
                if row:
                    context = SessionContext(
                        session_id=session_id,
                        project_id=row[0],
                        project_path=row[1],
                        project_name=row[2],
                        transcript_path=row[3],
                        scope=row[4],
                        updated_at=datetime.fromisoformat(row[5]) if row[5] else datetime.now(),
                        metadata=json.loads(row[6]) if row[6] else None
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
        if not aconnect:
            self.logger.error("Database connection not available")
            return None
        
        try:
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT id 
                    FROM sessions 
                    WHERE updated_at > datetime('now', '-5 minutes')
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)
                
                row = await cursor.fetchone()
                if row:
                    self.logger.debug(f"Found recent session: {row[0]}")
                    return row[0]
                    
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
        if not aconnect:
            self.logger.error("Database connection not available")
            return None
        
        try:
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT path, name
                    FROM projects 
                    WHERE id = ?
                """, (project_id,))
                
                row = await cursor.fetchone()
                if row:
                    return ProjectContext(
                        project_id=project_id,
                        project_path=row[0],
                        project_name=row[1]
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
        
        if not aconnect:
            self.logger.error("Database connection not available")
            return project_id
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO projects (id, path, name, last_active)
                    VALUES (?, ?, ?, datetime('now'))
                """, (project_id, project_path, project_name))
                
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
        if not aconnect:
            self.logger.error("Database connection not available")
            return None
        
        try:
            # Create hash of tool inputs for matching
            import json
            inputs_json = json.dumps(tool_inputs, sort_keys=True)
            inputs_hash = hashlib.sha256(inputs_json.encode()).hexdigest()[:16]
            
            self.logger.debug(f"Looking for tool call: {tool_name} with hash {inputs_hash}")
            
            async with aconnect(self.db_path, writer=False) as conn:
                cursor = await conn.execute("""
                    SELECT session_id 
                    FROM tool_calls 
                    WHERE tool_name = ? AND tool_inputs_hash = ?
                    ORDER BY called_at DESC
                    LIMIT 1
                """, (tool_name, inputs_hash))
                
                row = await cursor.fetchone()
                if row:
                    session_id = row[0]
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
            True if recorded successfully
        """
        if not aconnect:
            self.logger.error("Database connection not available")
            return False
        
        try:
            import json
            inputs_json = json.dumps(tool_inputs, sort_keys=True)
            inputs_hash = hashlib.sha256(inputs_json.encode()).hexdigest()[:16]
            
            async with aconnect(self.db_path, writer=True) as conn:
                await conn.execute("""
                    INSERT INTO tool_calls 
                    (session_id, tool_name, tool_inputs_hash, tool_inputs, called_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (session_id, tool_name, inputs_hash, inputs_json))
                
                self.logger.debug(f"Recorded tool call: {tool_name} for session {session_id}")
                return True
                
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
        if not aconnect:
            self.logger.error("Database connection not available")
            return 0
        
        try:
            async with aconnect(self.db_path, writer=True) as conn:
                cursor = await conn.execute("""
                    DELETE FROM sessions 
                    WHERE updated_at < datetime('now', ? || ' hours')
                """, (-max_age_hours,))
                
                count = cursor.rowcount
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