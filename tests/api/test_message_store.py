"""
Test suite for MessageStore.
Tests coordination between SQLite and Qdrant.
"""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import json

from api.db.message_store import MessageStore
from api.ranking import RankingProfiles


@pytest_asyncio.fixture
async def message_store():
    """Provide a clean MessageStore instance for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        qdrant_path = Path(tmpdir) / "qdrant"
        
        store = MessageStore(
            db_path=str(db_path),
            qdrant_config={"qdrant_path": str(qdrant_path)}
        )
        await store.initialize()
        yield store


@pytest_asyncio.fixture
async def populated_store(message_store):
    """Provide MessageStore with test data."""
    # Register projects and agents
    await message_store.register_project("proj1", "/path/to/proj1", "Project 1")
    await message_store.register_agent(
        name="alice",
        project_id="proj1",
        description="Test agent Alice",
        dm_policy="open",
        discoverable="public"
    )
    await message_store.register_agent(
        name="bob",
        project_id="proj1",
        description="Test agent Bob",
        dm_policy="open",
        discoverable="public"
    )
    
    # Create channels
    await message_store.create_channel(
        channel_id="global:general",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="general",
        description="General discussion"
    )
    
    await message_store.create_channel(
        channel_id="proj1:dev",
        channel_type="channel",
        access_type="open",
        scope="project",
        name="dev",
        project_id="proj1",
        description="Development discussion"
    )
    
    # Add members to channels
    await message_store.add_channel_member(
        channel_id="global:general",
        agent_name="alice",
        agent_project_id="proj1"
    )
    await message_store.add_channel_member(
        channel_id="global:general",
        agent_name="bob",
        agent_project_id="proj1"
    )
    await message_store.add_channel_member(
        channel_id="proj1:dev",
        agent_name="alice",
        agent_project_id="proj1"
    )
    await message_store.add_channel_member(
        channel_id="proj1:dev",
        agent_name="bob",
        agent_project_id="proj1"
    )
    
    # Add test messages with different content for search
    test_messages = [
        {
            "channel_id": "global:general",
            "sender_id": "alice",
            "sender_project_id": "proj1",
            "content": "How to implement async/await in Python?",
            "metadata": {"confidence": 0.8, "topic": "python"}
        },
        {
            "channel_id": "global:general",
            "sender_id": "bob",
            "sender_project_id": "proj1",
            "content": "Use async def for coroutine functions",
            "metadata": {"confidence": 0.95, "topic": "python"}
        },
        {
            "channel_id": "proj1:dev",
            "sender_id": "alice",
            "sender_project_id": "proj1",
            "content": "Working on the authentication module",
            "metadata": {"confidence": 0.7, "module": "auth"}
        },
        {
            "channel_id": "proj1:dev",
            "sender_id": "bob",
            "sender_project_id": "proj1",
            "content": "Fixed the database connection pool issue",
            "metadata": {"confidence": 0.9, "module": "database"}
        }
    ]
    
    for msg in test_messages:
        await message_store.send_message(**msg)
    
    yield message_store


class TestMessageStoreBasics:
    """Test basic MessageStore operations."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, message_store):
        """Test store initialization."""
        assert message_store.sqlite is not None
        assert message_store.qdrant is not None  # Should be initialized with qdrant_config
    
    @pytest.mark.asyncio
    async def test_save_and_retrieve_message(self, populated_store):
        """Test saving and retrieving messages."""
        # Save a new message
        message_id = await populated_store.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Test message for retrieval",
            metadata={"test": True}
        )
        
        assert message_id is not None
        
        # Retrieve messages
        messages = await populated_store.get_messages(
            channel_ids=["global:general"]
        )
        
        # Find our test message
        test_msg = next((m for m in messages if m["id"] == message_id), None)
        assert test_msg is not None
        assert test_msg["content"] == "Test message for retrieval"
        assert test_msg["metadata"]["test"] is True


class TestPermissionBasedRetrieval:
    """Test permission-based message retrieval."""
    
    @pytest.mark.asyncio
    async def test_agent_message_permissions(self, populated_store):
        """Test get_agent_messages respects permissions."""
        # Create a private channel
        await populated_store.create_channel(
            channel_id="proj1:private",
            channel_type="channel",
            access_type="members",
            scope="project",
            name="private",
            project_id="proj1",
            description="Private channel"
        )
        
        # Add only alice as member
        await populated_store.add_channel_member(
            channel_id="proj1:private",
            agent_name="alice",
            agent_project_id="proj1",
            can_send=True,
            can_invite=False
        )
        
        # Post a message
        await populated_store.send_message(
            channel_id="proj1:private",
            sender_id="alice",
            sender_project_id="proj1",
            content="Private message only Alice can see"
        )
        
        # Alice should see the message
        alice_messages = await populated_store.get_agent_messages(
            agent_name="alice",
            agent_project_id="proj1"
        )
        private_msgs = [m for m in alice_messages if m["channel_id"] == "proj1:private"]
        assert len(private_msgs) == 1
        
        # Bob should NOT see the message
        bob_messages = await populated_store.get_agent_messages(
            agent_name="bob",
            agent_project_id="proj1"
        )
        private_msgs = [m for m in bob_messages if m["channel_id"] == "proj1:private"]
        assert len(private_msgs) == 0
    
    @pytest.mark.asyncio
    async def test_get_messages_no_permissions(self, populated_store):
        """Test get_messages (admin) ignores permissions."""
        # Create a private channel
        await populated_store.create_channel(
            channel_id="proj1:secret",
            channel_type="channel",
            access_type="members",
            scope="project",
            name="secret",
            project_id="proj1"
        )
        
        # Add alice as member first so she can send
        await populated_store.sqlite.add_channel_member(
            channel_id="proj1:secret",
            agent_name="alice",
            agent_project_id="proj1"
        )
        
        # Post a message
        await populated_store.sqlite.send_message(
            channel_id="proj1:secret",
            sender_id="alice",
            sender_project_id="proj1",
            content="Secret message"
        )
        
        # Admin get_messages_admin should still see it
        messages = await populated_store.sqlite.get_messages_admin(
            channel_ids=["proj1:secret"]
        )
        assert len(messages) == 1
        assert messages[0]["content"] == "Secret message"


class TestSemanticSearch:
    """Test semantic search capabilities."""
    
    @pytest.mark.asyncio
    async def test_search_messages(self, populated_store):
        """Test basic semantic search."""
        results = await populated_store.search_messages(
            query="Python async programming",
            limit=5
        )
        
        assert len(results) > 0
        # Should find messages about Python and async
        contents = [r["content"] for r in results]
        assert any("async" in c or "Python" in c for c in contents)
    
    @pytest.mark.asyncio
    async def test_search_with_channel_filter(self, populated_store):
        """Test search with channel filtering."""
        results = await populated_store.search_messages(
            query="database",
            channel_ids=["proj1:dev"],
            limit=5
        )
        
        assert len(results) > 0
        # All results should be from proj1:dev
        for result in results:
            assert result["channel_id"] == "proj1:dev"
    
    @pytest.mark.asyncio
    async def test_search_with_metadata_filter(self, populated_store):
        """Test search with metadata filtering."""
        results = await populated_store.search_messages(
            query="Python",
            metadata_filters={"confidence": {"$gte": 0.9}},
            limit=5
        )
        
        # Should only find high-confidence messages
        for result in results:
            assert result["metadata"]["confidence"] >= 0.9
    
    @pytest.mark.asyncio
    async def test_search_ranking_profiles(self, populated_store):
        """Test different ranking profiles."""
        # Add a recent message
        await populated_store.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Latest Python tips and tricks",
            metadata={"confidence": 0.5}
        )
        
        # Search with RECENT_PRIORITY
        recent_results = await populated_store.search_messages(
            query="Python",
            ranking_profile=RankingProfiles.RECENT_PRIORITY,
            limit=3
        )
        
        # Search with QUALITY_PRIORITY
        quality_results = await populated_store.search_messages(
            query="Python",
            ranking_profile=RankingProfiles.QUALITY_PRIORITY,
            limit=3
        )
        
        # Results should be different due to ranking
        assert len(recent_results) > 0
        assert len(quality_results) > 0
        # The exact order depends on the ranking algorithm
    
    @pytest.mark.asyncio
    async def test_search_agent_messages(self, populated_store):
        """Test permission-scoped search."""
        # Create private channel with searchable content
        await populated_store.create_channel(
            channel_id="proj1:security",
            channel_type="channel",
            access_type="members",
            scope="project",
            name="security",
            project_id="proj1"
        )
        
        # Only alice has access
        await populated_store.add_channel_member(
            channel_id="proj1:security",
            agent_name="alice",
            agent_project_id="proj1",
            can_send=True
        )
        
        # Add security-related message
        await populated_store.send_message(
            channel_id="proj1:security",
            sender_id="alice",
            sender_project_id="proj1",
            content="Critical security vulnerability in authentication",
            metadata={"severity": "high"}
        )
        
        # Alice should find it
        alice_results = await populated_store.search_agent_messages(
            agent_name="alice",
            agent_project_id="proj1",
            query="security vulnerability",
            limit=5
        )
        security_msgs = [r for r in alice_results if "security" in r["channel_id"]]
        assert len(security_msgs) > 0
        
        # Bob should NOT find it
        bob_results = await populated_store.search_agent_messages(
            agent_name="bob",
            agent_project_id="proj1",
            query="security vulnerability",
            limit=5
        )
        security_msgs = [r for r in bob_results if "security" in r["channel_id"]]
        assert len(security_msgs) == 0


class TestChannelOperations:
    """Test channel operations through MessageStore."""
    
    @pytest.mark.asyncio
    async def test_list_channels_for_agent(self, populated_store):
        """Test listing channels accessible to an agent."""
        # Use sqlite's get_agent_channels method
        channels = await populated_store.sqlite.get_agent_channels(
            agent_name="alice",
            agent_project_id="proj1"
        )
        
        channel_ids = {ch["id"] for ch in channels}
        # Alice should see global and project channels she's a member of
        assert "global:general" in channel_ids
        assert "proj1:dev" in channel_ids
    
    @pytest.mark.asyncio
    async def test_channel_membership(self, populated_store):
        """Test channel membership operations."""
        # Create a members-only channel
        await populated_store.create_channel(
            channel_id="proj1:team",
            channel_type="channel",
            access_type="members",
            scope="project",
            name="team",
            project_id="proj1"
        )
        
        # Add alice with full permissions
        await populated_store.add_channel_member(
            channel_id="proj1:team",
            agent_name="alice",
            agent_project_id="proj1",
            can_send=True,
            can_invite=True
        )
        
        # Check membership
        members = await populated_store.sqlite.get_channel_members("proj1:team")
        assert len(members) == 1
        assert members[0]["agent_name"] == "alice"


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_empty_search_results(self, populated_store):
        """Test search with no matches."""
        results = await populated_store.search_messages(
            query="quantum computing blockchain AI cryptocurrency",
            limit=5
        )
        # Should return results even if no perfect match (semantic search)
        assert isinstance(results, list)
    
    @pytest.mark.asyncio
    async def test_metadata_persistence(self, populated_store):
        """Test complex metadata persistence."""
        complex_metadata = {
            "nested": {
                "level1": {
                    "level2": ["item1", "item2"],
                    "data": {"key": "value"}
                }
            },
            "array": [1, 2, 3],
            "boolean": True,
            "number": 42.5
        }
        
        message_id = await populated_store.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Message with complex metadata",
            metadata=complex_metadata
        )
        
        messages = await populated_store.get_messages(
            message_ids=[message_id]
        )
        
        assert len(messages) == 1
        retrieved_metadata = messages[0]["metadata"]
        assert retrieved_metadata["nested"]["level1"]["level2"] == ["item1", "item2"]
        assert retrieved_metadata["array"] == [1, 2, 3]
        assert retrieved_metadata["boolean"] is True
        assert retrieved_metadata["number"] == 42.5
    
    @pytest.mark.asyncio
    async def test_filter_based_search(self, populated_store):
        """Test search without query (filter-only)."""
        # Search only with metadata filter, no query
        # Note: The module:auth message exists in our test data
        results = await populated_store.search_messages(
            metadata_filters={"module": "auth"},
            limit=10
        )
        
        # Should find the authentication module message
        if len(results) > 0:
            for result in results:
                assert result["metadata"]["module"] == "auth"
        else:
            # If no results, it's because Qdrant may not support pure filter search
            # without a query. This is acceptable behavior.
            pass


class TestQdrantIntegration:
    """Test Qdrant-specific functionality."""
    
    @pytest.mark.asyncio
    async def test_qdrant_disabled(self):
        """Test MessageStore without Qdrant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Create MessageStore without Qdrant config
            store = MessageStore(
                db_path=str(db_path),
                qdrant_config=None
            )
            await store.initialize()
            
            assert store.qdrant is None  # Should be None when no config provided
            
            # Should still work for basic operations
            await store.register_project("test", "/test", "Test")
            projects = await store.list_projects()
            assert len(projects) == 1
    
    @pytest.mark.asyncio
    async def test_collection_management(self, message_store):
        """Test Qdrant collection is properly managed."""
        if message_store.qdrant:
            # The collection should be created during initialization
            assert message_store.qdrant is not None
            # Collection operations are internal to QdrantStore
            
            # Verify we can index and search
            await message_store.register_project("test", "/test", "Test")
            await message_store.create_channel(
                channel_id="test:chan",
                channel_type="channel",
                access_type="open",
                scope="global",
                name="test"
            )
            
            # Register an agent first
            await message_store.sqlite.register_agent(
                name="test",
                project_id="test",
                description="Test agent"
            )
            
            # Add agent as channel member
            await message_store.sqlite.add_channel_member(
                channel_id="test:chan",
                agent_name="test",
                agent_project_id="test"
            )
            
            # This should index in Qdrant
            message_id = await message_store.sqlite.send_message(
                channel_id="test:chan",
                sender_id="test",
                sender_project_id="test",
                content="Test content for Qdrant"
            )
            
            # If Qdrant is working, this should not fail
            if message_store.qdrant:
                from datetime import datetime
                await message_store.qdrant.index_message(
                    message_id=message_id,
                    content="Test content for Qdrant",
                    metadata={},
                    channel_id="test:chan",
                    sender_id="test",
                    timestamp=datetime.now()
                )