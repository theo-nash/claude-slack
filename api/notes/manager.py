#!/usr/bin/env python3
"""
NotesManager: Manages agent notes as private single-member channels

Agent notes are implemented as private channels where only the agent is a member.
This provides a unified approach using the standard channel/message infrastructure
while maintaining privacy and searchability.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime


class NotesManager:
    """Manages agent notes using private channels"""
    
    def __init__(self, message_store):
        """
        Initialize NotesManager with MessageStore.
        
        Args:
            message_store: MessageStore instance for all storage operations
        """
        self.store = message_store
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def get_notes_channel_id(agent_name: str, agent_project_id: Optional[str] = None) -> str:
        """
        Generate the channel ID for an agent's notes channel.
        
        Args:
            agent_name: Name of the agent
            agent_project_id: Optional project ID
            
        Returns:
            Channel ID in format: notes:{agent_name}:{project_id|global}
        """
        scope = agent_project_id[:8] if agent_project_id else 'global'
        return f"notes:{agent_name}:{scope}"
    
    async def ensure_notes_channel(self, 
                                  agent_name: str, 
                                  agent_project_id: Optional[str] = None) -> str:
        """
        Ensure a notes channel exists for an agent.
        Creates it if it doesn't exist.
        
        Args:
            agent_name: Name of the agent
            agent_project_id: Optional project ID
            
        Returns:
            Channel ID of the notes channel
        """
        channel_id = self.get_notes_channel_id(agent_name, agent_project_id)
        
        # Check if channel exists
        existing = await self.store.get_channel(channel_id)
        if existing:
            return channel_id
        
        # Create the notes channel
        scope = 'project' if agent_project_id else 'global'
        
        # Create channel
        await self.store.create_channel(
            channel_id=channel_id,
            channel_type='channel',
            access_type='private',  # Private ensures only members can access
            scope=scope,
            name=f"notes-{agent_name}",
            project_id=agent_project_id,
            description=f"Private notes for {agent_name}",
            created_by=agent_name,
            created_by_project_id=agent_project_id
        )
        
        # Add agent as the sole member using unified model
        # For private channels, they cannot leave (can_leave=False)
        await self.store.add_channel_member(
            channel_id=channel_id,
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            invited_by='system',  # System creates notes channels
            source='system',
            can_leave=False,  # Cannot leave notes channel
            can_send=True,
            can_invite=False,  # No one else can be invited
            can_manage=True,  # Agent manages their own notes
        )
        
        self.logger.info(f"Created notes channel for {agent_name}: {channel_id}")
        return channel_id
    
    async def write_note(self,
                        agent_name: str,
                        agent_project_id: Optional[str],
                        content: str,
                        tags: Optional[List[str]] = None,
                        session_context: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Write a note to an agent's notes channel.
        
        Args:
            agent_name: Agent writing the note
            agent_project_id: Agent's project ID
            content: Note content
            tags: Optional tags for categorization
            session_context: Optional session context or description
            metadata: Optional additional metadata
            
        Returns:
            Message ID of the created note
        """
        # Ensure notes channel exists
        channel_id = await self.ensure_notes_channel(agent_name, agent_project_id)
        
        # Prepare note metadata
        note_metadata = {
            "type": "note",
            "tags": tags or [],
            "session_context": session_context,
            **(metadata or {})
        }
        
        # Send message to notes channel
        message_id = await self.store.send_message(
            channel_id=channel_id,
            sender_id=agent_name,
            sender_project_id=agent_project_id,
            content=content,
            metadata=note_metadata
        )
        
        self.logger.debug(f"Note written for {agent_name}: {message_id}")
        return message_id
    
    async def search_notes(self,
                          agent_name: str,
                          agent_project_id: Optional[str],
                          query: Optional[str] = None,
                          tags: Optional[List[str]] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search an agent's notes using semantic search if available.
        
        Args:
            agent_name: Agent whose notes to search
            agent_project_id: Agent's project ID
            query: Optional text to search for (uses semantic search if available)
            tags: Optional tags to filter by
            limit: Maximum number of results
            
        Returns:
            List of notes matching the criteria
            
        Note:
            To filter by session, pass session_context in the note's metadata when writing,
            then search with query="session context text" or use the underlying
            store.search_agent_messages directly with metadata_filters={'session_context': 'value'}
        """
        channel_id = self.get_notes_channel_id(agent_name, agent_project_id)
        
        # Build metadata filters using MongoDB-style syntax
        metadata_filters = {"type": "note"}
        
        # Add tag filtering using the new filtering system's $contains operator
        if tags:
            # If multiple tags provided, match notes that have ANY of the tags
            if len(tags) == 1:
                # Single tag: use $contains directly
                metadata_filters["tags"] = {"$contains": tags[0]}
            else:
                # Multiple tags: use $or to match any of them
                metadata_filters["$or"] = [
                    {"tags": {"$contains": tag}} for tag in tags
                ]
        
        # Use search_agent_messages for permission-safe searching
        # This will use semantic search if query is provided and Qdrant is available
        messages = await self.store.search_agent_messages(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            query=query,
            channel_ids=[channel_id],  # Only search in notes channel
            metadata_filters=metadata_filters,
            limit=limit
        )
        
        # Format results consistently
        results = []
        for msg in messages:
            metadata = msg.get('metadata', {})
            
            results.append({
                'id': msg['id'],
                'content': msg['content'],
                'tags': metadata.get('tags', []),
                'session_context': metadata.get('session_context'),
                'timestamp': msg['timestamp'],
                'metadata': metadata,
                # Include search score if available (from semantic search)
                'search_score': msg.get('search_scores', {}).get('final_score') if msg.get('search_scores') else None
            })
        
        return results
    
    async def get_recent_notes(self,
                              agent_name: str,
                              agent_project_id: Optional[str],
                              limit: int = 20,
                              session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent notes for an agent.
        
        Args:
            agent_name: Agent whose notes to retrieve
            agent_project_id: Agent's project ID
            limit: Maximum number of notes
            session_id: Optional session ID to filter by
            
        Returns:
            List of recent notes
        """
        return await self.search_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            limit=limit
        )
    
    
    async def peek_agent_notes(self,
                              target_agent_name: str,
                              target_project_id: Optional[str],
                              requester_name: str,
                              requester_project_id: Optional[str],
                              query: Optional[str] = None,
                              limit: int = 20) -> List[Dict[str, Any]]:
        """
        Peek at another agent's notes (for debugging or META agents).
        
        Note: This bypasses privacy. Should only be used for:
        - System administrators
        - META agents with oversight roles
        - Debugging with permission
        
        Args:
            target_agent_name: Agent whose notes to peek at
            target_project_id: Target agent's project ID
            requester_name: Agent making the request (for audit)
            requester_project_id: Requester's project ID
            query: Optional search query
            limit: Maximum number of notes
            
        Returns:
            List of notes from target agent
        """
        self.logger.warning(
            f"Agent {requester_name} peeking at {target_agent_name}'s notes"
        )
        
        # In production, you might want to check permissions here
        # For now, we'll allow it but log the access
        
        return await self.search_notes(
            agent_name=target_agent_name,
            agent_project_id=target_project_id,
            query=query,
            limit=limit
        )