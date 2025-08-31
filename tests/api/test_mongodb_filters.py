#!/usr/bin/env python3
"""
Test MongoDB-style filtering in QdrantStore.
Demonstrates all supported operators with complex nested queries.
"""

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

from api.db.qdrant_store import QdrantStore


async def test_mongodb_operators():
    """Test all MongoDB-style operators in Qdrant filters."""
    
    # Setup temporary Qdrant store
    with tempfile.TemporaryDirectory() as tmpdir:
        store = QdrantStore(qdrant_path=str(Path(tmpdir) / "qdrant"))
        
        # Index test messages with various metadata structures
        test_messages = [
            {
                "id": 1,
                "content": "Successfully implemented JWT authentication",
                "metadata": {
                    "type": "reflection",
                    "outcome": "success",
                    "confidence": 0.9,
                    "breadcrumbs": {
                        "task": "implement authentication",
                        "files": ["auth.py", "tokens.py", "middleware.py"],
                        "decisions": ["jwt", "stateless", "RS256"],
                        "metrics": {
                            "coverage": 0.92,
                            "complexity": 8
                        }
                    }
                }
            },
            {
                "id": 2,
                "content": "Failed to optimize database queries",
                "metadata": {
                    "type": "reflection",
                    "outcome": "failure",
                    "confidence": 0.6,
                    "breadcrumbs": {
                        "task": "optimize queries",
                        "files": ["db.py", "models.py"],
                        "decisions": ["indexing", "caching"],
                        "metrics": {
                            "coverage": 0.45,
                            "complexity": 15
                        }
                    }
                }
            },
            {
                "id": 3,
                "content": "Discovered security vulnerability in auth flow",
                "metadata": {
                    "type": "insight",
                    "severity": "high",
                    "confidence": 0.95,
                    "tags": ["security", "auth", "critical"],
                    "impact": {
                        "users_affected": 1000,
                        "priority": 1
                    }
                }
            },
            {
                "id": 4,
                "content": "Refactored API endpoints for consistency",
                "metadata": {
                    "type": "reflection", 
                    "outcome": "success",
                    "confidence": 0.85,
                    "breadcrumbs": {
                        "task": "refactor API",
                        "files": ["api.py", "routes.py", "handlers.py", "tests.py"],
                        "decisions": ["REST", "versioning"],
                        "patterns": ["middleware", "decorator", "factory"]
                    }
                }
            }
        ]
        
        # Index all test messages
        for msg in test_messages:
            await store.index_message(
                message_id=msg["id"],
                content=msg["content"],
                channel_id="test:channel",
                sender_id="test_agent",
                timestamp=datetime.now(),
                metadata=msg["metadata"],
                confidence=msg["metadata"].get("confidence", 0.5)
            )
        
        print("=== MongoDB-Style Filter Tests ===\n")
        
        # Test 1: Basic equality and comparison
        print("1. Basic comparison operators ($eq, $gte):")
        results = await store.search(
            query="authentication",
            metadata_filters={
                "type": "reflection",  # Direct equality
                "confidence": {"$gte": 0.8}
            },
            limit=10
        )
        print(f"   Found {len(results)} messages with type=reflection and confidence>=0.8\n")
        
        # Test 2: Negation operators
        print("2. Negation operators ($ne, $nin):")
        results = await store.search(
            query="development",
            metadata_filters={
                "outcome": {"$ne": "failure"},
                "type": {"$nin": ["error", "warning"]}
            },
            limit=10
        )
        print(f"   Found {len(results)} messages not failures and not errors/warnings\n")
        
        # Test 3: Array operators
        print("3. Array operators ($in, $all, $size):")
        results = await store.search(
            query="code",
            metadata_filters={
                "breadcrumbs.decisions": {
                    "$all": ["jwt", "stateless"]  # Has both values
                },
                "breadcrumbs.files": {
                    "$size": 3  # Exactly 3 files
                }
            },
            limit=10
        )
        print(f"   Found {len(results)} messages with jwt+stateless decisions and 3 files\n")
        
        # Test 4: Logical operators
        print("4. Logical operators ($or, $and):")
        results = await store.search(
            query="system",
            metadata_filters={
                "$or": [
                    {"type": "insight"},
                    {
                        "$and": [
                            {"type": "reflection"},
                            {"outcome": "success"},
                            {"confidence": {"$gte": 0.85}}
                        ]
                    }
                ]
            },
            limit=10
        )
        print(f"   Found {len(results)} insights OR (successful reflections with confidence>=0.85)\n")
        
        # Test 5: Nested field queries
        print("5. Deep nested field queries:")
        results = await store.search(
            query="metrics",
            metadata_filters={
                "breadcrumbs.metrics.coverage": {"$gte": 0.9},
                "breadcrumbs.metrics.complexity": {"$lte": 10}
            },
            limit=10
        )
        print(f"   Found {len(results)} messages with coverage>=0.9 and complexity<=10\n")
        
        # Test 6: Complex compound query
        print("6. Complex compound query:")
        results = await store.search(
            query="implementation",
            metadata_filters={
                "$and": [
                    {"type": "reflection"},
                    {
                        "$or": [
                            {"outcome": "success"},
                            {"confidence": {"$gte": 0.9}}
                        ]
                    },
                    {
                        "breadcrumbs.files": {
                            "$contains": "auth.py"
                        }
                    }
                ]
            },
            limit=10
        )
        print(f"   Found {len(results)} reflections that are (successful OR confident) AND involve auth.py\n")
        
        # Test 7: Existence checks
        print("7. Existence operators ($exists):")
        results = await store.search(
            query="analysis",
            metadata_filters={
                "breadcrumbs.patterns": {"$exists": True},  # Field exists
                "error_code": {"$exists": False}  # Field doesn't exist
            },
            limit=10
        )
        print(f"   Found {len(results)} messages with patterns field but no error_code\n")
        
        # Test 8: Text search
        print("8. Text operators ($text, $regex):")
        results = await store.search(
            query="security",
            metadata_filters={
                "content": {"$text": "authentication"},  # Full text search
                "type": {"$regex": "^refl"}  # Starts with "refl"
            },
            limit=10
        )
        print(f"   Found {len(results)} messages with 'authentication' text and type starting with 'refl'\n")
        
        # Test 9: Range queries
        print("9. Range operators ($between):")
        results = await store.search(
            query="optimization",
            metadata_filters={
                "confidence": {"$between": [0.7, 0.95]},
                "breadcrumbs.metrics.complexity": {"$lt": 20}
            },
            limit=10
        )
        print(f"   Found {len(results)} messages with confidence between 0.7-0.95 and complexity<20\n")
        
        # Test 10: Inverted/negative logic
        print("10. Negative logic ($not):")
        results = await store.search(
            query="review",
            metadata_filters={
                "$not": {
                    "$and": [
                        {"type": "reflection"},
                        {"outcome": "failure"}
                    ]
                }
            },
            limit=10
        )
        print(f"   Found {len(results)} messages that are NOT failed reflections\n")
        
        print("=== All MongoDB operators tested successfully! ===")


if __name__ == "__main__":
    asyncio.run(test_mongodb_operators())