#!/usr/bin/env python3
"""
Centralized Environment Configuration for Claude-Slack
Handles all Claude Code environment variables and path resolution

This module provides a single source of truth for:
- CLAUDE_CONFIG_DIR: Custom configuration directory (instead of ~/.claude)
- CLAUDE_PROJECT_DIR: Explicit project directory from Claude Code
- CLAUDE_WORKING_DIR: Workspace directory for multi-repo setups
- Path resolution that respects these environment variables
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from functools import lru_cache
from datetime import datetime, timedelta


class EnvironmentConfig:
    """
    Centralized configuration manager that respects Claude Code environment variables.
    
    This class provides:
    - Automatic detection of Claude Code environment variables
    - Robust project detection with multiple strategies
    - Centralized path resolution
    - Caching for performance
    """
    
    # Cache duration for project detection results
    CACHE_TTL_SECONDS = 300  # 5 minutes
    
    def __init__(self):
        """Initialize the environment configuration manager"""
        self._project_cache = {}
        self._cache_timestamps = {}
        
    # ============================================================================
    # Core Environment Variable Access
    # ============================================================================
    
    @property
    def claude_config_dir(self) -> Path:
        """
        Get Claude configuration directory, respecting CLAUDE_CONFIG_DIR.
        
        Returns:
            Path to Claude configuration directory (defaults to ~/.claude)
        """
        config_dir = os.environ.get('CLAUDE_CONFIG_DIR')
        if config_dir:
            return Path(config_dir).expanduser().resolve()
        return Path.home() / '.claude'
    
    @property
    def claude_project_dir(self) -> Optional[Path]:
        """
        Get explicit project directory from CLAUDE_PROJECT_DIR environment variable.
        
        This is set by Claude Code when executing hooks and represents the
        absolute path to the project root directory.
        
        Returns:
            Path to project directory or None if not set
        """
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR')
        if project_dir:
            return Path(project_dir).resolve()
        return None
    
    @property
    def claude_working_dir(self) -> Optional[Path]:
        """
        Get workspace directory from CLAUDE_WORKING_DIR environment variable.
        
        This is used for multi-repository workspaces.
        
        Returns:
            Path to workspace directory or None if not set
        """
        working_dir = os.environ.get('CLAUDE_WORKING_DIR')
        if working_dir:
            return Path(working_dir).resolve()
        return None
    
    # ============================================================================
    # Path Resolution (respecting CLAUDE_CONFIG_DIR)
    # ============================================================================
    
    @property
    def global_claude_dir(self) -> Path:
        """Get the global Claude directory (alias for claude_config_dir)"""
        return self.claude_config_dir
    
    @property
    def db_path(self) -> Path:
        """Get path to the claude-slack database"""
        return self.global_claude_dir / 'data' / 'claude-slack.db'
    
    @property
    def config_path(self) -> Path:
        """Get path to the claude-slack configuration file"""
        return self.global_claude_dir / 'config' / 'claude-slack.config.yaml'
    
    @property
    def mcp_dir(self) -> Path:
        """Get path to the MCP server directory"""
        return self.global_claude_dir / 'mcp' / 'claude-slack'
    
    @property
    def global_agents_dir(self) -> Path:
        """Get path to global agents directory"""
        return self.global_claude_dir / 'agents'
    
    @property
    def logs_dir(self) -> Path:
        """Get path to logs directory"""
        return self.global_claude_dir / 'logs'
    
    @property
    def sessions_dir(self) -> Path:
        """Get path to sessions directory"""
        return self.global_claude_dir / 'data' / 'claude-slack-sessions'
    
    @property
    def hooks_dir(self) -> Path:
        """Get path to global hooks directory"""
        return self.global_claude_dir / 'hooks'
    
    @property
    def scripts_dir(self) -> Path:
        """Get path to global scripts directory"""
        return self.global_claude_dir / 'scripts'
    
    # ============================================================================
    # Project Detection with Multiple Strategies
    # ============================================================================
    
    def find_project_root(self, working_dir: Optional[str] = None) -> Optional[Path]:
        """
        Find project root using multiple strategies in order of reliability.
        
        Strategies (in order):
        1. CLAUDE_PROJECT_DIR environment variable (most reliable)
        2. Working directory walk-up to find .claude directory
        3. CLAUDE_WORKING_DIR scan for projects (workspace mode)
        
        Args:
            working_dir: Starting directory for search (defaults to cwd)
            
        Returns:
            Path to project root or None if no project found
        """
        # Strategy 1: Check CLAUDE_PROJECT_DIR (most reliable)
        if project_dir := self.claude_project_dir:
            if self._validate_project_directory(project_dir):
                return project_dir
        
        # Strategy 2: Walk up from working directory
        start_dir = Path(working_dir).resolve() if working_dir else Path.cwd()
        if found_project := self._walk_up_for_project(start_dir):
            return found_project
        
        # Strategy 3: Check workspace for projects
        if workspace_dir := self.claude_working_dir:
            projects = self._find_projects_in_workspace(workspace_dir)
            # If we're inside one of the workspace projects, return it
            for project in projects:
                try:
                    start_dir.relative_to(project)
                    return project
                except ValueError:
                    continue
        
        return None
    
    def _validate_project_directory(self, path: Path) -> bool:
        """
        Validate that a directory is a valid Claude Code project.
        
        Args:
            path: Directory to validate
            
        Returns:
            True if valid Claude Code project directory
        """
        if not path.exists():
            return False
        
        claude_dir = path / '.claude'
        if not claude_dir.exists() or not claude_dir.is_dir():
            return False
        
        # Check for common Claude project indicators
        # At minimum, should have .claude directory
        # Optionally check for settings files or agents directory
        return True
    
    def _walk_up_for_project(self, start_dir: Path) -> Optional[Path]:
        """
        Walk up directory tree to find .claude directory.
        
        Args:
            start_dir: Starting directory for search
            
        Returns:
            Path to project root or None
        """
        current = start_dir
        
        # Check cache first
        cache_key = str(start_dir)
        if cache_key in self._project_cache:
            cached_time = self._cache_timestamps.get(cache_key, 0)
            if (datetime.now().timestamp() - cached_time) < self.CACHE_TTL_SECONDS:
                return self._project_cache[cache_key]
        
        # Walk up directory tree
        while current != current.parent:
            if (current / '.claude').exists():
                if self._validate_project_directory(current):
                    # Cache the result
                    self._project_cache[cache_key] = current
                    self._cache_timestamps[cache_key] = datetime.now().timestamp()
                    return current
            current = current.parent
        
        # Cache negative result too
        self._project_cache[cache_key] = None
        self._cache_timestamps[cache_key] = datetime.now().timestamp()
        return None
    
    def _find_projects_in_workspace(self, workspace: Path) -> List[Path]:
        """
        Find all Claude Code projects in a workspace directory.
        
        Args:
            workspace: Workspace directory to search
            
        Returns:
            List of project root paths
        """
        projects = []
        
        # Don't recurse too deep (max 3 levels)
        max_depth = 3
        
        for root, dirs, _ in os.walk(workspace):
            depth = len(Path(root).relative_to(workspace).parts)
            if depth > max_depth:
                dirs.clear()  # Don't recurse deeper
                continue
            
            if '.claude' in dirs:
                project_path = Path(root)
                if self._validate_project_directory(project_path):
                    projects.append(project_path)
                    # Don't search inside projects
                    dirs.remove('.claude')
        
        return projects
    
    # ============================================================================
    # Project Information
    # ============================================================================
    
    def get_project_info(self, project_path: Optional[Path] = None) -> Optional[Dict[str, str]]:
        """
        Get information about a project.
        
        Args:
            project_path: Path to project (defaults to finding current project)
            
        Returns:
            Dictionary with project_id, project_path, project_name, scope
        """
        if project_path is None:
            project_path = self.find_project_root()
        
        if project_path is None:
            return None
        
        project_path = Path(project_path).resolve()
        
        return {
            'project_id': self.get_project_id(project_path),
            'project_path': str(project_path),
            'project_name': project_path.name,
            'scope': 'project'
        }
    
    @staticmethod
    def get_project_id(project_path: Path) -> str:
        """
        Generate consistent project ID from path.
        
        Args:
            project_path: Absolute path to project root
            
        Returns:
            32-character project ID
        """
        return hashlib.sha256(str(project_path).encode()).hexdigest()[:32]
    
    # ============================================================================
    # Scope Detection
    # ============================================================================
    
    def determine_scope(self, working_dir: Optional[str] = None) -> Tuple[str, Optional[Dict[str, str]]]:
        """
        Determine if we're in project or global scope.
        
        Args:
            working_dir: Working directory to check
            
        Returns:
            Tuple of (scope, project_info) where scope is 'project' or 'global'
        """
        project_root = self.find_project_root(working_dir)
        
        if project_root:
            project_info = self.get_project_info(project_root)
            return ('project', project_info)
        else:
            return ('global', None)
    
    # ============================================================================
    # Directory Creation Helpers
    # ============================================================================
    
    def ensure_directories(self):
        """Ensure all required directories exist"""
        directories = [
            self.db_path.parent,
            self.config_path.parent,
            self.mcp_dir,
            self.logs_dir,
            self.sessions_dir,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    # ============================================================================
    # Debug and Diagnostic Information
    # ============================================================================
    
    def get_debug_info(self) -> Dict[str, any]:
        """
        Get debug information about current configuration.
        
        Returns:
            Dictionary with all configuration details
        """
        return {
            'environment_variables': {
                'CLAUDE_CONFIG_DIR': os.environ.get('CLAUDE_CONFIG_DIR', '(not set)'),
                'CLAUDE_PROJECT_DIR': os.environ.get('CLAUDE_PROJECT_DIR', '(not set)'),
                'CLAUDE_WORKING_DIR': os.environ.get('CLAUDE_WORKING_DIR', '(not set)'),
            },
            'resolved_paths': {
                'global_claude_dir': str(self.global_claude_dir),
                'db_path': str(self.db_path),
                'config_path': str(self.config_path),
                'mcp_dir': str(self.mcp_dir),
            },
            'project_detection': {
                'current_project': str(self.find_project_root()) if self.find_project_root() else None,
                'from_env': str(self.claude_project_dir) if self.claude_project_dir else None,
                'workspace': str(self.claude_working_dir) if self.claude_working_dir else None,
            },
            'cache_stats': {
                'cached_projects': len(self._project_cache),
                'cache_entries': list(self._project_cache.keys()),
            }
        }


# ============================================================================
# Singleton Instance
# ============================================================================

# Create a singleton instance for easy import
env_config = EnvironmentConfig()


# ============================================================================
# Convenience Functions
# ============================================================================

def get_claude_config_dir() -> Path:
    """Get Claude configuration directory"""
    return env_config.claude_config_dir


def get_project_root(working_dir: Optional[str] = None) -> Optional[Path]:
    """Find current project root"""
    return env_config.find_project_root(working_dir)


def get_db_path() -> Path:
    """Get database path"""
    return env_config.db_path


def get_config_path() -> Path:
    """Get configuration file path"""
    return env_config.config_path


if __name__ == "__main__":
    # Test/debug mode - print configuration
    import json
    config = EnvironmentConfig()
    print("Claude-Slack Environment Configuration")
    print("=" * 50)
    print(json.dumps(config.get_debug_info(), indent=2))