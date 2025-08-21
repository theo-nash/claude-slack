#!/usr/bin/env python3
"""
slack_session_start.py - MUST BE INSTALLED GLOBALLY in Claude hooks directory
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
    from admin_operations import AdminOperations
except ImportError:
    AdminOperations = None

try:
    from subscriptions.manager import SubscriptionManager
except ImportError:
    SubscriptionManager = None

try:
    from sessions.manager import SessionManager
except ImportError:
    SessionManager = None
    
try:
    from environment_config import env_config
    USE_ENV_CONFIG = True
except ImportError:
    # Fallback if environment_config not available yet
    USE_ENV_CONFIG = False

# Set up logging - use new centralized logging system
try:
    from log_manager.manager import get_logger
    logger = get_logger('session_start', component='hook')
    
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
    logger = logging.getLogger('SessionStart')
    logger.addHandler(logging.NullHandler())
    log_json_data = lambda l, m, d, level=None: pass
    log_db_result = lambda l, o, s, d=None: pass

def get_project_id(project_path: str) -> str:
    """
    Generate consistent project ID from path
    
    Args:
        project_path: Absolute path to project root
        
    Returns:
        32-character project ID
    """
    return hashlib.sha256(project_path.encode()).hexdigest()[:32]

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

def register_session_in_db(session_id: str, project_info: Optional[Dict[str, str]]) -> bool:
    """
    Register session in SQLite database at session start.
    
    Args:
        session_id: Current session ID
        project_info: Dict with project_id, project_path, project_name, transcript_path or None
        
    Returns:
        True if successful
    """
    try:
        logger.debug(f"Registering session: {session_id}")
        if project_info:
            log_json_data(logger, "Project info", project_info)
        # Database path - use environment config if available
        if USE_ENV_CONFIG:
            db_path = env_config.db_path
        else:
            db_path = Path(claude_config_dir) / 'data' / 'claude-slack.db'
        
        logger.debug(f"Using database: {db_path}")
        
        # Ensure database directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use the connection helper for proper connection management
        with connect(db_path, writer=True) as conn:
            # First, register project if we have one (required for foreign key constraint)
            if project_info and project_info.get('project_id'):
                logger.debug(f"Registering project: {project_info['project_name']}")
                
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO projects (id, path, name, created_at, last_active)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """, (
                    project_info['project_id'],
                    project_info['project_path'],
                    project_info['project_name']
                ))
                
                if cursor.rowcount > 0:
                    logger.info(f"Created new project: {project_info['project_name']}")
                
                # Update last_active if project already exists
                cursor = conn.execute("""
                    UPDATE projects 
                    SET last_active = datetime('now')
                    WHERE id = ?
                """, (project_info['project_id'],))
                
                if cursor.rowcount > 0:
                    logger.debug(f"Updated project last_active for: {project_info['project_name']}")
            
            # Now insert or update session context (after project exists)
            cursor = conn.execute("""
                INSERT OR REPLACE INTO sessions 
                (id, project_id, project_path, project_name, transcript_path, scope, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                session_id,
                project_info.get('project_id') if project_info else None,
                project_info.get('project_path') if project_info else None,
                project_info.get('project_name') if project_info else None,
                project_info.get('transcript_path') if project_info else None,
                'project' if project_info and project_info.get('project_id') else 'global'
            ))
            
            logger.debug(f"Session {'updated' if cursor.rowcount > 0 else 'inserted'}")
            
            # Register the default "assistant" agent for every session
            cursor = conn.execute("""
                INSERT OR IGNORE INTO agents (name, project_id, description, status, last_active)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (
                'assistant',
                project_info.get('project_id') if project_info else None,
                'Default Claude Code assistant agent',
                'online'
            ))
            
            if cursor.rowcount > 0:
                logger.debug("Registered default 'assistant' agent")
            
            # Handle advanced project setup if available
            if project_info and project_info.get('project_id'):
                # Use AdminOperations to handle all registration and channel creation
                if AdminOperations is not None:
                    try:
                        logger.debug("Using AdminOperations for project setup")
                        
                        # Initialize admin operations
                        import asyncio
                        admin_ops = AdminOperations()
                        
                        # Register project and create channels
                        logger.debug(f"Registering project via AdminOps: {project_info['project_path']}")
                        asyncio.run(admin_ops.register_project(
                            project_info['project_path'],
                            project_info['project_name']
                        ))
                        
                        # Create global channels
                        logger.debug("Creating default global channels")
                        asyncio.run(admin_ops.create_default_channels())
                        
                        # Sync project links from config
                        logger.debug("Syncing project links from config")
                        asyncio.run(admin_ops.sync_project_links_from_config())
                        
                        logger.info("AdminOperations setup completed successfully")
                        
                    except Exception as e:
                        logger.warning(f"AdminOperations error (falling back): {e}")
                        logger.debug(f"AdminOps traceback:\n{traceback.format_exc()}")
                        # Fall back to basic registration
                        pass
                else:
                    # Fallback: Create minimal default channels
                    logger.debug("AdminOperations not available, using fallback channel creation")
                    project_id_short = project_info['project_id'][:8]
                    default_channels = [
                        ('general', 'Project general discussion'),
                        ('dev', 'Development discussion')
                    ]
                    
                    for name, description in default_channels:
                        channel_id = f"proj_{project_id_short}:{name}"
                        cursor = conn.execute("""
                            INSERT OR IGNORE INTO channels 
                            (id, project_id, scope, name, description, created_at, is_default)
                            VALUES (?, ?, 'project', ?, ?, datetime('now'), 1)
                        """, (channel_id, project_info['project_id'], name, description))
                        
                        if cursor.rowcount > 0:
                            logger.debug(f"Created channel: {channel_id}")
        
        log_db_result(logger, 'register_session', True, {
            'session_id': session_id,
            'scope': 'project' if project_info and project_info.get('project_id') else 'global'
        })
        return True
        
    except sqlite3.OperationalError as e:
        logger.warning(f"Database operational error: {e}")
        log_db_result(logger, 'register_session', False, {'error': str(e)})
        return False
        
    except Exception as e:
        logger.error(f"Error registering session: {e}\n{traceback.format_exc()}")
        log_db_result(logger, 'register_session', False, {'error': str(e)})
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
        if USE_ENV_CONFIG:
            config_path = env_config.config_path
        else:
            config_path = Path(claude_config_dir) / 'config' / 'claude-slack.config.yaml'
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
        
        logger.info(f"Successfully updated agent {agent_name} with MCP tools")
        return True
        
    except Exception as e:
        logger.error(f"Error updating agent {agent_name}: {e}\n{traceback.format_exc()}")
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
        logger.debug(f"Agent file not found: {agent_file}")
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
        
        logger.info(f"Added default channel subscriptions to agent: {agent_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding subscriptions to {agent_name}: {e}\n{traceback.format_exc()}")
        return False

def sync_agent_subscriptions_to_db(session_id: str, project_info: Optional[Dict[str, str]]) -> bool:
    """
    Sync agent channel subscriptions from frontmatter to database using SubscriptionManager.
    
    This reads all agent files and syncs their channel subscriptions to the 
    subscriptions table, which becomes the source of truth for queries.
    
    Args:
        session_id: Current session ID
        project_info: Dict with project_id, project_path, project_name or None
        
    Returns:
        True if successful
    """
    try:
        logger.info("Starting sync of agent subscriptions to database using SubscriptionManager")
        
        if not SubscriptionManager:
            logger.warning("SubscriptionManager not available, falling back to basic sync")
            return False
        
        # Database path
        if USE_ENV_CONFIG:
            db_path = env_config.db_path
        else:
            db_path = Path(claude_config_dir) / 'data' / 'claude-slack.db'
        
        # Initialize subscription manager
        subscription_manager = SubscriptionManager(str(db_path))
        
        # Determine which directories to scan
        claude_dirs = []
        agents_synced = 0
        
        # Always check global agents
        if USE_ENV_CONFIG:
            global_claude = env_config.global_claude_dir
        else:
            global_claude = Path(claude_config_dir)
        if global_claude.exists():
            claude_dirs.append((global_claude, None))  # None for global project_id
    
        # Check project agents if in project
        if project_info and project_info.get('project_path'):
            project_claude = Path(project_info['project_path']) / '.claude'
            if project_claude.exists():
                claude_dirs.append((project_claude, project_info['project_id']))
    
        # Process each directory
        for claude_dir, context_project_id in claude_dirs:
            agents_dir = claude_dir / 'agents'
            if not agents_dir.exists():
                logger.debug(f"Agents directory not found: {agents_dir}")
                continue
        
            logger.debug(f"Processing agents in: {agents_dir}")
            
            for agent_file in agents_dir.glob('*.md'):
                agent_name = agent_file.stem
                logger.debug(f"Processing agent: {agent_name}")
            
                # Use SubscriptionManager to sync from frontmatter
                try:
                    import asyncio
                    
                    # First sync from frontmatter
                    success = asyncio.run(subscription_manager.sync_from_frontmatter(
                        agent_name, context_project_id, str(agent_file)
                    ))
                    
                    if success:
                        agents_synced += 1
                        logger.debug(f"Successfully synced subscriptions for {agent_name}")
                        
                        # Check if agent has any subscriptions, if not apply defaults
                        subs = asyncio.run(subscription_manager.get_subscriptions(agent_name, context_project_id))
                        if not subs['global'] and not subs['project']:
                            logger.info(f"No subscriptions found for {agent_name}, applying defaults")
                            applied = asyncio.run(subscription_manager.apply_default_subscriptions(
                                agent_name, context_project_id, force=False
                            ))
                            if applied['global'] or applied['project']:
                                logger.info(f"Applied default subscriptions for {agent_name}: {applied}")
                    else:
                        logger.warning(f"Failed to sync subscriptions for {agent_name}")
                
                except Exception as e:
                    logger.warning(f"Error syncing subscriptions for {agent_name}: {e}")
                    logger.debug(f"Sync error traceback:\n{traceback.format_exc()}")
                    continue
    
        logger.info(f"Sync complete: {agents_synced} agents processed")
        log_db_result(logger, 'sync_subscriptions', True, {
            'agents_synced': agents_synced
        })
        return True
        
    except Exception as e:
        logger.error(f"Error syncing subscriptions to database: {e}\n{traceback.format_exc()}")
        log_db_result(logger, 'sync_subscriptions', False, {'error': str(e)})
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
        
        # Extract session information
        session_id = payload.get('session_id', '')
        cwd = payload.get('cwd', os.getcwd())
        hook_event = payload.get('hook_event_name', '')
        transcript_path = payload.get('transcript_path', '')
        
        # Only process for SessionStart
        if hook_event != 'SessionStart':
            logger.debug(f"Ignoring non-SessionStart event: {hook_event}")
            return 0
        
        logger.info(f"SessionStart Hook: session={session_id}, cwd={cwd}")
        logger.debug(f"Transcript: {transcript_path}")
        logger.debug("--- SessionStart Hook Processing ---")
        
        # Find project root from cwd or environment
        project_path = os.environ.get('CLAUDE_PROJECT_DIR')
        if not project_path and cwd:
            # Use cwd as project path if CLAUDE_PROJECT_DIR not set
            # This assumes we're in a project directory
            project_path = cwd
            logger.debug(f"Using cwd as project path: {project_path}")
        elif project_path:
            logger.debug(f"Using CLAUDE_PROJECT_DIR: {project_path}")
        
        # Prepare project info - always include transcript_path
        project_info = None
        if project_path:
            project_info = {
                'project_id': get_project_id(project_path),
                'project_path': project_path,
                'project_name': os.path.basename(project_path),
                'transcript_path': transcript_path if transcript_path else None,
            }
            
            logger.info(f"Project detected: {project_info['project_name']} (ID: {project_info['project_id'][:8]}...)")
            logger.debug(f"Full project ID: {project_info['project_id']}")
            logger.debug(f"Transcript path: {project_info.get('transcript_path', 'None')}")
        else:
            # Even for global sessions, we want to store the transcript path
            project_info = {
                'transcript_path': transcript_path if transcript_path else None,
            }
            logger.info("No project detected, running in global context")
        
        # Register session in database
        logger.info("Registering session in database")
        success = register_session_in_db(session_id, project_info)
        
        if success:
            logger.info("Session registered successfully")
        else:
            logger.warning("Failed to register session")
        
        # Sync agent subscriptions to database
        logger.info("Starting agent subscription sync")
        sync_success = sync_agent_subscriptions_to_db(session_id, project_info)
        
        if sync_success:
            logger.info("Agent subscriptions synced successfully")
        else:
            logger.warning("Failed to sync agent subscriptions")
        
        # Process agents to ensure they have MCP tools and subscriptions
        logger.info("Processing agents for MCP tools and channel subscriptions")
        claude_dirs = []
        
        # Always check global agents
        if USE_ENV_CONFIG:
            global_claude = env_config.global_claude_dir
        else:
            global_claude = Path(claude_config_dir)
        if global_claude.exists():
            claude_dirs.append(global_claude)
        
        # Check project agents if in project
        if project_path:
            project_claude = Path(project_path) / '.claude'
            if project_claude.exists():
                claude_dirs.append(project_claude)
        
        agents_updated = 0
        tools_added_count = 0
        subs_added_count = 0
        
        for claude_dir in claude_dirs:
            agents_dir = claude_dir / 'agents'
            if not agents_dir.exists():
                logger.debug(f"No agents directory at: {agents_dir}")
                continue
            
            logger.debug(f"Processing agents in: {agents_dir}")
            
            for agent_file in agents_dir.glob('*.md'):
                agent_name = agent_file.stem
                logger.debug(f"Processing agent: {agent_name}")
                
                # Ensure MCP tools
                tools_added = ensure_agent_mcp_tools(claude_dir, agent_name)
                if tools_added:
                    tools_added_count += 1
                    logger.info(f"Added MCP tools to agent: {agent_name}")
                
                # Ensure channel subscriptions
                subs_added = ensure_agent_channel_subscriptions(claude_dir, agent_name)
                if subs_added:
                    subs_added_count += 1
                    logger.info(f"Added channel subscriptions to agent: {agent_name}")
                
                if tools_added or subs_added:
                    agents_updated += 1
                    updates = []
                    if tools_added:
                        updates.append("tools")
                    if subs_added:
                        updates.append("subscriptions")
                    logger.debug(f"Updated {agent_name}: {', '.join(updates)}")
        
        if agents_updated > 0:
            logger.info(f"Agent processing complete: {agents_updated} agents updated ({tools_added_count} tools, {subs_added_count} subscriptions)")
            logger.debug(f"Total agents updated: {agents_updated}")
            logger.debug(f"Tools added: {tools_added_count}")
            logger.debug(f"Subscriptions added: {subs_added_count}")
            # Silent success message to stderr (for user visibility)
            print(f"Claude-Slack: {agents_updated} agents configured", file=sys.stderr)
        else:
            logger.debug("No agents needed updates")
        
        logger.info("SessionStart hook completed successfully")
        return 0
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        logger.debug(f"Raw input: {input_data[:500]}...")  # Log first 500 chars
        return 0
        
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}\n{traceback.format_exc()}")
        return 0

if __name__ == '__main__':
    sys.exit(main())