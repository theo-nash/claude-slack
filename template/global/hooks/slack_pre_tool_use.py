#!/usr/bin/env python3
"""
slack_pre_tool_use.py - MUST BE INSTALLED GLOBALLY in Claude hooks directory
Sets project context in SQLite database before each tool invocation.

This hook receives a JSON payload from Claude Code on stdin containing:
- session_id: Current session identifier  
- cwd: Current working directory
- tool_name: Name of the tool being invoked
- tool_input: Tool-specific parameters

The hook detects if we're in a project context by looking for .claude
directory and stores the session context in the SQLite database.
"""

import os
import sys
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

# Add MCP directory to path to import environment_config
claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
sys.path.insert(0, os.path.join(claude_config_dir, 'mcp', 'claude-slack'))

try:
    from environment_config import env_config
    USE_ENV_CONFIG = True
except ImportError:
    # Fallback if environment_config not available yet
    USE_ENV_CONFIG = False

def find_project_root(working_dir: str) -> Optional[str]:
    """
    Walk up from working_dir to find .claude directory
    
    Args:
        working_dir: Current working directory from hook payload
        
    Returns:
        Absolute path to project root or None if no project found
    """
    if USE_ENV_CONFIG:
        # Use centralized project detection
        result = env_config.find_project_root(working_dir)
        return str(result) if result else None
    
    # Fallback to original logic
    current = Path(working_dir).resolve()
    
    # Walk up directory tree
    while current != current.parent:
        if (current / '.claude').exists():
            return str(current)
        current = current.parent
    
    return None  # No project found, use global context

def get_project_id(project_path: str) -> str:
    """
    Generate consistent project ID from path
    
    Args:
        project_path: Absolute path to project root
        
    Returns:
        32-character project ID
    """
    return hashlib.sha256(project_path.encode()).hexdigest()[:32]

def set_session_context_db(session_id: str, project_info: Optional[Dict[str, str]]) -> bool:
    """
    Store session context in SQLite database.
    Uses WAL mode for better concurrency and falls back to file if DB is locked.
    
    Args:
        session_id: Current session ID
        project_info: Dict with project_id, project_path, project_name or None
        
    Returns:
        True if successful
    """
    try:
        # Database path - use environment config if available
        if USE_ENV_CONFIG:
            db_path = env_config.db_path
        else:
            db_path = Path(claude_config_dir) / 'data' / 'claude-slack.db'
        
        # Ensure database directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect with short timeout to avoid blocking
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        
        # Enable WAL mode for better concurrency (only needs to be done once)
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Insert or update session context
        conn.execute("""
            INSERT OR REPLACE INTO sessions 
            (id, project_id, project_path, project_name, transcript_path, scope, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            session_id,
            project_info.get('project_id') if project_info else None,
            project_info.get('project_path') if project_info else None,
            project_info.get('project_name') if project_info else None,
            project_info.get('transcript_path') if project_info else None,
            'project' if project_info else 'global'
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except sqlite3.OperationalError as e:
        # Database is locked or other operational error
        # Fall back to file-based storage
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"Database unavailable, using file fallback: {e}", file=sys.stderr)
        return set_session_context_file(session_id, project_info)
        
    except Exception as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"Error writing session to database: {e}", file=sys.stderr)
        # Fall back to file storage
        return set_session_context_file(session_id, project_info)

def set_session_context_file(session_id: str, project_info: Optional[Dict[str, str]]) -> bool:
    """
    Fallback: Write session context to a file if database is unavailable.
    
    Args:
        session_id: Current session ID
        project_info: Dict with project_id, project_path, project_name or None
        
    Returns:
        True if successful
    """
    try:
        # Create sessions directory - use environment config if available
        if USE_ENV_CONFIG:
            sessions_dir = env_config.sessions_dir
        else:
            sessions_dir = Path(claude_config_dir) / 'data' / 'claude-slack-sessions'
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Write session context file
        session_file = sessions_dir / f"{session_id}.json"
        context = {
            'session_id': session_id,
            'project_id': project_info.get('project_id') if project_info else None,
            'project_path': project_info.get('project_path') if project_info else None,
            'project_name': project_info.get('project_name') if project_info else None,
            'scope': 'project' if project_info else 'global'
        }
        
        session_file.write_text(json.dumps(context, indent=2))
        return True
        
    except Exception as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"Error writing session context file: {e}", file=sys.stderr)
        return False

def main():
    """Main hook entry point - reads JSON from stdin"""
    try:
        # Read JSON payload from stdin
        input_data = sys.stdin.read()
        if not input_data:
            # No input, might be testing
            return 0
            
        payload = json.loads(input_data)
        
        # Extract fields from payload
        session_id = payload.get('session_id', '')
        cwd = payload.get('cwd', os.getcwd())
        tool_name = payload.get('tool_name', '')
        hook_event = payload.get('hook_event_name', '')
        transcript_path = payload.get('transcript_path', '')
        
        # Debug logging if enabled
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            if USE_ENV_CONFIG:
                debug_file = env_config.logs_dir / 'slack_pre_tool_use.log'
            else:
                debug_file = Path(claude_config_dir) / 'logs' / 'slack_pre_tool_use.log'
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_file, 'a') as f:
                f.write(f"\n--- PreToolUse Hook ---\n")
                f.write(f"Session: {session_id}\n")
                f.write(f"CWD: {cwd}\n")
                f.write(f"Tool: {tool_name}\n")
                f.write(f"Event: {hook_event}\n")
                f.write(f"Transcript: {transcript_path}\n")
        
        # Only process for claude-slack MCP tools
        # Check if this is a claude-slack tool invocation
        tool_input = payload.get('tool_input', {})
        
        # For MCP tools, the tool_name might be the MCP server name
        # and the actual tool would be in tool_input
        is_slack_tool = (
            'claude_slack' in tool_name or 
            'claude-slack' in tool_name or
            (tool_name == 'mcp' and 'claude-slack' in str(tool_input))
        )
        
        if not is_slack_tool:
            # Not our tool, pass through
            return 0
        
        # Find project root from cwd
        project_path = find_project_root(cwd)
        
        # Prepare project info if in project
        project_info = None
        if project_path:
            project_info = {
                'project_id': get_project_id(project_path),
                'project_path': project_path,
                'project_name': os.path.basename(project_path),
                'transcript_path': transcript_path
            }
            
            if os.environ.get('CLAUDE_SLACK_DEBUG'):
                with open(debug_file, 'a') as f:
                    f.write(f"Project detected: {project_info['project_name']}\n")
                    f.write(f"Project ID: {project_info['project_id']}\n")
        else:
            if os.environ.get('CLAUDE_SLACK_DEBUG'):
                with open(debug_file, 'a') as f:
                    f.write("No project detected, using global context\n")
        
        # Set session context in database (with file fallback)
        success = set_session_context_db(session_id, project_info)
        
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            with open(debug_file, 'a') as f:
                f.write(f"Context set: {success}\n")
        
        # Always return 0 to allow tool to continue
        return 0
        
    except json.JSONDecodeError as e:
        # Invalid JSON input, log if debug enabled
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"PreToolUse: Invalid JSON input: {e}", file=sys.stderr)
        return 0
        
    except Exception as e:
        # Any other error, log but don't fail
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"PreToolUse: Unexpected error: {e}", file=sys.stderr)
        return 0

if __name__ == '__main__':
    sys.exit(main())