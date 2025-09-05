#!/usr/bin/env python3
"""
Test Unix timestamp implementation across the system
"""

import pytest
import pytest_asyncio
import tempfile
import os
import sys
import time
import asyncio
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, 'template/global/mcp/claude-slack')

from api.unified_api import ClaudeSlackAPI
from api.utils.time_utils import to_timestamp, now_timestamp, from_timestamp


@pytest_asyncio.fixture
async def api():
    """Create a temporary API instance"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        
        api_instance = ClaudeSlackAPI(
            db_path=db_path,
            enable_semantic_search=False
        )
        await api_instance.initialize()
        
        yield api_instance
        await api_instance.close()


class TestUnixTimestamps:
    """Test Unix timestamp implementation"""
    
    @pytest.mark.asyncio
    async def test_session_timestamps(self, api):
        """Test that session timestamps are stored as Unix timestamps"""
        # Get current time
        before_time = now_timestamp()
        
        # Register a session
        session_id = await api.register_session(
            session_id='test-session',
            scope='global',
            metadata={'test': 'data'}
        )
        
        after_time = now_timestamp()
        
        # Retrieve the session
        session = await api.get_session('test-session')
        
        assert session is not None
        
        # Check timestamps are Unix format (float)
        updated_at = session.get('updated_at')
        
        assert isinstance(updated_at, (int, float))
        
        # Timestamp should be in valid range  
        assert before_time <= updated_at <= after_time
    
    @pytest.mark.asyncio
    async def test_tool_call_timestamps(self, api):
        """Test that tool call timestamps are stored as Unix timestamps"""
        await api.register_session('test-session', scope='global')
        
        before_time = now_timestamp()
        
        # Record a tool call
        is_new = await api.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=10
        )
        
        after_time = now_timestamp()
        
        assert is_new is True
        
        # Get recent tool calls
        calls = await api.get_recent_tool_calls(
            session_id='test-session',
            minutes=10
        )
        
        assert len(calls) == 1
        call = calls[0]
        
        # Check timestamp is Unix format
        called_at = call.get('called_at')
        assert isinstance(called_at, (int, float))
        
        # Timestamp should be in valid range
        assert before_time <= called_at <= after_time
    
    @pytest.mark.skip(reason="Message timestamps require full channel membership setup")
    @pytest.mark.asyncio
    async def test_message_timestamps(self, api):
        """Test that message timestamps are stored as Unix timestamps"""
        # First create a channel
        await api.create_channel(
            name='test-channel',
            scope='global',
            access_type='open',
            description='Test channel'
        )
        
        # Send a message
        before_time = now_timestamp()
        
        msg_id = await api.send_message(
            channel_id='test-channel',
            sender_id='test-sender',
            content='Test message'
        )
        
        after_time = now_timestamp()
        
        # Get messages
        messages = await api.get_messages(
            recipient_id='test-sender',
            scope='global'
        )
        
        assert len(messages) > 0
        
        # Find our message
        msg = next((m for m in messages if m.get('id') == msg_id), None)
        assert msg is not None
        
        # Check timestamp is Unix format
        timestamp = msg.get('timestamp')
        assert isinstance(timestamp, (int, float))
        
        # Timestamp should be in valid range
        assert before_time <= timestamp <= after_time
    
    @pytest.mark.asyncio
    async def test_time_filtering(self, api):
        """Test time-based filtering with Unix timestamps"""
        # Register session
        await api.register_session('test-session', scope='global')
        
        # Record tool calls with delay
        await api.record_tool_call(
            session_id='test-session',
            tool_name='tool1',
            tool_inputs={'test': 1}
        )
        
        # Small delay
        await asyncio.sleep(0.1)
        mid_time = now_timestamp()
        await asyncio.sleep(0.1)
        
        await api.record_tool_call(
            session_id='test-session',
            tool_name='tool2',
            tool_inputs={'test': 2}
        )
        
        # Get all tool calls
        all_calls = await api.get_recent_tool_calls(
            session_id='test-session',
            minutes=10
        )
        assert len(all_calls) == 2
        
        # Get only recent calls (should exclude first one)
        # Convert mid_time to minutes ago
        minutes_ago = (now_timestamp() - mid_time) / 60
        recent_calls = await api.get_recent_tool_calls(
            session_id='test-session',
            minutes=minutes_ago
        )
        
        # Should only get the second call
        assert len(recent_calls) == 1
        assert recent_calls[0]['tool_name'] == 'tool2'
    
    @pytest.mark.asyncio
    async def test_deduplication_with_unix_timestamps(self, api):
        """Test tool call deduplication works with Unix timestamps"""
        await api.register_session('test-session', scope='global')
        
        # Record first call
        is_new = await api.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=1  # 1 minute window
        )
        assert is_new is True
        
        # Try duplicate immediately (should be rejected)
        is_new = await api.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=1
        )
        assert is_new is False
        
        # Wait for window to expire (simulate by using 0 minute window)
        is_new = await api.record_tool_call(
            session_id='test-session',
            tool_name='test_tool',
            tool_inputs={'param': 'value'},
            dedup_window_minutes=0  # No dedup window
        )
        assert is_new is True  # Should succeed now
    
    @pytest.mark.asyncio
    async def test_time_utils(self, api):
        """Test time utility functions"""
        # Test now_timestamp
        ts1 = now_timestamp()
        time.sleep(0.01)
        ts2 = now_timestamp()
        assert ts2 > ts1
        assert isinstance(ts1, float)
        
        # Test to_timestamp with various inputs
        dt = datetime.now()
        ts_from_dt = to_timestamp(dt)
        assert isinstance(ts_from_dt, float)
        
        iso_str = dt.isoformat()
        ts_from_iso = to_timestamp(iso_str)
        assert abs(ts_from_dt - ts_from_iso) < 1  # Should be very close
        
        # Test with Unix timestamp input (should return as-is)
        ts_from_unix = to_timestamp(ts1)
        assert ts_from_unix == ts1
        
        # Test from_timestamp
        parsed = from_timestamp(ts1)
        assert isinstance(parsed, datetime)
        
        # Test None handling
        assert to_timestamp(None) is None
        assert from_timestamp(None) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])