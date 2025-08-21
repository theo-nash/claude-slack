#!/usr/bin/env python3
"""
Test script to verify agent_id validation in claude-slack MCP server
"""

import asyncio
import json
import sys
import os

# Add the MCP server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'template/global/mcp/claude-slack'))

from db.manager import DatabaseManager
from environment_config import env_config

async def test_agent_validation():
    """Test agent validation with various scenarios"""
    
    # Initialize database
    db_path = str(env_config.db_path)
    db_manager = DatabaseManager(db_path)
    await db_manager.initialize()
    
    print("Testing agent validation scenarios...\n")
    
    # Test 1: Register test agents
    print("1. Registering test agents...")
    await db_manager.register_agent("example-agent", "Example agent for testing")
    await db_manager.register_agent("test-agent-1", "Test agent 1")
    await db_manager.register_agent("test-agent-2", "Test agent 2")
    print("   ✓ Registered 3 test agents\n")
    
    # Test 2: Get list of agents
    print("2. Fetching all agents...")
    agents = await db_manager.get_agents_by_scope(None)
    print(f"   Found {len(agents)} agents:")
    for agent in agents:
        print(f"   • {agent['name']}")
    print()
    
    # Test 3: Validate existing agent
    print("3. Validating existing agent 'example-agent'...")
    agent = await db_manager.get_agent("example-agent")
    if agent:
        print("   ✓ Agent found and validated")
    else:
        print("   ✗ Agent not found")
    print()
    
    # Test 4: Validate non-existing agent
    print("4. Validating non-existing agent 'invalid-agent'...")
    agent = await db_manager.get_agent("invalid-agent")
    if not agent:
        print("   ✓ Correctly identified as non-existing")
    else:
        print("   ✗ Unexpectedly found agent")
    print()
    
    # Test 5: Test with empty agent_id
    print("5. Testing with empty agent_id...")
    agent = await db_manager.get_agent("")
    if not agent:
        print("   ✓ Correctly rejected empty agent_id")
    else:
        print("   ✗ Unexpectedly accepted empty agent_id")
    print()
    
    print("✅ All validation tests completed!")
    
    # Close database connection
    await db_manager.close()

if __name__ == "__main__":
    asyncio.run(test_agent_validation())