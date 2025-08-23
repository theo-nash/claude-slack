#!/usr/bin/env python3
"""
Tests for NotesManager
Verifies that agent notes work correctly as private channels
"""

import asyncio
import os
import sys
import tempfile
import shutil
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'template', 'global', 'mcp', 'claude-slack'))

from db.manager_v3 import DatabaseManagerV3
from notes.manager import NotesManager

class TestNotesManager:
    """Test NotesManager functionality"""
    
    def __init__(self):
        self.test_dir = None
        self.db_path = None
        self.db = None
        self.notes_manager = None
    
    async def setup(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp(prefix='notes_manager_test_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Initialize database
        self.db = DatabaseManagerV3(self.db_path)
        await self.db.initialize()
        
        # Initialize notes manager
        self.notes_manager = NotesManager(self.db_path)
        await self.notes_manager.initialize()
        
        # Register test project
        await self.db.register_project('proj_123', '/test/project', 'Test Project')
        
        # Register test agents
        await self.db.register_agent('alice', None, 'Alice Agent')
        await self.db.register_agent('bob', 'proj_123', 'Bob in Project')
        
        print(f"✅ Test environment created")
    
    async def teardown(self):
        """Clean up test environment"""
        if self.db:
            await self.db.close()
        
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        print("✅ Test environment cleaned up")
    
    async def test_notes_channel_creation(self):
        """Test that notes channels are created correctly"""
        print("\n🧪 Testing notes channel creation...")
        
        # Create notes channel for alice
        channel_id = await self.notes_manager.ensure_notes_channel('alice', None)
        assert channel_id == 'notes:alice:global'
        print(f"  ✅ Created global notes channel: {channel_id}")
        
        # Verify channel exists and has correct properties
        channel = await self.db.get_channel(channel_id)
        assert channel is not None
        assert channel['channel_type'] == 'channel'
        assert channel['access_type'] == 'private'
        assert channel['scope'] == 'global'
        print("  ✅ Channel has correct properties")
        
        # Verify alice is the only member
        members = await self.db.get_channel_members(channel_id)
        assert len(members) == 1
        assert members[0]['agent_name'] == 'alice'
        assert members[0]['role'] == 'owner'
        print("  ✅ Alice is the sole owner")
        
        # Create project-scoped notes channel for bob
        bob_channel_id = await self.notes_manager.ensure_notes_channel('bob', 'proj_123')
        assert bob_channel_id == 'notes:bob:proj_123'
        print(f"  ✅ Created project notes channel: {bob_channel_id}")
        
        # Ensure idempotency
        same_channel_id = await self.notes_manager.ensure_notes_channel('alice', None)
        assert same_channel_id == channel_id
        print("  ✅ Channel creation is idempotent")
        
        return True
    
    async def test_write_and_read_notes(self):
        """Test writing and reading notes"""
        print("\n🧪 Testing note writing and reading...")
        
        # Write a simple note
        note_id = await self.notes_manager.write_note(
            agent_name='alice',
            agent_project_id=None,
            content='This is my first note'
        )
        assert note_id is not None
        print(f"  ✅ Wrote note with ID: {note_id}")
        
        # Write a note with tags and metadata
        note2_id = await self.notes_manager.write_note(
            agent_name='alice',
            agent_project_id=None,
            content='Found a bug in authentication',
            tags=['bug', 'auth', 'important'],
            session_id='session_123',
            metadata={'severity': 'high', 'file': 'auth.py'}
        )
        print(f"  ✅ Wrote tagged note with ID: {note2_id}")
        
        # Read recent notes
        recent_notes = await self.notes_manager.get_recent_notes('alice', None, limit=10)
        assert len(recent_notes) == 2
        print(f"  ✅ Retrieved {len(recent_notes)} recent notes")
        
        # Verify note content
        # Check which order they're in
        for i, note in enumerate(recent_notes):
            if 'bug in authentication' in note['content']:
                latest_note = note
                assert 'bug' in latest_note['tags']
                assert latest_note['session_id'] == 'session_123'
                print("  ✅ Note content and metadata preserved")
                break
        else:
            # Debug output if not found
            print(f"  ❌ Could not find bug note. Notes: {[n['content'][:30] for n in recent_notes]}")
            assert False, "Could not find the bug note"
        
        return True
    
    async def test_search_notes(self):
        """Test searching notes"""
        print("\n🧪 Testing note search...")
        
        # Write several notes with different tags
        await self.notes_manager.write_note(
            'alice', None, 'Learning about async patterns',
            tags=['learning', 'async']
        )
        await self.notes_manager.write_note(
            'alice', None, 'Fixed the async bug in handler',
            tags=['bug-fix', 'async']
        )
        await self.notes_manager.write_note(
            'alice', None, 'TODO: Review security guidelines',
            tags=['todo', 'security']
        )
        await self.notes_manager.write_note(
            'alice', None, 'Deployed to production',
            tags=['deployment']
        )
        
        # Search by content
        results = await self.notes_manager.search_notes(
            'alice', None, query='async'
        )
        assert len(results) == 2
        print(f"  ✅ Found {len(results)} notes with 'async'")
        
        # Search by tags
        results = await self.notes_manager.search_notes(
            'alice', None, tags=['todo']
        )
        assert len(results) == 1
        assert 'security' in results[0]['content']
        print("  ✅ Tag search works correctly")
        
        # Search with multiple tags (OR logic)
        results = await self.notes_manager.search_notes(
            'alice', None, tags=['bug-fix', 'deployment']
        )
        assert len(results) == 2
        print("  ✅ Multi-tag search works")
        
        return True
    
    async def test_session_notes(self):
        """Test session-specific notes"""
        print("\n🧪 Testing session notes...")
        
        session1 = "session_001"
        session2 = "session_002"
        
        # Write notes in different sessions
        await self.notes_manager.write_note(
            'alice', None, 'Session 1: Starting investigation',
            session_id=session1
        )
        await self.notes_manager.write_note(
            'alice', None, 'Session 1: Found root cause',
            session_id=session1
        )
        await self.notes_manager.write_note(
            'alice', None, 'Session 2: Different task',
            session_id=session2
        )
        
        # Get notes from session 1
        session1_notes = await self.notes_manager.get_session_notes(
            'alice', None, session1
        )
        assert len(session1_notes) == 2
        print(f"  ✅ Retrieved {len(session1_notes)} notes from session 1")
        
        # Get notes from session 2
        session2_notes = await self.notes_manager.get_session_notes(
            'alice', None, session2
        )
        assert len(session2_notes) == 1
        print(f"  ✅ Retrieved {len(session2_notes)} notes from session 2")
        
        return True
    
    async def test_project_scoped_notes(self):
        """Test that project-scoped notes are separate"""
        print("\n🧪 Testing project-scoped notes...")
        
        # Write notes for bob in project
        await self.notes_manager.write_note(
            'bob', 'proj_123', 'Project-specific note',
            tags=['project']
        )
        
        # Create another bob in global scope
        await self.db.register_agent('bob', None, 'Bob Global')
        
        # Write global note for bob
        await self.notes_manager.write_note(
            'bob', None, 'Global note',
            tags=['global']
        )
        
        # Get project notes
        project_notes = await self.notes_manager.get_recent_notes('bob', 'proj_123')
        assert len(project_notes) == 1
        assert 'Project-specific' in project_notes[0]['content']
        print("  ✅ Project notes are isolated")
        
        # Get global notes
        global_notes = await self.notes_manager.get_recent_notes('bob', None)
        assert len(global_notes) == 1
        assert 'Global note' in global_notes[0]['content']
        print("  ✅ Global notes are separate")
        
        return True
    
    async def test_notes_privacy(self):
        """Test that notes channels are truly private"""
        print("\n🧪 Testing notes privacy...")
        
        # Alice writes a note
        await self.notes_manager.write_note(
            'alice', None, 'Private information'
        )
        
        # Get alice's notes channel
        alice_channel_id = NotesManager.get_notes_channel_id('alice', None)
        
        # Verify bob cannot access alice's notes channel
        can_access = await self.db.check_agent_can_access_channel(
            'bob', 'proj_123', alice_channel_id
        )
        assert not can_access
        print("  ✅ Bob cannot access Alice's notes channel")
        
        # Verify alice can access her own notes
        can_access = await self.db.check_agent_can_access_channel(
            'alice', None, alice_channel_id
        )
        assert can_access
        print("  ✅ Alice can access her own notes channel")
        
        # Test peek functionality (for META agents)
        peeked_notes = await self.notes_manager.peek_agent_notes(
            target_agent_name='alice',
            target_project_id=None,
            requester_name='admin',
            requester_project_id=None,
            limit=1
        )
        assert len(peeked_notes) == 1
        print("  ✅ Admin can peek at notes (logged)")
        
        return True
    
    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("NotesManager Tests")
        print("=" * 60)
        
        try:
            await self.setup()
            
            # Run tests
            results = []
            results.append(await self.test_notes_channel_creation())
            results.append(await self.test_write_and_read_notes())
            results.append(await self.test_search_notes())
            results.append(await self.test_session_notes())
            results.append(await self.test_project_scoped_notes())
            results.append(await self.test_notes_privacy())
            
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
    tester = TestNotesManager()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    asyncio.run(main())