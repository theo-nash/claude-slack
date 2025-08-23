#!/usr/bin/env python3
"""
Core functionality tests for Phase 2 (v3.0.0) Permission System
Tests unified channels, access control, and DM as channels
"""

import asyncio
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'template', 'global', 'mcp', 'claude-slack'))

from db.manager_v3 import DatabaseManagerV3

class TestPhase2Core:
    """Test core Phase 2 functionality"""
    
    def __init__(self):
        self.test_dir = None
        self.db_path = None
        self.db = None
    
    async def setup(self):
        """Set up test environment"""
        # Create temporary directory for test database
        self.test_dir = tempfile.mkdtemp(prefix='claude_slack_test_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Initialize database
        self.db = DatabaseManagerV3(self.db_path)
        await self.db.initialize()
        
        print(f"✅ Test environment created at: {self.test_dir}")
    
    async def teardown(self):
        """Clean up test environment"""
        if self.db:
            await self.db.close()
        
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        print("✅ Test environment cleaned up")
    
    async def test_channel_creation_with_access_types(self):
        """Test creating channels with different access types"""
        print("\n🧪 Testing channel creation with access types...")
        
        # Register a test agent
        await self.db.register_agent('test-agent', None, 'Test Agent')
        
        # Test 1: Create open channel
        open_channel_id = 'global:test-open'
        await self.db.create_channel(
            channel_id=open_channel_id,
            channel_type='channel',
            access_type='open',
            scope='global',
            name='test-open',
            description='Open channel for testing',
            created_by='test-agent'
        )
        print("  ✅ Created open channel")
        
        # Test 2: Create members-only channel
        members_channel_id = 'global:test-members'
        await self.db.create_channel(
            channel_id=members_channel_id,
            channel_type='channel',
            access_type='members',
            scope='global',
            name='test-members',
            description='Members-only channel',
            created_by='test-agent'
        )
        print("  ✅ Created members-only channel")
        
        # Test 3: Create private channel
        private_channel_id = 'global:test-private'
        await self.db.create_channel(
            channel_id=private_channel_id,
            channel_type='channel',
            access_type='private',
            scope='global',
            name='test-private',
            description='Private channel',
            created_by='test-agent'
        )
        print("  ✅ Created private channel")
        
        return True
    
    async def test_dm_as_channels(self):
        """Test that DMs are created as private channels"""
        print("\n🧪 Testing DM as channels...")
        
        # Register two agents
        await self.db.register_agent('alice', None, 'Alice Agent')
        await self.db.register_agent('bob', None, 'Bob Agent')
        
        # Create DM channel between them
        dm_channel_id = await self.db.create_or_get_dm_channel(
            'alice', None, 'bob', None
        )
        
        expected_id = 'dm:alice::bob:'  # Since both are global agents
        assert dm_channel_id == expected_id, f"Expected {expected_id}, got {dm_channel_id}"
        print(f"  ✅ DM channel created with ID: {dm_channel_id}")
        
        # Verify both agents are members
        alice_channels = await self.db.get_agent_channels('alice', None)
        bob_channels = await self.db.get_agent_channels('bob', None)
        
        assert any(c['id'] == dm_channel_id for c in alice_channels), "Alice should have access to DM"
        assert any(c['id'] == dm_channel_id for c in bob_channels), "Bob should have access to DM"
        print("  ✅ Both agents have access to DM channel")
        
        # Test idempotency - creating again should return same channel
        dm_channel_id2 = await self.db.create_or_get_dm_channel(
            'bob', None, 'alice', None  # Note: reversed order
        )
        assert dm_channel_id == dm_channel_id2, "Should return same channel ID"
        print("  ✅ DM channel creation is idempotent")
        
        return True
    
    async def test_access_control(self):
        """Test that access control works properly"""
        print("\n🧪 Testing access control...")
        
        # Register agents
        await self.db.register_agent('member1', None, 'Member 1')
        await self.db.register_agent('member2', None, 'Member 2')
        await self.db.register_agent('outsider', None, 'Outsider')
        
        # Create a members-only channel
        channel_id = 'global:members-test'
        await self.db.create_channel(
            channel_id=channel_id,
            channel_type='channel',
            access_type='members',
            scope='global',
            name='members-test',
            created_by='member1'
        )
        
        # Add member1 and member2 to the channel
        await self.db.add_channel_member(channel_id, 'member1', None, role='owner')
        await self.db.add_channel_member(channel_id, 'member2', None, role='member')
        print("  ✅ Added members to channel")
        
        # Test: member1 and member2 should see the channel
        member1_channels = await self.db.get_agent_channels('member1', None)
        member2_channels = await self.db.get_agent_channels('member2', None)
        
        assert any(c['id'] == channel_id for c in member1_channels), "member1 should see channel"
        assert any(c['id'] == channel_id for c in member2_channels), "member2 should see channel"
        print("  ✅ Members can see the channel")
        
        # Test: outsider should NOT see the channel
        outsider_channels = await self.db.get_agent_channels('outsider', None)
        assert not any(c['id'] == channel_id for c in outsider_channels), "outsider should NOT see channel"
        print("  ✅ Non-members cannot see the channel")
        
        # Test: outsider cannot send messages to the channel
        try:
            await self.db.send_message(
                channel_id=channel_id,
                sender_id='outsider',
                sender_project_id=None,
                content='This should fail'
            )
            assert False, "Outsider should not be able to send messages"
        except ValueError as e:
            assert 'does not have access' in str(e)
            print("  ✅ Non-members cannot send messages")
        
        # Test: member can send messages
        message_id = await self.db.send_message(
            channel_id=channel_id,
            sender_id='member1',
            sender_project_id=None,
            content='Hello from member1'
        )
        assert message_id > 0
        print("  ✅ Members can send messages")
        
        return True
    
    async def test_permission_views(self):
        """Test that permission views work correctly"""
        print("\n🧪 Testing permission views...")
        
        # Register agents and create channels
        await self.db.register_agent('viewer', None, 'Viewer Agent')
        
        # Create different types of channels
        open_channel = 'global:view-open'
        members_channel = 'global:view-members'
        
        await self.db.create_channel(
            channel_id=open_channel,
            channel_type='channel',
            access_type='open',
            scope='global',
            name='view-open'
        )
        
        await self.db.create_channel(
            channel_id=members_channel,
            channel_type='channel',
            access_type='members',
            scope='global',
            name='view-members'
        )
        
        # Subscribe viewer to open channel
        await self.db.subscribe_to_channel('viewer', None, open_channel)
        
        # Add viewer as member to members channel
        await self.db.add_channel_member(members_channel, 'viewer', None)
        
        # Get channels through the view
        viewer_channels = await self.db.get_agent_channels('viewer', None)
        
        channel_ids = [c['id'] for c in viewer_channels]
        assert open_channel in channel_ids, "Should see subscribed open channel"
        assert members_channel in channel_ids, "Should see members channel"
        print(f"  ✅ Permission view returns correct channels: {channel_ids}")
        
        # Test unsubscribe
        await self.db.unsubscribe_from_channel('viewer', None, open_channel)
        viewer_channels = await self.db.get_agent_channels('viewer', None)
        channel_ids = [c['id'] for c in viewer_channels]
        
        assert open_channel not in channel_ids, "Should not see unsubscribed channel"
        assert members_channel in channel_ids, "Should still see members channel"
        print("  ✅ Unsubscribe removes access correctly")
        
        return True
    
    async def test_dm_permissions(self):
        """Test DM permission policies"""
        print("\n🧪 Testing DM permissions...")
        
        # Register agents with different policies
        await self.db.register_agent('open-agent', None, 'Open Agent', dm_policy='open')
        await self.db.register_agent('restricted-agent', None, 'Restricted Agent', dm_policy='restricted')
        await self.db.register_agent('closed-agent', None, 'Closed Agent', dm_policy='closed')
        await self.db.register_agent('normal-agent', None, 'Normal Agent', dm_policy='open')
        
        # Test 1: Open agent can receive DMs from anyone
        dm_channel = await self.db.create_or_get_dm_channel(
            'normal-agent', None, 'open-agent', None
        )
        assert dm_channel is not None
        print("  ✅ Open agent can receive DMs")
        
        # Test 2: Closed agent cannot receive DMs
        try:
            await self.db.create_or_get_dm_channel(
                'normal-agent', None, 'closed-agent', None
            )
            assert False, "Should not be able to DM closed agent"
        except ValueError as e:
            assert 'not allowed' in str(e)
            print("  ✅ Closed agent blocks all DMs")
        
        # Test 3: Restricted agent requires explicit permission
        try:
            await self.db.create_or_get_dm_channel(
                'normal-agent', None, 'restricted-agent', None
            )
            assert False, "Should not be able to DM restricted agent without permission"
        except ValueError as e:
            assert 'not allowed' in str(e)
            print("  ✅ Restricted agent blocks DMs without permission")
        
        # Add permission for normal-agent to DM restricted-agent
        await self.db.set_dm_permission(
            'restricted-agent', None,
            'normal-agent', None,
            'allow',
            'Testing allowed DM'
        )
        
        # Now it should work
        dm_channel = await self.db.create_or_get_dm_channel(
            'normal-agent', None, 'restricted-agent', None
        )
        assert dm_channel is not None
        print("  ✅ Restricted agent allows DMs with permission")
        
        # Test 4: Block specific agent
        await self.db.set_dm_permission(
            'open-agent', None,
            'normal-agent', None,
            'block',
            'Testing block'
        )
        
        try:
            await self.db.create_or_get_dm_channel(
                'normal-agent', None, 'open-agent', None
            )
            assert False, "Should be blocked"
        except ValueError as e:
            assert 'not allowed' in str(e)
            print("  ✅ Specific blocks work even for open agents")
        
        return True
    
    async def test_cross_project_channels(self):
        """Test channels across projects"""
        print("\n🧪 Testing cross-project channels...")
        
        # Register projects
        await self.db.register_project('proj_123', '/home/test/project1', 'Project 1')
        await self.db.register_project('proj_456', '/home/test/project2', 'Project 2')
        
        # Register agents in different projects
        await self.db.register_agent('alice', 'proj_123', 'Alice in Project 1')
        await self.db.register_agent('bob', 'proj_456', 'Bob in Project 2')
        await self.db.register_agent('charlie', None, 'Charlie Global')
        
        # Create a global channel
        global_channel = 'global:cross-project'
        await self.db.create_channel(
            channel_id=global_channel,
            channel_type='channel',
            access_type='members',
            scope='global',
            name='cross-project'
        )
        
        # Add all agents as members
        await self.db.add_channel_member(global_channel, 'alice', 'proj_123')
        await self.db.add_channel_member(global_channel, 'bob', 'proj_456')
        await self.db.add_channel_member(global_channel, 'charlie', None)
        
        # All should see the channel
        alice_channels = await self.db.get_agent_channels('alice', 'proj_123')
        bob_channels = await self.db.get_agent_channels('bob', 'proj_456')
        charlie_channels = await self.db.get_agent_channels('charlie', None)
        
        assert any(c['id'] == global_channel for c in alice_channels)
        assert any(c['id'] == global_channel for c in bob_channels)
        assert any(c['id'] == global_channel for c in charlie_channels)
        print("  ✅ Cross-project channel membership works")
        
        # Test cross-project DM
        dm_channel = await self.db.create_or_get_dm_channel(
            'alice', 'proj_123', 'bob', 'proj_456'
        )
        assert dm_channel is not None
        print(f"  ✅ Cross-project DM created: {dm_channel}")
        
        return True
    
    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("Phase 2 Core Functionality Tests")
        print("=" * 60)
        
        try:
            await self.setup()
            
            # Run tests
            results = []
            results.append(await self.test_channel_creation_with_access_types())
            results.append(await self.test_dm_as_channels())
            results.append(await self.test_access_control())
            results.append(await self.test_permission_views())
            results.append(await self.test_dm_permissions())
            results.append(await self.test_cross_project_channels())
            
            # Summary
            print("\n" + "=" * 60)
            print("Test Summary")
            print("=" * 60)
            
            total = len(results)
            passed = sum(1 for r in results if r)
            
            if passed == total:
                print(f"✅ All {total} tests passed!")
                return True
            else:
                print(f"❌ {passed}/{total} tests passed")
                return False
            
        finally:
            await self.teardown()

async def main():
    """Main test runner"""
    tester = TestPhase2Core()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    asyncio.run(main())