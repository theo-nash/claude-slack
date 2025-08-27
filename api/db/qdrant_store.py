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
    Filter, FieldCondition, Range, MatchValue, MatchAny
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
        
        # Store in Qdrant with native nested structure
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=message_id,
                    vector=embedding,
                    payload={
                        "channel_id": channel_id,
                        "sender_id": sender_id,
                        "sender_project_id": sender_project_id,
                        "content": content,  # Store for debugging/analysis
                        "metadata": metadata or {},  # Native nested JSON!
                        "confidence": confidence or 0.5,
                        "timestamp": timestamp.isoformat()
                    }
                )
            ]
        )
    
    def _build_filter(self, 
                     channel_ids: Optional[List[str]] = None,
                     sender_ids: Optional[List[str]] = None,
                     metadata_filters: Optional[Dict[str, Any]] = None,
                     min_confidence: Optional[float] = None) -> Optional[Filter]:
        """
        Build Qdrant filter from parameters.
        Supports arbitrary nested metadata filtering with dot notation.
        """
        conditions = []
        
        if channel_ids:
            conditions.append(FieldCondition(
                key="channel_id",
                match=MatchAny(any=channel_ids)
            ))
        
        if sender_ids:
            conditions.append(FieldCondition(
                key="sender_id",
                match=MatchAny(any=sender_ids)
            ))
        
        if min_confidence is not None:
            conditions.append(FieldCondition(
                key="confidence",
                range=Range(gte=min_confidence)
            ))
        
        # Handle arbitrary metadata filters
        if metadata_filters:
            for field_path, value in metadata_filters.items():
                # Prepend 'metadata.' if not already there
                if not field_path.startswith('metadata.'):
                    field_path = f"metadata.{field_path}"
                
                if isinstance(value, dict) and any(k.startswith('$') for k in value):
                    # Handle MongoDB-style operators
                    for op, op_value in value.items():
                        if op == "$gte":
                            conditions.append(FieldCondition(
                                key=field_path,
                                range=Range(gte=op_value)
                            ))
                        elif op == "$gt":
                            conditions.append(FieldCondition(
                                key=field_path,
                                range=Range(gt=op_value)
                            ))
                        elif op == "$lte":
                            conditions.append(FieldCondition(
                                key=field_path,
                                range=Range(lte=op_value)
                            ))
                        elif op == "$lt":
                            conditions.append(FieldCondition(
                                key=field_path,
                                range=Range(lt=op_value)
                            ))
                        elif op in ["$in", "$contains"]:
                            # Qdrant uses MatchAny for "in" operations
                            values = op_value if isinstance(op_value, list) else [op_value]
                            conditions.append(FieldCondition(
                                key=field_path,
                                match=MatchAny(any=values)
                            ))
                        elif op == "$ne":
                            # Not equal - Qdrant doesn't have direct support, 
                            # would need to use should_not in Filter
                            pass  # Skip for now, can be added if needed
                else:
                    # Direct equality
                    conditions.append(FieldCondition(
                        key=field_path,
                        match=MatchValue(value=value)
                    ))
        
        return Filter(must=conditions) if conditions else None
    
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
    
    def close(self):
        """Close connections (no-op for Qdrant client)"""
        pass  # Qdrant client doesn't need explicit closing