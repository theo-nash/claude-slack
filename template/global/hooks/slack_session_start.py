#!/usr/bin/env python3
"""
slack_session_start.py - MUST BE INSTALLED GLOBALLY at ~/.claude/hooks/
Initializes claude-slack session context and ensures agent MCP tool access.

This hook runs at the start of every Claude Code session and:
1. Registers the session with the messaging system
2. Detects project context from working directory
3. Ensures agents have access to claude-slack MCP tools
4. Creates project channels from configuration file
5. Syncs project links from configuration to database

This ensures projects are discovered immediately, not just when tools are called.
"""

import os
import sys
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

# Add MCP directory to path to import admin_operations
sys.path.insert(0, str(Path.home() / '.claude' / 'mcp' / 'claude-slack'))

try:
    from admin_operations import AdminOperations
except ImportError:
    AdminOperations = None

def find_project_root(working_dir: str) -> Optional[str]:
    """
    Walk up from working_dir to find .claude directory
    
    Args:
        working_dir: Current working directory
        
    Returns:
        Absolute path to project root or None if no project found
    """
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

def register_session_in_db(session_id: str, project_info: Optional[Dict[str, str]]) -> bool:
    """
    Register session in SQLite database at session start.
    
    Args:
        session_id: Current session ID
        project_info: Dict with project_id, project_path, project_name or None
        
    Returns:
        True if successful
    """
    try:
        # Database path
        db_path = Path.home() / '.claude' / 'data' / 'claude-slack.db'
        
        # Ensure database directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect with short timeout
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Insert or update session context
        conn.execute("""
            INSERT OR REPLACE INTO sessions 
            (id, project_id, project_path, project_name, scope, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            session_id,
            project_info.get('project_id') if project_info else None,
            project_info.get('project_path') if project_info else None,
            project_info.get('project_name') if project_info else None,
            'project' if project_info else 'global'
        ))
        
        # Register project if new
        if project_info:
            conn.execute("""
                INSERT OR IGNORE INTO projects (id, path, name, created_at, last_active)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """, (
                project_info['project_id'],
                project_info['project_path'],
                project_info['project_name']
            ))
            
            # Update last_active if project already exists
            conn.execute("""
                UPDATE projects 
                SET last_active = datetime('now')
                WHERE id = ?
            """, (project_info['project_id'],))
            
            # Use AdminOperations to handle all registration and channel creation
            if AdminOperations is not None:
                try:
                    # Initialize admin operations
                    import asyncio
                    admin_ops = AdminOperations()
                    
                    # Register project and create channels
                    asyncio.run(admin_ops.register_project(
                        project_info['project_path'],
                        project_info['project_name']
                    ))
                    
                    # Create global channels
                    asyncio.run(admin_ops.create_default_channels())
                    
                    # Sync project links from config
                    asyncio.run(admin_ops.sync_project_links_from_config())
                    
                except Exception as e:
                    if os.environ.get('CLAUDE_SLACK_DEBUG'):
                        print(f"Error using AdminOperations: {e}", file=sys.stderr)
                    # Fall back to basic registration
                    pass
            else:
                # Fallback: Create minimal default channels
                project_id_short = project_info['project_id'][:8]
                default_channels = [
                    ('general', 'Project general discussion'),
                    ('dev', 'Development discussion')
                ]
                
                for name, description in default_channels:
                    channel_id = f"proj_{project_id_short}:{name}"
                    conn.execute("""
                        INSERT OR IGNORE INTO channels 
                        (id, project_id, scope, name, description, created_at, is_default)
                        VALUES (?, ?, 'project', ?, ?, datetime('now'), 1)
                    """, (channel_id, project_info['project_id'], name, description))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"Error registering session in database: {e}", file=sys.stderr)
        return False

def ensure_agent_mcp_tools(claude_dir: Path, agent_name: str) -> bool:
    """
    Ensure an agent has access to claude-slack MCP tools.
    
    Args:
        claude_dir: Path to .claude directory (global or project)
        agent_name: Name of the agent file (without .md)
        
    Returns:
        True if tools were added, False if already present or agent not found
    """
    agent_file = claude_dir / 'agents' / f'{agent_name}.md'
    if not agent_file.exists():
        return False
    
    # Get MCP tools from config
    slack_tools = []
    try:
        # Try to read from config first
        config_path = Path.home() / '.claude' / 'config' / 'claude-slack.config.yaml'
        if config_path.exists():
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Get tool names from config and add prefix
            tool_names = config.get('default_mcp_tools', [])
            slack_tools = [f'mcp__claude-slack__{tool}' for tool in tool_names]
    except Exception:
        pass
    
    # Fallback to hardcoded list if config read fails
    if not slack_tools:
        slack_tools = [
            'mcp__claude-slack__send_channel_message',
            'mcp__claude-slack__send_direct_message',
            'mcp__claude-slack__get_messages',
            'mcp__claude-slack__list_channels',
            'mcp__claude-slack__subscribe_to_channel',
            'mcp__claude-slack__unsubscribe_from_channel',
            'mcp__claude-slack__get_my_subscriptions',
            'mcp__claude-slack__search_messages',
            'mcp__claude-slack__get_current_project',
            'mcp__claude-slack__list_projects',
            'mcp__claude-slack__list_agents',
            'mcp__claude-slack__create_channel',
            'mcp__claude-slack__get_linked_projects'
        ]
    
    try:
        with open(agent_file, 'r') as f:
            content = f.read()
        
        if not content.startswith('---'):
            return False
        
        # Find frontmatter boundaries
        lines = content.split('\n')
        end_index = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_index = i
                break
        
        if end_index == -1:
            return False
        
        # Find tools line
        tools_line_index = -1
        tools_value = None
        for i in range(1, end_index):
            if lines[i].startswith('tools:'):
                tools_line_index = i
                tools_value = lines[i].split(':', 1)[1].strip()
                break
        
        # If no tools or "All"/"*", agent already has access
        if tools_line_index == -1 or tools_value in ['All', 'all', '"All"', "'All'", '*', '"*"', "'*'"]:
            return False
        
        # Parse existing tools
        if tools_value.startswith('[') and tools_value.endswith(']'):
            # List format: tools: [tool1, tool2]
            tools_str = tools_value[1:-1]
            existing_tools = [t.strip().strip('"').strip("'") for t in tools_str.split(',') if t.strip()]
        else:
            # Single tool or comma-separated
            existing_tools = [t.strip() for t in tools_value.split(',')]
        
        # Check if slack tools already present
        missing_tools = [tool for tool in slack_tools if tool not in existing_tools]
        
        if not missing_tools:
            return False
        
        # Add missing tools
        all_tools = existing_tools + missing_tools
        
        # Format tools line
        if len(all_tools) > 3:
            # Multi-line YAML list format
            tools_lines = ['tools:']
            for tool in all_tools:
                tools_lines.append(f'  - {tool}')
            
            # Replace old tools line with new multi-line format
            lines = lines[:tools_line_index] + tools_lines + lines[tools_line_index + 1:]
        else:
            # Single line format
            lines[tools_line_index] = f'tools: [{", ".join(all_tools)}]'
        
        # Write back
        new_content = '\n'.join(lines)
        with open(agent_file, 'w') as f:
            f.write(new_content)
        
        return True
        
    except Exception as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"Error updating agent {agent_name}: {e}", file=sys.stderr)
        return False

def ensure_agent_channel_subscriptions(claude_dir: Path, agent_name: str) -> bool:
    """
    Ensure agent has default channel subscriptions in frontmatter.
    
    Args:
        claude_dir: Path to .claude directory
        agent_name: Name of the agent file (without .md)
        
    Returns:
        True if subscriptions were added, False otherwise
    """
    agent_file = claude_dir / 'agents' / f'{agent_name}.md'
    if not agent_file.exists():
        return False
    
    try:
        with open(agent_file, 'r') as f:
            content = f.read()
        
        if not content.startswith('---'):
            return False
        
        # Find frontmatter boundaries
        lines = content.split('\n')
        end_index = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_index = i
                break
        
        if end_index == -1:
            return False
        
        # Check if channels already exist
        has_channels = False
        for i in range(1, end_index):
            if lines[i].startswith('channels:'):
                has_channels = True
                break
        
        if has_channels:
            return False
        
        # Add default channel subscriptions before the closing ---
        channel_lines = [
            'channels:',
            '  global:',
            '    - general',
            '    - announcements',
            '  project:',
            '    - dev'
        ]
        
        # Insert before the closing ---
        lines = lines[:end_index] + channel_lines + lines[end_index:]
        
        # Write back
        new_content = '\n'.join(lines)
        with open(agent_file, 'w') as f:
            f.write(new_content)
        
        return True
        
    except Exception as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"Error adding subscriptions to {agent_name}: {e}", file=sys.stderr)
        return False

def main():
    """Main hook entry point - reads JSON from stdin"""
    try:
        # Read JSON payload from stdin
        input_data = sys.stdin.read()
        if not input_data:
            return 0
        
        payload = json.loads(input_data)
        
        # Extract session information
        session_id = payload.get('session_id', '')
        cwd = payload.get('cwd', os.getcwd())
        hook_event = payload.get('hook_event_name', '')
        
        # Only process for SessionStart
        if hook_event != 'SessionStart':
            return 0
        
        # Debug logging if enabled
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            debug_file = Path.home() / '.claude' / 'logs' / 'slack_session_start.log'
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_file, 'a') as f:
                f.write(f"\n--- SessionStart Hook ---\n")
                f.write(f"Session: {session_id}\n")
                f.write(f"CWD: {cwd}\n")
        
        # Find project root from cwd
        project_path = find_project_root(cwd)
        
        # Prepare project info if in project
        project_info = None
        if project_path:
            project_info = {
                'project_id': get_project_id(project_path),
                'project_path': project_path,
                'project_name': os.path.basename(project_path)
            }
            
            if os.environ.get('CLAUDE_SLACK_DEBUG'):
                with open(debug_file, 'a') as f:
                    f.write(f"Project detected: {project_info['project_name']}\n")
                    f.write(f"Project ID: {project_info['project_id']}\n")
        
        # Register session in database
        success = register_session_in_db(session_id, project_info)
        
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            with open(debug_file, 'a') as f:
                f.write(f"Session registered: {success}\n")
        
        # Process agents to ensure they have MCP tools and subscriptions
        claude_dirs = []
        
        # Always check global agents
        global_claude = Path.home() / '.claude'
        if global_claude.exists():
            claude_dirs.append(global_claude)
        
        # Check project agents if in project
        if project_path:
            project_claude = Path(project_path) / '.claude'
            if project_claude.exists():
                claude_dirs.append(project_claude)
        
        agents_updated = 0
        for claude_dir in claude_dirs:
            agents_dir = claude_dir / 'agents'
            if not agents_dir.exists():
                continue
            
            for agent_file in agents_dir.glob('*.md'):
                agent_name = agent_file.stem
                
                # Ensure MCP tools
                tools_added = ensure_agent_mcp_tools(claude_dir, agent_name)
                
                # Ensure channel subscriptions
                subs_added = ensure_agent_channel_subscriptions(claude_dir, agent_name)
                
                if tools_added or subs_added:
                    agents_updated += 1
                    if os.environ.get('CLAUDE_SLACK_DEBUG'):
                        updates = []
                        if tools_added:
                            updates.append("tools")
                        if subs_added:
                            updates.append("subscriptions")
                        with open(debug_file, 'a') as f:
                            f.write(f"Updated {agent_name}: {', '.join(updates)}\n")
        
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            with open(debug_file, 'a') as f:
                f.write(f"Total agents updated: {agents_updated}\n")
        
        # Silent success message to stderr
        if agents_updated > 0:
            print(f"Claude-Slack: {agents_updated} agents configured", file=sys.stderr)
        
        return 0
        
    except json.JSONDecodeError as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"SessionStart: Invalid JSON input: {e}", file=sys.stderr)
        return 0
        
    except Exception as e:
        if os.environ.get('CLAUDE_SLACK_DEBUG'):
            print(f"SessionStart: Error: {e}", file=sys.stderr)
        return 0

if __name__ == '__main__':
    sys.exit(main())