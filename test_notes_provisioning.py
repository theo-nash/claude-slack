#!/usr/bin/env python3
"""
Test notes channel provisioning with the unified membership model.
"""

import asyncio
import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, '/home/gbode/at/claude-slack/template/global/mcp/claude-slack')

from db.manager import DatabaseManager
from config.reconciliation import ReconciliationPlan, RegisterAgentAction
from notes.manager import NotesManager

TEST_DIR = tempfile.mkdtemp(prefix="notes_test_")
TEST_DB = os.path.join(TEST_DIR, "test.db")

print("=" * 60)
print("NOTES CHANNEL PROVISIONING TEST")
print("=" * 60)

async def test_notes_provisioning():
    """Test that notes channels are created when agents are registered"""
    
    # Initialize database
    db = DatabaseManager(TEST_DB)
    await db.initialize()
    
    print("\n1. Testing agent registration with notes channel...")
    
    # Create a reconciliation plan
    plan = ReconciliationPlan()
    
    # Add agent registration with notes channel
    action = RegisterAgentAction(
        name="test-agent",
        description="Test agent with notes",
        create_notes_channel=True  # This should create notes channel
    )
    plan.add_action(action)
    
    # Execute the plan
    results = await plan.execute(db)
    
    print(f"   Registration success: {results['success']}")
    print(f"   Actions executed: {results['executed']}")
    
    # Check if agent was registered
    agent = await db.get_agent("test-agent")
    assert agent is not None, "Agent should be registered"
    print(f"   ✓ Agent registered: {agent['name']}")
    
    # Check if notes channel was created
    notes_channel_id = NotesManager.get_notes_channel_id("test-agent", None)
    print(f"   Expected notes channel ID: {notes_channel_id}")
    
    channel = await db.get_channel(notes_channel_id)
    assert channel is not None, "Notes channel should exist"
    print(f"   ✓ Notes channel created: {channel['id']}")
    
    # Verify channel properties
    assert channel['access_type'] == 'private', "Notes channel should be private"
    assert channel['scope'] == 'global', "Global agent should have global notes"
    print(f"   ✓ Channel is private with correct scope")
    
    # Check membership
    members = await db.get_channel_members(notes_channel_id)
    assert len(members) == 1, "Notes channel should have exactly one member"
    member = members[0]
    
    print(f"   Member details:")
    print(f"     - Agent: {member['agent_name']}")
    print(f"     - Can leave: {member['can_leave']}")
    print(f"     - Can send: {member['can_send']}")
    print(f"     - Can invite: {member['can_invite']}")
    print(f"     - Can manage: {member['can_manage']}")
    print(f"     - Invited by: {member['invited_by']}")
    
    assert member['agent_name'] == 'test-agent'
    assert member['can_leave'] == False, "Cannot leave notes channel"
    assert member['can_send'] == True, "Can write notes"
    assert member['can_invite'] == False, "Cannot invite others to notes"
    assert member['can_manage'] == True, "Can manage own notes"
    assert member['invited_by'] == 'system', "System creates notes channels"
    
    print("   ✓ Membership configured correctly")
    
    return db

async def test_notes_operations():
    """Test writing and reading notes"""
    
    db = DatabaseManager(TEST_DB)
    notes_mgr = NotesManager(TEST_DB)
    
    print("\n2. Testing notes operations...")
    
    # Write a note
    note_id = await notes_mgr.write_note(
        agent_name="test-agent",
        agent_project_id=None,
        content="This is a test note",
        tags=["test", "demo"],
        session_id="test_session_123"
    )
    
    print(f"   ✓ Note written with ID: {note_id}")
    
    # Search notes
    notes = await notes_mgr.search_notes(
        agent_name="test-agent",
        agent_project_id=None,
        query="test"
    )
    
    assert len(notes) > 0, "Should find the note"
    note = notes[0]
    
    print(f"   Found note:")
    print(f"     - Content: {note['content']}")
    print(f"     - Tags: {note['tags']}")
    print(f"     - Session: {note['session_id']}")
    
    assert "test" in note['content'].lower()
    assert "test" in note['tags']
    assert note['session_id'] == "test_session_123"
    
    print("   ✓ Notes search works correctly")
    
    # Get recent notes
    recent = await notes_mgr.get_recent_notes(
        agent_name="test-agent",
        agent_project_id=None,
        limit=5
    )
    
    assert len(recent) > 0, "Should have recent notes"
    print(f"   ✓ Retrieved {len(recent)} recent notes")

async def test_project_agent_notes():
    """Test notes for project-scoped agents"""
    
    db = DatabaseManager(TEST_DB)
    
    print("\n3. Testing project agent notes...")
    
    # First register the project
    await db.register_project(
        project_id="test_proj_456",
        project_path="/tmp/test_project",
        project_name="Test Project"
    )
    print("   ✓ Project registered")
    
    # Register a project agent with notes
    plan = ReconciliationPlan()
    action = RegisterAgentAction(
        name="project-agent",
        project_id="test_proj_456",
        description="Project agent with notes",
        create_notes_channel=True
    )
    plan.add_action(action)
    
    results = await plan.execute(db)
    print(f"   Registration results: {results}")
    if not results['success']:
        for result in results.get('results', []):
            if not result.success:
                print(f"   Failed action: {result.action_type} - {result.error}")
    assert results['success'], "Should register project agent"
    
    # Check notes channel
    notes_channel_id = NotesManager.get_notes_channel_id(
        "project-agent", 
        "test_proj_456"
    )
    print(f"   Project notes channel ID: {notes_channel_id}")
    
    channel = await db.get_channel(notes_channel_id)
    assert channel is not None, "Project notes channel should exist"
    assert channel['scope'] == 'project', "Should be project-scoped"
    assert channel['project_id'] == 'test_proj_456', "Should have correct project"
    
    print("   ✓ Project agent notes channel created correctly")

async def main():
    """Run all tests"""
    try:
        await test_notes_provisioning()
        await test_notes_operations()
        await test_project_agent_notes()
        
        print("\n" + "=" * 60)
        print("✅ ALL NOTES TESTS PASSED!")
        print("=" * 60)
        print("\nNotes channel provisioning works correctly with:")
        print("✓ Automatic creation during agent registration")
        print("✓ Correct unified membership model")
        print("✓ Private channels with can_leave=False")
        print("✓ Both global and project agents")
        print("✓ Notes operations (write, search, recent)")
        
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