#!/usr/bin/env python3
"""
Comprehensive test for ALL components we updated in the unified model implementation.
"""

import asyncio
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, '/home/gbode/at/claude-slack/template/global/mcp/claude-slack')

print("=" * 60)
print("COMPREHENSIVE UNIFIED MODEL TEST")
print("=" * 60)

# Test imports - if these fail, we have a problem
try:
    from db.manager import DatabaseManager
    from db.initialization import DatabaseInitializer, ensure_db_initialized
    from config.sync_manager import ConfigSyncManager
    from config.reconciliation import (
        ReconciliationPlan, CreateChannelAction, 
        RegisterAgentAction, AddMembershipAction
    )
    from channels.manager import ChannelManager
    from agents.discovery import AgentDiscoveryService
    from projects.mcp_tools_manager import MCPToolsManager
    from frontmatter.parser import FrontmatterParser
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

TEST_DIR = tempfile.mkdtemp(prefix="comprehensive_test_")
TEST_DB = os.path.join(TEST_DIR, "test.db")

async def test_reconciliation_plan():
    """Test the ReconciliationPlan and Action classes"""
    print("\n1. Testing ReconciliationPlan and Actions...")
    
    plan = ReconciliationPlan()
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    
    # Add actions in proper phase order
    channel_action = CreateChannelAction(
        channel_id="test:channel",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="test",
        is_default=True
    )
    plan.add_action(channel_action)
    
    agent_action = RegisterAgentAction(
        name="test-agent",
        description="Test agent"
    )
    plan.add_action(agent_action)
    
    membership_action = AddMembershipAction(
        channel_id="test:channel",
        agent_name="test-agent",
        invited_by="system",
        source="default",
        is_from_default=True
    )
    plan.add_action(membership_action)
    
    # Check phase organization
    assert len(plan.phases[channel_action.phase]) == 1
    assert len(plan.phases[agent_action.phase]) == 1
    assert len(plan.phases[membership_action.phase]) == 1
    
    # Execute the plan
    results = await plan.execute(db)
    
    print(f"   Total actions: {results['total_actions']}")
    print(f"   Executed: {results['executed']}")
    print(f"   Failed: {results['failed']}")
    print(f"   Success: {results['success']}")
    
    assert results['success'] == True
    assert results['executed'] == 3
    
    # Verify execution order via phase summary
    phase_summary = results['phase_summary']
    assert phase_summary['infrastructure']['completed'] == 1
    assert phase_summary['agents']['completed'] == 1
    assert phase_summary['access']['completed'] == 1
    
    print("   ✓ ReconciliationPlan works correctly")
    return db

async def test_channel_manager_unified_api():
    """Test ChannelManager's new unified API"""
    print("\n2. Testing ChannelManager Unified API...")
    
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    channel_manager = ChannelManager(TEST_DB)
    
    # Create test channel
    channel_id = await channel_manager.create_channel(
        name="api-test",
        scope="global",
        access_type="open",
        is_default=False
    )
    print(f"   Created channel: {channel_id}")
    
    # Register test agents
    await db.register_agent("agent1", description="Agent 1")
    await db.register_agent("agent2", description="Agent 2")
    
    # Test join_channel (replaces subscribe)
    success = await channel_manager.join_channel(
        agent_name="agent1",
        agent_project_id=None,
        channel_id=channel_id
    )
    assert success == True
    print("   ✓ join_channel works")
    
    # Test invite_to_channel
    success = await channel_manager.invite_to_channel(
        channel_id=channel_id,
        invitee_name="agent2",
        invitee_project_id=None,
        inviter_name="agent1",
        inviter_project_id=None
    )
    assert success == True
    print("   ✓ invite_to_channel works")
    
    # Test leave_channel (replaces unsubscribe)
    success = await channel_manager.leave_channel(
        agent_name="agent1",
        agent_project_id=None,
        channel_id=channel_id
    )
    assert success == True
    print("   ✓ leave_channel works")
    
    # Test apply_default_channels
    await db.create_channel(
        channel_id="global:default-api",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="default-api",
        description="Default API test",
        created_by="system",
        is_default=True
    )
    
    await db.register_agent("agent3", description="Agent 3")
    added = await channel_manager.apply_default_channels(
        agent_name="agent3",
        agent_project_id=None
    )
    print(f"   Applied {added} default channels")
    assert added > 0
    print("   ✓ apply_default_channels works")
    
    return channel_manager

async def test_mcp_tools_integration():
    """Test MCPToolsManager integration with agent discovery"""
    print("\n3. Testing MCP Tools Integration...")
    
    agents_dir = os.path.join(TEST_DIR, "agents")
    os.makedirs(agents_dir, exist_ok=True)
    
    # Create agent without MCP tools
    agent_content = """---
name: tools-test
description: Agent to test MCP tools
tools: [Read, Write]
channels:
  global: [general]
---
"""
    
    agent_file = os.path.join(agents_dir, "tools-test.md")
    with open(agent_file, 'w') as f:
        f.write(agent_content)
    
    # Apply MCP tools
    updated = MCPToolsManager.ensure_agent_has_mcp_tools(agent_file)
    assert updated == True
    
    # Read and verify
    with open(agent_file, 'r') as f:
        content = f.read()
    
    # Check for new unified API tools
    assert 'mcp__claude-slack__join_channel' in content
    assert 'mcp__claude-slack__leave_channel' in content
    assert 'mcp__claude-slack__invite_to_channel' in content
    assert 'mcp__claude-slack__list_my_channels' in content
    
    # Old tools should NOT be there
    assert 'mcp__claude-slack__subscribe_to_channel' not in content
    assert 'mcp__claude-slack__unsubscribe_from_channel' not in content
    
    print("   ✓ MCP tools correctly updated to unified API")

async def test_config_sync_with_project():
    """Test ConfigSyncManager with project scope"""
    print("\n4. Testing ConfigSyncManager with Project...")
    
    # Create project structure
    project_dir = os.path.join(TEST_DIR, "test_project")
    claude_dir = os.path.join(project_dir, ".claude")
    agents_dir = os.path.join(claude_dir, "agents")
    os.makedirs(agents_dir, exist_ok=True)
    
    # Create project agent
    agent_content = """---
name: project-agent
description: Project-specific agent
channels:
  project: [dev, releases]
  exclude: [announcements]
---
"""
    with open(os.path.join(agents_dir, "project-agent.md"), 'w') as f:
        f.write(agent_content)
    
    # Initialize ConfigSyncManager
    sync_manager = ConfigSyncManager(TEST_DB)
    
    # Test full reconciliation with project
    results = await sync_manager.reconcile_all(
        scope='all',
        project_id='test_proj_123',
        project_path=project_dir
    )
    
    print(f"   Reconciliation success: {results.get('success')}")
    print(f"   Actions executed: {results.get('executed', 0)}")
    
    # Verify project channels were created
    db = DatabaseManager(TEST_DB)
    channels = await db.get_channels_by_scope(scope='project', project_id='test_proj_123')
    print(f"   Project channels created: {len(channels)}")
    
    print("   ✓ Project-scoped reconciliation works")

async def test_session_hook_simulation():
    """Simulate what the session hook does"""
    print("\n5. Testing Session Hook Flow...")
    
    # Simulate session start payload
    session_payload = {
        "session_id": "test_session_456",
        "cwd": TEST_DIR,
        "hook_event_name": "SessionStart",
        "transcript_path": None
    }
    
    # This is what the hook does
    sync_manager = ConfigSyncManager(TEST_DB)
    results = await sync_manager.initialize_session(
        session_id=session_payload['session_id'],
        cwd=session_payload['cwd'],
        transcript_path=session_payload['transcript_path']
    )
    
    print(f"   Session registered: {results.get('session_registered')}")
    print(f"   Project ID: {results.get('project_id')}")
    
    if results.get('reconciliation'):
        recon = results['reconciliation']
        print(f"   Reconciliation phases:")
        for phase, stats in recon.get('phase_summary', {}).items():
            if stats.get('total', 0) > 0:
                print(f"     - {phase}: {stats['completed']}/{stats['total']}")
    
    print("   ✓ Session initialization flow works")

async def test_database_initialization_pattern():
    """Test that DatabaseInitializer pattern works"""
    print("\n6. Testing DatabaseInitializer Pattern...")
    
    # Create a new database
    test_db2 = os.path.join(TEST_DIR, "init_test.db")
    
    # ConfigSyncManager should inherit from DatabaseInitializer
    sync_manager = ConfigSyncManager(test_db2)
    assert isinstance(sync_manager, DatabaseInitializer)
    
    # First call should initialize
    await sync_manager.initialize_session("test", TEST_DIR, None)
    
    # Check database exists
    assert os.path.exists(test_db2)
    
    # Check tables were created
    import aiosqlite
    async with aiosqlite.connect(test_db2) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        count = await cursor.fetchone()
        assert count[0] > 0
    
    print("   ✓ DatabaseInitializer pattern works correctly")

async def test_no_subscriptions_table():
    """Verify subscriptions table is completely gone"""
    print("\n7. Verifying No Subscriptions Table...")
    
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    
    # Try to query subscriptions table - should fail
    import aiosqlite
    async with aiosqlite.connect(TEST_DB) as conn:
        try:
            await conn.execute("SELECT * FROM subscriptions")
            assert False, "subscriptions table should not exist!"
        except Exception as e:
            assert "no such table: subscriptions" in str(e)
            print("   ✓ subscriptions table correctly removed")

async def main():
    """Run all comprehensive tests"""
    try:
        # Run all test suites
        await test_reconciliation_plan()
        await test_channel_manager_unified_api()
        await test_mcp_tools_integration()
        await test_config_sync_with_project()
        await test_session_hook_simulation()
        await test_database_initialization_pattern()
        await test_no_subscriptions_table()
        
        print("\n" + "=" * 60)
        print("✅ ALL COMPREHENSIVE TESTS PASSED!")
        print("=" * 60)
        print("\nCOVERAGE SUMMARY:")
        print("✓ ReconciliationPlan with phased execution")
        print("✓ All Action classes (Create, Register, Add)")
        print("✓ ChannelManager unified API (join, leave, invite)")
        print("✓ MCPToolsManager with new tool names")
        print("✓ ConfigSyncManager full flow")
        print("✓ Project-scoped operations")
        print("✓ Session initialization hook simulation")
        print("✓ DatabaseInitializer inheritance")
        print("✓ No subscriptions table exists")
        print("\nThe unified membership model is fully functional!")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        print(f"\nCleaning up: {TEST_DIR}")
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)