#!/usr/bin/env python3
"""
MongoDB-style filter to SQL converter for SQLite.
Converts MongoDB query operators to SQLite JSON queries.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime


class MongoToSQLFilter:
    """
    Converts MongoDB-style filters to SQLite WHERE clauses.
    
    Supports:
    - Comparison: $eq, $ne, $gt, $gte, $lt, $lte
    - Array/List: $in, $nin, $contains, $not_contains, $all, $size
    - Logical: $and, $or, $not
    - Existence: $exists, $null, $empty
    - Text: $regex, $text
    - Special: $between
    """
    
    # Valid MongoDB operators
    COMPARISON_OPS = {'$eq', '$ne', '$gt', '$gte', '$lt', '$lte'}
    ARRAY_OPS = {'$in', '$nin', '$contains', '$not_contains', '$all', '$size'}
    LOGICAL_OPS = {'$and', '$or', '$not'}
    EXISTENCE_OPS = {'$exists', '$null', '$empty'}
    TEXT_OPS = {'$regex', '$text'}
    SPECIAL_OPS = {'$between'}
    
    ALL_OPS = COMPARISON_OPS | ARRAY_OPS | LOGICAL_OPS | EXISTENCE_OPS | TEXT_OPS | SPECIAL_OPS
    
    def __init__(self, 
                 metadata_column: str = 'metadata',
                 use_fts: bool = False,
                 max_depth: int = 10):
        """
        Initialize the filter converter.
        
        Args:
            metadata_column: Name of the JSON column (default: 'metadata')
            use_fts: Whether to use FTS for text searches
            max_depth: Maximum nesting depth to prevent DoS
        """
        self.metadata_column = metadata_column
        self.use_fts = use_fts
        self.max_depth = max_depth
        self.params: List[Any] = []
        self.depth = 0
    
    def parse(self, filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Parse MongoDB-style filters into SQL WHERE clause.
        
        Args:
            filters: MongoDB-style filter dictionary
            
        Returns:
            Tuple of (where_clause, params)
        """
        self.params = []
        self.depth = 0
        
        if not filters:
            return "1=1", []
        
        sql = self._parse_dict(filters)
        return sql, self.params
    
    def _parse_dict(self, filters: Dict[str, Any]) -> str:
        """Parse a dictionary of filters."""
        self.depth += 1
        if self.depth > self.max_depth:
            raise ValueError(f"Filter nesting exceeds maximum depth of {self.max_depth}")
        
        try:
            conditions = []
            
            for key, value in filters.items():
                if key.startswith('$'):
                    # Logical operator at top level
                    if key not in self.LOGICAL_OPS:
                        raise ValueError(f"Unknown operator: {key}")
                    conditions.append(self._parse_logical(key, value))
                else:
                    # Field condition
                    conditions.append(self._parse_field(key, value))
            
            result = f"({' AND '.join(conditions)})" if conditions else "1=1"
            return result
            
        finally:
            self.depth -= 1
    
    def _parse_logical(self, operator: str, value: Any) -> str:
        """Parse logical operators ($and, $or, $not)."""
        if operator == '$and':
            if not isinstance(value, list):
                raise ValueError(f"${operator} requires a list")
            
            conditions = []
            for condition in value:
                if not isinstance(condition, dict):
                    raise ValueError(f"${operator} conditions must be dictionaries")
                conditions.append(self._parse_dict(condition))
            
            return f"({' AND '.join(conditions)})" if conditions else "1=1"
        
        elif operator == '$or':
            if not isinstance(value, list):
                raise ValueError(f"${operator} requires a list")
            
            conditions = []
            for condition in value:
                if not isinstance(condition, dict):
                    raise ValueError(f"${operator} conditions must be dictionaries")
                conditions.append(self._parse_dict(condition))
            
            return f"({' OR '.join(conditions)})" if conditions else "0=1"
        
        elif operator == '$not':
            if not isinstance(value, dict):
                raise ValueError(f"${operator} requires a dictionary")
            
            inner_condition = self._parse_dict(value)
            return f"NOT ({inner_condition})"
        
        else:
            raise ValueError(f"Unknown logical operator: {operator}")
    
    def _parse_field(self, field_path: str, value: Any) -> str:
        """Parse a field condition."""
        # Check if value contains operators
        if isinstance(value, dict) and any(k.startswith('$') for k in value):
            # Parse operators
            return self._parse_field_operators(field_path, value)
        else:
            # Direct equality
            return self._build_equality(field_path, value)
    
    def _parse_field_operators(self, field_path: str, operators: Dict[str, Any]) -> str:
        """Parse field-level operators."""
        conditions = []
        
        for op, op_value in operators.items():
            if op not in self.ALL_OPS:
                raise ValueError(f"Unknown operator: {op}")
            
            # Comparison operators
            if op == '$eq':
                conditions.append(self._build_equality(field_path, op_value))
            
            elif op == '$ne':
                conditions.append(f"NOT ({self._build_equality(field_path, op_value)})")
            
            elif op == '$gt':
                json_path = self._get_json_extract(field_path, self._infer_type(op_value))
                self.params.append(op_value)
                conditions.append(f"{json_path} > ?")
            
            elif op == '$gte':
                json_path = self._get_json_extract(field_path, self._infer_type(op_value))
                self.params.append(op_value)
                conditions.append(f"{json_path} >= ?")
            
            elif op == '$lt':
                json_path = self._get_json_extract(field_path, self._infer_type(op_value))
                self.params.append(op_value)
                conditions.append(f"{json_path} < ?")
            
            elif op == '$lte':
                json_path = self._get_json_extract(field_path, self._infer_type(op_value))
                self.params.append(op_value)
                conditions.append(f"{json_path} <= ?")
            
            # Array operators
            elif op == '$in':
                if not isinstance(op_value, list):
                    op_value = [op_value]
                json_path = self._get_json_extract(field_path)
                placeholders = ','.join(['?' for _ in op_value])
                self.params.extend(op_value)
                conditions.append(f"{json_path} IN ({placeholders})")
            
            elif op == '$nin':
                if not isinstance(op_value, list):
                    op_value = [op_value]
                json_path = self._get_json_extract(field_path)
                placeholders = ','.join(['?' for _ in op_value])
                self.params.extend(op_value)
                conditions.append(f"{json_path} NOT IN ({placeholders})")
            
            elif op == '$contains':
                # Check if array contains value
                json_path = self._get_json_extract(field_path)
                self.params.append(json.dumps(op_value) if not isinstance(op_value, str) else op_value)
                conditions.append(
                    f"EXISTS (SELECT 1 FROM json_each({json_path}) WHERE value = ?)"
                )
            
            elif op == '$not_contains':
                # Check if array doesn't contain value
                json_path = self._get_json_extract(field_path)
                self.params.append(json.dumps(op_value) if not isinstance(op_value, str) else op_value)
                conditions.append(
                    f"NOT EXISTS (SELECT 1 FROM json_each({json_path}) WHERE value = ?)"
                )
            
            elif op == '$all':
                # All values must be present
                if not isinstance(op_value, list):
                    raise ValueError(f"${op} requires a list")
                json_path = self._get_json_extract(field_path)
                all_conditions = []
                for val in op_value:
                    self.params.append(json.dumps(val) if not isinstance(val, str) else val)
                    all_conditions.append(
                        f"EXISTS (SELECT 1 FROM json_each({json_path}) WHERE value = ?)"
                    )
                conditions.append(f"({' AND '.join(all_conditions)})")
            
            elif op == '$size':
                # Array size check
                json_path = self._get_json_extract(field_path)
                self.params.append(op_value)
                conditions.append(f"json_array_length({json_path}) = ?")
            
            # Existence operators
            elif op == '$exists':
                json_path = self._get_json_extract(field_path)
                if op_value:
                    conditions.append(f"json_type({json_path}) IS NOT NULL")
                else:
                    conditions.append(f"json_type({json_path}) IS NULL")
            
            elif op == '$null':
                json_path = self._get_json_extract(field_path)
                conditions.append(f"json_type({json_path}) = 'null'")
            
            elif op == '$empty':
                json_path = self._get_json_extract(field_path)
                # Check for empty array or empty string
                conditions.append(
                    f"(json_array_length({json_path}) = 0 OR {json_path} = '')"
                )
            
            # Text operators
            elif op == '$regex':
                json_path = self._get_json_extract(field_path)
                # SQLite REGEXP requires loading extension or using LIKE
                # We'll use LIKE with % wildcards for basic pattern matching
                pattern = op_value.replace('%', '\\%').replace('_', '\\_')
                pattern = f"%{pattern}%"
                self.params.append(pattern)
                conditions.append(f"{json_path} LIKE ? ESCAPE '\\'")
            
            elif op == '$text':
                # Full text search
                if self.use_fts:
                    # Assume FTS table exists
                    self.params.append(op_value)
                    conditions.append(f"content MATCH ?")
                else:
                    # Fallback to LIKE
                    json_path = self._get_json_extract(field_path)
                    pattern = f"%{op_value}%"
                    self.params.append(pattern)
                    conditions.append(f"{json_path} LIKE ?")
            
            # Special operators
            elif op == '$between':
                if not isinstance(op_value, list) or len(op_value) != 2:
                    raise ValueError(f"${op} requires a list of two values")
                json_path = self._get_json_extract(field_path, self._infer_type(op_value[0]))
                self.params.extend(op_value)
                conditions.append(f"{json_path} BETWEEN ? AND ?")
        
        return f"({' AND '.join(conditions)})" if conditions else "1=1"
    
    def _build_equality(self, field_path: str, value: Any) -> str:
        """Build an equality condition."""
        json_path = self._get_json_extract(field_path)
        
        if value is None:
            return f"json_type({json_path}) = 'null'"
        elif isinstance(value, bool):
            # SQLite stores booleans as 0/1 in JSON
            self.params.append(1 if value else 0)
            return f"{json_path} = ?"
        elif isinstance(value, (int, float)):
            self.params.append(value)
            return f"CAST({json_path} AS REAL) = ?"
        elif isinstance(value, str):
            self.params.append(value)
            return f"{json_path} = ?"
        elif isinstance(value, (list, dict)):
            # For complex types, compare as JSON strings
            self.params.append(json.dumps(value))
            return f"json({json_path}) = json(?)"
        else:
            # Convert to string for comparison
            self.params.append(str(value))
            return f"{json_path} = ?"
    
    def _get_json_extract(self, field_path: str, cast_type: Optional[str] = None) -> str:
        """
        Generate JSON extract expression.
        
        Args:
            field_path: Dot-separated path (e.g., "user.name")
            cast_type: Optional SQL type to cast to ('REAL', 'INTEGER', 'TEXT')
        """
        # Handle special root fields that aren't in metadata
        root_fields = {'id', 'channel_id', 'sender_id', 'sender_project_id', 
                      'content', 'timestamp', 'confidence', 'thread_id'}
        
        if field_path in root_fields:
            # Direct column access
            if cast_type:
                return f"CAST({field_path} AS {cast_type})"
            return field_path
        
        # Convert dot notation to JSON path
        json_path = '$.' + field_path
        extract = f"json_extract({self.metadata_column}, '{json_path}')"
        
        if cast_type:
            return f"CAST({extract} AS {cast_type})"
        return extract
    
    def _infer_type(self, value: Any) -> Optional[str]:
        """Infer SQL type for casting."""
        if isinstance(value, bool):
            return 'INTEGER'
        elif isinstance(value, int):
            return 'INTEGER'
        elif isinstance(value, float):
            return 'REAL'
        elif isinstance(value, str):
            # Check if it looks like a number
            try:
                float(value)
                return 'REAL'
            except ValueError:
                return 'TEXT'
        return None


class SQLiteAdvancedSearch:
    """
    Advanced search capabilities for SQLite with MongoDB-style filtering.
    """
    
    def __init__(self, metadata_column: str = 'metadata'):
        """
        Initialize advanced search.
        
        Args:
            metadata_column: Name of the JSON metadata column
        """
        self.filter_converter = MongoToSQLFilter(metadata_column=metadata_column)
    
    def build_search_query(self,
                          base_table: str = 'messages',
                          text_query: Optional[str] = None,
                          metadata_filters: Optional[Dict[str, Any]] = None,
                          channel_ids: Optional[List[str]] = None,
                          sender_ids: Optional[List[str]] = None,
                          min_confidence: Optional[float] = None,
                          since: Optional[datetime] = None,
                          until: Optional[datetime] = None,
                          order_by: str = 'timestamp DESC',
                          limit: int = 100) -> Tuple[str, List[Any]]:
        """
        Build a complete search query with all filters.
        
        Returns:
            Tuple of (sql_query, params)
        """
        where_conditions = []
        params = []
        
        # Text search (if using FTS)
        if text_query:
            where_conditions.append(f"m.id IN (SELECT rowid FROM {base_table}_fts WHERE content MATCH ?)")
            params.append(text_query)
        
        # Channel filter
        if channel_ids:
            placeholders = ','.join(['?' for _ in channel_ids])
            where_conditions.append(f"m.channel_id IN ({placeholders})")
            params.extend(channel_ids)
        
        # Sender filter
        if sender_ids:
            placeholders = ','.join(['?' for _ in sender_ids])
            where_conditions.append(f"m.sender_id IN ({placeholders})")
            params.extend(sender_ids)
        
        # Confidence filter
        if min_confidence is not None:
            where_conditions.append("m.confidence >= ?")
            params.append(min_confidence)
        
        # Time range filters - convert to Unix timestamps
        if since:
            from api.utils.time_utils import to_timestamp
            where_conditions.append("m.timestamp >= ?")
            params.append(to_timestamp(since) if since else None)
        
        if until:
            from api.utils.time_utils import to_timestamp
            where_conditions.append("m.timestamp <= ?")
            params.append(to_timestamp(until) if until else None)
        
        # Metadata filters (MongoDB-style)
        if metadata_filters:
            filter_sql, filter_params = self.filter_converter.parse(metadata_filters)
            where_conditions.append(filter_sql)
            params.extend(filter_params)
        
        # Build complete query
        where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'
        
        sql = f"""
            SELECT m.*
            FROM {base_table} m
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(limit)
        
        return sql, params