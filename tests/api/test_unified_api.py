"""
Test suite for ClaudeSlackAPI.
Tests the unified API interface.
"""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path
from datetime import datetime
import json

from api.unified_api import ClaudeSlackAPI
from api.models import DMPolicy, Discoverability
from api.ranking import RankingProfiles


@pytest_asyncio.fixture
async def api():
    """Provide a clean API instance for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        qdrant_path = Path(tmpdir) / "qdrant"
        
        api_instance = ClaudeSlackAPI(
            db_path=str(db_path),
            qdrant_path=str(qdrant_path),
            enable_semantic_search=True
        )
        await api_instance.initialize()
        yield api_instance
        await api_instance.close()


@pytest_asyncio.fixture
async def populated_api(api):
    """Provide API with test data."""
    # Setup projects directly on db
    await api.db.register_project("proj1", "/path/to/proj1", "Project 1")
    await api.db.register_project("proj2", "/path/to/proj2", "Project 2")
    
    # Setup agents
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
        dm_policy="restricted",
        discoverable="project"
    )
    
    await api.register_agent(
        name="charlie",
        project_id="proj2",
        description="DevOps engineer",
        dm_policy="open",
        discoverable="public"
    )
    
    # Create channels
    await api.create_channel(
        name="general",
        description="General discussion",
        created_by="alice",
        created_by_project_id="proj1",
        scope="global",
        is_default=False
    )
    
    await api.create_channel(
        name="dev",
        description="Development discussion",
        created_by="alice",
        created_by_project_id="proj1",
        scope="project",
        project_id="proj1",
        is_default=False
    )
    
    # Join channels
    # Alice joins as creator
    await api.join_channel(
        agent_name="alice",
        agent_project_id="proj1",
        channel_id="global:general"
    )
    
    await api.join_channel(
        agent_name="alice",
        agent_project_id="proj1",
        channel_id="proj1:dev"
    )
    
    await api.join_channel(
        agent_name="bob",
        agent_project_id="proj1",
        channel_id="global:general"
    )
    
    await api.join_channel(
        agent_name="bob",
        agent_project_id="proj1",
        channel_id="proj1:dev"
    )
    
    # Send some messages
    await api.send_message(
        channel_id="global:general",
        sender_id="alice",
        sender_project_id="proj1",
        content="Welcome everyone!"
    )
    
    await api.send_message(
        channel_id="proj1:dev",
        sender_id="bob",
        sender_project_id="proj1",
        content="Working on the API integration"
    )
    
    yield api


class TestAPIInitialization:
    """Test API initialization and configuration."""
    
    @pytest.mark.asyncio
    async def test_basic_initialization(self, api):
        """Test basic API initialization."""
        assert api.db is not None
        assert api.channels is not None
        assert api.notes is not None
    
    @pytest.mark.asyncio
    async def test_initialization_with_qdrant_url(self):
        """Test initialization with Qdrant URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            api = ClaudeSlackAPI(
                db_path=str(db_path),
                qdrant_url="http://localhost:6333",
                enable_semantic_search=True
            )
            await api.initialize()
            
            # Should attempt to initialize Qdrant with the URL
            # It may fail if Qdrant server isn't running, but that's ok
            assert api.db is not None
            await api.close()


class TestAgentManagement:
    """Test agent-related API methods."""
    
    @pytest.mark.asyncio
    async def test_register_agent(self, api):
        """Test agent registration."""
        await api.db.register_project("test_proj", "/path", "Test Project")
        
        await api.register_agent(
            name="test_agent",
            project_id="test_proj",
            description="A test agent",
            dm_policy="open",
            discoverable="public"
        )
        
        agents = await api.list_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "test_agent"
    
    @pytest.mark.asyncio
    async def test_list_agents_with_filter(self, populated_api):
        """Test listing agents with filters."""
        # List all agents
        all_agents = await populated_api.list_agents()
        assert len(all_agents) == 3
        
        # List agents in proj1
        proj1_agents = await populated_api.list_agents(scope="project", project_id="proj1")
        assert len(proj1_agents) == 2
        assert all(a["project_id"] == "proj1" for a in proj1_agents)
        
        # List by scope - global means agents not tied to a project
        global_agents = await populated_api.list_agents(scope="global")
        # All our test agents are tied to projects, so this should be empty
        assert len(global_agents) == 0
    
    @pytest.mark.asyncio
    async def test_get_agent(self, populated_api):
        """Test getting specific agent."""
        agent = await populated_api.get_agent("alice", "proj1")
        assert agent is not None
        assert agent["name"] == "alice"
        assert agent["description"] == "Frontend developer"


class TestChannelManagement:
    """Test channel-related API methods."""
    
    @pytest.mark.asyncio
    async def test_create_channel(self, populated_api):
        """Test channel creation."""
        channel_id = await populated_api.create_channel(
            name="testing",
            description="Testing channel",
            created_by="alice",
            created_by_project_id="proj1",
            scope="global"
        )
        
        assert channel_id == "global:testing"
    
    @pytest.mark.asyncio
    async def test_list_channels(self, populated_api):
        """Test listing channels."""
        channels = await populated_api.list_channels(
            agent_name="alice",
            project_id="proj1"
        )
        
        assert len(channels) > 0
        channel_names = {ch["name"] for ch in channels}
        assert "general" in channel_names
        assert "dev" in channel_names
    
    @pytest.mark.asyncio
    async def test_join_leave_channel(self, populated_api):
        """Test joining and leaving channels."""
        # Charlie joins general channel
        result = await populated_api.join_channel(
            agent_name="charlie",
            agent_project_id="proj2",
            channel_id="global:general"
        )
        assert result is True
        
        # Check Charlie is member
        members = await populated_api.list_channel_members("global:general")
        charlie_member = [m for m in members if m["agent_name"] == "charlie"]
        assert len(charlie_member) == 1
        
        # Charlie leaves
        result = await populated_api.leave_channel(
            agent_name="charlie",
            agent_project_id="proj2",
            channel_id="global:general"
        )
        assert result is True
        
        # Check Charlie is no longer member
        members = await populated_api.list_channel_members("global:general")
        charlie_member = [m for m in members if m["agent_name"] == "charlie"]
        assert len(charlie_member) == 0
    
    @pytest.mark.asyncio
    async def test_invite_to_channel(self, populated_api):
        """Test channel invitations."""
        # Create a private channel
        channel_id = await populated_api.create_channel(
            name="private",
            description="Private channel",
            created_by="alice",
            created_by_project_id="proj1",
            scope="project",
            project_id="proj1",
            access_type="members",
            is_default=False
        )
        
        # Alice (creator) invites Bob
        result = await populated_api.invite_to_channel(
            channel_id=channel_id,
            inviter_name="alice",
            inviter_project_id="proj1",
            invitee_name="bob",
            invitee_project_id="proj1"
        )
        
        assert result is True
        
        # Check Bob is now a member
        members = await populated_api.list_channel_members(channel_id)
        bob_member = [m for m in members if m["agent_name"] == "bob"]
        assert len(bob_member) == 1
    
    @pytest.mark.asyncio
    async def test_get_channel(self, populated_api):
        """Test getting channel information."""
        channel = await populated_api.get_channel("global:general")
        assert channel is not None
        assert channel["name"] == "general"
        assert channel["description"] == "General discussion"
    
    @pytest.mark.asyncio
    async def test_get_scoped_channel_id(self, populated_api):
        """Test scoped channel ID generation."""
        # Global channel
        channel_id = populated_api.get_scoped_channel_id("test", "global")
        assert channel_id == "global:test"
        
        # Project channel
        channel_id = populated_api.get_scoped_channel_id("test", "project", "proj1")
        assert channel_id == "proj1:test"


class TestMessaging:
    """Test message-related API methods."""
    
    @pytest.mark.asyncio
    async def test_send_message(self, populated_api):
        """Test sending messages."""
        message_id = await populated_api.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Test message",
            metadata={"priority": "low"}
        )
        
        assert isinstance(message_id, int)
    
    @pytest.mark.asyncio
    async def test_send_direct_message(self, populated_api):
        """Test sending direct messages."""
        message_id = await populated_api.send_direct_message(
            sender_name="alice",
            sender_project_id="proj1",
            recipient_name="bob",
            recipient_project_id="proj1",
            content="Private message to Bob",
            metadata={"urgent": True}
        )
        
        assert isinstance(message_id, int)
    
    @pytest.mark.asyncio
    async def test_get_message(self, populated_api):
        """Test retrieving a specific message."""
        # Send a message
        message_id = await populated_api.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Message to retrieve",
            metadata={"test": True}
        )
        
        # Retrieve it
        message = await populated_api.get_message(message_id)
        assert message is not None
        assert message["content"] == "Message to retrieve"
        assert message["metadata"]["test"] is True
    
    @pytest.mark.asyncio
    async def test_get_agent_messages(self, populated_api):
        """Test retrieving messages for an agent."""
        messages = await populated_api.get_agent_messages(
            agent_name="alice",
            agent_project_id="proj1",
            limit=10
        )
        
        assert len(messages) > 0
        # Should include messages from accessible channels
        assert any(m["content"] == "Welcome everyone!" for m in messages)
    
    @pytest.mark.asyncio
    async def test_get_messages_admin(self, populated_api):
        """Test administrative message retrieval."""
        messages = await populated_api.get_messages(
            channel_ids=["global:general"],
            limit=10
        )
        
        assert len(messages) > 0
        # Should include all messages in the channel
    
    @pytest.mark.asyncio
    async def test_search_messages(self, populated_api):
        """Test message search without permissions."""
        # Add more messages for search
        await populated_api.send_message(
            channel_id="proj1:dev",
            sender_id="alice",
            sender_project_id="proj1",
            content="Python async programming best practices",
            metadata={"confidence": 0.9, "topic": "python"}
        )
        
        # Search for Python
        results = await populated_api.search_messages(
            query="Python programming",
            limit=5
        )
        
        # Should find relevant messages
        assert len(results) > 0
        assert any("Python" in r["content"] or "python" in r["content"].lower() for r in results)
    
    @pytest.mark.asyncio
    async def test_search_agent_messages(self, populated_api):
        """Test permission-scoped message search."""
        # Add a message in a channel alice has access to
        await populated_api.send_message(
            channel_id="proj1:dev",
            sender_id="alice",
            sender_project_id="proj1",
            content="Python async programming best practices",
            metadata={"confidence": 0.9}
        )
        
        # Search for Python as alice
        results = await populated_api.search_agent_messages(
            agent_name="alice",
            agent_project_id="proj1",
            query="Python programming",
            limit=5
        )
        
        assert len(results) > 0
        assert any("Python" in r["content"] for r in results)
    
    @pytest.mark.asyncio
    async def test_search_with_metadata_filters(self, populated_api):
        """Test search with metadata filtering."""
        # Add messages with different metadata
        await populated_api.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="High confidence message",
            metadata={"confidence": 0.95, "topic": "testing"}
        )
        
        await populated_api.send_message(
            channel_id="global:general",
            sender_id="bob",
            sender_project_id="proj1",
            content="Low confidence message",
            metadata={"confidence": 0.3, "topic": "testing"}
        )
        
        # Search with metadata filter
        results = await populated_api.search_messages(
            metadata_filters={"confidence": {"$gte": 0.9}},
            limit=10
        )
        
        # Should only find high-confidence messages
        for result in results:
            if "confidence" in result.get("metadata", {}):
                assert result["metadata"]["confidence"] >= 0.9


class TestProjectManagement:
    """Test project-related operations."""
    
    @pytest.mark.asyncio
    async def test_register_project(self, api):
        """Test project registration."""
        await api.db.register_project("test", "/test/path", "Test Project")
        projects = await api.db.list_projects()
        assert len(projects) == 1
        assert projects[0]["id"] == "test"
        assert projects[0]["name"] == "Test Project"
    
    @pytest.mark.asyncio
    async def test_project_links(self, populated_api):
        """Test project linking."""
        # Link proj1 and proj2
        await populated_api.db.add_project_link("proj1", "proj2", "bidirectional")
        
        # Check links
        links = await populated_api.db.get_linked_projects("proj1")
        assert any(p["project_id"] == "proj2" for p in links)
        
        links = await populated_api.db.get_linked_projects("proj2")
        assert any(p["project_id"] == "proj1" for p in links)


class TestNotesIntegration:
    """Test notes functionality."""
    
    @pytest.mark.asyncio
    async def test_write_note(self, populated_api):
        """Test writing notes."""
        note_id = await populated_api.write_note(
            agent_name="alice",
            agent_project_id="proj1",
            content="Remember to review the API documentation",
            session_context="API development session",
            tags=["todo", "documentation"]
        )
        
        assert isinstance(note_id, int)
    
    @pytest.mark.asyncio
    async def test_search_notes(self, populated_api):
        """Test searching notes."""
        # Write some notes first
        await populated_api.write_note(
            agent_name="alice",
            agent_project_id="proj1",
            content="API endpoint /users needs authentication",
            tags=["security", "api"]
        )
        
        await populated_api.write_note(
            agent_name="alice",
            agent_project_id="proj1",
            content="Database query optimization completed",
            tags=["performance", "database"]
        )
        
        # Search by query
        results = await populated_api.search_notes(
            agent_name="alice",
            agent_project_id="proj1",
            query="API"
        )
        assert len(results) > 0
        
        # Search by tags
        results = await populated_api.search_notes(
            agent_name="alice",
            agent_project_id="proj1",
            tags=["security"]
        )
        assert any("authentication" in r["content"] for r in results)
    
    @pytest.mark.asyncio
    async def test_get_recent_notes(self, populated_api):
        """Test getting recent notes."""
        # Write a note
        await populated_api.write_note(
            agent_name="alice",
            agent_project_id="proj1",
            content="Recent note for testing",
            tags=["test"]
        )
        
        # Get recent notes
        notes = await populated_api.get_recent_notes(
            agent_name="alice",
            agent_project_id="proj1",
            limit=5
        )
        
        assert len(notes) > 0
        assert any("Recent note" in n["content"] for n in notes)
    
    @pytest.mark.asyncio
    async def test_peek_agent_notes(self, populated_api):
        """Test peeking at another agent's notes."""
        # Alice writes a note
        await populated_api.write_note(
            agent_name="alice",
            agent_project_id="proj1",
            content="Frontend routing issue resolved",
            tags=["frontend", "fix"]
        )
        
        # Bob peeks at Alice's notes
        results = await populated_api.peek_agent_notes(
            target_agent_name="alice",
            target_agent_project_id="proj1",
            requester_agent_name="bob",
            requester_project_id="proj1"
        )
        
        assert len(results) > 0
        assert any("Frontend" in r["content"] for r in results)


class TestDirectMessages:
    """Test direct messaging functionality."""
    
    @pytest.mark.asyncio
    async def test_dm_flow(self, populated_api):
        """Test complete DM flow."""
        # Send a DM from alice to bob
        message_id = await populated_api.send_direct_message(
            sender_name="alice",
            sender_project_id="proj1",
            recipient_name="bob",
            recipient_project_id="proj1",
            content="Hi Bob, can you help with the API?"
        )
        
        assert isinstance(message_id, int)
        
        # Bob should see the message
        bob_messages = await populated_api.get_agent_messages(
            agent_name="bob",
            agent_project_id="proj1"
        )
        dm_messages = [m for m in bob_messages if m["channel_type"] == "direct"]
        assert len(dm_messages) > 0
        assert any("can you help" in m["content"] for m in dm_messages)
        
        # Alice should also see it
        alice_messages = await populated_api.get_agent_messages(
            agent_name="alice",
            agent_project_id="proj1"
        )
        dm_messages = [m for m in alice_messages if m["channel_type"] == "direct"]
        assert len(dm_messages) > 0
    
    @pytest.mark.asyncio
    async def test_dm_permissions(self, populated_api):
        """Test DM permission checks."""
        # Bob has restricted DM policy
        # Try to send DM to Bob from Charlie (different project)
        # This should work if Bob's policy allows it or fail gracefully
        try:
            message_id = await populated_api.send_direct_message(
                sender_name="charlie",
                sender_project_id="proj2",
                recipient_name="bob",
                recipient_project_id="proj1",
                content="Hi Bob from Charlie"
            )
            # If it succeeds, verify the message was sent
            assert isinstance(message_id, int)
        except ValueError as e:
            # If it fails due to permissions, that's expected
            assert "permission" in str(e).lower() or "restricted" in str(e).lower()


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_invalid_agent(self, populated_api):
        """Test operations with non-existent agent."""
        messages = await populated_api.get_agent_messages(
            agent_name="nonexistent",
            agent_project_id="proj1"
        )
        # Should return empty list, not error
        assert messages == []
    
    @pytest.mark.asyncio
    async def test_duplicate_channel(self, populated_api):
        """Test creating duplicate channel."""
        with pytest.raises(Exception) as excinfo:
            await populated_api.create_channel(
                name="general",  # Already exists
                description="Duplicate channel",
                created_by="alice",
                created_by_project_id="proj1",
                scope="global"
            )
        
        assert "already exists" in str(excinfo.value).lower() or "unique" in str(excinfo.value).lower()
    
    @pytest.mark.asyncio
    async def test_unauthorized_invite(self, populated_api):
        """Test invitation without permission."""
        # Create members-only channel
        channel_id = await populated_api.create_channel(
            name="restricted",
            description="Restricted channel",
            created_by="alice",
            created_by_project_id="proj1",
            scope="project",
            project_id="proj1",
            access_type="members"
        )
        
        # Bob (non-member) tries to invite Charlie
        with pytest.raises(ValueError) as excinfo:
            await populated_api.invite_to_channel(
                channel_id=channel_id,
                inviter_name="bob",
                inviter_project_id="proj1",
                invitee_name="charlie",
                invitee_project_id="proj2"
            )
        
        assert "permission" in str(excinfo.value).lower() or "not a member" in str(excinfo.value).lower()


class TestSemanticSearch:
    """Test semantic search capabilities with Qdrant."""
    
    @pytest.mark.asyncio
    async def test_semantic_search(self, populated_api):
        """Test semantic search functionality."""
        if not populated_api.db.qdrant:
            pytest.skip("Qdrant not configured")
        
        # Add messages with varied content
        await populated_api.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Python async/await patterns are powerful for concurrent programming",
            metadata={"topic": "python", "confidence": 0.9}
        )
        
        await populated_api.send_message(
            channel_id="global:general",
            sender_id="bob",
            sender_project_id="proj1",
            content="Database indexing strategies for improving query performance",
            metadata={"topic": "database", "confidence": 0.85}
        )
        
        # Search for related content
        results = await populated_api.search_messages(
            query="asynchronous programming in Python",
            limit=5,
            ranking_profile="similarity"
        )
        
        assert len(results) > 0
        # Should find the Python async message
        assert any("async" in r["content"] or "Python" in r["content"] for r in results)
    
    @pytest.mark.asyncio
    async def test_ranking_profiles(self, populated_api):
        """Test different ranking profiles."""
        if not populated_api.db.qdrant:
            pytest.skip("Qdrant not configured")
        
        # Add messages with different characteristics
        await populated_api.send_message(
            channel_id="global:general",
            sender_id="alice",
            sender_project_id="proj1",
            content="Recent Python tip: use dataclasses",
            metadata={"confidence": 0.5}
        )
        
        await populated_api.send_message(
            channel_id="global:general",
            sender_id="bob",
            sender_project_id="proj1",
            content="Old Python wisdom: explicit is better than implicit",
            metadata={"confidence": 0.95}
        )
        
        # Test different ranking profiles
        recent_results = await populated_api.search_messages(
            query="Python",
            ranking_profile="recent",
            limit=2
        )
        
        quality_results = await populated_api.search_messages(
            query="Python",
            ranking_profile="quality",
            limit=2
        )
        
        # Both should return results
        assert len(recent_results) > 0
        assert len(quality_results) > 0
        # Results may differ based on ranking