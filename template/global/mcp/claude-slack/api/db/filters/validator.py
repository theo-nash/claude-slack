#!/usr/bin/env python3
"""
Pre-flight validation for MongoDB-style filters.
Validates filter structure, operators, and values before database execution.
"""

from typing import Any, Dict, List, Optional, Set, Union
from datetime import datetime
from enum import Enum

from .base import FilterOperator, InvalidFilterError


class FieldType(Enum):
    """Supported field types for validation."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    DATETIME = "datetime"
    ANY = "any"


class FilterValidator:
    """
    Validates MongoDB-style filters before processing.
    
    Features:
    - Validates operator syntax and combinations
    - Type checking for operator values
    - Field existence validation (optional)
    - Nested field path validation
    - Security checks (max depth, size limits)
    """
    
    # Valid MongoDB operators
    COMPARISON_OPS = {
        "$eq", "$ne", "$gt", "$gte", "$lt", "$lte"
    }
    
    ARRAY_OPS = {
        "$in", "$nin", "$all", "$size", "$contains", "$not_contains"
    }
    
    LOGICAL_OPS = {
        "$and", "$or", "$not", "$nor"
    }
    
    ELEMENT_OPS = {
        "$exists", "$null", "$empty", "$type"
    }
    
    TEXT_OPS = {
        "$regex", "$text", "$search"
    }
    
    SPECIAL_OPS = {
        "$between", "$near", "$geoWithin"
    }
    
    ALL_OPS = (COMPARISON_OPS | ARRAY_OPS | LOGICAL_OPS | 
               ELEMENT_OPS | TEXT_OPS | SPECIAL_OPS)
    
    def __init__(self,
                 max_depth: int = 10,
                 max_filter_size: int = 1000,
                 max_array_size: int = 100,
                 allowed_fields: Optional[Set[str]] = None,
                 field_types: Optional[Dict[str, FieldType]] = None,
                 allow_unknown_fields: bool = True,
                 allow_unknown_operators: bool = False):
        """
        Initialize validator with constraints.
        
        Args:
            max_depth: Maximum nesting depth for filters
            max_filter_size: Maximum size of filter dictionary
            max_array_size: Maximum size for array operators
            allowed_fields: Whitelist of allowed field names (None = all allowed)
            field_types: Expected types for fields (for type validation)
            allow_unknown_fields: Whether to allow fields not in field_types
            allow_unknown_operators: Whether to allow non-standard operators
        """
        self.max_depth = max_depth
        self.max_filter_size = max_filter_size
        self.max_array_size = max_array_size
        self.allowed_fields = allowed_fields
        self.field_types = field_types or {}
        self.allow_unknown_fields = allow_unknown_fields
        self.allow_unknown_operators = allow_unknown_operators
        
        # Track validation state
        self._current_depth = 0
        self._field_count = 0
    
    def validate(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize filters.
        
        Args:
            filters: MongoDB-style filter dictionary
            
        Returns:
            Validated and sanitized filters
            
        Raises:
            InvalidFilterError: If validation fails
        """
        # Reset state
        self._current_depth = 0
        self._field_count = 0
        
        # Check overall size
        if self._get_dict_size(filters) > self.max_filter_size:
            raise InvalidFilterError(
                f"Filter too large: exceeds {self.max_filter_size} elements"
            )
        
        # Validate structure
        validated = self._validate_level(filters, depth=0)
        
        return validated
    
    def _validate_level(self, obj: Any, depth: int) -> Any:
        """Validate a filter level recursively."""
        if depth > self.max_depth:
            raise InvalidFilterError(f"Filter exceeds maximum depth of {self.max_depth}")
        
        if not isinstance(obj, dict):
            raise InvalidFilterError(f"Expected dict, got {type(obj).__name__}")
        
        validated = {}
        
        for key, value in obj.items():
            # Check if it's an operator
            if key.startswith("$"):
                validated_value = self._validate_operator(key, value, depth)
                validated[key] = validated_value
            else:
                # It's a field name
                validated_field = self._validate_field(key, value, depth)
                validated[key] = validated_field
        
        return validated
    
    def _validate_operator(self, op: str, value: Any, depth: int) -> Any:
        """Validate an operator and its value."""
        # Check if operator is known
        if not self.allow_unknown_operators and op not in self.ALL_OPS:
            raise InvalidFilterError(f"Unknown operator: {op}")
        
        # Validate based on operator type
        if op in self.LOGICAL_OPS:
            return self._validate_logical_op(op, value, depth)
        elif op in self.COMPARISON_OPS:
            return self._validate_comparison_op(op, value)
        elif op in self.ARRAY_OPS:
            return self._validate_array_op(op, value)
        elif op in self.ELEMENT_OPS:
            return self._validate_element_op(op, value)
        elif op in self.TEXT_OPS:
            return self._validate_text_op(op, value)
        elif op == "$between":
            return self._validate_between_op(value)
        else:
            # Unknown operator - if allowed, pass through
            if self.allow_unknown_operators:
                return value
            raise InvalidFilterError(f"Unsupported operator: {op}")
    
    def _validate_logical_op(self, op: str, value: Any, depth: int) -> Any:
        """Validate logical operators ($and, $or, $not, $nor)."""
        if op in ("$and", "$or", "$nor"):
            # Must be an array of conditions
            if not isinstance(value, list):
                raise InvalidFilterError(f"{op} requires an array, got {type(value).__name__}")
            
            if len(value) == 0:
                raise InvalidFilterError(f"{op} requires at least one condition")
            
            # Validate each sub-condition
            validated = []
            for i, condition in enumerate(value):
                if not isinstance(condition, dict):
                    raise InvalidFilterError(
                        f"{op}[{i}] must be a dict, got {type(condition).__name__}"
                    )
                validated.append(self._validate_level(condition, depth + 1))
            
            return validated
        
        elif op == "$not":
            # Must be a single condition
            if not isinstance(value, dict):
                raise InvalidFilterError(f"$not requires a dict, got {type(value).__name__}")
            
            return self._validate_level(value, depth + 1)
        
        else:
            raise InvalidFilterError(f"Unknown logical operator: {op}")
    
    def _validate_comparison_op(self, op: str, value: Any) -> Any:
        """Validate comparison operators ($eq, $ne, $gt, etc)."""
        # Value can be string, number, boolean, or datetime
        if value is None:
            return value
        
        if isinstance(value, (str, int, float, bool)):
            return value
        
        if isinstance(value, datetime):
            # Convert datetime to Unix timestamp for consistency
            return value.timestamp()
        
        # Try to convert string dates
        if isinstance(value, str):
            try:
                # Validate ISO format and convert to Unix timestamp
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.timestamp()
            except:
                # Not a date, treat as string
                return value
        
        raise InvalidFilterError(
            f"{op} value must be string, number, boolean, or datetime, got {type(value).__name__}"
        )
    
    def _validate_array_op(self, op: str, value: Any) -> Any:
        """Validate array operators ($in, $nin, $all, etc)."""
        if op in ("$in", "$nin", "$all"):
            # Must be an array
            if not isinstance(value, list):
                raise InvalidFilterError(f"{op} requires an array, got {type(value).__name__}")
            
            if len(value) > self.max_array_size:
                raise InvalidFilterError(
                    f"{op} array exceeds maximum size of {self.max_array_size}"
                )
            
            # Validate each element
            validated = []
            for item in value:
                if not isinstance(item, (str, int, float, bool, type(None))):
                    raise InvalidFilterError(
                        f"{op} array items must be primitive types, got {type(item).__name__}"
                    )
                validated.append(item)
            
            return validated
        
        elif op == "$size":
            # Must be a number
            if not isinstance(value, (int, float)):
                raise InvalidFilterError(f"$size requires a number, got {type(value).__name__}")
            
            if value < 0:
                raise InvalidFilterError("$size cannot be negative")
            
            return int(value)
        
        elif op in ("$contains", "$not_contains"):
            # Single value (will be checked if array contains it)
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise InvalidFilterError(
                    f"{op} requires a primitive value, got {type(value).__name__}"
                )
            return value
        
        else:
            raise InvalidFilterError(f"Unknown array operator: {op}")
    
    def _validate_element_op(self, op: str, value: Any) -> Any:
        """Validate element operators ($exists, $null, etc)."""
        if op in ("$exists", "$null", "$empty"):
            # Must be boolean
            if not isinstance(value, bool):
                raise InvalidFilterError(f"{op} requires a boolean, got {type(value).__name__}")
            return value
        
        elif op == "$type":
            # Must be a valid type string
            valid_types = {"string", "number", "boolean", "array", "object", "null"}
            if value not in valid_types:
                raise InvalidFilterError(f"$type value must be one of {valid_types}, got {value}")
            return value
        
        else:
            raise InvalidFilterError(f"Unknown element operator: {op}")
    
    def _validate_text_op(self, op: str, value: Any) -> Any:
        """Validate text operators ($regex, $text, etc)."""
        if op in ("$regex", "$text", "$search"):
            # Must be string
            if not isinstance(value, str):
                raise InvalidFilterError(f"{op} requires a string, got {type(value).__name__}")
            
            # Validate regex syntax for $regex
            if op == "$regex":
                try:
                    import re
                    re.compile(value)
                except re.error as e:
                    raise InvalidFilterError(f"Invalid regex pattern: {e}")
            
            return value
        
        else:
            raise InvalidFilterError(f"Unknown text operator: {op}")
    
    def _validate_between_op(self, value: Any) -> List:
        """Validate $between operator."""
        if not isinstance(value, list):
            raise InvalidFilterError(f"$between requires an array, got {type(value).__name__}")
        
        if len(value) != 2:
            raise InvalidFilterError(f"$between requires exactly 2 values, got {len(value)}")
        
        # Both values must be comparable types
        for i, v in enumerate(value):
            if not isinstance(v, (str, int, float, datetime)):
                raise InvalidFilterError(
                    f"$between[{i}] must be string, number, or datetime, got {type(v).__name__}"
                )
        
        # Check that min <= max
        if value[0] > value[1]:
            raise InvalidFilterError(f"$between range invalid: {value[0]} > {value[1]}")
        
        return value
    
    def _validate_field(self, field: str, value: Any, depth: int) -> Any:
        """Validate a field and its conditions."""
        # Check if field is allowed
        if self.allowed_fields and field not in self.allowed_fields:
            # Check for nested fields (e.g., "user.name")
            root_field = field.split('.')[0]
            if root_field not in self.allowed_fields:
                raise InvalidFilterError(f"Field not allowed: {field}")
        
        # Check field type if specified
        if field in self.field_types and not self.allow_unknown_fields:
            expected_type = self.field_types[field]
            # Type checking would go here based on the operators used
        
        # If value is a dict, it contains operators
        if isinstance(value, dict):
            validated = {}
            for op, op_value in value.items():
                if not op.startswith("$"):
                    raise InvalidFilterError(
                        f"Invalid operator '{op}' for field '{field}' - operators must start with $"
                    )
                validated[op] = self._validate_operator(op, op_value, depth)
            return validated
        else:
            # Direct value comparison (implicit $eq)
            return self._validate_comparison_op("$eq", value)
    
    def _get_dict_size(self, obj: Any) -> int:
        """Count total elements in nested structure."""
        if isinstance(obj, dict):
            count = len(obj)
            for value in obj.values():
                count += self._get_dict_size(value)
            return count
        elif isinstance(obj, list):
            count = len(obj)
            for item in obj:
                count += self._get_dict_size(item)
            return count
        else:
            return 1
    
    @classmethod
    def create_default(cls) -> 'FilterValidator':
        """Create a validator with sensible defaults."""
        return cls(
            max_depth=10,
            max_filter_size=1000,
            max_array_size=100,
            allow_unknown_fields=True,
            allow_unknown_operators=False
        )
    
    @classmethod
    def create_strict(cls, allowed_fields: Set[str],
                     field_types: Dict[str, FieldType]) -> 'FilterValidator':
        """Create a strict validator with field restrictions."""
        return cls(
            max_depth=5,
            max_filter_size=500,
            max_array_size=50,
            allowed_fields=allowed_fields,
            field_types=field_types,
            allow_unknown_fields=False,
            allow_unknown_operators=False
        )