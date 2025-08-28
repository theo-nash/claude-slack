#!/usr/bin/env python3
"""Test the new general search_notes method."""

import asyncio
import os
from pathlib import Path
from datetime import datetime
from api.unified_api import ClaudeSlackAPI

async def test_search_notes():
    """Test the general search_notes functionality."""
    
    # Initialize API
    api = ClaudeSlackAPI(
        db_path="/tmp/test_claude_slack.db",
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        enable_semantic_search=bool(os.getenv("QDRANT_URL"))
    )
    
    await api.initialize()
    
    print("Testing general search_notes method...")
    print("=" * 60)
    
    # First, create some test notes from different agents
    test_agents = [
        ("alice", None),
        ("bob", None),
        ("charlie", None)  # All global agents for simplicity
    ]
    
    # Write test notes
    for agent_name, project_id in test_agents:
        for i in range(3):
            note_id = await api.write_note(
                agent_name=agent_name,
                agent_project_id=project_id,
                content=f"Test note {i} from {agent_name}: This is about {'debugging' if i == 0 else 'implementation' if i == 1 else 'testing'}",
                tags=["test", "debugging"] if i == 0 else ["test", "implementation"] if i == 1 else ["test", "validation"],
                metadata={
                    "confidence": 0.7 + i * 0.1,
                    "session_id": f"session-{agent_name}-{i}",
                    "complexity": i + 1
                }
            )
            print(f"Created note {note_id} for {agent_name}")
    
    print("\n" + "=" * 60)
    
    # Test 1: Search all notes without filters
    print("\nTest 1: Get all notes (no filters)")
    results = await api.search_notes(limit=5)
    print(f"Found {len(results)} notes")
    for r in results[:2]:
        print(f"  - {r.get('sender_id')}: {r.get('content', '')[:50]}...")
    
    # Test 2: Filter by agent names
    print("\nTest 2: Filter by specific agents")
    results = await api.search_notes(agent_names=["alice", "bob"])
    print(f"Found {len(results)} notes from alice and bob")
    
    # Test 3: Filter by tags
    print("\nTest 3: Filter by tags")
    results = await api.search_notes(tags=["debugging"])
    print(f"Found {len(results)} notes with 'debugging' tag")
    
    # Test 4: MongoDB-style metadata filters
    print("\nTest 4: MongoDB operators on metadata")
    results = await api.search_notes(
        metadata_filters={"confidence": {"$gte": 0.8}}
    )
    print(f"Found {len(results)} notes with confidence >= 0.8")
    
    # Test 5: Complex filter with $or
    print("\nTest 5: Complex $or filter")
    results = await api.search_notes(
        metadata_filters={
            "$or": [
                {"tags": {"$contains": "debugging"}},
                {"confidence": {"$gte": 0.9}}
            ]
        }
    )
    print(f"Found {len(results)} notes matching $or condition")
    
    # Test 6: Semantic search (if Qdrant enabled)
    if os.getenv("QDRANT_URL"):
        print("\nTest 6: Semantic search")
        results = await api.search_notes(
            query="debugging issues and problems",
            limit=3
        )
        print(f"Found {len(results)} semantically similar notes")
        for r in results:
            print(f"  - Score: {r.get('score', 0):.3f} | {r.get('content', '')[:50]}...")
    
    # Test 7: Combined filters
    print("\nTest 7: Combined filters (agent + metadata)")
    results = await api.search_notes(
        agent_names=["alice"],
        metadata_filters={"complexity": {"$lte": 2}}
    )
    print(f"Found {len(results)} notes from alice with complexity <= 2")
    
    print("\n" + "=" * 60)
    print("All tests completed successfully!")

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    env_path = Path.home() / "at" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    
    asyncio.run(test_search_notes())