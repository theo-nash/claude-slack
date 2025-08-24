#!/usr/bin/env python3
"""
Simple test for DatabaseManagerV3 and AgentManagerV3
"""

import asyncio
import tempfile
import os
import sys

# Add to path
sys.path.insert(0, 'template/global/mcp/claude-slack')

from db.manager_v3 import DatabaseManagerV3
from agents.manager_v3 import AgentManagerV3


async def test_database_manager():
    """Test DatabaseManagerV3 basic operations"""
    print("\n=== Testing DatabaseManagerV3 ===")
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        
        # Initialize database
        db = DatabaseManagerV3(db_path)
        await db.initialize()
        print("✓ Database initialized")
        
        # Test agent registration
        await db.register_agent(
            name='alice',
            project_id=None,
            description='Alice Test Agent',
            dm_policy='open',
            status='online'
        )
        print("✓ Agent registered")
        
        # Test get agent
        agent = await db.get_agent('alice', None)
        assert agent is not None
        assert agent['name'] == 'alice'
        assert agent['status'] == 'online'
        print("✓ Agent retrieved")
        
        # Test update agent
        await db.update_agent(
            agent_name='alice',
            agent_project_id=None,
            description='Alice Updated',
            status='busy'
        )
        agent = await db.get_agent('alice', None)
        assert agent['description'] == 'Alice Updated'
        assert agent['status'] == 'busy'
        print("✓ Agent updated")
        
        # Test channel creation
        await db.create_channel(
            channel_id='test:general',
            channel_type='channel',
            access_type='open',
            scope='global',
            name='General'
        )
        print("✓ Channel created")
        
        # Test message operations
        await db.subscribe_to_channel('alice', None, 'test:general')
        
        message_id = await db.send_message(
            channel_id='test:general',
            sender_id='alice',
            sender_project_id=None,
            content='Test message'
        )
        print(f"✓ Message sent (ID: {message_id})")
        
        # Test get_message
        message = await db.get_message(message_id)
        assert message is not None
        assert message['content'] == 'Test message'
        print("✓ Message retrieved")
        
        # Test update_message
        success = await db.update_message(
            message_id=message_id,
            content='Updated message',
            agent_name='alice',
            agent_project_id=None
        )
        assert success is True
        message = await db.get_message(message_id)
        assert message['content'] == 'Updated message'
        print("✓ Message updated")
        
        # Test delete_message
        success = await db.delete_message(
            message_id=message_id,
            agent_name='alice',
            agent_project_id=None
        )
        assert success is True
        message = await db.get_message(message_id)
        assert message['content'] == '[Message deleted]'
        print("✓ Message deleted (soft)")
        
        # Test DM permissions
        await db.register_agent('bob', None, 'Bob Test Agent')
        await db.set_dm_permission(
            agent_name='alice',
            agent_project_id=None,
            other_agent_name='bob',
            other_agent_project_id=None,
            permission='block',
            reason='Testing'
        )
        print("✓ DM permission set")
        
        # Test remove_dm_permission
        await db.remove_dm_permission(
            agent_name='alice',
            agent_project_id=None,
            other_agent_name='bob',
            other_agent_project_id=None
        )
        print("✓ DM permission removed")
        
        # Test get_dm_permission_stats
        stats = await db.get_dm_permission_stats('alice', None)
        assert 'agents_blocked' in stats
        assert 'agents_allowed' in stats
        print("✓ DM permission stats retrieved")
        
        print("\nDatabaseManagerV3: All tests passed! ✓✓✓")


async def test_agent_manager():
    """Test AgentManagerV3 operations"""
    print("\n=== Testing AgentManagerV3 ===")
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        
        # Initialize
        db = DatabaseManagerV3(db_path)
        await db.initialize()
        
        manager = AgentManagerV3(db_path)
        print("✓ AgentManager initialized")
        
        # Test agent registration
        success = await manager.register_agent(
            name='charlie',
            description='Charlie Test Agent',
            dm_policy='restricted',
            discoverable='public',
            status='online',
            metadata={'test': True}
        )
        assert success is True
        print("✓ Agent registered via manager")
        
        # Test agent_exists
        exists = await manager.agent_exists('charlie', None)
        assert exists is True
        exists = await manager.agent_exists('nonexistent', None)
        assert exists is False
        print("✓ Agent existence check works")
        
        # Test get_agent_settings
        settings = await manager.get_agent_settings('charlie', None)
        assert settings is not None
        assert settings['name'] == 'charlie'
        assert settings['dm_policy'] == 'restricted'
        print("✓ Agent settings retrieved")
        
        # Test set_dm_policy
        success = await manager.set_dm_policy(
            agent_name='charlie',
            agent_project_id=None,
            policy='closed',
            discoverable='private'
        )
        assert success is True
        settings = await manager.get_agent_settings('charlie', None)
        assert settings['dm_policy'] == 'closed'
        assert settings['discoverable'] == 'private'
        print("✓ DM policy updated")
        
        # Test block/unblock
        await manager.register_agent('diana', description='Diana Test')
        
        success = await manager.block_agent(
            agent_name='charlie',
            agent_project_id=None,
            target_agent='diana',
            target_project_id=None,
            reason='Test block'
        )
        assert success is True
        print("✓ Agent blocked")
        
        success = await manager.unblock_agent(
            agent_name='charlie',
            agent_project_id=None,
            target_agent='diana',
            target_project_id=None
        )
        assert success is True
        print("✓ Agent unblocked")
        
        # Test allow_agent
        success = await manager.allow_agent(
            agent_name='charlie',
            agent_project_id=None,
            target_agent='diana',
            target_project_id=None,
            reason='Test allow'
        )
        assert success is True
        print("✓ Agent allowed")
        
        # Test update_agent_settings
        success = await manager.update_agent_settings(
            agent_name='charlie',
            agent_project_id=None,
            description='Charlie Updated',
            status='busy'
        )
        assert success is True
        settings = await manager.get_agent_settings('charlie', None)
        assert settings['description'] == 'Charlie Updated'
        assert settings['status'] == 'busy'
        print("✓ Agent settings updated")
        
        # Test deactivate_agent
        success = await manager.deactivate_agent('charlie', None)
        assert success is True
        settings = await manager.get_agent_settings('charlie', None)
        assert settings['status'] == 'offline'
        print("✓ Agent deactivated")
        
        # Test get_dm_statistics
        stats = await manager.get_dm_statistics('charlie', None)
        assert 'dm_channels' in stats
        assert 'agents_allowed' in stats
        assert stats['agents_allowed'] == 1  # Diana
        print("✓ DM statistics retrieved")
        
        # Test validation
        success = await manager.register_agent(
            name='invalid',
            dm_policy='invalid_policy'  # Should fail
        )
        assert success is False
        print("✓ Validation works")
        
        print("\nAgentManagerV3: All tests passed! ✓✓✓")


async def main():
    """Run all tests"""
    print("Starting V3 Manager Tests...")
    
    try:
        await test_database_manager()
        await test_agent_manager()
        print("\n" + "="*50)
        print("ALL TESTS PASSED! 🎉")
        print("="*50)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())