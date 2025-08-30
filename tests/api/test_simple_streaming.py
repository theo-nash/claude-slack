#!/usr/bin/env python3
"""
Test for the simple streaming event system with auto-event proxy.
Verifies that events are automatically emitted when API methods are called.
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.unified_api import ClaudeSlackAPI
from api.events import EventTopic


async def event_consumer(api, client_id, topics=None):
    """Consumer that subscribes to events"""
    print(f"\n[{client_id}] Starting consumer (topics: {topics or 'all'})...")
    
    events_received = []
    
    try:
        # Subscribe with SSE format
        event_count = 0
        async for sse_data in api.subscribe_sse(client_id, topics):
            # Parse SSE format
            lines = sse_data.strip().split('\n')
            
            for line in lines:
                if line.startswith('event:'):
                    event_type = line[6:].strip()
                elif line.startswith('data:'):
                    data = json.loads(line[5:].strip())
                    event_count += 1
                    events_received.append(data)
                    
                    print(f"\n[{client_id}] Event #{event_count}:")
                    print(f"  Type: {event_type}")
                    print(f"  Topic: {data.get('topic')}")
                    print(f"  Payload: {json.dumps(data.get('payload', {}), indent=2)}")
                    
                    # Stop after 5 events
                    if event_count >= 5:
                        print(f"\n[{client_id}] Received 5 events, stopping")
                        break
                elif line.startswith(':'):
                    # Heartbeat
                    continue
                    
            if event_count >= 5:
                break
                
    except asyncio.CancelledError:
        print(f"\n[{client_id}] Consumer cancelled")
    except Exception as e:
        print(f"\n[{client_id}] Error: {e}")
        
    return events_received


async def test_auto_events(api):
    """Test that events are automatically emitted"""
    print("\n=== Testing Auto Event Emission ===")
    
    # Start a consumer for message events
    consumer_task = asyncio.create_task(
        event_consumer(api, "test-consumer", [EventTopic.MESSAGES])
    )
    
    # Give consumer time to start
    await asyncio.sleep(0.5)
    
    # Create test data
    print("\n[Test] Creating test agent...")
    await api.register_agent(
        name="test-agent",
        project_id=None,
        description="Test agent for streaming"
    )
    
    print("\n[Test] Creating test channel...")
    channel_id = await api.create_channel(
        name="test-channel",
        description="Test channel",
        scope="global",
        created_by="test-agent"
    )
    
    print("\n[Test] Joining channel...")
    await api.join_channel(
        agent_name="test-agent",
        agent_project_id=None,
        channel_id=channel_id
    )
    
    # Send messages - these should auto-emit events!
    print("\n[Test] Sending messages (should auto-emit events)...")
    for i in range(3):
        msg_id = await api.send_message(
            channel_id=channel_id,
            sender_id="test-agent",
            content=f"Test message {i+1} - auto event test"
        )
        print(f"  Sent message ID: {msg_id}")
        await asyncio.sleep(0.1)
    
    # Wait for consumer to receive events
    await asyncio.sleep(1)
    
    # Cancel consumer
    consumer_task.cancel()
    events = await consumer_task
    
    print(f"\n[Test] Consumer received {len(events)} events")
    return events


async def test_multiple_topics(api):
    """Test subscribing to multiple topics"""
    print("\n=== Testing Multiple Topics ===")
    
    # Start consumers for different topics
    all_consumer = asyncio.create_task(
        event_consumer(api, "all-consumer", None)  # All topics
    )
    
    channel_consumer = asyncio.create_task(
        event_consumer(api, "channel-consumer", [EventTopic.CHANNELS])
    )
    
    # Give consumers time to start
    await asyncio.sleep(0.5)
    
    # Create events of different types
    print("\n[Test] Creating mixed events...")
    
    # Channel event
    channel_id = await api.create_channel(
        name="multi-test-channel",
        description="Multi-topic test",
        scope="global",
        created_by="test-agent"
    )
    
    # Member event
    await api.join_channel(
        agent_name="test-agent",
        agent_project_id=None,
        channel_id=channel_id
    )
    
    # Message event
    await api.send_message(
        channel_id=channel_id,
        sender_id="test-agent",
        content="Multi-topic test message"
    )
    
    # Wait and cancel
    await asyncio.sleep(2)
    all_consumer.cancel()
    channel_consumer.cancel()
    
    all_events = await all_consumer
    channel_events = await channel_consumer
    
    print(f"\n[Test] All-consumer got {len(all_events)} events")
    print(f"[Test] Channel-consumer got {len(channel_events)} events")


async def test_statistics(api):
    """Test event statistics"""
    print("\n=== Testing Statistics ===")
    
    stats = api.get_event_stats()
    print("\nEvent System Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


async def main():
    """Main test function"""
    print("=" * 60)
    print("Simple Streaming Event System Test")
    print("=" * 60)
    
    # Initialize API
    api = ClaudeSlackAPI(
        db_path="/tmp/test_simple_streaming.db",
        enable_semantic_search=False
    )
    
    print("\nInitializing API...")
    await api.initialize()
    
    try:
        # Test auto event emission
        events = await test_auto_events(api)
        
        # Verify events were emitted
        assert len(events) > 0, "No events received!"
        print("\n✅ Auto event emission working!")
        
        # Test multiple topics
        await test_multiple_topics(api)
        
        # Show statistics
        await test_statistics(api)
        
    finally:
        # Cleanup
        print("\n\nCleaning up...")
        await api.close()
    
    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())