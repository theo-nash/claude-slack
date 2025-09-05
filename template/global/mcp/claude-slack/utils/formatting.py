#!/usr/bin/env python3
"""
Unified message formatting for claude-slack MCP server.
Provides consistent, human-readable output formats for all message types.

Format pattern for all messages:
[context] sender (time) tags: tag1, tag2:
content
"""

from datetime import datetime
from typing import Dict, List, Any, Optional


def format_time_ago(timestamp_value) -> str:
    """Convert timestamp to human-readable time ago format
    
    Args:
        timestamp_value: Unix timestamp (float/int) or ISO string for backward compatibility
    """
    try:
        import time
        
        # Handle Unix timestamps (our new format)
        if isinstance(timestamp_value, (int, float)):
            # Unix timestamps are in UTC
            current_time = time.time()
            diff_seconds = current_time - timestamp_value
        # Handle ISO strings (backward compatibility)
        elif isinstance(timestamp_value, str):
            timestamp = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
            now = datetime.now()
            diff_seconds = (now - timestamp).total_seconds()
        else:
            return str(timestamp_value)
        
        # Format the difference
        if diff_seconds < 60:
            return "just now"
        elif diff_seconds < 3600:
            minutes = int(diff_seconds / 60)
            return f"{minutes}m ago"
        elif diff_seconds < 86400:
            hours = int(diff_seconds / 3600)
            return f"{hours}h ago"
        elif diff_seconds < 604800:  # 7 days
            days = int(diff_seconds / 86400)
            return f"{days}d ago"
        else:
            weeks = int(diff_seconds / 604800)
            return f"{weeks}w ago"
    except Exception as e:
        return str(timestamp_value)


# ============================================================================
# Core Message Formatter - Single Source of Truth
# ============================================================================

def format_single_message(msg: Dict, context_override: str = None, agent_name: str = None) -> str:
    """
    Format a single message with consistent header pattern.
    This is THE source of truth for message formatting.
    
    Args:
        msg: Message dict with standard fields
        context_override: Override for context label
        agent_name: Current agent name (for DM direction)
    
    Returns:
        Formatted message string
    """
    # Determine context label
    context = _get_context_label(msg, context_override, agent_name)
    
    # Build header components
    sender = _get_sender_label(msg, agent_name)
    time_str = format_time_ago(msg.get('timestamp'))
    tags = _format_tags(msg)
    
    # Construct header line
    header_parts = [f"[{context}]"]
    if sender:
        header_parts.append(sender)
    header_parts.append(f"({time_str})")
    
    # Add message ID if present
    msg_id = msg.get('id')
    if msg_id:
        header_parts.append(f"[id:{msg_id}]")
    
    if tags:
        header_parts.append(f"[tags: {tags}]")
    
    header = " ".join(header_parts) + ":"
    
    # Add content
    content = msg.get('content', '')
    
    return f"{header}\n{content}"


# ============================================================================
# Helper Functions
# ============================================================================

def _get_context_label(msg: Dict, override: str = None, agent_name: str = None) -> str:
    """Determine the context label for a message."""
    if override:
        return override
    
    channel_id = msg.get('channel_id', '')
    
    if channel_id.startswith('notes:'):
        return "your note"
    
    elif channel_id.startswith('dm:'):
        # Determine direction based on sender
        sender_id = msg.get('sender_id')
        is_sent = msg.get('is_sent', sender_id == agent_name)
        
        if is_sent:
            # Extract recipient from channel_id or use recipient_id field
            recipient = msg.get('recipient_id')
            if not recipient and ':' in channel_id:
                parts = channel_id.split(':')
                # Find the other party (not the sender)
                for part in parts[1:]:
                    if part != sender_id and not part.startswith('proj_'):
                        recipient = part
                        break
            return f"DM to {recipient or 'unknown'}"
        else:
            return f"DM from {sender_id or 'unknown'}"
    
    elif channel_id.startswith('global:'):
        channel_name = channel_id.split(':', 1)[1]
        return f"{channel_name} channel, global"
    
    elif channel_id.startswith('proj_'):
        parts = channel_id.split(':', 1)
        channel_name = parts[1] if len(parts) > 1 else 'unknown'
        project_name = msg.get('project_name', 'unknown')
        return f"{channel_name} channel, {project_name}"
    
    else:
        # Fallback for unknown format
        return "message"


def _get_sender_label(msg: Dict, agent_name: str = None) -> Optional[str]:
    """Get sender label if applicable."""
    # Don't show sender for notes (they're always from the agent)
    if msg.get('channel_id', '').startswith('notes:'):
        return None
    
    # For DMs where agent is sender, show "You"
    sender_id = msg.get('sender_id')
    if sender_id == agent_name and msg.get('channel_id', '').startswith('dm:'):
        return "You"
    
    return sender_id


def _format_tags(msg: Dict) -> Optional[str]:
    """Extract and format tags from message or metadata."""
    # Try direct tags first, then metadata
    tags = msg.get('tags')
    if not tags and msg.get('metadata'):
        metadata = msg.get('metadata', {})
        if isinstance(metadata, dict):
            tags = metadata.get('tags')
    
    if tags and isinstance(tags, list) and len(tags) > 0:
        return ", ".join(str(tag) for tag in tags)
    return None


# ============================================================================
# Collection Formatters
# ============================================================================

def format_messages_list(messages: List[Dict], 
                         title: str,
                         agent_name: str = None,
                         context_override: str = None) -> str:
    """
    Format a list of messages with a title header.
    Uses format_single_message for consistency.
    """
    if not messages:
        return f"=== {title} ==="
    
    lines = [f"=== {title} ===", ""]
    
    for msg in messages:
        formatted = format_single_message(msg, context_override, agent_name)
        lines.append(formatted)
        lines.append("")  # Blank line between messages
    
    return "\n".join(lines).rstrip()


def format_get_messages_response(messages: List[Dict], 
                                 agent_name: str,
                                 project_name: str = None) -> str:
    """Format response for get_messages tool."""
    if not messages:
        return "No recent messages"
    
    # Group messages by type
    channel_msgs = []
    notes = []
    dms = []
    
    for msg in messages:
        channel_id = msg.get('channel_id', '')
        
        # Enrich with project name if available
        if project_name and not msg.get('project_name'):
            msg['project_name'] = project_name
        
        if channel_id.startswith('notes:'):
            notes.append(msg)
        elif channel_id.startswith('dm:'):
            # Mark if sent by agent
            if not msg.get('is_sent'):
                msg['is_sent'] = msg.get('sender_id') == agent_name
            dms.append(msg)
        else:
            channel_msgs.append(msg)
    
    # Build output sections
    total = len(messages)
    sections = []
    
    if channel_msgs:
        formatted = format_messages_list(
            channel_msgs, 
            f"CHANNELS",
            agent_name
        )
        sections.append(formatted)
    
    if notes:
        formatted = format_messages_list(
            notes,
            f"YOUR NOTES",
            agent_name
        )
        sections.append(formatted)
    
    if dms:
        formatted = format_messages_list(
            dms,
            f"DIRECT MESSAGES",
            agent_name
        )
        sections.append(formatted)
    
    # Combine with main header
    header = f"=== Recent Messages ({total} total) ==="
    if sections:
        return "\n\n".join([header] + sections)
    else:
        return header


def format_search_results(messages: List[Dict], 
                          query: str,
                          agent_name: str) -> str:
    """Format search results."""
    if not messages:
        return f'No messages found matching "{query}"'
    
    title = f'Search Results for "{query}" ({len(messages)} matches)'
    return format_messages_list(messages, title, agent_name)


def format_notes_response(notes: List[Dict], 
                          title: str = "Recent Notes",
                          agent_name: str = None) -> str:
    """Format notes-specific responses."""
    if not notes:
        return "No notes found"
    
    # Ensure all are marked as notes
    for note in notes:
        if not note.get('channel_id', '').startswith('notes:'):
            note['channel_id'] = 'notes:' + note.get('sender_id', agent_name or 'unknown')
    
    return format_messages_list(notes, title, agent_name)


# ============================================================================
# Backward Compatibility Wrappers
# ============================================================================

def format_messages_concise(messages_data: Dict, agent_name: str) -> str:
    """
    Legacy format wrapper - converts old structure to new format.
    """
    # Extract all messages into flat list
    all_messages = []
    
    # Get project name if available
    project_name = None
    if messages_data.get("project_messages"):
        project_name = messages_data["project_messages"].get("project_name")
    
    # Process global messages
    global_msgs = messages_data.get("global_messages", {})
    for channel_name, msgs in global_msgs.get("channel_messages", {}).items():
        for msg in msgs:
            msg['channel_id'] = f"global:{channel_name}"
            all_messages.append(msg)
    
    for msg in global_msgs.get("direct_messages", []):
        if 'channel_id' not in msg:
            msg['channel_id'] = f"dm:{msg.get('sender_id', 'unknown')}:{agent_name}"
        all_messages.append(msg)
    
    for msg in global_msgs.get("notes", []):
        if 'channel_id' not in msg:
            msg['channel_id'] = f"notes:{agent_name}"
        msg['scope'] = 'global'
        all_messages.append(msg)
    
    # Process project messages
    project_msgs = messages_data.get("project_messages", {})
    if project_msgs:
        for channel_name, msgs in project_msgs.get("channel_messages", {}).items():
            for msg in msgs:
                msg['channel_id'] = f"proj_{project_name}:{channel_name}"
                msg['project_name'] = project_name
                all_messages.append(msg)
        
        for msg in project_msgs.get("direct_messages", []):
            if 'channel_id' not in msg:
                msg['channel_id'] = f"dm:{msg.get('sender_id', 'unknown')}:{agent_name}:proj_{project_name}"
            msg['project_name'] = project_name
            all_messages.append(msg)
        
        for msg in project_msgs.get("notes", []):
            if 'channel_id' not in msg:
                msg['channel_id'] = f"notes:{agent_name}:proj_{project_name}"
            msg['scope'] = 'project'
            msg['project_name'] = project_name
            all_messages.append(msg)
    
    # Use new formatter
    return format_get_messages_response(all_messages, agent_name, project_name)


def format_flat_messages(messages: List[Dict], agent_name: str, project_name: str = None) -> str:
    """
    Format a flat list of messages from get_agent_messages.
    Now just a wrapper around the new formatter.
    """
    return format_get_messages_response(messages, agent_name, project_name)


def format_search_results_concise(results: List[Dict], query: str, agent_name: str) -> str:
    """Legacy wrapper for search results."""
    return format_search_results(results, query, agent_name)


def format_notes_concise(notes: List[Dict], title: str = "Notes") -> str:
    """Legacy wrapper for notes formatting."""
    return format_notes_response(notes, title)


def format_note_search_results(results: List[Dict], query: str = None, tags: List[str] = None) -> str:
    """Format note search results."""
    if not results:
        search_desc = []
        if query:
            search_desc.append(f'query "{query}"')
        if tags:
            search_desc.append(f'tags {tags}')
        search_str = " and ".join(search_desc) if search_desc else "all notes"
        return f"No notes found matching {search_str}"
    
    title = f"Found {len(results)} note(s)"
    if query:
        title += f' matching "{query}"'
    return format_notes_response(results, title)


def format_peek_notes(notes: List[Dict], agent_name: str, query: str = None) -> str:
    """Format peeking at another agent's notes."""
    if not notes:
        search_str = f' matching "{query}"' if query else ""
        return f"No notes found for {agent_name}{search_str}"
    
    title = f"Peeking at {agent_name}'s notes ({len(notes)} found)"
    return format_notes_response(notes, title)


# ============================================================================
# Other Formatters (Agents, Channels, etc.)
# ============================================================================

def format_agents_concise(agents: List) -> str:
    """Format agent list in concise, readable format"""
    if not agents:
        return "No agents found"
    
    output = [f"=== Available Agents ({len(agents)} total) ==="]
    
    # Helper to get attributes from either dict or object
    def get_attr(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    # Group by scope
    global_agents = [a for a in agents if get_attr(a, "project_id") is None]
    project_groups = {}
    for agent in agents:
        if get_attr(agent, "project_id") is not None:
            project = get_attr(agent, "project_name") or get_attr(agent, "project_id", "Unknown")[:8]
            if project not in project_groups:
                project_groups[project] = []
            project_groups[project].append(agent)
    
    # Format global agents
    if global_agents:
        output.append("\nGLOBAL:")
        for agent in global_agents:
            name = get_attr(agent, "name", "unknown")
            desc = get_attr(agent, "description", "No description")
            output.append(f'  {name}: {desc}')
    
    # Format project agents
    for project_name, project_agents in sorted(project_groups.items()):
        output.append(f"\nPROJECT ({project_name}):")
        for agent in project_agents:
            name = get_attr(agent, "name", "unknown")
            desc = get_attr(agent, "description", "No description")
            output.append(f'  {name}: {desc}')
    
    return "\n".join(output)


def format_channel_list(channels: List[Dict], agent_name: str = None) -> str:
    """
    Format channel list in concise, readable format
    """
    if not channels:
        return "No channels found"
    
    output = [f"=== Channels ({len(channels)} total) ==="]
    
    # Group by scope
    global_channels = []
    project_groups = {}
    
    for channel in channels:
        scope = channel.get('scope', 'global')
        if scope == 'global':
            global_channels.append(channel)
        else:
            project_name = channel.get('project_name')
            if not project_name:
                project_id = channel.get('project_id', 'unknown')
                project_name = project_id[:8] if len(project_id) > 8 else project_id
            if project_name not in project_groups:
                project_groups[project_name] = []
            project_groups[project_name].append(channel)
    
    # Format global channels
    if global_channels:
        output.append("\nGLOBAL:")
        for channel in global_channels:
            name = channel.get('name', channel.get('id', 'unknown'))
            desc = channel.get('description', '')
            access = channel.get('access_type', 'open')
            is_member = channel.get('is_member', False)
            
            # Build status indicators
            status = []
            if channel.get('is_default'):
                status.append('default')
            if is_member:
                status.append('member')
            if access == 'members':
                status.append('invite-only')
            elif access == 'private':
                status.append('private')
            if channel.get('is_archived'):
                status.append('archived')
            
            status_str = f" [{', '.join(status)}]" if status else ""
            desc_str = f": {desc}" if desc else ""
            
            output.append(f"  {name}{status_str}{desc_str}")
    
    # Format project channels
    for project_name, project_channels in sorted(project_groups.items()):
        output.append(f"\nPROJECT ({project_name}):")
        for channel in project_channels:
            name = channel.get('name', channel.get('id', 'unknown'))
            desc = channel.get('description', '')
            access = channel.get('access_type', 'open')
            is_member = channel.get('is_member', False)
            
            # Build status indicators
            status = []
            if channel.get('is_default'):
                status.append('default')
            if is_member:
                status.append('member')
            if access == 'members':
                status.append('invite-only')
            elif access == 'private':
                status.append('private')
            if channel.get('is_archived'):
                status.append('archived')
            
            status_str = f" [{', '.join(status)}]" if status else ""
            desc_str = f": {desc}" if desc else ""
            
            output.append(f"  {name}{status_str}{desc_str}")
    
    return "\n".join(output)


def format_channel_name(channel_id: str) -> str:
    """
    Format channel ID for display in messages.
    This is for backward compatibility.
    """
    if not channel_id:
        return "unknown"
    
    if channel_id.startswith('global:'):
        name = channel_id.split(':', 1)[1]
        return f"{name} (global)"
    elif channel_id.startswith('proj_'):
        parts = channel_id.split(':', 1)
        name = parts[1] if len(parts) > 1 else channel_id
        return name
    elif channel_id.startswith('dm:'):
        return "DM"
    elif channel_id.startswith('notes:'):
        return "Note"
    else:
        if ':' in channel_id:
            return channel_id.split(':', 1)[1]
        return channel_id