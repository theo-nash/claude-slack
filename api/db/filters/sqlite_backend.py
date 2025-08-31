#!/usr/bin/env python3
"""
SQLite backend for MongoDB-style filters.
Converts FilterExpression trees to SQLite WHERE clauses with JSON support.
"""

import json
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime

from .base import (
    FilterBackend, FilterCondition, FilterExpression, 
    FilterOperator, UnsupportedOperatorError
)


class SQLiteFilterBackend(FilterBackend):
    """
    Converts FilterExpression trees to SQLite WHERE clauses.
    Handles JSON metadata fields using SQLite's JSON functions.
    """
    
    # Operators supported by SQLite
    SUPPORTED_OPERATORS = {
        FilterOperator.EQ, FilterOperator.NE,
        FilterOperator.GT, FilterOperator.GTE,
        FilterOperator.LT, FilterOperator.LTE,
        FilterOperator.IN, FilterOperator.NIN,
        FilterOperator.AND, FilterOperator.OR, FilterOperator.NOT,
        FilterOperator.EXISTS, FilterOperator.NULL,
        FilterOperator.BETWEEN,
        # These require special handling
        FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS,
        FilterOperator.ALL, FilterOperator.SIZE,
        FilterOperator.EMPTY, FilterOperator.REGEX,
        FilterOperator.TEXT
    }
    
    # Fields that are direct columns (not in JSON metadata)
    DIRECT_FIELDS = {
        'id', 'channel_id', 'sender_id', 'sender_project_id',
        'content', 'timestamp', 'confidence', 'thread_id'
    }
    
    def __init__(self, 
                 metadata_column: str = 'metadata',
                 table_alias: str = 'm',
                 use_fts: bool = False,
                 fts_column: str = 'content'):
        """
        Initialize SQLite backend.
        
        Args:
            metadata_column: Name of the JSON metadata column
            table_alias: Table alias to use in generated SQL
            use_fts: Whether to use FTS5 for text searches
            fts_column: Column to use for FTS searches
        """
        self.metadata_column = metadata_column
        self.table_alias = table_alias
        self.use_fts = use_fts
        self.fts_column = fts_column
        self.params: List[Any] = []
    
    def convert(self, expression: FilterExpression) -> Tuple[str, List[Any]]:
        """
        Convert FilterExpression to SQLite WHERE clause.
        
        Args:
            expression: The filter expression tree
            
        Returns:
            Tuple of (where_clause, params)
        """
        self.params = []
        
        # Empty expression matches everything
        if not expression.conditions:
            return "1=1", []
        
        # Validate all operators are supported
        self.validate_expression(expression)
        
        # Convert to SQL
        sql = self._convert_expression(expression)
        return sql, self.params
    
    def supports_operator(self, operator: FilterOperator) -> bool:
        """Check if SQLite backend supports an operator."""
        return operator in self.SUPPORTED_OPERATORS
    
    def _convert_expression(self, expr: Union[FilterExpression, FilterCondition]) -> str:
        """Convert an expression or condition to SQL."""
        if isinstance(expr, FilterCondition):
            return self._convert_condition(expr)
        elif isinstance(expr, FilterExpression):
            return self._convert_compound(expr)
        else:
            raise ValueError(f"Unknown expression type: {type(expr)}")
    
    def _convert_compound(self, expr: FilterExpression) -> str:
        """Convert compound expression (AND/OR/NOT)."""
        if expr.operator == FilterOperator.AND:
            if not expr.conditions:
                return "1=1"
            parts = [self._convert_expression(c) for c in expr.conditions]
            return f"({' AND '.join(parts)})"
        
        elif expr.operator == FilterOperator.OR:
            if not expr.conditions:
                return "0=1"
            parts = [self._convert_expression(c) for c in expr.conditions]
            return f"({' OR '.join(parts)})"
        
        elif expr.operator == FilterOperator.NOT:
            if not expr.conditions:
                return "1=1"
            inner = self._convert_expression(expr.conditions[0])
            return f"NOT ({inner})"
        
        else:
            # Non-compound expression with multiple conditions
            # Treat as AND
            parts = [self._convert_expression(c) for c in expr.conditions]
            return f"({' AND '.join(parts)})"
    
    def _convert_condition(self, condition: FilterCondition) -> str:
        """Convert a single condition to SQL."""
        field_ref = self._get_field_reference(condition.field)
        op = condition.operator
        value = condition.value
        
        # Handle each operator type
        if op == FilterOperator.EQ:
            return self._build_equality(field_ref, value, condition.negated)
        
        elif op == FilterOperator.NE:
            return self._build_equality(field_ref, value, not condition.negated)
        
        elif op in {FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE}:
            return self._build_comparison(field_ref, op, value, condition.negated)
        
        elif op == FilterOperator.IN:
            return self._build_in(field_ref, value, condition.negated)
        
        elif op == FilterOperator.NIN:
            return self._build_in(field_ref, value, not condition.negated)
        
        elif op == FilterOperator.EXISTS:
            return self._build_exists(field_ref, value, condition.negated)
        
        elif op == FilterOperator.NULL:
            return self._build_null(field_ref, condition.negated)
        
        elif op == FilterOperator.EMPTY:
            return self._build_empty(field_ref, condition.negated)
        
        elif op == FilterOperator.CONTAINS:
            return self._build_contains(field_ref, value, condition.negated)
        
        elif op == FilterOperator.NOT_CONTAINS:
            return self._build_contains(field_ref, value, not condition.negated)
        
        elif op == FilterOperator.ALL:
            return self._build_all(field_ref, value, condition.negated)
        
        elif op == FilterOperator.SIZE:
            return self._build_size(field_ref, value, condition.negated)
        
        elif op == FilterOperator.BETWEEN:
            return self._build_between(field_ref, value, condition.negated)
        
        elif op == FilterOperator.REGEX:
            return self._build_regex(field_ref, value, condition.negated)
        
        elif op == FilterOperator.TEXT:
            return self._build_text(condition.field, value, condition.negated)
        
        else:
            raise UnsupportedOperatorError(op, "SQLite")
    
    def _get_field_reference(self, field: str) -> str:
        """
        Get SQL reference for a field.
        Returns either a direct column reference or JSON extract.
        """
        if field in self.DIRECT_FIELDS:
            # Direct column
            return f"{self.table_alias}.{field}" if self.table_alias else field
        else:
            # JSON field
            json_path = '$.' + field
            base = f"{self.table_alias}.{self.metadata_column}" if self.table_alias else self.metadata_column
            return f"json_extract({base}, '{json_path}')"
    
    def _build_equality(self, field_ref: str, value: Any, negated: bool) -> str:
        """Build equality comparison."""
        if value is None:
            # NULL comparison
            op = "IS NOT" if negated else "IS"
            return f"{field_ref} {op} NULL"
        
        # Type-specific handling
        if isinstance(value, bool):
            # SQLite JSON stores booleans as 0/1
            self.params.append(1 if value else 0)
        elif isinstance(value, (int, float)):
            self.params.append(value)
            # Cast JSON fields to numeric for comparison
            if 'json_extract' in field_ref:
                field_ref = f"CAST({field_ref} AS REAL)"
        elif isinstance(value, (list, dict)):
            # Complex types - compare as JSON
            self.params.append(json.dumps(value))
            if 'json_extract' in field_ref:
                field_ref = f"json({field_ref})"
                return f"{field_ref} {'!=' if negated else '='} json(?)"
        else:
            # String or other
            self.params.append(str(value))
        
        op = "!=" if negated else "="
        return f"{field_ref} {op} ?"
    
    def _build_comparison(self, field_ref: str, op: FilterOperator, value: Any, negated: bool) -> str:
        """Build comparison operators (GT, GTE, LT, LTE)."""
        # Cast to numeric if needed
        if 'json_extract' in field_ref:
            field_ref = f"CAST({field_ref} AS REAL)"
        
        self.params.append(value)
        
        sql_op = {
            FilterOperator.GT: ">",
            FilterOperator.GTE: ">=",
            FilterOperator.LT: "<",
            FilterOperator.LTE: "<="
        }[op]
        
        result = f"{field_ref} {sql_op} ?"
        return f"NOT ({result})" if negated else result
    
    def _build_in(self, field_ref: str, values: List[Any], negated: bool) -> str:
        """Build IN/NOT IN clause."""
        if not isinstance(values, list):
            values = [values]
        
        if not values:
            return "0=1" if not negated else "1=1"
        
        placeholders = ','.join(['?' for _ in values])
        self.params.extend(values)
        
        op = "NOT IN" if negated else "IN"
        return f"{field_ref} {op} ({placeholders})"
    
    def _build_exists(self, field_ref: str, should_exist: bool, negated: bool) -> str:
        """Build EXISTS check for JSON fields."""
        if negated:
            should_exist = not should_exist
        
        if 'json_extract' in field_ref:
            if should_exist:
                return f"json_type({field_ref}) IS NOT NULL"
            else:
                return f"json_type({field_ref}) IS NULL"
        else:
            # For direct columns, check NULL
            if should_exist:
                return f"{field_ref} IS NOT NULL"
            else:
                return f"{field_ref} IS NULL"
    
    def _build_null(self, field_ref: str, negated: bool) -> str:
        """Build NULL check."""
        if 'json_extract' in field_ref:
            op = "!=" if negated else "="
            return f"json_type({field_ref}) {op} 'null'"
        else:
            op = "IS NOT" if negated else "IS"
            return f"{field_ref} {op} NULL"
    
    def _build_empty(self, field_ref: str, negated: bool) -> str:
        """Build empty check (for arrays/strings)."""
        if 'json_extract' in field_ref:
            # Check for empty array or empty string
            conditions = [
                f"json_array_length({field_ref}) = 0",
                f"{field_ref} = ''"
            ]
            result = f"({' OR '.join(conditions)})"
        else:
            result = f"{field_ref} = ''"
        
        return f"NOT ({result})" if negated else result
    
    def _build_contains(self, field_ref: str, value: Any, negated: bool) -> str:
        """Build array contains check."""
        if 'json_extract' in field_ref:
            # Use json_each to check array contents
            if isinstance(value, str):
                param_value = value
            else:
                param_value = json.dumps(value)
            
            self.params.append(param_value)
            
            exists = f"EXISTS (SELECT 1 FROM json_each({field_ref}) WHERE value = ?)"
            return f"NOT {exists}" if negated else exists
        else:
            # For direct string columns, use LIKE
            self.params.append(f"%{value}%")
            op = "NOT LIKE" if negated else "LIKE"
            return f"{field_ref} {op} ?"
    
    def _build_all(self, field_ref: str, values: List[Any], negated: bool) -> str:
        """Build check for array containing all values."""
        if not isinstance(values, list):
            values = [values]
        
        if not values:
            return "1=1"
        
        if 'json_extract' in field_ref:
            # Check each value exists in array
            conditions = []
            for val in values:
                param_value = val if isinstance(val, str) else json.dumps(val)
                self.params.append(param_value)
                conditions.append(
                    f"EXISTS (SELECT 1 FROM json_each({field_ref}) WHERE value = ?)"
                )
            
            result = f"({' AND '.join(conditions)})"
            return f"NOT ({result})" if negated else result
        else:
            # Not applicable to non-array fields
            return "0=1"
    
    def _build_size(self, field_ref: str, size: int, negated: bool) -> str:
        """Build array size check."""
        if 'json_extract' in field_ref:
            self.params.append(size)
            op = "!=" if negated else "="
            return f"json_array_length({field_ref}) {op} ?"
        else:
            # Not applicable to non-array fields
            return "0=1"
    
    def _build_between(self, field_ref: str, values: List[Any], negated: bool) -> str:
        """Build BETWEEN clause."""
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError("$between requires exactly 2 values")
        
        # Cast to numeric if needed
        if 'json_extract' in field_ref:
            field_ref = f"CAST({field_ref} AS REAL)"
        
        self.params.extend(values)
        result = f"{field_ref} BETWEEN ? AND ?"
        return f"NOT ({result})" if negated else result
    
    def _build_regex(self, field_ref: str, pattern: str, negated: bool) -> str:
        """Build regex pattern match."""
        # SQLite doesn't have built-in REGEXP without extension
        # Use LIKE as fallback with wildcards
        like_pattern = pattern.replace('%', '\\%').replace('_', '\\_')
        like_pattern = f"%{like_pattern}%"
        
        self.params.append(like_pattern)
        op = "NOT LIKE" if negated else "LIKE"
        return f"{field_ref} {op} ? ESCAPE '\\'"
    
    def _build_text(self, field: str, query: str, negated: bool) -> str:
        """Build text search condition."""
        if self.use_fts and field == self.fts_column:
            # Use FTS5
            self.params.append(query)
            match = f"{self.table_alias}.id IN (SELECT rowid FROM {self.table_alias}_fts WHERE {self.fts_column} MATCH ?)"
            return f"NOT {match}" if negated else match
        else:
            # Fallback to LIKE
            field_ref = self._get_field_reference(field)
            self.params.append(f"%{query}%")
            op = "NOT LIKE" if negated else "LIKE"
            return f"{field_ref} {op} ?"