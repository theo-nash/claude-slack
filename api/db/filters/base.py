#!/usr/bin/env python3
"""
Base MongoDB-style filter parser.
Provides a shared abstraction for parsing MongoDB queries that can be
implemented by different backends (Qdrant, SQLite, PostgreSQL, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class FilterOperator(Enum):
    """MongoDB-style query operators."""
    # Comparison
    EQ = "$eq"
    NE = "$ne"
    GT = "$gt"
    GTE = "$gte"
    LT = "$lt"
    LTE = "$lte"
    
    # Array/List
    IN = "$in"
    NIN = "$nin"
    CONTAINS = "$contains"
    NOT_CONTAINS = "$not_contains"
    ALL = "$all"
    SIZE = "$size"
    
    # Logical
    AND = "$and"
    OR = "$or"
    NOT = "$not"
    
    # Existence
    EXISTS = "$exists"
    NULL = "$null"
    EMPTY = "$empty"
    
    # Text
    REGEX = "$regex"
    TEXT = "$text"
    
    # Special
    BETWEEN = "$between"
    
    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string is a valid operator."""
        return value in {op.value for op in cls}
    
    @classmethod
    def from_string(cls, value: str) -> Optional['FilterOperator']:
        """Convert string to operator."""
        for op in cls:
            if op.value == value:
                return op
        return None


@dataclass
class FilterCondition:
    """
    Represents a single filter condition.
    """
    field: Optional[str]  # None for logical operators
    operator: FilterOperator
    value: Any
    negated: bool = False
    
    def __repr__(self):
        neg = "NOT " if self.negated else ""
        if self.field:
            return f"{neg}{self.field} {self.operator.value} {self.value}"
        else:
            return f"{neg}{self.operator.value}: {self.value}"


@dataclass
class FilterExpression:
    """
    Represents a complete filter expression tree.
    Can contain nested conditions and logical operators.
    """
    operator: FilterOperator  # AND, OR, or NOT for compound expressions
    conditions: List[Union[FilterCondition, 'FilterExpression']]
    
    def is_compound(self) -> bool:
        """Check if this is a compound expression (AND/OR/NOT)."""
        return self.operator in {FilterOperator.AND, FilterOperator.OR, FilterOperator.NOT}
    
    def __repr__(self):
        if self.is_compound():
            return f"{self.operator.value}({self.conditions})"
        else:
            return f"Expression({self.conditions})"


class MongoFilterParser:
    """
    Parses MongoDB-style filter dictionaries into a structured format.
    This is backend-agnostic and produces a normalized representation
    that can be converted to different query languages.
    """
    
    def __init__(self, max_depth: int = 10):
        """
        Initialize the parser.
        
        Args:
            max_depth: Maximum nesting depth to prevent DoS attacks
        """
        self.max_depth = max_depth
        self._depth = 0
    
    def parse(self, filters: Dict[str, Any]) -> FilterExpression:
        """
        Parse MongoDB-style filters into a structured expression tree.
        
        Args:
            filters: MongoDB-style filter dictionary
            
        Returns:
            FilterExpression tree
            
        Raises:
            ValueError: If the filter is invalid or too deeply nested
        """
        if not filters:
            # Empty filter matches everything
            return FilterExpression(FilterOperator.AND, [])
        
        self._depth = 0
        return self._parse_dict(filters)
    
    def _parse_dict(self, filters: Dict[str, Any]) -> FilterExpression:
        """Parse a dictionary of filters."""
        self._depth += 1
        if self._depth > self.max_depth:
            raise ValueError(f"Filter nesting exceeds maximum depth of {self.max_depth}")
        
        try:
            conditions = []
            
            for key, value in filters.items():
                if key.startswith('$'):
                    # Top-level operator
                    op = FilterOperator.from_string(key)
                    if not op:
                        raise ValueError(f"Unknown operator: {key}")
                    
                    if op in {FilterOperator.AND, FilterOperator.OR, FilterOperator.NOT}:
                        # Logical operator
                        conditions.append(self._parse_logical(op, value))
                    else:
                        # Operator without field is invalid at top level
                        raise ValueError(f"Operator {key} requires a field")
                else:
                    # Field condition
                    conditions.extend(self._parse_field(key, value))
            
            # If we have multiple conditions, wrap in AND
            if len(conditions) == 1:
                return conditions[0] if isinstance(conditions[0], FilterExpression) else \
                       FilterExpression(FilterOperator.AND, conditions)
            else:
                return FilterExpression(FilterOperator.AND, conditions)
                
        finally:
            self._depth -= 1
    
    def _parse_logical(self, operator: FilterOperator, value: Any) -> FilterExpression:
        """Parse logical operators ($and, $or, $not)."""
        if operator in {FilterOperator.AND, FilterOperator.OR}:
            if not isinstance(value, list):
                raise ValueError(f"{operator.value} requires a list")
            
            conditions = []
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError(f"{operator.value} items must be dictionaries")
                conditions.append(self._parse_dict(item))
            
            return FilterExpression(operator, conditions)
        
        elif operator == FilterOperator.NOT:
            if not isinstance(value, dict):
                raise ValueError(f"{operator.value} requires a dictionary")
            
            inner = self._parse_dict(value)
            return FilterExpression(operator, [inner])
        
        else:
            raise ValueError(f"Not a logical operator: {operator.value}")
    
    def _parse_field(self, field: str, value: Any) -> List[Union[FilterCondition, FilterExpression]]:
        """Parse field-level conditions."""
        conditions = []
        
        if isinstance(value, dict) and any(k.startswith('$') for k in value):
            # Field with operators
            for op_str, op_value in value.items():
                op = FilterOperator.from_string(op_str)
                if not op:
                    raise ValueError(f"Unknown operator: {op_str}")
                
                if op in {FilterOperator.AND, FilterOperator.OR, FilterOperator.NOT}:
                    # Nested logical operator
                    conditions.append(self._parse_logical(op, op_value))
                else:
                    # Field operator
                    conditions.append(FilterCondition(field, op, op_value))
        else:
            # Direct equality
            conditions.append(FilterCondition(field, FilterOperator.EQ, value))
        
        return conditions


class FilterBackend(ABC):
    """
    Abstract base class for filter backends.
    Each database/search engine implements this to convert
    FilterExpression trees into their native query format.
    """
    
    @abstractmethod
    def convert(self, expression: FilterExpression) -> Any:
        """
        Convert a FilterExpression tree to the backend's native format.
        
        Args:
            expression: The filter expression tree
            
        Returns:
            Backend-specific query object
        """
        pass
    
    @abstractmethod
    def supports_operator(self, operator: FilterOperator) -> bool:
        """
        Check if this backend supports a specific operator.
        
        Args:
            operator: The operator to check
            
        Returns:
            True if supported, False otherwise
        """
        pass
    
    def validate_expression(self, expression: FilterExpression) -> None:
        """
        Validate that all operators in the expression are supported.
        
        Args:
            expression: The expression to validate
            
        Raises:
            ValueError: If an unsupported operator is found
        """
        self._validate_recursive(expression)
    
    def _validate_recursive(self, expr: Union[FilterExpression, FilterCondition]) -> None:
        """Recursively validate all operators."""
        if isinstance(expr, FilterCondition):
            if not self.supports_operator(expr.operator):
                raise ValueError(f"Operator {expr.operator.value} not supported by {self.__class__.__name__}")
        elif isinstance(expr, FilterExpression):
            if not self.supports_operator(expr.operator):
                raise ValueError(f"Operator {expr.operator.value} not supported by {self.__class__.__name__}")
            for condition in expr.conditions:
                self._validate_recursive(condition)


class FilterError(Exception):
    """Base exception for filter-related errors."""
    pass


class UnsupportedOperatorError(FilterError):
    """Raised when a backend doesn't support an operator."""
    def __init__(self, operator: FilterOperator, backend: str):
        super().__init__(f"Operator {operator.value} is not supported by {backend}")
        self.operator = operator
        self.backend = backend


class InvalidFilterError(FilterError):
    """Raised when a filter is malformed or invalid."""
    pass