#!/usr/bin/env python3
"""
Tests for time filtering with Unix timestamps.
"""

import pytest
import pytest_asyncio
import time
import asyncio
from datetime import datetime, timedelta
import tempfile
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from aiosqlite import connect as aconnect
from api.db.sqlite_store import SQLiteStore
from api.db.qdrant_store import QdrantStore
from api.db.message_store import MessageStore
from api.utils.time_utils import now_timestamp, to_timestamp


@pytest_asyncio.fixture
async def sqlite_store():
    """Create a temporary SQLite store for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    store = SQLiteStore(db_path)
    await store.initialize()
    yield store
    await store.close()
    os.unlink(db_path)


@pytest_asyncio.fixture
async def qdrant_store():
    """Create a Qdrant store for testing."""
    # Use in-memory mode for testing
    store = QdrantStore(":memory:", collection_name="test_messages")
    await store.initialize()
    yield store


@pytest_asyncio.fixture
async def message_store(sqlite_store, qdrant_store):
    """Create a message store with both SQLite and Qdrant."""
    store = MessageStore(
        sqlite_store=sqlite_store,
        qdrant_store=qdrant_store
    )
    yield store


@pytest.mark.asyncio
async def test_sqlite_unix_timestamp_storage(sqlite_store):
    """Test that SQLite stores and retrieves Unix timestamps correctly."""
    # Insert a message with current timestamp
    current_time = now_timestamp()
    
    message_id = await sqlite_store.send_message(
        channel_id="test-channel",
        sender_id="test-agent",
        sender_project_id="default",
        content="Test message",
        metadata={"test": True}
    )
    
    # Retrieve the message
    messages = await sqlite_store.get_messages(channel_ids=["test-channel"], limit=1)
    assert len(messages) == 1
    
    msg = messages[0]
    assert isinstance(msg['timestamp'], (int, float))
    assert abs(msg['timestamp'] - current_time) < 2  # Within 2 seconds


@pytest.mark.asyncio
async def test_sqlite_time_filtering(sqlite_store):
    """Test time filtering with Unix timestamps in SQLite."""
    # Insert messages at different times
    base_time = now_timestamp()
    
    # Message 1: 10 seconds ago
    past_time = base_time - 10
    await sqlite_store.send_message(
        channel_id="test-channel",
        sender_id="test-agent",
        sender_project_id="default",
        content="Past message",
        timestamp=past_time,
        metadata={}
    )
    
    # Message 2: Current time
    await sqlite_store.send_message(
        channel_id="test-channel",
        sender_id="test-agent",
        sender_project_id="default",
        content="Current message",
        timestamp=base_time,
        metadata={}
    )
    
    # Message 3: 10 seconds in future (for testing)
    future_time = base_time + 10
    await sqlite_store.send_message(
        channel_id="test-channel",
        sender_id="test-agent",
        sender_project_id="default",
        content="Future message",
        timestamp=future_time,
        metadata={}
    )
    
    # Test 'since' filter - should get current and future messages
    messages = await sqlite_store.get_messages(
        channel_ids=["test-channel"],
        since=base_time - 5,  # 5 seconds ago
        limit=10
    )
    assert len(messages) == 2
    assert messages[0]['content'] == "Future message"  # Most recent first
    assert messages[1]['content'] == "Current message"
    
    # Test 'until' filter - should get past and current messages
    messages = await sqlite_store.get_messages(
        channel_ids=["test-channel"],
        until=base_time + 5,  # 5 seconds from now
        limit=10
    )
    assert len(messages) == 2
    assert messages[0]['content'] == "Current message"  # Most recent first
    assert messages[1]['content'] == "Past message"
    
    # Test both 'since' and 'until' - should get only current message
    messages = await sqlite_store.get_messages(
        channel_ids=["test-channel"],
        since=base_time - 5,
        until=base_time + 5,
        limit=10
    )
    assert len(messages) == 1
    assert messages[0]['content'] == "Current message"


@pytest.mark.asyncio
async def test_qdrant_unix_timestamp_storage(qdrant_store):
    """Test that Qdrant stores Unix timestamps correctly."""
    # Create test embedding
    test_embedding = [0.1] * 1536  # Typical embedding dimension
    
    # Index a message with Unix timestamp
    current_time = now_timestamp()
    
    await qdrant_store.index_message(
        message_id=1,
        channel_id="test-channel",
        sender_id="test-agent",
        sender_project_id="test-project",
        content="Test message",
        embedding=test_embedding,
        metadata={"test": True},
        timestamp=current_time
    )
    
    # Search for the message
    results = await qdrant_store.search(
        query_embedding=test_embedding,
        limit=10
    )
    
    assert len(results) > 0
    result = results[0]
    
    # Check that timestamp is stored as Unix timestamp
    assert 'timestamp' in result['payload']
    assert isinstance(result['payload']['timestamp'], (int, float))
    assert abs(result['payload']['timestamp'] - current_time) < 2


@pytest.mark.asyncio
async def test_qdrant_time_filtering(qdrant_store):
    """Test time filtering with Unix timestamps in Qdrant."""
    test_embedding = [0.1] * 1536
    base_time = now_timestamp()
    
    # Index messages at different times
    messages = [
        (1, "Past message", base_time - 10),
        (2, "Current message", base_time),
        (3, "Future message", base_time + 10)
    ]
    
    for msg_id, content, timestamp in messages:
        await qdrant_store.index_message(
            message_id=msg_id,
            channel_id="test-channel",
            sender_id="test-agent",
            sender_project_id="test-project",
            content=content,
            embedding=test_embedding,
            metadata={},
            timestamp=timestamp
        )
    
    # Test 'since' filter
    results = await qdrant_store.search(
        query_embedding=test_embedding,
        since=base_time - 5,  # 5 seconds ago
        limit=10
    )
    
    contents = [r['payload']['content'] for r in results]
    assert "Current message" in contents
    assert "Future message" in contents
    assert "Past message" not in contents
    
    # Test 'until' filter
    results = await qdrant_store.search(
        query_embedding=test_embedding,
        until=base_time + 5,  # 5 seconds from now
        limit=10
    )
    
    contents = [r['payload']['content'] for r in results]
    assert "Past message" in contents
    assert "Current message" in contents
    assert "Future message" not in contents
    
    # Test both 'since' and 'until'
    results = await qdrant_store.search(
        query_embedding=test_embedding,
        since=base_time - 5,
        until=base_time + 5,
        limit=10
    )
    
    contents = [r['payload']['content'] for r in results]
    assert len(contents) == 1
    assert "Current message" in contents


@pytest.mark.asyncio
async def test_message_store_semantic_search_time_filtering(message_store):
    """Test semantic search with time filtering in MessageStore."""
    # This would require a mock embedding function
    # For now, we'll just test that the method accepts the parameters
    
    base_time = now_timestamp()
    
    # Add a test message
    async with aconnect(message_store.sqlite_store.db_path) as conn:
        await conn.execute("""
            INSERT INTO messages (channel_id, sender_id, sender_project_id, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("test-channel", "test-agent", "default", "Test message for semantic search", base_time, "{}"))
        await conn.commit()
    
    # Mock embedding function
    async def mock_embed(text):
        return [0.1] * 1536
    
    # Perform semantic search with time filters
    # This will use the mocked embed function
    original_embed = message_store.embed_func
    message_store.embed_func = mock_embed
    
    try:
        results = await message_store.semantic_search(
            query="test",
            since=base_time - 5,
            until=base_time + 5,
            limit=10
        )
        # The search should complete without errors
        assert isinstance(results, list)
    finally:
        message_store.embed_func = original_embed


@pytest.mark.asyncio
async def test_time_utils_conversions():
    """Test time utility conversion functions."""
    # Test now_timestamp
    current = now_timestamp()
    assert isinstance(current, float)
    assert current > 0
    
    # Test to_timestamp with various inputs
    
    # Unix timestamp (float)
    ts = 1234567890.5
    assert to_timestamp(ts) == ts
    
    # Unix timestamp (int)
    ts = 1234567890
    assert to_timestamp(ts) == float(ts)
    
    # Datetime object
    dt = datetime.now()
    ts = to_timestamp(dt)
    assert isinstance(ts, float)
    assert abs(ts - time.time()) < 2
    
    # ISO string
    iso_str = "2024-01-01T12:00:00"
    ts = to_timestamp(iso_str)
    assert isinstance(ts, float)
    
    # ISO string with timezone
    iso_str = "2024-01-01T12:00:00Z"
    ts = to_timestamp(iso_str)
    assert isinstance(ts, float)
    
    # ISO string with offset
    iso_str = "2024-01-01T12:00:00+00:00"
    ts = to_timestamp(iso_str)
    assert isinstance(ts, float)
    
    # None should return None
    assert to_timestamp(None) is None


@pytest.mark.asyncio
async def test_backward_compatibility(sqlite_store):
    """Test that the system handles legacy ISO timestamps correctly."""
    # This test ensures we can still read old data with ISO timestamps
    
    # Directly insert a message with ISO timestamp (simulating legacy data)
    async with aconnect(sqlite_store.db_path) as conn:
        iso_timestamp = "2024-01-01T12:00:00"
        
        await conn.execute("""
            INSERT INTO messages (channel_id, sender_id, sender_project_id, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("test-channel", "test-agent", "default", "Legacy message", iso_timestamp, "{}"))
        
        await conn.commit()
    
    # The system should still be able to retrieve this message
    messages = await sqlite_store.get_messages(channel_ids=["test-channel"], limit=1)
    assert len(messages) == 1
    assert messages[0]['content'] == "Legacy message"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])