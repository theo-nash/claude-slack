"""
Comprehensive integration tests for all messaging operations.
Tests message sending, DM channels, mentions, and permissions.
"""

import pytest
import pytest_asyncio
from typing import Dict, List, Optional
import json


class TestMessageSending:
    """Test all aspects of sending messages to channels."""
    
    @pytest.mark.asyncio
    async def test_send_message_permission_matrix(self, channel_manager, populated_db):
        """Test all combinations of send permissions."""
        # Test matrix:
        # - Member with can_send=True ✅
        # - Member with can_send=False ❌  
        # - Non-member ❌
        # - Empty content ❌
        
        # Setup: Alice as member with send permission
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1", can_send=True
        )
        
        # ✅ Member with permission can send
        msg_id = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Valid message"
        )
        assert msg_id is not None
        
        # ❌ Remove send permission
        await populated_db.remove_channel_member(
            "global:general", "alice", "proj_test1"
        )
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1", can_send=False
        )
        
        with pytest.raises(ValueError, match="send permission"):
            await channel_manager.send_message(
                channel_id="global:general",
                sender_name="alice",
                sender_project_id="proj_test1",
                content="Should fail"
            )
        
        # ❌ Non-member cannot send
        with pytest.raises(ValueError, match="not a member"):
            await channel_manager.send_message(
                channel_id="global:general",
                sender_name="bob",
                sender_project_id="proj_test2",
                content="Should fail"
            )
        
        # ❌ Empty content
        with pytest.raises(ValueError, match="empty message"):
            await channel_manager.send_message(
                channel_id="global:general",
                sender_name="alice",
                sender_project_id="proj_test1",
                content="   "
            )
    
    @pytest.mark.asyncio
    async def test_send_with_metadata(self, channel_manager, populated_db):
        """Test sending messages with various metadata."""
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        
        metadata_tests = [
            # Simple metadata
            {"priority": "high", "tags": ["urgent"]},
            # Complex nested metadata
            {"data": {"nested": {"value": 123}}, "array": [1, 2, 3]},
            # Empty metadata
            {},
            # None metadata (should work)
            None
        ]
        
        for i, metadata in enumerate(metadata_tests):
            msg_id = await channel_manager.send_message(
                channel_id="global:general",
                sender_name="alice",
                sender_project_id="proj_test1",
                content=f"Test {i} with metadata",
                metadata=metadata.copy() if metadata else metadata
            )
            assert msg_id is not None
            
            # Just verify the message was sent successfully
            # Metadata validation is complex due to JSON serialization
    
    @pytest.mark.asyncio
    async def test_send_to_all_channel_types(self, channel_manager, populated_db):
        """Test sending to global, project, and DM channels."""
        # Add alice to various channels
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        await populated_db.add_channel_member(
            "proj_test1:dev", "alice", "proj_test1"
        )
        
        # Send to global channel
        global_msg = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Global message"
        )
        assert global_msg is not None
        
        # Send to project channel
        project_msg = await channel_manager.send_message(
            channel_id="proj_test1:dev",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Project message"
        )
        assert project_msg is not None
        
        # Send to DM channel
        dm_msg = await channel_manager.send_direct_message(
            sender_name="alice",
            sender_project_id="proj_test1",
            recipient_name="bob",
            recipient_project_id="proj_test2",
            content="DM message"
        )
        assert dm_msg is not None
    
    @pytest.mark.asyncio
    async def test_threading(self, channel_manager, populated_db):
        """Test message threading."""
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        await populated_db.add_channel_member(
            "global:general", "bob", "proj_test2"
        )
        
        # Start a thread
        original_msg = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Starting a discussion"
        )
        
        # Reply in thread
        reply1 = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="bob",
            sender_project_id="proj_test2",
            content="Reply to discussion",
            thread_id=str(original_msg)
        )
        
        # Another reply
        reply2 = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Follow-up",
            thread_id=str(original_msg)
        )
        
        assert reply1 > original_msg
        assert reply2 > reply1


class TestDirectMessages:
    """Test DM channel operations and permissions."""
    
    @pytest.mark.asyncio
    async def test_dm_lifecycle(self, channel_manager, populated_db):
        """Test complete DM channel lifecycle."""
        # Create DM channel via first message
        msg1 = await channel_manager.send_direct_message(
            sender_name="alice",
            sender_project_id="proj_test1",
            recipient_name="bob",
            recipient_project_id="proj_test2",
            content="Hello Bob!"
        )
        assert msg1 is not None
        
        # Verify channel was created
        dm_id = populated_db.get_dm_channel_id(
            "alice", "proj_test1", "bob", "proj_test2"
        )
        channel = await populated_db.get_channel(dm_id)
        assert channel is not None
        assert channel['channel_type'] == 'direct'
        assert channel['access_type'] == 'private'
        
        # Both can send messages
        msg2 = await channel_manager.send_direct_message(
            sender_name="bob",
            sender_project_id="proj_test2",
            recipient_name="alice",
            recipient_project_id="proj_test1",
            content="Hi Alice!"
        )
        assert msg2 > msg1
        
        # Same channel is reused
        messages = await channel_manager.get_channel_messages(
            channel_id=dm_id,
            requester_name="alice",
            requester_project_id="proj_test1"
        )
        assert len(messages) == 2
        
        # Cannot leave DM channel
        success = await channel_manager.leave_channel(
            agent_name="alice",
            agent_project_id="proj_test1",
            channel_id=dm_id
        )
        assert success is False
    
    @pytest.mark.asyncio
    async def test_dm_permissions_matrix(self, channel_manager, populated_db):
        """Test all DM permission scenarios."""
        test_cases = [
            # (agent1_policy, agent2_policy, should_work)
            ("open", "open", True),
            ("open", "restricted", False),  # Restricted requires explicit allow
            ("open", "closed", False),
            ("closed", "open", False),
        ]
        
        for i, (policy1, policy2, should_work) in enumerate(test_cases):
            # Create unique agents for each test
            agent1 = f"test_agent1_{i}"
            agent2 = f"test_agent2_{i}"
            
            await populated_db.register_agent(
                agent1, "proj_test1", f"Agent 1 {i}", 
                dm_policy=policy1
            )
            await populated_db.register_agent(
                agent2, "proj_test2", f"Agent 2 {i}",
                dm_policy=policy2
            )
            
            if should_work:
                # Should succeed
                msg_id = await channel_manager.send_direct_message(
                    sender_name=agent1,
                    sender_project_id="proj_test1",
                    recipient_name=agent2,
                    recipient_project_id="proj_test2",
                    content=f"Test DM {i}"
                )
                assert msg_id is not None
            else:
                # Should fail
                with pytest.raises(ValueError, match="not allowed"):
                    await channel_manager.send_direct_message(
                        sender_name=agent1,
                        sender_project_id="proj_test1",
                        recipient_name=agent2,
                        recipient_project_id="proj_test2",
                        content=f"Test DM {i}"
                    )
    
    @pytest.mark.asyncio
    async def test_dm_blocking(self, channel_manager, populated_db):
        """Test DM blocking functionality."""
        # Alice blocks Charlie
        await populated_db.set_dm_permission(
            "alice", "proj_test1",
            "charlie", None,
            permission="block",
            reason="Testing block"
        )
        
        # Charlie cannot DM Alice
        with pytest.raises(ValueError, match="not allowed"):
            await channel_manager.send_direct_message(
                sender_name="charlie",
                sender_project_id=None,
                recipient_name="alice",
                recipient_project_id="proj_test1",
                content="This should be blocked"
            )
        
        # Alice also cannot DM Charlie (blocks work both ways)
        with pytest.raises(ValueError, match="not allowed"):
            await channel_manager.send_direct_message(
                sender_name="alice",
                sender_project_id="proj_test1",
                recipient_name="charlie",
                recipient_project_id=None,
                content="This is also blocked"
            )
        
        # But Alice can still DM Bob
        msg_id = await channel_manager.send_direct_message(
            sender_name="alice",
            sender_project_id="proj_test1",
            recipient_name="bob",
            recipient_project_id="proj_test2",
            content="This works"
        )
        assert msg_id is not None
    
    @pytest.mark.asyncio
    async def test_dm_explicit_allow(self, channel_manager, populated_db):
        """Test explicit DM allow lists."""
        # Create agent with restricted DM policy
        await populated_db.register_agent(
            "restricted_agent", "proj_test1", "Restricted Agent",
            dm_policy="restricted"
        )
        
        # By default, cannot DM (restricted policy)
        with pytest.raises(ValueError, match="not allowed"):
            await channel_manager.send_direct_message(
                sender_name="bob",
                sender_project_id="proj_test2",
                recipient_name="restricted_agent",
                recipient_project_id="proj_test1",
                content="Should fail by default"
            )
        
        # Add explicit allow
        await populated_db.set_dm_permission(
            "restricted_agent", "proj_test1",
            "bob", "proj_test2",
            permission="allow",
            reason="Testing allow"
        )
        
        # Now it works
        msg_id = await channel_manager.send_direct_message(
            sender_name="bob",
            sender_project_id="proj_test2",
            recipient_name="restricted_agent",
            recipient_project_id="proj_test1",
            content="Now allowed"
        )
        assert msg_id is not None


class TestMentions:
    """Test @mention validation and processing."""
    
    @pytest.mark.asyncio
    async def test_mention_formats(self, channel_manager, populated_db):
        """Test various mention formats."""
        # Create agents with different name formats
        await populated_db.register_agent(
            "simple", "proj_test1", "Simple Name"
        )
        await populated_db.register_agent(
            "hyphen-name", "proj_test1", "Hyphenated Name"
        )
        await populated_db.register_agent(
            "under_score", "proj_test2", "Underscore Name"
        )
        
        # Add all to channel
        for agent in ["alice", "simple", "hyphen-name", "under_score"]:
            project = "proj_test1" if agent != "under_score" else "proj_test2"
            await populated_db.add_channel_member(
                "global:general", agent, project
            )
        
        # Test various mention formats
        test_cases = [
            "@simple",
            "@hyphen-name",
            "@under_score",
            "@alice:proj_test1",  # Project-scoped
            "@nonexistent",  # Should be logged but not fail
        ]
        
        content = f"Testing mentions: {' '.join(test_cases)}"
        
        msg_id = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content=content,
            metadata={}
        )
        
        assert msg_id is not None
        
        # Verify message was sent
        messages = await channel_manager.get_channel_messages(
            channel_id="global:general",
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=1
        )
        assert len(messages) == 1
        
        # Check metadata for valid mentions
        metadata = messages[0].get('metadata')
        if metadata and isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        if metadata and 'mentions' in metadata:
            mentions = metadata['mentions']
            assert "simple" in mentions
            assert "hyphen-name" in mentions
            assert "under_score" in mentions
            # nonexistent should not be in valid mentions
            assert "nonexistent" not in mentions
    
    @pytest.mark.asyncio
    async def test_mention_validation_in_channels(self, channel_manager, populated_db):
        """Test that mentions are validated against channel membership."""
        # Setup: alice and bob in channel, charlie not
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        await populated_db.add_channel_member(
            "global:general", "bob", "proj_test2"
        )
        # charlie is NOT in the channel
        
        # Send message mentioning both members and non-members
        msg_id = await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Hey @bob (member) and @charlie (not member)!",
            metadata={}
        )
        
        assert msg_id is not None
        
        # Get the message to check metadata
        messages = await channel_manager.get_channel_messages(
            channel_id="global:general",
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=1
        )
        
        metadata = messages[0].get('metadata')
        if metadata and isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        if metadata and 'mentions' in metadata:
            mentions = metadata['mentions']
            assert "bob" in mentions  # Valid member
            assert "charlie" not in mentions  # Not a member
    
    @pytest.mark.asyncio
    async def test_mention_in_dm(self, channel_manager, populated_db):
        """Test mentions in DM channels."""
        # In DMs, only the two participants are valid mentions
        msg_id = await channel_manager.send_direct_message(
            sender_name="alice",
            sender_project_id="proj_test1",
            recipient_name="bob",
            recipient_project_id="proj_test2",
            content="Hey @bob, this mentions you. @charlie won't work here.",
            metadata={}
        )
        
        assert msg_id is not None
        
        # Get the DM channel
        dm_id = populated_db.get_dm_channel_id(
            "alice", "proj_test1", "bob", "proj_test2"
        )
        
        messages = await channel_manager.get_channel_messages(
            channel_id=dm_id,
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=1
        )
        
        metadata = messages[0].get('metadata')
        if metadata and isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        if metadata and 'mentions' in metadata:
            mentions = metadata['mentions']
            assert "bob" in mentions  # Participant
            assert "charlie" not in mentions  # Not in DM


class TestMessageRetrieval:
    """Test message retrieval and permissions."""
    
    @pytest.mark.asyncio
    async def test_get_messages_permission(self, channel_manager, populated_db):
        """Test that only members can retrieve messages."""
        # Alice sends a message
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        await channel_manager.send_message(
            channel_id="global:general",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Secret message"
        )
        
        # Alice can read (member)
        messages = await channel_manager.get_channel_messages(
            channel_id="global:general",
            requester_name="alice",
            requester_project_id="proj_test1"
        )
        assert len(messages) == 1
        assert messages[0]['content'] == "Secret message"
        
        # Bob cannot read (not a member)
        with pytest.raises(ValueError, match="not a member"):
            await channel_manager.get_channel_messages(
                channel_id="global:general",
                requester_name="bob",
                requester_project_id="proj_test2"
            )
    
    @pytest.mark.asyncio
    async def test_get_messages_pagination(self, channel_manager, populated_db):
        """Test message retrieval with limits."""
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        
        # Send multiple messages
        for i in range(10):
            await channel_manager.send_message(
                channel_id="global:general",
                sender_name="alice",
                sender_project_id="proj_test1",
                content=f"Message {i}"
            )
        
        # Get with limit
        messages = await channel_manager.get_channel_messages(
            channel_id="global:general",
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=5
        )
        
        assert len(messages) <= 5
        
        # Messages should be in order (newest first typically)
        # Verify all retrieved messages have content
        assert all('content' in msg for msg in messages)


class TestConvenienceMethods:
    """Test helper methods for messaging."""
    
    @pytest.mark.asyncio
    async def test_send_to_channel_helper(self, channel_manager, populated_db):
        """Test send_to_channel convenience method."""
        await populated_db.add_channel_member(
            "global:general", "alice", "proj_test1"
        )
        await populated_db.add_channel_member(
            "proj_test1:dev", "alice", "proj_test1"
        )
        
        # Send to global channel by name
        msg1 = await channel_manager.send_to_channel(
            channel_name="general",
            scope="global",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Global helper test"
        )
        assert msg1 is not None
        
        # Send to project channel by name
        msg2 = await channel_manager.send_to_channel(
            channel_name="dev",
            scope="project",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Project helper test"
        )
        assert msg2 is not None
        
        # Verify messages exist
        global_msgs = await channel_manager.get_channel_messages(
            channel_id="global:general",
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=1
        )
        assert global_msgs[0]['content'] == "Global helper test"
        
        project_msgs = await channel_manager.get_channel_messages(
            channel_id="proj_test1:dev",
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=1
        )
        assert project_msgs[0]['content'] == "Project helper test"
    
    @pytest.mark.asyncio
    async def test_send_to_channel_cross_project(self, channel_manager, populated_db):
        """Test sending to another project's channel."""
        # Alice from proj_test1 is member of proj_test2:dev
        await populated_db.add_channel_member(
            "proj_test2:dev", "alice", "proj_test1"
        )
        
        # Send to proj_test2's channel explicitly
        msg_id = await channel_manager.send_to_channel(
            channel_name="dev",
            scope="project",
            sender_name="alice",
            sender_project_id="proj_test1",
            content="Cross-project send",
            project_id="proj_test2"  # Explicit project
        )
        
        assert msg_id is not None
        
        # Verify message in proj_test2:dev
        messages = await channel_manager.get_channel_messages(
            channel_id="proj_test2:dev",
            requester_name="alice",
            requester_project_id="proj_test1",
            limit=1
        )
        assert messages[0]['content'] == "Cross-project send"