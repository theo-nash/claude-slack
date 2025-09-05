#!/usr/bin/env python3
"""
QdrantStore: Pure Qdrant vector storage operations.
Handles ONLY vector indexing and semantic search, no SQLite knowledge.
"""

import os
import sys
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from ..utils.time_utils import now_timestamp, to_timestamp, from_timestamp

# Add parent directory to path to import log_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, Range, MatchValue, MatchAny,
    MatchText, IsEmptyCondition, IsNullCondition, HasIdCondition,
    NestedCondition, MatchExcept, PayloadField, PayloadSchemaType
)
from sentence_transformers import SentenceTransformer

from ..ranking import RankingProfile, RankingProfiles
from .filters import MongoFilterParser, QdrantFilterBackend, FilterValidator


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
        # Initialize logger
        self.logger = get_logger('QdrantStore', component='manager')
        
        # Initialize Qdrant client
        if qdrant_url:
            # Remote Qdrant (Docker or cloud)
            if qdrant_api_key:
                self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
                self.logger.info(f"Connected to Qdrant cloud at {qdrant_url}")
            else:
                self.client = QdrantClient(url=qdrant_url)
                self.logger.info(f"Connected to Qdrant server at {qdrant_url}")
        elif qdrant_path:
            # Local Qdrant with explicit path
            self.client = QdrantClient(path=qdrant_path)
            self.logger.info(f"Initialized local Qdrant at {qdrant_path}")
        else:
            raise ValueError("Must provide either qdrant_path or qdrant_url")
        
        # Set up embedding model
        model_name = embedding_model or "all-MiniLM-L6-v2"
        
        # Detect best available device (CUDA if available and working, else CPU)
        import torch
        device = 'cpu'
        if torch.cuda.is_available():
            try:
                # Test if CUDA actually works with a small tensor
                test_tensor = torch.tensor([1.0]).cuda()
                _ = test_tensor * 2
                device = 'cuda'
                self.logger.info(f"Using CUDA for embeddings")
            except Exception as e:
                self.logger.warning(f"CUDA available but not working: {e}. Falling back to CPU")
                device = 'cpu'
        else:
            self.logger.info(f"CUDA not available, using CPU for embeddings")
        
        self.embedder = SentenceTransformer(model_name, device=device)
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
            self.logger.info(f"Created Qdrant collection '{self.collection_name}' with dimension {self.embedding_dim}")
        else:
            self.logger.debug(f"Using existing Qdrant collection '{self.collection_name}'")
            
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
            self.logger.debug(f"Generated embedding for message {message_id}")
        
        # Build payload with metadata and array lengths
        payload = {
            "channel_id": channel_id,
            "sender_id": sender_id,
            "sender_project_id": sender_project_id,
            "content": content,  # Store for debugging/analysis
            "metadata": metadata or {},  # Native nested JSON!
            "confidence": confidence or 0.5,
            "timestamp": to_timestamp(timestamp)  # Store as Unix timestamp
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
        self.logger.debug(f"Indexed message {message_id} in channel {channel_id}")
    
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
                     min_confidence: Optional[float] = None,
                     since: Optional[datetime] = None,
                     until: Optional[datetime] = None) -> Optional[Filter]:
        """
        Build Qdrant filter from parameters using the shared filter system.
        Supports MongoDB-style operators with arbitrary nested metadata filtering.
        """
        # Build combined filter object
        combined_filters = {}
        
        # Add basic filters as top-level conditions
        if channel_ids:
            combined_filters['channel_id'] = {'$in': channel_ids}
        
        if sender_ids:
            combined_filters['sender_id'] = {'$in': sender_ids}
        
        if min_confidence is not None:
            combined_filters['confidence'] = {'$gte': min_confidence}
        
        # Add time filters - convert to Unix timestamp for numeric comparison
        if since is not None:
            combined_filters['timestamp'] = combined_filters.get('timestamp', {})
            combined_filters['timestamp']['$gte'] = to_timestamp(since)
        
        if until is not None:
            combined_filters['timestamp'] = combined_filters.get('timestamp', {})
            combined_filters['timestamp']['$lte'] = to_timestamp(until)
        
        # Merge metadata filters
        if metadata_filters:
            # Validate filters first
            validator = FilterValidator.create_default()
            try:
                validated_filters = validator.validate(metadata_filters)
            except Exception as e:
                self.logger.error(f"Filter validation failed: {e}")
                raise ValueError(f"Invalid filter structure: {e}")
            
            # Merge validated filters with basic filters
            # If there are both, wrap in $and
            if combined_filters:
                combined_filters = {
                    '$and': [
                        combined_filters,
                        validated_filters
                    ]
                }
            else:
                combined_filters = validated_filters
        
        # If no filters, return None
        if not combined_filters:
            return None
        
        # Parse using shared system
        parser = MongoFilterParser()
        backend = QdrantFilterBackend(metadata_prefix='metadata')
        
        try:
            expression = parser.parse(combined_filters)
            qdrant_filter = backend.convert(expression)
            return qdrant_filter
        except Exception as e:
            self.logger.error(f"Failed to build Qdrant filter: {e}")
            raise ValueError(f"Failed to build filter: {e}")
    
    async def search(self,
                    query: str,
                    channel_ids: Optional[List[str]] = None,
                    sender_ids: Optional[List[str]] = None,
                    metadata_filters: Optional[Dict[str, Any]] = None,
                    min_confidence: Optional[float] = None,
                    since: Optional[datetime] = None,
                    until: Optional[datetime] = None,
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
            since: Only messages after this timestamp
            until: Only messages before this timestamp
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of tuples (message_id, score, payload)
        """
        # Generate query embedding
        query_embedding = self.embedder.encode(query).tolist()
        self.logger.debug(f"Searching for: '{query[:50]}...' with limit={limit}")
        
        # Build filter
        qdrant_filter = self._build_filter(
            channel_ids, sender_ids, metadata_filters, min_confidence, since, until
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
        
        self.logger.info(f"Search found {len(results)} results for query: '{query[:30]}...'")
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
        if not message_ids:
            return
            
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=message_ids
        )
        self.logger.info(f"Deleted {len(message_ids)} messages from Qdrant index")
    
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
            self.logger.debug("Created index for channel_id field")
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