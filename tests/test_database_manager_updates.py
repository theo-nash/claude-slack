#!/usr/bin/env python3
"""
Test DatabaseManager new methods: message CRUD and agent management
"""

import pytest
import pytest_asyncio
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, 'template/global/mcp/claude-slack')
from db.manager import DatabaseManager


@pytest_asyncio.fixture
async def db_manager():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        
        manager = DatabaseManager(db_path)
        await manager.initialize()
        
        # Register test project and agents
        await manager.register_project('test_proj', '/test/path', 'Test Project')
        await manager.register_agent('alice', 'test_proj', 'Alice Agent')
        await manager.register_agent('bob', None, 'Bob Agent')  # Global agent
        
        # Create a test channel
        await manager.create_channel(
            channel_id='test:general',
            channel_type='channel',
            access_type='open',
            scope='global',
            name='General',
            created_by='alice',
            created_by_project_id='test_proj'
        )
        
        # Subscribe agents to channel
        await manager.subscribe_to_channel('alice', 'test_proj', 'test:general')
        await manager.subscribe_to_channel('bob', None, 'test:general')
        
        yield manager


class TestMessageCRUD:
    """Test message CRUD operations"""
    
    @pytest.mark.asyncio
    async def test_get_message(self, db_manager):
        """Test getting a single message"""
        # Send a test message
        message_id = await db_manager.send_message(
            channel_id='test:general',
            sender_id='alice',
            sender_project_id='test_proj',
            content='Test message',
            metadata={'priority': 'high'}
        )
        
        # Get the message without permission check
        message = await db_manager.get_message(message_id)
        
        assert message is not None
        assert message['id'] == message_id
        assert message['content'] == 'Test message'
        assert message['sender_id'] == 'alice'
        assert message['channel_id'] == 'test:general'
        
        # Get with permission check - should work for alice
        message = await db_manager.get_message(
            message_id, 
            agent_name='alice',
            agent_project_id='test_proj'
        )
        assert message is not None
        
        # Get with permission check - should work for bob (subscribed)
        message = await db_manager.get_message(
            message_id,
            agent_name='bob',
            agent_project_id=None
        )
        assert message is not None
        
        # Get with permission check - should fail for non-subscribed agent
        await db_manager.register_agent('charlie', None, 'Charlie Agent')
        
        message = await db_manager.get_message(
            message_id,
            agent_name='charlie',
            agent_project_id=None
        )
        assert message is None  # No access
    
    @pytest.mark.asyncio
    async def test_update_message(self, db_manager):
        """Test updating a message"""
        # Send a message
        async with db_manager.get_connection(writer=True) as conn:
            message_id = await db_manager.send_message(
                conn,
                channel_id='test:general',
                sender_id='alice',
                sender_project_id='test_proj',
                content='Original content'
            )
        
        # Update by sender - should succeed
        async with db_manager.get_connection(writer=True) as conn:
            success = await db_manager.update_message(
                conn,
                message_id=message_id,
                content='Updated content',
                agent_name='alice',
                agent_project_id='test_proj'
            )
        assert success is True
        
        # Verify update
        async with db_manager.get_connection(writer=False) as conn:
            message = await db_manager.get_message(conn, message_id)
        assert message['content'] == 'Updated content'
        assert message['is_edited'] is True
        
        # Try to update by non-sender - should fail
        async with db_manager.get_connection(writer=True) as conn:
            success = await db_manager.update_message(
                conn,
                message_id=message_id,
                content='Hacked content',
                agent_name='bob',
                agent_project_id=None
            )
        assert success is False
        
        # Content should remain unchanged
        async with db_manager.get_connection(writer=False) as conn:
            message = await db_manager.get_message(conn, message_id)
        assert message['content'] == 'Updated content'
    
    @pytest.mark.asyncio
    async def test_delete_message(self, db_manager):
        """Test soft deleting a message"""
        # Create a members channel with bob as admin
        async with db_manager.get_connection(writer=True) as conn:
            await db_manager.create_channel(
                conn,
                channel_id='test:members',
                channel_type='channel',
                access_type='members',
                scope='global',
                name='Members Only'
            )
            await db_manager.add_channel_member(
                conn,
                channel_id='test:members',
                agent_name='bob',
                agent_project_id=None,
                role='admin'
            )
            await db_manager.add_channel_member(
                conn,
                channel_id='test:members',
                agent_name='alice',
                agent_project_id='test_proj',
                role='member'
            )
        
        # Alice sends a message
        async with db_manager.get_connection(writer=True) as conn:
            message_id = await db_manager.send_message(
                conn,
                channel_id='test:members',
                sender_id='alice',
                sender_project_id='test_proj',
                content='Delete me'
            )
        
        # Alice deletes her own message - should succeed
        async with db_manager.get_connection(writer=True) as conn:
            success = await db_manager.delete_message(
                conn,
                message_id=message_id,
                agent_name='alice',
                agent_project_id='test_proj'
            )
        assert success is True
        
        # Verify soft delete
        async with db_manager.get_connection(writer=False) as conn:
            message = await db_manager.get_message(conn, message_id)
        assert message['content'] == '[Message deleted]'
        assert message['is_edited'] is True
        
        # Send another message
        async with db_manager.get_connection(writer=True) as conn:
            message_id2 = await db_manager.send_message(
                conn,
                channel_id='test:members',
                sender_id='alice',
                sender_project_id='test_proj',
                content='Admin can delete'
            )
        
        # Bob (admin) deletes Alice's message - should succeed
        async with db_manager.get_connection(writer=True) as conn:
            success = await db_manager.delete_message(
                conn,
                message_id=message_id2,
                agent_name='bob',
                agent_project_id=None
            )
        assert success is True
        
        # Verify deletion
        async with db_manager.get_connection(writer=False) as conn:
            message = await db_manager.get_message(conn, message_id2)
        assert message['content'] == '[Message deleted]'


class TestAgentManagement:
    """Test agent management methods"""
    
    @pytest.mark.asyncio
    async def test_register_agent_full(self, db_manager):
        """Test registering an agent with all fields"""
        async with db_manager.get_connection(writer=True) as conn:
            await db_manager.register_agent(
                conn,
                name='diana',
                project_id='test_proj',
                description='Diana the Developer',
                dm_policy='restricted',
                discoverable='project',
                status='online',
                current_project_id='test_proj',
                metadata={'role': 'developer', 'skills': ['python', 'js']}
            )
        
        # Verify registration
        async with db_manager.get_connection(writer=False) as conn:
            agent = await db_manager.get_agent(conn, 'diana', 'test_proj')
        
        assert agent is not None
        assert agent['name'] == 'diana'
        assert agent['description'] == 'Diana the Developer'
        assert agent['dm_policy'] == 'restricted'
        assert agent['discoverable'] == 'project'
        assert agent['status'] == 'online'
        assert agent['metadata']['role'] == 'developer'
    
    @pytest.mark.asyncio
    async def test_update_agent(self, db_manager):
        """Test updating agent fields"""
        # Register an agent
        async with db_manager.get_connection(writer=True) as conn:
            await db_manager.register_agent(
                conn,
                name='eric',
                project_id=None,
                description='Eric Agent',
                status='offline'
            )
        
        # Update multiple fields
        async with db_manager.get_connection(writer=True) as conn:
            await db_manager.update_agent(
                conn,
                agent_name='eric',
                agent_project_id=None,
                status='online',
                description='Eric the Expert',
                dm_policy='closed',
                metadata={'expertise': 'security'}
            )
        
        # Verify updates
        async with db_manager.get_connection(writer=False) as conn:
            agent = await db_manager.get_agent(conn, 'eric', None)
        
        assert agent['status'] == 'online'
        assert agent['description'] == 'Eric the Expert'
        assert agent['dm_policy'] == 'closed'
        assert agent['metadata']['expertise'] == 'security'
    
    @pytest.mark.asyncio
    async def test_remove_dm_permission(self, db_manager):
        """Test removing DM permissions"""
        # Set up DM permissions
        async with db_manager.get_connection(writer=True) as conn:
            await db_manager.set_dm_permission(
                conn,
                agent_name='alice',
                agent_project_id='test_proj',
                other_agent_name='bob',
                other_agent_project_id=None,
                permission='block',
                reason='Testing'
            )
        
        # Verify block exists
        async with db_manager.get_connection(writer=False) as conn:
            can_dm = await db_manager.check_dm_permission(
                conn,
                agent1_name='bob',
                agent1_project_id=None,
                agent2_name='alice',
                agent2_project_id='test_proj'
            )
        assert can_dm is False  # Blocked
        
        # Remove permission
        async with db_manager.get_connection(writer=True) as conn:
            await db_manager.remove_dm_permission(
                conn,
                agent_name='alice',
                agent_project_id='test_proj',
                other_agent_name='bob',
                other_agent_project_id=None
            )
        
        # Verify removal - should now be able to DM (default open policy)
        async with db_manager.get_connection(writer=False) as conn:
            can_dm = await db_manager.check_dm_permission(
                conn,
                agent1_name='bob',
                agent1_project_id=None,
                agent2_name='alice',
                agent2_project_id='test_proj'
            )
        assert can_dm is True  # No longer blocked
    
    @pytest.mark.asyncio
    async def test_get_dm_permission_stats(self, db_manager):
        """Test getting DM permission statistics"""
        # Set up various permissions
        async with db_manager.get_connection(writer=True) as conn:
            # Alice blocks Charlie
            await db_manager.register_agent(conn, 'charlie', None)
            await db_manager.set_dm_permission(
                conn, 'alice', 'test_proj', 'charlie', None, 'block'
            )
            
            # Alice allows Diana (for restricted policy)
            await db_manager.register_agent(conn, 'diana', None)
            await db_manager.set_dm_permission(
                conn, 'alice', 'test_proj', 'diana', None, 'allow'
            )
            
            # Bob blocks Alice
            await db_manager.set_dm_permission(
                conn, 'bob', None, 'alice', 'test_proj', 'block'
            )
        
        # Get Alice's stats
        async with db_manager.get_connection(writer=False) as conn:
            stats = await db_manager.get_dm_permission_stats(
                conn, 'alice', 'test_proj'
            )
        
        assert stats['agents_blocked'] == 1  # Alice blocked Charlie
        assert stats['agents_allowed'] == 1  # Alice allowed Diana
        assert stats['blocked_by_others'] == 1  # Bob blocked Alice


if __name__ == '__main__':
    pytest.main([__file__, '-v'])