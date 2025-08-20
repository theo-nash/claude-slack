"""
Logging Package for Claude-Slack

Provides centralized file-only logging to avoid interfering with agent messaging.
All logs are written to ~/.claude/logs/claude-slack/
"""

from .manager import LoggingManager, get_logger, configure_logging, get_logging_manager

__all__ = ['LoggingManager', 'get_logger', 'configure_logging', 'get_logging_manager']