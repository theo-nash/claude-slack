# MongoDB-Style Filtering for SQLiteStore

## Overview
Port the sophisticated MongoDB-style query filtering from QdrantStore to SQLiteStore, enabling complex metadata queries with nested conditions and operators.

## Current State Analysis

### QdrantStore Implementation
- **Operators Supported:**
  - Comparison: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`
  - Array/List: `$in`, `$nin`, `$contains`, `$not_contains`, `$all`, `$size`
  - Logical: `$and`, `$or`, `$not`
  - Existence: `$exists`, `$null`
  - Text: `$regex`, `$text`
  - Special: `$empty`, `$between`

- **Architecture:**
  1. `_build_filter()` - Main entry point
  2. `_parse_metadata_filters()` - Recursive parser for logical operators
  3. `_parse_field_condition()` - Individual field condition parser
  4. Returns structured conditions (must/should/must_not)

### SQLiteStore Current Limitations
- Basic filtering only (channel_ids, message_type, min_confidence, since)
- Post-query filtering in Python (inefficient)
- No support for complex metadata queries
- No logical operators

## Implementation Design

### 1. SQL Query Builder Architecture

```python
class SQLiteFilterBuilder:
    """Builds SQL WHERE clauses from MongoDB-style filters"""
    
    def build_where_clause(self, metadata_filters: Dict[str, Any]) -> Tuple[str, List]:
        """
        Convert MongoDB-style filters to SQL WHERE clause
        Returns: (where_clause, params)
        """
        conditions = self._parse_filters(metadata_filters)
        return self._conditions_to_sql(conditions)
```

### 2. Key Challenges & Solutions

#### A. JSON Metadata Access in SQLite
SQLite stores metadata as JSON strings. We need to use SQLite's JSON functions:

```sql
-- Access nested field: metadata.breadcrumbs.files
json_extract(metadata, '$.breadcrumbs.files')

-- Array length for $size operator
json_array_length(json_extract(metadata, '$.breadcrumbs.files'))

-- Check if field exists
json_type(json_extract(metadata, '$.field')) IS NOT NULL
```

#### B. Operator Mapping

| MongoDB Operator | SQLite Implementation |
|-----------------|----------------------|
| `$eq` | `json_extract(metadata, '$.field') = ?` |
| `$ne` | `json_extract(metadata, '$.field') != ?` |
| `$gt` | `CAST(json_extract(metadata, '$.field') AS REAL) > ?` |
| `$in` | `json_extract(metadata, '$.field') IN (?, ?, ?)` |
| `$contains` | `EXISTS (SELECT 1 FROM json_each(json_extract(metadata, '$.field')) WHERE value = ?)` |
| `$size` | `json_array_length(json_extract(metadata, '$.field')) = ?` |
| `$exists` | `json_type(json_extract(metadata, '$.field')) IS NOT NULL` |
| `$regex` | `json_extract(metadata, '$.field') REGEXP ?` |
| `$and` | `(condition1 AND condition2 AND ...)` |
| `$or` | `(condition1 OR condition2 OR ...)` |
| `$not` | `NOT (condition)` |

#### C. Type Handling
SQLite JSON values need type casting for numeric comparisons:

```python
def _get_json_extract(self, field_path: str, cast_type: Optional[str] = None) -> str:
    """Generate JSON extract with optional type casting"""
    extract = f"json_extract(metadata, '$.{field_path}')"
    if cast_type:
        return f"CAST({extract} AS {cast_type})"
    return extract
```

### 3. Implementation Steps

#### Phase 1: Core Filter Builder
```python
class MongoToSQLFilter:
    def __init__(self):
        self.param_index = 0
        self.params = []
    
    def parse(self, filters: Dict) -> Tuple[str, List]:
        """Main entry point"""
        sql = self._parse_dict(filters)
        return sql, self.params
    
    def _parse_dict(self, filters: Dict) -> str:
        """Parse a dictionary of filters"""
        conditions = []
        for key, value in filters.items():
            if key.startswith('$'):
                # Logical operator
                conditions.append(self._parse_logical(key, value))
            else:
                # Field condition
                conditions.append(self._parse_field(key, value))
        return ' AND '.join(conditions) if conditions else '1=1'
```

#### Phase 2: Enhanced search_messages()
```python
async def search_messages_advanced(self, conn,
                                  agent_name: str,
                                  agent_project_id: Optional[str],
                                  query: Optional[str] = None,
                                  metadata_filters: Optional[Dict[str, Any]] = None,
                                  channel_ids: Optional[List[str]] = None,
                                  sender_ids: Optional[List[str]] = None,
                                  min_confidence: Optional[float] = None,
                                  limit: int = 50) -> List[Dict]:
    """
    Advanced search with MongoDB-style filtering
    """
    # Build base query
    query_parts = []
    params = []
    
    # Add metadata filters
    if metadata_filters:
        filter_sql, filter_params = MongoToSQLFilter().parse(metadata_filters)
        query_parts.append(filter_sql)
        params.extend(filter_params)
    
    # Build final query
    where_clause = ' AND '.join(query_parts) if query_parts else '1=1'
    
    sql = f"""
        SELECT m.*, c.name as channel_name
        FROM messages m
        INNER JOIN channels c ON m.channel_id = c.id
        WHERE {where_clause}
        ORDER BY m.timestamp DESC
        LIMIT ?
    """
    params.append(limit)
    
    # Execute and return
    cursor = await conn.execute(sql, params)
    return await cursor.fetchall()
```

### 4. Performance Considerations

#### Indexing Strategy
```sql
-- Create indexes for frequently queried JSON paths
CREATE INDEX idx_messages_metadata_type 
ON messages(json_extract(metadata, '$.type'));

CREATE INDEX idx_messages_metadata_priority 
ON messages(json_extract(metadata, '$.priority'));

-- Composite index for common queries
CREATE INDEX idx_messages_channel_timestamp 
ON messages(channel_id, timestamp DESC);
```

#### Query Optimization
1. Push filters to SQL level (avoid Python post-processing)
2. Use EXISTS for array operations (more efficient than json_each)
3. Limit JSON parsing to necessary fields
4. Consider materialized views for complex queries

### 5. Testing Strategy

#### Unit Tests
```python
def test_eq_operator():
    """Test $eq operator conversion"""
    filters = {"type": {"$eq": "alert"}}
    sql, params = MongoToSQLFilter().parse(filters)
    assert sql == "json_extract(metadata, '$.type') = ?"
    assert params == ["alert"]

def test_nested_and_or():
    """Test nested $and/$or operators"""
    filters = {
        "$and": [
            {"type": "alert"},
            {"$or": [
                {"priority": {"$gte": 5}},
                {"urgent": True}
            ]}
        ]
    }
    # Verify correct SQL generation
```

#### Integration Tests
- Test with real SQLite database
- Verify results match QdrantStore behavior
- Performance benchmarks
- Edge cases (null values, missing fields, type mismatches)

### 6. Migration Path

1. **Add new method**: `search_messages_advanced()` alongside existing
2. **Parallel testing**: Run both methods, compare results
3. **Performance validation**: Ensure new method doesn't degrade performance
4. **Gradual migration**: Update callers one by one
5. **Deprecate old method**: After validation period

### 7. Example Usage

```python
# Simple equality
filters = {"type": "alert", "priority": 5}

# Complex nested query
filters = {
    "$and": [
        {"channel_id": {"$in": ["general", "alerts"]}},
        {"$or": [
            {"priority": {"$gte": 7}},
            {"tags": {"$contains": "urgent"}}
        ]},
        {"processed": {"$ne": True}}
    ]
}

# Array operations
filters = {
    "mentions": {"$size": 3},
    "tags": {"$all": ["security", "critical"]},
    "attachments": {"$exists": True}
}

# Text search with metadata
results = await db.search_messages_advanced(
    agent_name="monitor",
    agent_project_id=None,
    query="error",  # FTS query
    metadata_filters={
        "severity": {"$gte": 4},
        "resolved": {"$ne": True}
    },
    limit=100
)
```

### 8. Error Handling

```python
class FilterError(Exception):
    """Raised when filter parsing fails"""
    pass

def _validate_operator(self, op: str):
    """Validate MongoDB operator"""
    valid_ops = {'$eq', '$ne', '$gt', '$gte', '$lt', '$lte', ...}
    if op not in valid_ops:
        raise FilterError(f"Unknown operator: {op}")
```

### 9. Security Considerations

1. **SQL Injection Prevention**: Always use parameterized queries
2. **Input Validation**: Validate all operators and field paths
3. **Depth Limits**: Prevent DoS via deeply nested queries
4. **Field Access Control**: Consider restricting certain metadata fields

### 10. Future Enhancements

- **Aggregation Pipeline**: Support for `$group`, `$sum`, etc.
- **Geospatial Queries**: If location data is stored
- **Full-Text + Metadata**: Combine FTS with metadata filters efficiently
- **Query Caching**: Cache compiled queries for repeated patterns
- **Query Explain**: Debug interface showing SQL generation