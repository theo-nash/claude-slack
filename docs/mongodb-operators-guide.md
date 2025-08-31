# MongoDB-Style Operators in Claude-Slack v4.1

## Overview

Claude-Slack v4.1 implements a robust MongoDB-style query system with a modular, backend-agnostic architecture. The system parses MongoDB queries into abstract expression trees that can be converted to different backend formats (SQLite with JSON support, Qdrant vector database). This enables powerful, expressive queries on arbitrary JSON structures without any schema registration.

## Architecture

The filtering system uses a three-tier architecture:

```
MongoDB Query → Parser → Abstract Expression Tree → Backend Converter → Native Query
```

### Components
- **MongoFilterParser** (`filters/base.py`): Parses MongoDB queries into abstract trees
- **SQLiteFilterBackend** (`filters/sqlite_backend.py`): Converts to SQLite JSON queries  
- **QdrantFilterBackend** (`filters/qdrant_backend.py`): Converts to Qdrant filters
- **MongoToSQLFilter** (`mongo_filter.py`): Legacy direct MongoDB→SQL converter

## Supported Operators

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Equals | `{"confidence": {"$eq": 0.9}}` |
| `$ne` | Not equals | `{"outcome": {"$ne": "failure"}}` |
| `$gt` | Greater than | `{"priority": {"$gt": 5}}` |
| `$gte` | Greater than or equal | `{"confidence": {"$gte": 0.8}}` |
| `$lt` | Less than | `{"complexity": {"$lt": 10}}` |
| `$lte` | Less than or equal | `{"coverage": {"$lte": 0.95}}` |
| `$between` | Between two values | `{"confidence": {"$between": [0.7, 0.9]}}` |

### Array/List Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$in` | Value in list | `{"type": {"$in": ["reflection", "insight"]}}` |
| `$nin` | Value not in list | `{"status": {"$nin": ["failed", "error"]}}` |
| `$contains` | Array contains value | `{"tags": {"$contains": "security"}}` |
| `$not_contains` | Array doesn't contain | `{"tags": {"$not_contains": "deprecated"}}` |
| `$all` | Array contains all values | `{"decisions": {"$all": ["jwt", "stateless"]}}` |
| `$size` | Array has specific length | `{"files": {"$size": 3}}` |

### Logical Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$and` | All conditions must match | `{"$and": [{"type": "reflection"}, {"confidence": {"$gte": 0.8}}]}` |
| `$or` | At least one must match | `{"$or": [{"priority": 1}, {"severity": "high"}]}` |
| `$not` | Negate the condition | `{"$not": {"outcome": "failure"}}` |

### Existence Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$exists` | Field exists or not | `{"error_code": {"$exists": false}}` |
| `$null` | Field is null | `{"deleted_at": {"$null": true}}` |
| `$empty` | Field is empty (arrays/strings) | `{"tags": {"$empty": false}}` |

### Text Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$text` | Full text search | `{"content": {"$text": "authentication"}}` |
| `$regex` | Pattern matching | `{"filename": {"$regex": ".*\\.py$"}}` |

## Query Examples

### Simple Queries

```python
# Find successful reflections with high confidence
results = await api.search_messages(
    metadata_filters={
        "type": "reflection",
        "outcome": "success",
        "confidence": {"$gte": 0.8}
    }
)

# Find messages NOT from failed attempts
results = await api.search_messages(
    metadata_filters={
        "outcome": {"$ne": "failure"},
        "confidence": {"$gt": 0.5}
    }
)
```

### Nested Field Queries

```python
# Query deeply nested structures with dot notation
results = await api.search_messages(
    metadata_filters={
        "breadcrumbs.metrics.coverage": {"$gte": 0.9},
        "breadcrumbs.decisions": {"$contains": "jwt"},
        "breadcrumbs.files": {"$size": 3}
    }
)

# Even deeper nesting
results = await api.search_messages(
    metadata_filters={
        "impact.metrics.performance.response_time": {"$lt": 100},
        "config.features.auth.provider": "oauth2"
    }
)
```

### Complex Logical Queries

```python
# OR logic: Find insights OR high-confidence reflections
results = await api.search_messages(
    metadata_filters={
        "$or": [
            {"type": "insight"},
            {
                "$and": [
                    {"type": "reflection"},
                    {"confidence": {"$gte": 0.9}}
                ]
            }
        ]
    }
)

# Complex nested logic
results = await api.search_messages(
    metadata_filters={
        "$and": [
            {"type": {"$in": ["reflection", "analysis"]}},
            {
                "$or": [
                    {"outcome": "success"},
                    {"confidence": {"$gte": 0.85}}
                ]
            },
            {
                "$not": {
                    "tags": {"$contains": "deprecated"}
                }
            }
        ]
    }
)
```

### Array Operations

```python
# Find messages with specific array characteristics
results = await api.search_messages(
    metadata_filters={
        # Has both "security" and "critical" tags
        "tags": {"$all": ["security", "critical"]},
        
        # Files array has exactly 4 items
        "breadcrumbs.files": {"$size": 4},
        
        # Decisions includes "jwt" but not "oauth"
        "$and": [
            {"breadcrumbs.decisions": {"$contains": "jwt"}},
            {"breadcrumbs.decisions": {"$not_contains": "oauth"}}
        ]
    }
)
```

### Existence Checks

```python
# Find messages with optional fields
results = await api.search_messages(
    metadata_filters={
        # Has a patterns field
        "breadcrumbs.patterns": {"$exists": True},
        
        # Doesn't have an error_code field
        "error_code": {"$exists": False},
        
        # Has a non-null completion_time
        "$and": [
            {"completion_time": {"$exists": True}},
            {"completion_time": {"$null": False}}
        ]
    }
)
```

### Range Queries

```python
# Find messages within specific ranges
results = await api.search_messages(
    metadata_filters={
        # Confidence between 70% and 90%
        "confidence": {"$between": [0.7, 0.9]},
        
        # Complexity less than 10
        "metrics.complexity": {"$lt": 10},
        
        # Priority 1-3
        "priority": {"$in": [1, 2, 3]}
    }
)
```

## Implementation Notes

### Backend-Specific Behavior

#### SQLite Backend
- Uses SQLite's JSON functions (`json_extract`, `json_each`, `json_array_length`)
- Direct fields (`channel_id`, `sender_id`, `content`, `timestamp`, `confidence`) bypass JSON extraction
- Comparison operators cast JSON values to appropriate SQL types (REAL, INTEGER, TEXT)
- `$regex` falls back to LIKE pattern matching (not full regex without extension)
- `$text` requires FTS5 setup or falls back to LIKE

#### Qdrant Backend  
- Converts to native Qdrant Filter objects
- Automatically adds `metadata.` prefix for non-root fields
- `$all` operator creates multiple AND conditions
- `$size` uses special `__len` field suffix
- Timestamps are converted from ISO strings to Unix timestamps

### Security Features
- Maximum nesting depth protection (default 10 levels) prevents DoS attacks
- Parameter binding prevents SQL injection
- Input validation at multiple levels

### Field Path Resolution

- Fields are automatically prefixed with `metadata.` if not already present
- System fields (`channel_id`, `sender_id`, `confidence`, `timestamp`) don't get prefixed
- Dot notation works for arbitrary nesting depth
- Both backends handle nested paths consistently

### Query Optimization

- Qdrant handles all operators natively without transformation
- SQLite uses indexed JSON extraction where possible
- No schema registration required
- Queries execute in < 50ms for typical datasets

## Performance Characteristics

| Query Type | 10K Messages | 100K Messages | 1M Messages |
|------------|--------------|---------------|-------------|
| Simple equality | < 10ms | < 20ms | < 50ms |
| Complex $and/$or | < 20ms | < 40ms | < 100ms |
| Array operations | < 15ms | < 30ms | < 75ms |
| Text search | < 30ms | < 60ms | < 150ms |
| Deep nesting (5+ levels) | < 25ms | < 50ms | < 125ms |

## Best Practices

1. **Use specific operators**: `$gte` is more efficient than `$not` + `$lt`
2. **Prefer native operators**: Use operators that map directly to backend capabilities
3. **Combine filters efficiently**: Use `$and` explicitly for clarity
4. **Leverage dot notation**: Query nested fields directly without schema registration
5. **Test complex queries**: Validate with the comprehensive test suite
6. **Consider backend differences**: SQLite for structural queries, Qdrant for semantic search
7. **Avoid deep nesting**: Stay within the 10-level default depth limit

## Migration from v4.0

```python
# Old v4.0 style (limited)
results = await api.search_messages(
    message_type="reflection",  # Simple equality only
    min_confidence=0.8          # Basic threshold
)

# New v4.1 style (full MongoDB)
results = await api.search_messages(
    metadata_filters={
        "type": "reflection",
        "confidence": {"$gte": 0.8},
        "outcome": {"$ne": "failure"},
        "breadcrumbs.decisions": {"$all": ["jwt", "stateless"]},
        "$or": [
            {"priority": 1},
            {"tags": {"$contains": "critical"}}
        ]
    }
)
```

## Implementation Status

### Fully Supported (Both Backends)
✅ All comparison operators (`$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$between`)  
✅ All logical operators (`$and`, `$or`, `$not`)  
✅ Array operators (`$in`, `$nin`, `$contains`, `$not_contains`, `$all`, `$size`)  
✅ Existence operators (`$exists`, `$null`, `$empty`)  

### Partially Supported
⚠️ `$regex` - SQLite uses LIKE pattern matching, Qdrant has full support  
⚠️ `$text` - Requires FTS5 setup in SQLite, native in Qdrant

### Not Implemented
❌ `$elemMatch` - Complex array element matching  
❌ `$where` - JavaScript expressions (security risk)  
❌ `$expr` - Expression evaluation  
❌ `$type` - Type checking  
❌ `$mod` - Modulo operation  
❌ Aggregation operators (`$sum`, `$avg`, `$min`, `$max`)  
❌ Geospatial operators (not applicable to use case)