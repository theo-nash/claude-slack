#!/usr/bin/env python3
"""
Comprehensive tests for DatabaseManager functionality.
Focuses on covering edge cases and less-tested methods.
"""

import pytest
import pytest_asyncio
import tempfile
import os
import sys
import json
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, 'template/global/mcp/claude-slack')

from db.manager import DatabaseManager


@pytest_asyncio.fixture
async def test_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        manager = DatabaseManager(db_path)  # Will auto-detect if HybridStore available
        await manager.initialize()
        yield manager
        await manager.close()


class TestDMPermissions:
    """Test direct message permission functionality."""
    
    @pytest.mark.asyncio
    async def test_dm_permission_stats(self, test_db):
        """Test get_dm_permission_stats method."""
        # Create agents
        await test_db.register_agent("agent1", None, "Agent 1")
        await test_db.register_agent("agent2", None, "Agent 2")
        await test_db.register_agent("agent3", None, "Agent 3")
        await test_db.register_agent("agent4", None, "Agent 4")
        
        # Set various permissions for agent1
        await test_db.set_dm_permission("agent1", None, "agent2", None, "allow")
        await test_db.set_dm_permission("agent1", None, "agent3", None, "block")
        await test_db.set_dm_permission("agent1", None, "agent4", None, "allow")
        
        # agent2 blocks agent1
        await test_db.set_dm_permission("agent2", None, "agent1", None, "block")
        
        # Get stats for agent1
        stats = await test_db.get_dm_permission_stats("agent1", None)
        
        assert stats['agents_blocked'] == 1  # agent1 blocked agent3
        assert stats['agents_allowed'] == 2  # agent1 allowed agent2 and agent4
        assert stats['blocked_by_others'] == 1  # agent2 blocked agent1
    
    @pytest.mark.asyncio
    async def test_remove_dm_permission(self, test_db):
        """Test removing DM permissions."""
        # Create agents
        await test_db.register_agent("remover", None, "Remover")
        await test_db.register_agent("target", None, "Target")
        
        # Set permission
        await test_db.set_dm_permission("remover", None, "target", None, "block")
        
        # Verify permission was set (they can't DM now)
        can_dm = await test_db.check_dm_permission("remover", None, "target", None)
        assert can_dm is False  # Returns False when blocked
        
        # Remove permission (doesn't return a value)
        await test_db.remove_dm_permission("remover", None, "target", None)
        
        # Verify it's gone (they can DM again)
        can_dm = await test_db.check_dm_permission("remover", None, "target", None)
        assert can_dm is True  # Returns True when no block exists
        
        # Try removing non-existent permission (should not raise error)
        await test_db.remove_dm_permission("remover", None, "target", None)


class TestConfigSync:
    """Test configuration synchronization tracking."""
    
    @pytest.mark.asyncio
    async def test_track_config_sync(self, test_db):
        """Test tracking configuration sync operations."""
        # Track first sync
        config_snapshot = json.dumps({"channels": ["general"], "agents": ["bot1"]})
        await test_db.track_config_sync(
            config_hash="hash123",
            config_snapshot=config_snapshot,
            scope="global",
            project_id=None,
            actions_taken="Created 5 channels",
            success=True,
            error_message=None
        )
        
        # Get last sync hash
        last_hash = await test_db.get_last_sync_hash()
        assert last_hash == "hash123"
        
        # Track another sync with errors (failed sync)
        await test_db.track_config_sync(
            config_hash="hash456",
            config_snapshot=json.dumps({"channels": ["general", "dev"]}),
            scope="global",
            project_id=None,
            actions_taken="Created 2 channels",
            success=False,
            error_message="Failed to create channel"
        )
        
        # Get updated hash (should still be hash123 since hash456 failed)
        last_hash = await test_db.get_last_sync_hash()
        assert last_hash == "hash123"  # Still the last successful sync
        
        # Track a successful sync (no delay needed with ISO timestamps)
        await test_db.track_config_sync(
            config_hash="hash789",
            config_snapshot=json.dumps({"channels": ["general", "dev", "random"]}),
            scope="global",
            project_id=None,
            actions_taken="Created 3 channels",
            success=True,
            error_message=None
        )
        
        # Now it should be updated
        last_hash = await test_db.get_last_sync_hash()
        assert last_hash == "hash789"
    
    @pytest.mark.asyncio
    async def test_get_last_sync_hash_empty(self, test_db):
        """Test getting last sync hash when no syncs exist."""
        last_hash = await test_db.get_last_sync_hash()
        assert last_hash is None


class TestMessageOperations:
    """Test message-related database operations."""
    
    @pytest.mark.asyncio
    async def test_search_messages(self, test_db):
        """Test message search functionality."""
        # Setup
        await test_db.register_agent("searcher", None, "Searcher")
        channel_id = await test_db.create_channel(
            channel_id="search-test",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="search-test",
            description="Search test channel"
        )
        await test_db.add_channel_member(channel_id, "searcher", None)
        
        # Send messages
        await test_db.send_message(channel_id, "searcher", None, "Hello world")
        await test_db.send_message(channel_id, "searcher", None, "Python is great")
        await test_db.send_message(channel_id, "searcher", None, "Testing search")
        
        # Test FTS search (force semantic_search=False)
        results = await test_db.search_messages(
            query="Python",
            agent_name="searcher",
            agent_project_id=None,
            semantic_search=False  # Force FTS
        )
        
        assert len(results) == 1
        assert "Python" in results[0]['content']
        
        # If semantic search available, test it too
        if test_db.has_semantic_search():
            semantic_results = await test_db.search_messages(
                query="Python programming",
                agent_name="searcher",
                agent_project_id=None,
                semantic_search=True
            )
            assert len(semantic_results) >= 1  # Should find Python-related messages
            assert any("Python" in r['content'] for r in semantic_results)
        
        # Search with no results (force FTS)
        results = await test_db.search_messages(
            query="JavaScript",
            agent_name="searcher", 
            agent_project_id=None,
            semantic_search=False
        )
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_get_message(self, test_db):
        """Test retrieving a specific message."""
        # Setup
        await test_db.register_agent("getter", None, "Getter")
        channel_id = await test_db.create_channel(
            channel_id="get-test",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="get-test",
            description="Get test channel"
        )
        await test_db.add_channel_member(channel_id, "getter", None)
        
        # Send a message
        msg_id = await test_db.send_message(
            channel_id, "getter", None,
            "Test message content",
            metadata={"key": "value"}
        )
        
        # Get the message
        message = await test_db.get_message(msg_id, "getter", None)
        
        assert message is not None
        assert message['id'] == msg_id
        assert message['content'] == "Test message content"
        # Metadata is stored as JSON string
        if message['metadata']:
            metadata = json.loads(message['metadata'])
            assert metadata['key'] == "value"
        
        # Try to get non-existent message
        message = await test_db.get_message(999999, "getter", None)
        assert message is None
        
        # Try to get message without permission
        await test_db.register_agent("other", None, "Other")
        message = await test_db.get_message(msg_id, "other", None)
        assert message is None
    
    @pytest.mark.asyncio
    async def test_update_message(self, test_db):
        """Test updating message content."""
        # Setup
        await test_db.register_agent("updater", None, "Updater")
        channel_id = await test_db.create_channel(
            channel_id="update-test",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="update-test",
            description="Update test channel"
        )
        await test_db.add_channel_member(channel_id, "updater", None)
        
        # Send a message
        msg_id = await test_db.send_message(
            channel_id, "updater", None,
            "Original content"
        )
        
        # Update the message (note: update_message takes content, agent_name, agent_project_id)
        updated = await test_db.update_message(
            msg_id,
            "Updated content",
            "updater",
            None
        )
        assert updated is True
        
        # Verify update
        message = await test_db.get_message(msg_id, "updater", None)
        assert message['content'] == "Updated content"
        assert message['edited_at'] is not None
        
        # Try to update non-existent message
        updated = await test_db.update_message(
            999999,
            "New content",
            "updater",
            None
        )
        assert updated is False
        
        # Try to update without permission
        await test_db.register_agent("other", None, "Other")
        updated = await test_db.update_message(
            msg_id,
            "Hacked content",
            "other",
            None
        )
        assert updated is False
    
    @pytest.mark.asyncio
    async def test_delete_message(self, test_db):
        """Test deleting messages."""
        # Setup
        await test_db.register_agent("deleter", None, "Deleter")
        channel_id = await test_db.create_channel(
            channel_id="delete-test",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="delete-test",
            description="Delete test channel"
        )
        await test_db.add_channel_member(channel_id, "deleter", None)
        
        # Send a message
        msg_id = await test_db.send_message(
            channel_id, "deleter", None,
            "To be deleted"
        )
        
        # Delete the message
        deleted = await test_db.delete_message(msg_id, "deleter", None)
        assert deleted is True
        
        # Verify soft deletion (message content replaced)
        message = await test_db.get_message(msg_id, "deleter", None)
        assert message is not None  # Soft delete keeps the message
        assert message['content'] == '[Message deleted]'
        assert message['is_edited'] == 1  # SQLite returns 1 for True
        
        # Check metadata includes deletion info
        if message['metadata']:
            metadata = json.loads(message['metadata'])
            assert metadata.get('deleted') == 1  # JSON stores as 1
            assert metadata.get('deleted_by') == 'deleter'
        
        # Try to delete again (should still work - idempotent)
        deleted = await test_db.delete_message(msg_id, "deleter", None)
        assert deleted is True  # Deletion is idempotent
        
        # Try to delete without permission
        msg_id2 = await test_db.send_message(
            channel_id, "deleter", None,
            "Another message"
        )
        await test_db.register_agent("other", None, "Other")
        deleted = await test_db.delete_message(msg_id2, "other", None)
        assert deleted is False


class TestChannelOperations:
    """Test channel-related operations."""
    
    @pytest.mark.asyncio
    async def test_get_default_channels(self, test_db):
        """Test retrieving default channels."""
        # Create channels with different default settings
        await test_db.create_channel(
            channel_id="default-global",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="default-global",
            description="Global default",
            is_default=True
        )
        await test_db.create_channel(
            channel_id="non-default",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="non-default",
            description="Not default",
            is_default=False
        )
        
        # Create project and project default channel
        await test_db.register_project("proj1", "/proj1", "Project 1")
        await test_db.create_channel(
            channel_id="default-project",
            channel_type="channel",
            access_type="open",
            scope="project",
            name="default-project",
            project_id="proj1",
            description="Project default",
            is_default=True
        )
        
        # Get global defaults
        defaults = await test_db.get_default_channels(scope="global")
        assert len(defaults) == 1
        assert defaults[0]['id'] == "default-global"
        
        # Get project defaults
        defaults = await test_db.get_default_channels(
            scope="project",
            project_id="proj1"
        )
        assert len(defaults) == 1
        assert defaults[0]['id'] == "default-project"
        
        # Get all defaults
        defaults = await test_db.get_default_channels(scope="all")
        assert len(defaults) == 2
    
    @pytest.mark.asyncio
    async def test_get_channels_by_scope(self, test_db):
        """Test retrieving channels by scope."""
        # Create channels
        await test_db.create_channel(
            channel_id="global1",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="global1",
            description="Global 1"
        )
        await test_db.create_channel(
            channel_id="global2",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="global2",
            description="Global 2"
        )
        
        # Create project channels
        await test_db.register_project("proj1", "/proj1", "Project 1")
        await test_db.create_channel(
            channel_id="proj1-chan",
            channel_type="channel",
            access_type="open",
            scope="project",
            name="proj1-chan",
            project_id="proj1",
            description="Project channel"
        )
        
        # Get global channels
        channels = await test_db.get_channels_by_scope(scope="global")
        assert len(channels) == 2
        assert all(c['scope'] == 'global' for c in channels)
        
        # Get project channels
        channels = await test_db.get_channels_by_scope(
            scope="project",
            project_id="proj1"
        )
        assert len(channels) == 1
        assert channels[0]['id'] == "proj1-chan"
        
        # Get all channels
        channels = await test_db.get_channels_by_scope(scope="all")
        assert len(channels) == 3


class TestAgentOperations:
    """Test agent-related operations."""
    
    @pytest.mark.asyncio
    async def test_get_agents_by_scope(self, test_db):
        """Test retrieving agents by scope."""
        # Create global agents
        await test_db.register_agent("global1", None, "Global 1")
        await test_db.register_agent("global2", None, "Global 2")
        
        # Create project agents
        await test_db.register_project("proj1", "/proj1", "Project 1")
        await test_db.register_agent("proj-agent", "proj1", "Project Agent")
        
        # Get global agents
        agents = await test_db.get_agents_by_scope(scope="global")
        assert len(agents) == 2
        assert all(a['project_id'] is None for a in agents)
        
        # Get project agents
        agents = await test_db.get_agents_by_scope(
            scope="project",
            project_id="proj1"
        )
        assert len(agents) == 1
        assert agents[0]['name'] == "proj-agent"
        
        # Get all agents
        agents = await test_db.get_agents_by_scope(scope="all")
        assert len(agents) == 3
    
    @pytest.mark.asyncio
    async def test_check_can_discover_agent(self, test_db):
        """Test agent discovery permission checks."""
        # Create agents
        await test_db.register_agent(
            "public_agent", None, "Public",
            discoverable="public"
        )
        await test_db.register_agent(
            "private_agent", None, "Private",
            discoverable="private"
        )
        
        await test_db.register_project("proj1", "/proj1", "Project 1")
        await test_db.register_agent(
            "project_agent", "proj1", "Project",
            discoverable="project"
        )
        
        # Create discovering agent
        await test_db.register_agent("discoverer", None, "Discoverer")
        
        # Check discovery permissions
        can_discover = await test_db.check_can_discover_agent(
            "discoverer", None,
            "public_agent", None
        )
        assert can_discover is True
        
        can_discover = await test_db.check_can_discover_agent(
            "discoverer", None,
            "private_agent", None
        )
        assert can_discover is False
        
        # Global agent can discover project agent
        can_discover = await test_db.check_can_discover_agent(
            "discoverer", None,
            "project_agent", "proj1"
        )
        assert can_discover is True


class TestValidation:
    """Test validation methods."""
    
    @pytest.mark.asyncio
    async def test_validate_mentions_batch(self, test_db):
        """Test batch mention validation."""
        # Setup
        await test_db.register_agent("sender", None, "Sender")
        await test_db.register_agent("mentioned1", None, "Mentioned 1")
        await test_db.register_agent("mentioned2", None, "Mentioned 2")
        
        channel_id = await test_db.create_channel(
            channel_id="mention-test",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="mention-test",
            description="Mention test"
        )
        
        # Add all agents to channel
        await test_db.add_channel_member(channel_id, "sender", None)
        await test_db.add_channel_member(channel_id, "mentioned1", None)
        await test_db.add_channel_member(channel_id, "mentioned2", None)
        
        # Validate mentions (expects list of dicts with name/project_id)
        results = await test_db.validate_mentions_batch(
            channel_id,
            [
                {"name": "mentioned1", "project_id": None},
                {"name": "mentioned2", "project_id": None},
                {"name": "non_existent", "project_id": None}
            ]
        )
        
        # Results has valid/invalid/unknown lists
        valid_names = [m["name"] for m in results["valid"]]
        unknown_names = [m["name"] for m in results["unknown"]]
        
        assert "mentioned1" in valid_names
        assert "mentioned2" in valid_names
        assert "non_existent" in unknown_names
    
    @pytest.mark.asyncio
    async def test_check_agent_can_access_channel(self, test_db):
        """Test channel access validation."""
        # Create channels
        await test_db.create_channel(
            channel_id="open-channel",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="open-channel",
            description="Open channel"
        )
        await test_db.create_channel(
            channel_id="invite-channel",
            channel_type="channel",
            access_type="private",
            scope="global",
            name="invite-channel",
            description="Invite only"
        )
        
        # Create agent
        await test_db.register_agent("accessor", None, "Accessor")
        
        # Check access to open channel (not a member yet)
        can_access = await test_db.check_agent_can_access_channel(
            "accessor", None, "open-channel"
        )
        assert can_access is False  # Not a member yet
        
        # Join open channel
        await test_db.add_channel_member("open-channel", "accessor", None)
        can_access = await test_db.check_agent_can_access_channel(
            "accessor", None, "open-channel"
        )
        assert can_access is True  # Now a member
        
        # Check access to invite-only channel (not a member)
        can_access = await test_db.check_agent_can_access_channel(
            "accessor", None, "invite-channel"
        )
        assert can_access is False
        
        # Add to invite channel and check again
        await test_db.add_channel_member("invite-channel", "accessor", None)
        can_access = await test_db.check_agent_can_access_channel(
            "accessor", None, "invite-channel"
        )
        assert can_access is True


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_close_database(self, test_db):
        """Test database close operation."""
        # Close should work without error
        await test_db.close()
        
        # Multiple closes should be safe
        await test_db.close()
    
    @pytest.mark.asyncio  
    async def test_project_operations_with_nulls(self, test_db):
        """Test project operations with null values."""
        # Get non-existent project
        project = await test_db.get_project("non-existent")
        assert project is None
        
        # Get links for non-existent project
        links = await test_db.get_project_links("non-existent")
        assert links == []
        
        # Check link between non-existent projects
        linked = await test_db.check_projects_linked("proj1", "proj2")
        assert linked is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])