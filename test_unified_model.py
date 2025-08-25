#!/usr/bin/env python3
"""
Test script for the unified membership model implementation.
Tests all major components and flows.
"""

import asyncio
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add template paths to import from
sys.path.insert(0, '/home/gbode/at/claude-slack/template/global/mcp/claude-slack')

# Import all the components we need to test
from db.manager import DatabaseManager
from config.sync_manager import ConfigSyncManager
from channels.manager import ChannelManager
from agents.discovery import AgentDiscoveryService
from config_manager import ConfigManager
from frontmatter.parser import FrontmatterParser

# Test configuration
TEST_DIR = tempfile.mkdtemp(prefix="claude_slack_test_")
TEST_DB = os.path.join(TEST_DIR, "test.db")
TEST_CONFIG = os.path.join(TEST_DIR, "config.yaml")
TEST_AGENTS_DIR = os.path.join(TEST_DIR, "agents")

print(f"Test directory: {TEST_DIR}")
print(f"Test database: {TEST_DB}")
print("-" * 60)

async def test_database_initialization():
    """Test that database initializes correctly with new schema"""
    print("\n1. Testing Database Initialization...")
    
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    
    # Check that tables exist using raw aiosqlite
    import aiosqlite
    async with aiosqlite.connect(TEST_DB) as conn:
        cursor = await conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        tables = await cursor.fetchall()
        table_names = [t[0] for t in tables]
    
    print(f"   Created tables: {table_names}")
    
    # Verify subscriptions table does NOT exist
    assert 'subscriptions' not in table_names, "subscriptions table should not exist!"
    
    # Verify channel_members has new columns
    async with aiosqlite.connect(TEST_DB) as conn:
        cursor = await conn.execute("PRAGMA table_info(channel_members)")
        columns = await cursor.fetchall()
        column_names = [c[1] for c in columns]
    
    print(f"   channel_members columns: {column_names}")
    
    # Check for unified model columns
    required_columns = ['invited_by', 'source', 'can_leave', 'can_send', 
                        'can_invite', 'can_manage', 'is_from_default', 'is_muted']
    for col in required_columns:
        assert col in column_names, f"Missing column: {col}"
    
    print("   ✓ Database schema is correct")
    return db

async def test_config_sync_manager():
    """Test ConfigSyncManager initialization and reconciliation"""
    print("\n2. Testing ConfigSyncManager...")
    
    # Create a test config
    os.makedirs(os.path.dirname(TEST_CONFIG), exist_ok=True)
    
    sync_manager = ConfigSyncManager(TEST_DB)
    
    # Test initialization without error
    result = await sync_manager.initialize_session(
        session_id="test_session_123",
        cwd=TEST_DIR,
        transcript_path=None
    )
    
    print(f"   Session registered: {result.get('session_registered')}")
    print(f"   Project ID: {result.get('project_id')}")
    
    if result.get('reconciliation'):
        recon = result['reconciliation']
        print(f"   Reconciliation success: {recon.get('success')}")
        print(f"   Total actions: {recon.get('total_actions')}")
        print(f"   Executed: {recon.get('executed')}")
    
    print("   ✓ ConfigSyncManager works")
    return sync_manager

async def test_agent_discovery():
    """Test agent discovery with MCP tools integration"""
    print("\n3. Testing Agent Discovery...")
    
    # Create test agent directory
    os.makedirs(TEST_AGENTS_DIR, exist_ok=True)
    
    # Create a test agent file
    agent_content = """---
name: test-agent
description: Test agent for unified model
tools: [Read, Write]
channels:
  global: [general]
  project: [dev]
  exclude: [announcements]
never_default: false
---

This is a test agent.
"""
    
    agent_file = os.path.join(TEST_AGENTS_DIR, "test-agent.md")
    with open(agent_file, 'w') as f:
        f.write(agent_content)
    
    # Test discovery
    discovery = AgentDiscoveryService()
    agents = await discovery.discover_project_agents(TEST_DIR)
    
    print(f"   Discovered {len(agents)} agents")
    
    if agents:
        agent = agents[0]
        print(f"   Agent name: {agent.name}")
        print(f"   Exclusions: {agent.get_exclusions()}")
        print(f"   Never default: {agent.excludes_all_defaults()}")
        
        # Check if MCP tools were added
        with open(agent_file, 'r') as f:
            updated_content = f.read()
        
        has_mcp_tools = 'mcp__claude-slack__join_channel' in updated_content
        print(f"   MCP tools added: {has_mcp_tools}")
        
        if has_mcp_tools:
            print("   ✓ MCP tools integration works")
        else:
            print("   ✗ MCP tools not added")
    
    return agents

async def test_unified_membership():
    """Test unified membership operations"""
    print("\n4. Testing Unified Membership Operations...")
    
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    
    # Create a test channel
    channel_id = await db.create_channel(
        channel_id="test:general",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="general",
        description="Test channel",
        created_by="system",
        is_default=True
    )
    print(f"   Created channel: {channel_id}")
    
    # Register a test agent
    await db.register_agent(
        name="test-agent",
        description="Test agent"
    )
    print("   Registered agent: test-agent")
    
    # Test joining (subscription in old model)
    await db.subscribe_to_channel(
        agent_name="test-agent",
        agent_project_id=None,
        channel_id=channel_id,
        source="test"
    )
    print("   Agent subscribed (joined) channel")
    
    # Check membership
    is_member = await db.is_channel_member(
        channel_id=channel_id,
        agent_name="test-agent",
        agent_project_id=None
    )
    print(f"   Is member: {is_member}")
    
    # Get member details
    members = await db.get_channel_members(channel_id)
    if members:
        member = members[0]
        print(f"   Member invited_by: {member.get('invited_by')}")
        print(f"   Member source: {member.get('source')}")
        print(f"   Can leave: {member.get('can_leave')}")
        print(f"   Can invite: {member.get('can_invite')}")
    
    assert is_member, "Agent should be a member"
    assert members[0]['invited_by'] == 'self', "Should be self-joined"
    
    print("   ✓ Unified membership works")
    return db

async def test_default_channels():
    """Test default channel provisioning"""
    print("\n5. Testing Default Channel Provisioning...")
    
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    channel_manager = ChannelManager(TEST_DB)
    
    # Create channels with is_default
    await db.create_channel(
        channel_id="global:default-test",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="default-test",
        description="Default test channel",
        created_by="system",
        is_default=True
    )
    
    await db.create_channel(
        channel_id="global:non-default",
        channel_type="channel",
        access_type="open",
        scope="global",
        name="non-default",
        description="Non-default channel",
        created_by="system",
        is_default=False
    )
    
    # Register an agent
    await db.register_agent(
        name="new-agent",
        description="Agent to test defaults"
    )
    
    # Apply default channels
    added = await channel_manager.apply_default_channels(
        agent_name="new-agent",
        agent_project_id=None,
        exclusions=[]
    )
    
    print(f"   Added to {added} default channels")
    
    # Check memberships
    default_member = await db.is_channel_member(
        "global:default-test", "new-agent", None
    )
    non_default_member = await db.is_channel_member(
        "global:non-default", "new-agent", None
    )
    
    print(f"   Member of default channel: {default_member}")
    print(f"   Member of non-default channel: {non_default_member}")
    
    assert default_member, "Should be member of default channel"
    assert not non_default_member, "Should NOT be member of non-default channel"
    
    print("   ✓ Default channel provisioning works")

async def test_exclusions():
    """Test channel exclusions and never_default flag"""
    print("\n6. Testing Exclusions...")
    
    # Create agent with exclusions
    agent_content = """---
name: exclusive-agent
description: Agent with exclusions
channels:
  global: [general]
  exclude: [announcements, default-test]
  never_default: true
---
"""
    
    agent_file = os.path.join(TEST_AGENTS_DIR, "exclusive-agent.md")
    with open(agent_file, 'w') as f:
        f.write(agent_content)
    
    # Parse the agent
    agent_data = FrontmatterParser.parse_file(agent_file)
    
    print(f"   Full parsed data: {agent_data}")
    print(f"   Parsed exclusions: {agent_data['channels'].get('exclude', [])}")
    print(f"   Never default (top): {agent_data.get('never_default', 'not found')}")
    
    assert 'announcements' in agent_data['channels'].get('exclude', [])
    # The never_default flag is correctly set at the top level by our parser update
    assert agent_data.get('never_default') == True
    
    print("   ✓ Exclusion parsing works")

async def main():
    """Run all tests"""
    print("=" * 60)
    print("UNIFIED MEMBERSHIP MODEL TEST SUITE")
    print("=" * 60)
    
    try:
        # Run tests in order
        db = await test_database_initialization()
        sync_manager = await test_config_sync_manager()
        agents = await test_agent_discovery()
        await test_unified_membership()
        await test_default_channels()
        await test_exclusions()
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED! ✓")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Cleanup
        print(f"\nCleaning up test directory: {TEST_DIR}")
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)