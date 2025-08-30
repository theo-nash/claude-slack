#!/usr/bin/env python3
"""
FastAPI Server for Claude-Slack
Provides REST API and SSE streaming for the unified claude-slack system.

This server:
1. Wraps the existing Python API (no rewrite needed)
2. Provides REST endpoints for Next.js
3. Streams events via SSE
4. Acts as single writer to SQLite (no concurrency issues)
5. Bridges MCP tools via HTTP
"""

import os
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.unified_api import ClaudeSlackAPI
from api.models import DMPolicy, Discoverability


# ==============================================================================
# Pydantic Models for Request/Response
# ==============================================================================

class MessageCreate(BaseModel):
    """Request model for creating a message"""
    channel_id: str
    content: str
    sender_id: str
    sender_project_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None

class MessageUpdate(BaseModel):
    """Request model for updating a message"""
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_edited: bool = True

class ChannelCreate(BaseModel):
    """Request model for creating a channel"""
    name: str
    description: Optional[str] = None
    scope: str = "global"  # "global" or "project"
    project_id: Optional[str] = None
    created_by: str
    created_by_project_id: Optional[str] = None
    is_default: bool = False

class AgentRegister(BaseModel):
    """Request model for registering an agent"""
    name: str
    project_id: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    dm_policy: str = "open"  # open, restricted, closed
    discoverable: str = "public"  # public, project, private

class ChannelJoin(BaseModel):
    """Request model for joining a channel"""
    agent_name: str
    agent_project_id: Optional[str] = None

class NoteCreate(BaseModel):
    """Request model for creating a note"""
    content: str
    agent_name: str
    agent_project_id: Optional[str] = None
    session_context: Optional[str] = None
    tags: Optional[List[str]] = None

class SearchRequest(BaseModel):
    """Request model for search operations"""
    query: Optional[str] = None
    channel_ids: Optional[List[str]] = None
    project_ids: Optional[List[str]] = None
    limit: int = 50
    ranking_profile: str = "balanced"  # recent, quality, balanced, similarity
    metadata_filters: Optional[Dict[str, Any]] = None

class MCPToolCall(BaseModel):
    """Request model for MCP tool invocations via HTTP"""
    tool_name: str
    params: Dict[str, Any]
    agent_name: str
    agent_project_id: Optional[str] = None


# ==============================================================================
# Application Lifecycle
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown.
    Ensures proper initialization and cleanup of resources.
    """
    # Startup
    print("🚀 Starting Claude-Slack API Server...")
    
    # Initialize API from environment or defaults
    app.state.api = ClaudeSlackAPI.from_env()
    await app.state.api.db.initialize()
    await app.state.api.events.start()
    
    print(f"✅ API Server ready on http://localhost:8000")
    print(f"📊 Database: {app.state.api.db.sqlite.db_path}")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Claude-Slack API Server...")
    await app.state.api.events.stop()
    await app.state.api.db.close()
    print("✅ Server shutdown complete")


# ==============================================================================
# FastAPI Application
# ==============================================================================

app = FastAPI(
    title="Claude-Slack API",
    description="Unified API for claude-slack messaging system with semantic search",
    version="5.0.0",
    lifespan=lifespan
)

# Configure CORS for Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js dev ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Event-Stream-Version"]
)


# ==============================================================================
# Health & Status Endpoints
# ==============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "5.0.0"
    }

@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    api: ClaudeSlackAPI = app.state.api
    
    # Get various stats
    event_stats = api.get_event_stats()
    
    # Get database stats via direct query
    db_stats = await api.db.sqlite.get_stats()
    
    return {
        "events": event_stats,
        "database": db_stats,
        "timestamp": datetime.now().isoformat()
    }


# ==============================================================================
# Message Endpoints
# ==============================================================================

@app.get("/api/messages")
async def get_messages(
    channel_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    since: Optional[str] = None,
    before: Optional[str] = None
):
    """Get messages with optional filtering"""
    api: ClaudeSlackAPI = app.state.api
    
    messages = await api.get_messages(
        channel_id=channel_id,
        limit=limit,
        offset=offset,
        since=since,
        before=before
    )
    
    return messages

@app.post("/api/messages", status_code=201)
async def create_message(message: MessageCreate):
    """Create a new message"""
    api: ClaudeSlackAPI = app.state.api
    
    msg_id = await api.send_message(
        channel_id=message.channel_id,
        sender_id=message.sender_id,
        sender_project_id=message.sender_project_id,
        content=message.content,
        metadata=message.metadata,
        thread_id=message.thread_id
    )
    
    # Fetch and return the created message
    messages = await api.get_messages(message_ids=[msg_id])
    return messages[0] if messages else {"id": msg_id}

@app.put("/api/messages/{message_id}")
async def update_message(message_id: int, update: MessageUpdate):
    """Update an existing message"""
    api: ClaudeSlackAPI = app.state.api
    
    success = await api.update_message(
        message_id=message_id,
        content=update.content,
        metadata=update.metadata,
        is_edited=update.is_edited
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    
    return {"success": True, "message_id": message_id}

@app.delete("/api/messages/{message_id}")
async def delete_message(message_id: int):
    """Delete a message"""
    api: ClaudeSlackAPI = app.state.api
    
    success = await api.delete_message(message_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    
    return {"success": True, "message_id": message_id}


# ==============================================================================
# Search Endpoints
# ==============================================================================

@app.post("/api/search")
async def search_messages(request: SearchRequest):
    """
    Search messages with semantic search and filtering.
    Uses Qdrant for vector search when available.
    """
    api: ClaudeSlackAPI = app.state.api
    
    results = await api.search_messages(
        query=request.query,
        channel_ids=request.channel_ids,
        project_ids=request.project_ids,
        limit=request.limit,
        ranking_profile=request.ranking_profile,
        metadata_filters=request.metadata_filters
    )
    
    return results


# ==============================================================================
# Channel Endpoints
# ==============================================================================

@app.get("/api/channels")
async def list_channels(
    agent_name: Optional[str] = None,
    project_id: Optional[str] = None,
    include_archived: bool = False,
    is_default: Optional[bool] = None
):
    """List channels with filtering"""
    api: ClaudeSlackAPI = app.state.api
    
    channels = await api.list_channels(
        agent_name=agent_name,
        project_id=project_id,
        include_archived=include_archived,
        is_default=is_default
    )
    
    return channels

@app.post("/api/channels", status_code=201)
async def create_channel(channel: ChannelCreate):
    """Create a new channel"""
    api: ClaudeSlackAPI = app.state.api
    
    # Determine full channel ID based on scope
    if channel.scope == "project" and not channel.project_id:
        raise HTTPException(
            status_code=400, 
            detail="Project ID required for project-scoped channels"
        )
    
    channel_id = await api.create_channel(
        name=channel.name,
        description=channel.description,
        scope=channel.scope,
        project_id=channel.project_id,
        created_by=channel.created_by,
        created_by_project_id=channel.created_by_project_id,
        is_default=channel.is_default
    )
    
    return {"channel_id": channel_id, "name": channel.name}

@app.post("/api/channels/{channel_id}/join")
async def join_channel(channel_id: str, request: ChannelJoin):
    """Join a channel"""
    api: ClaudeSlackAPI = app.state.api
    
    success = await api.join_channel(
        agent_name=request.agent_name,
        agent_project_id=request.agent_project_id,
        channel_id=channel_id
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to join channel")
    
    return {"success": True, "channel_id": channel_id}

@app.post("/api/channels/{channel_id}/leave")
async def leave_channel(channel_id: str, request: ChannelJoin):
    """Leave a channel"""
    api: ClaudeSlackAPI = app.state.api
    
    success = await api.leave_channel(
        agent_name=request.agent_name,
        agent_project_id=request.agent_project_id,
        channel_id=channel_id
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to leave channel")
    
    return {"success": True, "channel_id": channel_id}

@app.get("/api/channels/{channel_id}/members")
async def get_channel_members(channel_id: str):
    """Get members of a channel"""
    api: ClaudeSlackAPI = app.state.api
    
    members = await api.get_channel_members(channel_id)
    return members


# ==============================================================================
# Agent Endpoints
# ==============================================================================

@app.get("/api/agents")
async def list_agents(
    project_id: Optional[str] = None,
    include_descriptions: bool = True
):
    """List all agents"""
    api: ClaudeSlackAPI = app.state.api
    
    agents = await api.list_agents(
        project_id=project_id,
        include_descriptions=include_descriptions
    )
    
    return agents

@app.post("/api/agents", status_code=201)
async def register_agent(agent: AgentRegister):
    """Register a new agent"""
    api: ClaudeSlackAPI = app.state.api
    
    success = await api.register_agent(
        name=agent.name,
        project_id=agent.project_id,
        description=agent.description,
        status=agent.status,
        dm_policy=agent.dm_policy,
        discoverable=agent.discoverable
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to register agent")
    
    return {"success": True, "agent": agent.name}

@app.get("/api/agents/{agent_name}")
async def get_agent(agent_name: str, project_id: Optional[str] = None):
    """Get agent details"""
    api: ClaudeSlackAPI = app.state.api
    
    agent = await api.get_agent(agent_name, project_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return agent


# ==============================================================================
# Notes Endpoints
# ==============================================================================

@app.post("/api/notes", status_code=201)
async def create_note(note: NoteCreate):
    """Create a note"""
    api: ClaudeSlackAPI = app.state.api
    
    note_id = await api.notes.write_note(
        agent_name=note.agent_name,
        agent_project_id=note.agent_project_id,
        content=note.content,
        session_context=note.session_context,
        tags=note.tags
    )
    
    return {"note_id": note_id}

@app.get("/api/notes")
async def get_notes(
    agent_name: str,
    agent_project_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    query: Optional[str] = None,
    tags: Optional[List[str]] = Query(None)
):
    """Get notes for an agent"""
    api: ClaudeSlackAPI = app.state.api
    
    if query or tags:
        notes = await api.notes.search_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            query=query,
            tags=tags,
            limit=limit
        )
    else:
        notes = await api.notes.get_recent_notes(
            agent_name=agent_name,
            agent_project_id=agent_project_id,
            limit=limit
        )
    
    return notes


# ==============================================================================
# Event Streaming (SSE)
# ==============================================================================

@app.get("/api/events")
async def stream_events(
    client_id: Optional[str] = Query(None),
    topics: Optional[str] = Query(None),  # Comma-separated list
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID")
):
    """
    Server-Sent Events endpoint for real-time updates.
    
    Topics can be: messages, channels, members, agents, notes, system, or * for all
    """
    api: ClaudeSlackAPI = app.state.api
    
    # Generate client ID if not provided
    if not client_id:
        client_id = f"web_{datetime.now().timestamp()}"
    
    # Parse topics
    topic_list = None
    if topics:
        topic_list = [t.strip() for t in topics.split(",")]
    
    async def event_generator():
        """Generate SSE formatted events"""
        try:
            async for sse_data in api.subscribe_sse(
                client_id=client_id,
                topics=topic_list,
                last_event_id=last_event_id
            ):
                yield sse_data
        except asyncio.CancelledError:
            # Client disconnected
            await api.unsubscribe_events(client_id)
        except Exception as e:
            # Send error event
            yield f"event: error\ndata: {{'error': '{str(e)}'}}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "X-Event-Stream-Version": "2.0"
        }
    )


# ==============================================================================
# MCP Bridge Endpoints
# ==============================================================================

@app.post("/api/mcp/tool")
async def execute_mcp_tool(request: MCPToolCall):
    """
    Bridge endpoint for MCP tools to call via HTTP.
    This allows MCP server to delegate to the FastAPI server,
    ensuring single writer to SQLite.
    """
    api: ClaudeSlackAPI = app.state.api
    
    # Map tool names to API methods
    tool_map = {
        "send_message": api.send_message,
        "send_channel_message": api.send_message,
        "get_messages": api.get_messages,
        "search_messages": api.search_messages,
        "list_channels": api.list_channels,
        "create_channel": api.create_channel,
        "join_channel": api.join_channel,
        "leave_channel": api.leave_channel,
        "list_agents": api.list_agents,
        "register_agent": api.register_agent,
        "write_note": api.notes.write_note,
        "search_notes": api.notes.search_notes,
        "get_recent_notes": api.notes.get_recent_notes,
        "create_dm": api.create_or_get_dm_channel,
        "send_direct_message": api.send_direct_message,
    }
    
    if request.tool_name not in tool_map:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown tool: {request.tool_name}"
        )
    
    try:
        # Execute the tool with provided parameters
        result = await tool_map[request.tool_name](**request.params)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================================================================
# Project & Session Management
# ==============================================================================

@app.get("/api/projects")
async def list_projects():
    """List all projects"""
    api: ClaudeSlackAPI = app.state.api
    projects = await api.list_projects()
    return projects

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Get project details"""
    api: ClaudeSlackAPI = app.state.api
    project = await api.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return project

@app.get("/api/projects/{project_id}/links")
async def get_project_links(project_id: str):
    """Get linked projects"""
    api: ClaudeSlackAPI = app.state.api
    links = await api.get_linked_projects(project_id)
    return links

@app.post("/api/sessions")
async def register_session(
    agent_name: str,
    agent_project_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Register a new session"""
    api: ClaudeSlackAPI = app.state.api
    
    session_id = await api.register_session(
        agent_name=agent_name,
        agent_project_id=agent_project_id,
        metadata=metadata
    )
    
    return {"session_id": session_id}


# ==============================================================================
# Development Helpers
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Development server with auto-reload
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )