#!/usr/bin/env python3
"""
NotesManager: Manages agent notes as private single-member channels

Agent notes are implemented as private channels where only the agent is a member.
This provides a unified approach using the standard channel/message infrastructure
while maintaining privacy and searchability.
"""

import sys
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

try:
    from db.manager import DatabaseManager
    from db.initialization import DatabaseInitializer, ensure_db_initialized
except ImportError as e:
    print(f"Import error in NotesManager: {e}", file=sys.stderr)
    DatabaseManager = None
    DatabaseInitializer = object  # Fallback to object if not available
    ensure_db_initialized = lambda f: f  # No-op decorator

class NotesManager(DatabaseInitializer):
    """Manages agent notes using private channels"""
    
    def __init__(self, db_path: str):
        """
        Initialize NotesManager
        
        Args:
            db_path: Path to the database
        """
        
        # Initialize parent class (DatabaseInitializer)
        super().__init__()
        
        if DatabaseManager:
            self.db = DatabaseManager(db_path)
            self.db_manager = self.db  # Fixed typo: was db_maanaber
        else:
            self.db = None
            self.db_manager = None
            
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the NotesManager (ensures DB is ready)"""
        await self.db.initialize()
    
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
        scope = agent_project_id if agent_project_id else 'global'
        return f"notes:{agent_name}:{scope}"
    
    @ensure_db_initialized
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
        existing = await self.db.get_channel(channel_id)
        if existing:
            return channel_id
        
        # Create the notes channel
        scope = 'project' if agent_project_id else 'global'
        
        # Create channel
        await self.db.create_channel(
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
        await self.db.add_channel_member(
            channel_id=channel_id,
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            invited_by='system',  # System creates notes channels
            source='system',
            can_leave=False,  # Cannot leave notes channel
            can_send=True,
            can_invite=False,  # No one else can be invited
            can_manage=True,  # Agent manages their own notes
            is_from_default=False
        )
        
        self.logger.info(f"Created notes channel for {agent_name}: {channel_id}")
        return channel_id
    
    @ensure_db_initialized
    async def write_note(self,
                        agent_name: str,
                        agent_project_id: Optional[str],
                        content: str,
                        tags: Optional[List[str]] = None,
                        session_id: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Write a note to an agent's notes channel.
        
        Args:
            agent_name: Agent writing the note
            agent_project_id: Agent's project ID
            content: Note content
            tags: Optional tags for categorization
            session_id: Optional session identifier
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
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {})
        }
        
        # Send message to notes channel
        message_id = await self.db.send_message(
            channel_id=channel_id,
            sender_id=agent_name,
            sender_project_id=agent_project_id,
            content=content,
            metadata=note_metadata
        )
        
        self.logger.debug(f"Note written for {agent_name}: {message_id}")
        return message_id
    
    @ensure_db_initialized
    async def search_notes(self,
                          agent_name: str,
                          agent_project_id: Optional[str],
                          query: Optional[str] = None,
                          tags: Optional[List[str]] = None,
                          session_id: Optional[str] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search an agent's notes.
        
        Args:
            agent_name: Agent whose notes to search
            agent_project_id: Agent's project ID
            query: Optional text to search for
            tags: Optional tags to filter by
            session_id: Optional session to filter by
            limit: Maximum number of results
            
        Returns:
            List of notes matching the criteria
        """
        channel_id = self.get_notes_channel_id(agent_name, agent_project_id)
        
        # Get all messages from the notes channel
        messages = await self.db.get_messages(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            channel_id=channel_id,
            limit=limit * 2  # Get more initially for filtering
        )
        
        results = []
        for msg in messages:
            # Parse metadata
            metadata = msg.get('metadata', {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {}
            
            # Skip non-note messages (shouldn't happen but be safe)
            if metadata.get('type') != 'note':
                continue
            
            # Apply filters
            if query and query.lower() not in msg['content'].lower():
                continue
            
            if session_id and metadata.get('session_id') != session_id:
                continue
            
            if tags:
                note_tags = metadata.get('tags', [])
                if not any(tag in note_tags for tag in tags):
                    continue
            
            # Format result
            results.append({
                'id': msg['id'],
                'content': msg['content'],
                'tags': metadata.get('tags', []),
                'session_id': metadata.get('session_id'),
                'timestamp': msg['timestamp'],
                'metadata': metadata
            })
            
            if len(results) >= limit:
                break
        
        return results
    
    @ensure_db_initialized
    async def get_recent_notes(self,
                              agent_name: str,
                              agent_project_id: Optional[str],
                              limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent notes for an agent.
        
        Args:
            agent_name: Agent whose notes to retrieve
            agent_project_id: Agent's project ID
            limit: Maximum number of notes
            
        Returns:
            List of recent notes
        """
        return await self.search_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            limit=limit
        )
    
    async def get_session_notes(self,
                               agent_name: str,
                               agent_project_id: Optional[str],
                               session_id: str,
                               limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get all notes from a specific session.
        
        Args:
            agent_name: Agent whose notes to retrieve
            agent_project_id: Agent's project ID
            session_id: Session identifier
            limit: Maximum number of notes
            
        Returns:
            List of notes from the session
        """
        return await self.search_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            session_id=session_id,
            limit=limit
        )
    
    @ensure_db_initialized
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
    
    @ensure_db_initialized
    async def delete_note(self,
                         agent_name: str,
                         agent_project_id: Optional[str],
                         note_id: int) -> bool:
        """
        Delete a specific note.
        
        Args:
            agent_name: Agent who owns the note
            agent_project_id: Agent's project ID
            note_id: ID of the note to delete
            
        Returns:
            True if deleted, False if not found or not authorized
        """
        # For now, we don't have a delete_message method in DatabaseManager
        # This would need to be added if we want to support deletion
        self.logger.warning(f"Note deletion not yet implemented: {note_id}")
        return False
    
    @ensure_db_initialized
    async def tag_note(self,
                      agent_name: str,
                      agent_project_id: Optional[str],
                      note_id: int,
                      tags: List[str]) -> bool:
        """
        Add tags to an existing note.
        
        Args:
            agent_name: Agent who owns the note
            agent_project_id: Agent's project ID
            note_id: ID of the note to tag
            tags: Tags to add
            
        Returns:
            True if tagged, False if not found
        """
        # This would require an update_message_metadata method in DatabaseManager
        self.logger.warning(f"Note tagging not yet implemented: {note_id}")
        return False