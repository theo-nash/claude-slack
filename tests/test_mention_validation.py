#!/usr/bin/env python3
"""
Tests for @mention validation functionality
Ensures mentioned agents can only be notified if they have access to the channel
"""

import asyncio
import os
import sys
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'template', 'global', 'mcp', 'claude-slack'))

from db.manager_v3 import DatabaseManagerV3

class TestMentionValidation:
    """Test mention validation functionality"""
    
    def __init__(self):
        self.test_dir = None
        self.db_path = None
        self.db = None
    
    async def setup(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp(prefix='mention_validation_test_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Initialize database
        self.db = DatabaseManagerV3(self.db_path)
        await self.db.initialize()
        
        # Create test projects
        await self.db.register_project('proj_alpha', '/projects/alpha', 'Alpha Project')
        await self.db.register_project('proj_beta', '/projects/beta', 'Beta Project')
        
        # Create test agents
        await self.db.register_agent('alice', None, 'Alice Global')
        await self.db.register_agent('bob', 'proj_alpha', 'Bob in Alpha')
        await self.db.register_agent('charlie', 'proj_beta', 'Charlie in Beta')
        await self.db.register_agent('diana', None, 'Diana Global')
        
        # Create test channels
        # Open channel - anyone can subscribe
        await self.db.create_channel(
            channel_id='global:open-discussion',
            channel_type='channel',
            access_type='open',
            scope='global',
            name='open-discussion',
            description='Open discussion channel'
        )
        
        # Members-only channel with alice as creator
        await self.db.create_channel(
            channel_id='proj_alpha:team-alpha',
            channel_type='channel',
            access_type='members',
            scope='project',
            name='team-alpha',
            project_id='proj_alpha',
            description='Alpha team channel',
            created_by='alice',
            created_by_project_id=None
        )
        # For members-only channels, we need to explicitly add members
        # Alice as owner (creator)
        await self.db.add_channel_member('proj_alpha:team-alpha', 'alice', None, role='owner')
        # Bob as member
        await self.db.add_channel_member('proj_alpha:team-alpha', 'bob', 'proj_alpha', role='member')
        
        # Subscribe agents to open channel
        await self.db.subscribe_to_channel('alice', None, 'global:open-discussion')
        await self.db.subscribe_to_channel('diana', None, 'global:open-discussion')
        
        print(f"✅ Test environment created with 4 agents and 2 channels")
    
    async def teardown(self):
        """Clean up test environment"""
        if self.db:
            await self.db.close()
        
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        print("✅ Test environment cleaned up")
    
    async def test_single_mention_validation(self):
        """Test checking if a single agent can access a channel"""
        print("\n🧪 Testing single mention validation...")
        
        # Alice can access open-discussion (subscribed)
        can_access = await self.db.check_agent_can_access_channel(
            'alice', None, 'global:open-discussion'
        )
        assert can_access, "Alice should access open-discussion"
        print("  ✅ Subscribed agent can access open channel")
        
        # Bob cannot access open-discussion (not subscribed)
        can_access = await self.db.check_agent_can_access_channel(
            'bob', 'proj_alpha', 'global:open-discussion'
        )
        assert not can_access, "Bob should not access open-discussion"
        print("  ✅ Non-subscribed agent cannot access open channel")
        
        # Bob can access team-alpha (member)
        can_access = await self.db.check_agent_can_access_channel(
            'bob', 'proj_alpha', 'proj_alpha:team-alpha'
        )
        assert can_access, "Bob should access team-alpha"
        print("  ✅ Member can access members-only channel")
        
        # Charlie cannot access team-alpha (not a member)
        can_access = await self.db.check_agent_can_access_channel(
            'charlie', 'proj_beta', 'proj_alpha:team-alpha'
        )
        assert not can_access, "Charlie should not access team-alpha"
        print("  ✅ Non-member cannot access members-only channel")
        
        return True
    
    async def test_batch_mention_validation(self):
        """Test validating multiple mentions at once"""
        print("\n🧪 Testing batch mention validation...")
        
        # Test mentions in open-discussion channel
        mentions = [
            {'name': 'alice', 'project_id': None},      # Valid - subscribed
            {'name': 'bob', 'project_id': 'proj_alpha'}, # Invalid - not subscribed
            {'name': 'diana', 'project_id': None},      # Valid - subscribed
            {'name': 'eve', 'project_id': None},        # Unknown - doesn't exist
        ]
        
        result = await self.db.validate_mentions_batch(
            'global:open-discussion', mentions
        )
        
        # Check results
        valid_names = [m['name'] for m in result['valid']]
        invalid_names = [m['name'] for m in result['invalid']]
        unknown_names = [m['name'] for m in result['unknown']]
        
        assert 'alice' in valid_names, "Alice should be valid"
        assert 'diana' in valid_names, "Diana should be valid"
        assert 'bob' in invalid_names, "Bob should be invalid"
        assert 'eve' in unknown_names, "Eve should be unknown"
        
        print(f"  ✅ Batch validation: {len(result['valid'])} valid, "
              f"{len(result['invalid'])} invalid, {len(result['unknown'])} unknown")
        
        # Test mentions in team-alpha channel
        mentions = [
            {'name': 'alice', 'project_id': None},       # Valid - creator/owner
            {'name': 'bob', 'project_id': 'proj_alpha'}, # Valid - member
            {'name': 'charlie', 'project_id': 'proj_beta'}, # Invalid - not member
            {'name': 'diana', 'project_id': None},       # Invalid - not member
        ]
        
        result = await self.db.validate_mentions_batch(
            'proj_alpha:team-alpha', mentions
        )
        
        valid_names = [m['name'] for m in result['valid']]
        invalid_names = [m['name'] for m in result['invalid']]
        
        # Debug output if test fails
        if 'alice' not in valid_names:
            print(f"    Debug: Valid names: {valid_names}")
            print(f"    Debug: Invalid names: {invalid_names}")
            # Check if alice is actually a member
            is_member = await self.db.check_agent_can_access_channel(
                'alice', None, 'proj_alpha:team-alpha'
            )
            print(f"    Debug: Alice is member? {is_member}")
        
        assert 'alice' in valid_names, "Alice should be valid in team-alpha (creator)"
        assert 'bob' in valid_names, "Bob should be valid in team-alpha (member)"
        assert 'charlie' in invalid_names, "Charlie should be invalid"
        assert 'diana' in invalid_names, "Diana should be invalid"
        
        print(f"  ✅ Members-only validation: {len(result['valid'])} valid, "
              f"{len(result['invalid'])} invalid")
        
        return True
    
    async def test_dm_channel_mentions(self):
        """Test mention validation in DM channels"""
        print("\n🧪 Testing DM channel mention validation...")
        
        # Create DM between alice and bob
        dm_id = await self.db.create_or_get_dm_channel(
            'alice', None, 'bob', 'proj_alpha'
        )
        
        # Only alice and bob should be able to access this DM
        mentions = [
            {'name': 'alice', 'project_id': None},       # Valid - participant
            {'name': 'bob', 'project_id': 'proj_alpha'}, # Valid - participant
            {'name': 'charlie', 'project_id': 'proj_beta'}, # Invalid - not participant
            {'name': 'diana', 'project_id': None},       # Invalid - not participant
        ]
        
        result = await self.db.validate_mentions_batch(dm_id, mentions)
        
        valid_names = [m['name'] for m in result['valid']]
        invalid_names = [m['name'] for m in result['invalid']]
        
        assert len(result['valid']) == 2, "Only 2 agents should be valid in DM"
        assert 'alice' in valid_names, "Alice should be valid in DM"
        assert 'bob' in valid_names, "Bob should be valid in DM"
        assert 'charlie' in invalid_names, "Charlie should be invalid in DM"
        assert 'diana' in invalid_names, "Diana should be invalid in DM"
        
        print("  ✅ DM mentions correctly validated - only participants can be mentioned")
        
        return True
    
    async def test_empty_mentions(self):
        """Test handling empty mention list"""
        print("\n🧪 Testing empty mention list...")
        
        result = await self.db.validate_mentions_batch(
            'global:open-discussion', []
        )
        
        assert result == {'valid': [], 'invalid': [], 'unknown': []}
        print("  ✅ Empty mention list handled correctly")
        
        return True
    
    async def test_performance_with_many_mentions(self):
        """Test performance with many mentions"""
        print("\n🧪 Testing performance with many mentions...")
        
        # Create many test agents
        for i in range(20):
            await self.db.register_agent(f'test_{i}', None, f'Test Agent {i}')
            if i % 2 == 0:  # Subscribe every other agent
                await self.db.subscribe_to_channel(f'test_{i}', None, 'global:open-discussion')
        
        # Create mention list
        mentions = []
        for i in range(20):
            mentions.append({'name': f'test_{i}', 'project_id': None})
        # Add some unknown agents
        for i in range(20, 25):
            mentions.append({'name': f'unknown_{i}', 'project_id': None})
        
        import time
        start = time.time()
        result = await self.db.validate_mentions_batch(
            'global:open-discussion', mentions
        )
        elapsed = time.time() - start
        
        assert len(result['valid']) == 10, "Should have 10 valid (subscribed)"
        assert len(result['invalid']) == 10, "Should have 10 invalid (not subscribed)"
        assert len(result['unknown']) == 5, "Should have 5 unknown"
        
        print(f"  ✅ Validated {len(mentions)} mentions in {elapsed:.3f}s")
        print(f"     {len(result['valid'])} valid, {len(result['invalid'])} invalid, "
              f"{len(result['unknown'])} unknown")
        
        return True
    
    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("Mention Validation Tests")
        print("=" * 60)
        
        try:
            await self.setup()
            
            # Run tests
            results = []
            results.append(await self.test_single_mention_validation())
            results.append(await self.test_batch_mention_validation())
            results.append(await self.test_dm_channel_mentions())
            results.append(await self.test_empty_mentions())
            results.append(await self.test_performance_with_many_mentions())
            
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
    tester = TestMentionValidation()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    asyncio.run(main())