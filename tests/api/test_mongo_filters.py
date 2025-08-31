#!/usr/bin/env python3
"""
Tests for MongoDB-style filter system.
"""

import pytest
import sys
import os
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.db.filters import (
    MongoFilterParser, FilterOperator, FilterCondition, FilterExpression,
    SQLiteFilterBackend, QdrantFilterBackend, FilterValidator,
    InvalidFilterError, UnsupportedOperatorError
)
from api.db.qdrant_store import QdrantStore


class TestMongoFilterParser:
    """Test the MongoDB filter parser."""
    
    def test_empty_filter(self):
        """Test parsing empty filter."""
        parser = MongoFilterParser()
        expr = parser.parse({})
        assert expr.operator == FilterOperator.AND
        assert expr.conditions == []
    
    def test_simple_equality(self):
        """Test simple field equality."""
        parser = MongoFilterParser()
        expr = parser.parse({"type": "alert"})
        
        assert expr.operator == FilterOperator.AND
        assert len(expr.conditions) == 1
        cond = expr.conditions[0]
        assert isinstance(cond, FilterCondition)
        assert cond.field == "type"
        assert cond.operator == FilterOperator.EQ
        assert cond.value == "alert"
    
    def test_multiple_equalities(self):
        """Test multiple field equalities (implicit AND)."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "type": "alert",
            "priority": 5
        })
        
        assert expr.operator == FilterOperator.AND
        assert len(expr.conditions) == 2
    
    def test_comparison_operators(self):
        """Test comparison operators."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "priority": {"$gte": 5, "$lt": 10}
        })
        
        assert expr.operator == FilterOperator.AND
        assert len(expr.conditions) == 2
        
        # Check both conditions
        ops = {cond.operator for cond in expr.conditions}
        assert FilterOperator.GTE in ops
        assert FilterOperator.LT in ops
    
    def test_in_operator(self):
        """Test $in operator."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "status": {"$in": ["active", "pending"]}
        })
        
        assert len(expr.conditions) == 1
        cond = expr.conditions[0]
        assert cond.operator == FilterOperator.IN
        assert cond.value == ["active", "pending"]
    
    def test_logical_and(self):
        """Test explicit $and operator."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "$and": [
                {"type": "alert"},
                {"priority": 5}
            ]
        })
        
        assert expr.operator == FilterOperator.AND
        assert len(expr.conditions) == 2
        
        # Each condition should be a nested expression
        for cond in expr.conditions:
            assert isinstance(cond, FilterExpression)
    
    def test_logical_or(self):
        """Test $or operator."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "$or": [
                {"status": "active"},
                {"urgent": True}
            ]
        })
        
        assert expr.operator == FilterOperator.OR
        assert len(expr.conditions) == 2
    
    def test_logical_not(self):
        """Test $not operator."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "$not": {"type": "info"}
        })
        
        assert expr.operator == FilterOperator.NOT
        assert len(expr.conditions) == 1
    
    def test_nested_logical(self):
        """Test nested logical operators."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "$and": [
                {"type": "alert"},
                {"$or": [
                    {"priority": {"$gte": 7}},
                    {"urgent": True}
                ]}
            ]
        })
        
        assert expr.operator == FilterOperator.AND
        assert len(expr.conditions) == 2
        
        # Second condition should be OR
        or_expr = expr.conditions[1]
        assert or_expr.operator == FilterOperator.OR
        assert len(or_expr.conditions) == 2
    
    def test_exists_operator(self):
        """Test $exists operator."""
        parser = MongoFilterParser()
        expr = parser.parse({
            "metadata": {"$exists": True}
        })
        
        cond = expr.conditions[0]
        assert cond.operator == FilterOperator.EXISTS
        assert cond.value is True
    
    def test_array_operators(self):
        """Test array operators."""
        parser = MongoFilterParser()
        
        # $size operator
        expr = parser.parse({"tags": {"$size": 3}})
        assert expr.conditions[0].operator == FilterOperator.SIZE
        
        # $all operator
        expr = parser.parse({"tags": {"$all": ["urgent", "critical"]}})
        assert expr.conditions[0].operator == FilterOperator.ALL
        
        # $contains operator
        expr = parser.parse({"tags": {"$contains": "urgent"}})
        assert expr.conditions[0].operator == FilterOperator.CONTAINS
    
    def test_max_depth_protection(self):
        """Test max depth protection against DoS."""
        parser = MongoFilterParser(max_depth=3)
        
        # This should work (depth 3)
        parser.parse({
            "$and": [
                {"$or": [{"a": 1}, {"b": 2}]}
            ]
        })
        
        # This should fail (depth 4)
        with pytest.raises(ValueError, match="depth"):
            parser.parse({
                "$and": [
                    {"$or": [
                        {"$and": [{"a": 1}]}
                    ]}
                ]
            })
    
    def test_invalid_operator(self):
        """Test invalid operator handling."""
        parser = MongoFilterParser()
        
        with pytest.raises(ValueError, match="Unknown operator"):
            parser.parse({"$invalid": "test"})


class TestSQLiteFilterBackend:
    """Test SQLite filter backend."""
    
    def test_simple_equality(self):
        """Test simple equality conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"type": "alert"})
        sql, params = backend.convert(expr)
        
        assert "json_extract" in sql
        assert "$.type" in sql
        assert params == ["alert"]
    
    def test_direct_field(self):
        """Test direct column fields."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend(table_alias="m")
        
        expr = parser.parse({"channel_id": "general"})
        sql, params = backend.convert(expr)
        
        assert "m.channel_id = ?" in sql
        assert "json_extract" not in sql
        assert params == ["general"]
    
    def test_comparison_operators(self):
        """Test comparison operator conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"priority": {"$gte": 5}})
        sql, params = backend.convert(expr)
        
        assert "CAST" in sql  # Should cast to REAL for comparison
        assert ">= ?" in sql
        assert params == [5]
    
    def test_in_operator(self):
        """Test IN operator conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"status": {"$in": ["active", "pending"]}})
        sql, params = backend.convert(expr)
        
        assert "IN (?,?)" in sql
        assert params == ["active", "pending"]
    
    def test_logical_operators(self):
        """Test logical operator conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        # AND
        expr = parser.parse({
            "$and": [{"a": 1}, {"b": 2}]
        })
        sql, _ = backend.convert(expr)
        assert " AND " in sql
        
        # OR
        expr = parser.parse({
            "$or": [{"a": 1}, {"b": 2}]
        })
        sql, _ = backend.convert(expr)
        assert " OR " in sql
        
        # NOT
        expr = parser.parse({
            "$not": {"a": 1}
        })
        sql, _ = backend.convert(expr)
        assert "NOT (" in sql
    
    def test_array_contains(self):
        """Test array contains conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"tags": {"$contains": "urgent"}})
        sql, params = backend.convert(expr)
        
        assert "EXISTS" in sql
        assert "json_each" in sql
        assert params == ["urgent"]
    
    def test_array_size(self):
        """Test array size conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"tags": {"$size": 3}})
        sql, params = backend.convert(expr)
        
        assert "json_array_length" in sql
        assert params == [3]
    
    def test_exists_operator(self):
        """Test exists operator conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"metadata": {"$exists": True}})
        sql, params = backend.convert(expr)
        
        assert "json_type" in sql
        assert "IS NOT NULL" in sql
        assert params == []
    
    def test_null_operator(self):
        """Test null operator conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"field": {"$null": True}})
        sql, params = backend.convert(expr)
        
        assert "json_type" in sql
        assert "= 'null'" in sql
    
    def test_between_operator(self):
        """Test between operator conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend()
        
        expr = parser.parse({"priority": {"$between": [3, 7]}})
        sql, params = backend.convert(expr)
        
        assert "BETWEEN ? AND ?" in sql
        assert params == [3, 7]
    
    def test_complex_nested_query(self):
        """Test complex nested query conversion."""
        parser = MongoFilterParser()
        backend = SQLiteFilterBackend(table_alias="m")
        
        expr = parser.parse({
            "$and": [
                {"channel_id": {"$in": ["general", "alerts"]}},
                {"$or": [
                    {"priority": {"$gte": 7}},
                    {"tags": {"$contains": "urgent"}}
                ]},
                {"processed": {"$ne": True}}
            ]
        })
        
        sql, params = backend.convert(expr)
        
        # Check structure
        assert "AND" in sql
        assert "OR" in sql
        assert "IN (?,?)" in sql
        assert "EXISTS" in sql
        
        # Check params
        assert "general" in params
        assert "alerts" in params
        assert 7 in params
        assert "urgent" in params


class TestQdrantFilterBackend:
    """Test Qdrant filter backend."""
    
    def test_simple_equality(self):
        """Test simple equality conversion."""
        parser = MongoFilterParser()
        backend = QdrantFilterBackend()
        
        expr = parser.parse({"type": "alert"})
        filter_dict = backend.convert(expr)
        
        # Should produce a Filter with must conditions
        assert 'must' in filter_dict.__dict__
        conditions = filter_dict.__dict__['must']
        assert len(conditions) == 1
    
    def test_metadata_field(self):
        """Test metadata field handling."""
        parser = MongoFilterParser()
        backend = QdrantFilterBackend(metadata_prefix="metadata")
        
        expr = parser.parse({"custom_field": "value"})
        filter_dict = backend.convert(expr)
        
        # Check that metadata prefix is added
        condition = filter_dict.__dict__['must'][0]
        assert "metadata.custom_field" in str(condition)
    
    def test_root_field(self):
        """Test root field handling."""
        parser = MongoFilterParser()
        backend = QdrantFilterBackend()
        
        expr = parser.parse({"channel_id": "general"})
        filter_dict = backend.convert(expr)
        
        # Root fields should not have metadata prefix
        condition = filter_dict.__dict__['must'][0]
        assert condition.key == "channel_id"
    
    def test_array_all_operator(self):
        """Test $all operator conversion to multiple conditions."""
        parser = MongoFilterParser()
        backend = QdrantFilterBackend()
        
        expr = parser.parse({"tags": {"$all": ["urgent", "critical"]}})
        filter_dict = backend.convert(expr)
        
        # Should create multiple must conditions
        assert 'must' in filter_dict.__dict__
        conditions = filter_dict.__dict__['must']
        assert len(conditions) == 2  # One for each value


class TestEndToEnd:
    """End-to-end tests with real queries."""
    
    def test_monitoring_query(self):
        """Test a monitoring/alerting query."""
        query = {
            "$and": [
                {"type": "error"},
                {"severity": {"$gte": 4}},
                {"$or": [
                    {"source": "api"},
                    {"tags": {"$contains": "critical"}}
                ]},
                {"resolved": {"$ne": True}},
                {"timestamp": {"$gte": "2024-01-01T00:00:00"}}
            ]
        }
        
        # Parse
        parser = MongoFilterParser()
        expr = parser.parse(query)
        
        # Convert to SQLite
        sqlite = SQLiteFilterBackend()
        sql, params = sqlite.convert(expr)
        
        assert sql is not None
        assert len(params) > 0
        
        # Convert to Qdrant
        qdrant = QdrantFilterBackend()
        qdrant_filter = qdrant.convert(expr)
        
        assert qdrant_filter is not None
    
    def test_search_with_metadata(self):
        """Test search with complex metadata filters."""
        query = {
            "channel_id": "support",
            "metadata.user.tier": {"$in": ["premium", "enterprise"]},
            "metadata.tags": {"$all": ["bug", "verified"]},
            "metadata.priority": {"$between": [5, 10]},
            "metadata.attachments": {"$size": {"$gte": 1}}
        }
        
        parser = MongoFilterParser()
        expr = parser.parse(query)
        
        # Both backends should handle this
        sqlite = SQLiteFilterBackend()
        sql, params = sqlite.convert(expr)
        assert sql is not None
        
        qdrant = QdrantFilterBackend()
        # Note: Qdrant doesn't support nested $size with comparison
        # This would need special handling in real implementation


class TestFilterValidator:
    """Test the filter validator."""
    
    def test_valid_filters(self):
        """Test that valid filters pass validation."""
        validator = FilterValidator.create_default()
        
        # Simple valid filter
        result = validator.validate({"type": "alert"})
        assert result == {"type": "alert"}
        
        # Complex valid filter
        result = validator.validate({
            "$and": [
                {"priority": {"$gte": 5}},
                {"$or": [
                    {"status": "active"},
                    {"urgent": True}
                ]}
            ]
        })
        assert "$and" in result
    
    def test_invalid_operator(self):
        """Test that invalid operators are rejected."""
        validator = FilterValidator(allow_unknown_operators=False)
        
        with pytest.raises(InvalidFilterError, match="Unknown operator"):
            validator.validate({"$invalid": "test"})
    
    def test_max_depth_protection(self):
        """Test max depth protection."""
        validator = FilterValidator(max_depth=3)
        
        # This should work (depth 3)
        validator.validate({
            "$and": [{
                "$or": [{"a": 1}]
            }]
        })
        
        # This should fail (depth 4)
        with pytest.raises(InvalidFilterError, match="depth"):
            validator.validate({
                "$and": [{
                    "$or": [{
                        "$and": [{"a": 1}]
                    }]
                }]
            })
    
    def test_array_size_limit(self):
        """Test array size limits."""
        validator = FilterValidator(max_array_size=3)
        
        # Should work
        validator.validate({
            "status": {"$in": ["a", "b", "c"]}
        })
        
        # Should fail
        with pytest.raises(InvalidFilterError, match="array exceeds maximum"):
            validator.validate({
                "status": {"$in": ["a", "b", "c", "d"]}
            })
    
    def test_invalid_value_types(self):
        """Test type validation for operators."""
        validator = FilterValidator()
        
        # $gte should reject non-comparable types
        with pytest.raises(InvalidFilterError):
            validator.validate({
                "priority": {"$gte": {"invalid": "object"}}
            })
        
        # $in should be an array
        with pytest.raises(InvalidFilterError, match="array"):
            validator.validate({
                "status": {"$in": "not_an_array"}
            })
        
        # $exists should be boolean
        with pytest.raises(InvalidFilterError, match="boolean"):
            validator.validate({
                "field": {"$exists": "yes"}
            })
    
    def test_between_validation(self):
        """Test $between operator validation."""
        validator = FilterValidator()
        
        # Valid between
        result = validator.validate({
            "priority": {"$between": [1, 10]}
        })
        assert result["priority"]["$between"] == [1, 10]
        
        # Invalid - not an array
        with pytest.raises(InvalidFilterError, match="array"):
            validator.validate({
                "priority": {"$between": 5}
            })
        
        # Invalid - wrong number of values
        with pytest.raises(InvalidFilterError, match="exactly 2"):
            validator.validate({
                "priority": {"$between": [1, 2, 3]}
            })
        
        # Invalid - min > max
        with pytest.raises(InvalidFilterError, match="range invalid"):
            validator.validate({
                "priority": {"$between": [10, 1]}
            })
    
    def test_regex_validation(self):
        """Test regex pattern validation."""
        validator = FilterValidator()
        
        # Valid regex
        result = validator.validate({
            "content": {"$regex": "^test.*"}
        })
        assert result["content"]["$regex"] == "^test.*"
        
        # Invalid regex
        with pytest.raises(InvalidFilterError, match="Invalid regex"):
            validator.validate({
                "content": {"$regex": "[invalid(regex"}
            })


class TestQdrantStoreIntegration:
    """Test QdrantStore with new filter system."""
    
    @pytest.mark.asyncio
    async def test_qdrant_with_shared_filters(self):
        """Test that QdrantStore works with the shared filter system."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = QdrantStore(qdrant_path=str(Path(tmpdir) / "qdrant"))
            
            # Index test messages
            test_messages = [
                {
                    "id": 1,
                    "content": "High priority alert",
                    "metadata": {"type": "alert", "priority": 8, "tags": ["urgent"]}
                },
                {
                    "id": 2,
                    "content": "Low priority info",
                    "metadata": {"type": "info", "priority": 2, "tags": ["status"]}
                },
                {
                    "id": 3,
                    "content": "Medium priority warning",
                    "metadata": {"type": "warning", "priority": 5, "tags": ["monitor"]}
                }
            ]
            
            for msg in test_messages:
                await store.index_message(
                    message_id=msg["id"],
                    content=msg["content"],
                    channel_id="test",
                    sender_id="agent",
                    timestamp=datetime.now(),
                    metadata=msg["metadata"],
                    confidence=0.8
                )
            
            # Test with MongoDB filters
            results = await store.search(
                query="priority",
                metadata_filters={
                    "$or": [
                        {"priority": {"$gte": 7}},
                        {"tags": {"$contains": "urgent"}}
                    ]
                },
                limit=10
            )
            
            # Should find the high priority alert
            assert len(results) >= 1
            assert any(r[0] == 1 for r in results)  # Message ID 1 should be found
    
    @pytest.mark.asyncio
    async def test_filter_validation_in_qdrant(self):
        """Test that invalid filters are rejected by QdrantStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = QdrantStore(qdrant_path=str(Path(tmpdir) / "qdrant"))
            
            # Test with invalid filter
            with pytest.raises(ValueError, match="Invalid filter"):
                await store.search(
                    query="test",
                    metadata_filters={
                        "$invalid_operator": "value"
                    },
                    limit=10
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])