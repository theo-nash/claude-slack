#!/usr/bin/env python3
"""
Demo script showing MongoDB-style filtering in action.
Shows how the same query works across SQLite and Qdrant backends.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.db.filters import (
    MongoFilterParser, 
    SQLiteFilterBackend, 
    QdrantFilterBackend
)


def demo_query(description: str, query: dict):
    """Demo a single query across both backends."""
    print(f"\n{'='*60}")
    print(f"DEMO: {description}")
    print(f"{'='*60}")
    
    print(f"\nMongoDB Query:")
    print(json.dumps(query, indent=2))
    
    # Parse the query
    parser = MongoFilterParser()
    expression = parser.parse(query)
    
    print(f"\nParsed Expression Tree:")
    print(f"  Root: {expression.operator.value}")
    print(f"  Conditions: {len(expression.conditions)}")
    
    # Convert to SQLite
    print(f"\n--- SQLite Backend ---")
    sqlite = SQLiteFilterBackend(table_alias="m")
    sql, params = sqlite.convert(expression)
    
    print(f"SQL WHERE clause:")
    print(f"  {sql}")
    print(f"Parameters: {params}")
    
    # Convert to Qdrant (if possible)
    print(f"\n--- Qdrant Backend ---")
    try:
        qdrant = QdrantFilterBackend()
        qdrant_filter = qdrant.convert(expression)
        
        if qdrant_filter:
            print(f"Qdrant Filter generated successfully")
            print(f"  Type: {type(qdrant_filter).__name__}")
            if hasattr(qdrant_filter, '__dict__'):
                for key, value in qdrant_filter.__dict__.items():
                    if value:
                        print(f"  {key}: {len(value) if isinstance(value, list) else 'present'}")
        else:
            print("Empty filter (matches all)")
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("MongoDB-Style Filter System Demo")
    print("Showing how queries translate to SQLite and Qdrant")
    print("="*60)
    
    # Demo 1: Simple equality
    demo_query(
        "Simple Equality Filter",
        {"type": "alert", "priority": 5}
    )
    
    # Demo 2: Comparison operators
    demo_query(
        "Range Query with Comparisons",
        {
            "priority": {"$gte": 3, "$lt": 8},
            "confidence": {"$gt": 0.7}
        }
    )
    
    # Demo 3: Array operations
    demo_query(
        "Array Operations",
        {
            "tags": {"$contains": "urgent"},
            "categories": {"$all": ["security", "critical"]},
            "attachments": {"$size": 3}
        }
    )
    
    # Demo 4: Logical operators
    demo_query(
        "Complex Logical Query",
        {
            "$and": [
                {"channel_id": {"$in": ["general", "alerts"]}},
                {"$or": [
                    {"priority": {"$gte": 7}},
                    {"tags": {"$contains": "urgent"}}
                ]},
                {"processed": {"$ne": True}}
            ]
        }
    )
    
    # Demo 5: Existence checks
    demo_query(
        "Existence and Null Checks",
        {
            "metadata": {"$exists": True},
            "error": {"$null": True},
            "description": {"$empty": False}
        }
    )
    
    # Demo 6: Text search
    demo_query(
        "Text Search Query",
        {
            "content": {"$regex": "error.*critical"},
            "$or": [
                {"title": {"$text": "database"}},
                {"description": {"$text": "connection"}}
            ]
        }
    )
    
    # Demo 7: Nested metadata
    demo_query(
        "Nested Metadata Query",
        {
            "user.tier": {"$in": ["premium", "enterprise"]},
            "metrics.response_time": {"$lt": 500},
            "flags.reviewed": True,
            "timestamp": {"$between": ["2024-01-01", "2024-12-31"]}
        }
    )
    
    print("\n" + "="*60)
    print("Demo Complete!")
    print("="*60)
    print("\nKey Benefits of Shared Abstraction:")
    print("1. ✅ Write query once, use everywhere")
    print("2. ✅ Consistent behavior across backends")
    print("3. ✅ Type-safe and validated")
    print("4. ✅ Easy to extend with new operators")
    print("5. ✅ No code duplication")
    print("6. ✅ Backend-specific optimizations possible")


if __name__ == "__main__":
    main()