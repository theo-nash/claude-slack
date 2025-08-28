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
sys.path.insert(0, str(Path(__file__).parent.parent / "template" / "global" / "mcp" / "claude-slack"))

from db.manager import DatabaseManager
from channels.manager import ChannelManager
from notes.manager import NotesManager
from agents.manager import AgentManager
from utils.tool_orchestrator import MCPToolOrchestrator, ProjectContext
from config.sync_manager import ConfigSyncManager
from sessions.manager import SessionManager

# Mock logger for tests to avoid file system issues
import logging
logging.basicConfig(level=logging.CRITICAL)


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_db():
    """Provide a clean test database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(str(db_path))
        await db.initialize()
        yield db
        # Cleanup happens automatically when tmpdir is deleted


@pytest_asyncio.fixture
async def populated_db(test_db):
    """Provide a database with basic test data."""
    # Register projects
    await test_db.register_project("proj_test1", "/path/to/proj1", "Test Project 1")
    await test_db.register_project("proj_test2", "/path/to/proj2", "Test Project 2")
    
    # Register agents
    await test_db.register_agent(
        name="alice",
        project_id="proj_test1",
        description="Test agent Alice",
        dm_policy="open",
        discoverable="public"
    )
    
    await test_db.register_agent(
        name="bob",
        project_id="proj_test2",
        description="Test agent Bob",
        dm_policy="open",
        discoverable="public"
    )
    
    await test_db.register_agent(
        name="charlie",
        project_id=None,  # Global agent
        description="Global test agent Charlie",
        dm_policy="open",
        discoverable="public"
    )
    
    # Create some channels
    await test_db.create_channel(
        channel_id="global:general",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="general",
        description="General discussion"
    )
    
    await test_db.create_channel(
        channel_id="proj_test1:dev",
        channel_type="channel",
        access_type="open",
        scope="project",
        name="dev",
        project_id="proj_test1",
        description="Development discussion"
    )
    
    await test_db.create_channel(
        channel_id="proj_test1:private",
        channel_type="channel",
        access_type="members",
        scope="project",
        name="private",
        project_id="proj_test1",
        description="Private channel"
    )
    
    await test_db.create_channel(
        channel_id="proj_test2:dev",
        channel_type="channel", 
        access_type="open",
        scope="project",
        name="dev",
        project_id="proj_test2",
        description="Project 2 development"
    )
    
    yield test_db


# ============================================================================
# Manager Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def channel_manager(test_db):
    """Provide a ChannelManager instance with test database."""
    return ChannelManager(test_db.db_path)


@pytest_asyncio.fixture
async def notes_manager(test_db):
    """Provide a NotesManager instance with test database."""
    return NotesManager(test_db.db_path)


@pytest_asyncio.fixture
async def agent_manager(test_db):
    """Provide an AgentManager instance with test database."""
    return AgentManager(test_db.db_path)


@pytest_asyncio.fixture
async def session_manager(test_db):
    """Provide a SessionManager instance with test database."""
    return SessionManager(test_db.db_path)


@pytest_asyncio.fixture
async def tool_orchestrator(test_db, channel_manager, notes_manager, agent_manager):
    """Provide a MCPToolOrchestrator instance with all managers."""
    orchestrator = MCPToolOrchestrator(test_db.db_path)
    # The orchestrator initializes its own managers internally
    return orchestrator


@pytest_asyncio.fixture
async def config_sync_manager(test_db):
    """Provide a ConfigSyncManager instance."""
    return ConfigSyncManager(test_db.db_path)


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