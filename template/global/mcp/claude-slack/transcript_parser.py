#!/usr/bin/env python3
"""
Transcript Parser for Claude-Slack
Efficiently parses Claude session transcripts (JSONL format) to extract caller information and session metadata.
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class CallerInfo:
    """Information about who made a tool call"""
    agent: str              # "main", "task-executor", "memory-manager", etc.
    is_subagent: bool      # True if called from a subagent
    confidence: str        # "HIGH", "MEDIUM", "LOW"
    tool_name: Optional[str] = None  # The tool that was called
    timestamp: Optional[str] = None  # When the call was made
    error: Optional[str] = None      # Any error encountered during detection


class TranscriptParser:
    """
    Efficiently parse Claude session transcripts to extract caller information and metadata.
    Optimized for reading from the end of file for recent activity.
    """
    
    def __init__(self, transcript_path: str, max_read_size: int = 100000):
        """
        Initialize parser with transcript path.
        
        Args:
            transcript_path: Path to the JSONL transcript file
            max_read_size: Maximum bytes to read from end of file (default 100KB)
        """
        self.transcript_path = transcript_path
        self.max_read_size = max_read_size
        
        if not os.path.exists(transcript_path):
            raise FileNotFoundError(f"Transcript not found: {transcript_path}")
    
    def parse_all_entries(self) -> List[Dict]:
        """
        Parse all entries from the transcript.
        Used when we need to build UUID index for parent traversal.
        
        Returns:
            List of all parsed JSON entries
        """
        entries = []
        try:
            with open(self.transcript_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        return entries
    
    def parse_recent_entries(self, count: int = 100) -> List[Dict]:
        """
        Parse last N entries from end of file efficiently.
        
        Args:
            count: Number of recent entries to return
            
        Returns:
            List of parsed JSON entries (most recent last)
        """
        try:
            with open(self.transcript_path, 'r') as f:
                # Seek to end to get file size
                f.seek(0, 2)
                file_size = f.tell()
                
                # Read last chunk (up to max_read_size)
                read_size = min(self.max_read_size, file_size)
                f.seek(max(0, file_size - read_size))
                
                entries = []
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            # Skip malformed lines
                            continue
                
                # Return last N entries
                return entries[-count:] if len(entries) > count else entries
                
        except Exception as e:
            return []
    
    def get_caller_info(self, tool_name: Optional[str] = None) -> CallerInfo:
        """
        Get who made the most recent tool call by following parentUuid chain.
        
        Args:
            tool_name: If provided, find most recent call to this specific tool
            
        Returns:
            CallerInfo with agent name, is_subagent flag, and confidence level
        """
        # For caller detection, we need the full entries to build UUID index
        entries = self.parse_all_entries()
        
        if not entries:
            return CallerInfo(
                agent="unknown",
                is_subagent=False,
                confidence="LOW",
                error="No entries found in transcript"
            )
        
        # Build UUID index for fast parent lookups
        uuid_index = {entry.get("uuid"): entry for entry in entries if entry.get("uuid")}
        
        # Traverse from end to find tool invocation
        for i in range(len(entries) - 1, -1, -1):
            entry = entries[i]
            
            # Skip non-assistant entries
            if entry.get("type") != "assistant":
                continue
            
            message = entry.get("message", {})
            if not isinstance(message.get("content"), list):
                continue
            
            # Look for tool uses in the content
            for content in message["content"]:
                if content.get("type") != "tool_use":
                    continue
                
                found_tool = content.get("name", "")
                
                # Check if this matches our target tool (if specified)
                if tool_name:
                    # Support partial matching for MCP tools
                    if tool_name not in found_tool and not found_tool.endswith(tool_name):
                        continue
                
                # Found a matching tool invocation
                is_sidechain = entry.get("isSidechain", False)
                timestamp = entry.get("timestamp")
                
                if is_sidechain:
                    # Follow parentUuid chain to find Task invocation
                    # Pass entries and index for prompt-matching fallback
                    agent_type = self.get_subagent_type_from_parent_chain(
                        entry, uuid_index, entries, i
                    )
                    return CallerInfo(
                        agent=agent_type,
                        is_subagent=True,
                        confidence="HIGH" if agent_type != "unknown_subagent" else "MEDIUM",
                        tool_name=found_tool,
                        timestamp=timestamp
                    )
                else:
                    # Main agent
                    return CallerInfo(
                        agent="assistant",
                        is_subagent=False,
                        confidence="HIGH",
                        tool_name=found_tool,
                        timestamp=timestamp
                    )
        
        # No matching tool invocation found
        return CallerInfo(
            agent="unknown",
            is_subagent=False,
            confidence="LOW",
            error=f"No tool invocation found{f' for {tool_name}' if tool_name else ''}"
        )
    
    def find_matching_task_by_prompt(self, entries: List[Dict], prompt: str, before_index: int) -> Optional[str]:
        """
        Find a Task invocation with matching prompt before the given index.
        Returns the subagent_type if found.
        """
        # Search backwards from before_index
        for entry in reversed(entries[:before_index]):
            if entry.get("type") != "assistant":
                continue
                
            message = entry.get("message", {})
            if not isinstance(message.get("content"), list):
                continue
                
            for content in message["content"]:
                if content.get("type") == "tool_use" and content.get("name") == "Task":
                    task_input = content.get("input", {})
                    task_prompt = task_input.get("prompt", "")
                    
                    # Check if prompts match
                    if task_prompt == prompt:
                        return task_input.get("subagent_type", "unknown")
        
        return None
    
    def get_sidechain_prompt(self, entry: Dict) -> Optional[str]:
        """
        Get the prompt from a sidechain entry.
        For sidechains with parentUuid: null, the entry itself contains the prompt.
        """
        if entry.get("parentUuid") is None and entry.get("type") == "user":
            message = entry.get("message", {})
            content = message.get("content")
            
            if isinstance(content, str):
                return content
            elif isinstance(content, list) and len(content) > 0:
                # Handle structured content
                if isinstance(content[0], dict):
                    return content[0].get("text", "")
                else:
                    return str(content[0])
        
        return None
    
    def get_subagent_type_from_parent_chain(self, entry: Dict, uuid_index: Dict[str, Dict], entries: List[Dict] = None, entry_index: int = None) -> str:
        """
        Follow the parentUuid chain to find the Task invocation that launched this subagent.
        Falls back to prompt matching if chain is broken.
        
        Args:
            entry: The current entry (tool invocation by subagent)
            uuid_index: Index mapping UUIDs to entries for fast lookup
            entries: All entries (for prompt matching fallback)
            entry_index: Index of current entry (for prompt matching fallback)
            
        Returns:
            Subagent type (e.g., "task-executor", "memory-manager") or "unknown_subagent"
        """
        current_entry = entry
        visited = set()  # Prevent infinite loops
        
        # Follow parent chain up to 50 levels (reasonable limit)
        for _ in range(50):
            parent_uuid = current_entry.get("parentUuid")
            
            # Stop if no parent or we've seen this UUID before
            if not parent_uuid or parent_uuid in visited:
                break
                
            visited.add(parent_uuid)
            parent_entry = uuid_index.get(parent_uuid)
            
            if not parent_entry:
                break
            
            # Check if this parent is an assistant message with Task invocation
            if parent_entry.get("type") == "assistant":
                message = parent_entry.get("message", {})
                if isinstance(message.get("content"), list):
                    for content in message["content"]:
                        if content.get("type") == "tool_use" and content.get("name") == "Task":
                            # Found the Task invocation!
                            task_input = content.get("input", {})
                            return task_input.get("subagent_type", "unknown")
            
            # Move up the chain
            current_entry = parent_entry
        
        # If we couldn't follow the parent chain and we have entries for fallback
        if entries and entry_index is not None:
            # Try prompt-based matching
            # Walk back to find the sidechain start (parentUuid: null)
            for j in range(entry_index, -1, -1):
                check_entry = entries[j]
                if check_entry.get("isSidechain") and check_entry.get("parentUuid") is None:
                    # Found the sidechain start - get its prompt
                    prompt = self.get_sidechain_prompt(check_entry)
                    if prompt:
                        # Find matching task
                        subagent_type = self.find_matching_task_by_prompt(entries, prompt, j)
                        if subagent_type:
                            return subagent_type
                    break
        
        return "unknown_subagent"
    
    def get_subagent_type_from_task(self, entries: List[Dict], start_idx: int) -> str:
        """
        Legacy method - kept for backwards compatibility.
        Use get_subagent_type_from_parent_chain instead.
        """
        # Build UUID index
        uuid_index = {entry.get("uuid"): entry for entry in entries if entry.get("uuid")}
        return self.get_subagent_type_from_parent_chain(entries[start_idx], uuid_index)
    
    def get_session_metadata(self) -> Dict[str, Any]:
        """
        Extract session metadata from the first entry.
        
        Returns:
            Dictionary with session_id, version, cwd, git_branch
        """
        try:
            with open(self.transcript_path, 'r') as f:
                # Read first line
                first_line = f.readline().strip()
                if not first_line:
                    return {}
                
                first_entry = json.loads(first_line)
                
                return {
                    "session_id": first_entry.get("sessionId"),
                    "version": first_entry.get("version"),
                    "cwd": first_entry.get("cwd"),
                    "git_branch": first_entry.get("gitBranch"),
                    "user_type": first_entry.get("userType", "external")
                }
        except Exception:
            return {}
    
    def get_recent_tool_calls(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent tool invocations with their details.
        
        Args:
            limit: Maximum number of tool calls to return
            
        Returns:
            List of tool call details (most recent first)
        """
        entries = self.parse_recent_entries(count=200)  # Look at more entries for tool calls
        tool_calls = []
        
        for entry in reversed(entries):  # Start from most recent
            if entry.get("type") != "assistant":
                continue
            
            message = entry.get("message", {})
            if not isinstance(message.get("content"), list):
                continue
            
            for content in message["content"]:
                if content.get("type") == "tool_use":
                    tool_calls.append({
                        "tool_name": content.get("name"),
                        "tool_id": content.get("id"),
                        "input": content.get("input"),
                        "timestamp": entry.get("timestamp"),
                        "is_subagent": entry.get("isSidechain", False)
                    })
                    
                    if len(tool_calls) >= limit:
                        return tool_calls
        
        return tool_calls
    
    def get_last_user_message(self) -> Optional[str]:
        """
        Get the most recent user message content.
        
        Returns:
            User message text or None if not found
        """
        entries = self.parse_recent_entries()
        
        for entry in reversed(entries):
            if entry.get("type") == "user":
                message = entry.get("message", {})
                content = message.get("content")
                
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Extract text from content array
                    texts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            texts.append(item.get("text", ""))
                    return " ".join(texts) if texts else None
        
        return None
    
    def find_tool_invocation(self, tool_name: str, search_limit: int = 100) -> Optional[Dict]:
        """
        Find most recent invocation of a specific tool.
        
        Args:
            tool_name: Name of the tool to search for
            search_limit: Maximum number of entries to search
            
        Returns:
            Tool invocation details or None if not found
        """
        entries = self.parse_recent_entries(count=search_limit)
        
        for entry in reversed(entries):
            if entry.get("type") != "assistant":
                continue
            
            message = entry.get("message", {})
            if not isinstance(message.get("content"), list):
                continue
            
            for content in message["content"]:
                if content.get("type") == "tool_use":
                    found_tool = content.get("name", "")
                    if tool_name in found_tool or found_tool.endswith(tool_name):
                        return {
                            "tool_name": found_tool,
                            "tool_id": content.get("id"),
                            "input": content.get("input"),
                            "timestamp": entry.get("timestamp"),
                            "is_subagent": entry.get("isSidechain", False),
                            "uuid": entry.get("uuid")
                        }
        
        return None
    
    def get_tool_result(self, tool_use_id: str) -> Optional[Dict]:
        """
        Given a tool_use_id, find its corresponding result.
        
        Args:
            tool_use_id: The tool use ID to search for
            
        Returns:
            Tool result details or None if not found
        """
        entries = self.parse_recent_entries(count=200)
        
        for entry in entries:
            if entry.get("type") == "user":
                message = entry.get("message", {})
                content = message.get("content")
                
                if isinstance(content, list):
                    for item in content:
                        if (item.get("type") == "tool_result" and 
                            item.get("tool_use_id") == tool_use_id):
                            return {
                                "content": item.get("content"),
                                "timestamp": entry.get("timestamp"),
                                "is_error": item.get("is_error", False)
                            }
        
        return None