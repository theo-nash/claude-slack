#!/usr/bin/env python3
"""
Formatting utilities for claude-slack MCP server
Provides concise, token-efficient output formats for agent consumption
"""

from datetime import datetime
from typing import Dict, List, Any

def format_channel_name(channel_id: str) -> str:
    """
    Format channel ID for user-friendly display.
    
    Examples:
        'global:general' -> '#general'
        'proj_abc123:dev' -> '#dev (project)'
        'dm:alice:bob:proj_xyz' -> 'DM with alice'
        'notes:assistant:proj_abc' -> 'Notes'
    """
    if not channel_id:
        return "unknown"
    
    if channel_id.startswith('global:'):
        # Global channels get a special indicator
        name = channel_id.split(':', 1)[1]
        return f"#{name}!"  # ! indicates global
    elif channel_id.startswith('proj_'):
        # Project channels are the default
        name = channel_id.split(':', 1)[1]
        return f"#{name}"
    elif channel_id.startswith('dm:'):
        # Extract the other party's name
        parts = channel_id.split(':')
        # Find the name that's not 'assistant' 
        other = [p for p in parts[1:3] if p != 'assistant']
        if other:
            return f"DM with {other[0]}"
        return "DM"
    elif channel_id.startswith('notes:'):
        return "Personal Notes"
    else:
        # Unknown format, just return the name part if possible
        if ':' in channel_id:
            return f"#{channel_id.split(':', 1)[1]}"
        return f"#{channel_id}"

def format_time_ago(timestamp_str: str) -> str:
    """Convert timestamp to human-readable time ago format"""
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now()
        diff = now - timestamp
        
        if diff.total_seconds() < 60:
            return "just now"
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes}m ago"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}h ago"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            weeks = diff.days // 7
            return f"{weeks}w ago"
    except:
        return timestamp_str

def format_messages_concise(messages_data: Dict, agent_name: str) -> str:
    """
    Format messages in concise, human-readable format
    80% more token-efficient than JSON
    """
    output = []
    total_count = 0
    
    # Count total messages
    global_msgs = messages_data.get("global_messages", {})
    project_msgs = messages_data.get("project_messages", {})
    
    for channel_msgs in global_msgs.get("channel_messages", {}).values():
        total_count += len(channel_msgs)
    total_count += len(global_msgs.get("direct_messages", []))
    total_count += len(global_msgs.get("notes", []))
    
    if project_msgs:
        for channel_msgs in project_msgs.get("channel_messages", {}).values():
            total_count += len(channel_msgs)
        total_count += len(project_msgs.get("direct_messages", []))
        total_count += len(project_msgs.get("notes", []))
    
    output.append(f"=== Recent Messages ({total_count} total) ===")
    
    # Global channels
    if global_msgs.get("channel_messages"):
        output.append("\nGLOBAL CHANNELS:")
        for channel_name, messages in global_msgs["channel_messages"].items():
            for msg in messages:
                time_ago = format_time_ago(msg["timestamp"])
                output.append(f'[global/{channel_name}] {msg["sender_id"]}: "{msg["content"]}" ({time_ago})')
    
    # Project messages
    if project_msgs:
        project_name = project_msgs.get("project_name", "unknown")
        if project_msgs.get("channel_messages"):
            output.append(f"\nPROJECT: {project_name}")
            for channel_name, messages in project_msgs["channel_messages"].items():
                for msg in messages:
                    time_ago = format_time_ago(msg["timestamp"])
                    output.append(f'[project/{channel_name}] {msg["sender_id"]}: "{msg["content"]}" ({time_ago})')
    
    # Direct messages (both global and project)
    all_dms = []
    if global_msgs.get("direct_messages"):
        all_dms.extend(global_msgs["direct_messages"])
    if project_msgs and project_msgs.get("direct_messages"):
        all_dms.extend(project_msgs["direct_messages"])
    
    if all_dms:
        output.append("\nDIRECT MESSAGES:")
        for msg in all_dms:
            time_ago = format_time_ago(msg["timestamp"])
            if msg["is_sent"]:
                # Message sent by the agent
                output.append(f'[DM] You → {msg["recipient_id"]}: "{msg["content"]}" ({time_ago})')
            else:
                # Message received by the agent
                output.append(f'[DM] {msg["sender_id"]} → You: "{msg["content"]}" ({time_ago})')
    
    # Agent notes (both global and project)
    all_notes = []
    if global_msgs.get("notes"):
        for note in global_msgs["notes"]:
            note["scope"] = "global"
            all_notes.append(note)
    if project_msgs and project_msgs.get("notes"):
        for note in project_msgs["notes"]:
            note["scope"] = "project"
            all_notes.append(note)
    
    if all_notes:
        output.append("\nMY NOTES:")
        for note in all_notes:
            time_ago = format_time_ago(note["timestamp"])
            tags = note.get("tags", [])
            tag_str = f" #{', #'.join(tags)}" if tags else ""
            scope = note.get('scope', 'global')
            
            # Don't truncate - agents need full context
            content = note["content"]
            
            output.append(f'[{scope}/note{tag_str}] "{content}" ({time_ago})')
    
    if total_count == 0:
        return "=== No messages found ==="
    
    return "\n".join(output)

def format_agents_concise(agents: List[Dict]) -> str:
    """Format agent list in concise, readable format"""
    if not agents:
        return "=== No agents found ==="
    
    output = [f"=== Available Agents ({len(agents)} total) ==="]
    
    # Group by scope
    global_agents = [a for a in agents if a.get("project_id") is None]
    project_groups = {}
    for agent in agents:
        if agent.get("project_id") is not None:
            project = agent.get("project_id", "Unknown")[:8]
            if project not in project_groups:
                project_groups[project] = []
            project_groups[project].append(agent)
    
    # Format global agents
    if global_agents:
        output.append("\nGLOBAL:")
        for agent in global_agents:
            desc = agent.get("description", "No description")
            output.append(f'• {agent["name"]}: "{desc}"')
    
    # Format project agents
    for project_name, project_agents in project_groups.items():
        output.append(f"\nPROJECT: {project_name}")
        for agent in project_agents:
            desc = agent.get("description", "No description")
            output.append(f'• {agent["name"]}: "{desc}"')
    
    return "\n".join(output)

def format_search_results_concise(results: List[Dict], query: str, agent_name: str) -> str:
    """Format search results in concise format"""
    if not results:
        return f'=== No messages found matching "{query}" ==='
    
    output = [f'=== Search Results for "{query}" ({len(results)} matches) ===\n']
    
    for msg in results:
        timestamp = msg.get('timestamp', 'unknown time')
        time_ago = format_time_ago(timestamp)
        sender = msg.get('sender_id', 'unknown')
        content = msg.get('content', '')
        channel = msg.get('channel_id')
        
        # Don't truncate - agents need full context
        
        # Determine location and format appropriately
        if not channel:
            # Direct message
            if sender == agent_name:
                # Sent by the agent
                recipient = msg.get('recipient_id', 'unknown')
                output.append(f'[DM] You → {recipient}: "{content}" ({time_ago})')
            else:
                # Received by the agent
                output.append(f'[DM] {sender} → You: "{content}" ({time_ago})')
        else:
            # Use the new format_channel_name helper
            channel_display = format_channel_name(channel)
            output.append(f'[{channel_display}] {sender}: "{content}" ({time_ago})')
    
    return "\n".join(output)

def format_notes_concise(notes: List[Dict], title: str = "Notes") -> str:
    """Format notes in concise, readable format"""
    if not notes:
        return f"No {title.lower()} found"
    
    output = [f"=== {title} ===\n"]
    
    for note in notes:
        time_ago = format_time_ago(note["timestamp"])
        tags = note.get("tags", [])
        tag_str = f" #{', #'.join(tags)}" if tags else ""
        
        # Don't truncate - agents need full context
        content = note["content"]
        
        output.append(f'[note{tag_str}] "{content}" ({time_ago})')
    
    return "\n".join(output)

def format_note_search_results(results: List[Dict], query: str = None, tags: List[str] = None) -> str:
    """Format note search results"""
    if not results:
        search_desc = []
        if query:
            search_desc.append(f'query "{query}"')
        if tags:
            search_desc.append(f'tags {tags}')
        search_str = " and ".join(search_desc) if search_desc else "all notes"
        return f"No notes found matching {search_str}"
    
    title = f"Found {len(results)} note(s)"
    return format_notes_concise(results, title)

def format_peek_notes(notes: List[Dict], agent_name: str, query: str = None) -> str:
    """Format peeking at another agent's notes"""
    if not notes:
        search_str = f' matching "{query}"' if query else ""
        return f"No notes found for {agent_name}{search_str}"
    
    title = f"Peeking at {agent_name}'s notes ({len(notes)} found)"
    return format_notes_concise(notes, title)

def format_flat_messages(messages: List[Dict], agent_name: str, project_name: str = None) -> str:
    """
    Format a flat list of messages from get_agent_messages.
    Handles the transformation and formatting in one place.
    
    Args:
        messages: Flat list of message dictionaries
        agent_name: Name of the agent viewing messages
        project_name: Optional project name for context
        
    Returns:
        Formatted message string
    """
    if not messages:
        return "=== No recent messages ==="
    
    # Transform flat list into structured format
    messages_data = {
        "global_messages": {
            "channel_messages": {},
            "direct_messages": [],
            "notes": []
        },
        "project_messages": {
            "channel_messages": {},
            "direct_messages": [],
            "notes": [],
            "project_name": project_name or "unknown"
        }
    }
    
    # Group messages by type and scope
    for msg in messages:
        channel_id = msg.get('channel_id', '')
        
        # Check if it's a direct message
        if channel_id.startswith('dm:'):
            # Determine if sent or received
            is_sent = msg['sender_id'] == agent_name
            if is_sent:
                msg['is_sent'] = True
                msg['recipient_id'] = msg.get('recipient_id', 'unknown')
            else:
                msg['is_sent'] = False
            
            # Add to appropriate scope
            if 'proj_' in channel_id:
                messages_data['project_messages']['direct_messages'].append(msg)
            else:
                messages_data['global_messages']['direct_messages'].append(msg)
                
        # Check if it's a notes message
        elif channel_id.startswith('notes:'):
            # Determine scope from channel_id pattern
            if 'proj_' in channel_id or ':proj_' in channel_id:
                messages_data['project_messages']['notes'].append(msg)
            else:
                messages_data['global_messages']['notes'].append(msg)
                
        # Regular channel message
        else:
            # Extract channel name from ID
            if channel_id.startswith('global:'):
                channel_name = channel_id.split(':', 1)[1]
                if channel_name not in messages_data['global_messages']['channel_messages']:
                    messages_data['global_messages']['channel_messages'][channel_name] = []
                messages_data['global_messages']['channel_messages'][channel_name].append(msg)
                
            elif channel_id.startswith('proj_'):
                # Project channel
                parts = channel_id.split(':', 1)
                channel_name = parts[1] if len(parts) > 1 else channel_id
                if channel_name not in messages_data['project_messages']['channel_messages']:
                    messages_data['project_messages']['channel_messages'][channel_name] = []
                messages_data['project_messages']['channel_messages'][channel_name].append(msg)
    
    # Now use the existing format_messages_concise
    return format_messages_concise(messages_data, agent_name)

def format_channel_list(channels: List[Dict], agent_name: str = None) -> str:
    """
    Format channel list in concise, readable format
    
    Args:
        channels: List of channel dictionaries
        agent_name: Optional agent name to show membership status
        
    Returns:
        Formatted channel list string
    """
    if not channels:
        return "=== No channels found ==="
    
    output = [f"=== Channels ({len(channels)} total) ==="]
    
    # Group by scope
    global_channels = []
    project_groups = {}
    
    for channel in channels:
        scope = channel.get('scope', 'global')
        if scope == 'global':
            global_channels.append(channel)
        else:
            project_id = channel.get('project_id', 'unknown')
            project_name = channel.get('project_name', project_id[:8] if len(project_id) > 8 else project_id)
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
            if access == 'members':
                status.append('invite-only')
            elif access == 'private':
                status.append('private')
            if channel.get('is_archived'):
                status.append('archived')
            if channel.get('is_default'):
                status.append('default')
            if is_member:
                status.append('✓ member')
            
            status_str = f" [{', '.join(status)}]" if status else ""
            desc_str = f': "{desc}"' if desc else ""
            
            output.append(f"• {name}{status_str}{desc_str}")
    
    # Format project channels
    for project_name, project_channels in project_groups.items():
        output.append(f"\nPROJECT: {project_name}")
        for channel in project_channels:
            name = channel.get('name', channel.get('id', 'unknown'))
            desc = channel.get('description', '')
            access = channel.get('access_type', 'open')
            is_member = channel.get('is_member', False)
            
            # Build status indicators
            status = []
            if access == 'members':
                status.append('invite-only')
            elif access == 'private':
                status.append('private')
            if channel.get('is_archived'):
                status.append('archived')
            if channel.get('is_default'):
                status.append('default')
            if is_member:
                status.append('✓ member')
            
            status_str = f" [{', '.join(status)}]" if status else ""
            desc_str = f': "{desc}"' if desc else ""
            
            output.append(f"• {name}{status_str}{desc_str}")
    
    return "\n".join(output)