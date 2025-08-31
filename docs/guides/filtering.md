# Filtering Guide

Query your messages and notes with powerful MongoDB-style filters.

## Quick Examples

### Find High-Confidence Solutions
```python
results = search_messages(
    metadata_filters={
        "confidence": {"$gte": 0.8},
        "outcome": "success"
    }
)
```

### Find Recent Critical Issues
```python
results = search_messages(
    metadata_filters={
        "priority": {"$in": [1, 2]},
        "tags": {"$contains": "critical"}
    }
)
```

### Complex Query
```python
results = search_messages(
    metadata_filters={
        "$and": [
            {"type": "reflection"},
            {"$or": [
                {"confidence": {"$gte": 0.9}},
                {"tags": {"$contains": "verified"}}
            ]}
        ]
    }
)
```

## Common Patterns

### 1. Filter by Type and Confidence
```python
# Find high-quality reflections
results = search_messages(
    metadata_filters={
        "type": "reflection",        # Exact match
        "confidence": {"$gte": 0.7}  # Greater than or equal
    }
)
```

### 2. Search Within Arrays
```python
# Find messages with specific tags
results = search_messages(
    metadata_filters={
        "tags": {"$contains": "security"}  # Array contains
    }
)

# Find messages with ALL specified tags
results = search_messages(
    metadata_filters={
        "tags": {"$all": ["security", "critical"]}
    }
)
```

### 3. Nested Field Access
```python
# Query nested JSON with dot notation
results = search_messages(
    metadata_filters={
        "breadcrumbs.decisions": {"$contains": "jwt"},
        "breadcrumbs.metrics.coverage": {"$gte": 0.9}
    }
)
```

### 4. OR Logic
```python
# Find insights OR high-confidence reflections
results = search_messages(
    metadata_filters={
        "$or": [
            {"type": "insight"},
            {
                "type": "reflection",
                "confidence": {"$gte": 0.9}
            }
        ]
    }
)
```

### 5. Exclude Certain Results
```python
# Find all except failed attempts
results = search_messages(
    metadata_filters={
        "outcome": {"$ne": "failure"},     # Not equal
        "tags": {"$nin": ["deprecated", "obsolete"]}  # Not in list
    }
)
```

## Operator Quick Reference

### Comparison
| Operator | Meaning | Example |
|----------|---------|---------|
| `$eq` | Equals | `{"status": {"$eq": "active"}}` |
| `$ne` | Not equals | `{"status": {"$ne": "failed"}}` |
| `$gt` | Greater than | `{"priority": {"$gt": 5}}` |
| `$gte` | Greater or equal | `{"confidence": {"$gte": 0.8}}` |
| `$lt` | Less than | `{"errors": {"$lt": 3}}` |
| `$lte` | Less or equal | `{"latency": {"$lte": 100}}` |

### Arrays
| Operator | Meaning | Example |
|----------|---------|---------|
| `$in` | Value in list | `{"status": {"$in": ["active", "pending"]}}` |
| `$nin` | Not in list | `{"env": {"$nin": ["prod", "staging"]}}` |
| `$contains` | Array contains | `{"tags": {"$contains": "urgent"}}` |
| `$all` | Has all values | `{"skills": {"$all": ["python", "docker"]}}` |
| `$size` | Array length | `{"attachments": {"$size": 3}}` |

### Logical
| Operator | Meaning | Example |
|----------|---------|---------|
| `$and` | All conditions | `{"$and": [cond1, cond2]}` |
| `$or` | Any condition | `{"$or": [cond1, cond2]}` |
| `$not` | Negate | `{"$not": {"status": "failed"}}` |

### Existence
| Operator | Meaning | Example |
|----------|---------|---------|
| `$exists` | Field exists | `{"error": {"$exists": false}}` |
| `$null` | Is null | `{"deleted_at": {"$null": true}}` |

## Real-World Examples

### Find Debugging Information
```python
# Recent errors in production
debugging_info = search_messages(
    metadata_filters={
        "$and": [
            {"environment": "production"},
            {"$or": [
                {"level": "error"},
                {"tags": {"$contains": "bug"}}
            ]},
            {"resolved": {"$ne": true}}
        ]
    },
    ranking_profile="recent"  # Focus on recent issues
)
```

### Find Best Practices
```python
# High-quality architectural decisions
best_practices = search_messages(
    metadata_filters={
        "type": {"$in": ["decision", "reflection"]},
        "confidence": {"$gte": 0.85},
        "breadcrumbs.patterns": {"$exists": true}
    },
    ranking_profile="quality"
)
```

### Track Feature Progress
```python
# Find all work on a specific feature
feature_work = search_messages(
    metadata_filters={
        "$or": [
            {"feature": "payment-gateway"},
            {"tags": {"$contains": "payments"}},
            {"breadcrumbs.files": {"$contains": "payment"}}
        ]
    }
)
```

### Performance Metrics
```python
# Find performance improvements
improvements = search_messages(
    metadata_filters={
        "type": "optimization",
        "metrics.improvement_percent": {"$gt": 20},
        "metrics.response_time_ms": {"$lt": 100}
    }
)
```

## Combining with Semantic Search

Filters work perfectly with semantic search:

```python
# Semantic query + structured filters
results = search_messages(
    query="How to handle authentication",  # Semantic
    semantic_search=True,
    metadata_filters={                     # Structured
        "confidence": {"$gte": 0.7},
        "tags": {"$nin": ["deprecated"]},
        "outcome": "success"
    },
    ranking_profile="quality"
)
```

## Tips for Effective Filtering

### 1. Start Simple
```python
# Start with basic filters
filters = {"type": "reflection"}

# Then add complexity
filters = {
    "type": "reflection",
    "confidence": {"$gte": 0.8}
}
```

### 2. Use Dot Notation for Nested Fields
```python
# Access nested fields directly
filters = {
    "breadcrumbs.decisions": {"$contains": "redis"},
    "metrics.performance.latency": {"$lt": 50}
}
```

### 3. Combine Operators Logically
```python
# Clear, readable logic
filters = {
    "$and": [
        {"environment": "production"},  # Must be production
        {"$or": [                       # AND either of these
            {"priority": 1},
            {"severity": "critical"}
        ]}
    ]
}
```

### 4. Filter Before Semantic Search
```python
# Efficient: Filter first, then semantic search
results = search_messages(
    query="deployment strategies",
    metadata_filters={
        "type": "decision",        # Reduce dataset first
        "tags": {"$contains": "architecture"}
    },
    semantic_search=True
)
```

## Common Mistakes to Avoid

### ❌ Wrong: Forgetting $ prefix
```python
# This won't work as expected
filters = {"confidence": {"gte": 0.8}}  # Missing $
```

### ✅ Correct: Include $ prefix
```python
filters = {"confidence": {"$gte": 0.8}}
```

### ❌ Wrong: Mixing levels
```python
# Confusing structure
filters = {
    "type": "reflection",
    "$and": [...]  # Mixing field and operator at same level
}
```

### ✅ Correct: Proper nesting
```python
filters = {
    "$and": [
        {"type": "reflection"},
        # Other conditions...
    ]
}
```

## Performance Notes

- Filters execute in < 50ms for 100k messages
- Index commonly filtered fields for speed
- Complex nested queries still performant
- No schema registration required

## Related Documentation

- [Semantic Search](semantic-search.md) - AI-powered search
- [MongoDB Operators Reference](../reference/mongodb-operators.md) - Full operator list
- [API Reference](../reference/api/search.md) - Complete API docs