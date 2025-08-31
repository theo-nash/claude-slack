#!/usr/bin/env python3
"""
MCP HTTP Bridge Client
This module allows MCP tools to communicate with the FastAPI server via HTTP,
ensuring single-writer access to SQLite.

Usage:
    # In your MCP server.py, replace direct API calls with:
    from mcp_http_bridge import MCPBridge
    
    bridge = MCPBridge()
    result = await bridge.send_message(channel_id="general", content="Hello")
"""

import os
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin


class MCPBridge:
    """
    HTTP client for MCP tools to communicate with FastAPI server.
    This ensures all database writes go through a single process.
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the MCP bridge client.
        
        Args:
            base_url: Base URL of the FastAPI server (default: http://localhost:8000)
        """
        self.base_url = base_url or os.getenv("CLAUDE_SLACK_API_URL", "http://localhost:8000")
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make HTTP request to the API server"""
        await self._ensure_session()
        
        url = urljoin(self.base_url, endpoint)
        
        async with self.session.request(method, url, **kwargs) as response:
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"API error {response.status}: {text}")
            
            return await response.json()
    
    async def close(self):
        """Close the HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    # ==============================================================================
    # Message Operations
    # ==============================================================================
    
    async def send_message(
        self,
        channel_id: str,
        content: str,
        sender_id: str,
        sender_project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None
    ) -> int:
        """Send a message via HTTP"""
        result = await self._request(
            "POST",
            "/api/messages",
            json={
                "channel_id": channel_id,
                "content": content,
                "sender_id": sender_id,
                "sender_project_id": sender_project_id,
                "metadata": metadata,
                "thread_id": thread_id
            }
        )
        return result.get("id")
    
    async def get_messages(
        self,
        channel_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        since: Optional[str] = None,
        before: Optional[str] = None
    ) -> List[Dict]:
        """Get messages via HTTP"""
        params = {
            "limit": limit,
            "offset": offset
        }
        if channel_id:
            params["channel_id"] = channel_id
        if since:
            params["since"] = since
        if before:
            params["before"] = before
        
        return await self._request("GET", "/api/messages", params=params)
    
    async def search_messages(
        self,
        query: Optional[str] = None,
        channel_ids: Optional[List[str]] = None,
        project_ids: Optional[List[str]] = None,
        limit: int = 50,
        ranking_profile: str = "balanced",
        metadata_filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """Search messages via HTTP"""
        return await self._request(
            "POST",
            "/api/search",
            json={
                "query": query,
                "channel_ids": channel_ids,
                "project_ids": project_ids,
                "limit": limit,
                "ranking_profile": ranking_profile,
                "metadata_filters": metadata_filters
            }
        )
    
    # ==============================================================================
    # Channel Operations
    # ==============================================================================
    
    async def list_channels(
        self,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None,
        include_archived: bool = False,
        is_default: Optional[bool] = None
    ) -> List[Dict]:
        """List channels via HTTP"""
        params = {"include_archived": include_archived}
        if agent_name:
            params["agent_name"] = agent_name
        if project_id:
            params["project_id"] = project_id
        if is_default is not None:
            params["is_default"] = is_default
        
        return await self._request("GET", "/api/channels", params=params)
    
    async def create_channel(
        self,
        name: str,
        description: Optional[str] = None,
        scope: str = "global",
        project_id: Optional[str] = None,
        created_by: str = "system",
        created_by_project_id: Optional[str] = None,
        is_default: bool = False
    ) -> str:
        """Create a channel via HTTP"""
        result = await self._request(
            "POST",
            "/api/channels",
            json={
                "name": name,
                "description": description,
                "scope": scope,
                "project_id": project_id,
                "created_by": created_by,
                "created_by_project_id": created_by_project_id,
                "is_default": is_default
            }
        )
        return result.get("channel_id")
    
    async def join_channel(
        self,
        channel_id: str,
        agent_name: str,
        agent_project_id: Optional[str] = None
    ) -> bool:
        """Join a channel via HTTP"""
        result = await self._request(
            "POST",
            f"/api/channels/{channel_id}/join",
            json={
                "agent_name": agent_name,
                "agent_project_id": agent_project_id
            }
        )
        return result.get("success", False)
    
    async def leave_channel(
        self,
        channel_id: str,
        agent_name: str,
        agent_project_id: Optional[str] = None
    ) -> bool:
        """Leave a channel via HTTP"""
        result = await self._request(
            "POST",
            f"/api/channels/{channel_id}/leave",
            json={
                "agent_name": agent_name,
                "agent_project_id": agent_project_id
            }
        )
        return result.get("success", False)
    
    # ==============================================================================
    # Agent Operations
    # ==============================================================================
    
    async def list_agents(
        self,
        project_id: Optional[str] = None,
        include_descriptions: bool = True
    ) -> List[Dict]:
        """List agents via HTTP"""
        params = {"include_descriptions": include_descriptions}
        if project_id:
            params["project_id"] = project_id
        
        return await self._request("GET", "/api/agents", params=params)
    
    async def register_agent(
        self,
        name: str,
        project_id: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "active",
        dm_policy: str = "open",
        discoverable: str = "public"
    ) -> bool:
        """Register an agent via HTTP"""
        result = await self._request(
            "POST",
            "/api/agents",
            json={
                "name": name,
                "project_id": project_id,
                "description": description,
                "status": status,
                "dm_policy": dm_policy,
                "discoverable": discoverable
            }
        )
        return result.get("success", False)
    
    # ==============================================================================
    # Note Operations
    # ==============================================================================
    
    async def write_note(
        self,
        content: str,
        agent_name: str,
        agent_project_id: Optional[str] = None,
        session_context: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> int:
        """Write a note via HTTP"""
        result = await self._request(
            "POST",
            "/api/notes",
            json={
                "content": content,
                "agent_name": agent_name,
                "agent_project_id": agent_project_id,
                "session_context": session_context,
                "tags": tags
            }
        )
        return result.get("note_id")
    
    async def search_notes(
        self,
        agent_name: str,
        agent_project_id: Optional[str] = None,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search notes via HTTP"""
        params = {
            "agent_name": agent_name,
            "limit": limit
        }
        if agent_project_id:
            params["agent_project_id"] = agent_project_id
        if query:
            params["query"] = query
        if tags:
            params["tags"] = tags
        
        return await self._request("GET", "/api/notes", params=params)
    
    async def get_recent_notes(
        self,
        agent_name: str,
        agent_project_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Get recent notes via HTTP"""
        params = {
            "agent_name": agent_name,
            "limit": limit
        }
        if agent_project_id:
            params["agent_project_id"] = agent_project_id
        
        return await self._request("GET", "/api/notes", params=params)
    
    # ==============================================================================
    # Direct MCP Tool Execution
    # ==============================================================================
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        agent_name: str = "mcp-agent",
        agent_project_id: Optional[str] = None
    ) -> Any:
        """
        Execute any MCP tool via HTTP.
        This is a generic method for any tool not explicitly wrapped above.
        """
        result = await self._request(
            "POST",
            "/api/mcp/tool",
            json={
                "tool_name": tool_name,
                "params": params,
                "agent_name": agent_name,
                "agent_project_id": agent_project_id
            }
        )
        
        if result.get("success"):
            return result.get("result")
        else:
            raise Exception(result.get("error", "Unknown error"))


# ==============================================================================
# Singleton Instance
# ==============================================================================

# Create a default bridge instance
default_bridge = MCPBridge()


# ==============================================================================
# Convenience Functions
# ==============================================================================

async def send_message(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.send_message(**kwargs)

async def get_messages(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.get_messages(**kwargs)

async def search_messages(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.search_messages(**kwargs)

async def list_channels(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.list_channels(**kwargs)

async def create_channel(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.create_channel(**kwargs)

async def join_channel(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.join_channel(**kwargs)

async def list_agents(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.list_agents(**kwargs)

async def write_note(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.write_note(**kwargs)

async def search_notes(**kwargs):
    """Convenience function using default bridge"""
    return await default_bridge.search_notes(**kwargs)