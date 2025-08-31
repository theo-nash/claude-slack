#!/usr/bin/env python3
"""
Qdrant backend for MongoDB-style filters.
Converts FilterExpression trees to Qdrant Filter objects.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from qdrant_client.models import (
    Filter, FieldCondition, Range, MatchValue, MatchAny,
    MatchText, IsEmptyCondition, IsNullCondition,
    PayloadField
)

from .base import (
    FilterBackend, FilterCondition, FilterExpression,
    FilterOperator, UnsupportedOperatorError
)


class QdrantFilterBackend(FilterBackend):
    """
    Converts FilterExpression trees to Qdrant Filter objects.
    """
    
    # Operators supported by Qdrant
    SUPPORTED_OPERATORS = {
        FilterOperator.EQ, FilterOperator.NE,
        FilterOperator.GT, FilterOperator.GTE,
        FilterOperator.LT, FilterOperator.LTE,
        FilterOperator.IN, FilterOperator.NIN,
        FilterOperator.AND, FilterOperator.OR, FilterOperator.NOT,
        FilterOperator.EXISTS, FilterOperator.NULL, FilterOperator.EMPTY,
        FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS,
        FilterOperator.ALL, FilterOperator.SIZE,
        FilterOperator.REGEX, FilterOperator.TEXT,
        FilterOperator.BETWEEN
    }
    
    # Fields that are at root level (not under metadata)
    ROOT_FIELDS = {
        'channel_id', 'sender_id', 'sender_project_id',
        'content', 'timestamp', 'confidence'
    }
    
    def __init__(self, metadata_prefix: str = 'metadata'):
        """
        Initialize Qdrant backend.
        
        Args:
            metadata_prefix: Prefix for metadata fields
        """
        self.metadata_prefix = metadata_prefix
    
    def convert(self, expression: FilterExpression) -> Optional[Filter]:
        """
        Convert FilterExpression to Qdrant Filter.
        
        Args:
            expression: The filter expression tree
            
        Returns:
            Qdrant Filter object or None for empty filters
        """
        # Empty expression matches everything
        if not expression.conditions:
            return None
        
        # Validate all operators are supported
        self.validate_expression(expression)
        
        # Convert to Qdrant filter
        conditions = self._convert_expression(expression)
        
        # Build the filter
        if isinstance(conditions, Filter):
            return conditions
        elif isinstance(conditions, dict):
            return Filter(**conditions) if conditions else None
        else:
            return None
    
    def supports_operator(self, operator: FilterOperator) -> bool:
        """Check if Qdrant backend supports an operator."""
        return operator in self.SUPPORTED_OPERATORS
    
    def _convert_expression(self, expr: Union[FilterExpression, FilterCondition]) -> Union[Dict, Filter]:
        """Convert an expression or condition to Qdrant format."""
        if isinstance(expr, FilterCondition):
            return self._convert_condition(expr)
        elif isinstance(expr, FilterExpression):
            return self._convert_compound(expr)
        else:
            raise ValueError(f"Unknown expression type: {type(expr)}")
    
    def _convert_compound(self, expr: FilterExpression) -> Dict:
        """Convert compound expression (AND/OR/NOT)."""
        must = []
        should = []
        must_not = []
        
        if expr.operator == FilterOperator.AND:
            # All conditions must match
            for condition in expr.conditions:
                result = self._convert_expression(condition)
                if isinstance(result, dict):
                    # Merge conditions
                    must.extend(result.get('must', []))
                    should.extend(result.get('should', []))
                    must_not.extend(result.get('must_not', []))
                elif isinstance(result, FieldCondition):
                    must.append(result)
                elif isinstance(result, Filter):
                    must.append(result)
        
        elif expr.operator == FilterOperator.OR:
            # At least one condition must match
            for condition in expr.conditions:
                result = self._convert_expression(condition)
                if isinstance(result, dict):
                    # Each OR branch becomes a should with its own filter
                    branch_filter = Filter(**result) if result else None
                    if branch_filter:
                        should.append(branch_filter)
                elif isinstance(result, (FieldCondition, Filter)):
                    should.append(result)
        
        elif expr.operator == FilterOperator.NOT:
            # Negate the inner condition
            if expr.conditions:
                result = self._convert_expression(expr.conditions[0])
                if isinstance(result, dict):
                    # Swap must and must_not
                    must_not.extend(result.get('must', []))
                    must.extend(result.get('must_not', []))
                    # Negate should conditions
                    must_not.extend(result.get('should', []))
                elif isinstance(result, (FieldCondition, Filter)):
                    must_not.append(result)
        
        else:
            # Non-compound expression with multiple conditions
            # Treat as AND
            for condition in expr.conditions:
                result = self._convert_expression(condition)
                if isinstance(result, FieldCondition):
                    must.append(result)
                elif isinstance(result, dict):
                    must.extend(result.get('must', []))
        
        # Build result dictionary
        result = {}
        if must:
            result['must'] = must
        if should:
            result['should'] = should
        if must_not:
            result['must_not'] = must_not
        
        return result
    
    def _convert_condition(self, condition: FilterCondition) -> Union[Dict, FieldCondition]:
        """Convert a single condition to Qdrant format."""
        field_key = self._get_field_key(condition.field)
        op = condition.operator
        value = condition.value
        negated = condition.negated
        
        # Special handling for timestamp fields with string values
        if condition.field == 'timestamp' and isinstance(value, str):
            # Convert ISO timestamp string to Unix timestamp for Qdrant
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                value = dt.timestamp()  # Convert to Unix timestamp (float)
            except (ValueError, AttributeError):
                # If conversion fails, treat as string
                pass
        
        # Build the base condition
        if op == FilterOperator.EQ:
            base = FieldCondition(key=field_key, match=MatchValue(value=value))
        
        elif op == FilterOperator.NE:
            base = FieldCondition(key=field_key, match=MatchValue(value=value))
            negated = not negated  # Flip negation for NE
        
        elif op == FilterOperator.GT:
            base = FieldCondition(key=field_key, range=Range(gt=value))
        
        elif op == FilterOperator.GTE:
            base = FieldCondition(key=field_key, range=Range(gte=value))
        
        elif op == FilterOperator.LT:
            base = FieldCondition(key=field_key, range=Range(lt=value))
        
        elif op == FilterOperator.LTE:
            base = FieldCondition(key=field_key, range=Range(lte=value))
        
        elif op == FilterOperator.IN:
            values = value if isinstance(value, list) else [value]
            base = FieldCondition(key=field_key, match=MatchAny(any=values))
        
        elif op == FilterOperator.NIN:
            values = value if isinstance(value, list) else [value]
            base = FieldCondition(key=field_key, match=MatchAny(any=values))
            negated = not negated  # Flip for NIN
        
        elif op == FilterOperator.EXISTS:
            if value:
                # Field must exist (not null)
                base = IsNullCondition(is_null=PayloadField(key=field_key))
                negated = not negated  # We want NOT NULL
            else:
                # Field must not exist (is null)
                base = IsNullCondition(is_null=PayloadField(key=field_key))
        
        elif op == FilterOperator.NULL:
            base = IsNullCondition(is_null=PayloadField(key=field_key))
        
        elif op == FilterOperator.EMPTY:
            base = IsEmptyCondition(is_empty=PayloadField(key=field_key))
        
        elif op == FilterOperator.CONTAINS:
            # Array contains value - use MatchAny
            values = [value] if not isinstance(value, list) else value
            base = FieldCondition(key=field_key, match=MatchAny(any=values))
        
        elif op == FilterOperator.NOT_CONTAINS:
            # Array doesn't contain value
            values = [value] if not isinstance(value, list) else value
            base = FieldCondition(key=field_key, match=MatchAny(any=values))
            negated = not negated
        
        elif op == FilterOperator.ALL:
            # All values must be present
            if not isinstance(value, list):
                value = [value]
            # In Qdrant, we need multiple conditions ANDed together
            conditions = []
            for val in value:
                conditions.append(
                    FieldCondition(key=field_key, match=MatchAny(any=[val]))
                )
            return {'must': conditions}
        
        elif op == FilterOperator.SIZE:
            # Array size check - use special field with __len suffix
            size_field = f"{field_key}__len"
            base = FieldCondition(key=size_field, match=MatchValue(value=value))
        
        elif op == FilterOperator.BETWEEN:
            # Range between two values
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("$between requires exactly 2 values")
            base = FieldCondition(key=field_key, range=Range(gte=value[0], lte=value[1]))
        
        elif op == FilterOperator.REGEX:
            # Text pattern matching
            base = FieldCondition(key=field_key, match=MatchText(text=value))
        
        elif op == FilterOperator.TEXT:
            # Full text search
            base = FieldCondition(key=field_key, match=MatchText(text=value))
        
        else:
            raise UnsupportedOperatorError(op, "Qdrant")
        
        # Handle negation
        if negated:
            return {'must_not': [base]}
        else:
            return {'must': [base]} if isinstance(base, FieldCondition) else base
    
    def _get_field_key(self, field: str) -> str:
        """
        Get the Qdrant field key for a field name.
        Adds metadata prefix for non-root fields.
        """
        if field in self.ROOT_FIELDS:
            return field
        else:
            return f"{self.metadata_prefix}.{field}"