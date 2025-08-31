#!/usr/bin/env python3
"""
MessageStore: Unified storage abstraction that coordinates SQLite and Qdrant.
This is the single entry point for all message storage and retrieval operations.
"""

import os
import sys
import math
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

# Add parent directory to path to import log_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from log_manager import get_logger
except ImportError:
    import logging
    def get_logger(name, component=None):
        return logging.getLogger(name)

from .sqlite_store import SQLiteStore
from .qdrant_store import QdrantStore
from ..ranking import RankingProfiles, RankingProfile
from ..channels.manager import ChannelManager


class MessageStore:
    """
    Unified storage abstraction that coordinates between SQLite and Qdrant.
    
    Responsibilities:
    - Single transaction boundary for message storage
    - Coordinates SQLite (source of truth) and Qdrant (vector search)
    - Handles fallback logic when semantic search is unavailable
    - Ensures consistency between stores
    """
    
    def __init__(self, 
                 db_path: str,
                 qdrant_config: Optional[Dict] = None):
        """
        Initialize the unified message store.
        
        Args:
            db_path: Path to SQLite database
            qdrant_config: Optional Qdrant configuration:
                {
                    'qdrant_path': str,  # Local path
                    'qdrant_url': str,   # Remote URL
                    'qdrant_api_key': str,  # API key
                    'embedding_model': str  # Model name
                }
        """
        # Initialize logger
        self.logger = get_logger('MessageStore', component='manager')
        
        # Initialize SQLite store (always required)
        self.sqlite = SQLiteStore(db_path)
        self.logger.info(f"Initialized SQLite store at {db_path}")
        
        # Initialize Qdrant store (optional)
        self.qdrant = None
        if qdrant_config:
            try:
                self.qdrant = QdrantStore(**qdrant_config)
                self.logger.info("Qdrant store initialized - semantic search enabled")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Qdrant: {e} - continuing with SQLite only")
                # Continue without semantic search
        else:
            self.logger.debug("No Qdrant config provided - using SQLite only")
    
    async def initialize(self):
        """Initialize both stores"""
        self.logger.info("Initializing MessageStore")
        await self.sqlite.initialize()
        self.logger.info("MessageStore initialization complete")
    
    async def close(self):
        """Close all connections"""
        self.logger.info("Closing MessageStore connections")
        await self.sqlite.close()
        if self.qdrant:
            self.qdrant.close()
        self.logger.info("All connections closed")
    
    def has_semantic_search(self) -> bool:
        """Check if semantic search is available"""
        return self.qdrant is not None
    
    # ============================================================================
    # Message Storage
    # ============================================================================
    
    async def send_message(self,
                          channel_id: str,
                          sender_id: str,
                          sender_project_id: Optional[str],
                          content: str,
                          metadata: Optional[Dict] = None,
                          thread_id: Optional[str] = None) -> int:
        """
        Store a message in both SQLite and Qdrant.
        
        This is the primary storage method that ensures consistency.
        SQLite is the source of truth; Qdrant indexing is best-effort.
        
        Args:
            channel_id: Target channel
            sender_id: Sender agent name
            sender_project_id: Sender's project ID
            content: Message content
            metadata: Optional nested metadata
            thread_id: Optional thread ID
            
        Returns:
            Message ID
        """
        # Extract confidence from metadata if present
        confidence = None
        if metadata and isinstance(metadata, dict):
            confidence = metadata.get('confidence')
        
        # Ensure the channel exists
        self.logger.debug(f"Sending message to channel {channel_id} from {sender_id}")
        channel = await self.sqlite.get_channel(channel_id)
        if not channel:
            self.logger.error(f"Channel '{channel_id}' does not exist")
            raise ValueError(f"Channel '{channel_id}' does not exist")
        
        # Store in SQLite (source of truth)
        message_id = await self.sqlite.send_message(
            channel_id=channel_id,
            sender_id=sender_id,
            sender_project_id=sender_project_id,
            content=content,
            metadata=metadata,
            thread_id=thread_id
        )
        self.logger.debug(f"Message {message_id} stored in SQLite")
        
        # Index in Qdrant for semantic search (best-effort)
        if self.qdrant:
            try:
                # Get the timestamp from the just-created message
                message = await self.sqlite.get_message(message_id)
                timestamp = datetime.fromisoformat(message['timestamp'])
                
                await self.qdrant.index_message(
                    message_id=message_id,
                    content=content,
                    channel_id=channel_id,
                    sender_id=sender_id,
                    timestamp=timestamp,
                    metadata=metadata,
                    confidence=confidence,
                    sender_project_id=sender_project_id
                )
                self.logger.debug(f"Message {message_id} indexed in Qdrant")
            except Exception as e:
                # Log but don't fail the message send
                self.logger.warning(f"Failed to index message {message_id} in Qdrant: {e}")
        
        self.logger.info(f"Message {message_id} sent successfully to {channel_id}")
        return message_id
    
    # ============================================================================
    # Message Retrieval
    # ============================================================================
    
    async def get_message(self, 
                          message_id: int,
                          agent_name: Optional[str] = None,
                         agent_project_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get a specific message by ID.
        
        Args:
            message_id: The message ID
            agent_name: Optional agent requesting (for permission check)
            agent_project_id: Optional agent's project ID
        
        Returns:
            Message dict or None if not found/not accessible
        """
        self.logger.debug(f"Retrieving message {message_id}")
        return await self.sqlite.get_message(message_id)
    
    async def get_agent_messages(self,
                                agent_name: str,
                                agent_project_id: Optional[str] = None,
                                channel_id: Optional[str] = None,
                                limit: int = 100,
                                since: Optional[datetime] = None) -> List[Dict]:
        """
        Get messages visible to a specific agent (with permission checks).
        
        This method enforces SQLite-level permissions, only returning
        messages from channels the agent has access to.
        
        Args:
            agent_name: Agent requesting messages (for permissions)
            agent_project_id: Agent's project ID
            channel_id: Optional specific channel filter
            limit: Maximum messages
            since: Only messages after this timestamp
            
        Returns:
            List of message dictionaries visible to the agent
        """
        
        # Normalize channel ID
        if channel_id:
            self.logger.debug(f"Normalizing channel ID: {channel_id}")
            channel_id = ChannelManager.normalize_channel_id(
                channel_id,
                project_id=agent_project_id
            )
      
        # Delegate to SQLite with agent context for permission enforcement
        self.logger.debug(f"Getting messages for agent {agent_name} (project: {agent_project_id})")
        return await self.sqlite.get_messages(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            channel_id=channel_id,
            limit=limit,
            since=since
        )
    
    async def get_messages(self,
                          channel_ids: Optional[List[str]] = None,
                          sender_ids: Optional[List[str]] = None,
                          message_ids: Optional[List[int]] = None,
                          limit: int = 100,
                          since: Optional[datetime] = None) -> List[Dict]:
        """
        Get messages without permission checks (administrative access).
        
        This method bypasses agent permissions and retrieves messages
        directly. Use this for system operations, data migration, or
        administrative tasks.
        
        Args:
            channel_ids: Optional list of channel IDs to filter
            sender_ids: Optional list of sender IDs to filter
            message_ids: Optional list of specific message IDs
            limit: Maximum messages
            since: Only messages after this timestamp
            
        Returns:
            List of message dictionaries (no permission filtering)
        """
        # Use the new admin method that bypasses permissions
        self.logger.debug(f"Getting messages (admin mode) - channels: {channel_ids}, limit: {limit}")
        return await self.sqlite.get_messages_admin(
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            message_ids=message_ids,
            limit=limit,
            since=since
        )
    
    async def get_messages_by_ids(self,
                                 message_ids: List[int],
                                 agent_name: Optional[str] = None,
                                 agent_project_id: Optional[str] = None) -> List[Dict]:
        """
        Get multiple messages by their IDs.
        
        Args:
            message_ids: List of message IDs to retrieve
            agent_name: Optional agent requesting (for permission check)
            agent_project_id: Optional agent's project ID
        
        Returns:
            List of message dictionaries
        """
        self.logger.debug(f"Getting {len(message_ids)} messages by IDs")
        return await self.sqlite.get_messages_by_ids(
            message_ids=message_ids,
            agent_name=agent_name,
            agent_project_id=agent_project_id
        )
    
    # ============================================================================
    # Search Operations
    # ============================================================================
    
    async def search_messages(self,
                             query: Optional[str] = None,
                             project_ids: Optional[List[str]] = None,
                             channel_ids: Optional[List[str]] = None,
                             sender_ids: Optional[List[str]] = None,
                             metadata_filters: Optional[Dict[str, Any]] = None,
                             min_confidence: Optional[float] = None,
                             limit: int = 20,
                             ranking_profile: Union[str, RankingProfile, Dict] = "balanced") -> List[Dict]:
        """
        Search messages with optional semantic similarity.
        
        This method intelligently routes between:
        - Semantic search (Qdrant) when query is provided and available
        - Filter search (SQLite) for pure filtering operations
        - Hybrid approach combining both
        
        Args:
            query: Semantic search query (optional)
            project_ids: Filter by projects (None = all, [] = none, ["global"] = global only)
            channel_ids: Filter by specific channels (overrides project filtering)
            sender_ids: Filter by senders
            metadata_filters: Arbitrary nested metadata filters with MongoDB-style operators
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            ranking_profile: Ranking profile for semantic search
            
        Returns:
            List of messages with scores (if semantic)
        """
        # Handle project-based channel filtering
        if channel_ids is None and project_ids is not None:
            # If empty list, return no results
            if len(project_ids) == 0:
                self.logger.debug("Empty project_ids list, returning no results")
                return []
            
            # Get channels for specified projects
            self.logger.debug(f"Getting channels for projects: {project_ids}")
            channel_ids = await self._get_channels_for_projects(project_ids)
            if not channel_ids:
                self.logger.debug(f"No channels found for projects: {project_ids}")
                return []  # No channels found for specified projects
        
        if query and self.qdrant:
            # Semantic search via Qdrant
            self.logger.info(f"Performing semantic search: query='{query[:50]}...', limit={limit}")
            results = await self._semantic_search(
                query=query,
                channel_ids=channel_ids,
                sender_ids=sender_ids,
                metadata_filters=metadata_filters,
                min_confidence=min_confidence,
                limit=limit,
                ranking_profile=ranking_profile
            )
        else:
            # Filter-based search via SQLite
            self.logger.info(f"Performing filter-based search (no semantic): limit={limit}")
            results = await self._filter_search(
                channel_ids=channel_ids,
                sender_ids=sender_ids,
                metadata_filters=metadata_filters,
                min_confidence=min_confidence,
                limit=limit
            )
        
        self.logger.debug(f"Search returned {len(results)} results")
        return results
    
    async def search_agent_messages(self,
                                   agent_name: str,
                                   agent_project_id: Optional[str] = None,
                                   query: Optional[str] = None,
                                   channel_ids: Optional[List[str]] = None,
                                   sender_ids: Optional[List[str]] = None,
                                   metadata_filters: Optional[Dict[str, Any]] = None,
                                   min_confidence: Optional[float] = None,
                                   limit: int = 20,
                                   ranking_profile: Union[str, RankingProfile, Dict] = "balanced") -> List[Dict]:
        """
        Search messages with agent permission checks.
        
        This method ensures the agent can only search messages in channels
        they have access to. It first gets the agent's accessible channels,
        then performs the search within that scope.
        
        Args:
            agent_name: Agent performing the search (for permissions)
            agent_project_id: Agent's project ID
            query: Semantic search query (optional)
            channel_ids: Filter by specific channels (will be intersected with accessible channels)
            sender_ids: Filter by senders
            metadata_filters: Arbitrary nested metadata filters
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            ranking_profile: Ranking profile for semantic search
            
        Returns:
            List of messages with scores (if semantic) that agent has permission to see
        """
        # Normalize channel IDs
        _channel_ids = []
        
        if channel_ids:
            for channel_id in channel_ids:
                _channel_id = ChannelManager.normalize_channel_id(
                    channel_id,
                    project_id=agent_project_id
                )
                _channel_ids.append(_channel_id)
        
        # Get channels accessible to the agent
        self.logger.debug(f"Getting accessible channels for agent {agent_name}")
        accessible_channels = await self.sqlite.get_agent_channels(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            include_archived=False
        )
        
        accessible_channel_ids = [ch['id'] for ch in accessible_channels]
        
        # If no accessible channels, return empty
        if not accessible_channel_ids:
            self.logger.debug(f"Agent {agent_name} has no accessible channels")
            return []
        
        # If channel_ids specified, intersect with accessible channels
        if _channel_ids:
            # Only search in channels that are both specified AND accessible
            search_channel_ids = list(set(_channel_ids) & set(accessible_channel_ids))
            if not search_channel_ids:
                self.logger.debug("No overlap between requested and accessible channels")
                return []  # No overlap between requested and accessible channels
        else:
            # Search all accessible channels
            search_channel_ids = accessible_channel_ids
        
        # Now perform the search with the permission-filtered channel list
        if query and self.qdrant:
            # Semantic search via Qdrant
            self.logger.info(f"Agent {agent_name} semantic search: query='{query[:50]}...', channels={len(search_channel_ids)}")
            results = await self._semantic_search(
                query=query,
                channel_ids=search_channel_ids,
                sender_ids=sender_ids,
                metadata_filters=metadata_filters,
                min_confidence=min_confidence,
                limit=limit,
                ranking_profile=ranking_profile
            )
        else:
            # Filter-based search via SQLite
            self.logger.info(f"Agent {agent_name} filter search: channels={len(search_channel_ids)}")
            results = await self._filter_search_agent(
                agent_name=agent_name,
                agent_project_id=agent_project_id,
                channel_ids=search_channel_ids,
                sender_ids=sender_ids,
                metadata_filters=metadata_filters,
                min_confidence=min_confidence,
                limit=limit
            )
        
        self.logger.debug(f"Agent search returned {len(results)} results for {agent_name}")
        return results
    
    async def _semantic_search(self,
                              query: str,
                              channel_ids: Optional[List[str]] = None,
                              sender_ids: Optional[List[str]] = None,
                              metadata_filters: Optional[Dict[str, Any]] = None,
                              min_confidence: Optional[float] = None,
                              limit: int = 20,
                              ranking_profile: Union[str, RankingProfile, Dict] = "balanced") -> List[Dict]:
        """
        Perform semantic search using Qdrant + SQLite.
        
        Strategy:
        1. Search in Qdrant for semantically similar messages
        2. Retrieve full message data from SQLite
        3. Apply time decay and confidence ranking
        4. Return ranked results
        """
        # Get ranking profile
        if isinstance(ranking_profile, str):
            profile = RankingProfiles.get_profile(ranking_profile)
        elif isinstance(ranking_profile, dict):
            profile = RankingProfile(**ranking_profile)
        else:
            profile = ranking_profile
        
        # Search in Qdrant
        self.logger.debug(f"Querying Qdrant with ranking profile: {ranking_profile}")
        qdrant_results = await self.qdrant.search(
            query=query,
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            metadata_filters=metadata_filters,
            min_confidence=min_confidence,
            limit=limit * 3  # Get extra for re-ranking
        )
        
        if not qdrant_results:
            self.logger.debug("No results from Qdrant")
            return []
        
        # Extract message IDs and scores
        message_scores = {}
        message_payloads = {}
        for msg_id, score, payload in qdrant_results:
            message_scores[msg_id] = score
            message_payloads[msg_id] = payload
        
        # Retrieve full messages from SQLite
        message_ids = list(message_scores.keys())
        self.logger.debug(f"Retrieving {len(message_ids)} messages from SQLite")
        messages = await self.sqlite.get_messages_by_ids(message_ids)
        
        # Create ID to message mapping
        id_to_message = {msg['id']: msg for msg in messages}
        
        # Calculate final scores with time decay
        now = datetime.now()
        scored_results = []
        
        for msg_id, similarity_score in message_scores.items():
            if msg_id not in id_to_message:
                continue  # Message might have been deleted
            
            msg = id_to_message[msg_id]
            payload = message_payloads[msg_id]
            
            # Parse timestamp
            try:
                msg_time = datetime.fromisoformat(msg['timestamp'].replace(' ', 'T'))
            except:
                msg_time = datetime.strptime(msg['timestamp'], '%Y-%m-%d %H:%M:%S')
            
            # Calculate time decay
            age_hours = max(0, (now - msg_time).total_seconds() / 3600)
            decay_score = self._calculate_decay(age_hours, profile.decay_half_life_hours)
            
            # Get confidence score
            confidence_score = payload.get('confidence', 0.5)
            
            # Calculate final score
            total_weight = (profile.similarity_weight + 
                          profile.confidence_weight + 
                          profile.decay_weight)
            
            if total_weight > 0:
                final_score = (
                    (similarity_score * profile.similarity_weight +
                     confidence_score * profile.confidence_weight +
                     decay_score * profile.decay_weight) / total_weight
                )
            else:
                final_score = similarity_score
            
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
        final_results = [msg for _, msg in scored_results[:limit]]
        self.logger.debug(f"Semantic search returning {len(final_results)} results after ranking")
        return final_results
    
    async def _get_channels_for_projects(self, project_ids: List[str]) -> List[str]:
        """
        Get all channel IDs for the specified project IDs.
        
        Args:
            project_ids: List of project IDs (can include "global")
            
        Returns:
            List of channel IDs belonging to those projects
        """
        # Use the new efficient method
        self.logger.debug(f"Getting channels for {len(project_ids)} projects")
        channels = await self.sqlite.get_channels_by_projects(project_ids)
        self.logger.debug(f"Found {len(channels)} channels for specified projects")
        return [ch['id'] for ch in channels]
    
    async def _filter_search(self,
                            channel_ids: Optional[List[str]] = None,
                            sender_ids: Optional[List[str]] = None,
                            metadata_filters: Optional[Dict[str, Any]] = None,
                            min_confidence: Optional[float] = None,
                            limit: int = 20) -> List[Dict]:
        """
        Perform filter-based search using SQLite with MongoDB-style filtering.
        
        This is used when no query is provided or Qdrant is unavailable.
        """
        # Use the advanced search method with MongoDB-style filters
        self.logger.debug(f"Performing advanced filter search with metadata_filters: {metadata_filters}")
        return await self.sqlite.search_messages_advanced(
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            metadata_filters=metadata_filters,
            min_confidence=min_confidence,
            limit=limit
        )
    
    async def _filter_search_agent(self,
                                  agent_name: str,
                                  agent_project_id: Optional[str] = None,
                                  channel_ids: Optional[List[str]] = None,
                                  sender_ids: Optional[List[str]] = None,
                                  metadata_filters: Optional[Dict[str, Any]] = None,
                                  min_confidence: Optional[float] = None,
                                  limit: int = 20) -> List[Dict]:
        """
        Perform filter-based search with agent permissions using SQLite with MongoDB-style filtering.
        
        This is used when no semantic query is provided or Qdrant is unavailable,
        but we still need to respect agent permissions.
        """
        # Use the advanced search method with agent context for permissions
        self.logger.debug(f"Performing advanced filter search for agent {agent_name}")
        return await self.sqlite.search_messages_advanced(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            channel_ids=channel_ids,
            sender_ids=sender_ids,
            metadata_filters=metadata_filters,
            min_confidence=min_confidence,
            limit=limit
        )
    
    def _calculate_decay(self, age_hours: float, half_life_hours: float) -> float:
        """Calculate exponential decay score based on age"""
        if age_hours < 0:
            return 1.0  # Future messages get max score
        if half_life_hours <= 0:
            return 0.0  # Invalid half-life
        
        # Prevent overflow for very large ratios
        ratio = age_hours / half_life_hours
        if ratio > 100:  # Message is >100 half-lives old
            return 0.0
        
        return math.exp(-math.log(2) * ratio)
    
    # ============================================================================
    # Magic Method: Pass-through to SQLite Store
    # ============================================================================
    
    def __getattr__(self, name):
        """
        Proxy missing methods to the SQLite store.
        
        This eliminates the need for dozens of boilerplate delegation methods.
        Any method not explicitly defined in MessageStore will be forwarded to SQLiteStore.
        
        Methods that MessageStore overrides (like send_message, search_messages) 
        are handled directly and won't trigger this proxy.
        
        Examples of proxied methods:
            - Project management: register_project, get_project, list_projects
            - Agent management: register_agent, get_agent, get_discoverable_agents
            - Channel management: create_channel, get_channel, add_channel_member
            - Session management: register_session, get_session
            - Tool deduplication: record_tool_call, get_recent_tool_calls
        """
        # Check if SQLiteStore has the requested method
        if hasattr(self.sqlite, name):
            return getattr(self.sqlite, name)
        
        # If not found, raise AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")