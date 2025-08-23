#!/usr/bin/env python3
"""
Tests for ChannelManagerV3
Tests the updated channel manager with access types and DM support
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
from channels.manager_v3 import ChannelManagerV3, ChannelType, AccessType

class TestChannelManagerV3:
    """Test ChannelManagerV3 functionality"""
    
    def __init__(self):
        self.test_dir = None
        self.db_path = None
        self.db = None
        self.channel_manager = None
    
    async def setup(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp(prefix='channel_manager_test_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Initialize database
        self.db = DatabaseManagerV3(self.db_path)
        await self.db.initialize()
        
        # Initialize channel manager
        self.channel_manager = ChannelManagerV3(self.db_path)
        await self.channel_manager.initialize()
        
        # Register test project first
        await self.db.register_project('proj_123', '/test/project', 'Test Project')
        
        # Register test agents
        await self.db.register_agent('alice', None, 'Alice Agent')
        await self.db.register_agent('bob', None, 'Bob Agent')
        await self.db.register_agent('charlie', 'proj_123', 'Charlie in Project')
        
        print(f"✅ Test environment created")
    
    async def teardown(self):
        """Clean up test environment"""
        if self.db:
            await self.db.close()
        
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        print("✅ Test environment cleaned up")
    
    async def test_create_channel_with_access_types(self):
        """Test creating channels with different access types"""
        print("\n🧪 Testing channel creation with access types...")
        
        # Create open channel
        open_id = await self.channel_manager.create_channel(
            name='open-channel',
            scope='global',
            access_type='open',
            description='Open for all',
            created_by='alice'
        )
        assert open_id == 'global:open-channel'
        print(f"  ✅ Created open channel: {open_id}")
        
        # Create members-only channel
        members_id = await self.channel_manager.create_channel(
            name='members-only',
            scope='global',
            access_type='members',
            description='Members only',
            created_by='alice'
        )
        assert members_id == 'global:members-only'
        print(f"  ✅ Created members channel: {members_id}")
        
        # Verify creator is added as owner for members channel
        members = await self.channel_manager.get_channel_members(members_id)
        assert len(members) == 1
        assert members[0]['agent_name'] == 'alice'
        assert members[0]['role'] == 'owner'
        print("  ✅ Creator added as owner for members channel")
        
        # Create private channel
        private_id = await self.channel_manager.create_channel(
            name='private-channel',
            scope='global',
            access_type='private',
            description='Private channel',
            created_by='bob'
        )
        assert private_id == 'global:private-channel'
        print(f"  ✅ Created private channel: {private_id}")
        
        return True
    
    async def test_create_dm_channel(self):
        """Test creating DM channels"""
        print("\n🧪 Testing DM channel creation...")
        
        # Create DM between alice and bob
        dm_id = await self.channel_manager.create_dm_channel(
            'alice', None, 'bob', None
        )
        expected_id = 'dm:alice::bob:'
        assert dm_id == expected_id
        print(f"  ✅ Created DM channel: {dm_id}")
        
        # Verify both are members
        members = await self.channel_manager.get_channel_members(dm_id)
        assert len(members) == 2
        member_names = {m['agent_name'] for m in members}
        assert 'alice' in member_names
        assert 'bob' in member_names
        print("  ✅ Both agents are members of DM")
        
        # Test idempotency
        dm_id2 = await self.channel_manager.create_dm_channel(
            'bob', None, 'alice', None  # Reversed order
        )
        assert dm_id == dm_id2
        print("  ✅ DM creation is idempotent")
        
        # Create cross-project DM
        cross_dm = await self.channel_manager.create_dm_channel(
            'alice', None, 'charlie', 'proj_123'
        )
        expected = 'dm:alice::charlie:proj_123'
        assert cross_dm == expected
        print(f"  ✅ Created cross-project DM: {cross_dm}")
        
        return True
    
    async def test_get_channel(self):
        """Test retrieving channel information"""
        print("\n🧪 Testing channel retrieval...")
        
        # Create a channel
        channel_id = await self.channel_manager.create_channel(
            name='test-retrieve',
            scope='global',
            access_type='members',
            description='Test channel for retrieval',
            created_by='alice'
        )
        
        # Retrieve it
        channel = await self.channel_manager.get_channel(channel_id)
        assert channel is not None
        assert channel.id == channel_id
        assert channel.channel_type == ChannelType.CHANNEL
        assert channel.access_type == AccessType.MEMBERS
        assert channel.name == 'test-retrieve'
        assert channel.description == 'Test channel for retrieval'
        print(f"  ✅ Retrieved channel: {channel.name}")
        
        # Try to get non-existent channel
        missing = await self.channel_manager.get_channel('global:nonexistent')
        assert missing is None
        print("  ✅ Returns None for non-existent channel")
        
        return True
    
    async def test_list_channels_for_agent(self):
        """Test listing channels accessible to an agent"""
        print("\n🧪 Testing channel listing for agents...")
        
        # Create various channels
        open_ch = await self.channel_manager.create_channel('list-open', 'global', 'open')
        members_ch = await self.channel_manager.create_channel('list-members', 'global', 'members', created_by='alice')
        private_ch = await self.channel_manager.create_channel('list-private', 'global', 'private')
        dm_ch = await self.channel_manager.create_dm_channel('alice', None, 'bob', None)
        
        # Subscribe alice to open channel
        await self.channel_manager.subscribe_to_channel('alice', None, open_ch)
        
        # List channels for alice
        alice_channels = await self.channel_manager.list_channels_for_agent('alice', None)
        channel_ids = [ch['id'] for ch in alice_channels]
        
        # Alice should see: open (subscribed), members (creator), DM (participant)
        assert open_ch in channel_ids, "Alice should see subscribed open channel"
        assert members_ch in channel_ids, "Alice should see channel she created"
        assert dm_ch in channel_ids, "Alice should see her DM"
        assert private_ch not in channel_ids, "Alice should not see unrelated private channel"
        
        print(f"  ✅ Alice sees {len(alice_channels)} channels correctly")
        
        # List channels for bob
        bob_channels = await self.channel_manager.list_channels_for_agent('bob', None)
        bob_channel_ids = [ch['id'] for ch in bob_channels]
        
        # Bob should only see the DM
        assert dm_ch in bob_channel_ids, "Bob should see his DM"
        assert open_ch not in bob_channel_ids, "Bob should not see unsubscribed open channel"
        assert members_ch not in bob_channel_ids, "Bob should not see members channel"
        
        print(f"  ✅ Bob sees {len(bob_channels)} channels correctly")
        
        return True
    
    async def test_channel_membership(self):
        """Test channel membership functions"""
        print("\n🧪 Testing channel membership...")
        
        # Create a members channel
        channel_id = await self.channel_manager.create_channel(
            name='membership-test',
            scope='global',
            access_type='members',
            created_by='alice'
        )
        
        # Check alice is a member (as creator)
        is_member = await self.channel_manager.is_channel_member(
            channel_id, 'alice', None
        )
        assert is_member
        print("  ✅ Creator is a member")
        
        # Check bob is not a member
        is_member = await self.channel_manager.is_channel_member(
            channel_id, 'bob', None
        )
        assert not is_member
        print("  ✅ Non-member correctly identified")
        
        # Add bob as member using DatabaseManager
        await self.db.add_channel_member(
            channel_id, 'bob', None, role='member'
        )
        
        # Now bob should be a member
        is_member = await self.channel_manager.is_channel_member(
            channel_id, 'bob', None
        )
        assert is_member
        print("  ✅ New member detected after adding")
        
        # Get all members
        members = await self.channel_manager.get_channel_members(channel_id)
        assert len(members) == 2
        roles = {m['agent_name']: m['role'] for m in members}
        assert roles['alice'] == 'owner'
        assert roles['bob'] == 'member'
        print("  ✅ Member list includes all members with correct roles")
        
        return True
    
    
    async def test_parse_channel_id(self):
        """Test channel ID parsing"""
        print("\n🧪 Testing channel ID parsing...")
        
        # Parse global channel
        parsed = ChannelManagerV3.parse_channel_id('global:general')
        assert parsed['type'] == 'channel'
        assert parsed['scope'] == 'global'
        assert parsed['name'] == 'general'
        print("  ✅ Parsed global channel ID")
        
        # Parse project channel
        parsed = ChannelManagerV3.parse_channel_id('proj_abc123:dev')
        assert parsed['type'] == 'channel'
        assert parsed['scope'] == 'project'
        assert parsed['name'] == 'dev'
        assert parsed['project_id_short'] == 'abc123'
        print("  ✅ Parsed project channel ID")
        
        # Parse DM channel
        parsed = ChannelManagerV3.parse_channel_id('dm:alice::bob:proj_123')
        assert parsed['type'] == 'direct'
        assert parsed['agent1_name'] == 'alice'
        assert parsed['agent1_project_id'] is None
        assert parsed['agent2_name'] == 'bob'
        assert parsed['agent2_project_id'] == 'proj_123'
        print("  ✅ Parsed DM channel ID")
        
        # Parse unknown format
        parsed = ChannelManagerV3.parse_channel_id('unknown:format')
        assert parsed['type'] == 'unknown'
        assert parsed['raw'] == 'unknown:format'
        print("  ✅ Handled unknown format")
        
        return True
    
    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("ChannelManagerV3 Tests")
        print("=" * 60)
        
        try:
            await self.setup()
            
            # Run tests
            results = []
            results.append(await self.test_create_channel_with_access_types())
            results.append(await self.test_create_dm_channel())
            results.append(await self.test_get_channel())
            results.append(await self.test_list_channels_for_agent())
            results.append(await self.test_channel_membership())
            results.append(await self.test_parse_channel_id())
            
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
    tester = TestChannelManagerV3()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    asyncio.run(main())