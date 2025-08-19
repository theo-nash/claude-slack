#!/usr/bin/env python3
"""
Test suite for the centralized environment configuration module
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the MCP directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'template' / 'global' / 'mcp' / 'claude-slack'))

from environment_config import EnvironmentConfig, env_config


class TestEnvironmentConfig(unittest.TestCase):
    """Test the EnvironmentConfig class"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = EnvironmentConfig()
        self.original_env = os.environ.copy()
    
    def tearDown(self):
        """Clean up after tests"""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_default_claude_config_dir(self):
        """Test default configuration directory without environment variable"""
        # Clear any existing CLAUDE_CONFIG_DIR
        os.environ.pop('CLAUDE_CONFIG_DIR', None)
        
        config_dir = self.config.claude_config_dir
        expected = Path.home() / '.claude'
        self.assertEqual(config_dir, expected)
    
    def test_custom_claude_config_dir(self):
        """Test custom configuration directory from environment variable"""
        custom_dir = '/custom/claude/config'
        os.environ['CLAUDE_CONFIG_DIR'] = custom_dir
        
        # Create new instance to pick up env change
        config = EnvironmentConfig()
        self.assertEqual(str(config.claude_config_dir), custom_dir)
    
    def test_claude_project_dir_not_set(self):
        """Test when CLAUDE_PROJECT_DIR is not set"""
        os.environ.pop('CLAUDE_PROJECT_DIR', None)
        
        config = EnvironmentConfig()
        self.assertIsNone(config.claude_project_dir)
    
    def test_claude_project_dir_set(self):
        """Test when CLAUDE_PROJECT_DIR is set"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['CLAUDE_PROJECT_DIR'] = tmpdir
            
            config = EnvironmentConfig()
            self.assertEqual(str(config.claude_project_dir), tmpdir)
    
    def test_path_resolution_default(self):
        """Test path resolution with default configuration"""
        os.environ.pop('CLAUDE_CONFIG_DIR', None)
        
        config = EnvironmentConfig()
        home = Path.home()
        
        self.assertEqual(config.db_path, home / '.claude' / 'data' / 'claude-slack.db')
        self.assertEqual(config.config_path, home / '.claude' / 'config' / 'claude-slack.config.yaml')
        self.assertEqual(config.mcp_dir, home / '.claude' / 'mcp' / 'claude-slack')
        self.assertEqual(config.logs_dir, home / '.claude' / 'logs')
    
    def test_path_resolution_custom(self):
        """Test path resolution with custom CLAUDE_CONFIG_DIR"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['CLAUDE_CONFIG_DIR'] = tmpdir
            
            config = EnvironmentConfig()
            base = Path(tmpdir)
            
            self.assertEqual(config.db_path, base / 'data' / 'claude-slack.db')
            self.assertEqual(config.config_path, base / 'config' / 'claude-slack.config.yaml')
            self.assertEqual(config.mcp_dir, base / 'mcp' / 'claude-slack')
    
    def test_find_project_with_env_var(self):
        """Test project detection when CLAUDE_PROJECT_DIR is set"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'my-project'
            project_dir.mkdir()
            (project_dir / '.claude').mkdir()
            
            os.environ['CLAUDE_PROJECT_DIR'] = str(project_dir)
            
            config = EnvironmentConfig()
            found = config.find_project_root()
            
            self.assertEqual(found, project_dir)
    
    def test_find_project_walk_up(self):
        """Test project detection by walking up directory tree"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project structure
            project_dir = Path(tmpdir) / 'project'
            deep_dir = project_dir / 'src' / 'lib' / 'utils'
            deep_dir.mkdir(parents=True)
            (project_dir / '.claude').mkdir()
            
            # Clear environment variable
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
            
            config = EnvironmentConfig()
            found = config.find_project_root(str(deep_dir))
            
            self.assertEqual(found, project_dir)
    
    def test_find_project_none(self):
        """Test project detection when no project exists"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
            
            config = EnvironmentConfig()
            found = config.find_project_root(tmpdir)
            
            self.assertIsNone(found)
    
    def test_workspace_project_detection(self):
        """Test finding projects in a workspace"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create multiple projects
            project1 = workspace / 'project1'
            project2 = workspace / 'project2'
            project1.mkdir()
            project2.mkdir()
            (project1 / '.claude').mkdir()
            (project2 / '.claude').mkdir()
            
            os.environ['CLAUDE_WORKING_DIR'] = str(workspace)
            
            config = EnvironmentConfig()
            projects = config._find_projects_in_workspace(workspace)
            
            self.assertEqual(len(projects), 2)
            self.assertIn(project1, projects)
            self.assertIn(project2, projects)
    
    def test_project_info_generation(self):
        """Test project information generation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'test-project'
            project_dir.mkdir()
            (project_dir / '.claude').mkdir()
            
            config = EnvironmentConfig()
            info = config.get_project_info(project_dir)
            
            self.assertIsNotNone(info)
            self.assertEqual(info['project_name'], 'test-project')
            self.assertEqual(info['project_path'], str(project_dir))
            self.assertEqual(info['scope'], 'project')
            self.assertIsNotNone(info['project_id'])
            self.assertEqual(len(info['project_id']), 32)
    
    def test_scope_detection_project(self):
        """Test scope detection in a project"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.claude').mkdir()
            
            config = EnvironmentConfig()
            scope, info = config.determine_scope(str(project_dir))
            
            self.assertEqual(scope, 'project')
            self.assertIsNotNone(info)
            self.assertEqual(info['project_name'], 'project')
    
    def test_scope_detection_global(self):
        """Test scope detection outside a project"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EnvironmentConfig()
            scope, info = config.determine_scope(tmpdir)
            
            self.assertEqual(scope, 'global')
            self.assertIsNone(info)
    
    def test_cache_functionality(self):
        """Test that project detection caching works"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.claude').mkdir()
            
            config = EnvironmentConfig()
            
            # First call should cache
            result1 = config._walk_up_for_project(project_dir)
            self.assertEqual(result1, project_dir)
            
            # Check cache was populated
            cache_key = str(project_dir)
            self.assertIn(cache_key, config._project_cache)
            
            # Second call should use cache
            result2 = config._walk_up_for_project(project_dir)
            self.assertEqual(result2, result1)
    
    def test_debug_info(self):
        """Test debug information generation"""
        config = EnvironmentConfig()
        debug_info = config.get_debug_info()
        
        self.assertIn('environment_variables', debug_info)
        self.assertIn('resolved_paths', debug_info)
        self.assertIn('project_detection', debug_info)
        self.assertIn('cache_stats', debug_info)
    
    def test_ensure_directories(self):
        """Test directory creation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['CLAUDE_CONFIG_DIR'] = tmpdir
            
            config = EnvironmentConfig()
            config.ensure_directories()
            
            # Check that directories were created
            self.assertTrue(config.db_path.parent.exists())
            self.assertTrue(config.config_path.parent.exists())
            self.assertTrue(config.mcp_dir.exists())
            self.assertTrue(config.logs_dir.exists())
            self.assertTrue(config.sessions_dir.exists())


class TestConvenienceFunctions(unittest.TestCase):
    """Test the convenience functions"""
    
    def test_convenience_imports(self):
        """Test that convenience functions are importable"""
        from environment_config import (
            get_claude_config_dir,
            get_project_root,
            get_db_path,
            get_config_path
        )
        
        # Test they return expected types
        self.assertIsInstance(get_claude_config_dir(), Path)
        self.assertIsInstance(get_db_path(), Path)
        self.assertIsInstance(get_config_path(), Path)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)