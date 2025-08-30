#!/usr/bin/env python3
"""
Test that the event proxy correctly intercepts magic method pass-throughs.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.unified_api import ClaudeSlackAPI


async def test_passthrough_events():
    """Test that pass-through methods also emit events"""
    
    # Initialize API
    api = ClaudeSlackAPI(
        db_path="/tmp/test_passthrough.db",
        enable_semantic_search=False
    )
    await api.initialize()
    
    # Collect events
    events = []
    
    async def collect_events():
        async for event in api.events.subscribe("collector", None, False):
            events.append(event)
            print(f"Event captured: {event.type} - {event.topic}")
            if len(events) >= 5:
                break
    
    # Start collector
    collector = asyncio.create_task(collect_events())
    await asyncio.sleep(0.1)
    
    # Setup: Create agent and channel first
    await api.register_agent(
        name="test-sender",
        project_id=None,
        description="Test sender"
    )
    
    channel_id = await api.create_channel(
        name="test-channel",
        description="Test",
        scope="global",
        created_by="test-sender"
    )
    
    await api.join_channel(
        agent_name="test-sender",
        agent_project_id=None,
        channel_id=channel_id
    )
    
    print("\n1. Testing direct API method (send_message):")
    msg_id = await api.send_message(
        channel_id=channel_id,
        sender_id="test-sender", 
        content="Direct API call"
    )
    print(f"   Result: {msg_id}")
    
    print("\n2. Testing pass-through via __getattr__ (register_agent):")
    # register_agent is NOT defined in API, so it uses __getattr__
    await api.register_agent(
        name="test-agent",
        project_id=None,
        description="Testing passthrough"
    )
    print("   Called successfully")
    
    print("\n3. Testing another pass-through (update_agent):")
    # This is also not in API, goes through __getattr__
    await api.update_agent(
        agent_name="test-agent",  # Correct parameter name
        agent_project_id=None,
        status="busy",
        description="Updated via passthrough"
    )
    print("   Called successfully")
    
    # No need to test channels manager, already proven
    
    # Wait for events
    await asyncio.sleep(0.5)
    collector.cancel()
    try:
        await collector
    except asyncio.CancelledError:
        pass
    
    print(f"\n=== Captured {len(events)} events ===")
    for i, event in enumerate(events, 1):
        print(f"{i}. {event.type} ({event.topic})")
    
    await api.close()
    
    # Verify we got events
    assert len(events) >= 3, f"Expected at least 3 events, got {len(events)}"
    
    # Check event types
    event_types = [e.type for e in events]
    assert "message.created" in event_types, "send_message didn't emit event"
    assert "agent.registered" in event_types, "register_agent didn't emit event"
    assert "agent.updated" in event_types, "update_agent didn't emit event (passthrough)"
    
    print("\n✅ Pass-through event emission working correctly!")


if __name__ == "__main__":
    asyncio.run(test_passthrough_events())