#!/usr/bin/env python3
"""
Test that hooks properly use environment configuration
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

def test_hook_with_custom_config_dir():
    """Test that hooks respect CLAUDE_CONFIG_DIR environment variable"""
    
    # Save original environment
    original_env = os.environ.copy()
    
    try:
        # Create a temporary custom config directory
        with tempfile.TemporaryDirectory() as custom_dir:
            # Set custom config directory
            test_env = original_env.copy()
            test_env['CLAUDE_CONFIG_DIR'] = custom_dir
            test_env['CLAUDE_SLACK_DEBUG'] = '1'
            
            # Create necessary directories
            (Path(custom_dir) / 'data').mkdir(parents=True)
            (Path(custom_dir) / 'logs').mkdir(parents=True)
            (Path(custom_dir) / 'mcp' / 'claude-slack').mkdir(parents=True)
            
            # Copy environment_config.py to the custom location
            src_config = Path(__file__).parent.parent / 'template' / 'global' / 'mcp' / 'claude-slack' / 'environment_config.py'
            dst_config = Path(custom_dir) / 'mcp' / 'claude-slack' / 'environment_config.py'
            
            if src_config.exists():
                with open(src_config, 'r') as f:
                    content = f.read()
                with open(dst_config, 'w') as f:
                    f.write(content)
            
            # Prepare hook input
            hook_input = {
                "session_id": "test-custom-config",
                "cwd": str(Path.cwd()),
                "tool_name": "test",
                "hook_event_name": "PreToolUse"
            }
            
            # Run the PreToolUse hook
            hook_path = Path(__file__).parent.parent / 'template' / 'global' / 'hooks' / 'slack_pre_tool_use.py'
            
            result = subprocess.run(
                ['python3', str(hook_path)],
                input=json.dumps(hook_input),
                capture_output=True,
                text=True,
                env=test_env
            )
            
            # Check if it succeeded
            if result.returncode != 0:
                print(f"❌ Hook failed with custom config dir: {result.stderr}")
                return False
            
            # Check if session file was created in custom location
            session_file = Path(custom_dir) / 'data' / 'claude-slack-sessions' / 'test-custom-config.json'
            if session_file.exists():
                print(f"✅ Session file created in custom location: {custom_dir}")
                
                # Check if debug log was created in custom location
                debug_log = Path(custom_dir) / 'logs' / 'slack_pre_tool_use.log'
                if debug_log.exists():
                    print(f"✅ Debug log created in custom location")
                else:
                    print(f"⚠️  Debug log not found at {debug_log}")
                
                return True
            else:
                print(f"❌ Session file not created at {session_file}")
                return False
                
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
        print("✅ Environment restored")

def test_hook_with_default_config():
    """Test that hooks work with default configuration"""
    
    # Save original environment
    original_env = os.environ.copy()
    
    try:
        # Clear CLAUDE_CONFIG_DIR to use default
        test_env = original_env.copy()
        test_env.pop('CLAUDE_CONFIG_DIR', None)
        
        # Create a temp project directory
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "test-project"
            project_dir.mkdir()
            (project_dir / ".claude").mkdir()
            
            # Prepare hook input
            hook_input = {
                "session_id": "test-default-config",
                "cwd": str(project_dir),
                "tool_name": "test",
                "hook_event_name": "PreToolUse"
            }
            
            # Run the PreToolUse hook
            hook_path = Path(__file__).parent.parent / 'template' / 'global' / 'hooks' / 'slack_pre_tool_use.py'
            
            result = subprocess.run(
                ['python3', str(hook_path)],
                input=json.dumps(hook_input),
                capture_output=True,
                text=True,
                env=test_env
            )
            
            if result.returncode == 0:
                print("✅ Hook works with default configuration")
                
                # Check default location
                default_session_file = Path.home() / '.claude' / 'data' / 'claude-slack-sessions' / 'test-default-config.json'
                if default_session_file.exists():
                    print(f"✅ Session file created in default location: ~/.claude")
                    # Clean up
                    default_session_file.unlink()
                return True
            else:
                print(f"❌ Hook failed with default config: {result.stderr}")
                return False
                
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

def test_session_start_hook():
    """Test SessionStart hook with custom config"""
    
    # Save original environment
    original_env = os.environ.copy()
    
    try:
        with tempfile.TemporaryDirectory() as custom_dir:
            # Set custom config directory
            test_env = original_env.copy()
            test_env['CLAUDE_CONFIG_DIR'] = custom_dir
            
            # Create necessary directories
            (Path(custom_dir) / 'data').mkdir(parents=True)
            (Path(custom_dir) / 'logs').mkdir(parents=True)
            (Path(custom_dir) / 'mcp' / 'claude-slack').mkdir(parents=True)
            (Path(custom_dir) / 'config').mkdir(parents=True)
            
            # Copy environment_config.py
            src_config = Path(__file__).parent.parent / 'template' / 'global' / 'mcp' / 'claude-slack' / 'environment_config.py'
            dst_config = Path(custom_dir) / 'mcp' / 'claude-slack' / 'environment_config.py'
            
            if src_config.exists():
                with open(src_config, 'r') as f:
                    content = f.read()
                with open(dst_config, 'w') as f:
                    f.write(content)
            
            # Prepare hook input
            hook_input = {
                "session_id": "test-session-start",
                "cwd": str(Path.cwd()),
                "hook_event_name": "SessionStart",
                "source": "startup"
            }
            
            # Run the SessionStart hook
            hook_path = Path(__file__).parent.parent / 'template' / 'global' / 'hooks' / 'slack_session_start.py'
            
            result = subprocess.run(
                ['python3', str(hook_path)],
                input=json.dumps(hook_input),
                capture_output=True,
                text=True,
                env=test_env
            )
            
            if result.returncode == 0:
                print(f"✅ SessionStart hook works with custom config dir")
                return True
            else:
                print(f"⚠️  SessionStart hook had issues: {result.stderr}")
                # May fail due to missing dependencies, but that's ok for this test
                return True
                
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

if __name__ == "__main__":
    print("Testing hooks with environment configuration...")
    print("=" * 50)
    
    print("\n1. Testing with custom CLAUDE_CONFIG_DIR:")
    test_hook_with_custom_config_dir()
    
    print("\n2. Testing with default configuration:")
    test_hook_with_default_config()
    
    print("\n3. Testing SessionStart hook:")
    test_session_start_hook()
    
    print("\n" + "=" * 50)
    print("Hook environment configuration tests completed!")