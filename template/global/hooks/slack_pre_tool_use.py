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
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Add MCP directory to path to import modules
claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
mcp_dir = os.path.join(claude_config_dir, 'mcp', 'claude-slack')
sys.path.insert(0, mcp_dir)
sys.path.insert(0, os.path.join(mcp_dir, 'db'))
sys.path.insert(0, os.path.join(claude_config_dir, 'hooks'))

try:
    from environment_config import env_config
    USE_ENV_CONFIG = True
except ImportError:
    # Fallback if environment_config not available yet
    USE_ENV_CONFIG = False

# Import db_helpers for connection management
try:
    from db_helpers import connect
except ImportError:
    # Fallback if db_helpers not available
    from contextlib import contextmanager
    
    @contextmanager
    def connect(db_path: str, writer: bool = False):
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            if writer:
                conn.commit()
        except Exception:
            if writer:
                conn.rollback()
            raise
        finally:
            conn.close()

# Set up logging - use new centralized logging system
try:
    from log_manager.manager import get_logger
    logger = get_logger('pre_tool_use', component='hook')
    
    # Helper functions for structured logging
    def log_json_data(logger, message, data, level=logging.DEBUG):
        """Log data as JSON for structured logging"""
        logger.log(level, f"{message}: {json.dumps(data, default=str)}")
    
    def log_db_result(logger, operation, success, data=None):
        """Log database operation results"""
        if success:
            logger.info(f"DB {operation}: success")
        else:
            logger.error(f"DB {operation}: failed", extra={'data': data})
            
except ImportError:
    # Fallback to null logging if system not available
    import logging
    logger = logging.getLogger('PreToolUse')
    logger.addHandler(logging.NullHandler())
    def log_json_data(l, m, d, level=None): pass
    def log_db_result(l, o, s, d=None): pass

def record_tool_call(session_id: str, tool_name: str, tool_inputs: dict) -> bool:
    """
    Record tool call with session, tool name, and inputs for precise session tracking.
    
    Args:
        session_id: Current session ID
        tool_name: Name of the tool being called
        tool_inputs: Input parameters for the tool
        
    Returns:
        True if successful
    """
    try:
        logger.debug(f"Recording tool call: session={session_id}, tool={tool_name}")
        
        # Database path - use environment config if available
        if USE_ENV_CONFIG:
            db_path = env_config.db_path
        else:
            db_path = Path(claude_config_dir) / 'data' / 'claude-slack.db'
        
        logger.debug(f"Using database: {db_path}")
        
        # Ensure database directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use connection helper for proper management
        with connect(db_path, writer=True) as conn:
            # Create hash of tool inputs for efficient matching
            inputs_json = json.dumps(tool_inputs, sort_keys=True)
            inputs_hash = hashlib.sha256(inputs_json.encode()).hexdigest()[:16]
            
            logger.debug(f"Tool inputs hash: {inputs_hash}")
            
            # Record the tool call
            cursor = conn.execute("""
                INSERT INTO tool_calls (session_id, tool_name, tool_inputs_hash, tool_inputs)
                VALUES (?, ?, ?, ?)
            """, (session_id, tool_name, inputs_hash, inputs_json))
            
            tool_call_id = cursor.lastrowid
            logger.info(f"Recorded tool call with ID {tool_call_id}")
            
            # Also update session activity
            cursor = conn.execute("""
                UPDATE sessions
                SET updated_at = datetime('now')
                WHERE id=?
            """, (session_id,))
            
            sessions_updated = cursor.rowcount
            logger.debug(f"Updated {sessions_updated} session(s)")
        
        log_db_result(logger, 'record_tool_call', True, {
            'session_id': session_id,
            'tool': tool_name,
            'hash': inputs_hash,
            'sessions_updated': sessions_updated
        })
        return True
        
    except sqlite3.OperationalError as e:
        # Database is locked or other operational error
        logger.warning(f"Database unavailable: {e}, falling back to file storage")
        log_db_result(logger, 'record_tool_call', False, {'error': str(e), 'fallback': 'file'})
        return update_session_context_file(session_id, tool_name, tool_inputs)
        
    except Exception as e:
        logger.error(f"Error recording tool call: {e}\n{traceback.format_exc()}")
        log_db_result(logger, 'record_tool_call', False, {'error': str(e), 'fallback': 'file'})
        # Fall back to file storage
        return update_session_context_file(session_id, tool_name, tool_inputs)

def update_session_context_file(session_id: str, tool_name: str = None, tool_inputs: dict = None) -> bool:
    """
    Fallback: Write session update to a file if database is unavailable.
    
    Args:
        session_id: Current session ID
        tool_name: Name of the tool being called
        tool_inputs: Input parameters for the tool
        
    Returns:
        True if successful
    """
    try:
        logger.debug("Using file-based fallback for session storage")
        
        # Create sessions directory - use environment config if available
        if USE_ENV_CONFIG:
            sessions_dir = env_config.sessions_dir
        else:
            sessions_dir = Path(claude_config_dir) / 'data' / 'claude-slack-sessions'
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Write session context file with tool info
        session_file = sessions_dir / f"{session_id}.json"
        context = {
            'session_id': session_id,
            'tool_name': tool_name,
            'tool_inputs': tool_inputs,
            'updated_at': datetime.now().isoformat()
        }
        
        session_file.write_text(json.dumps(context, indent=2))
        logger.info(f"Wrote session context to {session_file}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write session file: {e}\n{traceback.format_exc()}")
        return False

def main():
    """Main hook entry point - reads JSON from stdin"""
    try:
        # Read JSON payload from stdin
        input_data = sys.stdin.read()
        if not input_data:
            logger.debug("No input data received, exiting")
            return 0
            
        payload = json.loads(input_data)
        log_json_data(logger, "Received payload", payload)
        
        # Extract fields from payload
        session_id = payload.get('session_id', '')
        cwd = payload.get('cwd', os.getcwd())
        tool_name = payload.get('tool_name', '')
        hook_event = payload.get('hook_event_name', '')
        transcript_path = payload.get('transcript_path', '')
        tool_input = payload.get('tool_input', {})
        
        logger.info(f"PreToolUse Hook: session={session_id}, tool={tool_name}, cwd={cwd}")
        logger.debug(f"Event: {hook_event}, Transcript: {transcript_path}")
                
        # For MCP tools, the tool_name might be the MCP server name
        # and the actual tool would be in tool_input
        is_slack_tool = (
            'claude_slack' in tool_name or 
            'claude-slack' in tool_name or
            (tool_name == 'mcp' and 'claude-slack' in str(tool_input))
        )
        
        if not is_slack_tool:
            logger.debug(f"Not a slack tool, passing through: {tool_name}")
            return 0
                
        logger.info(f"Processing slack tool: {tool_name}")
        
        # Record the tool call with inputs for precise session tracking
        success = record_tool_call(session_id, tool_name, tool_input)
        
        if success:
            logger.info("Tool call successfully recorded")
        else:
            logger.warning("Tool call recording failed but continuing")
        
        # Always return 0 to allow tool to continue
        return 0
        
    except json.JSONDecodeError as e:
        # Invalid JSON input
        logger.error(f"Invalid JSON input: {e}")
        logger.debug(f"Raw input: {input_data[:500]}...")  # Log first 500 chars
        return 0
        
    except Exception as e:
        # Any other error, log but don't fail
        logger.error(f"Unexpected error in main: {e}\n{traceback.format_exc()}")
        return 0

if __name__ == '__main__':
    sys.exit(main())