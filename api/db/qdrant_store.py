#!/usr/bin/env python3
"""
QdrantStore: Pure Qdrant vector storage operations.
Handles ONLY vector indexing and semantic search, no SQLite knowledge.
"""

import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, Range, MatchValue, MatchAny,
    MatchText, IsEmptyCondition, IsNullCondition, HasIdCondition,
    NestedCondition, MatchExcept, PayloadField, PayloadSchemaType
)
from sentence_transformers import SentenceTransformer

from ..ranking import RankingProfile, RankingProfiles


class QdrantStore:
    """
    Pure Qdrant storage for vector operations.
    No SQLite knowledge, only handles vector indexing and search.
    """
    
    def __init__(self, 
                 qdrant_path: Optional[str] = None,
                 qdrant_url: Optional[str] = None,
                 qdrant_api_key: Optional[str] = None,
                 embedding_model: Optional[str] = None,
                 collection_name: str = "messages"):
        """
        Initialize Qdrant store.
        
        Args:
            qdrant_path: Path to local Qdrant storage
            qdrant_url: URL for remote Qdrant (Docker or cloud)
            qdrant_api_key: API key for Qdrant cloud
            embedding_model: Embedding model name (defaults to all-MiniLM-L6-v2)
            collection_name: Name of the Qdrant collection
        """
        # Initialize Qdrant client
        if qdrant_url:
            # Remote Qdrant (Docker or cloud)
            if qdrant_api_key:
                self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            else:
                self.client = QdrantClient(url=qdrant_url)
        elif qdrant_path:
            # Local Qdrant with explicit path
            self.client = QdrantClient(path=qdrant_path)
        else:
            raise ValueError("Must provide either qdrant_path or qdrant_url")
        
        # Set up embedding model
        model_name = embedding_model or "all-MiniLM-L6-v2"
        self.embedder = SentenceTransformer(model_name)
        self.embedding_dim = self.embedder.get_sentence_embedding_dimension()
        
        # Collection name
        self.collection_name = collection_name
        
        # Ensure collection exists
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure Qdrant collection exists"""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE
                )
            )
            
        # Always ensure indexes exist (for new or existing collections)
        self._create_indexes()
    
    async def index_message(self,
                           message_id: int,
                           content: str,
                           channel_id: str,
                           sender_id: str,
                           timestamp: datetime,
                           metadata: Optional[Dict] = None,
                           confidence: Optional[float] = None,
                           sender_project_id: Optional[str] = None,
                           embedding: Optional[List[float]] = None) -> None:
        """
        Index a message in Qdrant for semantic search.
        Automatically extracts array lengths for $size operator support.
        
        Args:
            message_id: Unique message ID (from SQLite)
            content: Message content to embed
            channel_id: Channel identifier
            sender_id: Sender identifier
            timestamp: Message timestamp
            metadata: Optional nested metadata
            confidence: Optional confidence score
            sender_project_id: Optional project ID
            embedding: Pre-computed embedding (optional)
        """
        # Generate embedding if not provided
        if embedding is None:
            embedding = self.embedder.encode(content).tolist()
        
        # Build payload with metadata and array lengths
        payload = {
            "channel_id": channel_id,
            "sender_id": sender_id,
            "sender_project_id": sender_project_id,
            "content": content,  # Store for debugging/analysis
            "metadata": metadata or {},  # Native nested JSON!
            "confidence": confidence or 0.5,
            "timestamp": timestamp.isoformat()
        }
        
        # Add array length fields for $size operator support
        if metadata:
            array_lengths = self._extract_array_lengths(metadata)
            payload.update(array_lengths)
        
        # Store in Qdrant with native nested structure
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=message_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )
    
    def _extract_array_lengths(self, obj: Any, prefix: str = "metadata") -> Dict[str, int]:
        """
        Recursively extract array lengths from nested structures.
        Creates fields like 'metadata.breadcrumbs.files__len' for arrays.
        
        Args:
            obj: Object to traverse (dict, list, or primitive)
            prefix: Current path prefix
            
        Returns:
            Dictionary of path__len -> length mappings
        """
        lengths = {}
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{prefix}.{key}"
                lengths.update(self._extract_array_lengths(value, new_path))
                
        elif isinstance(obj, list):
            # Store the length of this array
            lengths[f"{prefix}__len"] = len(obj)
            
            # Also traverse list items if they're complex objects
            for i, item in enumerate(obj):
                if isinstance(item, dict):
                    # For arrays of objects, we might want to index nested fields
                    item_path = f"{prefix}[{i}]"
                    lengths.update(self._extract_array_lengths(item, item_path))
        
        return lengths
    
    def _build_filter(self, 
                     channel_ids: Optional[List[str]] = None,
                     sender_ids: Optional[List[str]] = None,
                     metadata_filters: Optional[Dict[str, Any]] = None,
                     min_confidence: Optional[float] = None) -> Optional[Filter]:
        """
        Build Qdrant filter from parameters.
        Supports MongoDB-style operators with arbitrary nested metadata filtering.
        
        Supported operators:
        - Comparison: $eq, $ne, $gt, $gte, $lt, $lte
        - Array/List: $in, $nin, $contains, $not_contains, $all, $size
        - Logical: $and, $or, $not
        - Existence: $exists, $null
        - Text: $regex, $text
        - Special: $empty
        """
        must_conditions = []
        should_conditions = []  # For $or operator
        must_not_conditions = []  # For negative operators
        
        # Handle basic filters
        if channel_ids:
            must_conditions.append(FieldCondition(
                key="channel_id",
                match=MatchAny(any=channel_ids)
            ))
        
        if sender_ids:
            must_conditions.append(FieldCondition(
                key="sender_id",
                match=MatchAny(any=sender_ids)
            ))
        
        if min_confidence is not None:
            must_conditions.append(FieldCondition(
                key="confidence",
                range=Range(gte=min_confidence)
            ))
        
        # Handle metadata filters with MongoDB-style operators
        if metadata_filters:
            parsed = self._parse_metadata_filters(metadata_filters)
            must_conditions.extend(parsed['must'])
            should_conditions.extend(parsed['should'])
            must_not_conditions.extend(parsed['must_not'])
        
        # Build the final filter
        filter_kwargs = {}
        
        if must_conditions:
            filter_kwargs['must'] = must_conditions
        
        if should_conditions:
            filter_kwargs['should'] = should_conditions
            
        if must_not_conditions:
            filter_kwargs['must_not'] = must_not_conditions
        
        return Filter(**filter_kwargs) if filter_kwargs else None
    
    def _parse_metadata_filters(self, filters: Dict[str, Any]) -> Dict[str, List]:
        """
        Parse metadata filters recursively to handle all MongoDB operators.
        Returns dict with 'must', 'should', and 'must_not' condition lists.
        """
        result = {
            'must': [],
            'should': [],
            'must_not': []
        }
        
        for field_path, value in filters.items():
            # Handle top-level logical operators
            if field_path == "$and":
                # All conditions must match
                for condition in value:
                    parsed = self._parse_metadata_filters(condition)
                    result['must'].extend(parsed['must'])
                    # Note: Nested should/must_not within $and become must conditions
                    if parsed['should']:
                        # Convert OR within AND to a nested filter
                        result['must'].append(Filter(should=parsed['should']))
                    if parsed['must_not']:
                        result['must'].append(Filter(must_not=parsed['must_not']))
                        
            elif field_path == "$or":
                # At least one condition must match
                for condition in value:
                    parsed = self._parse_metadata_filters(condition)
                    # Each OR branch becomes a should condition with its own filter
                    branch_filter = {}
                    if parsed['must']:
                        branch_filter['must'] = parsed['must']
                    if parsed['should']:
                        branch_filter['should'] = parsed['should']
                    if parsed['must_not']:
                        branch_filter['must_not'] = parsed['must_not']
                    
                    if branch_filter:
                        result['should'].append(Filter(**branch_filter))
                        
            elif field_path == "$not":
                # Negate the condition
                parsed = self._parse_metadata_filters(value)
                # Swap must and must_not
                result['must_not'].extend(parsed['must'])
                result['must'].extend(parsed['must_not'])
                # Handle should conditions (need to negate them)
                if parsed['should']:
                    # All should conditions must NOT match
                    for cond in parsed['should']:
                        result['must_not'].append(cond)
                        
            else:
                # Regular field condition
                conditions = self._parse_field_condition(field_path, value)
                for category, conds in conditions.items():
                    result[category].extend(conds)
        
        return result
    
    def _parse_field_condition(self, field_path: str, value: Any) -> Dict[str, List]:
        """
        Parse a single field condition and return categorized conditions.
        """
        result = {
            'must': [],
            'should': [],
            'must_not': []
        }
        
        # Ensure metadata prefix for non-system fields
        if not field_path.startswith('metadata.') and field_path not in ['channel_id', 'sender_id', 'confidence']:
            field_path = f"metadata.{field_path}"
        
        # Handle MongoDB operators
        if isinstance(value, dict) and any(k.startswith('$') for k in value):
            for op, op_value in value.items():
                # Comparison operators
                if op == "$eq":
                    result['must'].append(FieldCondition(
                        key=field_path,
                        match=MatchValue(value=op_value)
                    ))
                    
                elif op == "$ne":
                    result['must_not'].append(FieldCondition(
                        key=field_path,
                        match=MatchValue(value=op_value)
                    ))
                    
                elif op == "$gt":
                    result['must'].append(FieldCondition(
                        key=field_path,
                        range=Range(gt=op_value)
                    ))
                    
                elif op == "$gte":
                    result['must'].append(FieldCondition(
                        key=field_path,
                        range=Range(gte=op_value)
                    ))
                    
                elif op == "$lt":
                    result['must'].append(FieldCondition(
                        key=field_path,
                        range=Range(lt=op_value)
                    ))
                    
                elif op == "$lte":
                    result['must'].append(FieldCondition(
                        key=field_path,
                        range=Range(lte=op_value)
                    ))
                
                # Array/List operators
                elif op in ["$in", "$contains"]:
                    values = op_value if isinstance(op_value, list) else [op_value]
                    result['must'].append(FieldCondition(
                        key=field_path,
                        match=MatchAny(any=values)
                    ))
                    
                elif op in ["$nin", "$not_contains"]:
                    values = op_value if isinstance(op_value, list) else [op_value]
                    result['must_not'].append(FieldCondition(
                        key=field_path,
                        match=MatchAny(any=values)
                    ))
                    
                elif op == "$all":
                    # All values must be present (multiple must conditions)
                    for val in op_value:
                        result['must'].append(FieldCondition(
                            key=field_path,
                            match=MatchAny(any=[val])
                        ))
                
                elif op == "$size":
                    # Array size check - assumes we index array lengths as field__len
                    result['must'].append(FieldCondition(
                        key=f"{field_path}__len",
                        match=MatchValue(value=op_value)
                    ))
                
                # Existence operators
                elif op == "$exists":
                    if op_value:
                        # Field must exist (not null)
                        # In Qdrant, we check that field is NOT null
                        result['must_not'].append(IsNullCondition(
                            is_null=PayloadField(key=field_path)
                        ))
                    else:
                        # Field must not exist (is null)
                        result['must'].append(IsNullCondition(
                            is_null=PayloadField(key=field_path)
                        ))
                        
                elif op == "$null":
                    # Check if field is null
                    result['must'].append(IsNullCondition(
                        is_null=PayloadField(key=field_path)
                    ))
                    
                elif op == "$empty":
                    # Check if field is empty (for arrays/strings)
                    result['must'].append(IsEmptyCondition(
                        is_empty=PayloadField(key=field_path)
                    ))
                
                # Text operators
                elif op == "$regex":
                    # Text pattern matching
                    result['must'].append(FieldCondition(
                        key=field_path,
                        match=MatchText(text=op_value)
                    ))
                    
                elif op == "$text":
                    # Full text search
                    result['must'].append(FieldCondition(
                        key=field_path,
                        match=MatchText(text=op_value)
                    ))
                
                # Range combinations (between values)
                elif op == "$between":
                    # Expects [min, max]
                    if isinstance(op_value, list) and len(op_value) == 2:
                        result['must'].append(FieldCondition(
                            key=field_path,
                            range=Range(gte=op_value[0], lte=op_value[1])
                        ))
                        
        else:
            # Direct equality match
            result['must'].append(FieldCondition(
                key=field_path,
                match=MatchValue(value=value)
            ))
        
        return result
    
    async def search(self,
                    query: str,
                    channel_ids: Optional[List[str]] = None,
                    sender_ids: Optional[List[str]] = None,
                    metadata_filters: Optional[Dict[str, Any]] = None,
                    min_confidence: Optional[float] = None,
                    limit: int = 20,
                    offset: int = 0) -> List[Tuple[int, float, Dict]]:
        """
        Search for semantically similar messages.
        
        Args:
            query: Search query to embed
            channel_ids: Filter by channels
            sender_ids: Filter by senders
            metadata_filters: Arbitrary nested metadata filters
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of tuples (message_id, score, payload)
        """
        # Generate query embedding
        query_embedding = self.embedder.encode(query).tolist()
        
        # Build filter
        qdrant_filter = self._build_filter(
            channel_ids, sender_ids, metadata_filters, min_confidence
        )
        
        # Search in Qdrant
        search_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            query_filter=qdrant_filter,
            limit=limit,
            offset=offset
        )
        
        # Return results as tuples
        results = []
        for point in search_results:
            results.append((
                point.id,  # message_id
                point.score,  # similarity score
                point.payload  # full payload including metadata
            ))
        
        return results
    
    async def get_by_ids(self, message_ids: List[int]) -> Dict[int, Dict]:
        """
        Retrieve specific messages by IDs.
        
        Args:
            message_ids: List of message IDs to retrieve
            
        Returns:
            Dict mapping message_id to payload
        """
        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=message_ids
        )
        
        return {
            point.id: point.payload
            for point in points
        }
    
    async def delete_messages(self, message_ids: List[int]) -> None:
        """
        Delete messages from Qdrant index.
        
        Args:
            message_ids: List of message IDs to delete
        """
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=message_ids
        )
    
    async def update_metadata(self, 
                             message_id: int, 
                             metadata: Dict[str, Any]) -> None:
        """
        Update metadata for a specific message.
        
        Args:
            message_id: Message ID to update
            metadata: New metadata (replaces existing)
        """
        self.client.set_payload(
            collection_name=self.collection_name,
            payload={"metadata": metadata},
            points=[message_id]
        )
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        Exposed for cases where embedding is needed before storage.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        return self.embedder.encode(text).tolist()
    
    def _create_indexes(self):
        """
        Create indexes for fields we filter on.
        This improves query performance and is REQUIRED for Qdrant Cloud.
        Safe to call multiple times - will skip if indexes already exist.
        """
        try:
            # Create index for channel_id field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="channel_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass  # Index might already exist
        
        try:
            # Create index for sender_id field  
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="sender_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass  # Index might already exist
        
        try:
            # Create index for confidence field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="confidence",
                field_schema=PayloadSchemaType.FLOAT
            )
        except Exception:
            pass  # Index might already exist
        
        try:
            # Create index for timestamp field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="timestamp",
                field_schema=PayloadSchemaType.DATETIME
            )
        except Exception:
            pass  # Index might already exist
    
    def close(self):
        """Close connections (no-op for Qdrant client)"""
        pass  # Qdrant client doesn't need explicit closing