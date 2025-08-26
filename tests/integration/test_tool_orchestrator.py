"""
Integration tests for MCPToolOrchestrator.
Tests all MCP tool execution paths and validation logic.
"""

import pytest
import pytest_asyncio
import json
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

from utils.tool_orchestrator import MCPToolOrchestrator, ProjectContext


class TestToolOrchestrator:
    """Test the MCPToolOrchestrator class."""

    @pytest_asyncio.fixture
    async def orchestrator(self, test_db):
        """Provide an MCPToolOrchestrator instance."""
        orchestrator = MCPToolOrchestrator(test_db.db_path)
        await orchestrator.db.initialize()
        return orchestrator

    @pytest_asyncio.fixture
    async def test_context(self, test_db):
        """Provide a test project context."""
        await test_db.register_project("proj_test", "/test/project", "Test Project")
        return ProjectContext(
            project_id="proj_test",
            project_path="/test/project",
            project_name="Test Project"
        )

    @pytest_asyncio.fixture
    async def test_agents(self, test_db):
        """Register test agents."""
        await test_db.register_project("proj_test", "/test/project", "Test Project")
        
        # Register test agents
        await test_db.register_agent(
            name="alice",
            project_id="proj_test",
            description="Test agent Alice",
            dm_policy="open",
            discoverable="public"
        )
        
        await test_db.register_agent(
            name="bob",
            project_id=None,  # Global agent
            description="Test agent Bob",
            dm_policy="open",  # Changed to open for general testing
            discoverable="public"
        )
        
        return {"alice": "proj_test", "bob": None}


class TestChannelOperations(TestToolOrchestrator):
    """Test channel-related tool operations."""

    @pytest.mark.asyncio
    async def test_create_channel_global(self, orchestrator, test_agents):
        """Test creating a global channel."""
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "bob",
                "channel_id": "test-channel",
                "description": "Test channel",
                "scope": "global",
                "is_default": False
            }
        )
        
        assert result["success"] == True
        assert "Created global channel" in result["content"]
        
        # Verify channel was created
        channel = await orchestrator.db.get_channel("global:test-channel")
        assert channel is not None
        assert channel["name"] == "test-channel"
        assert channel["scope"] == "global"

    @pytest.mark.asyncio
    async def test_create_channel_project(self, orchestrator, test_agents, test_context):
        """Test creating a project channel."""
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "alice",
                "channel_id": "dev-channel",
                "description": "Development channel",
                "scope": "project"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Created project channel" in result["content"]

    @pytest.mark.asyncio
    async def test_create_channel_invalid_name(self, orchestrator, test_agents):
        """Test creating channel with invalid name."""
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "bob",
                "channel_id": "Test Channel!",  # Invalid characters
                "description": "Invalid channel"
            }
        )
        
        assert result["success"] == False
        assert "Invalid channel name" in result["error"]

    @pytest.mark.asyncio
    async def test_list_channels(self, orchestrator, test_agents, test_context):
        """Test listing available channels."""
        # Create some channels first
        await orchestrator.db.create_channel(
            channel_id="global:general",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="general",
            description="General discussion"
        )
        
        await orchestrator.db.create_channel(
            channel_id="proj_test:dev",
            channel_type="channel",
            access_type="open",
            scope="project",
            name="dev",
            project_id="proj_test",
            description="Development"
        )
        
        result = await orchestrator.execute_tool(
            "list_channels",
            {
                "agent_id": "alice",
                "scope": "all"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "general" in result["content"] or "dev" in result["content"]

    @pytest.mark.asyncio
    async def test_join_channel(self, orchestrator, test_agents, test_context):
        """Test joining an open channel."""
        # Create a channel first
        await orchestrator.db.create_channel(
            channel_id="global:test-join",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="test-join"
        )
        
        result = await orchestrator.execute_tool(
            "join_channel",
            {
                "agent_id": "alice",
                "channel_id": "test-join",
                "scope": "global"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Joined channel" in result["content"]
        
        # Verify membership
        is_member = await orchestrator.channels.is_channel_member(
            "global:test-join", "alice", "proj_test"
        )
        assert is_member == True

    @pytest.mark.asyncio
    async def test_leave_channel(self, orchestrator, test_agents, test_context):
        """Test leaving a channel."""
        # Create and join a channel first
        await orchestrator.db.create_channel(
            channel_id="global:test-leave",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="test-leave"
        )
        
        await orchestrator.channels.join_channel(
            "alice", "proj_test", "global:test-leave"
        )
        
        result = await orchestrator.execute_tool(
            "leave_channel",
            {
                "agent_id": "alice",
                "channel_id": "test-leave",
                "scope": "global"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Left channel" in result["content"]

    @pytest.mark.asyncio
    async def test_invite_to_channel(self, orchestrator, test_agents, test_context):
        """Test inviting another agent to a members channel."""
        # Create a members channel
        await orchestrator.db.create_channel(
            channel_id="global:members-only",
            channel_type="channel",
            access_type="members",
            scope="global",
            name="members-only"
        )
        
        # Alice joins first
        await orchestrator.db.add_channel_member(
            channel_id="global:members-only",
            agent_name="alice",
            agent_project_id="proj_test",
            can_invite=True
        )
        
        # Alice invites Bob
        result = await orchestrator.execute_tool(
            "invite_to_channel",
            {
                "agent_id": "alice",
                "channel_id": "members-only",
                "invitee_id": "bob",
                "scope": "global"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Invited bob" in result["content"]

    @pytest.mark.asyncio
    async def test_list_my_channels(self, orchestrator, test_agents, test_context):
        """Test listing agent's channels."""
        # Create and join some channels
        await orchestrator.db.create_channel(
            channel_id="global:test1",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="test1"
        )
        
        await orchestrator.channels.join_channel(
            "alice", "proj_test", "global:test1"
        )
        
        result = await orchestrator.execute_tool(
            "list_my_channels",
            {"agent_id": "alice"},
            context=test_context
        )
        
        assert result["success"] == True
        assert "test1" in result["content"]


class TestMessageOperations(TestToolOrchestrator):
    """Test message-related tool operations."""

    @pytest.mark.asyncio
    async def test_send_channel_message(self, orchestrator, test_agents, test_context):
        """Test sending a message to a channel."""
        # Create channel and join it
        await orchestrator.db.create_channel(
            channel_id="global:messaging",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="messaging"
        )
        
        await orchestrator.channels.join_channel(
            "alice", "proj_test", "global:messaging"
        )
        
        result = await orchestrator.execute_tool(
            "send_channel_message",
            {
                "agent_id": "alice",
                "channel_id": "messaging",
                "content": "Test message",
                "scope": "global"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Message sent" in result["content"]

    @pytest.mark.asyncio
    async def test_send_channel_message_not_member(self, orchestrator, test_agents, test_context):
        """Test sending message when not a channel member."""
        # Create channel but don't join
        await orchestrator.db.create_channel(
            channel_id="global:no-access",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="no-access"
        )
        
        result = await orchestrator.execute_tool(
            "send_channel_message",
            {
                "agent_id": "alice",
                "channel_id": "no-access",
                "content": "Should fail",
                "scope": "global"
            },
            context=test_context
        )
        
        assert result["success"] == False
        assert "must join" in result["error"]

    @pytest.mark.asyncio
    async def test_send_direct_message(self, orchestrator, test_agents, test_context):
        """Test sending a direct message."""
        result = await orchestrator.execute_tool(
            "send_direct_message",
            {
                "agent_id": "alice",
                "recipient_id": "bob",
                "content": "Hello Bob!"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "DM sent" in result["content"]

    @pytest.mark.asyncio
    async def test_send_direct_message_blocked(self, orchestrator, test_agents, test_context):
        """Test sending DM to agent with restricted policy."""
        # Register agent with closed DM policy
        await orchestrator.db.register_agent(
            name="charlie",
            project_id=None,
            dm_policy="closed"
        )
        
        result = await orchestrator.execute_tool(
            "send_direct_message",
            {
                "agent_id": "alice",
                "recipient_id": "charlie",
                "content": "This should fail"
            },
            context=test_context
        )
        
        assert result["success"] == False
        assert "DM not allowed" in result["error"] or "Cannot create DM" in result["error"]

    @pytest.mark.asyncio
    async def test_get_messages(self, orchestrator, test_agents, test_context):
        """Test getting messages for an agent."""
        # Create channel and send some messages
        await orchestrator.db.create_channel(
            channel_id="global:test-msgs",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="test-msgs"
        )
        
        await orchestrator.channels.join_channel(
            "alice", "proj_test", "global:test-msgs"
        )
        
        await orchestrator.db.send_message(
            channel_id="global:test-msgs",
            sender_id="alice",
            sender_project_id="proj_test",
            content="Test message 1"
        )
        
        result = await orchestrator.execute_tool(
            "get_messages",
            {
                "agent_id": "alice",
                "limit": 10
            },
            context=test_context
        )
        
        assert result["success"] == True
        # Messages should be formatted in the response

    @pytest.mark.asyncio
    async def test_search_messages(self, orchestrator, test_agents, test_context):
        """Test searching messages."""
        # Create channel and send messages
        await orchestrator.db.create_channel(
            channel_id="global:search-test",
            channel_type="channel",
            access_type="open",
            scope="global",
            name="search-test"
        )
        
        await orchestrator.channels.join_channel(
            "alice", "proj_test", "global:search-test"
        )
        
        await orchestrator.db.send_message(
            channel_id="global:search-test",
            sender_id="alice",
            sender_project_id="proj_test",
            content="This is a unique test message"
        )
        
        result = await orchestrator.execute_tool(
            "search_messages",
            {
                "agent_id": "alice",
                "query": "unique",
                "scope": "all"
            },
            context=test_context
        )
        
        assert result["success"] == True


class TestProjectOperations(TestToolOrchestrator):
    """Test project and discovery operations."""

    @pytest.mark.asyncio
    async def test_get_current_project(self, orchestrator, test_context):
        """Test getting current project context."""
        result = await orchestrator.execute_tool(
            "get_current_project",
            {},
            context=test_context
        )
        
        assert result["success"] == True
        assert "proj_test" in result["content"]
        assert "Test Project" in result["content"]

    @pytest.mark.asyncio
    async def test_get_current_project_no_context(self, orchestrator):
        """Test getting project context when none exists."""
        result = await orchestrator.execute_tool(
            "get_current_project",
            {},
            context=None
        )
        
        assert result["success"] == True
        assert "No project context" in result["content"]

    @pytest.mark.asyncio
    async def test_list_projects(self, orchestrator, test_agents, test_context):
        """Test listing all projects."""
        # Register additional project
        await orchestrator.db.register_project(
            "proj_other", "/other/project", "Other Project"
        )
        
        result = await orchestrator.execute_tool(
            "list_projects",
            {},
            context=test_context
        )
        
        assert result["success"] == True
        assert "Test Project" in result["content"]
        assert "Other Project" in result["content"]

    @pytest.mark.asyncio
    async def test_list_agents(self, orchestrator, test_agents, test_context):
        """Test listing discoverable agents."""
        result = await orchestrator.execute_tool(
            "list_agents",
            {
                "agent_id": "alice",
                "scope": "all",
                "include_descriptions": True
            },
            context=test_context
        )
        
        assert result["success"] == True
        # Should see bob (global agent)
        assert "bob" in result["content"].lower()

    @pytest.mark.asyncio
    async def test_list_agents_no_context(self, orchestrator):
        """Test listing agents without agent context."""
        result = await orchestrator.execute_tool(
            "list_agents",
            {"scope": "all"},  # Missing agent_id
            context=None
        )
        
        assert result["success"] == False
        assert "Missing required parameter: agent_id" in result["error"]

    @pytest.mark.asyncio
    async def test_get_linked_projects(self, orchestrator, test_context):
        """Test getting linked projects."""
        # Add another project and link it
        await orchestrator.db.register_project(
            "proj_linked", "/linked/project", "Linked Project"
        )
        await orchestrator.db.add_project_link(
            "proj_test", "proj_linked", "bidirectional"
        )
        
        result = await orchestrator.execute_tool(
            "get_linked_projects",
            {},
            context=test_context
        )
        
        assert result["success"] == True
        assert "Linked Project" in result["content"]

    @pytest.mark.asyncio
    async def test_get_linked_projects_no_context(self, orchestrator):
        """Test getting linked projects without context."""
        result = await orchestrator.execute_tool(
            "get_linked_projects",
            {},
            context=None
        )
        
        assert result["success"] == True
        assert "No project context" in result["content"]


class TestNotesOperations(TestToolOrchestrator):
    """Test notes-related tool operations."""

    @pytest.mark.asyncio
    async def test_write_note(self, orchestrator, test_agents, test_context):
        """Test writing a note."""
        result = await orchestrator.execute_tool(
            "write_note",
            {
                "agent_id": "alice",
                "content": "This is a test note",
                "tags": ["test", "example"],
                "session_context": "Testing notes"
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Note saved" in result["content"]

    @pytest.mark.asyncio
    async def test_write_note_no_content(self, orchestrator, test_agents, test_context):
        """Test writing note without content."""
        result = await orchestrator.execute_tool(
            "write_note",
            {
                "agent_id": "alice",
                "content": ""
            },
            context=test_context  # Add context to ensure agent is found
        )
        
        assert result["success"] == False
        assert "content is required" in result["error"]

    @pytest.mark.asyncio
    async def test_search_my_notes(self, orchestrator, test_agents, test_context):
        """Test searching own notes."""
        # Write some notes first
        await orchestrator.notes.write_note(
            "alice", "proj_test",
            "Important finding about the system",
            tags=["important", "system"]
        )
        
        await orchestrator.notes.write_note(
            "alice", "proj_test",
            "Another note about testing",
            tags=["test"]
        )
        
        result = await orchestrator.execute_tool(
            "search_my_notes",
            {
                "agent_id": "alice",
                "query": "system",
                "limit": 10
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "finding" in result["content"] or "system" in result["content"]

    @pytest.mark.asyncio
    async def test_get_recent_notes(self, orchestrator, test_agents, test_context):
        """Test getting recent notes."""
        # Write a note
        await orchestrator.notes.write_note(
            "alice", "proj_test",
            "Recent note for testing"
        )
        
        result = await orchestrator.execute_tool(
            "get_recent_notes",
            {
                "agent_id": "alice",
                "limit": 5
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Recent note" in result["content"]

    @pytest.mark.asyncio
    async def test_peek_agent_notes(self, orchestrator, test_agents, test_context):
        """Test peeking at another agent's notes."""
        # Write notes for bob
        await orchestrator.notes.write_note(
            "bob", None,
            "Bob's private note"
        )
        
        result = await orchestrator.execute_tool(
            "peek_agent_notes",
            {
                "agent_id": "alice",
                "target_agent": "bob",
                "limit": 5
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "Notes from bob" in result["content"]

    @pytest.mark.asyncio
    async def test_peek_agent_notes_not_found(self, orchestrator, test_agents, test_context):
        """Test peeking at non-existent agent's notes."""
        result = await orchestrator.execute_tool(
            "peek_agent_notes",
            {
                "agent_id": "alice",
                "target_agent": "nonexistent"
            },
            context=test_context
        )
        
        assert result["success"] == False
        assert "not found" in result["error"]


class TestValidationAndErrors(TestToolOrchestrator):
    """Test validation and error handling."""

    @pytest.mark.asyncio
    async def test_missing_agent_id(self, orchestrator):
        """Test tool requiring agent_id without providing it."""
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "channel_id": "test",
                "description": "Test"
            }
        )
        
        assert result["success"] == False
        assert "Missing required parameter: agent_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_agent_id(self, orchestrator):
        """Test with non-existent agent."""
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "nonexistent",
                "channel_id": "test",
                "description": "Test"
            }
        )
        
        assert result["success"] == False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_tool(self, orchestrator):
        """Test calling unknown tool."""
        result = await orchestrator.execute_tool(
            "unknown_tool",
            {"agent_id": "alice"}
        )
        
        assert result["success"] == False
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_agent_with_project_hint(self, orchestrator, test_agents, test_context):
        """Test agent_id with project hint (alice@proj_test)."""
        result = await orchestrator.execute_tool(
            "list_my_channels",
            {"agent_id": "alice@proj_test"},
            context=test_context
        )
        
        assert result["success"] == True

    @pytest.mark.asyncio
    async def test_channel_name_resolution(self, orchestrator, test_agents, test_context):
        """Test channel name resolution with and without scope prefix."""
        # Create a project channel (use correct ID format)
        proj_id_short = test_context.project_id[:8]
        await orchestrator.db.create_channel(
            channel_id=f"proj_{proj_id_short}:dev",
            channel_type="channel",
            access_type="open",
            scope="project",
            name="dev",
            project_id="proj_test"
        )
        
        # Test with just name (should resolve based on context)
        result = await orchestrator.execute_tool(
            "join_channel",
            {
                "agent_id": "alice",
                "channel_id": "dev"  # No scope prefix
            },
            context=test_context
        )
        
        # Should join the project channel based on context
        assert result["success"] == True

    @pytest.mark.asyncio
    async def test_scope_resolution(self, orchestrator, test_agents, test_context):
        """Test scope resolution with different contexts."""
        # Test with explicit global scope
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "alice",
                "channel_id": "global-test",
                "scope": "global"
            },
            context=test_context  # Has project context
        )
        
        assert result["success"] == True
        assert "global channel" in result["content"]
        
        # Test with no scope (should use project from context)
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "alice",
                "channel_id": "project-test"
                # No scope specified
            },
            context=test_context
        )
        
        assert result["success"] == True
        assert "project channel" in result["content"]


class TestIntegrationScenarios(TestToolOrchestrator):
    """Test complex integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_channel_workflow(self, orchestrator, test_agents, test_context):
        """Test complete channel workflow: create, join, message, leave."""
        # Ensure agents are registered
        await orchestrator.db.initialize()
        
        # Step 1: Create channel (alice is already registered via test_agents fixture)
        result = await orchestrator.execute_tool(
            "create_channel",
            {
                "agent_id": "alice",
                "channel_id": "workflow-test",
                "description": "Testing workflow",
                "scope": "global"
            },
            context=test_context
        )
        assert result["success"] == True
        
        # Step 2: Bob joins the channel
        result = await orchestrator.execute_tool(
            "join_channel",
            {
                "agent_id": "bob",
                "channel_id": "workflow-test",
                "scope": "global"
            }
        )
        assert result["success"] == True
        
        # Step 3: Alice sends a message
        result = await orchestrator.execute_tool(
            "send_channel_message",
            {
                "agent_id": "alice",
                "channel_id": "workflow-test",
                "content": "Hello everyone!",
                "scope": "global"
            },
            context=test_context
        )
        assert result["success"] == True
        
        # Step 4: Bob gets messages
        result = await orchestrator.execute_tool(
            "get_messages",
            {
                "agent_id": "bob",
                "limit": 10
            }
        )
        assert result["success"] == True
        
        # Step 5: Bob leaves the channel
        result = await orchestrator.execute_tool(
            "leave_channel",
            {
                "agent_id": "bob",
                "channel_id": "workflow-test",
                "scope": "global"
            }
        )
        assert result["success"] == True

    @pytest.mark.asyncio
    async def test_cross_project_communication(self, orchestrator, test_context):
        """Test communication between agents in different projects."""
        # Ensure database is initialized
        await orchestrator.db.initialize()
        
        # Setup: Create two projects with agents
        await orchestrator.db.register_project("proj_a", "/proj/a", "Project A")
        await orchestrator.db.register_project("proj_b", "/proj/b", "Project B")
        
        await orchestrator.db.register_agent("agent_a", "proj_a", dm_policy="open")
        await orchestrator.db.register_agent("agent_b", "proj_b", dm_policy="open")
        
        # Link the projects
        await orchestrator.db.add_project_link("proj_a", "proj_b", "bidirectional")
        
        context_a = ProjectContext(project_id="proj_a", project_path="/proj/a", project_name="Project A")
        
        # Agent A sends DM to Agent B (cross-project)
        result = await orchestrator.execute_tool(
            "send_direct_message",
            {
                "agent_id": "agent_a",
                "recipient_id": "agent_b",
                "content": "Cross-project message"
            },
            context=context_a
        )
        assert result["success"] == True
        
        # Agent A discovers Agent B
        result = await orchestrator.execute_tool(
            "list_agents",
            {
                "agent_id": "agent_a",
                "scope": "all"
            },
            context=context_a
        )
        assert result["success"] == True
        assert "agent_b" in result["content"]

    @pytest.mark.asyncio
    async def test_notes_workflow(self, orchestrator, test_agents, test_context):
        """Test complete notes workflow."""
        # Ensure database is initialized
        await orchestrator.db.initialize()
        
        # Write multiple notes with tags
        for i in range(3):
            result = await orchestrator.execute_tool(
                "write_note",
                {
                    "agent_id": "alice",
                    "content": f"Note {i}: Finding about component {i}",
                    "tags": ["component", f"v{i}"],
                    "session_context": "Testing session"
                },
                context=test_context
            )
            assert result["success"] == True
        
        # Search notes by content
        result = await orchestrator.execute_tool(
            "search_my_notes",
            {
                "agent_id": "alice",
                "query": "component"
            },
            context=test_context
        )
        assert result["success"] == True
        assert "Finding" in result["content"]
        
        # Get recent notes
        result = await orchestrator.execute_tool(
            "get_recent_notes",
            {
                "agent_id": "alice",
                "limit": 2
            },
            context=test_context
        )
        assert result["success"] == True
        
        # Bob peeks at Alice's notes
        result = await orchestrator.execute_tool(
            "peek_agent_notes",
            {
                "agent_id": "bob",
                "target_agent": "alice",
                "query": "Finding"
            },
            context=test_context  # Add context so alice can be found in proj_test
        )
        assert result["success"] == True
        assert "Notes from alice" in result["content"]