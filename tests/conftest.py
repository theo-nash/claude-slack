"""
Shared pytest fixtures for claude-slack tests.
Provides common test infrastructure for all test suites.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Load environment variables for testing (without hardcoding paths)
try:
    from dotenv import load_dotenv
    # Search for .env in common locations
    for env_path in [
        Path.cwd() / '.env',
        Path.cwd().parent / '.env', 
        Path.cwd().parent.parent / '.env',
        Path.home() / '.env',
    ]:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    # dotenv not installed, use system environment only
    pass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add template path for other imports but after parent so API takes precedence
sys.path.insert(1, str(Path(__file__).parent.parent / "template" / "global" / "mcp" / "claude-slack"))

# NEW: Import the unified API instead of individual managers
from api.unified_api import ClaudeSlackAPI

# Still need these for some tests
from agents.manager import AgentManager
from utils.tool_orchestrator import MCPToolOrchestrator, ProjectContext
from config.sync_manager import ConfigSyncManager
from sessions.manager import SessionManager

# Mock logger for tests to avoid file system issues
import logging
logging.basicConfig(level=logging.CRITICAL)


# ============================================================================
# NEW API Fixtures (Primary)
# ============================================================================

@pytest_asyncio.fixture
async def api():
    """Provide ClaudeSlackAPI instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        # Disable semantic search for old tests - they don't need Qdrant
        api_instance = ClaudeSlackAPI(
            db_path=str(db_path),
            enable_semantic_search=False  # Old tests don't need Qdrant
        )
        await api_instance.initialize()
        yield api_instance
        await api_instance.close()


# ============================================================================
# Compatibility Shims for Gradual Migration
# ============================================================================

@pytest_asyncio.fixture
async def test_db(api):
    """
    Legacy fixture - returns the full API for compatibility.
    Tests should use the high-level API methods.
    """
    return api


@pytest_asyncio.fixture
async def populated_db(api):
    """Provide a database with basic test data using the API."""
    # Get the SQLite store for direct database operations
    db = api.db.sqlite
    
    # Register projects using the SQLite store directly (old tests expect this)
    await db.register_project("proj_test1", "/path/to/proj1", "Test Project 1")
    await db.register_project("proj_test2", "/path/to/proj2", "Test Project 2")
    
    # Register agents
    await db.register_agent(
        name="alice",
        project_id="proj_test1",
        description="Test agent Alice",
        dm_policy="open",
        discoverable="public"
    )
    
    await db.register_agent(
        name="bob",
        project_id="proj_test2",
        description="Test agent Bob",
        dm_policy="open",
        discoverable="public"
    )
    
    await db.register_agent(
        name="charlie",
        project_id=None,  # Global agent
        description="Global test agent Charlie",
        dm_policy="open",
        discoverable="public"
    )
    
    # Create some channels
    await db.create_channel(
        channel_id="global:general",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="general",
        description="General discussion"
    )
    
    await db.create_channel(
        channel_id="proj_test1:dev",
        channel_type="channel",
        access_type="open",
        scope="project",
        name="dev",
        project_id="proj_test1",
        description="Development discussion"
    )
    
    await db.create_channel(
        channel_id="proj_test1:private",
        channel_type="channel",
        access_type="members",
        scope="project",
        name="private",
        project_id="proj_test1",
        description="Private channel"
    )
    
    await db.create_channel(
        channel_id="proj_test2:dev",
        channel_type="channel", 
        access_type="open",
        scope="project",
        name="dev",
        project_id="proj_test2",
        description="Project 2 development"
    )
    
    # Return the SQLite store for old tests that expect it
    yield db


# ============================================================================
# Manager Fixtures (Compatibility Shims)
# ============================================================================

@pytest_asyncio.fixture
async def channel_manager(api):
    """
    Legacy fixture - returns a compatibility wrapper for channel operations.
    Since join_channel and leave_channel are now on the API itself,
    we create a wrapper that forwards these calls.
    """
    class ChannelManagerWrapper:
        def __init__(self, api):
            self.api = api
            self.channels = api.channels  # For any direct channel manager calls
            
        async def join_channel(self, agent_name, agent_project_id, channel_id):
            return await self.api.join_channel(agent_name, agent_project_id, channel_id)
        
        async def leave_channel(self, agent_name, agent_project_id, channel_id):
            return await self.api.leave_channel(agent_name, agent_project_id, channel_id)
        
        async def create_dm_channel(self, agent1_name, agent1_project_id, 
                                  agent2_name, agent2_project_id):
            # Create a DM channel using the MessageStore (which forwards to SQLite)
            return await self.api.db.create_or_get_dm_channel(
                agent1_name, agent1_project_id, agent2_name, agent2_project_id
            )
        
        async def invite_to_channel(self, channel_id, inviting_agent_name=None, 
                                   inviting_project_id=None, invited_agent_name=None, 
                                   invited_project_id=None, 
                                   # Alternative parameter names used by some tests
                                   inviter_name=None, inviter_project_id=None,
                                   invitee_name=None, invitee_project_id=None):
            # Handle both parameter naming conventions
            inviter = inviting_agent_name or inviter_name
            inviter_proj = inviting_project_id or inviter_project_id
            invitee = invited_agent_name or invitee_name
            invitee_proj = invited_project_id or invitee_project_id
            
            # Check if channel is open (can't invite to open channels)
            channel = await self.api.db.sqlite.get_channel(channel_id)
            if channel and channel.get('access_type') == 'open':
                return False  # Can't invite to open channels
            
            # Use SQLite store for invite operations
            return await self.api.db.sqlite.add_channel_member(
                channel_id, invitee, invitee_proj,
                invited_by=inviter, source='invite',
                can_leave=True, can_send=True
            )
    
    return ChannelManagerWrapper(api)


@pytest_asyncio.fixture
async def notes_manager(api):
    """
    Legacy fixture - returns API's notes manager for compatibility.
    """
    return api.notes


@pytest_asyncio.fixture
async def agent_manager(api):
    """Provide an AgentManager instance with test database."""
    # AgentManager still exists in template, needs db_path
    return AgentManager(api.db.sqlite.db_path)


@pytest_asyncio.fixture
async def session_manager(api):
    """Provide a SessionManager instance with API."""
    # SessionManager now takes API instance
    return SessionManager(api)


@pytest_asyncio.fixture
async def tool_orchestrator(api):
    """
    Provide a MCPToolOrchestrator instance with API.
    The new orchestrator takes an API instance, not a db_path.
    """
    return MCPToolOrchestrator(api)


@pytest_asyncio.fixture
async def config_sync_manager(api):
    """Provide a ConfigSyncManager instance with API."""
    # ConfigSyncManager now uses the API
    return ConfigSyncManager(api)


# ============================================================================
# Project Context Fixtures
# ============================================================================

@pytest.fixture
def project_context():
    """Provide a test ProjectContext."""
    return ProjectContext(
        project_id="proj_test1",
        project_path="/path/to/proj1",
        project_name="Test Project 1"
    )


@pytest.fixture
def global_context():
    """Provide a global (no project) context."""
    return ProjectContext(
        project_id=None,
        project_path=None,
        project_name=None
    )


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_agents():
    """Provide sample agent data for testing."""
    return [
        {
            "name": "alice",
            "project_id": "proj_test1",
            "description": "Frontend developer",
            "dm_policy": "open",
            "discoverable": "public"
        },
        {
            "name": "bob",
            "project_id": "proj_test2",
            "description": "Backend developer",
            "dm_policy": "restricted",
            "discoverable": "project"
        },
        {
            "name": "charlie",
            "project_id": None,
            "description": "DevOps engineer",
            "dm_policy": "open",
            "discoverable": "public"
        }
    ]


@pytest.fixture
def sample_channels():
    """Provide sample channel configurations."""
    return [
        {
            "id": "global:general",
            "name": "general",
            "scope": "global",
            "access_type": "open",
            "description": "General discussion"
        },
        {
            "id": "global:announcements",
            "name": "announcements",
            "scope": "global",
            "access_type": "members",
            "description": "Official announcements",
            "is_default": True
        },
        {
            "id": "proj_test1:dev",
            "name": "dev",
            "scope": "project",
            "project_id": "proj_test1",
            "access_type": "open",
            "description": "Development discussion"
        }
    ]


# ============================================================================
# Async Test Support
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def linked_projects(test_db):
    """Create two linked projects for testing cross-project access."""
    await test_db.register_project("proj_a", "/path/to/proj_a", "Project A")
    await test_db.register_project("proj_b", "/path/to/proj_b", "Project B")
    await test_db.add_project_link("proj_a", "proj_b", "bidirectional")
    return ("proj_a", "proj_b")


@pytest.fixture
def mock_mcp_args():
    """Provide mock MCP tool arguments for testing."""
    def _make_args(**kwargs):
        base_args = {
            "agent_id": "test-agent",
            "scope": "all",
            "include_archived": False
        }
        base_args.update(kwargs)
        return base_args
    return _make_args


# ============================================================================
# Cleanup Utilities
# ============================================================================

@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_files():
    """Automatically cleanup any test files created during tests."""
    yield
    # Cleanup test artifacts if needed
    test_artifacts = Path("/tmp/claude-slack-test-*")
    for artifact in test_artifacts.parent.glob(test_artifacts.name):
        if artifact.is_dir():
            import shutil
            shutil.rmtree(artifact)
        elif artifact.is_file():
            artifact.unlink()