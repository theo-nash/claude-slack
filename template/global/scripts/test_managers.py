#!/usr/bin/env python3
"""
Test script to verify the new manager architecture is working correctly.
Run this after installation to ensure all managers are functioning properly.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ManagerTest')

# Add MCP directory to path
claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
mcp_dir = os.path.join(claude_config_dir, 'mcp', 'claude-slack')
sys.path.insert(0, mcp_dir)

async def test_managers():
    """Test all three managers to ensure they're working"""
    
    db_path = os.path.join(claude_config_dir, 'data', 'claude-slack.db')
    
    print("\n=== Testing Manager Architecture ===\n")
    
    # Test SessionManager
    print("1. Testing SessionManager...")
    try:
        from sessions.manager import SessionManager
        session_manager = SessionManager(db_path)
        
        # Register a test session
        success = await session_manager.register_session(
            session_id="test_session_001",
            project_path="/tmp/test_project",
            project_name="Test Project"
        )
        
        if success:
            print("   ✓ SessionManager: Session registration successful")
        else:
            print("   ✗ SessionManager: Session registration failed")
            
        # Get session context
        context = await session_manager.get_session_context("test_session_001")
        if context:
            print(f"   ✓ SessionManager: Retrieved context for project '{context.project_name}'")
        else:
            print("   ✗ SessionManager: Failed to retrieve context")
            
    except Exception as e:
        print(f"   ✗ SessionManager Error: {e}")
    
    # Test ChannelManager
    print("\n2. Testing ChannelManager...")
    try:
        from channels.manager import ChannelManager
        channel_manager = ChannelManager(db_path, session_manager)
        
        # Create a test channel
        channel_id = await channel_manager.create_channel(
            name="test_channel",
            scope="global",
            description="Test channel for manager verification"
        )
        
        if channel_id:
            print(f"   ✓ ChannelManager: Created channel '{channel_id}'")
        else:
            print("   ✗ ChannelManager: Channel creation failed")
            
        # List channels
        channels = await channel_manager.list_channels(scope="global")
        if channels:
            print(f"   ✓ ChannelManager: Found {len(channels)} global channels")
        else:
            print("   ✗ ChannelManager: Failed to list channels")
            
    except Exception as e:
        print(f"   ✗ ChannelManager Error: {e}")
    
    # Test SubscriptionManager
    print("\n3. Testing SubscriptionManager...")
    try:
        from subscriptions.manager import SubscriptionManager
        subscription_manager = SubscriptionManager(db_path)
        
        # Subscribe test agent to channel
        success = await subscription_manager.subscribe(
            agent_name="test_agent",
            agent_project_id=None,
            channel_name="test_channel",
            scope="global",
            source="test"
        )
        
        if success:
            print("   ✓ SubscriptionManager: Subscription successful")
        else:
            print("   ✗ SubscriptionManager: Subscription failed")
            
        # Get subscriptions
        subs = await subscription_manager.get_subscriptions("test_agent", None)
        if subs:
            print(f"   ✓ SubscriptionManager: Retrieved subscriptions - Global: {subs['global']}")
        else:
            print("   ✗ SubscriptionManager: Failed to retrieve subscriptions")
            
    except Exception as e:
        print(f"   ✗ SubscriptionManager Error: {e}")
    
    print("\n=== Manager Architecture Test Complete ===\n")
    print("Summary:")
    print("  • SessionManager: Foundation for session/project context")
    print("  • ChannelManager: CRUD operations for channels")
    print("  • SubscriptionManager: Agent-channel relationships")
    print("\nIf all tests passed, the new architecture is working correctly!")

if __name__ == "__main__":
    print("\nClaude-Slack Manager Architecture Test")
    print("=" * 40)
    asyncio.run(test_managers())