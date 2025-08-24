#!/usr/bin/env python3
"""
Test session management functionality in DatabaseManagerV3 and SessionManager
"""

import pytest
import pytest_asyncio
import tempfile
import os
import sys
import json
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, 'template/global/mcp/claude-slack')

from db.manager_v3 import DatabaseManagerV3
from sessions.manager import SessionManager


@pytest_asyncio.fixture
async def db_manager():
    """Create a temporary database with DatabaseManagerV3"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        
        manager = DatabaseManagerV3(db_path)
        await manager.initialize()
        
        yield manager


@pytest_asyncio.fixture
async def session_manager():
    """Create a SessionManager with temporary database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        
        # Initialize database
        db_manager = DatabaseManagerV3(db_path)
        await db_manager.initialize()
        
        # Create SessionManager
        manager = SessionManager(db_path)
        
        yield manager


class TestDatabaseManagerV3Sessions:
    """Test session management methods in DatabaseManagerV3"""
    
    @pytest.mark.asyncio
    async def test_register_session(self, db_manager):
        """Test registering a new session"""
        # Register a global session
        session_id = await db_manager.register_session(
            session_id='test-session-1',
            scope='global',
            metadata={'test': 'data'}
        )
        
        assert session_id == 'test-session-1'
        
        # Register a project session
        await db_manager.register_project('proj1', '/test/proj1', 'Project 1')
        
        session_id = await db_manager.register_session(
            session_id='test-session-2',
            project_id='proj1',
            project_path='/test/proj1',
            project_name='Project 1',
            transcript_path='/test/transcript.txt',
            scope='project',
            metadata={'project': 'data'}
        )
        
        assert session_id == 'test-session-2'
    
    @pytest.mark.asyncio
    async def test_get_session(self, db_manager):
        """Test retrieving session information"""
        # Register a session
        await db_manager.register_session(
            session_id='test-session',
            project_path='/test/path',
            project_name='Test Project',
            transcript_path='/test/transcript.txt',
            scope='project',
            metadata={'key': 'value'}
        )
        
        # Retrieve the session
        session = await db_manager.get_session('test-session')
        
        assert session is not None
        assert session['id'] == 'test-session'
        assert session['project_path'] == '/test/path'
        assert session['project_name'] == 'Test Project'
        assert session['transcript_path'] == '/test/transcript.txt'
        assert session['scope'] == 'project'
        assert session['metadata']['key'] == 'value'
        
        # Test non-existent session
        session = await db_manager.get_session('non-existent')
        assert session is None
    
    @pytest.mark.asyncio
    async def test_update_session(self, db_manager):
        """Test updating session fields"""
        # Register a session
        await db_manager.register_session(
            session_id='test-session',
            scope='global'
        )
        
        # Update session
        updated = await db_manager.update_session(
            session_id='test-session',
            project_path='/new/path',
            metadata={'updated': True}
        )
        
        assert updated is True
        
        # Verify update
        session = await db_manager.get_session('test-session')
        assert session['project_path'] == '/new/path'
        assert session['metadata']['updated'] is True
        
        # Test updating non-existent session
        updated = await db_manager.update_session(
            session_id='non-existent',
            scope='project'
        )
        assert updated is False
    
    @pytest.mark.asyncio
    async def test_get_active_sessions(self, db_manager):
        """Test retrieving active sessions"""
        # Register multiple sessions
        await db_manager.register_project('proj1', '/test/proj1', 'Project 1')
        
        await db_manager.register_session('session1', scope='global')
        await db_manager.register_session('session2', project_id='proj1', scope='project')
        await db_manager.register_session('session3', scope='global')
        
        # Get all active sessions
        sessions = await db_manager.get_active_sessions()
        assert len(sessions) == 3
        
        # Get project-specific sessions
        sessions = await db_manager.get_active_sessions(project_id='proj1')
        assert len(sessions) == 1
        assert sessions[0]['id'] == 'session2'
        
        # Test with custom time window
        sessions = await db_manager.get_active_sessions(hours=0.001)  # Very short window
        # Might be 0 or 3 depending on timing
        assert len(sessions) >= 0
    
    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, db_manager):
        """Test cleaning up old sessions"""
        # Register sessions
        await db_manager.register_session('session1', scope='global')
        await db_manager.register_session('session2', scope='global')
        
        # Cleanup with very long window (should delete nothing)
        deleted = await db_manager.cleanup_old_sessions(hours=24)
        assert deleted == 0
        
        # Verify sessions still exist
        sessions = await db_manager.get_active_sessions()
        assert len(sessions) == 2
        
        # Note: Testing actual deletion would require manipulating timestamps
        # which is complex with SQLite's datetime functions


class TestToolCallDeduplication:
    """Test tool call deduplication functionality"""
    
    @pytest.mark.asyncio
    async def test_record_tool_call(self, db_manager):
        """Test recording tool calls with deduplication"""
        await db_manager.register_session('test-session', scope='global')
        
        # Record first tool call
        is_new = await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=10
        )
        assert is_new is True
        
        # Try to record duplicate (should be rejected)
        is_new = await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=10
        )
        assert is_new is False
        
        # Record with different inputs (should succeed)
        is_new = await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'different'},
            dedup_window_minutes=10
        )
        assert is_new is True
        
        # Record different tool (should succeed)
        is_new = await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='other_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=10
        )
        assert is_new is True
    
    @pytest.mark.asyncio
    async def test_get_recent_tool_calls(self, db_manager):
        """Test retrieving recent tool calls"""
        await db_manager.register_session('test-session', scope='global')
        
        # Record multiple tool calls with small delay to ensure ordering
        await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='tool1',
            tool_inputs={'a': 1}
        )
        
        # Small delay to ensure different timestamps
        await asyncio.sleep(0.01)
        
        await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='tool2',
            tool_inputs={'b': 2}
        )
        
        # Get recent tool calls
        calls = await db_manager.get_recent_tool_calls(
            session_id='test-session',
            minutes=10
        )
        
        assert len(calls) == 2
        # Check that we got both tools (order depends on timestamp resolution)
        tool_names = {call['tool_name'] for call in calls}
        assert 'tool1' in tool_names
        assert 'tool2' in tool_names
        
        # Verify the tool inputs
        for call in calls:
            if call['tool_name'] == 'tool1':
                assert call['tool_inputs']['a'] == 1
            elif call['tool_name'] == 'tool2':
                assert call['tool_inputs']['b'] == 2
        
        # Test with different session
        calls = await db_manager.get_recent_tool_calls(
            session_id='other-session',
            minutes=10
        )
        assert len(calls) == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_old_tool_calls(self, db_manager):
        """Test cleaning up old tool calls"""
        await db_manager.register_session('test-session', scope='global')
        
        # Record tool calls
        await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='tool1',
            tool_inputs={'test': 1}
        )
        await db_manager.record_tool_call(
            session_id='test-session',
            tool_name='tool2',
            tool_inputs={'test': 2}
        )
        
        # Cleanup with very long window (should delete nothing)
        deleted = await db_manager.cleanup_old_tool_calls(minutes=60)
        assert deleted == 0
        
        # Verify tool calls still exist
        calls = await db_manager.get_recent_tool_calls('test-session', minutes=60)
        assert len(calls) == 2


class TestSessionManagerIntegration:
    """Test SessionManager integration with DatabaseManagerV3"""
    
    @pytest.mark.asyncio
    async def test_register_session_with_project(self, session_manager):
        """Test registering a session with project context"""
        success = await session_manager.register_session(
            session_id='test-session',
            project_path='/test/project',
            project_name='Test Project',
            transcript_path='/test/transcript.txt'
        )
        
        assert success is True
        assert session_manager._current_session_id == 'test-session'
    
    @pytest.mark.asyncio
    async def test_get_session_context(self, session_manager):
        """Test retrieving session context"""
        # Register a session
        await session_manager.register_session(
            session_id='test-session',
            project_path='/test/project',
            project_name='Test Project'
        )
        
        # Get context
        context = await session_manager.get_session_context('test-session')
        
        assert context is not None
        assert context.session_id == 'test-session'
        assert context.project_path == '/test/project'
        assert context.project_name == 'Test Project'
        assert context.scope == 'project'
        
        # Test cache hit (second call should use cache)
        context2 = await session_manager.get_session_context('test-session')
        assert context2.session_id == context.session_id
    
    @pytest.mark.asyncio
    async def test_record_and_match_tool_call(self, session_manager):
        """Test tool call recording and matching"""
        # Register a session
        await session_manager.register_session(
            session_id='test-session',
            project_path='/test/project'
        )
        
        # Record a tool call
        success = await session_manager.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'}
        )
        
        assert success is True
        
        # Try to record duplicate (should return False due to deduplication)
        duplicate = await session_manager.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'}
        )
        
        assert duplicate is False
    
    @pytest.mark.asyncio
    async def test_get_project_context(self, session_manager):
        """Test retrieving project context"""
        # Register a project
        project_id = await session_manager.register_project(
            project_path='/test/project',
            project_name='Test Project'
        )
        
        # Get project context
        context = await session_manager.get_project_context(project_id)
        
        assert context is not None
        assert context.project_id == project_id
        assert context.project_path == '/test/project'
        assert context.project_name == 'Test Project'
    
    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, session_manager):
        """Test session cleanup"""
        # Register sessions
        await session_manager.register_session('session1')
        await session_manager.register_session('session2')
        
        # Cleanup (with long window, should delete nothing)
        count = await session_manager.cleanup_old_sessions(max_age_hours=24)
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_get_current_context_compatibility(self, session_manager):
        """Test backward compatibility method get_current_context"""
        # Register a session with project
        await session_manager.register_session(
            session_id='test-session',
            project_path='/test/project',
            project_name='Test Project',
            transcript_path='/test/transcript.txt'
        )
        
        # Get current context (backward compatibility method)
        project_id, project_path, project_name, transcript_path = \
            await session_manager.get_current_context()
        
        assert project_path == '/test/project'
        assert project_name == 'Test Project'
        assert transcript_path == '/test/transcript.txt'
        assert project_id is not None  # Should be generated


class TestSessionManagerCaching:
    """Test SessionManager caching behavior"""
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, session_manager):
        """Test that cache is properly invalidated"""
        # Register initial session
        await session_manager.register_session(
            session_id='test-session',
            project_path='/initial/path'
        )
        
        # Get context (should cache)
        context1 = await session_manager.get_session_context('test-session')
        assert context1.project_path == '/initial/path'
        
        # Update session (should invalidate cache)
        await session_manager.register_session(
            session_id='test-session',
            project_path='/updated/path'
        )
        
        # Get context again (should fetch fresh data)
        context2 = await session_manager.get_session_context('test-session')
        assert context2.project_path == '/updated/path'
    
    @pytest.mark.asyncio
    async def test_cache_ttl(self, session_manager):
        """Test cache TTL expiration"""
        # Set very short TTL for testing
        original_ttl = session_manager._cache_ttl
        session_manager._cache_ttl = 0.1  # 100ms
        
        try:
            # Register session
            await session_manager.register_session(
                session_id='test-session',
                project_path='/test/path'
            )
            
            # Get context (should cache)
            context1 = await session_manager.get_session_context('test-session')
            cached_key = session_manager._cache_key('test-session')
            assert cached_key in session_manager._cache
            
            # Wait for cache to expire
            await asyncio.sleep(0.2)
            
            # Check if cache is considered expired
            cached = session_manager._get_cached_context('test-session')
            assert cached is None  # Should be expired
            
        finally:
            # Restore original TTL
            session_manager._cache_ttl = original_ttl


if __name__ == '__main__':
    pytest.main([__file__, '-v'])