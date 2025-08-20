#!/usr/bin/env python3
"""
Centralized Logging Manager for Claude-Slack

Provides file-only logging to avoid interfering with agent messaging.
All output goes to log files in ~/.claude/logs/claude-slack/
"""

import os
import sys
import logging
import logging.handlers
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


class LoggingManager:
    """
    Manages file-based logging for all Claude-Slack components.
    
    Features:
    - File-only output (no console interference)
    - Structured JSON logging for analysis
    - Component-specific log files
    - Automatic rotation and compression
    - Debug mode support via CLAUDE_SLACK_DEBUG
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the logging manager (singleton)"""
        if not self._initialized:
            self.claude_dir = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude'))
            self.log_dir = self.claude_dir / 'logs' / 'claude-slack'
            self.debug_mode = os.environ.get('CLAUDE_SLACK_DEBUG', '').lower() in ('1', 'true', 'yes')
            self.loggers = {}
            self._initialized = True
            
            # Ensure log directories exist
            self._ensure_log_directories()
            
            # Configure root logger to prevent any console output
            self._configure_root_logger()
    
    def _ensure_log_directories(self):
        """Create necessary log directories"""
        directories = [
            self.log_dir,
            self.log_dir / 'hooks',
            self.log_dir / 'managers',
            self.log_dir / 'archive'
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _configure_root_logger(self):
        """Configure the root logger to prevent console output"""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if self.debug_mode else logging.INFO)
        
        # Remove all existing handlers (especially console handlers)
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Add null handler to prevent any output
        root_logger.addHandler(logging.NullHandler())
    
    def get_logger(self, name: str, component: Optional[str] = None) -> logging.Logger:
        """
        Get or create a logger for a specific component.
        
        Args:
            name: Logger name (e.g., 'SessionManager')
            component: Component category ('manager', 'hook', None for main)
            
        Returns:
            Configured logger instance
        """
        logger_key = f"{component}.{name}" if component else name
        
        if logger_key in self.loggers:
            return self.loggers[logger_key]
        
        # Create new logger
        logger = logging.getLogger(f"claude-slack.{logger_key}")
        logger.setLevel(logging.DEBUG if self.debug_mode else logging.INFO)
        
        # Remove any inherited handlers
        logger.handlers = []
        logger.propagate = False
        
        # Determine log file path
        if component == 'hook':
            log_file = self.log_dir / 'hooks' / f"{name.lower()}.log"
        elif component == 'manager':
            log_file = self.log_dir / 'managers' / f"{name.lower()}.log"
        else:
            log_file = self.log_dir / f"{name.lower()}.log"
        
        # Add file handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        
        # Set formatter based on mode
        if self.debug_mode:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Add debug handler if in debug mode
        if self.debug_mode:
            debug_file = self.log_dir / 'debug.log'
            debug_handler = logging.handlers.RotatingFileHandler(
                debug_file,
                maxBytes=50 * 1024 * 1024,  # 50MB for debug
                backupCount=3,
                encoding='utf-8'
            )
            debug_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S.%f'
            )
            debug_handler.setFormatter(debug_formatter)
            debug_handler.setLevel(logging.DEBUG)
            logger.addHandler(debug_handler)
        
        # Add error-only handler
        error_file = self.log_dir / 'error.log'
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d]\n%(message)s\n',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)
        error_handler.setLevel(logging.ERROR)
        logger.addHandler(error_handler)
        
        # Cache and return
        self.loggers[logger_key] = logger
        return logger
    
    def log_with_context(self, logger: logging.Logger, level: int, message: str, 
                         context: Optional[Dict[str, Any]] = None):
        """
        Log a message with additional context.
        
        Args:
            logger: Logger instance
            level: Log level
            message: Log message
            context: Additional context dict
        """
        if context:
            # Format context as JSON for structured logging
            context_str = json.dumps(context, default=str)
            full_message = f"{message} | Context: {context_str}"
        else:
            full_message = message
        
        logger.log(level, full_message)
    
    def cleanup_old_logs(self, days: int = 7):
        """
        Clean up log files older than specified days.
        
        Args:
            days: Number of days to keep logs
        """
        import time
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        for log_file in self.log_dir.rglob('*.log*'):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                except Exception:
                    pass  # Ignore errors during cleanup


# Singleton instance
_logging_manager = None


def get_logging_manager() -> LoggingManager:
    """Get the singleton LoggingManager instance"""
    global _logging_manager
    if _logging_manager is None:
        _logging_manager = LoggingManager()
    return _logging_manager


def get_logger(name: str, component: Optional[str] = None) -> logging.Logger:
    """
    Convenience function to get a logger.
    
    Args:
        name: Logger name
        component: Component type ('manager', 'hook', or None)
        
    Returns:
        Configured logger
    """
    manager = get_logging_manager()
    return manager.get_logger(name, component)


def configure_logging():
    """Initialize logging system (called once at startup)"""
    manager = get_logging_manager()
    # This ensures the manager is initialized
    return manager


# Prevent any default logging to console
logging.getLogger().addHandler(logging.NullHandler())