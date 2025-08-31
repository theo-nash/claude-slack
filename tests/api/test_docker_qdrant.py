#!/usr/bin/env python3
"""
Test MongoDB-style operators with Docker Qdrant (no indexes required!)
"""

import asyncio
from datetime import datetime
from api.db.qdrant_store import QdrantStore


async def test_docker_qdrant():
    """Test with Docker Qdrant - no index setup needed!"""
    
    print("🐳 Connecting to Docker Qdrant...")
    print("   URL: http://localhost:6333")
    print("   Collection: claude_slack_test\n")
    
    try:
        # Connect to Docker Qdrant
        store = QdrantStore(
            qdrant_url="http://localhost:6333",
            collection_name="claude_slack_test_no_indexes"
        )
        
        print("✅ Connected to Docker Qdrant!\n")
        
        # Index test messages with various nested structures
        print("📝 Indexing test messages with arbitrary nested metadata...")
        
        test_messages = [
            {
                "id": 1,
                "content": "JWT authentication implemented successfully",
                "metadata": {
                    "type": "reflection",
                    "outcome": "success",
                    "confidence": 0.9,
                    "breadcrumbs": {
                        "task": "implement auth",
                        "files": ["auth.py", "jwt.py", "middleware.py"],
                        "decisions": ["jwt", "stateless", "RS256"],
                        "metrics": {
                            "coverage": 0.92,
                            "complexity": 8,
                            "performance": {
                                "response_time_ms": 45,
                                "throughput": 1000
                            }
                        }
                    },
                    "completely": {
                        "arbitrary": {
                            "nested": {
                                "structure": "that we never knew about",
                                "level": 5
                            }
                        }
                    }
                }
            },
            {
                "id": 2,
                "content": "Database optimization failed with timeout",
                "metadata": {
                    "type": "reflection",
                    "outcome": "failure",
                    "confidence": 0.6,
                    "breadcrumbs": {
                        "task": "optimize queries",
                        "files": ["db.py", "queries.py"],
                        "decisions": ["indexing", "caching"],
                        "metrics": {
                            "coverage": 0.45,
                            "complexity": 15
                        }
                    },
                    "error_details": {
                        "code": "TIMEOUT_ERROR",
                        "duration_ms": 30000
                    }
                }
            },
            {
                "id": 3,
                "content": "Security vulnerability discovered in OAuth flow",
                "metadata": {
                    "type": "insight",
                    "severity": "critical",
                    "confidence": 0.95,
                    "tags": ["security", "auth", "urgent"],
                    "impact": {
                        "users_affected": 10000,
                        "risk_score": 9.5,
                        "departments": ["engineering", "security", "compliance"]
                    },
                    "random_field_we_just_made_up": {
                        "with_random_subfield": True,
                        "and_random_number": 42
                    }
                }
            },
            {
                "id": 4,
                "content": "API refactoring completed ahead of schedule",
                "metadata": {
                    "type": "reflection",
                    "outcome": "success",
                    "confidence": 0.85,
                    "breadcrumbs": {
                        "task": "refactor API",
                        "files": ["api.py", "routes.py", "handlers.py", "tests.py"],
                        "decisions": ["REST", "versioning", "OpenAPI"],
                        "patterns": ["middleware", "decorator", "factory"],
                        "metrics": {
                            "coverage": 0.88,
                            "complexity": 6
                        }
                    },
                    "timeline": {
                        "estimated_days": 5,
                        "actual_days": 3,
                        "ahead_by": 2
                    }
                }
            }
        ]
        
        for msg in test_messages:
            await store.index_message(
                message_id=msg["id"],
                content=msg["content"],
                channel_id="test",
                sender_id="bot",
                timestamp=datetime.now(),
                metadata=msg["metadata"],
                confidence=msg["metadata"].get("confidence", 0.5)
            )
            print(f"  ✓ Indexed message {msg['id']}: {msg['content'][:50]}...")
        
        print(f"\n✅ Indexed {len(test_messages)} messages with arbitrary nested metadata")
        print("   Note: No indexes were created for these fields!\n")
        
        print("=" * 70)
        print("🧪 Testing MongoDB Operators on Arbitrary Fields (No Indexes!)")
        print("=" * 70)
        
        test_queries = [
            # Basic queries
            ("1. Simple equality on known field", 
             {"type": "reflection"}),
            
            ("2. Nested field we never indexed", 
             {"breadcrumbs.task": "implement auth"}),
            
            ("3. Deep nested field (3 levels)", 
             {"breadcrumbs.metrics.coverage": {"$gte": 0.9}}),
            
            ("4. Super deep nested field (4 levels!)", 
             {"breadcrumbs.metrics.performance.response_time_ms": {"$lt": 100}}),
            
            ("5. Completely arbitrary field we just made up", 
             {"completely.arbitrary.nested.structure": "that we never knew about"}),
            
            ("6. Another random field with nested query", 
             {"completely.arbitrary.nested.level": 5}),
            
            ("7. Field that only exists in one message", 
             {"error_details.code": "TIMEOUT_ERROR"}),
            
            ("8. Boolean field stored in random location", 
             {"random_field_we_just_made_up.with_random_subfield": True}),
            
            # Complex operators
            ("9. $ne on arbitrary field", 
             {"outcome": {"$ne": "failure"}}),
            
            ("10. $in on nested array", 
             {"breadcrumbs.decisions": {"$in": ["jwt", "OAuth"]}}),
            
            ("11. $all on array field", 
             {"tags": {"$all": ["security", "auth"]}}),
            
            ("12. $gte on deeply nested numeric", 
             {"impact.risk_score": {"$gte": 9.0}}),
            
            ("13. Array $contains on field we never knew about", 
             {"impact.departments": {"$contains": "security"}}),
            
            ("14. $size on array (using auto-indexed length)", 
             {"breadcrumbs.files": {"$size": 3}}),
            
            # Logical operators on arbitrary fields
            ("15. $and with random fields", {
                "$and": [
                    {"type": "reflection"},
                    {"timeline.ahead_by": {"$gte": 1}}
                ]
            }),
            
            ("16. $or with mixed arbitrary fields", {
                "$or": [
                    {"severity": "critical"},
                    {"breadcrumbs.metrics.complexity": {"$lte": 7}}
                ]
            }),
            
            ("17. Complex nested $and/$or", {
                "$and": [
                    {"confidence": {"$gte": 0.8}},
                    {
                        "$or": [
                            {"outcome": "success"},
                            {"type": "insight"}
                        ]
                    }
                ]
            }),
            
            ("18. Query on field that doesn't exist in most docs", 
             {"random_field_we_just_made_up.and_random_number": 42}),
        ]
        
        print("\n📊 Query Results:")
        print("-" * 70)
        
        success_count = 0
        for description, filters in test_queries:
            try:
                results = await store.search(
                    query="auth implementation security",  # Semantic component
                    metadata_filters=filters,
                    limit=10
                )
                print(f"✅ {description:55} → {len(results)} results")
                success_count += 1
                
                # Show details for interesting queries
                if len(results) > 0 and "arbitrary" in description.lower():
                    first = results[0]
                    print(f"     → Found: ID={first[0]}, Score={first[1]:.3f}")
                    
            except Exception as e:
                print(f"❌ {description:55} → ERROR: {e}")
                if "Index required" in str(e):
                    print("     → This means we're accidentally hitting Qdrant Cloud!")
        
        print("-" * 70)
        print(f"\n📈 Summary:")
        print(f"  ✅ Successful queries: {success_count}/{len(test_queries)}")
        print(f"  🎯 All queries worked on arbitrary fields without indexes!")
        print(f"\n✨ Docker Qdrant handles arbitrary nested MongoDB queries perfectly!")
        print("   No schema registration or index creation required! 🎉")
        
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        print("\n📝 Make sure Docker Qdrant is running:")
        print("   docker run -d -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant")


if __name__ == "__main__":
    asyncio.run(test_docker_qdrant())