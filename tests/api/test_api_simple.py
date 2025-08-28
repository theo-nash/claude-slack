#!/usr/bin/env python3
"""
Simple test script to verify the API works without pytest.
This can be run directly to test basic functionality.
"""

import asyncio
import tempfile
from pathlib import Path
import sys
import os

# Add API to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.unified_api import ClaudeSlackAPI


async def test_api():
    """Test basic API functionality."""
    print("Testing Claude-Slack API...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        qdrant_path = Path(tmpdir) / "qdrant"
        
        # Initialize API
        print("1. Initializing API...")
        api = ClaudeSlackAPI(
            db_path=str(db_path),
            qdrant_path=str(qdrant_path),
            enable_semantic_search=True
        )
        await api.initialize()
        print("   ✓ API initialized")
        
        # Register project
        print("2. Registering project...")
        await api.db.register_project("proj1", "/path/to/proj1", "Test Project")
        projects = await api.db.list_projects()
        assert len(projects) == 1
        print(f"   ✓ Project registered: {projects[0]['name']}")
        
        # Register agents
        print("3. Registering agents...")
        await api.register_agent(
            name="alice",
            project_id="proj1",
            description="Frontend developer",
            dm_policy="open",
            discoverable="public"
        )
        
        await api.register_agent(
            name="bob",
            project_id="proj1",
            description="Backend developer",
            dm_policy="open",
            discoverable="public"
        )
        
        agents = await api.list_agents()
        assert len(agents) == 2
        print(f"   ✓ Registered {len(agents)} agents")
        
        # Create channel
        print("4. Creating channel...")
        channel_id = await api.create_channel(
            name="general",
            description="General discussion",
            scope="global",
            created_by="alice",
            created_by_project_id="proj1"
        )
        assert channel_id == "global:general"
        print(f"   ✓ Channel created: {channel_id}")
        
        # Join channel as alice
        print("5. Alice joins channel...")
        result = await api.join_channel(
            agent_name="alice",
            agent_project_id="proj1",
            channel_id="global:general"
        )
        assert result is True
        print(f"   ✓ Alice joined channel")
        
        # Send message
        print("6. Sending message...")
        message_id = await api.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Hello, this is a test message!",
            metadata={"test": True, "confidence": 0.9}
        )
        assert isinstance(message_id, int)
        print(f"   ✓ Message sent with ID: {message_id}")
        
        # Retrieve messages
        print("7. Retrieving messages...")
        messages = await api.get_messages(
            channel_ids=["global:general"],
            limit=10
        )
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello, this is a test message!"
        print(f"   ✓ Retrieved {len(messages)} message(s)")
        
        # Test semantic search (if Qdrant is available)
        print("8. Testing semantic search...")
        try:
            # Add more messages for search
            await api.send_message(
                channel_id="global:general",
                sender_id="bob",
                sender_project_id="proj1",
                content="Python async programming is powerful",
                metadata={"topic": "python"}
            )
            
            await api.send_message(
                channel_id="global:general",
                sender_id="alice",
                sender_project_id="proj1",
                content="Database optimization techniques",
                metadata={"topic": "database"}
            )
            
            # Search
            results = await api.search_messages(
                query="Python programming",
                limit=5
            )
            
            if results:
                print(f"   ✓ Semantic search returned {len(results)} results")
                for i, result in enumerate(results[:3]):
                    print(f"      {i+1}. {result['content'][:50]}... (score: {result.get('score', 'N/A')})")
            else:
                print("   ⚠ Semantic search returned no results (Qdrant may not be configured)")
        except Exception as e:
            print(f"   ⚠ Semantic search not available: {e}")
        
        # Test notes
        print("9. Testing notes...")
        note_id = await api.write_note(
            agent_name="alice",
            agent_project_id="proj1",
            content="Remember to test the API thoroughly",
            tags=["testing", "api"]
        )
        assert isinstance(note_id, int)
        print(f"   ✓ Note written with ID: {note_id}")
        
        notes = await api.get_recent_notes(
            agent_name="alice",
            agent_project_id="proj1",
            limit=5
        )
        assert len(notes) == 1
        print(f"   ✓ Retrieved {len(notes)} note(s)")
        
        # Test direct messages
        print("10. Testing direct messages...")
        dm_id = await api.send_direct_message(
            sender_name="alice",
            sender_project_id="proj1",
            recipient_name="bob",
            recipient_project_id="proj1",
            content="Hi Bob, this is a private message"
        )
        assert isinstance(dm_id, int)
        print(f"   ✓ Direct message sent with ID: {dm_id}")
        
        # Test permission-based retrieval
        print("11. Testing permission-based message retrieval...")
        
        # Create a private channel
        private_channel_id = await api.create_channel(
            name="private",
            description="Private channel",
            scope="project",
            project_id="proj1",
            access_type="members",
            created_by="alice",
            created_by_project_id="proj1"
        )
        
        # Add alice as member
        await api.db.add_channel_member(
            channel_id=private_channel_id,
            agent_name="alice",
            agent_project_id="proj1",
            can_send=True,
            can_invite=True
        )
        
        # Alice posts to private channel
        await api.send_message(
            channel_id=private_channel_id,
            sender_id="alice",
            sender_project_id="proj1",
            content="This is a private message only Alice can see"
        )
        
        # Alice should see the message
        alice_messages = await api.get_agent_messages(
            agent_name="alice",
            agent_project_id="proj1"
        )
        private_msgs = [m for m in alice_messages if m["channel_id"] == private_channel_id]
        assert len(private_msgs) == 1
        print("   ✓ Alice can see private channel messages")
        
        # Bob should NOT see the message
        bob_messages = await api.get_agent_messages(
            agent_name="bob",
            agent_project_id="proj1"
        )
        private_msgs = [m for m in bob_messages if m["channel_id"] == private_channel_id]
        assert len(private_msgs) == 0
        print("   ✓ Bob cannot see private channel messages (correct)")
        
        print("\n✅ All tests passed!")
        
        # Close connections
        await api.close()


if __name__ == "__main__":
    try:
        asyncio.run(test_api())
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)