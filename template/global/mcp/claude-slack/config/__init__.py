"""
Configuration management package for Claude-Slack

This package contains:
- config_manager: YAML configuration loading and management
- reconciliation: Reconciliation plan builder for config sync
- sync_manager: Configuration synchronization manager
"""

from .sync_manager import ConfigSyncManager
from .reconciliation import ReconciliationPlan
from .config_manager import ConfigManager, get_config_manager

__all__ = ['ConfigSyncManager', 'ReconciliationPlan', "ConfigManager", 'get_config_manager']