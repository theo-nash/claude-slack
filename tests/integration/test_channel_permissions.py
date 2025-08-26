"""
Comprehensive tests for the v3 channel permissions model.
Tests the unified membership model, scope restrictions, and cross-project access.
"""

import pytest
from typing import Dict, List, Optional


class TestChannelPermissions:
    """Test suite for channel access and permissions."""
    
    # =========================================================================
    # Self-Join Tests (join_channel)
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_join_open_global_channel(self, channel_manager, populated_db):
        """Any agent can join an open global channel."""
        # Alice from proj_test1 joins global channel
        success = await channel_manager.join_channel(
            agent_name="alice",
            agent_project_id="proj_test1",
            channel_id="global:general"
        )
        assert success is True
        
        # Verify membership
        is_member = await populated_db.is_channel_member(
            "global:general", "alice", "proj_test1"
        )
        assert is_member is True
    
    @pytest.mark.asyncio
    async def test_join_open_same_project_channel(self, channel_manager, populated_db):
        """Agent can join open channel in same project."""
        # Add alice to her project first
        await populated_db.register_agent("alice2", "proj_test1", "Another agent")
        
        # Alice2 joins project channel
        success = await channel_manager.join_channel(
            agent_name="alice2",
            agent_project_id="proj_test1",
            channel_id="proj_test1:dev"
        )
        assert success is True
    
    @pytest.mark.asyncio
    async def test_cannot_join_different_project_channel(self, channel_manager, populated_db):
        """Agent cannot self-join channel from different unlinked project."""
        # Bob (proj_test2) tries to join proj_test1 channel
        success = await channel_manager.join_channel(
            agent_name="bob",
            agent_project_id="proj_test2",
            channel_id="proj_test1:dev"
        )
        assert success is False
    
    @pytest.mark.asyncio
    async def test_join_linked_project_channel(self, channel_manager, populated_db):
        """Agent can join open channel from linked project."""
        # Link the projects
        await populated_db.add_project_link("proj_test1", "proj_test2")
        
        # Now Bob can join proj_test1 channel
        success = await channel_manager.join_channel(
            agent_name="bob",
            agent_project_id="proj_test2",
            channel_id="proj_test1:dev"
        )
        assert success is True
    
    @pytest.mark.asyncio
    async def test_global_agent_join_project_channel(self, channel_manager, populated_db):
        """Global agent can join any project's open channel."""
        # Charlie (global) joins project channel
        success = await channel_manager.join_channel(
            agent_name="charlie",
            agent_project_id=None,
            channel_id="proj_test1:dev"
        )
        assert success is True
    
    @pytest.mark.asyncio
    async def test_cannot_join_members_channel(self, channel_manager, populated_db):
        """No agent can self-join a members-only channel."""
        # Alice tries to join members channel in her own project
        success = await channel_manager.join_channel(
            agent_name="alice",
            agent_project_id="proj_test1",
            channel_id="proj_test1:private"
        )
        assert success is False
    
    @pytest.mark.asyncio
    async def test_cannot_join_private_channel(self, channel_manager, populated_db):
        """No agent can join a private channel (DMs)."""
        # Create a DM channel
        dm_id = await channel_manager.create_dm_channel(
            "alice", "proj_test1", "bob", "proj_test2"
        )
        
        # Charlie tries to join the DM
        success = await channel_manager.join_channel(
            agent_name="charlie",
            agent_project_id=None,
            channel_id=dm_id
        )
        assert success is False
    
    # =========================================================================
    # Invitation Tests (invite_to_channel)
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_cannot_invite_to_open_channel(self, channel_manager, populated_db):
        """Cannot invite to open channels - they allow self-service joining."""
        # Alice joins first
        await channel_manager.join_channel(
            "alice", "proj_test1", "global:general"
        )
        
        # Alice tries to invite Bob to open channel (should fail)
        success = await channel_manager.invite_to_channel(
            channel_id="global:general",
            invitee_name="bob",
            invitee_project_id="proj_test2",
            inviter_name="alice",
            inviter_project_id="proj_test1"
        )
        assert success is False  # Can't invite to open channels
        
        # Bob should just join directly
        success = await channel_manager.join_channel(
            "bob", "proj_test2", "global:general"
        )
        assert success is True
    
    @pytest.mark.asyncio
    async def test_invite_cross_project_to_members_channel(self, channel_manager, populated_db):
        """Can invite agents from different projects to members-only channels."""
        # Create a members-only channel
        channel_id = await channel_manager.create_channel(
            name="team-private",
            scope="project",
            project_id="proj_test1",
            access_type="members",
            created_by="alice",
            created_by_project_id="proj_test1"
        )
        
        # Alice (creator) invites Bob from different project
        success = await channel_manager.invite_to_channel(
            channel_id=channel_id,
            invitee_name="bob",
            invitee_project_id="proj_test2",
            inviter_name="alice",
            inviter_project_id="proj_test1"
        )
        assert success is True
        
        # Bob can now access the members channel despite being from proj_test2
        is_member = await populated_db.is_channel_member(
            channel_id, "bob", "proj_test2"
        )
        assert is_member is True
    
    @pytest.mark.asyncio
    async def test_cannot_invite_to_private_channel(self, channel_manager, populated_db):
        """Cannot invite to private channels (DMs)."""
        # Create DM between Alice and Charlie
        dm_id = await channel_manager.create_dm_channel(
            "alice", "proj_test1", "charlie", None
        )
        
        # Alice tries to invite Bob to the DM
        success = await channel_manager.invite_to_channel(
            channel_id=dm_id,
            invitee_name="bob",
            invitee_project_id="proj_test2",
            inviter_name="alice",
            inviter_project_id="proj_test1"
        )
        assert success is False
    
    @pytest.mark.asyncio
    async def test_invite_to_members_channel(self, channel_manager, populated_db):
        """Members with invite permission can invite to members-only channels."""
        # Create a members channel with Alice as owner
        channel_id = await channel_manager.create_channel(
            name="team-only",
            scope="global",
            access_type="members",
            created_by="alice",
            created_by_project_id="proj_test1"
        )
        
        # Alice (creator with can_invite) invites Bob
        success = await channel_manager.invite_to_channel(
            channel_id=channel_id,
            invitee_name="bob",
            invitee_project_id="proj_test2",
            inviter_name="alice",
            inviter_project_id="proj_test1"
        )
        assert success is True
        
        # Bob is now a member
        is_member = await populated_db.is_channel_member(
            channel_id, "bob", "proj_test2"
        )
        assert is_member is True
    
    @pytest.mark.asyncio
    async def test_non_member_cannot_invite(self, channel_manager, populated_db):
        """Non-members cannot invite others to members-only channels."""
        # Use the existing members channel from populated_db
        # Bob (not a member of proj_test1:private) tries to invite Charlie
        success = await channel_manager.invite_to_channel(
            channel_id="proj_test1:private",
            invitee_name="charlie",
            invitee_project_id=None,
            inviter_name="bob",
            inviter_project_id="proj_test2"
        )
        assert success is False
    
    # =========================================================================
    # Channel Discovery Tests (list_available_channels)
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_list_available_global_channels(self, channel_manager, populated_db):
        """All agents can see global channels."""
        channels = await channel_manager.list_available_channels(
            agent_name="bob",
            agent_project_id="proj_test2",
            scope_filter="global"
        )
        
        channel_names = [c['name'] for c in channels]
        assert "general" in channel_names
        
        # Check joinability
        general = next(c for c in channels if c['name'] == 'general')
        assert general['can_join'] is True  # Open channel
        assert general['is_member'] is False  # Not yet joined
    
    @pytest.mark.asyncio
    async def test_list_available_project_channels(self, channel_manager, populated_db):
        """Agent sees channels from their project."""
        channels = await channel_manager.list_available_channels(
            agent_name="alice",
            agent_project_id="proj_test1",
            scope_filter="project"
        )
        
        channel_names = [c['name'] for c in channels]
        assert "dev" in channel_names  # Open channel
        assert "private" in channel_names  # Members channel (visible but not joinable)
        
        # Check joinability
        dev = next(c for c in channels if c['name'] == 'dev')
        assert dev['can_join'] is True
        
        private = next(c for c in channels if c['name'] == 'private')
        assert private['can_join'] is False  # Members-only
    
    @pytest.mark.asyncio
    async def test_list_available_linked_project_channels(self, channel_manager, populated_db):
        """Agent sees channels from linked projects."""
        # Link projects
        await populated_db.add_project_link("proj_test1", "proj_test2")
        
        # Bob can now see proj_test1 channels
        channels = await channel_manager.list_available_channels(
            agent_name="bob",
            agent_project_id="proj_test2",
            scope_filter="all"
        )
        
        # Should see proj_test1:dev
        proj1_channels = [c for c in channels if c.get('project_id') == 'proj_test1']
        assert len(proj1_channels) > 0
        
        dev = next((c for c in proj1_channels if c['name'] == 'dev'), None)
        assert dev is not None
        assert dev['can_join'] is True  # Can join open channel from linked project
    
    @pytest.mark.asyncio
    async def test_global_agent_sees_all_channels(self, channel_manager, populated_db):
        """Global agents can see all channels."""
        channels = await channel_manager.list_available_channels(
            agent_name="charlie",
            agent_project_id=None,
            scope_filter="all"
        )
        
        # Should see both global and project channels
        assert any(c['scope'] == 'global' for c in channels)
        assert any(c['scope'] == 'project' for c in channels)
        
        # Can join open channels from any project
        proj_channels = [c for c in channels if c['scope'] == 'project' and c['access_type'] == 'open']
        for channel in proj_channels:
            assert channel['can_join'] is True
    
    # =========================================================================
    # Leave Channel Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_leave_channel(self, channel_manager, populated_db):
        """Members can leave channels they joined."""
        # Alice joins and then leaves
        await channel_manager.join_channel("alice", "proj_test1", "global:general")
        
        success = await channel_manager.leave_channel(
            agent_name="alice",
            agent_project_id="proj_test1",
            channel_id="global:general"
        )
        assert success is True
        
        # No longer a member
        is_member = await populated_db.is_channel_member(
            "global:general", "alice", "proj_test1"
        )
        assert is_member is False
    
    @pytest.mark.asyncio
    async def test_cannot_leave_dm_channel(self, channel_manager, populated_db):
        """Cannot leave DM channels."""
        # Create DM
        dm_id = await channel_manager.create_dm_channel(
            "alice", "proj_test1", "bob", "proj_test2"
        )
        
        # Alice tries to leave
        success = await channel_manager.leave_channel(
            agent_name="alice",
            agent_project_id="proj_test1",
            channel_id=dm_id
        )
        assert success is False
    
    # =========================================================================
    # Default Channels Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_apply_default_channels(self, channel_manager, populated_db):
        """New agents auto-join default channels."""
        # Create a default channel
        await populated_db.create_channel(
            channel_id="global:welcome",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="welcome",
            is_default=True
        )
        
        # Register new agent
        await populated_db.register_agent("diana", None, "New agent")
        
        # Apply defaults
        count = await channel_manager.apply_default_channels(
            agent_name="diana",
            agent_project_id=None
        )
        assert count > 0
        
        # Diana is now in welcome channel
        is_member = await populated_db.is_channel_member(
            "global:welcome", "diana", None
        )
        assert is_member is True
    
    # =========================================================================
    # Message Permission Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_send_message_requires_membership(self, populated_db):
        """Only members can send messages to channels."""
        # Alice is not in global:general
        with pytest.raises(ValueError, match="does not have access"):
            await populated_db.send_message(
                channel_id="global:general",
                sender_id="alice",
                sender_project_id="proj_test1",
                content="Hello"
            )
        
        # Add Alice to channel
        await populated_db.add_channel_member(
            channel_id="global:general",
            agent_name="alice",
            agent_project_id="proj_test1"
        )
        
        # Now she can send
        message_id = await populated_db.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj_test1",
            content="Hello"
        )
        assert message_id > 0
    
    @pytest.mark.asyncio
    async def test_mention_validation(self, populated_db):
        """@mentions are validated against channel membership."""
        # Setup: Alice in channel, Bob not
        await populated_db.add_channel_member(
            channel_id="global:general",
            agent_name="alice",
            agent_project_id="proj_test1"
        )
        
        result = await populated_db.validate_mentions_batch(
            channel_id="global:general",
            mentions=[
                {"name": "alice", "project_id": "proj_test1"},  # Valid
                {"name": "bob", "project_id": "proj_test2"},    # Invalid (not member)
                {"name": "nobody", "project_id": None}          # Unknown
            ]
        )
        
        assert len(result['valid']) == 1
        assert result['valid'][0]['name'] == 'alice'
        
        assert len(result['invalid']) == 1
        assert result['invalid'][0]['name'] == 'bob'
        
        assert len(result['unknown']) == 1
        assert result['unknown'][0]['name'] == 'nobody'


class TestChannelCreation:
    """Test suite for channel creation scenarios."""
    
    @pytest.mark.asyncio
    async def test_create_global_channel(self, channel_manager, populated_db):
        """Create a global channel."""
        channel_id = await channel_manager.create_channel(
            name="test-global",
            scope="global",
            access_type="open",
            created_by="alice",
            created_by_project_id="proj_test1"
        )
        
        assert channel_id == "global:test-global"
        
        # Verify channel exists
        channel = await populated_db.get_channel(channel_id)
        assert channel is not None
        assert channel['scope'] == 'global'
        assert channel['access_type'] == 'open'
    
    @pytest.mark.asyncio
    async def test_create_project_channel(self, channel_manager, populated_db):
        """Create a project-scoped channel."""
        channel_id = await channel_manager.create_channel(
            name="test-project",
            scope="project",
            project_id="proj_test1",
            access_type="members",
            created_by="alice",
            created_by_project_id="proj_test1"
        )
        
        assert channel_id.startswith("proj_")
        assert "test-project" in channel_id
        
        # Creator should be added as member for members channels
        is_member = await populated_db.is_channel_member(
            channel_id, "alice", "proj_test1"
        )
        assert is_member is True
    
    @pytest.mark.asyncio
    async def test_create_dm_channel(self, channel_manager, populated_db):
        """Create a DM channel between two agents."""
        dm_id = await channel_manager.create_dm_channel(
            agent1_name="alice",
            agent1_project_id="proj_test1",
            agent2_name="bob",
            agent2_project_id="proj_test2"
        )
        
        assert dm_id.startswith("dm:")
        
        # Both agents should be members
        assert await populated_db.is_channel_member(dm_id, "alice", "proj_test1")
        assert await populated_db.is_channel_member(dm_id, "bob", "proj_test2")
        
        # Channel should be private
        channel = await populated_db.get_channel(dm_id)
        assert channel['access_type'] == 'private'
    
    @pytest.mark.asyncio
    async def test_dm_channel_consistent_id(self, channel_manager, populated_db):
        """DM channel ID is consistent regardless of agent order."""
        # Create DM with agents in one order
        dm_id1 = await channel_manager.create_dm_channel(
            "alice", "proj_test1", "bob", "proj_test2"
        )
        
        # Create with reversed order - should get same ID
        dm_id2 = await channel_manager.create_dm_channel(
            "bob", "proj_test2", "alice", "proj_test1"
        )
        
        assert dm_id1 == dm_id2