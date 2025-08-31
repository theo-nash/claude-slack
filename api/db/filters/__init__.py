"""
MongoDB-style filter system for multiple backends.

This module provides a unified way to express complex queries using MongoDB syntax
and convert them to different database backends (SQLite, Qdrant, etc.).

Example usage:
    from api.db.filters import MongoFilterParser, SQLiteFilterBackend
    
    # Parse MongoDB-style filter
    parser = MongoFilterParser()
    expression = parser.parse({
        "$and": [
            {"type": "alert"},
            {"priority": {"$gte": 5}},
            {"$or": [
                {"status": "active"},
                {"urgent": True}
            ]}
        ]
    })
    
    # Convert to SQLite
    sqlite_backend = SQLiteFilterBackend()
    where_clause, params = sqlite_backend.convert(expression)
"""

from .base import (
    FilterOperator,
    FilterCondition,
    FilterExpression,
    MongoFilterParser,
    FilterBackend,
    FilterError,
    UnsupportedOperatorError,
    InvalidFilterError
)

from .sqlite_backend import SQLiteFilterBackend
from .qdrant_backend import QdrantFilterBackend
from .validator import FilterValidator, FieldType

__all__ = [
    # Core classes
    'FilterOperator',
    'FilterCondition',
    'FilterExpression',
    'MongoFilterParser',
    'FilterBackend',
    
    # Backends
    'SQLiteFilterBackend',
    'QdrantFilterBackend',
    
    # Validation
    'FilterValidator',
    'FieldType',
    
    # Errors
    'FilterError',
    'UnsupportedOperatorError',
    'InvalidFilterError'
]