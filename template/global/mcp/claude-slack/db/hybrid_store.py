#!/usr/bin/env python3
"""
HybridStore: Dual storage system with SQLite + ChromaDB
Provides semantic search with time decay and confidence ranking.
"""

import os
import json
import math
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions


@dataclass
class RankingProfile:
    """Ranking parameters for search"""
    decay_half_life_hours: float = 168  # 1 week default
    decay_weight: float = 0.33
    similarity_weight: float = 0.34
    confidence_weight: float = 0.33


class RankingProfiles:
    """Pre-defined ranking profiles for common use cases"""
    
    RECENT_PRIORITY = RankingProfile(
        decay_half_life_hours=24,  # 1 day half-life
        decay_weight=0.6,
        similarity_weight=0.3,
        confidence_weight=0.1
    )
    
    QUALITY_PRIORITY = RankingProfile(
        decay_half_life_hours=720,  # 30 days half-life
        decay_weight=0.1,
        similarity_weight=0.4,
        confidence_weight=0.5
    )
    
    BALANCED = RankingProfile(
        decay_half_life_hours=168,  # 1 week half-life
        decay_weight=0.33,
        similarity_weight=0.34,
        confidence_weight=0.33
    )
    
    SIMILARITY_ONLY = RankingProfile(
        decay_half_life_hours=8760,  # 1 year (minimal decay)
        decay_weight=0.0,
        similarity_weight=1.0,
        confidence_weight=0.0
    )
    
    @classmethod
    def get_profile(cls, name: str) -> RankingProfile:
        """Get a named profile"""
        profiles = {
            'recent': cls.RECENT_PRIORITY,
            'quality': cls.QUALITY_PRIORITY,
            'balanced': cls.BALANCED,
            'similarity': cls.SIMILARITY_ONLY
        }
        return profiles.get(name, cls.BALANCED)


class HybridStore:
    """
    Dual storage system combining SQLite for structured data
    and ChromaDB for vector embeddings and semantic search.
    """
    
    def __init__(self, 
                 sqlite_path: str,
                 chroma_path: Optional[str] = None,
                 embedding_model: Optional[str] = None):
        """
        Initialize the hybrid store.
        
        Args:
            sqlite_path: Path to SQLite database
            chroma_path: Path to ChromaDB storage (defaults to sibling directory)
            embedding_model: Optional embedding model name (uses ChromaDB default if None)
        """
        # SQLite setup
        self.sqlite_path = sqlite_path
        self.conn = sqlite3.connect(sqlite_path)
        self.conn.row_factory = sqlite3.Row
        
        # ChromaDB setup
        if chroma_path is None:
            # Default to sibling directory of SQLite
            db_dir = os.path.dirname(sqlite_path)
            chroma_path = os.path.join(db_dir, 'chroma')
        
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Set up embedding function
        # Use ChromaDB's default embedding (all-MiniLM-L6-v2) or specified model
        if embedding_model:
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=embedding_model
            )
        else:
            # Use ChromaDB's default embedding function
            self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        
        # Get or create collection with embedding function
        self.collection = self.chroma_client.get_or_create_collection(
            name="messages",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function
        )
        
        # Initialize database schema
        self._init_schema()
    
    def _init_schema(self):
        """Verify schema exists - we use the existing schema.sql"""
        # The schema is already created by the existing DatabaseManager
        # We just verify the tables we need exist
        cursor = self.conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('messages', 'channels')
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'messages' not in tables or 'channels' not in tables:
            raise RuntimeError(
                "Required tables not found. Please ensure the database is "
                "initialized with the standard schema.sql"
            )
    
    async def store_message(self,
                           channel_id: str,
                           sender_id: str,
                           content: str,
                           metadata: Optional[Dict] = None,
                           confidence: Optional[float] = None,
                           sender_project_id: Optional[str] = None) -> int:
        """
        Store a message in both SQLite and ChromaDB.
        
        Args:
            channel_id: Channel identifier (e.g., "notes:agent-1")
            sender_id: Sender identifier
            content: Message content
            metadata: Optional metadata dict
            confidence: Optional confidence score [0, 1]
            sender_project_id: Optional project ID for the sender
            
        Returns:
            Message ID
        """
        # Store in SQLite using existing schema
        cursor = self.conn.execute(
            """
            INSERT INTO messages (channel_id, sender_id, sender_project_id, 
                                content, metadata, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (channel_id, sender_id, sender_project_id, content, 
             json.dumps(metadata) if metadata else None,
             confidence)
        )
        self.conn.commit()
        message_id = cursor.lastrowid
        
        # Prepare ChromaDB metadata
        chroma_metadata = {
            "channel_id": channel_id,
            "sender_id": sender_id,
            "confidence": str(confidence or 0.5),
            "timestamp": datetime.now().isoformat(),
            "message_type": metadata.get("type", "message") if metadata else "message"
        }
        
        # Add searchable fields from metadata
        if metadata:
            for key in ["task_id", "session_id", "outcome", "perspective"]:
                if key in metadata:
                    chroma_metadata[key] = str(metadata[key])
        
        # Store in ChromaDB (embedding will be generated automatically)
        self.collection.add(
            ids=[str(message_id)],
            documents=[content],  # ChromaDB will generate embeddings from this
            metadatas=[chroma_metadata]
        )
        
        return message_id
    
    async def add_to_chroma(self,
                           message_id: int,
                           channel_id: str,
                           sender_id: str,
                           content: str,
                           metadata: Optional[Dict] = None,
                           confidence: Optional[float] = None,
                           sender_project_id: Optional[str] = None) -> None:
        """
        Add an existing message to ChromaDB for semantic search.
        This is used when message already exists in SQLite.
        
        Args:
            message_id: Existing message ID from SQLite
            channel_id: Channel identifier
            sender_id: Sender identifier
            content: Message content
            metadata: Optional metadata dict
            confidence: Optional confidence score
            sender_project_id: Optional project ID
        """
        # Prepare ChromaDB metadata
        chroma_metadata = {
            "channel_id": channel_id,
            "sender_id": sender_id,
            "confidence": str(confidence or 0.5),
            "timestamp": datetime.now().isoformat(),
            "message_type": metadata.get("type", "message") if metadata else "message"
        }
        
        # Add searchable fields from metadata
        if metadata:
            for key in ["task_id", "session_id", "outcome", "perspective"]:
                if key in metadata:
                    chroma_metadata[key] = str(metadata[key])
        
        # Store in ChromaDB (embedding will be generated automatically)
        self.collection.add(
            ids=[str(message_id)],
            documents=[content],
            metadatas=[chroma_metadata]
        )
        
    
    def _calculate_decay(self, age_hours: float, half_life_hours: float) -> float:
        """Calculate exponential decay score based on age"""
        # Handle edge cases to prevent overflow
        if age_hours < 0:
            return 1.0  # Future messages get max score
        if half_life_hours <= 0:
            return 0.0  # Invalid half-life
        
        # Prevent overflow for very large ratios
        ratio = age_hours / half_life_hours
        if ratio > 100:  # Message is >100 half-lives old
            return 0.0
        
        return math.exp(-math.log(2) * ratio)
    
    def _build_chroma_where(self, 
                           channel_ids: Optional[List[str]] = None,
                           sender_ids: Optional[List[str]] = None,
                           message_type: Optional[str] = None,
                           min_confidence: Optional[float] = None,
                           since: Optional[datetime] = None) -> Optional[Dict]:
        """Build ChromaDB where clause from filters"""
        where = {}
        where_conditions = []
        
        if channel_ids:
            where_conditions.append({"channel_id": {"$in": channel_ids}})
        
        if sender_ids:
            where_conditions.append({"sender_id": {"$in": sender_ids}})
        
        if message_type:
            where_conditions.append({"message_type": message_type})
        
        if min_confidence is not None:
            # ChromaDB stores as string, need to filter in post-processing
            pass  # Handle in post-processing
        
        if since:
            # ChromaDB doesn't support date comparison well, filter in post
            pass  # Handle in post-processing
        
        if where_conditions:
            if len(where_conditions) == 1:
                where = where_conditions[0]
            else:
                where = {"$and": where_conditions}
        
        return where if where else None
    
    async def search(self,
                    query: Optional[str] = None,
                    channel_ids: Optional[List[str]] = None,
                    sender_ids: Optional[List[str]] = None,
                    message_type: Optional[str] = None,
                    min_confidence: Optional[float] = None,
                    since: Optional[datetime] = None,
                    limit: int = 20,
                    ranking_profile: Any = "balanced") -> List[Dict]:
        """
        Search messages with semantic similarity and intelligent ranking.
        
        Args:
            query: Semantic search query (optional)
            channel_ids: Filter by channels
            sender_ids: Filter by senders
            message_type: Filter by message type from metadata
            min_confidence: Minimum confidence threshold
            since: Only messages after this time
            limit: Maximum results to return
            ranking_profile: Profile name or RankingProfile object or dict
            
        Returns:
            List of messages with search scores
        """
        # Get ranking parameters
        if isinstance(ranking_profile, str):
            profile = RankingProfiles.get_profile(ranking_profile)
        elif isinstance(ranking_profile, dict):
            profile = RankingProfile(**ranking_profile)
        else:
            profile = ranking_profile
        
        results = []
        
        if query:
            # Semantic search via ChromaDB (ChromaDB will generate embedding from query)
            chroma_results = self.collection.query(
                query_texts=[query],  # ChromaDB generates embeddings automatically
                n_results=limit * 3,  # Get extra for filtering and re-ranking
                where=self._build_chroma_where(
                    channel_ids, sender_ids, message_type
                )
            )
            
            if not chroma_results['ids'][0]:
                return []
            
            message_ids = chroma_results['ids'][0]
            distances = chroma_results['distances'][0]
            metadatas = chroma_results['metadatas'][0]
            
            # Fetch full messages from SQLite and calculate scores
            now = datetime.now()
            scored_results = []
            
            for msg_id, distance, meta in zip(message_ids, distances, metadatas):
                # Fetch from SQLite
                cursor = self.conn.execute(
                    "SELECT * FROM messages WHERE id = ?",
                    (int(msg_id),)
                )
                row = cursor.fetchone()
                if not row:
                    continue
                
                msg = dict(row)
                
                # Parse stored JSON metadata
                if msg['metadata']:
                    msg['metadata'] = json.loads(msg['metadata'])
                
                # Apply filters that ChromaDB couldn't handle
                if min_confidence and (msg.get('confidence') or 0) < min_confidence:
                    continue
                
                # Parse timestamp - SQLite may return different formats
                try:
                    msg_time = datetime.fromisoformat(msg['timestamp'].replace(' ', 'T'))
                except:
                    # Fallback to parsing SQLite format
                    from datetime import datetime as dt
                    msg_time = dt.strptime(msg['timestamp'], '%Y-%m-%d %H:%M:%S')
                
                if since and msg_time < since:
                    continue
                
                # Calculate component scores
                similarity_score = 1 - distance
                confidence_score = msg.get('confidence') or 0.5  # Handle None values
                
                # Calculate time decay
                age_hours = max(0, (now - msg_time).total_seconds() / 3600)  # Ensure non-negative
                decay_score = self._calculate_decay(
                    age_hours, profile.decay_half_life_hours
                )
                
                # Calculate final score
                total_weight = (profile.similarity_weight + 
                              profile.confidence_weight + 
                              profile.decay_weight)
                
                final_score = (
                    (similarity_score * profile.similarity_weight +
                     confidence_score * profile.confidence_weight +
                     decay_score * profile.decay_weight) / total_weight
                )
                
                # Add scoring details
                msg['search_scores'] = {
                    'final_score': final_score,
                    'similarity': similarity_score,
                    'confidence': confidence_score,
                    'recency': decay_score,
                    'age_hours': age_hours
                }
                
                scored_results.append((final_score, msg))
            
            # Sort by final score and limit
            scored_results.sort(key=lambda x: x[0], reverse=True)
            results = [msg for _, msg in scored_results[:limit]]
        
        else:
            # Pure filter search via SQLite
            sql = """
                SELECT *,
                       (julianday('now') - julianday(timestamp)) * 24 as age_hours
                FROM messages
                WHERE 1=1
            """
            params = []
            
            if channel_ids:
                placeholders = ','.join('?' * len(channel_ids))
                sql += f" AND channel_id IN ({placeholders})"
                params.extend(channel_ids)
            
            if sender_ids:
                placeholders = ','.join('?' * len(sender_ids))
                sql += f" AND sender_id IN ({placeholders})"
                params.extend(sender_ids)
            
            if min_confidence is not None:
                sql += " AND confidence >= ?"
                params.append(min_confidence)
            
            if since:
                sql += " AND timestamp >= ?"
                params.append(since.isoformat())
            
            # Order by recency for non-semantic search
            sql += " ORDER BY timestamp DESC, confidence DESC LIMIT ?"
            params.append(limit)
            
            cursor = self.conn.execute(sql, params)
            
            for row in cursor.fetchall():
                msg = dict(row)
                
                # Parse metadata
                if msg['metadata']:
                    metadata = json.loads(msg['metadata'])
                    if message_type and metadata.get('type') != message_type:
                        continue
                    msg['metadata'] = metadata
                
                # Ensure age_hours is non-negative
                age_hours = max(0, msg.get('age_hours', 0))
                
                # Add decay score for consistency
                decay_score = self._calculate_decay(
                    age_hours, profile.decay_half_life_hours
                )
                
                msg['search_scores'] = {
                    'recency': decay_score,
                    'confidence': msg.get('confidence') or 0.5,
                    'age_hours': age_hours
                }
                
                results.append(msg)
        
        return results
    
    async def get_message(self, message_id: int) -> Optional[Dict]:
        """Get a single message by ID"""
        cursor = self.conn.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,)
        )
        row = cursor.fetchone()
        if row:
            msg = dict(row)
            if msg['metadata']:
                msg['metadata'] = json.loads(msg['metadata'])
            return msg
        return None
    
    def close(self):
        """Close database connections"""
        self.conn.close()