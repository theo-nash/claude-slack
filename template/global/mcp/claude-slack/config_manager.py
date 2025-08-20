#!/usr/bin/env python3
"""
Configuration Manager for Claude-Slack
Handles YAML configuration for default channels and project links
"""

import os
import yaml
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import fcntl
import tempfile


class ConfigManager:
    """Manages claude-slack configuration file"""
    
    DEFAULT_CONFIG = {
        "version": "1.0",
        "default_channels": {
            "global": [
                {
                    "name": "general",
                    "description": "General discussion"
                },
                {
                    "name": "announcements", 
                    "description": "Important updates"
                },
                {
                    "name": "cross-project",
                    "description": "Cross-project coordination"
                }
            ],
            "project": [
                {
                    "name": "general",
                    "description": "Project general discussion"
                },
                {
                    "name": "dev",
                    "description": "Development discussion"
                },
                {
                    "name": "releases",
                    "description": "Release coordination"
                }
            ]
        },
        "project_links": [],
        "settings": {
            "message_retention_days": 30,
            "max_message_length": 4000,
            "auto_create_channels": True,
            "auto_link_projects": True,
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config manager
        
        Args:
            config_path: Path to config file (defaults to ~/.claude/config/claude-slack.config.yaml)
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path.home() / ".claude" / "config" / "claude-slack.config.yaml"
        
        self._config_cache = None
        self._cache_mtime = None
    
    def ensure_config_exists(self) -> bool:
        """
        Ensure configuration file exists, create with defaults if not
        
        Returns:
            True if config was created, False if already existed
        """
        if self.config_path.exists():
            return False
        
        # Create directory if needed
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write default config
        self.save_config(self.DEFAULT_CONFIG)
        return True
    
    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Load configuration from YAML file with caching
        
        Args:
            force_reload: Force reload even if cached
            
        Returns:
            Configuration dictionary
        """
        # Check if we need to reload
        if not force_reload and self._config_cache is not None:
            try:
                current_mtime = os.path.getmtime(self.config_path)
                if current_mtime == self._cache_mtime:
                    return self._config_cache
            except OSError:
                pass
        
        # Ensure config exists
        self.ensure_config_exists()
        
        # Load config
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                
            # Merge with defaults to ensure all keys exist
            config = self._merge_with_defaults(config)
            
            # Cache the config
            self._config_cache = config
            self._cache_mtime = os.path.getmtime(self.config_path)
            
            return config
            
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.DEFAULT_CONFIG.copy()
    
    def save_config(self, config: Dict[str, Any], create_backup: bool = True) -> bool:
        """
        Save configuration to YAML file atomically
        
        Args:
            config: Configuration dictionary
            create_backup: Whether to create backup before saving
            
        Returns:
            True if successful
        """
        try:
            # Create backup if requested and file exists
            if create_backup and self.config_path.exists():
                backup_path = self.config_path.with_suffix('.yaml.bak')
                shutil.copy2(self.config_path, backup_path)
            
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=self.config_path.parent,
                suffix='.tmp',
                delete=False
            ) as tmp_file:
                yaml.dump(config, tmp_file, default_flow_style=False, sort_keys=False)
                tmp_path = tmp_file.name
            
            # Atomic rename
            os.replace(tmp_path, self.config_path)
            
            # Clear cache
            self._config_cache = None
            self._cache_mtime = None
            
            return True
            
        except Exception as e:
            print(f"Error saving config: {e}")
            # Clean up temp file if it exists
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False
    
    def get_default_channels(self, scope: str = "all") -> Dict[str, List[Dict]]:
        """
        Get default channels configuration
        
        Args:
            scope: "global", "project", or "all"
            
        Returns:
            Dictionary of channel configurations
        """
        config = self.load_config()
        channels = config.get("default_channels", {})
        
        if scope == "global":
            return {"global": channels.get("global", [])}
        elif scope == "project":
            return {"project": channels.get("project", [])}
        else:
            return channels
    
    def get_project_links(self) -> List[Dict]:
        """
        Get all project links from configuration
        
        Returns:
            List of project link configurations
        """
        config = self.load_config()
        return config.get("project_links", [])
    
    # Note: Business logic methods (add_project_link, remove_project_link, etc.)
    # have been moved to admin_operations.py for centralized management.
    # This class now focuses solely on YAML file operations.
    
    # Link analysis methods moved to admin_operations.py
    # Use AdminOperations.get_linked_projects() instead
    
    def get_settings(self) -> Dict[str, Any]:
        """
        Get general settings from configuration
        
        Returns:
            Settings dictionary
        """
        config = self.load_config()
        return config.get("settings", {})
    
    def update_setting(self, key: str, value: Any) -> bool:
        """
        Update a specific setting
        
        Args:
            key: Setting key
            value: New value
            
        Returns:
            True if successful
        """
        config = self.load_config()
        config.setdefault("settings", {})[key] = value
        return self.save_config(config)
    
    def _merge_with_defaults(self, config: Dict) -> Dict:
        """
        Merge loaded config with defaults to ensure all keys exist
        
        Args:
            config: Loaded configuration
            
        Returns:
            Merged configuration
        """
        import copy
        
        # Deep copy defaults
        merged = copy.deepcopy(self.DEFAULT_CONFIG)
        
        # Update with loaded values
        if "version" in config:
            merged["version"] = config["version"]
        
        if "default_channels" in config:
            merged["default_channels"] = config["default_channels"]
        
        if "project_links" in config:
            merged["project_links"] = config["project_links"]
        
        if "settings" in config:
            merged["settings"].update(config["settings"])
        
        return merged
    
    def validate_config(self) -> tuple[bool, List[str]]:
        """
        Validate configuration structure
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            config = self.load_config()
            
            # Check version
            if "version" not in config:
                errors.append("Missing 'version' field")
            
            # Check default_channels structure
            if "default_channels" not in config:
                errors.append("Missing 'default_channels' field")
            else:
                channels = config["default_channels"]
                if "global" not in channels:
                    errors.append("Missing 'default_channels.global'")
                elif not isinstance(channels["global"], list):
                    errors.append("'default_channels.global' must be a list")
                    
                if "project" not in channels:
                    errors.append("Missing 'default_channels.project'")
                elif not isinstance(channels["project"], list):
                    errors.append("'default_channels.project' must be a list")
            
            # Check project_links structure
            if "project_links" in config:
                if not isinstance(config["project_links"], list):
                    errors.append("'project_links' must be a list")
                else:
                    for i, link in enumerate(config["project_links"]):
                        if "source" not in link:
                            errors.append(f"Link {i}: missing 'source'")
                        if "target" not in link:
                            errors.append(f"Link {i}: missing 'target'")
                        if "type" not in link:
                            errors.append(f"Link {i}: missing 'type'")
            
            # Check settings structure
            if "settings" not in config:
                errors.append("Missing 'settings' field")
            elif not isinstance(config["settings"], dict):
                errors.append("'settings' must be a dictionary")
            
        except Exception as e:
            errors.append(f"Failed to load config: {str(e)}")
        
        return (len(errors) == 0, errors)


# Convenience functions for use in other modules
_default_manager = None

def get_config_manager() -> ConfigManager:
    """Get the default config manager instance"""
    global _default_manager
    if _default_manager is None:
        _default_manager = ConfigManager()
    return _default_manager

def load_config() -> Dict[str, Any]:
    """Load configuration using default manager"""
    return get_config_manager().load_config()

def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration using default manager"""
    return get_config_manager().save_config(config)

def get_default_channels(scope: str = "all") -> Dict[str, List[Dict]]:
    """Get default channels from configuration"""
    return get_config_manager().get_default_channels(scope)

def get_project_links() -> List[Dict]:
    """Get project links from configuration"""
    return get_config_manager().get_project_links()