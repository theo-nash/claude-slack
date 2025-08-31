#!/usr/bin/env python3
"""
Test nested field queries with MongoDB operators.
"""

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

from api.db.qdrant_store import QdrantStore


async def test_nested():
    """Test MongoDB operators on nested fields."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = QdrantStore(qdrant_path=str(Path(tmpdir) / "qdrant"))
        
        # Index messages with nested structures
        messages = [
            {
                "id": 1,
                "content": "JWT implementation successful",
                "metadata": {
                    "type": "reflection",
                    "breadcrumbs": {
                        "task": "auth",
                        "files": ["auth.py", "jwt.py"],
                        "metrics": {"coverage": 0.95, "complexity": 5}
                    }
                }
            },
            {
                "id": 2,
                "content": "OAuth2 integration complete",
                "metadata": {
                    "type": "reflection",
                    "breadcrumbs": {
                        "task": "auth",
                        "files": ["oauth.py"],
                        "metrics": {"coverage": 0.85, "complexity": 12}
                    }
                }
            },
            {
                "id": 3,
                "content": "Database optimization done",
                "metadata": {
                    "type": "analysis",
                    "breadcrumbs": {
                        "task": "performance",
                        "files": ["db.py", "queries.py", "cache.py"],
                        "metrics": {"coverage": 0.70, "complexity": 8}
                    }
                }
            }
        ]
        
        for msg in messages:
            await store.index_message(
                message_id=msg["id"],
                content=msg["content"],
                channel_id="test",
                sender_id="bot",
                timestamp=datetime.now(),
                metadata=msg["metadata"]
            )
        
        print("\n=== Nested Field Query Tests ===\n")
        
        # Test nested equality
        results = await store.search(
            query="implementation",
            metadata_filters={
                "breadcrumbs.task": "auth"
            },
            limit=10
        )
        print(f"1. Messages with breadcrumbs.task='auth': {len(results)}")
        
        # Test nested comparison
        results = await store.search(
            query="complete",
            metadata_filters={
                "breadcrumbs.metrics.coverage": {"$gte": 0.85}
            },
            limit=10
        )
        print(f"2. Messages with coverage >= 0.85: {len(results)}")
        
        # Test array size on nested field
        results = await store.search(
            query="optimization",
            metadata_filters={
                "breadcrumbs.files": {"$size": 3}
            },
            limit=10
        )
        print(f"3. Messages with exactly 3 files: {len(results)}")
        
        # Test complex nested query
        results = await store.search(
            query="auth",
            metadata_filters={
                "$and": [
                    {"type": "reflection"},
                    {"breadcrumbs.task": "auth"},
                    {"breadcrumbs.metrics.coverage": {"$gte": 0.9}}
                ]
            },
            limit=10
        )
        print(f"4. Reflections about auth with coverage >= 0.9: {len(results)}")
        
        # Test OR on nested fields
        results = await store.search(
            query="code",
            metadata_filters={
                "$or": [
                    {"breadcrumbs.metrics.complexity": {"$lte": 6}},
                    {"breadcrumbs.metrics.coverage": {"$gte": 0.9}}
                ]
            },
            limit=10
        )
        print(f"5. Low complexity OR high coverage: {len(results)}")
        
        # Test array contains on nested field
        results = await store.search(
            query="auth",
            metadata_filters={
                "breadcrumbs.files": {"$contains": "auth.py"}
            },
            limit=10
        )
        print(f"6. Messages with auth.py in files: {len(results)}")
        
        print("\n=== Nested query tests completed! ===")


if __name__ == "__main__":
    asyncio.run(test_nested())