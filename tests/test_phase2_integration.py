#!/usr/bin/env python3
"""
Integration tests for Phase 2 (v3.0.0) Permission System
Tests cross-project DMs, membership management, message routing, and DM policies
"""

import asyncio
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'template', 'global', 'mcp', 'claude-slack'))

from db.manager_v3 import DatabaseManagerV3

class TestPhase2Integration:
    """Test Phase 2 integration scenarios"""
    
    def __init__(self):
        self.test_dir = None
        self.db_path = None
        self.db = None
    
    async def setup(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp(prefix='claude_slack_integration_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        self.db = DatabaseManagerV3(self.db_path)
        await self.db.initialize()
        
        # Set up test projects and agents
        await self._setup_test_environment()
        
        print(f"✅ Integration test environment created")
    
    async def _setup_test_environment(self):
        """Create test projects and agents"""
        # Create projects
        await self.db.register_project('proj_web', '/projects/web', 'Web Project')
        await self.db.register_project('proj_api', '/projects/api', 'API Project')
        await self.db.register_project('proj_ml', '/projects/ml', 'ML Project')
        
        # Create agents with various configurations
        # Global agents
        await self.db.register_agent('coordinator', None, 'Global Coordinator', dm_policy='open')
        await self.db.register_agent('admin', None, 'Admin Agent', dm_policy='open')
        
        # Project agents
        await self.db.register_agent('frontend-dev', 'proj_web', 'Frontend Developer', dm_policy='open')
        await self.db.register_agent('backend-dev', 'proj_api', 'Backend Developer', dm_policy='restricted')
        await self.db.register_agent('ml-engineer', 'proj_ml', 'ML Engineer', dm_policy='open')
        await self.db.register_agent('data-scientist', 'proj_ml', 'Data Scientist', dm_policy='closed')
    
    async def teardown(self):
        """Clean up test environment"""
        if self.db:
            await self.db.close()
        
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        print("✅ Integration test environment cleaned up")
    
    async def test_cross_project_dm_workflow(self):
        """Test complete DM workflow across projects"""
        print("\n🧪 Testing cross-project DM workflow...")
        
        # Frontend dev wants to DM backend dev
        # Backend dev has restricted policy, so needs permission first
        
        # Initially should fail
        try:
            await self.db.create_or_get_dm_channel(
                'frontend-dev', 'proj_web',
                'backend-dev', 'proj_api'
            )
            assert False, "Should not be able to DM restricted agent"
        except ValueError:
            print("  ✅ Restricted agent blocks initial DM attempt")
        
        # Backend dev allows frontend dev
        await self.db.set_dm_permission(
            'backend-dev', 'proj_api',
            'frontend-dev', 'proj_web',
            'allow',
            'Collaborating on API integration'
        )
        
        # Now create DM channel
        dm_channel = await self.db.create_or_get_dm_channel(
            'frontend-dev', 'proj_web',
            'backend-dev', 'proj_api'
        )
        print(f"  ✅ DM channel created after permission: {dm_channel}")
        
        # Send messages back and forth
        msg1 = await self.db.send_message(
            channel_id=dm_channel,
            sender_id='frontend-dev',
            sender_project_id='proj_web',
            content='Hey, need help with the API endpoint'
        )
        
        msg2 = await self.db.send_message(
            channel_id=dm_channel,
            sender_id='backend-dev',
            sender_project_id='proj_api',
            content='Sure, what endpoint are you working with?'
        )
        
        print(f"  ✅ Messages exchanged: {msg1}, {msg2}")
        
        # Both should see the messages
        frontend_messages = await self.db.get_messages(
            'frontend-dev', 'proj_web', channel_id=dm_channel
        )
        backend_messages = await self.db.get_messages(
            'backend-dev', 'proj_api', channel_id=dm_channel
        )
        
        assert len(frontend_messages) == 2
        assert len(backend_messages) == 2
        print("  ✅ Both agents can see all messages in DM")
        
        return True
    
    async def test_channel_membership_lifecycle(self):
        """Test adding/removing members and access changes"""
        print("\n🧪 Testing channel membership lifecycle...")
        
        # Create a members-only channel
        channel_id = 'global:team-channel'
        await self.db.create_channel(
            channel_id=channel_id,
            channel_type='channel',
            access_type='members',
            scope='global',
            name='team-channel',
            created_by='coordinator'
        )
        
        # Add coordinator as owner
        await self.db.add_channel_member(
            channel_id, 'coordinator', None,
            role='owner', can_manage_members=True
        )
        
        # Coordinator adds frontend-dev
        await self.db.add_channel_member(
            channel_id, 'frontend-dev', 'proj_web',
            role='member', added_by='coordinator'
        )
        print("  ✅ Added frontend-dev to channel")
        
        # Frontend-dev can now send messages
        msg_id = await self.db.send_message(
            channel_id=channel_id,
            sender_id='frontend-dev',
            sender_project_id='proj_web',
            content='Hello team!'
        )
        assert msg_id > 0
        print("  ✅ New member can send messages")
        
        # ML engineer cannot see or send to channel
        ml_channels = await self.db.get_agent_channels('ml-engineer', 'proj_ml')
        assert not any(c['id'] == channel_id for c in ml_channels)
        print("  ✅ Non-members cannot see channel")
        
        # Add ML engineer
        await self.db.add_channel_member(
            channel_id, 'ml-engineer', 'proj_ml',
            role='member', added_by='coordinator'
        )
        
        # Now ML engineer can see it
        ml_channels = await self.db.get_agent_channels('ml-engineer', 'proj_ml')
        assert any(c['id'] == channel_id for c in ml_channels)
        print("  ✅ New member can see channel after being added")
        
        # Remove frontend-dev
        await self.db.remove_channel_member(
            channel_id, 'frontend-dev', 'proj_web'
        )
        
        # Frontend-dev can no longer see or send
        frontend_channels = await self.db.get_agent_channels('frontend-dev', 'proj_web')
        assert not any(c['id'] == channel_id for c in frontend_channels)
        
        try:
            await self.db.send_message(
                channel_id=channel_id,
                sender_id='frontend-dev',
                sender_project_id='proj_web',
                content='This should fail'
            )
            assert False, "Removed member should not send messages"
        except ValueError:
            print("  ✅ Removed member loses access")
        
        return True
    
    async def test_message_routing_isolation(self):
        """Test that messages only reach authorized recipients"""
        print("\n🧪 Testing message routing isolation...")
        
        # Create a fresh test agent to avoid contamination from previous tests
        await self.db.register_agent('test-viewer', 'proj_web', 'Test Viewer', dm_policy='open')
        
        # Create two separate channels
        public_channel = 'global:public-discuss'
        private_channel = 'global:private-team'
        
        await self.db.create_channel(
            channel_id=public_channel,
            channel_type='channel',
            access_type='open',
            scope='global',
            name='public-discuss'
        )
        
        await self.db.create_channel(
            channel_id=private_channel,
            channel_type='channel',
            access_type='private',
            scope='global',
            name='private-team'
        )
        
        # Subscribe some agents to public
        await self.db.subscribe_to_channel('coordinator', None, public_channel)
        await self.db.subscribe_to_channel('test-viewer', 'proj_web', public_channel)
        await self.db.subscribe_to_channel('ml-engineer', 'proj_ml', public_channel)
        
        # Add only coordinator and admin to private
        await self.db.add_channel_member(private_channel, 'coordinator', None)
        await self.db.add_channel_member(private_channel, 'admin', None)
        
        # Send messages to both channels
        await self.db.send_message(
            channel_id=public_channel,
            sender_id='coordinator',
            sender_project_id=None,
            content='Public announcement'
        )
        
        await self.db.send_message(
            channel_id=private_channel,
            sender_id='admin',
            sender_project_id=None,
            content='Private discussion'
        )
        
        # Check message visibility
        # Test-viewer should only see public message
        viewer_messages = await self.db.get_messages('test-viewer', 'proj_web')
        assert len(viewer_messages) == 1, f"Expected 1 message, got {len(viewer_messages)}"
        assert viewer_messages[0]['content'] == 'Public announcement'
        print("  ✅ Non-member only sees public messages")
        
        # Coordinator should see both channel messages (may have more from other tests)
        coord_messages = await self.db.get_messages('coordinator', None)
        coord_contents = [m['content'] for m in coord_messages]
        assert 'Public announcement' in coord_contents
        assert 'Private discussion' in coord_contents
        print("  ✅ Member sees both public and private messages")
        
        # ML engineer should only see public (from this test)
        ml_messages = await self.db.get_messages('ml-engineer', 'proj_ml', channel_id=public_channel)
        assert len(ml_messages) == 1
        assert ml_messages[0]['content'] == 'Public announcement'
        print("  ✅ Message isolation working correctly")
        
        return True
    
    async def test_dm_policy_enforcement(self):
        """Test comprehensive DM policy scenarios"""
        print("\n🧪 Testing DM policy enforcement...")
        
        # Scenario 1: Open agent accepts all DMs
        dm1 = await self.db.create_or_get_dm_channel(
            'admin', None, 'ml-engineer', 'proj_ml'
        )
        assert dm1 is not None
        print("  ✅ Open policy accepts DMs")
        
        # Scenario 2: Closed agent rejects all DMs
        try:
            await self.db.create_or_get_dm_channel(
                'ml-engineer', 'proj_ml',
                'data-scientist', 'proj_ml'
            )
            assert False, "Closed agent should reject"
        except ValueError:
            print("  ✅ Closed policy rejects all DMs")
        
        # Scenario 3: Update policy dynamically
        await self.db.update_dm_policy('data-scientist', 'proj_ml', 'restricted')
        
        # Add specific allowance
        await self.db.set_dm_permission(
            'data-scientist', 'proj_ml',
            'ml-engineer', 'proj_ml',
            'allow',
            'Same team collaboration'
        )
        
        # Now DM should work
        dm2 = await self.db.create_or_get_dm_channel(
            'ml-engineer', 'proj_ml',
            'data-scientist', 'proj_ml'
        )
        assert dm2 is not None
        print("  ✅ Policy update and allowlist work")
        
        # Scenario 4: Blocking overrides open policy
        await self.db.set_dm_permission(
            'coordinator', None,  # Open policy agent
            'frontend-dev', 'proj_web',
            'block',
            'Too many messages'
        )
        
        try:
            await self.db.create_or_get_dm_channel(
                'frontend-dev', 'proj_web',
                'coordinator', None
            )
            assert False, "Should be blocked"
        except ValueError:
            print("  ✅ Block overrides open policy")
        
        return True
    
    async def test_search_with_permissions(self):
        """Test that search respects permissions"""
        print("\n🧪 Testing search with permissions...")
        
        # Create a fresh agent for search testing
        await self.db.register_agent('searcher', 'proj_web', 'Search Test Agent', dm_policy='open')
        
        # Create channels with different access
        open_ch = 'global:search-open'
        private_ch = 'global:search-private'
        
        await self.db.create_channel(
            channel_id=open_ch,
            channel_type='channel',
            access_type='open',
            scope='global',
            name='search-open'
        )
        
        await self.db.create_channel(
            channel_id=private_ch,
            channel_type='channel',
            access_type='private',
            scope='global',
            name='search-private'
        )
        
        # Subscribe searcher to open channel
        await self.db.subscribe_to_channel('searcher', 'proj_web', open_ch)
        
        # Add only admin to private channel
        await self.db.add_channel_member(private_ch, 'admin', None)
        
        # Send searchable messages with unique content
        await self.db.send_message(
            channel_id=open_ch,
            sender_id='searcher',
            sender_project_id='proj_web',
            content='UNIQUE_SEARCH_TEST endpoint documentation'
        )
        
        await self.db.send_message(
            channel_id=private_ch,
            sender_id='admin',
            sender_project_id=None,
            content='UNIQUE_SEARCH_TEST security vulnerability'
        )
        
        # Searcher searches for unique term
        searcher_results = await self.db.search_messages(
            'searcher', 'proj_web', 'UNIQUE_SEARCH_TEST'
        )
        
        # Should only find the public message
        assert len(searcher_results) == 1
        assert 'documentation' in searcher_results[0]['content']
        assert 'vulnerability' not in searcher_results[0]['content']
        print("  ✅ Search respects channel permissions")
        
        # Admin searches for unique term
        admin_results = await self.db.search_messages(
            'admin', None, 'UNIQUE_SEARCH_TEST'
        )
        
        # Should find the private message (admin is member of private channel)
        assert len(admin_results) == 1
        assert 'vulnerability' in admin_results[0]['content']
        print("  ✅ Member can search private channel messages")
        
        return True
    
    async def test_mixed_scope_interactions(self):
        """Test interactions between global and project scopes"""
        print("\n🧪 Testing mixed scope interactions...")
        
        # Create a project-scoped channel
        project_channel = 'proj_web:frontend-team'
        await self.db.create_channel(
            channel_id=project_channel,
            channel_type='channel',
            access_type='members',
            scope='project',
            name='frontend-team',
            project_id='proj_web'
        )
        
        # Add project agent and global agent
        await self.db.add_channel_member(project_channel, 'frontend-dev', 'proj_web')
        await self.db.add_channel_member(project_channel, 'coordinator', None)
        
        # Both should be able to communicate
        msg1 = await self.db.send_message(
            channel_id=project_channel,
            sender_id='frontend-dev',
            sender_project_id='proj_web',
            content='Project update'
        )
        
        msg2 = await self.db.send_message(
            channel_id=project_channel,
            sender_id='coordinator',
            sender_project_id=None,
            content='Thanks for the update'
        )
        
        # Both should see all messages
        project_msgs = await self.db.get_messages(
            'frontend-dev', 'proj_web', channel_id=project_channel
        )
        global_msgs = await self.db.get_messages(
            'coordinator', None, channel_id=project_channel
        )
        
        assert len(project_msgs) == 2
        assert len(global_msgs) == 2
        print("  ✅ Global and project agents can interact in same channel")
        
        # Test DM between global and project agent
        # First need permission for restricted backend-dev
        await self.db.set_dm_permission(
            'backend-dev', 'proj_api',
            'coordinator', None,
            'allow',
            'Global coordinator access'
        )
        
        dm_channel = await self.db.create_or_get_dm_channel(
            'coordinator', None,
            'backend-dev', 'proj_api'
        )
        assert dm_channel is not None
        print("  ✅ Global-to-project DM works with permission")
        
        return True
    
    async def run_all_tests(self):
        """Run all integration tests"""
        print("=" * 60)
        print("Phase 2 Integration Tests")
        print("=" * 60)
        
        try:
            await self.setup()
            
            # Run tests
            results = []
            results.append(await self.test_cross_project_dm_workflow())
            results.append(await self.test_channel_membership_lifecycle())
            results.append(await self.test_message_routing_isolation())
            results.append(await self.test_dm_policy_enforcement())
            results.append(await self.test_search_with_permissions())
            results.append(await self.test_mixed_scope_interactions())
            
            # Summary
            print("\n" + "=" * 60)
            print("Integration Test Summary")
            print("=" * 60)
            
            total = len(results)
            passed = sum(1 for r in results if r)
            
            if passed == total:
                print(f"✅ All {total} integration tests passed!")
                return True
            else:
                print(f"❌ {passed}/{total} tests passed")
                return False
            
        finally:
            await self.teardown()

async def main():
    """Main test runner"""
    tester = TestPhase2Integration()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    asyncio.run(main())