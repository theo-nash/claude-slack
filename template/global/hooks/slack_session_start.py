#!/usr/bin/env python3
"""
slack_session_start.py - Simplified SessionStart hook using ProjectSetupManager

This hook runs at the start of every Claude Code session and uses the 
ProjectSetupManager to handle all initialization and setup tasks.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Add MCP directory to path to import modules
claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude'))
claude_slack_dir = os.path.join(claude_config_dir, 'claude-slack')
mcp_dir = os.path.join(claude_slack_dir, 'mcp')
sys.path.insert(0, mcp_dir)
sys.path.insert(0, os.path.join(claude_slack_dir, 'hooks'))

# Set up logging - use new centralized logging system
try:
    from log_manager.manager import get_logger
    logger = get_logger('session_start', component='hook')
    
    def log_json_data(logger, message, data, level=logging.DEBUG):
        """Log data as JSON for structured logging"""
        logger.log(level, f"{message}: {json.dumps(data, default=str)}")
        
except ImportError:
    # Fallback to null logging if system not available
    import logging
    logger = logging.getLogger('SessionStart')
    logger.addHandler(logging.NullHandler())
    def log_json_data(l, m, d, level=None): pass

try:
    from projects.setup_manager import ProjectSetupManager
except ImportError as e:
    logger.error(f"Failed to import ProjectSetupManager: {e}")
    ProjectSetupManager = None

try:
    from environment_config import env_config
    USE_ENV_CONFIG = True
except ImportError:
    USE_ENV_CONFIG = False


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
        logger.debug("--- SessionStart Hook Processing ---")
        
        # Use ProjectSetupManager if available
        if ProjectSetupManager:
            logger.info("Using ProjectSetupManager for session initialization")
            
            # Database path
            if USE_ENV_CONFIG:
                try:
                    db_path = env_config.db_path
                except Exception as e:
                    logger.warning(f"Failed to get db_path from env_config: {e}")
                    db_path = Path(claude_slack_dir) / 'data' / 'claude-slack.db'
            else:
                db_path = Path(claude_slack_dir) / 'data' / 'claude-slack.db'
            
            # Ensure database directory exists
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize setup manager
            try:
                setup_manager = ProjectSetupManager(str(db_path))
            except Exception as e:
                logger.error(f"Failed to initialize ProjectSetupManager: {e}")
                return 0
            
            # Initialize the session
            import asyncio
            try:
                results = asyncio.run(setup_manager.initialize_session(
                    session_id=session_id,
                    cwd=cwd,
                    transcript_path=transcript_path
                ))
            except Exception as e:
                logger.error(f"Failed to initialize session: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return 0
            
            # Check if we got valid results
            if not results:
                logger.warning("No results returned from session initialization")
                return 0
            
            # Log results
            if results.get('session_registered'):
                logger.info("Session registered successfully")
            
            # Handle project setup results (now a dict)
            project_setup = results.get('project_setup_performed', {})
            if project_setup:
                logger.info(f"Project setup completed:")
                logger.info(f"  - Project ID: {results.get('project_id', 'N/A')}")
                logger.info(f"  - Channels created: {len(project_setup.get('channels_created', []))}")
                logger.info(f"  - Agents registered: {len(project_setup.get('agents_registered', []))}")
                
                # Log any project setup errors
                if project_setup.get('errors'):
                    for error in project_setup['errors']:
                        logger.warning(f"Project setup warning: {error}")
                
                # Silent success message to stderr (for user visibility)
                agents_count = len(project_setup.get('agents_registered', []))
                if agents_count > 0:
                    print(f"Claude-Slack: {agents_count} project agents configured", file=sys.stderr)
            
            # Handle global setup results (now a dict)
            global_setup = results.get('global_setup_performed', {})
            if global_setup:
                logger.info(f"Global environment setup completed:")
                logger.info(f"  - Global channels created: {len(global_setup.get('channels_created', []))}")
                logger.info(f"  - Global agents registered: {len(global_setup.get('agents_registered', []))}")
                
                # Log any global setup errors
                if global_setup.get('errors'):
                    for error in global_setup['errors']:
                        logger.warning(f"Global setup warning: {error}")
                
                # Report global agents if any
                global_agents_count = len(global_setup.get('agents_registered', []))
                if global_agents_count > 0:
                    logger.info(f"Configured {global_agents_count} global agents")
            
            # Handle top-level errors
            if results.get('errors'):
                for error in results['errors']:
                    logger.error(f"Initialization error: {error}")
            
            # Summary message
            total_agents = 0
            project_setup = results.get('project_setup_performed', {})
            global_setup = results.get('global_setup_performed', {})
            
            if project_setup:
                total_agents += len(project_setup.get('agents_registered', []))
            if global_setup:
                total_agents += len(global_setup.get('agents_registered', []))
            
            if total_agents > 0:
                logger.info(f"SessionStart hook completed: {total_agents} total agents configured")
            else:
                logger.info("SessionStart hook completed successfully")
            
        else:
            logger.warning("ProjectSetupManager not available - limited initialization")
            # Could fall back to basic session registration here if needed
        
        return 0
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        return 0
        
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return 0


if __name__ == '__main__':
    sys.exit(main())