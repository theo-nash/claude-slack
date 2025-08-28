#!/usr/bin/env python3
"""
slack_session_start.py - SessionStart hook using ConfigSyncManager

This hook runs at the start of every Claude Code session and uses the 
ConfigSyncManager to handle all initialization and setup tasks with
the unified membership model and reconciliation pattern.
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
    from config.sync_manager import ConfigSyncManager
    from api.unified_api import ClaudeSlackAPI
except ImportError as e:
    logger.error(f"Failed to import ConfigSyncManager: {e}")
    ConfigSyncManager = None
    ClaudeSlackAPI = None

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
        
        # Use ConfigSyncManager if available
        if (ConfigSyncManager and ClaudeSlackAPI):
            logger.info("Using ConfigSyncManager and ClaudeSlackAPI for session initialization")
            
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
            
            # Initialize the api
            api = ClaudeSlackAPI(db_path = db_path, qdrant_url=os.getenv('QDRANT_URL', 'http://localhost:6333'))
            
            # Initialize the API (required async call)
            import asyncio
            try:
                asyncio.run(api.initialize())
                logger.info("API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize API: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return 0
            
            # Initialize sync manager
            try:
                sync_manager = ConfigSyncManager(api)
            except Exception as e:
                logger.error(f"Failed to initialize ConfigSyncManager: {e}")
                return 0
            
            # Initialize the session
            try:
                results = asyncio.run(sync_manager.initialize_session(
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
            
            # Handle reconciliation results
            reconciliation = results.get('reconciliation', {})
            if reconciliation and reconciliation.get('success'):
                logger.info(f"Reconciliation completed:")
                logger.info(f"  - Project ID: {results.get('project_id', 'N/A')}")
                logger.info(f"  - Total actions: {reconciliation.get('total_actions', 0)}")
                logger.info(f"  - Executed: {reconciliation.get('executed', 0)}")
                logger.info(f"  - Failed: {reconciliation.get('failed', 0)}")
                
                # Log phase summary
                phase_summary = reconciliation.get('phase_summary', {})
                for phase, stats in phase_summary.items():
                    if stats.get('total', 0) > 0:
                        logger.info(f"  - {phase}: {stats['completed']}/{stats['total']} completed")
                
                # Silent success message to stderr (for user visibility)
                executed = reconciliation.get('executed', 0)
                if executed > 0:
                    print(f"Claude-Slack: {executed} configuration actions applied", file=sys.stderr)
            
            # Handle top-level errors
            if results.get('errors'):
                for error in results['errors']:
                    logger.error(f"Initialization error: {error}")
            
            # Summary message
            if reconciliation and reconciliation.get('success'):
                logger.info("SessionStart hook completed: reconciliation successful")
            else:
                logger.info("SessionStart hook completed with reconciliation issues")
            
        else:
            logger.warning("ConfigSyncManager not available - limited initialization")
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