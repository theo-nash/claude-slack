#!/usr/bin/env python3
"""
Integration test for MongoDB-style filtering in SQLite and MessageStore.
Tests the full stack from MessageStore down to SQLite with MongoDB queries.
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.db.message_store import MessageStore
from api.db.sqlite_store import SQLiteStore


async def test_sqlite_advanced_search():
    """Test SQLiteStore's advanced search directly."""
    print("\n" + "="*60)
    print("Testing SQLiteStore Advanced Search")
    print("="*60)
    
    # Create test database
    db_path = "/tmp/test_mongo_filters.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    store = SQLiteStore(db_path)
    await store.initialize()
    
    # Create test project and agent
    await store.register_project("test-project", "Test Project", json.dumps({"description": "Test project"}))
    await store.register_agent("test-agent", "test-project", json.dumps({"type": "test"}))
    
    # Create test channel
    await store.create_channel(
        channel_id="test-channel",
        channel_type="channel",
        access_type="open",
        scope="project",
        name="Test Channel",
        project_id="test-project",
        description="Test channel",
        created_by="test-agent",
        created_by_project_id="test-project"
    )
    
    # Add agent to channel
    await store.add_channel_member("test-channel", "test-agent", "test-project")
    
    # Add test messages with various metadata
    messages = [
        {
            "content": "Alert: Database connection failed",
            "metadata": {
                "type": "alert",
                "priority": 8,
                "tags": ["database", "critical"],
                "confidence": 0.9
            }
        },
        {
            "content": "Warning: High memory usage",
            "metadata": {
                "type": "warning",
                "priority": 5,
                "tags": ["memory", "performance"],
                "confidence": 0.7
            }
        },
        {
            "content": "Info: System started successfully",
            "metadata": {
                "type": "info",
                "priority": 2,
                "tags": ["startup"],
                "confidence": 1.0
            }
        },
        {
            "content": "Error: Authentication failed",
            "metadata": {
                "type": "error",
                "priority": 7,
                "tags": ["auth", "security"],
                "confidence": 0.85,
                "user": {"tier": "premium", "id": 123}
            }
        },
        {
            "content": "Alert: Disk space low",
            "metadata": {
                "type": "alert",
                "priority": 6,
                "tags": ["disk", "storage"],
                "confidence": 0.8,
                "resolved": False
            }
        }
    ]
    
    # Insert messages
    print("\nInserting test messages...")
    for msg in messages:
        msg_id = await store.send_message(
            channel_id="test-channel",
            sender_id="test-agent",
            sender_project_id="test-project",
            content=msg["content"],
            metadata=msg["metadata"]
        )
        print(f"  Inserted message {msg_id}: {msg['content'][:40]}...")
    
    # Test 1: Simple equality filter
    print("\n--- Test 1: Simple Equality Filter ---")
    print("Query: {'type': 'alert'}")
    
    results = await store.search_messages_advanced(
        metadata_filters={"type": "alert"},
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        print(f"  - {r['content'][:50]}")
        print(f"    Metadata: {r.get('metadata', {})}")
    
    # Test 2: Comparison operators
    print("\n--- Test 2: Priority Range Filter ---")
    print("Query: {'priority': {'$gte': 6}}")
    
    results = await store.search_messages_advanced(
        metadata_filters={"priority": {"$gte": 6}},
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - Priority {metadata.get('priority')}: {r['content'][:50]}")
    
    # Test 3: Array contains
    print("\n--- Test 3: Tag Contains Filter ---")
    print("Query: {'tags': {'$contains': 'critical'}}")
    
    results = await store.search_messages_advanced(
        metadata_filters={"tags": {"$contains": "critical"}},
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - Tags {metadata.get('tags')}: {r['content'][:50]}")
    
    # Test 4: Complex logical query
    print("\n--- Test 4: Complex Logical Query ---")
    query = {
        "$and": [
            {"type": {"$in": ["alert", "error"]}},
            {"$or": [
                {"priority": {"$gte": 7}},
                {"tags": {"$contains": "critical"}}
            ]}
        ]
    }
    print(f"Query: {json.dumps(query, indent=2)}")
    
    results = await store.search_messages_advanced(
        metadata_filters=query,
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - Type={metadata.get('type')}, Priority={metadata.get('priority')}, Tags={metadata.get('tags')}")
        print(f"    {r['content'][:50]}")
    
    # Test 5: Nested field access
    print("\n--- Test 5: Nested Field Filter ---")
    print("Query: {'user.tier': 'premium'}")
    
    results = await store.search_messages_advanced(
        metadata_filters={"user.tier": "premium"},
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - User tier: {metadata.get('user', {}).get('tier')}")
        print(f"    {r['content'][:50]}")
    
    # Test 6: Confidence + metadata filter
    print("\n--- Test 6: Combined Confidence and Metadata Filter ---")
    print("Min confidence: 0.8, Query: {'type': {'$ne': 'info'}}")
    
    results = await store.search_messages_advanced(
        metadata_filters={"type": {"$ne": "info"}},
        min_confidence=0.8,
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - Confidence={metadata.get('confidence')}, Type={metadata.get('type')}")
        print(f"    {r['content'][:50]}")
    
    await store.close()
    print("\n✅ SQLiteStore advanced search tests complete!")


async def test_message_store_integration():
    """Test MessageStore integration with MongoDB-style filtering."""
    print("\n" + "="*60)
    print("Testing MessageStore Integration")
    print("="*60)
    
    # Create test database
    db_path = "/tmp/test_message_store_mongo.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Initialize MessageStore without Qdrant (SQLite only)
    store = MessageStore(db_path=db_path, qdrant_config=None)
    await store.initialize()
    
    # Create test project and agent
    await store.register_project("test-project", "Test Project", json.dumps({"description": "Test project"}))
    await store.register_agent("test-agent", "test-project", json.dumps({"type": "test"}))
    
    # Create test channel
    await store.create_channel(
        channel_id="test-channel",
        channel_type="channel",
        access_type="open",
        scope="project",
        name="Test Channel",
        project_id="test-project",
        description="Test channel",
        created_by="test-agent",
        created_by_project_id="test-project"
    )
    
    # Add agent to channel
    await store.add_channel_member("test-channel", "test-agent", "test-project")
    
    # Send test messages
    print("\nSending test messages through MessageStore...")
    
    messages = [
        ("High priority alert", {"type": "alert", "priority": 9, "tags": ["urgent"]}),
        ("Medium priority warning", {"type": "warning", "priority": 5, "tags": ["monitor"]}),
        ("Low priority info", {"type": "info", "priority": 1, "tags": ["status"]}),
        ("Critical error", {"type": "error", "priority": 8, "tags": ["urgent", "fix"]}),
    ]
    
    for content, metadata in messages:
        msg_id = await store.send_message(
            channel_id="test-channel",
            sender_id="test-agent",
            sender_project_id="test-project",
            content=content,
            metadata=metadata
        )
        print(f"  Sent message {msg_id}: {content}")
    
    # Test search_messages with MongoDB filters (no semantic query)
    print("\n--- Test: MessageStore.search_messages with MongoDB filters ---")
    query = {
        "$or": [
            {"priority": {"$gte": 8}},
            {"tags": {"$contains": "urgent"}}
        ]
    }
    print(f"Query: {json.dumps(query, indent=2)}")
    
    results = await store.search_messages(
        metadata_filters=query,
        limit=10
    )
    
    print(f"Found {len(results)} results:")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - Priority={metadata.get('priority')}, Tags={metadata.get('tags')}")
        print(f"    {r['content']}")
    
    # Test search_agent_messages with permissions
    print("\n--- Test: MessageStore.search_agent_messages with permissions ---")
    query = {"type": {"$in": ["alert", "error"]}}
    print(f"Query: {json.dumps(query, indent=2)}")
    
    results = await store.search_agent_messages(
        agent_name="test-agent",
        agent_project_id="test-project",
        metadata_filters=query,
        limit=10
    )
    
    print(f"Found {len(results)} results (with agent permissions):")
    for r in results:
        metadata = r.get('metadata', {})
        print(f"  - Type={metadata.get('type')}: {r['content']}")
    
    await store.close()
    print("\n✅ MessageStore integration tests complete!")


async def main():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("MongoDB-Style Filtering Integration Tests")
    print("="*60)
    
    try:
        # Test SQLiteStore directly
        await test_sqlite_advanced_search()
        
        # Test MessageStore integration
        await test_message_store_integration()
        
        print("\n" + "="*60)
        print("🎉 All integration tests passed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())